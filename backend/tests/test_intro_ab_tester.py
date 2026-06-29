"""
Unit tests for IntroABTester — generates intro variants and selects the strongest hook.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.intro_ab_tester import (
    IntroABTestResult,
    IntroVariant,
    run_intro_ab_test,
)


class TestIntroVariant:
    """Test IntroVariant Pydantic model validation."""

    def test_creates_variant_with_valid_scores(self) -> None:
        v = IntroVariant(
            text="My inference costs dropped 94% the week I stopped sending full documents to the LLM.",
            hook_type="outcome",
            specificity_score=0.9,
            curiosity_gap=0.85,
            voice_authenticity=0.8,
        )
        assert v.text
        assert v.hook_type == "outcome"
        assert 0.0 <= v.specificity_score <= 1.0

    def test_score_boundaries_are_inclusive(self) -> None:
        v = IntroVariant(
            text="Something happened that changed everything.",
            hook_type="scene",
            specificity_score=0.0,
            curiosity_gap=1.0,
            voice_authenticity=0.5,
        )
        assert v.specificity_score == 0.0
        assert v.curiosity_gap == 1.0

    def test_all_hook_types_accepted(self) -> None:
        for hook_type in ("outcome", "contradiction", "scene", "data_point"):
            v = IntroVariant(
                text=f"Test intro for {hook_type}.",
                hook_type=hook_type,
                specificity_score=0.5,
                curiosity_gap=0.5,
                voice_authenticity=0.5,
            )
            assert v.hook_type == hook_type


class TestIntroABTestResult:
    """Test IntroABTestResult Pydantic model and validators."""

    def _make_variants(self, n: int = 2) -> list[IntroVariant]:
        return [
            IntroVariant(
                text=f"Variant {i}: costs dropped when I changed the approach.",
                hook_type="outcome",
                specificity_score=0.5 + i * 0.1,
                curiosity_gap=0.5,
                voice_authenticity=0.7,
            )
            for i in range(n)
        ]

    def test_creates_result_with_two_variants(self) -> None:
        result = IntroABTestResult(
            variants=self._make_variants(2),
            best_intro="Variant 1: costs dropped when I changed the approach.",
            original_intro_problem="Original was too vague.",
        )
        assert len(result.variants) == 2
        assert result.best_intro
        assert result.original_intro_problem

    def test_accepts_up_to_four_variants(self) -> None:
        result = IntroABTestResult(
            variants=self._make_variants(4),
            best_intro="Variant 3: costs dropped when I changed the approach.",
            original_intro_problem="",
        )
        assert len(result.variants) == 4

    def test_variants_coerces_json_string(self) -> None:
        variants_json = json.dumps(
            [
                {
                    "text": "Costs fell 80% the week I switched.",
                    "hook_type": "data_point",
                    "specificity_score": 0.8,
                    "curiosity_gap": 0.7,
                    "voice_authenticity": 0.9,
                },
                {
                    "text": "The chart showed a cliff-edge drop on day 7.",
                    "hook_type": "scene",
                    "specificity_score": 0.7,
                    "curiosity_gap": 0.8,
                    "voice_authenticity": 0.75,
                },
            ]
        )
        result = IntroABTestResult(
            variants=variants_json,  # type: ignore[arg-type]
            best_intro="Costs fell 80% the week I switched.",
            original_intro_problem="",
        )
        assert len(result.variants) == 2

    def test_variants_coerces_invalid_json_raises_validation_error(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            IntroABTestResult(
                variants="not valid json",  # type: ignore[arg-type]
                best_intro="fallback intro",
                original_intro_problem="",
            )


@pytest.mark.asyncio
async def test_run_intro_ab_test_returns_result() -> None:
    """run_intro_ab_test returns IntroABTestResult when LLM succeeds."""
    mock_response = IntroABTestResult(
        variants=[
            IntroVariant(
                text="My AWS bill dropped 78% the month I stopped sending raw HTML to GPT-4.",
                hook_type="outcome",
                specificity_score=0.92,
                curiosity_gap=0.88,
                voice_authenticity=0.85,
            ),
            IntroVariant(
                text="The chart showed a 78% cost reduction but I almost missed it.",
                hook_type="scene",
                specificity_score=0.65,
                curiosity_gap=0.70,
                voice_authenticity=0.75,
            ),
        ],
        best_intro="My AWS bill dropped 78% the month I stopped sending raw HTML to GPT-4.",
        original_intro_problem="Original lacked a specific outcome before word 15.",
    )

    with patch("app.agents.intro_ab_tester.get_llm") as mock_get_llm, patch(
        "app.agents.intro_ab_tester.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_intro_ab_test(
            run_id="test-run-001",
            title="How I Cut My LLM Bill by 78%",
            content="The original intro.\n\nBody paragraph one.\n\nBody paragraph two.",
        )

    assert isinstance(result, IntroABTestResult)
    assert result.best_intro == mock_response.best_intro
    assert len(result.variants) == 2


@pytest.mark.asyncio
async def test_run_intro_ab_test_raises_on_none() -> None:
    """run_intro_ab_test raises ValueError when LLM returns None."""
    with patch("app.agents.intro_ab_tester.get_llm") as mock_get_llm, patch(
        "app.agents.intro_ab_tester.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="intro_ab_tester"):
            await run_intro_ab_test(
                run_id="test-run-002",
                title="Any Title",
                content="Some content here.",
            )


@pytest.mark.asyncio
async def test_run_intro_ab_test_passes_refined_angle() -> None:
    """run_intro_ab_test forwards refined_angle to the LLM prompt."""
    mock_response = IntroABTestResult(
        variants=[
            IntroVariant(
                text="Costs dropped.",
                hook_type="outcome",
                specificity_score=0.8,
                curiosity_gap=0.8,
                voice_authenticity=0.8,
            ),
            IntroVariant(
                text="Alternative hook.",
                hook_type="data_point",
                specificity_score=0.7,
                curiosity_gap=0.7,
                voice_authenticity=0.7,
            ),
        ],
        best_intro="Costs dropped.",
        original_intro_problem="",
    )

    with patch("app.agents.intro_ab_tester.get_llm") as mock_get_llm, patch(
        "app.agents.intro_ab_tester.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_intro_ab_test(
            run_id="test-run-003",
            title="Cost Optimization",
            content="Intro paragraph.\n\nBody.",
            refined_angle="DeepSeek wins on cost for short calls.",
        )

    assert isinstance(result, IntroABTestResult)
    call_args = mock_chain.ainvoke.call_args
    human_message = call_args[0][0][1]
    assert "DeepSeek wins on cost for short calls." in human_message.content
