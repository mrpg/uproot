# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
[Wir] ergreifen keine Idee, sondern die Idee ergreift uns, und
knechtet uns, und peitscht uns in die Arena hinein, daß wir,
wie gezwungene Gladiatoren, für sie kämpfen.

— Heinrich Heine
"""

from collections import defaultdict
from time import time  # This file uses clock time
from typing import TYPE_CHECKING, Any

from sortedcontainers import SortedList

import uproot.events as e
from uproot.types import InternalPage, Page, PlayerIdentifier, Sessionname, Username

if TYPE_CHECKING:
    from uproot.modules import ModuleManager
    from uproot.storage import Storage


__version_info__ = 0, 11, 0
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
CHAT_HOOKS: dict[tuple[str, str], list[tuple[str, str]]] = {}

APPS: "ModuleManager"
CONFIGS: dict[str, list[str]] = {}
CONFIGS_EXTRA: dict[str, Any] = {}


def leave_last_app(page: type[Page], player: "Storage") -> None:
    from uproot.core import switch_app

    switch_app(player, None)


PAGES: dict[str, type[Page]] = {
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
            "before_always_once": classmethod(leave_last_app),
        },
    ),
}


def set_offline(pid: PlayerIdentifier) -> None:
    try:
        t = ONLINE[pid.sname][pid.uname]

        del ONLINE[pid.sname][pid.uname]
        ONLINE_SORTED.remove((t, pid))
    except (KeyError, ValueError):
        pass

    e.set_attendance(pid)


def set_online(pid: PlayerIdentifier) -> None:
    t = time()

    previous = ONLINE[pid.sname].get(pid.uname)
    if previous is not None:
        try:
            ONLINE_SORTED.remove((previous, pid))
        except ValueError:
            pass

    ONLINE[pid.sname][pid.uname] = t
    ONLINE_SORTED.add((t, pid))

    e.set_attendance(pid)


def who_online(
    tolerance: float | None = None,
    sname: str | None = None,
) -> set[PlayerIdentifier]:
    """Return players seen within tolerance seconds, defaulting to one
    keepalive interval plus response slack. Retain timestamps for dropouts."""
    if tolerance is None:
        from uproot import deployment

        tolerance = deployment.KEEPALIVE_INTERVAL + deployment.KEEPALIVE_SLACK

    t = time()
    online = set()

    for last_seen, pid in reversed(ONLINE_SORTED):
        if t - last_seen > tolerance:
            break
        if sname is None or pid.sname == sname:
            online.add(pid)

    return online


def find_online(pid: PlayerIdentifier) -> float | None:
    try:
        return ONLINE[pid.sname][pid.uname]
    except KeyError:
        pass

    return None


def find_online_delta(pid: PlayerIdentifier) -> float | None:
    try:
        return time() - ONLINE[pid.sname][pid.uname]
    except KeyError:
        pass

    return None
