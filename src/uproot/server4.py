# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements the Admin REST API at /admin/api/.

All endpoints require Bearer token authentication via the Authorization header.
Tokens are configured in deployment.API_KEYS.
"""

import importlib.metadata
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

import uproot as u
import uproot.admin as a
import uproot.core as c
import uproot.deployment as d
import uproot.rooms as r
import uproot.types as t
from uproot.storage import Admin, Session

router = APIRouter(prefix=f"{d.ROOT}/admin/api/v1")


# =============================================================================
# Pydantic Models for Request/Response Validation
# =============================================================================


class SessionCreate(BaseModel):
    """Request body for creating a new session."""

    config: str = Field(..., description="Configuration name")
    n_players: int = Field(..., ge=1, description="Number of players to create")
    sname: Optional[str] = Field(
        None, description="Custom session name (auto-generated if omitted)"
    )
    unames: Optional[list[str]] = Field(
        None, description="Custom usernames for players"
    )
    settings: Optional[dict[str, Any]] = Field(None, description="Session settings")


class RoomCreate(BaseModel):
    """Request body for creating a new room."""

    name: str = Field(..., min_length=1, description="Room name")
    config: Optional[str] = Field(
        None, description="Default configuration for sessions"
    )
    labels: Optional[list[str]] = Field(
        None, description="Allowed labels for participants"
    )
    capacity: Optional[int] = Field(None, ge=1, description="Maximum capacity")
    open: bool = Field(False, description="Whether the room is open for joining")
    sname: Optional[str] = Field(None, description="Associated session name")


class PlayersAction(BaseModel):
    """Request body for player actions (advance, revert, etc.)."""

    unames: list[str] = Field(
        ..., min_length=1, description="List of usernames to act on"
    )


class PlayersFields(BaseModel):
    """Request body for inserting fields on players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    fields: dict[str, Any] = Field(..., description="Fields to set")
    reload: bool = Field(False, description="Whether to trigger page reload")


class PlayerRedirect(BaseModel):
    """Request body for redirecting players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    url: str = Field(
        ..., description="URL to redirect to (must start with http:// or https://)"
    )


class PlayerMessage(BaseModel):
    """Request body for sending admin messages to players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    message: str = Field(..., description="Message to send")


class DescriptionUpdate(BaseModel):
    """Request body for updating session description."""

    description: str = Field("", description="New description (empty to clear)")


class SettingsUpdate(BaseModel):
    """Request body for updating session settings."""

    settings: dict[str, Any] = Field(..., description="New settings")


class RoomSessionCreate(BaseModel):
    """Request body for creating a session within a room."""

    config: str = Field(..., description="Configuration name")
    n_players: int = Field(..., ge=1, description="Number of players")
    assignees: Optional[list[str]] = Field(
        None, description="Labels to assign to players"
    )
    settings: Optional[dict[str, Any]] = Field(None, description="Session settings")
    sname: Optional[str] = Field(None, description="Custom session name")
    unames: Optional[list[str]] = Field(None, description="Custom usernames")
    no_grow: bool = Field(False, description="Lock capacity to n_players")


class RoomUpdate(BaseModel):
    """Request body for updating room settings."""

    config: Optional[str] = Field(None, description="Default configuration")
    labels: Optional[list[str]] = Field(None, description="Allowed labels")
    capacity: Optional[int] = Field(None, ge=1, description="Maximum capacity")
    open: bool = Field(False, description="Whether the room is open")


# =============================================================================
# Sessions API
# =============================================================================


@router.get("/sessions/")
async def list_sessions(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """List all sessions with their metadata."""
    return a.sessions()


@router.get("/session/{sname}/")
async def get_session(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get detailed information about a specific session."""
    a.session_exists(sname)

    with Session(sname) as session:
        return dict(
            sname=session.name,
            config=session.config,
            active=session.active,
            testing=session.testing,
            description=session.description,
            room=session.room,
            settings=session.settings,
            n_players=len(session.players),
            n_groups=len(session.groups),
            n_models=len(session.models),
            apps=session.apps,
        )


@router.post("/sessions/", status_code=201)
async def create_session(
    body: SessionCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new session with the specified configuration and players."""
    if body.config not in u.CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid configuration")

    settings_parsed = (
        body.settings
        if body.settings is not None
        else u.CONFIGS_EXTRA.get(body.config, {}).get("settings", {})
    )

    with Admin() as admin:
        if body.sname and body.sname in admin.sessions:
            raise HTTPException(status_code=400, detail="Session name already exists")

        sid = c.create_session(
            admin,
            body.config,
            sname=body.sname,
            settings=settings_parsed,
        )

    with t.materialize(sid) as session:
        c.create_players(
            session,
            n=body.n_players,
            unames=body.unames,
        )

    c.finalize_session(sid)

    return dict(sname=sid.sname, created=True)


@router.patch("/session/{sname}/active/")
async def toggle_session_active(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Toggle the active status of a session."""
    a.session_exists(sname)
    await a.flip_active(sname)

    with Session(sname) as session:
        return dict(active=session.active)


@router.patch("/session/{sname}/testing/")
async def toggle_session_testing(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Toggle the testing mode of a session."""
    a.session_exists(sname)
    await a.flip_testing(sname)

    with Session(sname) as session:
        return dict(testing=session.testing)


@router.patch("/session/{sname}/description/")
async def update_session_description(
    sname: str,
    body: DescriptionUpdate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Update the description of a session."""
    a.session_exists(sname)

    try:
        await a.update_description(sname, body.description)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    return dict(description=body.description if body.description else None)


@router.patch("/session/{sname}/settings/")
async def update_session_settings(
    sname: str,
    body: SettingsUpdate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Update the settings of a session."""
    a.session_exists(sname)
    await a.update_settings(sname, **body.settings)

    return dict(settings=body.settings)


# =============================================================================
# Players API
# =============================================================================


@router.get("/session/{sname}/players/")
async def list_players(
    sname: str,
    fields: list[str] = Query(
        default=["id", "page_order", "show_page", "started", "label"]
    ),
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """Get specified fields for all players in a session."""
    a.session_exists(sname)
    return await a.fields_from_all(sname, fields)


@router.get("/session/{sname}/players/online/")
async def get_online_players(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get online status and info for all players in a session."""
    a.session_exists(sname)
    return await a.info_online(sname)


@router.patch("/session/{sname}/players/fields/")
async def set_player_fields(
    sname: str,
    body: PlayersFields,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Set arbitrary fields on specified players."""
    a.session_exists(sname)
    await a.insert_fields(sname, body.unames, body.fields, body.reload)

    return dict(updated=body.unames, fields=list(body.fields.keys()))


@router.post("/session/{sname}/players/advance/")
async def advance_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Advance specified players by one page."""
    a.session_exists(sname)
    return await a.advance_by_one(sname, body.unames)


@router.post("/session/{sname}/players/revert/")
async def revert_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Revert specified players by one page."""
    a.session_exists(sname)
    return await a.revert_by_one(sname, body.unames)


@router.post("/session/{sname}/players/end/")
async def put_players_to_end(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Move specified players to the end of the experiment."""
    a.session_exists(sname)
    return await a.put_to_end(sname, body.unames)


@router.post("/session/{sname}/players/reload/")
async def reload_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Force page reload for specified players."""
    a.session_exists(sname)
    await a.reload(sname, body.unames)

    return dict(reloaded=body.unames)


@router.post("/session/{sname}/players/redirect/")
async def redirect_players(
    sname: str,
    body: PlayerRedirect,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Redirect specified players to an external URL."""
    a.session_exists(sname)

    try:
        await a.redirect(sname, body.unames, body.url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return dict(redirected=body.unames, url=body.url)


@router.post("/session/{sname}/players/message/")
async def message_players(
    sname: str,
    body: PlayerMessage,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Send an admin message to specified players."""
    a.session_exists(sname)
    await a.adminmessage(sname, body.unames, body.message)

    return dict(messaged=body.unames)


@router.post("/session/{sname}/players/dropout/")
async def mark_players_dropout(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Mark specified players as manually dropped out."""
    a.session_exists(sname)
    await a.mark_dropout(sname, body.unames)

    return dict(marked_dropout=body.unames)


# =============================================================================
# Data Export API
# =============================================================================


@router.get("/session/{sname}/data/")
async def get_session_data(
    sname: str,
    since: float = Query(
        default=0.0, description="Only return data updated since this epoch timestamp"
    ),
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get all session data in display format, optionally filtered by timestamp."""
    a.session_exists(sname)
    data, last_update = await a.everything_from_session_display(sname, since)

    return dict(data=data, last_update=last_update)


@router.get("/session/{sname}/data/csv/")
async def download_session_csv(
    sname: str,
    format: str = Query(
        default="ultralong", description="Export format: ultralong, sparse, or latest"
    ),
    gvar: list[str] = Query(default=[], description="Group-by variables"),
    filters: bool = Query(default=False, description="Apply reasonable filters"),
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Download session data as CSV."""
    a.session_exists(sname)

    if format not in ("ultralong", "sparse", "latest"):
        raise HTTPException(
            status_code=400, detail="Invalid format. Use: ultralong, sparse, or latest"
        )

    csv_data = a.generate_csv(sname, format, gvar, filters)

    return Response(
        csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={sname}.csv"},
    )


@router.get("/session/{sname}/data/json/")
async def download_session_json(
    sname: str,
    format: str = Query(
        default="ultralong", description="Export format: ultralong, sparse, or latest"
    ),
    gvar: list[str] = Query(default=[], description="Group-by variables"),
    filters: bool = Query(default=False, description="Apply reasonable filters"),
    bauth: None = Depends(a.require_bearer_token),
) -> StreamingResponse:
    """Download session data as JSON (streaming)."""
    a.session_exists(sname)

    if format not in ("ultralong", "sparse", "latest"):
        raise HTTPException(
            status_code=400, detail="Invalid format. Use: ultralong, sparse, or latest"
        )

    return StreamingResponse(
        a.generate_json(sname, format, gvar, filters),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={sname}.json"},
    )


@router.get("/session/{sname}/page-times/")
async def get_page_times(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Download page visit times as CSV."""
    a.session_exists(sname)

    return Response(
        a.page_times(sname),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={sname}-page-times.csv"},
    )


# =============================================================================
# Rooms API
# =============================================================================


@router.get("/rooms/")
async def list_rooms(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """List all rooms with their configuration."""
    return dict(a.rooms())


@router.get("/room/{roomname}/")
async def get_room(
    roomname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get detailed information about a specific room."""
    a.room_exists(roomname)

    with Admin() as admin:
        room = admin.rooms[roomname]
        return dict(
            name=roomname,
            config=room.get("config"),
            labels=room.get("labels"),
            capacity=room.get("capacity"),
            open=room.get("open"),
            sname=room.get("sname"),
        )


@router.post("/rooms/", status_code=201)
async def create_room(
    body: RoomCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new room."""
    if body.config and body.config not in u.CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid configuration")

    if body.sname:
        a.session_exists(body.sname)

    with Admin() as admin:
        if body.name in admin.rooms:
            raise HTTPException(status_code=400, detail="Room name already exists")

        admin.rooms[body.name] = r.room(
            name=body.name,
            config=body.config,
            labels=body.labels,
            capacity=body.capacity,
            open=body.open,
            sname=body.sname,
        )

    if body.sname:
        with Session(body.sname) as session:
            session.room = body.name

    return dict(name=body.name, created=True)


@router.patch("/room/{roomname}/")
async def update_room(
    roomname: str,
    body: RoomUpdate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Update room settings (only when no session is associated)."""
    a.room_exists(roomname)

    if body.config and body.config not in u.CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid configuration")

    with Admin() as admin:
        if admin.rooms[roomname]["sname"] is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot edit room settings while a session is associated",
            )

        admin.rooms[roomname] = r.room(
            name=roomname,
            config=body.config,
            labels=body.labels,
            capacity=body.capacity,
            open=body.open,
            sname=None,
        )

    return dict(name=roomname, updated=True)


@router.delete("/room/{roomname}/")
async def delete_room(
    roomname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Delete a room (only when no session is associated)."""
    a.room_exists(roomname)

    try:
        await a.delete_room(roomname)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return dict(name=roomname, deleted=True)


@router.post("/room/{roomname}/disassociate/")
async def disassociate_room(
    roomname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Disassociate a room from its current session."""
    a.room_exists(roomname)

    with Admin() as admin:
        sname = admin.rooms[roomname]["sname"]

    if sname is None:
        raise HTTPException(status_code=400, detail="Room has no associated session")

    await a.disassociate(roomname, sname)

    return dict(name=roomname, disassociated=True)


@router.post("/room/{roomname}/session/", status_code=201)
async def create_session_in_room(
    roomname: str,
    body: RoomSessionCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new session within a room."""
    a.room_exists(roomname)

    if body.config not in u.CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid configuration")

    with Admin() as admin:
        if admin.rooms[roomname]["sname"] is not None:
            raise HTTPException(
                status_code=400, detail="Room already has an active session"
            )

    settings_parsed = (
        body.settings
        if body.settings is not None
        else u.CONFIGS_EXTRA.get(body.config, {}).get("settings", {})
    )

    assignees_list: list[Any] = body.assignees or []

    data: list[Any] = []

    if body.n_players > len(assignees_list):
        for _ in range(body.n_players - len(assignees_list)):
            assignees_list.append(None)

    for _, label in zip(range(body.n_players), assignees_list):
        if label is None:
            data.append({})
        else:
            data.append({"label": label})

    with Admin() as admin:
        sid = c.create_session(
            admin,
            body.config,
            sname=body.sname,
            settings=settings_parsed,
        )

        admin.rooms[roomname]["sname"] = sid.sname
        admin.rooms[roomname]["open"] = True

        if body.no_grow:
            admin.rooms[roomname]["capacity"] = body.n_players

    with t.materialize(sid) as session:
        session.room = roomname

        c.create_players(
            session,
            n=body.n_players,
            unames=body.unames,
            data=data,
        )

    c.finalize_session(sid)
    r.start(roomname)

    return dict(sname=sid.sname, roomname=roomname, created=True)


@router.get("/room/{roomname}/online/")
async def get_room_online(
    roomname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get online status for a room's waiting area."""
    a.room_exists(roomname)
    return await a.info_online(f"^{roomname}")


# =============================================================================
# Configurations API
# =============================================================================


@router.get("/configs/")
async def list_configs(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """List all available configurations and apps."""
    return a.configs()


@router.get("/configs/{cname}/summary/")
async def get_config_summary(
    cname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get a human-readable summary of a configuration."""
    if cname not in u.CONFIGS:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return dict(
        name=cname,
        summary=a.config_summary(cname),
        apps=u.CONFIGS[cname],
        settings=u.CONFIGS_EXTRA.get(cname, {}).get("settings", {}),
        multiple_of=u.CONFIGS_EXTRA.get(cname, {}).get("multiple_of", 1),
    )


# =============================================================================
# System API
# =============================================================================


@router.get("/announcements/")
async def get_announcements(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Fetch announcements from upstream."""
    try:
        return await a.announcements()
    except Exception:
        return dict(error="Failed to fetch announcements")


@router.get("/session/{sname}/digest/")
async def get_session_digest(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get list of apps that have digest methods available."""
    a.session_exists(sname)

    return dict(apps=a.get_digest(sname))


@router.get("/auth/sessions/")
async def get_auth_sessions(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get information about active authentication sessions."""
    return a.get_active_auth_sessions()


@router.get("/status/")
async def get_status(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get server status information."""
    dbsize_bytes = d.DATABASE.size()
    dbsize = float(dbsize_bytes) / (1024**2) if dbsize_bytes is not None else None

    return dict(
        version=u.__version__,
        database_size_mb=dbsize,
        packages={
            dist.metadata["name"]: dist.version
            for dist in importlib.metadata.distributions()
        },
        public_demo=d.PUBLIC_DEMO,
    )
