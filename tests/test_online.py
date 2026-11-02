import sys
from pathlib import Path

import pytest

uproot_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(uproot_src))

import uproot as u
import uproot.deployment as d
import uproot.events as e
import uproot.types as t


@pytest.fixture
def clean_online_state():
    u.ONLINE.clear()
    u.ONLINE_SORTED.clear()
    yield
    u.ONLINE.clear()
    u.ONLINE_SORTED.clear()


@pytest.mark.parametrize("tolerance", [None, 30.0])
def test_who_online_session_filter_skips_other_sessions(
    clean_online_state, monkeypatch, tolerance
):
    player_a = t.PlayerIdentifier(sname="A", uname="alice")
    player_b = t.PlayerIdentifier(sname="B", uname="bob")

    u.ONLINE[player_a.sname][player_a.uname] = 100.0
    u.ONLINE[player_b.sname][player_b.uname] = 105.0
    u.ONLINE_SORTED.add((100.0, player_a))
    u.ONLINE_SORTED.add((105.0, player_b))
    monkeypatch.setattr(u, "time", lambda: 110.0)
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", 9.0)

    assert u.who_online(tolerance=tolerance, sname="A") == {player_a}
    assert u.who_online(tolerance=tolerance, sname="missing") == set()


@pytest.mark.parametrize("interval", [1.0, 9.0, 27.0])
def test_who_online_default_expires_after_keepalive_slack(
    clean_online_state, monkeypatch, interval
):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", interval)
    monkeypatch.setattr(u, "time", lambda: 100.0)
    pid = t.PlayerIdentifier("A", "alice")
    u.set_online(pid)

    monkeypatch.setattr(u, "time", lambda: 100.0 + interval + 3.0)

    assert u.who_online() == {pid}

    monkeypatch.setattr(u, "time", lambda: 100.0 + interval + 3.01)

    assert u.who_online() == set()
    assert u.find_online(pid) == 100.0


@pytest.mark.parametrize(
    "tolerance, expected",
    [
        (0.0, {"carol"}),
        (10.0, {"carol"}),
        (25.0, {"bob", "carol"}),
        (60.0, {"alice", "bob", "carol"}),
    ],
)
def test_who_online_honors_explicit_tolerance(
    clean_online_state, monkeypatch, tolerance, expected
):
    for uname, last_seen in (("alice", 90.0), ("bob", 100.0), ("carol", 125.0)):
        monkeypatch.setattr(u, "time", lambda last_seen=last_seen: last_seen)
        u.set_online(t.PlayerIdentifier("A", uname))

    monkeypatch.setattr(u, "time", lambda: 125.0)

    assert u.who_online(tolerance=tolerance) == {
        t.PlayerIdentifier("A", uname) for uname in expected
    }


def test_who_online_default_filters_stale_players_across_sessions(
    clean_online_state, monkeypatch
):
    monkeypatch.setattr(d, "KEEPALIVE_INTERVAL", 9.0)

    for sname, last_seen in (("stale", 80.0), ("A", 100.0), ("B", 105.0)):
        monkeypatch.setattr(u, "time", lambda last_seen=last_seen: last_seen)
        u.set_online(t.PlayerIdentifier(sname, "alice"))

    monkeypatch.setattr(u, "time", lambda: 110.0)

    assert u.who_online() == {
        t.PlayerIdentifier("A", "alice"),
        t.PlayerIdentifier("B", "alice"),
    }


def test_identical_timestamps_are_allowed(clean_online_state, monkeypatch):
    monkeypatch.setattr(u, "time", lambda: 100.0)
    players = [t.PlayerIdentifier("A", uname) for uname in ("alice", "bob")]

    for pid in (*players, *players):
        u.set_online(pid)

    assert u.who_online(tolerance=0.0) == set(players)
    assert len(u.ONLINE_SORTED) == 2


def test_set_online_notifies_every_attendance_subscriber(clean_online_state):
    pid = t.PlayerIdentifier(sname="attendance-fanout", uname="alice")
    first = e.ATTENDANCE[pid.sname].subscribe()
    second = e.ATTENDANCE[pid.sname].subscribe()

    try:
        u.set_online(pid)

        assert first.get_nowait() == pid
        assert second.get_nowait() == pid
    finally:
        del e.ATTENDANCE[pid.sname]
