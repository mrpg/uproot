# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from asyncio import Event
from collections import defaultdict

from uproot.types import BoundedPulse, PlayerIdentifier, Sessionname, Value

ATTENDANCE: defaultdict[Sessionname, BoundedPulse] = defaultdict(BoundedPulse)
FIELDCHANGE: defaultdict[Sessionname, BoundedPulse] = defaultdict(BoundedPulse)
ROOMS: defaultdict[str, Event] = defaultdict(Event)


def set_attendance(pid: PlayerIdentifier) -> None:
    if pid.sname in ATTENDANCE:
        ATTENDANCE[pid.sname].set(pid.uname)


def set_fieldchange(
    namespace: tuple[str, ...],
    field: str,
    value: Value,
) -> None:
    sname = namespace[1]

    FIELDCHANGE[sname].set((namespace, field, value))


def set_room(roomname: str) -> None:
    ROOMS[roomname].set()
