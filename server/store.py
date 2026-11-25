import hashlib
import os
import secrets
from contextlib import contextmanager
from datetime import UTC, datetime

import sqlalchemy as sa

metadata = sa.MetaData()


def table(name, *columns):
    return sa.Table(name, metadata, *columns)


def col(name, kind=sa.String, **kwargs):
    return sa.Column(name, kind, **kwargs)


users = table(
    "users",
    col("email", primary_key=True),
    col("password"),
    col("name"),
    col("organizer", sa.Boolean),
    col("preferences", sa.JSON),
)
tokens = table(
    "tokens",
    col("digest", primary_key=True),
    col("email"),
    col("kind"),
    col("expires", sa.Float),
)
events = table(
    "events",
    col("id", primary_key=True),
    col("data", sa.JSON),
    col("revision", sa.Integer),
)
documents = table("documents", col("id", primary_key=True), col("pdf", sa.LargeBinary))
outbox = table(
    "outbox",
    col("id", primary_key=True),
    col("kind"),
    col("recipient"),
    col("data", sa.JSON),
    col("sent", sa.Boolean),
)
engine = sa.create_engine(
    os.getenv("DATABASE_URL", "sqlite:///judge.db"), pool_pre_ping=True
)


@contextmanager
def transaction():
    with engine.connect() as db:
        if db.dialect.name == "sqlite":
            db.exec_driver_sql("BEGIN IMMEDIATE")
        with db.begin_nested() if db.in_transaction() else db.begin():
            yield db
        db.commit()


def now():
    return datetime.now(UTC).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password(value, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    )


def issue(db, email, kind, lifetime):
    value = secrets.token_urlsafe(32)
    import time

    db.execute(
        tokens.insert().values(
            digest=digest(value), email=email, kind=kind, expires=time.time() + lifetime
        )
    )
    return value


def enqueue(db, kind, recipient, data):
    db.execute(
        outbox.insert().values(
            id=secrets.token_hex(16),
            kind=kind,
            recipient=recipient,
            data=data,
            sent=False,
        )
    )


devices = table("devices", col("token", primary_key=True), col("email"))
