import asyncio
import random

import pytest

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot.pages import page2path, path2page
from uproot.smithereens import (
    INTERNAL_PAGES,
    Between,
    Random,
    Repeat,
    Rounds,
    check_blocks,
    data_uri,
    move_to_page,
    rng,
    round_position,
)
from uproot.stable import decode, encode


class Target(t.Page):
    pass


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
        player.page_order = list(map(page2path, c.expand(ops)))

        for ix, page in enumerate(player.page_order):
            if page == "#RoundStart":
                player.show_page = ix
                asyncio.run(Rounds.next(player))
                player.x = f"{player.block}{player.round}"

        assert [r for r, _ in player.within(block="b").along("round")] == [1, 2]
        assert player.within(block="a", round=3).x == "a3"
        assert player.within(block="b", round=3).get("x") is None


def test_rounds_do_not_carry_over_to_the_next_app():
    with s.Player(*create_player()) as player:
        player.block, player.round_nested, player.round = "a", [3], 3

        for appname in ("next", "after_next"):  # Nothing to retract the second time
            c.make_start_app(appname).after_always_once(player)

        assert player.app == "after_next"
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
