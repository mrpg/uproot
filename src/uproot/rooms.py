# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
uproot rooms are finite-state machines.

if labels is not None: labels will be checked in any case. Labels may only be
used once.

State 0:
    open=False, the room is closed. Prospective players have to wait. If
    labels is not None, they have to enter their label. The same happens
    if open=True, but there is no config associated with the room.

State 1:
    open=True, the room is open. Prospective players don't wait.

    If no session is associated with the room, one is created and associated.

    - labels is not None or capacity is not None:
        add player only if associated session has free slots.
    - labels=None and capacity=None:
        a 'freejoin' room adds players to sessions.
"""

from typing import Any, Optional, TypeAlias

import uproot.events as e
from uproot.constraints import TOKEN_CHARS, return_or_raise, valid_token
from uproot.types import Sessionname

RoomType: TypeAlias = dict[str, Any]


def room(
    name: str,
    config: Optional[str] = None,
    labels: Optional[list[str]] = None,
    capacity: Optional[int] = None,
    open: bool = False,
    sname: Optional[Sessionname] = None,
) -> RoomType:
    if not valid_token(name):
        raise ValueError("Room name is invalid")

    if labels is not None:
        for label in labels:
            if len(label) > 128:
                raise ValueError("Room labels must be no longer than 128 characters")

    return {
        "name": name,
        "config": config,
        "labels": labels,
        "capacity": capacity,
        "open": open,
        "sname": sname,
    }


def freejoin(room: RoomType) -> bool:
    return room["labels"] is None and room["capacity"] is None


def labels_file(filename: str) -> set[str]:
    with open(filename) as f:
        return {
            return_or_raise(
                line.strip(), valid_token, msg="Label has invalid characters"
            )
            for line in f.readlines()
        }


def constrain_label(label: Any) -> str:
    if not isinstance(label, str):
        return ""

    if valid_token(label[:128]):
        return label[:128]

    newlabel = ""

    for ch in label:
        if ch in TOKEN_CHARS:
            newlabel += ch
        else:
            newlabel += "_"

        if len(newlabel) >= 128:
            break

    return newlabel


def validate(room: RoomType, label: str) -> bool:
    if freejoin(room):
        return True

    if room["labels"] is not None:
        return label != "" and label in room["labels"]

    return True


def start(roomname: str) -> None:
    """Signal that a room has started and clients can proceed."""
    e.set_room(roomname)


def reset(roomname: str) -> None:
    """Reset a room's state so it can be reused."""
    e.clear_room(roomname)
