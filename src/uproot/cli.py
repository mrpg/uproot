# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

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
    if public_demo and not unsafe:
        raise RuntimeError("If you use --public-demo, you MUST also use --unsafe.")

    d.HOST = host
    d.PORT = port
    d.UNSAFE = unsafe
    d.PUBLIC_DEMO = public_demo

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


async def api_request(
    base_url: str,
    auth: str,
    method: str,
    endpoint: str,
    data: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    """Make an API request to the admin API."""
    base_url = base_url.rstrip("/")
    endpoint = endpoint.strip("/")
    url = f"{base_url}/admin/api/{endpoint}/"
    headers = {"Authorization": f"Bearer {auth}"}

    async with aiohttp.ClientSession() as session:
        kwargs: dict[str, Any] = {"headers": headers}
        if data is not None:
            kwargs["json"] = data

        async with session.request(method, url, **kwargs) as response:
            try:
                result = await response.json()
            except aiohttp.ContentTypeError:
                result = await response.text()
            return response.status, result


# fmt: off
@click.command(help="Access the Admin REST API")
@click.option("--url", "-u", default="http://127.0.0.1:8000/", show_default="http://127.0.0.1:8000/", help="Server base URL")
@click.option("--auth", "-a", envvar="UPROOT_API_KEY", required=True, help="Bearer token (or set UPROOT_API_KEY)")
@click.option("--method", "-X", default="GET", show_default="GET", help="HTTP method")
@click.option("--data", "-d", default=None, help="JSON data for request body")
@click.argument("endpoint")
@click.pass_context
# fmt: on
def api(
    ctx: click.Context,
    url: str,
    auth: str,
    method: str,
    data: Optional[str],
    endpoint: str,
) -> None:
    """
    Access the Admin REST API.

    \b
    Examples:
      uproot api sessions                          # List sessions
      uproot api sessions/mysession                # Get session details
      uproot api rooms                             # List rooms
      uproot api configs                           # List configurations
      uproot api sessions/mysession/players        # Get players
      uproot api sessions/mysession/players/online # Get online players

    \b
      uproot api -X POST sessions -d '{"config":"myconfig","n_players":4}'
      uproot api -X PATCH sessions/mysession/active
      uproot api -X POST sessions/mysession/players/advance -d '{"unames":["ABC"]}'

    \b
    For HTTPS or non-default servers:
      uproot api -u https://example.com/ sessions
      uproot api -u https://example.com/mysubdir/ sessions
    """
    parsed_data = None
    if data:
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError as e:
            click.echo(f"Error: Invalid JSON data: {e}", err=True)
            ctx.exit(1)

    try:
        status, result = asyncio.run(
            api_request(url, auth, method.upper(), endpoint, parsed_data)
        )
    except aiohttp.ClientError as e:
        click.echo(f"Error: Connection failed: {e}", err=True)
        ctx.exit(1)

    if isinstance(result, dict) or isinstance(result, list):
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(result)

    if status >= 400:
        ctx.exit(1)


cli.add_command(api)
cli.add_command(deployment)
cli.add_command(dump)
cli.add_command(examples)
cli.add_command(new)
cli.add_command(newpage)
cli.add_command(reset)
cli.add_command(restore)
cli.add_command(run)
