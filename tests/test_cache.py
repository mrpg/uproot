from uproot.cache import dbns2tuple, flatten, tuple2dbns


def test_tuple2dbns():
    assert tuple2dbns(()) == ""
    assert tuple2dbns(("single",)) == "single"
    assert tuple2dbns(("first", "second")) == "first/second"
    assert tuple2dbns(("a", "b", "c", "d")) == "a/b/c/d"


def test_dbns2tuple():
    assert dbns2tuple("") == ()
    assert dbns2tuple("single") == ("single",)
    assert dbns2tuple("first/second") == ("first", "second")
    assert dbns2tuple("a/b/c/d") == ("a", "b", "c", "d")


def test_tuple2dbns_dbns2tuple_roundtrip():
    test_tuples = [("single",), ("first", "second"), ("a", "b", "c", "d")]

    for tup in test_tuples:
        dbns = tuple2dbns(tup)
        result = dbns2tuple(dbns)
        assert result == tup


def test_flatten_empty_dict():
    result = flatten({})
    assert result == {}


def test_flatten_simple_dict():
    d = {"key1": "value1", "key2": "value2"}
    result = flatten(d)
    expected = {("key1",): "value1", ("key2",): "value2"}
    assert result == expected


def test_flatten_nested_dict():
    d = {"level1": {"level2": {"key": "value"}, "simple": "data"}, "root": "root_value"}
    result = flatten(d)
    expected = {
        ("level1", "level2", "key"): "value",
        ("level1", "simple"): "data",
        ("root",): "root_value",
    }
    assert result == expected


def test_flatten_with_lists():
    d = {
        "list_field": [1, 2, 3],
        "nested": {"another_list": ["a", "b", "c"]},
        "simple": "value",
    }
    result = flatten(d)
    expected = {
        ("list_field",): [1, 2, 3],
        ("nested", "another_list"): ["a", "b", "c"],
        ("simple",): "value",
    }
    assert result == expected


def test_flatten_with_trail():
    d = {"key": "value"}
    result = flatten(d, trail=("prefix", "trail"))
    expected = {("prefix", "trail", "key"): "value"}
    assert result == expected


def test_flatten_mixed_types():
    d = {
        "string": "text",
        "number": 42,
        "boolean": True,
        "null": None,
        "list": [1, 2, 3],
        "nested": {"inner": "inner_value"},
    }
    result = flatten(d)
    expected = {
        ("string",): "text",
        ("number",): 42,
        ("boolean",): True,
        ("null",): None,
        ("list",): [1, 2, 3],
        ("nested", "inner"): "inner_value",
    }
    assert result == expected
