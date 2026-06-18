"""
Tests for quality snapshot persistence.

RED phase: quality_analysis_node must write every analysis result to the
quality_snapshots MongoDB collection so we can accumulate analytics on which
issue categories persist across revision cycles.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.models.post import QualityIssue, QualityReport, ReadRatioFactor


def _make_report(
    *,
    score: float = 0.85,
    read_ratio: float = 0.70,
    word_count: int = 1400,
    boost_eligible: bool = True,
    issues: list[QualityIssue] | None = None,
    strengths: list[str] | None = None,
) -> QualityReport:
    if issues is None:
        issues = [
            QualityIssue(
                severity="HIGH",
                category="paragraph_length",
                location="Section 2",
                suggestion="Split paragraph into two.",
            ),
            QualityIssue(
                severity="MEDIUM",
                category="generic_close",
                location="Conclusion",
                suggestion="Use a specific question.",
            ),
        ]
    return QualityReport(
        score=score,
        read_ratio_prediction=read_ratio,
        read_ratio_hook_score=0.80,
        read_ratio_factors=[
            ReadRatioFactor(name="intro_length", measured="95 words", deduction=0.0, guidance="ok")
        ],
        word_count=word_count,
        medium_boost_eligible=boost_eligible,
        issues=issues,
        strengths=strengths or ["Strong hook", "Good specificity"],
        revision_prompt="Fix paragraph length in Section 2.",
    )


def _make_post_mock(title: str = "Test Post", content: str = "Content here") -> Any:
    post = MagicMock()
    post.title = title
    post.content = content
    return post


def _base_state(revision_count: int = 0, series_id: str | None = None) -> dict[str, Any]:
    return {
        "run_id": "test-run-123",
        "custom_topic": "DeepSeek cost savings",
        "series_id": series_id,
        "series_context": "",
        "series_position": None,
        "trend_context": "",
        "post": _make_post_mock(),
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": revision_count,
        "quality_history": [],
        "errors": [],
        "completed_steps": [],
    }


class TestQualitySnapshotPersistence:
    @pytest.mark.asyncio
    async def test_snapshot_written_on_quality_pass(self) -> None:
        """Must write a snapshot to quality_snapshots when the post passes all gates."""
        from app.agents.orchestrator import quality_analysis_node

        report = _make_report(score=0.95, read_ratio=0.75, word_count=1450)
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        mock_collection.insert_one.assert_called_once()
        snapshot = mock_collection.insert_one.call_args[0][0]
        assert snapshot["run_id"] == "test-run-123"
        assert snapshot["score"] == 0.95
        assert snapshot["passed"] is True

    @pytest.mark.asyncio
    async def test_snapshot_written_on_quality_fail(self) -> None:
        """Must write a snapshot to quality_snapshots even when the post fails gates."""
        from app.agents.orchestrator import quality_analysis_node

        report = _make_report(score=0.70, read_ratio=0.55, word_count=900)
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        mock_collection.insert_one.assert_called_once()
        snapshot = mock_collection.insert_one.call_args[0][0]
        assert snapshot["passed"] is False
        assert len(snapshot["gate_failures"]) > 0

    @pytest.mark.asyncio
    async def test_snapshot_includes_all_issues_not_truncated(self) -> None:
        """Snapshot must include the full issues list, not just top 3."""
        from app.agents.orchestrator import quality_analysis_node

        many_issues = [
            QualityIssue(
                severity="HIGH",
                category=f"cat_{i}",
                location=f"section_{i}",
                suggestion=f"fix {i}",
            )
            for i in range(6)
        ]
        report = _make_report(issues=many_issues)
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        snapshot = mock_collection.insert_one.call_args[0][0]
        assert len(snapshot["issues"]) == 6

    @pytest.mark.asyncio
    async def test_snapshot_iteration_matches_revision_count(self) -> None:
        """Snapshot iteration field must equal the revision_count from state."""
        from app.agents.orchestrator import quality_analysis_node

        report = _make_report()
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state(revision_count=3))

        snapshot = mock_collection.insert_one.call_args[0][0]
        assert snapshot["iteration"] == 3

    @pytest.mark.asyncio
    async def test_snapshot_contains_issue_summary(self) -> None:
        """Snapshot must include a precomputed issue_summary for easy aggregation queries."""
        from app.agents.orchestrator import quality_analysis_node

        issues = [
            QualityIssue(severity="HIGH", category="paragraph_length", location="s1", suggestion="s"),
            QualityIssue(severity="HIGH", category="heading_cadence", location="s2", suggestion="s"),
            QualityIssue(severity="MEDIUM", category="generic_close", location="s3", suggestion="s"),
            QualityIssue(severity="LOW", category="word_count", location="s4", suggestion="s"),
        ]
        report = _make_report(issues=issues)
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        snapshot = mock_collection.insert_one.call_args[0][0]
        summary = snapshot["issue_summary"]
        assert summary["high"] == 2
        assert summary["medium"] == 1
        assert summary["low"] == 1
        assert summary["total"] == 4

    @pytest.mark.asyncio
    async def test_snapshot_includes_topic_and_series_id(self) -> None:
        """Snapshot must include topic and series_id for cross-run analytics."""
        from app.agents.orchestrator import quality_analysis_node

        report = _make_report()
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state(series_id="series-abc"))

        snapshot = mock_collection.insert_one.call_args[0][0]
        assert snapshot["topic"] == "DeepSeek cost savings"
        assert snapshot["series_id"] == "series-abc"


class TestMaxRevisionCycles:
    def test_max_revision_cycles_is_six(self) -> None:
        """Default max_revision_cycles must be 6 to allow the pipeline enough attempts."""
        from app.config import Settings
        s = Settings()
        assert s.max_revision_cycles == 6, (
            "max_revision_cycles default must be 6 — was 2, not enough for structural fixes"
        )


# ── Structural checker integration ───────────────────────────────────────────

class TestStructuralCheckerIntegration:
    """Structural issues are prepended to LLM issues in quality_analysis_node."""

    @pytest.mark.asyncio
    async def test_structural_issues_prepended_to_llm_issues(self) -> None:
        """Structural checker runs first; its issues appear before LLM content issues."""
        from app.agents.orchestrator import quality_analysis_node

        llm_report = _make_report(issues=[
            QualityIssue(severity="HIGH", category="ai_pattern", location="para 1", suggestion="Remove 'Moreover'"),
        ])
        struct_issue = QualityIssue(
            severity="HIGH", category="paragraph_length",
            location="para 2", suggestion="Split paragraph",
        )
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=llm_report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[struct_issue]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        snapshot = mock_collection.insert_one.call_args[0][0]
        assert len(snapshot["issues"]) == 2
        assert snapshot["issues"][0]["category"] == "paragraph_length"
        assert snapshot["issues"][1]["category"] == "ai_pattern"

    @pytest.mark.asyncio
    async def test_structural_checker_called_with_post_content(self) -> None:
        """Structural checker must receive the actual post content string."""
        from app.agents.orchestrator import quality_analysis_node

        llm_report = _make_report()
        mock_structural = MagicMock(return_value=[])
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        post_content = "The actual post content for this test."
        state = _base_state()
        state["post"] = _make_post_mock(content=post_content)

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=llm_report),
            patch("app.agents.orchestrator.run_structural_checks", mock_structural),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(state)

        mock_structural.assert_called_once_with(post_content)

    @pytest.mark.asyncio
    async def test_no_structural_issues_report_unchanged(self) -> None:
        """When structural checker finds nothing, only LLM issues appear in snapshot."""
        from app.agents.orchestrator import quality_analysis_node

        llm_report = _make_report(issues=[
            QualityIssue(severity="HIGH", category="ai_pattern", location="p1", suggestion="fix"),
        ])
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=llm_report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        snapshot = mock_collection.insert_one.call_args[0][0]
        assert len(snapshot["issues"]) == 1
        assert snapshot["issues"][0]["category"] == "ai_pattern"

    @pytest.mark.asyncio
    async def test_merged_issue_summary_counts_structural_issues(self) -> None:
        """issue_summary counts must reflect merged (structural + LLM) issues."""
        from app.agents.orchestrator import quality_analysis_node

        llm_report = _make_report(issues=[
            QualityIssue(severity="MEDIUM", category="ai_pattern", location="p1", suggestion="fix"),
        ])
        structural_issues = [
            QualityIssue(severity="HIGH", category="paragraph_length", location="s1", suggestion="split"),
            QualityIssue(severity="HIGH", category="word_count", location="s2", suggestion="expand"),
        ]
        mock_collection = AsyncMock()
        mock_db = MagicMock()
        mock_db.quality_snapshots = mock_collection
        mock_db.posts = AsyncMock()
        mock_db.posts.update_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.run_quality_analysis", return_value=llm_report),
            patch("app.agents.orchestrator.run_structural_checks", return_value=structural_issues),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
        ):
            await quality_analysis_node(_base_state())

        snapshot = mock_collection.insert_one.call_args[0][0]
        summary = snapshot["issue_summary"]
        assert summary["high"] == 2
        assert summary["medium"] == 1
        assert summary["total"] == 3
