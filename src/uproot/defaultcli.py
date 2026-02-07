# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Optional

import aiohttp
import orjson


def is_uv() -> bool:
    """Detect if we're running under uv."""
    return "UV_VIRTUAL_ENV" in os.environ or "UV" in os.environ


def forward(args: list[str], command: Optional[str] = None) -> None:
    main_path = Path(".") / "main.py"

    if not main_path.is_file():
        print("Error: 'main.py' not found in current directory.", file=sys.stderr)
        print("Are you in an uproot project directory?", file=sys.stderr)
        print("Create a new project with:", file=sys.stderr)
        print("\tuproot setup <project-name>", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, str(Path(".").resolve()))

    sys.argv = ["uproot"]
    if command:
        sys.argv.append(command)
    sys.argv.extend(args)

    import main as _  # noqa: F401

    from uproot.cli import cli

    cli()


def show_help() -> None:
    print("Usage: uproot [OPTIONS] COMMAND [ARGS]...")
    print()
    print("Options:")
    print("  --version    Show version information")
    print("  --copyright  Show copyright information")
    print("  --help       Show this message")
    print()
    print("Commands:")
    print("  setup        Create a new uproot project")
    print("  api          Access the Admin REST API")
    print()
    print("Project commands (require main.py in current directory):")
    print("  run          Run this uproot project")
    print("  reset        Reset database")
    print("  dump         Dump database to file")
    print("  restore      Restore database from file")
    print("  new          Create new app")
    print("  examples     Download examples")
    print("  deployment   View deployment")
    print()
    print("For more help on a specific command, run:")
    print("\tuproot <command> --help")


def setup_command(
    path: str, force: bool = False, no_example: bool = False, minimal: bool = False
) -> None:
    import uproot.examples as ex

    path_ = Path(path)

    if (path_ / "main.py").is_file() and not force:
        print("'main.py' exists and --force not specified. Exiting.", file=sys.stderr)
        sys.exit(1)
    else:
        path_.mkdir(exist_ok=True)
        ex.setup_empty_project(path_, minimal)

        if not no_example:
            if minimal:
                ex.new_minimal_app(path_)
            else:
                ex.new_prisoners_dilemma(path_)

        run_prefix = "uv run " if is_uv() else ""

        print("📂 A new project has been created in '" + path + "'.")
        print("✅ 'main.py' and some other files have been written.")
        print("🚶 Go to the new project directory by running")
        print("\tcd " + path)
        print("📖 Get started by reading 'main.py'.")
        print("🚀 Then you may run this project using")
        print("\t" + run_prefix + "uproot run")
        print("📰 The following command provides additional information:")
        print("\t" + run_prefix + "uproot --help")
        print("🤯 Help, docs & code can be found at https://uproot.science/")


async def api_request(
    base_url: str,
    version: int,
    auth: str,
    method: str,
    endpoint: str,
    data: Optional[dict[str, Any]] = None,
) -> tuple[int, Any]:
    """Make an API request to the admin API."""
    base_url = base_url.rstrip("/")
    endpoint = endpoint.strip("/")
    url = f"{base_url}/admin/api/v{version}/{endpoint}/"
    headers = {
        "Authorization": f"Bearer {auth}",
        "User-Agent": "uproot-cli",
    }

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


def api_command(
    url: str,
    version: int,
    auth: str,
    method: str,
    data: Optional[str],
    endpoint: str,
) -> None:
    """Access the Admin REST API."""
    parsed_data = None
    if data:
        try:
            parsed_data = orjson.loads(data)
        except orjson.JSONDecodeError as e:
            print(f"Error: Invalid JSON data: {e}", file=sys.stderr)
            sys.exit(1)

    try:
        status, result = asyncio.run(
            api_request(url, version, auth, method.upper(), endpoint, parsed_data)
        )
    except aiohttp.ClientError as e:
        print(f"Error: Connection failed: {e}", file=sys.stderr)
        sys.exit(1)

    if isinstance(result, (dict, list)):
        print(orjson.dumps(result, option=orjson.OPT_INDENT_2).decode())
    else:
        print(result)

    if status >= 400:
        sys.exit(1)


def main() -> None:
    if len(sys.argv) == 1:
        print("uproot - A modern experimental framework")
        print("(c) Max R. P. Grossmann, Holger Gerhardt, et al., 2025")
        print("Full list of contributors: https://github.com/mrpg/uproot")
        print()
        print("This is free software; you are free to change and redistribute it.")
        print("There is NO WARRANTY, to the extent permitted by law.")
        print("Licensed under LGPL-3.0-or-later. See LICENSE for details.")
        print()
        print("Use --help for more options")
        return

    cmds = [
        "deployment",
        "dump",
        "examples",
        "new",
        "newpage",
        "reset",
        "restore",
        "run",
    ]

    parser = argparse.ArgumentParser(prog="uproot", add_help=False)
    parser.add_argument(
        "--version", action="store_true", help="Show version information."
    )
    parser.add_argument(
        "--copyright", action="store_true", help="Show copyright information."
    )
    parser.add_argument("--help", action="store_true", help="Show help.")

    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser("setup", help="Create a new uproot project")
    setup_parser.add_argument("path", help="Path to the new project directory")
    setup_parser.add_argument("--force", action="store_true", help="Skip checks.")
    setup_parser.add_argument(
        "--minimal", action="store_true", help="Create a minimal example app."
    )
    setup_parser.add_argument(
        "--no-example", action="store_true", help="Don't create example app."
    )

    api_parser = subparsers.add_parser(
        "api",
        help="Access the Admin REST API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Access the Admin REST API.",
        epilog="""\
Examples:
  uproot api sessions                          # List sessions
  uproot api sessions/mysession                # Get session details
  uproot api rooms                             # List rooms
  uproot api configs                           # List configurations
  uproot api sessions/mysession/players        # Get players
  uproot api sessions/mysession/players/online # Get online players

  uproot api -X POST sessions -d '{"config":"myconfig","n_players":4}'
  uproot api -X PATCH sessions/mysession/active
  uproot api -X POST sessions/mysession/players/advance -d '{"unames":["ABC"]}'

For HTTPS or non-default servers:
  uproot api -u https://example.com/ sessions
  uproot api -u https://example.com/mysubdir/ sessions
""",
    )
    api_parser.add_argument(
        "--url",
        "-u",
        default="http://127.0.0.1:8000/",
        help="Server base URL (default: http://127.0.0.1:8000/)",
    )
    api_parser.add_argument(
        "--auth",
        "-a",
        default=os.environ.get("UPROOT_API_KEY"),
        help="Bearer token (or set UPROOT_API_KEY)",
    )
    api_parser.add_argument(
        "--method", "-X", default="GET", help="HTTP method (default: GET)"
    )
    api_parser.add_argument(
        "--data", "-d", default=None, help="JSON data for request body"
    )
    api_parser.add_argument("endpoint", help="API endpoint")

    for cmd in cmds:
        subparsers.add_parser(cmd, add_help=False)

    args, unknown = parser.parse_known_args()

    if args.version:
        import uproot as u

        print(f"uproot-science {u.__version__}")
    elif args.help:
        show_help()
    elif args.command == "setup":
        setup_command(args.path, args.force, args.no_example, args.minimal)
    elif args.command == "api":
        if not args.auth:
            print(
                "Error: --auth/-a is required (or set UPROOT_API_KEY)", file=sys.stderr
            )
            sys.exit(1)
        api_command(
            args.url,
            1,
            args.auth,
            args.method,
            args.data,
            args.endpoint,
        )
    elif args.command in cmds:
        forward(unknown, args.command)
    else:
        forward(sys.argv[1:])


if __name__ == "__main__":
    main()
