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
from fastapi.responses import RedirectResponse
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
from uproot.types import InternalPage, Page


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Never]:
    if not d.DATABASE.ensure():
        # This is the first time the DB is used when running a project
        d.FIRST_RUN = True

    load_database_into_memory()

    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(app, admin)
        j.restore(app, admin)

    d.LOGGER.info(f"This is uproot {u.__version__} (https://uproot.science/)")
    d.LOGGER.info(f"Server is running at http://{d.HOST}:{d.PORT}{d.ROOT}/")

    if (la := len(d.ADMINS)) == 1:
        d.LOGGER.info("There is 1 admin")
    else:
        d.LOGGER.info(f"There are {la} admins")

    if d.FIRST_RUN:
        print(file=stderr)
        print(
            "Since this is the first run, here are the admins' credentials.",
            file=stderr,
        )
        print("You can view and change them in 'main.py'.", file=stderr)
        print(file=stderr)

        for i, (user, pw) in enumerate(d.ADMINS.items(), 1):
            print(f"ADMIN {i}:")
            print(f"  Username: {user}", file=stderr)
            print(f"  Password: {pw}", file=stderr)

        print(file=stderr)

    tasks = []

    u.APPS.start_watching()

    for gj in j.GLOBAL_JOBS:
        tasks.append(
            asyncio.create_task(
                cast(Callable[..., Coroutine[None, None, Never]], gj)(app)
            )
        )

    await d.lifespan_start(app, tasks)

    ...
    yield  # type: ignore[misc]
    ...

    await d.lifespan_stop(app, tasks)

    for t_ in tasks:
        t_.cancel()

    u.APPS.stop_watching()

    await asyncio.gather(*tasks)


uproot_server = FastAPI(
    lifespan=lifespan,
    redirect_slashes=False,
)

uproot_server.include_router(router1)
uproot_server.include_router(router2)
uproot_server.include_router(router3)


@uproot_server.get("/favicon.ico")
async def favicon(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{d.ROOT}/static/_uproot/favicon.ico", status_code=301)


def post_app_import(app: Any) -> Any:
    appname = app.__name__

    ensure(
        not hasattr(app, "C") or isinstance(app.C, type),
        TypeError,
        f"'C' must be a class (app {appname})",
    )
    ensure(
        not hasattr(app, "Constants"),
        TypeError,
        f"Use 'C' instead of 'Constants' (app {appname})",
    )

    # Add landing page (if desired)
    if hasattr(app, "LANDING_PAGE") and app.LANDING_PAGE:
        ensure(
            not hasattr(app, "LandingPage"),
            TypeError,
            f"'LandingPage' is a reserved Page name (app {appname})",
        )

        class LandingPage(Page):
            __module__ = appname
            template = app_or_default(app, "LandingPage.html")

            @classmethod
            async def before_always_once(page, player: Storage) -> None:
                player._uproot_part += 1

        app.LandingPage = (
            LandingPage  # This is not technically necessary, but good practice
        )
        app.page_order.insert(0, app.LandingPage)

    # Demarcate beginning of new app and set player.app
    ensure(
        not hasattr(app, "NextApp"),
        TypeError,
        f"'NextApp' is a reserved Page name (app {appname})",
    )

    class NextApp(InternalPage):
        __module__ = appname

        @classmethod
        def after_always_once(page, player: Storage) -> None:
            player.app = appname

    app.NextApp = NextApp
    app.page_order.insert(0, app.NextApp)


@validate_call(config=dict(arbitrary_types_allowed=True))
def load_config(
    server: FastAPI, config: str, apps: list[str], extra: Optional[Any] = None
) -> None:
    ensure(not config.startswith("~"), ValueError, "Config path cannot start with '~'")

    if not hasattr(u, "APPS"):
        u.APPS = ModuleManager(post_app_import)

    u.CONFIGS[config] = list()
    u.CONFIGS_PPATHS[config] = list()
    u.CONFIGS_EXTRA[config] = extra

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
            u.CONFIGS_EXTRA[f"~{appname}"] = extra

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
