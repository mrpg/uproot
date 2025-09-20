# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from collections import defaultdict
from typing import Any
from uuid import UUID

from pydantic import validate_call

from uproot.types import uuid

CredentialType = str
EntryType = dict[str, Any]
PathType = tuple[str, ...]

Q: defaultdict[PathType, asyncio.Queue[tuple[UUID, EntryType]]] = defaultdict(
    asyncio.Queue
)


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

    Q[path].put_nowait((u, entry))

    return path, u


@validate_call
async def read(path: PathType) -> tuple[UUID, EntryType]:
    """
    Read and remove the next entry from the queue specified by path.

    Args:
        path: A tuple of strings identifying the queue.

    Returns:
        A tuple containing the UUID and the entry.

    Raises:
        KeyError: If the specified queue doesn't exist.
    """
    u, entry = await Q[path].get()
    Q[path].task_done()

    return u, entry
