# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Callable, Optional, Sequence, cast
from uuid import UUID

from pydantic import validate_call

import uproot as u
import uproot.models as um
from uproot.flexibility import flexible
from uproot.storage import Storage
from uproot.types import (
    Bunch,
    ModelIdentifier,
    PlayerIdentifier,
    SessionIdentifier,
    token_unchecked,
)

COLLISIONS: tuple[dict[str, str], dict[str, str]] = {}, {}


class Message(metaclass=um.Entry):
    sender: Optional[PlayerIdentifier]
    text: str


def show_msg(
    chat: ModelIdentifier,
    id: UUID,
    time: Optional[float],
    msg: Message,
    as_viewed_by: Optional[PlayerIdentifier] = None,
) -> dict[str, Any]:
    pseudonyms = um.get_field(chat, "pseudonyms")

    # Initialize variables to satisfy static analysis
    joined_pid = ""
    anonymized = ""

    if msg.sender is not None:
        joined_pid = str(msg.sender)
        anonymized = pseudonyms.get(joined_pid, anonymize(joined_pid))

    if as_viewed_by is None:  # admin
        if msg.sender is None:
            sender_representation = ("admin", "")
        else:
            sender_representation = ("other", f'{joined_pid} ("{anonymized}")')
    elif msg.sender is None:
        sender_representation = ("admin", "")
    elif msg.sender == as_viewed_by:
        sender_representation = ("self", anonymized)
    else:
        sender_representation = ("other", anonymized)

    return {
        "cname": chat.mname,
        "id": id,
        "sender": sender_representation,
        "time": time,
        "text": msg.text,
    }


def anonymize(s: str) -> str:
    if s not in COLLISIONS[0]:
        while True:
            anonid = token_unchecked(6).upper()

            if anonid not in COLLISIONS[1]:
                COLLISIONS[0][s] = anonid
                COLLISIONS[1][anonid] = s
                break

    return COLLISIONS[0][s]


@flexible
@validate_call
def create(session: SessionIdentifier) -> ModelIdentifier:
    chat = um.create_model(session, tag="chat")

    with um.get_storage(chat) as m:
        m.players = []
        m.pseudonyms = {}

    return chat


@validate_call
def model(chat: ModelIdentifier) -> Storage:
    return um.get_storage(chat)


@validate_call
def players(chat: ModelIdentifier) -> Bunch:
    return cast(Bunch, um.get_field(chat, "players"))


@flexible
def add_player(
    chat: ModelIdentifier, pid: PlayerIdentifier, pseudonym: Optional[str] = None
) -> None:
    with model(chat) as m:
        m.players.append(pid)

        if pseudonym is not None:
            m.pseudonyms[str(pid)] = pseudonym


@validate_call
def messages(chat: ModelIdentifier) -> list[tuple[UUID, float, Message]]:
    return um.get_entries(chat, Message)


@flexible
@validate_call
def add_message(
    chat: ModelIdentifier,
    sender: Optional[PlayerIdentifier],
    msgtext: str,
) -> UUID:
    return um.add_raw_entry(
        chat,
        {"sender": sender, "text": msgtext},
    )


@validate_call
def exists(chat: ModelIdentifier) -> bool:
    return um.model_exists(chat)


async def notify(
    mid: ModelIdentifier,
    msg_id: UUID,
    pid: PlayerIdentifier,
    player: Storage,
    msgtext: str,
    recipients: Sequence[PlayerIdentifier] | None = None,
) -> None:
    import uproot.deployment as d
    import uproot.queues as q
    from uproot.types import ensure_awaitable, optional_call

    if recipients is None:
        recipients = players(mid)

    msg = Message(sender=pid, text=msgtext)  # type: ignore[call-arg]

    for p in recipients:
        q.enqueue(
            tuple(p),
            {
                "source": "chat",
                "data": show_msg(
                    mid,
                    msg_id,
                    d.DATABASE.now,  # HACK: approximate time
                    msg,
                    p,
                ),
                "event": "_uproot_Chatted",
            },
        )

    for fmodule, fname in u.CHAT_HOOKS.get((mid.sname, mid.mname), ()):
        try:
            await ensure_awaitable(
                optional_call,
                u.APPS[fmodule],
                fname,
                chat=mid,
                player=player,
                message=msgtext,
            )
        except Exception:
            d.LOGGER.exception(f"Exception in chat hook {fmodule}.{fname}")


def on_message(
    chat: ModelIdentifier,
    fun: Callable[..., Any],
) -> None:
    pair = (fun.__module__, fun.__name__)

    with model(chat) as m:
        if not hasattr(m, "_uproot_on_message"):
            m._uproot_on_message = []

        if pair not in m._uproot_on_message:
            m._uproot_on_message.append(list(pair))

    key = (chat.sname, chat.mname)
    hooks = u.CHAT_HOOKS.setdefault(key, [])

    if pair not in hooks:
        hooks.append(pair)
