import asyncio
import sys
from collections import defaultdict
from types import SimpleNamespace

import anyio
import orjson
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sortedcontainers import SortedList

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.jobs as j
import uproot.queues as q
import uproot.storage as s
from uproot import server1
from uproot.smithereens import (
    live,
    mark_dropout,
    move_to_end,
    stop_watching_for_dropout,
    watch_for_dropout,
)


async def handle_dropout(player):
    player.dropout_calls += 1
    move_to_end(player)


async def count_first(player):
    player.first_calls += 1


async def count_second(player):
    player.second_calls += 1


async def stop_partner(player):
    player.dropout_calls += 1

    with s.Player(*player.partner) as partner:
        stop_watching_for_dropout(partner)


async def watch_partner(player):
    player.dropout_calls += 1

    with s.Player(*player.partner) as partner:
        watch_for_dropout(partner, handle_dropout)


async def mark_partner(player):
    player.dropout_calls += 1
    mark_dropout(player.partner)


def add_partner(pid):
    with s.Session(pid.sname) as session:
        partner = c.create_player(session)

    for one, other in ((pid, partner), (partner, pid)):
        with s.Player(*one) as player:
            player.page_order = ["dropout-test/Hello"]
            player.show_page = 0
            player.dropout_calls = 0
            player.partner = other

    return partner


@pytest.fixture
def watched_player(monkeypatch):
    d.DATABASE.reset()
    monkeypatch.setattr(u, "ONLINE", defaultdict(dict))
    monkeypatch.setattr(u, "ONLINE_SORTED", SortedList())
    monkeypatch.setattr(u, "WATCH", set())
    monkeypatch.setattr(u, "MANUAL_DROPOUTS", set())
    monkeypatch.setattr(u, "APPS", {__name__: sys.modules[__name__]}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"dropout-test": []})
    monkeypatch.setattr(q, "Q", {})
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", 9.0)

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "dropout-test")

    with s.Session(sid) as session:
        pid = c.create_player(session)

    with s.Player(*pid) as player:
        player.page_order = ["dropout-test/Hello"]
        player.show_page = 0
        player.started = True
        player.dropout_calls = 0
        watch_for_dropout(player, handle_dropout)

    app = FastAPI()
    app.include_router(server1.router)

    return TestClient(app), pid


def hello(websocket, future=1):
    websocket.send_json({"endpoint": "hello", "future": future})

    assert orjson.loads(websocket.receive_bytes())["payload"]["future"] == future


async def poll_dropouts(app):
    task = asyncio.create_task(j.dropout_watcher(app))

    try:
        await asyncio.sleep(0)
    finally:
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.parametrize(
    "cancel_scope", [False, True], ids=["disconnect", "cancel-scope"]
)
async def test_websocket_cleanup_finishes_live_handler(
    watched_player, monkeypatch, cancel_scope
):
    client, pid = watched_player
    started = asyncio.Event()
    finished = asyncio.Event()

    class LivePage:
        @live
        async def wait(page, player):
            started.set()
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                finished.set()

    monkeypatch.setattr(server1, "path2page", lambda path: LivePage)
    deregister = q.deregister
    messages = iter(
        (
            {"type": "websocket.connect"},
            {
                "type": "websocket.receive",
                "text": orjson.dumps(
                    {
                        "endpoint": "invoke",
                        "payload": {"mname": "wait", "args": [], "kwargs": {}},
                    }
                ).decode(),
            },
            {"type": "websocket.disconnect", "code": 1000},
        )
    )

    async def receive():
        message = next(messages)
        if message["type"] == "websocket.disconnect":
            async with asyncio.timeout(5):
                await started.wait()
        return message

    async def send(message):
        pass

    with anyio.CancelScope() as scope:

        def deregister_then_cancel(path, queue):
            if cancel_scope:
                asyncio.get_running_loop().call_soon(scope.cancel)
            deregister(path, queue)

        monkeypatch.setattr(q, "deregister", deregister_then_cancel)

        await client.app(
            {
                "type": "websocket",
                "path": f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
                "root_path": "",
                "scheme": "ws",
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"origin", b"http://testserver"),
                ],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "subprotocols": [],
            },
            receive,
            send,
        )

    assert finished.is_set()
    assert tuple(pid) not in q.Q


async def test_closed_tab_triggers_dropout_once_after_tolerance(
    watched_player, monkeypatch
):
    client, pid = watched_player
    monkeypatch.setattr(u, "time", lambda: 100.0)

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        hello(websocket)

    assert tuple(pid) not in q.Q

    monkeypatch.setattr(u, "time", lambda: 130.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player.show_page == 0

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 1
        assert player._uproot_dropout is True
        assert player.show_page == len(player.page_order)
        assert player._uproot_watch == []

    assert not u.WATCH
    assert u.find_online(pid) == 100.0
    assert pid not in u.who_online(sname=pid.sname)


async def test_reconnecting_before_tolerance_resets_dropout_clock(
    watched_player, monkeypatch
):
    client, pid = watched_player

    for now in (100.0, 125.0):
        monkeypatch.setattr(u, "time", lambda now=now: now)

        with client.websocket_connect(
            f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
            headers={"origin": "http://testserver"},
        ) as websocket:
            hello(websocket)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0

    monkeypatch.setattr(u, "time", lambda: 156.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 1


def test_closing_one_tab_preserves_other_tabs_last_seen(watched_player, monkeypatch):
    client, pid = watched_player
    path = f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/"
    headers = {"origin": "http://testserver"}

    with client.websocket_connect(path, headers=headers) as remaining:
        monkeypatch.setattr(u, "time", lambda: 100.0)
        hello(remaining)

        with client.websocket_connect(path, headers=headers) as closing:
            monkeypatch.setattr(u, "time", lambda: 110.0)
            hello(closing)

        assert u.find_online(pid) == 110.0
        assert len(q.Q[tuple(pid)]) == 1

        monkeypatch.setattr(u, "time", lambda: 120.0)
        hello(remaining, future=2)

        assert u.find_online(pid) == 120.0

    assert tuple(pid) not in q.Q


async def test_missing_heartbeats_trigger_dropout(watched_player, monkeypatch):
    client, pid = watched_player
    monkeypatch.setattr(u, "time", lambda: 100.0)

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        hello(websocket)
        monkeypatch.setattr(u, "time", lambda: 131.0)
        await poll_dropouts(client.app)

        with s.Player(*pid) as player:
            assert player.dropout_calls == 1


async def test_player_never_seen_online_is_not_timed_out(watched_player):
    client, pid = watched_player
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player._uproot_dropout is False

    assert u.WATCH


async def test_finished_player_closing_tab_is_not_a_dropout(
    watched_player, monkeypatch
):
    client, pid = watched_player

    with s.Player(*pid) as player:
        player.show_page = len(player.page_order)

    monkeypatch.setattr(u, "time", lambda: 100.0)

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        hello(websocket)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player._uproot_dropout is False
        assert player._uproot_watch == []

    assert not u.WATCH


async def test_manual_dropout_flags_finished_player(watched_player):
    client, pid = watched_player

    with s.Player(*pid) as player:
        player.show_page = len(player.page_order)

    mark_dropout(pid)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player._uproot_dropout is True
        assert player._uproot_watch == []

    assert not u.WATCH
    assert not u.MANUAL_DROPOUTS


async def test_manual_dropout_flags_player_without_watcher(watched_player):
    client, pid = watched_player

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)

    mark_dropout(pid)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player._uproot_dropout is True

    assert not u.MANUAL_DROPOUTS


async def test_manual_dropout_during_handler_waits_for_next_pass(
    watched_player, monkeypatch
):
    client, pid = watched_player
    partner = add_partner(pid)

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)
        watch_for_dropout(player, mark_partner)

    with s.Player(*partner) as player:
        watch_for_dropout(player, handle_dropout)

    monkeypatch.setattr(u, "time", lambda: 100.0)
    u.set_online(pid)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*partner) as player:
        assert player.dropout_calls == 0

    assert u.MANUAL_DROPOUTS == {partner}

    await poll_dropouts(client.app)

    with s.Player(*partner) as player:
        assert player.dropout_calls == 1
        assert player._uproot_dropout is True

    assert not u.MANUAL_DROPOUTS


async def test_manual_dropout_of_unknown_player_is_dropped(watched_player):
    client, pid = watched_player
    mark_dropout(c.t.PlayerIdentifier(pid.sname, "nobody"))
    await poll_dropouts(client.app)

    assert not u.MANUAL_DROPOUTS


async def test_every_watcher_fires_at_its_own_tolerance(watched_player, monkeypatch):
    client, pid = watched_player
    u.WATCH.clear()

    with s.Player(*pid) as player:
        player._uproot_watch = []
        player.first_calls = 0
        player.second_calls = 0
        watch_for_dropout(player, count_first, tolerance=30.0)
        watch_for_dropout(player, count_second, tolerance=60.0)

    monkeypatch.setattr(u, "time", lambda: 100.0)

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        hello(websocket)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.first_calls == 1
        assert player.second_calls == 0

    monkeypatch.setattr(u, "time", lambda: 161.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.first_calls == 1
        assert player.second_calls == 1
        assert player._uproot_watch == []

    assert not u.WATCH


async def test_stopped_player_closing_tab_is_not_a_dropout(watched_player, monkeypatch):
    client, pid = watched_player
    monkeypatch.setattr(u, "time", lambda: 100.0)

    with client.websocket_connect(
        f"{d.ROOT}/ws/{pid.sname}/{pid.uname}/",
        headers={"origin": "http://testserver"},
    ) as websocket:
        hello(websocket)

        with s.Player(*pid) as player:
            stop_watching_for_dropout(player)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 0
        assert player._uproot_dropout is False
        assert player.show_page == 0
        assert player._uproot_watch == []

    assert not u.WATCH


def test_stopping_ends_every_watcher_of_that_player_only(watched_player):
    pid = watched_player[1]
    partner = add_partner(pid)

    with s.Player(*pid) as player:
        watch_for_dropout(player, count_first, tolerance=60.0)

    with s.Player(*partner) as player:
        watch_for_dropout(player, handle_dropout)

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)
        stop_watching_for_dropout(player)

        assert player._uproot_watch == []

    assert {entry[0] for entry in u.WATCH} == {partner}


def test_stopped_watchers_stay_stopped_after_restart(watched_player):
    client, pid = watched_player
    admin = SimpleNamespace(_uproot_key=u.KEY, _uproot_sessions=[pid.sname])
    u.WATCH.clear()
    j.restore(client.app, admin)

    assert {entry[0] for entry in u.WATCH} == {pid}

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)

    assert not u.WATCH

    j.restore(client.app, admin)

    assert not u.WATCH


async def test_stopping_during_handler_skips_entry_and_keeps_watcher_alive(
    watched_player, monkeypatch
):
    client, pid = watched_player
    partner = add_partner(pid)

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)

    for now, one in ((100.0, pid), (101.0, partner)):
        monkeypatch.setattr(u, "time", lambda now=now: now)
        u.set_online(one)

        with s.Player(*one) as player:
            watch_for_dropout(player, stop_partner)

    monkeypatch.setattr(u, "time", lambda: 140.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as first, s.Player(*partner) as second:
        assert first.dropout_calls + second.dropout_calls == 1

    assert not u.WATCH


async def test_watching_during_handler_keeps_watcher_alive(watched_player, monkeypatch):
    client, pid = watched_player
    partner = add_partner(pid)

    with s.Player(*pid) as player:
        stop_watching_for_dropout(player)
        watch_for_dropout(player, watch_partner)

    monkeypatch.setattr(u, "time", lambda: 100.0)
    u.set_online(pid)

    monkeypatch.setattr(u, "time", lambda: 131.0)
    await poll_dropouts(client.app)

    with s.Player(*pid) as player:
        assert player.dropout_calls == 1

    assert {entry[0] for entry in u.WATCH} == {partner}
