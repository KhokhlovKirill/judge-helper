import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:judge_helper/main.dart';
import 'package:judge_helper/client.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();
  testWidgets('JUDGE-44 вход → соревнование → оценка → сервер', (tester) async {
    final client = Client();
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
    await tester.tap(person);
    await until(find.byType(TextFormField));
    await tester.enterText(find.byType(TextFormField).at(0), '8.4');
    await tester.enterText(find.byType(TextFormField).at(1), '9');
    await tester.tap(find.text('Сохранить'));
    final confirm = find.text('Отправить оценку');
    await until(confirm);
    await tester.tap(confirm);
    await until(find.textContaining('8.4 / 9.0'));
    final events = await client.api('/events');
    final item = await client.api('/events/${events.single['id']}');
    expect(item['scores']['1']['mobile@example.test']['t'], 84);
    expect(item['results'].single['total'], 8.64);
    await tester.tap(find.text('Результаты'));
    await until(find.text('Распределение итоговых баллов'));
    await tester.pumpWidget(const SizedBox());
  });
}
