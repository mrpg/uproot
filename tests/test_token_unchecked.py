import re
from string import ascii_letters, ascii_lowercase, digits

import pytest

from uproot.types import token_unchecked

ALPHANUMERIC = ascii_letters + digits


def test_assertion_error_for_zero_length():
    with pytest.raises(AssertionError):
        token_unchecked(0)


def test_assertion_error_for_negative_length():
    with pytest.raises(AssertionError):
        token_unchecked(-1)

    with pytest.raises(AssertionError):
        token_unchecked(-10)


def test_correct_length():
    assert len(token_unchecked(1)) == 1
    assert len(token_unchecked(5)) == 5
    assert len(token_unchecked(10)) == 10
    assert len(token_unchecked(100)) == 100


def test_first_character_is_lowercase_letter():
    for _ in range(50):  # Multiple runs due to randomness
        token = token_unchecked(10)
        assert token[0] in ascii_lowercase


def test_remaining_characters_are_alphanumeric():
    for _ in range(50):
        token = token_unchecked(10)
        for char in token[1:]:
            assert char in ALPHANUMERIC


def test_single_character_token():
    token = token_unchecked(1)
    assert len(token) == 1
    assert token in ascii_lowercase


def test_valid_python_identifier_pattern():
    for _ in range(20):
        token = token_unchecked(8)
        # Should match Python identifier pattern
        assert re.match(r"^[a-z][a-zA-Z0-9]*$", token)


def test_different_tokens_generated():
    # Very unlikely to generate same token twice
    tokens = {token_unchecked(20) for _ in range(100)}
    assert len(tokens) > 90  # Should be mostly unique


def test_edge_case_large_length():
    token = token_unchecked(1000)
    assert len(token) == 1000
    assert token[0] in ascii_lowercase
    assert all(c in ALPHANUMERIC for c in token[1:])


def test_generates_valid_python_identifier():
    for _ in range(50):
        token = token_unchecked(8)
        assert token.isidentifier(), f"'{token}' is not a valid Python identifier"


def test_various_lengths_are_valid_identifiers():
    for length in [1, 5, 10, 25, 100]:
        token = token_unchecked(length)
        assert token.isidentifier(), f"Length {length} token '{token}' is not valid"
