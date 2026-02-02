# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Player operations service."""

from typing import Any

import uproot as u
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
    """Get specified fields from all players in a session."""
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
    """Insert fields into player objects."""
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


async def put_to_end(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
    """Put players to the end of their page order."""
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


async def revert_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[str, Any]]:
    """Revert players by one page."""
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


async def reload(sname: t.Sessionname, unames: list[str]) -> None:
    """Force reload for specified players."""
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


async def redirect(sname: t.Sessionname, unames: list[str], url: str) -> None:
    """Redirect specified players to a URL."""
    session_exists(sname, False)

    if not url.startswith("http://") and not url.startswith("https://"):
        raise ValueError("URL must start with http:// or https://")

    for uname in unames:
        ptuple = sname, uname

        q.enqueue(
            ptuple,
            dict(
                source="admin",
                kind="action",
                payload=dict(
                    action="redirect",
                    url=url,
                ),
            ),
        )


async def adminmessage(sname: t.Sessionname, unames: list[str], msg: str) -> None:
    """Send an admin message to specified players."""
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
