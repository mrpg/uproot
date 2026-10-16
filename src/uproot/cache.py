# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
The global appendmuch Store, set by uproot.deployment.
"""

from typing import TYPE_CHECKING, Any

from uproot.constraints import ensure_not_none

if TYPE_CHECKING:
    from appendmuch import Store


STORE: "Store | None" = None


def set_store(store: "Store") -> None:
    global STORE
    STORE = store


def get_namespace(
    namespace: tuple[str, ...],
    create: bool = False,
) -> dict[str, Any] | None:
    if ensure_not_none(STORE):
        return STORE.get_namespace(namespace, create)

    return None  # unreachable


MISSING = object()


def peek(namespace: tuple[str, ...], field: str, default: Any = MISSING) -> Any:
    """Return the current value of a field like Storage, but without copying
    it. Callers must not mutate the value. Without a current value, return
    default if given."""
    if ensure_not_none(STORE):
        history = STORE.field_history(namespace, field)

        if history and not history[-1].unavailable:
            return history[-1].data

    if default is not MISSING:
        return default

    raise AttributeError(f"{namespace!r} has no current value for {field!r}")


def load_database_into_memory() -> None:
    if ensure_not_none(STORE):
        STORE.load()
