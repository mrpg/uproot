# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Data export and extraction service."""

import asyncio
from bisect import bisect_right
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Iterator,
    TypeAlias,
    cast,
)

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


def generate_data(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
    player_data_only: bool = False,
) -> tuple[
    Iterator[dict[str, Any]],
    Callable[[Iterator[dict[str, Any]]], Iterator[dict[str, Any]]],
    dict[str, list[str]],
]:
    """Generate data in the specified format."""
    gvar = [gv for gv in gvar if gv]

    # Initialize to satisfy static analysis (case _ will raise if no match)
    transformer: Callable[[Iterator[dict[str, Any]]], Iterator[dict[str, Any]]]
    transkwargs: dict[str, Any]

    match format:
        case "ultralong":
            transkwargs_ul: dict[str, Any] = {}
            transformer, transkwargs = data.noop, transkwargs_ul
        case "sparse":
            transkwargs_sp: dict[str, Any] = {}
            transformer, transkwargs = data.long_to_wide, transkwargs_sp
        case "latest":
            transformer, transkwargs = data.latest, {"group_by_fields": gvar}
        case _:
            raise NotImplementedError

    alldata = data.partial_matrix(everything_from_session(sname))

    if player_data_only:
        alldata = data.player_storage_only(alldata)

    if filters:
        alldata = data.reasonable_filters(alldata)

    return alldata, transformer, transkwargs


def generate_csv(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
    player_data_only: bool = False,
) -> str:
    """Generate CSV data for a session."""
    alldata, transformer, transkwargs = generate_data(
        sname, format, gvar, filters, player_data_only
    )

    return data.csv_out(transformer(alldata, **transkwargs))


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
    player_data_only: bool = False,
) -> AsyncGenerator[str, None]:
    """Generate JSONL data for a session as an async generator."""
    alldata, transformer, transkwargs = generate_data(
        sname, format, gvar, filters, player_data_only
    )

    async for chunk in data.jsonl_out(transformer(alldata, **transkwargs)):
        yield chunk
        await asyncio.sleep(0)


def page_times(sname: t.Sessionname) -> str:
    """Generate CSV of page timing data for a session."""
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

    return data.csv_out(times)
