"""Tests for tts_sft.answer_extraction."""
from __future__ import annotations

from tts_sft.answer_extraction import (
    extract_boxed_answer,
    extract_final_answer,
    is_exact_match,
    normalize_math_answer,
)


class TestExtractBoxed:
    def test_simple_box(self):
        assert extract_boxed_answer("the answer is \\boxed{42}.") == "42"

    def test_no_box_returns_none(self):
        assert extract_boxed_answer("no box here, sorry") is None

    def test_empty_input_returns_none(self):
        assert extract_boxed_answer("") is None
        assert extract_boxed_answer(None) is None  # type: ignore[arg-type]

    def test_multiple_boxes_returns_last(self):
        text = "first try \\boxed{3} then I realize \\boxed{5} is right."
        assert extract_boxed_answer(text) == "5"

    def test_three_boxes_returns_last(self):
        text = "\\boxed{1} ... \\boxed{2} ... \\boxed{3}"
        assert extract_boxed_answer(text) == "3"

    def test_nested_braces_preserved(self):
        text = "answer: \\boxed{\\frac{1}{2}}"
        assert extract_boxed_answer(text) == "\\frac{1}{2}"

    def test_deeply_nested(self):
        text = "\\boxed{\\frac{a+b}{c+d}}"
        assert extract_boxed_answer(text) == "\\frac{a+b}{c+d}"

    def test_unbalanced_braces_bails(self):
        # No closing brace at all -> nothing extracted
        text = "\\boxed{42"
        assert extract_boxed_answer(text) is None


class TestExtractFinalAnswer:
    def test_prefers_boxed_over_textual(self):
        text = "Final answer: 99\n\nWait, actually \\boxed{100}"
        assert extract_final_answer(text) == "100"

    def test_final_answer_phrase(self):
        assert extract_final_answer("blah blah\nFinal answer: 7") == "7"

    def test_the_answer_is_phrase(self):
        assert extract_final_answer("So the answer is 12.") == "12."

    def test_answer_colon(self):
        assert extract_final_answer("Working...\nAnswer: -3") == "-3"

    def test_case_insensitive(self):
        assert extract_final_answer("FINAL ANSWER: 8") == "8"

    def test_none_when_nothing_found(self):
        assert extract_final_answer("just some reasoning without a verdict") is None

    def test_last_occurrence_of_textual_marker(self):
        text = "Answer: 3\nlet me reconsider\nAnswer: 5"
        assert extract_final_answer(text) == "5"


class TestNormalize:
    def test_strips_dollar_signs(self):
        assert normalize_math_answer("$42$") == "42"

    def test_strips_thousands_commas(self):
        assert normalize_math_answer("1,000") == "1000"
        assert normalize_math_answer("12,345,678") == "12345678"

    def test_preserves_non_thousands_commas(self):
        # "(1, 2)" should keep its comma
        assert normalize_math_answer("(1, 2)") == "(1, 2)"

    def test_strips_trailing_punctuation(self):
        assert normalize_math_answer("42.") == "42"
        assert normalize_math_answer("5,") == "5"

    def test_handles_none(self):
        assert normalize_math_answer(None) == ""

    def test_strips_whitespace(self):
        assert normalize_math_answer("   42   ") == "42"

    def test_strips_outer_braces(self):
        assert normalize_math_answer("{42}") == "42"


class TestIsExactMatch:
    def test_basic_match(self):
        assert is_exact_match("42", "42") is True

    def test_comma_normalization_then_match(self):
        assert is_exact_match("1,000", "1000") is True

    def test_dollar_sign_normalization_then_match(self):
        assert is_exact_match("$5$", "5") is True

    def test_numeric_fallback(self):
        assert is_exact_match("42.0", "42") is True

    def test_mismatch(self):
        assert is_exact_match("42", "43") is False

    def test_no_gold(self):
        assert is_exact_match("42", None) is False
        assert is_exact_match("42", "") is False

    def test_no_pred(self):
        assert is_exact_match(None, "42") is False


class TestLatexAwareMatching:
    """Regression for the Node 1 smoke false-negative and related LaTeX renderings."""

    def test_node1_boxed_tuple_vs_leftright_gold(self):
        # The exact Node 1 case: model boxed (3, pi/2); gold uses \left( .. \right).
        pred = extract_final_answer("...so the answer is \\boxed{(3, \\frac{\\pi}{2})}.")
        assert pred == "(3, \\frac{\\pi}{2})"
        gold = "\\left( 3, \\frac{\\pi}{2} \\right)"
        assert is_exact_match(pred, gold) is True

    def test_left_right_stripped(self):
        assert is_exact_match("(3, \\frac{\\pi}{2})", "\\left(3, \\frac{\\pi}{2}\\right)") is True

    def test_internal_whitespace_ignored(self):
        assert is_exact_match("( 1 , 2 )", "(1,2)") is True

    def test_latex_thin_space_ignored(self):
        assert is_exact_match("(1,2)", "(1,\\,2)") is True

    def test_dfrac_folds_to_frac(self):
        assert is_exact_match("\\dfrac{1}{2}", "\\frac{1}{2}") is True

    def test_different_tuple_still_wrong(self):
        # Same shape, different value -> must stay a non-match (no over-normalization).
        assert is_exact_match("(3, \\frac{\\pi}{2})", "\\left( 4, \\frac{\\pi}{2} \\right)") is False
        assert is_exact_match("(3, \\frac{\\pi}{2})", "\\left( 3, \\frac{\\pi}{3} \\right)") is False

    def test_normalize_contract_unchanged(self):
        # The gentler normalizer must STILL preserve display spacing (no regression).
        assert normalize_math_answer("(1, 2)") == "(1, 2)"
