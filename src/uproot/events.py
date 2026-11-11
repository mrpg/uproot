# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from asyncio import Event
from collections import defaultdict

from uproot.types import BoundedPulse, PlayerIdentifier, Sessionname, Value

ATTENDANCE: defaultdict[Sessionname, BoundedPulse] = defaultdict(BoundedPulse)
FIELDCHANGE: defaultdict[Sessionname, BoundedPulse] = defaultdict(BoundedPulse)
ADMINCHAT: defaultdict[Sessionname, BoundedPulse] = defaultdict(BoundedPulse)


class RoomEvent(Event):
    """Readiness of one room lifetime; deletion also terminates its waiters."""

    deleted: bool = False

    def delete(self) -> None:
        self.deleted = True
        # Wake existing waiters, while keeping the readiness flag clear.
        self.set()
        self.clear()

    async def wait_ready(self) -> bool:
        if not self.deleted:
            await super().wait()
        return not self.deleted


ROOMS: defaultdict[str, RoomEvent] = defaultdict(RoomEvent)


def set_attendance(pid: PlayerIdentifier) -> None:
    if pid.sname in ATTENDANCE:
        ATTENDANCE[pid.sname].set(pid)


def set_fieldchange(
    namespace: tuple[str, ...],
    field: str,
    value: Value,
) -> None:
    sname = namespace[1]

    FIELDCHANGE[sname].set((namespace, field, value))


def set_room(roomname: str) -> None:
    ROOMS[roomname].set()


def clear_room(roomname: str) -> None:
    ROOMS[roomname].clear()


def delete_room(roomname: str) -> None:
    signal = ROOMS.pop(roomname, None)
    if signal is not None:
        signal.delete()
