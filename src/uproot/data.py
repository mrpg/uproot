# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv as pycsv
from io import StringIO
from typing import Any, AsyncGenerator, Callable, Iterable, Iterator, Optional, cast

import orjson as json

import uproot.deployment as d
from uproot.constraints import ensure


def raw2json(b: Optional[bytes]) -> str:
    """
    This function unpacks the raw data received from the database. Since the database
    just stores binary JSON with a one-byte type prefix, we can just strip the former
    and allow the user of this function to use the resulting str as true JSON.
    """
    if b is not None:
        return b[1:].decode("utf-8")
    else:
        return d.UNAVAILABLE_EQUIVALENT


def json2csv(js: str) -> str:
    """
    This function gets the output of raw2json(). This is then normalized.
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
    history_raw: Iterator[tuple[str, str, "RawValue"]],  # This is wrong now (TODO)
) -> Iterator[dict[str, Any]]:
    previous_field: Optional[str]
    previous_time: float

    previous_field, previous_time = None, 0.0

    for namespace, field, v in history_raw:
        if d.SKIP_INTERNAL and (
            field.startswith("_uproot_")
            or (namespace in ("group", "session", "model") and field == "players")
            or (namespace in "session" and field in ("models", "groups"))
        ):
            continue

        ensure(
            previous_field != field or cast(float, v.time) >= previous_time,
            RuntimeError,
            "Time ordering violation in data stream",
        )  # guaranteed by contract

        yield {
            "!storage": namespace,
            "!field": field,
            "!time": v.time,
            "!context": v.context,
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
            row["!field"].strip('"'): row["!data"],  # ha!
        }


def noop(pm: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    yield from pm


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


def rowsort_key(
    priority_fields: Optional[list[str]] = None,
) -> tuple[Callable[[str], tuple[int, str]], Callable[[dict[str, Any]], list[Any]]]:
    if priority_fields is None:
        priority_fields = []

    sortkeys = ["!storage", "!time"] + priority_fields

    def keykey(key: str) -> tuple[int, str]:
        prio = 0

        if key in sortkeys:
            prio = -1
        elif key in ("session", "key", "page_order") or key.startswith("_uproot_"):
            prio = 1

        return (
            prio,
            key,
        )

    def rowkey(row: dict[str, Any]) -> list[Any]:
        return [row.get(c, None) for c in sortkeys]

    return keykey, rowkey


def csv_out(
    rows: Iterable[dict[str, Any]], priority_fields: Optional[list[str]] = None
) -> str:
    rows = list(rows)

    buffer = StringIO()
    csvfields: set[str] = set()

    for row in rows:
        csvfields.update(row.keys())

    keys = rowsort_key(priority_fields)

    dw = pycsv.DictWriter(buffer, fieldnames=sorted(csvfields, key=keys[0]))
    dw.writeheader()

    for row in sorted(rows, key=keys[1]):
        dw.writerow(
            {
                k: json2csv(
                    raw2json(v)
                    if v is None or isinstance(v, bytes)
                    else json.dumps(v).decode("utf-8")
                )
                for k, v in row.items()
            }
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
            (
                f'"{k}":{raw2json(v)}'
                if v is None or isinstance(v, bytes)
                else f'"{k}":{json.dumps(v).decode("utf-8")}'
            )
            for k, v in row.items()
        )
        yield "}"

    yield "]"
