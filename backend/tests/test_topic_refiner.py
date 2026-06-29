"""Tests for the TopicRefiner agent.

RED phase: all tests written before implementation exists.

The topic_refiner module must:
  1. Take a raw topic, research results, and optional grounding context.
  2. Synthesize into a structured TopicBrief with refined_angle, hook_seed, etc.
  3. Use supervisor model for editorial judgment.
  4. Return formatted_brief suitable for injection into content generator.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.topic_refiner import TopicBrief, run_topic_refinement

# ── Test data ────────────────────────────────────────────────────────────────

SAMPLE_BRIEF = TopicBrief(
    refined_angle="DeepSeek V3 wins on cost up to 8K tokens/call; above that Claude caching closes the gap.",
    hook_seed="My API bill dropped from $2,800 to $178 the month I stopped sending long contexts to DeepSeek.",
    target_audience="Backend engineers running LLM pipelines who assume cheapest model always wins.",
    h2_structure=[
        "The Bill That Made Me Switch",
        "Where DeepSeek Breaks",
        "The Caching Loophole Nobody Talks About",
        "The Four Use Cases I Gave Back to Claude",
    ],
    key_claims=[
        "DeepSeek V3 input pricing as of 2024",
        "Claude Sonnet prompt cache hit pricing",
    ],
    concession="For document processing over 8K tokens/call, Claude caching makes it competitive or cheaper.",
    formatted_brief="ANGLE: DeepSeek wins on cost up to 8K tokens...\nHOOK: My bill dropped...",
)


# ── TopicBrief model tests ───────────────────────────────────────────────────


class TestTopicBriefModel:
    def test_topic_brief_has_required_fields(self) -> None:
        assert SAMPLE_BRIEF.refined_angle
        assert SAMPLE_BRIEF.hook_seed
        assert SAMPLE_BRIEF.target_audience
        assert len(SAMPLE_BRIEF.h2_structure) >= 4
        assert len(SAMPLE_BRIEF.key_claims) >= 2
        assert SAMPLE_BRIEF.concession
        assert SAMPLE_BRIEF.formatted_brief

    def test_topic_brief_h2_structure_min_length(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            TopicBrief(
                refined_angle="a",
                hook_seed="b",
                target_audience="c",
                h2_structure=["only", "one"],  # min_length=4
                key_claims=["c1", "c2"],
                concession="d",
                formatted_brief="e",
            )

    def test_topic_brief_h2_structure_max_length(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            TopicBrief(
                refined_angle="a",
                hook_seed="b",
                target_audience="c",
                h2_structure=["h1", "h2", "h3", "h4", "h5", "h6", "h7"],  # max_length=6
                key_claims=["c1", "c2"],
                concession="d",
                formatted_brief="e",
            )

    def test_topic_brief_key_claims_min_length(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            TopicBrief(
                refined_angle="a",
                hook_seed="b",
                target_audience="c",
                h2_structure=["h1", "h2", "h3", "h4"],
                key_claims=["only one"],  # min_length=2
                concession="d",
                formatted_brief="e",
            )

    def test_topic_brief_h2_structure_coerces_json_string(self) -> None:
        brief = TopicBrief(
            refined_angle="a",
            hook_seed="b",
            target_audience="c",
            h2_structure=json.dumps(["H1", "H2", "H3", "H4"]),
            key_claims=json.dumps(["claim1", "claim2"]),
            concession="d",
            formatted_brief="e",
        )
        assert len(brief.h2_structure) == 4
        assert brief.h2_structure[0] == "H1"

    def test_topic_brief_key_claims_coerces_json_string(self) -> None:
        brief = TopicBrief(
            refined_angle="a",
            hook_seed="b",
            target_audience="c",
            h2_structure=["h1", "h2", "h3", "h4"],
            key_claims=json.dumps(["claim1", "claim2", "claim3"]),
            concession="d",
            formatted_brief="e",
        )
        assert len(brief.key_claims) == 3
        assert brief.key_claims[0] == "claim1"

    def test_topic_brief_coerces_invalid_json_to_empty_list_fails_min_length(
        self,
    ) -> None:
        # When JSON parsing fails, the validator returns an empty list
        # But min_length=2 will catch this and raise ValidationError
        with pytest.raises(Exception):  # ValidationError
            TopicBrief(
                refined_angle="a",
                hook_seed="b",
                target_audience="c",
                h2_structure=["h1", "h2", "h3", "h4"],
                key_claims="invalid json [[[",  # coerces to [], then fails min_length
                concession="d",
                formatted_brief="e",
            )


# ── run_topic_refinement tests ───────────────────────────────────────────────


class TestRunTopicRefinement:
    @pytest.mark.asyncio
    async def test_run_topic_refinement_returns_brief(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_BRIEF)

        with (
            patch("app.agents.topic_refiner.get_llm") as mock_get_llm,
            patch(
                "app.agents.topic_refiner.get_model_name",
                return_value="claude-sonnet-4-6",
            ),
            patch("app.agents.topic_refiner.AgentTokenTracker"),
            patch(
                "app.agents.topic_refiner.with_langchain_retry", side_effect=lambda x: x
            ),
            patch("app.agents.topic_refiner.load_prompt", return_value="system prompt"),
            patch(
                "app.agents.topic_refiner.load_template",
                return_value=MagicMock(
                    format=MagicMock(return_value="formatted message")
                ),
            ),
        ):
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = mock_chain
            mock_get_llm.return_value = mock_llm

            result = await run_topic_refinement(
                run_id="test-run",
                topic="DeepSeek vs Claude costs",
                research_results="DeepSeek pricing: $0.27/MTok input...",
                grounding_context="I saved $2,622/month switching models.",
            )

        assert result is not None
        assert result.refined_angle.startswith("DeepSeek")
        assert len(result.h2_structure) >= 4
        assert len(result.key_claims) >= 2
        assert result.hook_seed != ""
        assert result.concession != ""
        assert result.formatted_brief != ""

    @pytest.mark.asyncio
    async def test_run_topic_refinement_raises_on_none(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)

        with (
            patch("app.agents.topic_refiner.get_llm") as mock_get_llm,
            patch(
                "app.agents.topic_refiner.get_model_name",
                return_value="claude-sonnet-4-6",
            ),
            patch("app.agents.topic_refiner.AgentTokenTracker"),
            patch(
                "app.agents.topic_refiner.with_langchain_retry", side_effect=lambda x: x
            ),
            patch("app.agents.topic_refiner.load_prompt", return_value="system"),
            patch(
                "app.agents.topic_refiner.load_template",
                return_value=MagicMock(format=MagicMock(return_value="msg")),
            ),
        ):
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = mock_chain
            mock_get_llm.return_value = mock_llm

            with pytest.raises(ValueError, match="topic_refiner"):
                await run_topic_refinement("run1", "topic", "research", "")

    @pytest.mark.asyncio
    async def test_run_topic_refinement_works_without_grounding(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_BRIEF)

        with (
            patch("app.agents.topic_refiner.get_llm") as mock_get_llm,
            patch(
                "app.agents.topic_refiner.get_model_name",
                return_value="claude-sonnet-4-6",
            ),
            patch("app.agents.topic_refiner.AgentTokenTracker"),
            patch(
                "app.agents.topic_refiner.with_langchain_retry", side_effect=lambda x: x
            ),
            patch("app.agents.topic_refiner.load_prompt", return_value="system"),
            patch(
                "app.agents.topic_refiner.load_template",
                return_value=MagicMock(format=MagicMock(return_value="msg")),
            ),
        ):
            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = mock_chain
            mock_get_llm.return_value = mock_llm

            result = await run_topic_refinement("run1", "topic", "research")
            assert result is not None

    @pytest.mark.asyncio
    async def test_run_topic_refinement_truncates_long_research(self) -> None:
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_BRIEF)

        with (
            patch("app.agents.topic_refiner.get_llm") as mock_get_llm,
            patch(
                "app.agents.topic_refiner.get_model_name",
                return_value="claude-sonnet-4-6",
            ),
            patch("app.agents.topic_refiner.AgentTokenTracker"),
            patch(
                "app.agents.topic_refiner.with_langchain_retry", side_effect=lambda x: x
            ),
            patch("app.agents.topic_refiner.load_prompt", return_value="system"),
            patch(
                "app.agents.topic_refiner.load_template",
            ) as mock_load_template,
        ):
            mock_template = MagicMock()
            mock_template.format = MagicMock(return_value="msg")
            mock_load_template.return_value = mock_template

            mock_llm = MagicMock()
            mock_llm.with_structured_output.return_value = mock_chain
            mock_get_llm.return_value = mock_llm

            # Research results are 10KB
            long_research = "x" * 10000

            await run_topic_refinement("run1", "topic", long_research)

            # Verify that format was called and the research was truncated
            mock_template.format.assert_called_once()
            call_kwargs = mock_template.format.call_args[1]
            assert len(call_kwargs["research_results"]) <= 4000


# ── Guard assertion ──────────────────────────────────────────────────────────


def test_topic_refiner_module_has_correct_exports() -> None:
    """Prove we loaded the correct module and not a different agent."""
    from app.agents import topic_refiner

    assert hasattr(topic_refiner, "TopicBrief")
    assert hasattr(topic_refiner, "run_topic_refinement")
    # topic_refiner should NOT have fields from other agents
    assert not hasattr(topic_refiner, "FactCheckRequest")  # from fact_checker
    assert not hasattr(topic_refiner, "ContentSection")  # from content_generator
