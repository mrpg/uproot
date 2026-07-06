# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file implements the Admin REST API at /admin/api/.

All endpoints require Bearer token authentication via the Authorization header.
Tokens are configured in deployment.API_KEYS.
"""

import hmac
import importlib.metadata
import sys
from pathlib import Path
from typing import Any, Optional, TypeAlias

import orjson
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from pydantic import BaseModel, Field

import uproot as u
import uproot.admin as a
import uproot.core as c
import uproot.deployment as d
import uproot.i18n as i18n
import uproot.rooms as r
import uproot.types as t
from uproot.pages import BUILTINS
from uproot.pages import ENV as PENV
from uproot.pages import static_factory
from uproot.storage import Admin, Session, Storage

router = APIRouter(prefix=f"{d.ROOT}/admin/api/v1")
Session_: TypeAlias = Storage

# =============================================================================
# Pydantic Models for Request/Response Validation
# =============================================================================


class SessionCreate(BaseModel):
    """Request body for creating a new session."""

    config: str = Field(..., description="Configuration name")
    n_players: int = Field(..., ge=0, description="Number of players to create")
    sname: Optional[str] = Field(
        None, description="Custom session name (auto-generated if omitted)"
    )
    unames: Optional[list[str]] = Field(
        None, description="Custom usernames for players"
    )
    settings: Optional[dict[str, Any]] = Field(None, description="Session settings")
    simulate: bool = Field(False, description="Enable response simulation")


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
    open: Optional[bool] = Field(
        None,
        description=(
            "Whether the room is open for joining "
            "(defaults to true if sname is given, false otherwise)"
        ),
    )
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


class PlayerTimeout(BaseModel):
    """Request body for adjusting player timeouts."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    delta: float = Field(60.0, description="Timeout adjustment in seconds")


class PlayerMessage(BaseModel):
    """Request body for sending admin messages to players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    message: str = Field(..., description="Message to send")


class AdminchatMessage(BaseModel):
    """Request body for sending an admin chat message to one player."""

    message: str = Field(..., description="Message to send")
    enable_replies: Optional[bool] = Field(
        None,
        description="Optionally update whether the player may reply",
    )


class AdminchatBroadcast(BaseModel):
    """Request body for sending an admin chat message to multiple players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    message: str = Field(..., description="Message to send")
    enable_replies: Optional[bool] = Field(
        None,
        description="Optionally update whether all recipients may reply",
    )


class AdminchatReplies(BaseModel):
    """Request body for toggling player reply permission."""

    enabled: bool = Field(..., description="Whether player replies are enabled")


class DescriptionUpdate(BaseModel):
    """Request body for updating session description."""

    description: str = Field("", description="New description (empty to clear)")


class SettingsUpdate(BaseModel):
    """Request body for updating session settings."""

    settings: dict[str, Any] = Field(..., description="New settings")


class RoomSessionCreate(BaseModel):
    """Request body for creating a session within a room."""

    config: str = Field(..., description="Configuration name")
    n_players: int = Field(..., ge=0, description="Number of players")
    assignees: Optional[list[str]] = Field(
        None, description="Labels to assign to players"
    )
    settings: Optional[dict[str, Any]] = Field(None, description="Session settings")
    sname: Optional[str] = Field(None, description="Custom session name")
    unames: Optional[list[str]] = Field(None, description="Custom usernames")
    no_grow: bool = Field(False, description="Lock capacity to n_players")
    simulate: bool = Field(False, description="Enable response simulation")


class RoomUpdate(BaseModel):
    """Request body for updating room settings."""

    config: Optional[str] = Field(None, description="Default configuration")
    labels: Optional[list[str]] = Field(None, description="Allowed labels")
    capacity: Optional[int] = Field(None, ge=1, description="Maximum capacity")
    open: Optional[bool] = Field(
        None,
        description=(
            "Whether the room is open "
            "(defaults to true if sname is given, otherwise unchanged)"
        ),
    )
    sname: Optional[str] = Field(
        None, description="Existing session to associate with the room"
    )


class RoomOpen(BaseModel):
    """Request body for setting a room's open status."""

    open: bool = Field(..., description="Whether the room should be open")


class RoomCapacity(BaseModel):
    """Request body for setting a room's capacity."""

    capacity: Optional[int] = Field(
        ..., ge=1, description="Maximum capacity (null for unlimited)"
    )


class RoomClose(BaseModel):
    """Request body for closing a room."""

    disassociate: bool = Field(
        False,
        description="If true, disassociate the session before closing",
    )


class PlayersGroup(BaseModel):
    """Request body for grouping player actions."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    action: str = Field(
        ...,
        description="Grouping action: same_group, reset, or by_size",
    )
    group_size: int = Field(1, ge=1, description="Group size for by_size")
    shuffle: bool = Field(False, description="Shuffle players before grouping")
    reload: bool = Field(False, description="Whether to trigger page reload")


class PlayersChatReplies(BaseModel):
    """Request body for toggling admin chat replies for multiple players."""

    unames: list[str] = Field(..., min_length=1, description="List of usernames")
    enabled: bool = Field(..., description="Whether player replies are enabled")


class AuthLogin(BaseModel):
    """Request body for creating the same browser admin session as /admin/login/."""

    user: str = Field("admin", description="Admin username")
    pw: str = Field("", description="Admin password")
    token: str = Field("", description="Auto-login token")
    pow_challenge: str = Field("", description="Proof-of-work challenge")
    pow_solution: str = Field("", description="Proof-of-work solution")


class AuthToken(BaseModel):
    """Request body naming a browser admin auth token."""

    auth_token: str = Field(..., description="Value of the uauth browser cookie")


def ensure_config_exists(config: str) -> None:
    if config not in u.CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid configuration")


def ensure_unames_count(n_players: int, unames: Optional[list[str]]) -> None:
    if unames is not None and len(unames) != n_players:
        raise HTTPException(
            status_code=400,
            detail="Number of player names must match n_players",
        )


def ensure_assignees_count(n_players: int, assignees: Optional[list[str]]) -> None:
    if assignees is not None and len(assignees) > n_players:
        raise HTTPException(
            status_code=400,
            detail="Number of assignees cannot exceed n_players",
        )


def create_room_payload(
    name: str,
    config: Optional[str],
    labels: Optional[list[str]],
    capacity: Optional[int],
    open: bool,
    sname: Optional[str],
) -> dict[str, Any]:
    try:
        return r.room(
            name=name,
            config=config,
            labels=labels,
            capacity=capacity,
            open=open,
            sname=sname,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def api_value(value: Any) -> Any:
    try:
        orjson.dumps(value)
        return value
    except TypeError:
        return a.pipeline_result_display(value)


def room_detail(roomname: str) -> dict[str, Any]:
    with Admin() as admin:
        room = admin.rooms[roomname]
        payload = {
            "name": roomname,
            "config": room.get("config"),
            "labels": room.get("labels"),
            "capacity": room.get("capacity"),
            "open": room.get("open"),
            "sname": room.get("sname"),
            "urls": {
                "room": f"{d.ROOT}/room/{roomname}/",
                "label_template": f"{d.ROOT}/room/{roomname}/?label={{label}}",
            },
        }

    if payload["sname"] is not None:
        with Session(payload["sname"]) as session:
            payload["n_players"] = len(session._uproot_players)

    return payload


def session_detail(sname: str) -> dict[str, Any]:
    with Session(sname) as session:
        players = [pid.uname for pid in session._uproot_players]
        groups = [
            gid.gname if hasattr(gid, "gname") else gid
            for gid in session._uproot_groups
        ]
        models = [
            mid.mname if hasattr(mid, "mname") else mid
            for mid in session._uproot_models
        ]

        return {
            "sname": session.name,
            "config": session.config,
            "active": session.active,
            "testing": session._uproot_testing,
            "initialized": session._uproot_initialized,
            "simulate": session._uproot_simulate,
            "description": session.description,
            "room": session.room,
            "settings": session.settings,
            "secret": session._uproot_secret,
            "n_players": len(players),
            "n_groups": len(groups),
            "n_models": len(models),
            "players": players,
            "groups": groups,
            "models": models,
            "apps": session.apps,
            "urls": {
                "session": f"{d.ROOT}/s/{sname}/{session._uproot_secret}/",
                "player_template": f"{d.ROOT}/p/{sname}/{{uname}}/",
            },
        }


async def pipeline_data_from_request(request: Request) -> tuple[Any, bool]:
    if request.method != "POST":
        return None, False

    body = await request.body()
    if not body.strip():
        return None, False

    try:
        return orjson.loads(body), True
    except orjson.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail="Pipeline data must be valid JSON"
        ) from exc


def missing_i18n_terms() -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}

    for term, lang in sorted(i18n.MISSING):
        term_str = str(term)

        if term_str not in missing:
            missing[term_str] = []
        missing[term_str].append(lang)

    return missing


def valid_export_format(format: str) -> None:
    if format not in ("ultralong", "sparse", "latest"):
        raise HTTPException(
            status_code=400, detail="Invalid format. Use: ultralong, sparse, or latest"
        )


def briefcase_export_response(
    sname: str,
    gvar: list[str],
    filters: bool,
    filetype: str,
) -> Response:
    if filetype not in ("csv", "jsonl"):
        raise HTTPException(
            status_code=400, detail="Invalid filetype. Use: csv or jsonl"
        )

    return Response(
        a.generate_briefcase(sname, gvar, filters, filetype),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={sname}.zip"},
    )


def jsonl_export_response(
    sname: str,
    format: str,
    gvar: list[str],
    filters: bool,
) -> StreamingResponse:
    valid_export_format(format)

    return StreamingResponse(
        a.generate_jsonl(sname, format, gvar, filters),
        media_type="application/jsonl",
        headers={"Content-Disposition": f"attachment; filename={sname}.jsonl"},
    )


def admin_app_template(appname: str, template_name: str) -> Path:
    template_path = Path(".") / appname / template_name
    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"{template_name} not found")

    return template_path


def admin_app_context(
    appname: str, session: Session_, data: dict[str, Any] | None = None
) -> dict[str, Any]:
    return (
        (data or {})
        | BUILTINS
        | {
            "__panic__": True,
            "session": session,
            "internalstatic": static_factory(),
            "projectstatic": static_factory("_project"),
            "appstatic": static_factory(appname),
            "C": getattr(u.APPS[appname], "C", {}),
        }
    )


async def rendered_digest_fragment(sname: str, appname: str) -> str:
    if appname not in a.get_digest(sname):
        raise HTTPException(status_code=404, detail="Digest not found")

    template_path = admin_app_template(appname, "AdminDigest.html")
    app = u.APPS[appname]

    with Session(sname) as session:
        value = await t.ensure_awaitable(app.digest, session=session)
        data = value if isinstance(value, dict) else {"data": value}
        context = admin_app_context(appname, session, data)
        return await PENV.get_template(str(template_path)).render_async(**context)


async def rendered_pipeline_fragment(sname: str, appname: str) -> str:
    if appname not in a.get_pipelines(sname):
        raise HTTPException(status_code=404, detail="Pipeline not found")

    template_path = admin_app_template(appname, "AdminPipeline.html")

    with Session(sname) as session:
        context = admin_app_context(appname, session)
        return await PENV.get_template(str(template_path)).render_async(**context)


# =============================================================================
# Sessions API
# =============================================================================


@router.get("/sessions/")
async def list_sessions(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """List all sessions with their metadata."""
    return a.sessions()


@router.get("/sessions/{sname}/")
async def get_session(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get detailed information about a specific session."""
    a.session_exists(sname)
    return session_detail(sname)


@router.post("/sessions/", status_code=201)
async def create_session(
    body: SessionCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new session with the specified configuration and players."""
    ensure_config_exists(body.config)
    ensure_unames_count(body.n_players, body.unames)

    settings_parsed = (
        body.settings
        if body.settings is not None
        else u.CONFIGS_EXTRA.get(body.config, {}).get("settings", {})
    )

    with Admin() as admin:
        if body.sname and body.sname in admin._uproot_sessions:
            raise HTTPException(status_code=400, detail="Session name already exists")

        sid = c.create_session(
            admin,
            body.config,
            sname=body.sname,
            settings=settings_parsed,
        )

    with t.materialize(sid) as session:
        if body.simulate:
            session._uproot_simulate = True

        c.create_players(
            session,
            n=body.n_players,
            unames=body.unames,
        )

    return {"sname": sid.sname, "created": True}


@router.patch("/sessions/{sname}/active/")
async def toggle_session_active(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Toggle the active status of a session."""
    a.session_exists(sname)
    await a.flip_active(sname)

    with Session(sname) as session:
        return {"active": session.active}


@router.patch("/sessions/{sname}/testing/")
async def toggle_session_testing(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Toggle the testing mode of a session."""
    a.session_exists(sname)
    await a.flip_testing(sname)

    with Session(sname) as session:
        return {"testing": session._uproot_testing}


@router.post("/sessions/{sname}/initialize/")
async def initialize_session(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Run new_session callbacks for a session that has not been initialized."""
    a.session_exists(sname)
    await a.run_new_session(sname)

    with Session(sname) as session:
        return {"initialized": session._uproot_initialized}


@router.patch("/sessions/{sname}/description/")
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

    return {"description": body.description if body.description else None}


@router.patch("/sessions/{sname}/settings/")
async def update_session_settings(
    sname: str,
    body: SettingsUpdate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Update the settings of a session."""
    a.session_exists(sname)
    await a.update_settings(sname, **body.settings)

    return {"settings": body.settings}


# =============================================================================
# Players API
# =============================================================================


@router.get("/sessions/{sname}/players/")
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


@router.get("/sessions/{sname}/players/online/")
async def get_online_players(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get online status and info for all players in a session."""
    a.session_exists(sname)
    return await a.info_online(sname)


@router.get("/sessions/{sname}/multiview/")
async def get_multiview_players(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get player metadata needed to reproduce the admin multiview."""
    a.session_exists(sname)
    players = []

    with Session(sname) as session:
        for player_id, pid in enumerate(session._uproot_players):
            with t.materialize(pid) as player:
                players.append(
                    {
                        "id": player_id,
                        "uname": player.name,
                        "label": player.label,
                        "url": f"{d.ROOT}/p/{sname}/{player.name}/",
                    }
                )

    return {"sname": sname, "players": players}


@router.patch("/sessions/{sname}/players/fields/")
async def set_player_fields(
    sname: str,
    body: PlayersFields,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Set arbitrary fields on specified players."""
    a.session_exists(sname)
    await a.insert_fields(sname, body.unames, body.fields, body.reload)

    return {"updated": body.unames, "fields": list(body.fields.keys())}


@router.post("/sessions/{sname}/players/advance/")
async def advance_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Advance specified players by one page."""
    a.session_exists(sname)
    return await a.advance_by_one(sname, body.unames)


@router.post("/sessions/{sname}/players/revert/")
async def revert_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Revert specified players by one page."""
    a.session_exists(sname)
    return await a.revert_by_one(sname, body.unames)


@router.post("/sessions/{sname}/players/end/")
async def put_players_to_end(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Move specified players to the end of the experiment."""
    a.session_exists(sname)
    return await a.put_to_end(sname, body.unames)


@router.post("/sessions/{sname}/players/reload/")
async def reload_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Force page reload for specified players."""
    a.session_exists(sname)
    await a.reload(sname, body.unames)

    return {"reloaded": body.unames}


@router.post("/sessions/{sname}/players/timeout/")
async def adjust_timeout(
    sname: str,
    body: PlayerTimeout,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Adjust the page timeout for specified players."""
    a.session_exists(sname)

    try:
        await a.adjust_timeout(sname, body.unames, body.delta)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"adjusted": body.unames, "delta": body.delta}


@router.post("/sessions/{sname}/players/redirect/")
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

    return {"redirected": body.unames, "url": body.url}


@router.post("/sessions/{sname}/players/message/")
async def message_players(
    sname: str,
    body: PlayerMessage,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Send an admin message to specified players."""
    a.session_exists(sname)
    await a.adminmessage(sname, body.unames, body.message)

    return {"messaged": body.unames}


@router.post("/sessions/{sname}/players/initialize/")
async def initialize_players(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Run new_player callbacks for players that have not been initialized."""
    a.session_exists(sname)
    await a.run_new_player(sname, body.unames)

    return {"initialized": body.unames}


@router.post("/sessions/{sname}/players/group/")
async def group_players(
    sname: str,
    body: PlayersGroup,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Manage group assignments for selected players."""
    a.session_exists(sname)

    try:
        return await a.group_players(
            sname,
            body.unames,
            body.action,
            body.group_size,
            body.shuffle,
            body.reload,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/sessions/{sname}/admin-chat/")
async def get_adminchat_overview(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """Summarize admin chat state for each player in a session."""
    a.session_exists(sname)
    return await a.adminchat_overview(sname)


@router.get("/sessions/{sname}/players/{uname}/admin-chat/")
async def get_player_adminchat(
    sname: str,
    uname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get admin chat metadata and transcript for one player."""
    a.session_exists(sname)
    return await a.adminchat_thread(sname, uname)


@router.post("/sessions/{sname}/players/{uname}/admin-chat/")
async def send_player_adminchat(
    sname: str,
    uname: str,
    body: AdminchatMessage,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Send an admin chat message to one player."""
    a.session_exists(sname)
    return await a.send_adminchat(sname, uname, body.message, body.enable_replies)


@router.patch("/sessions/{sname}/players/{uname}/admin-chat/replies/")
async def set_player_adminchat_replies(
    sname: str,
    uname: str,
    body: AdminchatReplies,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Enable or disable a player's ability to reply in admin chat."""
    a.session_exists(sname)
    return await a.set_adminchat_replies(sname, uname, body.enabled)


@router.post("/sessions/{sname}/players/admin-chat/")
async def broadcast_adminchat(
    sname: str,
    body: AdminchatBroadcast,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Send an admin chat message to multiple players at once."""
    a.session_exists(sname)
    return await a.send_adminchat_to_players(
        sname, body.unames, body.message, body.enable_replies
    )


@router.patch("/sessions/{sname}/players/admin-chat/replies/")
async def set_players_adminchat_replies(
    sname: str,
    body: PlayersChatReplies,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Enable or disable admin chat replies for multiple players."""
    a.session_exists(sname)
    return await a.set_adminchat_replies_for_players(sname, body.unames, body.enabled)


@router.post("/sessions/{sname}/players/dropout/")
async def mark_players_dropout(
    sname: str,
    body: PlayersAction,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Mark specified players as manually dropped out."""
    a.session_exists(sname)
    info_online = await a.mark_dropout(sname, body.unames)

    return {
        "marked_dropout": body.unames,
        "info": info_online["info"],
        "online": info_online["online"],
    }


# =============================================================================
# Data Export API
# =============================================================================


@router.get("/sessions/{sname}/data/")
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

    return {"data": data, "last_update": last_update}


@router.get("/sessions/{sname}/data/export/")
async def download_session_export(
    sname: str,
    filetype: str = Query(default="csv", description="Export file type: csv or jsonl"),
    gvar: list[str] = Query(
        default=[],
        description="Group-by variables for the optional grouped latest format",
    ),
    filters: bool = Query(default=True, description="Apply reasonable filters"),
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Download a ZIP briefcase of session data, as in the admin UI.

    The briefcase always contains the ultralong, sparse, and latest formats
    as per-storage CSV or JSONL files; passing gvar adds a grouped latest
    format on top.
    """
    a.session_exists(sname)

    return briefcase_export_response(sname, gvar, filters, filetype)


@router.get("/sessions/{sname}/data/jsonl/")
async def download_session_jsonl(
    sname: str,
    format: str = Query(
        default="ultralong", description="Export format: ultralong, sparse, or latest"
    ),
    gvar: list[str] = Query(default=[], description="Group-by variables"),
    filters: bool = Query(default=False, description="Apply reasonable filters"),
    bauth: None = Depends(a.require_bearer_token),
) -> StreamingResponse:
    """Download session data as JSONL (streaming)."""
    a.session_exists(sname)

    return jsonl_export_response(sname, format, gvar, filters)


@router.get("/sessions/{sname}/page-times/")
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


@router.get("/sessions/{sname}/digests/")
async def get_session_digests(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Run all available app digests for a session."""
    a.session_exists(sname)
    available = a.get_digest(sname)
    digests = {}

    with Session(sname) as session:
        for appname in available:
            app = u.APPS[appname]
            digests[appname] = api_value(
                await t.ensure_awaitable(app.digest, session=session)
            )

    return {"apps": available, "digests": digests}


@router.get("/sessions/{sname}/digests/html/")
async def get_session_digest_fragments(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Render the app-authored AdminDigest.html fragments shown by the admin UI."""
    a.session_exists(sname)
    fragments = {}

    for appname in a.get_digest(sname):
        fragments[appname] = await rendered_digest_fragment(sname, appname)

    return {"apps": list(fragments), "html": fragments}


@router.get("/sessions/{sname}/digests/{appname}/")
async def get_session_digest(
    sname: str,
    appname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Run one app digest for a session."""
    a.session_exists(sname)

    if appname not in a.get_digest(sname):
        raise HTTPException(status_code=404, detail="Digest not found")

    app = u.APPS[appname]

    with Session(sname) as session:
        digest = await t.ensure_awaitable(app.digest, session=session)

    return {"app": appname, "digest": api_value(digest)}


@router.get("/sessions/{sname}/digests/{appname}/html/")
async def get_session_digest_fragment(
    sname: str,
    appname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> HTMLResponse:
    """Render one app-authored AdminDigest.html fragment."""
    a.session_exists(sname)
    return HTMLResponse(await rendered_digest_fragment(sname, appname))


@router.get("/sessions/{sname}/pipelines/")
async def list_session_pipelines(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """List apps that provide a pipeline for a session."""
    a.session_exists(sname)
    return {"apps": a.get_pipelines(sname)}


@router.get("/sessions/{sname}/pipelines/html/")
async def list_session_pipeline_fragments(
    sname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Render app-authored AdminPipeline.html fragments shown by the admin UI."""
    a.session_exists(sname)
    fragments = {}

    for appname in a.get_pipelines(sname):
        template_path = Path(".") / appname / "AdminPipeline.html"
        if template_path.exists():
            fragments[appname] = await rendered_pipeline_fragment(sname, appname)

    return {"apps": a.get_pipelines(sname), "html": fragments}


@router.get("/sessions/{sname}/pipelines/{appname}/html/")
async def get_session_pipeline_fragment(
    sname: str,
    appname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> HTMLResponse:
    """Render one app-authored AdminPipeline.html fragment."""
    a.session_exists(sname)
    return HTMLResponse(await rendered_pipeline_fragment(sname, appname))


async def run_session_pipeline_response(
    request: Request,
    sname: str,
    appname: str,
    filetype: str = Query(default="csv", description="Export file type: csv or jsonl"),
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Run an app pipeline, optionally passing a JSON request body."""
    a.session_exists(sname)

    if appname not in a.get_pipelines(sname):
        raise HTTPException(status_code=404, detail="Pipeline not found")

    pipeline_data, data_was_provided = await pipeline_data_from_request(request)

    try:
        result = await a.run_pipeline(sname, appname, pipeline_data, data_was_provided)
    except a.PipelineInvocationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not a.is_custom_data_export(result):
        return PlainTextResponse(a.pipeline_result_display(result))

    if filetype not in ("csv", "jsonl"):
        raise HTTPException(status_code=400, detail="Invalid filetype")

    rows = result
    filename = f"{sname}-{appname}"

    if filetype == "csv":
        return Response(
            a.generate_custom_csv(rows),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )

    return StreamingResponse(
        a.generate_custom_jsonl(rows),
        media_type="application/jsonl",
        headers={"Content-Disposition": f"attachment; filename={filename}.jsonl"},
    )


@router.get("/sessions/{sname}/pipelines/{appname}/runs/")
async def get_session_pipeline_run(
    request: Request,
    sname: str,
    appname: str,
    filetype: str = Query(default="csv", description="Export file type: csv or jsonl"),
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Run an app pipeline without custom JSON data, matching the admin UI button."""
    return await run_session_pipeline_response(request, sname, appname, filetype, bauth)


@router.post("/sessions/{sname}/pipelines/{appname}/runs/")
async def create_session_pipeline_run(
    request: Request,
    sname: str,
    appname: str,
    filetype: str = Query(default="csv", description="Export file type: csv or jsonl"),
    bauth: None = Depends(a.require_bearer_token),
) -> Response:
    """Run an app pipeline, optionally passing a JSON request body."""
    return await run_session_pipeline_response(request, sname, appname, filetype, bauth)


# =============================================================================
# Rooms API
# =============================================================================


@router.get("/rooms/")
async def list_rooms(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, dict[str, Any]]:
    """List all rooms with their configuration."""
    return dict(a.rooms())


@router.get("/rooms/{roomname}/")
async def get_room(
    roomname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get detailed information about a specific room."""
    a.room_exists(roomname)
    return room_detail(roomname)


@router.post("/rooms/", status_code=201)
async def create_room(
    body: RoomCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new room."""
    if body.config:
        ensure_config_exists(body.config)

    if body.sname:
        a.ensure_session_available_for_room(body.sname, body.name)

    # Unless overridden, associating an existing session opens the room: the
    # point of the association is to admit players into that session right away.
    open_status = bool(body.sname) if body.open is None else body.open

    with Admin() as admin:
        if body.name in admin.rooms:
            raise HTTPException(status_code=400, detail="Room name already exists")

        admin.rooms[body.name] = create_room_payload(
            name=body.name,
            config=body.config,
            labels=body.labels,
            capacity=body.capacity,
            open=open_status,
            sname=body.sname,
        )

    if body.sname:
        with Session(body.sname) as session:
            session.room = body.name

        if open_status:
            r.start(body.name)

    return room_detail(body.name) | {"created": True}


@router.patch("/rooms/{roomname}/")
async def update_room(
    roomname: str,
    body: RoomUpdate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Update room settings, optionally associating an existing session
    (only when no session is currently associated)."""
    a.room_exists(roomname)

    if body.sname:
        a.ensure_session_available_for_room(body.sname, roomname)

    with Admin() as admin:
        current = admin.rooms[roomname]

        if current["sname"] is not None:
            raise HTTPException(
                status_code=400,
                detail="Cannot edit room settings while a session is associated",
            )

        if body.open is None and "open" in body.model_fields_set:
            raise HTTPException(status_code=400, detail="open cannot be null")

        config = body.config if "config" in body.model_fields_set else current["config"]
        labels = body.labels if "labels" in body.model_fields_set else current["labels"]
        capacity = (
            body.capacity
            if "capacity" in body.model_fields_set
            else current["capacity"]
        )
        sname = body.sname or None

        if "open" in body.model_fields_set:
            open_status = body.open
        elif sname:
            # Unless overridden, associating an existing session opens the
            # room: the point of the association is to admit players into
            # that session right away.
            open_status = True
        else:
            open_status = current["open"]

        if config:
            ensure_config_exists(config)

        admin.rooms[roomname] = create_room_payload(
            name=roomname,
            config=config,
            labels=labels,
            capacity=capacity,
            open=bool(open_status),
            sname=sname,
        )

    if sname:
        with Session(sname) as session:
            session.room = roomname

        if open_status:
            # Release players already waiting on this room's hello page
            r.start(roomname)

    return room_detail(roomname) | {"updated": True}


@router.delete("/rooms/{roomname}/")
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

    return {"name": roomname, "deleted": True}


@router.delete("/rooms/{roomname}/sessions/")
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

    return room_detail(roomname) | {"disassociated": True}


@router.patch("/rooms/{roomname}/open/")
async def set_room_open(
    roomname: str,
    body: RoomOpen,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Set a room's open status without requiring disassociation."""
    a.room_exists(roomname)

    try:
        await a.set_room_open(roomname, body.open)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return room_detail(roomname) | {"open": body.open}


@router.patch("/rooms/{roomname}/capacity/")
async def set_room_capacity(
    roomname: str,
    body: RoomCapacity,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Set a room's capacity, even while a session is associated."""
    a.room_exists(roomname)

    try:
        await a.set_room_capacity(roomname, body.capacity)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return room_detail(roomname)


@router.post("/rooms/{roomname}/close/")
async def close_room(
    roomname: str,
    body: RoomClose,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Close a room, optionally disassociating its session first."""
    a.room_exists(roomname)

    try:
        await a.close_room(roomname, body.disassociate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return room_detail(roomname) | {
        "closed": True,
        "disassociated": body.disassociate,
    }


@router.post("/rooms/{roomname}/sessions/", status_code=201)
async def create_session_in_room(
    roomname: str,
    body: RoomSessionCreate,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Create a new session within a room."""
    a.room_exists(roomname)
    ensure_config_exists(body.config)
    ensure_unames_count(body.n_players, body.unames)
    ensure_assignees_count(body.n_players, body.assignees)

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
        assignees_list.extend([None] * (body.n_players - len(assignees_list)))

    for label in assignees_list[: body.n_players]:
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

        if body.simulate:
            session._uproot_simulate = True

        c.create_players(
            session,
            n=body.n_players,
            unames=body.unames,
            data=data,
        )

    r.start(roomname)

    return session_detail(sid.sname) | {
        "roomname": roomname,
        "created": True,
    }


@router.get("/rooms/{roomname}/online/")
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


@router.get("/dashboard/")
async def get_dashboard(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get the same top-level aggregate shown on the admin dashboard."""
    sessions = a.sessions()

    return {
        "configs": a.configs(),
        "rooms": a.rooms(),
        "active_sessions": {
            sname: sinfo for sname, sinfo in sessions.items() if sinfo["active"]
        },
    }


@router.get("/configs/")
async def list_configs(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """List all available configurations and apps."""
    return a.configs()


@router.get("/configs/{cname}/")
async def get_config(
    cname: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get details for a configuration."""
    if cname not in u.CONFIGS:
        raise HTTPException(status_code=404, detail="Configuration not found")

    return {
        "name": cname,
        "summary": a.config_summary(cname),
        "apps": u.CONFIGS[cname],
        "settings": u.CONFIGS_EXTRA.get(cname, {}).get("settings", {}),
        "suggested_multiple": u.CONFIGS_EXTRA.get(cname, {}).get(
            "suggested_multiple", 1
        ),
    }


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
        return {"error": "Failed to fetch announcements"}


@router.get("/praise/")
async def get_praise(
    bauth: None = Depends(a.require_bearer_token),
) -> PlainTextResponse:
    """Fetch the same praise text shown by the admin UI."""
    try:
        return PlainTextResponse(await a.praise())
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch praise")


@router.get("/auth/challenge/")
async def get_auth_challenge() -> dict[str, Any]:
    """Issue the same login proof-of-work challenge used by the admin UI."""
    pow_challenge, pow_difficulty = a.make_pow_challenge()

    return {
        "pow_challenge": pow_challenge,
        "pow_difficulty": pow_difficulty,
        "login_token_enabled": d.LOGIN_TOKEN is not None,
    }


@router.post("/auth/login/", status_code=201)
async def create_auth_session(body: AuthLogin) -> dict[str, Any]:
    """Create the same browser admin session token as submitting /admin/login/."""
    auth_token = None

    if body.token and body.user == "admin" and d.LOGIN_TOKEN is not None:
        if hmac.compare_digest(body.token, d.LOGIN_TOKEN):
            a.ensure_globals()
            auth_token = a.create_auth_token_for_user(body.user)
    else:
        if not a.verify_pow(body.pow_challenge, body.pow_solution, body.user):
            raise HTTPException(status_code=401, detail="Invalid proof of work")

        auth_token = await a.create_auth_token_async(body.user, body.pw)

    if auth_token is None:
        raise HTTPException(status_code=401, detail="Invalid admin credentials")

    session = a.from_cookie(auth_token)

    return {
        "user": session["user"],
        "auth_token": auth_token,
        "cookie": {
            "name": "uauth",
            "value": auth_token,
            "max_age": 86400,
            "path": f"{d.ROOT}/",
            "httponly": True,
            "samesite": "strict",
        },
    }


@router.get("/auth/sessions/")
async def get_auth_sessions(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get information about active authentication sessions."""
    return a.get_active_auth_sessions()


@router.delete("/auth/tokens/current/")
async def revoke_current_auth_session(
    body: AuthToken,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Revoke one browser admin session token, matching /admin/logout/."""
    session = a.from_cookie(body.auth_token)
    if not session["user"]:
        raise HTTPException(status_code=404, detail="Auth token not found")

    revoked = a.revoke_auth_token(body.auth_token)
    return {"user": session["user"], "revoked": revoked}


@router.delete("/auth/tokens/")
async def revoke_current_user_auth_sessions(
    body: AuthToken,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Revoke all browser admin sessions for the user named by one token."""
    session = a.from_cookie(body.auth_token)
    if not session["user"]:
        raise HTTPException(status_code=404, detail="Auth token not found")

    revoked_count = a.revoke_all_user_tokens(session["user"])
    return {"user": session["user"], "revoked": revoked_count}


@router.delete("/auth/sessions/{user}/")
async def revoke_user_auth_sessions(
    user: str,
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Revoke all browser admin sessions for one user."""
    revoked_count = a.revoke_all_user_tokens(user)
    return {"user": user, "revoked": revoked_count}


@router.get("/database/dump/")
async def dump_database(
    bauth: None = Depends(a.require_bearer_token),
) -> StreamingResponse:
    """Download a complete machine-readable database dump."""
    return StreamingResponse(
        d.DATABASE.dump(),
        media_type="application/msgpack",
        headers={"Content-Disposition": "attachment; filename=uproot.msgpack"},
    )


@router.get("/status/")
async def get_status(
    bauth: None = Depends(a.require_bearer_token),
) -> dict[str, Any]:
    """Get server status information."""
    dbsize_bytes = d.DATABASE.size()
    dbsize = float(dbsize_bytes) / (1024**2) if dbsize_bytes is not None else None
    packages = {
        dist.metadata["name"]: dist.version
        for dist in importlib.metadata.distributions()
    }

    return {
        "versions": {
            "uproot": u.__version__,
            "python": sys.version,
        },
        "database": {
            "driver": d.DATABASE.__class__.__name__,
            "size_bytes": dbsize_bytes,
            "size_mb": dbsize,
        },
        "auth_sessions": a.get_active_auth_sessions(),
        "packages": packages,
        "missing_i18n": missing_i18n_terms(),
        "public_demo": d.PUBLIC_DEMO,
        "unsafe": d.UNSAFE,
    }
