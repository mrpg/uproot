# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements player routes.
"""

import asyncio
import hashlib
import os.path
import traceback
from collections import deque
from datetime import datetime, timezone
from email.utils import formatdate, parsedate_to_datetime
from pathlib import Path
from time import time
from typing import Any, Iterable, Optional, cast
from urllib.parse import quote

import orjson
from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    ORJSONResponse,
    RedirectResponse,
    Response,
)
from starlette.datastructures import UploadFile

import uproot as u
import uproot.admin as a
import uproot.chat as chat
import uproot.deployment as d
import uproot.jobs as j
import uproot.queues as q
import uproot.types as t
from uproot.constraints import ensure, valid_token
from uproot.core import find_free_slot
from uproot.pages import (
    path2page,
    render,
    render_error,
    show2path,
    timeout_reached,
    validate,
    verify_csrf,
)
from uproot.storage import (
    Player,
    Session,
    Storage,
)
from uproot.types import ensure_awaitable, optional_call, optional_call_once

PROCESSED_FUTURES: deque[str] = deque(maxlen=8 * 1024)


def safe_redirect(url: str) -> str:
    """Ensure redirect URL is safe by validating it's a relative URL.

    This prevents open redirect vulnerabilities by ensuring the URL:
    - Starts with / (relative to our domain)
    - Doesn't start with // (which would be protocol-relative)
    """
    if not url.startswith("/"):
        raise ValueError("Redirect URL must be relative")
    if url.startswith("//"):
        raise ValueError("Protocol-relative URLs not allowed")
    return url


PROCESSED_FUTURES_LOCK = asyncio.Lock()
router = APIRouter(prefix=d.ROOT)


@router.get("/")
async def index(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{d.ROOT}/admin/", status_code=303)


@router.post("/enqueue/{queue:path}")
async def enqueue(
    request: Request,
    queue: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    path = tuple(queue.strip("/").split("/"))

    # Parse request body
    body = await request.json()
    entry = body.get("entry")

    path, u = q.enqueue(path, entry)

    return {
        "status": "enqueued",
        "path": list(path),
        "u": u,
    }


def valid_player(sname: t.Sessionname, uname: str) -> Storage:
    player = Player(sname, uname)

    if not player:
        raise HTTPException(status_code=403, detail="Bad user")

    return player


async def show_page(
    request: Request,
    player: Storage,
    uauth: Optional[str] = None,
) -> str:
    # This function is written in a very verbose style to reveal logic issues early

    ppath = show2path(player.page_order, player.show_page)
    page = path2page(ppath)
    proceed = False
    direction = 1  # 1 for forward, -1 for backward
    form = None
    formdata = None
    custom_errors: list[str] = []
    metadata = dict()

    if timeout_reached(page, player, d.TIMEOUT_TOLERANCE):
        await ensure_awaitable(
            optional_call, page, "timeout_reached", default_return=True, player=player
        )
        proceed = True

    if request.method == "GET":
        if player.show_page == -1:
            pass
        elif player.started and len(player.page_order) > player.show_page > -1:
            if await ensure_awaitable(
                optional_call, page, "show", default_return=True, player=player
            ):
                pass
            else:
                proceed = True
        elif len(player.page_order) == player.show_page:
            pass
        else:
            raise HTTPException(status_code=501)
    elif request.method == "POST":
        formdata = await request.form()

        try:
            uproot_from_value = formdata["_uproot_from"]
            ensure(isinstance(uproot_from_value, str), ValueError)
            uproot_from_str = str(uproot_from_value)

            # Check for back navigation
            if uproot_from_str.startswith("back-"):
                send_from = int(
                    uproot_from_str[5:]
                )  # Extract page number after "back-"
                is_back_navigation = True
            else:
                send_from = int(uproot_from_str)
                is_back_navigation = False
        except ValueError:
            send_from = -1000
            is_back_navigation = False

        if player.show_page == send_from and verify_csrf(page, player, formdata):
            if is_back_navigation:
                # Handle back navigation
                if (
                    hasattr(page, "allow_back")
                    and page.allow_back
                    and player.show_page > 0
                ):
                    # Set direction to backward and proceed
                    direction = -1
                    proceed = True
                else:
                    # Back navigation not allowed
                    if not hasattr(page, "allow_back") or not page.allow_back:
                        raise RuntimeError(
                            f"Back navigation attempted but not allowed on page {page.__class__.__name__}"
                        )
                    else:
                        raise RuntimeError(
                            f"Back navigation attempted but player is at first page (show_page={player.show_page})"
                        )
            elif player.show_page == -1:  # Initialize.html
                if not player.started:
                    player.started = True

                proceed = True
            else:  # any other page - need to validate
                form, valid, custom_errors = await validate(page, player, formdata)
                stealth_fields: dict[str, Any] = dict()

                for stealth in cast(
                    Iterable[str],
                    await ensure_awaitable(
                        optional_call,
                        page,
                        "stealth_fields",
                        default_return=(),
                        player=player,
                    ),
                ):
                    stealth_fields[stealth] = None

                if valid:
                    if form is not None:
                        for fname, field in form._fields.items():
                            if (
                                isinstance(field.data, UploadFile)
                                or fname in stealth_fields
                            ):
                                stealth_fields[fname] = field.data
                            else:
                                if fname in formdata:
                                    setattr(player, fname, field.data)
                                else:
                                    # Since this nonetheless validated, it must be an
                                    # optional field that was cleared - set to None!
                                    # See issue #156.
                                    setattr(player, fname, None)

                        if stealth_fields:
                            stealth_errors = await ensure_awaitable(
                                optional_call,
                                page,
                                "handle_stealth_fields",
                                default_return=[],
                                player=player,
                                **stealth_fields,
                            )
                            if isinstance(stealth_errors, str):
                                stealth_errors = [stealth_errors]
                            if stealth_errors:
                                custom_errors.extend(stealth_errors)
                                proceed = False
                            else:
                                proceed = True
                        else:
                            proceed = True
                    else:
                        proceed = True
        else:
            pass
    else:
        raise HTTPException(status_code=400)

    if proceed:
        proceed = cast(
            bool,
            await ensure_awaitable(
                optional_call, page, "may_proceed", default_return=True, player=player
            ),
        )

    if proceed and player.show_page < len(player.page_order):
        # Only call after_once and after_always_once for forward navigation
        if direction == 1:
            await ensure_awaitable(
                optional_call_once,
                page,
                "after_once",
                storage=player,
                show_page=player.show_page,
                player=player,
            )
            await ensure_awaitable(
                optional_call_once,
                page,
                "after_always_once",
                storage=player,
                show_page=player.show_page,
                player=player,
            )

        if direction == 1:
            # Forward navigation
            candidate = player.show_page + 1

            while candidate <= len(player.page_order):
                page = path2page(show2path(player.page_order, candidate))
                player.show_page = candidate

                await ensure_awaitable(
                    optional_call,
                    page,
                    "early",
                    player=player,
                    request=request,
                )

                await ensure_awaitable(
                    optional_call_once,
                    page,
                    "before_always_once",
                    storage=player,
                    show_page=candidate,
                    player=player,
                )

                if await ensure_awaitable(
                    optional_call, page, "show", default_return=True, player=player
                ):
                    # Ladies and gentlemen, we got him!
                    break
                else:
                    await ensure_awaitable(
                        optional_call_once,
                        page,
                        "after_always_once",
                        storage=player,
                        show_page=candidate,
                        player=player,
                    )

                candidate += 1
        else:
            # Backward navigation - neutral, no lifecycle methods
            candidate = player.show_page - 1

            while candidate >= 0:
                page = path2page(show2path(player.page_order, candidate))
                player.show_page = candidate

                # Only check if page should be shown, no other lifecycle methods
                if await ensure_awaitable(
                    optional_call, page, "show", default_return=True, player=player
                ):
                    # Ladies and gentlemen, we got him!
                    break

                candidate -= 1

    if (
        to := await ensure_awaitable(optional_call, page, "set_timeout", player=player)
    ) is not None:
        metadata["remaining_seconds"] = to

    pid = cast(t.PlayerIdentifier, ~player)

    u.set_online(pid)

    # Only call before_once for forward navigation (backward is neutral)
    if direction == 1:
        await ensure_awaitable(
            optional_call_once,
            page,
            "before_once",
            storage=player,
            show_page=player.show_page,
            player=player,
        )

    return await render(
        request.app,
        request,
        player,
        page,
        formdata if not proceed else None,
        custom_errors,
        metadata,
        uauth,
    )


def nocache(response: Response) -> None:
    response.headers["Cache-Control"] = (
        "no-cache, no-store, must-revalidate, private, max-age=0"
    )
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["Last-Modified"] = "0"
    response.headers["ETag"] = ""
    response.headers["Vary"] = "*"
    response.headers["X-Accel-Expires"] = "0"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"


@router.get("/s/{sname}/{secret}/")
@router.get("/room/{roomname}/")
async def avoid_side_effects_when_previewing(
    request: Request,
) -> HTMLResponse:
    return HTMLResponse(
        await render(
            request.app,
            request,
            None,
            path2page("JustPOST.html"),
        ),
    )


@router.post("/s/{sname}/{secret}/")
async def sessionwide(
    request: Request,
    sname: t.Sessionname,
    secret: str,
) -> Response:
    # Verify sname and secret
    a.session_exists(sname)
    session = Session(sname)

    with session:
        if not secret == session._uproot_secret:
            raise HTTPException(status_code=401)

        free_slot = find_free_slot(session)

        if free_slot is not None:
            _, free_uname = free_slot

            # Redirect to player
            with Player(sname, free_uname) as p:
                p.started = True  # This prevents race conditions

            redirect_url = safe_redirect(
                f"{d.ROOT}/p/{quote(sname, safe='')}/{quote(free_uname, safe='')}/"
            )
            return RedirectResponse(redirect_url, status_code=303)
        else:
            # Session is full, so to speak
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomFull.html"),
                    metadata=dict(called_from="session"),
                ),
                status_code=423,
            )


@router.get("/p/{sname}/{uname}/")
@router.post("/p/{sname}/{uname}/")
async def show_page_wrapper(
    request: Request,
    sname: t.Sessionname,
    uname: str,
    player: Storage = Depends(valid_player),
    uauth: Optional[str] = Cookie(None),
) -> HTMLResponse:
    with player:
        try:
            response = HTMLResponse(
                await show_page(request, player, uauth),
            )
        except Exception as exc:
            response = HTMLResponse(
                await render_error(request, player, uauth, exc),
                status_code=500,
            )

    nocache(response)

    return response


@router.websocket("/ws/{sname}/{uname}/")
async def ws(
    websocket: WebSocket,
    sname: t.Sessionname,
    uname: t.Username,
    player: Storage = Depends(valid_player),
    uauth: Optional[str] = Cookie(None),
) -> None:
    await websocket.accept()

    pid = cast(t.PlayerIdentifier, ~player)
    data = a.from_cookie(uauth)
    is_admin = (
        a.verify_auth_token(data.get("user", ""), data.get("token", "")) is not None
    )

    tasks = dict()
    background_tasks: set[asyncio.Task[Any]] = set()
    args: dict[str, dict[str, Any]] = dict(
        from_queue=dict(
            pid=pid,
        ),
        from_websocket=dict(
            websocket=websocket,
        ),
        timer=dict(
            interval=30.0,
        ),
    )

    async def process_websocket_message(result: dict[str, Any]) -> None:
        u.set_online(pid)

        async with PROCESSED_FUTURES_LOCK:
            if "future" in result and result["future"] in PROCESSED_FUTURES:
                return
            elif "future" in result:
                PROCESSED_FUTURES.append(result["future"])

        invoke_respond = True
        invoke_response: Any = None
        invoke_exception = False

        with player:
            match result:
                case {"endpoint": "hello"}:
                    pass
                case {"endpoint": "time"}:
                    invoke_response = time()
                case {"endpoint": "jserrors", "payload": msg} if isinstance(msg, str):
                    # Use repr() to prevent log injection attacks
                    epath = f"{d.ROOT}/p/{sname}/{uname}/"
                    d.LOGGER.error(f"JavaScript error [{epath!r}]: {msg[:256]!r}")
                case {
                    "endpoint": "skip",
                    "payload": new_show_page,
                } if isinstance(
                    new_show_page, int
                ) and (is_admin or player.session.testing):
                    player.show_page = new_show_page
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
                ):
                    ppath = show2path(player.page_order, player.show_page)
                    page = path2page(ppath)

                    try:
                        live_method = getattr(page, mname)

                        if not hasattr(live_method, "__live__"):
                            raise TypeError(
                                f"{live_method} must be decorated with @live"
                            )
                        else:
                            invoke_response = await ensure_awaitable(
                                live_method,
                                player,
                                *margs,
                                **mkwargs,
                            )
                    except Exception as _e:
                        traceback.print_exc()
                        invoke_exception = True

                case {"endpoint": "chat_add", "payload": payload} if (
                    len(payload) == 2
                    and isinstance(payload[0], str)
                    and isinstance(payload[1], str)
                    and valid_token(payload[0])
                ):
                    mname, msgtext = payload

                    mid = t.ModelIdentifier(sname, mname)

                    if chat.exists(mid) and pid in (pp := chat.players(mid)):
                        msg = chat.add_message(mid, pid, msgtext)

                        for p in pp:
                            q.enqueue(
                                tuple(p),
                                dict(
                                    source="chat",
                                    data=chat.show_msg(
                                        mid,
                                        msg,
                                        p,
                                    ),
                                    event="_uproot_Chatted",
                                ),
                            )

                        invoke_respond = False
                    else:
                        d.LOGGER.warning(
                            f"Ignored chat message starting with '{msgtext[:32]}' for "
                            f"non-existing chat starting with '{mname[:32]}' (or no auth)"
                        )
                case {
                    "endpoint": "chat_get",
                    "payload": mname,
                } if isinstance(
                    mname, str
                ) and valid_token(mname):
                    mid = t.ModelIdentifier(sname, mname)

                    if chat.exists(mid) and pid in (pp := chat.players(mid)):
                        invoke_response = [
                            chat.show_msg(mid, msg, pid) for msg in chat.messages(mid)
                        ]
                    else:
                        d.LOGGER.warning(
                            f"Ignored chat request for non-existing chat "
                            f"starting with '{mname[:32]}' (or no auth, {pp})"
                        )
                case _:
                    d.LOGGER.warning(
                        f"Ignored websocket message starting with '{repr(result)[:64]}' (is_admin: {is_admin})"
                    )

        if invoke_respond:
            await websocket.send_bytes(
                orjson.dumps(
                    dict(
                        kind="invoke",
                        payload=dict(
                            data=invoke_response,
                            future=result["future"],
                            error=invoke_exception,
                        ),
                    )
                )
            )

    for jj in j.PLAYER_JOBS:
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
                    new_task = asyncio.create_task(cast(Any, factory)(**args[fname]))
                    tasks[new_task] = (fname, factory)

                if fname == "from_queue":
                    u_, entry = result

                    match entry:
                        case {
                            "source": "admin",
                            "kind": kind_,
                            "payload": payload_,
                        } if isinstance(kind_, str) and isinstance(payload_, dict):
                            await websocket.send_bytes(
                                orjson.dumps(
                                    dict(
                                        kind=kind_,
                                        payload=payload_,
                                        source="admin",
                                    )
                                )
                            )
                        case _:
                            await websocket.send_bytes(
                                orjson.dumps(
                                    dict(
                                        kind="queue",
                                        payload=dict(
                                            u=u_,
                                            entry=entry,
                                        ),
                                    )
                                )
                            )
                elif fname == "from_websocket":
                    bg_task = asyncio.create_task(process_websocket_message(result))
                    background_tasks.add(bg_task)
                    bg_task.add_done_callback(background_tasks.discard)
                elif fname == "timer":
                    pass  # placeholder for the future
                else:
                    raise NotImplementedError(fname)
            except WebSocketDisconnect:
                for task in tasks:
                    task.cancel()
                for task in background_tasks:
                    task.cancel()

                await asyncio.gather(
                    *tasks.keys(), *background_tasks, return_exceptions=True
                )

                return
            except Exception as exc:
                raise exc

            if fname != "from_websocket":
                new_task = asyncio.create_task(cast(Any, factory)(**args[fname]))
                tasks[new_task] = (fname, factory)


@router.get("/static/{realm}/{location:path}")
async def anystatic(request: Request, realm: str, location: str) -> Response:
    """
    Serve static files from controlled _static directories.

    Security Model:
    - Files can only be served from _static directories within the project
    - Path traversal attacks (../) are prevented through multiple layers
    - Symbolic links within _static are allowed and will be followed
    - Direct path manipulation to escape _static boundaries is blocked

    Args:
        realm: Namespace for static files (_uproot, _project, or app name)
        location: Relative path to file within the realm's _static directory
    """

    # SECURITY LAYER 1: Validate realm parameter
    # realm.isidentifier() ensures realm can ONLY contain:
    # - Letters (a-z, A-Z)
    # - Digits (0-9, but not as first character)
    # - Underscores (_)
    # This prevents injection of path separators (/, \) or traversal sequences (..)
    # Examples blocked: "../etc", "../../passwd", "app/../etc"
    if not realm.isidentifier():  # KEEP AS IS
        raise HTTPException(status_code=404)

    # SECURITY LAYER 2: Construct base_path from controlled locations only
    # All base paths point to _static directories within controlled areas:
    # - _uproot: Package's own static files (bundled with installation)
    # - _project: Project root's static files (current working directory)
    # - Other: App-specific static files under {cwd}/{realm}/_static
    # No user input can influence these base paths except via validated realm
    if realm == "_uproot":
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_static")
    elif realm == "_project":
        base_path = os.path.join(os.getcwd(), "_static")
    else:
        base_path = os.path.join(os.getcwd(), realm, "_static")

    # SECURITY LAYER 3: Normalize paths to resolve . and .. components
    # os.path.abspath() resolves relative path components but does NOT follow symlinks
    # (unlike os.path.realpath() which would follow symlinks)
    # This allows symbolic links within _static to work (intentional design)
    # while still preventing ../../../etc/passwd style attacks
    base_path = os.path.abspath(base_path)
    target_path = os.path.abspath(os.path.join(base_path, location))

    # SECURITY LAYER 4: Verify target_path is within base_path boundary
    # This is the critical path traversal prevention check.
    # Examples of what this blocks:
    # - location="../../../etc/passwd" -> target_path="/etc/passwd" (doesn't start with base_path)
    # - location="/etc/passwd" -> target_path="/etc/passwd" (os.path.join discards base_path for absolute paths)
    #
    # Why base_path + os.sep instead of just base_path?
    # - Prevents prefix attacks: if base_path="/app/_static" and we only checked startswith("/app/_static")
    #   then "/app/_static_evil/file" would incorrectly pass
    # - The trailing separator ensures we're checking for a directory boundary
    #
    # Why symbolic links still work:
    # - If _static/mylink -> /external/data exists
    # - target_path would be {base_path}/mylink/file (NOT /external/data/file)
    # - This passes the check because we used abspath() not realpath()
    # - FileResponse will follow the symlink when actually serving the file
    if not target_path.startswith(base_path + os.sep):
        raise HTTPException(status_code=404)

    # SECURITY LAYER 5: Verify each path component exists (defense in depth)
    # This provides:
    # 1. Additional validation that the path is legitimate
    # 2. Early detection of non-existent files (before stat/file operations)
    # 3. Helpful developer feedback for case-sensitivity issues
    # This layer is not strictly required for security (Layer 4 handles that)
    # but provides defense in depth and better error messages
    # Use the validated target_path (not raw location) for additional safety
    relative_path = os.path.relpath(target_path, base_path)
    path_parts = Path(relative_path).parts
    current_path = Path(base_path)

    for part in path_parts:
        # Ensure current_path stays within base_path boundary
        if (
            not str(current_path).startswith(base_path + os.sep)
            and str(current_path) != base_path
        ):
            raise HTTPException(status_code=404)
        actual_names = os.listdir(current_path)
        if part not in actual_names:
            # Check for case mismatches (helpful for cross-platform development)
            # e.g., requesting "Image.PNG" when file is actually "image.png"
            matches = [n for n in actual_names if n.lower() == part.lower()]
            if matches:
                d.LOGGER.error(
                    f"Case mismatch in {{%% static %%}}: '{part}' should be '{matches[0]}'"
                )
                raise HTTPException(status_code=500)
            else:
                raise HTTPException(status_code=404)

        current_path = current_path / part

    # SECURITY LAYER 6: Prevent directory listing
    # Static file serving should only serve files, not directories
    # This prevents enumeration of directory contents
    if os.path.isdir(target_path):
        raise HTTPException(status_code=404)

    # At this point, target_path has been validated through 6 security layers:
    # 1. realm contains no path separators or traversal sequences
    # 2. base_path points to a controlled _static directory
    # 3. Path components (. and ..) have been normalized
    # 4. target_path is confirmed to be within base_path boundary
    # 5. Each path component has been verified to exist
    # 6. target_path is confirmed to be a file, not a directory
    #
    # It is now safe to serve this file.

    stat = os.stat(target_path)

    etag_base = f"{stat.st_mtime}-{stat.st_size}-{stat.st_ino}"
    etag = f'"{hashlib.md5(etag_base.encode()).hexdigest()}"'  # nosec B324 - MD5 for ETag generation, not cryptographic use

    last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    last_modified_str = formatdate(stat.st_mtime, usegmt=True)

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=304)

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            if_modified_since_dt = parsedate_to_datetime(if_modified_since)
            if last_modified <= if_modified_since_dt:
                return Response(status_code=304)
        except (ValueError, TypeError):
            pass

    headers = {
        "ETag": etag,
        "Last-Modified": last_modified_str,
        "Cache-Control": "public, max-age=3600",
        "Accept-Ranges": "bytes",
    }

    return FileResponse(target_path, headers=headers)


@router.get("/api/{appname}/{sname}/")
@router.post("/api/{appname}/{sname}/")
async def app_queries(
    request: Request,
    appname: str,
    sname: t.Sessionname,
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    if appname not in u.APPS:
        raise HTTPException(status_code=400, detail="Invalid app")

    if not hasattr(u.APPS[appname], "api"):
        raise HTTPException(status_code=400, detail="App has no api()")

    a.session_exists(sname)

    with Session(sname) as session:
        result = await ensure_awaitable(
            u.APPS[appname].api,
            request=request,
            session=session,
        )

        if type(result) is Response:
            return result
        else:
            return ORJSONResponse(result)


@router.get("/api2/{appname}/{sname}/")
@router.post("/api2/{appname}/{sname}/")
async def app_queries2(
    request: Request,
    appname: str,
    sname: t.Sessionname,
) -> Response:
    if appname not in u.APPS:
        raise HTTPException(status_code=400, detail="Invalid app")

    if not hasattr(u.APPS[appname], "api2"):
        raise HTTPException(status_code=400, detail="App has no api2()")

    a.session_exists(sname)

    with Session(sname) as session:
        result = await ensure_awaitable(
            u.APPS[appname].api2,
            request=request,
            session=session,
        )

        if type(result) is Response:
            return result
        else:
            return ORJSONResponse(result)
