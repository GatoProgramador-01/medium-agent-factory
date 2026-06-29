"""
Unit tests for orchestrator nodes: intro_ab_testing_node and series_coherence_node.

Tests verify that the nodes correctly invoke agent functions, handle errors gracefully,
and return properly structured state updates.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.orchestrator import (
    intro_ab_testing_node,
    series_coherence_node,
    PipelineState,
)
from app.agents.content_generator import GeneratedPost
from app.agents.intro_ab_tester import IntroABTestResult, IntroVariant
from app.agents.series_coherence_checker import (
    SeriesCoherenceResult,
    SeriesCoherenceIssue,
)


class TestIntroABTestingNode:
    """Test intro_ab_testing_node: replaces first paragraph with A/B-tested intro."""

    @pytest.mark.asyncio
    async def test_intro_ab_testing_node_replaces_first_paragraph(self) -> None:
        """intro_ab_testing_node replaces first paragraph with best_intro."""
        original_intro = "The old introduction paragraph that was not very strong."
        best_intro = "My API bills dropped 94% when I stopped sending long contexts."

        mock_post = GeneratedPost(
            title="Cost Optimization Strategy",
            subtitle="A practical guide",
            content=f"{original_intro}\n\nSecond paragraph with body content.\n\nThird paragraph.",
            tags=["ai", "costs", "optimization", "llm", "budget"],
            image_suggestions=["cost chart", "comparison graph", "before/after diagram"],
        )

        mock_result = IntroABTestResult(
            variants=[
                IntroVariant(
                    text=best_intro,
                    hook_type="outcome",
                    specificity_score=0.95,
                    curiosity_gap=0.9,
                    voice_authenticity=0.85,
                ),
                IntroVariant(
                    text="Alternative hook about cost reduction.",
                    hook_type="data_point",
                    specificity_score=0.85,
                    curiosity_gap=0.8,
                    voice_authenticity=0.8,
                ),
            ],
            best_intro=best_intro,
            original_intro_problem="Original lacked a specific outcome.",
        )

        state: PipelineState = {
            "run_id": "test-sprint18-001",
            "custom_topic": "LLM cost optimization",
            "grounding_context": "",
            "series_id": None,
            "series_position": None,
            "series_context": "",
            "trend_context": "",
            "refined_topic": None,
            "topic_brief": {"refined_angle": "Focus on token efficiency."},
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_intro_ab_test"
        ) as mock_run_test, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_run_test.return_value = mock_result

            result = await intro_ab_testing_node(state)

            assert result.get("post") is not None
            assert result["post"].content.startswith(best_intro)
            assert "intro_variants" in result
            assert best_intro in result["intro_variants"]
            assert "intro_ab_testing" in result.get("completed_steps", [])

    @pytest.mark.asyncio
    async def test_intro_ab_testing_node_returns_empty_on_no_post(self) -> None:
        """intro_ab_testing_node returns empty dict when post is None."""
        state: PipelineState = {
            "run_id": "test-sprint18-002",
            "custom_topic": "topic",
            "grounding_context": "",
            "series_id": None,
            "series_position": None,
            "series_context": "",
            "trend_context": "",
            "refined_topic": None,
            "topic_brief": None,
            "post": None,  # No post
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        result = await intro_ab_testing_node(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_intro_ab_testing_node_returns_empty_on_no_content(self) -> None:
        """intro_ab_testing_node returns empty dict when post.content is empty."""
        mock_post = GeneratedPost(
            title="Empty Post",
            subtitle="",
            content="",  # Empty content
            tags=["empty"],
            image_suggestions=[],
        )

        state: PipelineState = {
            "run_id": "test-sprint18-003",
            "custom_topic": "topic",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        result = await intro_ab_testing_node(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_intro_ab_testing_node_returns_empty_on_exception(self) -> None:
        """intro_ab_testing_node returns empty dict when run_intro_ab_test raises."""
        mock_post = GeneratedPost(
            title="Test Post",
            subtitle="Subtitle",
            content="Some content here.",
            tags=["test"],
            image_suggestions=[],
        )

        state: PipelineState = {
            "run_id": "test-sprint18-004",
            "custom_topic": "topic",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_intro_ab_test"
        ) as mock_run_test, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_run_test.side_effect = Exception("LLM error")

            result = await intro_ab_testing_node(state)

            assert result == {}

    @pytest.mark.asyncio
    async def test_intro_ab_testing_node_skips_empty_paragraphs(self) -> None:
        """intro_ab_testing_node finds first non-empty paragraph to replace."""
        best_intro = "Strong opening paragraph."

        mock_post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="\n\n\n\n\nOriginal weak intro.\n\nBody content here.",
            tags=["test"],
            image_suggestions=[],
        )

        mock_result = IntroABTestResult(
            variants=[
                IntroVariant(
                    text=best_intro,
                    hook_type="outcome",
                    specificity_score=0.9,
                    curiosity_gap=0.85,
                    voice_authenticity=0.8,
                ),
                IntroVariant(
                    text="Alternative opening approach.",
                    hook_type="data_point",
                    specificity_score=0.85,
                    curiosity_gap=0.8,
                    voice_authenticity=0.75,
                ),
            ],
            best_intro=best_intro,
            original_intro_problem="",
        )

        state: PipelineState = {
            "run_id": "test-sprint18-005",
            "custom_topic": "topic",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_intro_ab_test"
        ) as mock_run_test, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_run_test.return_value = mock_result

            result = await intro_ab_testing_node(state)

            assert result.get("post") is not None
            # Node preserves empty paragraphs, so check best_intro is in content
            assert best_intro in result["post"].content


class TestSeriesCoherenceNode:
    """Test series_coherence_node: validates installment coherence in series."""

    @pytest.mark.asyncio
    async def test_series_coherence_node_returns_score(self) -> None:
        """series_coherence_node returns coherence_score when series_context present."""
        mock_post = GeneratedPost(
            title="Part 2: Advanced Techniques",
            subtitle="Continuing the series",
            content="Part 2 explores advanced topics building on Part 1 fundamentals.",
            tags=["series", "advanced", "tutorial", "guide", "techniques"],
            image_suggestions=["diagram", "chart", "example"],
        )

        mock_result = SeriesCoherenceResult(
            coherence_score=0.88,
            issues=[],
            continuity_notes=["Well positioned as Part 2"],
            revised_content="",
        )

        state: PipelineState = {
            "run_id": "test-sprint18-006",
            "custom_topic": "series topic",
            "grounding_context": "",
            "series_id": "series-001",
            "series_position": 2,
            "series_context": "Part 1 covered fundamentals. Part 2 should go deeper.",
            "trend_context": "",
            "refined_topic": None,
            "topic_brief": {"refined_angle": "Advanced techniques"},
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_series_coherence_check"
        ) as mock_check, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_check.return_value = mock_result

            result = await series_coherence_node(state)

            assert result.get("series_coherence_score") == 0.88
            assert "series_coherence" in result.get("completed_steps", [])
            assert result.get("post") is not None

    @pytest.mark.asyncio
    async def test_series_coherence_node_skips_without_series_context(self) -> None:
        """series_coherence_node returns empty dict for standalone posts."""
        mock_post = GeneratedPost(
            title="Standalone Post",
            subtitle="Not part of a series",
            content="This is a standalone post with no series context.",
            tags=["standalone"],
            image_suggestions=[],
        )

        state: PipelineState = {
            "run_id": "test-sprint18-007",
            "custom_topic": "topic",
            "grounding_context": "",
            "series_id": None,
            "series_position": None,
            "series_context": "",  # No series context
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        result = await series_coherence_node(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_series_coherence_node_skips_without_post(self) -> None:
        """series_coherence_node returns empty dict when post is None."""
        state: PipelineState = {
            "run_id": "test-sprint18-008",
            "custom_topic": "topic",
            "grounding_context": "",
            "series_id": "series-001",
            "series_position": 1,
            "series_context": "Some series context",
            "trend_context": "",
            "refined_topic": None,
            "topic_brief": None,
            "post": None,  # No post
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        result = await series_coherence_node(state)

        assert result == {}

    @pytest.mark.asyncio
    async def test_series_coherence_node_patches_content_when_revised(self) -> None:
        """series_coherence_node updates post.content when revised_content provided."""
        original_content = "Original part 2 content that drifts from series theme."
        revised_content = "Revised part 2 content that aligns with series progression."

        mock_post = GeneratedPost(
            title="Part 2",
            subtitle="",
            content=original_content,
            tags=["series"],
            image_suggestions=[],
        )

        mock_result = SeriesCoherenceResult(
            coherence_score=0.72,
            issues=[
                SeriesCoherenceIssue(
                    category="continuity",
                    severity="MEDIUM",
                    location="Paragraph 2",
                    suggestion="Improve callback to Part 1",
                ),
            ],
            continuity_notes=["Minor drift detected"],
            revised_content=revised_content,
        )

        state: PipelineState = {
            "run_id": "test-sprint18-009",
            "custom_topic": "series topic",
            "grounding_context": "",
            "series_id": "series-001",
            "series_position": 2,
            "series_context": "Series plan here",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_series_coherence_check"
        ) as mock_check, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_check.return_value = mock_result

            result = await series_coherence_node(state)

            assert result.get("post") is not None
            assert result["post"].content == revised_content
            assert result.get("series_coherence_score") == 0.72

    @pytest.mark.asyncio
    async def test_series_coherence_node_returns_empty_on_exception(self) -> None:
        """series_coherence_node returns empty dict when checker raises exception."""
        mock_post = GeneratedPost(
            title="Part 1",
            subtitle="",
            content="Some content",
            tags=["series"],
            image_suggestions=[],
        )

        state: PipelineState = {
            "run_id": "test-sprint18-010",
            "custom_topic": "topic",
            "grounding_context": "",
            "series_id": "series-001",
            "series_position": 1,
            "series_context": "Series context here",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_series_coherence_check"
        ) as mock_check, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_check.side_effect = Exception("Checker error")

            result = await series_coherence_node(state)

            assert result == {}

    @pytest.mark.asyncio
    async def test_series_coherence_node_skips_empty_revised_content(self) -> None:
        """series_coherence_node does not patch post when revised_content is empty."""
        original_content = "Original content is fine as-is."

        mock_post = GeneratedPost(
            title="Part 3",
            subtitle="",
            content=original_content,
            tags=["series"],
            image_suggestions=[],
        )

        mock_result = SeriesCoherenceResult(
            coherence_score=0.92,
            issues=[],
            continuity_notes=["Excellent alignment"],
            revised_content="",  # Empty — no revision needed
        )

        state: PipelineState = {
            "run_id": "test-sprint18-011",
            "custom_topic": "topic",
            "grounding_context": "",
            "series_id": "series-001",
            "series_position": 3,
            "series_context": "Series plan",
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
            "intro_variants": [],
            "series_coherence_score": None,
            "image_enrichment_changes": [],
        }

        with patch(
            "app.agents.orchestrator.run_series_coherence_check"
        ) as mock_check, patch(
            "app.agents.orchestrator.log_step", new_callable=AsyncMock
        ):
            mock_check.return_value = mock_result

            result = await series_coherence_node(state)

            assert result.get("post") is not None
            assert result["post"].content == original_content
            assert result.get("series_coherence_score") == 0.92
