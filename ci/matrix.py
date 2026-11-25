"""Trace Jira cases to executable checks. Validate the entire catalog on each PR."""

import ast
from pathlib import Path

API = "tests/test_api.py"
DOMAIN = "tests/test_domain.py"
INTEGRATIONS = "tests/test_integrations.py"
MOBILE = "mobile/integration_test/competition_test.dart"
QUEUE = "mobile/test/queue_test.dart"


def unit(path, name):
    return ("server", path, name)


auth = unit(API, "test_invite_password_reset")
roles = unit(API, "test_access_edit")
flow = unit(API, "test_flow_pdf_and_visibility")
rank = unit(DOMAIN, "test_ranking")
limit = unit(API, "test_excel_limit")
reconnect = unit(API, "test_concurrent_reconnect")
device = ("mobile", MOBILE, "JUDGE-44 вход")
offline = ("flutter", QUEUE, "Офлайн, перезапуск")
conflict = ("flutter", QUEUE, "Конфликт сохраняет")
restore = ("infrastructure", "ci/verify_restore.py", "fingerprints")
load = ("infrastructure", "ci/load.py", "main")
CASES = {
    16: ("Приглашение", [auth]),
    17: ("Невалидные пароли", [auth]),
    18: ("Вход и восстановление", [auth]),
    19: ("Полномочия ролей", [roles, flow]),
    20: ("Изменение соревнования", [roles]),
    21: ("Назначение бригады", [roles]),
    22: ("Добавление и редактирование", [roles]),
    23: ("Жизненный цикл", [flow]),
    24: ("Обязательные поля и номер", [roles]),
    25: ("Границы оценок", [unit(DOMAIN, "test_valid_scores")]),
    26: ("Ошибочные оценки", [unit(DOMAIN, "test_invalid_scores")]),
    27: ("Видимость", [flow]),
    28: ("500 участников", [limit]),
    29: ("Возрастные границы", [unit(DOMAIN, "test_category"), roles]),
    30: ("Исправления и аудит", [flow]),
    31: ("Скорость и идемпотентность", [flow, reconnect]),
    32: ("Отбрасывание крайних", [rank]),
    33: ("Равенство результатов", [rank]),
    34: ("Формула и округление", [rank]),
    35: ("Офлайн и перезапуск", [offline]),
    36: (
        "Обновления и сортировка",
        [flow, ("flutter", "mobile/test/results_test.dart", "Сортировка")],
    ),
    37: ("Конфликт и повтор", [conflict, reconnect]),
    38: ("Синхронизация без дублей", [offline, reconnect]),
    39: ("Формирование PDF", [flow]),
    40: ("Утверждение и блокировка", [flow]),
    41: ("50 одновременных пользователей", [load]),
    42: ("Восстановление резервной копии", [restore]),
    43: ("Выгрузка и отправка", [flow, unit(INTEGRATIONS, "test_mail_delivery")]),
    44: ("Android и iOS, телефоны и планшеты", [device]),
}
EXTRA = {
    "Яндекс ID": [unit(INTEGRATIONS, "test_yandex_round_trip")],
    "Импорт Excel": [limit],
    "Графики": [flow],
    "Уведомления и настройки": [flow, unit(INTEGRATIONS, "test_push_preferences")],
    "Self-healing": [
        unit("tests/test_healing.py", "test_replay_and_business_failure"),
        ("self-healing", "ci/healing_ui.py", "run"),
    ],
}


def validate():
    assert set(CASES) == set(range(16, 45))
    for checks in [*[c[1] for c in CASES.values()], *EXTRA.values()]:
        for _, path, symbol in checks:
            src = Path(path).read_text()
            if path.endswith(".py"):
                assert symbol in {
                    n.name
                    for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef)
                }, (path, symbol)
            else:
                assert symbol in src, (path, symbol)


if __name__ == "__main__":
    validate()
