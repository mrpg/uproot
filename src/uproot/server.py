# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from contextlib import asynccontextmanager
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
from uproot.constraints import ensure
from uproot.modules import ModuleManager
from uproot.pages import page2path
from uproot.server1 import router as router1
from uproot.server2 import router as router2
from uproot.server3 import router as router3
from uproot.storage import Admin


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Never]:
    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(app, admin)
        j.restore(app, admin)

    d.LOGGER.info(f"This is uproot {u.__version__} (https://uproot.science/)")
    d.LOGGER.info(f"Server is running at http://{d.HOST}:{d.PORT}{d.ROOT}/")
    d.LOGGER.info(f"Admin panel is at http://{d.HOST}:{d.PORT}{d.ROOT}/admin/")

    if (la := len(d.ADMINS)) == 1:
        d.LOGGER.info("There is 1 admin")
    else:
        d.LOGGER.info(f"There are {la} admins")

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
    return RedirectResponse(f"{d.ROOT}/static/uproot/favicon.ico", status_code=301)


@validate_call(config=dict(arbitrary_types_allowed=True))
def load_config(
    server: FastAPI, config: str, apps: list[str], extra: Optional[Any] = None
) -> None:
    ensure(not config.startswith("~"), ValueError, "Config path cannot start with '~'")

    if not hasattr(u, "APPS"):
        u.APPS = ModuleManager()

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
