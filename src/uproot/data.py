# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import csv as pycsv
from io import BytesIO, StringIO
from typing import Any, AsyncGenerator, Iterable, Iterator, Mapping, Optional, cast
from zipfile import ZIP_DEFLATED, ZipFile

import orjson as json

import uproot.deployment as d
from uproot import cache
from uproot.constraints import ensure
from uproot.stable import encode_raw
from uproot.types import Value, sha256


def value2json(data: Any, unavailable: bool = False) -> str:
    if unavailable:
        return d.UNAVAILABLE_EQUIVALENT

    return encode_raw(data)[1].decode("utf-8")  # This is guaranteed to work


def json2csv(js: str) -> str:
    """
    This function gets the output of value2json(). This is then normalized.
    The user of this function will use the return value as some input to a function
    that properly escapes and outputs each cell. This function targets R's CSV dialect.
    """
    if js == "null":
        return ""

    if js.startswith('"') and js.endswith('"'):
        return cast(str, json.loads(js))  # strings will be properly escaped below

    if js in ("true", "false"):
        return js.upper()

    return js


def partial_matrix(
    everything: dict[tuple[str, ...], list[Value]],
) -> Iterator[dict[str, Any]]:
    previous_field: Optional[str]
    previous_seq: int

    previous_field, previous_seq = None, 0

    for k, values in everything.items():
        namespace = k[:-1]
        field = k[-1]

        for v in values:
            ensure(
                previous_field != field or v.seq >= previous_seq,
                RuntimeError,
                "Sequence ordering violation in data stream",
            )  # guaranteed by contract

            yield {
                "!storage": cache.tuple2dbns(namespace),
                "!field": field,
                "!time": v.time,
                "!seq": v.seq,
                "!context": v.context,
                "!unavailable": v.unavailable,
                "!data": v.data,
            }

            previous_field, previous_seq = field, v.seq


def long_to_wide(pm: Iterable[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for row in pm:
        yield {
            "!storage": row["!storage"],
            "!field": row["!field"],
            "!time": row["!time"],
            "!seq": row["!seq"],
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
            elif field == "_uproot_settings":
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

    # Process each storage
    for storage, changes in storage_changes.items():
        changes.sort(key=lambda x: x["!seq"])

        # Build state evolution and track all seen combinations
        current_state: dict[str, dict[str, Any]] = {}
        seen_combinations: dict[str, dict[str, Any]] = {}
        latest_state: dict[str, Any] | None = None

        for change in changes:
            field = change["!field"]
            seq = change["!seq"]
            # Update current state for this field
            current_state[field] = {
                "data": change["!data"],
                "unavailable": change["!unavailable"],
                "seq": seq,
            }

            state_snapshot = {
                "!storage": storage,
                "!time": change["!time"],
                "!seq": seq,
            }

            for f, field_state in current_state.items():
                if not field_state["unavailable"]:
                    state_snapshot[f] = field_state["data"]

            latest_state = state_snapshot

            if group_by_fields:
                # Check if all group_by_fields exist and are available
                all_fields_valid = True
                combination_values = []

                for gf in group_by_fields:
                    if gf not in current_state or current_state[gf]["unavailable"]:
                        all_fields_valid = False
                        break

                    combination_values.append(current_state[gf]["data"])

                if all_fields_valid:
                    combination_key = repr(tuple(combination_values))
                    seen_combinations[combination_key] = state_snapshot
            else:
                # No grouping - track single latest state
                seen_combinations[""] = state_snapshot

        # Yield all tracked combinations
        if group_by_fields and latest_state is not None and not seen_combinations:
            yield latest_state

        yield from seen_combinations.values()


DATA_DICTIONARY: dict[str, Any] = {
    "about": (
        "This file defines the uproot-internal columns, i.e., those whose "
        "names start with '!'. All other columns have other types, which "
        "are not documented here. Types below refer to the JSON "
        "representation (as in JSONL exports); CSV files render booleans as "
        "TRUE/FALSE, null as the empty cell, and lists/objects as JSON."
    ),
    "columns": {
        "!storage": {
            "type": "string",
            "description": (
                "Path of the storage object (row owner) that this row belongs "
                "to, e.g. 'player/mysession/abcde'. The first component is the "
                "storage kind; each kind is exported into a separate file."
            ),
        },
        "!field": {
            "type": "string",
            "description": (
                "Name of the field whose change this row records. Only present "
                "in the event-log formats (ultralong, sparse); in sparse, the "
                "new value is found in the column named by !field."
            ),
        },
        "!time": {
            "type": ["number", "null"],
            "description": (
                "Unix timestamp (seconds since 1970-01-01 UTC) at which the "
                "change was committed. In 'latest'-style formats: the time of "
                "the most recent change reflected in the row. Rows are NOT "
                "sorted by !time; see !seq."
            ),
        },
        "!seq": {
            "type": "integer",
            "description": (
                "Database-wide sequence number of the change, assigned in "
                "strictly increasing order at commit time. Sorting rows by "
                "!seq yields the true chronological order of events; gaps are "
                "normal (e.g., rows excluded by filters). In 'latest'-style "
                "formats: the !seq of the most recent change reflected in "
                "the row."
            ),
        },
        "!context": {
            "type": "string",
            "description": (
                "Code location that wrote the value, as "
                "'module.function:line'. Only present in the event-log formats "
                "(ultralong, sparse)."
            ),
        },
        "!unavailable": {
            "type": "boolean",
            "description": (
                "True if this row records the deletion of !field (a "
                "tombstone): from this change on, the field has no value until "
                "it is set again. Only present in the event-log formats "
                "(ultralong, sparse)."
            ),
        },
        "!data": {
            "type": "any",
            "description": (
                "The new value of !field after this change; its type varies "
                "by field. Only present in ultralong."
            ),
        },
    },
}


def column_order(field: str) -> tuple[int, str]:
    """Sort key that puts !-columns first and bulky columns last."""
    if field.startswith("!"):
        return (0, field)

    if field in ("packages", "page_order"):
        return (2, field)

    return (1, field)


def value_cell(key: str) -> bool:
    """Whether a column holds the changed value itself (rather than metadata).

    In tombstone rows (!unavailable), only value cells are masked; the
    !-prefixed metadata columns are kept intact.
    """
    return key == "!data" or not key.startswith("!")


def csv_out(rows: Iterable[dict[str, Any]]) -> str:
    rows = list(rows)

    buffer = StringIO()
    csvfields: dict[str, None] = {}

    for row in rows:
        csvfields.update(dict.fromkeys(row.keys()))

    sorted_fields = sorted(csvfields, key=column_order)

    dw = pycsv.DictWriter(buffer, fieldnames=sorted_fields)
    dw.writeheader()

    for row in rows:
        unavailable = row.get("!unavailable", False)
        dw.writerow(
            {
                k: json2csv(value2json(v, unavailable and value_cell(k)))
                for k, v in row.items()
            }
        )

    return buffer.getvalue()


def split_by_storage_kind(
    rows: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Partition rows by the first component of their "!storage" namespace."""
    kinds: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        kind = row["!storage"].split("/", 1)[0]
        kinds.setdefault(kind, []).append(row)

    return kinds


def rows_to_bytes(rows: Iterable[dict[str, Any]], filetype: str) -> bytes:
    """Serialize rows to a CSV or JSONL file body."""
    ensure(filetype in ("csv", "jsonl"), ValueError, "Invalid filetype")

    if filetype == "csv":
        return csv_out(rows).encode("utf-8")

    return "".join(jsonl_line(row) for row in rows).encode("utf-8")


def briefcase_extras(zf: ZipFile, wrapper: str, contents: dict[str, bytes]) -> None:
    """Add general non-data files to a briefcase.

    For now, this writes a SHA256SUMS file that `sha256sum -c` can verify
    from within the extracted wrapper directory.
    """
    zf.writestr(
        f"{wrapper}/SHA256SUMS",
        "".join(f"{sha256(blob)}  {name}\n" for name, blob in contents.items()),
    )


def briefcase_out(
    formats: Mapping[str, Iterable[dict[str, Any]]],
    wrapper: str,
    filetype: str,
    readme: str,
    extras: Optional[Mapping[str, bytes]] = None,
) -> bytes:
    """Create a ZIP "briefcase" wrapped in a single top-level directory.

    Each entry in `formats` becomes its own subdirectory holding one file per
    storage kind (player.csv, session.csv, …). Each file only contains columns
    for the fields that actually occur within its own storage kind. A
    README.txt, a DATA_DICTIONARY.json defining the uproot-internal (!)
    columns, any `extras` (path → file body), and a SHA256SUMS file covering
    every other file sit directly inside the wrapper directory.
    """
    buffer = BytesIO()

    with ZipFile(buffer, "w", ZIP_DEFLATED, compresslevel=1) as zf:
        contents = {
            "README.txt": readme.encode("utf-8"),
            "DATA_DICTIONARY.json": json.dumps(
                DATA_DICTIONARY, option=json.OPT_INDENT_2
            ),
        }

        if extras:
            contents.update(extras)

        for fmt, rows in formats.items():
            for kind, kindrows in sorted(split_by_storage_kind(rows).items()):
                contents[f"{fmt}/{kind}.{filetype}"] = rows_to_bytes(kindrows, filetype)

        for name, blob in contents.items():
            zf.writestr(f"{wrapper}/{name}", blob)

        briefcase_extras(zf, wrapper, contents)

    return buffer.getvalue()


def json_ready_row(row: dict[str, Any]) -> dict[str, Any]:
    unavailable = row.get("!unavailable", False)
    return {
        key: json.loads(value2json(value, unavailable and value_cell(key)))
        for key, value in row.items()
    }


def jsonl_line(row: dict[str, Any]) -> str:
    ready = json_ready_row(row)
    sorted_keys = sorted(ready, key=column_order)

    return json.dumps({k: ready[k] for k in sorted_keys}).decode("utf-8") + "\n"


async def jsonl_out(rows: Iterable[dict[str, Any]]) -> AsyncGenerator[str, None]:
    for row in rows:
        yield jsonl_line(row)
