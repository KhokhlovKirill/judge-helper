import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'client.dart';
import 'push.dart';
import 'competition.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final client = Client();
  await client.init();
  runApp(JudgeApp(client: client));
}

class JudgeApp extends StatelessWidget {
  final Client client;
  const JudgeApp({super.key, required this.client});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Помощник судьи',
    theme: ThemeData(
      colorSchemeSeed: const Color(0xff245b65),
      useMaterial3: true,
    ),
    home: Home(client: client),
  );
}

class Home extends StatefulWidget {
  final Client client;
  const Home({super.key, required this.client});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> {
  final address = TextEditingController(), password = TextEditingController();
  List events = [];
  bool busy = false;
  String error = '';
  Client get c => widget.client;
  @override
  void initState() {
    super.initState();
    if (c.email.isNotEmpty) {
      run(() async {
        await refresh();
        await PushDelivery.attach(c);
      });
    }
  }

  @override
  void dispose() {
    address.dispose();
    password.dispose();
    super.dispose();
  }

  Future<void> refresh() async {
    events = await c.cached('/events');
  }

  Future<void> run(Future<void> Function() f) async {
    setState(() {
      busy = true;
      error = '';
    });
    try {
      await f();
    } catch (e) {
      error = e.toString();
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> login() async {
    await c.signIn(
      await c.api(
        '/login',
        method: 'POST',
        data: {'email': address.text, 'password': password.text},
      ),
    );
    password.clear();
    await refresh();
    await PushDelivery.attach(c);
  }

  Future<void> yandex() async {
    final result = await c.api('/yandex', method: 'POST');
    await launchUrl(
      Uri.parse(result['url']),
      mode: LaunchMode.externalApplication,
    );
    for (int i = 0; i < 120; i++) {
      await Future<void>.delayed(const Duration(seconds: 3));
      if (!mounted) return;
      final s = await c.api(
        '/yandex/poll',
        method: 'POST',
        data: {'poll': result['poll']},
      );
      if (s['token'] != null) {
        await c.signIn(s);
        await PushDelivery.attach(c);
        await refresh();
        return;
      }
    }
    throw const HttpException('Время входа истекло');
  }

  @override
  Widget build(BuildContext context) {
    final logged = c.email.isNotEmpty;
    return Scaffold(
      appBar: AppBar(
        title: Text(logged ? 'Соревнования' : 'Помощник судьи'),
        actions: logged
            ? [
                IconButton(
                  tooltip: 'Обновить',
                  onPressed: () => run(refresh),
                  icon: const Icon(Icons.refresh),
                ),
                IconButton(
                  tooltip: 'Уведомления',
                  icon: const Icon(Icons.notifications_outlined),
                  onPressed: () => run(() async {
                    final prefs = Map<String, dynamic>.from(
                      await c.api('/preferences'),
                    );
                    if (!context.mounted) return;
                    await showDialog(
                      context: context,
                      builder: (ctx) => StatefulBuilder(
                        builder: (ctx, change) => AlertDialog(
                          title: const Text('Уведомления'),
                          content: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              for (final e in {
                                'assigned': 'Назначение',
                                'next': 'Вызов участника',
                                'scored': 'Оценки собраны',
                                'approved': 'Протокол утверждён',
                              }.entries)
                                SwitchListTile(
                                  title: Text(e.value),
                                  value: prefs[e.key],
                                  onChanged: (v) =>
                                      change(() => prefs[e.key] = v),
                                ),
                            ],
                          ),
                          actions: [
                            TextButton(
                              onPressed: () => Navigator.pop(ctx),
                              child: const Text('Готово'),
                            ),
                          ],
                        ),
                      ),
                    );
                    await c.api('/preferences', method: 'PUT', data: prefs);
                  }),
                ),
                IconButton(
                  tooltip: 'Выйти',
                  onPressed: () => run(() async {
                    await PushDelivery.detach(c);
                    await c.signIn({});
                    events = [];
                  }),
                  icon: const Icon(Icons.logout),
                ),
              ]
            : null,
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            if (busy) const LinearProgressIndicator(),
            if (error.isNotEmpty)
              Text(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (!logged) ...[
              TextField(
                controller: address,
                decoration: const InputDecoration(labelText: 'Email'),
                keyboardType: TextInputType.emailAddress,
              ),
              TextField(
                controller: password,
                decoration: const InputDecoration(labelText: 'Пароль'),
                obscureText: true,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: busy ? null : () => run(login),
                child: const Text('Войти'),
              ),
              TextButton(
                onPressed: busy ? null : () => run(yandex),
                child: const Text('Яндекс ID'),
              ),
              TextButton(
                onPressed: () => run(() async {
                  await c.api(
                    '/reset',
                    method: 'POST',
                    data: {'email': address.text},
                  );
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Проверьте почту')),
                    );
                  }
                }),
                child: const Text('Восстановить пароль'),
              ),
            ] else ...[
              if (c.session['organizer'] == true)
                Wrap(
                  spacing: 8,
                  children: [
                    OutlinedButton(
                      onPressed: () => run(() async {
                        final f = await fields(context, 'Пригласить судью', {
                          'Имя': '',
                          'Email': '',
                        });
                        if (f != null) {
                          await c.api(
                            '/invite',
                            method: 'POST',
                            data: {'email': f['Email'], 'name': f['Имя']},
                          );
                        }
                      }),
                      child: const Text('Пригласить судью'),
                    ),
                    FilledButton(
                      onPressed: () => run(() async {
                        await editEvent(context, c);
                        await refresh();
                      }),
                      child: const Text('Создать соревнование'),
                    ),
                  ],
                ),
              if (events.isEmpty && !busy)
                const Text('Назначенных соревнований пока нет'),
              for (final e in events)
                ListTile(
                  title: Text(e['title']),
                  subtitle: Text('${e['date']} · ${e['venue']}'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () async {
                    await Navigator.push(
                      context,
                      MaterialPageRoute(
                        builder: (_) => CompetitionPage(client: c, id: e['id']),
                      ),
                    );
                    if (mounted) run(refresh);
                  },
                ),
            ],
          ],
        ),
      ),
    );
  }
}
