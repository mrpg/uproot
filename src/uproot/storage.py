# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import copy
import threading
from inspect import currentframe
from time import time
from typing import Any, Callable, Iterator, Optional, Union, cast

from typing_extensions import Literal

from uproot.constraints import ensure
from uproot.deployment import DATABASE
from uproot.stable import IMMUTABLE_TYPES
from uproot.types import (
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    RawValue,
    SessionIdentifier,
    Sessionname,
    Username,
    Value,
    context,
)

VALID_TRAIL0: tuple[str, ...] = ("admin", "session", "player", "group", "model")
DEFAULT_VIRTUAL: dict[str, Callable[["Storage"], Any]] = dict(
    session=lambda p: p._uproot_session(),
    group=lambda p: p._uproot_group(),
    along=lambda p: (lambda field: within.along(p, field)),
    within=lambda p: (lambda **context: within(p, **context)),
)
# Simplified in-memory storage - store entire database history in memory
# Structure: namespace -> field -> list of t.Value objects (complete history)
# Current values are derived from the last non-tombstone entry in history
MEMORY_HISTORY: dict[str, dict[str, list[Value]]] = {}
_memory_lock = threading.RLock()


def _safe_deepcopy(value: Any) -> Any:
    if isinstance(value, IMMUTABLE_TYPES):
        return value

    return copy.deepcopy(value)


def _get_current_value(namespace: str, field: str) -> Any:
    """Get current value from last history entry.
    NOTE: Assumes caller holds _memory_lock.
    """
    if (
        namespace in MEMORY_HISTORY
        and field in MEMORY_HISTORY[namespace]
        and MEMORY_HISTORY[namespace][field]
    ):
        # Check if latest entry is available (not a tombstone)
        latest = MEMORY_HISTORY[namespace][field][-1]
        if not latest.unavailable:
            return _safe_deepcopy(latest.data)

    raise AttributeError(f"Key not found: ({namespace}, {field})")


def _has_current_value(namespace: str, field: str) -> bool:
    """Check if there's a current (non-tombstone) value.
    NOTE: Assumes caller holds _memory_lock.
    """
    if (
        namespace in MEMORY_HISTORY
        and field in MEMORY_HISTORY[namespace]
        and MEMORY_HISTORY[namespace][field]
    ):
        # Check if latest entry is available (not a tombstone)
        latest = MEMORY_HISTORY[namespace][field][-1]
        return not latest.unavailable

    return False


def load_database_into_memory() -> None:
    """Load the entire database history into memory at startup for faster access."""
    global MEMORY_HISTORY

    with _memory_lock:
        MEMORY_HISTORY.clear()

        from uproot.deployment import DATABASE

        # Load complete history using history_all with empty prefix to get everything
        for namespace, field, value in DATABASE.history_all(""):
            if namespace not in MEMORY_HISTORY:
                MEMORY_HISTORY[namespace] = {}

            if field not in MEMORY_HISTORY[namespace]:
                MEMORY_HISTORY[namespace][field] = []

            # Add to history
            MEMORY_HISTORY[namespace][field].append(value)


def db_request(
    caller: Optional["Storage"],
    action: str,
    key: str = "",
    value: Optional[Any] = None,
    *,
    context: Optional[str] = None,
    extra: Optional[
        Union[
            str,
            tuple[list[str], str],
            tuple[str, float],
            dict[str, Any],
        ]
    ] = None,
) -> Any:
    # print(f"!!! db_request({caller}, {repr(action)}, {repr(key)}, ...)")

    ensure(
        key == "" or key.isidentifier(),
        ValueError,
        "Key must be empty or a valid identifier",
    )
    rval = None

    if caller is not None:
        namespace = caller.__path__

    DATABASE.now = time()

    # For writes, use write-through to database
    match action, key, value:
        # WRITE-ONLY - Always write to database immediately
        case "insert", _, _ if isinstance(context, str):
            DATABASE.insert(namespace, key, value, context)
            # Update in-memory data
            with _memory_lock:
                if namespace not in MEMORY_HISTORY:
                    MEMORY_HISTORY[namespace] = {}

                if key not in MEMORY_HISTORY[namespace]:
                    MEMORY_HISTORY[namespace][key] = []

                # Add to history with current timestamp
                new_value = Value(DATABASE.now, False, _safe_deepcopy(value), context)

                # Special handling for player lists - replace entire history like database does
                if key == "players" and namespace.startswith("session/"):
                    MEMORY_HISTORY[namespace][key] = [new_value]
                else:
                    MEMORY_HISTORY[namespace][key].append(new_value)
            rval = value

        case "delete", _, None if isinstance(context, str):
            DATABASE.delete(namespace, key, context)
            # Update in-memory data
            with _memory_lock:
                # Add tombstone to history
                if namespace not in MEMORY_HISTORY:
                    MEMORY_HISTORY[namespace] = {}
                if key not in MEMORY_HISTORY[namespace]:
                    MEMORY_HISTORY[namespace][key] = []

                tombstone = Value(DATABASE.now, True, None, context)
                MEMORY_HISTORY[namespace][key].append(tombstone)

        # READ-ONLY - Use in-memory data exclusively
        case "get", _, None:
            with _memory_lock:
                rval = _get_current_value(namespace, key)

        case "get_field_history", _, None:
            with _memory_lock:
                if namespace in MEMORY_HISTORY and key in MEMORY_HISTORY[namespace]:
                    rval = MEMORY_HISTORY[namespace][key]
                else:
                    rval = []

        case "fields", "", None:
            with _memory_lock:
                if namespace in MEMORY_HISTORY:
                    # Return only fields that have current (non-tombstone) values
                    rval = [
                        field
                        for field in MEMORY_HISTORY[namespace].keys()
                        if _has_current_value(namespace, field)
                    ]
                else:
                    rval = []

        case "has_fields", "", None:
            with _memory_lock:
                if namespace in MEMORY_HISTORY:
                    rval = any(
                        _has_current_value(namespace, field)
                        for field in MEMORY_HISTORY[namespace].keys()
                    )
                else:
                    rval = False

        case "history", "", None:
            with _memory_lock:
                rval = (
                    MEMORY_HISTORY[namespace] if namespace in MEMORY_HISTORY else dict()
                )

        case "get_many", "", None if isinstance(extra, tuple):
            mpaths: list[str]
            mpaths, mkey = cast(tuple[list[str], str], extra)
            with _memory_lock:
                result = {}
                for namespace in mpaths:
                    if _has_current_value(namespace, mkey):
                        # Get the latest non-tombstone value
                        if (
                            namespace in MEMORY_HISTORY
                            and mkey in MEMORY_HISTORY[namespace]
                            and MEMORY_HISTORY[namespace][mkey]
                        ):
                            latest = MEMORY_HISTORY[namespace][mkey][-1]
                            if not latest.unavailable:
                                result[(namespace, mkey)] = latest
                rval = result

        case "get_latest", "", None if isinstance(extra, tuple):
            mpath: str
            since: float
            mpath, since = cast(tuple[str, float], extra)
            with _memory_lock:
                result = {}
                for ns, fields in MEMORY_HISTORY.items():
                    if ns.startswith(mpath):
                        for field, values in fields.items():
                            if values and values[-1].time > since:
                                result[(ns, field)] = values[-1]
                rval = result

        case "history_all", "", None if isinstance(extra, str):
            mpathstart: str
            mpathstart = extra
            with _memory_lock:
                result = []
                for ns, fields in MEMORY_HISTORY.items():
                    if ns.startswith(mpathstart):
                        for field, values in fields.items():
                            for value in values:
                                result.append((ns, field, value))
                rval = iter(result)

        case "history_raw", "", None if isinstance(extra, str):
            mpathstart = extra
            with _memory_lock:
                result = []
                for ns, fields in MEMORY_HISTORY.items():
                    if ns.startswith(mpathstart):
                        for field, values in fields.items():
                            for value in values:
                                # Convert to RawValue
                                from uproot.stable import encode

                                raw_data = (
                                    encode(value.data)
                                    if not value.unavailable
                                    else None
                                )
                                raw_value = RawValue(
                                    value.time,
                                    value.unavailable,
                                    raw_data,
                                    value.context,
                                )
                                result.append((ns, field, raw_value))
                rval = iter(result)

        case "get_within_context", _, None if isinstance(extra, dict):
            context_fields: dict[str, Any]
            context_fields = extra
            with _memory_lock:
                # This is complex - need to implement the context window logic using in-memory data
                if (
                    namespace not in MEMORY_HISTORY
                    or key not in MEMORY_HISTORY[namespace]
                ):
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

                target_values = MEMORY_HISTORY[namespace][key]

                # Iterate from newest to oldest
                for i in range(len(target_values) - 1, -1, -1):
                    target_value = target_values[i]

                    if target_value.unavailable:
                        continue

                    target_time = cast(float, target_value.time)
                    all_contexts_match = True

                    # Check each required context field at target_time
                    for context_field, required_value in context_fields.items():
                        if (
                            namespace not in MEMORY_HISTORY
                            or context_field not in MEMORY_HISTORY[namespace]
                        ):
                            all_contexts_match = False
                            break

                        context_values = MEMORY_HISTORY[namespace][context_field]

                        # Find the latest context value at or before target_time
                        context_state = None
                        for cv in reversed(context_values):
                            if cast(float, cv.time) <= target_time:
                                context_state = cv
                                break

                        if (
                            context_state is None
                            or context_state.unavailable
                            or context_state.data != required_value
                        ):
                            all_contexts_match = False
                            break

                    if all_contexts_match:
                        # Verify this is still the latest within the context window
                        still_valid = True
                        earliest_context_change = None

                        # Find when any context field changed after target_time
                        for context_field, required_value in context_fields.items():
                            if (
                                namespace in MEMORY_HISTORY
                                and context_field in MEMORY_HISTORY[namespace]
                            ):
                                context_values = MEMORY_HISTORY[namespace][
                                    context_field
                                ]

                                for cv in context_values:
                                    if cast(float, cv.time) > target_time:
                                        if cv.unavailable or cv.data != required_value:
                                            if (
                                                earliest_context_change is None
                                                or cv.time < earliest_context_change
                                            ):
                                                earliest_context_change = cv.time
                                            break

                        # Check if there's a later target value before context change
                        if earliest_context_change is not None:
                            for tv in target_values:
                                if (
                                    target_time
                                    < cast(float, tv.time)
                                    < earliest_context_change
                                ):
                                    still_valid = False
                                    break

                        if still_valid:
                            rval = target_value.data
                            break
                else:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

        # ERROR
        case _, _, _:
            raise NotImplementedError

    return rval


def mkpath(*trail: str) -> str:
    return "/".join(trail)


def field_from_paths(paths: list[str], field: str) -> dict[tuple[str, str], Value]:
    return cast(
        dict[tuple[str, str], Value],
        db_request(
            None,
            "get_many",
            extra=(paths, field),
        ),
    )


def all_good(key: tuple[str, str]) -> bool:
    return True


def fields_from_session(
    sname: Sessionname, since_epoch: float = 0
) -> dict[tuple[str, str], Value]:
    return cast(
        dict[tuple[str, str], Value],
        db_request(
            None,
            "get_latest",
            extra=(f"player/{sname}/", since_epoch),
        ),
    )


def history_all(mpathstart: str) -> Iterator[tuple[str, str, Value]]:
    return cast(
        Iterator[tuple[str, str, Value]],
        db_request(
            None,
            "history_all",
            extra=mpathstart,
        ),
    )


def history_raw(mpathstart: str) -> Iterator[tuple[str, str, RawValue]]:
    return cast(
        Iterator[tuple[str, str, RawValue]],
        db_request(
            None,
            "history_raw",
            extra=mpathstart,
        ),
    )


class within:
    __slots__ = (
        "__storage__",
        "__context_fields__",
    )

    def __init__(self, storage: "Storage", **context: Any) -> None:
        self.__storage__ = storage
        self.__context_fields__ = context

    def __getattr__(self, name: str) -> Any:
        try:
            return db_request(
                self.__storage__,
                "get_within_context",
                name,
                extra=self.__context_fields__,
            )
        except AttributeError:
            return None

    @classmethod
    def along(cls, storage: "Storage", field: str) -> Iterator[tuple[Any, "within"]]:
        for value in cast(list[Value], db_request(storage, "get_field_history", field)):
            if value.data is not None:
                yield value.data, within(storage, **{field: value.data})


class Storage:
    __slots__ = (
        "__accessed_fields__",
        "__allow_mutable__",
        "__field_cache__",
        "__explicitly_set__",
        "__assigned_values__",
        "name",
        "__path__",
        "__trail__",
        "__virtual__",
        "__weakref__",
    )

    def __init__(
        self,
        *trail: str,
        virtual: Optional[dict[str, Callable[["Storage"], Any]]] = None,
    ):
        ensure(
            all(t.isidentifier() for t in trail),
            ValueError,
            f"{repr(trail)} has invalid identifiers",
        )
        ensure(trail[0] in VALID_TRAIL0, ValueError, "Invalid trail start")

        object.__setattr__(self, "name", trail[-1])
        object.__setattr__(self, "__path__", mkpath(*trail))
        object.__setattr__(self, "__trail__", trail)
        object.__setattr__(self, "__allow_mutable__", False)
        object.__setattr__(self, "__accessed_fields__", dict())
        object.__setattr__(self, "__field_cache__", dict())
        object.__setattr__(self, "__explicitly_set__", set())
        object.__setattr__(self, "__assigned_values__", dict())
        object.__setattr__(self, "__virtual__", virtual or DEFAULT_VIRTUAL)

    def __invert__(self) -> Identifier:
        match self.__trail__[0]:
            case "session":
                return SessionIdentifier(*self.__trail__[1:])
            case "player":
                return PlayerIdentifier(*self.__trail__[1:])
            case "group":
                return GroupIdentifier(*self.__trail__[1:])
            case "model":
                return ModelIdentifier(*self.__trail__[1:])
            case _:
                raise NotImplementedError

    def __hash__(self) -> int:
        return hash(self.__trail__)

    def __setattr__(self, name: str, value: Any) -> None:
        ensure(
            name.isidentifier(), ValueError, "Attribute name must be a valid identifier"
        )

        if name == "name" or (name.startswith("__") and name.endswith("__")):
            ensure(
                name in self.__slots__,
                AttributeError,
                f"Attribute '{name}' not in __slots__",
            )
            return object.__setattr__(self, name, value)

        virtual = object.__getattribute__(self, "__virtual__")

        if name in virtual:
            raise AttributeError(f"Cannot assign to virtual field '{name}'")

        newval = db_request(
            self,
            "insert",
            name,
            value,
            context=context(currentframe()),
        )

        # Update caches and track explicit assignment
        self.__field_cache__[name] = newval
        # Don't set baseline in __accessed_fields__ if we're in a context manager
        # The baseline will be set at context exit to capture any in-place changes
        if not self.__allow_mutable__:
            self.__accessed_fields__[name] = _safe_deepcopy(newval)
        self.__explicitly_set__.add(name)
        # Track the originally assigned value to detect post-assignment modifications
        self.__assigned_values__[name] = _safe_deepcopy(newval)

    def __guarded_return__(self, value: Any) -> Any:
        if isinstance(value, IMMUTABLE_TYPES) or self.__allow_mutable__:
            return value
        else:
            raise ValueError(
                f"This {repr(self)} must be wrapped in a context manager (use 'with')."
            )

    def __getattribute__(self, name: str) -> Any:
        if name in ("name", "flush", "get") or (
            name.startswith("__") and name.endswith("__")
        ):
            return object.__getattribute__(self, name)

        accessed_fields = object.__getattribute__(self, "__accessed_fields__")
        field_cache = object.__getattribute__(self, "__field_cache__")
        virtual = object.__getattribute__(self, "__virtual__")

        if name in virtual:
            return virtual[name](self)

        # Check if we have a cached copy of this field
        if name in field_cache:
            return self.__guarded_return__(field_cache[name])

        try:
            value = db_request(self, "get", name)
            # Cache the value for consistent object identity
            field_cache[name] = value
            # For deep modification detection, store a copy of the original only on first access
            if name not in accessed_fields:
                accessed_fields[name] = _safe_deepcopy(value)
            return self.__guarded_return__(value)
        except NameError as e:
            raise AttributeError(f"{self} has no .{name}") from e

    def __delattr__(self, name: str) -> None:
        db_request(self, "delete", name, None, context=context(currentframe()))
        self.__field_cache__.pop(name, None)
        self.__accessed_fields__.pop(name, None)
        self.__explicitly_set__.discard(name)
        self.__assigned_values__.pop(name, None)

    def __enter__(self) -> "Storage":
        self.__allow_mutable__ = True
        # Clear caches to ensure fresh values and baselines for this context
        self.__field_cache__.clear()
        self.__accessed_fields__.clear()
        self.__explicitly_set__.clear()
        self.__assigned_values__.clear()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:  # type: ignore[no-untyped-def]
        if exc_type is None:
            self.flush()
            self.__allow_mutable__ = False
        # Clear field cache when exiting context to ensure fresh values next time
        self.__field_cache__.clear()

        return False

    def flush(self) -> None:
        try:
            accessed_fields = object.__getattribute__(self, "__accessed_fields__")
            field_cache = object.__getattribute__(self, "__field_cache__")
            explicitly_set = object.__getattribute__(self, "__explicitly_set__")
            assigned_values = object.__getattribute__(self, "__assigned_values__")
        except AttributeError:
            return  # Object wasn't fully initialized

        # Check all fields in the cache (includes both accessed and explicitly set fields)
        all_fields = set(accessed_fields.keys()) | set(field_cache.keys())

        for field in all_fields:
            if field in field_cache:
                current_value = field_cache[field]
                original_value = accessed_fields.get(field)

                # For explicitly set fields, we need special handling
                if field in explicitly_set:
                    assigned_value = assigned_values.get(field)
                    # Only save if current value differs from the originally assigned value
                    if current_value != assigned_value:
                        # Save the modified value (post-assignment modification detected)
                        db_request(
                            self,
                            "insert",
                            field,
                            current_value,
                            context=context(currentframe()),
                        )
                    # Update baseline for explicitly set field
                    accessed_fields[field] = _safe_deepcopy(current_value)
                    continue

                # For accessed-only fields, compare against original baseline
                if original_value is not None and current_value != original_value:
                    # Save the modified value for fields that were only accessed, not explicitly set
                    db_request(
                        self,
                        "insert",
                        field,
                        current_value,
                        context=context(currentframe()),
                    )
                    # Update our accessed_fields to the new baseline
                    accessed_fields[field] = _safe_deepcopy(current_value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Storage):
            return False

        return cast(bool, self.__path__ == other.__path__)

    def __fields__(self) -> list[str]:
        return cast(list[str], db_request(self, "fields"))

    def __bool__(self) -> bool:
        return cast(bool, db_request(self, "has_fields"))

    def __history__(self) -> dict[str, list[Value]]:
        return cast(list[tuple[str, Value]], db_request(self, "history"))

    def __repr__(self) -> str:
        if len(self.__trail__) == 1:
            return f"{self.__trail__[0].capitalize()}()"
        return f"{self.__trail__[0].capitalize()}(*{repr(self.__trail__[1:])})"

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return getattr(self, name)
        except AttributeError:
            return default


def Admin() -> Storage:
    return Storage("admin")


def Session(sname: Sessionname) -> Storage:
    return Storage("session", sname)


def Group(sname: Sessionname, gname: str) -> Storage:
    return Storage("group", sname, gname)


def Player(sname: Sessionname, uname: Username) -> Storage:
    return Storage("player", sname, uname)


def Model(sname: Sessionname, mname: str) -> Storage:
    return Storage("model", sname, mname)
