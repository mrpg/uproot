# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file intends to provide a simple replacement for raw `assert`s.
"""

from typing import Optional


def ensure(
    condition: bool,
    exctype: type[Exception] = ValueError,
    msg: Optional[str] = None,
) -> None:
    if msg:
        msg = "Constraint violation: " + msg
    else:
        msg = "Constraint violation"

    if not condition:
        raise exctype(msg)
