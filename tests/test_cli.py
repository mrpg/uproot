# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import click
from click.testing import CliRunner

import uproot as u
import uproot.cli as uproot_cli
from uproot.services import config_service


def test_public_demo_warns(monkeypatch) -> None:
    monkeypatch.setattr(uproot_cli, "run_server", lambda host, port: None)

    result = CliRunner().invoke(
        uproot_cli.cli,
        ["run", "--unsafe", "--public-demo"],
        color=False,
    )

    assert result.exit_code == 0
    assert (
        "WARNING: --public-demo is only for hosting a public-facing demo. "
        "Do not use it during development."
    ) in result.output


def test_announcements_matches_status_page_messages(monkeypatch) -> None:
    data = {
        "recommendedVersion": u.__version__,
        "generalAnnouncement": "A general message.",
        "announcements": {u.__version__: "A version message."},
    }

    async def fetch_announcements():
        return data

    monkeypatch.setattr(config_service, "announcements", fetch_announcements)

    result = CliRunner().invoke(uproot_cli.cli, ["announcements"], color=True)

    assert result.exit_code == 0
    assert click.unstyle(result.output) == (
        f"You are running version {u.__version__}. "
        f"The current version is {u.__version__}.\n"
        "General announcement: A general message.\n"
        "Announcement for your version: A version message.\n"
    )
    assert (
        click.style("General announcement: A general message.", fg="green")
        in result.output
    )
    assert (
        click.style(
            "Announcement for your version: A version message.",
            fg="red",
            bold=True,
        )
        in result.output
    )
