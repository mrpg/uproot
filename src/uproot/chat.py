# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from typing import Any, Callable, Optional, Sequence, cast
from uuid import UUID

from pydantic import validate_call

import uproot as u
import uproot.deployment as d
import uproot.events as e
import uproot.models as um
import uproot.queues as q
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
    sender: PlayerIdentifier | str | None
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

    if isinstance(msg.sender, str):
        sender_representation = ("other", msg.sender)
    elif msg.sender is not None:
        joined_pid = str(msg.sender)
        anonymized = pseudonyms.get(joined_pid, anonymize(joined_pid))

        if as_viewed_by is None:  # admin
            sender_representation = ("other", f'{joined_pid} ("{anonymized}")')
        elif msg.sender == as_viewed_by:
            sender_representation = ("self", anonymized)
        else:
            sender_representation = ("other", anonymized)
    elif as_viewed_by is None:  # admin
        sender_representation = ("admin", "")
    else:
        sender_representation = ("admin", "")

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
    sender: PlayerIdentifier | str | None,
    msgtext: str,
) -> UUID:
    return um.add_raw_entry(
        chat,
        {"sender": sender, "text": msgtext},
    )


@validate_call
def exists(chat: ModelIdentifier) -> bool:
    return um.model_exists(chat)


@validate_call
def is_adminchat(chat: ModelIdentifier) -> bool:
    return cast(bool, um.get_field(chat, "tag") == "adminchat")


@validate_call
def has_messages(chat: ModelIdentifier) -> bool:
    return bool(messages(chat))


@validate_call
def adminchat_for_player(pid: PlayerIdentifier) -> Optional[ModelIdentifier]:
    with pid() as player:
        return cast(Optional[ModelIdentifier], player.get("_uproot_adminchat"))


@validate_call
def adminchat_reply_state(pid: PlayerIdentifier) -> bool:
    with pid() as player:
        return bool(player.get("_uproot_adminchat_replies", False))


@flexible
@validate_call
def create_adminchat(pid: PlayerIdentifier) -> ModelIdentifier:
    session = SessionIdentifier(pid.sname)
    chat = um.create_model(session, tag="adminchat")

    with um.get_storage(chat) as m:
        m.players = [pid]
        m.pseudonyms = {}

    return chat


@flexible
@validate_call
def ensure_adminchat(pid: PlayerIdentifier) -> ModelIdentifier:
    existing = adminchat_for_player(pid)

    if existing is not None and exists(existing):
        return existing

    chat = create_adminchat(pid)

    with pid() as player:
        player._uproot_adminchat = chat

    return chat


def _adminchat_can_reply(
    as_viewed_by: Optional[PlayerIdentifier],
) -> Optional[bool]:
    if as_viewed_by is None:
        return None

    return adminchat_reply_state(as_viewed_by)


def show_adminchat_msg(
    chat: ModelIdentifier,
    id: UUID,
    time: Optional[float],
    msg: Message,
    as_viewed_by: Optional[PlayerIdentifier] = None,
) -> dict[str, Any]:
    if isinstance(msg.sender, str):
        sender_representation = ("other", msg.sender)
    elif msg.sender is None:
        sender_representation = ("admin", "")
    elif as_viewed_by is not None and msg.sender == as_viewed_by:
        sender_representation = ("self", msg.sender.uname)
    else:
        sender_representation = ("other", msg.sender.uname)

    return {
        "cname": chat.mname,
        "id": id,
        "sender": sender_representation,
        "time": time,
        "text": msg.text,
        "can_reply": _adminchat_can_reply(as_viewed_by),
    }


@validate_call
def adminchat_event(
    pid: PlayerIdentifier,
    *,
    kind: str,
    message: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    mid = ensure_adminchat(pid)
    entries = messages(mid)
    last_message = entries[-1][2] if entries else None

    with pid() as player:
        label = player.get("label", "")
        player_id = player.get("id")
        page_order = player.get("page_order", [])
        show_page = player.get("show_page", -1)

    if isinstance(page_order, list) and 0 <= show_page < len(page_order):
        page = page_order[show_page]
    elif show_page == -1:
        page = "Initialize.html"
    else:
        page = "End.html"

    return {
        "kind": kind,
        "uname": pid.uname,
        "chat": {
            "chat_id": mid.mname,
            "enabled": adminchat_reply_state(pid),
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
        },
        "player": {
            "uname": pid.uname,
            "label": label,
            "id": player_id,
            "show_page": show_page,
            "page_order": page_order,
            "page": page,
        },
        "message": message,
    }


@validate_call
def set_adminchat_replies(
    pid: PlayerIdentifier,
    enabled: bool,
) -> dict[str, Any]:
    mid = ensure_adminchat(pid)

    with pid() as player:
        player._uproot_adminchat = mid
        player._uproot_adminchat_replies = enabled

    q.enqueue(
        tuple(pid),
        {
            "source": "adminchat",
            "data": {
                "cname": mid.mname,
                "canReply": enabled,
                "hasMessages": has_messages(mid),
            },
            "event": "_uproot_AdminchatStateChanged",
        },
    )

    event = adminchat_event(pid, kind="state")
    e.ADMINCHAT[pid.sname].set(event)
    return event


async def notify(
    mid: ModelIdentifier,
    msg_id: UUID,
    pid: PlayerIdentifier | str | None,
    player: Storage | None,
    msgtext: str,
    recipients: Sequence[PlayerIdentifier] | None = None,
) -> None:
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


async def notify_adminchat(
    mid: ModelIdentifier,
    msg_id: UUID,
    pid: PlayerIdentifier | None,
    player: Storage | None,
    msgtext: str,
) -> None:
    from uproot.types import ensure_awaitable, optional_call

    recipients = players(mid)
    msg = Message(sender=pid, text=msgtext)  # type: ignore[call-arg]

    for recipient in recipients:
        q.enqueue(
            tuple(recipient),
            {
                "source": "chat",
                "data": show_adminchat_msg(
                    mid,
                    msg_id,
                    d.DATABASE.now,
                    msg,
                    recipient,
                ),
                "event": "_uproot_Chatted",
            },
        )

    if recipients:
        e.ADMINCHAT[mid.sname].set(
            adminchat_event(
                recipients[0],
                kind="message",
                message=show_adminchat_msg(mid, msg_id, d.DATABASE.now, msg, None),
            )
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
