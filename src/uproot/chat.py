# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Optional, cast

from pydantic import validate_call

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

COLLISIONS: tuple[dict[str, str], dict[str, str]] = dict(), dict()


class Message(metaclass=um.Entry):
    sender: Optional[PlayerIdentifier]
    text: str


def show_msg(
    chat: ModelIdentifier,
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

    return dict(
        cname=chat.mname,
        id=msg.id,  # type: ignore[attr-defined]
        sender=sender_representation,
        time=msg.time,  # type: ignore[attr-defined]
        text=msg.text,
    )


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
        m.players = list()
        m.pseudonyms = dict()

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
def messages(chat: ModelIdentifier) -> list[Message]:
    return um.get_entries(chat, Message)


@flexible
@validate_call
def add_message(
    chat: ModelIdentifier,
    sender: Optional[PlayerIdentifier],
    msgtext: str,
) -> Message:
    from uproot.deployment import DATABASE

    um.add_raw_entry(
        chat,
        dict(sender=sender, text=msgtext),
    )

    return Message(sender, msgtext, time=DATABASE.now)  # type: ignore


@validate_call
def exists(chat: ModelIdentifier) -> bool:
    return um.model_exists(chat)
