import os
from pathlib import Path

import appendmuch
import pytest

import uproot as u
import uproot.cache as cache
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
from uproot.read import read
from uproot.stable import CODEC


def build_read_database(path: Path) -> None:
    driver = appendmuch.Sqlite3(str(path), table_prefix="uproot")
    store = appendmuch.Store(driver, codec=CODEC)
    previous_cache_store = cache.STORE
    previous_store_attribute_exists = "STORE" in vars(d)
    previous_store_attribute = vars(d).get("STORE")
    d.STORE = store
    cache.set_store(store)
    try:
        store.load()
        u.CONFIGS["readtest"] = []
        with s.Admin() as admin:
            c.create_admin(admin)
            sid = c.create_session(admin, "readtest", sname="session1")
        with s.Session(*sid) as session:
            pid1 = c.create_player(session, uname="player1")
            pid2 = c.create_player(session, uname="player2")
            gid = c.create_group(session, [pid1, pid2], gname="group1")
        with s.Player(*pid1) as player:
            player.label = "A"
            player.role = "buyer"
            player.score = 7
        with s.Player(*pid2) as player:
            player.label = "B"
            player.role = "seller"
        with s.Group(*gid) as group:
            group.round = 1
    finally:
        store.close()
        if previous_store_attribute_exists:
            d.STORE = previous_store_attribute
        else:
            vars(d).pop("STORE", None)
        if previous_cache_store is None:
            cache.STORE = None
            cache.MEMORY_HISTORY = {}
        else:
            cache.set_store(previous_cache_store)


def test_read_plain_rows(tmp_path):
    path = tmp_path / "uproot.sqlite3"
    build_read_database(path)

    with read(os.fspath(path)) as database:
        assert database.session_rows(["sid"]) == [
            {"session": "session1", "sid": "session1"}
        ]
        assert database.group_rows(["round"]) == [
            {"session": "session1", "group": "group1", "round": 1}
        ]
        assert database.player_rows(["label", "role", "score"]) == [
            {
                "session": "session1",
                "uname": "player1",
                "label": "A",
                "role": "buyer",
                "score": 7,
            },
            {
                "session": "session1",
                "uname": "player2",
                "label": "B",
                "role": "seller",
                "score": None,
            },
        ]
        assert database.membership_rows() == [
            {
                "session": "session1",
                "group": "group1",
                "uname": "player1",
                "position": 0,
            },
            {
                "session": "session1",
                "group": "group1",
                "uname": "player2",
                "position": 1,
            },
        ]


def test_read_snapshot(tmp_path):
    path = tmp_path / "uproot.sqlite3"
    build_read_database(path)

    with read(os.fspath(path)) as database:
        snapshot = database.snapshot(
            session_fields=["sid"],
            group_fields=["round"],
            player_fields=["label"],
        )

    assert snapshot.as_dict() == {
        "sessions": [{"session": "session1", "sid": "session1"}],
        "groups": [{"session": "session1", "group": "group1", "round": 1}],
        "players": [
            {"session": "session1", "uname": "player1", "label": "A"},
            {"session": "session1", "uname": "player2", "label": "B"},
        ],
        "memberships": [
            {
                "session": "session1",
                "group": "group1",
                "uname": "player1",
                "position": 0,
            },
            {
                "session": "session1",
                "group": "group1",
                "uname": "player2",
                "position": 1,
            },
        ],
    }


def test_read_plain_rows_reject_identifier_field_collisions(tmp_path):
    path = tmp_path / "uproot.sqlite3"
    build_read_database(path)

    with read(os.fspath(path)) as database:
        with pytest.raises(ValueError, match="session"):
            database.session_rows(["session"])

        with pytest.raises(ValueError, match="session"):
            database.group_rows(["session"])

        with pytest.raises(ValueError, match="group"):
            database.group_rows(["group"])

        with pytest.raises(ValueError, match="session"):
            database.player_rows(["session"])

        with pytest.raises(ValueError, match="uname"):
            database.player_rows(["uname"])
