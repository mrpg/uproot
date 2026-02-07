# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from operator import attrgetter
from typing import Any, Optional, Union, cast


def resolve(referent: Union["FieldReferent", Any], obj: Any) -> Any:
    if isinstance(referent, FieldReferent):
        current = obj

        for field in referent.path:
            current = getattr(current, field)

        return current

    return referent


class Comparison:
    def __init__(
        self,
        op: str,
        lhs: Union["FieldReferent", Any],
        rhs: Union["FieldReferent", Any],
    ) -> None:
        self.op = op
        self.lhs = lhs
        self.rhs = rhs

    def __bool__(self) -> bool:
        raise ValueError

    def __repr__(self) -> str:
        return f"[{self.lhs} {self.op} {self.rhs}]"

    def __call__(self, obj: Any = None) -> bool:
        if self.op == ">":
            return cast(bool, resolve(self.lhs, obj) > resolve(self.rhs, obj))
        if self.op == ">=":
            return cast(bool, resolve(self.lhs, obj) >= resolve(self.rhs, obj))
        if self.op == "<":
            return cast(bool, resolve(self.lhs, obj) < resolve(self.rhs, obj))
        if self.op == "<=":
            return cast(bool, resolve(self.lhs, obj) <= resolve(self.rhs, obj))
        if self.op == "==":
            return cast(bool, resolve(self.lhs, obj) == resolve(self.rhs, obj))
        if self.op == "!=":
            return cast(bool, resolve(self.lhs, obj) != resolve(self.rhs, obj))

        raise NotImplementedError


class FieldReferent:
    def __init__(self, path: Optional[list[str]] = None) -> None:
        self._path = path or []
        self._get = attrgetter(".".join(self._path))

    def __getattr__(self, name: str) -> "FieldReferent":
        return FieldReferent(self._path + [name])

    def __repr__(self) -> str:
        return f"FieldReferent(path={self._path})"

    @property
    def path(self) -> list[str]:
        return self._path.copy()

    def __gt__(self, rhs: Any) -> Comparison:
        return Comparison(">", self, rhs)

    def __ge__(self, rhs: Any) -> Comparison:
        return Comparison(">=", self, rhs)

    def __lt__(self, rhs: Any) -> Comparison:
        return Comparison("<", self, rhs)

    def __le__(self, rhs: Any) -> Comparison:
        return Comparison("<=", self, rhs)

    def __eq__(self, rhs: object) -> Comparison:  # type: ignore[override]
        return Comparison("==", self, rhs)

    def __ne__(self, rhs: object) -> Comparison:  # type: ignore[override]
        return Comparison("!=", self, rhs)

    def __bool__(self) -> bool:
        raise ValueError("You must compare the field directly against False.")

    def __call__(self, obj: object) -> Any:
        return self._get(obj)
