import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'score_queue.dart';
export 'score_queue.dart';
import 'dart:typed_data';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:sqflite/sqflite.dart';

class Client with ScoreQueue {
  final String base;
  final http.Client httpClient;
  Client({String? endpoint, http.Client? transport})
    : base =
          endpoint ??
          const String.fromEnvironment(
            'API_URL',
            defaultValue: 'http://127.0.0.1:8000',
          ),
      httpClient = transport ?? http.Client();
  Json session = {};
  static const vault = FlutterSecureStorage();
  @override
  late Database db;

  @override
  String get email => session['email'] ?? '';
  Future<void> init() async {
    db = await openDatabase(
      '${await getDatabasesPath()}/judge.db',
      version: 1,
      onCreate: (d, _) async {
        await d.execute(
          'CREATE TABLE cache(owner TEXT, path TEXT, value TEXT, PRIMARY KEY(owner,path))',
        );
        await d.execute(
          'CREATE TABLE queue(op TEXT PRIMARY KEY, owner TEXT, event TEXT, number TEXT, body TEXT, error TEXT, UNIQUE(owner,event,number))',
        );
      },
    );
    session = jsonDecode(await vault.read(key: 'session') ?? '{}');
  }

  Future<void> signIn(Json value) async {
    session = value;
    await vault.write(key: 'session', value: jsonEncode(value));
  }

  Future<dynamic> api(
    String path, {
    String method = 'GET',
    Object? data,
    Uint8List? bytes,
    bool pdf = false,
  }) async {
    final request = http.Request(method, Uri.parse('$base$path'));
    if (session['token'] != null) {
      request.headers['Authorization'] = 'Bearer ${session['token']}';
    }
    if (bytes != null) {
      request.bodyBytes = bytes;
    } else if (data != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(data);
    }
    final response = await http.Response.fromStream(
      await httpClient.send(request).timeout(const Duration(seconds: 15)),
    );
    if (response.statusCode >= 400) {
      throw ApiError(
        response.statusCode,
        '${jsonDecode(utf8.decode(response.bodyBytes))['detail']}',
      );
    }
    return pdf
        ? response.bodyBytes
        : jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<dynamic> cached(String path) async {
    final owner = email;
    try {
      final value = await api(path);
      await db.insert('cache', {
        'owner': owner,
        'path': path,
        'value': jsonEncode(value),
      }, conflictAlgorithm: ConflictAlgorithm.replace);
      offline = false;
      return value;
    } on ApiError {
      rethrow;
    } on Exception {
      offline = true;
      final row = await db.query(
        'cache',
        where: 'owner=? AND path=?',
        whereArgs: [owner, path],
      );
      if (row.isEmpty) rethrow;
      return jsonDecode(row.single['value'] as String);
    }
  }

  @override
  Future<void> postScore(String path, Json body) async {
    await api(path, method: "POST", data: body);
  }

  Future<WebSocket> updates(String id) async {
    final url = Uri.parse('$base/events/$id/updates');
    final socket = await WebSocket.connect(
      url.replace(scheme: url.scheme == 'https' ? 'wss' : 'ws').toString(),
    );
    socket.add(session['token']);
    return socket;
  }
}
