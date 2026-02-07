# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from typing import Any, Optional, cast
from uuid import UUID

from fastapi import FastAPI, WebSocket

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.queues as q
import uproot.storage as s
from uproot.types import (
    PlayerIdentifier,
    Sessionname,
    Username,
    Value,
    ensure_awaitable,
    identify,
    optional_call,
)


async def from_queue(pid: PlayerIdentifier) -> tuple[UUID, q.EntryType]:
    return await q.read(tuple(pid))  # convention: queue path = (sname, uname)


async def from_websocket(websocket: WebSocket) -> dict[str, Any]:
    return cast(dict[str, Any], await websocket.receive_json())


async def subscribe_to_attendance(
    sname: Sessionname,
) -> Username:
    return cast(
        Username,
        await e.ATTENDANCE[sname].wait(),
    )


async def subscribe_to_fieldchange(
    sname: Sessionname,
    fields: Optional[list[str]] = None,
) -> tuple[tuple[str, ...], str, Value]:
    while True:
        received = await e.FIELDCHANGE[sname].wait()

        if fields is None or received[1] in fields:
            return cast(tuple[tuple[str, ...], str, Value], received)


async def subscribe_to_room(roomname: str) -> bool:
    await e.ROOMS[roomname].wait()
    return True


async def timer(interval: float) -> None:
    await asyncio.sleep(interval)


async def dropout_watcher(app: FastAPI, interval: float = 3.0) -> None:
    removals = set()

    while True:
        for entry in u.WATCH:
            pid, tolerance, fmodule, fname = entry

            triplet = tolerance, fmodule, fname
            last = u.find_online_delta(pid)

            if pid not in u.MANUAL_DROPOUTS and (last is None or last <= tolerance):
                # player is online or assumed to be
                pass
            else:
                u.set_offline(pid)

                with pid() as player:
                    player._uproot_dropout = True

                    if player.show_page != len(player.page_order):
                        try:
                            await ensure_awaitable(
                                optional_call, u.APPS[fmodule], fname, player=player
                            )
                        except Exception as e:
                            d.LOGGER.error(
                                f"Exception in dropout handler {fmodule}.{fname}: {e}"
                            )
                        else:
                            player._uproot_watch.remove(triplet)

                removals.add(entry)

        if removals:
            for entry in removals:
                u.WATCH.discard(entry)

            removals.clear()
            u.MANUAL_DROPOUTS.clear()

        await asyncio.sleep(interval)


def synchronize_rooms(app: FastAPI, admin: s.Storage) -> None:
    if not hasattr(admin, "rooms"):
        admin.rooms = dict()

    for room in d.DEFAULT_ROOMS:
        if room["name"] not in admin.rooms:
            admin.rooms[room["name"]] = room


def restore(app: FastAPI, admin: s.Storage) -> None:
    u.KEY = admin._uproot_key

    for sname in admin.sessions:
        with s.Session(sname) as session:
            for pid in session.players:
                with s.Player(pid.sname, pid.uname) as player:
                    # Handle watches
                    watches = getattr(player, "_uproot_watch", None)
                    if watches is not None:
                        for watch in cast(set[tuple[float, str, str]], watches):
                            u.WATCH.add((pid, *watch))


def here(
    sname: Sessionname,
    show_page: int,
    among: Optional[list[PlayerIdentifier]] = None,
    strict: bool = True,
) -> set[PlayerIdentifier]:
    if strict:
        return {
            pid
            for pid in u.who_online(d.HERE_TOLERANCE, sname)
            if (among is None or pid in among) and pid().show_page == show_page
        }
    else:
        # TODO: Technically speaking, if strict is False, others need not be online.

        return {
            pid
            for pid in u.who_online(d.HERE_TOLERANCE, sname)
            if (among is None or pid in among) and pid().show_page >= show_page
        }


def try_group(player: s.Storage, show_page: int, group_size: int) -> Optional[str]:
    """
    Try to create exactly one group from available players.

    Args:
        player: Caller
        show_page: Page number where grouping should occur
        group_size: Required number of players per group

    Returns:
        Group name if a group was created, None otherwise
    """
    # Get all players on the same page (not checking group status yet)
    sname = player._uproot_session
    same_page = here(sname, show_page)

    # Not enough players available
    if len(same_page) < group_size:
        return None

    # Verification that players are still valid and ungrouped
    valid_members = list()
    for pid in same_page:
        add_to_valid = False

        if pid == identify(player):
            add_to_valid = player._uproot_group is None
        else:
            add_to_valid = pid()._uproot_group is None

        if add_to_valid:
            valid_members.append(pid)

    # Still have enough valid players
    if len(valid_members) >= group_size:
        # Take exactly group_size members
        group_members = valid_members[:group_size]

        # Create the group
        with s.Session(sname) as session:
            gid = c.create_group(session, group_members)

        return gid.gname

    return None


GLOBAL_JOBS = [
    dropout_watcher,
]


ADMIN_JOBS = [
    from_websocket,
    timer,
]

PLAYER_JOBS = [
    from_queue,
    from_websocket,
    timer,
]

ROOM_JOBS = [
    subscribe_to_room,
    from_websocket,
    timer,
]
