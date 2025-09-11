# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import base64
from decimal import Decimal
from typing import Any

from orjson import dumps as jd
from orjson import loads as jl

import uproot.types as t

TYPES: dict[type, int] = {
    int: 0,  # JSON "number"
    float: 1,  # JSON "number"
    str: 2,  # JSON "string"
    tuple: 3,
    bytes: 4,
    bool: 5,  # JSON "boolean"
    complex: 6,
    type(None): 7,  # JSON "null"
    Decimal: 8,
    frozenset: 9,
    t.PlayerIdentifier: 64,
    t.SessionIdentifier: 65,
    t.GroupIdentifier: 66,
    t.ModelIdentifier: 67,
    list: 128,  # JSON "array"
    dict: 129,  # JSON "object"
    bytearray: 130,
    set: 131,
    t.Bunch: 132,
}


IMMUTABLE_TYPES: tuple[type, ...] = tuple(k for k, v in TYPES.items() if v < 128)
MUTABLE_TYPES: tuple[type, ...] = tuple(k for k, v in TYPES.items() if v >= 128)


def _encode(data: Any) -> tuple[int, bytes]:
    match data:
        case bool():
            return 5, jd(data)
        case t.SessionIdentifier():
            return 65, jd(data.sname)
        case int():
            return 0, jd(data)
        case float():
            return 1, jd(data)
        case str():
            return 2, jd(data)
        case tuple():
            return 3, jd(data)
        case bytes():
            # While very robust and fast, this is wasteful and naïve
            # Should perhaps be changed (with full backwards compat)
            return 4, jd(base64.b64encode(data).decode("ascii"))
        case complex():
            return 6, jd([data.real, data.imag])
        case None:
            return 7, b"null"
        case Decimal():
            return 8, jd(str(data))
        case frozenset():
            return 9, jd(list(data))
        case t.PlayerIdentifier():
            return 64, jd([data.sname, data.uname])
        case t.GroupIdentifier():
            return 66, jd([data.sname, data.gname])
        case t.ModelIdentifier():
            return 67, jd([data.sname, data.mname])
        case list() if data and all(
            isinstance(el, t.PlayerIdentifier) for el in data
        ):  # t.Bunch-like
            return 132, jd(data)
        case list():
            return 128, jd(data)
        case dict():
            return 129, jd(data)
        case bytearray():
            # See comment about bytes
            return 130, jd(base64.b64encode(data).decode("ascii"))
        case set():
            return 131, jd(list(data))
        case _:
            raise NotImplementedError(f"{data} has invalid type: {type(data)}")


def _decode(typeid: int, raw: bytes) -> Any:
    match typeid:
        case 0:  # int
            return jl(raw)
        case 1:  # float
            return jl(raw)
        case 2:  # str
            return jl(raw)
        case 3:  # tuple
            return tuple(jl(raw))
        case 4:  # bytes
            return base64.b64decode(jl(raw).encode("ascii"))
        case 5:  # bool
            return jl(raw)
        case 6:  # complex
            r, i = jl(raw)
            return complex(r, i)
        case 7:  # None
            return None
        case 8:  # Decimal
            return Decimal(jl(raw))
        case 9:  # frozenset
            return frozenset(jl(raw))
        case 64:  # PlayerIdentifier
            sname, uname = jl(raw)
            return t.PlayerIdentifier(sname, uname)
        case 65:  # SessionIdentifier
            return t.SessionIdentifier(jl(raw))
        case 66:  # GroupIdentifier
            sname, gname = jl(raw)
            return t.GroupIdentifier(sname, gname)
        case 67:  # ModelIdentifier
            sname, mname = jl(raw)
            return t.ModelIdentifier(sname, mname)
        case 128:  # list
            return jl(raw)
        case 129:  # dict
            return jl(raw)
        case 130:  # bytearray
            return bytearray(base64.b64decode(jl(raw).encode("ascii")))
        case 131:  # set
            return set(jl(raw))
        case 132:  # Bunch
            return t.Bunch(t.PlayerIdentifier(**el) for el in jl(raw))
        case _:
            raise NotImplementedError(f"Invalid typeid: {typeid}")


def encode(data: Any) -> bytes:
    typeid, raw = _encode(data)
    return bytes([typeid]) + raw


def decode(allbytes: bytes) -> Any:
    return _decode(allbytes[0], allbytes[1:])
