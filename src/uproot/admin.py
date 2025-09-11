# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import secrets
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Iterator, Optional

import aiohttp
from fastapi import HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sortedcontainers import SortedDict

import uproot as u
import uproot.cache as cache
import uproot.data as data
import uproot.deployment as d
import uproot.queues as q
import uproot.storage as s
import uproot.types as t


async def adminmessage(sname: t.Sessionname, unames: list[str], msg: str) -> None:
    session_exists(sname, False)

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            dict(
                source="adminmessage",
                data=msg,
                event="_uproot_AdminMessaged",
            ),
        )


def admins() -> str:
    return t.sha256("\n".join(f"{user}\t{pw}" for user, pw in d.ADMINS.items()))


def _get_serializer() -> URLSafeTimedSerializer:
    """Get configured token serializer."""
    # Use key + admins hash as secret key for maximum security
    secret_key = t.sha256(f"{u.KEY}:{admins()}")
    return URLSafeTimedSerializer(secret_key)


def _get_active_tokens() -> set[str]:
    """Get set of currently active tokens from storage."""
    with s.Admin() as admin:
        return getattr(admin, "active_auth_tokens", set())


def _store_active_tokens(tokens: set[str]) -> None:
    """Store set of active tokens to storage."""
    with s.Admin() as admin:
        admin.active_auth_tokens = tokens

    # Clean up expired tokens when storing active ones
    _cleanup_expired_tokens()


def _cleanup_expired_tokens() -> None:
    """Remove expired tokens from storage."""
    serializer = _get_serializer()
    active_tokens = _get_active_tokens()
    valid_tokens = set()

    for token in active_tokens:
        try:
            serializer.loads(token, max_age=86400)  # 24 hours
            valid_tokens.add(token)
        except (BadSignature, SignatureExpired):
            continue  # Token is expired or invalid, don't keep it

    if len(valid_tokens) != len(active_tokens):
        _store_active_tokens(valid_tokens)


async def advance_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[t.Username, Optional[float]]]:
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if -1 < player.show_page < len(player.page_order):
                player.show_page += 1

                q.enqueue(
                    tuple(pid),
                    dict(
                        source="admin",
                        kind="action",
                        payload=dict(
                            action="reload",
                        ),
                    ),
                )

                u.set_info(
                    pid,
                    None,
                    player.page_order,
                    player.show_page,
                )

    return info_online(sname)


async def announcements() -> dict[str, Any]:
    ANNOUNCEMENTS_URL = "https://raw.githubusercontent.com/mrpg/uproot/refs/heads/main/announcements.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(ANNOUNCEMENTS_URL) as response:
            return await response.json(content_type="text/plain")


def config_summary(cname: str) -> str:
    try:
        if cname.startswith("~"):
            return getattr(u.APPS[u.CONFIGS[cname][0]], "DESCRIPTION", "").strip()
        else:
            return " → ".join(u.CONFIGS[cname])
    except Exception:
        return ""


def configs() -> dict[str, SortedDict[str, str]]:
    return dict(
        configs=SortedDict(
            {
                c: displaystr(config_summary(c))
                for c in u.CONFIGS
                if not c.startswith("~")
            }
        ),
        apps=SortedDict(
            {c: displaystr(config_summary(c)) for c in u.CONFIGS if c.startswith("~")}
        ),
    )


def displaystr(s: str) -> str:
    s = s.strip()

    if len(s) > 128:
        s = s[:128] + "…"

    return s


def from_cookie(uauth: str) -> dict[str, str]:
    """Parse authentication token from cookie.

    Returns dict with 'user' and 'token' keys, or empty strings if invalid.
    """
    try:
        serializer = _get_serializer()
        active_tokens = _get_active_tokens()

        # Verify token is in active set and not expired
        if uauth not in active_tokens:
            return dict(user="", token="")

        # Verify token signature and expiration (24 hours)
        data = serializer.loads(uauth, max_age=86400)

        if not isinstance(data, dict) or "user" not in data:
            return dict(user="", token="")

        return dict(user=data["user"], token=uauth)
    except (BadSignature, SignatureExpired, Exception):
        return dict(user="", token="")


def everything_from_session(
    sname: t.Sessionname,
) -> dict[tuple[str, ...], list[t.Value]]:
    # Go ahead… https://www.youtube.com/watch?v=2WhHW8zD620

    matches = dict()
    sname = str(sname)

    for lvl1_k, lvl1_v in cache.MEMORY_HISTORY.items():
        if isinstance(lvl1_v, dict) and sname in lvl1_v:
            k = (
                lvl1_k,
                sname,
            )
            matches |= cache.flatten(cache.get_namespace(k), k)

    return matches


def generate_csv(sname: t.Sessionname, format: str, gvar: list[str]) -> str:
    gvar = [gv for gv in gvar if gv]

    transformer: Callable[[Iterator[dict[str, Any]]], Iterator[dict[str, Any]]]
    transkwargs: dict[str, list[str]]
    priority_fields: list[str]

    match format:
        case "ultralong":
            transformer, transkwargs, priority_fields = data.noop, {}, []
        case "sparse":
            transformer, transkwargs, priority_fields = data.long_to_wide, {}, []
        case "latest":
            transformer, transkwargs, priority_fields = (
                data.latest,
                {"group_by_fields": gvar},
                gvar,
            )
        case _:
            raise NotImplementedError

    alldata = data.partial_matrix(everything_from_session(sname))

    return data.csv_out(
        transformer(alldata, **transkwargs), priority_fields=priority_fields
    )


async def generate_json(
    sname: t.Sessionname, format: str, gvar: list[str]
) -> AsyncGenerator:
    gvar = [gv for gv in gvar if gv]

    transformer: Callable[[Iterator[dict]], Iterator[dict]]
    transkwargs: dict[str, list[str]]

    match format:
        case "ultralong":
            transformer, transkwargs = data.noop, {}
        case "sparse":
            transformer, transkwargs = data.long_to_wide, {}
        case "latest":
            transformer, transkwargs = data.latest, {"group_by_fields": gvar}
        case _:
            raise NotImplementedError

    alldata = data.partial_matrix(everything_from_session(sname))

    async for chunk in data.json_out(transformer(alldata, **transkwargs)):
        yield chunk
        await asyncio.sleep(0)


def create_auth_token(user: str, pw: str) -> Optional[str]:
    """Create a new authentication token for a user.

    Args:
        user: Username
        pw: Password

    Returns:
        Signed token string if credentials are valid, None otherwise
    """
    # Verify credentials first
    if user not in d.ADMINS or d.ADMINS[user] != pw:
        return None

    # Create token data
    token_data = {
        "user": user,
        "created_at": datetime.utcnow().isoformat(),
        "nonce": secrets.token_hex(16),  # Prevent token reuse across sessions
    }

    # Sign the token
    serializer = _get_serializer()
    token = serializer.dumps(token_data)

    # Store token in active set
    active_tokens = _get_active_tokens()
    active_tokens.add(token)
    _store_active_tokens(active_tokens)

    return token


def revoke_auth_token(token: str) -> bool:
    """Revoke a specific authentication token.

    Args:
        token: Token to revoke

    Returns:
        True if token was revoked, False if it wasn't active
    """
    active_tokens = _get_active_tokens()
    if token in active_tokens:
        active_tokens.remove(token)
        _store_active_tokens(active_tokens)
        return True
    return False


def revoke_all_user_tokens(user: str) -> int:
    """Revoke all authentication tokens for a specific user.

    Args:
        user: Username whose tokens should be revoked

    Returns:
        Number of tokens revoked
    """
    serializer = _get_serializer()
    active_tokens = _get_active_tokens()
    tokens_to_keep = set()
    revoked_count = 0

    for token in active_tokens:
        try:
            data = serializer.loads(token, max_age=86400)
            if isinstance(data, dict) and data.get("user") != user:
                tokens_to_keep.add(token)
            else:
                revoked_count += 1
        except (BadSignature, SignatureExpired):
            revoked_count += 1  # Count expired tokens as revoked

    _store_active_tokens(tokens_to_keep)
    return revoked_count


def get_active_sessions() -> dict[str, dict[str, Any]]:
    """Get information about all active authentication sessions.

    Returns:
        Dict mapping usernames to session info
    """
    serializer = _get_serializer()
    active_tokens = _get_active_tokens()
    sessions = {}

    for token in active_tokens:
        try:
            data = serializer.loads(token, max_age=86400)
            if isinstance(data, dict) and "user" in data:
                user = data["user"]
                if user not in sessions:
                    sessions[user] = {"token_count": 0, "created_at": []}
                sessions[user]["token_count"] += 1
                if "created_at" in data:
                    sessions[user]["created_at"].append(data["created_at"])
        except (BadSignature, SignatureExpired):
            continue

    return sessions


def info_online(
    sname: t.Sessionname,
) -> dict[str, Any]:
    info = u.INFO[sname]
    online = u.ONLINE[sname]

    return dict(info=info, online=online)


async def insert_fields(
    sname: t.Sessionname, unames: list[str], fields: dict, reload: bool = False
) -> None:
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            for k, v in fields.items():
                setattr(player, k, v)

            if reload:
                q.enqueue(
                    tuple(pid),
                    dict(
                        source="admin",
                        kind="action",
                        payload=dict(
                            action="reload",
                        ),
                    ),
                )


async def mark_dropout(sname: t.Sessionname, unames: list[str]) -> None:
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        u.MANUAL_DROPOUTS.add(pid)


async def put_to_end(sname: t.Sessionname, unames: list[str]) -> dict[str, dict]:
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if player.show_page < len(player.page_order):
                player.show_page = len(player.page_order)

                q.enqueue(
                    tuple(pid),
                    dict(
                        source="admin",
                        kind="action",
                        payload=dict(
                            action="reload",
                        ),
                    ),
                )

                u.set_info(
                    pid,
                    None,
                    player.page_order,
                    player.show_page,
                )

    return info_online(sname)


async def reload(sname: t.Sessionname, unames: list[str]) -> None:
    session_exists(sname, False)

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            dict(
                source="admin",
                kind="action",
                payload=dict(
                    action="reload",
                ),
            ),
        )


async def revert_by_one(sname: t.Sessionname, unames: list[str]) -> dict[str, dict]:
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if -1 < player.show_page <= len(player.page_order):
                player.show_page -= 1

                q.enqueue(
                    tuple(pid),
                    dict(
                        source="admin",
                        kind="action",
                        payload=dict(
                            action="reload",
                        ),
                    ),
                )

                u.set_info(
                    pid,
                    None,
                    player.page_order,
                    player.show_page,
                )

    return info_online(sname)


def session_exists(sname: t.Sessionname, raise_http: bool = True) -> None:
    with s.Admin() as admin:
        if sname not in admin.sessions:
            if raise_http:
                raise HTTPException(status_code=400, detail="Invalid session")
            else:
                raise ValueError("Invalid session")


def room_exists(roomname: str, raise_http: bool = True) -> None:
    with s.Admin() as admin:
        if roomname not in admin.rooms:
            if raise_http:
                raise HTTPException(status_code=400, detail="Invalid room")
            else:
                raise ValueError("Invalid room")


async def disassociate(roomname: str, sname: t.Sessionname) -> None:
    room_exists(roomname, False)
    session_exists(sname, False)

    with s.Admin() as admin:
        admin.rooms[roomname]["sname"] = None

    with s.Session(sname) as session:
        session.room = None


def rooms() -> SortedDict[str, dict]:
    with s.Admin() as admin:
        return SortedDict(admin.rooms)


def sessions() -> dict[str, dict[str, Any]]:
    with s.Admin() as admin:
        snames = admin.sessions

    def get_session_field_value(sname: str, field: str, default_data=None):
        """Get current value of a field for a session, or return default."""
        session_data = cache.get_namespace(("session", sname))
        if (
            session_data
            and isinstance(session_data, dict)
            and field in session_data
            and isinstance(session_data[field], list)
            and session_data[field]
            and not session_data[field][-1].unavailable
        ):
            return session_data[field][-1]
        return t.Value(0.0, False, default_data)

    return {
        sname: {
            "sname": sname,
            "active": get_session_field_value(sname, "active", False).data,
            "config": get_session_field_value(sname, "config", None).data,
            "room": get_session_field_value(sname, "room", None).data,
            "description": get_session_field_value(sname, "description", None).data,
            "n_players": len(get_session_field_value(sname, "players", []).data or []),
            "n_groups": len(get_session_field_value(sname, "groups", []).data or []),
            "started": get_session_field_value(sname, "config", None).time,
        }
        for sname in snames
    }


async def flip_active(sname: t.Sessionname) -> None:
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.active = not session.active


def verify_auth_token(user: str, token: str) -> Optional[str]:
    """Verify an authentication token.

    Args:
        user: Expected username
        token: Token to verify

    Returns:
        Username if token is valid, None otherwise
    """
    try:
        serializer = _get_serializer()
        active_tokens = _get_active_tokens()

        # Check if token is in active set
        if token not in active_tokens:
            return None

        # Verify token signature and expiration
        data = serializer.loads(token, max_age=86400)

        if not isinstance(data, dict) or data.get("user") != user:
            return None

        return user
    except (BadSignature, SignatureExpired, Exception):
        return None


async def viewdata(
    sname: t.Sessionname, since_epoch: float = 0
) -> tuple[SortedDict, float]:
    session_exists(sname, False)

    rval: SortedDict = SortedDict()
    latest: dict = s.fields_from_session(sname, since_epoch)
    last_update: float = since_epoch

    for (parts, field), v in latest.items():
        if len(parts) >= 3 and parts[0] == "player":
            uname = parts[2]

            if uname not in rval:
                rval[uname] = SortedDict()

            rval[uname][field] = dict(
                time=v.time,
                unavailable=v.unavailable,
                type_representation=str(type(v.data)),
                value_representation=repr(v.data),
                context=v.context,
            )

            if v.time > last_update:
                last_update = v.time

    return rval, last_update
