# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional

import uproot as u
import uproot.examples as ex


def forward(args: list[str], command: Optional[str] = None) -> None:
    cmd = [sys.executable, str(Path(".") / "main.py")]

    if command:
        cmd.append(command)

    cmd.extend(args)
    sys.exit(subprocess.call(cmd))


def setup_command(path: str, force: bool = False, no_example: bool = False) -> None:
    path_ = Path(path)

    if (path_ / "main.py").is_file() and not force:
        print("'main.py' exists and --force not specified. Exiting.", file=sys.stderr)
        sys.exit(1)
    else:
        path_.mkdir(exist_ok=True)
        ex.setup_mere_project(path_)

        if not no_example:
            ex.setup_mere_app(path_)

        print("📂 A new project has been created in '" + path + "'.")
        print("✅ 'main.py' and some other files have been written.")
        print("⬇️  Go to the new project directory by running")
        print("\tcd " + path)
        print("📖 Get started by reading 'main.py'.")
        print("🚀 Then you may run this project using")
        print("\tuproot run")
        print("📰 The following command provides additional information:")
        print("\tuproot --help")
        print("🤯 Help, docs & code can be found at https://uproot.science/")


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

    parser = argparse.ArgumentParser(prog="uproot", add_help=False)
    parser.add_argument(
        "--version", action="store_true", help="Show version information."
    )
    parser.add_argument(
        "--copyright", action="store_true", help="Show copyright information."
    )
    parser.add_argument("--help", action="store_true", help="Show help.")

    subparsers = parser.add_subparsers(dest="command")

    setup_parser = subparsers.add_parser("setup", add_help=False)
    setup_parser.add_argument("path")
    setup_parser.add_argument("--force", action="store_true", help="Skip checks.")
    setup_parser.add_argument(
        "--no-example", action="store_true", help="Don't create example app."
    )

    for cmd in ["deployment", "dump", "new", "reset", "restore", "run"]:
        subparsers.add_parser(cmd, add_help=False)

    args, unknown = parser.parse_known_args()

    if args.version:
        print(f"uproot-science {u.__version__}")
    elif args.help:
        forward(sys.argv[1:])
    elif args.command == "setup":
        setup_command(args.path, args.force, args.no_example)
    elif args.command in ["deployment", "dump", "new", "reset", "restore", "run"]:
        forward(unknown, args.command)
    else:
        forward(sys.argv[1:])


if __name__ == "__main__":
    main()
