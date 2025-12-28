# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file exposes an internal API that end users MUST NOT rely upon. Rely upon storage.py instead.

Note: SQL queries in this file use f-strings for table names (self.tblextra) which are
controlled class attributes, not user input. All user-provided data uses parameterized
queries (%s or ?) to prevent SQL injection. The f-strings are safe in this context.
"""

import sqlite3
import threading
import time
from abc import ABC
from contextlib import contextmanager
from typing import Any, Iterator, Optional, cast

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

    def history_all(self) -> Iterator[tuple[str, str, t.Value]]:
        """Return complete history for all fields in all namespaces.
        Used for loading data into memory at startup.
        """
        raise NotImplementedError

    def close(self) -> None:
        """Close database connections and clean up resources. Default implementation does nothing."""
        pass

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
        raise Exception  # To trigger ensure() -> False

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

    def history_all(self) -> Iterator[tuple[str, str, t.Value]]:
        with self._lock:
            for namespace, fields in self.log.items():
                for field, values in fields.items():
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
            tblextra == "" or tblextra.isidentifier(),  # KEEP AS IS
            ValueError,
            "tblextra must be empty or valid Python identifier",
        )

        self.pool = psycopg_pool.ConnectionPool(
            conninfo,
            open=True,
            min_size=min_size,
            max_size=max_size,
            **kwargs,
        )
        self.tblextra = tblextra
        self._batch_inserts: list[tuple[Any, ...]] = []
        self._last_batch_time = time.time()
        self._batch_size = 100
        self._batch_timeout = 0.1
        self._lock = threading.RLock()

    def _process_batch(self, conn: Any, cur: Any) -> None:
        """Process accumulated batch inserts."""
        if not self._batch_inserts:
            return

        try:
            cur.executemany(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",  # nosec B608
                self._batch_inserts,
            )
            self._batch_inserts.clear()
            self._last_batch_time = time.time()
        except Exception:
            self._batch_inserts.clear()
            raise

    def _should_flush_batch(self) -> bool:
        """Check if batch should be flushed."""
        return (
            len(self._batch_inserts) >= self._batch_size
            or time.time() - self._last_batch_time >= self._batch_timeout
        )

    def close(self) -> None:
        """Close the connection pool and wait for all worker threads to stop."""
        with self._lock:
            # Flush any pending operations before closing
            if self._batch_inserts and hasattr(self, "pool") and self.pool:
                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        self._process_batch(conn, cur)

        if hasattr(self, "pool") and self.pool:
            self.pool.close(timeout=5.0)

    def test_connection(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT 1")

    def test_tables(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 "
                    f"WHERE EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'uproot{self.tblextra}_values')"  # nosec B608
                )
                result = cur.fetchone()
                ensure(result and result[0] == 1, RuntimeError, "Table does not exist")

    def size(self) -> Optional[int]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT COALESCE(pg_total_relation_size('uproot{self.tblextra}_values'::regclass), 0)"  # nosec B608
                )
                result = cur.fetchone()
                return cast(int, result[0]) if result else None

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
                # Create unique index for efficient upserts on players field in session namespaces
                cur.execute(
                    f"CREATE UNIQUE INDEX uproot{self.tblextra}_players_idx ON uproot{self.tblextra}_values (namespace, field) WHERE field = 'players' AND namespace LIKE 'session/%'"
                )

    def dump(self) -> Iterator[bytes]:
        with self._lock:
            # Flush pending operations before dump
            if self._batch_inserts:
                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        self._process_batch(conn, cur)

        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values"  # nosec B608
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
        with self._lock:
            # Flush any pending operations first
            if self._batch_inserts:
                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        self._process_batch(conn, cur)

        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                unpacker = msgpack.Unpacker(msgpack_stream, raw=False)

                # Use batched inserts for restore as well
                batch = []
                upsert_batch = []

                for row_dict in unpacker:
                    namespace = row_dict["namespace"]
                    field = row_dict["field"]

                    # Special handling for player lists - replace existing value, don't create history
                    if field == "players" and namespace.startswith("session/"):
                        upsert_batch.append(
                            (
                                row_dict["value"],
                                row_dict["created_at"],
                                row_dict["context"],
                                namespace,
                                field,
                                namespace,
                                field,
                                row_dict["value"],
                                row_dict["created_at"],
                                row_dict["context"],
                            )
                        )
                    else:
                        batch.append(
                            (
                                namespace,
                                field,
                                row_dict["value"],
                                row_dict["created_at"],
                                row_dict["context"],
                            )
                        )

                # Execute batched operations
                if upsert_batch:
                    # Handle upserts for players field
                    for values in upsert_batch:
                        cur.execute(
                            f"UPDATE uproot{self.tblextra}_values SET value = %s, created_at = %s, context = %s WHERE namespace = %s AND field = %s",  # nosec B608
                            values[:5],
                        )
                        if cur.rowcount == 0:
                            cur.execute(
                                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",  # nosec B608
                                values[5:],
                            )

                if batch:
                    cur.executemany(
                        f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",  # nosec B608
                        batch,
                    )

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        with self._lock:
            # Special handling for player lists - these need immediate processing
            if field == "players" and namespace.startswith("session/"):
                # Flush any pending batches first
                if self._batch_inserts:
                    with self.pool.connection() as conn:
                        with conn.transaction(), conn.cursor() as cur:
                            self._process_batch(conn, cur)

                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        cur.execute(
                            f"UPDATE uproot{self.tblextra}_values SET value = %s, created_at = %s, context = %s WHERE namespace = %s AND field = %s",  # nosec B608
                            (encode(data), self.now, context, namespace, field),
                        )
                        if cur.rowcount == 0:
                            cur.execute(
                                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",  # nosec B608
                                (namespace, field, encode(data), self.now, context),
                            )
            else:
                # Normal append-only operations - batch these
                self._batch_inserts.append(
                    (namespace, field, encode(data), self.now, context)
                )

                # Process batch if it's time to flush
                if self._should_flush_batch():
                    with self.pool.connection() as conn:
                        with conn.transaction(), conn.cursor() as cur:
                            self._process_batch(conn, cur)

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self._lock:
            # Delete operations are batched too
            self._batch_inserts.append((namespace, field, None, self.now, context))

            # Process batch if it's time to flush
            if self._should_flush_batch():
                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        self._process_batch(conn, cur)

    def history_all(self) -> Iterator[tuple[str, str, t.Value]]:
        with self._lock:
            # Flush pending operations before reading history
            if self._batch_inserts:
                with self.pool.connection() as conn:
                    with conn.transaction(), conn.cursor() as cur:
                        self._process_batch(conn, cur)

        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values ORDER BY created_at ASC",  # nosec B608
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
            tblextra == "" or tblextra.isidentifier(),  # KEEP AS IS
            ValueError,
            "tblextra must be empty or valid Python identifier",
        )
        self.database = database
        self.tblextra = tblextra
        self._lock = threading.RLock()
        self._connection: Optional[sqlite3.Connection] = None
        self._batch_inserts: list[tuple[Any, ...]] = []
        self._last_batch_time = time.time()
        self._batch_size = 100
        self._batch_timeout = 0.1

    def _get_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            self._connection = sqlite3.connect(self.database, check_same_thread=False)
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=NORMAL")
            self._connection.execute("PRAGMA cache_size=-64000")  # 64MB cache
            self._connection.execute("PRAGMA temp_store=MEMORY")
            self._connection.execute("PRAGMA mmap_size=268435456")  # 256MB mmap
        return self._connection

    @contextmanager
    def _batch_context(self) -> Iterator[Any]:
        """Context manager for batched operations."""
        conn = self._get_connection()
        try:
            yield conn
            self._process_batch(conn)
        except Exception:
            conn.rollback()
            raise

    def _process_batch(self, conn: sqlite3.Connection) -> None:
        """Process accumulated batch inserts."""
        if not self._batch_inserts:
            return

        try:
            conn.executemany(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",  # nosec B608
                self._batch_inserts,
            )
            conn.commit()
            self._batch_inserts.clear()
            self._last_batch_time = time.time()
        except Exception:
            self._batch_inserts.clear()
            raise

    def _should_flush_batch(self) -> bool:
        """Check if batch should be flushed."""
        return (
            len(self._batch_inserts) >= self._batch_size
            or time.time() - self._last_batch_time >= self._batch_timeout
        )

    def close(self) -> None:
        """Close database connection and flush any pending batches."""
        with self._lock:
            if self._connection:
                if self._batch_inserts:
                    self._process_batch(self._connection)
                self._connection.close()
                self._connection = None

    def test_connection(self) -> None:
        conn = self._get_connection()
        conn.execute("SELECT 1")

    def test_tables(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='uproot{self.tblextra}_values'"  # nosec B608
        )
        ensure(cursor.fetchone() is not None, RuntimeError, "Table does not exist")

    def size(self) -> Optional[int]:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()"
        )
        row = cursor.fetchone()
        result = cast(int, row[0]) if row else None
        return result

    def reset(self) -> None:
        with self._lock:
            # Flush any pending operations first
            if self._batch_inserts:
                self._process_batch(self._get_connection())

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
            # Create unique index for efficient upserts on players field in session namespaces
            conn.execute(
                f"CREATE UNIQUE INDEX uproot{self.tblextra}_players_idx ON uproot{self.tblextra}_values (namespace, field) WHERE field = 'players' AND namespace LIKE 'session/%'"
            )
            conn.commit()

    def dump(self) -> Iterator[bytes]:
        with self._lock:
            # Flush pending operations before dump
            if self._batch_inserts:
                self._process_batch(self._get_connection())

            conn = self._get_connection()
            cursor = conn.execute(
                f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values"  # nosec B608
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

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        with self._lock:
            # Flush any pending operations first
            if self._batch_inserts:
                self._process_batch(self._get_connection())

            conn = self._get_connection()
            unpacker = msgpack.Unpacker(msgpack_stream, raw=False)

            # Use batched inserts for restore as well
            batch = []
            upsert_batch = []

            for row_dict in unpacker:
                namespace = row_dict["namespace"]
                field = row_dict["field"]

                # Special handling for player lists - replace existing value, don't create history
                if field == "players" and namespace.startswith("session/"):
                    upsert_batch.append(
                        (
                            row_dict["value"],
                            row_dict["created_at"],
                            row_dict["context"],
                            namespace,
                            field,
                            namespace,
                            field,
                            row_dict["value"],
                            row_dict["created_at"],
                            row_dict["context"],
                        )
                    )
                else:
                    batch.append(
                        (
                            namespace,
                            field,
                            row_dict["value"],
                            row_dict["created_at"],
                            row_dict["context"],
                        )
                    )

            # Execute batched operations
            if upsert_batch:
                # Handle upserts for players field
                for values in upsert_batch:
                    cursor = conn.execute(
                        f"UPDATE uproot{self.tblextra}_values SET value = ?, created_at = ?, context = ? WHERE namespace = ? AND field = ?",  # nosec B608
                        values[:5],
                    )
                    if cursor.rowcount == 0:
                        conn.execute(
                            f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",  # nosec B608
                            values[5:],
                        )

            if batch:
                conn.executemany(
                    f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",  # nosec B608
                    batch,
                )

            conn.commit()

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        with self._lock:
            # Special handling for player lists - these need immediate processing
            if field == "players" and namespace.startswith("session/"):
                # Flush any pending batches first
                if self._batch_inserts:
                    self._process_batch(self._get_connection())

                conn = self._get_connection()
                cursor = conn.execute(
                    f"UPDATE uproot{self.tblextra}_values SET value = ?, created_at = ?, context = ? WHERE namespace = ? AND field = ?",  # nosec B608
                    (encode(data), self.now, context, namespace, field),
                )
                if cursor.rowcount == 0:
                    conn.execute(
                        f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",  # nosec B608
                        (namespace, field, encode(data), self.now, context),
                    )
                conn.commit()
            else:
                # Normal append-only operations - batch these
                self._batch_inserts.append(
                    (namespace, field, encode(data), self.now, context)
                )

                # Process batch if it's time to flush
                if self._should_flush_batch():
                    self._process_batch(self._get_connection())

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self._lock:
            # Delete operations are batched too
            self._batch_inserts.append((namespace, field, None, self.now, context))

            # Process batch if it's time to flush
            if self._should_flush_batch():
                self._process_batch(self._get_connection())

    def history_all(self) -> Iterator[tuple[str, str, t.Value]]:
        with self._lock:
            # Flush pending operations before reading history
            if self._batch_inserts:
                self._process_batch(self._get_connection())

            conn = self._get_connection()
            cursor = conn.execute(
                f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values ORDER BY created_at ASC",  # nosec B608
            )

            for namespace, field, value, created_at, context in cursor:
                yield namespace, field, t.Value(
                    created_at,
                    value is None,
                    decode(value) if value is not None else None,
                    context,
                )
