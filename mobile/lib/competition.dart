import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';
import 'client.dart';
import 'results.dart';

const groups = ['Дети', 'Юниоры', 'Взрослые', 'Ветераны'];
const states = {
  'draft': 'Черновик',
  'active': 'Идёт',
  'finished': 'Завершено',
  'approved': 'Утверждено',
};
Future<Map<String, String>?> fields(
  BuildContext context,
  String title,
  Map<String, String> values,
) async {
  final result = {...values};
  return showDialog<Map<String, String>>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final e in values.entries)
              TextFormField(
                initialValue: e.value,
                decoration: InputDecoration(labelText: e.key),
                onChanged: (v) => result[e.key] = v,
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(ctx, result),
          child: const Text('Сохранить'),
        ),
      ],
    ),
  );
}

Future<void> editEvent(BuildContext context, Client c, [Json? event]) async {
  final f = await fields(context, 'Соревнование', {
    'Название': event?['title'] ?? '',
    'Дата (ГГГГ-ММ-ДД)':
        event?['date'] ?? DateTime.now().toIso8601String().substring(0, 10),
    'Место': event?['venue'] ?? '',
    'Email судей через запятую': event?['judges'].join(', ') ?? '',
    'Email главного судьи': event?['chief'] ?? '',
    'Возраст начала категорий': event?['boundaries'].join(', ') ?? '13, 18, 40',
  });
  if (f == null) return;
  await c.api(
    event == null ? '/events' : '/events/${event['id']}',
    method: event == null ? 'POST' : 'PUT',
    data: {
      'title': f['Название'],
      'date': f['Дата (ГГГГ-ММ-ДД)'],
      'venue': f['Место'],
      'judges': f['Email судей через запятую']!
          .split(',')
          .map((s) => s.trim())
          .toList(),
      'chief': f['Email главного судьи'],
      'boundaries': f['Возраст начала категорий']!
          .split(',')
          .map((s) => int.parse(s.trim()))
          .toList(),
    },
  );
}

class CompetitionPage extends StatefulWidget {
  final Client client;
  final String id;
  const CompetitionPage({super.key, required this.client, required this.id});
  @override
  State<CompetitionPage> createState() => _CompetitionPageState();
}

class _CompetitionPageState extends State<CompetitionPage> {
  Json? event;
  List<Json> queue = [];
  String error = '', sort = 'rank';
  bool fetching = false, ascending = true, working = false, connecting = false;
  int tab = 0, group = 0;
  Timer? timer;
  WebSocket? socket;
  Client get c => widget.client;
  String get path => '/events/${widget.id}';
  @override
  void initState() {
    super.initState();
    refresh();
    connect();
    timer = Timer.periodic(const Duration(seconds: 4), (_) {
      refresh();
      connect();
    });
  }

  Future<void> connect() async {
    if (connecting || socket != null) return;
    connecting = true;
    try {
      final ws = await c.updates(widget.id);
      if (!mounted) {
        await ws.close();
        return;
      }
      socket = ws;
      ws.listen(
        (_) => refresh(),
        onDone: () {
          socket = null;
        },
        onError: (Object _) {
          socket = null;
        },
        cancelOnError: true,
      );
    } catch (_) {
      /* Refresh retries when connectivity returns. */
    } finally {
      connecting = false;
    }
  }

  Future<void> refresh() async {
    if (fetching) return;
    fetching = true;
    try {
      await c.sync();
      final value = await c.cached(path);
      final pending = await c.pending(widget.id);
      if (mounted) {
        setState(() {
          event = value;
          queue = pending;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      fetching = false;
    }
  }

  Future<void> run(Future<void> Function() work) async {
    if (working) return;
    setState(() {
      working = true;
      error = '';
    });
    try {
      await work();
      await refresh();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => working = false);
    }
  }

  @override
  void dispose() {
    timer?.cancel();
    socket?.close();
    super.dispose();
  }

  Future<void> person([Json? p]) async {
    final f = await fields(context, 'Участник', {
      'Стартовый номер': '${p?['number'] ?? ''}',
      'Фамилия': p?['surname'] ?? '',
      'Имя': p?['name'] ?? '',
      'Дата рождения': p?['birth'] ?? '',
      'Клуб': p?['club'] ?? '',
      'Комментарий': p?['comment'] ?? '',
      'Согласие представителя (да/нет)': p?['consent'] == true ? 'да' : 'нет',
    });
    if (f == null) return;
    await c.api(
      '$path/participants${p == null ? '' : '?original=${p['number']}'}',
      method: 'POST',
      data: {
        'number': int.parse(f['Стартовый номер']!),
        'surname': f['Фамилия'],
        'name': f['Имя'],
        'birth': f['Дата рождения'],
        'club': f['Клуб'],
        'comment': f['Комментарий'],
        'consent': f['Согласие представителя (да/нет)']!.toLowerCase() == 'да',
      },
    );
  }

  Future<void> importFile() async {
    final file = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['xlsx'],
      withData: true,
    );
    if (file == null) return;
    final bytes = file.files.single.bytes!;
    final preview = await c.api('$path/import', method: 'POST', bytes: bytes);
    if (!mounted) return;
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Предпросмотр импорта'),
        content: SingleChildScrollView(
          child: Text(
            [
              for (final p in preview['valid'])
                "${p['number']}. ${p['surname']} ${p['name']}",
              for (final e in preview['errors'])
                "Строка ${e['row']}: ${e['error']}",
            ].join('\n'),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Добавить корректные строки'),
          ),
        ],
      ),
    );
    if (yes == true) {
      await c.api('$path/import?confirm=true', method: 'POST', bytes: bytes);
    }
  }

  Future<void> mark(String n) async {
    final scores = event!['scores'][n] ?? {};
    final own = scores[c.email];
    final pending = queue.where((q) => q['number'] == n).firstOrNull;
    if (pending != null) {
      final local = jsonDecode(pending['body']);
      if (pending['error'] == null) {
        throw StateError('Оценка ожидает отправки');
      }
      final response = await showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Конфликт версий'),
          content: Text(
            "Локально: ${local['technique']} / ${local['artistry']}\nНа сервере: ${own == null ? '—' : '${own['t'] / 10} / ${own['a'] / 10}'}\n${pending['error']}",
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, 'server'),
              child: const Text('Принять серверную'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(ctx, 'request'),
              child: const Text('Запросить исправление'),
            ),
            if (event!['corrections'][n]?[c.email]?['approved'] == true)
              TextButton(
                onPressed: () => Navigator.pop(ctx, 'retry'),
                child: const Text('Отправить локальную'),
              ),
          ],
        ),
      );
      if (response == 'server') {
        await c.db.delete('queue', where: 'op=?', whereArgs: [pending['op']]);
      }
      if (response == 'request') await requestCorrection(n);
      if (response == 'retry') {
        local['version'] = own['version'];
        local['operation'] = operationId();
        await c.db.update(
          'queue',
          {'body': jsonEncode(local), 'op': local['operation'], 'error': null},
          where: 'op=?',
          whereArgs: [pending['op']],
        );
      }
      return;
    }
    if (own != null &&
        event!['corrections'][n]?[c.email]?['approved'] != true) {
      await requestCorrection(n);
      return;
    }
    final f = await fields(context, 'Оценка №$n', {
      'Техника': own == null ? '' : '${own['t'] / 10}',
      'Артистизм': own == null ? '' : '${own['a'] / 10}',
    });
    if (f == null || !mounted) return;
    final t = f['Техника']!.replaceAll(',', '.'),
        a = f['Артистизм']!.replaceAll(',', '.');
    if (![
      t,
      a,
    ].every((s) => RegExp(r'^(10([.]0)?|[0-9]([.][0-9])?)$').hasMatch(s))) {
      throw const FormatException('Введите от 0 до 10 с шагом 0,1');
    }
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Подтвердите оценки'),
        content: Text('Техника $t · Артистизм $a'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена'),
          ),
          Semantics(
            identifier:
                const bool.fromEnvironment('DEMO_RENAMED_BUTTON') && n != '1'
                ? 'confirm_marks'
                : 'score_confirm',
            child: FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Отправить оценку'),
            ),
          ),
        ],
      ),
    );
    if (yes == true) await c.enqueue(widget.id, n, t, a, own?['version'] ?? 0);
  }

  Future<void> requestCorrection(String n) async {
    final f = await fields(context, 'Запросить исправление', {'Причина': ''});
    if (f != null) {
      await c.api(
        '$path/corrections/$n',
        method: 'POST',
        data: {'reason': f['Причина']},
      );
    }
  }

  Widget button(String label, Future<void> Function() action) => OutlinedButton(
    onPressed: working ? null : () => run(action),
    child: Text(label),
  );
  Future<void> change(String action) =>
      c.api('$path/actions/$action', method: 'POST');
  Future<void> pdf() async {
    final Uint8List bytes = await c.api('$path/protocol.pdf', pdf: true);
    final file = File(
      '${(await getApplicationDocumentsDirectory()).path}/protocol-${widget.id}.pdf',
    );
    await file.writeAsBytes(bytes);
    await OpenFilex.open(file.path);
  }

  @override
  Widget build(BuildContext context) {
    final e = event;
    final owner = e?['owner'] == c.email, chief = e?['chief'] == c.email;
    return Scaffold(
      appBar: AppBar(title: Text(e?['title'] ?? 'Соревнование')),
      bottomNavigationBar: NavigationBar(
        selectedIndex: tab,
        onDestinationSelected: (v) => setState(() => tab = v),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.groups_outlined),
            label: 'Участники',
          ),
          NavigationDestination(
            icon: Icon(Icons.leaderboard_outlined),
            label: 'Результаты',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            label: 'Протокол',
          ),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (error.isNotEmpty)
              Text(
                error,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            if (e == null || working) const LinearProgressIndicator(),
            if (e != null) ...[
              Text(
                '${e['date']} · ${e['venue']} · ${states[e['state']]}',
                style: Theme.of(context).textTheme.titleMedium,
              ),
              Text(
                c.offline
                    ? 'Без сети · в очереди ${queue.length}'
                    : 'На связи · в очереди ${queue.length}',
              ),
              if (c.lastSync != null)
                Text(
                  'Синхронизация ${TimeOfDay.fromDateTime(c.lastSync!).format(context)}',
                ),
              if (e['next'] != null && e['state'] == 'active')
                Text("Вызван участник №${e['next']}"),
              if (tab == 0) ...[
                Wrap(
                  spacing: 8,
                  children: [
                    if (owner && e['state'] == 'draft') ...[
                      button('Настройки', () => editEvent(context, c, e)),
                      button('Добавить участника', person),
                      button('Импорт Excel', importFile),
                      button('Начать', () => change('start')),
                    ],
                    if (owner && e['state'] == 'active')
                      button('Завершить', () => change('finish')),
                  ],
                ),
                for (final p in e['participants'].values)
                  Card(
                    child: ListTile(
                      title: Text(
                        "${p['number']}. ${p['surname']} ${p['name']}",
                      ),
                      subtitle: Text(
                        [
                          groups[p['category']],
                          p['club'],
                          'Оценили: ${(e['progress']['${p['number']}'] ?? []).length}/${e['judges'].length}',
                          for (final q in queue.where(
                            (q) => q['number'] == '${p['number']}',
                          ))
                            q['error'] ?? 'Сохранена локально',
                          for (final s
                              in (e['scores']['${p['number']}'] as Map? ?? {})
                                  .entries)
                            '${s.key}: ${s.value['t'] / 10} / ${s.value['a'] / 10}',
                        ].join(' · '),
                      ),
                      onTap: () => run(() async {
                        if (owner && e['state'] == 'draft') {
                          await person(p);
                        } else if (e['state'] == 'active' &&
                            e['judges'].contains(c.email)) {
                          await mark('${p['number']}');
                        }
                      }),
                      trailing: (chief || owner) && e['state'] == 'active'
                          ? IconButton(
                              tooltip: 'Вызвать участника',
                              icon: const Icon(Icons.campaign_outlined),
                              onPressed: () => run(
                                () => change("next?number=${p['number']}"),
                              ),
                            )
                          : null,
                    ),
                  ),
                if (chief)
                  for (final entry in (e['corrections'] as Map).entries)
                    for (final req in (entry.value as Map).entries)
                      if (req.value['approved'] == false)
                        button(
                          'Разрешить №${entry.key} · ${req.key}: ${req.value['reason']}',
                          () async {
                            await c.api(
                              '$path/corrections/${entry.key}',
                              method: 'POST',
                              data: {'approve': true, 'judge': req.key},
                            );
                          },
                        ),
              ],
              if (tab == 0 && (e['audit'] as List).isNotEmpty)
                ExpansionTile(
                  title: const Text('История исправлений'),
                  children: [
                    for (final a in e['audit'])
                      ListTile(
                        title: Text("№${a['number']} · ${a['judge']}"),
                        subtitle: Text(
                          "${a['old']['t'] / 10} / ${a['old']['a'] / 10} → ${a['new'][0] / 10} / ${a['new'][1] / 10}\n${a['reason']} · ${a['time']}",
                        ),
                      ),
                  ],
                ),
              if (tab == 1) ...resultWidgets(e),
              if (tab == 2)
                Wrap(
                  spacing: 8,
                  children: [
                    if (chief && e['state'] == 'finished')
                      button('Сформировать PDF', () => change('protocol')),
                    if (chief &&
                        e['state'] == 'finished' &&
                        e['draft_protocol'] == true)
                      button('Утвердить', () => change('approve')),
                    if (e['state'] == 'approved' ||
                        chief && e['draft_protocol'] == true)
                      button('Открыть PDF', pdf),
                    if (chief && e['state'] == 'approved')
                      button('Отправить по email', () async {
                        final f = await fields(context, 'Отправка протокола', {
                          'Email': '',
                        });
                        if (f != null) {
                          await c.api(
                            '$path/email',
                            method: 'POST',
                            data: {'email': f['Email']},
                          );
                        }
                      }),
                    if (e['state'] == 'active' || e['state'] == 'draft')
                      const Text(
                        'Протокол будет доступен после завершения соревнования.',
                      ),
                  ],
                ),
            ],
          ],
        ),
      ),
    );
  }

  List<Widget> resultWidgets(Json e) {
    final rows = sortedResults(e['results'], group, sort, ascending);
    const columns = {
      'rank': 'Место',
      'name': 'Участник',
      'club': 'Клуб',
      'technique': 'Техника',
      'artistry': 'Артистизм',
      'total': 'Итог',
    };
    final distribution = e['charts']['distribution']['$group'] ?? [];
    final deviations = e['charts']['deviations']['$group'] as Map? ?? {};
    return [
      DropdownButton<int>(
        value: group,
        items: [
          for (int i = 0; i < 4; i++)
            DropdownMenuItem(value: i, child: Text(groups[i])),
        ],
        onChanged: (v) => setState(() => group = v!),
      ),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columns: [
            for (final col in columns.entries)
              DataColumn(
                label: Text(col.value),
                onSort: (_, v) => setState(() {
                  ascending = sort == col.key ? !ascending : true;
                  sort = col.key;
                }),
              ),
          ],
          rows: [
            for (final row in rows)
              DataRow(
                cells: [
                  for (final col in columns.keys) DataCell(Text('${row[col]}')),
                ],
              ),
          ],
        ),
      ),
      const Text('Распределение итоговых баллов'),
      for (int i = 0; i < 10; i++)
        Builder(
          builder: (_) {
            final count = (distribution as List)
                .where((v) => v >= i && (i == 9 ? v <= 10 : v < i + 1))
                .length;
            return ListTile(
              title: Text('$i–${i + 1} · $count'),
              subtitle: LinearProgressIndicator(
                value: rows.isEmpty ? 0 : count / rows.length,
              ),
            );
          },
        ),
      const Text('Отклонение судей от среднего'),
      for (final d in deviations.entries)
        ListTile(
          title: Text('${d.key}: ${d.value}'),
          subtitle: LinearProgressIndicator(value: (d.value as num).abs() / 10),
        ),
    ];
  }
}
