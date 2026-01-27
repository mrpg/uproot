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


def test_bracket_grouping_in_random():
    """Test that Bracket groups pages together in Random shuffling"""
    from unittest.mock import Mock

    from uproot.smithereens import Random as SmithereensRandom

    # Mock a player with page_order
    mock_player = Mock()
    mock_player.page_order = [
        "#RandomStart",
        "Hello",
        "#{",  # Bracket start
        "A",
        "B",
        "C",
        "#}",  # Bracket end
        "X",
        "Y",
        "#RandomEnd",
    ]
    mock_player.show_page = 0

    # Run the start method multiple times to test grouping
    original_order = mock_player.page_order.copy()

    # Test that A, B, C stay together as a group
    for _ in range(10):  # Multiple runs to test randomization
        mock_player.page_order = original_order.copy()

        # Call the start method
        import asyncio

        asyncio.run(SmithereensRandom.start(mock_player))

        # Find the positions of A, B, C
        a_pos = mock_player.page_order.index("A")
        b_pos = mock_player.page_order.index("B")
        c_pos = mock_player.page_order.index("C")

        # A, B, C should be consecutive
        positions = sorted([a_pos, b_pos, c_pos])
        assert (
            positions[1] == positions[0] + 1
        ), f"A, B, C not consecutive: {mock_player.page_order}"
        assert (
            positions[2] == positions[1] + 1
        ), f"A, B, C not consecutive: {mock_player.page_order}"

        # X and Y should still be individual elements
        x_pos = mock_player.page_order.index("X")
        y_pos = mock_player.page_order.index("Y")

        # The randomized section should contain all elements between RandomStart and RandomEnd
        start_pos = mock_player.page_order.index("#RandomStart")
        end_pos = mock_player.page_order.index("#RandomEnd")
        randomized_section = mock_player.page_order[start_pos + 1 : end_pos]

        # Should contain Hello, A, B, C (as group), X, Y
        assert "Hello" in randomized_section
        assert "A" in randomized_section
        assert "B" in randomized_section
        assert "C" in randomized_section
        assert "X" in randomized_section
        assert "Y" in randomized_section


# Tests for Between operator
def test_between_selects_exactly_one_page():
    """Test that Between selects exactly one page from the options"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    mock_player.page_order = [
        "#BetweenStart",
        "A",
        "B",
        "C",
        "#BetweenEnd",
    ]
    mock_player.show_page = 0
    mock_player.between_showed = None

    # Run multiple times to verify randomness
    selected_pages = set()
    for _ in range(30):
        mock_player.page_order = [
            "#BetweenStart",
            "A",
            "B",
            "C",
            "#BetweenEnd",
        ]
        mock_player.between_showed = None

        asyncio.run(SmithereenssBetween.start(mock_player))

        # Check that exactly one page remains between markers
        start_ix = mock_player.page_order.index("#BetweenStart")
        end_ix = mock_player.page_order.index("#BetweenEnd")
        between_pages = mock_player.page_order[start_ix + 1 : end_ix]

        assert len(between_pages) == 1, f"Expected 1 page, got {between_pages}"
        assert between_pages[0] in ("A", "B", "C")
        selected_pages.add(between_pages[0])

        # Verify between_showed was recorded
        assert mock_player.between_showed == [between_pages[0]]

    # After 30 runs, we should have seen all three pages at least once
    assert selected_pages == {
        "A",
        "B",
        "C",
    }, f"Not all pages were selected: {selected_pages}"


def test_between_with_bracket_groups():
    """Test that Between treats bracketed groups as single options"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    original_order = [
        "#BetweenStart",
        "A",
        "#{",
        "B",
        "C",
        "#}",
        "D",
        "#BetweenEnd",
    ]
    mock_player.show_page = 0
    mock_player.between_showed = None

    # Track what gets selected
    selections = {"A": 0, "B_C": 0, "D": 0}

    for _ in range(60):
        mock_player.page_order = original_order.copy()
        mock_player.between_showed = None

        asyncio.run(SmithereenssBetween.start(mock_player))

        start_ix = mock_player.page_order.index("#BetweenStart")
        end_ix = mock_player.page_order.index("#BetweenEnd")
        between_pages = mock_player.page_order[start_ix + 1 : end_ix]

        if between_pages == ["A"]:
            selections["A"] += 1
        elif between_pages == ["#{", "B", "C", "#}"]:
            selections["B_C"] += 1
        elif between_pages == ["D"]:
            selections["D"] += 1
        else:
            pytest.fail(f"Unexpected selection: {between_pages}")

    # All three options should have been selected at least once
    assert selections["A"] > 0, "Option A was never selected"
    assert selections["B_C"] > 0, "Option B_C was never selected"
    assert selections["D"] > 0, "Option D was never selected"


def test_between_records_selection():
    """Test that Between records the selected page in between_showed"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    mock_player.page_order = [
        "#BetweenStart",
        "A",
        "B",
        "#BetweenEnd",
    ]
    mock_player.show_page = 0
    mock_player.between_showed = None

    asyncio.run(SmithereenssBetween.start(mock_player))

    # between_showed should be a list with the selected page
    assert isinstance(mock_player.between_showed, list)
    assert len(mock_player.between_showed) == 1
    assert mock_player.between_showed[0] in ("A", "B")


def test_between_multiple_blocks_accumulate():
    """Test that multiple Between blocks accumulate in between_showed"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    mock_player.between_showed = ["PreviousPage"]

    mock_player.page_order = [
        "#BetweenStart",
        "X",
        "Y",
        "#BetweenEnd",
    ]
    mock_player.show_page = 0

    asyncio.run(SmithereenssBetween.start(mock_player))

    # Should have previous page plus the new selection
    assert len(mock_player.between_showed) == 2
    assert mock_player.between_showed[0] == "PreviousPage"
    assert mock_player.between_showed[1] in ("X", "Y")


def test_between_empty_pages():
    """Test Between with no pages"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    mock_player.page_order = [
        "#BetweenStart",
        "#BetweenEnd",
    ]
    mock_player.show_page = 0
    mock_player.between_showed = None

    asyncio.run(SmithereenssBetween.start(mock_player))

    # Nothing should be between the markers
    start_ix = mock_player.page_order.index("#BetweenStart")
    end_ix = mock_player.page_order.index("#BetweenEnd")
    between_pages = mock_player.page_order[start_ix + 1 : end_ix]
    assert between_pages == []


def test_between_nested_depth():
    """Test that nested Between blocks are handled correctly (depth tracking)"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Between as SmithereenssBetween

    mock_player = Mock()
    # Outer Between contains inner Between as one option
    mock_player.page_order = [
        "#BetweenStart",  # Outer start
        "A",
        "#{",
        "#BetweenStart",  # Inner start (nested)
        "X",
        "Y",
        "#BetweenEnd",  # Inner end
        "#}",
        "B",
        "#BetweenEnd",  # Outer end
    ]
    mock_player.show_page = 0
    mock_player.between_showed = None

    asyncio.run(SmithereenssBetween.start(mock_player))

    # Should select one of: A, the bracketed group (with nested Between), or B
    start_ix = mock_player.page_order.index("#BetweenStart")
    # Find the LAST #BetweenEnd (the outer one after selection)
    end_indices = [
        i for i, p in enumerate(mock_player.page_order) if p == "#BetweenEnd"
    ]
    end_ix = end_indices[-1] if end_indices else None

    assert end_ix is not None
    between_pages = mock_player.page_order[start_ix + 1 : end_ix]

    # Valid selections are: ["A"], ["#{", "#BetweenStart", "X", "Y", "#BetweenEnd", "#}"], or ["B"]
    assert (
        between_pages == ["A"]
        or between_pages == ["#{", "#BetweenStart", "X", "Y", "#BetweenEnd", "#}"]
        or between_pages == ["B"]
    ), f"Unexpected selection: {between_pages}"


# Tests for smithereens.Rounds operator
def test_rounds_expand():
    """Test that Rounds.expand() repeats pages n times with markers"""
    from uproot.smithereens import Rounds as SmithereensRounds

    rounds = SmithereensRounds(A, B, n=3)
    result = rounds.expand()

    # Should repeat the structure 3 times
    # Each iteration has: #{, #RoundStart, A, B, #RoundEnd, #}
    assert len(result) == 18  # 6 elements * 3 repetitions

    # Convert to paths for easier comparison
    paths = [getattr(p, "__name__", str(p)) for p in result]

    # Verify the structure repeats correctly
    expected_unit = ["{", "RoundStart", "A", "B", "RoundEnd", "}"]
    for i in range(3):
        for j, expected in enumerate(expected_unit):
            assert expected in paths[i * 6 + j], f"Mismatch at position {i * 6 + j}"


def test_rounds_next_initializes_round():
    """Test that Rounds.next() initializes player.round to 1 when not set"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    mock_player = Mock(spec=[])  # Empty spec so hasattr returns False
    mock_player.page_order = ["#RoundStart", "A", "#RoundEnd"]
    mock_player.show_page = 0

    asyncio.run(SmithereensRounds.next(mock_player))

    assert mock_player.round == 1
    assert mock_player.round_nested == [1]


def test_rounds_next_increments_round():
    """Test that Rounds.next() increments player.round"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    mock_player = Mock()
    mock_player.page_order = [
        "#RoundStart",
        "A",
        "#RoundEnd",
        "#RoundStart",
        "A",
        "#RoundEnd",
        "#RoundStart",
        "A",
        "#RoundEnd",
    ]
    mock_player.round = 1

    mock_player.show_page = 3  # Second #RoundStart
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 2
    assert mock_player.round_nested == [2]

    mock_player.show_page = 6  # Third #RoundStart
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 3
    assert mock_player.round_nested == [3]


def test_rounds_next_handles_none_round():
    """Test that Rounds.next() handles player.round being None"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    mock_player = Mock()
    mock_player.round = None
    mock_player.page_order = ["#RoundStart", "A", "#RoundEnd"]
    mock_player.show_page = 0

    asyncio.run(SmithereensRounds.next(mock_player))

    assert mock_player.round == 1
    assert mock_player.round_nested == [1]


# Tests for smithereens.Repeat operator
def test_repeat_expand():
    """Test that Repeat.expand() returns pages with markers"""
    from uproot.smithereens import Repeat as SmithereensRepeat

    repeat = SmithereensRepeat(A, B)
    result = repeat.expand()

    # Should have: #{, #RepeatStart, A, B, #RepeatEnd, #}
    assert len(result) == 6

    paths = [getattr(p, "__name__", str(p)) for p in result]
    assert "{" in paths[0]
    assert "RepeatStart" in paths[1]
    assert result[2] is A
    assert result[3] is B
    assert "RepeatEnd" in paths[4]
    assert "}" in paths[5]


def test_repeat_next_initializes_round():
    """Test that Repeat.next() initializes player.round to 1"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock(spec=[])

    asyncio.run(SmithereensRepeat.next(mock_player))

    assert mock_player.round == 1


def test_repeat_next_increments_round():
    """Test that Repeat.next() increments player.round"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock()
    mock_player.round = 5

    asyncio.run(SmithereensRepeat.next(mock_player))

    assert mock_player.round == 6


def test_repeat_continue_maybe_adds_pages_when_add_round_true():
    """Test that Repeat.continue_maybe() duplicates pages when add_round is True"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock()
    mock_player.page_order = [
        "Before",
        "#RepeatStart",
        "A",
        "B",
        "#RepeatEnd",
        "After",
    ]
    mock_player.show_page = 3  # Somewhere in the repeat block
    mock_player.add_round = True

    asyncio.run(SmithereensRepeat.continue_maybe(mock_player))

    # Should have duplicated the repeat block
    expected = [
        "Before",
        "#RepeatStart",
        "A",
        "B",
        "#RepeatEnd",
        "#RepeatStart",
        "A",
        "B",
        "#RepeatEnd",
        "After",
    ]
    assert mock_player.page_order == expected


def test_repeat_continue_maybe_no_change_when_add_round_false():
    """Test that Repeat.continue_maybe() does nothing when add_round is False"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock()
    original_order = [
        "Before",
        "#RepeatStart",
        "A",
        "B",
        "#RepeatEnd",
        "After",
    ]
    mock_player.page_order = original_order.copy()
    mock_player.show_page = 3
    mock_player.add_round = False

    asyncio.run(SmithereensRepeat.continue_maybe(mock_player))

    # Should be unchanged
    assert mock_player.page_order == original_order


def test_repeat_continue_maybe_multiple_iterations():
    """Test that Repeat.continue_maybe() can add multiple iterations"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock()
    mock_player.page_order = [
        "#RepeatStart",
        "A",
        "#RepeatEnd",
    ]
    mock_player.show_page = 1

    # First continuation
    mock_player.add_round = True
    asyncio.run(SmithereensRepeat.continue_maybe(mock_player))

    assert mock_player.page_order == [
        "#RepeatStart",
        "A",
        "#RepeatEnd",
        "#RepeatStart",
        "A",
        "#RepeatEnd",
    ]

    # Second continuation (at end of first repeat)
    mock_player.show_page = 4  # Position in the second repeat block
    mock_player.add_round = True
    asyncio.run(SmithereensRepeat.continue_maybe(mock_player))

    assert mock_player.page_order == [
        "#RepeatStart",
        "A",
        "#RepeatEnd",
        "#RepeatStart",
        "A",
        "#RepeatEnd",
        "#RepeatStart",
        "A",
        "#RepeatEnd",
    ]


def test_repeat_continue_maybe_raises_without_start_marker():
    """Test that Repeat.continue_maybe() raises if #RepeatStart not found"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Repeat as SmithereensRepeat

    mock_player = Mock()
    mock_player.page_order = [
        "A",
        "B",
        "#RepeatEnd",
    ]
    mock_player.show_page = 1
    mock_player.add_round = True

    with pytest.raises(RuntimeError, match="Could not find #RepeatStart"):
        asyncio.run(SmithereensRepeat.continue_maybe(mock_player))


# Tests for smithereens.Bracket operator
def test_bracket_expand():
    """Test that Bracket.expand() wraps pages with bracket markers"""
    from uproot.smithereens import Bracket as SmithereenssBracket

    bracket = SmithereenssBracket(A, B, C)
    result = bracket.expand()

    # Should have: #{, A, B, C, #}
    assert len(result) == 5

    paths = [getattr(p, "__name__", str(p)) for p in result]
    assert "{" in paths[0]
    assert result[1] is A
    assert result[2] is B
    assert result[3] is C
    assert "}" in paths[4]


def test_bracket_expand_empty():
    """Test that Bracket.expand() handles empty pages"""
    from uproot.smithereens import Bracket as SmithereenssBracket

    bracket = SmithereenssBracket()
    result = bracket.expand()

    # Should have just: #{, #}
    assert len(result) == 2

    paths = [getattr(p, "__name__", str(p)) for p in result]
    assert "{" in paths[0]
    assert "}" in paths[1]


def test_bracket_expand_single_page():
    """Test that Bracket.expand() works with a single page"""
    from uproot.smithereens import Bracket as SmithereenssBracket

    bracket = SmithereenssBracket(A)
    result = bracket.expand()

    assert len(result) == 3

    paths = [getattr(p, "__name__", str(p)) for p in result]
    assert "{" in paths[0]
    assert result[1] is A
    assert "}" in paths[2]


# Tests for nested Rounds
def test_rounds_nested_expand():
    """Test that nested Rounds expand correctly"""
    from uproot.smithereens import Rounds as SmithereensRounds

    # Rounds(A, Rounds(B, C, n=2), Z, n=2)
    inner = SmithereensRounds(B, C, n=2)
    outer = SmithereensRounds(A, inner, End, n=2)

    from uproot.core import expand

    result = expand([outer])

    # Count occurrences
    a_count = sum(1 for p in result if p is A)
    b_count = sum(1 for p in result if p is B)
    c_count = sum(1 for p in result if p is C)
    end_count = sum(1 for p in result if p is End)

    # Outer repeats 2 times, inner repeats 2 times within each outer
    # A appears once per outer iteration = 2
    # B, C appear once per inner iteration = 2 * 2 = 4
    # End appears once per outer iteration = 2
    assert a_count == 2
    assert b_count == 4
    assert c_count == 4
    assert end_count == 2


def test_rounds_nested_round_tracking():
    """Test that nested Rounds track round_nested correctly"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    # Simulate page_order for Rounds(A, Rounds(B, C, n=2), Z, n=2)
    # Expanded structure (simplified, just markers):
    # Iteration 1 of outer:
    #   #{, #RoundStart, A, #{, #RoundStart, B, C, #RoundEnd, #},
    #                       #{, #RoundStart, B, C, #RoundEnd, #}, Z, #RoundEnd, #}
    # Iteration 2 of outer: (same structure repeated)

    mock_player = Mock()
    mock_player.page_order = [
        # Outer iteration 1
        "#{",
        "#RoundStart",  # pos 1: outer round 1
        "A",
        "#{",
        "#RoundStart",  # pos 4: inner round 1 (of outer 1)
        "B",
        "C",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 10: inner round 2 (of outer 1)
        "B",
        "C",
        "#RoundEnd",
        "#}",
        "Z",
        "#RoundEnd",
        "#}",
        # Outer iteration 2
        "#{",
        "#RoundStart",  # pos 19: outer round 2
        "A",
        "#{",
        "#RoundStart",  # pos 22: inner round 1 (of outer 2)
        "B",
        "C",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 28: inner round 2 (of outer 2)
        "B",
        "C",
        "#RoundEnd",
        "#}",
        "Z",
        "#RoundEnd",
        "#}",
    ]

    # Test at position 1: first #RoundStart (outer round 1)
    mock_player.show_page = 1
    mock_player.round = None
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 1
    assert mock_player.round_nested == [1]

    # Test at position 4: first inner #RoundStart (inner round 1 of outer 1)
    mock_player.show_page = 4
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 2
    assert mock_player.round_nested == [1, 1]

    # Test at position 10: second inner #RoundStart (inner round 2 of outer 1)
    mock_player.show_page = 10
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 3
    assert mock_player.round_nested == [1, 2]

    # Test at position 19: second outer #RoundStart (outer round 2)
    mock_player.show_page = 19
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 4
    assert mock_player.round_nested == [2]

    # Test at position 22: inner #RoundStart (inner round 1 of outer 2)
    mock_player.show_page = 22
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 5
    assert mock_player.round_nested == [2, 1]

    # Test at position 28: inner #RoundStart (inner round 2 of outer 2)
    mock_player.show_page = 28
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 6
    assert mock_player.round_nested == [2, 2]


def test_rounds_deeply_nested():
    """Test Rounds with three levels of nesting"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    # Three levels: Rounds(Rounds(Rounds(A, n=2), n=2), n=2)
    # This creates: 2 * 2 * 2 = 8 total A pages

    mock_player = Mock()
    # Simplified page_order with just the markers for testing
    mock_player.page_order = [
        # Level 0, iteration 1
        "#{",
        "#RoundStart",  # pos 1: [1]
        "#{",
        "#RoundStart",  # pos 3: [1, 1]
        "#{",
        "#RoundStart",  # pos 5: [1, 1, 1]
        "A",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 10: [1, 1, 2]
        "A",
        "#RoundEnd",
        "#}",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 17: [1, 2]
        "#{",
        "#RoundStart",  # pos 19: [1, 2, 1]
        "A",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 24: [1, 2, 2]
        "A",
        "#RoundEnd",
        "#}",
        "#RoundEnd",
        "#}",
        "#RoundEnd",
        "#}",
        # Level 0, iteration 2
        "#{",
        "#RoundStart",  # pos 33: [2]
        # ... (similar structure)
    ]

    test_cases = [
        (1, [1]),
        (3, [1, 1]),
        (5, [1, 1, 1]),
        (10, [1, 1, 2]),
        (17, [1, 2]),
        (19, [1, 2, 1]),
        (24, [1, 2, 2]),
        (33, [2]),
    ]

    mock_player.round = None
    for pos, expected_nested in test_cases:
        mock_player.show_page = pos
        asyncio.run(SmithereensRounds.next(mock_player))
        assert (
            mock_player.round_nested == expected_nested
        ), f"At position {pos}: expected {expected_nested}, got {mock_player.round_nested}"


def test_rounds_nested_single_level_still_works():
    """Test that single-level Rounds still works correctly with round_nested"""
    import asyncio
    from unittest.mock import Mock

    from uproot.smithereens import Rounds as SmithereensRounds

    mock_player = Mock()
    mock_player.page_order = [
        "#{",
        "#RoundStart",  # pos 1
        "A",
        "B",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 7
        "A",
        "B",
        "#RoundEnd",
        "#}",
        "#{",
        "#RoundStart",  # pos 13
        "A",
        "B",
        "#RoundEnd",
        "#}",
    ]

    mock_player.round = None

    mock_player.show_page = 1
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 1
    assert mock_player.round_nested == [1]

    mock_player.show_page = 7
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 2
    assert mock_player.round_nested == [2]

    mock_player.show_page = 13
    asyncio.run(SmithereensRounds.next(mock_player))
    assert mock_player.round == 3
    assert mock_player.round_nested == [3]
