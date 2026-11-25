import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:judge_helper/main.dart';
import 'package:judge_helper/client.dart';

void main() {
  testWidgets('Судья видит варианты входа и восстановления', (tester) async {
    await tester.pumpWidget(JudgeApp(client: Client()));
    expect(find.text('Email'), findsOneWidget);
    expect(find.text('Пароль'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Войти'), findsOneWidget);
    expect(find.text('Яндекс ID'), findsOneWidget);
    expect(find.text('Восстановить пароль'), findsOneWidget);
  });
}
