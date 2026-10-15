import random
import sys
from pathlib import Path

import pytest

uproot_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(uproot_src))

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.jobs as j
import uproot.queues as q
import uproot.storage as s
from uproot.jobs import try_group
from uproot.types import GroupCreatingWait, SynchronizingWait


@pytest.fixture
def session_with_two_players():
    d.DATABASE.reset()
    q.Q.clear()
    u.CONFIGS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with s.Session(sid) as session:
        pids = [c.create_player(session), c.create_player(session)]

    for pid in pids:
        q.register(tuple(pid))
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
        assert set(group._uproot_players) == set(pids)
        assert group.app == Wait.__module__
        assert group.after_grouping_ran is True

    for pid in pids:
        [queue] = q.Q[tuple(pid)]
        queued_id, queued = queue.get_nowait()
        assert queued_id is not None
        assert queued["event"] == "Grouped"
        assert queued["constraint"] == 0
        assert queued["data"] == gid


@pytest.mark.parametrize("group_on_poll", [False, True])
async def test_group_creating_wait_keeps_group_assigned_before_first_show(
    session_with_two_players, group_on_poll
):
    sid, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

        @classmethod
        def after_grouping(page, group):
            group.calls = group.get("calls", 0) + 1

    if group_on_poll:
        with s.Player(*pids[1]) as player:
            player.show_page = -1
        with s.Player(*pids[0]) as player:
            assert await Wait.show(player) is True
        with s.Player(*pids[1]) as player:
            player.show_page = 0

    with s.Player(*pids[0]) as player:
        if group_on_poll:
            assert await Wait.please_group(player) == ("submit", 1)
        else:
            assert await Wait.show(player) is False
        gid = player._uproot_group

    for pid in pids[1:] + pids:
        with s.Player(*pid) as player:
            assert await Wait.show(player) is False
            assert await Wait.please_group(player) == ("submit", 1)
            assert player._uproot_group == gid

    with s.Session(sid) as session:
        assert session._uproot_groups == [gid.gname]

    with s.Group(*gid) as group:
        assert group.calls == 1
        assert set(group._uproot_players) == set(pids)


@pytest.mark.parametrize("bulk_advance", [False, True])
async def test_group_creating_wait_groups_players_once_per_page(
    session_with_two_players, monkeypatch, bulk_advance
):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        extra_pids = [c.create_player(session) for unused in range(10)]

    for pid in extra_pids:
        q.register(tuple(pid))
    pids += extra_pids

    generator = random.Random(0)
    monkeypatch.setattr(j, "rng", lambda: generator)

    class Wait(GroupCreatingWait):
        group_size = 2

        @classmethod
        def after_grouping(page, group):
            group.calls = group.get("calls", 0) + 1

    previous_groups = set()

    for show_page in (2, 7):
        if bulk_advance:
            for pid in pids:
                with s.Player(*pid) as player:
                    player.show_page = show_page

        for pid in pids:
            with s.Player(*pid) as player:
                player.show_page = show_page
                await Wait.show(player)

        for pid in pids:
            with s.Player(*pid) as player:
                assert await Wait.please_group(player) == ("submit", 1)
                assert await Wait.show(player) is False

        with s.Session(sid) as session:
            current_groups = set(session._uproot_groups) - previous_groups

        assert len(current_groups) == len(pids) // Wait.group_size
        members = []

        for gname in current_groups:
            with s.Group(sid, gname) as group:
                assert len(group._uproot_players) == Wait.group_size
                assert group.calls == 1
                members.extend(group._uproot_players)

                for member in group.players:
                    assert member._uproot_group == group.gid

        assert len(members) == len(set(members)) == len(pids)
        assert set(members) == set(pids)
        previous_groups.update(current_groups)


async def test_try_group_ignores_players_on_other_page_at_same_show_page(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

    with s.Session(sid) as session:
        pids += [c.create_player(session), c.create_player(session)]

    for pid in pids[2:]:
        q.register(tuple(pid))

    # pids[1:] took a shorter Between branch, so their index 2 is Game, not
    # Wait. pids[1] and pids[2] were grouped at index 1. pids[3] has no group,
    # so only its page rules it out as a member for pids[0].
    for pid in pids:
        with s.Player(*pid) as player:
            player.show_page = 2

            if pid == pids[0]:
                player.page_order = ["app/A", "app/B", "app/Wait"]
            else:
                player.page_order = ["app/A", "app/Wait", "app/Game"]

    with s.Session(sid) as session:
        gid = c.create_group(session, pids[1:3])

    with s.Player(*pids[0]) as player:
        assert try_group(player, 2, Wait) is None
        assert await Wait.please_group(player) == ("wait", 0.5)

    for pid in pids[1:3]:
        with s.Player(*pid) as player:
            assert player._uproot_group == gid

    with s.Player(*pids[3]) as player:
        assert player._uproot_group is None
        assert "2:clear_group" not in player.get("_uproot_what_ran", ())


async def test_group_creating_wait_refreshes_player_fields_set_through_group_players(
    session_with_two_players,
):
    _, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

        @classmethod
        def after_grouping(page, group):
            for member in group.players:
                with member:
                    member.role = f"role{member.member_id}"

    with s.Player(*pids[0]) as player:
        assert await Wait.show(player) is False
        assert player.role == f"role{player.member_id}"


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


async def test_synchronizing_wait_refreshes_player_fields_set_through_group_players(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        c.create_group(session, pids, expected_size=2)

    class Wait(SynchronizingWait):
        @classmethod
        def all_here(page, group):
            for member in group.players:
                with member:
                    member.bonus = f"bonus{member.member_id}"

    with s.Player(*pids[0]) as player:
        assert await Wait.may_proceed(player) is True
        assert player.bonus == "bonus0"


async def test_synchronizing_wait_show_skips_page_and_notifies_waiters_when_ready(
    session_with_two_players,
):
    sid, pids = session_with_two_players

    with s.Session(sid) as session:
        c.create_group(session, pids, expected_size=2)

    q.Q.clear()
    queues = {tuple(pid): q.register(tuple(pid)) for pid in pids}

    with s.Player(*pids[1]) as player:
        player.show_page = -1

    class Wait(SynchronizingWait):
        pass

    with s.Player(*pids[0]) as player:
        assert await Wait.show(player) is True

    assert queues[tuple(pids[0])].empty()

    with s.Player(*pids[1]) as player:
        player.show_page = 0
        assert await Wait.show(player) is False

    for pid in pids:
        queued_id, queued = queues[tuple(pid)].get_nowait()
        assert queued_id is not None
        assert queued["event"] == "Synchronized"
        assert queued["constraint"] == 0
        assert queued["data"] is None


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

    class Wait(GroupCreatingWait):
        group_size = 0

    with (
        s.Player(*pids[0]) as player,
        pytest.raises(ValueError, match="Group size must be positive"),
    ):
        try_group(player, player.show_page, Wait)


def test_try_group_randomizes_members_and_order(session_with_two_players, monkeypatch):
    sid, pids = session_with_two_players

    class Wait(GroupCreatingWait):
        group_size = 2

    with s.Session(sid) as session:
        extra_pids = [c.create_player(session), c.create_player(session)]

    for pid in extra_pids:
        q.register(tuple(pid))
        with s.Player(*pid) as player:
            player.show_page = 0

    all_pids = pids + extra_pids
    sampled_pids = [all_pids[2], all_pids[0]]

    class StubRandom:
        def sample(self, population, *, k):
            assert k == 2
            assert population == all_pids
            return sampled_pids

    monkeypatch.setattr(j, "rng", StubRandom)

    with s.Player(*pids[0]) as player:
        gname = try_group(player, player.show_page, Wait)

    assert gname is not None
    with s.Group(sid, gname) as group:
        assert group._uproot_players == sampled_pids
