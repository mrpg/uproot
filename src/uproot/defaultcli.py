# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from pathlib import Path

import click

import uproot as u
import uproot.examples as ex


@click.group(invoke_without_command=True)
@click.pass_context
@click.option("--version", is_flag=True, help="Show version information.")
@click.option("--copyright", is_flag=True, help="Show copyright information.")
def main(ctx: click.Context, version: bool, copyright: bool) -> None:
    if ctx.invoked_subcommand is None:
        if version:
            click.echo(f"uproot-science {u.__version__}")
        elif copyright:
            click.echo("uproot - A modern experimental framework")
            click.echo("(c) Max R. P. Grossmann, Holger Gerhardt, et al., 2025")
            click.echo("Full list of contributors: https://github.com/mrpg/uproot")
            click.echo()
            click.echo(
                "This is free software; you are free to change and redistribute it."
            )
            click.echo("There is NO WARRANTY, to the extent permitted by law.")
            click.echo("Licensed under LGPL-3.0-or-later. See LICENSE for details.")
            click.echo()
            click.echo("Use --help for more options")
        else:
            click.echo(ctx.get_help())


# fmt: off
@main.command()
@click.pass_context
@click.argument("path")
@click.option("--force", is_flag=True, help="Skip checks.")
@click.option("--no-example", is_flag=True, help="Don't create example app.")
# fmt: on
def setup(
    ctx: click.Context, path: str, force: bool = False, no_example: bool = False
) -> None:
    path_ = Path(path)

    if (path_ / "main.py").is_file() and not force:
        click.echo("'main.py' exists and --force not specified. Exiting.", err=True)
        ctx.exit(1)
    else:
        path_.mkdir(exist_ok=True)

        ex.setup_mere_project(path_)

        if not no_example:
            ex.setup_mere_app(path_)

        click.echo("📂 A new project has been created in '" + path + "'.")
        click.echo("✅ 'main.py' and some other files have been written.")
        click.echo("⬇️  Go to the new project directory by running")
        click.echo("\tcd " + path)
        click.echo("🔍 Get started by reading 'main.py'.")
        click.echo("🚀 Then you may run this project using")
        click.echo("\tpython main.py run")
        click.echo("🚨 On some systems, 'python3' must be used instead of 'python'.")
        click.echo("📰 The following commands provide additional information:")
        click.echo("\tpython main.py --help")
        click.echo("\tpython main.py run --help")
        click.echo("🤯 Help, docs & code can be found at https://uproot.science/")


if __name__ == "__main__":
    main()
