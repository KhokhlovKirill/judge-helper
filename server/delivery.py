"""Transactional outbox for SMTP and mobile notifications."""

import logging
import os
import smtplib
import time
from email.message import EmailMessage

import httpx
import sqlalchemy as sa

from . import store as S

LABELS = {
    "assigned": "Назначение на соревнование",
    "next": "Вызов участника",
    "scored": "Все оценки получены",
    "approved": "Протокол утверждён",
}


def deliver(db, row):
    payload = row["data"]
    if row["kind"] == "email":
        message = EmailMessage()
        message["From"] = os.getenv("SMTP_FROM", "judge@example.test")
        message["To"] = row["recipient"]
        message["Subject"] = payload["subject"]
        message["Message-ID"] = f"<{row['id']}@judge-helper>"
        message.set_content(payload["text"])
        if "document" in payload:
            pdf = db.scalar(
                sa.select(S.documents.c.pdf).where(
                    S.documents.c.id == payload["document"]
                )
            )
            message.add_attachment(
                pdf, maintype="application", subtype="pdf", filename="protocol.pdf"
            )
        with smtplib.SMTP(
            os.getenv("SMTP_HOST", "localhost"),
            int(os.getenv("SMTP_PORT", "1025")),
            timeout=10,
        ) as smtp:
            if os.getenv("SMTP_TLS") == "1":
                smtp.starttls()
            if os.getenv("SMTP_USER"):
                smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
        return
    tokens = db.scalars(
        sa.select(S.devices.c.token).where(S.devices.c.email == row["recipient"])
    ).all()
    if not tokens:
        return
    import google.auth
    from google.auth.transport.requests import Request

    credentials, project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/firebase.messaging"]
    )
    credentials.refresh(Request())
    for token in tokens:
        r = httpx.post(
            f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
            headers={"Authorization": "Bearer " + credentials.token},
            json={
                "message": {
                    "token": token,
                    "notification": {
                        "title": LABELS[payload["kind"]],
                        "body": payload["title"],
                    },
                    "data": {"event": payload["event"], "kind": payload["kind"]},
                }
            },
        )
        if r.status_code == 404:
            db.execute(S.devices.delete().where(S.devices.c.token == token))
        else:
            r.raise_for_status()


def drain():
    with S.transaction() as db:
        rows = (
            db.execute(
                sa.select(S.outbox)
                .where(S.outbox.c.sent.is_(False))
                .with_for_update(skip_locked=True)
                .limit(50)
            )
            .mappings()
            .all()
        )
        for row in rows:
            try:
                deliver(db, row)
            except Exception:
                logging.exception("Delivery failed for %s", row["id"])
                continue
            db.execute(
                S.outbox.update().where(S.outbox.c.id == row["id"]).values(sent=True)
            )


if __name__ == "__main__":
    S.metadata.create_all(S.engine)
    while True:
        drain()
        time.sleep(2)
