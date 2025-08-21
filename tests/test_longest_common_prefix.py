import uproot.types as t


def test_empty_list():
    assert t.longest_common_prefix([]) == ""


def test_single_string():
    assert t.longest_common_prefix(["hello"]) == "hello"


def test_no_common_prefix():
    assert t.longest_common_prefix(["abc", "def", "ghi"]) == ""


def test_identical_strings():
    assert t.longest_common_prefix(["test", "test", "test"]) == "test"


def test_partial_common_prefix():
    assert t.longest_common_prefix(["flower", "flow", "flight"]) == "fl"


def test_one_string_is_prefix():
    assert t.longest_common_prefix(["test", "testing", "tester"]) == "test"


def test_empty_string_in_list():
    assert t.longest_common_prefix(["abc", "", "ab"]) == ""


def test_different_lengths():
    assert t.longest_common_prefix(["a", "ab", "abc"]) == "a"


def test_first_char_different():
    assert t.longest_common_prefix(["abc", "bcd", "cde"]) == ""


def test_two_strings():
    assert t.longest_common_prefix(["abcdef", "abcxyz"]) == "abc"


def test_case_sensitive():
    assert t.longest_common_prefix(["ABC", "abc"]) == ""
    assert t.longest_common_prefix(["ABC", "ABc"]) == "AB"
