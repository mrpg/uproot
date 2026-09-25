from decimal import Decimal

import pytest

from uproot.pages import fmtnum_filter as fmtnum


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2.345, "2.35"),
        (1.005, "1.01"),
        (0.125, "0.13"),
        (2.5, "2.50"),
        (999.995, "1,000.00"),
        (12345.675, "12,345.68"),
    ],
)
def test_floats_round_half_up(value, expected):
    assert fmtnum(value) == expected


def test_decimals_round_half_up():
    assert fmtnum(Decimal("2.345")) == "2.35"
    assert fmtnum(Decimal("0.125")) == "0.13"


def test_zero_places_round_half_up():
    assert fmtnum(2.5, places=0) == "3"
    assert fmtnum(3.5, places=0) == "4"


def test_integers_and_booleans():
    assert fmtnum(3) == "3.00"
    assert fmtnum(10**20, places=0) == "100,000,000,000,000,000,000"
    assert fmtnum(True) == "1.00"


def test_negative_values_use_minus_sign():
    assert fmtnum(-1234.5, pre="$") == "−$1,234.50"
    assert fmtnum(-2.345) == "−2.35"


def test_negative_values_rounding_to_zero_have_no_sign():
    assert fmtnum(-0.001) == "0.00"
    assert fmtnum(-0.0) == "0.00"


def test_separators():
    assert fmtnum(1234.5, sep=".", decsep=",") == "1.234,50"
    assert fmtnum(1234.5, sep="", decsep=",") == "1234,50"
    assert fmtnum(1234.5, sep="") == "1234.50"
    assert fmtnum(1234567, sep=" ", places=0) == "1 234 567"


def test_prefix_suffix_and_nbsp():
    assert fmtnum(36, post=" €") == "36.00\xa0€"
    assert fmtnum(36, post=" €", use_nbsp=False) == "36.00 €"
    assert fmtnum(1234.5, pre="$ ", sep=".", decsep=",") == "$\xa01.234,50"


def test_tiny_and_non_finite_values():
    assert fmtnum(1e-7) == "0.00"
    assert fmtnum(float("nan")) == "nan"
    assert fmtnum(float("inf"), pre="$") == "$inf"
