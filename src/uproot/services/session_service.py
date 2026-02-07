# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Session management service."""

from typing import Any

from fastapi import HTTPException

import uproot as u
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t


def session_exists(sname: t.Sessionname, raise_http: bool = True) -> None:
    """Check if a session exists.

    Args:
        sname: Session name to check
        raise_http: If True, raise HTTPException; otherwise raise ValueError
    """
    with s.Admin() as admin:
        if sname not in admin.sessions:
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
        snames = admin.sessions

    for sname in snames:
        with s.Session(sname) as session:
            stats[sname] = {
                "sname": session.name,  # Exactly equal to sname
                "created": session.__history__()["_uproot_session"][0].time,
                "active": session.active,
                "config": session.config,
                "room": session.room,
                "description": session.description,
                "n_players": len(session.players),
                "n_groups": len(session.groups),
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
        session.testing = not session.testing


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
        session.settings = newsettings


def get_digest(sname: t.Sessionname) -> list[str]:
    """Get list of apps that have digest methods for a session."""
    with s.Session(sname) as session:
        apps = session.apps

    return [appname for appname in apps if hasattr(u.APPS[appname], "digest")]
