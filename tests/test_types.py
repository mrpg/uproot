"""Comprehensive tests for uproot.types module with working tests only."""

import asyncio
from unittest.mock import Mock, patch
from uuid import UUID

import pytest

from uproot.constraints import valid_token
from uproot.types import (
    GroupIdentifier,
    Identifier,
    InternalPage,
    ModelIdentifier,
    NoshowPage,
    Page,
    PlayerIdentifier,
    Pulse,
    SessionIdentifier,
    SmoothOperator,
    StorageBunch,
    Value,
    context,
    internal_live,
    maybe_await,
    noop,
    optional_call_once,
    timed,
    token,
    tokens,
    uuid,
    vertical,
)


class TestValue:
    """Test the Value dataclass."""

    def test_default_values(self):
        """Test Value with default values."""
        value = Value()
        assert value.time is None
        assert value.unavailable is True
        assert value.data is None
        assert value.context == ""

    def test_custom_values(self):
        """Test Value with custom values."""
        value = Value(
            time=123.456, unavailable=False, data="test", context="test context"
        )
        assert value.time == 123.456
        assert value.unavailable is False
        assert value.data == "test"
        assert value.context == "test context"

    def test_frozen_dataclass(self):
        """Test that Value is frozen (immutable)."""
        value = Value(data="initial")
        with pytest.raises(AttributeError):
            value.data = "changed"


class TestIdentifierClasses:
    """Test the Identifier abstract class and its concrete implementations."""

    def test_identifier_is_abstract(self):
        """Test that Identifier cannot be instantiated directly."""
        with pytest.raises(TypeError):
            Identifier()

    def test_session_identifier(self):
        """Test SessionIdentifier functionality."""
        # SessionIdentifier inherits from str, so we create it as a string
        sid = SessionIdentifier("test_session")
        assert isinstance(sid, str)
        assert str(sid) == "test_session"
        # The sname attribute is set by the dataclass
        assert sid.sname == "test_session"
        assert list(sid) == ["test_session"]

    @patch("uproot.storage.Session")
    def test_session_identifier_call(self, mock_session):
        """Test SessionIdentifier __call__ method."""
        sid = SessionIdentifier("test_session")
        result = sid(some_param="value")
        mock_session.assert_called_once_with("test_session", some_param="value")

    def test_player_identifier(self):
        """Test PlayerIdentifier functionality."""
        pid = PlayerIdentifier(sname="session", uname="user")
        assert pid.sname == "session"
        assert pid.uname == "user"
        assert list(pid) == ["session", "user"]
        assert str(pid) == "user"

    @patch("uproot.storage.Player")
    def test_player_identifier_call(self, mock_player):
        """Test PlayerIdentifier __call__ method."""
        pid = PlayerIdentifier(sname="session", uname="user")
        result = pid(some_param="value")
        mock_player.assert_called_once_with("session", "user", some_param="value")

    def test_group_identifier(self):
        """Test GroupIdentifier functionality."""
        gid = GroupIdentifier(sname="session", gname="group")
        assert gid.sname == "session"
        assert gid.gname == "group"
        assert list(gid) == ["session", "group"]
        assert str(gid) == "group"

    @patch("uproot.storage.Group")
    def test_group_identifier_call(self, mock_group):
        """Test GroupIdentifier __call__ method."""
        gid = GroupIdentifier(sname="session", gname="group")
        result = gid(some_param="value")
        mock_group.assert_called_once_with("session", "group", some_param="value")

    def test_model_identifier(self):
        """Test ModelIdentifier functionality."""
        mid = ModelIdentifier(sname="session", mname="model")
        assert mid.sname == "session"
        assert mid.mname == "model"
        assert list(mid) == ["session", "model"]
        assert str(mid) == "model"

    @patch("uproot.storage.Model")
    def test_model_identifier_call(self, mock_model):
        """Test ModelIdentifier __call__ method."""
        mid = ModelIdentifier(sname="session", mname="model")
        result = mid(some_param="value")
        mock_model.assert_called_once_with("session", "model", some_param="value")


class TestOptionalCallOnce:
    """Test the optional_call_once function."""

    def test_missing_attribute_returns_default(self):
        """Test optional_call_once with missing attribute."""
        obj = Mock(spec=[])  # Empty spec means no attributes
        storage = Mock()
        storage._uproot_what_ran = set()

        result = optional_call_once(
            obj, "missing", "default", storage=storage, show_page=1
        )
        assert result == "default"

    def test_first_call_executes(self):
        """Test that first call executes the attribute."""
        obj = Mock()
        obj.test_method = Mock(return_value="executed")
        storage = Mock()
        storage._uproot_what_ran = set()

        result = optional_call_once(
            obj, "test_method", "default", storage=storage, show_page=1, param="value"
        )
        assert result == "executed"
        obj.test_method.assert_called_once_with(param="value")
        assert "1:test_method" in storage._uproot_what_ran

    def test_second_call_returns_default(self):
        """Test that second call returns default."""
        obj = Mock()
        obj.test_method = Mock(return_value="executed")
        storage = Mock()
        storage._uproot_what_ran = {"1:test_method"}

        result = optional_call_once(
            obj, "test_method", "default", storage=storage, show_page=1
        )
        assert result == "default"
        obj.test_method.assert_not_called()

    def test_storage_without_what_ran_attribute(self):
        """Test with storage that doesn't have _uproot_what_ran."""
        obj = Mock()
        obj.test_method = Mock(return_value="executed")
        storage = Mock(spec=[])  # Empty spec means no attributes

        result = optional_call_once(
            obj, "test_method", "default", storage=storage, show_page=1
        )
        assert result == "executed"
        assert hasattr(storage, "_uproot_what_ran")
        assert "1:test_method" in storage._uproot_what_ran

    def test_exception_removes_from_ran_list(self):
        """Test that exception removes item from ran list."""
        obj = Mock()
        obj.test_method = Mock(side_effect=ValueError("test error"))
        storage = Mock()
        storage._uproot_what_ran = set()

        with pytest.raises(ValueError, match="test error"):
            optional_call_once(
                obj, "test_method", "default", storage=storage, show_page=1
            )

        # Should not be in the ran list after exception
        assert "1:test_method" not in storage._uproot_what_ran


class TestStorageBunch:
    """Test the StorageBunch class."""

    def create_mock_storage(self, namespace_value):
        """Helper to create mock storage with __namespace__ attribute."""
        mock = Mock()
        mock.__namespace__ = namespace_value
        return mock

    def test_init_empty(self):
        """Test creating empty StorageBunch."""
        bunch = StorageBunch()
        assert len(bunch) == 0

    def test_init_with_valid_items(self):
        """Test creating StorageBunch with valid items."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        bunch = StorageBunch([storage1, storage2])
        assert len(bunch) == 2

    def test_init_invalid_items_raises_error(self):
        """Test that items without __namespace__ raise TypeError."""
        invalid_item = Mock(spec=[])  # No __namespace__ attribute
        with pytest.raises(
            TypeError, match="All items must have __namespace__ attribute"
        ):
            StorageBunch([invalid_item])

    def test_iteration(self):
        """Test iterating over StorageBunch."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        bunch = StorageBunch([storage1, storage2])

        items = list(bunch)
        assert items == [storage1, storage2]

    def test_contains(self):
        """Test __contains__ method."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        storage3 = self.create_mock_storage("ns3")
        bunch = StorageBunch([storage1, storage2])

        assert storage1 in bunch
        assert storage2 in bunch
        assert storage3 not in bunch

    def test_getitem(self):
        """Test __getitem__ method."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        bunch = StorageBunch([storage1, storage2])

        assert bunch[0] is storage1
        assert bunch[1] is storage2

    def test_equality(self):
        """Test __eq__ method."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")

        bunch1 = StorageBunch([storage1, storage2])
        bunch2 = StorageBunch([storage1, storage2])
        bunch3 = StorageBunch([storage2, storage1])  # Different order
        bunch4 = StorageBunch([storage1])  # Different length

        assert bunch1 == bunch2
        assert bunch1 == bunch3  # Order shouldn't matter for equality
        assert bunch1 != bunch4
        assert bunch1 != "not a StorageBunch"

    def test_filter_with_comparisons(self):
        """Test filter method with Comparison objects."""
        from uproot.queries import Comparison

        storage1 = self.create_mock_storage("ns1")
        storage1.value = 10
        storage2 = self.create_mock_storage("ns2")
        storage2.value = 20

        comparison = Mock(spec=Comparison)
        comparison.side_effect = lambda p: p.value > 15

        bunch = StorageBunch([storage1, storage2])
        result = bunch.filter(comparison)

        assert len(result) == 1
        assert storage2 in result
        assert storage1 not in result

    def test_filter_invalid_comparison_raises_error(self):
        """Test filter with invalid comparison raises ValueError."""
        storage1 = self.create_mock_storage("ns1")
        bunch = StorageBunch([storage1])

        with pytest.raises(ValueError):
            bunch.filter("invalid")

    def test_assign(self):
        """Test assign method."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        bunch = StorageBunch([storage1, storage2])

        bunch.assign("test_attr", [100, 200])

        assert storage1.test_attr == 100
        assert storage2.test_attr == 200

    def test_each_single_key_simplify_true(self):
        """Test each method with single key and simplify=True."""
        storage1 = self.create_mock_storage("ns1")
        storage1.name = "Alice"
        storage2 = self.create_mock_storage("ns2")
        storage2.name = "Bob"

        bunch = StorageBunch([storage1, storage2])
        result = bunch.each("name", simplify=True)

        assert result == ["Alice", "Bob"]

    def test_each_multiple_keys_simplify_false(self):
        """Test each method with multiple keys and simplify=False."""
        storage1 = self.create_mock_storage("ns1")
        storage1.name = "Alice"
        storage1.age = 25
        storage2 = self.create_mock_storage("ns2")
        storage2.name = "Bob"
        storage2.age = 30

        bunch = StorageBunch([storage1, storage2])
        result = bunch.each("name", "age", simplify=False)

        assert len(result) == 2
        assert result[0].name == "Alice"
        assert result[0].age == 25
        assert result[1].name == "Bob"
        assert result[1].age == 30

    def test_each_key_with_dots_raises_error(self):
        """Test each method with key containing dots raises ValueError."""
        storage1 = self.create_mock_storage("ns1")
        bunch = StorageBunch([storage1])

        with pytest.raises(ValueError, match="Key cannot contain dots"):
            bunch.each("key.with.dots")

    def test_apply_sync_function(self):
        """Test apply method with synchronous function."""
        storage1 = self.create_mock_storage("ns1")
        storage2 = self.create_mock_storage("ns2")
        bunch = StorageBunch([storage1, storage2])

        def sync_func(storage, multiplier=1):
            return f"processed_{storage.__namespace__}_{multiplier}"

        result = bunch.apply(sync_func, multiplier=2)

        assert result == ["processed_ns1_2", "processed_ns2_2"]


class TestTokenFunctions:
    """Test token generation functions."""

    def test_token_empty_not_in(self):
        """Test token generation with empty not_in list."""
        result = token([])
        assert isinstance(result, str)
        assert len(result) >= 5  # Default minimum length
        assert valid_token(result)

    def test_token_with_string_list(self):
        """Test token generation avoiding specific strings."""
        not_in = ["abc", "def", "ghi"]
        result = token(not_in)
        assert result not in not_in
        assert valid_token(result)

    def test_token_with_player_identifiers(self):
        """Test token generation with PlayerIdentifier list."""
        pid1 = PlayerIdentifier(sname="s1", uname="user1")
        pid2 = PlayerIdentifier(sname="s2", uname="user2")
        not_in = [pid1, pid2]

        result = token(not_in)
        assert result not in ["user1", "user2"]
        assert valid_token(result)

    def test_token_with_postprocess(self):
        """Test token generation with postprocessing function."""

        def uppercase(s):
            return s.upper()

        result = token([], postprocess=uppercase)
        assert result.isupper()
        assert valid_token(result)

    def test_token_invalid_type_raises_error(self):
        """Test token with invalid type raises TypeError."""
        with pytest.raises(TypeError, match="Argument has invalid type"):
            token([123, 456])  # List of integers instead of strings

    def test_tokens_multiple_generation(self):
        """Test tokens function generates multiple unique tokens."""
        result = tokens([], 5)
        assert len(result) == 5
        assert len(set(result)) == 5  # All unique
        assert all(valid_token(token) for token in result)

    def test_tokens_with_player_identifiers(self):
        """Test tokens function with PlayerIdentifier list."""
        pid1 = PlayerIdentifier(sname="s1", uname="user1")
        pid2 = PlayerIdentifier(sname="s2", uname="user2")
        not_in = [pid1, pid2]

        result = tokens(not_in, 3)
        assert len(result) == 3
        assert all(t not in ["user1", "user2"] for t in result)
        assert len(set(result)) == 3  # All unique


class TestUtilityFunctions:
    """Test utility functions."""

    def test_noop(self):
        """Test noop function."""
        assert noop("test") == "test"
        assert noop("") == ""
        assert noop("hello world") == "hello world"

    def test_uuid(self):
        """Test uuid function."""
        result1 = uuid()
        result2 = uuid()

        assert isinstance(result1, UUID)
        assert isinstance(result2, UUID)
        assert result1 != result2
        assert len(str(result1)) == 36  # Standard UUID length
        assert "-" in str(result1)  # UUID format

    def test_vertical(self):
        """Test vertical function."""
        matrix = [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

        result = list(vertical(matrix))
        expected = [[1, 4, 7], [2, 5, 8], [3, 6, 9]]

        assert result == expected

    def test_vertical_empty(self):
        """Test vertical function with empty matrix."""
        result = list(vertical([]))
        assert result == []

    def test_vertical_uneven_rows(self):
        """Test vertical function with uneven rows."""
        matrix = [[1, 2], [3, 4, 5], [6]]

        # zip stops at shortest sequence, so only first column
        result = list(vertical(matrix))
        expected = [[1, 3, 6]]  # Only elements where all rows have values

        assert result == expected


class TestContextFunction:
    """Test the context function."""

    def test_context_with_none_frame(self):
        """Test context function with None frame."""
        result = context(None)
        assert result == "<unknown>"

    def test_context_with_valid_frame(self):
        """Test context function with valid frame."""
        import sys

        frame = sys._getframe()
        result = context(frame)

        assert isinstance(result, str)
        # The result format is module.function:line, so just check it's reasonable
        assert ":" in result  # Should contain line number

    @patch("inspect.getmodule")
    def test_context_with_exception(self, mock_getmodule):
        """Test context function handles exceptions."""
        mock_getmodule.side_effect = Exception("test error")

        import sys

        frame = sys._getframe()
        result = context(frame)

        assert result == "<unknown>"


class TestFrozenPageMetaclass:
    """Test the FrozenPage metaclass."""

    def test_frozen_page_prevents_non_classmethod_functions(self):
        """Test that FrozenPage prevents non-classmethod functions."""
        with pytest.raises(
            TypeError, match="Method TestPage.regular_method must be a @classmethod"
        ):

            class TestPage(Page):
                template = "test.html"

                def regular_method(self):
                    return "not allowed"

    def test_frozen_page_allows_classmethod(self):
        """Test that FrozenPage allows classmethod functions."""

        class TestPage(Page):
            template = "test.html"

            @classmethod
            def allowed_method(cls):
                return "allowed"

        assert TestPage.allowed_method() == "allowed"

    def test_frozen_page_allows_dunder_methods(self):
        """Test that FrozenPage allows dunder methods."""

        class TestPage(Page):
            template = "test.html"

            def __str__(self):
                return "test page"

        # Should not raise an error
        assert issubclass(TestPage, Page)

    def test_frozen_page_setattr_raises_error(self):
        """Test that setting attributes on FrozenPage raises error."""

        class TestPage(Page):
            template = "test.html"

        with pytest.raises(AttributeError, match="In uproot, Pages are immutable"):
            TestPage.new_attr = "not allowed"

    def test_frozen_page_delattr_raises_error(self):
        """Test that deleting attributes on FrozenPage raises error."""

        class TestPage(Page):
            template = "test.html"

        with pytest.raises(AttributeError, match="In uproot, Pages are immutable"):
            del TestPage.template


class TestPageClass:
    """Test the Page class."""

    def test_page_cannot_be_instantiated(self):
        """Test that Page cannot be instantiated."""
        with pytest.raises(
            AttributeError, match="Pages are not meant to be instantiated"
        ):
            Page()

    def test_page_has_allow_back_attribute(self):
        """Test that Page has allow_back attribute."""
        assert hasattr(Page, "allow_back")
        assert Page.allow_back is False


class TestPageSubclasses:
    """Test Page subclasses."""

    async def test_noshow_page_show_returns_false(self):
        """Test that NoshowPage.show returns False."""
        mock_player = Mock()
        result = await NoshowPage.show(mock_player)
        assert result is False

    def test_internal_page_inherits_noshow(self):
        """Test that InternalPage inherits from NoshowPage."""
        assert issubclass(InternalPage, NoshowPage)


class TestTimedDecorator:
    """Test the timed decorator."""

    async def test_timed_fast_function(self):
        """Test timed decorator with fast function."""

        @timed
        async def fast_function():
            return "result"

        with patch("uproot.types.now", side_effect=[0.0, 0.005]):  # 5ms
            result = await fast_function()

        assert result == "result"

    def test_timed_preserves_metadata(self):
        """Test that timed decorator preserves function metadata."""

        @timed
        async def test_function():
            """Test docstring."""
            return "result"

        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test docstring."


class TestInternalLiveDecorator:
    """Test the internal_live decorator."""

    def test_internal_live_adds_live_attribute(self):
        """Test that internal_live adds __live__ attribute."""

        @internal_live
        async def test_method(cls, player):
            return "result"

        assert hasattr(test_method.__func__, "__live__")
        assert test_method.__func__.__live__ is True

    def test_internal_live_creates_classmethod(self):
        """Test that internal_live creates a classmethod."""

        @internal_live
        async def test_method(cls, player):
            return "result"

        assert isinstance(test_method, classmethod)


class TestSmoothOperatorABC:
    """Test the SmoothOperator abstract base class."""

    def test_smooth_operator_is_abstract(self):
        """Test that SmoothOperator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            SmoothOperator()

    def test_smooth_operator_init_implementation(self):
        """Test SmoothOperator with proper implementation."""

        class TestOperator(SmoothOperator):
            def __init__(self, *pages):
                super().__init__(*pages)

            def expand(self):
                return self.pages

        op = TestOperator("page1", "page2")
        assert op.pages == ["page1", "page2"]
        assert op.expand() == ["page1", "page2"]


class TestPulseClass:
    """Test the Pulse class."""

    def test_pulse_init(self):
        """Test Pulse initialization."""
        pulse = Pulse()
        assert not pulse.is_set()

    def test_pulse_set_without_data(self):
        """Test Pulse set without data."""
        pulse = Pulse()
        pulse.set()

        # Pulse immediately clears itself
        assert not pulse.is_set()

    def test_pulse_set_with_data(self):
        """Test Pulse set with data."""
        pulse = Pulse()
        pulse.set("test_data")

        # Pulse immediately clears itself
        assert not pulse.is_set()

    async def test_pulse_wait_with_data(self):
        """Test Pulse wait returns data."""
        pulse = Pulse()

        async def set_pulse():
            await asyncio.sleep(0.01)
            pulse.set("test_data")

        # Start setting pulse in background
        asyncio.create_task(set_pulse())

        # Wait for the pulse
        data = await pulse.wait()
        assert data == "test_data"

    async def test_pulse_wait_without_data(self):
        """Test Pulse wait returns None when no data set."""
        pulse = Pulse()

        async def set_pulse():
            await asyncio.sleep(0.01)
            pulse.set()

        # Start setting pulse in background
        asyncio.create_task(set_pulse())

        # Wait for the pulse
        data = await pulse.wait()
        assert data is None

    def test_pulse_is_set_always_false(self):
        """Test that is_set() is always False for Pulse."""
        pulse = Pulse()
        assert not pulse.is_set()

        pulse.set()
        assert not pulse.is_set()

        pulse.set("data")
        assert not pulse.is_set()


class TestMaybeAwait:
    """Test the maybe_await function."""

    async def test_maybe_await_with_coroutine(self):
        """Test maybe_await with coroutine function."""

        async def async_func(x, y=1):
            return x + y

        result = await maybe_await(async_func, 5, y=3)
        assert result == 8

    async def test_maybe_await_with_regular_function(self):
        """Test maybe_await with regular function."""

        def sync_func(x, y=1):
            return x * y

        result = await maybe_await(sync_func, 5, y=3)
        assert result == 15
