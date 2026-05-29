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
from uproot.constraints import ensure
from uproot.types import (
    PlayerIdentifier,
    Sessionname,
    Username,
    Value,
    ensure_awaitable,
    materialize,
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


async def subscribe_to_adminchat(
    sname: Sessionname,
) -> dict[str, Any]:
    return cast(dict[str, Any], await e.ADMINCHAT[sname].wait())


async def subscribe_to_room(roomname: str) -> bool:
    await e.ROOMS[roomname].wait()
    return True


async def timer(interval: float) -> None:
    await asyncio.sleep(interval)


async def dropout_watcher(app: FastAPI, interval: float = 3.0) -> None:
    removals = set()

    while True:
        for entry in u.WATCH:
            try:
                pid, tolerance, fmodule, fname = entry

                triplet = [tolerance, fmodule, fname]
                last = u.find_online_delta(pid)

                if pid not in u.MANUAL_DROPOUTS and (last is None or last <= tolerance):
                    # player is online or assumed to be
                    pass
                else:
                    u.set_offline(pid)

                    with materialize(pid) as player:
                        player._uproot_dropout = True

                        if player.show_page != len(player.page_order):
                            try:
                                await ensure_awaitable(
                                    optional_call,
                                    u.APPS[fmodule],
                                    fname,
                                    player=player,
                                )
                            except Exception:
                                d.LOGGER.exception(
                                    f"Exception in dropout handler {fmodule}.{fname}"
                                )
                            else:
                                if triplet in player._uproot_watch:
                                    player._uproot_watch.remove(triplet)

                    removals.add(entry)
            except Exception:
                d.LOGGER.exception(f"Exception in dropout watcher for entry {entry}")

        if removals:
            for entry in removals:
                u.WATCH.discard(entry)

            removals.clear()
            u.MANUAL_DROPOUTS.clear()

        await asyncio.sleep(interval)


def synchronize_rooms(app: FastAPI, admin: s.Storage) -> None:
    if not hasattr(admin, "rooms"):
        admin.rooms = {}

    for room in d.DEFAULT_ROOMS:
        if room["name"] not in admin.rooms:
            admin.rooms[room["name"]] = room


def restore(app: FastAPI, admin: s.Storage) -> None:
    u.KEY = admin._uproot_key

    for sname in admin._uproot_sessions:
        with s.Session(sname) as session:
            for pid in session._uproot_players:
                with s.Player(pid.sname, pid.uname) as player:
                    # Handle watches
                    watches = getattr(player, "_uproot_watch", None)
                    if watches is not None:
                        for watch in cast(list[list[Any]], watches):
                            u.WATCH.add((pid, *watch))

            for mname in session._uproot_models:
                with s.Model(sname, mname) as model_:
                    hooks = getattr(model_, "_uproot_on_message", None)

                    if hooks is not None:
                        for hook in cast(list[list[str]], hooks):
                            key = (sname, mname)
                            entries = u.CHAT_HOOKS.setdefault(key, [])
                            pair = (hook[0], hook[1])

                            if pair not in entries:
                                entries.append(pair)


def here(
    sname: Sessionname,
    show_page: int,
    among: Optional[list[PlayerIdentifier]] = None,
    strict: bool = True,
) -> set[PlayerIdentifier]:
    with s.Session(sname) as session:
        all_players: list[PlayerIdentifier] = session._uproot_players

    if strict:
        return {
            pid
            for pid in all_players
            if (among is None or pid in among)
            and materialize(pid).show_page == show_page
        }
    else:
        return {
            pid
            for pid in all_players
            if (among is None or pid in among)
            and materialize(pid).show_page >= show_page
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
    sname = player._uproot_session
    ensure(group_size > 0, ValueError, "Group size must be positive")

    with s.Session(sname) as session:
        same_page = [
            pid
            for pid in session._uproot_players
            if materialize(pid).show_page == show_page
        ]

        if len(same_page) < group_size:
            return None

        valid_members = []
        for pid in same_page:
            if materialize(pid)._uproot_group is None:
                valid_members.append(pid)

        if len(valid_members) >= group_size:
            group_members = valid_members[:group_size]
            gid = c.create_group(session, group_members, expected_size=group_size)
            player.refresh("_uproot_group")

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
