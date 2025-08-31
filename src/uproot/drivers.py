# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file exposes an internal API that end users MUST NOT rely upon. Rely upon storage.py instead.
"""

import sqlite3
import threading
from abc import ABC
from typing import Any, Iterator, Optional, cast

import msgpack

import uproot.types as t
from uproot.stable import decode, encode


class DBDriver(ABC):
    """
    Abstract base class for database drivers providing append-only log functionality.

    CONTRACT:

    1. THREAD SAFETY: All implementations MUST be thread-safe for use as global
       singletons in async web applications. Multiple threads may access the same
       instance concurrently.

    2. SYNCHRONOUS OPERATIONS: All methods MUST be synchronous (no async/await).
       This allows the driver to be used in both sync and async contexts.

    3. APPEND-ONLY SEMANTICS: The database represents an append-only log where:
       - insert() adds new entries with timestamps
       - delete() adds tombstone entries (does not physically delete)
       - History is preserved and ordered by time ASC
       There is one exception: it is ALLOWED to store only the current value of
       dbfields that begin with "session/" and end with ":players".

    4. VALUE SEMANTICS: Data is returned as Any or a t.Value object containing:
       - time: timestamp (float)
       - unavailable: boolean flag for tombstones
       - data: the actual payload (Any type, encoded)
       - context: string context/metadata

    5. KEY STRUCTURE: Keys consist of two components:
       - namespace: hierarchical prefix (can contain colons, e.g., "session/123")
       - field: the specific field name (no colons allowed)
       The old-style "namespace:field" dbfield format is split into separate columns
       for efficient querying and indexing.

    6. CURRENT STATE: get() and get_many() check the most recent entry for each key.
       If the latest entry is a tombstone (unavailable==True), the key is treated as
       unavailable and get() raises AttributeError while get_many() omits it.

    7. ENCODING: Data MUST be encoded/decoded using the provided functions.

    8. ERROR HANDLING: Missing keys should raise AttributeError (not KeyError).
       Connection issues should raise RuntimeError.

    9. TIMESTAMP HANDLING: The 'now' class variable provides the current timestamp
       for all operations. This allows for consistent timestamping across operations.

    10. DUMP/RESTORE: Must support msgpack-based serialization for backup/migration.
        The format is standardized across all implementations.
    """

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

    def get(self, namespace: str, field: str) -> Any:
        """Get current (non-unavailable) value. Raises AttributeError if missing."""
        raise NotImplementedError

    def get_field_all_namespaces(self, field: str) -> dict[tuple[str, str], t.Value]:
        """Get latest values for a specific field across all namespaces. Returns dict with (namespace, field) tuples as keys."""
        raise NotImplementedError

    def get_many(
        self, namespaces: list[str], field: str
    ) -> dict[tuple[str, str], t.Value]:
        """Get current values for single field across multiple namespaces. Missing keys are omitted."""
        raise NotImplementedError

    def get_field_history(self, namespace: str, field: str) -> list[t.Value]:
        """Return complete history for a single field in a namespace. t.Values MUST be ordered by time ASC."""
        raise NotImplementedError

    def get_latest(
        self, sstr: str, since_epoch: float = 0
    ) -> dict[tuple[str, str], t.Value]:
        """Get all keys starting with sstr updated after since_epoch. Returns dict with (namespace, field) tuples as keys."""
        raise NotImplementedError

    def get_within_context(
        self, namespace: str, context_fields: dict[str, Any], target_field: str
    ) -> Any:
        """
        Get the latest value of target_field within the time window where ALL context fields match their specified values.

        The time window is defined as:
        - Start: when ALL context_fields were set to their specified values (the latest such time)
        - End: when ANY context_field was changed to a different value (or current time if still active)

        Args:
            namespace: The namespace to query (e.g., "abc")
            context_fields: Dict mapping field names to values that define the context window
                           (e.g., {"round": 1, "phase": "attack"})
            target_field: The field to retrieve within that window (e.g., "guess")

        Returns:
            The decoded data of the latest value of target_field within the context window

        Raises:
            AttributeError: If the context combination was never active, or if target_field has no value within the window
        """
        raise NotImplementedError

    def delete(self, namespace: str, field: str, context: str) -> None:
        """Mark entry as unavailable (tombstone). Does not physically remove."""
        raise NotImplementedError

    def fields(self, sstr: str) -> list[str]:
        """Return field names (last part after colon) matching prefix."""
        raise NotImplementedError

    def has_fields(self, sstr: str) -> bool:
        """Check if any fields exist with given prefix."""
        raise NotImplementedError

    def history(self, sstr: str) -> Iterator[tuple[str, t.Value]]:
        """Return complete history for fields. t.Values MUST be ordered by time ASC."""
        raise NotImplementedError

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        """Return complete history for all fields in all namespaces starting with sstr.
        Yields tuples of (namespace, field, t.Value), with values ordered by time ASC as in history().
        """
        raise NotImplementedError

    def history_raw(self, sstr: str) -> Iterator[tuple[str, str, t.RawValue]]:
        """Return complete history for all fields in all namespaces starting with sstr.
        Yields tuples of (namespace, field, t.RawValue), with values ordered by time ASC as in history().
        Does not decode the raw binary value received from the database.
        """
        raise NotImplementedError

    def ensure(self) -> None:
        try:
            self.test_connection()
        except Exception as exc:
            raise RuntimeError(
                "Cannot connect to database.",
            ) from exc

        try:
            self.test_tables()
        except Exception:
            self.reset()


class Memory(DBDriver):
    """High-performance in-memory implementation with optimized data structures."""

    def __init__(self) -> None:
        # Nested structure: namespace -> field -> list of values
        self.log: dict[str, dict[str, list[t.Value]]] = {}
        self._lock = threading.RLock()
        self._cache_version = 0

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
            self._cache_version += 1

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

            self._cache_version += 1

    def delete(self, namespace: str, field: str, context: str) -> None:
        with self._lock:
            if namespace not in self.log or field not in self.log[namespace]:
                raise AttributeError(f"Key not found: {namespace}:{field}")

            self.log[namespace][field].append(t.Value(self.now, True, None, context))

    def get(self, namespace: str, field: str) -> Any:
        with self._lock:
            if namespace not in self.log or field not in self.log[namespace]:
                raise AttributeError(f"Key not found: {namespace}:{field}")

            latest = self.log[namespace][field][-1]
            if latest.unavailable:
                raise AttributeError(f"Key not found: {namespace}:{field}")

            return latest.data

    def get_field_all_namespaces(self, field: str) -> dict[tuple[str, str], t.Value]:
        rval = {}
        with self._lock:
            for namespace, fields in self.log.items():
                if field in fields:
                    values = fields[field]
                    if values:
                        latest = values[-1]
                        if not latest.unavailable:
                            rval[(namespace, field)] = latest
        return rval

    def get_field_history(self, namespace: str, field: str) -> list[t.Value]:
        with self._lock:
            if namespace not in self.log or field not in self.log[namespace]:
                return []
            return list(self.log[namespace][field])

    def get_latest(
        self, sstr: str, since_epoch: float = 0
    ) -> dict[tuple[str, str], t.Value]:
        rval: dict[tuple[str, str], t.Value] = {}
        with self._lock:
            for namespace, fields in self.log.items():
                for field, values in fields.items():
                    # Check if namespace starts with sstr (no more dbfield strings!)
                    if namespace.startswith(sstr) and values:
                        # Get the latest value
                        latest = values[-1]

                        # Check if it was updated after since_epoch
                        if latest.time is not None and latest.time > since_epoch:
                            # Include both available and unavailable (tombstone) entries
                            # This matches the SQL implementations
                            rval[(namespace, field)] = latest

        return rval

    def get_many(
        self, namespaces: list[str], field: str
    ) -> dict[tuple[str, str], t.Value]:
        rval = {}
        with self._lock:
            for namespace in namespaces:
                if namespace in self.log and field in self.log[namespace]:
                    values = self.log[namespace][field]
                    if values:
                        latest = values[-1]
                        if not latest.unavailable:
                            rval[namespace, field] = latest
        return rval

    def get_within_context(
        self, namespace: str, context_fields: dict[str, Any], target_field: str
    ) -> Any:
        with self._lock:
            # Check if namespace and target field exist
            if namespace not in self.log or target_field not in self.log[namespace]:
                raise AttributeError(
                    f"No value found for {target_field} within the specified context in namespace {namespace}"
                )

            # Get all target field values (already ordered by time)
            target_values = self.log[namespace][target_field]

            # Iterate from newest to oldest
            for i in range(len(target_values) - 1, -1, -1):
                target_value = target_values[i]

                # Skip tombstones
                if target_value.unavailable:
                    continue

                target_time = cast(float, target_value.time)
                all_contexts_match = True

                # Check each required context field at target_time
                for context_field, required_value in context_fields.items():
                    if (
                        namespace not in self.log
                        or context_field not in self.log[namespace]
                    ):
                        all_contexts_match = False
                        break

                    context_values = self.log[namespace][context_field]

                    # Find the latest context value at or before target_time
                    context_state = None
                    for cv in reversed(context_values):
                        if cast(float, cv.time) <= target_time:
                            context_state = cv
                            break

                    # No context value exists at this time
                    if context_state is None:
                        all_contexts_match = False
                        break

                    # Context is tombstoned
                    if context_state.unavailable:
                        all_contexts_match = False
                        break

                    # Check if context value matches
                    if context_state.data != required_value:
                        all_contexts_match = False
                        break

                if all_contexts_match:
                    # Verify this target value is still the latest within the context window
                    still_valid = True

                    # Find when any context field changed after target_time
                    earliest_context_change = None

                    for context_field, required_value in context_fields.items():
                        if (
                            namespace in self.log
                            and context_field in self.log[namespace]
                        ):
                            context_values = self.log[namespace][context_field]

                            # Find the next change after target_time
                            for cv in context_values:
                                if cast(float, cv.time) > target_time:
                                    # Check if the value actually changed
                                    if cv.unavailable or cv.data != required_value:
                                        if (
                                            earliest_context_change is None
                                            or cv.time < earliest_context_change  # type: ignore[unreachable]
                                        ):
                                            earliest_context_change = cv.time
                                        break

                    # If context changed, check if there's a later target value before the change
                    if earliest_context_change is not None:
                        # Check if any target value exists between target_time and earliest_context_change
                        for tv in target_values:
                            if (
                                target_time
                                < cast(float, tv.time)
                                < earliest_context_change
                            ):
                                still_valid = False
                                break

                    if still_valid:
                        return target_value.data

            # No valid value found
            raise AttributeError(
                f"No value found for {target_field} within the specified context in namespace {namespace}"
            )

    def fields(self, sstr: str) -> list[str]:
        with self._lock:
            fields_set = set()
            for namespace, fields in self.log.items():
                for field in fields:
                    if namespace.startswith(sstr):
                        fields_set.add(field)

            return list(fields_set)

    def has_fields(self, sstr: str) -> bool:
        with self._lock:
            for namespace, fields in self.log.items():
                for field in fields:
                    if namespace.startswith(sstr):
                        return True
            return False

    def history(self, sstr: str) -> Iterator[tuple[str, t.Value]]:
        for namespace, fields in self.log.items():
            for field, values in fields.items():
                if namespace.startswith(sstr):
                    for value in values:
                        yield field, value

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        for namespace, fields in self.log.items():
            for field, values in fields.items():
                if namespace.startswith(sstr):
                    for value in values:
                        yield namespace, field, value

    def history_raw(self, sstr: str) -> Iterator[tuple[str, str, t.RawValue]]:
        for namespace, fields in self.log.items():
            for field, values in fields.items():
                if namespace.startswith(sstr):
                    for value in values:
                        yield namespace, field, t.RawValue(
                            time=value.time,
                            unavailable=value.unavailable,
                            data=(
                                encode(value.data) if not value.unavailable else None
                            ),
                            context=value.context,
                        )


class PostgreSQL(DBDriver):
    """High-performance PostgreSQL implementation with prepared statements."""

    def __init__(
        self,
        conninfo: str = "",
        tblextra: str = "",
        min_size: int = 5,
        max_size: int = 50,
        **kwargs: Any,
    ) -> None:
        import psycopg_pool

        assert tblextra == "" or tblextra.isidentifier()

        self.pool = psycopg_pool.ConnectionPool(
            conninfo,
            open=True,
            min_size=min_size,
            max_size=max_size,
            **kwargs,
        )
        self.tblextra = tblextra
        self._prepare_statements()

    def _prepare_statements(self) -> None:
        """Prepare frequently used SQL statements for better performance."""
        self._queries = {
            "insert": f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, %s, %s, %s)",
            "delete": f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (%s, %s, NULL, %s, %s)",
            "get": f"SELECT current_value FROM uproot{self.tblextra}_keys WHERE namespace = %s AND field = %s",
            "get_latest": f"SELECT namespace, field, current_value, last_updated_at, context FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE %s || '%%' AND last_updated_at > %s",
            "get_many": f"SELECT namespace, field, current_value, last_updated_at, context FROM uproot{self.tblextra}_keys WHERE namespace LIKE %s || '%%' AND field = %s",
            "fields": f"SELECT DISTINCT field FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE %s || '%%'",
            "has_fields": f"SELECT EXISTS(SELECT 1 FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE %s || '%%')",
            "history": f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values WHERE namespace || ':' || field LIKE %s || '%%' ORDER BY created_at ASC",
            "dump": f"SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values",
        }

    def test_connection(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute("SELECT 1")
                ((value,),) = cur
                assert value == 1

    def test_tables(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 "
                    f"WHERE EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'uproot{self.tblextra}_values') "
                    f"AND EXISTS(SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = 'uproot{self.tblextra}_keys')"
                )
                ((value,),) = cur
                assert value == 1

    def size(self) -> Optional[int]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"""SELECT COALESCE(
                    pg_total_relation_size('uproot{self.tblextra}_values'::regclass) +
                    pg_total_relation_size('uproot{self.tblextra}_keys'::regclass), 0
                    )"""
                )
                return cur.fetchone()[0]

    def dump(self) -> Iterator[bytes]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["dump"])
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

                rows = []
                for row_dict in unpacker:
                    namespace, field = row_dict["namespace"], row_dict["field"]
                    rows.append(
                        (
                            namespace,
                            field,
                            row_dict["value"],
                            row_dict["created_at"],
                            row_dict["context"],
                        )
                    )

                    if len(rows) >= 1000:
                        cur.executemany(self._queries["insert"], rows)
                        rows = []

                if rows:
                    cur.executemany(self._queries["insert"], rows)

    def reset(self) -> None:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"""
                DROP TABLE IF EXISTS uproot{self.tblextra}_values;
                DROP TABLE IF EXISTS uproot{self.tblextra}_keys;

                CREATE TABLE uproot{self.tblextra}_keys (
                    namespace VARCHAR(255),
                    field VARCHAR(255),
                    current_value BYTEA,
                    last_updated_at FLOAT NOT NULL,
                    context VARCHAR(255) NOT NULL,
                    PRIMARY KEY (namespace, field)
                );

                CREATE TABLE uproot{self.tblextra}_values (
                    namespace VARCHAR(255),
                    field VARCHAR(255),
                    value BYTEA,
                    created_at FLOAT NOT NULL,
                    context VARCHAR(255) NOT NULL,
                    FOREIGN KEY (namespace, field) REFERENCES uproot{self.tblextra}_keys(namespace, field) DEFERRABLE INITIALLY DEFERRED
                );

                -- Indexes for efficient queries
                CREATE INDEX idx_uproot{self.tblextra}_values_ns_field ON uproot{self.tblextra}_values(namespace, field);
                CREATE INDEX idx_uproot{self.tblextra}_values_created_at ON uproot{self.tblextra}_values(created_at);
                CREATE INDEX idx_uproot{self.tblextra}_keys_namespace ON uproot{self.tblextra}_keys(namespace);
                CREATE INDEX idx_uproot{self.tblextra}_keys_composite ON uproot{self.tblextra}_keys((namespace || ':' || field) text_pattern_ops);

                CREATE OR REPLACE FUNCTION update_uproot{self.tblextra}_keys() RETURNS TRIGGER AS $$
                BEGIN
                    INSERT INTO uproot{self.tblextra}_keys (namespace, field, current_value, last_updated_at, context)
                    VALUES (NEW.namespace, NEW.field, NEW.value, NEW.created_at, NEW.context)
                    ON CONFLICT (namespace, field) DO UPDATE
                    SET current_value = NEW.value,
                    last_updated_at = NEW.created_at,
                    context = NEW.context;

                    IF NEW.field = 'players' AND NEW.namespace LIKE 'session/%' THEN
                        DELETE FROM uproot{self.tblextra}_values
                        WHERE namespace = NEW.namespace AND field = NEW.field AND created_at < NEW.created_at;
                    END IF;

                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                CREATE TRIGGER maintain_uproot{self.tblextra}_keys
                AFTER INSERT ON uproot{self.tblextra}_values
                FOR EACH ROW EXECUTE FUNCTION update_uproot{self.tblextra}_keys();"""
                )

    def get_field_all_namespaces(self, field: str) -> dict[tuple[str, str], t.Value]:
        rval = {}
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT namespace, field, current_value, last_updated_at, context "
                    f"FROM uproot{self.tblextra}_keys "
                    f"WHERE field = %s AND current_value IS NOT NULL",
                    (field,),
                )

                for namespace, field, value, time, context in cur:
                    rval[(namespace, field)] = t.Value(
                        time, False, decode(value), context
                    )

        return rval

    def get_field_history(self, namespace: str, field: str) -> list[t.Value]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(
                    f"SELECT value, created_at, context FROM uproot{self.tblextra}_values "
                    f"WHERE namespace = %s AND field = %s "
                    f"ORDER BY created_at ASC",
                    (namespace, field),
                )

                return [
                    t.Value(
                        created_at,
                        value is None,
                        decode(value) if value is not None else None,
                        context,
                    )
                    for value, created_at, context in cur
                ]

    def get_latest(
        self, sstr: str, since_epoch: float = 0
    ) -> dict[tuple[str, str], t.Value]:
        rval = {}
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["get_latest"], (sstr, since_epoch))

                for namespace, field, value, time, context in cur:
                    if value is not None:
                        rval[(namespace, field)] = t.Value(
                            time, False, decode(value), context
                        )
                    else:
                        rval[(namespace, field)] = t.Value(time, True, None, context)

        return rval

    def get_many(
        self, namespaces: list[str], field: str
    ) -> dict[tuple[str, str], t.Value]:
        if not namespaces:
            return {}

        rval = {}
        namespaceprefix = t.longest_common_prefix(namespaces)

        namespaces = set(namespaces)

        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["get_many"], (namespaceprefix, field))

                for namespace, field, value, time, context in cur:
                    if namespace in namespaces and value is not None:
                        rval[namespace, field] = t.Value(
                            time, False, decode(value), context
                        )

        return rval

    def get_within_context(
        self, namespace: str, context_fields: dict[str, Any], target_field: str
    ) -> Any:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Get all target field values ordered by time DESC
                cur.execute(
                    f"SELECT value, created_at FROM uproot{self.tblextra}_values "
                    f"WHERE namespace = %s AND field = %s "
                    f"ORDER BY created_at DESC",
                    (namespace, target_field),
                )

                target_values = cur.fetchall()

                for target_value, target_time in target_values:
                    # Skip tombstones
                    if target_value is None:
                        continue

                    all_contexts_match = True

                    # Check each required context field at target_time
                    for context_field, required_value in context_fields.items():
                        cur.execute(
                            f"SELECT value FROM uproot{self.tblextra}_values "
                            f"WHERE namespace = %s AND field = %s AND created_at <= %s "
                            f"ORDER BY created_at DESC LIMIT 1",
                            (namespace, context_field, target_time),
                        )

                        context_row = cur.fetchone()

                        # No context value exists at this time
                        if not context_row:
                            all_contexts_match = False
                            break

                        # Context is tombstoned
                        if context_row[0] is None:
                            all_contexts_match = False
                            break

                        # Check if context value matches
                        if decode(context_row[0]) != required_value:
                            all_contexts_match = False
                            break

                    if all_contexts_match:
                        # Verify this target value is still the latest within the context window
                        still_valid = True

                        # Find when any context field changed after target_time
                        earliest_context_change = None

                        for context_field, required_value in context_fields.items():
                            cur.execute(
                                f"SELECT value, created_at FROM uproot{self.tblextra}_values "
                                f"WHERE namespace = %s AND field = %s AND created_at > %s "
                                f"ORDER BY created_at ASC LIMIT 1",
                                (namespace, context_field, target_time),
                            )

                            next_change = cur.fetchone()

                            if next_change:
                                next_value, next_time = next_change
                                # Check if the value actually changed
                                if (
                                    next_value is None
                                    or decode(next_value) != required_value
                                ):
                                    if (
                                        earliest_context_change is None
                                        or next_time < earliest_context_change  # type: ignore[unreachable]
                                    ):
                                        earliest_context_change = next_time

                        # If context changed, check if there's a later target value before the change
                        if earliest_context_change is not None:
                            cur.execute(
                                f"SELECT 1 FROM uproot{self.tblextra}_values "
                                f"WHERE namespace = %s AND field = %s "
                                f"AND created_at > %s AND created_at < %s "
                                f"LIMIT 1",
                                (
                                    namespace,
                                    target_field,
                                    target_time,
                                    earliest_context_change,
                                ),
                            )

                            if cur.fetchone():
                                still_valid = False

                        if still_valid:
                            return decode(target_value)

                # No valid value found
                raise AttributeError(
                    f"No value found for {target_field} within the specified context in namespace {namespace}"
                )

    def fields(self, sstr: str) -> list[str]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["fields"], (sstr,))
                return [field for (field,) in cur]

    def has_fields(self, sstr: str) -> bool:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["has_fields"], (sstr,))
                return bool(cur.fetchone()[0])

    def history(self, sstr: str) -> Iterator[tuple[str, t.Value]]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(self._queries["history"], (sstr,))

                for namespace, field, value, created_at, context in cur:
                    yield (
                        field,
                        t.Value(
                            created_at,
                            value is None,
                            decode(value) if value is not None else None,
                            context,
                        ),
                    )

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Use LIKE with proper escaping
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context "
                    f"FROM uproot{self.tblextra}_values "
                    f"WHERE namespace || ':' || field LIKE %s "
                    f"ORDER BY created_at ASC",
                    (sstr + "%",),
                )

                for namespace, field, value, created_at, context in cur:
                    yield (
                        namespace,
                        field,
                        t.Value(
                            created_at,
                            value is None,
                            decode(value) if value is not None else None,
                            context,
                        ),
                    )

    def history_raw(self, sstr: str) -> Iterator[tuple[str, str, t.RawValue]]:
        with self.pool.connection() as conn:
            with conn.transaction(), conn.cursor() as cur:
                # Use LIKE with proper escaping
                cur.execute(
                    f"SELECT namespace, field, value, created_at, context "
                    f"FROM uproot{self.tblextra}_values "
                    f"WHERE namespace || ':' || field LIKE %s "
                    f"ORDER BY created_at ASC",
                    (sstr + "%",),
                )

                for namespace, field, value, created_at, context in cur:
                    yield (
                        namespace,
                        field,
                        t.RawValue(
                            created_at,
                            value is None,
                            value,
                            context,
                        ),
                    )


class Sqlite3(DBDriver):
    """Thread-safe SQLite implementation optimized for async web applications."""

    def __init__(
        self, db_path: str = "uproot.sqlite3", tblextra: str = "", **kwargs: Any
    ) -> None:
        assert tblextra == "" or tblextra.isidentifier()

        if "isolation_level" not in kwargs:
            kwargs["isolation_level"] = "IMMEDIATE"

        kwargs["check_same_thread"] = False

        self.db_path = db_path
        self.conn_kwargs = kwargs
        self.tblextra = tblextra
        self._local = threading.local()
        self._lock = threading.RLock()

        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA cache_size = -64000")
            conn.execute("PRAGMA temp_store = MEMORY")
            conn.execute("PRAGMA mmap_size = 268435456")

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection for thread safety."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path, **self.conn_kwargs)

            self._local.connection.execute("PRAGMA journal_mode = WAL")
            self._local.connection.execute("PRAGMA synchronous = NORMAL")
            self._local.connection.execute("PRAGMA cache_size = -64000")
            self._local.connection.execute("PRAGMA temp_store = MEMORY")

        return cast(sqlite3.Connection, self._local.connection)

    def test_connection(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute("SELECT 1")
        ((value,),) = cursor
        assert value == 1

    def test_tables(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT 1 "
            f"WHERE EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'uproot{self.tblextra}_values') "
            f"AND EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'uproot{self.tblextra}_keys')"
        )
        ((value,),) = cursor
        assert value == 1

    def size(self) -> Optional[int]:
        conn = self._get_connection()

        page_size = conn.execute("PRAGMA page_size").fetchone()[0]
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]

        return page_size * page_count

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

    def restore(self, msgpack_stream: Iterator[bytes]) -> None:
        conn = self._get_connection()
        unpacker = msgpack.Unpacker(msgpack_stream, raw=False)

        rows = []
        for row_dict in unpacker:
            namespace, field = row_dict["namespace"], row_dict["field"]
            rows.append(
                (
                    namespace,
                    field,
                    row_dict["value"],
                    row_dict["created_at"],
                    row_dict["context"],
                )
            )

            if len(rows) >= 1000:
                conn.executemany(
                    f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
                    rows,
                )
                rows = []

        if rows:
            conn.executemany(
                f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
                rows,
            )

        conn.commit()

    def reset(self) -> None:
        with self._lock:
            conn = self._get_connection()
            conn.executescript(
                f"""
            DROP TABLE IF EXISTS uproot{self.tblextra}_values;
            DROP TABLE IF EXISTS uproot{self.tblextra}_keys;

            CREATE TABLE uproot{self.tblextra}_keys (
                namespace VARCHAR(255),
                field VARCHAR(255),
                current_value BLOB,
                last_updated_at FLOAT NOT NULL,
                context VARCHAR(255) NOT NULL,
                PRIMARY KEY (namespace, field)
            );

            CREATE TABLE uproot{self.tblextra}_values (
                namespace VARCHAR(255),
                field VARCHAR(255),
                value BLOB,
                created_at FLOAT NOT NULL,
                context VARCHAR(255) NOT NULL,
                FOREIGN KEY (namespace, field) REFERENCES uproot{self.tblextra}_keys(namespace, field) DEFERRABLE INITIALLY DEFERRED
            );

            -- Indexes for efficient queries
            CREATE INDEX idx_uproot{self.tblextra}_values_ns_field ON uproot{self.tblextra}_values(namespace, field);
            CREATE INDEX idx_uproot{self.tblextra}_values_created_at ON uproot{self.tblextra}_values(created_at);
            CREATE INDEX idx_uproot{self.tblextra}_keys_namespace ON uproot{self.tblextra}_keys(namespace);

            CREATE TRIGGER maintain_uproot{self.tblextra}_keys
            AFTER INSERT ON uproot{self.tblextra}_values
            FOR EACH ROW
            WHEN NEW.field = 'players' AND NEW.namespace LIKE 'session/%'
            BEGIN
                -- Update keys table
                INSERT INTO uproot{self.tblextra}_keys (namespace, field, current_value, last_updated_at, context)
                VALUES (NEW.namespace, NEW.field, NEW.value, NEW.created_at, NEW.context)
                ON CONFLICT (namespace, field) DO UPDATE
                SET current_value = NEW.value,
                    last_updated_at = NEW.created_at,
                    context = NEW.context;

                -- Only delete for this specific case
                DELETE FROM uproot{self.tblextra}_values
                WHERE namespace = NEW.namespace
                AND field = NEW.field
                AND created_at < NEW.created_at;
            END;

            -- Separate trigger for other cases (no DELETE)
            CREATE TRIGGER maintain_uproot{self.tblextra}_keys_general
            AFTER INSERT ON uproot{self.tblextra}_values
            FOR EACH ROW
            WHEN NOT (NEW.field = 'players' AND NEW.namespace LIKE 'session/%')
            BEGIN
                INSERT INTO uproot{self.tblextra}_keys (namespace, field, current_value, last_updated_at, context)
                VALUES (NEW.namespace, NEW.field, NEW.value, NEW.created_at, NEW.context)
                ON CONFLICT (namespace, field) DO UPDATE
                SET current_value = NEW.value,
                    last_updated_at = NEW.created_at,
                    context = NEW.context;
            END;"""
            )

    def insert(self, namespace: str, field: str, data: Any, context: str) -> None:
        conn = self._get_connection()
        conn.execute(
            f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, ?, ?, ?)",
            (namespace, field, encode(data), self.now, context),
        )
        conn.commit()

    def delete(self, namespace: str, field: str, context: str) -> None:
        conn = self._get_connection()
        conn.execute(
            f"INSERT INTO uproot{self.tblextra}_values (namespace, field, value, created_at, context) VALUES (?, ?, NULL, ?, ?)",
            (namespace, field, self.now, context),
        )
        conn.commit()

    def get(self, namespace: str, field: str) -> Any:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT current_value FROM uproot{self.tblextra}_keys WHERE namespace = ? AND field = ?",
            (namespace, field),
        )

        row = cursor.fetchone()
        if row and row[0] is not None:
            return decode(row[0])

        raise AttributeError(f"Key not found: {namespace}:{field}")

    def get_field_all_namespaces(self, field: str) -> dict[tuple[str, str], t.Value]:
        rval = {}
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, current_value, last_updated_at, context "
            f"FROM uproot{self.tblextra}_keys "
            f"WHERE field = ? AND current_value IS NOT NULL",
            (field,),
        )

        for namespace, field, value, time, context in cursor:
            rval[(namespace, field)] = t.Value(time, False, decode(value), context)

        return rval

    def get_field_history(self, namespace: str, field: str) -> list[t.Value]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT value, created_at, context FROM uproot{self.tblextra}_values "
            f"WHERE namespace = ? AND field = ? "
            f"ORDER BY created_at ASC",
            (namespace, field),
        )

        return [
            t.Value(
                created_at,
                value is None,
                decode(value) if value is not None else None,
                context,
            )
            for value, created_at, context in cursor
        ]

    def get_latest(
        self, sstr: str, since_epoch: float = 0
    ) -> dict[tuple[str, str], t.Value]:
        rval = {}
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, current_value, last_updated_at, context FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE ? || '%' AND last_updated_at > ?",
            (sstr, since_epoch),
        )

        for namespace, field, value, time, context in cursor:
            if value is not None:
                rval[(namespace, field)] = t.Value(time, False, decode(value), context)
            else:
                rval[(namespace, field)] = t.Value(time, True, None, context)

        return rval

    def get_many(
        self, namespaces: list[str], field: str
    ) -> dict[tuple[str, str], t.Value]:
        if not namespaces:
            return {}

        rval = {}
        conn = self._get_connection()

        cursor = conn.execute(
            f"SELECT namespace, field, current_value, last_updated_at, context FROM uproot{self.tblextra}_keys WHERE namespace LIKE ? || '%' AND field = ?",
            (t.longest_common_prefix(namespaces), field),
        )

        namespaces = set(namespaces)

        for namespace, field, value, time, context in cursor:
            if namespace in namespaces and value is not None:
                rval[namespace, field] = t.Value(time, False, decode(value), context)

        return rval

    def get_within_context(
        self, namespace: str, context_fields: dict[str, Any], target_field: str
    ) -> Any:
        conn = self._get_connection()

        # Get all target field values ordered by time DESC
        cursor = conn.execute(
            f"SELECT value, created_at FROM uproot{self.tblextra}_values "
            f"WHERE namespace = ? AND field = ? "
            f"ORDER BY created_at DESC",
            (namespace, target_field),
        )

        target_values = cursor.fetchall()

        for target_value, target_time in target_values:
            # Skip tombstones
            if target_value is None:
                continue

            all_contexts_match = True

            # Check each required context field at target_time
            for context_field, required_value in context_fields.items():
                cursor = conn.execute(
                    f"SELECT value FROM uproot{self.tblextra}_values "
                    f"WHERE namespace = ? AND field = ? AND created_at <= ? "
                    f"ORDER BY created_at DESC LIMIT 1",
                    (namespace, context_field, target_time),
                )

                context_row = cursor.fetchone()

                # No context value exists at this time
                if not context_row:
                    all_contexts_match = False
                    break

                # Context is tombstoned
                if context_row[0] is None:
                    all_contexts_match = False
                    break

                # Check if context value matches
                if decode(context_row[0]) != required_value:
                    all_contexts_match = False
                    break

            if all_contexts_match:
                # Verify this target value is still the latest within the context window
                still_valid = True

                # Find when any context field changed after target_time
                earliest_context_change = None

                for context_field, required_value in context_fields.items():
                    cursor = conn.execute(
                        f"SELECT value, created_at FROM uproot{self.tblextra}_values "
                        f"WHERE namespace = ? AND field = ? AND created_at > ? "
                        f"ORDER BY created_at ASC LIMIT 1",
                        (namespace, context_field, target_time),
                    )

                    next_change = cursor.fetchone()

                    if next_change:
                        next_value, next_time = next_change
                        # Check if the value actually changed
                        if next_value is None or decode(next_value) != required_value:
                            if (
                                earliest_context_change is None
                                or next_time < earliest_context_change  # type: ignore[unreachable]
                            ):
                                earliest_context_change = next_time

                # If context changed, check if there's a later target value before the change
                if earliest_context_change is not None:
                    cursor = conn.execute(
                        f"SELECT 1 FROM uproot{self.tblextra}_values "
                        f"WHERE namespace = ? AND field = ? "
                        f"AND created_at > ? AND created_at < ? "
                        f"LIMIT 1",
                        (namespace, target_field, target_time, earliest_context_change),
                    )

                    if cursor.fetchone():
                        still_valid = False

                if still_valid:
                    return decode(target_value)

        # No valid value found
        raise AttributeError(
            f"No value found for {target_field} within the specified context in namespace {namespace}"
        )

    def fields(self, sstr: str) -> list[str]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT DISTINCT field FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE ? || '%'",
            (sstr,),
        )
        return [field for (field,) in cursor]

    def has_fields(self, sstr: str) -> bool:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT EXISTS(SELECT 1 FROM uproot{self.tblextra}_keys WHERE namespace || ':' || field LIKE ? || '%')",
            (sstr,),
        )
        return bool(cursor.fetchone()[0])

    def history(self, sstr: str) -> Iterator[tuple[str, t.Value]]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"""SELECT namespace, field, value, created_at, context FROM uproot{self.tblextra}_values
            WHERE namespace || ':' || field LIKE ? || '%' ORDER BY created_at ASC""",
            (sstr,),
        )

        for namespace, field, value, created_at, context in cursor:
            yield (
                field,
                t.Value(
                    created_at,
                    value is None,
                    decode(value) if value is not None else None,
                    context,
                ),
            )

    def history_all(self, sstr: str) -> Iterator[tuple[str, str, t.Value]]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, value, created_at, context "
            f"FROM uproot{self.tblextra}_values "
            f"WHERE namespace || ':' || field LIKE ? "
            f"ORDER BY created_at ASC",
            (sstr + "%",),
        )

        for namespace, field, value, created_at, context in cursor:
            yield (
                namespace,
                field,
                t.Value(
                    created_at,
                    value is None,
                    decode(value) if value is not None else None,
                    context,
                ),
            )

    def history_raw(self, sstr: str) -> Iterator[tuple[str, str, t.RawValue]]:
        conn = self._get_connection()
        cursor = conn.execute(
            f"SELECT namespace, field, value, created_at, context "
            f"FROM uproot{self.tblextra}_values "
            f"WHERE namespace || ':' || field LIKE ? "
            f"ORDER BY created_at ASC",
            (sstr + "%",),
        )

        for namespace, field, value, created_at, context in cursor:
            yield (
                namespace,
                field,
                t.RawValue(
                    created_at,
                    value is None,
                    value,
                    context,
                ),
            )
