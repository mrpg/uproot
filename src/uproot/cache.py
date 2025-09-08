import copy
import threading
from time import time
from typing import Any, Optional, Union, cast

from uproot.constraints import ensure
from uproot.deployment import DATABASE
from uproot.stable import IMMUTABLE_TYPES
from uproot.types import RawValue, Value

MEMORY_HISTORY: dict[tuple[str, ...], dict[str, list[Value]]] = {}
LOCK = threading.RLock()


def safe_deepcopy(value: Any) -> Any:
    if isinstance(value, IMMUTABLE_TYPES):
        return value

    return copy.deepcopy(value)


def tuple2dbns(ns: tuple[str, ...]) -> str:
    return "/".join(ns)


def dbns2tuple(dbns: str) -> tuple[str]:
    return tuple(str.split("/"))


def load_database_into_memory() -> None:
    """Load the entire database history into memory at startup for faster access."""
    global MEMORY_HISTORY

    with LOCK:
        MEMORY_HISTORY.clear()

        # Load complete history using history_all with empty prefix to get everything
        for dbns, field, value in DATABASE.history_all(""):
            namespace = dbns2tuple(dbns)

            if namespace not in MEMORY_HISTORY:
                MEMORY_HISTORY[namespace] = {}

            if field not in MEMORY_HISTORY[namespace]:
                MEMORY_HISTORY[namespace][field] = []

            # Add to history
            MEMORY_HISTORY[namespace][field].append(value)


def get_current_value(namespace: str, field: str) -> Any:
    """Get current value from last history entry.
    NOTE: Assumes caller holds LOCK.
    """
    if (
        namespace in MEMORY_HISTORY
        and field in MEMORY_HISTORY[namespace]
        and MEMORY_HISTORY[namespace][field]
    ):
        # Check if latest entry is available (not a tombstone)
        latest = MEMORY_HISTORY[namespace][field][-1]
        if not latest.unavailable:
            return safe_deepcopy(latest.data)

    raise AttributeError(f"Key not found: ({namespace}, {field})")


def has_current_value(namespace: str, field: str) -> bool:
    """Check if there's a current (non-tombstone) value.
    NOTE: Assumes caller holds LOCK.
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
        namespace = caller.__namespace__

    DATABASE.now = time()

    # For writes, use write-through to database
    match action, key, value:
        # WRITE-ONLY - Always write to database immediately
        case "insert", _, _ if isinstance(context, str):
            DATABASE.insert(tuple2dbns(namespace), key, value, context)
            # Update in-memory data
            with LOCK:
                if namespace not in MEMORY_HISTORY:
                    MEMORY_HISTORY[namespace] = {}

                if key not in MEMORY_HISTORY[namespace]:
                    MEMORY_HISTORY[namespace][key] = []

                # Add to history with current timestamp
                new_value = Value(DATABASE.now, False, safe_deepcopy(value), context)

                # Special handling for player lists - replace entire history like database does
                if key == "players" and namespace[0] == "session":
                    MEMORY_HISTORY[namespace][key] = [new_value]
                else:
                    MEMORY_HISTORY[namespace][key].append(new_value)
            rval = value

        case "delete", _, None if isinstance(context, str):
            DATABASE.delete(tuple2dbns(namespace), key, context)
            # Update in-memory data
            with LOCK:
                # Add tombstone to history
                if namespace not in MEMORY_HISTORY:
                    MEMORY_HISTORY[namespace] = {}
                if key not in MEMORY_HISTORY[namespace]:
                    MEMORY_HISTORY[namespace][key] = []

                tombstone = Value(DATABASE.now, True, None, context)
                MEMORY_HISTORY[namespace][key].append(tombstone)

        # READ-ONLY - Use in-memory data exclusively
        case "get", _, None:
            with LOCK:
                rval = get_current_value(namespace, key)

        case "get_field_history", _, None:
            with LOCK:
                if namespace in MEMORY_HISTORY and key in MEMORY_HISTORY[namespace]:
                    rval = MEMORY_HISTORY[namespace][key]
                else:
                    rval = []

        case "fields", "", None:
            with LOCK:
                if namespace in MEMORY_HISTORY:
                    # Return only fields that have current (non-tombstone) values
                    rval = [
                        field
                        for field in MEMORY_HISTORY[namespace].keys()
                        if has_current_value(namespace, field)
                    ]
                else:
                    rval = []

        case "has_fields", "", None:
            with LOCK:
                if namespace in MEMORY_HISTORY:
                    rval = any(
                        has_current_value(namespace, field)
                        for field in MEMORY_HISTORY[namespace].keys()
                    )
                else:
                    rval = False

        case "history", "", None:
            with LOCK:
                rval = (
                    MEMORY_HISTORY[namespace] if namespace in MEMORY_HISTORY else dict()
                )

        case "get_many", "", None if isinstance(extra, tuple):
            mpaths: list[str]
            mpaths, mkey = cast(tuple[list[str], str], extra)
            with LOCK:
                result = {}
                for namespace in mpaths:
                    if has_current_value(namespace, mkey):
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
            with LOCK:
                result = {}
                for ns, fields in MEMORY_HISTORY.items():
                    dbns = tuple2dbns(ns)  # TODO: This is a monkeypatch => remove
                    if dbns.startswith(mpath):
                        for field, values in fields.items():
                            if values and values[-1].time > since:
                                result[(ns, field)] = values[-1]
                rval = result

        case "history_all", "", None if isinstance(extra, str):
            mpathstart: str
            mpathstart = extra
            with LOCK:
                result = []
                for ns, fields in MEMORY_HISTORY.items():
                    dbns = tuple2dbns(ns)  # TODO: This is a monkeypatch => remove
                    if dbns.startswith(mpathstart):
                        for field, values in fields.items():
                            for value in values:
                                result.append((ns, field, value))
                rval = iter(result)

        case "history_raw", "", None if isinstance(extra, str):
            mpathstart = extra
            with LOCK:
                result = []
                for ns, fields in MEMORY_HISTORY.items():
                    dbns = tuple2dbns(ns)  # TODO: This is a monkeypatch => remove
                    if dbns.startswith(mpathstart):
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
            with LOCK:
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
