from unittest.mock import patch

from uproot.data import csv_out, json2csv, long_to_wide, noop, value2json


def test_value2json_unavailable():
    result = value2json("anything", unavailable=True)
    assert result == "null"


def test_value2json_available():
    with patch("uproot.stable._encode") as mock_encode:
        mock_encode.return_value = (None, b'{"test":"data"}')
        result = value2json({"test": "data"}, unavailable=False)
        assert result == '{"test":"data"}'


def test_json2csv_null():
    assert json2csv("null") == ""


def test_json2csv_string():
    assert json2csv('"hello world"') == "hello world"
    assert json2csv('"test"') == "test"


def test_json2csv_boolean_true():
    assert json2csv("true") == "TRUE"


def test_json2csv_boolean_false():
    assert json2csv("false") == "FALSE"


def test_json2csv_number():
    assert json2csv("42") == "42"
    assert json2csv("3.14") == "3.14"


def test_json2csv_array():
    assert json2csv("[1,2,3]") == "[1,2,3]"


def test_noop():
    test_data = [
        {"field1": "value1", "field2": "value2"},
        {"field1": "value3", "field2": "value4"},
    ]

    result = list(noop(test_data))
    assert result == test_data


def test_long_to_wide():
    test_data = [
        {
            "!storage": "test_storage",
            "!field": "test_field",
            "!time": 123.456,
            "!context": "test_context",
            "!unavailable": False,
            "!data": "test_data",
        }
    ]

    result = list(long_to_wide(test_data))
    expected = [
        {
            "!storage": "test_storage",
            "!field": "test_field",
            "!time": 123.456,
            "!context": "test_context",
            "!unavailable": False,
            "test_field": "test_data",
        }
    ]

    assert result == expected


def test_long_to_wide_quoted_field():
    test_data = [
        {
            "!storage": "test_storage",
            "!field": '"quoted_field"',
            "!time": 123.456,
            "!context": "test_context",
            "!unavailable": False,
            "!data": "test_data",
        }
    ]

    result = list(long_to_wide(test_data))
    assert result[0]["quoted_field"] == "test_data"


def test_csv_out():
    test_rows = [
        {"field1": "value1", "field2": "value2", "!unavailable": False},
        {"field1": "value3", "field2": "value4", "!unavailable": False},
    ]

    with (
        patch("uproot.data.value2json") as mock_v2j,
        patch("uproot.data.json2csv") as mock_j2c,
    ):

        mock_v2j.return_value = "mocked_json"
        mock_j2c.return_value = "mocked_csv"

        result = csv_out(test_rows)

        assert isinstance(result, str)
        # Check that headers are present (order may vary)
        assert "field1" in result and "field2" in result and "!unavailable" in result
        assert "mocked_csv" in result


def test_csv_out_empty():
    result = csv_out([])
    # Empty CSV still has a header line when no fields are present
    assert result.strip() == ""
