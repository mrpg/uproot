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
from uproot.events import set_fieldchange
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
        key == "" or key.isidentifier(),  # KEEP AS IS
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

                if namespace[0] in ("session", "player", "group", "model"):
                    set_fieldchange(
                        namespace,
                        key,
                        new_value,
                    )

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

                if namespace[0] in ("session", "player", "group", "model"):
                    set_fieldchange(
                        namespace,
                        key,
                        tombstone,
                    )

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

        case "get_within_context", _, None if isinstance(extra, dict):
            # WITHIN-ADJACENT
            # This code should stay algorithmically close to latest() in viewdata.js.

            ctx = extra
            with LOCK:
                ns_ = get_namespace(namespace)

                if not ns_ or not isinstance(ns_, dict) or key not in ns_:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

                # Verify all context fields exist
                for cf in ctx:
                    if cf not in ns_:
                        raise AttributeError(
                            f"No value found for {key} within the specified context in namespace {namespace}"
                        )

                # Collect all changes
                changes = []

                for field in set([key] + list(ctx.keys())):
                    if field in ns_:
                        for val in ns_[field]:
                            changes.append(
                                {
                                    "time": cast(float, val.time),
                                    "field": field,
                                    "unavailable": val.unavailable,
                                    "data": val.data,
                                }
                            )

                # Sort by time (just to be safe)
                changes.sort(key=lambda x: x["time"])

                # Build state evolution
                current_state = {}
                latest_valid_state = None

                for change in changes:
                    # Update current state with timestamp info
                    current_state[change["field"]] = {
                        "unavailable": change["unavailable"],
                        "data": change["data"],
                        "time": change["time"],
                    }

                    # Check if all conditions are met
                    all_conditions_met = True

                    if ctx:
                        for cond_field, cond_value in ctx.items():
                            if (
                                cond_field not in current_state
                                or current_state[cond_field]["unavailable"]
                                or current_state[cond_field]["data"] != cond_value
                            ):
                                all_conditions_met = False
                                break

                    # Check temporal ordering constraint: for non-context fields,
                    # context fields must be set before or at the same time as the target field
                    temporal_constraint_met = True
                    if (
                        all_conditions_met
                        and key in current_state
                        and ctx
                        and key not in ctx
                    ):
                        target_time = current_state[key]["time"]
                        for cond_field in ctx.keys():
                            if cond_field in current_state:
                                context_time = current_state[cond_field]["time"]
                                if context_time > target_time:
                                    temporal_constraint_met = False
                                    break

                    if all_conditions_met and temporal_constraint_met:
                        if (
                            key in current_state
                            and not current_state[key]["unavailable"]
                        ):
                            latest_valid_state = current_state[key]["data"]

                if latest_valid_state is None:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

                rval = latest_valid_state

        # ERROR
        case _, _, _:
            raise NotImplementedError

    return rval
