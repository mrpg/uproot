# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from decimal import Decimal
from typing import Annotated, Any, Awaitable, Callable, Iterable, cast

from markupsafe import Markup
from pydantic import validate_call

import uproot as u
import uproot.chat
import uproot.types as t
from uproot.constraints import ensure
from uproot.flexibility import PlayerLike, flexible, is_player_like
from uproot.pages import page2path
from uproot.queries import FieldReferent
from uproot.queues import enqueue
from uproot.storage import Player, Storage


def live(method: Callable[..., Any]) -> Callable[..., Any]:
    wrapped = t.timed(validate_call(method, config=dict(arbitrary_types_allowed=True)))  # type: ignore[call-overload]
    newmethod = classmethod(wrapped)

    newmethod.__func__.__live__ = True  # type: ignore[attr-defined]

    return newmethod  # type: ignore[return-value]


@flexible
def send_to_one(
    recipient: t.PlayerIdentifier,
    data: Any,
    event: str = "_uproot_Received",
) -> None:
    enqueue(
        tuple(recipient),
        dict(
            source="send_to",
            data=data,
            event=event,
        ),
    )


def send_to(
    recipient: PlayerLike | Iterable[PlayerLike],
    data: Any,
    event: str = "_uproot_Received",
) -> None:
    if is_player_like(recipient):
        send_to_one(recipient, data, event)
    elif isinstance(recipient, Iterable):
        for one_recipient in recipient:  # type: ignore[union-attr]
            send_to_one(one_recipient, data, event)
    else:
        raise TypeError(
            "send_to must be called with a PlayerLike or Iterable[PlayerLike]."
        )


@flexible
def others_in_session(player: Storage) -> t.StorageBunch:
    pid = ~player

    with player._uproot_session() as s:
        bunch = s.players

    return t.StorageBunch([Player(*pid_) for pid_ in bunch if pid_ != pid])


@flexible
def others_in_group(player: Storage) -> t.StorageBunch:
    pid = ~player

    with player.group as g:
        bunch = g.players

    return t.StorageBunch([Player(*pid_) for pid_ in bunch if pid_ != pid])


@flexible
def other_in_group(player: Storage) -> Storage:
    others = others_in_group(player)

    ensure(len(others) == 1, ValueError, "Expected exactly one other player in group")

    return others[0]


@flexible
def other_in_session(player: Storage) -> Storage:
    others = others_in_session(player)

    ensure(len(others) == 1, ValueError, "Expected exactly one other player in session")

    return others[0]


def players(
    arg: Annotated[Storage, "Session or Group object"] | list[t.PlayerIdentifier],
) -> t.StorageBunch:
    if isinstance(arg, list):
        return t.StorageBunch([Player(*pid) for pid in arg])
    elif isinstance(arg, Storage) and arg.__namespace__[0] in ("session", "group"):
        with arg:
            return players(getattr(arg, "players"))
    else:
        raise NotImplementedError(
            f"players() can only be called with a Session or Group storage object or a list, "
            f"yet it was invoked with {arg}"
        )


@flexible
def reload(player: Storage) -> None:
    enqueue(
        (player._uproot_session, player.name),
        dict(
            source="admin",
            kind="action",
            payload=dict(
                action="reload",
            ),
        ),
    )


@flexible
def move_to_page(player: Storage, target: type[t.Page], reload_: bool = True) -> None:
    target_path = page2path(target)
    player.show_page = player.page_order.index(target_path, player.show_page)

    if reload_:
        reload(player)


@flexible
def move_to_end(player: Storage, reload_: bool = True) -> None:
    player.show_page = len(player.page_order)

    if reload_:
        reload(player)


@flexible
def mark_dropout(player: Storage) -> None:
    pid = cast(t.PlayerIdentifier, ~player)

    u.MANUAL_DROPOUTS.add(pid)


@flexible
def watch_for_dropout(
    player: Storage,
    fun: Callable[[Storage], Awaitable[None]],
    tolerance: float = 30.0,
) -> None:
    triplet = (tolerance, fun.__module__, fun.__name__)

    ensure(
        callable(fun) and (isinstance(tolerance, int) or isinstance(tolerance, float)),
        TypeError,
        "Function must be callable and tolerance must be int or float",
    )

    if not hasattr(player, "_uproot_watch"):
        player._uproot_watch = list()

    player._uproot_watch.append(triplet)

    u.WATCH.add((cast(t.PlayerIdentifier, ~player), *triplet))


class Random(t.SmoothOperator):
    def __init__(self, *pages: t.PageLike) -> None:
        self.pages: list[t.PageLike] = [
            INTERNAL_PAGES["{"],
            INTERNAL_PAGES["RandomStart"],
            *pages,
            INTERNAL_PAGES["RandomEnd"],
            INTERNAL_PAGES["}"],
        ]

    def expand(self) -> list[t.PageLike]:
        return self.pages

    @classmethod
    async def start(page, player: Storage) -> None:
        from random import shuffle

        # Find the nearest #RandomStart before our position
        start_ix = None
        for i in range(player.show_page, -1, -1):
            if player.page_order[i] == "#RandomStart":
                start_ix = i
                break

        if start_ix is None:
            raise RuntimeError("Could not find #RandomStart")

        # Find the matching #RandomEnd for this #RandomStart
        random_depth = 1
        end_ix = None
        for i in range(start_ix + 1, len(player.page_order)):
            if player.page_order[i] == "#RandomStart":
                random_depth += 1
            elif player.page_order[i] == "#RandomEnd":
                random_depth -= 1
                if random_depth == 0:
                    end_ix = i
                    break

        if end_ix is None:
            raise RuntimeError("Could not find matching #RandomEnd")

        pages = player.page_order[start_ix + 1 : end_ix]

        # Group pages by brackets
        grouped_pages = []
        i = 0
        while i < len(pages):
            if pages[i] == "#{":
                # Find the matching closing bracket
                bracket_group = ["#{"]
                bracket_depth = 1
                i += 1  # Skip the opening bracket

                while i < len(pages) and bracket_depth > 0:
                    if pages[i] == "#{":
                        bracket_depth += 1
                    elif pages[i] == "#}":
                        bracket_depth -= 1

                    bracket_group.append(pages[i])
                    i += 1

                if bracket_depth == 0:
                    grouped_pages.append(bracket_group)
                else:
                    raise RuntimeError("Unmatched opening bracket")
            elif pages[i] == "#}":
                raise RuntimeError("Unmatched closing bracket")
            else:
                grouped_pages.append([pages[i]])
                i += 1

        # Shuffle the groups
        shuffle(grouped_pages)

        # Flatten back to page list
        shuffled_pages = []
        for group in grouped_pages:
            shuffled_pages.extend(group)

        player.page_order[start_ix + 1 : end_ix] = shuffled_pages


class Rounds(t.SmoothOperator):
    def __init__(self, *pages: t.PageLike, n: int) -> None:
        self.pages = [
            INTERNAL_PAGES["{"],
            INTERNAL_PAGES["RoundStart"],
            *pages,
            INTERNAL_PAGES["RoundEnd"],
            INTERNAL_PAGES["}"],
        ]
        self.n = n

    def expand(self) -> list[t.PageLike]:
        return self.n * self.pages

    @classmethod
    async def next(page, player: Storage) -> None:
        if not hasattr(player, "round") or player.round is None:
            player.round = 1
        else:
            player.round += 1


class Repeat(t.SmoothOperator):
    def __init__(self, *pages: t.PageLike) -> None:
        self.pages = [
            INTERNAL_PAGES["{"],
            INTERNAL_PAGES["RepeatStart"],
            *pages,
            INTERNAL_PAGES["RepeatEnd"],
            INTERNAL_PAGES["}"],
        ]

    def expand(self) -> list[t.PageLike]:
        return self.pages

    @classmethod
    async def continue_maybe(page, player: Storage) -> None:
        end_ix = player.page_order.index("#RepeatEnd", player.show_page)

        for start_ix in range(end_ix - 1, -1, -1):
            if player.page_order[start_ix] == "#RepeatStart":
                break
        else:
            raise RuntimeError("Could not find #RepeatStart")

        do_continue = player.add_round

        if do_continue:
            player.page_order = (
                player.page_order[: (end_ix + 1)]
                + player.page_order[start_ix : (end_ix + 1)]
                + player.page_order[(end_ix + 1) :]
            )

    @classmethod
    async def next(page, player: Storage) -> None:
        if not hasattr(player, "round") or player.round is None:
            player.round = 1
        else:
            player.round += 1


class Bracket(t.SmoothOperator):
    def __init__(self, *pages: t.PageLike) -> None:
        self.pages = [
            INTERNAL_PAGES["{"],
            *pages,
            INTERNAL_PAGES["}"],
        ]

    def expand(self) -> list[t.PageLike]:
        return self.pages


INTERNAL_PAGES = {
    "RandomStart": type(
        "RandomStart",
        (t.InternalPage,),
        dict(after_always_once=Random.__dict__["start"]),
    ),
    "RandomEnd": type(
        "RandomEnd",
        (t.InternalPage,),
        dict(),
    ),
    "RoundStart": type(
        "RoundStart",
        (t.InternalPage,),
        dict(before_always_once=Rounds.__dict__["next"]),
    ),
    "RoundEnd": type(
        "RoundEnd",
        (t.InternalPage,),
        dict(),
    ),
    "RepeatStart": type(
        "RepeatStart",
        (t.InternalPage,),
        dict(before_always_once=Repeat.__dict__["next"]),
    ),
    "RepeatEnd": type(
        "RepeatEnd",
        (t.InternalPage,),
        dict(before_always_once=Repeat.__dict__["continue_maybe"]),
    ),
    "{": type(
        "{",
        (t.InternalPage,),
        dict(),
    ),
    "}": type(
        "}",
        (t.InternalPage,),
        dict(),
    ),
}


chat = uproot.chat
cu = Decimal
GroupCreatingWait = t.GroupCreatingWait
Page = t.Page
_p = FieldReferent()
safe = Markup
SynchronizingWait = t.SynchronizingWait
uuid = t.uuid
