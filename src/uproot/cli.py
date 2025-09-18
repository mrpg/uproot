# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import os
import platform
import sys
import time
from pathlib import Path

import click
import uvicorn

import uproot.deployment as d
import uproot.examples as ex

sys.argv[0] = "uproot"


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


def do_reset(ctx: click.Context, yes: bool) -> None:
    if not yes:
        user_says = input("Please type YES to reset the database: ")

        if user_says != "YES":
            click.echo("Aborting.")
            ctx.exit(1)

        for i in range(3):
            # we are nice
            print(f"{3-i}...")
            time.sleep(1)

    d.DATABASE.reset()
    d.DATABASE.close()

    if not yes:
        click.echo("Database was reset.")


@click.group()
def cli() -> None:
    pass


# fmt: off
@click.command(help="Run this uproot project")
@click.option("--host", "-h", default="127.0.0.1", show_default="127.0.0.1", help="Host")
@click.option("--port", "-p", default=8000, show_default=8000, help="Port")
@click.pass_context
# fmt: on
def run(ctx: click.Context, host: str, port: int) -> None:
    d.HOST = host
    d.PORT = port

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
    return do_reset(ctx, yes)


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
    do_reset(ctx, yes)

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
@click.command(help="View deployment")
@click.pass_context
# fmt: on
def deployment(ctx: click.Context) -> None:
    for k, v in os.environ.items():
        if k.startswith("UPROOT"):
            click.echo(f"{k}={v}")


cli.add_command(deployment)
cli.add_command(dump)
cli.add_command(reset)
cli.add_command(restore)
cli.add_command(run)
cli.add_command(new)
