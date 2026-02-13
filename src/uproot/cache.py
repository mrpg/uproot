# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
Compatibility layer that delegates to appendmuch Store.
"""

from typing import TYPE_CHECKING, Any, Optional, Sequence, Union

import appendmuch

if TYPE_CHECKING:
    from appendmuch import Store

    from uproot.storage import Storage


STORE: Optional["Store"] = None
MEMORY_HISTORY: dict[str, Any] = {}

dbns2tuple = appendmuch.dbns2tuple
flatten = appendmuch.flatten
tuple2dbns = appendmuch.tuple2dbns


def set_store(store: "Store") -> None:
    global STORE, MEMORY_HISTORY
    STORE = store
    MEMORY_HISTORY = store.cache


def safe_deepcopy(value: Any) -> Any:
    assert STORE is not None
    from appendmuch.utils import safe_deepcopy as sd

    return sd(value, STORE.codec.immutable_types())


def get_namespace(
    namespace: tuple[str, ...],
    create: bool = False,
) -> Optional[dict[str, Any]]:
    assert STORE is not None
    return STORE.get_namespace(namespace, create)


def field_history_since(
    namespace: tuple[str, ...],
    field: str,
    since: float,
) -> list[Any]:
    assert STORE is not None
    return STORE.field_history_since(namespace, field, since)


def load_database_into_memory() -> None:
    assert STORE is not None
    STORE.load()


def get_current_value(namespace: tuple[str, ...], field: str) -> Any:
    assert STORE is not None
    return STORE.get_current_value(namespace, field)


def db_request(
    caller: Optional["Storage"],
    action: str,
    key: str = "",
    value: Optional[Any] = None,
    *,
    context: Optional[str] = None,
    extra: Optional[
        Union[
            str,
            tuple[list[str], str],
            tuple[Sequence[tuple[str, ...]], str],
            tuple[str, float],
            dict[str, Any],
        ]
    ] = None,
) -> Any:
    assert STORE is not None
    return STORE.db_request(caller, action, key, value, ctx=context, extra=extra)
