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
from typing import Any, Callable, Optional, cast

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
    JSONResponse,
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
from uproot.pages import static_factory
from uproot.storage import Admin, Session

router = APIRouter(prefix=f"{d.ROOT}/admin")

LAST_FAILED_LOGIN = 0
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


async def auth_required(request: Request):
    uauth = request.cookies.get("uauth")
    if not uauth:
        raise HTTPException(status_code=303, headers={"Location": LOGIN_URL})

    data = a.from_cookie(uauth)

    if a.verify_secret(**data) is None:
        raise HTTPException(status_code=303, headers={"Location": LOGIN_URL})


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
            internal_static=static_factory(),
            _uproot_js=context,
            _uproot_internal=context,
            _uproot_errors=None,
            JSON_TERMS=i18n.json(d.LANGUAGE),
        )
    )

    return await ENV.get_template(ppath).render_async(
        **(intermediate_context | context_nojson)
    )


@router.get("/logout/")
def logout(
    auth=Depends(auth_required),
) -> RedirectResponse:
    response = RedirectResponse(f"{d.ROOT}/admin/login/")
    response.delete_cookie("uauth")

    return response


@validate_call(config=dict(arbitrary_types_allowed=True))
def set_cookie(
    response: Response,
    user: str,
    secret: str,
    secure: bool,
) -> None:
    assert ":" not in secret

    response.set_cookie(
        key="uauth",
        value=f"{user}:{secret}",
        max_age=86400,
        path=f"{d.ROOT}/",
        httponly=True,
        secure=secure,
        samesite="strict",
    )


@router.get("/dashboard/")
async def dashboard(
    request: Request,
    auth=Depends(auth_required),
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


@router.get("/sessions/")
async def sessions(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "AllSessions.html",
            dict(
                sessions=a.sessions(),
            ),
        )
    )


@router.get("/rooms/")
async def sessions(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "WaitingRooms.html",
            dict(
                rooms=a.rooms(),
                sessions=a.sessions(),
            ),
        )
    )


@router.get("/status/")
async def status(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return HTMLResponse(
        await render(
            "ServerStatus.html",
            dict(
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


@router.get("/dump/")
async def dump(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return StreamingResponse(
        d.DATABASE.dump(),
        media_type="application/msgpack",
        headers={"Content-Disposition": "attachment; filename=uproot.msgpack"},
    )


@router.get("/devinfo/")
async def devinfo(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    # to be extended

    return JSONResponse(
        dict(
            missing_terms=list(i18n.MISSING),
        )
    )


@router.get("/session/{sname}/data/")
async def session_data(
    request: Request,
    sname: t.Sessionname,
    format: str,
    gvar: list[str] = Query(default=[]),
    filetype: str = "csv",
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)

    if filetype == "csv":
        t0 = now()
        csv = a.generate_csv(sname, format, gvar)
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
            a.generate_json(sname, format, gvar),
            media_type="text/json",
            headers={"Content-Disposition": f"attachment; filename={sname}.json"},
        )
    else:
        raise NotImplementedError


@router.get("/new_session/")
async def new_session(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return HTMLResponse(await render("NewSession.html", dict(configs=a.configs())))


@router.get("/new_room/")
async def new_room(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    with Admin() as admin:
        return HTMLResponse(
            await render(
                "NewRoom.html",
                dict(
                    configs=a.configs(),
                    rooms_available=[*admin.rooms.keys()],
                    sessions_available=admin.sessions,
                ),
            )
        )


@router.post("/new_room/")
async def new_room(
    request: Request,
    name: str = Form(),
    use_config: Optional[bool] = Form(False),
    config: Optional[str] = Form(""),
    use_labels: Optional[bool] = Form(False),
    labels: Optional[str] = Form(""),
    use_size: Optional[bool] = Form(False),
    size: Optional[int] = Form(1),
    use_session: Optional[bool] = Form(False),
    sname: Optional[str] = Form(""),
    start: Optional[bool] = Form(False),
    auth=Depends(auth_required),
) -> Response:
    with Admin() as admin:
        if name in admin.rooms:
            raise HTTPException(status_code=400, detail="Room name already exists")

        admin.rooms[name] = r.room(
            name=name,
            config=(config if use_config else None),
            labels=(
                [a.strip() for a in labels.split("\n") if a.strip()]
                if use_labels
                else None
            ),
            size=(size if use_size else None),
            start=bool(start),
            sname=(sname if use_session and sname.strip() else None),
        )

    return RedirectResponse(f"{d.ROOT}/admin/rooms/", status_code=303)


@router.post("/new_session/")
async def new_session(
    request: Request,
    config: str = Form(),
    nplayers: int = Form(),
    automatic_sname: Optional[bool] = Form(False),
    automatic_unames: Optional[bool] = Form(False),
    sname: Optional[str] = Form(""),
    unames: Optional[str] = Form(""),
    auth=Depends(auth_required),
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
                None if automatic_unames else [a.strip() for a in unames.split("\n")]
            ),
        )

    return RedirectResponse(f"{d.ROOT}/admin/session/{sid.sname}/", status_code=303)


def session_exists(sname: t.Sessionname) -> None:
    with Admin() as admin:
        if sname not in admin.sessions:
            raise HTTPException(status_code=400, detail="Invalid session")


@router.get("/session/{sname}/monitor/")
async def session_monitor(
    request: Request,
    sname: t.Sessionname,
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)

    return HTMLResponse(
        await render("Monitor.html", dict(sname=sname) | a.info_online(sname))
    )


@router.get("/room/{roomname}/")
async def roommain(
    request: Request,
    roomname: str,
    auth=Depends(auth_required),
) -> Response:
    with Admin() as admin:
        assert roomname in admin.rooms

        return HTMLResponse(
            await render(
                "RoomMain.html",
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
    auth=Depends(auth_required),
) -> Response:
    assignees = assignees.split("|")
    assert all(ass.lstrip("#").isidentifier() for ass in assignees)
    shuffle(assignees)

    data = []

    for _, label in zip_longest(range(nplayers), assignees):
        if label is None:
            data.append({})
        else:
            data.append({"label": label})

    with Admin() as admin:
        assert roomname in admin.rooms and admin.rooms[roomname]["sname"] is None

        sid = c.create_session(
            admin,
            config,
            sname=(None if automatic_sname else sname),
        )

        admin.rooms[roomname]["sname"] = sid.sname
        admin.rooms[roomname]["start"] = True

    with sid() as session:
        c.create_players(
            session,
            n=nplayers,
            unames=(
                None if automatic_unames else [a.strip() for a in unames.split("\n")]
            ),
            data=data,
        )

    e.set_room(roomname)

    return RedirectResponse(f"{d.ROOT}/admin/session/{sid.sname}/", status_code=303)


@router.get("/session/{sname}/")
async def sessionmain(
    request: Request,
    sname: t.Sessionname,
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)

    with Session(sname) as session:
        description = session.get("description")
        secret = session.get("_uproot_secret")

    return HTMLResponse(
        await render(
            "SessionMain.html",
            dict(
                sname=sname,
                description=description,
                secret=secret,
            )
            | a.info_online(sname),
        )
    )


@router.get("/session/{sname}/viewdata/")
async def session_viewdata(
    request: Request,
    sname: t.Sessionname,
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)
    return HTMLResponse(await render("ViewData.html", dict(sname=sname)))


@router.get("/session/{sname}/selectdata/")
async def session_selectdata(
    request: Request,
    sname: t.Sessionname,
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)
    return HTMLResponse(await render("SelectData.html", dict(sname=sname)))


@router.get("/session/{sname}/multiview/")
async def session_multiview(
    request: Request,
    sname: t.Sessionname,
    auth=Depends(auth_required),
) -> Response:
    session_exists(sname)

    return HTMLResponse(
        await render("MultiView.html", dict(sname=sname) | a.info_online(sname))
    )  # HACK


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

    if now() - LAST_FAILED_LOGIN > 5.0 and user in d.ADMINS and d.ADMINS[user] == pw:
        response = RedirectResponse(f"{d.ROOT}/admin/dashboard/", status_code=303)
        set_cookie(
            response,
            user,
            a.get_secret(user, pw),
            x_forwarded_proto.lower() == "https"
            or not (
                host.startswith("localhost") or host.startswith("127.0.0.")
            ),  # Safari really sucks
        )

        return response

    LAST_FAILED_LOGIN = now()

    return RedirectResponse(f"{d.ROOT}/admin/login/?bad=1", status_code=303)


@router.get("/")
async def home(
    request: Request,
    auth=Depends(auth_required),
) -> Response:
    return RedirectResponse(f"{d.ROOT}/admin/dashboard/", status_code=303)


@router.websocket("/ws/")
async def ws(websocket: WebSocket, uauth: Optional[str] = Cookie(None)) -> None:
    if uauth is None or a.verify_secret(**a.from_cookie(uauth)) is None:
        raise HTTPException(status_code=403, detail="Bad user")

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
        fun = cast(Callable, jj)

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
                        } if isinstance(
                            sname, str  # type: ignore[has-type]
                        ):
                            newfname = "subscribe_to_attendance"  # type: ignore[unreachable]
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
                            await websocket.send_json(
                                dict(
                                    kind="invoke",
                                    payload=dict(
                                        data=await cast(Callable, FUNS[mname])(
                                            *margs,
                                            **mkwargs,
                                        ),
                                        future=result["future"],
                                    ),
                                )
                            )
                        case _:
                            pass
                            # ~ raise NotImplementedError(result)
                elif fname == "subscribe_to_attendance":
                    uname, show_page_from_attendance = result
                    sname = args[fname]["sname"]
                    info = u.get_info(t.PlayerIdentifier(sname, uname))

                    await websocket.send_json(
                        dict(
                            kind="event",
                            payload=dict(
                                event="Attended",
                                detail=dict(
                                    uname=uname,
                                    show_page_from_attendance=show_page_from_attendance,
                                    info=info,
                                ),
                            ),
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
            new_task = asyncio.create_task(cast(Callable, factory)(**args[fname]))
            tasks[new_task] = (fname, factory)


FUNS = dict(
    advance_by_one=a.advance_by_one,
    revert_by_one=a.revert_by_one,
    insert_fields=a.insert_fields,
    put_to_end=a.put_to_end,
    reload=a.reload,
    mark_dropout=a.mark_dropout,
    adminmessage=a.adminmessage,
    viewdata=a.viewdata,
    announcements=a.announcements,
)
