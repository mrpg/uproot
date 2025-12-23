# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Optional


def forward(args: list[str], command: Optional[str] = None) -> None:
    main_path = Path(".") / "main.py"

    if not main_path.is_file():
        print("Error: 'main.py' not found in current directory.", file=sys.stderr)
        print("Are you in an uproot project directory?", file=sys.stderr)
        print("Create a new project with:", file=sys.stderr)
        print("\tuproot setup <project-name>", file=sys.stderr)
        sys.exit(1)

    cmd = [sys.executable, str(main_path)]

    if command:
        cmd.append(command)

    cmd.extend(args)
    sys.exit(subprocess.call(cmd))


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

        print("📂 A new project has been created in '" + path + "'.")
        print("✅ 'main.py' and some other files have been written.")
        print("🚶 Go to the new project directory by running")
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

    cmds = ["deployment", "dump", "examples", "new", "reset", "restore", "run"]

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
    elif args.command in cmds:
        forward(unknown, args.command)
    else:
        forward(sys.argv[1:])


if __name__ == "__main__":
    main()
