import uproot.queues as q


def setup_function():
    q.Q.clear()
    q.ACTIVE.clear()


def test_enqueue_drops_without_registered_consumer():
    path = ("session", "player")

    q.enqueue(path, {"event": "Ignored"})

    assert path not in q.Q


def test_cleanup_removes_queue_and_blocks_later_enqueue():
    path = ("session", "player")
    q.register(path)
    q.enqueue(path, {"event": "Queued"})

    q.cleanup(path)
    q.enqueue(path, {"event": "Ignored"})

    assert path not in q.Q


def test_registered_queue_drops_oldest_entry_when_full():
    path = ("session", "player")
    q.register(path)

    for index in range(q.MAX_QUEUE_SIZE + 1):
        q.enqueue(path, {"index": index})

    assert q.Q[path].qsize() == q.MAX_QUEUE_SIZE
    first_id, first_entry = q.Q[path].get_nowait()
    assert first_id is not None
    assert first_entry["index"] == 1
