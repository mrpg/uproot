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
    Type,
    TypeVar,
    Union,
    cast,
    overload,
)

from pydantic import Field, validate_call
from pydantic.dataclasses import dataclass as validated_dataclass

import uproot.core as c
import uproot.storage as s
from uproot.flexibility import flexible
from uproot.types import (
    FrozenDottedDict,
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    SessionIdentifier,
)

E = TypeVar("E")
T = TypeVar("T")
EntryType = TypeVar("EntryType")


class Entry(type):
    """
    Metaclass for model entries. Automatically adds time field and creates
    immutable pydantic dataclasses.
    """

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Type[Any]:
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
def create_model(
    session: SessionIdentifier, *, tag: Optional[str] = None
) -> ModelIdentifier:
    """
    Create a new model in the given session.

    Args:
        session: The session identifier to create the model in
        tag: Optional tag for the model

    Returns:
        The identifier of the newly created model

    Raises:
        RuntimeError: If model creation fails
    """
    try:
        with session() as s:
            mid = c.create_model(s, data=dict(tag=tag))
        return mid
    except Exception as e:
        raise RuntimeError(f"Failed to create model: {e}") from e


def get_storage(mid: ModelIdentifier) -> s.Storage:
    """
    Get the storage instance for a model.

    Args:
        mid: The model identifier

    Returns:
        The storage instance

    Raises:
        ValueError: If model doesn't exist or access fails
    """
    try:
        storage = mid()
        if not storage:
            raise ValueError(f"Model {mid} not found")
        return storage
    except Exception as e:
        raise ValueError(f"Failed to access model {mid}: {e}") from e


@flexible
@validate_call
def auto_add_entry(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Any,
    **other_fields: Any,
) -> Any:
    """
    Automatically create and add an entry with auto-filled identifier fields.

    Args:
        mid: The model identifier to add the entry to
        pid: The player identifier for auto-filling
        entry_type: The entry class to create
        **other_fields: Additional fields to set on the entry

    Returns:
        The created entry instance

    Raises:
        ValueError: If entry creation fails
        RuntimeError: If adding to model fails
    """
    try:
        auto_fields: dict[str, Any] = {}

        # Auto-fill identifier fields based on type annotations
        for field_name, field_type in getattr(
            entry_type, "__annotations__", {}
        ).items():
            if inspect.isclass(field_type) and issubclass(field_type, Identifier):
                if field_type == PlayerIdentifier:
                    auto_fields[field_name] = pid
                elif field_type == SessionIdentifier:
                    with pid() as player:
                        auto_fields[field_name] = player.session
                elif field_type == GroupIdentifier:
                    with pid() as player:
                        auto_fields[field_name] = player.group
                elif field_type == ModelIdentifier:
                    auto_fields[field_name] = mid
                else:
                    raise ValueError(f"Unsupported identifier type: {field_type}")

        # Merge auto-filled and user-provided fields
        all_fields = auto_fields | other_fields

        # Create the entry instance
        new_entry = entry_type(**all_fields)

        # Add it to the model
        add_raw_entry(mid, new_entry)

        return new_entry

    except Exception as e:
        raise ValueError(f"Failed to auto-add entry: {e}") from e


@overload
def add_entry(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Any,
    **other_fields: Any,
) -> Any:
    """Auto-fill identifiers and add entry."""
    ...


@overload
def add_entry(
    mid: ModelIdentifier,
    entry: Union[dict[str, Any], Any],
    *,
    preserve_time: bool = False,
) -> None:
    """Add raw entry without auto-filling."""
    ...


def add_entry(
    mid: ModelIdentifier,
    pid_or_entry: Union[PlayerIdentifier, dict[str, Any], Any],
    entry_type_or_preserve_time: Union[Any, bool] = False,
    **other_fields_or_kwargs: Any,
) -> Union[Any, None]:
    """
    Add an entry to the model with smart auto-filling behavior.

    This function has two modes:

    1. Auto-filling mode (recommended):
       add_entry(model_id, player_id, EntryClass, field1=value1, field2=value2)
       - Automatically fills identifier fields based on type annotations
       - Returns the created entry instance

    2. Raw mode (for advanced use):
       add_entry(model_id, entry_instance_or_dict, preserve_time=False)
       - Adds entry as-is without auto-filling
       - Returns None

    Args:
        mid: The model identifier
        pid_or_entry: PlayerIdentifier (auto mode) or entry instance/dict (raw mode)
        entry_type_or_preserve_time: Entry class (auto mode) or preserve_time flag (raw mode)
        **other_fields_or_kwargs: Field values (auto mode) or additional kwargs (raw mode)

    Returns:
        Created entry instance in auto mode, None in raw mode

    Raises:
        ValueError: If entry creation or adding fails

    Examples:
        # Auto-filling mode (recommended)
        offer = add_entry(model_id, player_id, Offer, price=100.0, quantity=5)

        # Raw mode (advanced)
        add_entry(model_id, Offer(pid=player_id, price=100.0), preserve_time=True)
    """
    # Detect which mode we're in based on the second argument
    if isinstance(pid_or_entry, PlayerIdentifier):
        # Auto-filling mode: pid_or_entry is PlayerIdentifier, entry_type_or_preserve_time is Type
        return auto_add_entry(
            mid,
            pid_or_entry,
            entry_type_or_preserve_time,  # type: ignore
            **other_fields_or_kwargs,
        )
    else:
        # Raw mode: pid_or_entry is the entry, entry_type_or_preserve_time might be preserve_time
        preserve_time = (
            bool(entry_type_or_preserve_time)
            if isinstance(entry_type_or_preserve_time, bool)
            else False
        )
        add_raw_entry(mid, pid_or_entry, preserve_time=preserve_time)
        return None


@validate_call
def add_raw_entry(
    mid: ModelIdentifier,
    entry: Union[dict[str, Any], Any],
    *,
    preserve_time: bool = False,
) -> None:
    """
    Add a raw entry to the model without auto-filling identifier fields.

    Use this when you need direct control over all fields or when adding
    non-Entry objects (like plain dicts).

    Args:
        mid: The model identifier to add the entry to
        entry: The entry to add (dataclass instance or dict)
        preserve_time: Whether to preserve the time field if present

    Raises:
        ValueError: If entry format is invalid or adding to model fails
    """
    try:
        # Convert entry to dict format
        if hasattr(entry, "__is_pydantic_dataclass__"):
            entry_dict = asdict(entry)
            is_entry_instance = isinstance(type(entry), Entry)
            time_should_be_removed = (
                is_entry_instance
                and entry_dict.get("time") is None
                and not preserve_time
            )
        else:
            entry_dict = dict(entry) if not isinstance(entry, dict) else entry
            time_should_be_removed = False

        # Validate entry structure
        if not pyall(
            isinstance(k, str) and k.isidentifier() for k in entry_dict.keys()
        ):
            invalid_keys = [
                k
                for k in entry_dict.keys()
                if not (isinstance(k, str) and k.isidentifier())
            ]
            raise ValueError(
                f"Entry keys must be valid Python identifiers. Invalid keys: {invalid_keys}"
            )

        # Filter out time field if appropriate
        filtered_entry = {
            k: v
            for k, v in entry_dict.items()
            if k != "time" or preserve_time or not time_should_be_removed
        }

        # Store the entry
        with get_storage(mid) as storage:
            setattr(storage, "entry", filtered_entry)

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to add entry to model {mid}: {e}") from e


def _with_time(
    rawentry: dict[str, Any],
    time: Optional[float],
    as_type: Type[T] = FrozenDottedDict,
) -> T:
    """Create an instance with time field added."""
    return as_type(**(dict(time=time) | rawentry))


@overload
def get_entries(mid: ModelIdentifier) -> Iterator[FrozenDottedDict]: ...


@overload
def get_entries(mid: ModelIdentifier, as_type: Type[T]) -> Iterator[T]: ...


def get_entries(
    mid: ModelIdentifier,
    as_type: Type[T] = FrozenDottedDict,
) -> Iterator[T]:
    """
    Get all entries from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entries to (defaults to FrozenDottedDict)

    Returns:
        Iterator of entries with timestamps

    Raises:
        ValueError: If model access fails
    """
    try:
        with get_storage(mid) as storage:
            for value in storage.__history__().get("entry", []):
                if not value.unavailable:
                    entry_data = cast(dict[str, Any], value.data)
                    yield _with_time(entry_data, value.time, as_type)
    except Exception as e:
        raise ValueError(f"Failed to get entries from model {mid}: {e}") from e


def _entry_matches(
    entry_dict: dict[str, Any],
    predicate: Optional[Callable[..., bool]],
    field_filters: dict[str, Any],
) -> bool:
    """Check if an entry matches the given filters and predicate."""
    # Check callable predicate first (more flexible)
    if predicate is not None:
        try:
            if not predicate(**entry_dict):
                return False
        except Exception:
            # If predicate fails, entry doesn't match
            return False

    # Check field equality filters
    for field_name, expected_value in field_filters.items():
        if field_name not in entry_dict or entry_dict[field_name] != expected_value:
            return False

    return True


@overload
def filter_entries(
    mid: ModelIdentifier,
    predicate: Optional[Callable[..., bool]] = None,
    **field_filters: Any,
) -> Iterator[FrozenDottedDict]: ...


@overload
def filter_entries(
    mid: ModelIdentifier,
    predicate: Optional[Callable[..., bool]] = None,
    *,
    as_type: Type[T],
    **field_filters: Any,
) -> Iterator[T]: ...


def filter_entries(
    mid: ModelIdentifier,
    predicate: Optional[Callable[..., bool]] = None,
    *,
    as_type: Type[T] = FrozenDottedDict,
    **field_filters: Any,
) -> Iterator[T]:
    """
    Filter entries from a model based on predicate and field values.

    Args:
        mid: The model identifier
        predicate: Optional callable predicate that receives entry fields as kwargs
        as_type: Type to convert entries to (defaults to FrozenDottedDict)
        **field_filters: Field name/value pairs for exact matching

    Returns:
        Iterator of matching entries with timestamps

    Raises:
        ValueError: If model access fails

    Example:
        # Filter by field value
        for entry in filter_entries(mid, player_id=123):
            print(entry)

        # Filter by predicate (must accept **kwargs)
        for entry in filter_entries(mid, lambda **kwargs: kwargs['score'] > 100):
            print(entry)

        # Combine both
        for entry in filter_entries(mid, lambda **kwargs: kwargs['score'] > 100, status="active"):
            print(entry)
    """
    try:
        with get_storage(mid) as storage:
            for value in storage.__history__().get("entry", []):
                if not value.unavailable:
                    entry_data = cast(dict[str, Any], value.data)

                    if _entry_matches(entry_data, predicate, field_filters):
                        yield _with_time(entry_data, value.time, as_type)

    except Exception as e:
        raise ValueError(f"Failed to filter entries from model {mid}: {e}") from e


@overload
def get_latest_entry(mid: ModelIdentifier) -> FrozenDottedDict: ...


@overload
def get_latest_entry(mid: ModelIdentifier, as_type: Type[T]) -> T: ...


def get_latest_entry(
    mid: ModelIdentifier,
    as_type: Type[T] = FrozenDottedDict,
) -> T:
    """
    Get the most recent entry from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entry to (defaults to FrozenDottedDict)

    Returns:
        The latest entry (without timestamp since it's the current state)

    Raises:
        ValueError: If no entry exists or model access fails
    """
    try:
        with get_storage(mid) as storage:
            if not hasattr(storage, "entry"):
                raise ValueError(f"No entries found in model {mid}")

            entry_data = cast(dict[str, Any], storage.entry)
            return _with_time(entry_data, None, as_type)

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to get latest entry from model {mid}: {e}") from e


@validate_call
def get_field(mid: ModelIdentifier, field_name: str) -> Any:
    """
    Get a specific field value from the model's latest entry.

    Args:
        mid: The model identifier
        field_name: Name of the field to retrieve

    Returns:
        The field value

    Raises:
        AttributeError: If field doesn't exist
        ValueError: If model access fails
    """
    try:
        with get_storage(mid) as storage:
            if not hasattr(storage, field_name):
                raise AttributeError(f"Field '{field_name}' not found in model {mid}")
            return getattr(storage, field_name)
    except AttributeError:
        raise
    except Exception as e:
        raise ValueError(
            f"Failed to get field '{field_name}' from model {mid}: {e}"
        ) from e


@validate_call
def model_exists(mid: ModelIdentifier) -> bool:
    """
    Check if a model exists.

    Args:
        mid: The model identifier to check

    Returns:
        True if the model exists, False otherwise
    """
    try:
        return bool(get_storage(mid))
    except (ValueError, AttributeError):
        return False


def ignore_time_field(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to ignore time field in function arguments.

    Useful for functions that should not process time fields from entries.
    """

    @wraps(func)
    def wrapper(time: Optional[float] = None, **kwargs: Any) -> T:
        return func(**kwargs)

    return wrapper
