import 'dart:convert';
import 'dart:math';
import 'package:sqflite/sqflite.dart';

typedef Json = Map<String, dynamic>;

class ApiError implements Exception {
  final int status;
  final String detail;
  ApiError(this.status, this.detail);
  @override
  String toString() => detail;
}

String operationId() {
  final random = Random.secure();
  final b = List.generate(16, (_) => random.nextInt(256));
  b[6] = (b[6] & 15) | 64;
  b[8] = (b[8] & 63) | 128;
  final h = b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();
  return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}-${h.substring(16, 20)}-${h.substring(20)}';
}

mixin ScoreQueue {
  Database get db;
  String get email;
  Future<void> postScore(String path, Json body);
  bool syncing = false;
  bool offline = false;
  Future<List<Json>> pending(String event) => db.query(
    'queue',
    where: 'owner=? AND event=?',
    whereArgs: [email, event],
  );
  Future<void> enqueue(
    String event,
    String number,
    dynamic technique,
    dynamic artistry,
    int version,
  ) async {
    final op = operationId();
    final body = {
      'technique': technique,
      'artistry': artistry,
      'operation': op,
      'version': version,
    };
    await db.insert('queue', {
      'op': op,
      'owner': email,
      'event': event,
      'number': number,
      'body': jsonEncode(body),
    });
  }

  Future<void> sync() async {
    if (syncing || email.isEmpty) return;
    syncing = true;
    try {
      final rows = await db.query(
        'queue',
        where: 'owner=? AND error IS NULL',
        whereArgs: [email],
      );
      for (final row in rows) {
        if (row['owner'] != email) return;
        try {
          await postScore(
            '/events/${row['event']}/scores/${row['number']}',
            jsonDecode(row['body'] as String),
          );
          await db.delete('queue', where: 'op=?', whereArgs: [row['op']]);
          offline = false;
        } on ApiError catch (e) {
          if (e.status >= 500 || e.status == 401) return;
          await db.update(
            'queue',
            {'error': e.detail},
            where: 'op=?',
            whereArgs: [row['op']],
          );
        } on Exception {
          offline = true;
          return;
        }
      }
    } finally {
      syncing = false;
    }
  }
}
