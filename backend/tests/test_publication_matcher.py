"""
Publication matcher agent tests.

RED phase: all tests written before implementation exists.

The publication_matcher module must:
  1. Accept post metadata (title, tags, quality_score, boost_eligible).
  2. Call the LLM with a system prompt and formatted human message.
  3. Return PublicationMatchResult with 1-5 matches, a top_pick, and a strategy.
  4. Coerce LLM JSON strings containing smart quotes / em-dashes.
  5. Raise ValueError when LLM returns None.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.publication_matcher import PublicationMatch, PublicationMatchResult, run_publication_matching


class TestPublicationMatchModel:
    """PublicationMatch and PublicationMatchResult model tests."""

    def test_publication_match_has_required_fields(self) -> None:
        match = PublicationMatch(
            name="Towards Data Science",
            slug="towardsdatascience",
            fit_score=0.92,
            submission_url="https://medium.com/towards-data-science",
            why="Your post on LLM cost optimization fits perfectly.",
            audience_size="large (>100K)",
        )
        assert match.name == "Towards Data Science"
        assert match.slug == "towardsdatascience"
        assert match.fit_score == 0.92
        assert 0.0 <= match.fit_score <= 1.0

    def test_fit_score_must_be_0_to_1(self) -> None:
        """fit_score must be in valid range."""
        with pytest.raises(ValueError):
            PublicationMatch(
                name="TDS",
                slug="tds",
                fit_score=1.5,  # out of range
                submission_url="https://example.com",
                why="Why",
                audience_size="large",
            )

    def test_publication_match_result_has_matches_and_strategy(self) -> None:
        matches = [
            PublicationMatch(
                name="Towards Data Science",
                slug="towardsdatascience",
                fit_score=0.95,
                submission_url="https://medium.com/towards-data-science",
                why="Best fit for AI/ML content.",
                audience_size="large (>100K)",
            ),
            PublicationMatch(
                name="AI Advances",
                slug="ai-advances",
                fit_score=0.87,
                submission_url="https://medium.com/ai-advances",
                why="Nominate for Boost frequently.",
                audience_size="medium (10K-100K)",
            ),
        ]
        result = PublicationMatchResult(
            matches=matches,
            top_pick="Towards Data Science",
            strategy="Submit to TDS first; if rejected, try AI Advances for Boost nomination.",
        )
        assert len(result.matches) == 2
        assert result.top_pick == "Towards Data Science"
        assert result.matches[0].fit_score > result.matches[1].fit_score

    def test_publication_match_result_requires_at_least_one_match(self) -> None:
        """matches list must have 1-5 items."""
        with pytest.raises(ValueError):
            PublicationMatchResult(
                matches=[],  # empty list
                top_pick="None",
                strategy="No strategy.",
            )

    def test_publication_match_result_allows_up_to_five_matches(self) -> None:
        """matches list must have at most 5 items."""
        matches = [
            PublicationMatch(
                name=f"Pub{i}",
                slug=f"pub{i}",
                fit_score=0.9 - (i * 0.05),
                submission_url=f"https://example.com/pub{i}",
                why=f"Reason {i}",
                audience_size="medium",
            )
            for i in range(5)
        ]
        result = PublicationMatchResult(
            matches=matches,
            top_pick="Pub0",
            strategy="Strategy.",
        )
        assert len(result.matches) == 5

    def test_publication_match_result_rejects_six_matches(self) -> None:
        """matches list must reject > 5 items."""
        matches = [
            PublicationMatch(
                name=f"Pub{i}",
                slug=f"pub{i}",
                fit_score=0.9 - (i * 0.05),
                submission_url=f"https://example.com/pub{i}",
                why=f"Reason {i}",
                audience_size="medium",
            )
            for i in range(6)
        ]
        with pytest.raises(ValueError):
            PublicationMatchResult(
                matches=matches,
                top_pick="Pub0",
                strategy="Strategy.",
            )


class TestPublicationMatchJSON:
    """Test JSON coercion (smart quotes, em-dashes)."""

    def test_matches_coerce_json_string_with_smart_quotes(self) -> None:
        """Verify that LLM-emitted smart quotes are cleaned and parsed."""
        # Simulate LLM output with curly quotes (", ")
        json_with_quotes = '''[
            {
                "name": "Towards Data Science",
                "slug": "towardsdatascience",
                "fit_score": 0.95,
                "submission_url": "https://example.com",
                "why": "This is a reason with "smart quotes"",
                "audience_size": "large"
            }
        ]'''
        # This would be the raw LLM output — if it's coerced, it should parse
        result = PublicationMatchResult.model_validate({
            "matches": json_with_quotes,  # as string
            "top_pick": "Towards Data Science",
            "strategy": "Try this publication first.",
        })
        assert len(result.matches) == 1
        assert result.matches[0].name == "Towards Data Science"

    def test_matches_coerce_em_dashes(self) -> None:
        """Verify that em-dashes (—) are cleaned."""
        json_with_em_dash = '''[
            {
                "name": "Python in Plain English—A Guide",
                "slug": "python-plain-english",
                "fit_score": 0.88,
                "submission_url": "https://example.com",
                "why": "Python tutorials—practical examples",
                "audience_size": "medium"
            }
        ]'''
        result = PublicationMatchResult.model_validate({
            "matches": json_with_em_dash,
            "top_pick": "Python in Plain English",
            "strategy": "Strategy.",
        })
        assert len(result.matches) == 1
        # The em-dash should be cleaned to hyphen in the why field
        assert "—" not in result.matches[0].why or "-" in result.matches[0].why


class TestPublicationMatcherAgent:
    """Integration tests for run_publication_matching async function."""

    @pytest.mark.asyncio
    async def test_returns_result_with_matches_and_top_pick(self) -> None:
        """Verify the agent returns a structured result."""
        mock_result = PublicationMatchResult(
            matches=[
                PublicationMatch(
                    name="Towards Data Science",
                    slug="towardsdatascience",
                    fit_score=0.95,
                    submission_url="https://medium.com/towards-data-science",
                    why="Best fit for AI/ML content.",
                    audience_size="large (>100K)",
                ),
            ],
            top_pick="Towards Data Science",
            strategy="Submit to TDS; they nominate for Boost actively.",
        )

        with patch("app.agents.publication_matcher.get_llm") as mock_get_llm, \
             patch("app.agents.publication_matcher.get_model_name") as mock_model_name, \
             patch("app.agents.publication_matcher.load_prompt") as mock_load_prompt, \
             patch("app.agents.publication_matcher.load_template") as mock_load_template:

            mock_model_name.return_value = "claude-haiku-4-5-20251001"
            mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=mock_result
            )
            mock_load_prompt.return_value = "System prompt"
            mock_load_template.return_value.format = MagicMock(return_value="Human prompt")

            result = await run_publication_matching(
                run_id="test-run",
                title="Cost Optimization for LLM Inference",
                tags=["ai", "llm", "deepseek", "cost", "infrastructure"],
                quality_score=0.88,
                medium_boost_eligible=True,
                refined_angle="How to cut inference costs by 70% using DeepSeek V3.",
            )

            assert isinstance(result, PublicationMatchResult)
            assert len(result.matches) >= 1
            assert result.top_pick in [m.name for m in result.matches]

    @pytest.mark.asyncio
    async def test_raises_on_none_llm_response(self) -> None:
        """Verify that None LLM response raises ValueError."""
        with patch("app.agents.publication_matcher.get_llm") as mock_get_llm, \
             patch("app.agents.publication_matcher.get_model_name") as mock_model_name, \
             patch("app.agents.publication_matcher.load_prompt") as mock_load_prompt, \
             patch("app.agents.publication_matcher.load_template") as mock_load_template:

            mock_model_name.return_value = "claude-haiku-4-5-20251001"
            mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=None
            )
            mock_load_prompt.return_value = "System prompt"
            mock_load_template.return_value.format = MagicMock(return_value="Human prompt")

            with pytest.raises(ValueError, match="publication_matcher: LLM returned None"):
                await run_publication_matching(
                    run_id="test-run",
                    title="Some Title",
                    tags=["python", "tutorial"],
                    quality_score=0.80,
                    medium_boost_eligible=False,
                )

    @pytest.mark.asyncio
    async def test_high_quality_score_with_boost_eligible(self) -> None:
        """Test with high quality score and boost eligibility."""
        mock_result = PublicationMatchResult(
            matches=[
                PublicationMatch(
                    name="Towards Data Science",
                    slug="towardsdatascience",
                    fit_score=0.95,
                    submission_url="https://medium.com/towards-data-science",
                    why="Top-tier ML content.",
                    audience_size="large (>100K)",
                ),
                PublicationMatch(
                    name="AI Advances",
                    slug="ai-advances",
                    fit_score=0.88,
                    submission_url="https://medium.com/ai-advances",
                    why="AI-focused, nominates for Boost.",
                    audience_size="medium (10K-100K)",
                ),
            ],
            top_pick="Towards Data Science",
            strategy="TDS is best; AI Advances is fallback for Boost nomination.",
        )

        with patch("app.agents.publication_matcher.get_llm") as mock_get_llm, \
             patch("app.agents.publication_matcher.get_model_name") as mock_model_name, \
             patch("app.agents.publication_matcher.load_prompt") as mock_load_prompt, \
             patch("app.agents.publication_matcher.load_template") as mock_load_template:

            mock_model_name.return_value = "claude-haiku-4-5-20251001"
            mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=mock_result
            )
            mock_load_prompt.return_value = "System prompt"
            mock_load_template.return_value.format = MagicMock(return_value="Human prompt")

            result = await run_publication_matching(
                run_id="test-run",
                title="Advanced ML Techniques",
                tags=["machine-learning", "ai", "tutorial"],
                quality_score=0.90,
                medium_boost_eligible=True,
            )

            assert result is not None
            assert len(result.matches) >= 1

    @pytest.mark.asyncio
    async def test_low_quality_score_still_returns_matches(self) -> None:
        """Test with low quality score — should still return matches (no blocker)."""
        mock_result = PublicationMatchResult(
            matches=[
                PublicationMatch(
                    name="Dev Genius",
                    slug="dev-genius",
                    fit_score=0.72,
                    submission_url="https://blog.devgenius.io",
                    why="Solid engineering content fits here.",
                    audience_size="medium (10K-100K)",
                ),
            ],
            top_pick="Dev Genius",
            strategy="Self-publish first to build stats, then submit to Dev Genius.",
        )

        with patch("app.agents.publication_matcher.get_llm") as mock_get_llm, \
             patch("app.agents.publication_matcher.get_model_name") as mock_model_name, \
             patch("app.agents.publication_matcher.load_prompt") as mock_load_prompt, \
             patch("app.agents.publication_matcher.load_template") as mock_load_template:

            mock_model_name.return_value = "claude-haiku-4-5-20251001"
            mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
                return_value=mock_result
            )
            mock_load_prompt.return_value = "System prompt"
            mock_load_template.return_value.format = MagicMock(return_value="Human prompt")

            result = await run_publication_matching(
                run_id="test-run",
                title="Learning DevOps",
                tags=["devops", "docker", "tutorial"],
                quality_score=0.65,
                medium_boost_eligible=False,
            )

            assert result is not None
            assert len(result.matches) >= 1
