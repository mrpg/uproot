# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Session management service."""

import inspect
from typing import Any

from fastapi import HTTPException

import uproot as u
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t
from uproot.types import ensure_awaitable


class PipelineInvocationError(TypeError):
    pass


def session_exists(sname: t.Sessionname, raise_http: bool = True) -> None:
    """Check if a session exists.

    Args:
        sname: Session name to check
        raise_http: If True, raise HTTPException; otherwise raise ValueError
    """
    with s.Admin() as admin:
        if sname not in admin._uproot_sessions:
            if raise_http:
                raise HTTPException(status_code=400, detail="Invalid session")
            else:
                raise ValueError("Invalid session")


def sessions() -> dict[str, dict[str, Any]]:
    """Get all sessions with their stats."""
    if d.PUBLIC_DEMO:
        return {}

    stats = {}

    with s.Admin() as admin:
        snames = admin._uproot_sessions

    for sname in snames:
        with s.Session(sname) as session:
            stats[sname] = {
                "sname": session.name,  # Exactly equal to sname
                "created": session.__history__()["_uproot_session"][0].time,
                "active": session.active,
                "config": session.config,
                "room": session.room,
                "description": session.description,
                "n_players": len(session._uproot_players),
                "n_groups": len(session._uproot_groups),
            }

    return stats


async def flip_active(sname: t.Sessionname) -> None:
    """Toggle the active status of a session."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.active = not session.active


async def flip_testing(sname: t.Sessionname) -> None:
    """Toggle the testing status of a session."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        session._uproot_testing = not session._uproot_testing


async def run_new_session(sname: t.Sessionname) -> None:
    """Manually run new_session callbacks for a session that hasn't been initialized."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        if session.get("_uproot_initialized", False):
            raise HTTPException(status_code=400, detail="Session already initialized")

        for appname in session.apps:
            app = u.APPS[appname]

            if hasattr(app, "new_session"):
                app.new_session(session)

        session._uproot_initialized = True


async def update_description(sname: t.Sessionname, newdesc: str) -> None:
    """Update session description."""
    if d.PUBLIC_DEMO:
        raise PermissionError("Cannot update description in public demo.")

    session_exists(sname, False)

    with s.Session(sname) as session:
        session.description = newdesc if newdesc else None


async def update_settings(sname: t.Sessionname, **newsettings: Any) -> None:
    """Update session settings."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        session._uproot_settings = newsettings


def get_digest(sname: t.Sessionname) -> list[str]:
    """Get list of apps that have digest methods for a session."""
    with s.Session(sname) as session:
        apps = session.apps

    return [appname for appname in apps if hasattr(u.APPS[appname], "digest")]


def get_pipelines(sname: t.Sessionname) -> list[str]:
    """Get list of apps that have pipeline methods for a session."""
    with s.Session(sname) as session:
        apps = session.apps

    return [appname for appname in apps if hasattr(u.APPS[appname], "pipeline")]


def pipeline_call_kwargs(
    pipeline: Any, data: Any, data_was_provided: bool
) -> dict[str, Any]:
    """Return validated optional keyword arguments for a pipeline callable."""
    try:
        params = inspect.signature(pipeline).parameters
    except (TypeError, ValueError):
        if data_was_provided:
            raise PipelineInvocationError(
                "Cannot pass pipeline data to a callable with no signature"
            )
        return {}

    accepts_arbitrary_kwargs = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values()
    )
    data_param = params.get("data")
    accepts_data = data_param is not None or accepts_arbitrary_kwargs

    if data_was_provided and not accepts_data:
        raise PipelineInvocationError(
            "Pipeline data was provided, but pipeline() does not accept data"
        )

    if data_param is not None:
        data_required = (
            data_param.default is inspect.Parameter.empty
            and data_param.kind
            in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            )
        )

        if data_required and not data_was_provided:
            raise PipelineInvocationError(
                "pipeline() requires data, but no pipeline data was provided"
            )

        return {"data": data}

    if data_was_provided and accepts_arbitrary_kwargs:
        return {"data": data}

    return {}


async def run_pipeline(
    sname: t.Sessionname,
    appname: str,
    data: Any = None,
    data_was_provided: bool = False,
) -> Any:
    """Run an app pipeline for a session, optionally passing JSON-compatible data."""
    session_exists(sname, False)

    if appname not in get_pipelines(sname):
        raise ValueError("No pipeline available")

    app = u.APPS[appname]

    with s.Session(sname) as session:
        return await ensure_awaitable(
            app.pipeline,
            session=session,
            **pipeline_call_kwargs(app.pipeline, data, data_was_provided),
        )
