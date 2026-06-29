"""
Unit tests for SeriesCoherenceChecker — validates series installment continuity.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.series_coherence_checker import (
    SeriesCoherenceIssue,
    SeriesCoherenceResult,
    run_series_coherence_check,
)


class TestSeriesCoherenceIssue:
    """Test SeriesCoherenceIssue Pydantic model validation."""

    def test_creates_issue_with_valid_severity(self) -> None:
        for severity in ("LOW", "MEDIUM", "HIGH"):
            issue = SeriesCoherenceIssue(
                category="continuity",
                severity=severity,
                location="Paragraph 3",
                suggestion="Add a callback to Part 1's cost numbers.",
            )
            assert issue.severity == severity

    def test_all_categories_accepted(self) -> None:
        for category in ("continuity", "repetition", "spoiler", "missing_callback"):
            issue = SeriesCoherenceIssue(
                category=category,
                severity="MEDIUM",
                location="Intro",
                suggestion="Fix the issue.",
            )
            assert issue.category == category


class TestSeriesCoherenceResult:
    """Test SeriesCoherenceResult Pydantic model and validators."""

    def test_creates_result_with_score_and_issues(self) -> None:
        result = SeriesCoherenceResult(
            coherence_score=0.85,
            issues=[
                SeriesCoherenceIssue(
                    category="missing_callback",
                    severity="LOW",
                    location="Conclusion",
                    suggestion="Reference the benchmark from Part 1.",
                )
            ],
            continuity_notes=["Part 1 introduced the cost problem; Part 2 should solve it."],
            revised_content="",
        )
        assert result.coherence_score == 0.85
        assert len(result.issues) == 1
        assert len(result.continuity_notes) == 1

    def test_empty_issues_is_valid(self) -> None:
        result = SeriesCoherenceResult(
            coherence_score=1.0,
            issues=[],
            continuity_notes=[],
            revised_content="",
        )
        assert result.issues == []
        assert result.coherence_score == 1.0

    def test_issues_coerces_json_string(self) -> None:
        issues_json = json.dumps(
            [
                {
                    "category": "repetition",
                    "severity": "LOW",
                    "location": "Section 2",
                    "suggestion": "Remove repeated benchmark paragraph.",
                }
            ]
        )
        result = SeriesCoherenceResult(
            coherence_score=0.75,
            issues=issues_json,  # type: ignore[arg-type]
            continuity_notes=[],
            revised_content="",
        )
        assert len(result.issues) == 1

    def test_continuity_notes_coerces_invalid_json_to_empty(self) -> None:
        result = SeriesCoherenceResult(
            coherence_score=0.9,
            issues=[],
            continuity_notes="not json",  # type: ignore[arg-type]
            revised_content="",
        )
        assert result.continuity_notes == []

    def test_score_boundaries_accepted(self) -> None:
        for score in (0.0, 0.5, 1.0):
            result = SeriesCoherenceResult(
                coherence_score=score,
                issues=[],
                continuity_notes=[],
                revised_content="",
            )
            assert result.coherence_score == score


@pytest.mark.asyncio
async def test_run_series_coherence_check_returns_result() -> None:
    """run_series_coherence_check returns SeriesCoherenceResult when LLM succeeds."""
    mock_response = SeriesCoherenceResult(
        coherence_score=0.88,
        issues=[
            SeriesCoherenceIssue(
                category="missing_callback",
                severity="LOW",
                location="Conclusion",
                suggestion="Add a forward reference to Part 3.",
            )
        ],
        continuity_notes=["Part 2 correctly builds on the cost analysis from Part 1."],
        revised_content="",
    )

    with patch("app.agents.series_coherence_checker.get_llm") as mock_get_llm, patch(
        "app.agents.series_coherence_checker.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_series_coherence_check(
            run_id="test-run-001",
            title="Part 2: Solving the Cost Problem",
            content="This post solves the problem introduced in Part 1.",
            series_context="3-part series on LLM cost optimization. Part 1 covered the problem.",
            series_position=2,
        )

    assert isinstance(result, SeriesCoherenceResult)
    assert result.coherence_score == mock_response.coherence_score
    assert len(result.issues) == 1


@pytest.mark.asyncio
async def test_run_series_coherence_check_raises_on_none() -> None:
    """run_series_coherence_check raises ValueError when LLM returns None."""
    with patch("app.agents.series_coherence_checker.get_llm") as mock_get_llm, patch(
        "app.agents.series_coherence_checker.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="series_coherence_checker"):
            await run_series_coherence_check(
                run_id="test-run-002",
                title="Part 2",
                content="Some content.",
                series_context="Series context here.",
            )


@pytest.mark.asyncio
async def test_run_series_coherence_check_without_position() -> None:
    """run_series_coherence_check works when series_position is None."""
    mock_response = SeriesCoherenceResult(
        coherence_score=0.92,
        issues=[],
        continuity_notes=["Position not specified; general coherence check passed."],
        revised_content="",
    )

    with patch("app.agents.series_coherence_checker.get_llm") as mock_get_llm, patch(
        "app.agents.series_coherence_checker.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_series_coherence_check(
            run_id="test-run-003",
            title="An Installment",
            content="Content without position info.",
            series_context="Series about AI cost.",
        )

    assert isinstance(result, SeriesCoherenceResult)
    assert result.coherence_score == 0.92


@pytest.mark.asyncio
async def test_run_series_coherence_check_detects_high_severity_issue() -> None:
    """run_series_coherence_check returns HIGH severity issues when post spoils future content."""
    mock_response = SeriesCoherenceResult(
        coherence_score=0.45,
        issues=[
            SeriesCoherenceIssue(
                category="spoiler",
                severity="HIGH",
                location="Section 3",
                suggestion="Remove the benchmark numbers that belong in Part 3.",
            ),
            SeriesCoherenceIssue(
                category="repetition",
                severity="MEDIUM",
                location="Introduction",
                suggestion="Remove the repeated problem statement from Part 1.",
            ),
        ],
        continuity_notes=["Post reveals the final benchmark results too early."],
        revised_content="",
    )

    with patch("app.agents.series_coherence_checker.get_llm") as mock_get_llm, patch(
        "app.agents.series_coherence_checker.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_series_coherence_check(
            run_id="test-run-004",
            title="Part 2: The Journey",
            content="In Part 3 we will show that the cost dropped by exactly 94%.",
            series_context="3-part series; benchmarks revealed only in Part 3.",
            series_position=2,
        )

    high_issues = [i for i in result.issues if i.severity == "HIGH"]
    assert len(high_issues) >= 1
    assert any(i.category == "spoiler" for i in high_issues)
