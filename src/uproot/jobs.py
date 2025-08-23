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

BACKGROUND_TASKS: dict[Any, asyncio.Task] = dict()


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
    def is_player(dbfield: str) -> bool:
        return dbfield.startswith("player/")

    u.KEY = admin._uproot_key

    _minusone = Value(0.0, False, -1)
    _none = Value(0.0, False, None)

    ids, porders, pshows, all_watches = (
        s.field_from_all("id", is_player),
        s.field_from_all("page_order", is_player),
        s.field_from_all("show_page", is_player),
        s.field_from_all("_uproot_watch", is_player),
    )

    for dbfield, porder in porders.items():
        _, sname, uname, _ = s.mktrail(dbfield)
        pid = PlayerIdentifier(sname, uname)

        id_ = cast(Optional[int], ids.get(f"player/{sname}/{uname}:id", _none).data)
        page_order = cast(list[str], porder.data)
        show_page = cast(
            int, pshows.get(f"player/{sname}/{uname}:show_page", _minusone).data
        )

        u.set_info(
            pid,
            id_,
            page_order,
            show_page,
        )

    for dbfield, watchset in all_watches.items():
        _, sname, uname, _ = s.mktrail(dbfield)
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


async def mkgroup(sname: Sessionname, show_page: int, group_size: int) -> None:
    while True:
        same_page = [
            pid for pid in here(sname, show_page) if pid()._uproot_group is None
        ]

        if len(same_page) == 0:
            return

        while len(same_page) >= group_size:
            group_members = {same_page.pop() for _ in range(group_size)}

            with s.Session(sname) as session:
                gid = c.create_group(session, group_members)

            for pid in group_members:
                await q.enqueue(
                    tuple(pid),
                    dict(
                        source="mkgroup",
                        gname=gid.gname,
                    ),
                )

            return

        try:
            await asyncio.wait_for(e.ATTENDANCE[sname].wait(), timeout=3.0)
        except asyncio.TimeoutError:
            pass


async def grouping_watcher(app: "FastAPI") -> None:
    def handle_task_done(task: asyncio.Task, key: Any) -> None:
        BACKGROUND_TASKS.pop(key, None)
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            d.LOGGER.error(f"Background task {key} failed: {e}", exc_info=True)

    while True:
        _, msg = await q.read(("admin", "grouping_watcher"))

        match msg:
            case {
                "sname": Sessionname(sname),
                "show_page": int(show_page),
                "group_size": int(group_size),
            }:
                tpl = sname, show_page, group_size

                if tpl not in BACKGROUND_TASKS:
                    task = asyncio.create_task(mkgroup(*tpl))
                    BACKGROUND_TASKS[tpl] = task
                    task.add_done_callback(
                        lambda t, key=tpl: handle_task_done(t, key),  # type: ignore[misc]
                    )
            case _:
                d.LOGGER.warning(f"Invalid grouping_watcher message: {msg}")


GLOBAL_JOBS = [
    dropout_watcher,
    grouping_watcher,
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
