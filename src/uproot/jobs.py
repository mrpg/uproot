# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from typing import Any, Optional, cast

from fastapi import FastAPI, WebSocket

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.queues as q
import uproot.storage as s
from uproot.types import PlayerIdentifier, Sessionname, Username, Value, optional_call


async def from_queue(pid: PlayerIdentifier) -> tuple[str, q.EntryType]:
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


async def subscribe_to_room(roomname: str) -> bool:
    return cast(
        bool,
        await e.ROOMS[roomname].wait(),
    )


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
                            await optional_call(u.APPS[fmodule], fname, player=player)
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
    def is_player(key: tuple[str, str]) -> bool:
        namespace, field = key
        return namespace.startswith("player/")

    u.KEY = admin._uproot_key

    _minusone = Value(0.0, False, -1)
    _none = Value(0.0, False, None)

    ids, porders, pshows, all_watches = (
        s.field_from_all("id", is_player),
        s.field_from_all("page_order", is_player),
        s.field_from_all("show_page", is_player),
        s.field_from_all("_uproot_watch", is_player),
    )

    for (namespace, field), porder in porders.items():
        # Extract sname and uname from namespace path like "player/session_name/user_name"
        parts = namespace.split("/")
        if len(parts) >= 3 and parts[0] == "player":
            sname, uname = parts[1], parts[2]
            pid = PlayerIdentifier(sname, uname)

            # Look up other values using the same namespace and different fields
            id_ = cast(Optional[int], ids.get((namespace, "id"), _none).data)
            page_order = cast(list[str], porder.data)
            show_page = cast(int, pshows.get((namespace, "show_page"), _minusone).data)

            u.set_info(
                pid,
                id_,
                page_order,
                show_page,
            )

    for (namespace, field), watchset in all_watches.items():
        # Extract sname and uname from namespace path like "player/session_name/user_name"
        parts = namespace.split("/")
        if len(parts) >= 3 and parts[0] == "player":
            sname, uname = parts[1], parts[2]
            pid = PlayerIdentifier(sname, uname)

            if not watchset.unavailable:
                for watch in cast(set[tuple[float, str, str]], watchset.data):
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
            for pid in u.who_online(3.0, sname)
            if (among is None or pid in among)
            and cast(int, u.get_info(pid)[2]) == show_page
        }
    else:
        return {
            pid
            for pid in u.who_online(3.0, sname)
            if (among is None or pid in among)
            and cast(int, u.get_info(pid)[2]) >= show_page
        }


def try_group(sname: Sessionname, show_page: int, group_size: int) -> Optional[str]:
    """
    Try to create exactly one group from available players.

    Args:
        sname: Session name
        show_page: Page number where grouping should occur
        group_size: Required number of players per group

    Returns:
        Group name if a group was created, None otherwise
    """
    # Get all players on the same page (not checking group status yet)
    same_page = list(here(sname, show_page))

    # Not enough players available
    if len(same_page) < group_size:
        return None

    # Select first group_size players deterministically
    selected = same_page[:group_size]

    # Final verification that selected players are still valid and ungrouped
    valid_members = set()
    for pid in selected:
        try:
            player = pid()
            if (
                player._uproot_group is None
                and cast(int, u.get_info(pid)[2]) == show_page
            ):
                valid_members.add(pid)
        except Exception:
            continue

    # Still have enough valid players
    if len(valid_members) >= group_size:
        # Take exactly group_size members
        group_members = set(list(valid_members)[:group_size])

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
