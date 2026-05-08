import sys
from pathlib import Path

import pytest

uproot_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(uproot_src))

import uproot as u  # noqa: E402
import uproot.core as c  # noqa: E402
import uproot.deployment as d  # noqa: E402
import uproot.storage as s  # noqa: E402
from uproot.jobs import try_group  # noqa: E402
from uproot.types import GroupCreatingWait, SynchronizingWait  # noqa: E402


@pytest.fixture
def session_with_two_players():
    d.DATABASE.reset()
    u.CONFIGS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with s.Session(sid) as session:
        pids = [c.create_player(session), c.create_player(session)]

    for pid in pids:
        with s.Player(*pid) as player:
            player.show_page = 0

    return sid, pids


async def test_group_creating_wait_refreshes_player_and_runs_after_grouping(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

        @classmethod
        def after_grouping(page, group):
            group.after_grouping_ran = True

    with s.Player(*pids[0]) as player:
        assert await Wait.show(player) is False
        assert player._uproot_group is not None
        gid = player._uproot_group

    with s.Group(sid, gid.gname) as group:
        assert group._uproot_players == pids
        assert group.app == Wait.__module__
        assert group.after_grouping_ran is True


async def test_group_creating_wait_does_not_overwrite_app_set_by_after_grouping(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

        @classmethod
        def after_grouping(page, group):
            group.app = "custom_app"

    with s.Player(*pids[0]) as player:
        assert await Wait.show(player) is False
        gid = player._uproot_group

    with s.Group(sid, gid.gname) as group:
        assert group.app == "custom_app"


def test_group_creating_wait_rejects_async_after_grouping():
    with pytest.raises(TypeError, match="after_grouping must not be async"):

        class Wait(GroupCreatingWait):
            group_size = 2

            @classmethod
            async def after_grouping(page, group):
                pass


def test_synchronizing_wait_rejects_async_all_here():
    with pytest.raises(TypeError, match="all_here must not be async"):

        class Wait(SynchronizingWait):
            @classmethod
            async def all_here(page, group):
                pass


def test_create_group_does_not_append_group_when_member_validation_fails(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        c.create_group(session, [pids[0], pids[1]], gname="first")

    with s.Session(sid) as session:
        with pytest.raises(RuntimeError, match="Player already belongs to a group"):
            c.create_group(session, [pids[0]], gname="second")

        assert session._uproot_groups == ["first"]


def test_create_group_expected_size_mismatch_fails_before_append(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        with pytest.raises(ValueError, match="Expected group of size 3, got 2"):
            c.create_group(session, pids, gname="bad", expected_size=3)

        assert session._uproot_groups == []


def test_create_group_duplicate_member_fails_before_append(session_with_two_players):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        with pytest.raises(ValueError, match="Group members must be unique"):
            c.create_group(session, [pids[0], pids[0]], expected_size=2)

        assert session._uproot_groups == []

    with s.Player(*pids[0]) as player:
        assert player._uproot_group is None


def test_try_group_rejects_nonpositive_group_size(session_with_two_players):
    _, pids = session_with_two_players

    with s.Player(*pids[0]) as player:
        with pytest.raises(ValueError, match="Group size must be positive"):
            try_group(player, player.show_page, 0)
