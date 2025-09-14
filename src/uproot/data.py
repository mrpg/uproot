# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv as pycsv
from io import StringIO
from typing import Any, AsyncGenerator, Iterable, Iterator, Optional, cast

import orjson as json

import uproot.cache as cache
import uproot.deployment as d
from uproot.constraints import ensure
from uproot.stable import _encode
from uproot.types import Value


def value2json(data: Any, unavailable: bool = False) -> str:
    if unavailable:
        return d.UNAVAILABLE_EQUIVALENT
    else:
        return _encode(data)[1].decode("utf-8")  # This is guaranteed to work


def json2csv(js: str) -> str:
    """
    This function gets the output of value2json(). This is then normalized.
    The user of this function will use the return value as some input to a function
    that properly escapes and outputs each cell. This function targets R's CSV dialect.
    """
    if js == "null":
        return ""
    elif js.startswith('"') and js.endswith('"'):
        return cast(str, json.loads(js))  # strings will be properly escaped below
    elif js == "true" or js == "false":
        return js.upper()
    else:
        return js


def partial_matrix(
    everything: dict[tuple[str, ...], list[Value]],
) -> Iterator[dict[str, Any]]:
    previous_field: Optional[str]
    previous_time: float

    previous_field, previous_time = None, 0.0

    for k, values in everything.items():
        namespace = k[:-1]
        field = k[-1]

        for v in values:
            ensure(
                previous_field != field or cast(float, v.time) >= previous_time,
                RuntimeError,
                "Time ordering violation in data stream",
            )  # guaranteed by contract

            yield {
                "!storage": cache.tuple2dbns(namespace),
                "!field": field,
                "!time": v.time,
                "!context": v.context,
                "!unavailable": v.unavailable,
                "!data": v.data,
            }

            previous_field, previous_time = field, cast(
                float, v.time
            )  # v.time is a float here because it's straight outta the DB


def long_to_wide(pm: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for row in pm:
        yield {
            "!storage": row["!storage"],
            "!field": row["!field"],
            "!time": row["!time"],
            "!context": row["!context"],
            "!unavailable": row["!unavailable"],
            row["!field"].strip('"'): row["!data"],  # ha!
        }


def noop(pm: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    yield from pm


def reasonable_filters(pm: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for row in pm:
        storage = row["!storage"]
        field = row["!field"]
        data = row["!data"]

        if field.startswith("_uproot_"):
            if field == "_uproot_group" and data is not None:
                row["!field"] = "group"
                row["!data"] = f"group/{data.sname}/{data.gname}"
            elif field == "_uproot_session":
                row["!field"] = "session"
                row["!data"] = f"session/{data}"
            elif field == "_uproot_dropout":
                pass
            else:
                continue

        if storage.startswith("session/"):
            namespace = cache.dbns2tuple(storage)
            if len(namespace) >= 2:
                _, sname = namespace[0], namespace[1]
            else:
                continue

            if field == "groups":
                row["!data"] = [f"group/{sname}/{gname}" for gname in data]
            elif field == "players":
                row["!data"] = [f"player/{sname}/{uname}" for _, uname in data]

        yield row


def latest(
    pm: Iterable[dict[str, Any]], group_by_fields: Optional[list[str]] = None
) -> Iterator[dict[str, Any]]:
    if group_by_fields is None:
        group_by_fields = []

    # Collect changes by storage
    storage_changes: dict[str, list[dict[str, Any]]] = {}

    for row in pm:
        storage = row["!storage"]
        if storage not in storage_changes:
            storage_changes[storage] = []

        storage_changes[storage].append(row)

    # Process each storage to build state snapshots
    all_snapshots = []

    for storage, changes in storage_changes.items():
        # Sort changes by time within this storage
        changes.sort(key=lambda x: x["!time"])

        # Build state evolution
        current_state = {"!storage": storage}

        for change in changes:
            current_state[change["!field"]] = change["!data"]
            current_state["!time"] = change["!time"]
            current_state["!unavailable"] = change["!unavailable"]
            # Save snapshot after each change
            all_snapshots.append(current_state.copy())

    # Group snapshots and keep latest for each group
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}

    for snapshot in all_snapshots:
        group_key = tuple(
            snapshot.get(field) for field in ["!storage"] + group_by_fields
        )

        if group_key not in groups or snapshot["!time"] > groups[group_key]["!time"]:
            groups[group_key] = snapshot

    yield from groups.values()


def csv_out(rows: Iterable[dict[str, Any]]) -> str:
    rows = list(rows)

    buffer = StringIO()
    csvfields: set[str] = set()

    for row in rows:
        csvfields.update(row.keys())

    dw = pycsv.DictWriter(buffer, fieldnames=csvfields)
    dw.writeheader()

    for row in rows:
        dw.writerow(
            {k: json2csv(value2json(v, row["!unavailable"])) for k, v in row.items()}
        )

    return buffer.getvalue()


async def json_out(rows: Iterable[dict[str, Any]]) -> AsyncGenerator[str, None]:
    first = True
    yield "["

    for row in rows:
        if not first:
            yield ","
        else:
            first = False

        yield "{"
        yield ",".join(
            (f'"{k}":{value2json(v, row["!unavailable"])}') for k, v in row.items()
        )
        yield "}"

    yield "]"
