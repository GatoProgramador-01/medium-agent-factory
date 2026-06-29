"""
Finalize node — exemplar saving tests.

RED phase: tests verify that finalize_node calls save_exemplar when
quality_score >= 0.95 (EXEMPLAR_THRESHOLD), and that exceptions during
exemplar saving do not crash the pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any

import pytest

from app.agents.content_generator import GeneratedPost
from app.agents.orchestrator import finalize_node, PipelineState
from app.models.post import QualityReport, QualityIssue, PostStatus


@pytest.fixture
def mock_db() -> MagicMock:
    """Mock database for finalize_node tests."""
    db = MagicMock()
    db.posts = MagicMock()
    db.posts.update_one = AsyncMock()
    db.pipeline_runs = MagicMock()
    db.pipeline_runs.update_one = AsyncMock()
    return db


@pytest.fixture
def mock_settings() -> MagicMock:
    """Mock settings for quality thresholds."""
    settings = MagicMock()
    settings.max_revision_cycles = 3
    return settings


@pytest.fixture
def base_state() -> PipelineState:
    """Base pipeline state for finalize tests."""
    return {
        "run_id": "test-run-123",
        "custom_topic": "Test Topic",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "post": GeneratedPost(
            title="Test Post Title",
            subtitle="Test Subtitle",
            content="Test content here.\n\nMore content.",
            tags=["test", "example"],
            image_suggestions=["suggestion1"],
        ),
        "quality_report": QualityReport(
            score=0.96,
            word_count=1500,
            read_ratio_prediction=0.75,
            hook_strength=0.85,
            specificity_score=0.80,
            voice_authenticity=0.88,
            insight_value=0.92,
            medium_boost_eligible=True,
            read_ratio_hook_score=0.85,
            read_ratio_factors=[],
            issues=[],
            strengths=["strong hook"],
            revision_prompt="Revise for clarity",
        ),
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
        "recommended_publication": True,
        "publication_confidence": 0.85,
    }


class TestFinalizeExemplarSaving:
    @pytest.mark.asyncio
    async def test_finalize_calls_save_exemplar_when_score_gte_095(
        self, base_state: PipelineState, mock_db: MagicMock
    ) -> None:
        """
        When quality_score >= 0.95 (EXEMPLAR_THRESHOLD),
        finalize_node should call save_exemplar with the post data.
        """
        with patch("app.agents.orchestrator.get_db", return_value=mock_db):
            with patch(
                "app.agents.orchestrator.save_exemplar", new_callable=AsyncMock
            ) as mock_save:
                with patch(
                    "app.agents.orchestrator.log_step", new_callable=AsyncMock
                ):
                    # Ensure score meets threshold
                    assert base_state["quality_report"].score >= 0.95
                    assert base_state["post"] is not None

                    result = await finalize_node(base_state)

                    # Assert save_exemplar was called
                    mock_save.assert_called_once()
                    call_args = mock_save.call_args
                    assert call_args is not None
                    # Check that title and content were passed
                    assert call_args.kwargs["title"] == "Test Post Title"
                    assert "Test content here" in call_args.kwargs["content"]
                    assert call_args.kwargs["score"] == 0.96
                    assert call_args.kwargs["tags"] == ["test", "example"]

                    # finalize should return successfully
                    assert "completed_steps" in result
                    assert "finalized" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_finalize_skips_exemplar_when_score_lt_095(
        self, base_state: PipelineState, mock_db: MagicMock
    ) -> None:
        """
        When quality_score < 0.95, finalize_node should NOT call save_exemplar.
        """
        # Set score below threshold
        base_state["quality_report"].score = 0.85

        with patch("app.agents.orchestrator.get_db", return_value=mock_db):
            with patch(
                "app.agents.orchestrator.save_exemplar", new_callable=AsyncMock
            ) as mock_save:
                with patch(
                    "app.agents.orchestrator.log_step", new_callable=AsyncMock
                ):
                    result = await finalize_node(base_state)

                    # Assert save_exemplar was NOT called
                    mock_save.assert_not_called()

                    # finalize should still complete
                    assert "completed_steps" in result
                    assert "finalized" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_finalize_exemplar_exception_does_not_crash(
        self, base_state: PipelineState, mock_db: MagicMock
    ) -> None:
        """
        If save_exemplar raises an Exception, finalize_node should catch it
        and continue (wrapped in try/except). The pipeline should not crash.
        """
        with patch("app.agents.orchestrator.get_db", return_value=mock_db):
            with patch(
                "app.agents.orchestrator.save_exemplar", new_callable=AsyncMock
            ) as mock_save:
                # Make save_exemplar raise an exception
                mock_save.side_effect = Exception("Exemplar DB unavailable")

                with patch(
                    "app.agents.orchestrator.log_step", new_callable=AsyncMock
                ):
                    # Should not raise
                    result = await finalize_node(base_state)

                    # finalize should still complete successfully
                    assert "completed_steps" in result
                    assert "finalized" in result["completed_steps"]
                    # No errors added to state
                    assert not base_state.get("errors")

    @pytest.mark.asyncio
    async def test_finalize_with_no_post_skips_exemplar(
        self, base_state: PipelineState, mock_db: MagicMock
    ) -> None:
        """
        If post is None, finalize should not attempt save_exemplar.
        """
        base_state["post"] = None

        with patch("app.agents.orchestrator.get_db", return_value=mock_db):
            with patch(
                "app.agents.orchestrator.save_exemplar", new_callable=AsyncMock
            ) as mock_save:
                with patch(
                    "app.agents.orchestrator.log_step", new_callable=AsyncMock
                ):
                    result = await finalize_node(base_state)

                    # save_exemplar should not be called
                    mock_save.assert_not_called()

                    # finalize should still complete
                    assert "completed_steps" in result
                    assert "finalized" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_finalize_with_no_quality_report_skips_exemplar(
        self, base_state: PipelineState, mock_db: MagicMock
    ) -> None:
        """
        If quality_report is None, finalize should not attempt save_exemplar.
        """
        base_state["quality_report"] = None

        with patch("app.agents.orchestrator.get_db", return_value=mock_db):
            with patch(
                "app.agents.orchestrator.save_exemplar", new_callable=AsyncMock
            ) as mock_save:
                with patch(
                    "app.agents.orchestrator.log_step", new_callable=AsyncMock
                ):
                    result = await finalize_node(base_state)

                    # save_exemplar should not be called
                    mock_save.assert_not_called()

                    # finalize should still complete
                    assert "completed_steps" in result
                    assert "finalized" in result["completed_steps"]
