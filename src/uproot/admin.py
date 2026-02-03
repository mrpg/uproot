# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Admin module - re-exports from focused service modules."""

# Re-export from auth service
from uproot.services.auth import (
    ADMINS,
    ADMINS_HASH,
    ADMINS_SECRET_KEY,
    cleanup_expired_tokens,
    create_auth_token,
    create_auth_token_for_user,
    create_token_internal,
    ensure_globals,
    from_cookie,
    get_active_auth_sessions,
    get_active_tokens,
    get_secret_key,
    get_serializer,
    require_bearer_token,
    revoke_all_user_tokens,
    revoke_auth_token,
    store_active_tokens,
    verify_auth_token,
    verify_bearer_token,
)

# Re-export from config service
from uproot.services.config_service import (
    announcements,
    config_summary,
    configs,
    displaystr,
    praise,
)

# Re-export from data service
from uproot.services.data_service import (
    DisplayValue,
    data_display,
    everything_from_session,
    everything_from_session_display,
    generate_csv,
    generate_data,
    generate_json,
    page_times,
)

# Re-export from player service
from uproot.services.player_service import (
    adminmessage,
    advance_by_one,
    fields_from_all,
    info_online,
    insert_fields,
    mark_dropout,
    put_to_end,
    redirect,
    reload,
    revert_by_one,
)

# Re-export from room service
from uproot.services.room_service import (
    delete_room,
    disassociate,
    room_exists,
    rooms,
)

# Re-export from session service
from uproot.services.session_service import (
    flip_active,
    flip_testing,
    get_digest,
    session_exists,
    sessions,
    update_description,
    update_settings,
)

__all__ = [
    # Auth
    "ADMINS",
    "ADMINS_HASH",
    "ADMINS_SECRET_KEY",
    "cleanup_expired_tokens",
    "create_auth_token",
    "create_auth_token_for_user",
    "create_token_internal",
    "ensure_globals",
    "from_cookie",
    "get_active_auth_sessions",
    "get_active_tokens",
    "get_secret_key",
    "get_serializer",
    "require_bearer_token",
    "revoke_all_user_tokens",
    "revoke_auth_token",
    "store_active_tokens",
    "verify_auth_token",
    "verify_bearer_token",
    # Session
    "flip_active",
    "flip_testing",
    "get_digest",
    "session_exists",
    "sessions",
    "update_description",
    "update_settings",
    # Player
    "adminmessage",
    "advance_by_one",
    "fields_from_all",
    "info_online",
    "insert_fields",
    "mark_dropout",
    "put_to_end",
    "redirect",
    "reload",
    "revert_by_one",
    # Room
    "delete_room",
    "disassociate",
    "room_exists",
    "rooms",
    # Data
    "DisplayValue",
    "data_display",
    "everything_from_session",
    "everything_from_session_display",
    "generate_csv",
    "generate_data",
    "generate_json",
    "page_times",
    # Config
    "announcements",
    "config_summary",
    "configs",
    "displaystr",
    "praise",
]
