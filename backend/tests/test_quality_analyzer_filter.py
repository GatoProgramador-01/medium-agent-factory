"""
Tests for the structural-category filter in quality_analyzer.py.

Verifies that:
1. _STRUCTURAL_CATEGORIES is a frozenset with exactly the 5 required members.
2. The filter expression correctly removes structural issues and preserves content issues.
"""

import pytest

from app.agents.quality_analyzer import _STRUCTURAL_CATEGORIES
from app.models.post import QualityIssue


def _make_issue(category: str) -> QualityIssue:
    return QualityIssue(
        category=category,
        severity="HIGH",
        location="test location",
        suggestion="fix it",
    )


def _apply_filter(issues: list[QualityIssue]) -> list[QualityIssue]:
    """Replicate the filter expression from run_quality_analysis()."""
    return [i for i in issues if i.category not in _STRUCTURAL_CATEGORIES]


class TestStructuralCategoriesConstant:
    """_STRUCTURAL_CATEGORIES must be a frozenset with all 5 required members."""

    def test_is_frozenset(self) -> None:
        assert isinstance(_STRUCTURAL_CATEGORIES, frozenset)

    def test_contains_word_count(self) -> None:
        assert "word_count" in _STRUCTURAL_CATEGORIES

    def test_contains_paragraph_length(self) -> None:
        assert "paragraph_length" in _STRUCTURAL_CATEGORIES

    def test_contains_heading_cadence(self) -> None:
        assert "heading_cadence" in _STRUCTURAL_CATEGORIES

    def test_contains_intro_length(self) -> None:
        assert "intro_length" in _STRUCTURAL_CATEGORIES

    def test_contains_image_missing(self) -> None:
        assert "image_missing" in _STRUCTURAL_CATEGORIES

    def test_exactly_five_members(self) -> None:
        assert len(_STRUCTURAL_CATEGORIES) == 5

    def test_content_categories_not_included(self) -> None:
        content_cats = {"ai_pattern", "hook_strength", "specificity", "voice"}
        assert _STRUCTURAL_CATEGORIES.isdisjoint(content_cats)


class TestStructuralIssueFilter:
    """Filter removes structural issues and preserves content issues."""

    def test_word_count_issue_is_removed(self) -> None:
        result = _apply_filter([_make_issue("word_count")])
        assert result == []

    def test_paragraph_length_issue_is_removed(self) -> None:
        result = _apply_filter([_make_issue("paragraph_length")])
        assert result == []

    def test_heading_cadence_issue_is_removed(self) -> None:
        result = _apply_filter([_make_issue("heading_cadence")])
        assert result == []

    def test_intro_length_issue_is_removed(self) -> None:
        result = _apply_filter([_make_issue("intro_length")])
        assert result == []

    def test_image_missing_issue_is_removed(self) -> None:
        result = _apply_filter([_make_issue("image_missing")])
        assert result == []

    def test_all_five_structural_categories_removed_at_once(self) -> None:
        raw = [_make_issue(cat) for cat in _STRUCTURAL_CATEGORIES]
        assert _apply_filter(raw) == []

    def test_ai_pattern_issue_is_kept(self) -> None:
        result = _apply_filter([_make_issue("ai_pattern")])
        assert len(result) == 1
        assert result[0].category == "ai_pattern"

    def test_arbitrary_content_category_is_kept(self) -> None:
        result = _apply_filter([_make_issue("hook_strength")])
        assert len(result) == 1
        assert result[0].category == "hook_strength"

    def test_mixed_issues_only_content_survives(self) -> None:
        raw = [
            _make_issue("word_count"),
            _make_issue("ai_pattern"),
            _make_issue("heading_cadence"),
            _make_issue("hook_strength"),
        ]
        result = _apply_filter(raw)
        cats = {r.category for r in result}
        assert cats == {"ai_pattern", "hook_strength"}

    def test_empty_input_gives_empty_output(self) -> None:
        assert _apply_filter([]) == []

    def test_multiple_content_issues_all_preserved(self) -> None:
        raw = [
            _make_issue("ai_pattern"),
            _make_issue("hook_strength"),
            _make_issue("specificity"),
        ]
        result = _apply_filter(raw)
        assert len(result) == 3

    def test_order_of_content_issues_preserved(self) -> None:
        raw = [_make_issue("ai_pattern"), _make_issue("specificity")]
        result = _apply_filter(raw)
        assert result[0].category == "ai_pattern"
        assert result[1].category == "specificity"

    @pytest.mark.parametrize("structural_cat", [
        "word_count",
        "paragraph_length",
        "heading_cadence",
        "intro_length",
        "image_missing",
    ])
    def test_each_structural_category_removed_when_mixed_with_content(
        self, structural_cat: str
    ) -> None:
        raw = [_make_issue(structural_cat), _make_issue("ai_pattern")]
        result = _apply_filter(raw)
        cats = [r.category for r in result]
        assert structural_cat not in cats
        assert "ai_pattern" in cats
