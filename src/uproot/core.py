# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

# This file uses context managers on Storage instances solely if
# the Storage instance is "below" or "a member of" the entity being
# created, initialized, and so on.

import importlib.metadata
import inspect
import sys
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any, cast

import uproot as u
import uproot.queues as q
import uproot.storage as s
import uproot.types as t
from uproot.constraints import ensure


def create_admin(admin: s.Storage) -> None:
    if not hasattr(admin, "_uproot_key"):
        admin._uproot_key = t.uuid()

    if not hasattr(admin, "_uproot_sessions"):
        admin._uproot_sessions = []

    if not hasattr(admin, "rooms"):
        admin.rooms = {}


def create_session(
    admin: s.Storage,
    config: str,
    *,
    sname: t.Sessionname | None = None,
    check_unique: bool = True,
    settings: dict[str, Any] | None = None,
) -> t.SessionIdentifier:
    ensure(
        settings is None or isinstance(settings, dict),
        TypeError,
        "Session settings must be a JSON object",
    )

    if settings is None:
        settings = {}

    if sname is None:
        sname = t.token(admin._uproot_sessions)
    elif check_unique:
        ensure(
            not any(s == sname for s in admin._uproot_sessions),
            ValueError,
            "Session name already exists",
        )

    for appname in u.CONFIGS[config]:
        app = u.APPS[appname]

        if hasattr(app, "validate_session_settings"):
            validator = app.validate_session_settings
            ensure(
                not inspect.iscoroutinefunction(validator),
                TypeError,
                "validate_session_settings() must be synchronous",
            )
            validator(
                admin=admin,
                config=config,
                settings=settings,
            )

    sid = t.SessionIdentifier(sname)

    with s.Session(sname) as session:
        session.active = True
        session.apps = u.CONFIGS[config]
        session.config = config
        session.description = None
        session._uproot_groups = []
        session._uproot_models = []
        session._uproot_players = []
        session.packages = {
            dist.metadata["name"]: dist.version
            for dist in importlib.metadata.distributions()
        } | {"python": sys.version}
        session.room = None
        session._uproot_settings = settings
        session.sid = sid
        session._uproot_initialized = False
        session._uproot_simulate = False
        session._uproot_testing = False
        session._uproot_secret = t.token_unchecked(8)
        session._uproot_session = t.identify(session)

        admin._uproot_sessions.append(sname)

    return sid


def create_model(
    session: s.Storage,
    *,
    mname: str | None = None,
    check_unique: bool = True,
    data: dict[str, Any] | None = None,
) -> t.ModelIdentifier:
    sname = session.name

    if mname is None:
        mname = t.token(session._uproot_models)
    elif check_unique:
        ensure(
            not any(mname_ == mname for mname_ in session._uproot_models),
            ValueError,
            "Model name already exists",
        )

    mid = t.ModelIdentifier(sname, mname)

    with s.Model(*mid) as model:
        model.id = len(session._uproot_models) + 1
        model.mid = mid
        model._uproot_on_message = []
        model._uproot_session = t.identify(session)

        if data is not None:
            for k, v in data.items():
                setattr(model, k, v)

    session._uproot_models.append(mname)

    return mid


def create_group(
    session: s.Storage,
    members: Iterable[t.PlayerIdentifier],
    *,
    gname: str | None = None,
    check_unique: bool = True,
    expected_size: int | None = None,
    overwrite: bool = False,
) -> t.GroupIdentifier:
    sname = session.name
    members_ = list(members)

    ensure(
        len(set(members_)) == len(members_),
        ValueError,
        "Group members must be unique",
    )

    if expected_size is not None:
        ensure(
            len(members_) == expected_size,
            ValueError,
            f"Expected group of size {expected_size}, got {len(members_)}",
        )

    for pid in members_:
        with t.materialize(pid) as player:
            ensure(
                overwrite or player._uproot_group is None,
                RuntimeError,
                "Player already belongs to a group and overwrite=False",
            )

    if gname is None:
        gname = t.token(session._uproot_groups)
    elif check_unique:
        ensure(
            gname not in session._uproot_groups, ValueError, "Group name already exists"
        )

    gid = t.GroupIdentifier(sname, gname)

    session._uproot_groups.append(gname)

    with t.materialize(gid) as group:
        group.gid = gid
        group.id = len(session._uproot_groups)
        group._uproot_players = members_
        group._uproot_session = t.identify(session)

        for i, pid in enumerate(members_):
            with t.materialize(pid) as player:
                player._uproot_group = gid
                player.member_id = i
                q.enqueue(
                    tuple(pid),
                    {
                        "source": "grouping",
                        "constraint": player.show_page,
                        "event": "Grouped",
                        "data": gid,
                    },
                )

    return gid


def add_to_group(
    group: s.Storage,
    members: Iterable[t.PlayerIdentifier],
    *,
    overwrite: bool = False,
) -> None:
    gid = cast(t.GroupIdentifier, t.identify(group))

    start_index = len(group._uproot_players)

    for i, pid in enumerate(members):
        with t.materialize(pid) as player:
            ensure(
                overwrite or player._uproot_group is None,
                RuntimeError,
                "Player already belongs to a group and overwrite=False",
            )

            player._uproot_group = gid
            player.member_id = start_index + i

        group._uproot_players.append(pid)


def initialize_player(
    pid: t.PlayerIdentifier,
    has_id: int,
    config: str,
    *,
    data: dict[str, Any] | None = None,
) -> None:
    with t.materialize(pid) as player:
        player.app = None
        player.config = config
        player.id = has_id
        player.label = ""  # Automatically assigned by a room
        player.page_order = []
        player.payoff = Decimal(0)
        player.pid = pid
        player.show_page = -1
        player.started = False
        player._uproot_adminchat = None
        player._uproot_adminchat_replies = False
        player._uproot_dropout = False
        player._uproot_group = None
        player._uproot_initialized = False
        player._uproot_key = t.uuid()
        player._uproot_part = 0
        player._uproot_session = t.SessionIdentifier(pid.sname)
        player._uproot_timeouts_until = {}
        player._uproot_watch = []

        if data is not None:
            for k, v in data.items():
                setattr(player, k, v)


def create_player(
    session: s.Storage,
    *,
    uname: str | None = None,
    check_unique: bool = True,
    data: dict[str, Any] | None = None,
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
    n: int | None = None,
    unames: list[str] | None = None,
    check_unique: bool = True,
    data: list[dict[str, Any]] | None = None,
) -> list[t.PlayerIdentifier]:
    unames_: list[str]
    data_: Sequence[dict[str, Any] | None]

    if unames is None and n is not None:
        unames_ = list(t.tokens(session._uproot_players, n))
    elif unames is not None:
        if check_unique:
            ensure(
                not any((p.uname in unames) for p in session._uproot_players),
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

    rval: list[t.PlayerIdentifier] = []

    for startid, (pid, d_) in enumerate(zip(pids, data_), len(session._uproot_players)):
        initialize_player(pid, startid, config, data=d_)
        rval.append(pid)

    session._uproot_players.extend(pids)

    return rval


def find_free_slot(session: s.Storage, label: str = "") -> t.PlayerIdentifier | None:
    fallback: t.PlayerIdentifier | None = None

    for pid in session._uproot_players:
        with t.materialize(pid) as player:
            if not player.started:
                if label != "" and player.get("label", "") == label:
                    return cast(t.PlayerIdentifier, pid)

                if fallback is None and player.get("label", "") == "":
                    fallback = cast(t.PlayerIdentifier, pid)

    return fallback


def expand(pages: Any) -> list[type[t.Page]]:
    result = []

    for item in pages:
        if isinstance(item, list):
            result.extend(expand(item))
        elif isinstance(item, t.SmoothOperator):
            expanded = item.expand()

            result.extend(expand(expanded))
        else:
            result.append(item)

    return result


def make_start_app(appname: str) -> type[t.InternalPage]:
    class StartApp(t.InternalPage):
        __module__ = appname

        @classmethod
        def after_always_once(page, player: s.Storage) -> None:
            player.app = appname

    return StartApp


def make_landing_page(app: Any, appname: str) -> type[t.InternalPage]:
    from uproot.pages import app_or_default

    class LandingPage(t.InternalPage):
        __module__ = appname
        template = app_or_default(app, "LandingPage.html")

        @classmethod
        async def show(page, player: s.Storage) -> bool:
            return True

        @classmethod
        async def before_always_once(page, player: s.Storage) -> None:
            player._uproot_part += 1

    return LandingPage


def resolve_page_order(
    player: s.Storage,
    config: str,
) -> list[str]:
    from uproot.pages import page2path

    result: list[str] = []

    for appname in u.CONFIGS[config]:
        app = u.APPS[appname]

        ensure(
            not hasattr(app, "Constants"),
            AttributeError,
            f"Use 'C' instead of 'Constants' (app {appname})",
        )

        full_pages: list[t.PageLike] = [make_start_app(appname)]

        if hasattr(app, "LANDING_PAGE") and app.LANDING_PAGE:
            full_pages.append(make_landing_page(app, appname))

        if hasattr(app, "page_order"):
            if isinstance(app.page_order, list):
                full_pages.extend(app.page_order)
            elif callable(app.page_order):
                full_pages.extend(app.page_order(player=player))
            else:
                raise TypeError(f"{app}.page_order must be list or callable")

        for page in expand(full_pages):
            result.append(page2path(page))

    return result
