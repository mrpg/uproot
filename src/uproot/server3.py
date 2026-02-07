# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements room routes.
"""

import asyncio
from typing import Any, Optional, cast
from urllib.parse import quote

import orjson
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.jobs as j
import uproot.rooms as ur
import uproot.types as t
from uproot.constraints import ensure, valid_token
from uproot.pages import path2page, render
from uproot.storage import Admin, Player, Session
from uproot.utils import safe_redirect

router = APIRouter(prefix=d.ROOT)


@router.post("/room/{roomname}/")
async def roommain(
    request: Request,
    roomname: str,
    label: Optional[str] = None,
    bad: Optional[bool] = False,
) -> Response:
    ensure(valid_token(roomname), ValueError, "Room name invalid")

    new_session = False

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
                        metadata={
                            "roomname": roomname,
                            "needlabel": True,
                            "bad": False,
                        },
                    ),
                )
            elif not ur.validate(room, label) and not bad:
                redirect_url = safe_redirect(
                    f"{d.ROOT}/room/{quote(roomname, safe='')}/?bad=1"
                )
                return RedirectResponse(redirect_url, status_code=303)
            elif bad:
                return HTMLResponse(
                    await render(
                        request.app,
                        request,
                        None,
                        path2page("RoomHello.html"),
                        metadata={"roomname": roomname, "needlabel": True, "bad": True},
                    ),
                )

        # Room not open - show waiting page

        if room["sname"] is None and (room["config"] is None or not room["open"]):
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomHello.html"),
                    metadata={"roomname": roomname, "needlabel": False},
                ),
            )

        # Room is ready - attempt to join

        capacity = 0

        if room["capacity"] is not None:
            capacity = room["capacity"]
        elif room["labels"] is not None:
            capacity = len(room["labels"])

        if room["sname"] is None:
            # TODO: move this elsewhere entirely
            sid = c.create_session(
                admin,
                room["config"],
                settings=u.CONFIGS_EXTRA.get(room["config"], {}).get("settings", {}),
            )
            room["sname"] = sid.sname
            c.finalize_session(sid)  # This seems fine?!
            new_session = True

    session = Session(room["sname"])

    if label != "":
        # Check existing players in this session for the same label
        with Session(room["sname"]) as session:
            for pid in session.players:
                with Player(pid.sname, pid.uname) as player:
                    if hasattr(player, "label") and player.label == label:
                        return RedirectResponse(
                            f"{d.ROOT}/p/{pid.sname}/{pid.uname}/", status_code=303
                        )

    # Try to add new player

    with session:
        if new_session:
            session.room = roomname

        free_slot = c.find_free_slot(session)

        if (
            ur.freejoin(room)
            or len(session.players) < capacity
            or free_slot is not None
        ):
            sname = room["sname"]

            if free_slot is not None:
                _, free_uname = free_slot

                # Redirect to player
                with Player(sname, free_uname) as player:
                    player.started = True
                    player.label = label

                redirect_to = f"{d.ROOT}/p/{sname}/{free_uname}/"
            else:
                pid = c.create_player(session)

                with t.materialize(pid) as player:
                    player.started = True
                    player.label = label

                redirect_to = f"{d.ROOT}/p/{sname}/{pid.uname}/"

            return RedirectResponse(redirect_to, status_code=303)
        else:
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomFull.html"),
                    metadata={"called_from": "room"},
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
        if not valid_token(roomname) or roomname not in admin.rooms:
            return

        room = admin.rooms[roomname]

    needs_label = room["labels"] is not None

    if label == "" and not needs_label:
        existing_labels = [pid.uname for pid in u.who_online(sname=f"^{roomname}")]
        local_context = t.token(existing_labels, str.upper)  # Implement fingerprinting?
    elif not needs_label or label in room["labels"]:
        # Eagerly accept label
        local_context = label
    else:
        raise HTTPException(status_code=401)

    await websocket.accept()

    pid = t.PlayerIdentifier(f"^{roomname}", local_context)
    tasks = {}
    args: dict[str, dict[str, Any]] = {
        "from_websocket": {
            "websocket": websocket,
        },
        "subscribe_to_room": {
            "roomname": roomname,
        },
        "timer": {
            "interval": 30.0,
        },
    }

    for jj in j.ROOM_JOBS:
        tasks[asyncio.create_task(cast(Any, jj)(**args[jj.__name__]))] = (
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
                result = await finished

                if fname == "from_websocket":
                    u.set_online(pid)

                    await websocket.send_bytes(
                        orjson.dumps(
                            {
                                "kind": "event",
                                "payload": {
                                    "event": "RoomLabelProvided",
                                    "detail": {
                                        "label": local_context,
                                    },
                                },
                            }
                        )
                    )

                    # Handle hello endpoint for heartbeat
                    if isinstance(result, dict) and result.get("endpoint") == "hello":
                        # Respond to hello to maintain heartbeat
                        await websocket.send_bytes(
                            orjson.dumps(
                                {
                                    "kind": "invoke",
                                    "payload": {
                                        "future": result.get("future"),
                                        "error": False,
                                        "data": None,
                                    },
                                }
                            )
                        )
                    # Otherwise ignore messages (for now)
                elif fname == "subscribe_to_room":
                    await websocket.send_bytes(
                        orjson.dumps(
                            {
                                "kind": "event",
                                "payload": {
                                    "event": "RoomStarted",
                                    "detail": {
                                        "label": local_context,
                                    },
                                },
                            }
                        )
                    )
                elif fname == "timer":
                    pass  # Placeholder for the future
                else:
                    raise NotImplementedError(fname)
            except WebSocketDisconnect:
                # Unlike the main ws, this really means the person went away
                u.set_offline(pid)

                for task in tasks:
                    task.cancel()

                await asyncio.gather(*tasks.keys(), return_exceptions=True)

                return
            except Exception as exc:
                raise exc

            # Re-add new instance of the same task (except one-shot tasks)
            if fname != "subscribe_to_room":
                new_task = asyncio.create_task(cast(Any, factory)(**args[fname]))
                tasks[new_task] = (fname, factory)
