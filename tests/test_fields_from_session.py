from time import sleep

import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
from uproot.cache import load_database_into_memory


def test_fields_from_session_basic():
    """Test fields_from_session returns player fields from a session."""
    d.DATABASE.reset()
    u.CONFIGS["test_session"] = []
    u.CONFIGS_PPATHS["test_session"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test_session")

    session_name = str(sid)  # Get actual session name

    with sid() as session:
        pid1 = c.create_player(session)
        pid2 = c.create_player(session)

    # Add some fields to players
    pid1().score = 100
    pid1().level = 5
    pid2().score = 200
    pid2().nickname = "player2"

    # Load data into memory cache
    load_database_into_memory()

    # Get all fields from session
    result = s.fields_from_session(session_name)

    # Should have entries for both players (including system fields)
    assert len(result) > 20  # Many system fields plus our custom ones

    # Check that we have our expected custom fields among all fields
    all_fields = {key[1] for key in result.keys()}
    assert "score" in all_fields
    assert "level" in all_fields
    assert "nickname" in all_fields

    # Check that all returned values are Value objects
    for value in result.values():
        assert hasattr(value, "time")
        assert hasattr(value, "data")
        assert hasattr(value, "unavailable")

    # Check that we can find our specific values
    score_entries = [(k, v) for k, v in result.items() if k[1] == "score"]
    assert len(score_entries) == 2  # One for each player
    score_values = [v.data for k, v in score_entries]
    assert set(score_values) == {100, 200}


def test_fields_from_session_with_since():
    """Test fields_from_session with since parameter filters correctly."""
    d.DATABASE.reset()
    u.CONFIGS["test_since"] = []
    u.CONFIGS_PPATHS["test_since"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test_since")

    session_name = str(sid)  # Get actual session name

    with sid() as session:
        pid = c.create_player(session)

    # Add initial field
    pid().initial_field = "old_value"

    # Record timestamp after first insert
    from time import time

    checkpoint = time()

    # Small delay to ensure timestamp difference
    sleep(0.01)

    # Add field after checkpoint
    pid().new_field = "new_value"
    pid().initial_field = "updated_value"

    # Load data into memory cache
    load_database_into_memory()

    # Get fields from session after checkpoint
    result = s.fields_from_session(session_name, since_epoch=checkpoint)

    # Should only include fields modified after checkpoint
    assert len(result) >= 2  # At least new_field and updated initial_field

    # Check that all returned fields have timestamps after checkpoint
    for value in result.values():
        assert value.time > checkpoint

    # Check that we have our expected fields that were modified after checkpoint
    modified_fields = {key[1] for key in result.keys()}
    assert "new_field" in modified_fields
    assert "initial_field" in modified_fields


def test_fields_from_session_empty():
    """Test fields_from_session with empty session."""
    d.DATABASE.reset()
    u.CONFIGS["empty_session"] = []
    u.CONFIGS_PPATHS["empty_session"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        c.create_session(admin, "empty_session")

    # Get fields from empty session
    result = s.fields_from_session("empty_session")

    # Should return empty dict
    assert result == {}


def test_fields_from_session_nonexistent():
    """Test fields_from_session with nonexistent session."""
    d.DATABASE.reset()

    # Get fields from nonexistent session
    result = s.fields_from_session("nonexistent_session")

    # Should return empty dict
    assert result == {}
