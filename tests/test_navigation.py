"""Navigation as specified in uproot-proofs (Pages.lean): Back, timeouts, moves
by hooks, and requests that do not carry the current page's form."""

import asyncio
import time

import pytest
from starlette.datastructures import FormData

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot import server1
from uproot.fields import IntegerField
from uproot.pages import page2path
from uproot.server1 import show_page
from uproot.services import player_service as ps
from uproot.smithereens import Rounds, move_to_end, move_to_page

LOG: list = []


class GetRequest:
    method = "GET"
    app = None


class PostRequest:
    method = "POST"
    app = None

    def __init__(self, data: dict) -> None:
        self.data = data

    async def form(self) -> FormData:
        return FormData(self.data)


async def render_spy(app, request, player, page, formdata=None, errors=None, *rest):
    LOG.append(("display", page.__name__, player.show_page, formdata is not None))
    return page.__name__


@pytest.fixture
def setup(monkeypatch):
    def setup_(pages, position, **fields):
        LOG.clear()
        d.DATABASE.reset()
        u.CONFIGS["test"] = []
        monkeypatch.setattr(u, "APPS", {}, raising=False)
        monkeypatch.setattr(server1, "render", render_spy)

        for page in pages:
            if not page2path(page).startswith("#"):
                monkeypatch.setitem(u.PAGES, page2path(page), page)

        with s.Admin() as admin:
            c.create_admin(admin)
            sid = c.create_session(admin, "test")

        with s.Session(sid) as session:
            pid = c.create_player(session)

        with s.Player(*pid) as player:
            player.page_order = [page2path(page) for page in pages]
            player.started = True
            player.show_page = position

            for key, value in fields.items():
                setattr(player, key, value)

        return pid

    return setup_


def csrf(pid) -> str:
    with s.Player(*pid) as player:
        return f"{player._uproot_session}+{player.name}+{player._uproot_key}"


async def request(pid, data=None) -> str:
    with s.Player(*pid) as player:
        return await show_page(
            GetRequest() if data is None else PostRequest(data), player
        )


def position(pid) -> int:
    with s.Player(*pid) as player:
        return player.show_page


def ran(pid) -> set:
    with s.Player(*pid) as player:
        return set(player.get("_uproot_what_ran", frozenset()))


class Hidden(t.NoshowPage):
    pass


class First(t.Page):
    allow_back = True


async def test_back_without_earlier_shown_page_stays(setup):
    pid = setup([Hidden, First], 1)

    assert (
        await request(pid, {"_uproot_from": "back-1", "_uproot_csrf": csrf(pid)})
        == "First"
    )
    assert position(pid) == 1


class Before(t.Page):
    pass


class TimedBack(t.Page):
    allow_back = True
    timeout = 60

    @classmethod
    def fields(page, player):
        return {"answer": IntegerField(label="Answer")}

    @classmethod
    def timeout_reached(page, player):
        LOG.append("timeout_reached")


async def test_back_after_deadline_is_timed_out_submission(setup):
    pid = setup([Before, TimedBack], 1, _uproot_timeouts_until={"1": time.time() - 10})
    data = {"_uproot_from": "back-1", "_uproot_csrf": csrf(pid), "answer": "7"}

    assert await request(pid, data) == "End"
    assert "timeout_reached" in LOG

    with s.Player(*pid) as player:
        assert player.answer == 7


class Blocking(t.Page):
    allow_back = True

    @classmethod
    def may_proceed(page, player):
        return False


async def test_may_proceed_does_not_gate_back(setup):
    pid = setup([Before, Blocking], 1)

    assert (
        await request(pid, {"_uproot_from": "back-1", "_uproot_csrf": csrf(pid)})
        == "Before"
    )
    assert position(pid) == 0


class Start(t.Page):
    pass


class Mover(t.NoshowPage):
    @classmethod
    def after_always_once(page, player):
        move_to_page(player, Target, reload_=False)


class Between(t.Page):
    pass


class Target(t.Page):
    @classmethod
    def early(page, player, request):
        LOG.append("Target.early")

    @classmethod
    def before_always_once(page, player):
        LOG.append("Target.before_always_once")


@pytest.mark.parametrize("hook", ["early", "after_once"])
async def test_move_to_end_finishes_current_phase_before_cleanup(setup, hook):
    def move(player):
        with s.Player(*t.identify(player)) as other:
            move_to_end(other, reload_=False)

    def observe(player):
        LOG.append(("old phase", player.app, player.round))

    class Moving(t.Page):
        @classmethod
        def early(page, player, request):
            if hook == "early":
                move(player)

        @classmethod
        def before_always_once(page, player):
            if hook == "early":
                observe(player)

        @classmethod
        def after_once(page, player):
            move(player)

        @classmethod
        def after_always_once(page, player):
            observe(player)

    pid = setup([Moving], 0, app="test", block="a", round=2, round_nested=[2])
    data = None if hook == "early" else {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}
    assert await request(pid, data) == "End"
    assert ("old phase", "test", 2) in LOG
    with s.Player(*pid) as player:
        assert player.app is None
        assert not hasattr(player, "round")
        assert not c.in_page_request(player)


async def test_spawned_task_does_not_inherit_end_deferral(setup):
    class Moving(t.Page):
        @classmethod
        async def early(page, player, request):
            async def external_move():
                with s.Player(*t.identify(player)) as other:
                    move_to_end(other, reload_=False)
                    assert other.app is None

            await asyncio.create_task(external_move())

    pid = setup([Moving], 0, app="test")
    assert await request(pid) == "End"


async def test_failed_request_restores_end_cleanup_context(setup):
    class Failing(t.Page):
        @classmethod
        def early(page, player, request):
            raise ValueError("failed hook")

    pid = setup([Failing], 0, app="test")
    with pytest.raises(ValueError, match="failed hook"):
        await request(pid)
    with s.Player(*pid) as player:
        assert not c.in_page_request(player)
        move_to_end(player, reload_=False)
        assert player.app is None


async def test_failed_request_still_reaches_deferred_end(setup):
    class Moving(t.Page):
        @classmethod
        def early(page, player, request):
            with s.Player(*t.identify(player)) as other:
                move_to_end(other, reload_=False)
            raise ValueError("after move")

    pid = setup([Moving], 0, app="test", block="a", round=2, round_nested=[2])
    with pytest.raises(ValueError, match="after move"):
        await request(pid)
    with s.Player(*pid) as player:
        assert player.show_page == len(player.page_order)
        assert player.app is None
        assert not hasattr(player, "round")


@pytest.mark.parametrize("foreign", [False, True])
async def test_loading_retains_actual_request_for_early(setup, foreign):
    class Aware(t.Page):
        @classmethod
        def fields(page, player):
            return {"answer": IntegerField(label="Answer")}

        @classmethod
        def early(page, player, request):
            player.method = request.method

    pid = setup([Aware], 0, answer=13)
    data = {"_uproot_from": "1", "answer": "99"} if foreign else None
    assert await request(pid, data) == "Aware"
    with s.Player(*pid) as player:
        assert player.method == ("POST" if foreign else "GET")
        assert player.answer == 13


async def test_back_selects_before_entry_without_rechecking_show(setup):
    class Prior(t.Page):
        @classmethod
        def show(page, player):
            LOG.append("select")
            return player.visible

        @classmethod
        def early(page, player, request):
            LOG.append("enter")
            player.visible = False

    pid = setup([Prior, First], 1, visible=True)
    assert (
        await request(pid, {"_uproot_from": "back-1", "_uproot_csrf": csrf(pid)})
        == "Prior"
    )
    assert LOG[:2] == ["select", "enter"]
    with s.Player(*pid) as player:
        assert not player.visible


async def test_move_from_skipped_page_is_kept(setup):
    pid = setup([Start, Mover, Between, Target], 0)

    assert (
        await request(pid, {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}) == "Target"
    )
    assert position(pid) == 3


class Decision(t.Page):
    @classmethod
    def before_once(page, player):
        move_to_page(player, Target, reload_=False)


async def test_move_from_before_once_enters_target(setup):
    pid = setup([Start, Decision, Target], 0)

    assert (
        await request(pid, {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}) == "Target"
    )
    assert LOG[:2] == ["Target.early", "Target.before_always_once"]


class Gate(t.Page):
    @classmethod
    def may_proceed(page, player):
        with s.Player(*t.identify(player)) as other:
            move_to_page(other, Target, reload_=False)

        return False


async def test_move_from_refusing_may_proceed_is_kept(setup):
    pid = setup([Gate, Between, Target], 0)

    assert (
        await request(pid, {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}) == "Target"
    )
    assert LOG[-1] == ("display", "Target", 2, False)
    assert "0:before_once" not in ran(pid) and "2:before_once" not in ran(pid)


class Conditional(t.Page):
    @classmethod
    def show(page, player):
        return player.get("flag", False)

    @classmethod
    def before_once(page, player):
        LOG.append("Conditional.before_once")


class Setter(t.Page):
    allow_back = True

    @classmethod
    def before_always_once(page, player):
        player.flag = True


async def test_back_to_page_not_displayed_before_runs_before_once(setup):
    pid = setup([Start, Conditional, Setter], 0)

    assert (
        await request(pid, {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}) == "Setter"
    )
    assert "Conditional.before_once" not in LOG

    assert await request(
        pid, {"_uproot_from": "back-2", "_uproot_csrf": csrf(pid)}
    ) == ("Conditional")
    assert "Conditional.before_once" in LOG


class Answer(t.Page):
    allow_back = True


async def test_back_does_not_cross_start_of_round(setup):
    pages = c.expand([Rounds(Answer, n=2)])
    pid = setup(pages, 0)
    paths = [page2path(page) for page in pages]
    first = paths.index(page2path(Answer))
    second = paths.index(page2path(Answer), first + 1)

    await request(pid)
    assert position(pid) == first
    await request(pid, {"_uproot_from": str(first), "_uproot_csrf": csrf(pid)})
    assert position(pid) == second

    await request(pid, {"_uproot_from": f"back-{second}", "_uproot_csrf": csrf(pid)})

    with s.Player(*pid) as player:
        assert player.show_page == second
        assert player.round == 2


class Old(t.Page):
    pass


class Skipped(t.Page):
    @classmethod
    def show(page, player):
        return False

    @classmethod
    def before_always_once(page, player):
        LOG.append("Skipped.before_always_once")


class After(t.Page):
    pass


async def test_foreign_form_is_handled_as_loading_page(setup):
    pid = setup([Old, Skipped, After], 0)
    await ps.advance_by_one(pid.sname, [pid.uname])

    assert (
        await request(pid, {"_uproot_from": "0", "_uproot_csrf": csrf(pid)}) == "After"
    )
    assert LOG[0] == "Skipped.before_always_once"


async def test_post_with_bad_token_is_handled_as_loading_page(setup):
    pid = setup([Old, After], 0)

    assert await request(pid, {"_uproot_from": "0", "_uproot_csrf": "bad"}) == "Old"
    assert position(pid) == 0


@pytest.mark.parametrize("hook", ["before_once", "show", "before_form_save"])
@pytest.mark.parametrize("other_writer", [False, True])
async def test_hooks_preserve_page_order_changes(setup, hook, other_writer):
    def reorder(page, player, **kwargs):
        player.page_order[1:] = reversed(player.page_order[1:])

        if other_writer:
            with s.Player(*t.identify(player)) as other:
                other.page_order = [other.page_order[0], page2path(After)]

        return True

    page = type(
        "Reordering",
        (t.Page,),
        {
            hook: classmethod(reorder),
            "fields": {"answer": IntegerField(label="Answer")},
            "may_proceed": False,
        },
    )
    pid = setup([page, Before, After], 0)
    data = (
        {"_uproot_from": "0", "_uproot_csrf": csrf(pid), "answer": "7"}
        if hook == "before_form_save"
        else None
    )

    assert await request(pid, data) == "Reordering"

    with s.Player(*pid) as player:
        expected = [page, After] if other_writer else [page, After, Before]
        assert player.page_order == list(map(page2path, expected))
