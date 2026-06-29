"""Image description enricher agent for Medium post image placeholders.

Improves image prompts, alt text, and captions after the content has passed
quality gates. The agent is intentionally non-blocking because imagery should
raise polish without preventing publication.
"""

import inspect
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import retryable_llm_call
from app.prompt_loader import load_prompt, load_template


class EnrichedImageDescription(BaseModel):
    """A replacement image placeholder with publication-ready metadata."""

    original_placeholder: str = Field(description="Exact placeholder text found in the post")
    description: str = Field(description="Specific image search or generation description")
    alt_text: str = Field(description="Accessible alt text, 10-18 words")
    caption: str = Field(description="Optional short caption; empty when not needed")
    placement_reason: str = Field(description="Why this visual belongs at this point")


class ImageEnrichmentResult(BaseModel):
    """Image placeholder replacements and updated image suggestions."""

    images: list[EnrichedImageDescription] = Field(
        default_factory=list,
        max_length=5,
        description="Enriched image placeholders in reading order",
    )
    image_suggestions: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="Improved image search ideas for the post metadata",
    )

    @field_validator("images", "image_suggestions", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce JSON strings emitted by structured-output models."""
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            cleaned = (
                v.replace("‘", "'").replace("’", "'")
                 .replace("“", '"').replace("”", '"')
                 .replace("—", "-").replace("–", "-")
                 .replace("…", "...")
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []


async def run_image_description_enrichment(
    run_id: str,
    title: str,
    content: str,
    image_suggestions: list[str],
    refined_angle: str = "",
) -> ImageEnrichmentResult:
    """Enrich image placeholders and image search suggestions.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        title: Current post title.
        content: Approved post content.
        image_suggestions: Existing image suggestions from the generator.
        refined_angle: TopicRefiner central argument, when available.

    Returns:
        ImageEnrichmentResult with replacements and metadata suggestions.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="image_description_enricher",
        run_id=run_id,
        model=model_name,
    )

    placeholders = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("[IMAGE:") and line.strip().endswith("]")
    ]
    excerpt = " ".join(content.split()[:700])

    messages = [
        SystemMessage(content=load_prompt("image_description_enricher_system")),
        HumanMessage(
            content=load_template("image_description_enricher_human").format(
                title=title,
                refined_angle=refined_angle or "Not specified.",
                placeholders="\n".join(placeholders) or "(no placeholders found)",
                image_suggestions="\n".join(image_suggestions) or "(none)",
                post_excerpt=excerpt,
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> ImageEnrichmentResult | None:
        chain = get_llm("worker", callbacks=[tracker]).with_structured_output(
            ImageEnrichmentResult
        )
        if inspect.isawaitable(chain):
            chain = await chain  # type: ignore[assignment]
        return await chain.ainvoke(messages)  # type: ignore[return-value]

    output = await _invoke()
    if output is None:
        raise ValueError(
            "image_description_enricher: LLM returned None - structured output failed"
        )
    return output
