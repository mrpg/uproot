# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Room operations service."""

from fastapi import HTTPException
from sortedcontainers import SortedDict

import uproot.deployment as d
import uproot.rooms as r
import uproot.storage as s
import uproot.types as t
from uproot.services.session_service import session_exists


def room_exists(roomname: str, raise_http: bool = True) -> None:
    """Check if a room exists.

    Args:
        roomname: Room name to check
        raise_http: If True, raise HTTPException; otherwise raise ValueError
    """
    with s.Admin() as admin:
        if roomname not in admin.rooms:
            if raise_http:
                raise HTTPException(status_code=400, detail="Invalid room")
            else:
                raise ValueError("Invalid room")


def rooms() -> SortedDict[str, dict]:
    """Get all rooms."""
    if d.PUBLIC_DEMO:
        return SortedDict()

    with s.Admin() as admin:
        return SortedDict(admin.rooms)


async def disassociate(roomname: str, sname: t.Sessionname) -> None:
    """Disassociate a session from a room."""
    room_exists(roomname, False)
    session_exists(sname, False)

    with s.Admin() as admin:
        admin.rooms[roomname]["sname"] = None

    with s.Session(sname) as session:
        session.room = None

    r.reset(roomname)


async def delete_room(roomname: str) -> None:
    """Delete a room."""
    room_exists(roomname, False)

    with s.Admin() as admin:
        if admin.rooms[roomname]["sname"] is not None:
            raise ValueError("Cannot delete room while a session is associated")

        del admin.rooms[roomname]

    r.reset(roomname)
