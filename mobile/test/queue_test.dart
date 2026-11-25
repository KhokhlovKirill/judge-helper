import 'dart:io';
import 'package:flutter_test/flutter_test.dart';
import 'package:judge_helper/score_queue.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class TestQueue with ScoreQueue {
  @override
  final Database db;
  @override
  String email = 'judge';
  final Future<void> Function(String, Json) send;
  TestQueue(this.db, this.send);
  @override
  Future<void> postScore(String path, Json body) => send(path, body);
}

void main() {
  sqfliteFfiInit();
  late Directory dir;
  late Database db;
  late String path;
  setUp(() async {
    dir = await Directory.systemTemp.createTemp('judge-queue');
    path = '${dir.path}/queue.db';
    db = await databaseFactoryFfi.openDatabase(path);
    await db.execute(
      'CREATE TABLE queue(op TEXT PRIMARY KEY, owner TEXT, event TEXT, number TEXT, body TEXT, error TEXT, UNIQUE(owner,event,number))',
    );
  });
  tearDown(() async {
    await db.close();
    await dir.delete(recursive: true);
  });
  test('Офлайн, перезапуск, повторное подключение и защита от дубля', () async {
    final first = TestQueue(
      db,
      (_, _) async => throw const SocketException('offline'),
    );
    await first.enqueue('event', '7', 8.2, 9, 0);
    await first.sync();
    expect(first.offline, isTrue);
    final id = (await first.pending('event')).single['op'];
    await db.close();
    db = await databaseFactoryFfi.openDatabase(path);
    final seen = <String>[];
    final second = TestQueue(db, (url, b) async {
      expect(url, '/events/event/scores/7');
      expect(b['technique'], 8.2);
      seen.add(b['operation']);
    });
    await Future.wait([second.sync(), second.sync()]);
    await second.sync();
    expect(seen, [id]);
    expect(await second.pending('event'), isEmpty);
  });
  test(
    'Конфликт сохраняет данные, временные ошибки оставляют оценку в очереди',
    () async {
      int status = 503;
      final q = TestQueue(
        db,
        (_, _) async => throw ApiError(status, 'версии различаются'),
      );
      await q.enqueue('e', '1', 9, 9, 0);
      for (final code in [503, 401]) {
        status = code;
        await q.sync();
        expect((await q.pending('e')).single['error'], isNull);
      }
      status = 409;
      await q.sync();
      expect((await q.pending('e')).single['error'], 'версии различаются');
      expect(ApiError(409, 'конфликт').toString(), 'конфликт');
      q.email = '';
      await q.sync();
      expect(await q.pending('e'), isEmpty);
    },
  );
  test(
    'Смена пользователя во время отправки сохраняет его остальные записи',
    () async {
      late TestQueue q;
      q = TestQueue(db, (_, _) async {
        q.email = 'другой';
      });
      await q.enqueue('e', '1', 1, 2, 0);
      await q.enqueue('e', '2', 3, 4, 0);
      await q.sync();
      q.email = 'judge';
      expect((await q.pending('e')).length, 1);
    },
  );
}
