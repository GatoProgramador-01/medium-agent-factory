"""Tests for topic_refinement_node in the orchestrator."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_topic_refinement_node_sets_refined_topic():
    from app.agents.orchestrator import topic_refinement_node

    mock_brief = MagicMock()
    mock_brief.formatted_brief = "ANGLE: DeepSeek wins... HOOK: My bill dropped..."
    mock_brief.refined_angle = "DeepSeek cost savings"
    mock_brief.target_audience = "developers"
    mock_brief.model_dump.return_value = {"refined_angle": "test", "hook_seed": "test"}

    with patch("app.agents.orchestrator.log_step", new_callable=AsyncMock):
        with patch("app.agents.topic_refiner.run_topic_refinement", new_callable=AsyncMock, return_value=mock_brief):
            result = await topic_refinement_node({
                "run_id": "r1",
                "custom_topic": "DeepSeek vs Claude",
                "trend_context": "DeepSeek pricing...",
                "grounding_context": "I saved $2k",
                "series_id": None,
                "series_position": None,
                "series_context": "",
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
            })

    assert result["refined_topic"] == "ANGLE: DeepSeek wins... HOOK: My bill dropped..."
    assert result["topic_brief"] is not None


@pytest.mark.asyncio
async def test_topic_refinement_node_falls_back_on_error():
    from app.agents.orchestrator import topic_refinement_node

    with patch("app.agents.orchestrator.log_step", new_callable=AsyncMock):
        with patch("app.agents.topic_refiner.run_topic_refinement", side_effect=Exception("API error")):
            result = await topic_refinement_node({
                "run_id": "r1",
                "custom_topic": "raw topic",
                "trend_context": "",
                "grounding_context": "",
                "series_id": None,
                "series_position": None,
                "series_context": "",
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
            })

    assert result["refined_topic"] == "raw topic"
    assert result["topic_brief"] is None


@pytest.mark.asyncio
async def test_topic_refinement_node_uses_grounding_context():
    from app.agents.orchestrator import topic_refinement_node

    mock_brief = MagicMock()
    mock_brief.formatted_brief = "brief"
    mock_brief.refined_angle = "test"
    mock_brief.target_audience = "test"
    mock_brief.model_dump.return_value = {}

    with patch("app.agents.orchestrator.log_step", new_callable=AsyncMock):
        with patch("app.agents.topic_refiner.run_topic_refinement", new_callable=AsyncMock, return_value=mock_brief) as mock_refine:
            await topic_refinement_node({
                "run_id": "r1",
                "custom_topic": "topic",
                "trend_context": "research",
                "grounding_context": "user provided this",
                "series_id": None,
                "series_position": None,
                "series_context": "",
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
            })

    mock_refine.assert_called_once()
    call_kwargs = mock_refine.call_args.kwargs
    assert call_kwargs.get("grounding_context") == "user provided this"


def test_pipeline_state_has_refined_topic_key():
    from app.agents.orchestrator import PipelineState
    # PipelineState is a TypedDict — check the key is declared
    hints = PipelineState.__annotations__
    assert "refined_topic" in hints


def test_pipeline_state_has_topic_brief_key():
    from app.agents.orchestrator import PipelineState
    hints = PipelineState.__annotations__
    assert "topic_brief" in hints
