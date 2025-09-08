import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t


def setup():
    d.DATABASE.reset()
    u.CONFIGS["test"] = []
    u.CONFIGS_PPATHS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with sid() as session:
        pid = c.create_player(session)

    return sid, pid


def test_storage_constructors():
    admin = s.Admin()
    assert admin.__namespace__ == ("admin",)

    session = s.Session("test_session")
    assert session.__namespace__ == ("session", "test_session")

    player = s.Player("test_session", "test_user")
    assert player.__namespace__ == ("player", "test_session", "test_user")

    group = s.Group("test_session", "test_group")
    assert group.__namespace__ == ("group", "test_session", "test_group")

    model = s.Model("test_session", "test_model")
    assert model.__namespace__ == ("model", "test_session", "test_model")


def test_field_access():
    sid, pid = setup()

    # Set and get field
    pid().x = 42

    with pid() as player:
        assert player.x == 42

    # Field doesn't exist
    try:
        with pid() as player:
            _ = player.nonexistent

        assert False, "Should raise AttributeError"
    except AttributeError:
        pass


def test_field_update_context():
    sid, pid = setup()

    with pid() as player:
        player.y = -42
        assert player.y == -42

        player.y = 17
        assert player.y == 17


def test_field_deletion():
    sid, pid = setup()

    pid().to_delete = "value"

    with pid() as player:
        assert player.to_delete == "value"

    del pid().to_delete

    try:
        with pid() as player:
            value = player.to_delete

        assert False, f"Should raise AttributeError after deletion, but got: {value}"
    except AttributeError:
        pass


def test_fields_method():
    sid, pid = setup()

    pid().field1 = 1
    pid().field2 = 2
    pid().field3 = 3

    fields = pid().__fields__()
    assert type(fields) is list
    assert "field1" in fields
    assert "field2" in fields
    assert "field3" in fields


def test_bool_method():
    sid, pid = setup()

    # Empty storage should be falsy
    empty_player = s.Player("test", "empty_user")
    assert not empty_player

    # Storage with fields should be truthy
    pid().some_field = "value"
    assert pid()


def test_storage_equality():
    sid, pid = setup()

    # Same path should be equal
    player1 = s.Player("test", "user1")
    player2 = s.Player("test", "user1")
    assert player1 == player2

    # Different paths should not be equal
    player3 = s.Player("test", "user2")
    assert player1 != player3


def test_identifier_conversion():
    sid, pid = setup()

    # Test ~ operator
    session = s.Session("test")
    session_id = ~session
    assert type(session_id) is t.SessionIdentifier
    assert session_id.sname == "test"

    player = s.Player("test", "user")
    player_id = ~player
    assert type(player_id) is t.PlayerIdentifier
    assert player_id.sname == "test"
    assert player_id.uname == "user"


def test_history():
    sid, pid = setup()

    # Set field multiple times
    pid().counter = 1
    pid().counter = 2
    pid().counter = 3

    history = pid().__history__()
    assert "counter" in history

    # History should contain values for counter field
    counter_history = history["counter"]
    assert len(counter_history) >= 3


def test_within_basic():
    sid, pid = setup()

    # Set up data with different contexts
    pid().score = 10
    pid().level = 1

    # Access within specific context
    with pid() as player:
        within_ctx = player.within(score=10)
        assert within_ctx.score == 10
        assert within_ctx.level == 1


def test_within_nonexistent():
    sid, pid = setup()

    pid().x = 1

    with pid() as player:
        within_ctx = player.within(y=2)
        # Accessing non-existent field in context returns None
        assert within_ctx.x is None


def test_along_iteration():
    sid, pid = setup()

    # Create history for a field
    pid().state = "init"
    pid().state = "running"
    pid().state = "complete"

    with pid() as player:
        states = []
        contexts = []

        for value, ctx in player.along("state"):
            states.append(value)
            contexts.append(ctx)

        assert "init" in states
        assert "running" in states
        assert "complete" in states
        assert len(contexts) == len(states)


def test_field_from_paths():
    sid, pid = setup()

    # Create multiple players with same field
    pid().score = 100

    with sid() as session:
        pid2 = c.create_player(session)
        pid2().score = 200

    paths = [pid().__namespace__, pid2().__namespace__]
    scores = s.field_from_paths(paths, "score")

    assert type(scores) is dict
    assert len(scores) == 2
    assert 100 in [v.data for v in scores.values()]
    assert 200 in [v.data for v in scores.values()]


def test_list_assignment_then_append():
    """Test that assignment followed by in-place append is properly detected."""
    sid, pid = setup()

    # Assign a list and then append to it within the same context
    with pid() as player:
        player.my_list = [1, 2, 3]
        player.my_list.append(4)
        # At this point, player.my_list should be [1, 2, 3, 4]
        assert player.my_list == [1, 2, 3, 4]

    # Verify that the appended value was actually persisted
    with pid() as player:
        assert player.my_list == [
            1,
            2,
            3,
            4,
        ], f"Expected [1, 2, 3, 4], got {player.my_list}"


def test_no_double_flush_for_assigned_unchanged_values():
    """Test that flush doesn't create duplicate entries for assigned but unchanged values."""
    sid, pid = setup()

    # Track history count before
    initial_history = pid().__history__()
    initial_count = len(initial_history.get("unchanged_value", []))

    with pid() as player:
        # Assign a value but don't modify it further
        player.unchanged_value = "test"
        # Don't modify player.unchanged_value - flush should not create additional entry

    # Check that only the assignment created a history entry, not the flush
    final_history = pid().__history__()
    final_count = len(final_history.get("unchanged_value", []))

    # Should have exactly one new entry from the assignment
    assert (
        final_count == initial_count + 1
    ), f"Expected {initial_count + 1} entries, got {final_count}"


def test_storage_repr():
    admin = s.Admin()
    assert repr(admin) == "Admin()"

    session = s.Session("test")
    assert repr(session) == "Session(*('test',))"

    player = s.Player("test", "user")
    assert repr(player) == "Player(*('test', 'user'))"
