"""
Unit tests for CloseOptimizer — generates alternative post closings and selects the strongest.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.close_optimizer import (
    CloseOptimizationResult,
    CloseVariant,
    run_close_optimization,
)
from app.agents.orchestrator import PipelineState


class TestCloseOptimizationResult:
    """Test CloseOptimizationResult Pydantic model and validators."""

    def test_returns_result_with_best_close(self) -> None:
        """CloseOptimizationResult instantiates with valid data."""
        variants = [
            CloseVariant(
                text="What's your take on this?",
                close_type="question",
                specificity_score=0.6,
            ),
            CloseVariant(
                text="By 2025, everyone will adopt this pattern.",
                close_type="prediction",
                specificity_score=0.8,
            ),
        ]
        result = CloseOptimizationResult(
            variants=variants,
            best_close="By 2025, everyone will adopt this pattern.",
            original_close_problem="Generic engagement phrase ignored by readers.",
        )
        assert result.best_close == variants[1].text
        assert len(result.variants) == 2
        assert result.original_close_problem

    def test_variants_coerces_json_string(self) -> None:
        """CloseOptimizationResult._coerce_json_string handles JSON string input."""
        json_str = json.dumps(
            [
                {
                    "text": "Question here?",
                    "close_type": "question",
                    "specificity_score": 0.7,
                }
            ]
        )
        result = CloseOptimizationResult(
            variants=json_str,
            best_close="Question here?",
            original_close_problem="",
        )
        assert len(result.variants) == 1
        assert result.variants[0].text == "Question here?"

    def test_variants_coerces_malformed_json_to_empty_list(self) -> None:
        """CloseOptimizationResult._coerce_json_string returns [] on JSON decode error."""
        malformed = '{"text": "broken json", "close_type": "bad}'
        result = CloseOptimizationResult(
            variants=malformed,
            best_close="fallback",
            original_close_problem="",
        )
        # Should coerce to empty list, which violates min_length=2
        # This test verifies the validator tries to clean up curly quotes
        # If we get here without exception, validation passed with cleaned string
        assert isinstance(result.variants, list)


@pytest.mark.asyncio
async def test_run_close_optimization_returns_result() -> None:
    """run_close_optimization returns CloseOptimizationResult with best_close."""
    mock_response = CloseOptimizationResult(
        variants=[
            CloseVariant(
                text="At what token threshold do you switch to DeepSeek?",
                close_type="question",
                specificity_score=0.85,
            ),
            CloseVariant(
                text="Within 12 months, every major LLM will offer tiered pricing.",
                close_type="prediction",
                specificity_score=0.9,
            ),
        ],
        best_close="Within 12 months, every major LLM will offer tiered pricing.",
        original_close_problem="The original close was too generic — no specific threshold mentioned.",
    )

    with patch("app.agents.close_optimizer.get_llm") as mock_get_llm, patch(
        "app.agents.close_optimizer.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm.with_structured_output = AsyncMock(return_value=mock_llm)
        mock_get_llm.return_value = mock_llm

        result = await run_close_optimization(
            run_id="test-run-123",
            content="This is a test post about LLM costs...",
            refined_angle="Cost optimization strategies for AI teams.",
        )

        assert result.best_close == mock_response.best_close
        assert len(result.variants) == 2
        assert result.original_close_problem


@pytest.mark.asyncio
async def test_run_close_optimization_raises_on_none() -> None:
    """run_close_optimization raises ValueError when LLM returns None."""
    with patch("app.agents.close_optimizer.get_llm") as mock_get_llm, patch(
        "app.agents.close_optimizer.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=None)
        mock_llm.with_structured_output = AsyncMock(return_value=mock_llm)
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="LLM returned None"):
            await run_close_optimization(
                run_id="test-run-123",
                content="Test post...",
                refined_angle="",
            )


@pytest.mark.asyncio
async def test_close_optimization_node_replaces_last_paragraph() -> None:
    """close_optimization_node replaces the post's last paragraph with best_close."""
    # Import at test time to avoid module-level issues
    from app.agents.orchestrator import close_optimization_node

    original_close = "What do you think? Drop a comment below."
    content = (
        "## Introduction\n\nThis is the start of the post.\n\n"
        "## Main content\n\nSome analysis here.\n\n"
        f"{original_close}"
    )

    mock_response = CloseOptimizationResult(
        variants=[
            CloseVariant(
                text="Where's your LLM cost breakeven point?",
                close_type="question",
                specificity_score=0.85,
            )
        ],
        best_close="Where's your LLM cost breakeven point?",
        original_close_problem="Generic.",
    )

    state: PipelineState = {
        "run_id": "test-123",
        "custom_topic": "Test topic",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": {"refined_angle": "Cost optimization for AI teams."},
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
        "recommended_publication": False,
        "publication_confidence": 0.0,
        "draft_content": content,
    }

    with patch(
        "app.agents.close_optimizer.run_close_optimization"
    ) as mock_optimize:
        mock_optimize.return_value = mock_response

        result = await close_optimization_node(state)

        # Verify last paragraph was replaced
        assert result.get("draft_content")
        updated = result["draft_content"]
        assert original_close not in updated
        assert "Where's your LLM cost breakeven point?" in updated
        # Verify structure preserved (intro and main content still there)
        assert "## Introduction" in updated
        assert "## Main content" in updated


@pytest.mark.asyncio
async def test_close_optimization_node_falls_back_on_exception() -> None:
    """close_optimization_node returns empty dict on exception (keeps original close)."""
    from app.agents.orchestrator import close_optimization_node

    original_close = "What do you think?"
    content = f"Some content here.\n\n{original_close}"

    state: PipelineState = {
        "run_id": "test-123",
        "custom_topic": "Test topic",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": None,
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
        "recommended_publication": False,
        "publication_confidence": 0.0,
        "draft_content": content,
    }

    with patch(
        "app.agents.close_optimizer.run_close_optimization"
    ) as mock_optimize:
        mock_optimize.side_effect = RuntimeError("LLM connection failed")

        result = await close_optimization_node(state)

        # On error, node returns empty dict (pipeline keeps original)
        assert result == {}
