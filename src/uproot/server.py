# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import math
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
from urllib.parse import quote

import click
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
from uproot.services.auth import admin_password_salt, hash_admin_password
from uproot.storage import Admin
from uproot.types import (
    ensure_awaitable,
    optional_call,
)

MIN_PASSWORD_LENGTH: int = 5
ADMINS_PASSWORDS_HASHED: bool = False


def validate_admin_password_lengths() -> None:
    for user, pw in d.ADMINS.items():
        if isinstance(pw, str) and len(pw) < MIN_PASSWORD_LENGTH:
            d.LOGGER.critical(
                "Configured admin password is shorter than the minimum length"
            )
            raise SystemExit(1)


def normalize_admin_passwords() -> None:
    global ADMINS_PASSWORDS_HASHED

    if ADMINS_PASSWORDS_HASHED:
        return

    for user, pw in d.ADMINS.items():
        if isinstance(pw, str):
            d.ADMINS[user] = hash_admin_password(user, pw, admin_password_salt(user))

    ADMINS_PASSWORDS_HASHED = True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[Never]:
    d.DATABASE.ensure()
    load_database_into_memory()

    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(admin)
        j.restore(app, admin)
        nsessions = len(admin._uproot_sessions)

    if d.ORIGIN is None:
        d.ORIGIN = f"http://{d.HOST}:{d.PORT}"

    click.echo(
        f"This is {click.style(f'uproot {u.__version__}', bold=True)} "
        f"({click.style('https://uproot.science/', fg='bright_blue')})",
        err=True,
    )
    click.echo(
        f"{click.style('Server is running at', bold=True)} "
        f"{click.style(f'{d.ORIGIN}{d.ROOT}/', fg='bright_blue')}",
        err=True,
    )

    if d.PUBLIC_DEMO:
        announcement_reminder = (
            "REMINDER: Check for important announcements regularly with "
            "`uproot announcements`."
        )
    else:
        announcement_reminder = (
            "REMINDER: Check for important announcements regularly on the "
            "Status page in the admin area."
        )

    click.secho(
        announcement_reminder,
        fg="yellow",
        bold=True,
        err=True,
    )

    try:
        import setproctitle

        setproctitle.setproctitle(f"[uproot server @ {d.HOST}:{d.PORT}]")
    except Exception:  # nosec B110
        pass

    if (la := len(d.ADMINS)) == 1:
        click.echo("There is 1 admin.", err=True)
    else:
        click.echo(f"There are {la} admins.", err=True)

    if nsessions == 1:
        click.echo("There is 1 session.", err=True)
    else:
        click.echo(f"There are {nsessions} sessions.", err=True)

    if not d.UNSAFE and not ADMINS_PASSWORDS_HASHED:
        validate_admin_password_lengths()

    normalize_admin_passwords()

    if d.UNSAFE:
        click.echo(err=True)

        if d.PUBLIC_DEMO:
            click.secho(
                "WARNING: --public-demo is only for hosting a public-facing demo. "
                "Do not use it during development.",
                fg="yellow",
                bold=True,
                err=True,
            )
        else:
            click.secho(
                "!!! You are using unsafe mode. Only ever do so on localhost.",
                fg="red",
                bold=True,
                err=True,
            )

        click.echo(
            f"{click.style('Admin area:', bold=True)}\n\t"
            f"{click.style(f'{d.ORIGIN}{d.ROOT}/admin/', fg='bright_blue')}",
            err=True,
        )
        click.echo(err=True)
    else:
        if len(d.ADMINS) == 1 and "admin" in d.ADMINS and d.ADMINS["admin"] is ...:
            d.ensure_login_token()

            click.echo(err=True)
            click.secho(
                "You can securely log in through the URL below because you are using the\n"
                "default administrator ('admin') with an empty password (...). If you add\n"
                "more administrators, change admin's username or set a password, this\n"
                "message will no longer appear.",
                fg="bright_black",
                italic=True,
                err=True,
            )
            click.echo(err=True)

            click.echo(
                f"{click.style('Auto login:', bold=True)}\n\t"
                f"{click.style(f'{d.ORIGIN}{d.ROOT}/admin/login/#{d.LOGIN_TOKEN}', fg='bright_blue')}",
                err=True,
            )

            click.echo(err=True)

    if d.QUICK_ROOM is not None:
        room_url = f"{d.ORIGIN}{d.ROOT}/room/{quote(d.QUICK_ROOM, safe='')}/"
        click.echo(
            f"{click.style('Room:', bold=True)}\n\t"
            f"{click.style(room_url, fg='bright_blue')}",
            err=True,
        )
        click.echo(err=True)

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

    spawned = list(j.BACKGROUND_TASKS)

    for t_ in spawned:
        t_.cancel()

    await asyncio.gather(*spawned, return_exceptions=True)

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


if d.ROBOTS_TXT:

    @uproot_server.get("/robots.txt")
    async def robots(request: Request) -> PlainTextResponse:
        return PlainTextResponse(f"User-agent: *\nDisallow: {d.ROOT}/")


@validate_call(config={"arbitrary_types_allowed": True})
def load_config(
    server: FastAPI,
    config: str,
    apps: list[str],
    *,
    settings: Optional[dict[str, Any]] = None,
) -> None:
    ensure(not config.startswith("~"), ValueError, "Config path cannot start with '~'")

    if not hasattr(u, "APPS"):
        u.APPS = ModuleManager()

    u.CONFIGS[config] = []
    u.CONFIGS_EXTRA[config] = {
        "settings": settings or {},
    }

    for appname in apps:
        if appname not in u.APPS:
            u.APPS.import_module(appname)

        if f"~{appname}" not in u.CONFIGS:
            u.CONFIGS[f"~{appname}"] = [appname]

            sm = getattr(u.APPS[appname], "SUGGESTED_MULTIPLE", 1)

            u.CONFIGS_EXTRA[f"~{appname}"] = {
                "settings": {},
                "suggested_multiple": sm,
            }

        u.CONFIGS[config].append(appname)

    # Compute suggested_multiple as LCM of all apps' SUGGESTED_MULTIPLE constants
    suggested = 1

    for appname in u.CONFIGS[config]:
        sm = getattr(u.APPS[appname], "SUGGESTED_MULTIPLE", 1)

        if sm > 1:
            suggested = math.lcm(suggested, sm)

    u.CONFIGS_EXTRA[config]["suggested_multiple"] = suggested
