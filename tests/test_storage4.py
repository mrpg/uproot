from uproot.storage import Storage, load_database_into_memory
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

        history = list(storage.__history__())

        int_found = False
        str_found = False
        float_found = False

        for field_name, value in history:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data is not None
            assert value.time is not None
            assert isinstance(value.context, str)

            if field_name == "test_int":
                assert value.data == 42
                int_found = True
            elif field_name == "test_str":
                assert value.data == "hello"
                str_found = True
            elif field_name == "test_float":
                assert value.data == 3.14
                float_found = True

        assert int_found and str_found and float_found

    def test_mutable_types_history_coherence(self):
        storage = Storage("model", "testsession2", "testmodel2")

        with storage:
            storage.test_list = [1, 2, 3]
            storage.test_dict = {"key": "value"}
            storage.test_set = {1, 2, 3}

        history = list(storage.__history__())

        list_found = False
        dict_found = False
        set_found = False

        for field_name, value in history:
            assert isinstance(value, Value)
            assert not value.unavailable
            assert value.data is not None
            assert value.time is not None
            assert isinstance(value.context, str)

            if field_name == "test_list":
                assert value.data == [1, 2, 3]
                list_found = True
            elif field_name == "test_dict":
                assert value.data == {"key": "value"}
                dict_found = True
            elif field_name == "test_set":
                assert value.data == {1, 2, 3}
                set_found = True

        assert list_found and dict_found and set_found

    def test_history_ordering_coherence(self):
        storage = Storage("model", "testsession3", "testmodel3")

        with storage:
            storage.first = 1

        with storage:
            storage.second = 2

        history = list(storage.__history__())

        assert len(history) == 2

        first_time = None
        second_time = None

        for field_name, value in history:
            if field_name == "first":
                first_time = value.time
            elif field_name == "second":
                second_time = value.time

        assert first_time is not None and second_time is not None
        assert first_time <= second_time

    def test_mutable_modification_history_coherence(self):
        storage = Storage("model", "testsession4", "testmodel4")

        with storage:
            storage.mutable_list = [1, 2, 3]
            storage.mutable_list.append(4)

        history = list(storage.__history__())

        value_entries = [value for field, value in history if field == "mutable_list"]

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

        history = list(storage.__history__())

        tombstone_found = False
        for field_name, value in history:
            if field_name == "temp_field" and value.unavailable:
                assert value.data is None
                tombstone_found = True
                break

        assert tombstone_found
