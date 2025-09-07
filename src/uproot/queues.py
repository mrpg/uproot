# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, validate_call

from uproot.types import uuid

CredentialType = str
EntryType = dict[str, Any]
PathType = tuple[str, ...]

Q: defaultdict[PathType, asyncio.Queue[tuple[str, EntryType]]] = defaultdict(
    asyncio.Queue
)
CREDENTIALS: dict[PathType, CredentialType] = dict()


class EntryRequest(BaseModel):
    credential: CredentialType
    entry: EntryType


@validate_call
def is_authorized(path: PathType, cred: CredentialType) -> bool:
    """
    Verify if the provided credential is authorized to access the specified path.

    This function checks if the given credential matches the one stored for the
    specified path in the CREDENTIALS dictionary. It's designed to be used as
    a simple authentication mechanism to protect queue access.

    Args:
        path: A tuple of strings identifying the queue.
        cred: The API key or credential string to validate against the stored
              credential for the specified path.

    Returns:
        bool: True if the credential is valid for the path (exists and matches),
              False otherwise.
    """
    return path in CREDENTIALS and CREDENTIALS[path] == cred


@validate_call
def enqueue(path: PathType, entry: EntryType) -> tuple[PathType, str]:
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
async def read(path: PathType) -> tuple[str, EntryType]:
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
