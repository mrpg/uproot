import asyncio

import orjson
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.jobs as j
import uproot.rooms as r
import uproot.services.room_service as room_ops
import uproot.storage as s
from uproot import server2, server3, server4

CONFIG = "test-rooms"


def setup(**rooms: dict) -> str:
    d.DATABASE.reset()
    u.CONFIGS[CONFIG] = []
    u.CONFIGS_EXTRA[CONFIG] = {"settings": {}}

    with s.Admin() as admin:
        c.create_admin(admin)
        admin.rooms = {}
        sid = c.create_session(admin, CONFIG)

        for name, kwargs in rooms.items():
            admin.rooms[name] = r.room(name, **kwargs)

    for name in rooms:
        e.clear_room(name)

    return sid.sname


def released(roomname: str) -> bool:
    return e.ROOMS[roomname].is_set()


@pytest.mark.parametrize(
    ("open", "sname", "config", "expected"),
    [
        (False, None, None, False),
        (False, None, CONFIG, False),
        (False, "s", None, False),
        (False, "s", CONFIG, False),
        (True, None, None, False),
        (True, None, CONFIG, True),
        (True, "s", None, True),
        (True, "s", CONFIG, True),
        (True, None, "unloaded", False),
        (True, "s", "unloaded", True),
    ],
)
def test_ready(
    monkeypatch,
    open: bool,
    sname: str | None,
    config: str | None,
    expected: bool,
):
    monkeypatch.setitem(u.CONFIGS, CONFIG, [])
    room = {"open": open, "sname": sname, "config": config}

    assert r.ready(room) is expected


def test_reopening_room_with_session_releases_waiting_players():
    sname = setup(lab={})

    with s.Admin() as admin:
        admin.rooms["lab"]["sname"] = sname
        admin.rooms["lab"]["open"] = True

    r.sync("lab")
    assert released("lab")

    asyncio.run(room_ops.set_room_open("lab", False))
    assert not released("lab")

    asyncio.run(room_ops.set_room_open("lab", True))
    assert released("lab")


def test_opening_room_with_config_releases_waiting_players():
    setup(lab={"config": CONFIG})

    r.sync("lab")
    assert not released("lab")

    asyncio.run(room_ops.set_room_open("lab", True))
    assert released("lab")


def test_room_without_session_or_config_cannot_open():
    setup(lab={})

    with pytest.raises(ValueError):
        asyncio.run(room_ops.set_room_open("lab", True))

    assert not released("lab")


def test_room_with_unloaded_config_is_not_ready(monkeypatch):
    monkeypatch.setattr(u, "APPS", {}, raising=False)
    setup()
    asyncio.run(
        server2.new_room2(
            request=None,
            name="lab",
            config="unloaded",
            labels="",
            use_labels=False,
            capacity="",
            room_sname="",
            open=True,
            auth={},
        )
    )

    assert not released("lab")

    with pytest.raises(ValueError):
        asyncio.run(room_ops.set_room_open("lab", True))

    app = FastAPI()
    app.include_router(server3.router)
    response = TestClient(app).post(f"{d.ROOT}/room/lab/", follow_redirects=False)

    assert response.status_code == 200  # the waiting page, not an error

    with s.Admin() as admin:
        assert admin.rooms["lab"]["sname"] is None

    # A config that is no longer loaded (e.g., after a restart) stops releasing
    asyncio.run(room_ops.set_room_open("lab", False))

    with s.Admin() as admin:
        admin.rooms["lab"]["config"] = CONFIG

    asyncio.run(room_ops.set_room_open("lab", True))
    assert released("lab")

    monkeypatch.delitem(u.CONFIGS, CONFIG)
    r.sync("lab")
    assert not released("lab")


@pytest.mark.parametrize(("config", "expected"), [(CONFIG, True), (None, False)])
def test_disassociating_keeps_release_iff_room_stays_ready(
    config: str | None, expected: bool
):
    sname = setup(lab={"config": config})

    with s.Admin() as admin:
        admin.rooms["lab"]["sname"] = sname
        admin.rooms["lab"]["open"] = True

    r.sync("lab")
    asyncio.run(room_ops.disassociate("lab", sname))

    assert released("lab") is expected


def test_closing_and_deleting_room_stop_release():
    sname = setup(lab={"config": CONFIG, "open": True})

    with s.Admin() as admin:
        admin.rooms["lab"]["sname"] = sname

    r.sync("lab")
    asyncio.run(room_ops.close_room("lab", disassociate_session=True))
    assert not released("lab")

    asyncio.run(room_ops.set_room_open("lab", True))
    assert released("lab")

    asyncio.run(room_ops.delete_room("lab"))
    assert not released("lab")


def test_waiting_player_is_released_and_admitted_on_reopen():
    sname = setup(lab={})

    with s.Admin() as admin:
        admin.rooms["lab"]["sname"] = sname

    r.sync("lab")
    app = FastAPI()
    app.include_router(server3.router)
    client = TestClient(app)

    with client.websocket_connect(
        f"{d.ROOT}/roomws/lab/?label=waiting1", headers={"origin": "http://testserver"}
    ) as websocket:
        websocket.portal.call(room_ops.set_room_open, "lab", True)
        message = orjson.loads(websocket.receive_bytes())

    assert message["payload"]["event"] == "RoomStarted"
    assert message["payload"]["detail"]["label"] == "waiting1"

    response = client.post(
        f"{d.ROOT}/room/lab/", data={"label": "waiting1"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(f"{d.ROOT}/p/{sname}/")


@pytest.mark.parametrize("capacity", [-1, 2.5, True, "3"])
def test_capacity_must_be_a_non_negative_integer(capacity):
    setup(lab={})

    with pytest.raises(ValueError):
        r.room("other", capacity=capacity)

    with pytest.raises(ValueError):
        asyncio.run(room_ops.set_room_capacity("lab", capacity))


def test_empty_config_and_sname_mean_none():
    room = r.room("lab", config="", sname="", open=True)

    assert room["config"] is None
    assert room["sname"] is None
    assert not r.ready(room)


def test_api_room_with_empty_sname_is_not_associated():
    setup()

    detail = asyncio.run(
        server4.create_room(
            server4.RoomCreate(name="lab", config="", sname="", open=True), None
        )
    )

    assert detail["sname"] is None
    assert detail["config"] is None
    assert not released("lab")

    asyncio.run(room_ops.delete_room("lab"))


def test_disassociate_requires_the_rooms_own_session():
    sname = setup(lab={}, other={})

    with s.Admin() as admin:
        other = c.create_session(admin, CONFIG).sname

    for roomname, sname_ in [("lab", sname), ("other", other)]:
        asyncio.run(
            server4.update_room(roomname, server4.RoomUpdate(sname=sname_), None)
        )

    # For example, a stale admin page that still shows an old association
    with pytest.raises(ValueError):
        asyncio.run(room_ops.disassociate("lab", other))

    with s.Admin() as admin:
        assert admin.rooms["lab"]["sname"] == sname
        assert admin.rooms["other"]["sname"] == other

    with s.Session(sname) as session:
        assert session.room == "lab"

    with s.Session(other) as session:
        assert session.room == "other"


def new_session_in_room_form(**kwargs):
    form = {
        "request": None,
        "roomname": "lab",
        "config": CONFIG,
        "assignees": "",
        "nplayers": 2,
        "settings": "",
        "sname": "",
        "unames": "",
        "disable_growth": False,
        "simulate": False,
        "auth": {},
    }

    return server2.new_session_in_room(**(form | kwargs))


def test_failed_session_in_room_leaves_room_untouched():
    setup(lab={"config": CONFIG})

    with s.Admin() as admin:
        sessions = list(admin._uproot_sessions)

    with pytest.raises(HTTPException) as server2_error:
        asyncio.run(new_session_in_room_form(unames="only_one", disable_growth=True))

    with pytest.raises(HTTPException) as server4_error:
        asyncio.run(
            server4.create_session_in_room(
                "lab",
                server4.RoomSessionCreate(
                    n_players=1, unames=["bad name"], no_grow=True
                ),
                None,
            )
        )

    assert server2_error.value.status_code == 400
    assert server4_error.value.status_code == 400

    with s.Admin() as admin:
        assert admin.rooms["lab"] == r.room("lab", config=CONFIG)
        assert admin._uproot_sessions == sessions

    assert not released("lab")

    response = asyncio.run(
        new_session_in_room_form(assignees='["a1"]', disable_growth=True)
    )

    assert response.status_code == 303

    with s.Admin() as admin:
        room = admin.rooms["lab"]

    assert room["open"] is True
    assert room["capacity"] == 2
    assert released("lab")

    with s.Session(room["sname"]) as session:
        assert session.room == "lab"
        labels = []

        for pid in session._uproot_players:
            with s.Player(pid.sname, pid.uname) as player:
                labels.append(player.label)

    assert sorted(labels) == ["", "a1"]


async def authenticated() -> dict:
    return {"user": "admin"}


def test_session_in_room_rejects_negative_nplayers():
    setup(lab={"config": CONFIG})
    app = FastAPI()
    app.include_router(server2.router)
    app.dependency_overrides[server2.auth_required] = authenticated
    client = TestClient(app)

    def post(nplayers: str):
        return client.post(
            f"{d.ROOT}/admin/room/lab/",
            data={
                "config": CONFIG,
                "assignees": "[]",
                "nplayers": nplayers,
                "disable_growth": "true",
            },
            follow_redirects=False,
        )

    assert post("-1").status_code == 422
    assert post("0").status_code == 303

    with s.Admin() as admin:
        assert admin.rooms["lab"]["capacity"] == 0


def test_capacity_zero_admits_only_reentry_and_precreated_slots(monkeypatch):
    monkeypatch.setattr(u, "APPS", {}, raising=False)
    sname = setup(lab={"config": CONFIG, "open": True})

    with s.Admin() as admin:
        admin.rooms["lab"]["sname"] = sname

    with s.Session(sname) as session:
        c.create_players(session, n=1, data=[{"label": "slot1"}])

    r.sync("lab")
    asyncio.run(room_ops.set_room_capacity("lab", 0))

    app = FastAPI()
    app.include_router(server3.router)
    client = TestClient(app)

    def post(label: str):
        return client.post(
            f"{d.ROOT}/room/lab/", data={"label": label}, follow_redirects=False
        )

    claimed = post("slot1")
    assert claimed.status_code == 303

    assert post("newcomer").status_code == 423

    reentry = post("slot1")
    assert reentry.status_code == 303
    assert reentry.headers["location"] == claimed.headers["location"]


def test_default_room_with_session_is_rejected(monkeypatch):
    sname = setup()
    monkeypatch.setattr(d, "DEFAULT_ROOMS", [r.room("lab", sname=sname)])

    with s.Admin() as admin:
        with pytest.raises(ValueError):
            j.synchronize_rooms(admin)

        assert "lab" not in admin.rooms

    with s.Session(sname) as session:
        assert session.room is None


def test_default_rooms_are_added_once(monkeypatch):
    setup()
    monkeypatch.setattr(d, "DEFAULT_ROOMS", [r.room("lab", config=CONFIG)])

    with s.Admin() as admin:
        j.synchronize_rooms(admin)
        admin.rooms["lab"]["open"] = True
        j.synchronize_rooms(admin)

        assert admin.rooms["lab"]["config"] == CONFIG
        assert admin.rooms["lab"]["open"] is True
