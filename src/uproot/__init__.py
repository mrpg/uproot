# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from collections import defaultdict
from time import time  # This file uses clock time
from typing import TYPE_CHECKING, Any, Optional, Union

from sortedcontainers import SortedList

from uproot.types import InternalPage, Page, PlayerIdentifier, Sessionname, Username

if TYPE_CHECKING:
    from uproot.modules import ModuleManager


__version__ = "0.0.1"
__author__ = "Max R. P. Grossmann, Holger Gerhardt, et al."
__email__ = "info@uproot.science"


KEY: str = ""
INFO: defaultdict[
    Sessionname,
    dict[
        Username,
        tuple[
            Optional[int],
            list[str],
            int,
        ],
    ],
] = defaultdict(dict)
ONLINE: dict[PlayerIdentifier, float] = dict()
ONLINE_SORTED: SortedList[tuple[float, PlayerIdentifier]] = SortedList()
MANUAL_DROPOUTS: set[PlayerIdentifier] = set()
WATCH: set[tuple[PlayerIdentifier, float, str, str]] = set()

APPS: "ModuleManager"
CONFIGS: dict[str, list[str]] = dict()
CONFIGS_PPATHS: dict[str, list[str]] = dict()
CONFIGS_EXTRA: dict[str, Any] = dict()
PAGES: dict[str, Union[tuple[str, str], type[Page]]] = {
    "Initialize.html": type(
        "Initialize",
        (InternalPage,),
        dict(
            show=True,
            template="Initialize.html",
        ),
    ),
    "RoomHello.html": type(
        "RoomHello",
        (InternalPage,),
        dict(
            show=True,
            template="RoomHello.html",
        ),
    ),
    "RoomFull.html": type(
        "RoomFull",
        (InternalPage,),
        dict(
            show=True,
            template="RoomFull.html",
        ),
    ),
    "End.html": type(
        "End",
        (InternalPage,),
        dict(
            show=True,
            template="End.html",
        ),
    ),
}


def set_info(
    pid: PlayerIdentifier,
    id_: Optional[int],
    page_order: list[str],
    show_page: int,
) -> None:
    if id_ is None and pid.uname in INFO[pid.sname]:
        id_ = INFO[pid.sname][pid.uname][0]

    INFO[pid.sname][pid.uname] = id_, page_order, show_page


def get_info(pid: PlayerIdentifier) -> tuple[Optional[int], list[str], int]:
    try:
        return INFO[pid.sname][pid.uname]
    except KeyError:
        return None, None


def set_offline(pid: PlayerIdentifier) -> None:
    try:
        t = ONLINE[pid]

        del ONLINE[pid]
        ONLINE_SORTED.remove((t, pid))
    except Exception:
        pass


def set_online(pid: PlayerIdentifier) -> None:
    t = time()

    ONLINE[pid] = t
    ONLINE_SORTED.add((t, pid))


def who_online(tolerance: float, sname: Optional[str] = None) -> set[PlayerIdentifier]:
    t = time()
    online = set()

    for e in reversed(ONLINE_SORTED):
        if t - e[0] <= tolerance and (sname is None or e[1].sname == sname):
            online.add(e[1])
        else:
            break

    return online


def find_online(pid: PlayerIdentifier) -> Optional[float]:
    try:
        return ONLINE[pid]
    except KeyError:
        pass

    return None


def find_online_delta(pid: PlayerIdentifier) -> Optional[float]:
    try:
        return time() - ONLINE[pid]
    except KeyError:
        pass

    return None
