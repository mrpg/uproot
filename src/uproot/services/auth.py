# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Authentication and authorization service."""

import secrets
from datetime import datetime, timezone
from types import EllipsisType
from typing import Any, Optional, cast

from fastapi import Header, HTTPException
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

import uproot as u
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t

# Module-level state for admin credentials
ADMINS: dict[str, str | EllipsisType] = {}
ADMINS_HASH: Optional[str] = None
ADMINS_SECRET_KEY: Optional[str] = None


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
        "created_at": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16),  # Prevent token reuse across sessions
    }

    # Sign the token
    serializer = get_serializer()
    token = serializer.dumps(token_data)

    # Store token in active set
    active_tokens = get_active_tokens()
    active_tokens.add(token)
    store_active_tokens(active_tokens)

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
        # Sanitize user input to prevent log injection
        d.LOGGER.debug(f"Invalid login attempt for user: {user[:32]!r}")
        return None

    return create_token_internal(user)


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
                    sessions[user] = {  # nosec B105 - counter, not a credential
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
            "token": "",  # nosec B105
        }
    try:
        serializer = get_serializer()
        active_tokens = get_active_tokens()

        # Verify token is in active set and not expired
        if uauth not in active_tokens:
            return {
                "user": "",
                "token": "",  # nosec B105
            }

        # Verify token signature and expiration (24 hours)
        data = serializer.loads(uauth, max_age=86400)

        if not isinstance(data, dict) or "user" not in data:
            return {
                "user": "",
                "token": "",  # nosec B105
            }

        return {"user": data["user"], "token": uauth}
    except (BadSignature, SignatureExpired):
        return {
            "user": "",
            "token": "",  # nosec B105
        }


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
