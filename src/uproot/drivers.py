# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file exposes an internal API that end users MUST NOT rely upon. Rely upon storage.py instead.
"""

import sqlite3
import threading
from abc import ABC
from typing import Any, Iterator, Optional

import msgpack

import uproot.types as t
from uproot.constraints import ensure
from uproot.stable import decode, encode


class DBDriver(ABC):
    now: float = 0.0

    def size(self) -> Optional[int]:
        """Returns approximate database size in octets if possible, else None."""
        raise NotImplementedError

    def dump(self) -> Iterator[bytes]:
        """Serialize all data as msgpack bytes for backup/migration."""
        raise NotImplementedError

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        """Restore data from msgpack stream created by dump()."""
        raise NotImplementedError

    def reset(self) -> None:
        """Initialize/reset database schema. Destroys all existing data."""
        raise NotImplementedError

    def test_connection(self) -> None:
        """Verify database connectivity. Raise exception if unavailable."""
        raise NotImplementedError

    def test_tables(self) -> None:
        """Verify required tables exist. Raise exception if missing."""
        raise NotImplementedError

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        """Insert new entry. Data will be encoded automatically."""
        raise NotImplementedError

    def delete(self, namespace: str, field: str, context: str) -> None:
        """Mark entry as unavailable (tombstone). Does not physically remove."""
        raise NotImplementedError

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        """Return complete history for all fields in all namespaces starting with sstr.
        Used for loading data into memory at startup.
        """
        raise NotImplementedError

    def ensure(self) -> bool:
        try:
            self.test_connection()
        except Exception as exc:
            raise RuntimeError(
                "Cannot connect to database.",
            ) from exc

        try:
            self.test_tables()
            return True
        except Exception:
            self.reset()
            return False


class Memory(DBDriver):
    """Simplified in-memory implementation for write-through operations and startup loading."""

    def __init__(self) -> None:
        # Nested structure: namespace -> field -> list of values
        self.log: dict[str, dict[str, list[t.Value]]] = {}
        self._lock = threading.RLock()

    def test_connection(self) -> None:
        pass

    def test_tables(self) -> None:
        pass

    def size(self) -> Optional[int]:
        return None

    def dump(self) -> Iterator[bytes]:
        with self._lock:
            for namespace, fields in self.log.items():
                for field, values in fields.items():
                    for v in values:
                        yield msgpack.packb(
                            {
                                "namespace": namespace,
                                "field": field,
                                "value": encode(v.data),
                                "created_at": v.time,
                                "context": v.context,
                            }
                        )

    def reset(self) -> None:
        with self._lock:
            self.log.clear()

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        with self._lock:
            unpacker = msgpack.Unpacker(msgpack_stream, raw=False)
            for row_dict in unpacker:
                namespace, field = row_dict["namespace"], row_dict["field"]
                value = decode(row_dict["value"])
                time = row_dict["created_at"]
                context = row_dict["context"]

                if namespace not in self.log:
                    self.log[namespace] = {}
                if field not in self.log[namespace]:
                    self.log[namespace][field] = []

                self.log[namespace][field].append(
                    t.Value(time, value is None, value, context)
                )

                # Special handling for player lists
                if field == "players" and namespace.startswith("session/"):
                    self.log[namespace][field] = self.log[namespace][field][-1:]

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        with self._lock:
            if namespace not in self.log:
                self.log[namespace] = {}
            if field not in self.log[namespace]:
                self.log[namespace][field] = []

            self.log[namespace][field].append(t.Value(self.now, False, data, context))

            # Special handling for player lists
            if field == "players" and namespace.startswith("session/"):
                self.log[namespace][field] = self.log[namespace][field][-1:]

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self._lock:
            if namespace not in self.log or field not in self.log[namespace]:
                raise AttributeError(f"Key not found: ({namespace}, {field})")

            self.log[namespace][field].append(t.Value(self.now, True, None, context))

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        with self._lock:
            for namespace, fields in self.log.items():
                for field, values in fields.items():
                    if namespace.startswith(sstr):
                        for value in values:
                            yield namespace, field, value


class PostgreSQL(DBDriver):
    """Simplified PostgreSQL implementation for write-through operations only."""

    def __init__(
        self,
        conninfo: str = "",
        tblextra: str = "",
        min_size: int = 5,
        max_size: int = 50,
        **kwargs: Any,
    ) -> None:
        import psycopg_pool

        ensure(
            tblextra == "" or tblextra.isidentifier(),
            ValueError,
            "tblextra must be empty or valid identifier",
        )

        self.pool = psycopg_pool.ConnectionPool(
            conninfo,
            open=True,
            min_size=min_size,
            max_size=max_size,
            **kwargs,
        )
        self.tblextra = tblextra

    def test_connection(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT 1")

    def test_tables(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 "
                    f"WHERE EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'uproot{self.tblextra}_values')"
                )

    def size(self) -> Optional[int]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT COALESCE(pg_total_relation_size('uproot{self.tblextra}_values'::regclass), 0)"
                )
                return cur.fetchone()[0]

    def reset(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"DROP TABLE IF EXISTS uproot{self.tblextra}_values CASCADE"
                )
                cur.execute(
                    f"""
                    CREATE TABLE uproot{self.tblextra}_values (
                        id BIGSERIAL PRIMARY KEY,
                        namespace TEXT NOT NULL,
                        field TEXT NOT NULL,
                        value BYTEA,
                        created_at DOUBLE PRECISION NOT NULL,
                        context TEXT NOT NULL
                    )
                    """
                )

    def dump(self) -> Iterator[bytes]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values"
                )
                for namespace, field, value, created_at, context in cur:
                    yield msgpack.packb(
                        {
                            "namespace": namespace,
                            "field": field,
                            "value": value,
                            "created_at": created_at,
                            "context": context,
                        }
                    )

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                unpacker = msgpack.Unpacker(msgpack_stream, raw=False)

                for row_dict in unpacker:
                    namespace = row_dict["namespace"]
                    field = row_dict["field"]

                    # Special handling for player lists - replace existing value, don't create history
                    if field == "players" and namespace.startswith("session/"):
                        # Delete existing entries for this namespace/field first
                        cur.execute(
                            f"DELETE FROM uproot{self.tblextra}_values WHERE namespace = %s AND field = %s",
                            (namespace, field),
                        )

                    cur.execute(
                        f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",
                        (
                            namespace,
                            field,
                            row_dict["value"],
                            row_dict["created_at"],
                            row_dict["context"],
                        ),
                    )

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Special handling for player lists - replace existing value, don't create history
                if field == "players" and namespace.startswith("session/"):
                    # Delete existing entries for this namespace/field first
                    cur.execute(
                        f"DELETE FROM uproot{self.tblextra}_values WHERE namespace = %s AND field = %s",
                        (namespace, field),
                    )

                # Insert the new value (normal append-only for most fields, replacement for players)
                cur.execute(
                    f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",
                    (namespace, field, encode(data), self.now, context),
                )

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",
                    (namespace, field, None, self.now, context),
                )

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values WHERE namespace LIKE %s ORDER BY created_at ASC",
                    (sstr + "%",),
                )
                for namespace, field, value, created_at, context in cur:
                    yield namespace, field, t.Value(
                        created_at,
                        value is None,
                        decode(value) if value is not None else None,
                        context,
                    )


class Sqlite3(DBDriver):
    """Simplified SQLite3 implementation for write-through operations only."""

    def __init__(self, database: str, tblextra: str = "") -> None:
        ensure(
            tblextra == "" or tblextra.isidentifier(),
            ValueError,
            "tblextra must be empty or valid identifier",
        )
        self.database = database
        self.tblextra = tblextra
        self._lock = threading.RLock()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def test_connection(self) -> None:
        conn = self._get_connection()
        conn.execute("SELECT 1")
        conn.close()

    def test_tables(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='uproot{self.tblextra}_values'"
        )
        ensure(cursor.fetchone() is not None, RuntimeError, "Table does not exist")
        conn.close()

    def size(self) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
        )
        result = cursor.fetchone()[0]
        conn.close()
        return result

    def reset(self) -> None:
        conn = self._get_connection()
        conn.execute(f"DROP TABLE IF EXISTS uproot{self.tblextra}_values")
        conn.execute(
            f"""
            CREATE TABLE uproot{self.tblextra}_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                field TEXT NOT NULL,
                value BLOB,
                created_at REAL NOT NULL,
                context TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def dump(self) -> Iterator[bytes]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values"
        )
        for namespace, field, value, created_at, context in cursor:
            yield msgpack.packb(
                {
                    "namespace": namespace,
                    "field": field,
                    "value": value,
                    "created_at": created_at,
                    "context": context,
                }
            )
        conn.close()

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        conn = self._get_connection()
        unpacker = msgpack.Unpacker(msgpack_stream, raw=False)

        for row_dict in unpacker:
            namespace = row_dict["namespace"]
            field = row_dict["field"]

            # Special handling for player lists - replace existing value, don't create history
            if field == "players" and namespace.startswith("session/"):
                # Delete existing entries for this namespace/field first
                conn.execute(
                    f"DELETE FROM uproot{self.tblextra}_values WHERE namespace = ? AND field = ?",
                    (namespace, field),
                )

            conn.execute(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
                (
                    namespace,
                    field,
                    row_dict["value"],
                    row_dict["created_at"],
                    row_dict["context"],
                ),
            )

        conn.commit()
        conn.close()

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        with self._lock:
            conn = self._get_connection()

            # Special handling for player lists - replace existing value, don't create history
            if field == "players" and namespace.startswith("session/"):
                # Delete existing entries for this namespace/field first
                conn.execute(
                    f"DELETE FROM uproot{self.tblextra}_values WHERE namespace = ? AND field = ?",
                    (namespace, field),
                )

            # Insert the new value (normal append-only for most fields, replacement for players)
            conn.execute(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
                (namespace, field, encode(data), self.now, context),
            )

            conn.commit()
            conn.close()

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self._lock:
            conn = self._get_connection()
            conn.execute(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
                (namespace, field, None, self.now, context),
            )
            conn.commit()
            conn.close()

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values WHERE namespace LIKE ? ORDER BY created_at ASC",
            (sstr + "%",),
        )

        for namespace, field, value, created_at, context in cursor:
            yield namespace, field, t.Value(
                created_at,
                value is None,
                decode(value) if value is not None else None,
                context,
            )

        conn.close()
