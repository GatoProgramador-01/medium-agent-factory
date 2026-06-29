"""
Unit tests for TitleOptimizer — generates headline variants and selects the strongest.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.title_optimizer import (
    TitleOptimizationResult,
    TitleVariant,
    run_title_optimization,
)
from app.agents.orchestrator import PipelineState


class TestTitleVariant:
    """Test TitleVariant Pydantic model validation."""

    def test_creates_variant_with_valid_scores(self) -> None:
        """TitleVariant instantiates with valid scores in [0, 1]."""
        variant = TitleVariant(
            text="My API Bill Dropped 94% When I Stopped Using GPT-4",
            formula="OUTCOME",
            specificity_score=0.9,
            curiosity_gap=0.85,
            seo_friendliness=0.8,
        )
        assert variant.text
        assert variant.formula == "OUTCOME"
        assert 0.0 <= variant.specificity_score <= 1.0
        assert 0.0 <= variant.curiosity_gap <= 1.0
        assert 0.0 <= variant.seo_friendliness <= 1.0

    def test_score_boundaries_are_inclusive(self) -> None:
        """TitleVariant accepts 0.0 and 1.0 as valid boundary scores."""
        v = TitleVariant(
            text="Why Cheap LLMs Are Not Always Cheap",
            formula="COUNTER-INTUITIVE",
            specificity_score=0.0,
            curiosity_gap=1.0,
            seo_friendliness=0.5,
        )
        assert v.specificity_score == 0.0
        assert v.curiosity_gap == 1.0


class TestTitleOptimizationResult:
    """Test TitleOptimizationResult Pydantic model and validators."""

    def test_returns_result_with_best_title(self) -> None:
        """TitleOptimizationResult instantiates with valid variants and best_title."""
        variants = [
            TitleVariant(
                text="Understanding AI Cost Optimization",
                formula="OUTCOME",
                specificity_score=0.3,
                curiosity_gap=0.2,
                seo_friendliness=0.4,
            ),
            TitleVariant(
                text="My API Bill Dropped 94% When I Stopped Sending Long Contexts",
                formula="OUTCOME",
                specificity_score=0.95,
                curiosity_gap=0.9,
                seo_friendliness=0.85,
            ),
        ]
        result = TitleOptimizationResult(
            variants=variants,
            best_title="My API Bill Dropped 94% When I Stopped Sending Long Contexts",
            original_title_weakness="Original title was too vague — no measurable outcome.",
        )
        assert result.best_title == variants[1].text
        assert len(result.variants) == 2
        assert result.original_title_weakness

    def test_variants_coerces_json_string(self) -> None:
        """TitleOptimizationResult._coerce_json_string handles JSON string input."""
        json_str = json.dumps(
            [
                {
                    "text": "The 8K Token Threshold That Changed Everything",
                    "formula": "THRESHOLD",
                    "specificity_score": 0.85,
                    "curiosity_gap": 0.9,
                    "seo_friendliness": 0.7,
                }
            ]
        )
        result = TitleOptimizationResult(
            variants=json_str,
            best_title="The 8K Token Threshold That Changed Everything",
            original_title_weakness="",
        )
        assert len(result.variants) == 1
        assert result.variants[0].text == "The 8K Token Threshold That Changed Everything"

    def test_variants_coerces_malformed_json_to_empty_list(self) -> None:
        """TitleOptimizationResult._coerce_json_string returns [] on JSON decode error."""
        malformed = '{"text": "broken json, "formula": "bad}'
        result = TitleOptimizationResult(
            variants=malformed,
            best_title="fallback title",
            original_title_weakness="",
        )
        assert isinstance(result.variants, list)

    def test_variants_coerces_curly_quote_json(self) -> None:
        """TitleOptimizationResult._coerce_json_string handles curly quotes from LLMs."""
        # LLMs often emit curly quotes that break standard json.loads
        curly_quote_json = (
            '[{"text": “Why Cheap Models Cost More”, '
            '"formula": "COUNTER-INTUITIVE", '
            '"specificity_score": 0.7, '
            '"curiosity_gap": 0.8, '
            '"seo_friendliness": 0.6}]'
        )
        result = TitleOptimizationResult(
            variants=curly_quote_json,
            best_title="Why Cheap Models Cost More",
            original_title_weakness="",
        )
        assert isinstance(result.variants, list)


@pytest.mark.asyncio
async def test_run_title_optimization_returns_result() -> None:
    """run_title_optimization returns TitleOptimizationResult with best_title."""
    mock_response = TitleOptimizationResult(
        variants=[
            TitleVariant(
                text="DeepSeek V3 Beat GPT-4o on Cost — Until It Didn't",
                formula="SPECIFIC_FAILURE",
                specificity_score=0.9,
                curiosity_gap=0.95,
                seo_friendliness=0.8,
            ),
            TitleVariant(
                text="The 8K Token Threshold That Broke My DeepSeek Budget",
                formula="THRESHOLD",
                specificity_score=0.92,
                curiosity_gap=0.88,
                seo_friendliness=0.75,
            ),
        ],
        best_title="DeepSeek V3 Beat GPT-4o on Cost — Until It Didn't",
        original_title_weakness="Original title lacked a specific outcome or threshold.",
    )

    with patch("app.agents.title_optimizer.get_llm") as mock_get_llm, patch(
        "app.agents.title_optimizer.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_title_optimization(
            run_id="test-run-456",
            title="Understanding LLM Cost Optimization",
            content="My API bill dropped from $2,800 to $178 the month I stopped sending long contexts to DeepSeek.",
            refined_angle="DeepSeek V3 wins on cost up to 8K tokens - above that threshold Claude caching competes.",
        )

        assert result.best_title == mock_response.best_title
        assert len(result.variants) == 2
        assert result.original_title_weakness


@pytest.mark.asyncio
async def test_run_title_optimization_raises_on_none() -> None:
    """run_title_optimization raises ValueError when LLM returns None."""
    with patch("app.agents.title_optimizer.get_llm") as mock_get_llm, patch(
        "app.agents.title_optimizer.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="LLM returned None"):
            await run_title_optimization(
                run_id="test-run-456",
                title="Test title",
                content="Test content...",
                refined_angle="",
            )


@pytest.mark.asyncio
async def test_title_optimization_node_replaces_post_title() -> None:
    """title_optimization_node replaces post.title with best_title and stores variants."""
    from app.agents.orchestrator import title_optimization_node
    from app.agents.content_generator import GeneratedPost

    original_title = "Understanding LLM Cost Optimization"
    best_title = "My API Bill Dropped 94% When I Stopped Sending Long Contexts"

    mock_post = GeneratedPost(
        title=original_title,
        subtitle="A practical guide",
        content="My API bill dropped from $2,800 to $178 the month I switched strategies.",
        tags=["AI", "LLM"],
        image_suggestions=[],
    )

    mock_response = TitleOptimizationResult(
        variants=[
            TitleVariant(
                text=best_title,
                formula="OUTCOME",
                specificity_score=0.95,
                curiosity_gap=0.9,
                seo_friendliness=0.85,
            )
        ],
        best_title=best_title,
        original_title_weakness="Original title was too generic — no measurable outcome.",
    )

    state: PipelineState = {
        "run_id": "test-123",
        "custom_topic": "LLM cost optimization",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": {"refined_angle": "DeepSeek V3 wins on cost up to 8K tokens."},
        "post": mock_post,
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
        "draft_content": "",
        "title_variants": [],
    }

    with patch(
        "app.agents.orchestrator.run_title_optimization"
    ) as mock_optimize, patch(
        "app.agents.orchestrator.log_step", new_callable=AsyncMock
    ):
        mock_optimize.return_value = mock_response

        result = await title_optimization_node(state)

        assert result.get("post") is not None
        assert result["post"].title == best_title
        assert "title_variants" in result
        assert best_title in result["title_variants"]
        assert "title_optimization" in result.get("completed_steps", [])
        # Original title must no longer be the post title
        assert result["post"].title != original_title


@pytest.mark.asyncio
async def test_title_optimization_node_falls_back_on_exception() -> None:
    """title_optimization_node returns empty dict on exception (keeps original title)."""
    from app.agents.orchestrator import title_optimization_node
    from app.agents.content_generator import GeneratedPost

    original_title = "Understanding AI Costs"
    mock_post = GeneratedPost(
        title=original_title,
        subtitle="",
        content="Some content here.",
        tags=[],
        image_suggestions=[],
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
        "topic_brief": None,
        "post": mock_post,
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
        "draft_content": "",
        "title_variants": [],
    }

    with patch(
        "app.agents.orchestrator.run_title_optimization"
    ) as mock_optimize, patch(
        "app.agents.orchestrator.log_step", new_callable=AsyncMock
    ):
        mock_optimize.side_effect = RuntimeError("LLM connection failed")

        result = await title_optimization_node(state)

        # On error, node returns empty dict (pipeline keeps original)
        assert result == {}
        # Post title must be unchanged
        assert mock_post.title == original_title


@pytest.mark.asyncio
async def test_title_optimization_node_returns_empty_on_no_post() -> None:
    """title_optimization_node returns empty dict when state has no post."""
    from app.agents.orchestrator import title_optimization_node

    state: PipelineState = {
        "run_id": "test-no-post",
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
        "draft_content": "",
        "title_variants": [],
    }

    result = await title_optimization_node(state)

    assert result == {}
