import argparse
import getpass
import os
from .api import bootstrap, save
from . import store as S
from sqlalchemy import select


def anonymize(event_id, number):
    with S.transaction() as db:
        event = db.execute(
            select(S.events.c.data).where(S.events.c.id == event_id).with_for_update()
        ).scalar_one()
        if event["state"] == "approved":
            raise ValueError(
                "Утверждённый документ требует отдельного решения о сроке хранения"
            )
        S.hydrate(db, event)
        p = event["participants"][number]
        p.update(
            name=number, surname="Участник", club="—", comment="", birth=event["date"]
        )
        event["draft_protocol"] = False
        save(db, event, roster_changed=True)
        db.execute(S.documents.delete().where(S.documents.c.id == event_id))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="cmd", required=True)
    new = commands.add_parser("organizer")
    new.add_argument("email")
    new.add_argument("name")
    anon = commands.add_parser("anonymize")
    anon.add_argument("event")
    anon.add_argument("number")
    args = parser.parse_args()
    if args.cmd == "organizer":
        bootstrap(
            args.email,
            args.name,
            os.getenv("ORGANIZER_PASSWORD") or getpass.getpass("Пароль: "),
        )
    else:
        anonymize(args.event, args.number)
