"""Synthetic fixture for a dedicated, empty acceptance database."""

import argparse
import uuid
from server import store as S
from server.api import bootstrap


def seed(prefix="mobile", participants=1, judges=1):
    bootstrap(f"{prefix}@example.test", "Главный судья", "Contest123")
    chief = f"{prefix}@example.test"
    panel = [chief] + [f"{prefix}{i}@example.test" for i in range(1, judges)]
    event_id = str(uuid.uuid4())
    persons = {
        str(i): dict(
            number=i,
            surname="Тестов",
            name=f"Участник {i}",
            club="Старт",
            birth="2000-01-01",
            category=2,
            comment="",
            consent=False,
        )
        for i in range(1, participants + 1)
    }
    event = dict(
        id=event_id,
        title="Мобильная приёмка",
        date="2026-11-25",
        venue="Москва",
        chief=chief,
        owner=chief,
        judges=panel,
        boundaries=[13, 18, 40],
        state="active",
        participants=persons,
        scores={},
        operations={},
        audit=[],
        corrections={},
    )
    with S.transaction() as db:
        password = S.password("Contest123")
        if len(panel) > 1:
            db.execute(
                S.users.insert(),
                [
                    dict(
                        email=j,
                        name=j,
                        password=password,
                        organizer=False,
                        preferences={},
                    )
                    for j in panel[1:]
                ],
            )
        db.execute(S.events.insert().values(id=event_id, data=event, revision=1))
    return event_id, panel


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--prefix", default="mobile")
    p.add_argument("--participants", type=int, default=1)
    args = p.parse_args()
    print(seed(args.prefix, args.participants)[0])
