# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from collections import defaultdict
from typing import Optional

from uproot.types import PlayerIdentifier, Pulse, Sessionname

ATTENDANCE: defaultdict[Sessionname, Pulse] = defaultdict(Pulse)
ROOMS: defaultdict[str, Pulse] = defaultdict(Pulse)


def set_attendance(pid: PlayerIdentifier, show_page: Optional[int] = None) -> None:
    if pid.sname in ATTENDANCE:
        ATTENDANCE[pid.sname].set((pid.uname, show_page))


def set_room(roomname: str) -> None:
    if roomname in ROOMS:
        ROOMS[roomname].set(True)
