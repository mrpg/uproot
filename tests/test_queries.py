from dataclasses import dataclass

import pytest

from uproot.queries import Comparison, FieldReferent, resolve


@dataclass
class Person:
    name: str
    age: int
    address: "Address"


@dataclass
class Address:
    street: str
    city: str
    country: str


@dataclass
class Company:
    name: str
    ceo: Person
    employees: list[Person]


# FieldReferent basic functionality tests


def test_field_referent_empty_initialization():
    _ = FieldReferent()
    assert _.path == []


def test_field_referent_initialization_with_path():
    field = FieldReferent(["name", "first"])
    assert field.path == ["name", "first"]


def test_field_referent_path_is_copy():
    _ = FieldReferent(["name"])
    path1 = _.path
    path2 = _.path
    assert path1 is not path2
    path1.append("test")
    assert _.path == ["name"]


def test_field_referent_getattr_builds_path():
    _ = FieldReferent()
    name_field = _.name
    assert name_field.path == ["name"]

    nested_field = _.address.city
    assert nested_field.path == ["address", "city"]


def test_field_referent_chained_getattr():
    _ = FieldReferent()
    deep_field = _.company.ceo.address.country
    assert deep_field.path == ["company", "ceo", "address", "country"]


def test_field_referent_bool_raises_error():
    _ = FieldReferent()
    with pytest.raises(
        ValueError, match="You must compare the field directly against False"
    ):
        bool(_)


def test_field_referent_call_simple_object():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    assert _.name(person) == "John"
    assert _.age(person) == 30


def test_field_referent_call_nested_object():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    assert _.address.street(person) == "123 Main St"
    assert _.address.city(person) == "Springfield"
    assert _.address.country(person) == "USA"


# Comparison creation tests


def test_field_referent_comparison_operators():
    _ = FieldReferent()

    assert isinstance(_.age > 18, Comparison)
    assert isinstance(_.age >= 18, Comparison)
    assert isinstance(_.age < 65, Comparison)
    assert isinstance(_.age <= 65, Comparison)
    assert isinstance(_.name == "John", Comparison)
    assert isinstance(_.name != "Jane", Comparison)


def test_comparison_attributes():
    _ = FieldReferent()
    comp = _.age > 18

    assert comp.op == ">"
    assert comp.lhs.path == ["age"]
    assert comp.rhs == 18


def test_comparison_bool_raises_error():
    _ = FieldReferent()
    comp = _.age > 18
    with pytest.raises(ValueError):
        bool(comp)


# Comparison evaluation tests


def test_comparison_greater_than():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.age > 18
    assert comp(person) is True

    comp = _.age > 35
    assert comp(person) is False


def test_comparison_greater_equal():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.age >= 30
    assert comp(person) is True

    comp = _.age >= 35
    assert comp(person) is False


def test_comparison_less_than():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.age < 35
    assert comp(person) is True

    comp = _.age < 25
    assert comp(person) is False


def test_comparison_less_equal():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.age <= 30
    assert comp(person) is True

    comp = _.age <= 25
    assert comp(person) is False


def test_comparison_equal():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.name == "John"
    assert comp(person) is True

    comp = _.name == "Jane"
    assert comp(person) is False


def test_comparison_not_equal():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.name != "Jane"
    assert comp(person) is True

    comp = _.name != "John"
    assert comp(person) is False


def test_comparison_with_nested_fields():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    comp =_.address.city == "Springfield"
    assert comp(person) is True

    comp = _.address.country != "Canada"
    assert comp(person) is True


def test_comparison_field_to_field():
    _ = FieldReferent()

    class TestObj:
        def __init__(self):
            self.a = 10
            self.b = 5
            self.c = 10

    obj = TestObj()

    comp =_.a > _.b
    assert comp(obj) is True

    comp = _.a == _.c
    assert comp(obj) is True

    comp = _.b >= _.a
    assert comp(obj) is False


def test_comparison_invalid_operator():
    comp = Comparison("invalid", FieldReferent(), 5)
    with pytest.raises(NotImplementedError):
        comp({})


# resolve function tests


def test_resolve_with_field_referent():
    _ = FieldReferent()
    address = Address("123 Main St", "Springfield", "USA")
    person = Person("John", 30, address)

    assert resolve(_.name, person) == "John"
    assert resolve(_.address.city, person) == "Springfield"


def test_resolve_with_literal_value():
    assert resolve(42, None) == 42
    assert resolve("hello", None) == "hello"
    assert resolve([1, 2, 3], None) == [1, 2, 3]


def test_resolve_with_none():
    assert resolve(None, None) is None


# Integration and edge case tests


def test_complex_nested_structure():
    _ = FieldReferent()

    address1 = Address("123 Main St", "Springfield", "USA")
    address2 = Address("456 Oak Ave", "Springfield", "USA")

    ceo = Person("Alice", 45, address1)
    employee = Person("Bob", 28, address2)

    company = Company("TechCorp", ceo, [employee])

    # Test deeply nested access
    comp =_.ceo.address.street == "123 Main St"
    assert comp(company) is True

    comp = _.ceo.age < 40
    assert comp(company) is False


def test_field_referent_with_list_access():
    _ = FieldReferent()

    class Container:
        def __init__(self):
            self.items = [1, 2, 3, 4, 5]

    container = Container()

    # This should work for accessing the list itself
    assert _.items(container) == [1, 2, 3, 4, 5]


def test_comparison_with_none_values():
    _ = FieldReferent()

    class TestObj:
        def __init__(self):
            self.value = None

    obj = TestObj()

    comp = _.value == None  # noqa: E711 - Comparison framework requires ==
    assert comp(obj) is True

    comp = _.value != None  # noqa: E711 - Comparison framework requires !=
    assert comp(obj) is False


def test_comparison_with_boolean_values():
    _ = FieldReferent()

    class TestObj:
        def __init__(self):
            self.active = True
            self.disabled = False

    obj = TestObj()

    comp =_.active == True
    assert comp(obj) is True

    comp = _.disabled == False
    assert comp(obj) is True


def test_field_referent_preserves_immutability():
    _ = FieldReferent()
    name_field = _.name
    age_field = _.age

    # Original should be unchanged
    assert _.path == []
    assert name_field.path == ["name"]
    assert age_field.path == ["age"]


def test_multiple_field_referent_instances():
    field1 = FieldReferent()
    field2 = FieldReferent()

    name1 = field1.name
    name2 = field2.name

    assert name1.path == name2.path
    assert name1 is not name2


def test_comparison_string_operations():
    _ = FieldReferent()

    class Person:
        def __init__(self, name):
            self.name = name

    person = Person("Alice")

    comp =_.name == "Alice"
    assert comp(person) is True

    comp = _.name != "Bob"
    assert comp(person) is True


def test_comparison_numeric_edge_cases():
    _ = FieldReferent()

    class Numbers:
        def __init__(self):
            self.zero = 0
            self.negative = -5
            self.float_val = 3.14

    nums = Numbers()

    comp =_.zero == 0
    assert comp(nums) is True

    comp = _.negative < 0
    assert comp(nums) is True

    comp = _.float_val > 3
    assert comp(nums) is True
