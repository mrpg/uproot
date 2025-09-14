import pytest

from uproot.constraints import ensure


def test_ensure_true_condition():
    ensure(True)


def test_ensure_false_condition_default_exception():
    with pytest.raises(ValueError, match="Constraint violation"):
        ensure(False)


def test_ensure_false_condition_custom_message():
    with pytest.raises(ValueError, match="Constraint violation: Custom error"):
        ensure(False, msg="Custom error")


def test_ensure_false_condition_custom_exception():
    with pytest.raises(TypeError, match="Constraint violation"):
        ensure(False, exctype=TypeError)


def test_ensure_false_condition_custom_exception_and_message():
    with pytest.raises(RuntimeError, match="Constraint violation: Runtime error"):
        ensure(False, exctype=RuntimeError, msg="Runtime error")


def test_ensure_with_falsy_values():
    ensure(True)
    ensure(1)
    ensure("non-empty")
    ensure([1])
    ensure({"key": "value"})

    with pytest.raises(ValueError):
        ensure(False)

    with pytest.raises(ValueError):
        ensure(0)

    with pytest.raises(ValueError):
        ensure("")

    with pytest.raises(ValueError):
        ensure([])

    with pytest.raises(ValueError):
        ensure({})
