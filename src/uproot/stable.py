# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

"""
This file provides low-level encoding and decoding facilities. THE FUNCTIONALITY
EXHIBITED BY THIS FILE MUST REMAIN BACKWARD COMPATIBLE EVEN ACROSS MAJOR VERSIONS.

This is now a thin wrapper around appendmuch's Codec, registering uproot-specific types.
"""

from typing import Any

from appendmuch import Codec
from orjson import dumps as jd
from orjson import loads as jl

import uproot.types as t

CODEC = Codec()

# Register uproot-specific types

CODEC.register(
    t.SessionIdentifier,
    65,
    lambda d: jd(d.sname),
    lambda r: t.SessionIdentifier(jl(r)),
)

CODEC.register(
    t.PlayerIdentifier,
    64,
    lambda d: jd([d.sname, d.uname]),
    lambda r: t.PlayerIdentifier(*jl(r)),
)

CODEC.register(
    t.GroupIdentifier,
    66,
    lambda d: jd([d.sname, d.gname]),
    lambda r: t.GroupIdentifier(*jl(r)),
)

CODEC.register(
    t.ModelIdentifier,
    67,
    lambda d: jd([d.sname, d.mname]),
    lambda r: t.ModelIdentifier(*jl(r)),
)

# Bunch: list[PlayerIdentifier] — uses predicate to distinguish from plain list
CODEC.register(
    list,
    132,
    jd,
    lambda r: t.Bunch(t.PlayerIdentifier(**el) for el in jl(r)),
    mutable=True,
    predicate=lambda d: d and all(isinstance(el, t.PlayerIdentifier) for el in d),
)


def _get_types() -> dict[type, int]:
    return CODEC.type_map()


TYPES: dict[type, int] = _get_types()
IMMUTABLE_TYPES: tuple[type, ...] = CODEC.immutable_types()
MUTABLE_TYPES: tuple[type, ...] = CODEC.mutable_types()


def encode(data: Any) -> bytes:
    return CODEC.encode(data)


def decode(allbytes: bytes) -> Any:
    return CODEC.decode(allbytes)


def _encode(data: Any) -> tuple[int, bytes]:
    return CODEC.encode_raw(data)
