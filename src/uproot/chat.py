# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Iterator, Optional
from uuid import uuid4

from pydantic import Field, validate_call
from pydantic.dataclasses import dataclass as validated_dataclass

import uproot.model as um
import uproot.types as t
from uproot.flexibility import flexible
from uproot.storage import Storage

COLLISIONS: tuple[dict[str, str], dict[str, str]] = dict(), dict()


class Message(metaclass=um.Entry):
    id: str = Field(
        default_factory=lambda: str(uuid4()),
        exclude=True,
        repr=False,
    )
    sender: Optional[t.PlayerIdentifier] = None
    text: str = ""


@validated_dataclass
class ConveniencePlayerIdentifierList:
    _list: list[t.PlayerIdentifier]


def show_msg(
    chat: t.ModelIdentifier,
    msg: Message,
    as_viewed_by: Optional[t.PlayerIdentifier] = None,
    *,
    with_time: Optional[float] = None,
) -> dict[str, Any]:
    pseudonyms = um.get(chat, "pseudonyms")

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
        id=msg.id,
        sender=sender_representation,
        time=msg.time or with_time,  # type: ignore[attr-defined]
        text=msg.text,
    )


def anonymize(s: str) -> str:
    if s not in COLLISIONS[0]:
        while True:
            anonid = t.token_unchecked(6).upper()

            if anonid not in COLLISIONS[1]:
                COLLISIONS[0][s] = anonid
                COLLISIONS[1][anonid] = s
                break

    return COLLISIONS[0][s]


@flexible
@validate_call
def create(session: t.SessionIdentifier) -> t.ModelIdentifier:
    chat = um.create(session, tag="chat")

    with um.model(chat) as m:
        m.players = list()
        m.pseudonyms = dict()

    return chat


@validate_call
def model(chat: t.ModelIdentifier) -> Storage:
    return um.model(chat)


@validate_call
def players(chat: t.ModelIdentifier) -> list[t.PlayerIdentifier]:
    return ConveniencePlayerIdentifierList(_list=um.get(chat, "players"))._list


@flexible
@validate_call
def add_player(
    chat: t.ModelIdentifier, pid: t.PlayerIdentifier, pseudonym: Optional[str] = None
) -> None:
    with model(chat) as m:
        m.players.append(pid)

        if pseudonym is not None:
            m.pseudonyms[str(pid)] = pseudonym


@validate_call
def messages(chat: t.ModelIdentifier) -> Iterator[Message]:
    return um.all(chat, as_type=Message)


@flexible
@validate_call
def add(chat: t.ModelIdentifier, msg: Message) -> None:
    return um.add(chat, msg)


@validate_call
def exists(chat: t.ModelIdentifier) -> bool:
    return um.exists(chat)
