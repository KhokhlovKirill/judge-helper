import asyncio
import hmac
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated
from uuid import UUID, uuid4
from zipfile import BadZipFile

import httpx
import sqlalchemy as sa
from fastapi import (
    Depends,
    FastAPI,
    Header,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, ValidationError

from . import store as S
from .domain import RuleError, category, charts, require, results, submit, transition
from .formats import protocol, spreadsheet


@asynccontextmanager
async def lifespan(app):
    S.metadata.create_all(S.engine)
    yield


app = FastAPI(title="Помощник судьи", lifespan=lifespan)
KINDS = ("assigned", "next", "scored", "approved")


@app.exception_handler(RuleError)
async def problem(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status)


def db_session():
    with S.transaction() as db:
        yield db


DB = Annotated[sa.Connection, Depends(db_session, scope="function")]


def email(value):
    value = value.strip().lower()
    require(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value), "Некорректный email")
    return value


def get_user(db, address):
    return (
        db.execute(sa.select(S.users).where(S.users.c.email == address))
        .mappings()
        .first()
    )


def token_user(db, token, kind):
    record = (
        db.execute(
            sa.select(S.tokens)
            .where(
                S.tokens.c.digest == S.digest(token),
                S.tokens.c.kind == kind,
                S.tokens.c.expires > time.time(),
            )
            .with_for_update()
        )
        .mappings()
        .first()
    )
    require(record, "Ссылка или сеанс недействительны", 401)
    return get_user(db, record["email"])


def actor(db: DB, authorization: Annotated[str, Header()]):
    return token_user(db, authorization.removeprefix("Bearer "), "session")


Actor = Annotated[dict, Depends(actor, scope="function")]


def send_link(db, address, kind):
    token = S.issue(db, address, kind, 3600)
    url = (
        os.getenv("PUBLIC_URL", "http://localhost:8000")
        + "/account/"
        + kind
        + "?token="
        + token
    )
    S.enqueue(db, "email", address, dict(subject="Помощник судьи", text=url))


def bootstrap(address, name, secret):
    check_password(secret)
    S.metadata.create_all(S.engine)
    with S.transaction() as db:
        db.execute(
            S.users.insert().values(
                email=email(address),
                name=name,
                password=S.password(secret),
                organizer=True,
                preferences={},
            )
        )


def check_password(value):
    require(
        len(value) >= 8
        and any(c.isalpha() for c in value)
        and any(c.isdigit() for c in value),
        "Пароль от 8 символов с буквами и цифрами",
    )


class Credentials(BaseModel):
    email: str
    password: str


@app.get("/health")
def health(db: DB):
    db.execute(sa.select(1))
    return {"status": "ok"}


@app.post("/login")
def login(body: Credentials, db: DB):
    user = get_user(db, email(body.email))
    require(
        user
        and user["password"]
        and hmac.compare_digest(
            S.password(body.password, user["password"].split(":")[0]), user["password"]
        ),
        "Неверный email или пароль",
        401,
    )
    return session(db, user)


def session(db, user):
    return dict(
        token=S.issue(db, user["email"], "session", 30 * 86400),
        email=user["email"],
        organizer=user["organizer"],
    )


@app.post("/invite")
def invite(body: dict, db: DB, user: Actor):
    require(user["organizer"], "Только организатор", 403)
    address = email(body.get("email", ""))
    existing = get_user(db, address)
    require(not existing or not existing["password"], "Уже зарегистрирован", 409)
    if not existing:
        db.execute(
            S.users.insert().values(
                email=address,
                name=body.get("name") or address,
                organizer=False,
                preferences={},
            )
        )
    send_link(db, address, "invite")
    return {"queued": True}


@app.post("/reset")
def reset(body: dict, db: DB):
    address = email(body.get("email", ""))
    if get_user(db, address):
        send_link(db, address, "reset")
    return {"queued": True}


@app.get("/account/{kind}", response_class=HTMLResponse)
def password_form(kind: str):
    require(kind in ("reset", "invite"), "Нет формы", 404)
    return '<meta charset="utf-8"><title>Помощник судьи</title><form method="post"><label>Новый пароль <input type="password" minlength="8" name="password" required></label><button>Сохранить</button></form>'


@app.post("/account/{kind}")
async def activate(kind: str, token: str, request: Request, db: DB):
    require(kind in ("reset", "invite"), "Нет формы", 404)
    body = (
        await request.json()
        if "application/json" in request.headers.get("content-type", "")
        else await request.form()
    )
    check_password(body.get("password", ""))
    user = token_user(db, token, kind)
    db.execute(
        S.users.update()
        .where(S.users.c.email == user["email"])
        .values(password=S.password(body["password"]))
    )
    db.execute(S.tokens.delete().where(S.tokens.c.email == user["email"]))
    return {"message": "Пароль сохранён. Войдите в приложение."}


# Browser-based OAuth. The polling secret is delivered only to the initiating device.
@app.post("/yandex")
def yandex_start(db: DB):
    from urllib.parse import urlencode

    client = os.getenv("YANDEX_CLIENT_ID")
    require(client, "Яндекс ID не настроен", 503)
    state = S.issue(db, "", "oauth", 600)
    poll = S.issue(db, S.digest(state), "poll", 600)
    url = "https://oauth.yandex.ru/authorize?" + urlencode(
        dict(
            response_type="code",
            client_id=client,
            state=state,
            redirect_uri=os.environ["PUBLIC_URL"] + "/yandex/callback",
        )
    )
    return {"url": url, "poll": poll}


@app.get("/yandex/callback")
def yandex_callback(code: str, state: str, db: DB):
    digest = S.digest(state)
    used = db.execute(
        S.tokens.delete().where(
            S.tokens.c.digest == digest,
            S.tokens.c.kind == "oauth",
            S.tokens.c.expires > time.time(),
        )
    )
    require(used.rowcount, "Сеанс истёк", 401)
    token = httpx.post(
        "https://oauth.yandex.ru/token",
        data=dict(
            grant_type="authorization_code",
            code=code,
            client_id=os.environ["YANDEX_CLIENT_ID"],
            client_secret=os.environ["YANDEX_CLIENT_SECRET"],
        ),
    ).json()
    require("access_token" in token, "Ошибка Яндекс ID", 401)
    profile = httpx.get(
        "https://login.yandex.ru/info",
        headers={"Authorization": "OAuth " + token["access_token"]},
    ).json()
    user = get_user(db, email(profile.get("default_email", "")))
    require(user and user["password"], "Сначала примите приглашение", 403)
    db.execute(
        S.tokens.update()
        .where(S.tokens.c.email == digest, S.tokens.c.kind == "poll")
        .values(email=user["email"], kind="ready")
    )
    return HTMLResponse("Вход подтверждён. Вернитесь в приложение.")


@app.post("/yandex/poll")
def yandex_poll(body: dict, db: DB):
    key = S.digest(body.get("poll", ""))
    row = (
        db.execute(
            sa.select(S.tokens)
            .where(S.tokens.c.digest == key, S.tokens.c.expires > time.time())
            .with_for_update()
        )
        .mappings()
        .first()
    )
    require(row and row["kind"] in ("ready", "poll"), "Сеанс истёк", 401)
    if row["kind"] == "poll":
        return {"pending": True}
    db.execute(S.tokens.delete().where(S.tokens.c.digest == key))
    return session(db, get_user(db, row["email"]))


class Competition(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    venue: str = Field(min_length=1, max_length=150)
    date: date
    judges: list[str] = Field(min_length=1, max_length=50)
    chief: str
    boundaries: list[int] = Field(
        default_factory=lambda: [13, 18, 40], min_length=3, max_length=3
    )


class Participant(BaseModel):
    number: int = Field(gt=0)
    surname: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    birth: date
    club: str = Field(min_length=1, max_length=150)
    comment: str = Field(default="", max_length=500)
    consent: bool = False


class Score(BaseModel):
    technique: float | str
    artistry: float | str
    operation: UUID
    version: int = Field(ge=0)


def setup(db, body):
    data = body.model_dump(mode="json")
    judges = [email(j) for j in body.judges]
    chief = email(body.chief)
    require(
        chief in judges and len(set(judges)) == len(judges), "Проверьте состав бригады"
    )
    require(all(get_user(db, j) for j in judges), "Сначала пригласите судью")
    bounds = body.boundaries
    require(0 < bounds[0] < bounds[1] < bounds[2], "Границы должны возрастать")
    return data | {"judges": judges, "chief": chief}


def load(db, eid, user, lock=False):
    query = sa.select(S.events).where(S.events.c.id == eid)
    record = db.execute(query.with_for_update() if lock else query).mappings().first()
    require(record, "Соревнование не найдено", 404)
    event = record["data"]
    require(user in event["judges"] or user == event["owner"], "Нет доступа", 403)
    return event


def save(db, event):
    db.execute(
        S.events.update()
        .where(S.events.c.id == event["id"])
        .values(data=event, revision=S.events.c.revision + 1)
    )


def editable(event, user):
    require(user == event["owner"], "Только организатор", 403)
    require(event["state"] == "draft", "Настройки зафиксированы", 409)


def notify(db, event, kind, recipients):
    for recipient in recipients:
        if get_user(db, recipient)["preferences"].get(kind, True):
            S.enqueue(
                db,
                "push",
                recipient,
                dict(event=event["id"], kind=kind, title=event["title"]),
            )


@app.post("/events")
def create(body: Competition, db: DB, user: Actor):
    require(user["organizer"], "Только организатор", 403)
    event = setup(db, body) | dict(
        id=str(uuid4()),
        owner=user["email"],
        state="draft",
        participants={},
        scores={},
        corrections={},
        audit=[],
        operations={},
    )
    db.execute(S.events.insert().values(id=event["id"], data=event, revision=1))
    notify(db, event, "assigned", event["judges"])
    return {"id": event["id"]}


@app.get("/events")
def listing(db: DB, user: Actor):
    return [
        {k: e[k] for k in ("id", "title", "date", "venue", "state")}
        for e in db.scalars(sa.select(S.events.c.data))
        if user["email"] in [e["owner"], *e["judges"]]
    ]


@app.put("/events/{eid}")
def edit(eid: str, body: Competition, db: DB, user: Actor):
    e = load(db, eid, user["email"], True)
    editable(e, user["email"])
    data = setup(db, body)
    new = set(data["judges"]) - set(e["judges"])
    e.update(data)
    for p in e["participants"].values():
        p["category"] = category(p["birth"], e["date"], e["boundaries"])
    save(db, e)
    notify(db, e, "assigned", new)
    return {"id": eid}


@app.get("/events/{eid}")
def detail(eid: str, db: DB, user: Actor):
    actor = user["email"]
    e = load(db, eid, actor)
    data = {
        k: v
        for k, v in e.items()
        if k not in ("scores", "audit", "operations", "corrections")
    }
    data["scores"] = {
        n: (
            scores
            if actor in scores or actor == e["owner"] and actor not in e["judges"]
            else {}
        )
        for n, scores in e["scores"].items()
    }
    data["progress"] = {n: list(s) for n, s in e["scores"].items()}
    data["corrections"] = {
        n: {j: p for j, p in req.items() if actor in (j, e["chief"])}
        for n, req in e["corrections"].items()
    }
    data["audit"] = [a for a in e["audit"] if actor in (a["judge"], e["chief"])]
    data["results"] = results(e, actor)
    data["charts"] = charts(e, data["results"])
    return data


def insert_person(e, p, original=None):
    item = p.model_dump(mode="json")
    number = str(p.number)
    require(original is None or original in e["participants"], "Нет участника", 404)
    require(
        number == original or number not in e["participants"],
        "Стартовый номер занят",
        409,
    )
    require(
        original is not None or len(e["participants"]) < 500, "Достигнут лимит 500", 409
    )
    item["category"] = category(item["birth"], e["date"], e["boundaries"])
    require(
        category(item["birth"], e["date"], [18]) != 0 or p.consent,
        "Укажите согласие представителя",
    )
    if original:
        del e["participants"][original]
    e["participants"][number] = item


@app.post("/events/{eid}/participants")
def participant(
    eid: str, body: Participant, db: DB, user: Actor, original: str | None = None
):
    e = load(db, eid, user["email"], True)
    editable(e, user["email"])
    insert_person(e, body, original)
    save(db, e)
    return {"number": body.number}


@app.post("/events/{eid}/import")
async def excel(eid: str, request: Request, db: DB, user: Actor, confirm: bool = False):
    e = load(db, eid, user["email"], True)
    editable(e, user["email"])
    raw = await request.body()
    require(len(raw) <= 2_000_000, "Файл слишком велик")
    valid, errors = [], []
    try:
        for i, row in enumerate(spreadsheet(raw), 2):
            try:
                person = Participant(**row)
                insert_person(e, person)
                valid.append(person.model_dump(mode="json"))
            except (ValueError, ValidationError) as exc:
                errors.append(dict(row=i, error=str(exc)))
    except (ValueError, BadZipFile, KeyError) as exc:
        raise RuleError("Ошибка Excel: " + str(exc)) from exc
    if confirm:
        save(db, e)
    return {"valid": valid, "errors": errors}


@app.post("/events/{eid}/scores/{number}")
def score(eid: str, number: str, body: Score, db: DB, user: Actor):
    e = load(db, eid, user["email"], True)
    version, completed = submit(
        e, user["email"], number, body.model_dump(mode="json"), S.now()
    )
    save(db, e)
    if completed:
        notify(db, e, "scored", e["judges"])
    return {"version": version}


@app.post("/events/{eid}/corrections/{number}")
def correction(eid: str, number: str, body: dict, db: DB, user: Actor):
    who = user["email"]
    e = load(db, eid, who, True)
    judge = body.get("judge", who)
    require(
        e["state"] == "active" and judge in e["scores"].get(number, {}),
        "Нет доступной оценки",
        409,
    )
    req = e["corrections"].setdefault(number, {})
    if body.get("approve"):
        require(who == e["chief"], "Только главный судья", 403)
        require(judge in req, "Нет запроса", 409)
        req[judge]["approved"] = True
    else:
        require(
            who == judge and body.get("reason", "").strip(),
            "Нужна причина и своя оценка",
        )
        req[judge] = dict(reason=body["reason"], approved=False)
    save(db, e)
    return req[judge]


def make_pdf(db, e):
    return protocol(
        e, results(e, e["chief"]), {j: get_user(db, j)["name"] for j in e["judges"]}
    )


@app.post("/events/{eid}/actions/{action}")
def action(eid: str, action: str, db: DB, user: Actor, number: str = ""):
    who = user["email"]
    e = load(db, eid, who, True)
    if action == "next":
        require(
            who in (e["chief"], e["owner"])
            and e["state"] == "active"
            and number in e["participants"],
            "Вызов недоступен",
            403,
        )
        e["next"] = number
        notify(db, e, "next", e["judges"])
    elif action == "protocol":
        require(
            who == e["chief"] and e["state"] == "finished",
            "Формирует главный судья после завершения",
            403,
        )
        e["draft_protocol"] = True
        pdf = make_pdf(db, e)
        db.execute(S.documents.delete().where(S.documents.c.id == eid))
        db.execute(S.documents.insert().values(id=eid, pdf=pdf))
    else:
        transition(e, action, who)
        if action == "approve":
            e["approved_at"] = S.now()
            db.execute(
                S.documents.update()
                .where(S.documents.c.id == eid)
                .values(pdf=make_pdf(db, e))
            )
            notify(db, e, "approved", e["judges"])
    save(db, e)
    return {"state": e["state"]}


@app.get("/events/{eid}/protocol.pdf")
def download(eid: str, db: DB, user: Actor):
    e = load(db, eid, user["email"])
    require(
        e["state"] == "approved"
        or (e.get("draft_protocol") and user["email"] == e["chief"]),
        "Протокол недоступен",
        403,
    )
    return Response(
        db.scalar(sa.select(S.documents.c.pdf).where(S.documents.c.id == eid)),
        media_type="application/pdf",
    )


@app.post("/events/{eid}/email")
def mail(eid: str, body: dict, db: DB, user: Actor):
    e = load(db, eid, user["email"])
    require(
        e["state"] == "approved" and e["chief"] == user["email"],
        "Нет утверждённого протокола или прав",
        403,
    )
    S.enqueue(
        db,
        "email",
        email(body.get("email", "")),
        dict(subject=e["title"], text="Утверждённый протокол", document=eid),
    )
    return {"queued": True}


@app.get("/preferences")
def preferences(user: Actor):
    return {kind: user["preferences"].get(kind, True) for kind in KINDS}


@app.put("/preferences")
def set_preferences(body: dict[str, bool], db: DB, user: Actor):
    require(set(body) <= set(KINDS), "Неизвестное уведомление")
    db.execute(
        S.users.update()
        .where(S.users.c.email == user["email"])
        .values(preferences=user["preferences"] | body)
    )
    return {"saved": True}


@app.websocket("/events/{eid}/updates")
async def updates(ws: WebSocket, eid: str):
    await ws.accept()
    try:
        token = await asyncio.wait_for(ws.receive_text(), 10)
        last = None
        while True:
            with S.engine.connect() as db:
                who = token_user(db, token, "session")["email"]
                load(db, eid, who)
                revision = db.scalar(
                    sa.select(S.events.c.revision).where(S.events.c.id == eid)
                )
            if revision != last:
                await ws.send_json({"revision": revision})
                last = revision
            try:
                await asyncio.wait_for(ws.receive_text(), 0.35)
            except TimeoutError:
                pass
    except TimeoutError, RuleError:
        await ws.close(code=1008)
    except WebSocketDisconnect:
        pass


@app.put("/device")
def device(body: dict, db: DB, user: Actor):
    token = body.get("token", "")
    require(
        isinstance(token, str) and 20 <= len(token) <= 4096,
        "Некорректный токен устройства",
    )
    db.execute(S.devices.delete().where(S.devices.c.token == token))
    db.execute(S.devices.insert().values(token=token, email=user["email"]))
    return {"saved": True}


@app.delete("/device")
def forget_device(body: dict, db: DB, user: Actor):
    db.execute(
        S.devices.delete().where(
            S.devices.c.token == body.get("token"), S.devices.c.email == user["email"]
        )
    )
    return {"saved": True}
