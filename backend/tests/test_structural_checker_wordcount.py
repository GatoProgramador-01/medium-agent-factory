"""
Tests for _check_word_count() in structural_checker.py.

Verifies the three-band severity logic:
  < 700 words          -> HIGH, "critically short" message
  700..(min-1) words   -> HIGH, "below gate threshold" message
  >= min_word_count    -> no issue

No severity is ever LOW (old two-tier logic was removed).
"""

import pytest

from app.agents.structural_checker import _check_word_count


def _make_content(n_words: int) -> str:
    """Generate plain text with exactly n_words words."""
    return " ".join(["word"] * n_words)


class TestWordCountCriticallyShortBand:
    """Word counts below 700 -> HIGH, critically short message."""

    def test_zero_words_is_critically_short(self) -> None:
        issues = _check_word_count("")
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "critically short" in issues[0].suggestion

    def test_500_words_is_critically_short(self) -> None:
        issues = _check_word_count(_make_content(500))
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "critically short" in issues[0].suggestion

    def test_699_words_is_critically_short(self) -> None:
        issues = _check_word_count(_make_content(699))
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "critically short" in issues[0].suggestion

    def test_critically_short_message_contains_word_count(self) -> None:
        issues = _check_word_count(_make_content(500))
        assert "500" in issues[0].suggestion

    def test_critically_short_message_contains_needed_words(self) -> None:
        # 1300 - 500 = 800 needed
        issues = _check_word_count(_make_content(500))
        assert "800" in issues[0].suggestion

    def test_critically_short_category_is_word_count(self) -> None:
        issues = _check_word_count(_make_content(100))
        assert issues[0].category == "word_count"


class TestWordCountBelowGateBand:
    """700 <= wc < min_word_count -> HIGH, below gate threshold message."""

    def test_700_words_is_below_gate(self) -> None:
        issues = _check_word_count(_make_content(700))
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "below gate threshold" in issues[0].suggestion

    def test_1000_words_is_below_gate(self) -> None:
        issues = _check_word_count(_make_content(1000))
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "below gate threshold" in issues[0].suggestion

    def test_1299_words_is_below_gate(self) -> None:
        issues = _check_word_count(_make_content(1299))
        assert len(issues) == 1
        assert issues[0].severity == "HIGH"
        assert "below gate threshold" in issues[0].suggestion

    def test_below_gate_message_contains_word_count(self) -> None:
        issues = _check_word_count(_make_content(900))
        assert "900" in issues[0].suggestion

    def test_below_gate_message_contains_needed_words(self) -> None:
        # 1300 - 900 = 400 needed
        issues = _check_word_count(_make_content(900))
        assert "400" in issues[0].suggestion

    def test_below_gate_message_contains_numbered_example_hint(self) -> None:
        issues = _check_word_count(_make_content(800))
        assert "numbered example" in issues[0].suggestion

    def test_below_gate_category_is_word_count(self) -> None:
        issues = _check_word_count(_make_content(1000))
        assert issues[0].category == "word_count"


class TestWordCountCustomMinWordCount:
    """Custom min_word_count param shifts the gate boundary."""

    def test_custom_min_at_boundary_is_clean(self) -> None:
        issues = _check_word_count(_make_content(1000), min_word_count=1000)
        assert issues == []

    def test_custom_min_one_below_boundary_is_below_gate(self) -> None:
        issues = _check_word_count(_make_content(999), min_word_count=1000)
        assert len(issues) == 1
        assert "below gate threshold" in issues[0].suggestion

    def test_custom_min_below_700_still_critically_short(self) -> None:
        # 500 words, min=1500 -> critically short
        issues = _check_word_count(_make_content(500), min_word_count=1500)
        assert "critically short" in issues[0].suggestion

    def test_needed_words_reflect_custom_min(self) -> None:
        # 800 words, min=1000 -> 200 needed
        issues = _check_word_count(_make_content(800), min_word_count=1000)
        assert "200" in issues[0].suggestion


class TestWordCountAboveMin:
    """wc >= min_word_count -> no issues."""

    def test_exactly_1300_words_is_clean(self) -> None:
        issues = _check_word_count(_make_content(1300))
        assert issues == []

    def test_1500_words_is_clean(self) -> None:
        issues = _check_word_count(_make_content(1500))
        assert issues == []

    def test_2000_words_is_clean(self) -> None:
        issues = _check_word_count(_make_content(2000))
        assert issues == []


class TestWordCountNeverLow:
    """No path through _check_word_count() returns LOW severity."""

    @pytest.mark.parametrize("n_words", [0, 300, 699, 700, 1000, 1299])
    def test_severity_never_low(self, n_words: int) -> None:
        issues = _check_word_count(_make_content(n_words))
        for issue in issues:
            assert issue.severity != "LOW", (
                f"Expected no LOW severity for {n_words} words, got {issue.severity}"
            )
