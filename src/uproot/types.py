# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import asyncio
import functools
import hashlib
import inspect
import random
from abc import ABC, abstractmethod
from collections import namedtuple
from string import ascii_lowercase, digits
from time import perf_counter as now
from time import time
from types import FrameType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Iterator,
    Literal,
    NamedTuple,
    Never,
    Optional,
    TypeAlias,
    TypeVar,
    Union,
    cast,
    overload,
)
from uuid import uuid4

from pydantic import validate_call
from pydantic.dataclasses import dataclass as validated_dataclass

from uproot.constraints import ensure
from uproot.queries import Comparison, FieldReferent

ALPHANUMERIC: str = ascii_lowercase + digits
TOKEN_SPARSITY: float = 1_000_000

if TYPE_CHECKING:
    from uproot.storage import Storage

T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

MaybeAwaitable: TypeAlias = Union[T, Awaitable[T]]
Sessionname: TypeAlias = str
Username: TypeAlias = str
PageLike: TypeAlias = Union[type["Page"], "SmoothOperator"]
PlayerType: TypeAlias = Annotated["Storage", "Player"]
Bunch: TypeAlias = list["PlayerIdentifier"]


class FrozenDottedDict(dict[str, V]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    def __setitem__(self, key: str, value: Any) -> Never:
        raise TypeError("FrozenDottedDict does not support item assignment")

    def __setattr__(self, name: str, value: Any) -> Never:
        raise TypeError("FrozenDottedDict does not support attribute assignment")

    def __delitem__(self, key: str) -> Never:
        raise TypeError("FrozenDottedDict does not support item deletion")

    def __delattr__(self, name: str) -> Never:
        raise TypeError("FrozenDottedDict does not support attribute deletion")

    def __getattr__(self, name: str) -> V:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{name}'"
            )

    def clear(self) -> Never:
        raise TypeError("FrozenDottedDict does not support clear()")

    def pop(self, *args: Any) -> Never:
        raise TypeError("FrozenDottedDict does not support pop()")

    def popitem(self) -> Never:
        raise TypeError("FrozenDottedDict does not support popitem()")

    def setdefault(self, *args: Any) -> Never:
        raise TypeError("FrozenDottedDict does not support setdefault()")

    def update(self, *args: Any, **kwargs: Any) -> Never:
        raise TypeError("FrozenDottedDict does not support update()")


@validated_dataclass(frozen=True)
class Value:
    time: Optional[float] = None
    unavailable: bool = True
    data: Optional[Any] = None
    context: str = ""


class Identifier(ABC):
    @abstractmethod
    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError

    def __str__(self) -> str:
        return "/".join([*self])


@validated_dataclass(frozen=True)
class SessionIdentifier(str, Identifier):
    sname: Sessionname

    def __iter__(self) -> Iterator[str]:
        yield from (self.sname,)

    def __call__(self, **kwargs: Any) -> "Storage":
        from uproot.storage import Session

        return Session(*self, **kwargs)


@validated_dataclass(frozen=True)
class PlayerIdentifier(Identifier):
    sname: Sessionname
    uname: Username

    def __iter__(self) -> Iterator[str]:
        yield from (self.sname, self.uname)

    def __call__(self, **kwargs: Any) -> "Storage":
        from uproot.storage import Player

        return Player(*self, **kwargs)


@validated_dataclass(frozen=True)
class GroupIdentifier(Identifier):
    sname: Sessionname
    gname: str

    def __iter__(self) -> Iterator[str]:
        yield from (self.sname, self.gname)

    def __call__(self, **kwargs: Any) -> "Storage":
        from uproot.storage import Group

        return Group(self.sname, self.gname, **kwargs)


@validated_dataclass(frozen=True)
class ModelIdentifier(Identifier):
    sname: Sessionname
    mname: str

    def __iter__(self) -> Iterator[str]:
        yield from (self.sname, self.mname)

    def __call__(self, **kwargs: Any) -> "Storage":
        from uproot.storage import Model

        return Model(self.sname, self.mname, **kwargs)


async def maybe_await(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    result = func(*args, **kwargs)

    if inspect.iscoroutine(result):
        return await result

    return result


def optional_call(
    obj: Any,
    attr: str,
    *,
    default_return: Optional[Any] = None,
    **kwargs: Any,
) -> Any | None:
    if hasattr(obj, attr):
        attr_ = getattr(obj, attr)
    else:
        return default_return

    if callable(attr_):
        return attr_(**kwargs)
    else:
        return attr_


def optional_call_once(
    obj: Any,
    attr: str,
    default_return: Optional[Any] = None,
    *,
    storage: "Storage",
    show_page: int,
    **kwargs: Any,
) -> Any | None:
    if not hasattr(obj, attr):
        return default_return  # short circuit

    hereruns = f"{show_page}:{attr}"

    if not hasattr(storage, "_uproot_what_ran"):
        storage._uproot_what_ran = set()

    if hereruns in storage._uproot_what_ran:
        return default_return

    storage._uproot_what_ran.add(hereruns)

    try:
        return optional_call(obj, attr, default_return=default_return, **kwargs)
    except Exception as e:
        storage._uproot_what_ran.remove(hereruns)

        raise e


class StorageBunch:
    def __init__(self, iterable: Iterable["Storage"] = ()) -> None:
        ensure(
            all(hasattr(item, "__namespace__") for item in iterable),
            TypeError,
            "All items must have __namespace__ attribute",
        )

        self.l = tuple(iterable)
        self.s = set(self.l)

    def __len__(self) -> int:
        return len(self.l)

    def __iter__(self) -> Iterator["Storage"]:
        return iter(self.l)

    def __contains__(self, item: "Storage") -> bool:
        return item in self.s

    def __getitem__(self, ix: int) -> "Storage":
        return self.l[ix]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StorageBunch):
            return False
        if len(self.l) != len(other.l):
            return False

        return self.s == other.s

    def filter(self, *comparisons: Comparison | FieldReferent) -> "StorageBunch":
        result = []

        for p in self.l:
            g = True

            for comparison in comparisons:
                if isinstance(comparison, Comparison) or isinstance(
                    comparison, FieldReferent
                ):
                    g = comparison(p)
                else:
                    raise ValueError

                if not g:
                    break

            if g:
                result.append(p)

        return StorageBunch(result)

    def assign(self, key: str, values: Iterable[Any]) -> None:
        for p, val in zip(self, values):
            setattr(p, key, val)

    @overload
    def each(
        self, *keys: str | FieldReferent, simplify: Literal[True] = True
    ) -> list[Any]: ...

    @overload
    def each(
        self, *keys: str | FieldReferent, simplify: Literal[False]
    ) -> list[NamedTuple]: ...

    def each(
        self, *keys: str | FieldReferent, simplify: bool = True
    ) -> Union[list[Any], list[NamedTuple]]:
        rkeys: list[str] = []

        for k in keys:
            if isinstance(k, str):
                ensure("." not in k, ValueError, "Key cannot contain dots")
                rkeys.append(k)
            elif isinstance(k, FieldReferent):
                ensure(
                    len(k.path) == 1,
                    ValueError,
                    "FieldReferent path must have exactly one element",
                )
                rkeys.append(k.path[-1])

        dtuple = cast(type[NamedTuple], namedtuple("data", rkeys))
        rval = [dtuple(**{k: getattr(p, k) for k in rkeys}) for p in self.l]  # type: ignore[call-overload]

        if len(rkeys) == 1 and simplify:
            return [v for (v,) in rval]

        return rval

    def apply(
        self,
        fun: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Union[list[Any], Awaitable[list[Any]]]:
        if inspect.iscoroutinefunction(fun):
            return asyncio.gather(*[fun(p, *args, **kwargs) for p in self.l])
        else:
            return [fun(p, *args, **kwargs) for p in self.l]


def noop(s: str) -> str:
    return s


def token_unchecked(outlen: int) -> str:
    """This function generates a random Python identifier."""
    ensure(outlen > 0, ValueError, "Output length must be positive")

    return random.choice(ascii_lowercase) + "".join(
        random.choices(ALPHANUMERIC, k=outlen - 1)
    )


def token(
    not_in: Collection[str] | Bunch, postprocess: Callable[[str], str] = noop
) -> str:
    if not_in and isinstance(not_in, list) and isinstance(not_in[0], PlayerIdentifier):
        not_in = cast(Bunch, not_in)
        not_in = [el.uname for el in not_in]

    ensure(
        not not_in or not isinstance(not_in, list) or type(not_in[0]) is str,
        TypeError,
        "Argument has invalid type",
    )

    length = 5
    acc = int((len(ascii_lowercase) * len(ALPHANUMERIC) ** length) / TOKEN_SPARSITY)

    while len(not_in) >= acc:
        length += 1
        acc += int(
            (len(ascii_lowercase) * len(ALPHANUMERIC) ** length) / TOKEN_SPARSITY
        )

    while True:
        token_str = postprocess(token_unchecked(length))

        if token_str not in not_in:
            return token_str


@validate_call
def tokens(not_in: list[str] | Bunch, n: int) -> list[str]:
    if not_in and isinstance(not_in[0], PlayerIdentifier):
        not_in = cast(Bunch, not_in)
        not_in = [el.uname for el in not_in]

    rval: list[str] = list()

    for _ in range(n):
        t = None

        while t is None or t in rval:
            t = token(not_in)

        rval.append(t)

    return rval


def sha256(b: str | bytes) -> str:
    if isinstance(b, str):
        b = b.encode("utf-8")

    return hashlib.sha256(b).hexdigest()


def uuid() -> str:
    return str(uuid4())


def longest_common_prefix(strings: list[str]) -> str:
    if not strings:
        return ""

    for i in range(len(strings[0])):
        char = strings[0][i]
        for string in strings[1:]:
            if i >= len(string) or string[i] != char:
                return strings[0][:i]

    return strings[0]


class FrozenPage(type):
    def __new__(
        cls: type["FrozenPage"],
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
    ) -> type:
        for attr_name, attr_value in namespace.items():
            if (
                callable(attr_value)
                and not attr_name.startswith("__")
                and not isinstance(attr_value, classmethod)
            ):
                raise TypeError(f"Method {name}.{attr_name} must be a @classmethod")

            if attr_name in (
                "all_here",
                "after_grouping",
            ) and inspect.iscoroutinefunction(attr_value):
                raise TypeError(f"Method {name}.{attr_name} must not be async")

        return super().__new__(cls, name, bases, namespace)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            "In uproot, Pages are immutable. Remember to separate code and data."
        )

    def __delattr__(self, name: str) -> None:
        raise AttributeError(
            "In uproot, Pages are immutable. Remember to separate code and data."
        )


class Page(metaclass=FrozenPage):
    allow_back: bool = False
    template: str

    # ideally, the following attributes should have types like
    #    show: Union[bool, classmethod[type["Page"], [PlayerType], MaybeAwaitable[bool]]]
    # but that does not yet work
    # in fact, not even
    #    show: Union[bool, Any]
    # works! NO BUENO!

    after_always_once: Any
    after_once: Any
    before_always_once: Any
    before_once: Any
    context: Any
    fields: Any
    handle_stealth_fields: Any
    jsvars: Any
    may_proceed: Any
    show: Any
    stealth_fields: Any
    timeout: Any
    timeout_reached: Any
    validate: Any

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise AttributeError("Pages are not meant to be instantiated.")

    @classmethod
    async def set_timeout(page: type["Page"], player: "Storage") -> Optional[float]:
        to_sec = cast(
            Optional[float],
            await maybe_await(
                optional_call, page, "timeout", default_return=None, player=player
            ),
        )

        if to_sec is None:
            return None

        if str(player.show_page) in player._uproot_timeouts_until:
            return cast(
                float,
                max(0.0, player._uproot_timeouts_until[str(player.show_page)] - time()),
            )
        else:
            player._uproot_timeouts_until[str(player.show_page)] = time() + to_sec

            return to_sec


def timed(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(func)  # Preserves metadata
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        t0 = now()
        result = await func(*args, **kwargs)

        if (t := now() - t0) > 0.01:
            import uproot.deployment as d

            d.LOGGER.warning(
                f"{func.__module__}.{func.__name__} is slow (took {t:.3f} seconds)"
            )

        return result

    return wrapper


def internal_live(method: Callable[..., Any]) -> Callable[..., Any]:
    wrapped = timed(validate_call(method, config=dict(arbitrary_types_allowed=True)))  # type: ignore[call-overload]
    newmethod = classmethod(wrapped)

    newmethod.__func__.__live__ = True  # type: ignore[attr-defined]

    return newmethod  # type: ignore[return-value]


def context(frame: FrameType | None) -> str:
    try:
        if frame is None:
            return "<unknown>"

        caller_frame = frame.f_back
        if caller_frame is None:
            return "<unknown>"

        caller_function = caller_frame.f_code.co_name
        caller_lineno = caller_frame.f_lineno

        caller_module = inspect.getmodule(caller_frame)
        module_name = caller_module.__name__ if caller_module else "<unknown>"

        return f"{module_name}.{caller_function}:{caller_lineno}"
    except Exception:
        return "<unknown>"


class NoshowPage(Page):
    @classmethod
    async def show(page, player: "Storage") -> bool:
        return False


class InternalPage(NoshowPage):
    pass


class GroupCreatingWait(InternalPage):
    group_size: int
    template = "GroupCreatingWait.html"

    after_grouping: Any

    @classmethod
    async def show(page, player: "Storage") -> bool:
        # Already in a group - don't show page
        if page.call_after(player):
            return False

        # Try to create a group immediately
        from uproot.jobs import try_group

        try_group(player, player.show_page, page.group_size)

        # If grouping succeeded, player now has a group - don't show page
        if page.call_after(player):
            return False

        # Need to wait for more players
        return True

    @internal_live
    async def please_group(page, player: Any) -> tuple[str, float]:
        # Check group status after any potential await points
        if player._uproot_group is not None:
            return "submit", 1

        from uproot.jobs import here, try_group

        # Always try to create a group
        try_group(player, player.show_page, page.group_size)

        # Re-check group status after grouping attempt
        if page.call_after(player):
            return "submit", 1

        # Get fresh count for progress display
        all_here = here(player._uproot_session, player.show_page)
        ungrouped_count = 0

        for pid in all_here:
            cgroup = None

            if pid == ~player:
                cgroup = player._uproot_group
            else:
                with pid() as player_:
                    cgroup = player_._uproot_group

            if cgroup is None:
                ungrouped_count += 1

        return "wait", ungrouped_count / page.group_size

    @classmethod
    async def may_proceed(page, player: "Storage") -> bool:
        return page.call_after(player)

    @classmethod
    def call_after(page, player: "Storage") -> bool:
        if player._uproot_group is not None:
            group = player.group

            with group:
                optional_call_once(
                    page,
                    "after_grouping",
                    storage=group,
                    show_page=player.show_page,
                    group=group,
                )

            # This works because all_here and after_grouping must not be async

            return True
        else:
            return False


class SynchronizingWait(InternalPage):
    template = "SynchronizingWait.html"
    synchronize = "group"

    all_here: Any

    @classmethod
    async def show(page, player: "Storage") -> bool:
        return True

    @classmethod
    def wait_for(page, player: "Storage") -> list[PlayerIdentifier]:
        if page.synchronize == "group":
            s = player.group
        elif page.synchronize == "session":
            s = player.session
        else:
            raise NotImplementedError

        with s:
            return cast(list[PlayerIdentifier], s.players)

    @internal_live
    async def wait(page, player: Any) -> tuple[str, float]:
        from uproot.jobs import here

        wf = page.wait_for(player)
        # For synchronization, allow players who have advanced past this page (strict=False)
        h = here(player._uproot_session, player.show_page, wf, False)

        if len(h) == len(wf):
            return "submit", 1
        else:
            return "wait", len(h) / len(wf)

    @classmethod
    async def may_proceed(page, player: "Storage") -> bool:
        # Use fresh wait check instead of potentially stale frontend data
        from uproot.jobs import here

        wf = page.wait_for(player)
        # For synchronization, allow players who have advanced past this page (strict=False)
        h = here(player._uproot_session, player.show_page, wf, False)

        # All required players must be here or advanced
        if len(h) < len(wf):
            return False

        if page.synchronize == "group":
            group = player._uproot_group()

            with group:
                await maybe_await(
                    optional_call_once,
                    page,
                    "all_here",
                    storage=group,
                    show_page=player.show_page,
                    group=group,
                )
        elif page.synchronize == "session":
            session = player.session

            with session:
                await maybe_await(
                    optional_call_once,
                    page,
                    "all_here",
                    storage=session,
                    show_page=player.show_page,
                    session=session,
                )
        else:
            raise NotImplementedError

        return True


class SmoothOperator(ABC):
    @abstractmethod
    def __init__(self, *pages: "PageLike") -> None:
        self.pages: list["PageLike"] = list(pages)

    @abstractmethod
    def expand(self) -> list["PageLike"]:
        return self.pages


def vertical(matrix: Iterable[Any]) -> Iterator[list[Any]]:
    """This function transposes matrix. Useful for 'vertical' unpacking."""
    return map(list, zip(*matrix))


class Pulse(asyncio.Event):
    "An asyncio.Event that immediately unsets. May carry associated data."

    def set(self, data: Any = None) -> None:
        self._data = data

        super().set()
        super().clear()

    async def wait(self) -> Any:
        await super().wait()

        return self._data

    def is_set(self) -> bool:
        return False
