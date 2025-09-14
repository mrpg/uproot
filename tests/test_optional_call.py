from unittest.mock import Mock

import pytest

from uproot.types import maybe_await, optional_call


class MockObject:
    def __init__(self):
        self.attr_value = "test_value"
        self.number = 42

    def sync_method(self, x=1, y=2):
        return x + y

    async def async_method(self, x=1, y=2):
        return x * y


async def test_missing_attribute_returns_default():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "nonexistent")
    assert result is None

    result = await maybe_await(
        optional_call, obj, "nonexistent", default_return="custom"
    )
    assert result == "custom"


async def test_non_callable_attribute_returns_value():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "attr_value")
    assert result == "test_value"

    result = await maybe_await(optional_call, obj, "number")
    assert result == 42


async def test_sync_callable_with_no_args():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "sync_method")
    assert result == 3  # 1 + 2 default


async def test_sync_callable_with_kwargs():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "sync_method", x=5, y=10)
    assert result == 15


async def test_async_callable_with_no_args():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "async_method")
    assert result == 2  # 1 * 2 default


async def test_async_callable_with_kwargs():
    obj = MockObject()
    result = await maybe_await(optional_call, obj, "async_method", x=3, y=4)
    assert result == 12


async def test_callable_with_exception():
    def failing_method():
        raise ValueError("test error")

    obj = Mock()
    obj.failing = failing_method

    with pytest.raises(ValueError, match="test error"):
        await maybe_await(optional_call, obj, "failing")


async def test_async_callable_with_exception():
    async def failing_async():
        raise RuntimeError("async error")

    obj = Mock()
    obj.failing_async = failing_async

    with pytest.raises(RuntimeError, match="async error"):
        await maybe_await(optional_call, obj, "failing_async")


async def test_lambda_function():
    obj = Mock()
    obj.lambda_attr = lambda x: x * 2

    result = await maybe_await(optional_call, obj, "lambda_attr", x=5)
    assert result == 10
