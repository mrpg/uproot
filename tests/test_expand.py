import random

import pytest

from uproot.core import expand
from uproot.types import FrozenPage, Page, PageLike, SmoothOperator


# Test page classes
class Hello(Page):
    template = "hello.html"


class A(Page):
    template = "a.html"


class B(Page):
    template = "b.html"


class C(Page):
    template = "c.html"


class End(Page):
    template = "end.html"


# Test SmoothOperator implementations
class Random(SmoothOperator):
    def __init__(self, *pages: PageLike) -> None:
        super().__init__(*pages)

    def expand(self) -> list[PageLike]:
        shuffled = self.pages.copy()
        random.shuffle(shuffled)
        return shuffled


class Sequential(SmoothOperator):
    def __init__(self, *pages: PageLike) -> None:
        super().__init__(*pages)

    def expand(self) -> list[PageLike]:
        return self.pages


class Repeat(SmoothOperator):
    def __init__(self, times: int, *pages: PageLike) -> None:
        self.times = times
        super().__init__(*pages)

    def expand(self) -> list[PageLike]:
        result = []
        for _ in range(self.times):
            result.extend(self.pages)
        return result


# Tests for expand function
def test_expand_empty_list():
    result = expand([])
    assert result == []


def test_expand_only_page_classes():
    pages = [Hello, A, B, End]
    result = expand(pages)
    assert result == [Hello, A, B, End]


def test_expand_single_smooth_operator():
    sequential = Sequential(A, B, C)
    pages = [sequential]
    result = expand(pages)
    assert result == [A, B, C]


def test_expand_mixed_pages_and_operators():
    sequential = Sequential(A, B)
    pages = [Hello, sequential, End]
    result = expand(pages)
    assert result == [Hello, A, B, End]


def test_expand_nested_operators():
    inner = Sequential(B, C)
    outer = Sequential(A, inner)
    pages = [outer]
    result = expand(pages)
    assert result == [A, B, C]


def test_expand_deeply_nested_operators():
    level3 = Sequential(C)
    level2 = Sequential(B, level3)
    level1 = Sequential(A, level2)
    pages = [level1]
    result = expand(pages)
    assert result == [A, B, C]


def test_expand_multiple_operators():
    op1 = Sequential(A, B)
    op2 = Sequential(C)
    pages = [Hello, op1, op2, End]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]


def test_expand_repeat_operator():
    repeat = Repeat(3, A, B)
    pages = [repeat]
    result = expand(pages)
    assert result == [A, B, A, B, A, B]


def test_expand_complex_nesting():
    inner_repeat = Repeat(2, B)
    outer_seq = Sequential(A, inner_repeat, C)
    pages = [Hello, outer_seq, End]
    result = expand(pages)
    assert result == [Hello, A, B, B, C, End]


# Tests for SmoothOperator implementations
def test_sequential_operator_initialization():
    seq = Sequential(A, B, C)
    assert seq.pages == [A, B, C]


def test_sequential_operator_expand():
    seq = Sequential(A, B, C)
    result = seq.expand()
    assert result == [A, B, C]


def test_random_operator_initialization():
    rand = Random(A, B, C)
    assert set(rand.pages) == {A, B, C}
    assert len(rand.pages) == 3


def test_random_operator_expand_contains_same_elements():
    rand = Random(A, B, C)
    result = rand.expand()
    assert set(result) == {A, B, C}
    assert len(result) == 3


def test_repeat_operator_initialization():
    repeat = Repeat(2, A, B)
    assert repeat.times == 2
    assert repeat.pages == [A, B]


def test_repeat_operator_expand():
    repeat = Repeat(3, A)
    result = repeat.expand()
    assert result == [A, A, A]


def test_repeat_operator_zero_times():
    repeat = Repeat(0, A, B)
    result = repeat.expand()
    assert result == []


def test_smooth_operator_with_no_pages():
    seq = Sequential()
    assert seq.pages == []
    assert seq.expand() == []


def test_smooth_operator_with_single_page():
    seq = Sequential(A)
    assert seq.pages == [A]
    assert seq.expand() == [A]


# Tests for Page classes
def test_page_classes_cannot_be_instantiated():
    with pytest.raises(AttributeError, match="Pages are not meant to be instantiated"):
        Hello()

    with pytest.raises(AttributeError, match="Pages are not meant to be instantiated"):
        A()


def test_page_classes_are_classes():
    assert isinstance(Hello, type)
    assert isinstance(A, type)
    assert issubclass(Hello, Page)
    assert issubclass(A, Page)


def test_page_classes_have_metaclass():
    assert type(Hello) is FrozenPage
    assert type(A) is FrozenPage


# Integration tests
def test_realistic_page_order_example():
    """Test the example from the docstring"""
    page_order = [Hello, Random(A, B, C), End]
    result = expand(page_order)

    # Should have Hello first, End last, and A, B, C in some order in between
    assert len(result) == 5
    assert result[0] is Hello
    assert result[-1] is End
    assert set(result[1:4]) == {A, B, C}


def test_complex_realistic_scenario():
    """Test a more complex realistic scenario"""
    intro_pages = Sequential(Hello, A)
    random_middle = Random(B, C)
    outro_pages = Sequential(End)

    page_order = [intro_pages, random_middle, outro_pages]
    result = expand(page_order)

    assert len(result) == 5
    assert result[0] is Hello
    assert result[1] is A
    assert result[-1] is End
    assert set(result[2:4]) == {B, C}


def test_empty_operators_are_handled():
    empty_seq = Sequential()
    pages = [Hello, empty_seq, End]
    result = expand(pages)
    assert result == [Hello, End]


# Property-based testing for Random operator
def test_random_operator_always_returns_same_elements():
    """Random should shuffle but not change the elements"""
    original_pages = [A, B, C, Hello, End]
    rand = Random(*original_pages)

    for _ in range(10):  # Test multiple expansions
        result = rand.expand()
        assert len(result) == len(original_pages)
        assert set(result) == set(original_pages)


def test_nested_random_operators():
    """Test that nested random operators work correctly"""
    inner_random = Random(B, C)
    outer_random = Random(A, inner_random)

    pages = [outer_random]
    result = expand(pages)

    # Should contain A, B, C in some order
    assert len(result) == 3
    assert set(result) == {A, B, C}


# Additional tests for nested SmoothOperators and recursive expand behavior


class Conditional(SmoothOperator):
    """A SmoothOperator that includes pages based on a condition"""

    def __init__(self, condition: bool, *pages: PageLike) -> None:
        self.condition = condition
        super().__init__(*pages)

    def expand(self) -> list[PageLike]:
        return self.pages if self.condition else []


class Interleave(SmoothOperator):
    """A SmoothOperator that interleaves two sequences"""

    def __init__(self, seq1: SmoothOperator, seq2: SmoothOperator) -> None:
        self.seq1 = seq1
        self.seq2 = seq2
        super().__init__(seq1, seq2)

    def expand(self) -> list[PageLike]:
        list1 = self.seq1.expand()
        list2 = self.seq2.expand()
        result = []
        max_len = max(len(list1), len(list2))

        for i in range(max_len):
            if i < len(list1):
                result.append(list1[i])
            if i < len(list2):
                result.append(list2[i])

        return result


# Tests for recursive expand behavior
def test_expand_three_level_nesting():
    """Test expand with three levels of SmoothOperator nesting"""
    level3 = Sequential(C)
    level2 = Sequential(B, level3)  # Contains another SmoothOperator
    level1 = Sequential(A, level2)  # Contains another SmoothOperator

    pages = [Hello, level1, End]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]


def test_expand_four_level_nesting():
    """Test expand with four levels of SmoothOperator nesting"""
    level4 = Sequential(End)
    level3 = Sequential(C, level4)
    level2 = Sequential(B, level3)
    level1 = Sequential(A, level2)

    pages = [Hello, level1]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]


def test_expand_multiple_nested_branches():
    """Test expand with multiple nested branches"""
    branch1 = Sequential(A, Sequential(B))
    branch2 = Sequential(Sequential(C), End)

    pages = [Hello, branch1, branch2]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]


def test_expand_nested_with_repeat():
    """Test expand with nested Repeat operators"""
    inner_repeat = Repeat(2, B)
    outer_repeat = Repeat(2, A, inner_repeat)

    pages = [outer_repeat]
    result = expand(pages)
    assert result == [A, B, B, A, B, B]


def test_expand_nested_with_conditional():
    """Test expand with nested Conditional operators"""
    true_branch = Conditional(True, B, C)
    false_branch = Conditional(False, Hello, End)
    container = Sequential(A, true_branch, false_branch)

    pages = [container]
    result = expand(pages)
    assert result == [A, B, C]  # false_branch expands to empty list


def test_expand_complex_nested_conditionals():
    """Test expand with complex nested conditional logic"""
    inner_true = Conditional(True, B)
    inner_false = Conditional(False, C)
    outer = Sequential(A, inner_true, inner_false, End)

    pages = [Hello, outer]
    result = expand(pages)
    assert result == [Hello, A, B, End]


def test_expand_interleaved_sequences():
    """Test expand with custom Interleave operator"""
    seq1 = Sequential(A, B)
    seq2 = Sequential(C, End)
    interleaved = Interleave(seq1, seq2)

    pages = [Hello, interleaved]
    result = expand(pages)
    assert result == [Hello, A, C, B, End]


def test_expand_nested_random_in_sequential():
    """Test expand with Random nested inside Sequential"""
    nested_random = Random(B, C)
    container = Sequential(A, nested_random, End)

    pages = [Hello, container]
    result = expand(pages)

    assert len(result) == 5
    assert result[0] is Hello
    assert result[1] is A
    assert result[-1] is End
    assert set(result[2:4]) == {B, C}


def test_expand_sequential_in_random():
    """Test expand with Sequential nested inside Random"""
    nested_seq = Sequential(B, C)
    container = Random(A, nested_seq, End)

    pages = [container]
    result = expand(pages)

    # Should contain A, B, C, End but B and C should be consecutive
    assert len(result) == 4
    assert set(result) == {A, B, C, End}

    # Find B and C positions - they should be consecutive
    b_pos = result.index(B)
    c_pos = result.index(C)
    assert abs(b_pos - c_pos) == 1


def test_expand_deeply_nested_empty_operators():
    """Test expand with deeply nested empty operators"""
    empty3 = Sequential()
    empty2 = Sequential(empty3)
    empty1 = Sequential(A, empty2, B)

    pages = [empty1]
    result = expand(pages)
    assert result == [A, B]


def test_expand_recursive_with_all_operator_types():
    """Test expand combining all operator types recursively"""
    repeat_section = Repeat(2, A)
    conditional_section = Conditional(True, B, C)
    random_section = Random(conditional_section, End)
    main_sequence = Sequential(Hello, repeat_section, random_section)

    pages = [main_sequence]
    result = expand(pages)

    assert len(result) == 6  # Hello, A, A, B, C, End (or B, C, End in random order)
    assert result[0] is Hello
    assert result[1] is A
    assert result[2] is A
    assert set(result[3:]) == {B, C, End}


def test_expand_very_deep_nesting():
    """Test expand with very deep nesting (10 levels)"""
    current = Sequential(End)

    # Build 10 levels of nesting
    for i in range(9, -1, -1):
        current = Sequential(current)

    pages = [Hello, current]
    result = expand(pages)
    assert result == [Hello, End]


def test_expand_mixed_nesting_patterns():
    """Test expand with various mixed nesting patterns"""
    # Create a complex structure:
    # Sequential(
    #   A,
    #   Random(
    #     B,
    #     Sequential(C, Repeat(2, End))
    #   )
    # )
    deep_repeat = Repeat(2, End)
    deep_seq = Sequential(C, deep_repeat)
    random_part = Random(B, deep_seq)
    main_seq = Sequential(A, random_part)

    pages = [Hello, main_seq]
    result = expand(pages)

    assert len(result) == 6
    assert result[0] is Hello
    assert result[1] is A

    # The remaining should be some permutation of [B, C, End, End]
    remaining = result[2:]
    assert len(remaining) == 4
    assert remaining.count(End) == 2
    assert B in remaining
    assert C in remaining


def test_expand_preserves_order_in_nested_sequential():
    """Test that expand preserves order even with deep nesting"""
    # Create: Sequential(A, Sequential(B, Sequential(C, Sequential(End))))
    innermost = Sequential(End)
    level3 = Sequential(C, innermost)
    level2 = Sequential(B, level3)
    level1 = Sequential(A, level2)

    pages = [Hello, level1]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]


def test_expand_handles_operator_returning_operators():
    """Test expand when an operator's expand() returns other operators"""

    class MetaOperator(SmoothOperator):
        def __init__(self, *operators: SmoothOperator) -> None:
            self.operators = operators
            super().__init__()

        def expand(self) -> list[PageLike]:
            return list(self.operators)

    seq1 = Sequential(A, B)
    seq2 = Sequential(C, End)
    meta = MetaOperator(seq1, seq2)

    pages = [Hello, meta]
    result = expand(pages)
    assert result == [Hello, A, B, C, End]
