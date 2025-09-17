from datetime import date, datetime, time
from unittest.mock import patch

from uproot.data import csv_out, json2csv, long_to_wide, noop, value2json
from uproot.stable import decode, encode


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


def test_stable_encode_decode_date():
    test_date = date(2025, 9, 17)
    encoded = encode(test_date)
    decoded = decode(encoded)
    assert decoded == test_date
    assert isinstance(decoded, date)


def test_stable_encode_decode_time():
    test_time = time(14, 30, 45, 123456)
    encoded = encode(test_time)
    decoded = decode(encoded)
    assert decoded == test_time
    assert isinstance(decoded, time)


def test_stable_encode_decode_time_no_microseconds():
    test_time = time(14, 30, 45)
    encoded = encode(test_time)
    decoded = decode(encoded)
    assert decoded == test_time
    assert isinstance(decoded, time)


def test_stable_encode_decode_datetime():
    test_datetime = datetime(2025, 9, 17, 14, 30, 45, 123456)
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)


def test_stable_encode_decode_datetime_no_microseconds():
    test_datetime = datetime(2025, 9, 17, 14, 30, 45)
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)


def test_stable_encode_decode_datetime_with_timezone():
    from datetime import timedelta, timezone

    test_datetime = datetime(
        2025, 9, 17, 14, 30, 45, 123456, timezone(timedelta(hours=5, minutes=30))
    )
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)
    assert decoded.tzinfo == test_datetime.tzinfo


def test_stable_encode_decode_datetime_naive():
    # Test that naive datetimes remain naive (no timezone info)
    test_datetime = datetime(2025, 9, 17, 14, 30, 45)
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)
    assert decoded.tzinfo is None
    assert test_datetime.tzinfo is None


def test_stable_encode_decode_datetime_utc():
    from datetime import timezone

    test_datetime = datetime(2025, 9, 17, 14, 30, 45, tzinfo=timezone.utc)
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)
    assert decoded.tzinfo == timezone.utc


def test_stable_encode_decode_datetime_negative_offset():
    from datetime import timedelta, timezone

    # Test negative timezone offset (e.g., US timezones)
    test_datetime = datetime(
        2025, 9, 17, 14, 30, 45, tzinfo=timezone(timedelta(hours=-8))
    )
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)
    assert decoded.tzinfo == test_datetime.tzinfo


def test_stable_encode_decode_datetime_fractional_offset():
    from datetime import timedelta, timezone

    # Test fractional timezone offset (e.g., India +05:30, Nepal +05:45)
    test_datetime = datetime(
        2025, 9, 17, 14, 30, 45, tzinfo=timezone(timedelta(hours=5, minutes=45))
    )
    encoded = encode(test_datetime)
    decoded = decode(encoded)
    assert decoded == test_datetime
    assert isinstance(decoded, datetime)
    assert decoded.tzinfo == test_datetime.tzinfo


def test_stable_encode_decode_time_with_timezone():
    from datetime import timedelta, timezone

    # Test that time objects can also have timezone info
    test_time = time(14, 30, 45, 123456, tzinfo=timezone(timedelta(hours=2)))
    encoded = encode(test_time)
    decoded = decode(encoded)
    assert decoded == test_time
    assert isinstance(decoded, time)
    assert decoded.tzinfo == test_time.tzinfo


def test_stable_encode_decode_time_naive():
    # Test that naive time objects remain naive
    test_time = time(14, 30, 45)
    encoded = encode(test_time)
    decoded = decode(encoded)
    assert decoded == test_time
    assert isinstance(decoded, time)
    assert decoded.tzinfo is None
    assert test_time.tzinfo is None


def test_stable_encode_decode_timezone_preservation():
    from datetime import timedelta, timezone

    # Test that different timezone objects with same offset are handled correctly
    tz1 = timezone(timedelta(hours=3))
    tz2 = timezone(timedelta(hours=3), name="Custom+3")

    dt1 = datetime(2025, 9, 17, 14, 30, 45, tzinfo=tz1)
    dt2 = datetime(2025, 9, 17, 14, 30, 45, tzinfo=tz2)

    encoded1 = encode(dt1)
    encoded2 = encode(dt2)
    decoded1 = decode(encoded1)
    decoded2 = decode(encoded2)

    # Both should decode to the same time but maintain their timezone info
    assert decoded1 == dt1
    assert decoded2 == dt2
    assert decoded1.tzinfo.utcoffset(None) == tz1.utcoffset(None)
    assert decoded2.tzinfo.utcoffset(None) == tz2.utcoffset(None)


def test_stable_encode_decode_date_edge_cases():
    # Test date boundary conditions
    test_cases = [
        date(1, 1, 1),  # Minimum valid date
        date(9999, 12, 31),  # Maximum valid date
        date(2000, 2, 29),  # Leap year date
        date(1900, 2, 28),  # Non-leap year boundary
    ]

    for test_date in test_cases:
        encoded = encode(test_date)
        decoded = decode(encoded)
        assert decoded == test_date
        assert isinstance(decoded, date)
        assert not isinstance(
            decoded, datetime
        )  # Ensure it's exactly date, not datetime


def test_stable_encode_decode_time_edge_cases():
    # Test time boundary conditions
    test_cases = [
        time(0, 0, 0),  # Midnight
        time(23, 59, 59),  # End of day
        time(12, 0, 0, 0),  # Noon with explicit zero microseconds
        time(23, 59, 59, 999999),  # Maximum time
        time(0, 0, 0, 1),  # Minimum non-zero microseconds
    ]

    for test_time in test_cases:
        encoded = encode(test_time)
        decoded = decode(encoded)
        assert decoded == test_time
        assert isinstance(decoded, time)
        assert decoded.tzinfo is None  # All test cases are naive


def test_stable_encode_decode_datetime_edge_cases():
    from datetime import timedelta, timezone

    # Test datetime boundary and edge conditions
    test_cases = [
        datetime(1, 1, 1, 0, 0, 0),  # Minimum datetime
        datetime(9999, 12, 31, 23, 59, 59, 999999),  # Maximum datetime
        datetime(2000, 2, 29, 12, 0, 0),  # Leap year datetime
        datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc),  # UTC at epoch boundary
        datetime(
            2025, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=14))
        ),  # Maximum positive offset
        datetime(
            2025, 1, 1, 0, 0, 0, tzinfo=timezone(timedelta(hours=-12))
        ),  # Maximum negative offset
    ]

    for test_datetime in test_cases:
        encoded = encode(test_datetime)
        decoded = decode(encoded)
        assert decoded == test_datetime
        assert isinstance(decoded, datetime)
        if test_datetime.tzinfo is None:
            assert decoded.tzinfo is None
        else:
            assert decoded.tzinfo is not None
            assert decoded.tzinfo.utcoffset(None) == test_datetime.tzinfo.utcoffset(
                None
            )


def test_stable_type_ids_normative():
    # Test that the type IDs are exactly as specified
    from uproot.stable import TYPES

    assert TYPES[date] == 10
    assert TYPES[time] == 11
    assert TYPES[datetime] == 12


def test_stable_datetime_types_immutable():
    # Test that datetime types are classified as immutable
    from uproot.stable import IMMUTABLE_TYPES, MUTABLE_TYPES

    assert date in IMMUTABLE_TYPES
    assert time in IMMUTABLE_TYPES
    assert datetime in IMMUTABLE_TYPES
    assert date not in MUTABLE_TYPES
    assert time not in MUTABLE_TYPES
    assert datetime not in MUTABLE_TYPES


def test_stable_encode_decode_iso_format_normative():
    # Test that encoding produces valid ISO format strings
    from orjson import loads

    # Test date ISO format
    test_date = date(2025, 9, 17)
    encoded = encode(test_date)
    assert encoded[0] == 10  # Type ID
    iso_string = (
        loads(encoded[1:]).decode()
        if isinstance(loads(encoded[1:]), bytes)
        else loads(encoded[1:])
    )
    assert iso_string == "2025-09-17"

    # Test time ISO format
    test_time = time(14, 30, 45, 123456)
    encoded = encode(test_time)
    assert encoded[0] == 11  # Type ID
    iso_string = loads(encoded[1:])
    assert iso_string == "14:30:45.123456"

    # Test datetime ISO format
    test_datetime = datetime(2025, 9, 17, 14, 30, 45, 123456)
    encoded = encode(test_datetime)
    assert encoded[0] == 12  # Type ID
    iso_string = loads(encoded[1:])
    assert iso_string == "2025-09-17T14:30:45.123456"

    # Test datetime with timezone ISO format
    from datetime import timedelta, timezone

    test_datetime_tz = datetime(
        2025, 9, 17, 14, 30, 45, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )
    encoded = encode(test_datetime_tz)
    assert encoded[0] == 12  # Type ID
    iso_string = loads(encoded[1:])
    assert iso_string == "2025-09-17T14:30:45+05:30"
