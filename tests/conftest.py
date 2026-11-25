import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from server import store as S
from server.api import app, bootstrap


@pytest.fixture
def api(tmp_path, monkeypatch):
    url = os.getenv("TEST_DATABASE_URL", f"sqlite:///{tmp_path}/test.db")
    engine = create_engine(url)
    monkeypatch.setattr(S, "engine", engine)
    # The PostgreSQL service is dedicated to this serial test run.
    S.metadata.drop_all(engine)
    with TestClient(app) as client:
        bootstrap("org@example.test", "Организатор", "Password1")
        yield client
    engine.dispose()


def login(api, address):
    r = api.post("/login", json={"email": address, "password": "Password1"})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]}


def last_link(address):
    with S.engine.connect() as db:
        return (
            db.execute(
                select(S.outbox.c.data).where(
                    S.outbox.c.recipient == address, S.outbox.c.kind == "email"
                )
            )
            .scalars()
            .all()[-1]["text"]
            .replace("http://localhost:8000", "")
        )


def invite(api, org, address):
    assert (
        api.post(
            "/invite",
            headers=org,
            json={"email": address, "name": address.split("@")[0]},
        ).status_code
        == 200
    )
    link = last_link(address)
    assert api.post(link, json={"password": "Password1"}).status_code == 200
    return login(api, address)


def participant(n=1, **opts):
    return (
        dict(
            number=n,
            surname="Тестов",
            name=f"Участник {n}",
            birth="2000-01-01",
            club="Старт",
            comment="",
            consent=False,
        )
        | opts
    )


def event_body(judges):
    return dict(
        title="Кубок", venue="Москва", date="2026-06-01", judges=judges, chief=judges[0]
    )


@pytest.fixture
def contest(api):
    org = login(api, "org@example.test")
    judges = ["chief@example.test", "judge@example.test"]
    chief, judge = [invite(api, org, j) for j in judges]
    eid = api.post("/events", headers=org, json=event_body(judges)).json()["id"]
    path = "/events/" + eid
    assert api.post(path + "/participants", headers=org, json=participant()).is_success
    return path, org, chief, judge


def score(t=8, a=9, v=0):
    return dict(technique=t, artistry=a, version=v, operation=str(uuid.uuid4()))
