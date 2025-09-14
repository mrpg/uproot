import pytest

from uproot.flexibility import TypeRegistry


def test_type_registry_init():
    registry = TypeRegistry()
    assert registry._equivalences == {}
    assert registry._converters == {}


def test_get_equivalent_types_no_equivalence():
    registry = TypeRegistry()
    result = registry.get_equivalent_types(int)
    assert result == (int,)


def test_register_equivalence():
    registry = TypeRegistry()

    def str_to_int(s):
        return int(s)

    def int_to_str(i):
        return str(i)

    registry.register_equivalence(
        str,
        int,
        converters={
            (str, int): str_to_int,
            (int, str): int_to_str,
        },
    )

    assert registry.get_equivalent_types(str) == (str, int)
    assert registry.get_equivalent_types(int) == (str, int)


def test_convert_same_type():
    registry = TypeRegistry()
    result = registry.convert("hello", str, str)
    assert result == "hello"


def test_convert_with_converter():
    registry = TypeRegistry()

    def str_to_int(s):
        return int(s)

    registry.register_equivalence(
        str,
        int,
        converters={
            (str, int): str_to_int,
        },
    )

    result = registry.convert("42", str, int)
    assert result == 42


def test_convert_no_converter():
    registry = TypeRegistry()

    with pytest.raises(TypeError, match="No converter from .* to .*"):
        registry.convert("hello", str, int)


def test_register_multiple_equivalences():
    registry = TypeRegistry()

    def a_to_b(x):
        return f"b_{x}"

    def b_to_a(x):
        return f"a_{x}"

    def a_to_c(x):
        return f"c_{x}"

    class A:
        pass

    class B:
        pass

    class C:
        pass

    registry.register_equivalence(
        A,
        B,
        converters={
            (A, B): a_to_b,
            (B, A): b_to_a,
        },
    )

    registry.register_equivalence(
        A,
        C,
        converters={
            (A, C): a_to_c,
        },
    )

    # The second registration should overwrite the first for A
    assert registry.get_equivalent_types(A) == (A, C)
    assert registry.get_equivalent_types(C) == (A, C)
    # B still has its old equivalence from the first registration
    assert registry.get_equivalent_types(B) == (A, B)
