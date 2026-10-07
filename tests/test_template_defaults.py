import pytest
from starlette.requests import Request

import uproot as u
import uproot.deployment as d
from uproot import server
from uproot.pages import path2page, render


@pytest.fixture
def defaults(monkeypatch):
    monkeypatch.setattr(u, "APPS", {}, raising=False)
    monkeypatch.setattr(d, "TEMPLATE_DEFAULTS", dict(d.TEMPLATE_DEFAULTS))

    return d.TEMPLATE_DEFAULTS


async def render_page(template: str) -> str:
    request = Request({"type": "http", "path": "/", "headers": []})

    return await render(None, request, None, path2page(template))


async def test_everything_loads_by_default(defaults):
    html = await render_page("RoomFull.html")

    assert "webfonts.css" in html
    assert "inter-tnum.css" in html
    assert "alpinejs" in html


async def test_defaults_disable_webfonts_and_alpine(defaults):
    defaults["disable_uproot_fonts"] = True
    defaults["disable_alpinejs"] = True
    html = await render_page("RoomFull.html")

    assert "webfonts.css" not in html
    assert "inter-tnum.css" not in html
    assert "alpinejs" not in html
    assert "bootstrap.min.css" in html


async def test_template_set_overrides_defaults(defaults):
    # JustPOST.html has {% set disable_auto_start = True %}
    html = await render_page("JustPOST.html")

    assert "uproot.wsstart()" not in html


async def test_builtin_buddy_by_default(defaults):
    html = await render_page("RoomFull.html")

    assert "/static/_uproot/buddy.svg" in html


async def test_buddy_image_uses_static(defaults):
    defaults["buddy_image"] = "mybuddy.png"
    html = await render_page("RoomFull.html")

    assert "buddy.svg" not in html
    assert '/mybuddy.png"' in html  # missing file, so no ?v=


async def test_builtin_buddy_label_by_default(defaults):
    html = await render_page("RoomFull.html")

    assert html.count("Chat with Research Coordinator") == 2


async def test_buddy_label_replaces_label_and_title(defaults):
    defaults["buddy_label"] = "Messages from the study team"
    html = await render_page("RoomFull.html")

    assert "Chat with Research Coordinator" not in html
    assert html.count("Messages from the study team") == 2


def test_shipped_defaults_are_valid():
    server.validate_template_defaults()


@pytest.mark.parametrize(
    "change",
    [
        {"disable_uproot_font": True},  # misspelt
        {"disable_alpinejs": "yes"},
        {"disable_alpinejs": 1},
        {"buddy_image": True},
        {"buddy_label": 1},
    ],
)
def test_invalid_defaults_are_rejected(defaults, change):
    defaults |= change

    with pytest.raises(SystemExit):
        server.validate_template_defaults()


def test_reassigned_incomplete_defaults_are_rejected(monkeypatch):
    monkeypatch.setattr(d, "TEMPLATE_DEFAULTS", {"disable_uproot_fonts": True})

    with pytest.raises(SystemExit):
        server.validate_template_defaults()
