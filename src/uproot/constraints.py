# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file intends to provide (1) a simple replacement for raw `assert`s and (2) functions for commonly used constraints.
"""

import string
from typing import Any, Callable, Optional

TOKEN_CHARS = set(string.ascii_letters + string.digits + "-._")


def valid_token(x: str) -> bool:
    if not isinstance(x, str):
        return False  # type: ignore[unreachable]

    for ch in x:
        if ch not in TOKEN_CHARS:
            return False

    return True


def return_or_raise(
    value: Any,
    predicate: Callable[[Any], bool],
    exctype: type[Exception] = ValueError,
    msg: Optional[str] = None,
) -> Any:
    if predicate(value):
        return value

    if msg:
        msg = "Constraint violation: " + msg
    else:
        msg = "Constraint violation"

    raise exctype(msg)


def ensure(
    condition: bool,
    exctype: type[Exception] = ValueError,
    msg: Optional[str] = None,
) -> None:
    if not condition:
        if msg:
            msg = "Constraint violation: " + msg
        else:
            msg = "Constraint violation"

        raise exctype(msg)
