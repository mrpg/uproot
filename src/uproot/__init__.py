# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from collections import defaultdict
from time import time  # This file uses clock time
from typing import TYPE_CHECKING, Any, Optional, Union

from sortedcontainers import SortedList

import uproot.events as e
from uproot.types import InternalPage, Page, PlayerIdentifier, Sessionname, Username

if TYPE_CHECKING:
    from uproot.modules import ModuleManager


__version_info__ = 0, 0, 1
__version__ = ".".join(map(str, __version_info__))
__author__ = "Max R. P. Grossmann, Holger Gerhardt, et al."
__email__ = "info@uproot.science"


KEY: str = ""
ONLINE: defaultdict[
    Sessionname,
    dict[Username, float],
] = defaultdict(dict)
ONLINE_SORTED: SortedList[tuple[float, PlayerIdentifier]] = SortedList()
MANUAL_DROPOUTS: set[PlayerIdentifier] = set()
WATCH: set[tuple[PlayerIdentifier, float, str, str]] = set()

APPS: "ModuleManager"
CONFIGS: dict[str, list[str]] = {}
CONFIGS_PPATHS: dict[str, list[str]] = {}
CONFIGS_EXTRA: dict[str, Any] = {}
PAGES: dict[str, Union[tuple[str, str], type[Page]]] = {
    "Initialize.html": type(
        "Initialize",
        (InternalPage,),
        {
            "show": True,
            "template": "Initialize.html",
        },
    ),
    "JustPOST.html": type(
        "JustPOST",
        (InternalPage,),
        {
            "show": True,
            "template": "JustPOST.html",
        },
    ),
    "RoomHello.html": type(
        "RoomHello",
        (InternalPage,),
        {
            "show": True,
            "template": "RoomHello.html",
        },
    ),
    "RoomFull.html": type(
        "RoomFull",
        (InternalPage,),
        {
            "show": True,
            "template": "RoomFull.html",
        },
    ),
    "End.html": type(
        "End",
        (InternalPage,),
        {
            "show": True,
            "template": "End.html",
            "before_always_once": classmethod(
                lambda page, player: setattr(player, "app", None)
            ),  # See Lundh's rules: https://docs.python.org/3/howto/functional.html …
        },
    ),
}


def set_offline(pid: PlayerIdentifier) -> None:
    try:
        t = ONLINE[pid.sname][pid.uname]

        del ONLINE[pid.sname][pid.uname]
        ONLINE_SORTED.remove((t, pid))
    except Exception:  # nosec B110 - Best effort cleanup, failures are acceptable
        pass

    e.set_attendance(pid)


def set_online(pid: PlayerIdentifier) -> None:
    t = time()

    ONLINE[pid.sname][pid.uname] = t
    ONLINE_SORTED.add((t, pid))

    e.set_attendance(pid)


def who_online(
    tolerance: Optional[float] = None,
    sname: Optional[str] = None,
) -> set[PlayerIdentifier]:
    online = set()

    if tolerance is None:
        if sname is None:
            for sessionname, users in ONLINE.items():
                for username in users.keys():
                    online.add(PlayerIdentifier(sname=sessionname, uname=username))
        else:
            if sname in ONLINE:
                for username in ONLINE[sname].keys():
                    online.add(PlayerIdentifier(sname=sname, uname=username))
    else:
        t = time()

        for e in reversed(ONLINE_SORTED):
            if t - e[0] <= tolerance and (sname is None or e[1].sname == sname):
                online.add(e[1])
            else:
                break

    return online


def find_online(pid: PlayerIdentifier) -> Optional[float]:
    try:
        return ONLINE[pid.sname][pid.uname]
    except KeyError:
        pass

    return None


def find_online_delta(pid: PlayerIdentifier) -> Optional[float]:
    try:
        return time() - ONLINE[pid.sname][pid.uname]
    except KeyError:
        pass

    return None
