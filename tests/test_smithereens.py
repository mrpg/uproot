import asyncio
import random

import pytest

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot.data import latest
from uproot.pages import page2path, path2page
from uproot.server1 import (
    PageTransitionState,
    advance_to_next_visible_page,
    run_current_page_after_hooks,
    show_page,
)
from uproot.services import player_service as ps
from uproot.services.data_service import data_rows_for_session
from uproot.smithereens import (
    INTERNAL_PAGES,
    Between,
    Random,
    Repeat,
    Rounds,
    check_blocks,
    data_uri,
    move_to_end,
    move_to_page,
    rng,
    round_position,
)
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


def grouped_player_rows(player: s.Storage, grouping: list[str]) -> list[dict]:
    sname = t.identify(player).sname
    rows = latest(data_rows_for_session(sname, filters=True), grouping)

    return [row for row in rows if row["!storage"].startswith("player/")]


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
        player.block, player.round_nested, player.round = "a", [2], 2

    if how == "move_to_end":
        move_to_end(s.Player(*pid), reload_=False)
    elif how == "put_to_end":
        await ps.put_to_end(pid.sname, [pid.uname])
    else:
        await ps.advance_by_one(pid.sname, [pid.uname])

    with s.Player(*pid) as player:
        assert player.show_page == len(player.page_order)
        assert player.app is None
        assert not hasattr(player, "round")
        assert not hasattr(player, "round_nested")
        assert not hasattr(player, "block")


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


async def test_arriving_players_enter_their_page_as_navigation_does(monkeypatch):
    calls = []

    class Arrival(t.Page):
        @classmethod
        def early(page, player, request):
            calls.append("early")

        @classmethod
        def before_always_once(page, player):
            calls.append("before_always_once")
            player.ready = True

        @classmethod
        def show(page, player):
            calls.append("show")
            return player.get("ready", False)

    monkeypatch.setitem(u.PAGES, page2path(Arrival), Arrival)
    monkeypatch.setattr("uproot.server1.render", render_name)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Arrival)]
        player.started = True
        player.show_page = 0

    move_to_page(s.Player(*pid), Arrival, reload_=False)

    for _ in range(2):  # Arriving, then reloading
        with s.Player(*pid) as player:
            assert await show_page(GetRequest(), player) == "Arrival"

    assert calls == ["early", "before_always_once", "show", "show"]


async def test_arriving_players_skip_pages_that_are_not_shown(monkeypatch):
    calls = []

    class Hidden(t.Page):
        @classmethod
        def show(page, player):
            return False

        @classmethod
        def may_proceed(page, player):
            calls.append("may_proceed")
            return True

        @classmethod
        def after_once(page, player):
            calls.append("after_once")

        @classmethod
        def after_always_once(page, player):
            calls.append("after_always_once")

    for page in (Hidden, Target):
        monkeypatch.setitem(u.PAGES, page2path(page), page)

    monkeypatch.setattr("uproot.server1.render", render_name)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Hidden), page2path(Target)]
        player.started = True
        player.show_page = 0

    move_to_page(s.Player(*pid), Hidden, reload_=False)

    with s.Player(*pid) as player:
        assert await show_page(GetRequest(), player) == "Target"
        assert player.show_page == 2

    assert calls == ["after_always_once"]


async def test_skipped_get_page_honors_moves_through_session_players(monkeypatch):
    class Intermediate(t.Page):
        pass

    class Hidden(t.NoshowPage):
        @classmethod
        def after_always_once(page, player):
            for member in player.session.players:
                move_to_page(member, Target, reload_=False)

    for page in (Hidden, Intermediate, Target):
        monkeypatch.setitem(u.PAGES, page2path(page), page)

    monkeypatch.setattr("uproot.server1.render", render_name)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = [page2path(page) for page in (Hidden, Intermediate, Target)]
        player.started = True
        player.show_page = 0

        assert await show_page(GetRequest(), player) == "Target"
        assert player.show_page == 2


async def test_pages_that_timed_out_count_as_submitted_when_reloaded(monkeypatch):
    calls = []

    class Timed(t.Page):
        @classmethod
        def show(page, player):
            return False  # E.g., no longer shown once time is up

        @classmethod
        def after_once(page, player):
            calls.append("after_once")

        @classmethod
        def after_always_once(page, player):
            calls.append("after_always_once")

    for page in (Timed, Target):
        monkeypatch.setitem(u.PAGES, page2path(page), page)

    monkeypatch.setattr("uproot.server1.render", render_name)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Timed), page2path(Target)]
        player.started = True
        player.show_page = 1
        player._uproot_timeouts_until = {"1": 0.0}

        assert await show_page(GetRequest(), player) == "Target"

    assert calls == ["after_once", "after_always_once"]


async def test_navigation_runs_early_whenever_it_passes_a_page(monkeypatch):
    calls = []

    class Early(t.Page):
        @classmethod
        def early(page, player, request):
            calls.append(player.show_page)

    monkeypatch.setitem(u.PAGES, page2path(Early), Early)
    pid = create_player()

    with s.Player(*pid) as player:
        player.page_order = ["test/First", page2path(Early)]

        for _ in range(2):  # E.g., after going back
            player.show_page = 0
            state = PageTransitionState(0, proceed=True)
            assert await advance_to_next_visible_page(None, player, state) is Early

    assert calls == [1, 1]


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


def test_rounds_count_per_block_within_each_app():
    def app(name: str, *ops: t.PageLike) -> list[str]:
        return [f"{name}/#StartApp", *map(page2path, c.expand(list(ops)))]

    page_order = app(
        "first",
        Rounds(Target, n=2, block="x"),
        Rounds(Target, n=1, block="y"),
        Repeat(Target, block="x"),
    ) + app("second", Rounds(Target, n=1, block="x"))

    starts = [
        i for i, p in enumerate(page_order) if p in ("#RoundStart", "#RepeatStart")
    ]

    assert [round_position(page_order, i)[:2] for i in starts] == [
        ("x", 1),
        ("x", 2),
        ("y", 1),
        ("x", 3),
        ("x", 1),
    ]


def test_block_markers_resolve_to_rounds_reset():
    assert path2page("#RoundsReset:practice") is INTERNAL_PAGES["RoundsReset"]


def test_rounds_of_different_blocks_never_mix():
    ops = [Rounds(Target, n=3, block="a"), Rounds(Target, n=2, block="b")]

    with s.Player(*create_player()) as player:
        c.make_start_app("test").after_always_once(player)
        player.page_order = list(map(page2path, c.expand(ops)))

        for ix, page in enumerate(player.page_order):
            if page == "#RoundStart":
                player.show_page = ix
                asyncio.run(Rounds.next(player))
                player.x = f"{player.block}{player.round}"

        assert [r for r, _ in player.within(block="b").along("round")] == [1, 2]
        assert player.within(block="a", round=3).x == "a3"
        assert player.within(block="b", round=3).get("x") is None

    rows = grouped_player_rows(player, ["app", "block", "round"])

    assert [row["x"] for row in rows] == ["a1", "a2", "a3", "b1", "b2"]


@pytest.mark.parametrize("loop_position", [None, 0, 1, 2])
@pytest.mark.parametrize("grouping", [["app", "block", "round"], ["round", "app"]])
def test_grouped_export_preserves_apps_without_rounds(loop_position, grouping):
    expected = []

    with s.Player(*create_player()) as player:
        for position, appname in enumerate(("first", "middle", "last")):
            c.make_start_app(appname).after_always_once(player)
            player.answer = appname

            if position == loop_position:
                ops = [Rounds(Target, n=2, block="main")]
                player.page_order = list(map(page2path, c.expand(ops)))

                for ix, page in enumerate(player.page_order):
                    if page == "#RoundStart":
                        player.show_page = ix
                        asyncio.run(Rounds.next(player))
                        player.answer = f"{appname}{player.round}"
                        expected.append((appname, player.round, player.answer))
            else:
                expected.append((appname, None, player.answer))

        u.PAGES["End.html"].before_always_once(player)
        player.answer = "after the end"

    rows = grouped_player_rows(player, grouping)

    assert [(row["app"], row.get("round"), row["answer"]) for row in rows] == expected


def test_grouped_export_ends_the_last_round_at_the_end():
    with s.Player(*create_player()) as player:
        c.make_start_app("game").after_always_once(player)
        player.page_order = list(map(page2path, c.expand([Rounds(Target, n=2)])))

        for ix, page in enumerate(player.page_order):
            if page == "#RoundStart":
                player.show_page = ix
                asyncio.run(Rounds.next(player))
                player.answer = player.round

        u.PAGES["End.html"].before_always_once(player)
        player.answer = "after the end"

    rows = grouped_player_rows(player, ["round"])

    assert [(row["app"], row["round"], row["answer"]) for row in rows] == [
        ("game", 1, 1),
        ("game", 2, 2),
    ]


def test_rounds_do_not_carry_over_to_the_next_app():
    with s.Player(*create_player()) as player:
        player.block, player.round_nested, player.round = "a", [3], 3

        for appname in ("next", "after_next"):  # Nothing to retract the second time
            c.make_start_app(appname).after_always_once(player)

        assert player.app == "after_next"
        assert not hasattr(player, "round")
        assert not hasattr(player, "round_nested")
        assert not hasattr(player, "block")


def test_rounds_do_not_carry_over_to_the_end():
    with s.Player(*create_player()) as player:
        c.make_start_app("last").after_always_once(player)
        player.block, player.round_nested, player.round = "a", [2], 2

        u.PAGES["End.html"].before_always_once(player)

        assert player.app is None
        assert not hasattr(player, "round")
        assert not hasattr(player, "round_nested")
        assert not hasattr(player, "block")


def test_check_blocks_demands_blocks_where_rounds_could_mix():
    check_blocks("app", [Rounds(Target, n=2), Target])
    check_blocks("app", [Between(Rounds(Target, n=2), Repeat(Target))])
    check_blocks("app", [Rounds(Target, n=2, block="a"), Repeat(Target, block="a")])

    with pytest.raises(ValueError, match="needs a block"):
        check_blocks("app", [Rounds(Target, n=2, block="a"), Random(Repeat(Target))])

    with pytest.raises(ValueError, match="nested"):
        check_blocks("app", [Rounds(Rounds(Target, n=2, block="a"), n=2)])

    with pytest.raises(ValueError, match="identifier"):
        Rounds(Target, n=2, block="two words")


def test_check_blocks_ignores_empty_rounds():
    check_blocks("app", [Rounds(Target, n=0), Rounds(Target, n=2)])
    check_blocks("app", [Rounds(Rounds(Target, n=1, block="unused"), n=0)])

    with pytest.raises(ValueError, match="needs a block"):
        check_blocks("app", [Rounds(Target, n=0), Rounds(Target, n=2), Repeat(Target)])
