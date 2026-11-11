# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
uproot rooms are finite-state machines.

if labels is not None: participants must enter a label, and each label maps to
at most one player. A non-empty list accepts only the listed labels. An empty
list accepts any non-empty label.

State 0 (not ready):
    open=False, or there is neither a session nor a loaded config associated
    with the room. Prospective players have to wait. If labels is not None,
    they have to enter a valid label first.

State 1 (ready):
    open=True and a session or a loaded config (one in uproot.CONFIGS) is
    associated with the room. Prospective players don't wait.

    If no session is associated with the room, one is created and associated.

    - capacity is not None or labels is non-empty:
        add player only if associated session has free slots. Without an
        explicit capacity, the number of labels is the capacity.
    - capacity=None and labels is None or empty:
        a 'freejoin' room adds players to sessions.

After each change, sync() sets the readiness event iff the room is ready.
Awakened clients recheck readiness when joining. Deletion terminates existing
subscriptions separately; a new room with the same name has a fresh signal.
"""

from typing import Any, TypeAlias

import uproot as u
import uproot.events as e
from uproot.constraints import TOKEN_CHARS, return_or_raise, valid_token
from uproot.storage import Admin
from uproot.types import Sessionname

RoomType: TypeAlias = dict[str, Any]


def room(
    name: str,
    config: str | None = None,
    labels: list[str] | None = None,
    capacity: int | None = None,
    open: bool = False,
    sname: Sessionname | None = None,
) -> RoomType:
    if not valid_token(name):
        raise ValueError("Room name is invalid")

    check_capacity(capacity)

    if labels is not None:
        seen: set[str] = set()

        for label in labels:
            if not label:
                raise ValueError("Room labels must not be empty")
            if len(label) > 128:
                raise ValueError("Room labels must be no longer than 128 characters")
            if not valid_token(label):
                raise ValueError("Room labels contain invalid characters")
            if label in seen:
                raise ValueError("Room labels must be unique")

            seen.add(label)

    # An empty config or sname means none: storing "" would make the room
    # count as ready or as associated with a session that does not exist.
    return {
        "name": name,
        "config": config or None,
        "labels": labels,
        "capacity": capacity,
        "open": open,
        "sname": sname or None,
    }


def check_capacity(capacity: Any) -> None:
    if capacity is not None and (type(capacity) is not int or capacity < 0):
        raise ValueError("Room capacity must be a non-negative integer")


def freejoin(room: RoomType) -> bool:
    return not room["labels"] and room["capacity"] is None


def from_file(filename: str) -> list[str]:
    labels: dict[str, None] = {}

    with open(filename, encoding="utf-8") as f:
        for line in f:
            label = line.split("#")[0].strip()
            if not label:
                continue

            return_or_raise(label, valid_token, msg="Label has invalid characters")
            labels[label] = None

    return list(labels)


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
        if not room["labels"]:
            return label != ""

        return label != "" and label in room["labels"]

    return True


def ready(room: RoomType) -> bool:
    """Whether prospective players proceed instead of waiting. A config that is
    not loaded (e.g., removed from the project) cannot start a session."""
    return bool(room["open"]) and (
        room["sname"] is not None or room["config"] in u.CONFIGS
    )


def sync(roomname: str) -> None:
    """Release waiting players iff the room exists and is ready. Call this after
    every change to a room."""
    with Admin() as admin:
        room = admin.rooms.get(roomname)

    if room is not None and ready(room):
        e.set_room(roomname)
    else:
        e.clear_room(roomname)
