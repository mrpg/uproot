from functools import wraps
from inspect import signature
from typing import (
    Any,
    Callable,
    ParamSpec,
    Tuple,
    TypeAlias,
    TypeVar,
    Union,
    get_type_hints,
)

from uproot.storage import Storage
from uproot.types import PlayerIdentifier, SessionIdentifier

Player: TypeAlias = Storage
PlayerLike: TypeAlias = Union[Player, PlayerIdentifier]
Session: TypeAlias = Storage
SessionLike: TypeAlias = Union[Session, SessionIdentifier]

P1 = ParamSpec("P1")
P2 = ParamSpec("P2")
T = TypeVar("T")


class TypeRegistry:
    def __init__(self) -> None:
        self._equivalences: dict[type, Tuple[type, ...]] = {}
        self._converters: dict[Tuple[type, type], Callable[..., Any]] = {}

    def register_equivalence(
        self,
        *types: type,
        converters: dict[Tuple[type, type], Callable[..., Any]],
    ) -> None:
        for t in types:
            self._equivalences[t] = types
        for (from_type, to_type), converter in converters.items():
            self._converters[(from_type, to_type)] = converter

    def get_equivalent_types(self, target_type: type) -> Tuple[type, ...]:
        return self._equivalences.get(target_type, (target_type,))

    def convert(self, value: Any, from_type: type, to_type: type) -> Any:
        if from_type == to_type:
            return value
        converter = self._converters.get((from_type, to_type))
        if converter:
            return converter(value)
        raise TypeError(f"No converter from {from_type} to {to_type}")


_registry = TypeRegistry()


def to_player(p: Player | PlayerIdentifier) -> Player:
    if isinstance(p, Player):
        return p
    elif isinstance(p, PlayerIdentifier):
        return Player(p.sname, p.uname)
    else:
        raise TypeError


def to_pid(p: Player | PlayerIdentifier) -> PlayerIdentifier:
    if isinstance(p, PlayerIdentifier):
        return p
    elif isinstance(p, Player):
        return PlayerIdentifier(p.session.name, p.name)
    else:
        raise TypeError


def to_session(s: Session | SessionIdentifier) -> Session:
    if isinstance(s, Session):
        return s
    elif isinstance(s, SessionIdentifier):
        return Session(s.sname)
    else:
        raise TypeError


def to_sid(s: Session | SessionIdentifier) -> SessionIdentifier:
    if isinstance(s, SessionIdentifier):
        return s
    elif isinstance(s, Session):
        return SessionIdentifier(s.name)
    else:
        raise TypeError


_registry.register_equivalence(
    Player,
    PlayerIdentifier,
    converters={
        (Player, PlayerIdentifier): to_pid,
        (PlayerIdentifier, Player): to_player,
    },
)

_registry.register_equivalence(
    Session,
    SessionIdentifier,
    converters={
        (Session, SessionIdentifier): to_sid,
        (SessionIdentifier, Session): to_session,
    },
)


def flexible(func: Callable[P1, T]) -> Callable[P2, T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        sig = signature(func)
        hints = get_type_hints(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()

        for param_name, value in bound.arguments.items():
            if param_name in hints:
                expected_type = hints[param_name]
                equivalent_types = _registry.get_equivalent_types(expected_type)

                if len(equivalent_types) > 1:
                    value_type = type(value)
                    if value_type in equivalent_types and value_type != expected_type:
                        bound.arguments[param_name] = _registry.convert(
                            value, value_type, expected_type
                        )
                    elif value_type not in equivalent_types:
                        raise TypeError(
                            f"Parameter {param_name} must be one of {equivalent_types}"
                        )

        return func(*bound.args, **bound.kwargs)

    return wrapper


def is_player_like(obj: Any) -> bool:
    return isinstance(obj, PlayerIdentifier) or (
        isinstance(obj, Storage) and obj.__trail__[0] == "player"
    )


def is_session_like(obj: Any) -> bool:
    return isinstance(obj, SessionIdentifier) or (
        isinstance(obj, Storage) and obj.__trail__[0] == "session"
    )
