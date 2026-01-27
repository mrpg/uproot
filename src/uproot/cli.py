# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import os
import platform
import shutil
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import aiohttp
import click
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

        resource.setrlimit(
            resource.RLIMIT_NOFILE, (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        )
    except (OSError, ValueError, ModuleNotFoundError):
        try:
            hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
            resource.setrlimit(resource.RLIMIT_NOFILE, (hard_limit, hard_limit))
        except (OSError, ValueError):
            pass


async def get_examples(url: str, target_dir: str = "uproot-examples-master") -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            response.raise_for_status()

            zip_path = "temp.zip"
            with open(zip_path, "wb") as f:
                async for chunk in response.content.iter_chunked(8192):
                    f.write(chunk)

    try:
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
        Path(zip_path).unlink(missing_ok=True)


@click.group()
def cli() -> None:
    pass


# fmt: off
@click.command(help="Run this uproot project")
@click.option("--host", "-h", default="127.0.0.1", show_default="127.0.0.1", help="Host")
@click.option("--port", "-p", default=8000, show_default=8000, help="Port")
@click.option("--unsafe", default=False, is_flag=True, help="Run without admin authentication")
@click.pass_context
# fmt: on
def run(
    ctx: click.Context,
    host: str,
    port: int,
    unsafe: bool,
) -> None:
    d.HOST = host
    d.PORT = port
    d.UNSAFE = unsafe

    set_ulimit()

    uvicorn.run(
        "main:uproot_server",
        host=host,
        port=port,
        workers=1,  # must be 1
        **d.UVICORN_KWARGS,
    )


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
cli.add_command(reset)
cli.add_command(restore)
cli.add_command(run)
