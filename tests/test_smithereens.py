import random

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot.pages import page2path
from uproot.smithereens import data_uri, move_to_page, rng
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
