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
MAX_QUEUE_SIZE = 1024

Q: dict[PathType, asyncio.Queue[tuple[UUID, EntryType]]] = {}
ACTIVE: set[PathType] = set()


@validate_call
def register(path: PathType) -> None:
    ACTIVE.add(path)
    Q.setdefault(path, asyncio.Queue(maxsize=MAX_QUEUE_SIZE))


@validate_call
def cleanup(path: PathType) -> None:
    ACTIVE.discard(path)
    queue = Q.pop(path, None)

    if queue is None:
        return

    while not queue.empty():
        queue.get_nowait()
        queue.task_done()


@validate_call
def enqueue(path: PathType, entry: EntryType) -> tuple[PathType, UUID]:
    """
    Enqueue an entry into the queue specified by path.

    Args:
        path: A tuple of strings identifying the queue.
        entry: The entry to enqueue.

    Returns:
        A tuple of the path and the UUID assigned to the entry.
    """
    u = uuid()

    if path not in ACTIVE:
        return path, u

    queue = Q.setdefault(path, asyncio.Queue(maxsize=MAX_QUEUE_SIZE))

    if queue.full():
        queue.get_nowait()
        queue.task_done()

    queue.put_nowait((u, entry))

    return path, u


@validate_call
async def read(path: PathType) -> tuple[UUID, EntryType]:
    """
    Read and remove the next entry from the queue specified by path.

    Args:
        path: A tuple of strings identifying the queue.

    Returns:
        A tuple containing the UUID and the entry.

    The path is registered as an active consumer before waiting.
    """
    register(path)
    queue = Q[path]
    u, entry = await queue.get()
    queue.task_done()

    return u, entry
