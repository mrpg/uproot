# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""Internal storage drafts for validating page moves before committing them."""

from collections.abc import Callable
from copy import deepcopy
from typing import Any, Self

from uproot.storage import Storage


def draft(player: Storage) -> tuple[Any, Callable[[], None]]:
    """A stand-in for player and a function that commits its changes to player.
    Until then, they stay out of player's history. Commit retracts explicitly
    deleted fields first, then writes final values in last-assignment order."""
    missing = object()
    values: dict[str, Any] = {}  # Field -> value in the draft, or missing
    retracted: dict[str, None] = {}  # Preserve the order of explicit deletions

    class Draft:
        def __getattr__(self, name: str) -> Any:
            if name not in values:
                value = getattr(player, name, missing)
                values[name] = missing if value is missing else deepcopy(value)

            if values[name] is missing:
                raise AttributeError(f"{player} has no .{name}")

            return values[name]

        def __setattr__(self, name: str, value: Any) -> None:
            values.pop(name, None)
            values[name] = value

        def __delattr__(self, name: str) -> None:
            getattr(self, name)  # Raises AttributeError if there is none
            retracted[name] = None
            values[name] = missing

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc_info: object) -> None:
            pass

        def get(self, name: str, default: Any = None) -> Any:
            return getattr(self, name, default)

        def refresh(self, *fields: str) -> None:
            pass  # The draft is the only writer until it is committed

    def commit() -> None:
        # End the old round/block even if the draft sets it again. Otherwise,
        # history can pair a new app or block with the previous round.
        for name in retracted:
            if hasattr(player, name):
                delattr(player, name)

        for name, value in values.items():
            original = getattr(player, name, missing)

            if value is missing:
                if original is not missing:
                    delattr(player, name)
            elif original is missing or original != value:
                setattr(player, name, value)

    return Draft(), commit
