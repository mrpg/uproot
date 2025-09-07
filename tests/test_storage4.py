from uproot.cache import load_database_into_memory
from uproot.storage import Storage
from uproot.types import Value


class TestHistoryCoherence:
    def setup_method(self):
        load_database_into_memory()

    def test_simple_types_history_coherence(self):
        storage = Storage("model", "testsession", "testmodel")

        with storage:
            storage.test_int = 42
            storage.test_str = "hello"
            storage.test_float = 3.14

        history = storage.__history__()

        assert "test_int" in history
        assert "test_str" in history
        assert "test_float" in history

        for value in history["test_int"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == 42
            assert value.time is not None
            assert isinstance(value.context, str)

        for value in history["test_str"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == "hello"
            assert value.time is not None
            assert isinstance(value.context, str)

        for value in history["test_float"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == 3.14
            assert value.time is not None
            assert isinstance(value.context, str)

    def test_mutable_types_history_coherence(self):
        storage = Storage("model", "testsession2", "testmodel2")

        with storage:
            storage.test_list = [1, 2, 3]
            storage.test_dict = {"key": "value"}
            storage.test_set = {1, 2, 3}

        history = storage.__history__()

        assert "test_list" in history
        assert "test_dict" in history
        assert "test_set" in history

        for value in history["test_list"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == [1, 2, 3]
            assert value.time is not None
            assert isinstance(value.context, str)

        for value in history["test_dict"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == {"key": "value"}
            assert value.time is not None
            assert isinstance(value.context, str)

        for value in history["test_set"]:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data == {1, 2, 3}
            assert value.time is not None
            assert isinstance(value.context, str)

    def test_history_ordering_coherence(self):
        storage = Storage("model", "testsession3", "testmodel3")

        with storage:
            storage.first = 1

        with storage:
            storage.second = 2

        history = storage.__history__()

        assert "first" in history
        assert "second" in history

        first_time = history["first"][-1].time
        second_time = history["second"][-1].time

        assert first_time is not None and second_time is not None
        assert first_time <= second_time

    def test_mutable_modification_history_coherence(self):
        storage = Storage("model", "testsession4", "testmodel4")

        with storage:
            storage.mutable_list = [1, 2, 3]
            storage.mutable_list.append(4)

        history = storage.__history__()

        assert "mutable_list" in history
        value_entries = history["mutable_list"]

        assert len(value_entries) >= 1

        final_value = value_entries[-1]
        assert isinstance(final_value, Value)
        assert not final_value.unavailable
        assert final_value.data == [1, 2, 3, 4]

    def test_tombstone_history_coherence(self):
        storage = Storage("model", "testsession5", "testmodel5")

        with storage:
            storage.temp_field = "temporary"

        del storage.temp_field

        history = storage.__history__()

        assert "temp_field" in history
        tombstone_found = False
        for value in history["temp_field"]:
            if value.unavailable:
                assert value.data is None
                tombstone_found = True
                break

        assert tombstone_found
