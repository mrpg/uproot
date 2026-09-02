from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from fastapi import HTTPException

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.server4 as api
import uproot.storage as s
from uproot.services import auth


def reset_admin_state() -> None:
    d.DATABASE.reset()
    u.CONFIGS["test-api"] = []
    u.CONFIGS_EXTRA["test-api"] = {"settings": {}}

    with s.Admin() as admin:
        c.create_admin(admin)


def test_admin_api_uses_plural_resource_paths() -> None:
    prefix = api.router.prefix
    paths = {route.path for route in api.router.routes}

    expected_paths = {
        f"{prefix}/dashboard/",
        f"{prefix}/sessions/{{sname}}/",
        f"{prefix}/sessions/{{sname}}/players/group/",
        f"{prefix}/sessions/{{sname}}/players/initialize/",
        f"{prefix}/sessions/{{sname}}/players/admin-chat/replies/",
        f"{prefix}/sessions/{{sname}}/data/export/",
        f"{prefix}/sessions/{{sname}}/digests/",
        f"{prefix}/sessions/{{sname}}/digests/html/",
        f"{prefix}/sessions/{{sname}}/digests/{{appname}}/html/",
        f"{prefix}/sessions/{{sname}}/pipelines/{{appname}}/runs/",
        f"{prefix}/sessions/{{sname}}/pipelines/html/",
        f"{prefix}/sessions/{{sname}}/pipelines/{{appname}}/html/",
        f"{prefix}/rooms/{{roomname}}/",
        f"{prefix}/rooms/{{roomname}}/sessions/",
        f"{prefix}/rooms/{{roomname}}/sessions/",
        f"{prefix}/configs/{{cname}}/",
        f"{prefix}/database/dump/",
        f"{prefix}/praise/",
        f"{prefix}/auth/challenge/",
        f"{prefix}/auth/login/",
        f"{prefix}/auth/tokens/current/",
        f"{prefix}/auth/tokens/",
    }

    assert expected_paths <= paths
    assert not any(path.startswith(f"{prefix}/session/") for path in paths)
    assert not any(path.startswith(f"{prefix}/room/") for path in paths)
    assert f"{prefix}/configs/{{cname}}/summary/" not in paths

    pipeline_path = f"{prefix}/sessions/{{sname}}/pipelines/{{appname}}/runs/"
    pipeline_methods = set()
    for route in api.router.routes:
        if route.path == pipeline_path:
            pipeline_methods |= route.methods
    assert {"GET", "POST"} <= pipeline_methods


async def test_create_session_accepts_zero_players_like_the_admin_ui() -> None:
    reset_admin_state()
    sname = f"api-zero-{uuid4().hex[:8]}"

    result = await api.create_session(
        api.SessionCreate(config="test-api", n_players=0, sname=sname),
        None,
    )
    detail = await api.get_session(sname, None)

    assert result["sname"] == sname
    assert detail["n_players"] == 0
    assert detail["players"] == []


async def test_session_settings_validation_errors_are_bad_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_admin_state()

    def validate_session_settings(
        admin: s.Storage,
        config: str,
        settings: dict[str, Any],
    ) -> None:
        raise ValueError("Invalid example settings")

    app = SimpleNamespace(validate_session_settings=validate_session_settings)
    monkeypatch.setattr(u, "APPS", {"settings_app": app}, raising=False)
    monkeypatch.setitem(u.CONFIGS, "test-api", ["settings_app"])

    with pytest.raises(HTTPException) as excinfo:
        await api.create_session(
            api.SessionCreate(config="test-api", n_players=0),
            None,
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid example settings"

    roomname = f"api-settings-room-{uuid4().hex[:8]}"
    await api.create_room(
        api.RoomCreate(name=roomname, config="test-api"),
        None,
    )

    with pytest.raises(HTTPException) as excinfo:
        await api.create_session_in_room(
            roomname,
            api.RoomSessionCreate(config="test-api", n_players=0),
            None,
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid example settings"


async def test_room_patch_preserves_omitted_fields() -> None:
    reset_admin_state()
    roomname = f"api-room-{uuid4().hex[:8]}"

    await api.create_room(
        api.RoomCreate(
            name=roomname,
            config="test-api",
            capacity=5,
            open=True,
        ),
        None,
    )

    detail = await api.update_room(roomname, api.RoomUpdate(labels=["alpha"]), None)

    assert detail["config"] == "test-api"
    assert detail["capacity"] == 5
    assert detail["open"] is True
    assert detail["labels"] == ["alpha"]


async def test_data_export_matches_admin_ui_filetype_switch() -> None:
    reset_admin_state()
    sname = f"api-export-{uuid4().hex[:8]}"

    await api.create_session(
        api.SessionCreate(config="test-api", n_players=0, sname=sname),
        None,
    )

    csv_response = await api.download_session_export(
        sname,
        "csv",
        ["label"],
        True,
        None,
    )
    jsonl_response = await api.download_session_export(
        sname,
        "jsonl",
        ["label"],
        True,
        None,
    )

    assert csv_response.media_type == "application/zip"
    assert jsonl_response.media_type == "application/zip"

    with pytest.raises(HTTPException) as excinfo:
        await api.download_session_export(
            sname,
            "xlsx",
            [],
            True,
            None,
        )

    assert excinfo.value.status_code == 400


async def test_rest_auth_can_create_and_revoke_ui_browser_session(monkeypatch) -> None:
    reset_admin_state()
    monkeypatch.setattr(auth, "ADMINS", {})
    monkeypatch.setattr(auth, "ADMINS_HASH", None)
    monkeypatch.setattr(auth, "ADMINS_SECRET_KEY", None)
    monkeypatch.setattr(d, "ADMINS", {"admin": ...}, raising=False)
    monkeypatch.setattr(d, "LOGIN_TOKEN", "test-login-token")

    challenge = await api.get_auth_challenge()
    created = await api.create_auth_session(
        api.AuthLogin(user="admin", token="test-login-token")
    )
    sessions = await api.get_auth_sessions(None)
    revoked = await api.revoke_current_auth_session(
        api.AuthToken(auth_token=created["auth_token"]),
        None,
    )

    assert challenge["login_token_enabled"] is True
    assert challenge["pow_challenge"]
    assert created["user"] == "admin"
    assert created["cookie"]["name"] == "uauth"
    assert sessions["admin"]["token_count"] == 1
    assert revoked == {"user": "admin", "revoked": True}
    assert await api.get_auth_sessions(None) == {}


async def test_rest_auth_can_revoke_all_ui_browser_sessions_for_current_user(
    monkeypatch,
) -> None:
    reset_admin_state()
    monkeypatch.setattr(auth, "ADMINS", {})
    monkeypatch.setattr(auth, "ADMINS_HASH", None)
    monkeypatch.setattr(auth, "ADMINS_SECRET_KEY", None)
    monkeypatch.setattr(d, "ADMINS", {"admin": ...}, raising=False)
    monkeypatch.setattr(d, "LOGIN_TOKEN", "test-login-token")

    first = await api.create_auth_session(
        api.AuthLogin(user="admin", token="test-login-token")
    )
    await api.create_auth_session(api.AuthLogin(user="admin", token="test-login-token"))

    revoked = await api.revoke_current_user_auth_sessions(
        api.AuthToken(auth_token=first["auth_token"]),
        None,
    )

    assert revoked == {"user": "admin", "revoked": 2}
    assert await api.get_auth_sessions(None) == {}
