# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2026.
# SPDX-License-Identifier: LGPL-3.0-or-later

from urllib.parse import urlsplit

from fastapi import WebSocket, WebSocketException, status


def default_origin_port(scheme: str) -> int:
    if scheme == "https":
        return 443

    return 80


def http_scheme_from_websocket(websocket: WebSocket) -> str:
    forwarded_proto = (
        websocket.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    )
    if forwarded_proto in ("http", "https"):
        return forwarded_proto
    if forwarded_proto == "ws":
        return "http"
    if forwarded_proto == "wss":
        return "https"

    websocket_scheme = websocket.url.scheme.lower()
    if websocket_scheme == "wss":
        return "https"
    if websocket_scheme == "ws":
        return "http"

    return websocket_scheme


def parse_origin(origin: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlsplit(origin)
        port = parsed.port
    except ValueError:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None
    if not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        return None

    return (
        scheme,
        parsed.hostname.lower(),
        port if port is not None else default_origin_port(scheme),
    )


def request_origin(websocket: WebSocket) -> tuple[str, str, int] | None:
    host = websocket.headers.get("host")
    if host is None:
        host = websocket.url.netloc

    return parse_origin(f"{http_scheme_from_websocket(websocket)}://{host}")


def require_same_origin_websocket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing WebSocket origin",
        )

    expected_origin = request_origin(websocket)
    actual_origin = parse_origin(origin)
    if actual_origin is None or expected_origin is None:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid WebSocket origin",
        )

    if actual_origin != expected_origin:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="WebSocket origin does not match request origin",
        )
