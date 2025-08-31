# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import builtins
import os
import time
import traceback
import urllib.parse
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, ItemsView, Iterable, Optional, cast

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined
from pydantic import validate_call
from wtforms import Form as BaseForm

import uproot as u
import uproot.admin as a
import uproot.deployment as d
import uproot.i18n as i18n
import uproot.types as t
from uproot.constraints import ensure
from uproot.storage import Storage
from uproot.storage import within as s_within

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from fastapi.datastructures import FormData

BUILTINS = {
    fname: getattr(builtins, fname)
    for fname in dir(builtins)
    if callable(getattr(builtins, fname))
} | dict(
    within=s_within,
    along=s_within.along,
)

ENV = Environment(
    loader=i18n.TranslateLoader(
        ChoiceLoader(
            [
                FileSystemLoader(d.PATH),
                FileSystemLoader(
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "default")
                ),
            ]
        )
    ),
    autoescape=True,
    undefined=StrictUndefined,
    cache_size=250,
    auto_reload=True,
    enable_async=True,
)


def static_factory(realm: str = "_uproot") -> Callable[[str], str]:
    def localstatic(fname: str) -> str:
        last_mile = "/".join(urllib.parse.quote_plus(part) for part in fname.split("/"))
        return f"{d.ROOT}/static/{realm}/{last_mile}"

    return localstatic


def function_context(page: Optional[type[t.Page]]) -> dict[str, Any]:
    if page is not None:
        return dict(
            internal_static=static_factory(),
            static=static_factory(page.__module__),
            app=page.__module__,
        )
    else:
        return dict(
            internal_static=static_factory(),
        )


async def form_factory(page: type[t.Page], player: object) -> type[BaseForm]:
    fields = await t.optional_call(page, "fields", default_return=None, player=player)

    if fields is not None:
        return type("FormOnPage", (BaseForm,), fields)
    else:
        raise ValueError


def timeout_reached(page: type[t.Page], player: Storage, tol: float) -> bool:
    try:
        return cast(
            bool, time.time() + tol >= player._uproot_timeouts_until[player.show_page]
        )
    except (AttributeError, KeyError):
        pass

    return False


async def render(
    server: "FastAPI",
    request: "Request",
    player: Optional[Storage],
    page: type[t.Page],
    formdata: Optional[Any] = None,
    custom_errors: Optional[list[str]] = None,
    metadata: Optional[dict[str, Any]] = None,
    uauth: Optional[str] = None,
) -> str:
    ppath = truepath(page)

    if player is None:
        sname, uname, thisis, key, session = [None] * 5
    else:
        sname, uname, thisis, key, session = (
            player._uproot_session,
            player.name,
            player.show_page,
            player.key,
            player._uproot_session(),
        )

    data = a.from_cookie(uauth) if uauth else {"user": "", "token": ""}
    is_admin = (
        a.verify_auth_token(data.get("user", ""), data.get("token", "")) is not None
    )

    try:
        form = await form_factory(page, player)

        if formdata is None:
            if hasattr(page, "keep_values") and page.keep_values:
                form = form(obj=player)
            else:
                form = form()
        else:
            form = form(formdata)
            form.validate()
    except ValueError:
        form = None

    app = u.APPS[page.__module__] if page.__module__ in u.APPS else None
    language = await t.optional_call(
        app,  # TODO: or previous app
        "language",
        default_return=d.LANGUAGE,
        player=player,
    )

    internal = dict(
        _uproot_internal=dict(
            sname=sname,
            uname=uname,
            thisis=thisis,
            key=key,
            root=d.ROOT,
            language=language,
            is_admin=is_admin,
        )
        | (metadata if metadata is not None else {})
    )
    jsvars = (
        cast(
            dict[str, Any],
            await t.optional_call(page, "jsvars", default_return=dict(), player=player),
        )
        | internal
    )

    context = (
        cast(
            dict[str, Any],
            await t.optional_call(
                page, "context", default_return=dict(), player=player
            ),
        )
        | BUILTINS
        | dict(
            session=session,
            player=player,
            page=page,
            app=app,
            form=form,
            JSON_TERMS=i18n.json(cast(i18n.ISO639, language)),
            show2path=show2path,
            _uproot_errors=custom_errors,
            _uproot_js=jsvars,
            _uproot_testing=(is_admin or (session is not None and session.testing)),
        )
        | function_context(page)
        | internal
    )

    return await ENV.get_template(ppath).render_async(**context)


async def render_error(
    request: "Request",
    player: Storage,
    uauth: Optional[str],
    exc: Exception,
) -> str:
    sname, uname, session = (
        player._uproot_session,
        player.name,
        player._uproot_session(),
    )

    data = a.from_cookie(uauth) if uauth else {"user": "", "token": ""}
    is_admin = (
        a.verify_auth_token(data.get("user", ""), data.get("token", "")) is not None
    )

    internal = dict(
        _uproot_internal=dict(
            sname=sname,
            uname=uname,
            root=d.ROOT,
            language=d.LANGUAGE,
            is_admin=is_admin,
        ),
    )

    context = (
        BUILTINS
        | dict(
            JSON_TERMS=i18n.json(d.LANGUAGE),
            _uproot_errors=None,
            _uproot_js=internal,  # not a huge fan of this construction
        )
        | function_context(None)
        | internal
        | dict(
            player=player,
            session=session,
            show2path=show2path,
            _uproot_testing=(is_admin or (session is not None and session.testing)),
        )
    )

    # the following builds some info about the exception for admins

    if is_admin:
        tb_list = traceback.extract_tb(exc.__traceback__)

        stack_frames = []

        for frame in tb_list:
            stack_frames.append(
                dict(
                    filename=frame.filename,
                    function=frame.name,
                    lineno=frame.lineno,
                    code=frame.line,
                )
            )

        # Get local variables from the last frame (where error occurred)
        if exc.__traceback__ is not None:
            last_frame = exc.__traceback__.tb_frame
            local_vars = dict((k, repr(v)) for k, v in last_frame.f_locals.items())
        else:
            local_vars = dict()

        context |= dict(
            error_message=str(exc),
            exception_type=type(exc).__name__,
            traceback=traceback.format_exc(),
            stack_frames=stack_frames,
            local_vars=local_vars,
        )

    d.LOGGER.error(traceback.format_exc())

    return await ENV.get_template("InternalError.html").render_async(**context)


def truepath(page: type[t.Page]) -> str:
    if t.InternalPage in page.__mro__ and hasattr(page, "show") and not page.show:
        return f"#{page.__name__}"
    else:
        if not hasattr(page, "template"):
            return f"{page.__module__}/{page.__name__}.html"
        else:
            return page.template


def page2path(page: type[t.Page]) -> str:
    if t.InternalPage in page.__mro__:
        return f"#{page.__name__}"
    else:
        return f"{page.__module__}/{page.__name__}.html"


def path2page(path: str) -> type[t.Page]:
    target_page = u.PAGES[path]

    if isinstance(target_page, tuple):
        return cast(type[t.Page], getattr(u.APPS[target_page[0]], target_page[1]))
    else:
        return target_page


@validate_call
def show2path(page_order: list[str], show_page: int) -> str:
    if show_page == -1:
        return "Initialize.html"
    elif 0 <= show_page < len(page_order):
        return page_order[show_page]
    elif cast(str, len(page_order) == show_page):
        return "End.html"
    else:
        raise ValueError(show_page)


async def validate(
    page: type[t.Page], player: Storage, formdata: "FormData"
) -> tuple[Any, bool, list[str]]:
    form = None
    errors = []

    if hasattr(page, "fields"):
        form = (await form_factory(page, player))(formdata)

        if not form.validate():
            return form, False, []

        errors_from_page = cast(
            str | list[str],
            await t.optional_call(
                page,
                "validate",
                default_return=[],
                player=player,
                data=form.data,
            ),
        )

        if isinstance(errors_from_page, str):
            errors = [errors_from_page]
        else:
            ensure(isinstance(errors, list), TypeError, "Errors must be a list")
            errors = errors_from_page

    return form, not errors, errors


def verify_csrf(page: type[t.Page], player: Storage, formdata: "FormData") -> bool:
    base = f"{player._uproot_session}+{player.name}+{player.key}"

    return "_uproot_csrf" in formdata and formdata["_uproot_csrf"] == t.sha256(
        base.encode("utf-8")
    )


def to_filter(value: float, places: int) -> str:
    return f"{value:.{places}f}"


def unixtime2datetime_filter(epoch: float, precise: bool = False) -> str:
    dt = datetime.fromtimestamp(epoch)

    if precise:
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    else:
        return dt.strftime("%H:%M:%S.%f")[:-3]


def type_filter(x: Any) -> str:
    return str(type(x))


def history2items(it: Iterable[tuple[str, t.Value]]) -> ItemsView[str, list[t.Value]]:
    rval: dict[str, list[t.Value]] = dict()

    for field, value in it:
        if field not in rval:
            rval[field] = list()

        rval[field].append(value)

    return rval.items()


ENV.filters["to"] = to_filter
ENV.filters["unixtime2datetime"] = unixtime2datetime_filter
ENV.filters["history2items"] = history2items
ENV.filters["repr"] = repr
ENV.filters["type"] = type_filter
