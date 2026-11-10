import asyncio

import orjson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.jobs as j
import uproot.rooms as r
import uproot.services.room_service as room_ops
import uproot.storage as s
from uproot import server3

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
    ],
)
def test_ready(open: bool, sname: str | None, config: str | None, expected: bool):
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


def test_negative_capacity_is_rejected():
    setup(lab={})

    with pytest.raises(ValueError):
        r.room("other", capacity=-1)

    with pytest.raises(ValueError):
        asyncio.run(room_ops.set_room_capacity("lab", -1))


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
