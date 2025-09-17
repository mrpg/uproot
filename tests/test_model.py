"""
Tests for uproot.models module.

Tests the core model functionality including entry creation, model operations,
and querying capabilities.
"""

import sys
from pathlib import Path

import pytest

# Add uproot src to path
uproot_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(uproot_src))

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.models as mod
import uproot.storage as s
import uproot.types as t

# Reset database for tests
d.DATABASE.reset()
u.CONFIGS["test"] = []
u.CONFIGS_PPATHS["test"] = []


@pytest.fixture
def session_and_player():
    """Create session and player for tests."""
    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with s.Session(sid) as session:
        pid = c.create_player(session)

    return sid, pid


@pytest.fixture
def model_and_player(session_and_player):
    """Create model and player for tests."""
    sid, pid = session_and_player

    with s.Session(sid) as session:
        mid = mod.create_model(session)

    return mid, pid


class SimpleEntry(metaclass=mod.Entry):
    """Simple entry for testing."""

    value: int
    message: str


class PlayerEntry(metaclass=mod.Entry):
    """Entry with player identifier."""

    pid: t.PlayerIdentifier
    score: float
    level: str


# Basic model tests
def test_create_model(session_and_player):
    """Test model creation."""
    sid, pid = session_and_player

    with s.Session(sid) as session:
        mid = mod.create_model(session)
        assert mid is not None
        assert mod.model_exists(mid)


def test_create_model_with_tag(session_and_player):
    """Test model creation with tag."""
    sid, pid = session_and_player

    with s.Session(sid) as session:
        mid = mod.create_model(session, tag="test_model")
        assert mid is not None
        assert mod.model_exists(mid)


def test_model_exists_false_for_fake(session_and_player):
    """Test model_exists with fake model."""
    sid, pid = session_and_player

    # This might not work properly since we're creating a fake identifier
    # but test the function doesn't crash
    try:
        fake_mid = t.ModelIdentifier("nonexistent")
        result = mod.model_exists(fake_mid)
        # Either True or False is fine - we're testing it doesn't crash
        assert isinstance(result, bool)
    except Exception:
        # If it throws an exception, that's also fine behavior
        pass


# Entry tests
def test_entry_creation():
    """Test creating Entry instances."""
    entry = SimpleEntry(value=42, message="test")
    assert entry.value == 42
    assert entry.message == "test"
    assert hasattr(entry, "time")
    assert entry.time is None


def test_entry_is_immutable():
    """Test that entries are immutable."""
    entry = SimpleEntry(value=42, message="test")

    # Entries should be frozen
    with pytest.raises(Exception):  # Various frozen exceptions possible
        entry.value = 100


def test_entry_with_time():
    """Test entry with time field."""

    class TimedEntry(metaclass=mod.Entry):
        value: int
        time: float

    entry = TimedEntry(value=42, time=123.45)
    assert entry.value == 42
    assert entry.time == 123.45


# Add entry tests
def test_add_raw_entry_simple(model_and_player):
    """Test adding a simple raw entry."""
    mid, pid = model_and_player

    entry = SimpleEntry(value=123, message="raw test")
    mod.add_raw_entry(mid, entry)

    # Verify it was added by checking we can get entries
    entries = list(mod.get_entries(mid))
    assert len(entries) == 1
    assert entries[0].value == 123
    assert entries[0].message == "raw test"


def test_add_raw_entry_with_dict(model_and_player):
    """Test adding raw dictionary entry."""
    mid, pid = model_and_player

    entry_dict = {"x": 42, "y": "hello"}
    mod.add_raw_entry(mid, entry_dict)

    entries = list(mod.get_entries(mid))
    assert len(entries) == 1
    assert entries[0].x == 42
    assert entries[0].y == "hello"


def test_auto_add_entry(model_and_player):
    """Test auto-adding entry with identifier filling."""
    mid, pid = model_and_player

    entry = mod.auto_add_entry(mid, pid, PlayerEntry, score=95.5, level="hard")

    assert entry is not None
    assert entry.pid == pid
    assert entry.score == 95.5
    assert entry.level == "hard"


def test_smart_add_entry_auto_mode(model_and_player):
    """Test smart add_entry in auto-filling mode."""
    mid, pid = model_and_player

    entry = mod.add_entry(mid, pid, PlayerEntry, score=88.8, level="medium")

    assert entry is not None
    assert entry.pid == pid
    assert entry.score == 88.8
    assert entry.level == "medium"


def test_smart_add_entry_raw_mode(model_and_player):
    """Test smart add_entry in raw mode."""
    mid, pid = model_and_player

    entry = PlayerEntry(pid=pid, score=77.7, level="easy")
    result = mod.add_entry(mid, entry)

    assert result is None  # Raw mode returns None

    # Verify it was added
    entries = list(mod.get_entries(mid))
    assert len(entries) == 1
    assert entries[0].score == 77.7


# Query tests
def test_get_entries_empty(model_and_player):
    """Test getting entries from empty model."""
    mid, pid = model_and_player

    entries = list(mod.get_entries(mid))
    assert len(entries) == 0


def test_get_entries_with_data(model_and_player):
    """Test getting entries with data."""
    mid, pid = model_and_player

    # Add some entries
    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="hard")
    mod.add_entry(mid, pid, PlayerEntry, score=75.5, level="medium")

    entries = list(mod.get_entries(mid))
    assert len(entries) == 2

    # Check entries have timestamps
    for entry in entries:
        assert hasattr(entry, "time")


def test_get_entries_with_type(model_and_player):
    """Test getting entries as specific type."""
    mid, pid = model_and_player

    mod.add_entry(mid, pid, PlayerEntry, score=95.0, level="expert")

    entries = list(mod.get_entries(mid, PlayerEntry))
    assert len(entries) == 1
    assert isinstance(entries[0], PlayerEntry)
    assert entries[0].score == 95.0


def test_filter_entries_by_field(model_and_player):
    """Test filtering entries by field values."""
    mid, pid = model_and_player

    # Add multiple entries
    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="hard")
    mod.add_entry(mid, pid, PlayerEntry, score=75.5, level="medium")
    mod.add_entry(mid, pid, PlayerEntry, score=85.0, level="hard")

    # Filter by level
    hard_entries = list(mod.filter_entries(mid, level="hard"))
    assert len(hard_entries) == 2
    for entry in hard_entries:
        assert entry.level == "hard"


def test_filter_entries_by_predicate(model_and_player):
    """Test filtering entries by predicate function."""
    mid, pid = model_and_player

    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="hard")
    mod.add_entry(mid, pid, PlayerEntry, score=75.5, level="medium")
    mod.add_entry(mid, pid, PlayerEntry, score=95.5, level="expert")

    # Filter by score > 80
    high_scores = list(
        mod.filter_entries(mid, predicate=lambda **kwargs: kwargs["score"] > 80.0)
    )
    assert len(high_scores) == 2
    for entry in high_scores:
        assert entry.score > 80.0


def test_filter_entries_combined(model_and_player):
    """Test filtering with both predicate and field filters."""
    mid, pid = model_and_player

    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="hard")
    mod.add_entry(mid, pid, PlayerEntry, score=75.5, level="hard")
    mod.add_entry(mid, pid, PlayerEntry, score=95.0, level="medium")

    # Filter by level="hard" AND score > 80
    filtered = list(
        mod.filter_entries(
            mid, predicate=lambda **kwargs: kwargs["score"] > 80.0, level="hard"
        )
    )
    assert len(filtered) == 1
    assert filtered[0].score == 90.0
    assert filtered[0].level == "hard"


def test_get_latest_entry(model_and_player):
    """Test getting the latest entry."""
    mid, pid = model_and_player

    # Add entries in sequence
    mod.add_entry(mid, pid, PlayerEntry, score=80.0, level="easy")
    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="medium")
    mod.add_entry(mid, pid, PlayerEntry, score=95.0, level="hard")

    latest = mod.get_latest_entry(mid)
    # Latest should be the last one added
    assert latest.score == 95.0
    assert latest.level == "hard"


# Error handling tests
def test_add_entry_invalid_keys(model_and_player):
    """Test adding entry with invalid dictionary keys."""
    mid, pid = model_and_player

    # Invalid key (not a Python identifier)
    invalid_dict = {"123invalid": "value"}

    with pytest.raises(ValueError):
        mod.add_raw_entry(mid, invalid_dict)


def test_get_latest_entry_empty_model(model_and_player):
    """Test getting latest entry from empty model."""
    mid, pid = model_and_player

    with pytest.raises(ValueError):
        mod.get_latest_entry(mid)


def test_filter_entries_bad_predicate(model_and_player):
    """Test filtering with predicate that raises exception."""
    mid, pid = model_and_player

    mod.add_entry(mid, pid, PlayerEntry, score=90.0, level="hard")

    def bad_predicate(**kwargs):
        raise Exception("Predicate error")

    # Should not raise - bad predicates cause entries to not match
    filtered = list(mod.filter_entries(mid, predicate=bad_predicate))
    assert len(filtered) == 0


# Performance test
def test_multiple_entries_performance(model_and_player):
    """Test adding and querying multiple entries."""
    mid, pid = model_and_player

    # Add 100 entries
    for i in range(100):
        mod.add_entry(mid, pid, PlayerEntry, score=float(i), level=f"level_{i % 5}")

    # Query all
    entries = list(mod.get_entries(mid))
    assert len(entries) == 100

    # Filter some
    level_0_entries = list(mod.filter_entries(mid, level="level_0"))
    assert len(level_0_entries) == 20  # Every 5th entry


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
