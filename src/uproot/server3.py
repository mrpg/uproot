# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements room routes.
"""

import asyncio
from typing import Any, Callable, Optional, cast

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.jobs as j
import uproot.rooms as ur
import uproot.types as t
from uproot.pages import path2page, render
from uproot.storage import Admin, Session, field_from_all, mktrail

router = APIRouter(prefix=d.ROOT)


@router.post("/room/{roomname}/")
async def roommain(
    request: Request,
    roomname: str,
    label: Optional[str] = None,
    bad: Optional[bool] = False,
) -> Response:
    assert roomname.isidentifier()

    with Admin() as admin:
        label = ur.constrain_label(label)

        if roomname not in admin.rooms:
            raise HTTPException(status_code=404)

        room = admin.rooms[roomname]
        needs_label = room["labels"] is not None

        # Handle label entry for rooms that require labels

        if needs_label:
            if label == "" and not bad:
                return HTMLResponse(
                    await render(
                        request.app,
                        request,
                        None,
                        path2page("RoomHello.html"),
                        metadata=dict(roomname=roomname, needlabel=True, bad=False),
                    ),
                )
            elif not ur.validate(room, label) and not bad:
                return RedirectResponse(
                    f"{d.ROOT}/room/{roomname}/?bad=1", status_code=303
                )
            elif bad:
                return HTMLResponse(
                    await render(
                        request.app,
                        request,
                        None,
                        path2page("RoomHello.html"),
                        metadata=dict(roomname=roomname, needlabel=True, bad=True),
                    ),
                )

        # Room not open - show waiting page

        if room["sname"] is None and (room["config"] is None or not room["start"]):
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomHello.html"),
                    metadata=dict(roomname=roomname, needlabel=False),
                ),
            )

        # Room is ready - attempt to join

        capacity = 0

        if room["labels"] is not None:
            capacity = len(room["labels"])
        elif room["capacity"] is not None:
            capacity = room["capacity"]

        if room["sname"] is None:
            room["sname"] = c.create_session(
                admin, room["config"]
            )  # TODO: remove side effect

    session = Session(room["sname"])

    # Check for existing player with same label

    def heresession(dbfield: str) -> bool:
        t1, t2, _, _ = mktrail(dbfield)

        return t1 == "player" and t2 == room["sname"]

    if label != "":
        for dbfield, labelvalue in field_from_all("label", heresession).items():
            _, sname, uname, _ = mktrail(dbfield)

            if labelvalue.data == label:
                return RedirectResponse(f"{d.ROOT}/p/{sname}/{uname}/", status_code=303)

    # Try to add new player

    with session:
        if ur.freejoin(room) or len(session.players) < capacity:
            with session:
                pid = c.create_player(session)

            player = pid()
            player.label = label

            return RedirectResponse(
                f"{d.ROOT}/p/{pid.sname}/{pid.uname}/", status_code=303
            )
        else:
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomFull.html"),
                    metadata=dict(called_from="room"),
                ),
                status_code=423,
            )


@router.websocket("/roomws/{roomname}/")
async def ws(
    websocket: WebSocket,
    roomname: str,
    label: str = "",
) -> None:
    label = ur.constrain_label(label)

    with Admin() as admin:
        if not (roomname.isidentifier() and roomname in admin.rooms):
            return

        room = admin.rooms[roomname]

    needs_label = room["labels"] is not None

    if label == "" and not needs_label:
        local_context = "#" + t.token_unchecked(6).upper()  # Implement fingerprinting?
    elif not needs_label or label in room["labels"]:
        # Eagerly accept label
        local_context = label
    else:
        raise HTTPException(status_code=401)

    await websocket.accept()

    pid = t.PlayerIdentifier(f"^{roomname}", local_context)
    tasks = dict()
    args: dict[str, dict[str, Any]] = dict(
        from_websocket=dict(
            websocket=websocket,
        ),
        subscribe_to_room=dict(
            roomname=roomname,
        ),
        timer=dict(
            interval=30.0,
        ),
    )

    for jj in j.ROOM_JOBS:
        tasks[asyncio.create_task(cast(Callable, jj)(**args[jj.__name__]))] = (
            jj.__name__,
            jj,
        )

    while True:
        done, pending = await asyncio.wait(
            tasks.keys(), return_when=asyncio.FIRST_COMPLETED
        )

        for finished in done:
            fname, factory = tasks.pop(finished)

            try:
                _ = await finished

                if fname == "from_websocket":
                    u.set_online(pid)
                    e.set_attendance(pid)
                    # Otherwise ignore messages (for now)
                elif fname == "subscribe_to_room":
                    await websocket.send_json(
                        dict(
                            kind="action",
                            payload=dict(
                                action="reload",
                            ),
                        )
                    )
                elif fname == "timer":
                    pass  # Placeholder for the future
                else:
                    raise NotImplementedError(fname)
            except WebSocketDisconnect:
                # Unlike the main ws, this really means the person went away
                u.set_offline(pid)
                e.set_attendance(pid)

                for task in tasks:
                    task.cancel()

                await asyncio.gather(*tasks.keys(), return_exceptions=True)

                return
            except Exception as exc:
                raise exc

            # Re-add new instance of the same task
            new_task = asyncio.create_task(cast(Callable, factory)(**args[fname]))
            tasks[new_task] = (fname, factory)
