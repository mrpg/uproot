"""Check uproot's rooms against the Lean model in uproot-formal
(UprootFormal/Rooms.lean and UprootFormal/Labels.lean).

Not run by default. Opt in with UPROOT_MODEL_TESTS=1, e.g.:

    UPROOT_MODEL_TESTS=1 uv run pytest tests/test_rooms_model.py

test_refinement runs random adversarial walks over the real room handlers.
After every operation, the abstract state must be unchanged (a rejected request)
or reachable by at most K steps of the model's Step relation (transcribed
below), and EventsOK, AssocOK, LabelsUnique and the exactness of the encoding
(no "" config or sname, capacities are non-negative ints) must hold on the real
state. Rooms may name a config that is not loaded, and restarts may load or
unload one. Size: UPROOT_MODEL_SEEDS (default "1"; comma-separated), and
UPROOT_MODEL_WALKS (default 50) walks of UPROOT_MODEL_STEPS (default 120) each.

test_admission_cases replays admission cases computed by the Lean model (in
uproot-formal: lake exe room-cases > room-cases.jsonl) through
POST /room/{roomname}/. Set UPROOT_FORMAL_CASES to that file;
UPROOT_FORMAL_SHARD=k/n replays every n-th case starting with the k-th.
"""

import asyncio
import inspect
import json
import os
import random
import types
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.jobs as j
import uproot.rooms as r
import uproot.server4 as api
import uproot.storage as s
from uproot import cli, server, server2, server3

pytestmark = pytest.mark.skipif(
    not os.getenv("UPROOT_MODEL_TESTS"),
    reason="model tests are opt-in: set UPROOT_MODEL_TESTS=1",
)

CONFIG = "model-cfg"  # always loaded
EXTRA = "model-extra"  # loaded or not, may change at restarts
UNLOADED = "model-unloaded"  # never loaded

# The restart operation replays the room-relevant prefix of server.lifespan.
LIFESPAN_PREFIX = """    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(admin)
        j.restore(app, admin)
        nsessions = len(admin._uproot_sessions)
        roomnames = list(admin.rooms)

    for roomname in roomnames:
        r.sync(roomname)
"""


async def fake_render(*args: Any, metadata: Any = None, **kwargs: Any) -> str:
    page = args[3] if len(args) > 3 else kwargs.get("page")
    return json.dumps({"page": page, "metadata": metadata})


@pytest.fixture
def model_env(monkeypatch):
    monkeypatch.setattr(u, "CONFIGS", u.CONFIGS | {CONFIG: []})  # a private copy
    monkeypatch.setitem(u.CONFIGS_EXTRA, CONFIG, {"settings": {}})
    monkeypatch.setattr(server3, "path2page", lambda path: path)
    monkeypatch.setattr(server3, "render", fake_render)
    monkeypatch.setattr(d, "DEFAULT_ROOMS", [])


def reset() -> None:
    d.DATABASE.reset()
    d.STORE.load()  # DATABASE.reset() clears the driver, not the store's cache
    e.ROOMS.clear()

    with s.Admin() as admin:
        c.create_admin(admin)
        admin.rooms = {}
        admin._uproot_sessions = []


# ------------------------------------------------- the model (Rooms.lean)


@dataclass(frozen=True)
class Room:
    config: Any
    labels: Any
    capacity: Any
    open: bool
    sname: Any


@dataclass(frozen=True)
class World:
    rooms: frozenset  # of (roomname, Room)
    sessions: frozenset
    sessroom: frozenset  # of (sname, roomname), for non-None entries
    events: frozenset  # roomnames whose event is set
    configs: frozenset  # uproot.CONFIGS (fixed while a process runs)

    def room_map(self) -> dict:
        return dict(self.rooms)

    def sessroom_map(self) -> dict:
        return dict(self.sessroom)


def mk(rooms: dict, sessions: Any, sessroom: dict, events: Any, configs: Any) -> World:
    return World(
        frozenset(rooms.items()),
        frozenset(sessions),
        frozenset((k, v) for k, v in sessroom.items() if v is not None),
        frozenset(events),
        frozenset(configs),
    )


def ready(room: Room, configs: frozenset) -> bool:
    return bool(room.open) and (room.sname is not None or room.config in configs)


def set_room(w: World, roomname: str, room: Room | None) -> World:
    rooms = w.room_map()

    if room is None:
        rooms.pop(roomname, None)
    else:
        rooms[roomname] = room

    return mk(rooms, w.sessions, w.sessroom_map(), w.events, w.configs)


def link(w: World, sname: str, roomname: str | None) -> World:
    sessroom = w.sessroom_map()
    sessroom[sname] = roomname

    return mk(w.room_map(), w.sessions, sessroom, w.events, w.configs)


def link_opt(w: World, sname: str | None, roomname: str) -> World:
    return w if sname is None else link(w, sname, roomname)


def new_session(w: World, sname: str) -> World:
    sessroom = w.sessroom_map()
    sessroom[sname] = None

    return mk(w.room_map(), w.sessions | {sname}, sessroom, w.events, w.configs)


def sync(w: World, roomname: str) -> World:
    room = w.room_map().get(roomname)
    events = set(w.events)

    if room is not None and ready(room, w.configs):
        events.add(roomname)
    else:
        events.discard(roomname)

    return mk(w.room_map(), w.sessions, w.sessroom_map(), events, w.configs)


def available(w: World, sname: str, roomname: str) -> bool:
    return (
        sname in w.sessions
        and all(room.sname != sname for rn, room in w.rooms if rn != roomname)
        and w.sessroom_map().get(sname) in (None, roomname)
    )


def restart(w: World, defaults: list, names: list, configs: frozenset) -> World:
    rooms = w.room_map()

    for roomname, room in defaults:  # addDefaults, on fresh events and configs
        if roomname not in rooms:
            rooms[roomname] = room

    w = mk(rooms, w.sessions, w.sessroom_map(), (), configs)

    for roomname in names:  # syncAll
        w = sync(w, roomname)

    return w


def successors(w: World, post: World, restart_args: Any) -> list:
    """One model step from w. Free parameters (the stored room, capacities, new
    session names) are taken from the observed post-state."""
    out = []
    post_rooms = post.room_map()
    new_snames = post.sessions - w.sessions

    for sname in new_snames:
        out.append(("newSession", new_session(w, sname)))

    for rn in set(w.room_map()) | set(post_rooms):
        cur = w.room_map().get(rn)

        if cur is None and rn in post_rooms:
            room = post_rooms[rn]
            if room.sname is None or available(w, room.sname, rn):
                stored = link_opt(set_room(w, rn, room), room.sname, rn)
                out.append(("createRoom", sync(stored, rn)))

        if cur is None:
            continue

        if rn in post_rooms and cur.sname is None:
            room = post_rooms[rn]
            if room.sname is None or available(w, room.sname, rn):
                stored = link_opt(set_room(w, rn, room), room.sname, rn)
                out.append(("updateRoom", sync(stored, rn)))

        if cur.sname is not None:
            detached = link(set_room(w, rn, replace(cur, sname=None)), cur.sname, None)
            out.append(("disassociate", sync(detached, rn)))
        else:
            out.append(("close", sync(set_room(w, rn, replace(cur, open=False)), rn)))
            out.append(("delete", sync(set_room(w, rn, None), rn)))

        for b in (False, True):
            if not b or cur.sname is not None or cur.config in w.configs:
                out.append(("setOpen", sync(set_room(w, rn, replace(cur, open=b)), rn)))

        caps = {cur.capacity} | (
            {post_rooms[rn].capacity} if rn in post_rooms else set()
        )

        for cap in caps:
            out.append(("setCapacity", set_room(w, rn, replace(cur, capacity=cap))))

        if cur.sname is None:
            for sname in new_snames:
                for cap in caps:
                    room = replace(cur, sname=sname, open=True, capacity=cap)
                    stored = link(set_room(new_session(w, sname), rn, room), sname, rn)
                    out.append(("sessionInRoom", sync(stored, rn)))

                if ready(cur, w.configs):
                    room = replace(cur, sname=sname)
                    stored = link(set_room(new_session(w, sname), rn, room), sname, rn)
                    out.append(("joinCreates", stored))

    if restart_args is not None:
        defaults, names = restart_args
        stored = restart(w, defaults, [], post.configs).room_map()

        if all(room.sname is None for _, room in defaults) and all(
            rn in names for rn in stored
        ):
            out.append(("restart", restart(w, defaults, names, post.configs)))

    return out


def explain(pre: World, post: World, depth: int, restart_args: Any) -> set | None:
    """All model step sequences of minimal length (at most depth) from pre to
    post, as tuples of constructor names: {()} for a stutter, None if none."""
    if post == pre:
        return {()}

    frontier = [(pre, ())]

    for _ in range(depth):
        nxt, found = [], set()

        for w, path in frontier:
            for name, w2 in successors(w, post, restart_args):
                if w2 == post:
                    found.add(path + (name,))
                nxt.append((w2, path + (name,)))

        if found:
            return found

        frontier = nxt

    return None


# --------------------------------------------- abstraction of real state


def to_room(raw: dict) -> Room:
    labels = tuple(raw["labels"]) if raw["labels"] is not None else None

    return Room(raw["config"], labels, raw["capacity"], bool(raw["open"]), raw["sname"])


def session_room(sname: str) -> Any:
    if sname == "" or not r.valid_token(sname):
        return None

    try:
        with s.Session(sname) as session:
            return session.room
    except AttributeError:
        return None


def abstract(known: set) -> tuple[World, dict]:
    with s.Admin() as admin:
        sessions = set(admin._uproot_sessions)
        raw = {k: dict(v) for k, v in admin.rooms.items()}

    rooms = {rn: to_room(room) for rn, room in raw.items()}
    sessroom = {sname: session_room(sname) for sname in known | sessions}
    events = {rn for rn, event in e.ROOMS.items() if event.is_set()}

    return mk(rooms, sessions, sessroom, events, u.CONFIGS), raw


def violations(w: World, raw: dict) -> list[str]:
    errors = []
    rooms, sessroom = w.room_map(), w.sessroom_map()

    for rn, room in raw.items():  # the encoding is exact
        if room["config"] == "" or room["sname"] == "":
            errors.append(f"room {rn}: empty string stored: {room}")

        cap = room["capacity"]

        if cap is not None and (type(cap) is not int or cap < 0):
            errors.append(f"room {rn}: capacity {cap!r}")

    for rn in set(rooms) | set(w.events):  # EventsOK
        if (rn in w.events) != (rn in rooms and ready(rooms[rn], w.configs)):
            errors.append(f"EventsOK fails at {rn}")

    for rn, room in rooms.items():  # AssocOK, both directions
        if room.sname is not None and (
            sessroom.get(room.sname) != rn or room.sname not in w.sessions
        ):
            errors.append(f"AssocOK fails: room {rn} names {room.sname}")

    for sname, rn in sessroom.items():
        if rn not in rooms or rooms[rn].sname != sname:
            errors.append(f"AssocOK fails: session {sname} names {rn}")

    for sname in w.sessions:  # LabelsUnique
        labels = []

        with s.Session(sname) as session:
            for pid in session._uproot_players:
                with s.Player(pid.sname, pid.uname) as player:
                    labels.append(player.label)

        nonempty = [label for label in labels if label != ""]

        if len(nonempty) != len(set(nonempty)):
            errors.append(f"LabelsUnique fails in {sname}: {labels}")

    return errors


# -------------------------------------------------------------- operations

ROOMS = ["r1", "r2", "r3", "quick1"]
LABELSETS = [None, [], ["a", "b"], ["a"], ["a", "a"], [""]]
CAPS = [None, 0, 1, 2, 3, -1, 2.5, True, "3"]
CONFIGS = [None, "", CONFIG, EXTRA, UNLOADED]
JOINLABELS = [None, "", "a", "b", "c", "a b"]


class Walk:
    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.known: set[str] = set()  # session names created or tried
        self.restart_args: Any = None

    def run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def pick_sname(self) -> str:
        """Mostly a free existing session, sometimes any session or garbage."""
        with s.Admin() as admin:
            existing = list(admin._uproot_sessions)
            claimed = {room["sname"] for room in admin.rooms.values()}

        free = [sname for sname in existing if sname not in claimed]
        roll = self.rng.random()

        if free and roll < 0.6:
            return self.rng.choice(free)
        if existing and roll < 0.8:
            return self.rng.choice(existing)

        return self.rng.choice(["ghost", "", " "])

    def pick_room(self) -> str:
        with s.Admin() as admin:
            existing = list(admin.rooms)

        if existing and self.rng.random() < 0.8:
            return self.rng.choice(existing)

        return self.rng.choice(ROOMS)

    def new_sname(self) -> str:
        sname = self.rng.choice(["", "", f"s{self.rng.randrange(10**6)}", "ghost", " "])
        self.known.add(sname)

        return sname

    def room_sname(self, roomname: str) -> Any:
        with s.Admin() as admin:
            room = admin.rooms.get(roomname)

        return None if room is None else room["sname"]

    def create_room_api(self) -> None:
        rng = self.rng
        body = {
            "name": rng.choice(ROOMS),
            "config": rng.choice(CONFIGS),
            "labels": rng.choice(LABELSETS),
            "capacity": rng.choice(CAPS),
            "open": rng.choice([None, False, True]),
        }

        if rng.random() < 0.6:
            body["sname"] = self.pick_sname()

        self.run(api.create_room(api.RoomCreate.model_validate(body), None))

    def new_room_form(self) -> None:
        rng = self.rng
        self.run(
            server2.new_room2(
                request=None,
                name=rng.choice(ROOMS),
                config=rng.choice(["", " ", CONFIG, EXTRA, UNLOADED]),
                labels=rng.choice(["", "a\nb", "a\na", "c"]),
                use_labels=rng.choice([False, True]),
                capacity=rng.choice(["", "0", "2", "-1", "x"]),
                room_sname=rng.choice(["", self.pick_sname()]),
                open=rng.choice([False, True]),
                auth={},
            )
        )

    def update_room_api(self) -> None:
        rng = self.rng
        fields = {}

        for key, pool in [
            ("config", CONFIGS),
            ("labels", LABELSETS),
            ("capacity", CAPS),
            ("open", [None, False, True]),
        ]:
            if rng.random() < 0.5:
                fields[key] = rng.choice(pool)

        if rng.random() < 0.5:
            fields["sname"] = self.pick_sname()

        body = api.RoomUpdate.model_validate(fields)
        self.run(api.update_room(self.pick_room(), body, None))

    def update_room_form(self) -> None:
        rng = self.rng
        self.run(
            server2.update_room_settings(
                request=None,
                roomname=self.pick_room(),
                config=rng.choice(["", CONFIG, EXTRA, UNLOADED]),
                labels=rng.choice(["", "a\nb"]),
                use_labels=rng.choice([False, True]),
                capacity=rng.choice(["", "1", "-2"]),
                room_sname=rng.choice(["", self.pick_sname()]),
                open=rng.choice([False, True]),
                auth={},
            )
        )

    def disassociate_rpc(self) -> None:  # incl. stale or foreign session names
        roomname = self.pick_room()
        own = self.rng.random() < 0.6
        sname = self.room_sname(roomname) if own else self.pick_sname()
        self.run(server2.FUNS["disassociate"](roomname, sname))

    def disassociate_api(self) -> None:
        self.run(api.disassociate_room(self.pick_room(), None))

    def close(self) -> None:
        flag = self.rng.choice([False, True])
        self.run(server2.FUNS["close_room"](self.pick_room(), flag))

    def set_open(self) -> None:
        value = self.rng.choice([False, True, 0, 1, "", "x"])
        self.run(server2.FUNS["set_room_open"](self.pick_room(), value))

    def set_capacity(self) -> None:
        value = self.rng.choice(CAPS)
        self.run(server2.FUNS["set_room_capacity"](self.pick_room(), value))

    def delete(self) -> None:
        if self.rng.random() < 0.5:
            self.run(server2.FUNS["delete_room"](self.pick_room()))
        else:
            self.run(api.delete_room(self.pick_room(), None))

    def session_in_room_form(self) -> None:  # nplayers >= 0 is enforced by FastAPI
        rng = self.rng
        self.run(
            server2.new_session_in_room(
                request=None,
                roomname=self.pick_room(),
                config=CONFIG,
                assignees=rng.choice(
                    [
                        "",
                        "[]",
                        '["a"]',
                        '["a","b"]',
                        '["a","a"]',
                        '[""]',
                        '["c","b","a","x"]',
                    ]
                ),
                nplayers=rng.choice([0, 1, 2, 3]),
                settings="",
                sname=self.new_sname(),
                unames=rng.choice(
                    ["", "p1", "p1\np2", "bad name", "p1\np1", "p1\np2\np3"]
                ),
                disable_growth=rng.choice([False, True]),
                simulate=False,
                auth={},
            )
        )

    def session_in_room_api(self) -> None:
        rng = self.rng
        body: dict[str, Any] = {
            "n_players": rng.choice([0, 1, 2, 3]),
            "assignees": rng.choice([None, [], ["a"], ["a", "b"], ["a", "a"], [""]]),
            "unames": rng.choice(
                [None, ["p1"], ["p1", "p2"], ["bad name"], ["p1", "p1"]]
            ),
            "no_grow": rng.choice([False, True]),
        }

        if rng.random() < 0.5:
            body["sname"] = self.new_sname()
        if rng.random() < 0.3:
            body["config"] = rng.choice([CONFIG, "nonexistent"])

        session = api.RoomSessionCreate.model_validate(body)
        self.run(api.create_session_in_room(self.pick_room(), session, None))

    def plain_session(self) -> None:
        rng = self.rng
        body: dict[str, Any] = {
            "config": CONFIG,
            "n_players": rng.choice([0, 1, 2]),
            "unames": rng.choice([None, ["p1"], ["bad name"]]),
        }

        if rng.random() < 0.5:
            body["sname"] = self.new_sname()

        self.run(api.create_session(api.SessionCreate.model_validate(body), None))

    def join(self) -> None:
        request = types.SimpleNamespace(app=None)  # only passed through to render
        label = self.rng.choice(JOINLABELS)
        self.run(
            server3.roommain(request=request, roomname=self.pick_room(), label=label)
        )

    def start_player(self) -> None:  # server1: started = True, label untouched
        with s.Admin() as admin:
            snames = list(admin._uproot_sessions)

        if not snames:
            return

        with s.Session(self.rng.choice(snames)) as session:
            pids = list(session._uproot_players)

        if pids:
            pid = self.rng.choice(pids)

            with s.Player(pid.sname, pid.uname) as player:
                player.started = True

    def random_defaults(self) -> list:
        rng = self.rng

        return [
            r.room(
                rng.choice(ROOMS),
                config=rng.choice([None, CONFIG, EXTRA, UNLOADED]),
                open=rng.choice([False, True]),
            )
            for _ in range(rng.choice([0, 1, 2]))
        ]

    def new_process(self) -> None:
        """A new process: events.ROOMS is in-memory, and the project may now
        load different configs."""
        e.ROOMS.clear()

        if self.rng.random() < 0.5:
            if EXTRA in u.CONFIGS:
                del u.CONFIGS[EXTRA]
            else:
                u.CONFIGS[EXTRA] = []

    def lifespan_prefix(self) -> list:

        with s.Admin() as admin:
            c.create_admin(admin)
            j.synchronize_rooms(admin)
            j.restore(None, admin)
            roomnames = list(admin.rooms)

        for roomname in roomnames:
            r.sync(roomname)

        return roomnames

    def defaults_now(self) -> list:
        return [(room["name"], to_room(room)) for room in d.DEFAULT_ROOMS]

    def restart(self) -> None:
        d.DEFAULT_ROOMS[:] = self.random_defaults()
        self.new_process()
        names = self.lifespan_prefix()
        self.restart_args = (self.defaults_now(), names)

    def restart_bad_default(self) -> None:
        """A default room with a session: startup must fail without changing
        rooms. The operator then fixes the configuration and restarts."""
        with s.Admin() as admin:
            snames = list(admin._uproot_sessions)
            before = {k: to_room(dict(v)) for k, v in admin.rooms.items()}

        if not snames:
            return self.restart()

        bad = dict(r.room(self.rng.choice(ROOMS)))
        bad["sname"] = self.rng.choice(snames)
        d.DEFAULT_ROOMS[:] = self.random_defaults() + [bad]

        e.ROOMS.clear()

        with pytest.raises(ValueError):
            self.lifespan_prefix()

        with s.Admin() as admin:
            after = {k: to_room(dict(v)) for k, v in admin.rooms.items()}

        assert after == before, "failed startup changed rooms"
        self.restart()

    def quick_room(self) -> None:  # CLI: create_quick_room, then the server starts
        d.DEFAULT_ROOMS[:] = self.random_defaults()
        self.new_process()
        cli.create_quick_room(CONFIG, False)
        names = self.lifespan_prefix()
        self.restart_args = (self.defaults_now(), names)


# (operation, weight, maximum number of model steps)
OPS = [
    (Walk.create_room_api, 6, 1),
    (Walk.new_room_form, 4, 1),
    (Walk.update_room_api, 5, 1),
    (Walk.update_room_form, 3, 1),
    (Walk.disassociate_rpc, 6, 1),
    (Walk.disassociate_api, 3, 1),
    (Walk.close, 4, 2),
    (Walk.set_open, 5, 1),
    (Walk.set_capacity, 4, 1),
    (Walk.delete, 3, 1),
    (Walk.session_in_room_form, 5, 1),
    (Walk.session_in_room_api, 5, 1),
    (Walk.plain_session, 2, 1),
    (Walk.join, 14, 1),
    (Walk.start_player, 4, 0),
    (Walk.restart, 2, 1),
    (Walk.restart_bad_default, 1, 1),
    (Walk.quick_room, 1, 3),
]

SEEDS = [int(x) for x in os.getenv("UPROOT_MODEL_SEEDS", "1").split(",")]
WALKS = int(os.getenv("UPROOT_MODEL_WALKS", "50"))
STEPS = int(os.getenv("UPROOT_MODEL_STEPS", "120"))


@pytest.mark.parametrize("seed", SEEDS)
def test_refinement(model_env, seed):
    assert LIFESPAN_PREFIX in inspect.getsource(server.lifespan), "lifespan changed"

    rng = random.Random(seed)
    used: set[str] = set()

    for walk_number in range(WALKS):
        reset()
        walk = Walk(rng)
        pre, raw = abstract(walk.known)
        assert pre == mk({}, (), {}, (), u.CONFIGS)
        assert not violations(pre, raw)
        trace: list[Any] = []

        for step in range(STEPS):
            op, _, depth = rng.choices(OPS, [w for _, w, _ in OPS])[0]
            walk.restart_args = None
            outcome = "ok"

            try:
                op(walk)
            except AssertionError:
                raise
            except Exception as exc:  # noqa: BLE001 — a rejected request
                outcome = repr(exc)[:120]

            post, raw = abstract(walk.known)
            paths = explain(pre, post, depth, walk.restart_args)
            errors = violations(post, raw)
            trace.append((op.__name__, outcome, paths))

            where = f"seed {seed}, walk {walk_number}, step {step}"
            assert (
                paths is not None
            ), f"{where}: not a model step\npre:  {pre}\npost: {post}\n{trace[-6:]}"
            assert not errors, f"{where}: {errors}\n{trace[-6:]}"

            used |= {name for path in paths for name in path}
            pre = post

    if WALKS * STEPS >= 2000:
        constructors = {
            "newSession", "createRoom", "updateRoom", "disassociate", "close",
            "setOpen", "setCapacity", "delete", "sessionInRoom", "joinCreates",
            "restart",
        }  # fmt: skip
        assert used == constructors, f"unexercised: {constructors - used}"


# ------------------------------------------- admission (Labels.lean cases)


def players_of(sname: str) -> list:
    out = []

    with s.Session(sname) as session:
        for pid in session._uproot_players:
            with s.Player(pid.sname, pid.uname) as player:
                out.append((pid.uname, player.label, player.started))

    return out


def replay(client: TestClient, case: dict) -> tuple[str, list]:
    reset()

    with s.Admin() as admin:
        if case["sname"] is not None:
            c.create_session(admin, CONFIG, sname=case["sname"])

        admin.rooms["lab"] = r.room(
            "lab",
            config={"cfg": CONFIG, "unknown": UNLOADED}.get(case["config"]),
            labels=case["labels"],
            capacity=case["capacity"],
            open=case["open"],
            sname=case["sname"],
        )

    if case["sname"] is not None:
        with s.Session(case["sname"]) as session:
            session.room = "lab"
            pids = c.create_players(session, n=len(case["players"]))

        for pid, (label, started) in zip(pids, case["players"]):
            with s.Player(pid.sname, pid.uname) as player:
                player.label = label
                player.started = started

    r.sync("lab")
    before = players_of(case["sname"]) if case["sname"] is not None else []
    assert [[label, st] for _, label, st in before] == case["players"]

    data = {"label": case["label"]} if case["label"] != "" else {}
    response = client.post(f"{d.ROOT}/room/lab/", data=data, follow_redirects=False)

    with s.Admin() as admin:
        sname_after = admin.rooms["lab"]["sname"]

    after = players_of(sname_after) if sname_after is not None else []

    if response.status_code == 200:
        body = json.loads(response.text)
        assert body["page"] == "RoomHello.html", body
        meta = body["metadata"]

        if meta["needlabel"]:
            outcome = "badLabel" if meta["bad"] else "askLabel"
        else:
            outcome = "wait"
    elif response.status_code == 423:
        assert json.loads(response.text)["page"] == "RoomFull.html"
        outcome = "full"
    else:
        assert response.status_code == 303, response.text[:200]
        path = urlparse(response.headers["location"]).path.rstrip("/").split("/")
        assert path[-2] == sname_after

        if len(after) == len(before) + 1:
            outcome = "newPlayer"
            assert after[-1][0] == path[-1]
        else:
            assert len(after) == len(before)
            index = [uname for uname, _, _ in before].index(path[-1])
            outcome = "resume" if before[index][2] else "reuseSlot"

    return outcome, [[label, st] for _, label, st in after]


@pytest.mark.skipif(
    not os.getenv("UPROOT_FORMAL_CASES"), reason="set UPROOT_FORMAL_CASES"
)
def test_admission_cases(model_env):
    shard, nshards = (
        int(x) for x in os.getenv("UPROOT_FORMAL_SHARD", "0/1").split("/")
    )
    app = FastAPI()
    app.include_router(server3.router)
    client = TestClient(app)
    total, mismatches = 0, []

    with open(os.environ["UPROOT_FORMAL_CASES"], encoding="utf-8") as f:
        for index, line in enumerate(f):
            if index % nshards != shard:
                continue

            case = json.loads(line)
            outcome, after = replay(client, case)
            total += 1

            if outcome != case["outcome"] or after != case["after"]:
                mismatches.append((case, outcome, after))

    assert total > 0
    assert (
        not mismatches
    ), f"{len(mismatches)}/{total} mismatches, e.g. {mismatches[:3]}"
