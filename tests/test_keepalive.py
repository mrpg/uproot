import orjson
import pytest
from fastapi import WebSocketDisconnect

import uproot.deployment as d
import uproot.jobs as j
from uproot import server, server2


class FakeWebSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def accept(self):
        pass

    async def receive_json(self):
        if not self.messages:
            raise WebSocketDisconnect()

        return self.messages.pop(0)

    async def send_bytes(self, data):
        self.sent.append(orjson.loads(data))


@pytest.mark.parametrize("value", [0, 0.5, -1, 27.5, 1e9, "30", float("nan")])
def test_invalid_keepalive_interval_is_rejected(monkeypatch, value):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", value)

    with pytest.raises(SystemExit):
        server.validate_keepalive_interval()


def test_short_dropout_tolerance_is_clamped(monkeypatch):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", 20.0)

    assert j.effective_tolerance(10.0) == 23.0
    assert j.effective_tolerance(120.0) == 120.0


@pytest.mark.parametrize("value", [1, 9.0, 27.0])
def test_valid_keepalive_interval_is_accepted(monkeypatch, value):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", value)

    server.validate_keepalive_interval()


async def test_admin_websocket_answers_keepalive(monkeypatch):
    monkeypatch.setattr(d, "UNSAFE", True)
    monkeypatch.setattr(server2, "require_same_origin_websocket", lambda ws: None)
    websocket = FakeWebSocket([{"endpoint": "hello", "payload": None, "future": 1}])

    await server2.ws(websocket, None)

    assert websocket.sent == [
        {"kind": "invoke", "payload": {"data": None, "future": 1, "error": False}}
    ]
