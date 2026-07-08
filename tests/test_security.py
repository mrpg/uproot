from types import SimpleNamespace

import pytest
from fastapi import WebSocketException, status
from starlette.datastructures import URL, Headers

from uproot import security


def make_websocket(url: str, headers: dict[str, str]):
    return SimpleNamespace(headers=Headers(headers), url=URL(url))


def test_parse_origin_normalizes_default_ports():
    assert security.parse_origin("https://Example.COM") == ("https", "example.com", 443)
    assert security.parse_origin("http://example.com") == ("http", "example.com", 80)


@pytest.mark.parametrize(
    "origin",
    [
        "ftp://example.com",
        "https://user@example.com",
        "https://example.com/path",
        "https://example.com/?x=1",
        "https://example.com/#fragment",
        "https://example.com:bad",
    ],
)
def test_parse_origin_rejects_non_origin_values(origin):
    assert security.parse_origin(origin) is None


def test_require_same_origin_websocket_accepts_matching_origin_behind_proxy():
    websocket = make_websocket(
        "ws://internal/admin/ws/",
        {
            "host": "experiment.example",
            "origin": "https://experiment.example",
            "x-forwarded-proto": "https",
        },
    )

    security.require_same_origin_websocket(websocket)


def test_require_same_origin_websocket_rejects_missing_origin():
    websocket = make_websocket(
        "ws://experiment.example/admin/ws/", {"host": "experiment.example"}
    )

    with pytest.raises(WebSocketException) as excinfo:
        security.require_same_origin_websocket(websocket)

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION
    assert excinfo.value.reason == "Missing WebSocket origin"


def test_require_same_origin_websocket_rejects_cross_origin():
    websocket = make_websocket(
        "wss://experiment.example/admin/ws/",
        {
            "host": "experiment.example",
            "origin": "https://evil.example",
        },
    )

    with pytest.raises(WebSocketException) as excinfo:
        security.require_same_origin_websocket(websocket)

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION
    assert excinfo.value.reason == "WebSocket origin does not match request origin"
