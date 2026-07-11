# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from click.testing import CliRunner

import uproot.cli as uproot_cli


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
