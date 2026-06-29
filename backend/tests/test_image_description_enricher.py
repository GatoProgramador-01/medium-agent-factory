"""
Unit tests for ImageDescriptionEnricher — enriches [IMAGE:] placeholders in post content.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.image_description_enricher import (
    EnrichedImageDescription,
    ImageEnrichmentResult,
    run_image_description_enrichment,
)


class TestEnrichedImageDescription:
    """Test EnrichedImageDescription Pydantic model validation."""

    def test_creates_description_with_all_fields(self) -> None:
        img = EnrichedImageDescription(
            original_placeholder="[IMAGE: cost graph]",
            description="Line chart showing AWS Lambda cost decrease from $2,800 to $178 over 30 days",
            alt_text="AWS cost chart showing 94% reduction after switching LLM routing strategy",
            caption="Monthly AWS bill: before and after routing optimization.",
            placement_reason="Immediately after the cost-drop claim in paragraph 3.",
        )
        assert img.original_placeholder == "[IMAGE: cost graph]"
        assert img.alt_text
        assert img.description

    def test_empty_caption_is_valid(self) -> None:
        img = EnrichedImageDescription(
            original_placeholder="[IMAGE: diagram]",
            description="Architecture diagram of the multi-agent pipeline",
            alt_text="Diagram showing five agent nodes connected by arrows",
            caption="",
            placement_reason="After the architecture section.",
        )
        assert img.caption == ""


class TestImageEnrichmentResult:
    """Test ImageEnrichmentResult Pydantic model and validators."""

    def _make_image(self, i: int = 0) -> EnrichedImageDescription:
        return EnrichedImageDescription(
            original_placeholder=f"[IMAGE: placeholder {i}]",
            description=f"Specific description for image {i}",
            alt_text=f"Alt text for image {i} showing the relevant concept clearly",
            caption="",
            placement_reason=f"After section {i}.",
        )

    def test_creates_result_with_images(self) -> None:
        result = ImageEnrichmentResult(
            images=[self._make_image(0), self._make_image(1)],
            image_suggestions=["cost comparison chart", "pipeline architecture diagram"],
        )
        assert len(result.images) == 2
        assert len(result.image_suggestions) == 2

    def test_empty_images_is_valid(self) -> None:
        result = ImageEnrichmentResult(images=[], image_suggestions=[])
        assert result.images == []
        assert result.image_suggestions == []

    def test_images_coerces_json_string(self) -> None:
        images_json = json.dumps(
            [
                {
                    "original_placeholder": "[IMAGE: graph]",
                    "description": "Cost graph",
                    "alt_text": "Line chart showing cost reduction over time with clear labels",
                    "caption": "",
                    "placement_reason": "After cost claim.",
                }
            ]
        )
        result = ImageEnrichmentResult(
            images=images_json,  # type: ignore[arg-type]
            image_suggestions=[],
        )
        assert len(result.images) == 1

    def test_image_suggestions_coerces_invalid_json_to_empty(self) -> None:
        result = ImageEnrichmentResult(
            images=[],
            image_suggestions="not json",  # type: ignore[arg-type]
        )
        assert result.image_suggestions == []

    def test_accepts_up_to_five_images(self) -> None:
        result = ImageEnrichmentResult(
            images=[self._make_image(i) for i in range(5)],
            image_suggestions=["a", "b", "c", "d", "e"],
        )
        assert len(result.images) == 5


@pytest.mark.asyncio
async def test_run_image_description_enrichment_returns_result() -> None:
    """run_image_description_enrichment returns ImageEnrichmentResult when LLM succeeds."""
    mock_response = ImageEnrichmentResult(
        images=[
            EnrichedImageDescription(
                original_placeholder="[IMAGE: cost graph]",
                description="Line chart: AWS bill dropping from $2,800 to $178 over 30 days",
                alt_text="AWS cost line chart showing 94% reduction over 30 days after LLM routing change",
                caption="",
                placement_reason="Immediately after the cost figure in paragraph 2.",
            )
        ],
        image_suggestions=["LLM cost comparison chart 2025", "AWS Lambda cost breakdown pie chart"],
    )

    with patch("app.agents.image_description_enricher.get_llm") as mock_get_llm, patch(
        "app.agents.image_description_enricher.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        content = "Intro paragraph.\n\n[IMAGE: cost graph]\n\nThe cost dropped dramatically."
        result = await run_image_description_enrichment(
            run_id="test-run-001",
            title="How I Cut My LLM Bill",
            content=content,
            image_suggestions=["cost chart", "pipeline diagram"],
        )

    assert isinstance(result, ImageEnrichmentResult)
    assert len(result.images) == 1
    assert result.images[0].description == mock_response.images[0].description


@pytest.mark.asyncio
async def test_run_image_description_enrichment_raises_on_none() -> None:
    """run_image_description_enrichment raises ValueError when LLM returns None."""
    with patch("app.agents.image_description_enricher.get_llm") as mock_get_llm, patch(
        "app.agents.image_description_enricher.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="image_description_enricher"):
            await run_image_description_enrichment(
                run_id="test-run-002",
                title="Test Title",
                content="Content with [IMAGE: placeholder].",
                image_suggestions=[],
            )


@pytest.mark.asyncio
async def test_run_image_description_enrichment_with_no_placeholders() -> None:
    """run_image_description_enrichment works when content has no IMAGE placeholders."""
    mock_response = ImageEnrichmentResult(
        images=[],
        image_suggestions=["cost comparison 2025", "architecture diagram"],
    )

    with patch("app.agents.image_description_enricher.get_llm") as mock_get_llm, patch(
        "app.agents.image_description_enricher.get_model_name"
    ) as mock_model_name:
        mock_model_name.return_value = "claude-haiku-4-5-20251001"
        mock_chain = AsyncMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm = MagicMock()
        mock_llm.with_structured_output = MagicMock(return_value=mock_chain)
        mock_get_llm.return_value = mock_llm

        result = await run_image_description_enrichment(
            run_id="test-run-003",
            title="No Images Post",
            content="Just text with no image placeholders.",
            image_suggestions=["generic suggestion"],
        )

    assert isinstance(result, ImageEnrichmentResult)
    assert result.images == []
