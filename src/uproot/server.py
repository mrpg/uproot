# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from contextlib import asynccontextmanager
from sys import stderr
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Coroutine,
    Never,
    Optional,
    cast,
)

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import validate_call

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.jobs as j
from uproot.cache import load_database_into_memory
from uproot.constraints import ensure
from uproot.modules import ModuleManager
from uproot.pages import app_or_default, page2path
from uproot.server1 import router as router1
from uproot.server2 import router as router2
from uproot.server3 import router as router3
from uproot.storage import Admin, Storage
from uproot.types import InternalPage, Page, ensure_awaitable, optional_call

MIN_PASSWORD_LENGTH: int = 5


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Never]:
    d.DATABASE.ensure()
    load_database_into_memory()

    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(app, admin)
        j.restore(app, admin)

    if d.ORIGIN is None:
        d.ORIGIN = f"http://{d.HOST}:{d.PORT}"

    d.LOGGER.info(f"This is uproot {u.__version__} (https://uproot.science/)")
    d.LOGGER.info(f"Server is running at {d.ORIGIN}{d.ROOT}/")

    try:
        import setproctitle

        setproctitle.setproctitle(f"[uproot server @ {d.HOST}:{d.PORT}]")
    except Exception:  # nosec B110 - Optional feature, OK if setproctitle unavailable
        pass

    if (la := len(d.ADMINS)) == 1:
        d.LOGGER.info("There is 1 admin")
    else:
        d.LOGGER.info(f"There are {la} admins")

    for user, pw in d.ADMINS.items():
        if isinstance(pw, str):
            pw_length = len(pw)
            if pw_length < MIN_PASSWORD_LENGTH:
                # Password variable no longer in scope during logging
                d.LOGGER.error(
                    f"Password for admin {user!r} is shorter than "
                    f"the minimum length ({MIN_PASSWORD_LENGTH}): got {pw_length}"
                )

    if len(d.ADMINS) == 1 and "admin" in d.ADMINS and d.ADMINS["admin"] is ...:
        d.ensure_login_token()

        print(file=stderr)
        print(
            "You can securely log in through the URL below because you are using the\n"
            "default administrator ('admin') with an empty password (...). If you add\n"
            "more administrators, change admin's username or set a password, this\n"
            "message will no longer appear.",
            file=stderr,
        )
        print(file=stderr)

        print(
            "Auto login:\n\t",
            f"{d.ORIGIN}{d.ROOT}/admin/login/#{d.LOGIN_TOKEN}",
            file=stderr,
        )

        print(file=stderr)

    tasks = []

    for gj in j.GLOBAL_JOBS:
        tasks.append(
            asyncio.create_task(
                cast(Callable[..., Coroutine[None, None, Never]], gj)(app)
            )
        )

    if hasattr(u, "APPS"):
        u.APPS.start_watching()

        for uapp in u.APPS.modules:
            uapp = u.APPS[uapp]

            await ensure_awaitable(optional_call, uapp, "restart")  # Thanks, Mia!

    await d.lifespan_start(app, tasks)

    ...
    yield  # type: ignore[misc]
    ...

    await d.lifespan_stop(app, tasks)

    for t_ in tasks:
        t_.cancel()

    if hasattr(u, "APPS"):
        u.APPS.stop_watching()

    await asyncio.gather(*tasks)


uproot_server = FastAPI(
    lifespan=lifespan,
    redirect_slashes=False,
)

uproot_server.add_middleware(
    GZipMiddleware,
    minimum_size=2048,
    compresslevel=3,
)

uproot_server.include_router(router1)
uproot_server.include_router(router2)
uproot_server.include_router(router3)


@uproot_server.get("/favicon.ico")
async def favicon(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{d.ROOT}/static/_uproot/favicon.ico", status_code=301)


@uproot_server.get("/robots.txt")
async def robots(request: Request) -> PlainTextResponse:
    return PlainTextResponse(f"User-agent: *\nDisallow: {d.ROOT}/")


def post_app_import(app: Any) -> Any:
    appname = app.__name__

    ensure(
        not hasattr(app, "Constants"),
        AttributeError,
        f"Use 'C' instead of 'Constants' (app {appname})",
    )

    # Add landing page (if desired)
    if hasattr(app, "LANDING_PAGE") and app.LANDING_PAGE:
        ensure(
            not hasattr(app, "LandingPage")
            or getattr(app.LandingPage, "__injected__", False),
            TypeError,
            f"'LandingPage' is a reserved Page name (app {appname})",
        )

        class LandingPage(Page):
            __injected__ = True
            __module__ = appname
            template = app_or_default(app, "LandingPage.html")

            @classmethod
            async def before_always_once(page, player: Storage) -> None:
                player._uproot_part += 1

        app.LandingPage = (
            LandingPage  # This is not technically necessary, but good practice
        )
        app.page_order.insert(0, app.LandingPage)

    # AdminDigest is used by SessionDigest in the admin area
    ensure(
        not hasattr(app, "AdminDigest")
        or getattr(app.AdminDigest, "__injected__", False),
        TypeError,
        f"'AdminDigest' is a reserved Page name (app {appname})",
    )

    # Demarcate beginning of new app and set player.app
    ensure(
        not hasattr(app, "StartApp") or getattr(app.StartApp, "__injected__", False),
        TypeError,
        f"'StartApp' is a reserved Page name (app {appname})",
    )

    class StartApp(InternalPage):
        __injected__ = True
        __module__ = appname

        @classmethod
        def after_always_once(page, player: Storage) -> None:
            player.app = appname

    app.StartApp = StartApp
    app.page_order.insert(0, app.StartApp)

    # Validate that Wait pages don't use after_* methods (except after_grouping)
    for page in c.expand(app.page_order):
        # Check if this page derives from a class with "Wait" in its name
        is_wait_page = any("Wait" in base.__name__ for base in page.__mro__)

        if is_wait_page:
            forbidden_methods = [
                attr
                for attr in dir(page)
                if attr.startswith("after_")
                and attr != "after_grouping"
                and hasattr(page, attr)
                and callable(getattr(page, attr))
                and not attr.startswith("_")
            ]

            ensure(
                len(forbidden_methods) == 0,
                TypeError,
                f"Page '{page.__name__}' inherits from a Wait page and has forbidden after_* methods: "
                f"{', '.join(forbidden_methods)}. Wait pages should use 'all_here' for "
                f"group-wide initialization instead of 'after_once' or 'after_always_once'. "
                f"(app {appname})",
            )


@validate_call(config=dict(arbitrary_types_allowed=True))
def load_config(
    server: FastAPI,
    config: str,
    apps: list[str],
    *,
    multiple_of: int = 1,  # TODO: Rename
    settings: Optional[dict[str, Any]] = None,
) -> None:
    ensure(not config.startswith("~"), ValueError, "Config path cannot start with '~'")

    if not hasattr(u, "APPS"):
        u.APPS = ModuleManager(post_app_import)

    u.CONFIGS[config] = list()
    u.CONFIGS_PPATHS[config] = list()
    u.CONFIGS_EXTRA[config] = dict(
        multiple_of=multiple_of,
        settings=settings or {},
    )

    for appname in apps:
        first_add = False

        if appname not in u.APPS:
            app = u.APPS.import_module(appname)
        else:
            app = u.APPS[appname]

        if f"~{appname}" not in u.CONFIGS:
            first_add = True

            u.CONFIGS[f"~{appname}"] = [appname]
            u.CONFIGS_PPATHS[f"~{appname}"] = list()

        u.CONFIGS[config].append(appname)

        for page in c.expand(app.page_order):
            path = page2path(page)
            u.CONFIGS_PPATHS[config].append(path)

            if first_add:
                u.CONFIGS_PPATHS[f"~{appname}"].append(path)

            if path not in u.PAGES:
                if not hasattr(app, page.__name__):
                    # page is internal to uproot
                    u.PAGES[path] = page
                else:
                    # page comes from app and is subject to reload modification
                    u.PAGES[path] = appname, page.__name__
