# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Player operations service."""

from typing import Any

import uproot as u
import uproot.chat as chat
import uproot.queues as q
import uproot.storage as s
import uproot.types as t
from uproot.services.session_service import session_exists


async def info_online(sname: t.Sessionname) -> dict[t.Username, Any]:
    """Get online status and info for all players in a session."""
    online = u.ONLINE[sname]
    rawinfo: dict[t.Username, dict[str, Any]] = (
        await fields_from_all(sname, ["id", "page_order", "show_page"])
        if not sname.startswith("^")
        else {}
    )

    return {
        "info": {
            k: (v["id"], v["page_order"], v["show_page"]) for k, v in rawinfo.items()
        },
        "online": online,
    }


async def fields_from_all(
    sname: t.Sessionname,
    fields: list[str],
) -> dict[t.Username, dict[str, Any]]:
    """Get specified fields from all players in a session."""
    retval: dict[t.Username, dict[str, Any]] = {}

    with s.Session(sname) as session:
        if not session:
            return retval

        for pid in session._uproot_players:
            with t.materialize(pid) as player:
                retval[pid.uname] = {}

                for field in fields:
                    retval[pid.uname][field] = player.get(field)

    return retval


async def insert_fields(
    sname: t.Sessionname,
    unames: list[str],
    fields: dict[str, Any],
    reload: bool = False,
) -> None:
    """Insert fields into player objects."""
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with t.materialize(pid) as player:
            for k, v in fields.items():
                setattr(player, k, v)

            if reload:
                q.enqueue(
                    tuple(pid),
                    {
                        "source": "admin",
                        "kind": "action",
                        "payload": {
                            "action": "reload",
                        },
                    },
                )


async def run_new_player(sname: t.Sessionname, unames: list[str]) -> None:
    """Manually run new_player callbacks for players that haven't been initialized."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        if not session.get("_uproot_initialized", False):
            for appname in session.apps:
                app = u.APPS[appname]

                if hasattr(app, "new_session"):
                    app.new_session(session)

            session._uproot_initialized = True

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with t.materialize(pid) as player:
            if player.get("_uproot_initialized", False):
                continue

            for appname in u.CONFIGS[player.config]:
                app = u.APPS[appname]

                if hasattr(app, "new_player"):
                    app.new_player(player=player)

            player._uproot_initialized = True


async def mark_dropout(sname: t.Sessionname, unames: list[str]) -> None:
    """Mark players as dropouts."""
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)
        u.MANUAL_DROPOUTS.add(pid)


async def advance_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[t.Username, Any]]:
    """Advance players by one page."""
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with t.materialize(pid) as player:
            if -1 < player.show_page < len(player.page_order):
                player.show_page += 1

                q.enqueue(
                    tuple(pid),
                    {
                        "source": "admin",
                        "kind": "action",
                        "payload": {
                            "action": "reload",
                        },
                    },
                )

    return await info_online(sname)


async def put_to_end(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
    """Put players to the end of their page order."""
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with t.materialize(pid) as player:
            if player.show_page < len(player.page_order):
                player.show_page = len(player.page_order)

                q.enqueue(
                    tuple(pid),
                    {
                        "source": "admin",
                        "kind": "action",
                        "payload": {
                            "action": "reload",
                        },
                    },
                )

    return await info_online(sname)


async def revert_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
    """Revert players by one page."""
    session_exists(sname, False)

    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with t.materialize(pid) as player:
            if -1 < player.show_page <= len(player.page_order):
                player.show_page -= 1

                q.enqueue(
                    tuple(pid),
                    {
                        "source": "admin",
                        "kind": "action",
                        "payload": {
                            "action": "reload",
                        },
                    },
                )

    return await info_online(sname)


async def reload(sname: t.Sessionname, unames: list[str]) -> None:
    """Force reload for specified players."""
    session_exists(sname, False)

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            {
                "source": "admin",
                "kind": "action",
                "payload": {
                    "action": "reload",
                },
            },
        )


async def redirect(sname: t.Sessionname, unames: list[str], url: str) -> None:
    """Redirect specified players to a URL."""
    session_exists(sname, False)

    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValueError("URL must start with http:// or https://")

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            {
                "source": "admin",
                "kind": "action",
                "payload": {
                    "action": "redirect",
                    "url": url,
                },
            },
        )


async def adminmessage(sname: t.Sessionname, unames: list[str], msg: str) -> None:
    """Send an admin message to specified players."""
    session_exists(sname, False)

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            {
                "source": "adminmessage",
                "data": msg,
                "event": "_uproot_AdminMessaged",
            },
        )


def _adminchat_summary(pid: t.PlayerIdentifier) -> dict[str, Any]:
    mid = chat.adminchat_for_player(pid)

    if mid is None or not chat.exists(mid):
        return {
            "chat_id": None,
            "enabled": False,
            "has_messages": False,
            "message_count": 0,
            "last_message_at": None,
            "last_sender": None,
            "last_message_text": None,
        }

    entries = chat.messages(mid)
    last_message = entries[-1][2] if entries else None

    return {
        "chat_id": mid.mname,
        "enabled": chat.adminchat_reply_state(pid),
        "has_messages": bool(entries),
        "message_count": len(entries),
        "last_message_at": entries[-1][1] if entries else None,
        "last_sender": (
            "admin"
            if last_message is not None and last_message.sender is None
            else "player" if last_message is not None else None
        ),
        "last_message_text": (
            last_message.text[:80] if last_message is not None else None
        ),
    }


async def adminchat_overview(sname: t.Sessionname) -> dict[str, dict[str, Any]]:
    """Summarize admin chat state for each player in a session."""
    session_exists(sname, False)

    with s.Session(sname) as session:
        return {pid.uname: _adminchat_summary(pid) for pid in session._uproot_players}


async def adminchat_thread(
    sname: t.Sessionname,
    uname: str,
) -> dict[str, Any]:
    """Get admin chat metadata and transcript for a single player."""
    session_exists(sname, False)

    pid = t.PlayerIdentifier(sname, uname)
    mid = chat.adminchat_for_player(pid)
    messages = []

    if mid is not None and chat.exists(mid):
        messages = [
            chat.show_adminchat_msg(mid, msg_id, msg_time, msg, None)
            for msg_id, msg_time, msg in chat.messages(mid)
        ]

    with t.materialize(pid) as player:
        payload = {
            "player": {
                "uname": uname,
                "id": player.get("id"),
                "label": player.get("label", ""),
                "show_page": player.get("show_page", -1),
                "page_order": player.get("page_order", []),
            },
            "chat": _adminchat_summary(pid),
            "messages": messages,
        }

    return payload


async def send_adminchat(
    sname: t.Sessionname,
    uname: str,
    message: str,
    enable_replies: bool | None = None,
) -> dict[str, Any]:
    """Send an admin chat message to one player."""
    session_exists(sname, False)

    pid = t.PlayerIdentifier(sname, uname)
    mid = chat.ensure_adminchat(pid)
    msgtext = message.strip()

    if msgtext == "":
        raise ValueError("Admin chat message cannot be empty")

    if enable_replies is not None:
        chat.set_adminchat_replies(pid, enable_replies)

    with t.materialize(pid) as player:
        player._uproot_adminchat = mid
        msg_id = chat.add_message(mid, None, msgtext)
        await chat.notify_adminchat(mid, msg_id, None, player, msgtext)

    return await adminchat_thread(sname, uname)


async def set_adminchat_replies(
    sname: t.Sessionname,
    uname: str,
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable replies for one player's admin chat."""
    session_exists(sname, False)

    pid = t.PlayerIdentifier(sname, uname)
    mid = chat.adminchat_for_player(pid)

    if (mid is None or not chat.exists(mid)) and not enabled:
        payload = await adminchat_thread(sname, uname)
        payload["kind"] = "state"
        return payload

    event = chat.set_adminchat_replies(pid, enabled)
    payload = await adminchat_thread(sname, uname)
    payload["kind"] = event["kind"]
    return payload


async def send_adminchat_to_players(
    sname: t.Sessionname,
    unames: list[str],
    message: str,
    enable_replies: bool | None = None,
) -> dict[str, Any]:
    """Send the same admin chat message to multiple players at once."""
    session_exists(sname, False)

    results = []

    for uname in unames:
        results.append(await send_adminchat(sname, uname, message, enable_replies))

    return {
        "sent_count": len(results),
        "players": results,
    }


async def set_adminchat_replies_for_players(
    sname: t.Sessionname,
    unames: list[str],
    enabled: bool,
) -> dict[str, Any]:
    """Enable or disable replies for multiple players at once."""
    session_exists(sname, False)

    updated = []

    for uname in unames:
        updated.append(await set_adminchat_replies(sname, uname, enabled))

    return {
        "enabled": enabled,
        "players": updated,
    }


async def group_players(
    sname: t.Sessionname,
    unames: list[str],
    action: str,
    group_size: int = 1,
    shuffle: bool = False,
    reload: bool = False,
) -> dict[str, Any]:
    """
    Manage player group assignments.

    Actions:
        - "same_group": Put all selected players in the same group
        - "reset": Remove group assignments from selected players
        - "by_size": Create groups of specified size

    Args:
        sname: Session name
        unames: List of player usernames
        action: One of "same_group", "reset", "by_size"
        group_size: Size of groups when action is "by_size"
        shuffle: Whether to shuffle players before grouping (for "by_size")
        reload: Whether to reload player pages after grouping

    Returns:
        Result dict with info about created/modified groups
    """
    import random

    import uproot.core as c

    session_exists(sname, False)

    sid = t.SessionIdentifier(sname)
    pids = [t.PlayerIdentifier(sname, uname) for uname in unames]

    # Shuffle players if requested
    if shuffle:
        random.shuffle(pids)

    result: dict[str, Any] = {"action": action, "players": unames}

    with t.materialize(sid) as session:
        if action == "same_group":
            # Put all selected players in the same group
            gid = c.create_group(session, pids, overwrite=True)
            result["groups_created"] = 1
            result["group_name"] = gid.gname

        elif action == "reset":
            # Remove group assignments from selected players
            reset_count = 0
            for pid in pids:
                with t.materialize(pid) as player:
                    if player._uproot_group is not None:
                        player._uproot_group = None
                        player.member_id = None
                        reset_count += 1
            result["players_reset"] = reset_count

        elif action == "by_size":
            # Create groups of specified size
            if group_size < 1:
                raise ValueError("Group size must be at least 1")
            if len(pids) % group_size != 0:
                raise ValueError(
                    f"Number of selected players ({len(pids)}) "
                    f"must be divisible by group size ({group_size})"
                )

            groups_created = []
            for i in range(0, len(pids), group_size):
                group_pids = pids[i : i + group_size]
                gid = c.create_group(session, group_pids, overwrite=True)
                groups_created.append(gid.gname)

            result["groups_created"] = len(groups_created)
            result["group_names"] = groups_created

        else:
            raise ValueError(f"Unknown action: {action}")

    # Optionally reload player pages
    if reload:
        for uname in unames:
            ptuple = sname, uname
            q.enqueue(
                ptuple,
                {
                    "source": "admin",
                    "kind": "action",
                    "payload": {
                        "action": "reload",
                    },
                },
            )

    return result
