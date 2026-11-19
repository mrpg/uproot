import sys
from collections import defaultdict

import pytest
from sortedcontainers import SortedList

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.queues as q
import uproot.storage as s
import uproot.types as t
from uproot import server1
from uproot.pages import page2path
from uproot.server1 import leave, visit
from uproot.services import player_service as ps
from uproot.smithereens import Between, RandomOrder, Repeat, watch_for_dropout


class First(t.Page):
    pass


class Second(t.Page):
    pass


class Chosen(t.Page):
    pass


class Dropped(t.Page):
    pass


class Again(t.Page):
    @classmethod
    def after_once(page, player):
        player.add_round = True


class DeterministicRng:
    def shuffle(self, groups):
        groups.reverse()

    def choice(self, groups):
        return groups[0]


async def count_dropout(player):
    player.dropout_calls += 1


def new_player(player):
    player.new_player_calls = player.get("new_player_calls", 0) + 1
    player.dropout_calls = 0
    watch_for_dropout(player, count_dropout)


def page_order(player):
    player.page_order_calls = player.get("page_order_calls", 0) + 1

    return [RandomOrder(First, Second), Between(Chosen, Dropped), Repeat(Again)]


ADMIN_ACTIONS = [ps.mark_dropout, ps.run_new_player]


@pytest.fixture
def pid(monkeypatch):
    d.DATABASE.reset()
    monkeypatch.setattr(u, "ONLINE", defaultdict(dict))
    monkeypatch.setattr(u, "ONLINE_SORTED", SortedList())
    monkeypatch.setattr(u, "WATCH", set())
    monkeypatch.setattr(u, "MANUAL_DROPOUTS", set())
    monkeypatch.setattr(u, "APPS", {__name__: sys.modules[__name__]}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"initialization-test": [__name__]})
    monkeypatch.setattr(q, "Q", {})
    monkeypatch.setattr("uproot.smithereens.rng", DeterministicRng)

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "initialization-test")

    with s.Session(sid) as session:
        return c.create_player(session)


async def start_and_reach_second_iteration(pid):
    with s.Player(*pid) as player:
        player.started = True
        server1.initialize(player)
        display = await visit(None, player, 0, again=True)

        for expected in (Second, First, Chosen, Again):
            assert display.page is expected
            display = await leave(None, player, player.show_page, display.page)

        assert display.page is Again
        assert player.page_order.index(page2path(Second)) < player.page_order.index(
            page2path(First)
        )
        assert page2path(Dropped) not in player.page_order
        assert player.page_order.count(page2path(Again)) == 2

        return list(player.page_order), player.show_page


@pytest.mark.parametrize("admin_action", ADMIN_ACTIONS)
async def test_admin_actions_keep_the_page_order_of_started_players(pid, admin_action):
    page_order_before, show_page_before = await start_and_reach_second_iteration(pid)

    await admin_action(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.page_order == page_order_before
        assert player.show_page == show_page_before


@pytest.mark.parametrize("admin_action", ADMIN_ACTIONS)
async def test_admin_actions_do_not_initialize_started_players_again(pid, admin_action):
    await start_and_reach_second_iteration(pid)

    await admin_action(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.new_player_calls == 1
        assert player.page_order_calls == 1


@pytest.mark.parametrize("admin_action", ADMIN_ACTIONS)
async def test_admin_actions_initialize_players_who_have_not_started(pid, admin_action):
    await admin_action(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player._uproot_initialized is True
        assert player.new_player_calls == 1
        assert player.page_order_calls == 1
        assert page2path(Chosen) in player.page_order
        assert page2path(Dropped) in player.page_order


async def test_marking_players_who_have_not_started_runs_their_dropout_handlers(pid):
    await ps.mark_dropout(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.dropout_calls == 1
        assert player._uproot_dropout is True
        assert player._uproot_watch == []


@pytest.mark.parametrize("admin_action", ADMIN_ACTIONS)
async def test_players_initialized_by_admins_get_their_page_order_when_they_start(
    pid, admin_action
):
    await admin_action(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        player.started = True
        server1.initialize(player)

        assert player.new_player_calls == 1
        assert player.page_order_calls == 2


def failing_page_order(player):
    raise RuntimeError("page_order failed")


@pytest.mark.parametrize("admin_action", ADMIN_ACTIONS)
async def test_failing_page_order_is_retried_without_running_new_player_again(
    pid, monkeypatch, admin_action
):
    working_page_order = page_order
    this_module = sys.modules[__name__]
    monkeypatch.setattr(this_module, "page_order", failing_page_order)

    with pytest.raises(RuntimeError, match="page_order failed"):
        await admin_action(pid.sname, [pid.uname])

    monkeypatch.setattr(this_module, "page_order", working_page_order)
    await admin_action(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.new_player_calls == 1
        assert player.page_order_calls == 1
        assert page2path(Chosen) in player.page_order
