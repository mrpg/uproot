import asyncio
from uuid import uuid4

import uproot.queues as q


def setup_function():
    q.Q.clear()


def test_enqueue_drops_without_registered_consumer():
    path = ("session", "player")

    q.enqueue(path, {"event": "Ignored"})

    assert path not in q.Q


def test_enqueue_fans_out_to_every_consumer():
    path = ("session", "player")
    first = q.register(path)
    second = q.register(path)

    q.enqueue(path, {"event": "Queued"})

    assert first.get_nowait()[1] == {"event": "Queued"}
    assert second.get_nowait()[1] == {"event": "Queued"}


def test_deregister_keeps_other_consumers_attached():
    path = ("session", "player")
    first = q.register(path)
    second = q.register(path)

    q.deregister(path, first)
    q.enqueue(path, {"event": "Queued"})

    assert first.empty()
    assert second.get_nowait()[1] == {"event": "Queued"}


def test_deregister_of_last_consumer_removes_path():
    path = ("session", "player")
    queue = q.register(path)
    q.enqueue(path, {"event": "Queued"})

    q.deregister(path, queue)
    q.enqueue(path, {"event": "Ignored"})

    assert path not in q.Q


def test_deregister_ignores_unknown_queue_and_path():
    path = ("session", "player")
    queue = q.register(path)

    q.deregister(("session", "other"), queue)
    q.deregister(path, q.register(("session", "other")))

    q.enqueue(path, {"event": "Queued"})
    assert queue.get_nowait()[1] == {"event": "Queued"}


def test_registered_queue_drops_oldest_entry_when_full():
    path = ("session", "player")
    queue = q.register(path)

    for index in range(q.MAX_QUEUE_SIZE + 1):
        q.enqueue(path, {"index": index})

    assert queue.qsize() == q.MAX_QUEUE_SIZE
    first_id, first_entry = queue.get_nowait()
    assert first_id is not None
    assert first_entry["index"] == 1


def test_put_lossy_retries_if_full_queue_is_empty_when_dropping(monkeypatch):
    queue = asyncio.Queue(maxsize=1)
    item = (uuid4(), {"event": "Queued"})
    state = {"get_attempts": 0, "put_attempts": 0}
    original_get_nowait = queue.get_nowait
    original_put_nowait = queue.put_nowait

    def get_nowait():
        state["get_attempts"] += 1

        if state["get_attempts"] == 1:
            raise asyncio.QueueEmpty

        return original_get_nowait()

    def put_nowait(item):
        state["put_attempts"] += 1

        if state["put_attempts"] == 1:
            raise asyncio.QueueFull

        return original_put_nowait(item)

    monkeypatch.setattr(queue, "get_nowait", get_nowait)
    monkeypatch.setattr(queue, "put_nowait", put_nowait)

    q.put_lossy(queue, item)

    assert queue.get_nowait() == item


async def test_read_returns_entries_in_order():
    path = ("session", "player")
    queue = q.register(path)

    q.enqueue(path, {"index": 0})
    q.enqueue(path, {"index": 1})

    assert (await q.read(queue))[1] == {"index": 0}
    assert (await q.read(queue))[1] == {"index": 1}
