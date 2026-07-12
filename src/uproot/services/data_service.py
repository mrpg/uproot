# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Data export and extraction service."""

import asyncio
import re
from bisect import bisect_right
from datetime import datetime, timezone
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Iterator,
    TypeAlias,
    cast,
)

import uproot
import uproot.cache as cache
import uproot.data as data
import uproot.storage as s
import uproot.types as t

DisplayValue: TypeAlias = tuple[
    Annotated[float | None, "time"],
    Annotated[bool, "unavailable"],
    Annotated[str | None, "typename"],
    Annotated[str, "displaystr"],
    Annotated[str, "context"],
]
DataRows: TypeAlias = Iterator[dict[str, Any]]
DataTransformer: TypeAlias = Callable[..., DataRows]


def everything_from_session(
    sname: t.Sessionname,
) -> dict[tuple[str, ...], list[t.Value]]:
    """Extract all data from a session."""
    # Go ahead… https://www.youtube.com/watch?v=2WhHW8zD620

    matches: dict[tuple[str, ...], Any] = {}
    sname = str(sname)

    for lvl1_k, lvl1_v in cache.MEMORY_HISTORY.items():
        if isinstance(lvl1_v, dict) and sname in lvl1_v:
            k = (
                lvl1_k,
                sname,
            )
            namespace = cache.get_namespace(k)
            if namespace is not None:
                matches |= cache.flatten(namespace, k)

    return matches


def data_display(x: Any) -> str:
    """Convert a value to a display-friendly string.

    This is similar to data.value2json and data.json2csv, but a bit simpler
    The intention is to provide a user-friendly string representation of 'x'
    """
    if isinstance(x, (bytearray, bytes)):
        # Nobody wants to view that in the browser (not in that form at least)
        return "[Binary]"
    else:
        try:
            return str(x)
        except Exception:
            return repr(x)


async def everything_from_session_display(
    sname: t.Sessionname,
    since_epoch: float = 0.0,
) -> tuple[dict[str, dict[str, list[DisplayValue]]], float]:
    """Get session data formatted for display.

    Returns a tuple of (data dict, last update timestamp).
    """
    # This function returns something that orjson can handle

    sname = str(sname)
    retval: dict[str, dict[str, list[DisplayValue]]] = {}
    last_update: float = since_epoch

    for uname, fields in cache.MEMORY_HISTORY.get("player", {}).get(sname, {}).items():
        retval[uname] = {}

        for field, values in fields.items():
            retval[uname][field] = displayvalues = [
                cast(
                    DisplayValue,
                    (
                        val.time,
                        val.unavailable,
                        type(val.data).__name__,
                        data_display(val.data),
                        val.context,
                    ),
                )
                for val in values
                if val.time is not None and val.time > since_epoch
            ]

            if displayvalues:
                if (
                    isinstance(displayvalues[-1][0], float)
                    and displayvalues[-1][0] > last_update
                ):
                    last_update = displayvalues[-1][0]
            else:
                del retval[uname][field]

        if not retval[uname]:
            del retval[uname]

        await asyncio.sleep(0)

    return retval, last_update


def data_rows_for_session(sname: t.Sessionname, filters: bool) -> DataRows:
    rows: DataRows = data.partial_matrix(everything_from_session(sname))

    if filters:
        rows = data.reasonable_filters(rows)

    return rows


def generate_data(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
) -> tuple[
    DataRows,
    DataTransformer,
    dict[str, Any],
]:
    """Generate data in the specified format."""
    gvar = [gv for gv in gvar if gv]

    match format:
        case "ultralong":
            return data_rows_for_session(sname, filters), data.noop, {}
        case "sparse":
            return data_rows_for_session(sname, filters), data.long_to_wide, {}
        case "latest":
            return (
                data_rows_for_session(sname, filters),
                data.latest,
                {"group_by_fields": gvar},
            )
        case _:
            raise NotImplementedError


def grouped_format_name(gvar: list[str]) -> str:
    """Directory name for the optional grouped "latest" format."""
    parts = [re.sub(r"[^A-Za-z0-9.-]+", "-", gv).strip("-") for gv in gvar]
    parts = [part for part in parts if part]

    if not parts:
        return "latest_grouped"

    return "latest_by_" + "_".join(parts)


def briefcase_readme(
    sname: str,
    filetype: str,
    gvar: list[str],
    filters: bool,
) -> str:
    """Compose the README.txt included in every briefcase."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f'Data export of uproot session "{sname}"'

    grouped = ""
    if gvar:
        grouped = (
            f"{grouped_format_name(gvar)}/\n"
            f"    One row per storage and per combination of "
            f"({', '.join(gvar)}): the\n"
            f"    state as it was at the end of each combination.\n\n"
        )

    if filters:
        filtered = (
            "Reasonable filters were applied: uproot-internal fields were\n"
            "excluded, renamed or transformed."
        )
    else:
        filtered = "No filters were applied: uproot-internal fields are included as-is."

    return (
        f"{title}\n"
        f"{'=' * len(title)}\n\n"
        f"Created {stamp} by uproot {uproot.__version__}.\n\n"
        f"Each directory in this archive contains the full session data in one\n"
        f"format, split into one {filetype.upper()} file per storage kind\n"
        f"(player.{filetype}, session.{filetype}, ...).\n\n"
        f"ultralong/\n"
        f"    Raw event log: every single change to any field is its own row.\n\n"
        f"sparse/\n"
        f"    Each row represents a change, with every field as its own column;\n"
        f"    only the fields that actually changed at that timestamp are\n"
        f"    filled in.\n\n"
        f"latest/\n"
        f"    One row per storage (e.g., per player) showing the final state:\n"
        f"    the last value of every field.\n\n"
        f"{grouped}"
        f"Note that nothing in these files is sorted by !time: rows come\n"
        f"grouped by storage and field, not chronologically. Where the order\n"
        f"of events matters, sort rows by !seq yourself; !seq reflects the\n"
        f"order in which changes were committed.\n\n"
        f"{filtered}\n\n"
        f"page_times.{filetype} lists every page visit: which player entered\n"
        f"which page at which time, and when they left it. It is derived\n"
        f"from the players' show_page and page_order histories.\n\n"
        f"DATA_DICTIONARY.json defines the uproot-internal columns, i.e.,\n"
        f'those whose names start with "!". All other columns have other\n'
        f"types, which are not documented there.\n\n"
        f"SHA256SUMS lists the SHA-256 hash of every file in this archive.\n"
        f"Verify the files' integrity from within this directory using\n\n"
        f"    sha256sum -c SHA256SUMS\n\n"
        f"For more details, see https://uproot.science/running/export/\n"
    )


def generate_briefcase(
    sname: t.Sessionname,
    gvar: list[str],
    filters: bool,
    filetype: str = "csv",
) -> bytes:
    """Generate a ZIP briefcase containing all key formats for a session.

    The briefcase always contains the ultralong, sparse, and latest formats
    as well as the page times; a non-empty `gvar` adds a grouped "latest"
    format on top.
    """
    gvar = [gv for gv in gvar if gv]
    rows = list(data_rows_for_session(sname, filters))

    formats: dict[str, DataRows] = {
        "ultralong": data.noop(rows),
        "sparse": data.long_to_wide(rows),
        "latest": data.latest(rows),
    }

    if gvar:
        formats[grouped_format_name(gvar)] = data.latest(rows, group_by_fields=gvar)

    return data.briefcase_out(
        formats,
        wrapper=str(sname),
        filetype=filetype,
        readme=briefcase_readme(str(sname), filetype, gvar, filters),
        extras={
            f"page_times.{filetype}": data.rows_to_bytes(
                page_times_rows(sname), filetype
            ),
        },
    )


def is_custom_data_export(value: Any) -> bool:
    """Return whether a pipeline value can be exported as tabular rows."""
    return isinstance(value, list) and all(
        isinstance(row, dict) and all(isinstance(key, str) for key in row)
        for row in value
    )


def generate_custom_csv(rows: list[dict[str, Any]]) -> str:
    return data.csv_out(rows)


async def generate_custom_jsonl(
    rows: list[dict[str, Any]],
) -> AsyncGenerator[str, None]:
    async for chunk in data.jsonl_out(rows):
        yield chunk
        await asyncio.sleep(0)


def pipeline_result_display(value: Any) -> str:
    if isinstance(value, str):
        return value

    try:
        return data.value2json(value)
    except Exception:
        return str(value)


async def generate_jsonl(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
) -> AsyncGenerator[str, None]:
    """Generate JSONL data for a session as an async generator."""
    alldata, transformer, transkwargs = generate_data(sname, format, gvar, filters)

    async for chunk in data.jsonl_out(transformer(alldata, **transkwargs)):
        yield chunk
        await asyncio.sleep(0)


def page_times_rows(sname: t.Sessionname) -> list[dict[str, Any]]:
    """Derive page timing rows (one per page visit) for a session."""
    times: list[dict[str, Any]] = []

    with s.Session(sname) as session:
        for pid in session._uproot_players:
            uname = pid.uname

            with t.materialize(pid) as player:
                one_row = False
                history = player.__history__()
                last_order = None

                show_pages = history.get("show_page", [])  # type: ignore[var-annotated]
                page_orders = history.get("page_order", [])  # type: ignore[var-annotated]

                for show_page in show_pages:
                    if not isinstance(show_page.data, int):
                        continue

                    # Binary search for the last page_order with time <= show_page.time.
                    if page_orders:
                        idx = bisect_right(
                            page_orders, show_page.time, key=lambda v: v.time
                        )
                        if idx > 0:
                            last_order = page_orders[idx - 1].data

                    page_name = None

                    if isinstance(last_order, list):
                        if show_page.data == len(last_order):
                            page_name = "(End)"
                        elif show_page.data == -1:
                            page_name = "(Initialize)"
                        else:
                            try:
                                page_name = last_order[show_page.data]
                            except (TypeError, IndexError):
                                pass

                    if one_row:
                        times[-1]["left"] = show_page.time

                    times.append(
                        {
                            "sname": sname,
                            "uname": uname,
                            "show_page": show_page.data,
                            "page_name": page_name,
                            "entered": show_page.time,
                            "left": None,
                            "context": show_page.context,
                        }
                    )
                    one_row = True

    return times
