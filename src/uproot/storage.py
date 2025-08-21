# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import copy
import heapq
import threading
from inspect import currentframe
from time import time
from typing import Any, Callable, Iterator, Optional, Union, cast

from typing_extensions import Literal

from uproot.deployment import DATABASE
from uproot.stable import IMMUTABLE_TYPES
from uproot.types import (
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    RawValue,
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
CACHE_ENABLED: bool = True
PATH_CACHE: dict[str, Any] = dict()
MAX_CACHE_SIZE = 4096
_cache_access_counter = 0
_cache_heap: list[tuple[int, str]] = []
_cache_latest_access: dict[str, int] = {}
_heap_cleanup_threshold = MAX_CACHE_SIZE * 3
_cache_lock = threading.RLock()


def _cleanup_heap() -> None:
    global _cache_heap, _cache_latest_access

    valid_entries = [
        (access_time, path)
        for access_time, path in _cache_heap
        if path in PATH_CACHE and _cache_latest_access.get(path, 0) == access_time
    ]

    _cache_heap = valid_entries
    heapq.heapify(_cache_heap)


def _evict_lru() -> None:
    global _cache_access_counter, _cache_heap, _cache_latest_access

    if len(_cache_heap) > _heap_cleanup_threshold:
        _cleanup_heap()

    while len(PATH_CACHE) >= MAX_CACHE_SIZE and _cache_heap:
        access_time, path = heapq.heappop(_cache_heap)
        if path in PATH_CACHE and _cache_latest_access.get(path, 0) == access_time:
            PATH_CACHE.pop(path, None)
            _cache_latest_access.pop(path, None)


def _touch_cache(path: str) -> None:
    global _cache_access_counter, _cache_heap, _cache_latest_access

    _cache_access_counter += 1
    _cache_latest_access[path] = _cache_access_counter
    heapq.heappush(_cache_heap, (_cache_access_counter, path))


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
            tuple[str, float],
            dict[str, Any],
        ]
    ] = None,
) -> Any:
    assert key == "" or key.isidentifier()
    rval = None

    if caller is not None:
        namespace = caller.__path__
        dbfield = f"{namespace}:{key}"

    DATABASE.now = time()

    match action, key, value:
        # WRITE-ONLY
        case "insert", _, _ if isinstance(context, str):
            DATABASE.insert(dbfield, value, context)
            rval = value
        case "delete", _, None if isinstance(context, str):
            DATABASE.delete(dbfield, context)

        # READ-ONLY - USE DBFIELD
        case "get", _, None:
            rval = DATABASE.get(dbfield)
        case "get_field_history", _, None:
            rval = DATABASE.get_field_history(namespace, key)
        case "fields", "", None:
            rval = DATABASE.fields(dbfield)
        case "has_fields", "", None:
            rval = DATABASE.has_fields(dbfield)
        case "history", "", None:
            rval = DATABASE.history(dbfield)

        # READ-ONLY - SPECIAL
        case "get_field_all_namespaces", "", None if isinstance(extra, str):
            mkey: str

            mkey = extra
            rval = DATABASE.get_field_all_namespaces(mkey)
        case "get_many", "", None if isinstance(extra, tuple):
            mpaths: list[str]

            mpaths, mkey = cast(tuple[list[str], str], extra)
            rval = DATABASE.get_many(mpaths, mkey)
        case "get_latest", "", None if isinstance(extra, tuple):
            mpath: str
            since: float

            mpath, since = cast(tuple[str, float], extra)
            rval = DATABASE.get_latest(mpath, since)
        case "history_all", "", None if isinstance(extra, str):
            mpathstart: str

            mpathstart = extra
            rval = DATABASE.history_all(mpathstart)
        case "history_raw", "", None if isinstance(extra, str):
            mpathstart = extra
            rval = DATABASE.history_raw(mpathstart)
        case "get_within_context", _, None if isinstance(extra, dict):
            context_fields: dict[str, Any]

            context_fields = extra
            rval = DATABASE.get_within_context(namespace, context_fields, key)

        # ERROR
        case _, _, _:
            raise NotImplementedError

    return rval


def mkpath(*trail: str) -> str:
    return "/".join(trail)


def mktrail(path: str) -> tuple[str, ...]:
    # TODO: this function is a misnomer
    main, last = path.split(":")
    return tuple(main.split("/") + [last])


def field_from_paths(paths: list[str], field: str) -> dict[tuple[str, str], Value]:
    return cast(
        dict[str, Value],
        db_request(
            None,
            "get_many",
            extra=(paths, field),
        ),
    )


def all_good(dbfield: str) -> bool:
    return True


def field_from_all(
    field: str, predicate: Callable[[str], bool] = all_good
) -> dict[str, Value]:
    def predicate_(dbfield: str) -> bool:
        try:
            return predicate(dbfield)
        except Exception:
            return False

    return {
        k: v
        for k, v in cast(
            dict[str, Value],
            db_request(
                None,
                "get_field_all_namespaces",
                extra=field,
            ),
        ).items()
        if predicate_(k)
    }


def fields_from_session(sname: Sessionname, since_epoch: float = 0) -> dict[str, Value]:
    return cast(
        dict[str, Value],
        db_request(
            None,
            "get_latest",
            extra=(f"player/{sname}/", since_epoch),
        ),
    )


def history_all(mpathstart: str) -> Iterator[tuple[str, str, Value]]:
    return cast(
        Iterator[tuple[str, str, Value]],
        db_request(
            None,
            "history_all",
            extra=mpathstart,
        ),
    )


def history_raw(mpathstart: str) -> Iterator[tuple[str, str, RawValue]]:
    return cast(
        Iterator[tuple[str, str, RawValue]],
        db_request(
            None,
            "history_raw",
            extra=mpathstart,
        ),
    )


def _safe_deepcopy(value: Any) -> Any:
    if isinstance(value, IMMUTABLE_TYPES):
        return value

    return copy.deepcopy(value)


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
        "__allow_mutable__",
        "_cache_ref",
        "name",
        "__path__",
        "__trail__",
        "__virtual__",
        "__weakref__",
    )

    def __init__(
        self,
        *trail: str,
        virtual: Optional[dict[str, Callable[["Storage"], Any]]] = None,
    ):
        assert all(
            t.isidentifier() for t in trail
        ), f"{repr(trail)} has invalid identifiers"
        assert trail[0] in VALID_TRAIL0

        object.__setattr__(self, "name", trail[-1])
        object.__setattr__(self, "__path__", mkpath(*trail))
        object.__setattr__(self, "__trail__", trail)
        object.__setattr__(self, "__allow_mutable__", False)
        object.__setattr__(self, "__accessed_fields__", dict())
        object.__setattr__(self, "__virtual__", virtual or DEFAULT_VIRTUAL)

        path = self.__path__
        with _cache_lock:
            if path not in PATH_CACHE:
                _evict_lru()
                PATH_CACHE[path] = dict()
                _touch_cache(path)

            cache_ref = PATH_CACHE[path]

        object.__setattr__(self, "_cache_ref", cache_ref)

    def __invert__(self) -> Identifier:
        match self.__trail__[0]:
            case "session":
                return SessionIdentifier(*self.__trail__[1:])
            case "player":
                return PlayerIdentifier(*self.__trail__[1:])
            case "group":
                return GroupIdentifier(*self.__trail__[1:])
            case "model":
                return ModelIdentifier(*self.__trail__[1:])
            case _:
                raise NotImplementedError

    def __hash__(self) -> int:
        return hash(self.__trail__)

    def __setattr__(self, name: str, value: Any) -> None:
        assert name.isidentifier()

        if name == "name" or (name.startswith("__") and name.endswith("__")):
            assert name in self.__slots__
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

        self._cache_ref[name] = newval
        self.__accessed_fields__[name] = _safe_deepcopy(newval)

    def __guarded_return__(self, value: Any) -> Any:
        if isinstance(value, IMMUTABLE_TYPES) or self.__allow_mutable__:
            return value
        else:
            raise ValueError(
                f"This {repr(self)} must be wrapped in a context manager (use 'with')."
            )

    def __getattribute__(self, name: str) -> Any:
        if name in ("name", "_cache_ref", "flush", "get") or (
            name.startswith("__") and name.endswith("__")
        ):
            return object.__getattribute__(self, name)

        cache_ref = object.__getattribute__(self, "_cache_ref")
        accessed_fields = object.__getattribute__(self, "__accessed_fields__")
        virtual = object.__getattribute__(self, "__virtual__")

        if name in virtual:
            return virtual[name](self)

        if name in cache_ref and CACHE_ENABLED:
            if name not in accessed_fields:
                accessed_fields[name] = _safe_deepcopy(cache_ref[name])

            return self.__guarded_return__(cache_ref[name])

        try:
            value = db_request(self, "get", name)
            cache_ref[name] = value
            accessed_fields[name] = _safe_deepcopy(value)

            return self.__guarded_return__(value)
        except NameError as e:
            raise AttributeError(f"{self} has no .{name}") from e

    def __delattr__(self, name: str) -> None:
        db_request(self, "delete", name, None, context=context(currentframe()))
        self._cache_ref.pop(name, None)
        self.__accessed_fields__.pop(name, None)

    def __enter__(self) -> "Storage":
        self.__allow_mutable__ = True

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:  # type: ignore[no-untyped-def]
        if exc_type is None:
            self.flush()
            self.__allow_mutable__ = False

        return False

    def flush(self) -> None:
        try:
            cache_ref = object.__getattribute__(self, "_cache_ref")
            accessed_fields = object.__getattribute__(self, "__accessed_fields__")
        except AttributeError:
            return  # Object wasn't fully initialized

        for field, original_value in accessed_fields.items():
            if field in cache_ref and cache_ref[field] != original_value:
                db_request(
                    self,
                    "insert",
                    field,
                    cache_ref[field],
                    context=context(currentframe()),
                )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Storage):
            return False

        return cast(bool, self.__path__ == other.__path__)

    def __fields__(self) -> list[str]:
        return cast(list[str], db_request(self, "fields"))

    def __bool__(self) -> bool:
        return cast(bool, db_request(self, "has_fields"))

    def __history__(self) -> Iterator[tuple[str, Value]]:
        return cast(Iterator[tuple[str, Value]], db_request(self, "history"))

    def __repr__(self) -> str:
        if len(self.__trail__) == 1:
            return f"{self.__trail__[0].capitalize()}()"
        return f"{self.__trail__[0].capitalize()}(*{repr(self.__trail__[1:])})"

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return getattr(self, name)
        except AttributeError:
            return default


def Admin() -> Storage:
    return Storage("admin")


def Session(sname: Sessionname) -> Storage:
    return Storage("session", sname)


def Group(sname: Sessionname, gname: str) -> Storage:
    return Storage("group", sname, gname)


def Player(sname: Sessionname, uname: Username) -> Storage:
    return Storage("player", sname, uname)


def Model(sname: Sessionname, mname: str) -> Storage:
    return Storage("model", sname, mname)
