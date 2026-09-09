from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.types import Scope

from uproot import server1


def fake_player() -> Any:
    player = nullcontext()
    vars(player)["_uproot_key"] = "player-key"
    return player


def request(headers: dict[str, str]) -> Request:
    scope = cast(
        Scope,
        {
            "type": "http",
            "method": "POST",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
        },
    )
    return Request(scope)


def test_api2_player_allows_legacy_anonymous_requests() -> None:
    assert server1.api2_player(request({}), "session") is None


def test_api2_player_authenticates_uproot_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = fake_player()
    monkeypatch.setattr(server1, "valid_player", lambda sname, uname: player)

    result = server1.api2_player(
        request(
            {
                "X-Uproot-Player": "participant",
                "X-Uproot-CSRF": "session+participant+player-key",
            }
        ),
        "session",
    )

    assert result is player


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Uproot-Player": "participant"},
        {"X-Uproot-CSRF": "session+participant+player-key"},
        {
            "X-Uproot-Player": "participant",
            "X-Uproot-CSRF": "session+participant+wrong-key",
        },
        {
            "X-Uproot-Player": "participant",
            "X-Uproot-CSRF": "session+participant+player-kéy",
        },
    ],
)
def test_api2_player_rejects_bad_credentials(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    monkeypatch.setattr(server1, "valid_player", lambda sname, uname: fake_player())

    with pytest.raises(HTTPException) as excinfo:
        server1.api2_player(request(headers), "session")

    assert excinfo.value.status_code == 403


@pytest.mark.parametrize("authenticated", [False, True])
async def test_app_queries2_passes_player_only_for_authenticated_calls(
    monkeypatch: pytest.MonkeyPatch,
    authenticated: bool,
) -> None:
    seen: dict[str, Any] = {}
    player = fake_player() if authenticated else None
    session = SimpleNamespace()

    async def api2(**kwargs: Any) -> dict[str, bool]:
        seen.update(kwargs)
        return {"ok": True}

    apps: dict[str, Any] = {}
    monkeypatch.setattr(server1.u, "APPS", apps, raising=False)
    monkeypatch.setitem(
        apps,
        "api2_test_app",
        SimpleNamespace(api2=api2),
    )
    monkeypatch.setattr(server1.a, "session_exists", lambda sname: None)
    monkeypatch.setattr(server1, "api2_player", lambda incoming, sname: player)
    monkeypatch.setattr(server1, "Session", lambda sname: nullcontext(session))

    incoming = request({})
    response = await server1.app_queries2(
        incoming,
        "api2_test_app",
        "session",
    )

    assert response.status_code == 200
    assert seen["request"] is incoming
    assert seen["session"] is session
    assert seen.get("player") is player
    assert ("player" in seen) is authenticated
    assert incoming.state.uproot_player is player
