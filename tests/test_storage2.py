import uproot as u
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s
import uproot.types as t


def expect_attribute_error(within_obj, field_name):
    """Helper to assert that accessing a field raises AttributeError."""
    try:
        getattr(within_obj, field_name)
        assert False, f"Expected AttributeError for field '{field_name}'"
    except AttributeError:
        pass  # Expected


def setup():
    d.DATABASE.reset()
    u.CONFIGS["test"] = []
    u.CONFIGS_PPATHS["test"] = []

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with t.materialize(sid) as session:
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
    t.materialize(pid).x = 42

    with t.materialize(pid) as player:
        assert player.x == 42

    # Field doesn't exist
    try:
        with t.materialize(pid) as player:
            _ = player.nonexistent

        assert False, "Should raise AttributeError"
    except AttributeError:
        pass


def test_field_update_context():
    sid, pid = setup()

    with t.materialize(pid) as player:
        player.y = -42
        assert player.y == -42

        player.y = 17
        assert player.y == 17


def test_field_deletion():
    sid, pid = setup()

    t.materialize(pid).to_delete = "value"

    with t.materialize(pid) as player:
        assert player.to_delete == "value"

    del t.materialize(pid).to_delete

    try:
        with t.materialize(pid) as player:
            value = player.to_delete

        assert False, f"Should raise AttributeError after deletion, but got: {value}"
    except AttributeError:
        pass


def test_fields_method():
    sid, pid = setup()

    t.materialize(pid).field1 = 1
    t.materialize(pid).field2 = 2
    t.materialize(pid).field3 = 3

    fields = t.materialize(pid).__fields__()
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
    t.materialize(pid).some_field = "value"
    assert t.materialize(pid)


def test_storage_equality():
    sid, pid = setup()

    # Same namespace should be equal
    player1 = s.Player("test", "user1")
    player2 = s.Player("test", "user1")
    assert player1 == player2

    # Different namespaces should not be equal
    player3 = s.Player("test", "user2")
    assert player1 != player3


def test_identifier_conversion():
    sid, pid = setup()

    # Test identify() function
    session = s.Session("test")
    session_id = t.identify(session)
    assert type(session_id) is t.SessionIdentifier
    assert session_id.sname == "test"

    player = s.Player("test", "user")
    player_id = t.identify(player)
    assert type(player_id) is t.PlayerIdentifier
    assert player_id.sname == "test"
    assert player_id.uname == "user"


def test_history():
    sid, pid = setup()

    # Set field multiple times
    t.materialize(pid).counter = 1
    t.materialize(pid).counter = 2
    t.materialize(pid).counter = 3

    history = t.materialize(pid).__history__()
    assert "counter" in history

    # History should contain values for counter field
    counter_history = history["counter"]
    assert len(counter_history) >= 3


def test_within_basic():
    sid, pid = setup()

    # Set up data with different contexts
    t.materialize(pid).score = 10
    t.materialize(pid).level = 1

    # Access within specific context
    with t.materialize(pid) as player:
        within_ctx = player.within(score=10)
        assert within_ctx.score == 10
        assert within_ctx.level == 1


def test_within_context_conditions_not_met():
    """Test context where the specified conditions are never satisfied."""
    sid, pid = setup()

    t.materialize(pid).x = 1
    t.materialize(pid).y = 1  # Set y to 1, but we'll look for y=2

    with t.materialize(pid) as player:
        # Context condition y=2 is never satisfied (y is actually 1)
        within_ctx = player.within(y=2)
        # When context conditions aren't met, field access raises AttributeError
        expect_attribute_error(within_ctx, "x")
        expect_attribute_error(within_ctx, "y")


def test_along_iteration():
    sid, pid = setup()

    # Create history for a field
    t.materialize(pid).state = "init"
    t.materialize(pid).state = "running"
    t.materialize(pid).state = "complete"

    with t.materialize(pid) as player:
        states = []
        contexts = []

        for value, ctx in player.along("state"):
            states.append(value)
            contexts.append(ctx)

        assert "init" in states
        assert "running" in states
        assert "complete" in states
        assert len(contexts) == len(states)


def test_list_assignment_then_append():
    """Test that assignment followed by in-place append is properly detected."""
    sid, pid = setup()

    # Assign a list and then append to it within the same context
    with t.materialize(pid) as player:
        player.my_list = [1, 2, 3]
        player.my_list.append(4)
        # At this point, player.my_list should be [1, 2, 3, 4]
        assert player.my_list == [1, 2, 3, 4]

    # Verify that the appended value was actually persisted
    with t.materialize(pid) as player:
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
    initial_history = t.materialize(pid).__history__()
    initial_count = len(initial_history.get("unchanged_value", []))

    with t.materialize(pid) as player:
        # Assign a value but don't modify it further
        player.unchanged_value = "test"
        # Don't modify player.unchanged_value - flush should not create additional entry

    # Check that only the assignment created a history entry, not the flush
    final_history = t.materialize(pid).__history__()
    final_count = len(final_history.get("unchanged_value", []))

    # Should have exactly one new entry from the assignment
    assert (
        final_count == initial_count + 1
    ), f"Expected {initial_count + 1} entries, got {final_count}"


def test_within_single_context_field():
    """Test that 'within' works with single context field (known working case)."""
    sid, pid = setup()

    # Set up current values
    t.materialize(pid).score = 100
    t.materialize(pid).level = 2
    t.materialize(pid).extra_data = "current"

    with t.materialize(pid) as player:
        # Single context field matching current value - this works
        within_ctx = player.within(score=100)
        assert within_ctx.score == 100
        assert within_ctx.level == 2
        assert within_ctx.extra_data == "current"


def test_within_multiple_context_fields_current_values():
    """Test multiple context fields with values that are all currently set."""
    sid, pid = setup()

    # Set up values that are all current
    t.materialize(pid).score = 100
    t.materialize(pid).level = 5

    with t.materialize(pid) as player:
        # Multiple context fields should all match when they're all currently set
        within_ctx = player.within(score=100, level=5)

        # All context fields should be accessible
        assert within_ctx.score == 100
        assert within_ctx.level == 5


def test_within_context_mismatch():
    """Test context where the specified value never existed."""
    sid, pid = setup()

    t.materialize(pid).score = 100
    t.materialize(pid).level = 5

    with t.materialize(pid) as player:
        # Context that doesn't match any historical values (score=200 never existed)
        within_ctx = player.within(score=200)
        # When context conditions are never satisfied, all field access returns None
        expect_attribute_error(within_ctx, "score")
        expect_attribute_error(within_ctx, "level")


def test_within_empty_context():
    sid, pid = setup()

    t.materialize(pid).score = 100
    t.materialize(pid).level = 5

    with t.materialize(pid) as player:
        # Empty context should work like normal access
        within_ctx = player.within()
        assert within_ctx.score == 100
        assert within_ctx.level == 5


def test_within_none_value_context():
    sid, pid = setup()

    t.materialize(pid).score = None
    t.materialize(pid).level = 5

    with t.materialize(pid) as player:
        # Context matching None value
        within_ctx = player.within(score=None)
        expect_attribute_error(within_ctx, "score")
        assert within_ctx.level == 5


def test_within_context_with_nonexistent_field():
    """Test context with non-existent field returns None for all field access."""
    sid, pid = setup()

    t.materialize(pid).real_field = "exists"

    with t.materialize(pid) as player:
        # Using non-existent field in context should work gracefully
        within_ctx = player.within(nonexistent_field="value")

        # When context field doesn't exist, all field access returns None
        expect_attribute_error(within_ctx, "real_field")
        expect_attribute_error(within_ctx, "nonexistent_field")


def test_within_complex_data_types():
    """Test within with complex data types as context fields."""
    sid, pid = setup()

    # Set up values with complex data types
    t.materialize(pid).scores = [10, 20, 30, 40]
    t.materialize(pid).metadata = {"level": 2, "difficulty": "hard"}
    t.materialize(pid).player_title = (
        "champion"  # Use player_title instead of name (which is auto-generated)
    )

    with t.materialize(pid) as player:
        # Test with complex list as context field
        within_ctx = player.within(scores=[10, 20, 30, 40])
        assert within_ctx.scores == [10, 20, 30, 40]
        assert within_ctx.metadata == {"level": 2, "difficulty": "hard"}
        assert within_ctx.player_title == "champion"

        # Test with complex dict as context field
        within_ctx2 = player.within(metadata={"level": 2, "difficulty": "hard"})
        assert within_ctx2.metadata == {"level": 2, "difficulty": "hard"}
        expect_attribute_error(within_ctx2, "scores")  # scores was set before metadata
        assert (
            within_ctx2.player_title == "champion"
        )  # player_title was set after metadata


def test_within_historical_values_works():
    """Test within actually works with historical values for single context fields!"""
    sid, pid = setup()

    # Create history
    t.materialize(pid).phase = "A"
    t.materialize(pid).data = "data_A1"

    t.materialize(pid).phase = "B"
    t.materialize(pid).data = "data_B1"

    t.materialize(pid).phase = "A"  # Back to phase A
    t.materialize(pid).data = "data_A2"

    with t.materialize(pid) as player:
        # Test with current value
        within_ctx_current = player.within(phase="A")
        assert within_ctx_current.phase == "A"
        assert within_ctx_current.data == "data_A2"  # Latest data when phase was A

        # Test with historical value - this actually works!
        within_ctx_historical = player.within(phase="B")
        assert within_ctx_historical.phase == "B"
        assert (
            within_ctx_historical.data == "data_B1"
        )  # Historical data when phase was B


def test_within_multiple_context_fields_simultaneous():
    """Test multiple context fields that were all set simultaneously."""
    sid, pid = setup()

    # Set up values that were all current at the same time
    t.materialize(pid).field_a = "value_a"
    t.materialize(pid).field_b = "value_b"
    t.materialize(pid).field_c = "value_c"

    with t.materialize(pid) as player:
        # Single context field should work
        within_ctx_single = player.within(field_a="value_a")
        assert within_ctx_single.field_a == "value_a"
        assert within_ctx_single.field_b == "value_b"
        assert within_ctx_single.field_c == "value_c"

        # Multiple context fields should work when they were all set simultaneously
        within_ctx_multi = player.within(field_a="value_a", field_b="value_b")
        assert within_ctx_multi.field_a == "value_a"
        assert within_ctx_multi.field_b == "value_b"
        assert (
            within_ctx_multi.field_c == "value_c"
        )  # Other fields should be accessible


def test_within_type_sensitivity():
    sid, pid = setup()

    t.materialize(pid).number_field = 42
    t.materialize(pid).string_field = "42"

    with t.materialize(pid) as player:
        # Test type-sensitive matching
        within_ctx = player.within(number_field=42)
        assert within_ctx.number_field == 42
        assert within_ctx.string_field == "42"

        # Different type should not match
        within_ctx2 = player.within(number_field="42")
        expect_attribute_error(within_ctx2, "number_field")


def test_within_boolean_context():
    """Test within with boolean values as context fields."""
    sid, pid = setup()

    t.materialize(pid).enabled = True
    t.materialize(pid).disabled = False
    t.materialize(pid).player_tag = (
        "veteran"  # Use player_tag instead of name (which is auto-generated)
    )

    with t.materialize(pid) as player:
        # Boolean context with True value
        within_ctx = player.within(enabled=True)
        assert within_ctx.enabled is True
        assert within_ctx.disabled is False
        assert within_ctx.player_tag == "veteran"

        # Boolean context with False value
        within_ctx2 = player.within(disabled=False)
        assert within_ctx2.disabled is False
        expect_attribute_error(
            within_ctx2, "enabled"
        )  # enabled was set before disabled
        assert within_ctx2.player_tag == "veteran"  # player_tag was set after disabled


def test_within_chaining_and_along_integration():
    sid, pid = setup()

    # Set up history
    t.materialize(pid).state = "init"
    t.materialize(pid).counter = 1
    t.materialize(pid).state = "running"
    t.materialize(pid).counter = 2
    t.materialize(pid).state = "complete"
    t.materialize(pid).counter = 3

    with t.materialize(pid) as player:
        # Test along method returns within contexts
        states = []
        within_contexts = []

        for value, within_ctx in player.along("state"):
            states.append(value)
            within_contexts.append(within_ctx)

        assert len(states) == len(within_contexts)
        assert "init" in states
        assert "running" in states
        assert "complete" in states

        # Test that within contexts work correctly
        for i, (state_val, ctx) in enumerate(zip(states, within_contexts)):
            if state_val is not None:
                # The context should have the state field set to the historical value
                assert hasattr(ctx, "__context_fields__")


def test_within_edge_cases():
    sid, pid = setup()

    t.materialize(pid).zero_value = 0
    t.materialize(pid).empty_string = ""
    t.materialize(pid).empty_list = []
    t.materialize(pid).empty_dict = {}
    t.materialize(pid).regular_field = "normal"

    with t.materialize(pid) as player:
        # Test with "falsy" values
        within_ctx = player.within(zero_value=0)
        assert within_ctx.zero_value == 0
        assert within_ctx.regular_field == "normal"

        within_ctx2 = player.within(empty_string="")
        assert within_ctx2.empty_string == ""
        assert within_ctx2.regular_field == "normal"

        within_ctx3 = player.within(empty_list=[])
        assert within_ctx3.empty_list == []

        within_ctx4 = player.within(empty_dict={})
        assert within_ctx4.empty_dict == {}


def test_within_binary_search_correctness():
    """Test that within correctly finds values in large histories using binary search."""
    sid, pid = setup()

    # Create large history (1000 entries)
    for i in range(1000):
        t.materialize(pid).counter = i
        t.materialize(pid).phase = f"phase_{i // 100}"  # Changes every 100 iterations
        t.materialize(pid).data = f"data_{i}"

    with t.materialize(pid) as player:
        # Test correctness with current values (last iteration): counter=999, phase=phase_9
        within_ctx = player.within(phase="phase_9")
        result = within_ctx.data
        assert result == "data_999"  # Should be the latest data

        # Test with multiple context fields - both should be satisfied
        within_ctx2 = player.within(phase="phase_9", counter=999)
        assert within_ctx2.data == "data_999"
        assert within_ctx2.phase == "phase_9"
        assert within_ctx2.counter == 999

        # Test with historical values
        within_ctx3 = player.within(phase="phase_5")
        # Should find data from when phase was "phase_5" (iterations 500-599)
        assert within_ctx3.phase == "phase_5"
        assert within_ctx3.data == "data_599"  # Latest data when phase_5 was current


def test_within_complex_interleaved_updates():
    """Test within with complex interleaved field updates to verify temporal consistency."""
    sid, pid = setup()

    # Create a scenario with interleaved updates to test temporal logic
    special_markers = []

    for i in range(50):  # Reduced from 100 for clearer test logic
        if i % 13 == 0:
            t.materialize(pid).mode = f"mode_{i // 13}"
        if i % 11 == 0:
            t.materialize(pid).level = i // 11
        if i % 7 == 0:
            t.materialize(pid).status = f"status_{i // 7}"
        if i % 17 == 0:
            t.materialize(pid).special_marker = f"marker_{i}"
            special_markers.append(f"marker_{i}")

        t.materialize(pid).tick = i

    with t.materialize(pid) as player:
        # Test current value access
        within_ctx = player.within(tick=49)  # Last tick value
        assert within_ctx.tick == 49

        # Test accessing state through current mode value
        current_mode = player.mode
        within_ctx2 = player.within(mode=current_mode)
        assert within_ctx2.mode == current_mode

        # Test with special marker if any exist
        if special_markers:
            current_marker = player.special_marker
            within_ctx3 = player.within(special_marker=current_marker)
            assert within_ctx3.special_marker == current_marker


def test_within_boundary_conditions():
    """Test within with edge cases and boundary conditions."""
    sid, pid = setup()

    # Test with None values, empty containers, and edge data
    t.materialize(pid).none_field = None
    t.materialize(pid).zero_field = 0
    t.materialize(pid).empty_string = ""
    t.materialize(pid).empty_list = []
    t.materialize(pid).empty_dict = {}
    t.materialize(pid).false_field = False
    t.materialize(pid).regular_field = "normal"

    with t.materialize(pid) as player:
        # Test context with None
        within_ctx1 = player.within(none_field=None)
        expect_attribute_error(within_ctx1, "none_field")
        assert within_ctx1.regular_field == "normal"

        # Test context with zero
        within_ctx2 = player.within(zero_field=0)
        assert within_ctx2.zero_field == 0
        assert within_ctx2.regular_field == "normal"

        # Test context with empty string
        within_ctx3 = player.within(empty_string="")
        assert within_ctx3.empty_string == ""
        assert within_ctx3.regular_field == "normal"

        # Test context with False
        within_ctx4 = player.within(false_field=False)
        assert within_ctx4.false_field is False
        assert within_ctx4.regular_field == "normal"


def test_within_realistic_gaming_scenario():
    """Test within with a realistic gaming scenario."""
    sid, pid = setup()

    # Simulate realistic gaming state progression
    t.materialize(pid).player_name = "TestPlayer"
    t.materialize(pid).level = 5
    t.materialize(pid).hp = 80
    t.materialize(pid).mp = 50
    t.materialize(pid).location = "dungeon_level_3"
    t.materialize(pid).equipment = {"weapon": "sword", "armor": "chainmail"}
    t.materialize(pid).status_effects = ["poison", "blessed"]

    with t.materialize(pid) as player:
        # Test context queries with different field types
        within_ctx1 = player.within(level=5)
        assert within_ctx1.level == 5
        expect_attribute_error(
            within_ctx1, "player_name"
        )  # player_name was set before level
        assert within_ctx1.location == "dungeon_level_3"  # location was set after level
        assert within_ctx1.hp == 80  # hp was set after level

        # Test with complex data type as context
        within_ctx2 = player.within(equipment={"weapon": "sword", "armor": "chainmail"})
        assert within_ctx2.equipment == {"weapon": "sword", "armor": "chainmail"}
        expect_attribute_error(within_ctx2, "level")  # level was set before equipment
        expect_attribute_error(within_ctx2, "hp")  # hp was set before equipment
        expect_attribute_error(
            within_ctx2, "player_name"
        )  # player_name was set before equipment

        # Test with list as context
        within_ctx3 = player.within(status_effects=["poison", "blessed"])
        assert within_ctx3.status_effects == ["poison", "blessed"]
        expect_attribute_error(within_ctx3, "hp")  # hp was set before status_effects
        expect_attribute_error(
            within_ctx3, "player_name"
        )  # player_name was set before status_effects
        expect_attribute_error(
            within_ctx3, "location"
        )  # location was set before status_effects


def test_within_advanced_historical_scenarios():
    """Test advanced historical lookup capabilities."""
    sid, pid = setup()

    # Create complex history with multiple state changes
    t.materialize(pid).game_state = "menu"
    t.materialize(pid).player_action = "start_game"
    t.materialize(pid).timestamp = 1000

    t.materialize(pid).game_state = "playing"
    t.materialize(pid).player_action = "move_north"
    t.materialize(pid).timestamp = 2000

    t.materialize(pid).game_state = "combat"
    t.materialize(pid).player_action = "attack"
    t.materialize(pid).timestamp = 3000

    t.materialize(pid).game_state = "playing"
    t.materialize(pid).player_action = "move_south"
    t.materialize(pid).timestamp = 4000

    t.materialize(pid).game_state = "inventory"
    t.materialize(pid).player_action = "use_potion"
    t.materialize(pid).timestamp = 5000

    with t.materialize(pid) as player:
        # Can look up any historical game state
        menu_ctx = player.within(game_state="menu")
        assert menu_ctx.game_state == "menu"
        assert menu_ctx.player_action == "start_game"
        assert menu_ctx.timestamp == 1000

        combat_ctx = player.within(game_state="combat")
        assert combat_ctx.game_state == "combat"
        assert combat_ctx.player_action == "attack"
        assert combat_ctx.timestamp == 3000

        # Current state
        current_ctx = player.within(game_state="inventory")
        assert current_ctx.game_state == "inventory"
        assert current_ctx.player_action == "use_potion"
        assert current_ctx.timestamp == 5000

        # Most recent "playing" state
        playing_ctx = player.within(game_state="playing")
        assert playing_ctx.game_state == "playing"
        assert playing_ctx.player_action == "move_south"  # Most recent playing action
        assert playing_ctx.timestamp == 4000  # Most recent playing timestamp


def test_within_carryover_values():
    """Test that within correctly handles temporal ordering constraint."""
    sid, pid = setup()

    # Scenario: field1 set before context conditions are met
    t.materialize(pid).field1 = 42  # t=0: field1 is set to 42
    t.materialize(pid).ctx1 = 1  # t=1: ctx1 is set to 1
    t.materialize(pid).ctx2 = 2  # t=2: ctx2 is set to 2 (context now satisfied)

    with t.materialize(pid) as player:
        # With temporal ordering constraint, field1 was set before context fields
        within_ctx = player.within(ctx1=1, ctx2=2)

        # Direct access should raise AttributeError
        expect_attribute_error(within_ctx, "field1")

        # But .get() should return default gracefully
        assert within_ctx.get("field1", "DEFAULT") == "DEFAULT"

        # Context fields should still be accessible
        assert within_ctx.ctx1 == 1  # Context value from t=1
        assert within_ctx.ctx2 == 2  # Context value from t=2


def test_within_multiple_context_windows():
    """Test within behavior when context is satisfied multiple times."""
    sid, pid = setup()

    # First context window
    t.materialize(pid).field1 = 42
    t.materialize(pid).ctx1 = 1
    t.materialize(pid).ctx2 = 2  # Context satisfied: field1=42

    # Break the context
    t.materialize(pid).ctx1 = 0  # Context no longer satisfied

    # Change field1 while context is broken
    t.materialize(pid).field1 = 100

    # Restore context - creates second context window
    t.materialize(pid).ctx1 = 1  # Context satisfied again: field1=100

    with t.materialize(pid) as player:
        # With temporal constraint, field1=100 was set before ctx1 was restored
        within_ctx = player.within(ctx1=1, ctx2=2)
        expect_attribute_error(
            within_ctx, "field1"
        )  # field1 was set before the final ctx1 restoration
        assert within_ctx.ctx1 == 1
        assert within_ctx.ctx2 == 2


def test_within_context_never_satisfied():
    """Test within behavior when context conditions are never satisfied."""
    sid, pid = setup()

    t.materialize(pid).field1 = 42
    t.materialize(pid).ctx1 = 1
    t.materialize(pid).ctx2 = 3  # ctx2=3, but we'll look for ctx2=2

    with t.materialize(pid) as player:
        # Context ctx1=1, ctx2=2 is never satisfied
        within_ctx = player.within(ctx1=1, ctx2=2)
        expect_attribute_error(
            within_ctx, "field1"
        )  # No value found in non-existent context
        expect_attribute_error(within_ctx, "ctx1")
        expect_attribute_error(within_ctx, "ctx2")


def test_within_context_changes_back_single_field():
    """Test that within only returns data from the LATEST context window when context changes back.

    This is the critical test that distinguishes between:
    - Early filtering: returns data from ANY matching context window
    - Late filtering: returns data only from the LATEST matching context window

    We use the late filtering approach for "within" semantics.
    """
    sid, pid = setup()

    # First context window: ctx1=1
    t.materialize(pid).ctx1 = 1  # t=0
    t.materialize(pid).field1 = 42  # t=1: field1 recorded during first ctx1=1 period

    # Context changes
    t.materialize(pid).ctx1 = 2  # t=2: context no longer ctx1=1

    # Second context window: ctx1=1 (changes back)
    t.materialize(pid).ctx1 = 1  # t=3: context returns to ctx1=1

    with t.materialize(pid) as player:
        # Query for ctx1=1 should only consider the LATEST ctx1=1 window (at t=3)
        # field1=42 was set during the first ctx1=1 window (at t=1)
        # At t=3, ctx1 was set at t=3, field1 was set at t=1
        # Since ctx1 time (3) > field1 time (1), field1 should be excluded
        within_ctx = player.within(ctx1=1)
        expect_attribute_error(
            within_ctx, "field1"
        )  # field1 from first window should not be visible
        assert within_ctx.ctx1 == 1  # But ctx1 itself should be accessible


def test_within_context_changes_back_with_new_data():
    """Test that data set in the LATEST context window IS visible."""
    sid, pid = setup()

    # First context window
    t.materialize(pid).ctx1 = 1  # t=0
    t.materialize(pid).field1 = 42  # t=1: old data from first window

    # Context changes
    t.materialize(pid).ctx1 = 2  # t=2

    # Second context window with new data
    t.materialize(pid).ctx1 = 1  # t=3: context returns to ctx1=1
    t.materialize(pid).field1 = 100  # t=4: NEW data set during second ctx1=1 window

    with t.materialize(pid) as player:
        within_ctx = player.within(ctx1=1)
        # field1=100 was set at t=4, ctx1 was set at t=3
        # Since ctx1 time (3) < field1 time (4), field1 should be included
        assert within_ctx.field1 == 100  # Latest data is visible
        assert within_ctx.ctx1 == 1


def test_within_context_changes_back_multiple_fields():
    """Test temporal constraint with multiple context fields that change back."""
    sid, pid = setup()

    # First context window
    t.materialize(pid).ctx1 = 1  # t=0
    t.materialize(pid).ctx2 = 2  # t=1
    t.materialize(pid).field1 = 42  # t=2: data from first window
    t.materialize(pid).field2 = 100  # t=3: more data from first window

    # Break context
    t.materialize(pid).ctx1 = 5  # t=4

    # Restore context
    t.materialize(pid).ctx1 = 1  # t=5: ctx1 back to 1 (ctx2 still 2)
    t.materialize(pid).field3 = 200  # t=6: new data in restored context

    with t.materialize(pid) as player:
        within_ctx = player.within(ctx1=1, ctx2=2)

        # field1 and field2 were set before the latest ctx1 restoration
        # ctx1 latest time is t=5, field1 time is t=2, field2 time is t=3
        expect_attribute_error(within_ctx, "field1")  # Old data excluded
        expect_attribute_error(within_ctx, "field2")  # Old data excluded

        # field3 was set after the latest ctx1 restoration
        # ctx1 time is t=5, field3 time is t=6
        assert within_ctx.field3 == 200  # New data included

        # Context fields themselves are always accessible
        assert within_ctx.ctx1 == 1
        assert within_ctx.ctx2 == 2


def test_within_complex_temporal_scenarios():
    """Test within with complex temporal sequences and temporal constraint enforcement."""
    sid, pid = setup()

    # Complex scenario with multiple field changes and context windows
    t.materialize(pid).base_value = "initial"
    t.materialize(pid).counter = 0

    t.materialize(pid).state = "A"
    t.materialize(pid).mode = 1
    t.materialize(pid).counter = (
        1  # Context: state=A, mode=1, counter=1, base_value="initial"
    )

    t.materialize(pid).base_value = "updated"
    t.materialize(pid).counter = (
        2  # Context: state=A, mode=1, counter=2, base_value="updated"
    )

    t.materialize(pid).state = "B"  # Break context
    t.materialize(pid).counter = 3

    t.materialize(pid).state = "A"  # Restore context (state set at this point)
    t.materialize(pid).counter = 4  # Context: state=A, mode=1, counter=4
    t.materialize(pid).base_value = "final"  # Set AFTER context restoration

    with t.materialize(pid) as player:
        # Find state when state=A and mode=1 were both true
        within_ctx = player.within(state="A", mode=1)

        # Should get the latest values from when context was satisfied
        assert within_ctx.state == "A"
        assert within_ctx.mode == 1
        assert within_ctx.counter == 4  # Latest counter when context was satisfied
        assert (
            within_ctx.base_value == "final"
        )  # Only values set AFTER latest context restoration are visible


def test_within_string_representations():
    sid, pid = setup()

    t.materialize(pid).test_field = "value"

    with t.materialize(pid) as player:
        within_ctx = player.within(test_field="value")

        # Test that within object behaves reasonably
        assert within_ctx.test_field == "value"

        # Access non-existent field
        expect_attribute_error(within_ctx, "nonexistent")


def test_within_multiple_context_fields_temporal_logic():
    """Test multiple context fields with complex temporal sequences and temporal constraint."""
    sid, pid = setup()

    # Create a temporal sequence where context conditions are satisfied at different times
    t.materialize(pid).field_a = "value_a1"
    t.materialize(pid).field_b = "value_b1"
    t.materialize(pid).target = "target1"

    # Change field_a, breaking the context
    t.materialize(pid).field_a = "value_a2"
    t.materialize(pid).target = "target2"

    # Restore field_a - this creates a NEW context window for field_a="value_a1", field_b="value_b1"
    t.materialize(pid).field_a = (
        "value_a1"  # Context restored here (latest establishment point)
    )
    # target was last set BEFORE this restoration, so it won't be visible with temporal constraint

    with t.materialize(pid) as player:
        # Context field_a="value_a1", field_b="value_b1" is restored at the point where field_a is set back
        # Since target was set BEFORE field_a was restored, target is NOT visible (temporal constraint)
        within_ctx1 = player.within(field_a="value_a1", field_b="value_b1")
        assert within_ctx1.field_a == "value_a1"
        assert within_ctx1.field_b == "value_b1"
        # target was set before the latest field_a restoration, so it's excluded by temporal constraint
        expect_attribute_error(within_ctx1, "target")

    # Now test with data set AFTER context restoration
    t.materialize(pid).target = "target4"  # Set after field_a restoration

    with t.materialize(pid) as player:
        within_ctx2 = player.within(field_a="value_a1", field_b="value_b1")
        assert (
            within_ctx2.target == "target4"
        )  # Now visible because set after context restoration

    # Change field_b, creating a different context
    t.materialize(pid).field_b = "value_b2"
    t.materialize(pid).target = "target3"

    with t.materialize(pid) as player:
        # Context field_a="value_a1", field_b="value_b2" is satisfied currently
        within_ctx3 = player.within(field_a="value_a1", field_b="value_b2")
        assert within_ctx3.field_a == "value_a1"
        assert within_ctx3.field_b == "value_b2"
        assert within_ctx3.target == "target3"  # Target from current context window


def test_within_context_field_does_not_exist():
    """Test within behavior when a context field was never set."""
    sid, pid = setup()

    t.materialize(pid).existing_field = "value"
    # never_set_field is never set

    with t.materialize(pid) as player:
        # Context with a field that was never set should work gracefully
        within_ctx = player.within(never_set_field="any_value")

        # When context field doesn't exist, all field access returns None
        expect_attribute_error(within_ctx, "existing_field")
        expect_attribute_error(within_ctx, "never_set_field")


def test_within_empty_context_equivalence():
    """Test that empty context behaves like normal field access."""
    sid, pid = setup()

    t.materialize(pid).field1 = "value1"
    t.materialize(pid).field2 = "value2"

    with t.materialize(pid) as player:
        # Empty context should be equivalent to normal access
        within_ctx = player.within()

        assert within_ctx.field1 == "value1"
        assert within_ctx.field2 == "value2"

        # Should be equivalent to direct access
        assert within_ctx.field1 == player.field1
        assert within_ctx.field2 == player.field2


def test_along_with_temporal_constraints():
    """Test that .along() correctly applies temporal constraints in each context window."""
    sid, pid = setup()

    # Create a sequence where context field changes multiple times
    # and we have data associated with each context value
    t.materialize(pid).level = 1
    t.materialize(pid).score = 100  # score set when level=1

    t.materialize(pid).level = 2
    t.materialize(pid).score = 200  # score set when level=2

    t.materialize(pid).level = 1  # level changes back to 1
    t.materialize(pid).hp = 50  # hp set when level=1 (second time)

    t.materialize(pid).level = 3
    t.materialize(pid).score = 300  # score set when level=3

    with t.materialize(pid) as player:
        # Iterate through level history using .along()
        level_contexts = {}
        for level_value, within_ctx in player.along("level"):
            level_contexts[level_value] = within_ctx

        # Check level=1 context
        # The .along() will create within(level=1), which should use the LATEST level=1 window
        # At the latest level=1 window, score was 200 (set before level changed back to 1)
        # So score should NOT be visible due to temporal constraint
        assert level_contexts[1].level == 1
        expect_attribute_error(
            level_contexts[1], "score"
        )  # score=200 was set before latest level=1
        assert level_contexts[1].hp == 50  # hp was set during latest level=1 window

        # Check level=2 context
        assert level_contexts[2].level == 2
        assert level_contexts[2].score == 200  # score was set when level=2

        # Check level=3 context
        assert level_contexts[3].level == 3
        assert level_contexts[3].score == 300  # score was set when level=3


def test_along_with_multiple_context_changes():
    """Test .along() behavior when the along field changes back and forth."""
    sid, pid = setup()

    # Create alternating pattern: A -> B -> A -> B
    t.materialize(pid).state = "A"
    t.materialize(pid).data1 = "a1"

    t.materialize(pid).state = "B"
    t.materialize(pid).data2 = "b1"

    t.materialize(pid).state = "A"
    t.materialize(pid).data3 = "a2"

    t.materialize(pid).state = "B"
    t.materialize(pid).data4 = "b2"

    with t.materialize(pid) as player:
        state_contexts = {}
        for state_value, within_ctx in player.along("state"):
            # Store the latest context for each state value
            # (along will visit each historical value, but we only keep the last one)
            state_contexts[state_value] = within_ctx

        # For state="A": along creates within(state="A")
        # This uses the LATEST state="A" window (from the 3rd occurrence)
        # data1 was set when state="A" first time, should NOT be visible (temporal constraint)
        # data3 was set when state="A" second time, SHOULD be visible
        assert state_contexts["A"].state == "A"
        expect_attribute_error(
            state_contexts["A"], "data1"
        )  # From first A window, excluded
        assert state_contexts["A"].data3 == "a2"  # From latest A window, included

        # For state="B": along creates within(state="B")
        # This uses the LATEST state="B" window (from the 4th occurrence)
        assert state_contexts["B"].state == "B"
        expect_attribute_error(
            state_contexts["B"], "data2"
        )  # From first B window, excluded
        assert state_contexts["B"].data4 == "b2"  # From latest B window, included


def test_storage_repr():
    admin = s.Admin()
    assert repr(admin) == "Admin()"

    session = s.Session("test")
    assert repr(session) == "Session(*('test',))"

    player = s.Player("test", "user")
    assert repr(player) == "Player(*('test', 'user'))"
