# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
Compatibility layer that delegates to appendmuch Store.
"""

from typing import TYPE_CHECKING, Any, Optional

import appendmuch

from uproot.constraints import ensure_not_none

if TYPE_CHECKING:
    from appendmuch import Store


STORE: Optional["Store"] = None
MEMORY_HISTORY: dict[str, Any] = {}

dbns2tuple = appendmuch.dbns2tuple
flatten = appendmuch.flatten
tuple2dbns = appendmuch.tuple2dbns


def set_store(store: "Store") -> None:
    global STORE, MEMORY_HISTORY
    STORE = store
    MEMORY_HISTORY = store.cache


def get_namespace(
    namespace: tuple[str, ...],
    create: bool = False,
) -> Optional[dict[str, Any]]:
    if ensure_not_none(STORE):
        return STORE.get_namespace(namespace, create)

    return None  # unreachable


def load_database_into_memory() -> None:
    if ensure_not_none(STORE):
        STORE.load()
