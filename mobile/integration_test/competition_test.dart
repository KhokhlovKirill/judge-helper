import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:judge_helper/main.dart';
import 'package:judge_helper/client.dart';

class TestConnection extends http.BaseClient {
  final http.Client network = http.Client();
  bool connected = true;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    if (!connected) throw const SocketException("offline");
    return network.send(request);
  }
}

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('JUDGE-44 вход → соревнование → оценка → сервер', (tester) async {
    final network = TestConnection();
    var client = Client(transport: network);
    await client.init();
    await client.signIn({});
    await tester.pumpWidget(JudgeApp(client: client));
    Future<void> until(Finder f) async {
      for (int i = 0; i < 150 && f.evaluate().isEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(f, findsWidgets);
    }

    await tester.enterText(find.byType(TextField).at(0), 'mobile@example.test');
    await tester.enterText(find.byType(TextField).at(1), 'Contest123');
    await tester.tap(find.text('Войти'));
    final title = find.text('Мобильная приёмка');
    await until(title);
    await tester.tap(title);
    final person = find.text('1. Тестов Участник 1');
    await until(person);
    await tester.ensureVisible(person);
    network.connected = false;
    await tester.tap(person);
    await until(find.byType(TextFormField));
    await tester.enterText(find.byType(TextFormField).at(0), '8.4');
    await tester.enterText(find.byType(TextFormField).at(1), '9');
    await tester.ensureVisible(find.text('Сохранить'));
    await tester.tap(find.text('Сохранить'));
    final confirm = find.text('Отправить оценку');
    await until(confirm);
    await tester.tap(confirm);
    await until(find.textContaining('Сохранена локально'));
    final eventList = await client.cached('/events');
    final eventId = eventList.single['id'];
    final original = (await client.pending(eventId)).single['op'];
    await tester.pumpWidget(const SizedBox());
    await client.db.close();
    client = Client(transport: network);
    await client.init();
    expect(client.email, 'mobile@example.test');
    expect((await client.pending(eventId)).single['op'], original);
    await tester.pumpWidget(JudgeApp(client: client));
    await until(title);
    await tester.tap(title);
    await until(person);
    network.connected = true;
    await until(find.textContaining('8.4 / 9.0'));
    final events = await client.api('/events');
    final item = await client.api('/events/${events.single['id']}');
    expect(item['scores']['1']['mobile@example.test']['t'], 84);
    expect(item['results'].single['total'], 8.64);
    await tester.tap(find.text('Результаты'));
    await until(find.text('Распределение итоговых баллов'));
    final url = '/events/$eventId';
    for (final action in ['finish', 'protocol', 'approve']) {
      await client.api('$url/actions/$action', method: 'POST');
    }
    final pdf = await client.api('$url/protocol.pdf', pdf: true);
    expect(ascii.decode(pdf.sublist(0, 5)), '%PDF-');
    expect(await client.pending(eventId), isEmpty);
    await tester.pumpWidget(const SizedBox());
  });
}
