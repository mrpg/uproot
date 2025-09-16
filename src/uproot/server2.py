# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements admin routes.
"""

# TODO: CSRF protection?

import asyncio
import builtins
import importlib.metadata
import os
import sys
from itertools import zip_longest
from random import shuffle
from time import perf_counter as now
from typing import Any, Optional, cast

import orjson
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined
from pydantic import validate_call
from sortedcontainers import SortedDict

import uproot as u
import uproot.admin as a
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.i18n as i18n
import uproot.jobs as j
import uproot.rooms as r
import uproot.types as t
from uproot.constraints import ensure
from uproot.pages import static_factory, to_filter
from uproot.storage import Admin, Session

# General settings


router = APIRouter(prefix=f"{d.ROOT}/admin")

LAST_FAILED_LOGIN = 0.0
LOGIN_URL = f"{d.ROOT}/admin/login/"
BUILTINS = {
    fname: getattr(builtins, fname)
    for fname in dir(builtins)
    if callable(getattr(builtins, fname))
}
ENV = Environment(
    loader=i18n.TranslateLoader(
        ChoiceLoader(
            [
                FileSystemLoader(
                    os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "default", "admin"
                    )
                ),
                FileSystemLoader(d.PATH),
            ]
        )
    ),
    autoescape=True,
    undefined=StrictUndefined,
    cache_size=250,
    auto_reload=True,
    enable_async=True,
)
ENV.filters["to"] = to_filter


async def render(
    ppath: str,
    context: Optional[dict[str, Any]] = None,
    context_nojson: Optional[dict[str, Any]] = None,
) -> str:
    if context is None:
        context = dict()

    if context_nojson is None:
        context_nojson = dict()

    context |= dict(
        language=d.LANGUAGE,
        root=d.ROOT,
    )

    intermediate_context = (
        context
        | BUILTINS
        | dict(
            internalstatic=static_factory(),
            _uproot_js=context,
            _uproot_internal=context,
            _uproot_errors=None,
            JSON_TERMS=i18n.json(d.LANGUAGE),
        )
    )

    return await ENV.get_template(ppath).render_async(
        **(intermediate_context | context_nojson)
    )


# Authentication


async def auth_required(request: Request) -> dict[str, Any]:
    uauth = request.cookies.get("uauth")
    if not uauth:
        raise HTTPException(status_code=303, headers={"Location": LOGIN_URL})

    data = a.from_cookie(uauth)

    if a.verify_auth_token(data.get("user", ""), data.get("token", "")) is None:
        raise HTTPException(status_code=303, headers={"Location": LOGIN_URL})

    return data


# Root directory


@router.get("/")
async def home(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return RedirectResponse(f"{d.ROOT}/admin/dashboard/", status_code=303)


# Websocket


@router.websocket("/ws/")
async def ws(websocket: WebSocket, uauth: Optional[str] = Cookie(None)) -> None:
    if uauth is None:
        raise HTTPException(status_code=403, detail="No authentication token")

    data = a.from_cookie(uauth)
    if a.verify_auth_token(data.get("user", ""), data.get("token", "")) is None:
        raise HTTPException(status_code=403, detail="Invalid authentication token")

    await websocket.accept()

    tasks = dict()
    args: dict[str, dict[str, Any]] = dict(
        from_websocket=dict(
            websocket=websocket,
        ),
        timer=dict(
            interval=30.0,
        ),
    )

    for jj in j.ADMIN_JOBS:
        fun = cast(Any, jj)

        tasks[asyncio.create_task(fun(**args[jj.__name__]))] = jj.__name__, jj

    while True:
        done, pending = await asyncio.wait(
            tasks.keys(), return_when=asyncio.FIRST_COMPLETED
        )

        for finished in done:
            fname, factory = tasks.pop(finished)

            try:
                result = await finished

                if fname == "from_websocket":
                    match result:
                        case {
                            "endpoint": "invoke",
                            "payload": {
                                "mname": "subscribe_to_attendance",
                                "args": [sname],
                            },
                        } if isinstance(sname, str):
                            newfname = "subscribe_to_attendance"
                            args[newfname] = dict(sname=sname)
                            tasks[
                                asyncio.create_task(
                                    j.subscribe_to_attendance(**args[newfname])
                                )
                            ] = (
                                newfname,
                                j.subscribe_to_attendance,
                            )
                        case {
                            "endpoint": "invoke",
                            "payload": {
                                "mname": mname,
                                "args": margs,
                                "kwargs": mkwargs,
                            },
                        } if (
                            isinstance(mname, str)
                            and isinstance(margs, list)
                            and isinstance(mkwargs, dict)
                            and mname in FUNS
                        ):
                            await websocket.send_bytes(
                                orjson.dumps(
                                    dict(
                                        kind="invoke",
                                        payload=dict(
                                            data=await cast(Any, FUNS[mname])(
                                                *margs,
                                                **mkwargs,
                                            ),
                                            future=result["future"],
                                        ),
                                    )
                                )
                            )
                        case _:
                            pass
                            # ~ raise NotImplementedError(result)
                elif fname == "subscribe_to_attendance":
                    pid = t.PlayerIdentifier(args[fname]["sname"], result)

                    with pid() as p:
                        info = (
                            p.id,
                            p.page_order,
                            p.show_page,
                        )  # TODO: Remove monkeypatch

                    await websocket.send_bytes(
                        orjson.dumps(
                            dict(
                                kind="event",
                                payload=dict(
                                    event="Attended",
                                    detail=dict(
                                        uname=pid.uname,
                                        info=info,
                                        online=u.find_online(pid),
                                    ),
                                ),
                            )
                        )
                    )
                elif fname == "timer":
                    pass  # placeholder for the future
                else:
                    raise NotImplementedError(fname)
            except WebSocketDisconnect:
                for task in tasks:
                    task.cancel()

                await asyncio.gather(*tasks.keys(), return_exceptions=True)

                return None

            # Re-add new instance of the same task
            new_task = asyncio.create_task(cast(Any, factory)(**args[fname]))
            tasks[new_task] = (fname, factory)


# Login page


@router.get("/login/")
async def login_get(
    request: Request,
    bad: Optional[bool] = False,
) -> HTMLResponse:
    response = HTMLResponse(await render("Login.html", dict(bad=bad)))

    if bad:
        response.status_code = 401

    return response


@router.post("/login/")
async def login_post(
    request: Request,
    user: str = Form(),
    pw: str = Form(),
    host: str = Header(""),
    x_forwarded_proto: str = Header(""),
) -> Response:
    global LAST_FAILED_LOGIN

    # Rate limiting: require 5 second delay after failed login
    if now() - LAST_FAILED_LOGIN <= 5.0:
        d.LOGGER.debug("POSTed too quickly")
        LAST_FAILED_LOGIN = now()
        return RedirectResponse(f"{d.ROOT}/admin/login/?bad=1", status_code=303)

    # Attempt to create authentication token
    token = a.create_auth_token(user, pw)
    if token is not None:
        response = RedirectResponse(f"{d.ROOT}/admin/dashboard/", status_code=303)
        set_auth_cookie(
            response,
            token,
            x_forwarded_proto.lower() == "https"
            or not (
                host.startswith("localhost") or host.startswith("127.0.0.")
            ),  # Safari really sucks
        )
        return response

    LAST_FAILED_LOGIN = now()
    return RedirectResponse(f"{d.ROOT}/admin/login/?bad=1", status_code=303)


# Logout page


@router.get("/logout/")
def logout(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> RedirectResponse:
    """Logout and revoke the current authentication token."""
    uauth = request.cookies.get("uauth")
    if uauth:
        # Revoke the specific token
        a.revoke_auth_token(uauth)

    response = RedirectResponse(f"{d.ROOT}/admin/login/")
    response.delete_cookie("uauth", path=f"{d.ROOT}/")

    return response


@validate_call(config=dict(arbitrary_types_allowed=True))
def set_auth_cookie(
    response: Response,
    token: str,
    secure: bool,
) -> None:
    """Set authentication cookie with secure token."""
    response.set_cookie(
        key="uauth",
        value=token,
        max_age=86400,  # 24 hours
        path=f"{d.ROOT}/",
        httponly=True,
        secure=secure,
        samesite="strict",
    )


# Dashboard


@router.get("/dashboard/")
async def dashboard(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "Dashboard.html",
            dict(
                configs=a.configs(),
                rooms=a.rooms(),
                sessions=a.sessions(),
            ),
        )
    )


# Rooms

# Overview of all rooms


@router.get("/rooms/")
async def rooms(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "Rooms.html",
            dict(
                rooms=a.rooms(),
                sessions=a.sessions(),
            ),
        )
    )


# New room


@router.get("/rooms/new/")
async def new_room(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    with Admin() as admin:
        return HTMLResponse(
            await render(
                "RoomsNew.html",
                dict(
                    configs=a.configs(),
                    rooms_available=[*admin.rooms.keys()],
                    sessions_available=admin.sessions,
                ),
            )
        )


@router.post("/rooms/new/")
async def new_room2(
    request: Request,
    name: str = Form(),
    use_config: Optional[bool] = Form(False),
    config: Optional[str] = Form(""),
    use_labels: Optional[bool] = Form(False),
    labels: Optional[str] = Form(""),
    use_capacity: Optional[bool] = Form(False),
    capacity: Optional[int] = Form(1),
    use_session: Optional[bool] = Form(False),
    sname: Optional[str] = Form(""),
    start: Optional[bool] = Form(False),
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    if sname:
        a.session_exists(sname)

    with Admin() as admin:
        if name in admin.rooms:
            raise HTTPException(status_code=400, detail="Room name already exists")

        admin.rooms[name] = r.room(
            name=name,
            config=(config if use_config else None),
            labels=(
                [a.strip() for a in labels.split("\n") if a.strip()]
                if labels
                else [] if use_labels else None
            ),
            capacity=(capacity if use_capacity else None),
            start=bool(start),
            sname=(sname if use_session and sname and sname.strip() else None),
        )

    if sname:
        with Session(sname) as session:
            session.room = name

    return RedirectResponse(f"{d.ROOT}/admin/room/{name}/", status_code=303)


# Particular room


@router.get("/room/{roomname}/")
async def roommain(
    request: Request,
    roomname: str,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    with Admin() as admin:
        ensure(roomname in admin.rooms, ValueError, "Room not found")

        return HTMLResponse(
            await render(
                "Room.html",
                dict(
                    roomname=roomname,
                    room=admin.rooms[roomname],
                    configs=a.configs(),
                )
                | a.info_online(f"^{roomname}"),
            )
        )


@router.post("/room/{roomname}/")
async def new_session_in_room(
    request: Request,
    roomname: str,
    config: str = Form(),
    assignees: str = Form(),
    nplayers: int = Form(),
    automatic_sname: Optional[bool] = Form(False),
    automatic_unames: Optional[bool] = Form(False),
    sname: Optional[str] = Form(""),
    unames: Optional[str] = Form(""),
    nogrow: Optional[bool] = Form(False),
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.room_exists(roomname)

    if assignees:
        assignees_list = orjson.loads(assignees)
        ensure(
            all(isinstance(ass, str) for ass in assignees_list),
            ValueError,
            "All assignees must be strings",
        )
        shuffle(assignees_list)
    else:
        assignees_list = []

    data: list[Any] = []
    nplayers = max(nplayers, len(assignees_list))

    for _, label in zip_longest(range(nplayers), assignees_list):
        if label is None:
            data.append({})
        else:
            data.append({"label": label})

    with Admin() as admin:
        ensure(
            admin.rooms[roomname]["sname"] is None,
            RuntimeError,
            "Room already has an active session",
        )

        sid = c.create_session(
            admin,
            config,
            sname=(None if automatic_sname else sname),
        )

        admin.rooms[roomname]["sname"] = sid.sname
        admin.rooms[roomname]["start"] = True

        if nogrow:
            admin.rooms[roomname]["capacity"] = nplayers

    with sid() as session:
        session.room = roomname

        c.create_players(
            session,
            n=nplayers,
            unames=(
                None
                if automatic_unames or unames is None
                else [a.strip() for a in unames.split("\n")]
            ),
            data=data,
        )

    c.finalize_session(sid)

    e.set_room(roomname)

    return RedirectResponse(f"{d.ROOT}/admin/session/{sid.sname}/", status_code=303)


# Sessions


# Overview of all sessions


@router.get("/sessions/")
async def sessions(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "Sessions.html",
            dict(
                sessions=a.sessions(),
            ),
        )
    )


# New session


@router.get("/sessions/new/")
async def new_session(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return HTMLResponse(await render("SessionsNew.html", dict(configs=a.configs())))


@router.post("/sessions/new/")
async def new_session2(
    request: Request,
    config: str = Form(),
    nplayers: int = Form(),
    automatic_sname: Optional[bool] = Form(False),
    automatic_unames: Optional[bool] = Form(False),
    sname: Optional[str] = Form(""),
    unames: Optional[str] = Form(""),
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    with Admin() as admin:
        sid = c.create_session(
            admin,
            config,
            sname=(None if automatic_sname else sname),
        )

    with sid() as session:
        c.create_players(
            session,
            n=nplayers,
            unames=(
                None
                if automatic_unames or unames is None
                else [a.strip() for a in unames.split("\n")]
            ),
        )

    c.finalize_session(sid)

    return RedirectResponse(f"{d.ROOT}/admin/session/{sid.sname}/", status_code=303)


# Particular session


@router.get("/session/{sname}/")
async def sessionmain(
    request: Request,
    sname: t.Sessionname,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.session_exists(sname)

    with Session(sname) as session:
        # TODO: Eliminate use of session.get()

        return HTMLResponse(
            await render(
                "Session.html",
                dict(
                    sname=sname,
                    description=session.get("description"),
                    room=session.get("room"),
                    secret=session.get("_uproot_secret"),
                    active=session.active,
                )
                | a.info_online(sname),
            )
        )


# Particular session: data
@router.get("/session/{sname}/data/")
async def session_data(
    request: Request,
    sname: t.Sessionname,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.session_exists(sname)
    return HTMLResponse(await render("SessionData.html", dict(sname=sname)))


# Particular session: get data
@router.get("/session/{sname}/data/get/")
async def session_data_download(
    request: Request,
    sname: t.Sessionname,
    format: str,
    filetype: str,
    gvar: list[str] = Query(default=[]),
    filters: bool = Query(default=False),
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.session_exists(sname)

    if filetype == "csv":
        t0 = now()
        csv = a.generate_csv(sname, format, gvar, filters)
        t1 = now()

        if t1 - t0 > 0.1:
            d.LOGGER.warning(f"generate_csv('{sname}', ...) took {(t1-t0):3f} seconds")

        return Response(
            csv,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={sname}.csv"},
        )
    elif filetype == "json":
        return StreamingResponse(
            a.generate_json(sname, format, gvar, filters),
            media_type="text/json",
            headers={"Content-Disposition": f"attachment; filename={sname}.json"},
        )
    else:
        raise NotImplementedError


# Particular session: view data
@router.get("/session/{sname}/viewdata/")
async def session_viewdata(
    request: Request,
    sname: t.Sessionname,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.session_exists(sname)
    return HTMLResponse(await render("SessionViewdata.html", dict(sname=sname)))


# Particular session: view multiple players’ screens
@router.get("/session/{sname}/multiview/")
async def session_multiview(
    request: Request,
    sname: t.Sessionname,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    a.session_exists(sname)

    return HTMLResponse(
        await render("SessionMultiview.html", dict(sname=sname) | a.info_online(sname))
    )


# Server status


@router.get("/status/")
async def status(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    dbsize_bytes = d.DATABASE.size()
    missing: dict[str, Any] = dict()

    dbsize = None
    if dbsize_bytes is not None:
        dbsize = float(dbsize_bytes) / (1024**2)

    for term, lang in sorted(i18n.MISSING):
        if term not in missing:
            missing[term] = list()
        missing[term].append(lang)

    sessions = a.get_active_sessions()

    return HTMLResponse(
        await render(
            "Status.html",
            dict(
                dbsize=dbsize,
                missing=missing,
                sessions=sessions,
                versions=dict(
                    uproot=u.__version__,
                    python=sys.version,
                ),
            ),
            dict(
                deployment=d,
                packages=SortedDict(
                    {
                        dist.metadata["name"]: dist.version
                        for dist in importlib.metadata.distributions()
                    }
                ).items(),
            ),
        )
    )


@router.get("/status/logout-all/")
async def logout_all(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    """Logout from all sessions by revoking all tokens for the current user."""
    uauth = request.cookies.get("uauth")
    if uauth:
        data = a.from_cookie(uauth)
        user = data.get("user", "")
        if user:
            revoked_count = a.revoke_all_user_tokens(user)
            d.LOGGER.info(f"Revoked {revoked_count} tokens for user {user}")

    response = RedirectResponse(f"{d.ROOT}/admin/login/", status_code=303)
    response.delete_cookie("uauth", path=f"{d.ROOT}/")

    return response


# Database dump


@router.get("/dump/")
async def dump(
    request: Request,
    auth: dict[str, Any] = Depends(auth_required),
) -> Response:
    return StreamingResponse(
        d.DATABASE.dump(),
        media_type="application/msgpack",
        headers={"Content-Disposition": "attachment; filename=uproot.msgpack"},
    )


# Functions


FUNS = dict(
    adminmessage=a.adminmessage,
    advance_by_one=a.advance_by_one,
    announcements=a.announcements,
    disassociate=a.disassociate,
    flip_active=a.flip_active,
    insert_fields=a.insert_fields,
    mark_dropout=a.mark_dropout,
    put_to_end=a.put_to_end,
    reload=a.reload,
    revert_by_one=a.revert_by_one,
    viewdata=a.viewdata,
)
