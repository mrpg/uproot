from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException, Request

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
from uproot import server2


class SettingsTemplate:
    def __init__(self, rendered_context: dict[str, Any]) -> None:
        self.rendered_context = rendered_context

    async def render_async(self, **context: Any) -> str:
        self.rendered_context.update(context)
        return "<p>Settings</p>"


class SettingsEnvironment:
    def __init__(self, rendered_context: dict[str, Any]) -> None:
        self.rendered_context = rendered_context

    def get_template(self, template_name: str) -> SettingsTemplate:
        assert template_name == "settings_app/AdminSettings.html"
        return SettingsTemplate(self.rendered_context)


def test_create_session_runs_app_settings_validation_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d.DATABASE.reset()
    calls: list[tuple[str, dict[str, Any]]] = []

    def validate_session_settings(
        admin: s.Storage,
        config: str,
        settings: dict[str, Any],
    ) -> None:
        calls.append((config, settings))

        if settings.get("destination") not in admin.rooms:
            raise ValueError("Destination does not exist")

    app = SimpleNamespace(validate_session_settings=validate_session_settings)
    monkeypatch.setattr(u, "APPS", {"settings_app": app}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"settings_config": ["settings_app"]})

    with s.Admin() as admin:
        c.create_admin(admin)
        admin.rooms = {}
        admin._uproot_sessions = []
        admin.rooms["existing"] = {}

        with pytest.raises(ValueError, match="Destination does not exist"):
            c.create_session(
                admin,
                "settings_config",
                settings={"destination": "missing"},
            )

        assert admin._uproot_sessions == []

        sid = c.create_session(
            admin,
            "settings_config",
            settings={"destination": "existing"},
        )

    with s.Session(sid.sname) as session:
        assert session.settings.destination == "existing"

    assert calls == [
        ("settings_config", {"destination": "missing"}),
        ("settings_config", {"destination": "existing"}),
    ]


async def test_admin_settings_context_is_passed_to_app_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d.DATABASE.reset()
    rendered_context: dict[str, Any] = {}
    default_settings = {"destination": "existing"}

    async def admin_settings_context(
        admin: s.Storage,
        config: str,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        assert config == "settings_config"
        assert settings is default_settings
        return {
            "available_destinations": sorted(admin.rooms),
            "config": "cannot override framework context",
            "settings": {"cannot": "override framework context"},
        }

    app = SimpleNamespace(
        C={"EXAMPLE": True}, admin_settings_context=admin_settings_context
    )
    monkeypatch.setattr(u, "APPS", {"settings_app": app}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"settings_config": ["settings_app"]})
    monkeypatch.setattr(
        u,
        "CONFIGS_EXTRA",
        {"settings_config": {"settings": default_settings}},
    )
    monkeypatch.setattr(
        server2.PENV, "get_template", SettingsEnvironment(rendered_context).get_template
    )
    monkeypatch.setattr(
        server2,
        "session_settings_templates",
        lambda config: [("settings_app/AdminSettings.html", "settings_app")],
    )

    with s.Admin() as admin:
        c.create_admin(admin)
        admin.rooms = {}
        admin._uproot_sessions = []
        admin.rooms["second"] = {}
        admin.rooms["first"] = {}

    forms, errors = await server2.render_session_settings_forms()

    assert errors == {}
    assert [str(form) for form in forms["settings_config"]] == ["<p>Settings</p>"]
    assert rendered_context["available_destinations"] == ["first", "second"]
    assert rendered_context["config"] == "settings_config"
    assert rendered_context["settings"] is default_settings


async def test_admin_ui_reports_session_settings_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d.DATABASE.reset()

    def validate_session_settings(
        admin: s.Storage,
        config: str,
        settings: dict[str, Any],
    ) -> None:
        raise ValueError("Invalid example settings")

    app = SimpleNamespace(validate_session_settings=validate_session_settings)
    monkeypatch.setattr(u, "APPS", {"settings_app": app}, raising=False)
    monkeypatch.setattr(u, "CONFIGS", {"settings_config": ["settings_app"]})

    with s.Admin() as admin:
        c.create_admin(admin)
        admin._uproot_sessions = []

    with pytest.raises(HTTPException) as excinfo:
        await server2.new_session2(
            request=cast(Request, None),
            config="settings_config",
            nplayers=0,
            settings="{}",
            sname="",
            unames="",
            simulate=False,
            auth={},
        )

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "Invalid example settings"
