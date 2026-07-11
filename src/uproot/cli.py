# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import os
import platform
import shutil
import sys
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Collection, Generator

import click
import httpx
import uvicorn

import uproot.deployment as d
import uproot.examples as ex

sys.argv[0] = "uproot"


@contextmanager
def confirmation(
    action: str, ctx: click.Context, yes: bool = False
) -> Generator[None, None, None]:
    """Context manager for dangerous operations requiring confirmation."""
    if not yes:
        user_says = input(f"Please type YES to {action}: ")

        if user_says != "YES":
            click.echo("Aborting.")
            if ctx:
                ctx.exit(1)
            else:
                sys.exit(1)

        for i in range(3):
            # We are nice
            print(f"{3-i}...")
            time.sleep(1)

    try:
        yield
    finally:
        if not yes:
            click.echo("Done.")


def set_ulimit() -> None:
    if platform.system() == "Windows":
        return

    try:
        import resource
    except ModuleNotFoundError:
        return

    try:
        resource.setrlimit(
            resource.RLIMIT_NOFILE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        )
    except (OSError, ValueError):
        try:
            hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard_limit, hard_limit))
        except (OSError, ValueError):
            pass


def configure_server(host: str, port: int, unsafe: bool, public_demo: bool) -> None:
    if public_demo and not unsafe:
        raise click.ClickException(
            "If you use --public-demo, you MUST also use --unsafe."
        )

    if public_demo:
        click.secho(
            "WARNING: --public-demo is only for hosting a public-facing demo. "
            "Do not use it during development.",
            fg="yellow",
            bold=True,
            err=True,
        )

    d.HOST = host
    d.PORT = port
    d.UNSAFE = unsafe
    d.PUBLIC_DEMO = public_demo


def run_server(host: str, port: int) -> None:
    set_ulimit()

    uvicorn.run(
        "main:uproot_server",
        host=host,
        port=port,
        workers=1,  # must be 1
        **d.UVICORN_KWARGS,
    )


def project_configs() -> list[str]:
    import uproot as u

    return sorted(config for config in u.CONFIGS if not config.startswith("~"))


def resolve_start_config(config_arg: str | None, config: str | None) -> str:
    if config_arg and config:
        raise click.ClickException(
            "Pass the config either as CONFIG or --config, not both."
        )

    selected_config = config or config_arg
    configs = project_configs()
    config_list = ", ".join(configs)

    if selected_config:
        if selected_config not in configs:
            if config_list:
                raise click.ClickException(
                    f"Unknown config {selected_config!r}. Available configs: {config_list}"
                )

            raise click.ClickException(f"Unknown config {selected_config!r}.")

        return selected_config

    if len(configs) == 1:
        return configs[0]

    if configs:
        raise click.ClickException(
            f"Multiple configs are loaded. Pass one explicitly: {config_list}"
        )

    raise click.ClickException("No project configs are loaded.")


def quick_room_number(roomname: str) -> int | None:
    if not roomname.startswith("quick"):
        return None

    suffix = roomname.removeprefix("quick")
    if not suffix.isdigit():
        return None

    return int(suffix)


def next_quick_roomname(roomnames: Collection[str]) -> str:
    highest = 0

    for roomname in roomnames:
        number = quick_room_number(roomname)

        if number is not None:
            highest = max(highest, number)

    return f"quick{highest + 1}"


def create_quick_room(config: str, simulate: bool) -> str:
    import uproot as u
    import uproot.core as c
    import uproot.jobs as j
    import uproot.rooms as r
    from uproot.cache import load_database_into_memory
    from uproot.storage import Admin, Session

    d.DATABASE.ensure()
    load_database_into_memory()

    with Admin() as admin:
        c.create_admin(admin)
        j.synchronize_rooms(admin)

        roomname = next_quick_roomname(admin.rooms)
        sid = c.create_session(
            admin,
            config,
            settings=u.CONFIGS_EXTRA.get(config, {}).get("settings", {}),
        )
        admin.rooms[roomname] = r.room(
            roomname,
            config=config,
            open=True,
            sname=sid.sname,
        )

    with Session(sid.sname) as session:
        session.room = roomname

        if simulate:
            session._uproot_simulate = True

    r.start(roomname)

    return roomname


async def get_examples(url: str, target_dir: str = "uproot-examples-master") -> None:
    zip_path = None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()

                with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
                    zip_path = f.name
                    async for chunk in response.aiter_bytes(8192):
                        f.write(chunk)

        if zip_path is None:
            raise RuntimeError("Failed to download ZIP archive")

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            all_files = zip_ref.namelist()

            readme_dirs = set()
            target_prefix = target_dir + "/"

            for file_path in all_files:
                if file_path.startswith(target_prefix) and file_path.endswith(
                    "README.md"
                ):
                    rel_path = file_path[len(target_prefix) :]
                    path_parts = rel_path.split("/")

                    if len(path_parts) == 2 and path_parts[1] == "README.md":
                        dir_name = path_parts[0]
                        readme_dirs.add(target_prefix + dir_name)

            for file_path in all_files:
                for readme_dir in readme_dirs:
                    if file_path.startswith(readme_dir + "/"):
                        rel_path = file_path[len(target_prefix) :]
                        target_path = Path(rel_path)

                        # Only create parent directory if the file is not at root level
                        if target_path.parent != Path("."):
                            target_path.parent.mkdir(parents=True, exist_ok=True)

                        # Skip if it's a directory entry
                        if not file_path.endswith("/"):
                            with zip_ref.open(file_path) as source:
                                with open(target_path, "wb") as target:
                                    shutil.copyfileobj(source, target)
                        break
    finally:
        if zip_path is not None:
            Path(zip_path).unlink(missing_ok=True)


@click.group()
def cli() -> None:
    pass


# fmt: off
@click.command(help="Run this uproot project")
@click.option("--host", "-h", default="127.0.0.1", show_default="127.0.0.1", help="Host")
@click.option("--port", "-p", default=8000, show_default=8000, help="Port")
@click.option("--unsafe", default=False, is_flag=True, help="Run without admin authentication")
@click.option("--public-demo", default=False, is_flag=True, help="Run a public demo (use with --unsafe)")
@click.pass_context
# fmt: on
def run(
    ctx: click.Context,
    host: str,
    port: int,
    unsafe: bool,
    public_demo: bool,
) -> None:
    configure_server(host, port, unsafe, public_demo)
    run_server(host, port)


# fmt: off
@click.command(help="Create and open a quick room, then run this uproot project")
@click.option("--host", "-h", default="127.0.0.1", show_default="127.0.0.1", help="Host")
@click.option("--port", "-p", default=8000, show_default=8000, help="Port")
@click.option("--unsafe", default=False, is_flag=True, help="Run without admin authentication")
@click.option("--public-demo", default=False, is_flag=True, help="Run a public demo (use with --unsafe)")
@click.option("--config", "-c", default=None, help="Config to start")
@click.option("--simulate", default=False, is_flag=True, help="Enable simulation for the quick room session")
@click.argument("config_arg", required=False, metavar="CONFIG")
@click.pass_context
# fmt: on
def start(
    ctx: click.Context,
    host: str,
    port: int,
    unsafe: bool,
    public_demo: bool,
    config: str | None,
    simulate: bool,
    config_arg: str | None,
) -> None:
    configure_server(host, port, unsafe, public_demo)
    selected_config = resolve_start_config(config_arg, config)
    d.QUICK_ROOM = create_quick_room(selected_config, simulate)
    run_server(host, port)


# fmt: off
@click.command(help="Reset database")
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
@click.pass_context
# fmt: on
def reset(ctx: click.Context, yes: bool) -> None:
    with confirmation("reset the database", ctx, yes):
        d.DATABASE.reset()
        d.DATABASE.close()


# fmt: off
@click.command(help="Dump database to file")
@click.option("--file", required=True, help="Output file.")
@click.pass_context
# fmt: on
def dump(ctx: click.Context, file: str) -> None:
    with open(file, "wb") as f:
        for chunk in d.DATABASE.dump():
            f.write(chunk)


# fmt: off
@click.command(help="Restore database from file")
@click.option("--file", required=True, help="Input file.")
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
@click.pass_context
# fmt: on
def restore(ctx: click.Context, file: str, yes: bool) -> None:
    with confirmation("reset the database", ctx, yes):
        d.DATABASE.reset()
        d.DATABASE.close()

    with open(file, "rb") as f:
        d.DATABASE.restore(f)

    if not yes:
        click.echo("Database was restored.")


# fmt: off
@click.command(help="Create new app")
@click.option("--minimal", is_flag=True, help="Create a minimal app.")
@click.argument("app")
@click.pass_context
# fmt: on
def new(ctx: click.Context, app: str, minimal: bool = False) -> None:
    if minimal:
        ex.new_minimal_app(Path("."), app)
    else:
        ex.new_prisoners_dilemma(Path("."), app)


# fmt: off
@click.command(help="Create new page in an app")
@click.argument("app")
@click.argument("page")
@click.pass_context
# fmt: on
def newpage(ctx: click.Context, app: str, page: str) -> None:
    ex.new_page(Path("."), app, page)


# fmt: off
@click.command(help="Download examples")
@click.pass_context
# fmt: on
def examples(ctx: click.Context) -> None:
    asyncio.run(
        get_examples(
            "https://github.com/mrpg/uproot-examples/archive/refs/heads/master.zip"
        )
    )


# fmt: off
@click.command(help="View deployment")
@click.pass_context
# fmt: on
def deployment(ctx: click.Context) -> None:
    for k, v in os.environ.items():
        if k.startswith("UPROOT"):
            click.echo(f"{k}={v}")


cli.add_command(deployment)
cli.add_command(dump)
cli.add_command(examples)
cli.add_command(new)
cli.add_command(newpage)
cli.add_command(reset)
cli.add_command(restore)
cli.add_command(run)
cli.add_command(start)
