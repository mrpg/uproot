import pytest

import uproot.deployment as d
import uproot.storage as s
from uproot.cache import peek


def test_peek_reads_current_value_without_copying():
    d.DATABASE.reset()
    namespace = ("player", "peeksession", "peekplayer")

    with s.Player(*namespace[1:]) as player:
        player.page_order = ["app/A", "app/B"]
        player.show_page = 1
        player.gone = True
        del player.gone

        assert peek(namespace, "show_page") == player.show_page
        assert peek(namespace, "page_order") == player.page_order
        assert peek(namespace, "page_order") is peek(namespace, "page_order")

    for field in ("gone", "missing"):
        with pytest.raises(AttributeError):
            peek(namespace, field)

        assert peek(namespace, field, None) is None
