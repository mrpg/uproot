# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from itertools import chain
from typing import Any, AsyncGenerator, Callable, Iterator, Optional

import aiohttp
from sortedcontainers import SortedDict

import uproot as u
import uproot.data as data
import uproot.deployment as d
import uproot.queues as q
import uproot.storage as s
import uproot.types as t

EXPORT_NAMESPACES = ("player/*/", "group/*/", "model/*/", "session/*")


async def adminmessage(sname: t.Sessionname, unames: list[str], msg: str) -> None:
    for uname in unames:
        ptuple = sname, uname

        await q.enqueue(
            ptuple,
            dict(
                source="adminmessage",
                data=msg,
                event="_uproot_AdminMessaged",
            ),
        )


def admins() -> str:
    return t.sha256("\n".join(f"{user}\t{pw}" for user, pw in d.ADMINS.items()))


async def advance_by_one(
    sname: t.Sessionname, unames: list[str]
) -> dict[str, dict[t.Username, Optional[float]]]:
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if -1 < player.show_page < len(player.page_order):
                player.show_page += 1

                await q.enqueue(
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
    ANNOUNCEMENTS_URL = (
        "https://raw.githubusercontent.com/mrpg/uproot/refs/heads/main/announcements.json"
    )

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
    try:
        user, secret = uauth.split(":")

        return dict(user=user, secret=secret)
    except Exception:
        return dict(user="", secret="")


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

    namespaces = (ns.replace("*", sname) for ns in EXPORT_NAMESPACES)
    alldata = data.partial_matrix(
        chain.from_iterable(s.history_raw(ns) for ns in namespaces)
    )

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

    namespaces = (ns.replace("*", sname) for ns in EXPORT_NAMESPACES)
    alldata = data.partial_matrix(
        chain.from_iterable(s.history_raw(ns) for ns in namespaces)
    )

    async for chunk in data.json_out(transformer(alldata, **transkwargs)):
        yield chunk
        await asyncio.sleep(0)


def get_secret(user: str, pw: str) -> str:
    salted = "/".join([user, pw, u.KEY, d.SALT, admins()])

    return t.sha256(salted)


def info_online(
    sname: t.Sessionname,
) -> dict[str, Any]:
    info = u.INFO[sname]
    online = {
        uname: u.find_online(t.PlayerIdentifier(sname, uname)) for uname in info.keys()
    }  # TODO: this seems inefficient

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
                await q.enqueue(
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
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        u.MANUAL_DROPOUTS.add(pid)


async def put_to_end(sname: t.Sessionname, unames: list[str]) -> dict[str, dict]:
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if player.show_page < len(player.page_order):
                player.show_page = len(player.page_order)

                await q.enqueue(
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
    for uname in unames:
        ptuple = sname, uname

        await q.enqueue(
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
    for uname in unames:
        pid = t.PlayerIdentifier(sname, uname)

        with pid() as player:
            if -1 < player.show_page <= len(player.page_order):
                player.show_page -= 1

                await q.enqueue(
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


def rooms() -> SortedDict[str, dict]:
    with s.Admin() as admin:
        return SortedDict(admin.rooms)


def sessions() -> dict[str, dict[str, Any]]:
    with s.Admin() as admin:
        snames = admin.sessions
        session_paths = [s.mkpath("session", sname) for sname in snames]

    fields = ["config", "description", "room", "players", "groups", "active"]

    data = {field: s.field_from_paths(session_paths, field) for field in fields}

    return {
        sname: {
            "sname": sname,
            "active": data["active"]
            .get((f"session/{sname}", "active"), t.Value(0.0, False, False))
            .data,
            "config": data["config"]
            .get((f"session/{sname}", "config"), t.Value(0.0, False, None))
            .data,
            "room": data["room"]
            .get((f"session/{sname}", "room"), t.Value(0.0, False, None))
            .data,
            "description": data["description"]
            .get((f"session/{sname}", "description"), t.Value(0.0, False, None))
            .data,
            "n_players": len(
                data["players"]
                .get((f"session/{sname}", "players"), t.Value(0.0, False, []))
                .data
                or []
            ),
            "n_groups": len(
                data["groups"]
                .get((f"session/{sname}", "groups"), t.Value(0.0, False, []))
                .data
                or []
            ),
            "started": data["config"]
            .get((f"session/{sname}", "config"), t.Value(0.0, False, None))
            .time,
        }
        for sname in snames
    }


def verify_secret(user: str, secret: str) -> Optional[str]:
    if user in d.ADMINS and secret == get_secret(user, d.ADMINS[user]):
        return user

    return None


async def viewdata(
    sname: t.Sessionname, since_epoch: float = 0
) -> tuple[SortedDict, float]:
    rval: SortedDict = SortedDict()
    latest: dict = s.fields_from_session(sname, since_epoch)
    last_update: float = since_epoch

    for path, v in latest.items():
        _, _, uname, field = s.mktrail(path)

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
