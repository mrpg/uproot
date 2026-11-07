# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import click
import pytest
from click.testing import CliRunner

import uproot as u
import uproot.cli as uproot_cli
from uproot.services import config_service


def test_announcements_matches_status_page_messages(monkeypatch) -> None:
    data = {
        "recommendedVersion": u.__version__,
        "generalAnnouncement": "A general message.",
        "versionIsCurrent": True,
        "versionAnnouncement": "A version message.",
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


def test_announcements_error(monkeypatch) -> None:
    async def fetch_announcements():
        return {"error": True}

    monkeypatch.setattr(config_service, "announcements", fetch_announcements)

    result = CliRunner().invoke(uproot_cli.cli, ["announcements"])

    assert result.exit_code == 1
    assert "We couldn't load announcements." in result.output


def test_version_is_current() -> None:
    assert config_service.version_is_current("1.2.3", "1.2.3")
    assert config_service.version_is_current("1.10", "1.9.5")
    assert not config_service.version_is_current("1.2", "1.2.1")
    assert not config_service.version_is_current("1.2.3rc1", "1.2.3")
    assert not config_service.version_is_current("0.1.0rc1", "0.2.0")
    assert not config_service.version_is_current("garbage", "0.1")


def test_run_uds_requires_origin(monkeypatch) -> None:
    monkeypatch.setattr(uproot_cli.d, "ORIGIN", None)
    monkeypatch.setattr(
        uproot_cli, "run_server", lambda *args: pytest.fail("server started")
    )

    result = CliRunner().invoke(uproot_cli.run, ["--uds", "/tmp/uproot.sock"])

    assert result.exit_code == 2
    assert "--uds requires UPROOT_ORIGIN" in result.output


def test_run_uds_rejects_host_and_port(monkeypatch) -> None:
    monkeypatch.setattr(uproot_cli.d, "ORIGIN", "https://example.com")
    monkeypatch.setattr(
        uproot_cli, "run_server", lambda *args: pytest.fail("server started")
    )

    for extra in (["--port", "8000"], ["-h", "127.0.0.1"]):
        result = CliRunner().invoke(
            uproot_cli.run, ["--uds", "/tmp/uproot.sock", *extra]
        )

        assert result.exit_code == 2
        assert "--uds cannot be combined with --host or --port" in result.output


def test_run_uds_starts_server_on_socket(monkeypatch) -> None:
    calls = []
    for name in ("HOST", "PORT", "UDS", "UNSAFE", "PUBLIC_DEMO"):
        monkeypatch.setattr(uproot_cli.d, name, getattr(uproot_cli.d, name))
    monkeypatch.setattr(uproot_cli.d, "ORIGIN", "https://example.com")
    monkeypatch.setattr(uproot_cli, "run_server", lambda *args: calls.append(args))

    result = CliRunner().invoke(uproot_cli.run, ["--uds", "/run/uproot/uproot.sock"])

    assert result.exit_code == 0, result.output
    assert calls == [("127.0.0.1", 8000, "/run/uproot/uproot.sock")]
    assert uproot_cli.d.UDS == "/run/uproot/uproot.sock"


def test_listener_kwargs() -> None:
    assert uproot_cli.listener_kwargs("0.0.0.0", 8080, None) == {
        "host": "0.0.0.0",
        "port": 8080,
    }
    assert uproot_cli.listener_kwargs("127.0.0.1", 8000, "/run/u.sock") == {
        "bind": ("unix:/run/u.sock",),
        "uds_permissions": 0o660,
    }
