import random

import pytest

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot.pages import page2path
from uproot.server1 import (
    PageTransitionState,
    advance_to_next_visible_page,
    run_current_page_after_hooks,
    show_page,
)
from uproot.services import player_service as ps
from uproot.smithereens import Repeat, data_uri, move_to_end, move_to_page, rng
from uproot.stable import decode, encode


class Target(t.Page):
    pass


class GetRequest:
    method = "GET"
    app = None


async def render_name(app, request, player, page, *args):
    return page.__name__


def create_player() -> t.PlayerIdentifier:
    d.DATABASE.reset()
    u.CONFIGS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with s.Session(sid) as session:
        return c.create_player(session)


def test_rng_returns_random_instance():
    value = rng()

    assert isinstance(value, random.Random)


def test_rng_is_reexported_from_types():
    assert rng is t.rng


def test_rng_uses_fresh_seed():
    first = rng()
    second = rng()

    assert first.getstate() != second.getstate()


def test_rng_can_be_encoded_and_decoded():
    value = rng()
    encoded = encode(value)
    decoded = decode(encoded)

    assert isinstance(decoded, random.Random)
    assert value.getstate() == decoded.getstate()


def test_rng_is_in_star_imports():
    namespace = {}

    exec("from uproot.smithereens import *", namespace)  # noqa: S102

    assert namespace["rng"] is rng


def test_data_uri_detects_mp4_by_ftyp_box():
    payload = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00"

    assert data_uri(payload).startswith("data:video/mp4;base64,")


def test_move_to_page_skips_players_who_have_not_started():
    pid = create_player()

    move_to_page(s.Player(*pid), Target)

    with s.Player(*pid) as player:
        assert player.show_page == -1


def test_move_to_page_moves_players_forward():
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Target)]
        player.show_page = 0

    move_to_page(s.Player(*pid), Target, reload_=False)

    with s.Player(*pid) as player:
        assert player.show_page == 1


def test_move_to_end_moves_players_to_the_end():
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Target)]
        player.show_page = 0

    move_to_end(s.Player(*pid), reload_=False)

    with s.Player(*pid) as player:
        assert player.show_page == 2


@pytest.mark.parametrize("how", ["move_to_end", "put_to_end", "advance_by_one"])
async def test_players_put_at_the_end_leave_their_app(how):
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Target)]
        player.show_page = 1
        player.app = "test"

    if how == "move_to_end":
        move_to_end(s.Player(*pid), reload_=False)
    elif how == "put_to_end":
        await ps.put_to_end(pid.sname, [pid.uname])
    else:
        await ps.advance_by_one(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.show_page == len(player.page_order)
        assert player.app is None


async def test_advancing_players_within_their_page_order_keeps_their_app():
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Target), page2path(Target)]
        player.show_page = 1
        player.app = "test"

    await ps.advance_by_one(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.show_page == 2
        assert player.app == "test"


async def test_loading_the_end_page_runs_its_hook(monkeypatch):
    monkeypatch.setattr("uproot.server1.render", render_name)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First"]
        player.started = True
        player.app = "test"
        player.show_page = 1  # At the end without its hook having run

        assert await show_page(GetRequest(), player) == "End"
        assert player.app is None


async def test_repeat_does_not_intercept_move_to_page(monkeypatch):
    class Feedback(t.Page):
        @classmethod
        def after_once(page, player):
            player.add_round = False
            move_to_page(player, Target, reload_=False)

    for page in (Target, Feedback):
        monkeypatch.setitem(u.PAGES, page2path(page), page)

    pid = create_player()
    with s.Player(*pid) as player:
        player.page_order = [
            page2path(page) for page in c.expand([Repeat(Target, Feedback), Target])
        ]

    current = None
    for expected in (Target, Feedback, Target):
        with s.Player(*pid) as player:
            state = PageTransitionState(player.show_page, proceed=True)
            if current is not None:
                await run_current_page_after_hooks(current, player, state)
            current = await advance_to_next_visible_page(None, player, state)
            assert current is expected

    with s.Player(*pid) as player:
        assert player.show_page == len(player.page_order) - 1
        assert player.round == 1
