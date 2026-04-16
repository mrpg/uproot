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

The returned :class:`Database` replaces the process-global store so
that ``Session``, ``Player``, ``Group``, etc. resolve against the
opened file.  Call :meth:`Database.close` (or use a ``with`` block)
to restore the previous store.
"""

from __future__ import annotations

from typing import Any

import appendmuch

import uproot.cache as cache
import uproot.deployment as d
from uproot.stable import CODEC
from uproot.storage import Admin, Group, Player, Session


class Database:
    """Read-only handle to an uproot database file.

    Parameters
    ----------
    path : str
        Path to an ``uproot.sqlite3`` file.
    """

    def __init__(self, path: str) -> None:
        driver = appendmuch.Sqlite3(str(path), table_prefix="uproot")
        self._store = appendmuch.Store(driver, codec=CODEC)
        self._store.load()

        self._prev_store = d.STORE
        d.STORE = self._store
        cache.set_store(self._store)

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

    # ── Lifecycle ────────────────────────────────────────────────

    def close(self) -> None:
        """Close the database and restore the previous global store."""
        self._store.close()
        d.STORE = self._prev_store
        cache.set_store(self._prev_store)

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Database({self._store.driver!r})"


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
