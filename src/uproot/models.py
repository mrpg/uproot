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

from pydantic import validate_call
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
    identify,
    materialize,
    uuid,
)

T = TypeVar("T")

# Return type for entry queries: (id, time, entry)
StoredEntry = tuple[UUID, float, T]


class Entry(type):
    """
    Metaclass for model entries. Creates immutable pydantic dataclasses.

    The 'id' field name is reserved - entries are assigned UUIDs by the
    storage layer, returned alongside entries in query results.
    """

    def __new__(
        cls,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> Type[Any]:
        annotations = namespace.get("__annotations__", {})

        if "id" in annotations:
            raise ValueError(
                f"Class {name} cannot define 'id' field - it's reserved for storage"
            )

        new_class = super().__new__(cls, name, bases, namespace)

        return validated_dataclass(
            new_class,  # type: ignore[arg-type]
            frozen=True,
        )


@flexible
@validate_call
def create_model(
    sid: SessionIdentifier, *, tag: Optional[str] = None
) -> ModelIdentifier:
    """
    Create a new model in the given session.

    Args:
        session: The session identifier to create the model in
        tag: Optional tag for the model

    Returns:
        The identifier of the newly created model
    """
    with materialize(sid) as s:
        mid = c.create_model(s, data=dict(tag=tag))

    return mid


def get_storage(mid: ModelIdentifier) -> s.Storage:
    """
    Get the storage instance for a model.

    Args:
        mid: The model identifier

    Returns:
        The storage instance
    """
    storage = materialize(mid)

    if not storage:
        raise ValueError(f"Model {mid} not found")

    return storage


@flexible
@validate_call
def auto_add_entry(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Any,
    **other_fields: Any,
) -> UUID:
    """
    Automatically create and add an entry with auto-filled identifier fields.

    Args:
        mid: The model identifier to add the entry to
        pid: The player identifier for auto-filling
        entry_type: The entry class to create
        **other_fields: Additional fields to set on the entry

    Returns:
        The UUID assigned to the stored entry
    """
    auto_fields: dict[str, Any] = {}

    # Auto-fill identifier fields based on type annotations
    for field_name, field_type in getattr(entry_type, "__annotations__", {}).items():
        if inspect.isclass(field_type) and issubclass(field_type, Identifier):
            if field_type == PlayerIdentifier:
                auto_fields[field_name] = pid
            elif field_type == SessionIdentifier:
                with materialize(pid) as player:
                    auto_fields[field_name] = player.session
            elif field_type == GroupIdentifier:
                with materialize(pid) as player:
                    auto_fields[field_name] = player.group
            elif field_type == ModelIdentifier:
                auto_fields[field_name] = mid
            else:
                raise ValueError(f"Unsupported identifier type: {field_type}")

    # Merge auto-filled and user-provided fields
    all_fields = auto_fields | other_fields

    # Create the entry instance
    new_entry = entry_type(**all_fields)

    # Add it to the model and return the UUID
    return add_raw_entry(mid, new_entry)


def add_entry(
    mid: ModelIdentifier,
    pid: PlayerIdentifier,
    entry_type: Any,
    **other_fields: Any,
) -> UUID:
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
        The UUID assigned to the stored entry

    Example:
        entry_id = add_entry(model_id, player_id, Offer, price=100.0, quantity=5)
    """
    if isinstance(pid, s.Storage):
        pid = identify(pid)  # type: ignore[assignment]

    return auto_add_entry(mid, pid, entry_type, **other_fields)


@validate_call
def add_raw_entry(
    mid: ModelIdentifier,
    entry: Union[dict[str, Any], Any],
) -> UUID:
    """
    Add a raw entry to the model without auto-filling identifier fields.

    Use this when you need direct control over all fields or when adding
    non-Entry objects (like plain dicts).

    Args:
        mid: The model identifier to add the entry to
        entry: The entry to add (dataclass instance or dict)

    Returns:
        The UUID assigned to the stored entry

    Raises:
        ValueError: If entry format is invalid or adding to model fails
    """
    # Convert entry to dict format
    if hasattr(entry, "__is_pydantic_dataclass__"):
        entry_dict = asdict(entry)  # type: ignore[arg-type]
    else:
        entry_dict = dict(entry) if not isinstance(entry, dict) else entry

    # Validate entry structure
    if not pyall(
        isinstance(k, str) and k.isidentifier() for k in entry_dict.keys()  # KEEP AS IS
    ):
        invalid_keys = [
            k
            for k in entry_dict.keys()
            if not (isinstance(k, str) and k.isidentifier())  # KEEP AS IS
        ]
        raise ValueError(
            f"Entry keys must be valid Python identifiers. Invalid keys: {invalid_keys}"
        )

    # Generate UUID and store as [id, entry_dict]
    entry_id = uuid()
    with get_storage(mid) as storage:
        setattr(storage, "entry", [str(entry_id), entry_dict])

    return entry_id


def _parse_stored_entry(
    data: Any,
    time: float,
    as_type: Type[T],
) -> StoredEntry[T]:
    """Parse stored [id, entry_dict] format into (id, time, entry) tuple."""
    entry_id, entry_dict = data
    return (UUID(entry_id), time, as_type(**entry_dict))


def get_entries(
    mid: ModelIdentifier,
    as_type: Type[T],
    subset: slice = slice(None),
) -> list[StoredEntry[T]]:
    """
    Get all entries from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entries to

    Returns:
        List of (id, time, entry) tuples
    """
    retval: list[StoredEntry[T]] = []

    with get_storage(mid) as storage:
        for value in storage.__history__().get("entry", [])[subset]:
            if not value.unavailable:
                retval.append(
                    _parse_stored_entry(value.data, cast(float, value.time), as_type)
                )

    return retval


def _entry_matches(
    entry: T,
    predicate: Optional[Callable[[T], bool]],
    field_filters: dict[str, Any],
) -> bool:
    """Check if an entry matches the given filters and predicate."""
    # Check callable predicate first (more flexible)
    if predicate is not None:
        try:
            if not predicate(entry):
                return False
        except Exception:
            # If predicate fails, entry doesn't match
            return False

    # Check field equality filters
    for field_name, expected_value in field_filters.items():
        try:
            if getattr(entry, field_name) != expected_value:
                return False
        except AttributeError:
            return False

    return True


def filter_entries(
    mid: ModelIdentifier,
    as_type: Type[T],
    *,
    id: Optional[UUID] = None,
    predicate: Optional[Callable[[T], bool]] = None,
    **field_filters: Any,
) -> list[StoredEntry[T]]:
    """
    Filter entries from a model based on predicate and field values.

    Args:
        mid: The model identifier
        as_type: Type to convert entries to
        id: Optional UUID to filter by entry id
        predicate: Optional callable that receives the entry object and returns bool
        **field_filters: Field name/value pairs for exact matching

    Returns:
        List of matching (id, time, entry) tuples

    Examples:
        # Filter by field value
        entries = filter_entries(mid, EntryType, player_id=123)

        # Filter by predicate
        high_scores = filter_entries(
            mid, EntryType,
            predicate=lambda entry: entry.score > 100
        )

        # Filter by entry id
        specific = filter_entries(mid, EntryType, id=some_uuid)
    """
    retval: list[StoredEntry[T]] = []

    with get_storage(mid) as storage:
        for value in storage.__history__().get("entry", []):
            if not value.unavailable:
                entry_id_str, entry_data = cast(tuple[str, dict[str, Any]], value.data)
                entry_id = UUID(entry_id_str)

                # Filter by id if specified
                if id is not None and entry_id != id:
                    continue

                entry = as_type(**entry_data)

                if _entry_matches(entry, predicate, field_filters):
                    retval.append((entry_id, cast(float, value.time), entry))

    return retval


def get_latest_entry(
    mid: ModelIdentifier,
    as_type: Type[T],
) -> StoredEntry[T]:
    """
    Get the most recent entry from a model.

    Args:
        mid: The model identifier
        as_type: Type to convert entry to

    Returns:
        The latest entry as (id, None, entry) tuple (time is None for current state)

    Raises:
        ValueError: If no entry exists or model access fails
    """
    with get_storage(mid) as storage:
        if not hasattr(storage, "entry"):
            raise ValueError(f"No entries found in model {mid}")

        value = storage.__history__()["entry"][-1]

        if not value.unavailable:
            return _parse_stored_entry(value.data, cast(float, value.time), as_type)
        else:
            raise ValueError(f"Model {mid} contains illegal tombstone entry")


@validate_call
def get_field(mid: ModelIdentifier, field_name: str) -> Any:
    """
    Get a specific field value from the model.

    Args:
        mid: The model identifier
        field_name: Name of the field to retrieve

    Returns:
        The field value
    """
    with get_storage(mid) as storage:
        return getattr(storage, field_name)


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
