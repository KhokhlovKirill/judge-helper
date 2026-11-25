from unittest.mock import MagicMock

from server import api as api_module, store as S, delivery
from conftest import login


def test_yandex_round_trip(api, monkeypatch):
    monkeypatch.setenv("PUBLIC_URL", "https://judge.example.test")
    assert api.post("/yandex").status_code == 503
    monkeypatch.setenv("YANDEX_CLIENT_ID", "test")
    monkeypatch.setenv("YANDEX_CLIENT_SECRET", "test")
    start = api.post("/yandex").json()
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(start["url"]).query)["state"][0]
    assert api.post("/yandex/poll", json={"poll": start["poll"]}).json() == {
        "pending": True
    }
    monkeypatch.setattr(
        api_module.httpx,
        "post",
        lambda *a, **kw: MagicMock(json=lambda: {"access_token": "fixture"}),
    )
    monkeypatch.setattr(
        api_module.httpx,
        "get",
        lambda *a, **kw: MagicMock(json=lambda: {"default_email": "org@example.test"}),
    )
    assert api.get(
        "/yandex/callback", params={"state": state, "code": "code"}
    ).is_success
    assert (
        api.get("/yandex/callback", params={"state": state, "code": "code"}).status_code
        == 401
    )
    ready = api.post("/yandex/poll", json={"poll": start["poll"]}).json()
    assert ready["organizer"] and ready["token"]
    assert api.post("/yandex/poll", json={"poll": start["poll"]}).status_code == 401


def test_mail_delivery(api, monkeypatch):
    smtp = MagicMock()
    monkeypatch.setattr(delivery.smtplib, "SMTP", lambda *a, **kw: smtp)
    org = login(api, "org@example.test")
    api.post(
        "/invite", headers=org, json={"email": "test@example.test"}
    ).raise_for_status()
    delivery.drain()
    delivery.drain()
    calls = smtp.__enter__.return_value.send_message.call_args_list
    assert len(calls) == 1 and calls[0].args[0]["To"] == "test@example.test"


def test_push_preferences(api, contest, monkeypatch):
    org = contest[1]
    for kind in api_module.KINDS:
        assert api.put("/preferences", headers=org, json={kind: False}).is_success
        assert api.get("/preferences", headers=org).json()[kind] is False
    token = "synthetic-token-for-device"
    assert api.put("/device", headers=org, json={"token": token}).is_success
    import google.auth

    credentials = MagicMock(token="fixture")
    monkeypatch.setattr(google.auth, "default", lambda **kw: (credentials, "example"))
    post = MagicMock()
    post.return_value.status_code = 200
    monkeypatch.setattr(delivery.httpx, "post", post)
    with S.transaction() as db:
        delivery.deliver(
            db,
            {
                "kind": "push",
                "recipient": "org@example.test",
                "data": {"event": "1", "kind": "next", "title": "Кубок"},
            },
        )
    assert post.call_args.kwargs["json"]["message"]["token"] == token
    assert api.request(
        "DELETE", "/device", headers=org, json={"token": token}
    ).is_success
