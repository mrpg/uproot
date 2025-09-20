# Copyright Max R. P. Grossmann, Holger Gerhardt, et al., 2025.
# SPDX-License-Identifier: LGPL-3.0-or-later

import inspect
from builtins import all as pyall
from dataclasses import asdict
from typing import (
    Any,
    Callable,
    Optional,
    Type,
    TypeVar,
    Union,
    cast,
)
from uuid import UUID

from pydantic import Field, validate_call
from pydantic.dataclasses import dataclass as validated_dataclass

import uproot.core as c
import uproot.storage as s
from uproot.flexibility import flexible
from uproot.types import (
    GroupIdentifier,
    Identifier,
    ModelIdentifier,
    PlayerIdentifier,
    SessionIdentifier,
    uuid,
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

        # Always add time field, prevent user override
        if "time" in annotations:
            raise ValueError(
                f"Class {name} cannot define 'time' field - it's automatically added by Entry metaclass"
            )

        # Always add id field, prevent user override
        if "id" in annotations:
            raise ValueError(
                f"Class {name} cannot define 'id' field - it's automatically added by Entry metaclass"
            )

        annotations["time"] = Optional[float]
        namespace["time"] = Field(
            default_factory=lambda: None,
            exclude=True,
            repr=False,
        )

        annotations["id"] = UUID
        namespace["id"] = Field(
            default_factory=uuid,
            exclude=True,
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


def add_entry(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Any,
    **other_fields: Any,
) -> Any:
    """
    Add an entry to the model with auto-filling of identifier fields.

    Automatically fills identifier fields (PlayerIdentifier, SessionIdentifier,
    GroupIdentifier, ModelIdentifier) based on type annotations in the entry class.

    Args:
        mid: The model identifier to add the entry to
        pid: The player identifier for auto-filling
        entry_type: The entry class to create
        **other_fields: Additional fields to set on the entry

    Returns:
        The created entry instance

    Raises:
        ValueError: If entry creation or adding fails

    Example:
        offer = add_entry(model_id, player_id, Offer, price=100.0, quantity=5)
    """
    if isinstance(pid, s.Storage):
        # We don't use @flexible here because it cannot handle Unions (neither can Max)
        pid = ~pid  # type: ignore[assignment]

    return auto_add_entry(mid, pid, entry_type, **other_fields)


@validate_call
def add_raw_entry(
    mid: ModelIdentifier,
    entry: Union[dict[str, Any], Any],
) -> None:
    """
    Add a raw entry to the model without auto-filling identifier fields.

    Use this when you need direct control over all fields or when adding
    non-Entry objects (like plain dicts). The time field is always filtered out
    since it's managed by the storage system.

    Args:
        mid: The model identifier to add the entry to
        entry: The entry to add (dataclass instance or dict)

    Raises:
        ValueError: If entry format is invalid or adding to model fails
    """
    # Convert entry to dict format
    if hasattr(entry, "__is_pydantic_dataclass__"):
        entry_dict = asdict(entry)  # type: ignore[arg-type]
    else:
        entry_dict = dict(entry) if not isinstance(entry, dict) else entry

    # Validate entry structure
    if not pyall(isinstance(k, str) and k.isidentifier() for k in entry_dict.keys()):
        invalid_keys = [
            k
            for k in entry_dict.keys()
            if not (isinstance(k, str) and k.isidentifier())
        ]
        raise ValueError(
            f"Entry keys must be valid Python identifiers. Invalid keys: {invalid_keys}"
        )

    # Always filter out time field since it's managed by the storage system
    filtered_entry = {k: v for k, v in entry_dict.items() if k != "time"}

    # Store the entry
    with get_storage(mid) as storage:
        setattr(storage, "entry", filtered_entry)


def _with_time(
    rawentry: dict[str, Any],
    time: Optional[float],
    as_type: Type[T],
) -> T:
    """Create an instance with time field added."""
    return as_type(**(dict(time=time) | rawentry))


def get_entries(
    mid: ModelIdentifier,
    as_type: Type[T],
) -> list[T]:
    """
    Get all entries from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entries to

    Returns:
        List of entries with timestamps

    Raises:
        ValueError: If model access fails
    """
    try:
        retval = []

        with get_storage(mid) as storage:
            for value in storage.__history__().get("entry", []):
                if not value.unavailable:
                    entry_data = cast(dict[str, Any], value.data)
                    retval.append(_with_time(entry_data, value.time, as_type))

        return retval
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


def filter_entries(
    mid: ModelIdentifier,
    as_type: Type[T],
    *,
    predicate: Optional[Callable[..., bool]] = None,
    **field_filters: Any,
) -> list[T]:
    """
    Filter entries from a model based on predicate and field values.

    Args:
        mid: The model identifier
        as_type: Type to convert entries to
        predicate: Optional callable predicate that receives entry fields as kwargs
        **field_filters: Field name/value pairs for exact matching

    Returns:
        List of matching entries with timestamps

    Raises:
        ValueError: If model access fails

    Examples:
        # Filter by field value
        entries = filter_entries(mid, EntryType, player_id=123)

        # Filter by predicate
        high_scores = filter_entries(
            mid, EntryType,
            predicate=lambda **kwargs: kwargs['score'] > 100
        )

        # Combine field filter and predicate
        active_high_scores = filter_entries(
            mid, EntryType,
            predicate=lambda **kwargs: kwargs['score'] > 100,
            status="active"
        )
    """
    try:
        retval = []

        with get_storage(mid) as storage:
            for value in storage.__history__().get("entry", []):
                if not value.unavailable:
                    entry_data = cast(dict[str, Any], value.data)

                    if _entry_matches(entry_data, predicate, field_filters):
                        retval.append(_with_time(entry_data, value.time, as_type))

        return retval
    except Exception as e:
        raise ValueError(f"Failed to filter entries from model {mid}: {e}") from e


def get_latest_entry(
    mid: ModelIdentifier,
    as_type: Type[T],
) -> T:
    """
    Get the most recent entry from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entry to

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
