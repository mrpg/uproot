# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Authentication and authorization service."""

import hmac
import ipaddress
from datetime import UTC, datetime
from time import monotonic
from types import EllipsisType
from typing import Any, cast

from fastapi import Header, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import uproot as u
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t

# Module-level state for admin credentials
ADMINS: dict[str, str | EllipsisType] = {}
ADMINS_HASH: str | None = None
ADMINS_SECRET_KEY: str | None = None

# IP-based login rate limiting (in-memory)
MAX_FAILED_ATTEMPTS = 50
ATTEMPT_WINDOW = 3600.0
BAN_DURATION = 6 * 3600.0
MAX_TRACKED_IPS = 10_000
CLEANUP_INTERVAL = 600.0

FAILED_ATTEMPTS: dict[str, list[float]] = {}
BANNED_IPS: dict[str, float] = {}
LAST_CLEANUP: float = 0.0


def is_localhost(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_loopback


def get_client_ip(request: Request) -> str:
    if request.client is None:
        return ""

    ip = request.client.host

    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        return ip


def sweep_stale_entries() -> None:
    global LAST_CLEANUP

    now = monotonic()

    if now - LAST_CLEANUP < CLEANUP_INTERVAL:
        return

    LAST_CLEANUP = now

    cutoff = now - ATTEMPT_WINDOW
    stale = [ip for ip, ts in FAILED_ATTEMPTS.items() if ts[-1] <= cutoff]

    for ip in stale:
        del FAILED_ATTEMPTS[ip]

    expired = [ip for ip, expiry in BANNED_IPS.items() if now >= expiry]

    for ip in expired:
        del BANNED_IPS[ip]


def is_ip_banned(ip: str) -> bool:
    if not ip or is_localhost(ip):
        return False

    expiry = BANNED_IPS.get(ip)

    if expiry is None:
        return False

    if monotonic() >= expiry:
        BANNED_IPS.pop(ip, None)
        FAILED_ATTEMPTS.pop(ip, None)
        return False

    return True


def record_failed_login(ip: str) -> None:
    """Reserve a login attempt; successful authentication removes it."""
    if not ip or is_localhost(ip):
        return

    sweep_stale_entries()

    if is_ip_banned(ip):
        return

    now = monotonic()
    cutoff = now - ATTEMPT_WINDOW
    attempts = FAILED_ATTEMPTS.get(ip)

    if attempts is not None:
        attempts = [ts for ts in attempts if ts > cutoff]
    else:
        tracked_ips = len(FAILED_ATTEMPTS) + len(BANNED_IPS)
        if tracked_ips >= MAX_TRACKED_IPS:
            return
        attempts = []

    attempts.append(now)
    FAILED_ATTEMPTS[ip] = attempts

    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        BANNED_IPS[ip] = now + BAN_DURATION
        del FAILED_ATTEMPTS[ip]


def clear_failed_logins(ip: str) -> None:
    FAILED_ATTEMPTS.pop(ip, None)
    BANNED_IPS.pop(ip, None)


def ensure_globals() -> None:
    """Initialize global admin credentials from deployment config."""
    global ADMINS, ADMINS_HASH, ADMINS_SECRET_KEY

    if ADMINS_HASH is None:
        ADMINS_HASH = t.sha256(
            "\n".join(f"{user}\t{pw}" for user, pw in d.ADMINS.items())
        )
        ADMINS_SECRET_KEY = t.sha256(f"{u.KEY}:{ADMINS_HASH}")

        # Prevent direct modification of d.ADMINS
        ADMINS = d.ADMINS
        del d.ADMINS


def get_secret_key() -> str:
    """Get the secret key for token signing."""
    ensure_globals()
    return cast(str, ADMINS_SECRET_KEY)


def get_serializer() -> URLSafeTimedSerializer:
    """Get configured token serializer."""
    return URLSafeTimedSerializer(get_secret_key())


def get_active_tokens() -> set[str]:
    """Get set of currently active tokens from storage."""
    with s.Admin() as admin:
        return getattr(admin, "active_auth_tokens", set())


def store_active_tokens(tokens: set[str], cleanup: bool = True) -> None:
    """Store set of active tokens to storage."""
    with s.Admin() as admin:
        admin.active_auth_tokens = tokens

    # Optionally clean up expired tokens when storing active ones
    if cleanup:
        cleanup_expired_tokens()


def cleanup_expired_tokens() -> None:
    """Remove expired tokens from storage."""
    serializer = get_serializer()
    active_tokens = get_active_tokens()
    valid_tokens = set()

    for token in active_tokens:
        try:
            serializer.loads(token, max_age=86400)  # 24 hours
            valid_tokens.add(token)
        except (BadSignature, SignatureExpired):
            continue  # Token is expired or invalid, don't keep it

    if len(valid_tokens) != len(active_tokens):
        # Store without triggering cleanup again to avoid recursion
        store_active_tokens(valid_tokens, cleanup=False)


def create_token_internal(user: str) -> str:
    """Internal helper to create and store an authentication token.

    Args:
        user: Username (must be valid)

    Returns:
        Signed token string
    """
    # Create token data
    token_data = {
        "user": user,
        "created_at": datetime.now(UTC).isoformat(),
        "nonce": t.rng().randbytes(16).hex(),  # Prevent token reuse across sessions
    }

    # Sign the token
    serializer = get_serializer()
    token = serializer.dumps(token_data)

    # Store token in active set
    active_tokens = get_active_tokens()
    active_tokens.add(token)
    store_active_tokens(active_tokens)

    return token


def admin_credentials_valid(user: str, pw: str) -> bool:
    if user not in ADMINS or ADMINS[user] is ...:
        d.LOGGER.debug(f"Invalid login attempt for user: {user[:32]!r}")
        return False

    stored_pw = cast(str, ADMINS[user])
    if not hmac.compare_digest(pw.encode(), stored_pw.encode()):
        d.LOGGER.debug(f"Invalid login attempt for user: {user[:32]!r}")
        return False

    return True


def create_auth_token(user: str, pw: str) -> str | None:
    """Create a new authentication token for a user.

    Args:
        user: Username
        pw: Password

    Returns:
        Signed token string if credentials are valid, None otherwise
    """
    ensure_globals()

    # Verify credentials first
    if not admin_credentials_valid(user, pw):
        return None

    return create_token_internal(user)


async def create_auth_token_async(user: str, pw: str) -> str | None:
    ensure_globals()

    if not admin_credentials_valid(user, pw):
        return None

    return create_token_internal(user)


def create_auth_token_for_user(user: str) -> str | None:
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

    return create_token_internal(user)


def revoke_auth_token(token: str) -> bool:
    """Revoke a specific authentication token.

    Args:
        token: Token to revoke

    Returns:
        True if token was revoked, False if it wasn't active
    """
    active_tokens = get_active_tokens()
    if token in active_tokens:
        active_tokens.remove(token)
        store_active_tokens(active_tokens)
        return True
    return False


def revoke_all_user_tokens(user: str) -> int:
    """Revoke all authentication tokens for a specific user.

    Args:
        user: Username whose tokens should be revoked

    Returns:
        Number of tokens revoked
    """
    serializer = get_serializer()
    active_tokens = get_active_tokens()
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

    store_active_tokens(tokens_to_keep)
    return revoked_count


def get_active_auth_sessions() -> dict[str, dict[str, Any]]:
    """Get information about all active authentication sessions.

    Returns:
        Dict mapping usernames to session info
    """
    serializer = get_serializer()
    active_tokens = get_active_tokens()
    sessions = {}

    for token in active_tokens:
        try:
            data = serializer.loads(token, max_age=86400)
            if isinstance(data, dict) and "user" in data:
                user = data["user"]
                if user not in sessions:
                    sessions[user] = {  # nosec
                        "token_count": 0,
                        "created_at": [],
                    }
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


def from_cookie(uauth: str | None) -> dict[str, str]:
    """Parse authentication token from cookie.

    Returns dict with 'user' and 'token' keys, or empty strings if invalid.
    """
    if not uauth:
        return {
            "user": "",
            "token": "",  # nosec
        }
    try:
        serializer = get_serializer()
        active_tokens = get_active_tokens()

        # Verify token is in active set and not expired
        if uauth not in active_tokens:
            return {
                "user": "",
                "token": "",  # nosec
            }

        # Verify token signature and expiration (24 hours)
        data = serializer.loads(uauth, max_age=86400)

        if not isinstance(data, dict) or "user" not in data:
            return {
                "user": "",
                "token": "",  # nosec
            }

        return {"user": data["user"], "token": uauth}
    except (BadSignature, SignatureExpired):
        return {
            "user": "",
            "token": "",  # nosec
        }


def verify_auth_token(user: str, token: str) -> str | None:
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
        serializer = get_serializer()
        active_tokens = get_active_tokens()

        # Check if token is in active set
        if token not in active_tokens:
            return None

        # Verify token signature and expiration
        data = serializer.loads(token, max_age=86400)

        if not isinstance(data, dict) or data.get("user") != user:
            return None

        return user
    except (BadSignature, SignatureExpired):
        return None


def verify_bearer_token(authorization: str | None) -> bool:
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

    return any(hmac.compare_digest(token, key) for key in d.API_KEYS)


def require_bearer_token(authorization: str | None = Header(None)) -> None:
    """FastAPI dependency that validates Bearer token from Authorization header.

    Raises:
        HTTPException: 401 if authentication fails
    """
    if not verify_bearer_token(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
