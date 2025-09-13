# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file exposes an internal API that end users MUST NOT rely upon. Rely upon storage.py instead.
"""

import copy
import threading
from time import time
from typing import TYPE_CHECKING, Any, Optional, Union, cast

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

        if isinstance(v, list):
            result[new_trail] = v
        elif isinstance(v, dict):
            result.update(flatten(v, new_trail))
        else:
            result[new_trail] = v

    return result


def get_namespace(
    namespace: tuple[str, ...], create: bool = False
) -> Optional[dict[str, Any]]:
    """Navigate to namespace location. If create=True, creates missing levels."""
    current = MEMORY_HISTORY

    for part in namespace:
        if not isinstance(current, dict):
            return None

        if create and part not in current:
            current[part] = {}
        elif part not in current:
            return None

        current = current[part]

    return cast(Optional[dict[str, Any]], current)


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
                nested_dict[field] = []

            # Add to history
            if nested_dict is not None:
                nested_dict[field].append(value)


def get_current_value(namespace: tuple[str, ...], field: str) -> Any:
    """Get current value from last history entry.
    NOTE: Assumes caller holds LOCK.
    """
    current = get_namespace(namespace)
    if (
        current
        and isinstance(current, dict)
        and field in current
        and isinstance(current[field], list)
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
                    nested_dict[key] = []

                # Add to history with current timestamp
                new_value = Value(DATABASE.now, False, safe_deepcopy(value), context)

                # Special handling for player lists - replace entire history like database does
                if nested_dict is not None:
                    if key == "players" and namespace[0] == "session":
                        nested_dict[key] = [new_value]
                    else:
                        nested_dict[key].append(new_value)
            rval = value

        case "delete", _, None if isinstance(context, str):
            DATABASE.delete(tuple2dbns(namespace), key, context)
            # Update in-memory data
            with LOCK:
                # Add tombstone to history
                nested_dict = get_namespace(namespace, create=True)
                if nested_dict is not None and key not in nested_dict:
                    nested_dict[key] = []

                tombstone = Value(DATABASE.now, True, None, context)
                if nested_dict is not None:
                    nested_dict[key].append(tombstone)

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
                    rval = []

        case "fields", "", None:
            with LOCK:
                current = get_namespace(namespace)
                if current and isinstance(current, dict):
                    # Return only fields that have current (non-tombstone) values
                    rval = []
                    for field in current.keys():
                        if (
                            isinstance(current[field], list)
                            and current[field]
                            and not current[field][-1].unavailable
                        ):
                            rval.append(field)
                else:
                    rval = []

        case "has_fields", "", None:
            with LOCK:
                current = get_namespace(namespace)
                if current and isinstance(current, dict):
                    # Check if any field has current (non-tombstone) values
                    rval = any(
                        isinstance(values, list)
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
            mnamespaces: list[str]
            mnamespaces, mkey = cast(tuple[list[str], str], extra)
            with LOCK:
                result = {}
                for namespace_str in mnamespaces:
                    namespace = dbns2tuple(namespace_str)
                    current = get_namespace(namespace)
                    if (
                        current
                        and isinstance(current, dict)
                        and mkey in current
                        and isinstance(current[mkey], list)
                        and current[mkey]
                    ):
                        latest = current[mkey][-1]
                        if not latest.unavailable:
                            result[(namespace_str, mkey)] = latest
                rval = result

        case "fields_from_session", "", None if isinstance(extra, tuple):
            sname: str
            since: float
            sname, since = cast(tuple[str, float], extra)
            with LOCK:
                session_result: dict[tuple[tuple[str, str, str], str], Any] = {}
                # Direct access to player data for this session
                session_players = get_namespace(("player", sname))
                if session_players and isinstance(session_players, dict):
                    for player_name, player_fields in session_players.items():
                        if isinstance(player_fields, dict):
                            ns = ("player", sname, player_name)
                            for field_name, values in player_fields.items():
                                field = cast(str, field_name)
                                if (
                                    values
                                    and isinstance(values, list)
                                    and values[-1].time > since
                                ):
                                    session_result[(ns, field)] = values[-1]
                rval = session_result

        case "get_within_context", _, None if isinstance(extra, dict):
            context_fields: dict[str, Any]
            context_fields = extra
            with LOCK:
                # This is complex - need to implement the context window logic using in-memory data
                current = get_namespace(namespace)
                if not current or not isinstance(current, dict) or key not in current:
                    raise AttributeError(
                        f"No value found for {key} within the specified context in namespace {namespace}"
                    )

                target_values = current[key]

                # Iterate from newest to oldest
                for i in range(len(target_values) - 1, -1, -1):
                    target_value = target_values[i]

                    if target_value.unavailable:
                        continue

                    target_time = cast(float, target_value.time)
                    all_contexts_match = True

                    # Check each required context field at target_time
                    for context_field, required_value in context_fields.items():
                        if context_field not in current:
                            all_contexts_match = False
                            break

                        context_values = current[context_field]

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
                            if context_field in current:
                                context_values = current[context_field]

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
