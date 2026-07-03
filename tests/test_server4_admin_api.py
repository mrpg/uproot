from uuid import uuid4

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.server4 as api
import uproot.storage as s


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
        f"{prefix}/sessions/{{sname}}/digests/",
        f"{prefix}/sessions/{{sname}}/pipelines/{{appname}}/runs/",
        f"{prefix}/rooms/{{roomname}}/",
        f"{prefix}/rooms/{{roomname}}/sessions/",
        f"{prefix}/rooms/{{roomname}}/sessions/",
        f"{prefix}/configs/{{cname}}/",
        f"{prefix}/database/dump/",
        f"{prefix}/praise/",
    }

    assert expected_paths <= paths
    assert not any(path.startswith(f"{prefix}/session/") for path in paths)
    assert not any(path.startswith(f"{prefix}/room/") for path in paths)
    assert f"{prefix}/configs/{{cname}}/summary/" not in paths


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
