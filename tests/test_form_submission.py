import sys
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import ChoiceLoader, DictLoader

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.queues as q
import uproot.storage as s
from uproot import pages, server1
from uproot.fields import IntegerField, StringField
from uproot.types import Page


class Guarded(Page):
    stealth_fields = ("secret",)

    @classmethod
    def fields(page, player):
        return {
            "visible": IntegerField(label="Visible", optional=True),
            "secret": StringField(label="Secret"),
        }

    @classmethod
    def handle_stealth_fields(page, player, data):
        player.handler_calls += 1

        if data["secret"] != "ok":
            return "Wrong secret"

        return None

    @classmethod
    def before_form_save(page, player, data):
        player.before_form_save_calls += 1


class Timed(Guarded):
    timeout = 60


class TimedValidated(Timed):
    @classmethod
    def validate(page, player, data):
        return "Never valid"


@pytest.fixture
def client(monkeypatch):
    d.DATABASE.reset()
    monkeypatch.setattr(u, "APPS", {__name__: sys.modules[__name__]}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"form-test": []})
    monkeypatch.setattr(q, "Q", {})
    monkeypatch.setattr(
        pages.ENV,
        "loader",
        ChoiceLoader(
            [
                DictLoader(
                    {
                        f"{__name__}/{name}.html": (
                            '{% extends "Base.html" %}'
                            "{% block main %}{{ fields() }}{% endblock main %}"
                        )
                        for name in ("Guarded", "Timed", "TimedValidated")
                    }
                ),
                pages.ENV.loader,
            ]
        ),
    )

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "form-test")

    with s.Session(sid) as session:
        pid = c.create_player(session)

    app = FastAPI()
    app.include_router(server1.router)

    return TestClient(app), pid


def start(pid, page):
    with s.Player(*pid) as player:
        player.page_order = [f"{__name__}/{page.__name__}"]
        player.show_page = 0
        player.started = True
        player._uproot_initialized = True
        player.handler_calls = 0
        player.before_form_save_calls = 0

        if issubclass(page, Timed):
            player._uproot_timeouts_until = {"0": time.time() - 10}

        return f"{player._uproot_session}+{player.name}+{player._uproot_key}"


def submit(client, pid, csrf, **fields):
    return client.post(
        f"/p/{pid.sname}/{pid.uname}/",
        data={"_uproot_from": "0", "_uproot_csrf": csrf} | fields,
    )


def test_rejection_by_stealth_handler_saves_nothing(client):
    client, pid = client
    response = submit(client, pid, start(pid, Guarded), visible="7", secret="no")

    assert "Wrong secret" in response.text

    with s.Player(*pid) as player:
        assert player.show_page == 0
        assert player.handler_calls == 1
        assert player.before_form_save_calls == 0
        assert not hasattr(player, "visible")
        assert not hasattr(player, "secret")


def test_acceptance_by_stealth_handler_saves_ordinary_fields_only(client):
    client, pid = client
    submit(client, pid, start(pid, Guarded), visible="7", secret="ok")

    with s.Player(*pid) as player:
        assert player.show_page == 1
        assert player.before_form_save_calls == 1
        assert player.visible == 7
        assert not hasattr(player, "secret")


def test_cleared_optional_field_is_saved_as_none(client):
    client, pid = client
    submit(client, pid, start(pid, Guarded), secret="ok")

    with s.Player(*pid) as player:
        assert player.show_page == 1
        assert player.visible is None


def test_expired_timeout_advances_despite_rejection_by_stealth_handler(client):
    client, pid = client
    submit(client, pid, start(pid, Timed), visible="7", secret="no")

    with s.Player(*pid) as player:
        assert player.show_page == 1
        assert player.handler_calls == 1
        assert not hasattr(player, "visible")


@pytest.mark.parametrize("page", [Timed, TimedValidated])
def test_errors_of_timed_out_page_are_not_shown_on_next_page(client, page):
    client, pid = client
    response = submit(client, pid, start(pid, page), visible="7", secret="no")

    assert "Wrong secret" not in response.text
    assert "Never valid" not in response.text

    with s.Player(*pid) as player:
        assert player.show_page == 1
