import io
import time
from concurrent.futures import ThreadPoolExecutor

from conftest import event_body, invite, last_link, login, participant, score
from openpyxl import Workbook
from pypdf import PdfReader
from sqlalchemy import select

from server import store as S
from server.formats import HEADERS


def test_invite_password_reset(api):
    org = login(api, "org@example.test")
    who = "new@example.test"
    assert api.post("/invite", headers=org, json={"email": who}).is_success
    link = last_link(who)
    assert api.get(link).is_success
    for password in ("abc123", "abcdefgh", "12345678"):
        assert api.post(link, json={"password": password}).status_code == 422
    assert api.post(link, json={"password": "Password1"}).is_success
    assert api.post(link, json={"password": "Password1"}).status_code == 401
    original = login(api, who)
    assert api.post("/reset", json={"email": who}).is_success
    reset = last_link(who)
    assert api.post(reset, data={"password": "Second123"}).is_success
    assert api.post(reset, data={"password": "Third123"}).status_code == 401
    assert api.get("/events", headers=original).status_code == 401
    assert (
        api.post("/login", json={"email": who, "password": "Password1"}).status_code
        == 401
    )
    assert api.post("/login", json={"email": who, "password": "Second123"}).is_success


def test_access_edit(api, contest):
    p, org, chief, judge = contest
    unauthorized = invite(api, org, "other@example.test")
    assert api.get("/events", headers=unauthorized).json() == []
    assert api.get(p, headers=unauthorized).status_code == 403
    b = event_body(["chief@example.test", "judge@example.test"])
    assert api.post("/events", headers=judge, json=b).status_code == 403
    assert api.put(p, headers=org, json=b | {"title": "Финал"}).is_success
    assert api.get(p, headers=chief).json()["title"] == "Финал"
    assert (
        api.put(p, headers=org, json=b | {"chief": "absent@example.test"}).status_code
        == 422
    )
    assert (
        api.post(p + "/participants", headers=org, json=participant()).status_code
        == 409
    )
    assert (
        api.post(
            p + "/participants", headers=org, json=participant(2, club="")
        ).status_code
        == 422
    )
    assert (
        api.post(
            p + "/participants", headers=org, json=participant(2, birth="2014-06-01")
        ).status_code
        == 422
    )
    assert api.post(
        p + "/participants?original=1",
        headers=org,
        json=participant(birth="2014-06-01", consent=True, club="Другой"),
    ).is_success
    assert api.get(p, headers=org).json()["participants"]["1"]["category"] == 0
    assert api.put(p, headers=org, json=b | {"boundaries": [12, 18, 40]}).is_success
    assert api.get(p, headers=org).json()["participants"]["1"]["category"] == 1
    assert api.post(p + "/actions/start", headers=org).is_success
    assert api.put(p, headers=org, json=b).status_code == 409
    assert (
        api.post(p + "/participants", headers=chief, json=participant(2)).status_code
        == 403
    )


def test_flow_pdf_and_visibility(api, contest):
    p, org, chief, judge = contest
    assert api.put("/preferences", headers=judge, json={"next": False}).is_success
    assert api.get("/preferences", headers=judge).json()["next"] is False
    assert api.post(p + "/actions/start", headers=org).is_success
    assert api.post(p + "/actions/next?number=1", headers=chief).is_success
    with api.websocket_connect(p + "/updates") as socket:
        socket.send_text(judge["Authorization"][7:])
        rev = socket.receive_json()["revision"]
        body = score()
        start = time.monotonic()
        assert api.post(p + "/scores/1", headers=chief, json=body).json() == {
            "version": 1
        }
        assert time.monotonic() - start < 1
        assert socket.receive_json()["revision"] > rev
    assert api.post(p + "/scores/1", headers=chief, json=body).json() == {"version": 1}
    hidden = api.get(p, headers=judge).json()
    assert (
        hidden["scores"]["1"] == {}
        and hidden["results"] == []
        and hidden["charts"]["distribution"] == {}
    )
    assert api.post(p + "/scores/1", headers=judge, json=score(9, 8)).is_success
    assert len(api.get(p, headers=judge).json()["scores"]["1"]) == 2
    assert (
        api.post(p + "/scores/1", headers=judge, json=score(10, 10, 1)).status_code
        == 409
    )
    assert api.post(
        p + "/corrections/1", headers=judge, json={"reason": "Опечатка"}
    ).is_success
    assert (
        api.post(
            p + "/corrections/1", headers=judge, json={"approve": True}
        ).status_code
        == 403
    )
    assert api.post(
        p + "/corrections/1",
        headers=chief,
        json={"judge": "judge@example.test", "approve": True},
    ).is_success
    assert api.post(p + "/scores/1", headers=judge, json=score(10, 10, 1)).is_success
    data = api.get(p, headers=chief).json()
    assert (
        data["audit"][0]["old"]["t"] == 90 and data["audit"][0]["reason"] == "Опечатка"
    )
    assert data["results"][0]["total"] == 9.2
    assert data["charts"]["distribution"] == {"2": [9.2]}
    assert data["charts"]["deviations"]["2"] == {
        "chief@example.test": -0.8,
        "judge@example.test": 0.8,
    }
    assert api.post(p + "/actions/finish", headers=org).is_success
    start = time.monotonic()
    assert api.post(p + "/actions/protocol", headers=chief).is_success
    assert time.monotonic() - start < 10
    assert api.post(p + "/actions/approve", headers=judge).status_code == 403
    assert api.post(p + "/actions/approve", headers=chief).is_success
    first = api.get(p + "/protocol.pdf", headers=chief).content
    printable = " ".join(
        page.extract_text() for page in PdfReader(io.BytesIO(first)).pages
    )
    for item in (
        "Кубок",
        "Москва",
        "Тестов",
        "Взрослые",
        "9.2",
        "Главный судья",
        "chief",
    ):
        assert item in printable
    assert (
        api.post(p + "/scores/1", headers=judge, json=score(0, 0, 2)).status_code == 409
    )
    assert (
        api.post(p + "/email", headers=chief, json={"email": "wrong"}).status_code
        == 422
    )
    assert api.post(
        p + "/email", headers=chief, json={"email": "team@example.test"}
    ).is_success
    assert first == api.get(p + "/protocol.pdf", headers=judge).content
    with S.engine.connect() as db:
        pushed = (
            db.execute(select(S.outbox).where(S.outbox.c.kind == "push"))
            .mappings()
            .all()
        )
        assert {x["data"]["kind"] for x in pushed} == {
            "assigned",
            "next",
            "scored",
            "approved",
        }
        assert not any(
            x["data"]["kind"] == "next" and x["recipient"] == "judge@example.test"
            for x in pushed
        )


def test_excel_limit(api, contest):
    path, org, _, _ = contest
    book = Workbook()
    ws = book.active
    ws.append(HEADERS)
    for i in range(1, 502):
        ws.append(["Тестов", "Имя", "2000-01-01", "Клуб", i, "", True])
    buf = io.BytesIO()
    book.save(buf)

    def send(confirm):
        return api.post(
            path + "/import?confirm=" + confirm, headers=org, content=buf.getvalue()
        ).json()

    preview = send("false")
    assert len(preview["valid"]) == 499 and len(preview["errors"]) == 2
    assert len(api.get(path, headers=org).json()["participants"]) == 1
    assert send("true") == preview
    for n in (1, 250, 500):
        assert api.post(
            path + f"/participants?original={n}",
            headers=org,
            json=participant(n, club="Изменён"),
        ).is_success
    people = api.get(path, headers=org).json()["participants"]
    assert len(people) == 500 and all(
        people[str(n)]["club"] == "Изменён" for n in (1, 250, 500)
    )


def test_concurrent_reconnect(api, contest):
    path, org, chief, _ = contest
    api.post(path + "/actions/start", headers=org).raise_for_status()
    b = score()
    with ThreadPoolExecutor(2) as pool:
        assert all(
            r.json() == {"version": 1}
            for r in pool.map(
                lambda _: api.post(path + "/scores/1", headers=chief, json=b), range(2)
            )
        )
    assert api.post(path + "/scores/1", headers=chief, json=score()).status_code == 409
    assert len(api.get(path, headers=chief).json()["scores"]["1"]) == 1
