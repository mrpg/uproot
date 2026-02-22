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
from uproot.server1 import router as router1
from uproot.server2 import router as router2
from uproot.server3 import router as router3
from uproot.server4 import router as router4
from uproot.storage import Admin
from uproot.types import (
    ensure_awaitable,
    optional_call,
)

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

    if d.UNSAFE:
        print(file=stderr)

        if not d.PUBLIC_DEMO:
            print(
                "!!! You are using unsafe mode. Only ever do so on localhost.",
                file=stderr,
            )

        print(
            "Admin area:\n\t",
            f"{d.ORIGIN}{d.ROOT}/admin/",
            file=stderr,
        )
        print(file=stderr)
    else:
        for user, pw in d.ADMINS.items():
            if isinstance(pw, str):
                pw_length = len(pw)
                # Clear password from memory before logging to prevent accidental leakage
                pw = None  # type: ignore
                if pw_length < MIN_PASSWORD_LENGTH:
                    # Only logging non-sensitive metadata (length), not the actual password
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
uproot_server.include_router(router4)


@uproot_server.get("/favicon.ico")
async def favicon(request: Request) -> RedirectResponse:
    return RedirectResponse(f"{d.ROOT}/static/_uproot/favicon.ico", status_code=301)


@uproot_server.get("/robots.txt")
async def robots(request: Request) -> PlainTextResponse:
    return PlainTextResponse(f"User-agent: *\nDisallow: {d.ROOT}/")


@validate_call(config={"arbitrary_types_allowed": True})
def load_config(
    _server: FastAPI,
    config: str,
    apps: list[str],
    *,
    multiple_of: int = 1,  # TODO: Rename
    settings: Optional[dict[str, Any]] = None,
) -> None:
    ensure(not config.startswith("~"), ValueError, "Config path cannot start with '~'")

    if not hasattr(u, "APPS"):
        u.APPS = ModuleManager()

    u.CONFIGS[config] = []
    u.CONFIGS_EXTRA[config] = {
        "multiple_of": multiple_of,
        "settings": settings or {},
    }

    for appname in apps:
        if appname not in u.APPS:
            u.APPS.import_module(appname)

        if f"~{appname}" not in u.CONFIGS:
            u.CONFIGS[f"~{appname}"] = [appname]

        u.CONFIGS[config].append(appname)
