import sys
from pathlib import Path

import pytest

uproot_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(uproot_src))

import uproot as u  # noqa: E402
import uproot.types as t  # noqa: E402


@pytest.fixture
def clean_online_state():
    u.ONLINE.clear()
    u.ONLINE_SORTED.clear()
    yield
    u.ONLINE.clear()
    u.ONLINE_SORTED.clear()


def test_who_online_session_filter_skips_other_sessions(
    clean_online_state, monkeypatch
):
    player_a = t.PlayerIdentifier(sname="A", uname="alice")
    player_b = t.PlayerIdentifier(sname="B", uname="bob")

    u.ONLINE[player_a.sname][player_a.uname] = 100.0
    u.ONLINE[player_b.sname][player_b.uname] = 105.0
    u.ONLINE_SORTED.add((100.0, player_a))
    u.ONLINE_SORTED.add((105.0, player_b))
    monkeypatch.setattr(u, "time", lambda: 110.0)

    assert u.who_online(tolerance=30, sname="A") == {player_a}
