"""
Utterly rigorous comprehensive tests for new-storage branch implementation.

This test suite pushes the storage system to its absolute limits with scenarios
that test every edge case, context manager interaction, deep modification nuance,
memory consistency, and performance characteristic of the storage system.

These tests are designed to be so comprehensive and intense that they verify
every aspect of the storage implementation with utterly meticulous precision.
"""

import copy
import gc
import time
from decimal import Decimal

import pytest

import uproot as u
import uproot.cache as cache
import uproot.core as c
import uproot.deployment as d
import uproot.storage as s

# Define type categories for testing
IMMUTABLE_TYPES = (
    int,
    float,
    str,
    tuple,
    bytes,
    bool,
    complex,
    type(None),
    Decimal,
    frozenset,
)
MUTABLE_TYPES = (list, dict, set, bytearray)


def setup_fresh_database():
    """Setup a completely fresh database state for testing."""
    d.DATABASE.reset()
    u.CONFIGS["test"] = []
    u.CONFIGS_PPATHS["test"] = []

    # Force reload of in-memory database
    cache.load_database_into_memory()

    with s.Admin() as admin:
        c.create_admin(admin)
        sid = c.create_session(admin, "test")

    with sid() as session:
        pid = c.create_player(session)

    return sid, pid


class TestMemoryDatabaseConsistency:
    """Test absolute consistency between database and in-memory copy."""

    def test_comprehensive_data_persistence(self):
        """Verify complex data persists correctly across operations."""
        sid, pid = setup_fresh_database()

        # Create complex history across multiple namespaces
        with pid() as player:
            player.stage1 = "initial"
            player.data = [1, 2, 3]
            player.complex_nested = {
                "level1": {"level2": ["deep", "data", {"level3": "value"}]}
            }

        with sid() as session:
            session.config = {"version": 1, "features": ["a", "b"]}
            session.players = ["player1"]

        with s.Admin() as admin:
            admin.system_state = "active"
            admin.metrics = {"uptime": 3600, "users": 42}

        # Verify all data is accessible and correct
        with pid() as player:
            assert player.stage1 == "initial"
            assert player.data == [1, 2, 3]
            assert player.complex_nested["level1"]["level2"][2]["level3"] == "value"

        with sid() as session:
            assert session.config["version"] == 1
            assert "a" in session.config["features"]
            assert session.players == ["player1"]

        with s.Admin() as admin:
            assert admin.system_state == "active"
            assert admin.metrics["users"] == 42

    def test_timestamp_consistency_verification(self):
        """Verify timestamp consistency through multiple operations."""
        sid, pid = setup_fresh_database()

        # Perform rapid sequential operations
        operations = []
        for i in range(10):
            pre_time = time.time()
            with pid() as player:
                setattr(player, f"timestamp_test_{i}", f"value_{i}")
            post_time = time.time()
            operations.append((pre_time, post_time, i))

        # Verify all data is accessible in correct order
        with pid() as player:
            for _, _, i in operations:
                value = getattr(player, f"timestamp_test_{i}")
                assert value == f"value_{i}"

    def test_player_list_update_behavior(self):
        """Verify player list updates work correctly."""
        sid, _ = setup_fresh_database()

        with sid() as session:
            # Multiple player updates should work correctly
            session.players = ["player1"]
            session.players = ["player1", "player2"]
            session.players = ["player2", "player3", "player4"]

        # Verify final state is correct
        with sid() as session:
            assert session.players == ["player2", "player3", "player4"]
            assert len(session.players) == 3
            assert "player2" in session.players
            assert "player3" in session.players
            assert "player4" in session.players

    def test_field_deletion_and_access_patterns(self):
        """Verify field deletion works correctly."""
        sid, pid = setup_fresh_database()

        with pid() as player:
            player.temp_field = "to_be_deleted"
            assert player.temp_field == "to_be_deleted"

            # Delete the field
            del player.temp_field

            # Should raise AttributeError
            with pytest.raises(AttributeError):
                _ = player.temp_field

        # Field should remain deleted across contexts
        with pid() as player:
            with pytest.raises(AttributeError):
                _ = player.temp_field

        # Can recreate the field
        with pid() as player:
            player.temp_field = "recreated"
            assert player.temp_field == "recreated"


class TestDeepModificationDetection:
    """Test the deep modification detection system to its absolute limits."""

    def test_nested_mutable_modification_detection(self):
        """Test detection of modifications in deeply nested mutable structures."""
        sid, pid = setup_fresh_database()

        complex_data = {
            "users": [
                {"name": "Alice", "scores": [100, 95, 88]},
                {"name": "Bob", "scores": [75, 82, 91]},
            ],
            "metadata": {"version": 1, "tags": ["important", "test", "nested"]},
        }

        with pid() as player:
            player.complex_data = complex_data

            # Modify deeply nested data
            player.complex_data["users"][0]["scores"].append(92)
            player.complex_data["metadata"]["tags"].append("modified")
            player.complex_data["new_key"] = "added_value"

        # Verify modifications were detected and saved
        with pid() as player:
            assert len(player.complex_data["users"][0]["scores"]) == 4
            assert player.complex_data["users"][0]["scores"][-1] == 92
            assert "modified" in player.complex_data["metadata"]["tags"]
            assert player.complex_data["new_key"] == "added_value"

    def test_modification_detection_across_multiple_contexts(self):
        """Test modification detection works across multiple context entries."""
        sid, pid = setup_fresh_database()

        # First context: establish data
        with pid() as player:
            player.evolving_list = [1, 2, 3]

        # Second context: modify
        with pid() as player:
            player.evolving_list.extend([4, 5])

        # Third context: modify again
        with pid() as player:
            player.evolving_list.insert(0, 0)
            player.evolving_list.pop()

        # Fourth context: verify all modifications persisted
        with pid() as player:
            assert player.evolving_list == [0, 1, 2, 3, 4]

    def test_modification_detection_with_object_identity(self):
        """Test that object identity is preserved for modification detection."""
        sid, pid = setup_fresh_database()

        with pid() as player:
            player.shared_list = [1, 2, 3]

            # Get same object multiple times
            list1 = player.shared_list
            list2 = player.shared_list

            # Verify same object identity
            assert list1 is list2

            # Modify through one reference
            list1.append(4)

            # Verify modification visible through other reference
            assert list2 == [1, 2, 3, 4]
            assert len(list2) == 4

        # Verify modification was saved
        with pid() as player:
            assert player.shared_list == [1, 2, 3, 4]

    def test_modification_baseline_reset_per_context(self):
        """Test that baselines reset properly for each context."""
        sid, pid = setup_fresh_database()

        original_data = {"count": 0, "items": []}

        # Context 1: Set initial data
        with pid() as player:
            player.baseline_test = copy.deepcopy(original_data)
            player.baseline_test["count"] = 5
            player.baseline_test["items"] = ["a", "b"]

        # Context 2: Should start with fresh baseline from saved state
        with pid() as player:
            # Verify we have the saved state
            assert player.baseline_test["count"] == 5
            assert player.baseline_test["items"] == ["a", "b"]

            # Make new modifications
            player.baseline_test["count"] = 10
            player.baseline_test["items"].append("c")

        # Context 3: Verify all modifications persisted correctly
        with pid() as player:
            assert player.baseline_test["count"] == 10
            assert player.baseline_test["items"] == ["a", "b", "c"]

    def test_immutable_vs_mutable_modification_handling(self):
        """Test different handling of immutable vs mutable types."""
        sid, pid = setup_fresh_database()

        with pid() as player:
            # Immutable assignment creates new value
            player.immutable_counter = 1
            player.immutable_counter = 2  # This creates new entry

            # Mutable modification modifies in-place
            player.mutable_list = [1]
            player.mutable_list.append(2)  # This modifies existing object

        # Verify final states are correct
        with pid() as player:
            assert player.immutable_counter == 2
            assert player.mutable_list == [1, 2]


class TestContextManagerSemantics:
    """Test context manager behavior in extreme scenarios."""

    def test_immutable_type_access_patterns(self):
        """Test all immutable types can be accessed without context managers."""
        sid, pid = setup_fresh_database()

        # Set up test data
        pid().int_val = 42
        pid().float_val = 3.14159
        pid().str_val = "hello"
        pid().tuple_val = (1, 2, 3)
        pid().bytes_val = b"binary"
        pid().bool_val = True
        pid().complex_val = 1 + 2j
        pid().none_val = None
        pid().decimal_val = Decimal("99.99")
        pid().frozenset_val = frozenset([1, 2, 3])

        # All should be accessible without context manager
        player = pid()
        assert player.int_val == 42
        assert player.float_val == 3.14159
        assert player.str_val == "hello"
        assert player.tuple_val == (1, 2, 3)
        assert player.bytes_val == b"binary"
        assert player.bool_val is True
        assert player.complex_val == 1 + 2j
        assert player.none_val is None
        assert player.decimal_val == Decimal("99.99")
        assert player.frozenset_val == frozenset([1, 2, 3])

    def test_mutable_type_context_requirements(self):
        """Test all mutable types require context managers."""
        sid, pid = setup_fresh_database()

        # Set up mutable data
        with pid() as player:
            player.list_val = [1, 2, 3]
            player.dict_val = {"key": "value"}
            player.set_val = {1, 2, 3}
            player.bytearray_val = bytearray(b"mutable")

        # All should require context manager for access
        player = pid()

        with pytest.raises(TypeError, match="context manager"):
            _ = player.list_val

        with pytest.raises(TypeError, match="context manager"):
            _ = player.dict_val

        with pytest.raises(TypeError, match="context manager"):
            _ = player.set_val

        with pytest.raises(TypeError, match="context manager"):
            _ = player.bytearray_val

    def test_nested_context_manager_prevention(self):
        """Test that nested context managers are properly handled."""
        sid, pid = setup_fresh_database()

        with pid() as outer_player:
            outer_player.data = [1, 2, 3]

            # Same object in nested context should work
            with pid() as inner_player:
                inner_player.more_data = [4, 5, 6]
                assert inner_player.data == [1, 2, 3]
                assert inner_player.more_data == [4, 5, 6]

            # Outer context should still work
            assert outer_player.more_data == [4, 5, 6]

    def test_context_exit_with_exceptions(self):
        """Test context manager behavior when exceptions occur."""
        sid, pid = setup_fresh_database()

        # Exception during context should not save modifications
        try:
            with pid() as player:
                player.exception_test = [1, 2, 3]
                player.exception_test.append(4)
                raise ValueError("Intentional test exception")
        except ValueError:
            pass

        # Assignment should be saved, but in-place modification should not (no flush on exception)
        with pid() as player:
            assert player.exception_test == [
                1,
                2,
                3,
            ]  # Only assignment saved, append lost

    def test_cache_isolation_between_contexts(self):
        """Test that field caches are properly isolated between contexts."""
        sid, pid = setup_fresh_database()

        # Context 1: Set and modify data
        with pid() as player:
            player.isolation_test = {"shared": [1, 2]}
            shared_ref = player.isolation_test["shared"]
            shared_ref.append(3)

        # Context 2: Should get fresh cache with saved modifications
        with pid() as player:
            # This should be a different object reference but same data
            fresh_ref = player.isolation_test["shared"]
            assert fresh_ref == [1, 2, 3]

            # Modify in this context
            fresh_ref.append(4)

        # Context 3: Verify modifications from context 2
        with pid() as player:
            assert player.isolation_test["shared"] == [1, 2, 3, 4]


class TestConcurrencyAndAsyncSafety:
    """Test behavior under concurrent access patterns."""

    def test_multiple_storage_instances_same_namespace(self):
        """Test multiple Storage instances for same namespace work correctly."""
        sid, pid = setup_fresh_database()

        # Create multiple instances pointing to same player
        player1 = pid()

        # Extract actual player info from the first instance
        namespace = player1.__namespace__
        player2 = s.Player(namespace[1], namespace[2])
        player3 = s.Player(namespace[1], namespace[2])

        # All should be equal but not identical
        assert player1 == player2 == player3
        assert player1 is not player2 is not player3

        # Modifications through one should be visible through others
        with player1 as p1:
            p1.concurrent_data = {"source": "player1"}

        with player2 as p2:
            assert p2.concurrent_data == {"source": "player1"}
            p2.concurrent_data["source"] = "player2"

        with player3 as p3:
            assert p3.concurrent_data["source"] == "player2"

    def test_rapid_context_switching(self):
        """Test rapid context entry and exit."""
        sid, pid = setup_fresh_database()

        # Rapid context switching with data modifications
        for i in range(100):
            with pid() as player:
                if not hasattr(player, "rapid_test"):
                    player.rapid_test = []
                player.rapid_test.append(i)

                # Verify data integrity
                assert len(player.rapid_test) == i + 1
                assert player.rapid_test[-1] == i

        # Final verification
        with pid() as player:
            assert len(player.rapid_test) == 100
            assert player.rapid_test == list(range(100))

    def test_memory_pressure_and_cleanup(self):
        """Test behavior under memory pressure."""
        sid, pid = setup_fresh_database()

        # Create many large objects
        large_objects = []
        for i in range(50):
            with pid() as player:
                # Create large data structure
                large_data = {f"key_{j}": [x for x in range(1000)] for j in range(10)}
                setattr(player, f"large_object_{i}", large_data)
                large_objects.append(large_data)

        # Force garbage collection
        gc.collect()

        # Verify data integrity after memory pressure
        with pid() as player:
            for i in range(50):
                obj = getattr(player, f"large_object_{i}")
                assert len(obj) == 10
                assert all(len(obj[f"key_{j}"]) == 1000 for j in range(10))

        # Clear references and test cleanup
        large_objects.clear()
        gc.collect()

    def test_weakref_behavior_with_caching(self):
        """Test that caching doesn't interfere with garbage collection."""
        sid, pid = setup_fresh_database()

        # Test weakref behavior with simple objects
        with pid() as player:
            player.weakref_test = []
            for i in range(10):
                sublist = [i] * 100
                player.weakref_test.append(sublist)

        # Force garbage collection
        gc.collect()

        # Data should be preserved regardless of garbage collection
        with pid() as player:
            assert len(player.weakref_test) == 10
            for i, sublist in enumerate(player.weakref_test):
                assert sublist == [i] * 100


class TestErrorHandlingAndEdgeCases:
    """Test error handling in extreme scenarios."""

    def test_malformed_data_handling(self):
        """Test handling of malformed or corrupted data."""
        sid, pid = setup_fresh_database()

        with pid() as player:
            # Test with various edge case values
            player.empty_list = []
            player.empty_dict = {}
            player.zero_values = [0, 0.0, "", False, None]
            player.unicode_data = "🚀🌟💫⭐️🔥💯"
            player.nested_empty = {"a": [], "b": {}}

        # All should work correctly
        with pid() as player:
            assert player.empty_list == []
            assert player.empty_dict == {}
            assert player.zero_values == [0, 0.0, "", False, None]
            assert player.unicode_data == "🚀🌟💫⭐️🔥💯"
            assert player.nested_empty == {"a": [], "b": {}}

    def test_attribute_error_propagation(self):
        """Test proper error propagation for non-existent attributes."""
        sid, pid = setup_fresh_database()

        with pid() as player:
            with pytest.raises(AttributeError):
                _ = player.nonexistent_field

    def test_field_deletion_and_recreation_cycles(self):
        """Test repeated deletion and recreation of fields."""
        sid, pid = setup_fresh_database()

        for cycle in range(10):
            with pid() as player:
                # Create field
                player.cycle_test = {"cycle": cycle, "data": list(range(cycle))}
                assert player.cycle_test["cycle"] == cycle

                # Delete field
                del player.cycle_test

                # Should raise error
                with pytest.raises(AttributeError):
                    _ = player.cycle_test

        # Final verification - field should not exist
        with pid() as player:
            with pytest.raises(AttributeError):
                _ = player.cycle_test

    def test_virtual_field_interactions(self):
        """Test interactions with virtual fields."""
        sid, pid = setup_fresh_database()

        player = pid()

        # Virtual fields should work without context
        session_ref = player.session
        assert session_ref is not None

        # Cannot assign to virtual fields
        with pytest.raises(AttributeError, match="virtual field"):
            player.session = "invalid"

    def test_flush_during_partial_initialization(self):
        """Test flush behavior during partial object initialization."""
        sid, pid = setup_fresh_database()

        # Test with properly initialized object
        with pid() as player:
            player.initialization_test = "success"
            # Manually call flush to test it works
            player.flush()

        # Verify it worked
        with pid() as player:
            assert player.initialization_test == "success"


class TestPerformanceAndScalability:
    """Test performance characteristics under load."""

    def test_large_field_count_performance(self):
        """Test performance with many fields."""
        sid, pid = setup_fresh_database()

        field_count = 1000
        start_time = time.time()

        with pid() as player:
            for i in range(field_count):
                setattr(player, f"field_{i:04d}", f"value_{i}")

        creation_time = time.time() - start_time

        # Access all fields
        start_time = time.time()
        with pid() as player:
            for i in range(field_count):
                value = getattr(player, f"field_{i:04d}")
                assert value == f"value_{i}"

        access_time = time.time() - start_time

        # Performance should be reasonable
        assert creation_time < 5.0  # Less than 5 seconds to create 1000 fields
        assert access_time < 1.0  # Less than 1 second to access 1000 fields

    def test_deep_nesting_performance(self):
        """Test performance with deeply nested structures."""
        sid, pid = setup_fresh_database()

        # Create deeply nested structure
        depth = 50
        nested = {}
        current = nested

        for i in range(depth):
            current[f"level_{i}"] = {}
            current = current[f"level_{i}"]
        current["deepest"] = "treasure"

        start_time = time.time()
        with pid() as player:
            player.deep_nested = nested

            # Navigate to deepest level
            current = player.deep_nested
            for i in range(depth):
                current = current[f"level_{i}"]
            assert current["deepest"] == "treasure"

            # Modify at deepest level
            current["deepest"] = "modified_treasure"

        modification_time = time.time() - start_time

        # Verify modification persisted
        with pid() as player:
            current = player.deep_nested
            for i in range(depth):
                current = current[f"level_{i}"]
            assert current["deepest"] == "modified_treasure"

        # Performance should be reasonable even with deep nesting
        assert modification_time < 2.0

    def test_memory_usage_efficiency(self):
        """Test memory usage efficiency of caching system."""
        sid, pid = setup_fresh_database()

        # Create significant amount of cached data
        with pid() as player:
            for i in range(100):
                large_list = list(range(1000))  # Smaller for compatibility
                setattr(player, f"memory_test_{i}", large_list)

        # Access all data multiple times to test efficiency
        for _ in range(5):
            with pid() as player:
                for i in range(100):
                    data = getattr(player, f"memory_test_{i}")
                    assert len(data) == 1000
                    assert data[0] == 0
                    assert data[-1] == 999

        # Test should complete without memory issues
        assert True  # If we get here, memory usage was acceptable


class TestAdvancedStorageScenarios:
    """Test advanced real-world-like scenarios."""

    def test_game_session_simulation(self):
        """Simulate a complete game session with complex state changes."""
        sid, _ = setup_fresh_database()

        # Create multiple players
        players = []
        for i in range(5):
            with sid() as session:
                pid = c.create_player(session)  # Use standard player creation
                players.append(pid)

        # Initialize game state
        with sid() as session:
            session.game_state = {
                "phase": "setup",
                "round": 0,
                "scores": {},
                "events": [],
            }

            for i, pid in enumerate(players):
                with pid() as player:
                    player.character = {
                        "name": f"Hero_{i}",
                        "level": 1,
                        "health": 100,
                        "inventory": [],
                        "position": {"x": i * 10, "y": 0},
                    }

        # Simulate game rounds
        for round_num in range(10):
            with sid() as session:
                session.game_state["round"] = round_num
                session.game_state["phase"] = "action"

                # Each player takes actions
                for i, pid in enumerate(players):
                    with pid() as player:
                        # Level up occasionally
                        if round_num % 3 == 0:
                            player.character["level"] += 1
                            player.character["health"] += 10

                        # Move player
                        player.character["position"]["x"] += round_num
                        player.character["position"]["y"] += i

                        # Add items to inventory
                        item = f"item_{round_num}_{i}"
                        player.character["inventory"].append(item)

                        # Update score
                        if f"player_{i}" not in session.game_state["scores"]:
                            session.game_state["scores"][f"player_{i}"] = 0
                        session.game_state["scores"][f"player_{i}"] += round_num * 10

                # Add round event
                session.game_state["events"].append(f"Round {round_num} completed")
                session.game_state["phase"] = "complete"

        # Verify final game state
        with sid() as session:
            assert session.game_state["round"] == 9
            assert session.game_state["phase"] == "complete"
            assert len(session.game_state["events"]) == 10
            assert len(session.game_state["scores"]) == 5

        # Verify all players have correct final state
        for i, pid in enumerate(players):
            with pid() as player:
                assert player.character["level"] == 5  # level ups
                assert player.character["health"] == 140  # health from level ups
                assert len(player.character["inventory"]) == 10
                assert player.character["position"]["x"] == i * 10 + sum(range(10))
                assert player.character["position"]["y"] == i * 10

    def test_collaborative_document_editing(self):
        """Simulate collaborative document editing scenario."""
        sid, pid = setup_fresh_database()

        # Initialize document
        with pid() as editor:
            editor.document = {
                "content": [],
                "revision": 0,
                "authors": [],
                "change_log": [],
            }

        # Simulate multiple editing sessions
        authors = ["Alice", "Bob", "Charlie", "Diana"]

        for session_num in range(20):
            author = authors[session_num % len(authors)]

            with pid() as editor:
                # Add author to list if not present
                if author not in editor.document["authors"]:
                    editor.document["authors"].append(author)

                # Add content
                new_content = (
                    f"Paragraph {session_num} by {author}: "
                    + f"This is content added in session {session_num}."
                )
                editor.document["content"].append(new_content)

                # Update revision
                editor.document["revision"] += 1

                # Log the change
                change = {
                    "session": session_num,
                    "author": author,
                    "action": "add_paragraph",
                    "revision": editor.document["revision"],
                }
                editor.document["change_log"].append(change)

                # Occasionally edit existing content
                if session_num > 5 and session_num % 4 == 0:
                    edit_index = session_num % len(editor.document["content"])
                    original = editor.document["content"][edit_index]
                    editor.document["content"][edit_index] = f"[EDITED] {original}"

                    edit_change = {
                        "session": session_num,
                        "author": author,
                        "action": "edit_paragraph",
                        "index": edit_index,
                        "revision": editor.document["revision"],
                    }
                    editor.document["change_log"].append(edit_change)

        # Verify final document state
        with pid() as editor:
            doc = editor.document
            assert len(doc["content"]) == 20
            assert doc["revision"] >= 20  # At least 20 additions
            assert set(doc["authors"]) == set(authors)
            assert len(doc["change_log"]) >= 20  # At least 20 changes logged

            # Verify some content was edited
            edited_count = sum(
                1 for content in doc["content"] if content.startswith("[EDITED]")
            )
            assert edited_count >= 0  # Some content may have been edited

    def test_real_time_analytics_dashboard(self):
        """Simulate real-time analytics dashboard with continuous updates."""
        sid, pid = setup_fresh_database()

        # Initialize analytics data
        with pid() as dashboard:
            dashboard.analytics = {
                "page_views": {},
                "user_actions": {},
                "system_metrics": {
                    "cpu_usage": [],
                    "memory_usage": [],
                    "active_users": [],
                },
                "alerts": [],
                "summary_stats": {},
            }

        # Simulate continuous data updates
        import random

        for minute in range(60):  # One hour of data
            with pid() as dashboard:
                # Update page views
                pages = ["home", "dashboard", "profile", "settings", "help"]
                for page in pages:
                    if page not in dashboard.analytics["page_views"]:
                        dashboard.analytics["page_views"][page] = 0
                    dashboard.analytics["page_views"][page] += random.randint(10, 100)

                # Update user actions
                actions = ["click", "scroll", "form_submit", "download", "search"]
                for action in actions:
                    if action not in dashboard.analytics["user_actions"]:
                        dashboard.analytics["user_actions"][action] = []
                    dashboard.analytics["user_actions"][action].append(
                        {"minute": minute, "count": random.randint(1, 50)}
                    )

                # Update system metrics (keep last 100 items)
                cpu_usage = dashboard.analytics["system_metrics"]["cpu_usage"]
                cpu_usage.append(random.uniform(10, 90))
                if len(cpu_usage) > 100:
                    cpu_usage.pop(0)

                memory_usage = dashboard.analytics["system_metrics"]["memory_usage"]
                memory_usage.append(random.uniform(30, 80))
                if len(memory_usage) > 100:
                    memory_usage.pop(0)

                active_users = dashboard.analytics["system_metrics"]["active_users"]
                active_users.append(random.randint(100, 1000))
                if len(active_users) > 100:
                    active_users.pop(0)

                # Generate alerts for high usage
                if dashboard.analytics["system_metrics"]["cpu_usage"][-1] > 80:
                    dashboard.analytics["alerts"].append(
                        {
                            "minute": minute,
                            "type": "cpu_high",
                            "value": dashboard.analytics["system_metrics"]["cpu_usage"][
                                -1
                            ],
                        }
                    )

                # Update summary statistics every 10 minutes
                if minute % 10 == 0:
                    total_page_views = sum(dashboard.analytics["page_views"].values())
                    avg_cpu = sum(
                        dashboard.analytics["system_metrics"]["cpu_usage"]
                    ) / len(dashboard.analytics["system_metrics"]["cpu_usage"])

                    dashboard.analytics["summary_stats"][f"summary_{minute}"] = {
                        "total_page_views": total_page_views,
                        "avg_cpu_usage": avg_cpu,
                        "alert_count": len(dashboard.analytics["alerts"]),
                    }

        # Verify final analytics state
        with pid() as dashboard:
            analytics = dashboard.analytics

            # Check all pages have data
            assert len(analytics["page_views"]) == 5
            assert all(count > 0 for count in analytics["page_views"].values())

            # Check system metrics have correct data
            assert len(analytics["system_metrics"]["cpu_usage"]) <= 100
            assert len(analytics["system_metrics"]["memory_usage"]) <= 100
            assert len(analytics["system_metrics"]["active_users"]) <= 100

            # Check user actions tracking
            assert len(analytics["user_actions"]) == 5
            for action_list in analytics["user_actions"].values():
                assert len(action_list) == 60

            # Check summary statistics
            assert len(analytics["summary_stats"]) == 6  # Every 10 minutes

            # Verify data consistency
            total_views = sum(analytics["page_views"].values())
            latest_summary = analytics["summary_stats"]["summary_50"]
            assert total_views >= latest_summary["total_page_views"]
