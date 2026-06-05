# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
Read-only access to uproot databases for offline analysis.

Open an ``uproot.sqlite3`` file and navigate its data using the same
Storage objects that the server uses internally::

    from uproot.read import read

    db = read("uproot.sqlite3")

    for session in db.sessions:
        for player in session.players:
            with player:
                print(player.name, player.label)

    db.close()

For analysis scripts that need regular dictionaries rather than live
Storage objects, ask for plain rows with selected fields::

    with read("uproot.sqlite3") as db:
        players = db.player_rows(["label", "role", "payoff"])
        memberships = db.membership_rows()

The returned :class:`Database` replaces the process-global store so
that ``Session``, ``Player``, ``Group``, etc. resolve against the
opened file.  Call :meth:`Database.close` (or use a ``with`` block)
to restore the previous store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import appendmuch

import uproot.cache as cache
import uproot.deployment as d
from uproot.stable import CODEC
from uproot.storage import Admin, Group, Player, Session


@dataclass(frozen=True)
class Snapshot:
    """Plain-row view of the core uproot object graph."""

    sessions: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    players: list[dict[str, Any]]
    memberships: list[dict[str, Any]]

    def as_dict(self) -> dict[str, list[dict[str, Any]]]:
        """Return the snapshot as a regular dictionary."""
        return {
            "sessions": self.sessions,
            "groups": self.groups,
            "players": self.players,
            "memberships": self.memberships,
        }


def field_values(
    storage: Any,
    fields: Iterable[str],
    reserved_fields: Iterable[str] = (),
) -> dict[str, Any]:
    reserved = set(reserved_fields)
    row = {}
    for field in fields:
        if field in reserved:
            raise ValueError(f"Field {field!r} collides with a row identifier column")
        try:
            row[field] = getattr(storage, field)
        except AttributeError:
            row[field] = None
    return row


class Database:
    """Read-only handle to an uproot database file.

    Parameters
    ----------
    path : str
        Path to an ``uproot.sqlite3`` file.
    """

    def __init__(self, path: str) -> None:
        driver = appendmuch.Sqlite3(str(path), table_prefix="uproot")
        self.store = appendmuch.Store(driver, codec=CODEC)
        self.store.load()

        self.prev_cache_store = cache.STORE
        self.prev_store_attribute_exists = "STORE" in vars(d)
        self.prev_store_attribute = vars(d).get("STORE")
        d.STORE = self.store
        cache.set_store(self.store)

    # ── Navigation helpers ───────────────────────────────────────

    @property
    def sessions(self) -> list[Any]:
        """All sessions in the database as Storage objects."""
        admin = Admin()
        with admin:
            return list(admin.sessions)

    def session(self, sname: str) -> Any:
        """Get a session by name."""
        return Session(sname)

    def group(self, sname: str, gname: str) -> Any:
        """Get a group by session name and group name."""
        return Group(sname, gname)

    def player(self, sname: str, uname: str) -> Any:
        """Get a player by session name and username."""
        return Player(sname, uname)

    # ── Plain-row analysis helpers ──────────────────────────────

    def session_rows(self, fields: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Return one plain dictionary per session.

        ``fields`` names additional storage fields to include.  Missing fields
        are represented as ``None``.
        """
        rows = []
        for session in self.sessions:
            with session:
                row = {"session": str(session.name)}
                row.update(field_values(session, fields, row))
                rows.append(row)
        return rows

    def group_rows(self, fields: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Return one plain dictionary per group."""
        rows = []
        for session in self.sessions:
            with session:
                session_name = str(session.name)
                groups = list(session.groups)
            for group in groups:
                with group:
                    row = {
                        "session": session_name,
                        "group": str(group.name),
                    }
                    row.update(field_values(group, fields, row))
                    rows.append(row)
        return rows

    def player_rows(self, fields: Iterable[str] = ()) -> list[dict[str, Any]]:
        """Return one plain dictionary per player."""
        rows = []
        for session in self.sessions:
            with session:
                session_name = str(session.name)
                players = list(session.players)
            for player in players:
                with player:
                    row = {
                        "session": session_name,
                        "uname": str(player.name),
                    }
                    row.update(field_values(player, fields, row))
                    rows.append(row)
        return rows

    def membership_rows(self) -> list[dict[str, Any]]:
        """Return group membership rows keyed by session, group, and username."""
        rows = []
        for session in self.sessions:
            with session:
                session_name = str(session.name)
                groups = list(session.groups)
            for group in groups:
                with group:
                    group_name = str(group.name)
                    players = list(group.players)
                for position, player in enumerate(players):
                    with player:
                        rows.append(
                            {
                                "session": session_name,
                                "group": group_name,
                                "uname": str(player.name),
                                "position": position,
                            }
                        )
        return rows

    def snapshot(
        self,
        *,
        session_fields: Iterable[str] = (),
        group_fields: Iterable[str] = (),
        player_fields: Iterable[str] = (),
    ) -> Snapshot:
        """Return plain-row session, group, player, and membership tables."""
        return Snapshot(
            sessions=self.session_rows(session_fields),
            groups=self.group_rows(group_fields),
            players=self.player_rows(player_fields),
            memberships=self.membership_rows(),
        )

    # ── Lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database and restore the previous global store."""
        self.store.close()
        if self.prev_store_attribute_exists:
            d.STORE = self.prev_store_attribute
        else:
            vars(d).pop("STORE", None)

        if self.prev_cache_store is None:
            cache.STORE = None
            cache.MEMORY_HISTORY = {}
        else:
            cache.set_store(self.prev_cache_store)

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Database({self.store.driver!r})"


def read(path: str) -> Database:
    """Open an uproot database file for read-only analysis.

    Parameters
    ----------
    path : str
        Path to an ``uproot.sqlite3`` file.

    Returns
    -------
    Database
        A handle providing access to sessions, groups, and players.

    Examples
    --------
    ::

        from uproot.read import read

        db = read("uproot.sqlite3")

        for session in db.sessions:
            for group in session.groups:
                for player in group.players:
                    with player:
                        print(player.name, player.label)

        db.close()
    """
    return Database(path)
