# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import secrets
from datetime import datetime
from types import EllipsisType
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Callable,
    Iterator,
    Optional,
    TypeAlias,
    cast,
)

import aiohttp
from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sortedcontainers import SortedDict

import uproot as u
import uproot.cache as cache
import uproot.data as data
import uproot.deployment as d
import uproot.queues as q
import uproot.storage as s
import uproot.types as t

ADMINS: dict[str, str | EllipsisType] = dict()
ADMINS_HASH: Optional[str] = None
ADMINS_SECRET_KEY: Optional[str] = None
DisplayValue: TypeAlias = tuple[
    Annotated[float | None, "time"],
    Annotated[bool, "unavailable"],
    Annotated[str | None, "typename"],
    Annotated[str, "displaystr"],
    Annotated[str, "context"],
]


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


def ensure_globals() -> None:
    global ADMINS, ADMINS_HASH, ADMINS_SECRET_KEY

    if ADMINS_HASH is None:
        ADMINS_HASH = t.sha256(
            "\n".join(f"{user}\t{pw}" for user, pw in d.ADMINS.items())
        )
        ADMINS_SECRET_KEY = t.sha256(f"{u.KEY}:{ADMINS_HASH}")

        # Prevent direct modification of d.ADMINS
        ADMINS = d.ADMINS
        del d.ADMINS


def _get_secret_key() -> str:
    ensure_globals()
    return cast(str, ADMINS_SECRET_KEY)


def _get_serializer() -> URLSafeTimedSerializer:
    """Get configured token serializer."""
    return URLSafeTimedSerializer(_get_secret_key())


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

    return await info_online(sname)


async def announcements() -> dict[str, Any]:
    ANNOUNCEMENTS_URL = "https://raw.githubusercontent.com/mrpg/uproot/refs/heads/main/announcements.json"

    async with aiohttp.ClientSession() as session:
        async with session.get(ANNOUNCEMENTS_URL) as response:
            return cast(dict[str, Any], await response.json(content_type="text/plain"))


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
            return dict(
                user="", token=""
            )  # nosec B106 - Empty strings for auth failure, not actual credentials

        # Verify token signature and expiration (24 hours)
        data = serializer.loads(uauth, max_age=86400)

        if not isinstance(data, dict) or "user" not in data:
            return dict(
                user="", token=""
            )  # nosec B106 - Empty strings for auth failure, not actual credentials

        return dict(user=data["user"], token=uauth)
    except (BadSignature, SignatureExpired, Exception):
        return dict(
            user="", token=""
        )  # nosec B106 - Empty strings for auth failure, not actual credentials


def everything_from_session(
    sname: t.Sessionname,
) -> dict[tuple[str, ...], list[t.Value]]:
    # Go ahead… https://www.youtube.com/watch?v=2WhHW8zD620

    matches: dict[tuple[str, ...], Any] = dict()
    sname = str(sname)

    for lvl1_k, lvl1_v in cache.MEMORY_HISTORY.items():
        if isinstance(lvl1_v, dict) and sname in lvl1_v:
            k = (
                lvl1_k,
                sname,
            )
            namespace = cache.get_namespace(k)
            if namespace is not None:
                matches |= cache.flatten(namespace, k)

    return matches


def data_display(x: Any) -> str:
    # This is similar to data.value2json and data.json2csv, but a bit simpler
    # The intention is to provide a user-friendly string representation of 'x'

    if isinstance(x, (bytearray, bytes)):
        # Nobody wants to view that in the browser (not in that form at least)
        return "[Binary]"
    else:
        try:
            return str(x)
        except Exception:
            return repr(x)


async def everything_from_session_display(
    sname: t.Sessionname,
    since_epoch: float = 0.0,
) -> tuple[dict[str, dict[str, list[DisplayValue]]], float]:
    # This function returns something that orjson can handle

    sname = str(sname)
    search_val = t.Value(since_epoch, True, None, "")
    retval: dict[str, dict[str, list[DisplayValue]]] = dict()
    last_update: float = since_epoch

    for uname, fields in cache.MEMORY_HISTORY.get("player", {}).get(sname, {}).items():
        retval[uname] = dict()

        for field, values in fields.items():
            from_ix = values.bisect_right(search_val)
            retval[uname][field] = displayvalues = [
                cast(
                    DisplayValue,
                    (
                        val.time,
                        val.unavailable,
                        type(val.data).__name__,
                        data_display(val.data),
                        val.context,
                    ),
                )
                for val in values[from_ix:]
            ]

            if displayvalues:
                if (
                    isinstance(displayvalues[-1][0], float)
                    and displayvalues[-1][0] > last_update
                ):
                    last_update = displayvalues[-1][0]
            else:
                del retval[uname][field]

        if not retval[uname]:
            del retval[uname]

        await asyncio.sleep(0)

    return retval, last_update


def generate_data(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
) -> tuple[
    Iterator[dict[str, Any]],
    Callable[[Iterator[dict[str, Any]]], Iterator[dict[str, Any]]],
    dict[str, list[str]],
]:
    gvar = [gv for gv in gvar if gv]

    match format:
        case "ultralong":
            transkwargs_ul: dict[str, Any] = {}
            transformer, transkwargs = data.noop, transkwargs_ul
        case "sparse":
            transkwargs_sp: dict[str, Any] = {}
            transformer, transkwargs = data.long_to_wide, transkwargs_sp
        case "latest":
            transformer, transkwargs = data.latest, {"group_by_fields": gvar}
        case _:
            raise NotImplementedError

    alldata = data.partial_matrix(everything_from_session(sname))

    if filters:
        alldata = data.reasonable_filters(alldata)

    return alldata, transformer, transkwargs


def generate_csv(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
) -> str:
    alldata, transformer, transkwargs = generate_data(sname, format, gvar, filters)

    return data.csv_out(transformer(alldata, **transkwargs))


async def generate_json(
    sname: t.Sessionname,
    format: str,
    gvar: list[str],
    filters: bool,
) -> AsyncGenerator[str, None]:
    alldata, transformer, transkwargs = generate_data(sname, format, gvar, filters)

    async for chunk in data.json_out(transformer(alldata, **transkwargs)):
        yield chunk
        await asyncio.sleep(0)


def _create_token_for_user(user: str) -> str:
    """Internal helper to create and store an authentication token.

    Args:
        user: Username (must be valid)

    Returns:
        Signed token string
    """
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


def create_auth_token(user: str, pw: str) -> Optional[str]:
    """Create a new authentication token for a user.

    Args:
        user: Username
        pw: Password

    Returns:
        Signed token string if credentials are valid, None otherwise
    """
    ensure_globals()

    # Verify credentials first
    if user not in ADMINS or ADMINS[user] is ... or ADMINS[user] != pw:
        d.LOGGER.debug(f"Invalid credentials: {user} {pw}")
        d.LOGGER.debug(f"Valid credentials would have been: {ADMINS}")
        return None

    return _create_token_for_user(user)


def create_auth_token_for_user(user: str) -> Optional[str]:
    """Create an authentication token for a user without password verification.

    This function should only be called after the user has been authenticated
    through another mechanism (e.g., LOGIN_TOKEN). It bypasses password checking
    and works even when the user's password is set to ellipsis (...).

    Args:
        user: Username

    Returns:
        Signed token string if user exists, None otherwise
    """
    ensure_globals()

    # Only verify user exists
    if user not in ADMINS:
        d.LOGGER.debug(f"User does not exist: {user}")
        return None

    return _create_token_for_user(user)


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


def get_active_auth_sessions() -> dict[str, dict[str, Any]]:
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
                token_count = sessions[user]["token_count"]
                if isinstance(token_count, int):
                    sessions[user]["token_count"] = token_count + 1
                if "created_at" in data:
                    created_at_list = sessions[user]["created_at"]
                    if isinstance(created_at_list, list):
                        created_at_list.append(data["created_at"])
        except (BadSignature, SignatureExpired):
            continue

    return sessions


def get_digest(sname: t.Sessionname) -> list[str]:
    with s.Session(sname) as session:
        apps = session.apps

    return [appname for appname in apps if hasattr(u.APPS[appname], "digest")]


async def info_online(
    sname: t.Sessionname,
) -> dict[t.Username, Any]:
    online = u.ONLINE[sname]
    rawinfo: dict[t.Username, dict[str, Any]] = (
        await fields_from_all(sname, ["id", "page_order", "show_page"])
        if not sname.startswith("^")
        else {}
    )

    return dict(
        info={
            k: (v["id"], v["page_order"], v["show_page"]) for k, v in rawinfo.items()
        },
        online=online,
    )


async def fields_from_all(
    sname: t.Sessionname,
    fields: list[str],
) -> dict[t.Username, dict[str, Any]]:
    retval: dict[t.Username, dict[str, Any]] = dict()

    with s.Session(sname) as session:
        if not session:
            return retval

        for pid in session.players:
            with pid() as player:
                retval[pid.uname] = dict()

                for field in fields:
                    retval[pid.uname][field] = player.get(field)

    return retval


async def insert_fields(
    sname: t.Sessionname,
    unames: list[str],
    fields: dict[str, Any],
    reload: bool = False,
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


async def put_to_end(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
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

    return await info_online(sname)


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


async def revert_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
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

    return await info_online(sname)


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
    stats = dict()

    with s.Admin() as admin:
        snames = admin.sessions

    for sname in snames:
        with s.Session(sname) as session:
            stats[sname] = dict(
                sname=session.name,  # Exactly equal to sname
                active=session.active,
                config=session.config,
                room=session.room,
                description=session.description,
                n_players=len(session.players),
                n_groups=len(session.groups),
            )  # TODO: created

    return stats


async def flip_active(sname: t.Sessionname) -> None:
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.active = not session.active


async def flip_testing(sname: t.Sessionname) -> None:
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.testing = not session.testing


async def update_description(sname: t.Sessionname, newdesc: str) -> None:
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.description = newdesc if newdesc else None


async def update_settings(sname: t.Sessionname, **newsettings: Any) -> None:
    session_exists(sname, False)

    with s.Session(sname) as session:
        session.settings = newsettings


def verify_auth_token(user: str, token: str) -> Optional[str]:
    """Verify an authentication token.

    Args:
        user: Expected username
        token: Token to verify

    Returns:
        Username if token is valid, None otherwise
    """
    if not user or not token:
        return None

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


def verify_bearer_token(authorization: Optional[str]) -> bool:
    """Verify a Bearer token from the Authorization header.

    Args:
        authorization: The Authorization header value (e.g., "Bearer <token>")

    Returns:
        True if the token is valid, False otherwise
    """
    if not authorization:
        return False

    # Check if it starts with "Bearer "
    if not authorization.startswith("Bearer "):
        return False

    # Extract the token
    token = authorization[7:]  # Remove "Bearer " prefix

    # Check if the token is in the API_KEYS set
    return token in d.API_KEYS


def require_bearer_token(authorization: Optional[str] = Header(None)) -> None:
    """FastAPI dependency that validates Bearer token from Authorization header.

    Raises:
        HTTPException: 401 if authentication fails
    """
    if not verify_bearer_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
