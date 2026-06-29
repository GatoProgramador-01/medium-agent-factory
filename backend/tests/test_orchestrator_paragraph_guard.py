"""Paragraph-length guardrails in pre-quality orchestrator nodes."""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.content_generator import GeneratedPost
from app.agents.intro_ab_tester import IntroABTestResult, IntroVariant
from app.agents.series_coherence_checker import SeriesCoherenceResult
from app.agents.structural_checker import run_structural_checks


def _post(content: str) -> GeneratedPost:
    return GeneratedPost(
        title="Test Title",
        subtitle="A subtitle",
        content=content,
        tags=["ai", "writing", "python", "llm", "tools"],
        image_suggestions=["img1", "img2", "img3"],
    )


def _five_sentence_paragraph(prefix: str = "Intro") -> str:
    return (
        f"{prefix} sentence one has enough words. "
        f"{prefix} sentence two has enough words. "
        f"{prefix} sentence three has enough words. "
        f"{prefix} sentence four has enough words. "
        f"{prefix} sentence five has enough words."
    )


@pytest.mark.asyncio
async def test_intro_ab_node_splits_best_intro_before_quality() -> None:
    from app.agents.orchestrator import intro_ab_testing_node

    result = IntroABTestResult(
        variants=[
            IntroVariant(
                text="Variant one has enough words.",
                hook_type="outcome",
                specificity_score=0.8,
                curiosity_gap=0.8,
                voice_authenticity=0.8,
            ),
            IntroVariant(
                text="Variant two has enough words.",
                hook_type="scene",
                specificity_score=0.8,
                curiosity_gap=0.8,
                voice_authenticity=0.8,
            ),
        ],
        best_intro=_five_sentence_paragraph(),
        original_intro_problem="Too slow.",
    )
    state = {
        "run_id": "test-run",
        "post": _post("Original intro.\n\n## Body\n\nShort body paragraph."),
        "topic_brief": None,
    }

    with (
        patch(
            "app.agents.orchestrator.run_intro_ab_test",
            new=AsyncMock(return_value=result),
        ),
        patch("app.agents.orchestrator.log_step", new=AsyncMock()),
    ):
        output = await intro_ab_testing_node(state)

    post = output["post"]
    assert "\n\n## Body" in post.content
    assert not any(
        issue.category == "paragraph_length"
        for issue in run_structural_checks(post.content)
    )


@pytest.mark.asyncio
async def test_series_coherence_node_splits_revised_content_before_quality() -> None:
    from app.agents.orchestrator import series_coherence_node

    revised = f"## Series Fit\n\n{_five_sentence_paragraph('Series')}"
    result = SeriesCoherenceResult(
        coherence_score=0.82,
        issues=[],
        continuity_notes=["Fits the series role."],
        revised_content=revised,
    )
    state = {
        "run_id": "test-run",
        "post": _post("Original intro.\n\n## Body\n\nShort body paragraph."),
        "series_context": "SERIES: Post 2 of 3",
        "series_position": 2,
        "topic_brief": None,
    }

    with (
        patch(
            "app.agents.orchestrator.run_series_coherence_check",
            new=AsyncMock(return_value=result),
        ),
        patch("app.agents.orchestrator.log_step", new=AsyncMock()),
    ):
        output = await series_coherence_node(state)

    post = output["post"]
    assert "Series sentence five" in post.content
    assert not any(
        issue.category == "paragraph_length"
        for issue in run_structural_checks(post.content)
    )
