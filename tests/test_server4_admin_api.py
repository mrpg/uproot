from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.server4 as api
import uproot.storage as s
from uproot.services import auth


@pytest.fixture(autouse=True)
def clean_rate_limit():
    auth.FAILED_ATTEMPTS.clear()
    auth.BANNED_IPS.clear()
    auth.LAST_CLEANUP = 0.0
    yield
    auth.FAILED_ATTEMPTS.clear()
    auth.BANNED_IPS.clear()
    auth.LAST_CLEANUP = 0.0


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
        f"{prefix}/auth/login/",
        f"{prefix}/auth/logout/",
        f"{prefix}/auth/logout-all/",
        f"{prefix}/sessions/{{sname}}/players/{{uname}}/",
    }

    assert expected_paths <= paths
    assert not any(path.startswith(f"{prefix}/session/") for path in paths)
    assert not any(path.startswith(f"{prefix}/room/") for path in paths)
    assert f"{prefix}/configs/{{cname}}/summary/" not in paths
    assert not any(path.startswith(f"{prefix}/auth/tokens/") for path in paths)

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
    request = SimpleNamespace(client=SimpleNamespace(host="10.20.30.40"))

    created = await api.create_auth_session(
        request,
        api.AuthLogin(user="admin", token="test-login-token"),
    )
    sessions = await api.get_auth_sessions(None)
    revoked = await api.revoke_auth_session(
        api.AuthToken(auth_token=created["auth_token"]),
        None,
    )

    assert created["user"] == "admin"
    assert created["cookie"]["name"] == "uauth"
    assert auth.FAILED_ATTEMPTS == {}
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
    request = SimpleNamespace(client=SimpleNamespace(host="10.20.30.40"))

    first = await api.create_auth_session(
        request,
        api.AuthLogin(user="admin", token="test-login-token"),
    )
    await api.create_auth_session(
        request,
        api.AuthLogin(user="admin", token="test-login-token"),
    )

    revoked = await api.revoke_token_user_auth_sessions(
        api.AuthToken(auth_token=first["auth_token"]),
        None,
    )

    assert revoked == {"user": "admin", "revoked": 2}
    assert await api.get_auth_sessions(None) == {}


async def test_rest_auth_rate_limits_before_rechecking_credentials(monkeypatch):
    ip = "10.20.30.40"
    request = SimpleNamespace(client=SimpleNamespace(host=ip))
    authenticate = AsyncMock(return_value=None)
    monkeypatch.setattr(api.a, "create_auth_token_async", authenticate)
    monkeypatch.setattr(auth, "MAX_FAILED_ATTEMPTS", 1)

    with pytest.raises(HTTPException) as excinfo:
        await api.create_auth_session(request, api.AuthLogin(user="admin", pw="bad"))

    assert excinfo.value.status_code == 401

    with pytest.raises(HTTPException) as excinfo:
        await api.create_auth_session(request, api.AuthLogin(user="admin", pw="bad"))

    assert excinfo.value.status_code == 429
    assert authenticate.await_count == 1


async def create_api_session(n_players: int = 0) -> tuple[str, list[str]]:
    sname = f"api-{uuid4().hex[:8]}"

    await api.create_session(
        api.SessionCreate(config="test-api", n_players=n_players, sname=sname),
        None,
    )

    return sname, (await api.get_session(sname, None))["players"]


async def test_session_settings_may_contain_any_key() -> None:
    reset_admin_state()
    sname, _ = await create_api_session()

    result = await api.update_session_settings(
        sname,
        api.SettingsUpdate(settings={"sname": 1, "settings": 2}),
        None,
    )
    detail = await api.get_session(sname, None)

    assert result == {"settings": {"sname": 1, "settings": 2}}
    assert detail["settings"] == {"sname": 1, "settings": 2}


async def test_invalid_player_field_names_are_bad_requests() -> None:
    reset_admin_state()
    sname, unames = await create_api_session(1)

    with pytest.raises(HTTPException) as excinfo:
        await api.set_player_fields(
            sname,
            api.PlayersFields(unames=unames, fields={"ok": 1, "a b": 2}),
            None,
        )

    assert excinfo.value.status_code == 400
    assert (await api.get_player(sname, unames[0], ["ok"], None)) == {"ok": None}


async def test_get_player_returns_requested_fields() -> None:
    reset_admin_state()
    sname, unames = await create_api_session(2)

    await api.set_player_fields(
        sname,
        api.PlayersFields(unames=unames[:1], fields={"score": 7}),
        None,
    )

    assert await api.get_player(sname, unames[0], ["score"], None) == {"score": 7}

    with pytest.raises(HTTPException) as excinfo:
        await api.get_player(sname, "nobody", ["score"], None)

    assert excinfo.value.status_code == 404


async def test_session_active_and_testing_are_set_explicitly() -> None:
    reset_admin_state()
    sname, _ = await create_api_session()

    for _ in range(2):
        assert await api.set_session_active(
            sname, api.SessionActive(active=False), None
        ) == {"active": False}
        assert await api.set_session_testing(
            sname, api.SessionTesting(testing=True), None
        ) == {"testing": True}


async def test_room_session_defaults_to_room_config() -> None:
    reset_admin_state()
    roomname = f"api-room-{uuid4().hex[:8]}"
    bare_roomname = f"api-bare-{uuid4().hex[:8]}"

    await api.create_room(api.RoomCreate(name=roomname, config="test-api"), None)
    await api.create_room(api.RoomCreate(name=bare_roomname), None)

    result = await api.create_session_in_room(
        roomname,
        api.RoomSessionCreate(n_players=1),
        None,
    )

    assert result["config"] == "test-api"
    assert result["roomname"] == roomname

    with pytest.raises(HTTPException) as excinfo:
        await api.create_session_in_room(
            bare_roomname,
            api.RoomSessionCreate(n_players=1),
            None,
        )

    assert excinfo.value.status_code == 400


async def test_pipeline_filetype_is_checked_before_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_admin_state()
    calls = []

    def pipeline(session: s.Storage) -> list[dict[str, Any]]:
        calls.append(session.name)
        return [{"a": 1}]

    app = SimpleNamespace(pipeline=pipeline)
    monkeypatch.setattr(u, "APPS", {"pipeline_app": app}, raising=False)
    monkeypatch.setitem(u.CONFIGS, "test-api", ["pipeline_app"])
    sname, _ = await create_api_session()
    request = SimpleNamespace(method="GET")

    with pytest.raises(HTTPException) as excinfo:
        await api.get_session_pipeline_run(request, sname, "pipeline_app", "xlsx", None)

    assert excinfo.value.status_code == 400
    assert calls == []


async def test_digest_fragments_skip_apps_without_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_admin_state()
    app = SimpleNamespace(digest=lambda session: 1)
    monkeypatch.setattr(u, "APPS", {"digest_app_without_template": app}, raising=False)
    monkeypatch.setitem(u.CONFIGS, "test-api", ["digest_app_without_template"])
    sname, _ = await create_api_session()

    assert await api.get_session_digest_fragments(sname, None) == {
        "apps": ["digest_app_without_template"],
        "html": {},
    }


async def test_dashboard_reports_version_and_announcements_nudge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reset_admin_state()
    monkeypatch.setattr(d, "UPSTREAM", False)
    monkeypatch.setattr(api.a, "sessions", dict)

    dashboard = await api.get_dashboard(None)

    assert dashboard["uproot_version"] == u.__version__
    assert dashboard["nudge_announcements"] is False
