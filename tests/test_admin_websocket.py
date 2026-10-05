import orjson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import uproot.deployment as d
import uproot.events as e
from uproot import server2


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
