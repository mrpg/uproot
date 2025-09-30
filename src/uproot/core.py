# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

# This file uses context managers on Storage instances solely if
# the Storage instance is "below" or "a member of" the entity being
# created, initialized, and so on.

import importlib.metadata
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence

import uproot as u
import uproot.storage as s
import uproot.types as t
from uproot.constraints import ensure

if TYPE_CHECKING:
    pass


def create_admin(admin: s.Storage) -> None:
    if not hasattr(admin, "_uproot_key"):
        admin._uproot_key = t.uuid()

    if not hasattr(admin, "sessions"):
        admin.sessions = list()

    if not hasattr(admin, "rooms"):
        admin.rooms = dict()


def create_session(
    admin: s.Storage,
    config: str,
    *,
    sname: Optional[t.Sessionname] = None,
    check_unique: bool = True,
) -> t.SessionIdentifier:
    if sname is None:
        sname = t.token(admin.sessions)
    elif check_unique:
        ensure(
            not any(s == sname for s in admin.sessions),
            ValueError,
            "Session name already exists",
        )

    with s.Session(sname) as session:
        session.active = True
        session.apps = u.CONFIGS[config]  # Use this instead of CONFIGS (TODO)
        session.name = sname
        session.config = config
        session.description = None
        session.groups = list()
        session.models = list()
        session.players = list()
        session.packages = {
            dist.metadata["name"]: dist.version
            for dist in importlib.metadata.distributions()
        }
        session.room = None
        session.testing = False
        session._uproot_secret = t.token_unchecked(8)
        session._uproot_session = ~session

        admin.sessions.append(sname)

    return t.SessionIdentifier(sname)


def finalize_session(sid: t.SessionIdentifier) -> None:
    with sid() as session:
        for appname in session.apps:
            app = u.APPS[appname]

            if hasattr(app, "new_session"):
                app.new_session(session)


def create_model(
    session: s.Storage,
    *,
    mname: Optional[str] = None,
    check_unique: bool = True,
    data: Optional[dict[str, Any]] = None,
) -> t.ModelIdentifier:
    sname = session.name

    if mname is None:
        mname = t.token(session.models)
    elif check_unique:
        ensure(
            not any(mname_ == mname for mname_ in session.models),
            ValueError,
            "Model name already exists",
        )

    mid = t.ModelIdentifier(sname, mname)

    with s.Model(*mid) as model:
        model.id = len(session.models)
        model._uproot_session = ~session

        if data is not None:
            for k, v in data.items():
                setattr(model, k, v)

    session.models.append(mname)

    return mid


def create_group(
    session: s.Storage,
    members: Iterable[t.PlayerIdentifier],
    *,
    gname: Optional[str] = None,
    check_unique: bool = True,
    overwrite: bool = False,
) -> t.GroupIdentifier:
    sname = session.name

    if gname is None:
        gname = t.token(session.groups)
    elif check_unique:
        ensure(gname not in session.groups, ValueError, "Group name already exists")

    gid = t.GroupIdentifier(sname, gname)

    session.groups.append(gname)

    with gid() as group:
        group.id = len(session.groups)
        group.players = list(members)
        group._uproot_session = ~session

        for i, pid in enumerate(members):
            with pid() as player:
                ensure(
                    overwrite or player._uproot_group is None,
                    RuntimeError,
                    "Player already belongs to a group and overwrite=False",
                )

                player._uproot_group = gid
                player.member_id = i

    return gid


def initialize_player(
    pid: t.PlayerIdentifier,
    has_id: int,
    config: str,
    *,
    data: Optional[dict[str, Any]] = None,
) -> None:
    with pid() as player:
        player.app = None
        player.id = has_id
        player.label = ""  # Automatically assigned by a room
        player.page_order = u.CONFIGS_PPATHS[config]
        player.payoff = Decimal("0")
        player.show_page = -1
        player.started = False
        player._uproot_adminchat = None
        player._uproot_dropout = False
        player._uproot_group = None
        player._uproot_key = t.uuid()
        player._uproot_part = 0
        player._uproot_session = t.SessionIdentifier(pid.sname)
        player._uproot_timeouts_until = dict()

        if data is not None:
            for k, v in data.items():
                setattr(player, k, v)

        for appname in u.CONFIGS[config]:
            app = u.APPS[appname]

            if hasattr(app, "new_player"):
                app.new_player(player=player)


def create_player(
    session: s.Storage,
    *,
    uname: Optional[str] = None,
    check_unique: bool = True,
    data: Optional[dict[str, Any]] = None,
) -> t.PlayerIdentifier:
    if data is not None:
        data_ = [data]
    else:
        data_ = None

    if uname is not None:
        return create_players(
            session,
            unames=[uname],
            check_unique=check_unique,
            data=data_,
        ).pop()
    else:
        return create_players(session, n=1, data=data_).pop()


def create_players(
    session: s.Storage,
    *,
    n: Optional[int] = None,
    unames: Optional[list[str]] = None,
    check_unique: bool = True,
    data: Optional[list[dict[str, Any]]] = None,
) -> list[t.PlayerIdentifier]:
    unames_: list[str]
    data_: Sequence[Optional[dict[str, Any]]]

    if unames is None and n is not None:
        unames_ = list(t.tokens(session.players, n))
    elif unames is not None:
        if check_unique:
            ensure(
                not any((p.uname in unames) for p in session.players),
                ValueError,
                "Username already exists",
            )

        unames_ = unames
        ensure(
            len(set(unames_)) == len(unames), ValueError, "Duplicate usernames provided"
        )
    else:
        raise ValueError("Invalid invocation.")

    if data is None:
        data_ = [None] * len(unames_)
    else:
        ensure(
            len(data) == len(unames_) and all(isinstance(d, dict) for d in data),
            ValueError,
            "Data length must match usernames length and all items must be dicts",
        )

        data_ = data

    sname = session.name
    config = session.config

    pids = [t.PlayerIdentifier(sname, uname) for uname in unames_]

    rval: list[t.PlayerIdentifier] = list()

    for startid, (pid, d_) in enumerate(zip(pids, data_), len(session.players)):
        initialize_player(pid, startid, config, data=d_)
        rval.append(pid)

    session.players.extend(
        pids
    )  # TODO: this causes app.new_player to receive a stale player.session

    return rval


def find_free_slot(session: s.Storage) -> Optional[t.PlayerIdentifier]:
    for pid in session.players:
        with pid() as player:
            if not player.get("started", True):
                return pid

    return None


def expand(pages: list[t.PageLike]) -> list[type[t.Page]]:
    result = []

    for item in pages:
        if isinstance(item, t.SmoothOperator):
            expanded = item.expand()

            result.extend(expand(expanded))
        else:
            result.append(item)

    return result
