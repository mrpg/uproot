from uuid import uuid4

import uproot as u
import uproot.chat as chat
import uproot.core as c
import uproot.deployment as d
import uproot.events as e
import uproot.queues as q
import uproot.storage as s
import uproot.types as t
from uproot.services import player_service as ps


def setup_module():
    d.DATABASE.reset()
    q.Q.clear()
    e.ADMINCHAT.clear()
    u.CONFIGS["test"] = []


def make_player() -> t.PlayerIdentifier:
    q.Q.clear()
    e.ADMINCHAT.clear()
    sname = f"test-adminchat-{uuid4().hex[:8]}"
    uname = f"alice-{uuid4().hex[:6]}"

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test", sname=sname)

    with s.Session(sid) as session:
        return c.create_player(session, uname=uname)


async def next_event(pid: t.PlayerIdentifier, expected: str, predicate=None) -> dict:
    while True:
        _queue_id, queued = await q.read(tuple(pid))
        if queued["event"] == expected and (predicate is None or predicate(queued)):
            return queued


async def test_adminchat_overview_is_empty_before_first_message():
    pid = make_player()

    overview = await ps.adminchat_overview(pid.sname)

    assert overview[pid.uname]["chat_id"] is None
    assert overview[pid.uname]["enabled"] is False
    assert overview[pid.uname]["message_count"] == 0


async def test_send_adminchat_creates_thread_and_notifies_player():
    pid = make_player()

    payload = await ps.send_adminchat(
        pid.sname, pid.uname, "Please stay on this page.", True
    )

    assert payload["player"]["uname"] == pid.uname
    assert payload["chat"]["enabled"] is True
    assert payload["chat"]["message_count"] == 1
    assert payload["messages"][0]["sender"][0] == "admin"
    assert payload["messages"][0]["text"] == "Please stay on this page."

    with t.materialize(pid) as player:
        assert player._uproot_adminchat is not None
        assert player._uproot_adminchat_replies is True

    queued = await next_event(pid, "_uproot_Chatted")
    assert queued["data"]["sender"][0] == "admin"
    assert queued["data"]["can_reply"] is True

    event = await e.ADMINCHAT[pid.sname].wait()
    assert event["uname"] == pid.uname
    assert event["kind"] in {"state", "message"}


async def test_set_adminchat_replies_emits_state_change():
    pid = make_player()
    await ps.send_adminchat(pid.sname, pid.uname, "Opening channel.", False)

    result = await ps.set_adminchat_replies(pid.sname, pid.uname, True)

    assert result["chat"]["enabled"] is True

    state = await next_event(
        pid,
        "_uproot_AdminchatStateChanged",
        lambda queued: queued["data"]["canReply"] is True,
    )
    assert state["data"]["canReply"] is True


async def test_bulk_enable_replies_creates_chat_without_message():
    pid = make_player()

    result = await ps.set_adminchat_replies_for_players(pid.sname, [pid.uname], True)

    assert result["enabled"] is True
    assert result["players"][0]["chat"]["enabled"] is True
    assert result["players"][0]["chat"]["has_messages"] is False

    with t.materialize(pid) as player:
        assert player._uproot_adminchat is not None
        assert player._uproot_adminchat_replies is True

    state = await next_event(
        pid,
        "_uproot_AdminchatStateChanged",
        lambda queued: queued["data"]["canReply"] is True,
    )
    assert state["data"]["hasMessages"] is False


async def test_disable_replies_without_existing_chat_is_a_noop():
    pid = make_player()

    result = await ps.set_adminchat_replies(pid.sname, pid.uname, False)

    assert result["chat"]["chat_id"] is None
    assert result["chat"]["enabled"] is False
    assert result["chat"]["has_messages"] is False

    with t.materialize(pid) as player:
        assert player._uproot_adminchat is None
        assert player._uproot_adminchat_replies is False


async def test_broadcast_sends_to_multiple_players():
    pid1 = make_player()
    sname = pid1.sname

    with s.Session(sname) as session:
        pid2 = c.create_player(session, uname=f"bob-{uuid4().hex[:6]}")

    result = await ps.send_adminchat_to_players(
        sname, [pid1.uname, pid2.uname], "Hello everyone!", True
    )

    assert result["sent_count"] == 2
    assert len(result["players"]) == 2

    for payload in result["players"]:
        assert payload["chat"]["message_count"] == 1
        assert payload["chat"]["enabled"] is True
        assert payload["messages"][0]["text"] == "Hello everyone!"


async def test_overview_includes_last_message_text():
    pid = make_player()
    await ps.send_adminchat(pid.sname, pid.uname, "Can you hear me?")

    overview = await ps.adminchat_overview(pid.sname)

    assert overview[pid.uname]["last_message_text"] == "Can you hear me?"
    assert overview[pid.uname]["last_sender"] == "admin"


async def test_player_reply_appears_in_admin_thread():
    pid = make_player()
    await ps.send_adminchat(pid.sname, pid.uname, "Need anything?", True)

    mid = chat.adminchat_for_player(pid)
    assert mid is not None

    msg_id = chat.add_message(mid, pid, "Yes, I have a question.")

    with t.materialize(pid) as player:
        await chat.notify_adminchat(mid, msg_id, pid, player, "Yes, I have a question.")

    thread = await ps.adminchat_thread(pid.sname, pid.uname)

    assert len(thread["messages"]) == 2
    assert thread["messages"][-1]["sender"] == ("other", pid.uname)
    assert thread["messages"][-1]["text"] == "Yes, I have a question."
