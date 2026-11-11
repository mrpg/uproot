# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements player routes.
"""

import asyncio
import contextlib
import functools
import hashlib
import hmac
import traceback
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from time import time
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import quote
from weakref import WeakValueDictionary

import anyio
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
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.datastructures import UploadFile

import uproot as u
import uproot.deployment as d
import uproot.jobs as j
import uproot.queues as q
import uproot.services.auth as auth_service
import uproot.services.player_service as player_ops
import uproot.services.room_service as room_ops
import uproot.services.session_service as session_ops
import uproot.types as t
from uproot import chat, i18n
from uproot.constraints import valid_token
from uproot.core import find_free_slot, starts_segment
from uproot.pages import (
    path2page,
    render,
    render_error,
    show2path,
    static_files,
    static_path,
    static_version,
    timeout_reached,
    validate,
    verify_csrf,
)
from uproot.security import require_same_origin_websocket
from uproot.storage import (
    Player,
    Session,
    Storage,
)
from uproot.types import ensure_awaitable, optional_call, optional_call_once
from uproot.utils import safe_redirect_response

router = APIRouter(prefix=d.ROOT)
PAGE_LOCKS: WeakValueDictionary[tuple[t.Sessionname, str], asyncio.Lock] = (
    WeakValueDictionary()
)


def page_lock(sname: t.Sessionname, uname: str) -> asyncio.Lock:
    key = (sname, uname)
    lock = PAGE_LOCKS.get(key)

    if lock is None:
        lock = asyncio.Lock()
        PAGE_LOCKS[key] = lock

    return lock


# How hooks that a page does not define behave (default_return)
DEFAULTS: dict[str, bool] = {"show": True, "may_proceed": True, "allow_back": False}


@dataclass(frozen=True)
class Shown:
    """How a displayed page shows its form: fresh (the default), or with the
    submitted values and the errors found in them, if any."""

    formdata: Any = None
    custom_errors: list[str] | None = None
    field_errors: dict[str, list[str]] | None = None


FRESH = Shown()


@dataclass(frozen=True)
class Display:
    """The page that a request displays, and how it shows its form."""

    page: type[t.Page]
    shown: Shown = FRESH


# The participant-facing state machine. Its specification is Pages.lean in
# uproot-proofs, whose names (call, once, visit, leave, ...) these functions
# share. A request ends by displaying the page at the player's position:
#
# 1. Entering. A position is entered whenever navigation reaches it: early(),
#    then before_always_once. Then show() decides. A page that is not shown is
#    skipped (after_always_once, then the next position is entered); a shown
#    page is displayed (before_once, then the page). End.html is always shown.
# 2. Once. before_always_once, before_once, after_once and after_always_once
#    run the first time their occasion arises at a position, always, but only
#    once. early() runs whenever navigation reaches a position, but loading the
#    page runs it only if it has never run there.
# 3. Forms. Only the form of the page at the player's position, with a valid
#    token, can be submitted. Any other request is handled as loading the page.
# 4. Leaving. An accepted submission leaves the page if may_proceed allows it.
# 5. Timeouts. After a page's deadline, every request is a timed-out
#    submission, also Back.
# 6. Back leads to the nearest earlier page that is shown, without crossing the
#    start of an app, a round or an iteration of Repeat. Otherwise, the player
#    stays.
# 7. Moves. A hook may move the player (move_to_page, move_to_end). The hooks of
#    the current step finish, then the player enters the target.


def page_at(player: Storage, position: int) -> type[t.Page]:
    return path2page(show2path(player.page_order, position))


def current_page(player: Storage) -> type[t.Page]:
    return page_at(player, player.show_page)


async def call(page: type[t.Page], hook: str, player: Storage, **kwargs: Any) -> Any:
    """Run a hook of page, if page defines it. Flush in-place changes before
    refreshing moves made through another Storage instance."""
    result = await ensure_awaitable(
        optional_call,
        page,
        hook,
        default_return=DEFAULTS.get(hook),
        player=player,
        **kwargs,
    )
    player.flush()
    player.refresh("show_page", "page_order")

    return result


async def once(
    page: type[t.Page],
    hook: str,
    player: Storage,
    position: int,
    *,
    again: bool = False,
    **kwargs: Any,
) -> None:
    """Run a hook of page if it has not run at position yet, or again."""
    await ensure_awaitable(
        optional_call_once,
        page,
        hook,
        storage=player,
        show_page=position,
        rerun=again,
        player=player,
        **kwargs,
    )
    player.flush()
    player.refresh("show_page", "page_order")


async def enter_page(
    request: Request,
    page: type[t.Page],
    player: Storage,
    show_page: int,
    *,
    rerun: bool,
) -> None:
    """Enter the page at position show_page: early(), then before_always_once.
    rerun: run early() even if it has run there before (navigation)."""
    await once(page, "early", player, show_page, again=rerun, request=request)
    await once(page, "before_always_once", player, show_page)


async def visit_position(
    request: Request,
    player: Storage,
    position: int,
    again: bool,
    shown: Shown | None,
) -> tuple[type[t.Page], int | None]:
    """One position of visit(): its page, and where to go on (None if the page
    is to be displayed)."""
    end = len(player.page_order)

    if position >= end:
        player.show_page = end
        page = page_at(player, end)
        await enter_page(request, page, player, end, rerun=again)
        await once(page, "before_once", player, end)

        return page, None

    player.show_page = position
    page = page_at(player, position)
    await enter_page(request, page, player, position, rerun=again)

    if player.show_page != position:
        return page, player.show_page

    is_shown = shown is not None or bool(await call(page, "show", player))

    if player.show_page != position:
        return page, player.show_page

    if is_shown:
        await once(page, "before_once", player, position)

        return page, None if player.show_page == position else player.show_page

    await once(page, "after_always_once", player, position)

    return page, position + 1 if player.show_page == position else player.show_page


async def visit(
    request: Request,
    player: Storage,
    position: int,
    *,
    again: bool,
    shown: Shown | None = None,
) -> Display:
    """Enter position and go on from there until a page is displayed. again:
    run early() even if it has run before (navigation, as opposed to loading the
    page). shown: display position with this form, without asking show()
    (staying, or going back, which asked)."""
    while True:
        page, next_position = await visit_position(
            request, player, position, again, shown
        )

        if next_position is None:
            return Display(page, shown or FRESH)

        position, again, shown = next_position, True, None


async def leave(
    request: Request, player: Storage, position: int, page: type[t.Page]
) -> Display:
    """Leave position forward: after_once, after_always_once, then enter the
    next position, or the one a hook moved the player to."""
    await once(page, "after_once", player, position)
    await once(page, "after_always_once", player, position)

    if player.show_page != position:
        return await visit(request, player, player.show_page, again=True)

    return await visit(request, player, position + 1, again=True)


async def proceed(
    request: Request, player: Storage, position: int, page: type[t.Page]
) -> Display:
    """Leave position forward, unless it is the end."""
    if position < len(player.page_order):
        return await leave(request, player, position, page)

    return await visit(request, player, position, again=False, shown=FRESH)


async def load(request: Request, player: Storage, position: int) -> Display:
    """Load the page at position, unless a hook moved the player."""
    if player.show_page != position:
        return await visit(request, player, player.show_page, again=True)

    return await visit(request, player, position, again=False)


async def stay(
    request: Request, player: Storage, position: int, shown: Shown
) -> Display:
    """Stay at position and display it with shown, unless a hook moved the
    player."""
    if player.show_page != position:
        return await visit(request, player, player.show_page, again=True)

    return await visit(request, player, position, again=False, shown=shown)


async def go_back(
    request: Request, player: Storage, position: int, page: type[t.Page]
) -> Display:
    """Back to the nearest earlier page that is shown, without crossing the
    start of an app, a round or an iteration of Repeat. Otherwise, stay."""
    allowed = await call(page, "allow_back", player)

    if player.show_page != position:
        return await visit(request, player, player.show_page, again=True)

    if allowed:
        candidate = position - 1

        while candidate >= 0 and not starts_segment(player.page_order[candidate]):
            player.show_page = candidate
            shown = await call(page_at(player, candidate), "show", player)

            if player.show_page != candidate:
                return await visit(request, player, player.show_page, again=True)

            if shown:
                return await visit(request, player, candidate, again=True, shown=FRESH)

            candidate -= 1

        player.show_page = position

    return await stay(request, player, position, FRESH)


@router.get("/")
async def index(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{d.ROOT}/admin/", status_code=303)


@router.post("/enqueue/{queue:path}")
async def enqueue(
    request: Request,
    queue: str,
    bauth: None = Depends(auth_service.require_bearer_token),
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


def api2_player(request: Request, sname: t.Sessionname) -> Storage | None:
    """Authenticate optional player credentials supplied by uproot.api2()."""
    uname = request.headers.get("X-Uproot-Player")
    supplied_csrf = request.headers.get("X-Uproot-CSRF")

    if uname is None and supplied_csrf is None:
        return None
    if not uname or not supplied_csrf:
        raise HTTPException(status_code=403, detail="Incomplete player credentials")

    try:
        player = valid_player(sname, uname)
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=403, detail="Bad user") from error

    with player:
        expected_csrf = f"{sname}+{uname}+{player._uproot_key}"

    if not supplied_csrf.isascii() or not hmac.compare_digest(
        supplied_csrf, expected_csrf
    ):
        raise HTTPException(status_code=403, detail="Bad user")

    return player


ValidPlayer = Depends(valid_player)


def initialize(player: Storage) -> None:
    with player.session as session:
        session_ops.run_new_session_callbacks(session)

    player_ops.prepare_player_callbacks(player)


async def save_form(
    page: type[t.Page], player: Storage, form: Any, formdata: Any
) -> list[str]:
    """Save a validated form and return the errors of handle_stealth_fields.
    Stealth fields and uploads are passed to that handler instead of being
    saved. If it rejects the submission, nothing is saved, just as when
    validate() rejects it."""
    manual = set(
        cast(
            Iterable[str],
            await ensure_awaitable(
                optional_call,
                page,
                "stealth_fields",
                default_return=(),
                player=player,
            ),
        )
    ) | {
        fname
        for fname, field in form._fields.items()
        if isinstance(field.data, UploadFile)
    }

    if manual:
        errors = await ensure_awaitable(
            optional_call,
            page,
            "handle_stealth_fields",
            default_return=[],
            player=player,
            data=form.data,
        )

        if isinstance(errors, str):
            errors = [errors]
        if errors:
            return list(errors)

    await ensure_awaitable(
        optional_call,
        page,
        "before_form_save",
        player=player,
        data=MappingProxyType(form.data),
    )

    for fname, field in form._fields.items():
        if fname not in manual:
            # A field missing from formdata that nonetheless validated must be
            # an optional field that was cleared - set to None! See issue #156.
            setattr(player, fname, field.data if fname in formdata else None)

    return []


async def timeout_fires(page: type[t.Page], player: Storage) -> bool:
    """A page timeout counts as reached up to TIMEOUT_TOLERANCE seconds early.
    Within that window, the page only advances if may_proceed allows it. Once
    the deadline has passed, may_proceed is skipped, so that wait pages that
    time out cannot loop forever."""
    if not timeout_reached(page, player, d.TIMEOUT_TOLERANCE):
        return False

    if timeout_reached(page, player, 0.0):
        return True

    return bool(await call(page, "may_proceed", player))


async def timed_out(page: type[t.Page], player: Storage) -> bool:
    """Whether the deadline of the player's position counts as reached; if so,
    timeout_reached has run."""
    if not await timeout_fires(page, player):
        return False

    await call(page, "timeout_reached", player)

    return True


async def accept(
    page: type[t.Page], player: Storage, formdata: Any
) -> tuple[bool, Shown]:
    """Check a submitted form and save it if it is accepted: if the fields
    validate and neither validate() nor handle_stealth_fields rejects it."""
    form, valid, custom_errors, field_errors = await validate(page, player, formdata)

    if valid and form is not None:
        stealth_errors = await save_form(page, player, form, formdata)
        custom_errors.extend(stealth_errors)
        valid = not stealth_errors

    player.flush()
    player.refresh("show_page", "page_order")

    return valid, Shown(formdata, custom_errors, field_errors)


def submission(player: Storage, formdata: Any) -> tuple[bool, Any] | None:
    """(back, formdata) if formdata is the form of the player's position with a
    valid token, None otherwise. _uproot_from is the position, prefixed with
    back- for Back."""
    if formdata is None:
        return None

    source = formdata.get("_uproot_from")

    if not isinstance(source, str):
        return None

    back = source.startswith("back-")

    try:
        position = int(source.removeprefix("back-"))
    except ValueError:
        return None

    if position != player.show_page or not verify_csrf(player, formdata):
        return None

    return back, formdata


async def respond(request: Request, player: Storage) -> Display:
    """What a request does, up to displaying a page."""
    if request.method == "GET":
        formdata = None
    elif request.method == "POST":
        formdata = await request.form()
    else:
        raise HTTPException(status_code=400)

    position = player.show_page
    submitted = submission(player, formdata)

    if position == -1:  # Initialize.html
        if submitted is not None and not submitted[0]:
            player.started = True
            initialize(player)

            return await visit(request, player, 0, again=True)

        return Display(current_page(player))

    page = current_page(player)  # Fails for invalid positions
    fired = await timed_out(page, player)

    if submitted is None:
        if fired:
            return await proceed(request, player, position, page)

        return await load(request, player, position)

    back, formdata = submitted

    if fired:  # A timed-out submission, even of Back
        await accept(page, player, formdata)

        return await proceed(request, player, position, page)

    if back:
        return await go_back(request, player, position, page)

    accepted, shown = await accept(page, player, formdata)

    if accepted and await call(page, "may_proceed", player):
        return await proceed(request, player, position, page)

    return await stay(request, player, position, shown)


async def show_page(
    request: Request,
    player: Storage,
    uauth: str | None = None,
) -> str:
    display = await respond(request, player)
    metadata = {}

    u.set_online(cast(t.PlayerIdentifier, t.identify(player)))

    if (
        to := await ensure_awaitable(
            optional_call, display.page, "set_timeout", player=player
        )
    ) is not None:
        metadata["remaining_seconds"] = to

    return await render(
        request.app,
        request,
        player,
        display.page,
        display.shown.formdata,
        display.shown.custom_errors,
        metadata,
        uauth,
        display.shown.field_errors,
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


@router.get("/s/{sname}/{secret}")
async def session_without_terminating_slash(
    request: Request,
    sname: str,
    secret: str,
) -> Response:
    query = f"?{request.url.query}" if request.url.query else ""
    redirect_url = (
        f"{d.ROOT}/s/{quote(sname, safe='')}/{quote(secret, safe='')}/{query}"
    )

    return safe_redirect_response(redirect_url, status_code=307)


@router.get("/s/{sname}/{secret}/")
@router.get("/room/{roomname}/")
async def avoid_side_effects_when_previewing(
    request: Request,
) -> HTMLResponse:
    if "sname" in request.path_params:
        session_ops.session_exists(request.path_params["sname"])
    elif "roomname" in request.path_params:
        room_ops.room_exists(request.path_params["roomname"])

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
    session_ops.session_exists(sname)
    session = Session(sname)

    with session:
        if not hmac.compare_digest(secret, session._uproot_secret):
            raise HTTPException(status_code=401)

        free_slot = find_free_slot(session)

        if free_slot is not None:
            _, free_uname = free_slot

            # Redirect to player
            with Player(sname, free_uname) as p:
                p.started = True  # This prevents race conditions

            redirect_url = (
                f"{d.ROOT}/p/{quote(sname, safe='')}/{quote(free_uname, safe='')}/"
            )

            return safe_redirect_response(redirect_url)
        else:
            # Session is full, so to speak
            return HTMLResponse(
                await render(
                    request.app,
                    request,
                    None,
                    path2page("RoomFull.html"),
                    metadata={"called_from": "session"},
                ),
                status_code=423,
            )


@router.get("/p/{sname}/{uname}/")
@router.post("/p/{sname}/{uname}/")
async def show_page_wrapper(
    request: Request,
    sname: t.Sessionname,
    uname: str,
    player: Storage = ValidPlayer,
    uauth: str | None = Cookie(None),
) -> HTMLResponse:
    async with page_lock(sname, uname):
        with player:
            try:
                response = HTMLResponse(
                    await show_page(request, player, uauth),
                )
            except Exception as exc:  # noqa: BLE001
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
    player: Storage = ValidPlayer,
    uauth: str | None = Cookie(None),
) -> None:
    require_same_origin_websocket(websocket)
    await websocket.accept()

    pid = cast(t.PlayerIdentifier, t.identify(player))
    queue = q.register(tuple(pid))  # convention: queue path = (sname, uname)

    processed_futures: deque[int | str] = deque(maxlen=8 * 1024)
    send_lock = asyncio.Lock()
    tasks = {}
    background_tasks: set[asyncio.Task[None]] = set()
    args: dict[str, dict[str, Any]] = {
        "from_queue": {
            "queue": queue,
        },
        "from_websocket": {
            "websocket": websocket,
        },
    }

    async def send_websocket_message(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_bytes(orjson.dumps(payload))

    async def run_process(result: dict[str, Any]) -> None:
        try:
            await process_websocket_message(result)
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    async def process_websocket_message(result: dict[str, Any]) -> None:
        u.set_online(pid)

        if "future" in result and result["future"] in processed_futures:
            return
        elif "future" in result:
            processed_futures.append(result["future"])

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
                    d.LOGGER.error(
                        "JavaScript error reported by browser (%s bytes)", len(msg)
                    )
                case {
                    "endpoint": "skip",
                    "payload": new_show_page,
                } if isinstance(
                    new_show_page, int
                ) and (player.session._uproot_testing or auth_service.logged_in(uauth)):
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
                    except Exception:  # noqa: BLE001
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

                    if len(msgtext) > chat.MAX_MESSAGE_LENGTH:
                        d.LOGGER.warning(
                            "Ignored oversized chat message from %s for chat starting with '%s'",
                            pid,
                            mname[:32],
                        )
                    elif chat.exists(mid) and pid in (pp := chat.players(mid)):
                        if chat.is_adminchat(mid):
                            if not chat.adminchat_reply_state(pid):
                                d.LOGGER.warning(
                                    f"Player {pid} tried to reply to admin chat "
                                    f"starting with '{mname[:32]}' while replies were disabled"
                                )
                            else:
                                msg_id = chat.add_message(mid, pid, msgtext)
                                await chat.notify_adminchat(
                                    mid,
                                    msg_id,
                                    pid,
                                    player,
                                    msgtext,
                                )
                                invoke_respond = False
                        else:
                            msg_id = chat.add_message(mid, pid, msgtext)
                            await chat.notify(mid, msg_id, pid, player, msgtext, pp)
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
                        if chat.is_adminchat(mid):
                            invoke_response = [
                                chat.show_adminchat_msg(mid, msg_id, msg_time, msg, pid)
                                for msg_id, msg_time, msg in chat.messages(mid)
                            ]
                        else:
                            invoke_response = [
                                chat.show_msg(mid, msg_id, msg_time, msg, pid)
                                for msg_id, msg_time, msg in chat.messages(mid)
                            ]
                    else:
                        d.LOGGER.warning(
                            f"Ignored chat request for non-existing chat "
                            f"starting with '{mname[:32]}' (or no auth, {pp})"
                        )
                case _:
                    d.LOGGER.warning(
                        f"Ignored websocket message starting with '{repr(result)[:64]}'"
                    )

        if invoke_respond and "future" in result:
            await send_websocket_message(
                {
                    "kind": "invoke",
                    "payload": {
                        "data": invoke_response,
                        "future": result["future"],
                        "error": invoke_exception,
                    },
                }
            )

    for jj in j.PLAYER_JOBS:
        tasks[asyncio.create_task(cast(Any, jj)(**args[jj.__name__]))] = (
            jj.__name__,
            jj,
        )

    try:
        while True:
            done = (
                await asyncio.wait(tasks.keys(), return_when=asyncio.FIRST_COMPLETED)
            )[0]

            for finished in done:
                fname, factory = tasks.pop(finished)
                try:
                    result = await finished

                    if fname == "from_websocket":
                        new_task = asyncio.create_task(
                            cast(Any, factory)(**args[fname])
                        )
                        tasks[new_task] = (fname, factory)

                    if fname == "from_queue":
                        u_, entry = result

                        match entry:
                            case {
                                "source": "admin",
                                "kind": kind_,
                                "payload": payload_,
                            } if isinstance(kind_, str) and isinstance(payload_, dict):
                                await send_websocket_message(
                                    {
                                        "kind": kind_,
                                        "payload": payload_,
                                        "source": "admin",
                                    }
                                )
                            case _:
                                await send_websocket_message(
                                    {
                                        "kind": "queue",
                                        "payload": {
                                            "u": u_,
                                            "entry": entry,
                                        },
                                    }
                                )
                    elif fname == "from_websocket":
                        bg_task = asyncio.create_task(run_process(result))
                        background_tasks.add(bg_task)
                        bg_task.add_done_callback(background_tasks.discard)
                    else:
                        raise NotImplementedError(fname)
                except WebSocketDisconnect:
                    return
                except Exception:  # noqa: BLE001
                    d.LOGGER.exception("Closing player websocket after handler failure")
                    return

                if fname != "from_websocket":
                    new_task = asyncio.create_task(cast(Any, factory)(**args[fname]))
                    tasks[new_task] = (fname, factory)
    finally:
        # Keep the last-seen timestamp for dropout detection and other tabs.
        q.deregister(tuple(pid), queue)

        pending_tasks = [*tasks, *background_tasks]
        for task in pending_tasks:
            task.cancel()

        # Let live handlers finish cleanup even if the request scope is cancelled.
        with anyio.CancelScope(shield=True):
            await asyncio.gather(*pending_tasks, return_exceptions=True)


@functools.lru_cache(maxsize=64)
def terms_body(language: str, version: int) -> tuple[str, str]:
    body = i18n.script(language)
    etag = hashlib.sha256(body.encode()).hexdigest()

    return body, etag


@router.get("/terms/{language}.js")
async def terms(request: Request, language: str) -> Response:
    if language not in i18n.LANGUAGES:
        body = "window.uproot = window.uproot || {};\nwindow.uproot.terms = {};\n"
        return Response(body, media_type="application/javascript")

    body, etag = terms_body(language, i18n.VERSION)

    response = Response(body, media_type="application/javascript")
    response.headers["ETag"] = f'"{etag}"'

    # Versioned links (see terms_url) may be cached indefinitely
    if request.query_params.get("v") == i18n.version(language):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "public, max-age=3600"

    return response


@router.get("/static/{realm}/{location:path}")
async def anystatic(request: Request, realm: str, location: str) -> Response:
    """
    Serve static files from controlled _static directories.
    """

    if not realm.isidentifier():
        raise HTTPException(status_code=404)

    response = await static_files(realm).get_response(location, request.scope)

    if response.status_code in (200, 206, 304):
        # Versioned links (see static_factory) may be cached indefinitely
        version = request.query_params.get("v")
        path = static_path(realm, location)

        if version is None:
            response.headers["Cache-Control"] = "public, max-age=3600"
        elif path is not None and version == static_version(path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache"

    return response


@router.get("/api/{appname}/{sname}/")
@router.post("/api/{appname}/{sname}/")
async def app_queries(
    request: Request,
    appname: str,
    sname: t.Sessionname,
    bauth: None = Depends(auth_service.require_bearer_token),
) -> Response:
    if appname not in u.APPS:
        raise HTTPException(status_code=400, detail="Invalid app")

    if not hasattr(u.APPS[appname], "api"):
        raise HTTPException(status_code=400, detail="App has no api()")

    session_ops.session_exists(sname)

    with Session(sname) as session:
        result = await ensure_awaitable(
            u.APPS[appname].api,
            request=request,
            session=session,
        )

        if isinstance(result, Response):
            return result
        else:
            return JSONResponse(result)


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

    session_ops.session_exists(sname)
    player = api2_player(request, sname)
    request.state.uproot_player = player

    with Session(sname) as session, contextlib.ExitStack() as stack:
        if player is not None:
            stack.enter_context(player)

        kwargs = {
            "request": request,
            "session": session,
        }
        if player is not None:
            kwargs["player"] = player

        result = await ensure_awaitable(
            u.APPS[appname].api2,
            **kwargs,
        )

        if isinstance(result, Response):
            return result
        else:
            return JSONResponse(result)
