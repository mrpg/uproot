# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from typing import Any
from uuid import UUID

from pydantic import validate_call

from uproot.types import uuid

CredentialType = str
EntryType = dict[str, Any]
PathType = tuple[str, ...]
QueueType = asyncio.Queue[tuple[UUID, EntryType]]
MAX_QUEUE_SIZE = 1024

Q: dict[PathType, list[QueueType]] = {}


def put_lossy(queue: QueueType, item: tuple[UUID, EntryType]) -> None:
    """
    Put an item into a bounded queue, dropping oldest entries as needed.
    """
    while True:
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                continue

            queue.task_done()


@validate_call
def register(path: PathType) -> QueueType:
    """
    Attach a new consumer to the queues of path and return its queue.

    Each consumer (usually a websocket connection) owns exactly one queue,
    so concurrent consumers of the same path (a second tab, a not yet
    reaped predecessor connection) never interfere with one another. The
    caller must pass the returned queue to deregister() when it is done.
    """
    queue: QueueType = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    Q.setdefault(path, []).append(queue)

    return queue


def deregister(path: PathType, queue: QueueType) -> None:
    """
    Detach a consumer's queue from path.

    Only the given queue is removed; other consumers of the same path keep
    receiving entries. Unknown queues and paths are ignored.
    """
    queues = Q.get(path)

    if queues is None:
        return

    try:
        queues.remove(queue)
    except ValueError:
        pass

    if not queues:
        del Q[path]


@validate_call
def enqueue(path: PathType, entry: EntryType) -> tuple[PathType, UUID]:
    """
    Enqueue an entry into the queue of every consumer attached to path.

    Entries are dropped if no consumer is attached; a full queue drops its
    oldest entry to make room.

    Args:
        path: A tuple of strings identifying the queue.
        entry: The entry to enqueue.

    Returns:
        A tuple of the path and the UUID assigned to the entry.
    """
    u = uuid()

    for queue in tuple(Q.get(path, ())):
        put_lossy(queue, (u, entry))

    return path, u


async def read(queue: QueueType) -> tuple[UUID, EntryType]:
    """
    Read and remove the next entry from a queue obtained via register().

    Args:
        queue: The consumer's queue.

    Returns:
        A tuple containing the UUID and the entry.
    """
    u, entry = await queue.get()
    queue.task_done()

    return u, entry
