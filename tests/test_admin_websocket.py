import orjson
import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.storage as s
import uproot.types as t
from uproot import server1, server2
from uproot.services import auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(d, "UNSAFE", True)

    app = FastAPI()
    app.include_router(server2.router)

    return TestClient(app)


def subscribe_message(sname: str) -> dict:
    return {
        "endpoint": "invoke",
        "payload": {"mname": "subscribe_to_adminchat", "args": [sname]},
    }


def test_repeated_subscription_replaces_previous(client):
    sname = "ws-duplicate-subscription"
    pulse = e.ADMINCHAT[sname]

    with client.websocket_connect(
        f"{d.ROOT}/admin/ws/", headers={"origin": "http://testserver"}
    ) as websocket:
        websocket.send_json(subscribe_message(sname))
        websocket.send_json(subscribe_message(sname))

        # Messages are handled in order, so both subscriptions are done once this is answered
        websocket.send_json({"endpoint": "hello", "future": 1})
        assert orjson.loads(websocket.receive_bytes())["payload"]["future"] == 1

        assert len(pulse.subscribers) == 1

        websocket.portal.call(pulse.set, {"uname": "someone"})
        websocket.send_json({"endpoint": "hello", "future": 2})

        received = [orjson.loads(websocket.receive_bytes()) for _ in range(2)]
        events = [m for m in received if m["kind"] == "event"]

        assert [m["payload"]["event"] for m in events] == ["AdminchatUpdated"]
        assert not pulse.subscribers[0].qsize()

    assert pulse.subscribers == []


@pytest.fixture
def auth_client(monkeypatch):
    d.DATABASE.reset()
    monkeypatch.setattr(d, "UNSAFE", False)
    monkeypatch.setattr(u, "KEY", "test-auth-key")
    monkeypatch.setattr(d, "ADMINS", {"admin": ...}, raising=False)
    monkeypatch.setattr(auth, "ADMINS", {})
    monkeypatch.setattr(auth, "ADMINS_HASH", None)
    monkeypatch.setattr(auth, "ADMINS_SECRET_KEY", None)
    u.CONFIGS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)

    app = FastAPI()
    app.include_router(server1.router)
    app.include_router(server2.router)

    client = TestClient(app)
    token = auth.create_auth_token_for_user("admin")
    client.cookies.set("uauth", token)

    return client, token


def hello(websocket, future) -> dict:
    websocket.send_json({"endpoint": "hello", "future": future})

    return orjson.loads(websocket.receive_bytes())


def test_admin_websocket_requires_login(auth_client):
    client, _ = auth_client
    client.cookies.clear()

    with (
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect(
            f"{d.ROOT}/admin/ws/", headers={"origin": "http://testserver"}
        ),
    ):
        pass

    assert excinfo.value.code == 1008


def test_admin_websocket_rejects_commands_after_logout(auth_client, monkeypatch):
    client, token = auth_client
    calls = []

    async def spy(*args, **kwargs):
        calls.append(args)

    monkeypatch.setitem(server2.FUNS, "spy", spy)

    with client.websocket_connect(
        f"{d.ROOT}/admin/ws/", headers={"origin": "http://testserver"}
    ) as websocket:
        assert hello(websocket, 1)["payload"]["future"] == 1

        auth.revoke_auth_token(token)

        websocket.send_json(
            {
                "endpoint": "invoke",
                "future": 2,
                "payload": {"mname": "spy", "args": [], "kwargs": {}},
            }
        )

        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_bytes()

    assert excinfo.value.code == 1008
    assert calls == []


def test_admin_websocket_stops_events_after_logout(auth_client):
    client, _ = auth_client
    sname = "ws-logout-events"
    pulse = e.ADMINCHAT[sname]

    with client.websocket_connect(
        f"{d.ROOT}/admin/ws/", headers={"origin": "http://testserver"}
    ) as websocket:
        websocket.send_json(subscribe_message(sname))
        hello(websocket, 1)

        auth.revoke_all_user_tokens("admin")
        websocket.portal.call(pulse.set, {"uname": "someone"})

        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_bytes()

    assert excinfo.value.code == 1008
    assert pulse.subscribers == []


def test_player_websocket_rejects_admin_skip_after_logout(auth_client):
    client, token = auth_client

    with s.Admin() as admin:
        sid = c.create_session(admin, "test")

    with s.Session(sid) as session:
        pid = c.create_player(session)

    def skip(websocket, show_page, future) -> None:
        websocket.send_json(
            {"endpoint": "skip", "payload": show_page, "future": future}
        )
        assert orjson.loads(websocket.receive_bytes())["payload"]["future"] == future

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        skip(websocket, 1, 1)

        with t.materialize(pid) as player:
            assert player.show_page == 1

        auth.revoke_auth_token(token)
        skip(websocket, 2, 2)

        with t.materialize(pid) as player:
            assert player.show_page == 1
