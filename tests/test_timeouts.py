import time

import uproot.deployment as d
from uproot.server1 import timeout_fires
from uproot.types import Page


class FakePlayer:
    def __init__(self, deadline: float) -> None:
        self.show_page = 0
        self._uproot_timeouts_until = {"0": deadline}
        self.may_proceed_calls = 0

    def refresh(self, *fields: str) -> None:
        pass


class Blocking(Page):
    timeout = 60

    @classmethod
    def may_proceed(page, player):
        player.may_proceed_calls += 1
        return False


class Allowing(Page):
    timeout = 60

    @classmethod
    def may_proceed(page, player):
        player.may_proceed_calls += 1
        return True


class Plain(Page):
    timeout = 60


async def test_timeout_does_not_fire_before_tolerance_window():
    player = FakePlayer(time.time() + d.TIMEOUT_TOLERANCE + 10)

    assert await timeout_fires(Allowing, player) is False
    assert player.may_proceed_calls == 0


async def test_timeout_in_tolerance_window_respects_may_proceed():
    player = FakePlayer(time.time() + d.TIMEOUT_TOLERANCE / 2)

    assert await timeout_fires(Blocking, player) is False
    assert await timeout_fires(Allowing, player) is True
    assert player.may_proceed_calls == 2


async def test_timeout_in_tolerance_window_fires_without_may_proceed():
    player = FakePlayer(time.time() + d.TIMEOUT_TOLERANCE / 2)

    assert await timeout_fires(Plain, player) is True


async def test_timeout_after_deadline_skips_may_proceed():
    player = FakePlayer(time.time() - 0.1)

    assert await timeout_fires(Blocking, player) is True
    assert player.may_proceed_calls == 0


async def test_no_timeout_without_deadline():
    player = FakePlayer(0.0)
    player._uproot_timeouts_until = {}

    assert await timeout_fires(Allowing, player) is False
