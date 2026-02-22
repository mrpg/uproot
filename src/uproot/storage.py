# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Callable, cast

import appendmuch

from uproot.constraints import ensure, valid_token
from uproot.types import (
    Bound,
    GroupIdentifier,
    PlayerIdentifier,
    Sessionname,
    Username,
    materialize,
)

VALID_TRAIL0: tuple[str, ...] = ("admin", "session", "player", "group", "model")


def all_good(key: tuple[str, str]) -> bool:
    return True


within = appendmuch.within


class Storage(appendmuch.Storage):
    def __init__(
        self,
        *namespace: str,
        virtual: dict[str, Callable[["Storage"], Any]] | None = None,
    ) -> None:
        from uproot.deployment import STORE

        ensure(
            all(type(t) is str and valid_token(t) for t in namespace),
            ValueError,
            f"{repr(namespace)} is an invalid namespace",
        )
        ensure(namespace[0] in VALID_TRAIL0, ValueError, "Invalid namespace start")

        super().__init__(
            *namespace,
            store=STORE,
            virtual=virtual if virtual is not None else {},
        )

    def __repr__(self) -> str:
        if len(self.__namespace__) == 1:
            return f"{self.__namespace__[0].capitalize()}()"
        return f"{self.__namespace__[0].capitalize()}(*{repr(self.__namespace__[1:])})"


def virtual_group(
    storage: Storage,
) -> Storage | Callable[[str | GroupIdentifier], Storage] | None:
    if storage.__namespace__[0] == "player":
        if storage._uproot_group is None:
            return None
        else:
            return cast(Storage, storage._uproot_group())
    elif storage.__namespace__[0] == "session":

        def grabber(glike: str | GroupIdentifier) -> Storage:
            if isinstance(glike, str):
                return Group(storage.name, glike)
            elif isinstance(glike, GroupIdentifier) and glike.sname == storage.name:
                return materialize(glike)
            else:
                raise TypeError

        return grabber
    else:
        raise AttributeError


def virtual_player(storage: Storage) -> Callable[[str | PlayerIdentifier], Storage]:
    if storage.__namespace__[0] == "session":

        def grabber(plike: str | PlayerIdentifier) -> Storage:
            if isinstance(plike, str):
                return Player(storage.name, plike)
            elif isinstance(plike, PlayerIdentifier) and plike.sname == storage.name:
                return materialize(plike)
            else:
                raise TypeError

        return grabber
    else:
        raise AttributeError


def virtual_context(storage: Storage) -> Any:
    if storage.__namespace__[0] == "player":
        if (app := storage.get("app")) is None:
            return None
        else:
            import uproot as u

            if (context := getattr(u.APPS[app], "Context", None)) is None:
                return None
            else:
                return Bound(context, storage)
    else:
        raise AttributeError


def Admin() -> Storage:
    return Storage(
        "admin",
        virtual={
            "along": lambda s: (lambda field: within.along(s, field)),
            "within": lambda s: (lambda **ctx: within(s, **ctx)),
        },
    )


def Session(sname: Sessionname) -> Storage:
    return Storage(
        "session",
        str(sname),
        virtual={
            "group": virtual_group,
            "player": virtual_player,
            "along": lambda s: (lambda field: within.along(s, field)),
            "within": lambda s: (lambda **ctx: within(s, **ctx)),
        },
    )


def Group(sname: Sessionname, gname: str) -> Storage:
    return Storage(
        "group",
        str(sname),
        gname,
        virtual={
            "session": lambda s: materialize(s._uproot_session),
            "along": lambda s: (lambda field: within.along(s, field)),
            "within": lambda s: (lambda **ctx: within(s, **ctx)),
        },
    )


def Player(sname: Sessionname, uname: Username) -> Storage:
    return Storage(
        "player",
        str(sname),
        str(uname),
        virtual={
            "session": lambda s: materialize(s._uproot_session),
            "group": virtual_group,
            "along": lambda s: (lambda field: within.along(s, field)),
            "within": lambda s: (lambda **ctx: within(s, **ctx)),
            "context": virtual_context,
        },
    )


def Model(sname: Sessionname, mname: str) -> Storage:
    return Storage(
        "model",
        str(sname),
        mname,
        virtual={
            "session": lambda s: materialize(s._uproot_session),
            "along": lambda s: (lambda field: within.along(s, field)),
            "within": lambda s: (lambda **ctx: within(s, **ctx)),
        },
    )
