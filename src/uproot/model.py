# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import inspect
from builtins import all as pyall
from dataclasses import asdict
from functools import wraps
from typing import (
    Any,
    Callable,
    Iterator,
    Optional,
    TypeVar,
    cast,
)

from pydantic import Field, validate_call
from pydantic.dataclasses import dataclass as validated_dataclass

import uproot.core as c
import uproot.storage as s
from uproot.constraints import ensure
from uproot.flexibility import flexible
from uproot.types import (
    FrozenDottedDict,
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    SessionIdentifier,
)

E = TypeVar("E", bound="Entry")


class Entry(type):
    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Any:  # typing this gets too complicated
        annotations = namespace.get("__annotations__", {})

        if "time" not in annotations:
            annotations["time"] = Optional[float]
            namespace["time"] = Field(
                default_factory=lambda: None,
                exclude=True,
                repr=False,
            )

        namespace["__annotations__"] = annotations

        new_class = super().__new__(cls, name, bases, namespace)
        return validated_dataclass(
            new_class,  # type: ignore[arg-type]
            frozen=True,
        )  # this does not have arbitrary_types_allowed=True on purpose


@flexible
@validate_call
def create(session: SessionIdentifier, *, tag: Optional[str] = None) -> ModelIdentifier:
    with session() as s:
        mid = c.create_model(s, data=dict(tag=tag))

    return mid


@validate_call
def model(mid: ModelIdentifier) -> s.Storage:
    return mid()


@flexible
def autoadd(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Entry,
    **other_fields: Any,
) -> None:
    fill: dict[str, Any] = dict()

    for field, expected_type in entry_type.__annotations__.items():
        if inspect.isclass(expected_type) and issubclass(expected_type, Identifier):
            if expected_type == PlayerIdentifier:
                fill[field] = pid
            elif expected_type == SessionIdentifier:
                fill[field] = pid().session
            elif expected_type == GroupIdentifier:
                fill[field] = pid().group
            elif expected_type == ModelIdentifier:
                fill[field] = mid
            else:
                raise ValueError(f"Unexpected Identifier in model: {expected_type}")

    new_entry = entry_type(**(fill | other_fields))
    add(mid, new_entry)

    return new_entry


@validate_call
def add(
    mid: ModelIdentifier,
    entry: Any,
    as_is: bool = False,
) -> None:
    if hasattr(entry, "__is_pydantic_dataclass__"):
        entry_as_dict = asdict(entry)
        time_removable = (
            isinstance(type(entry), Entry) and entry_as_dict.get("time") is None
        )
    else:
        entry_as_dict = dict(entry)
        time_removable = False

    ensure(
        pyall((isinstance(k, str) and k.isidentifier()) for k in entry_as_dict.keys()),
        ValueError,
        (
            "Custom model entries must be convertable into dict[str, Any], with all "
            "keys being valid Python identifiers."
        ),
    )

    new_entry = {
        k: v
        for k, v in entry_as_dict.items()
        if k != "time" or as_is or not time_removable
    }

    with model(mid) as model_:
        setattr(
            model_,
            "entry",
            new_entry,
        )

    return new_entry


def _with_time(
    rawentry: dict[str, Any],
    time: Optional[float],
    as_type: Optional[Any] = None,
) -> Any:
    if as_type is None:
        as_type = FrozenDottedDict

    return as_type(**(dict(time=time) | rawentry))


def all(
    mid: ModelIdentifier,
    as_type: Optional[Any] = None,
) -> Iterator[Any]:
    if as_type is None:
        as_type = FrozenDottedDict

    with model(mid) as model_:
        for field, value in model_.__history__():
            if field == "entry" and not value.unavailable:
                d = cast(dict[str, Any], value.data)

                yield _with_time(d, value.time, as_type)


def _fits(
    entry_as_dict: dict[str, Any],
    predicate: Optional[Callable[..., bool]],
    predicates: dict[str, Any],
) -> bool:
    if predicate is not None:
        if not predicate(**entry_as_dict):
            return False

    for pk, pv in predicates.items():
        if pk not in entry_as_dict or entry_as_dict[pk] != pv:
            return False

    return True


def filter(
    mid: ModelIdentifier,
    _callable_predicate: Optional[Callable[..., bool]] = None,
    as_type: Optional[Any] = None,
    **predicates: Any,
) -> Iterator[Any]:
    if as_type is None:
        as_type = FrozenDottedDict

    with model(mid) as model_:
        for field, value in model_.__history__():
            if field == "entry" and not value.unavailable:
                d = cast(dict[str, Any], value.data)

                if _fits(
                    d,
                    _callable_predicate,
                    predicates,
                ):
                    yield _with_time(d, value.time, as_type)


def latest(
    mid: ModelIdentifier,
    as_type: Optional[Any] = None,
) -> Any:
    if as_type is None:
        as_type = FrozenDottedDict

    with model(mid) as model_:
        d = cast(dict[str, Any], model_.entry)

        return _with_time(d, None, as_type)


@validate_call
def get(
    mid: ModelIdentifier,
    field: str,
) -> Any:
    with model(mid) as model_:
        return getattr(model_, field)


@validate_call
def exists(mid: ModelIdentifier) -> bool:
    return bool(model(mid))


def without_time(fun: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(fun)
    def wrapper(time: Optional[float], **kwargs: Any) -> Any:
        return fun(**kwargs)

    return wrapper
