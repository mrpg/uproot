# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

from inspect import currentframe
from types import TracebackType
from typing import Any, Callable, Iterator, Optional, cast

from typing_extensions import Literal

from uproot.cache import db_request, safe_deepcopy
from uproot.constraints import ensure, valid_token
from uproot.stable import IMMUTABLE_TYPES
from uproot.types import (
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    SessionIdentifier,
    Sessionname,
    Username,
    Value,
    context,
)

VALID_TRAIL0: tuple[str, ...] = ("admin", "session", "player", "group", "model")
DEFAULT_VIRTUAL: dict[str, Callable[["Storage"], Any]] = dict(
    session=lambda p: p._uproot_session(),
    group=lambda p: p._uproot_group(),
    along=lambda p: (lambda field: within.along(p, field)),
    within=lambda p: (lambda **context: within(p, **context)),
)


def all_good(key: tuple[str, str]) -> bool:
    return True


class within:
    __slots__ = (
        "__storage__",
        "__context_fields__",
    )

    def __init__(self, storage: "Storage", **context: Any) -> None:
        self.__storage__ = storage
        self.__context_fields__ = context

    def __getattr__(self, name: str) -> Any:
        try:
            return db_request(
                self.__storage__,
                "get_within_context",
                name,
                extra=self.__context_fields__,
            )
        except AttributeError:
            return None

    @classmethod
    def along(cls, storage: "Storage", field: str) -> Iterator[tuple[Any, "within"]]:
        for value in cast(list[Value], db_request(storage, "get_field_history", field)):
            if value.data is not None:
                yield value.data, within(storage, **{field: value.data})


class Storage:
    __slots__ = (
        "__accessed_fields__",
        "__contexts__",
        "__field_cache__",
        "__explicitly_set__",
        "__assigned_values__",
        "name",
        "__namespace__",
        "__virtual__",
        "__weakref__",
    )

    def __init__(
        self,
        *namespace: str,
        virtual: Optional[dict[str, Callable[["Storage"], Any]]] = None,
    ):
        ensure(
            all(type(t) is str and valid_token(t) for t in namespace),
            ValueError,
            f"{repr(namespace)} is an invalid namespace",
        )
        ensure(namespace[0] in VALID_TRAIL0, ValueError, "Invalid namespace start")

        object.__setattr__(self, "name", namespace[-1])
        object.__setattr__(self, "__namespace__", namespace)
        object.__setattr__(self, "__contexts__", 0)
        object.__setattr__(self, "__accessed_fields__", dict())
        object.__setattr__(self, "__field_cache__", dict())
        object.__setattr__(self, "__explicitly_set__", set())
        object.__setattr__(self, "__assigned_values__", dict())
        object.__setattr__(self, "__virtual__", virtual or DEFAULT_VIRTUAL)

    def __invert__(self) -> Identifier:
        match self.__namespace__[0]:
            case "session":
                return SessionIdentifier(*self.__namespace__[1:])
            case "player":
                return PlayerIdentifier(*self.__namespace__[1:])
            case "group":
                return GroupIdentifier(*self.__namespace__[1:])
            case "model":
                return ModelIdentifier(*self.__namespace__[1:])
            case _:
                raise NotImplementedError

    def __hash__(self) -> int:
        return hash(self.__namespace__)

    def __setattr__(self, name: str, value: Any) -> None:
        ensure(
            name.isidentifier(),  # KEEP AS IS
            ValueError,
            "Attribute name must be a valid identifier",
        )

        if name == "name" or (name.startswith("__") and name.endswith("__")):
            ensure(
                name in self.__slots__,
                AttributeError,
                f"Attribute '{name}' not in __slots__",
            )
            return object.__setattr__(self, name, value)

        virtual = object.__getattribute__(self, "__virtual__")

        if name in virtual:
            raise AttributeError(f"Cannot assign to virtual field '{name}'")

        newval = db_request(
            self,
            "insert",
            name,
            value,
            context=context(currentframe()),
        )

        # Update caches and track explicit assignment
        self.__field_cache__[name] = newval
        # Don't set baseline in __accessed_fields__ if we're in a context manager
        # The baseline will be set at context exit to capture any in-place changes
        if self.__contexts__ == 0:
            self.__accessed_fields__[name] = safe_deepcopy(newval)
        self.__explicitly_set__.add(name)
        # Track the originally assigned value to detect post-assignment modifications
        self.__assigned_values__[name] = safe_deepcopy(newval)

    def __guarded_return__(self, name: str, value: Any) -> Any:
        ensure(
            isinstance(value, IMMUTABLE_TYPES) or self.__contexts__ > 0,
            TypeError,
            f"This {repr(self)} must be wrapped in a context manager (use 'with') "
            f"because the field '{name}' is of a mutable type ({type(value).__name__}).",
        )

        return value

    def __getattribute__(self, name: str) -> Any:
        if name in ("name", "flush", "get") or (
            name.startswith("__") and name.endswith("__")
        ):
            return object.__getattribute__(self, name)

        accessed_fields = object.__getattribute__(self, "__accessed_fields__")
        field_cache = object.__getattribute__(self, "__field_cache__")
        virtual = object.__getattribute__(self, "__virtual__")

        if name in virtual:
            return virtual[name](self)

        # Check if we have a cached copy of this field
        if name in field_cache:
            return self.__guarded_return__(name, field_cache[name])

        try:
            value = db_request(self, "get", name)
            # Cache the value for consistent object identity
            field_cache[name] = value
            # For deep modification detection, store a copy of the original only on first access
            if name not in accessed_fields:
                accessed_fields[name] = safe_deepcopy(value)
            return self.__guarded_return__(name, value)
        except NameError as e:
            raise AttributeError(f"{self} has no .{name}") from e

    def __delattr__(self, name: str) -> None:
        db_request(self, "delete", name, None, context=context(currentframe()))
        self.__field_cache__.pop(name, None)
        self.__accessed_fields__.pop(name, None)
        self.__explicitly_set__.discard(name)
        self.__assigned_values__.pop(name, None)

    def __enter__(self) -> "Storage":
        self.__contexts__ += 1
        # Clear caches to ensure fresh values and baselines for this context
        self.__field_cache__.clear()
        self.__accessed_fields__.clear()
        self.__explicitly_set__.clear()
        self.__assigned_values__.clear()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> Literal[False]:
        if exc_type is None:
            self.flush()
            self.__contexts__ -= 1
        # Clear field cache when exiting context to ensure fresh values next time
        self.__field_cache__.clear()

        return False

    def flush(self) -> None:
        try:
            accessed_fields = object.__getattribute__(self, "__accessed_fields__")
            field_cache = object.__getattribute__(self, "__field_cache__")
            explicitly_set = object.__getattribute__(self, "__explicitly_set__")
            assigned_values = object.__getattribute__(self, "__assigned_values__")
        except AttributeError:
            return  # Object wasn't fully initialized

        # Check all fields in the cache (includes both accessed and explicitly set fields)
        all_fields = set(accessed_fields.keys()) | set(field_cache.keys())

        for field in all_fields:
            if field in field_cache:
                current_value = field_cache[field]
                original_value = accessed_fields.get(field)

                # For explicitly set fields, we need special handling
                if field in explicitly_set:
                    assigned_value = assigned_values.get(field)
                    # Only save if current value differs from the originally assigned value
                    if current_value != assigned_value:
                        # Save the modified value (post-assignment modification detected)
                        db_request(
                            self,
                            "insert",
                            field,
                            current_value,
                            context=context(currentframe()),
                        )
                    # Update baseline for explicitly set field
                    accessed_fields[field] = safe_deepcopy(current_value)
                    continue

                # For accessed-only fields, compare against original baseline
                if original_value is not None and current_value != original_value:
                    # Save the modified value for fields that were only accessed, not explicitly set
                    db_request(
                        self,
                        "insert",
                        field,
                        current_value,
                        context=context(currentframe()),
                    )
                    # Update our accessed_fields to the new baseline
                    accessed_fields[field] = safe_deepcopy(current_value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Storage):
            return False

        return cast(bool, self.__namespace__ == other.__namespace__)

    def __fields__(self) -> list[str]:
        return cast(list[str], db_request(self, "fields"))

    def __bool__(self) -> bool:
        return cast(bool, db_request(self, "has_fields"))

    def __history__(self) -> dict[str, list[Value]]:
        return cast(dict[str, list[Value]], db_request(self, "history"))

    def __repr__(self) -> str:
        if len(self.__namespace__) == 1:
            return f"{self.__namespace__[0].capitalize()}()"
        return f"{self.__namespace__[0].capitalize()}(*{repr(self.__namespace__[1:])})"

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return getattr(self, name)
        except AttributeError:
            return default


def Admin() -> Storage:
    return Storage("admin")


def Session(sname: Sessionname) -> Storage:
    return Storage("session", str(sname))


def Group(sname: Sessionname, gname: str) -> Storage:
    return Storage("group", str(sname), gname)


def Player(sname: Sessionname, uname: Username) -> Storage:
    return Storage("player", str(sname), str(uname))


def Model(sname: Sessionname, mname: str) -> Storage:
    return Storage("model", str(sname), mname)
