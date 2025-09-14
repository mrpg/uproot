# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file exposes an internal API that end users MUST NOT rely upon. Rely upon storage.py instead.
"""

import copy
import threading
from time import time
from typing import TYPE_CHECKING, Any, Optional, Sequence, Union, cast

from sortedcontainers import SortedList

from uproot.constraints import ensure
from uproot.deployment import DATABASE
from uproot.stable import IMMUTABLE_TYPES
from uproot.types import Value

if TYPE_CHECKING:
    from uproot.storage import Storage

MEMORY_HISTORY: dict[str, Any] = {}
LOCK = threading.RLock()


def safe_deepcopy(value: Any) -> Any:
    if isinstance(value, IMMUTABLE_TYPES):
        return value

    return copy.deepcopy(value)


def tuple2dbns(ns: tuple[str, ...]) -> str:
    return "/".join(ns)


def dbns2tuple(dbns: str) -> tuple[str, ...]:
    return tuple(dbns.split("/"))


def flatten(
    d: dict[str, Any], trail: tuple[str, ...] = ()
) -> dict[tuple[str, ...], Any]:
    result = {}

    for k, v in d.items():
        new_trail = trail + (k,)

        if hasattr(v, "__iter__") and not isinstance(v, (dict, str)):
            result[new_trail] = v
        elif isinstance(v, dict):
            result.update(flatten(v, new_trail))
        else:
            result[new_trail] = v

    return result


def get_namespace(
    namespace: tuple[str, ...],
    create: bool = False,
) -> Optional[dict[str, Any]]:
    """Navigate to namespace location. If create=True, creates missing levels."""
    current: Any = MEMORY_HISTORY

    for part in namespace:
        if not isinstance(current, dict):
            return None

        if create and part not in current:
            current[part] = {}
        elif part not in current:
            return None

        current = current[part]

    return cast(Optional[dict[str, Any]], current)


def field_history_since(
    namespace: tuple[str, ...],
    field: str,
    since: float,
) -> list[Value]:
    with LOCK:
        current = get_namespace(namespace)
        if not current or not isinstance(current, dict) or field not in current:
            return []

        values = current[field]
        if hasattr(values, "__iter__") and hasattr(values, "bisect_right"):
            # Use binary search to find first entry after 'since'
            search_val = Value(since, True, None, "")
            start_idx = values.bisect_right(search_val)
            return list(values[start_idx:])
        else:
            # Fallback for non-SortedList (shouldn't happen with current implementation)
            return [v for v in values if cast(float, v.time) > since]


def load_database_into_memory() -> None:
    """Load the entire database history into memory at startup for faster access."""
    global MEMORY_HISTORY

    with LOCK:
        MEMORY_HISTORY.clear()

        # Load complete history using history_all with empty prefix to get everything
        for dbns, field, value in DATABASE.history_all():
            namespace = dbns2tuple(dbns)

            # Get or create the nested dictionary for this namespace
            nested_dict = get_namespace(namespace, create=True)

            if nested_dict is not None and field not in nested_dict:
                nested_dict[field] = SortedList(key=lambda v: v.time)

            # Add to history
            if nested_dict is not None:
                nested_dict[field].add(value)


def get_current_value(namespace: tuple[str, ...], field: str) -> Any:
    """Get current value from last history entry.
    NOTE: Assumes caller holds LOCK.
    """
    current = get_namespace(namespace)
    if (
        current
        and isinstance(current, dict)
        and field in current
        and hasattr(current[field], "__iter__")
        and current[field]
    ):
        # Check if latest entry is available (not a tombstone)
        latest = current[field][-1]
        if not latest.unavailable:
            return safe_deepcopy(latest.data)

    raise AttributeError(f"Key not found: ({namespace}, {field})")


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
            tuple[Sequence[tuple[str, ...]], str],
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
                # Get or create the nested dictionary for this namespace
                nested_dict = get_namespace(namespace, create=True)

                if nested_dict is not None and key not in nested_dict:
                    nested_dict[key] = SortedList(key=lambda v: v.time)

                # Add to history with current timestamp
                new_value = Value(DATABASE.now, False, safe_deepcopy(value), context)

                # Special handling for player lists - replace entire history like database does
                if nested_dict is not None:
                    if key == "players" and namespace[0] == "session":
                        nested_dict[key] = SortedList([new_value], key=lambda v: v.time)
                    else:
                        nested_dict[key].add(new_value)
            rval = value

        case "delete", _, None if isinstance(context, str):
            DATABASE.delete(tuple2dbns(namespace), key, context)
            # Update in-memory data
            with LOCK:
                # Add tombstone to history
                nested_dict = get_namespace(namespace, create=True)
                if nested_dict is not None and key not in nested_dict:
                    nested_dict[key] = SortedList(key=lambda v: v.time)

                tombstone = Value(DATABASE.now, True, None, context)
                if nested_dict is not None:
                    nested_dict[key].add(tombstone)

        # READ-ONLY - Use in-memory data exclusively
        case "get", _, None:
            with LOCK:
                rval = get_current_value(namespace, key)

        case "get_field_history", _, None:
            with LOCK:
                current = get_namespace(namespace)
                if current and isinstance(current, dict) and key in current:
                    rval = current[key]
                else:
                    rval = SortedList(key=lambda v: v.time)

        case "fields", "", None:
            with LOCK:
                current = get_namespace(namespace)
                if current and isinstance(current, dict):
                    # Return only fields that have current (non-tombstone) values
                    rval = []
                    for field in current.keys():
                        if (
                            hasattr(current[field], "__iter__")
                            and current[field]
                            and not current[field][-1].unavailable
                        ):
                            rval.append(field)
                else:
                    rval = SortedList(key=lambda v: v.time)

        case "has_fields", "", None:
            with LOCK:
                current = get_namespace(namespace)
                if current and isinstance(current, dict):
                    # Check if any field has current (non-tombstone) values
                    rval = any(
                        hasattr(values, "__iter__")
                        and values
                        and not values[-1].unavailable
                        for values in current.values()
                    )
                else:
                    rval = False

        case "history", "", None:
            with LOCK:
                current = get_namespace(namespace)
                rval = current if current and isinstance(current, dict) else {}

        case "get_many", "", None if isinstance(extra, tuple):
            mnamespaces: Sequence[tuple[str, ...]]
            mnamespaces, mkey = cast(tuple[Sequence[tuple[str, ...]], str], extra)
            with LOCK:
                result = {}
                for namespace in mnamespaces:
                    current = get_namespace(namespace)
                    if (
                        current
                        and isinstance(current, dict)
                        and mkey in current
                        and hasattr(current[mkey], "__iter__")
                        and current[mkey]
                    ):
                        latest = current[mkey][-1]
                        if not latest.unavailable:
                            result[(namespace, mkey)] = latest
                rval = result

        case "fields_from_session", "", None if isinstance(extra, tuple):
            sname: str
            since: float
            sname, since = cast(tuple[str, float], extra)
            with LOCK:
                session_result: dict[tuple[tuple[str, str, str], str], Any] = {}
                session_players = get_namespace(("player", sname))
                if session_players and isinstance(session_players, dict):
                    for player_name, player_fields in session_players.items():
                        if isinstance(player_fields, dict):
                            ns = ("player", sname, player_name)
                            for field_name, values in player_fields.items():
                                field = cast(str, field_name)
                                if values and hasattr(values, "__iter__") and values:
                                    latest = values[-1]
                                    if latest.time > since:
                                        session_result[(ns, field)] = latest
                rval = session_result

        case "get_within_context", _, None if isinstance(extra, dict):
            ctx = extra
            with LOCK:
                ns_ = get_namespace(namespace)
                if not ns_ or not isinstance(ns_, dict) or key not in ns_:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

                tvals = ns_[key]

                # Verify all context fields exist
                for cf in ctx:
                    if cf not in ns_:
                        raise AttributeError(
                            f"No value found for {key} within the specified context in namespace {namespace}"
                        )

                # Find latest valid target in matching context window
                for i in range(len(tvals) - 1, -1, -1):
                    tv = tvals[i]
                    if tv.unavailable:
                        continue

                    tt = cast(float, tv.time)

                    # Check context at target time and find context window end
                    ctx_valid = True
                    ctx_end = None

                    for cf, rv in ctx.items():
                        ctx_vals = ns_[cf]

                        # Binary search for context state at tt (latest value <= tt)
                        # Create a dummy Value object for binary search
                        search_val = Value(tt, True, None, "")
                        idx = ctx_vals.bisect_right(search_val) - 1
                        if idx < 0:
                            ctx_valid = False
                            break

                        ctx_state = ctx_vals[idx]
                        if ctx_state.unavailable or ctx_state.data != rv:
                            ctx_valid = False
                            break

                        # Find when this context changes after tt
                        next_idx = ctx_vals.bisect_right(search_val)
                        for k in range(next_idx, len(ctx_vals)):
                            cv = ctx_vals[k]
                            if cv.unavailable or cv.data != rv:
                                if ctx_end is None or cv.time < ctx_end:
                                    ctx_end = cv.time
                                break

                    if not ctx_valid:
                        continue

                    # Check if any later target exists before context end
                    is_latest = True
                    if ctx_end is not None:
                        for j in range(i + 1, len(tvals)):
                            tv_later = tvals[j]
                            if (
                                not tv_later.unavailable
                                and cast(float, tv_later.time) < ctx_end
                            ):
                                is_latest = False
                                break

                    if is_latest:
                        rval = tv.data
                        break
                else:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

        # ERROR
        case _, _, _:
            raise NotImplementedError

    return rval
