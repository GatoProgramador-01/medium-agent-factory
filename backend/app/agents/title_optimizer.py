"""Title optimizer agent. Generates 3–5 headline variants for an approved post
and selects the strongest one based on specificity, curiosity gap, and SEO signal.

Runs after content_generation, before fact_check. The initial LLM-generated title
is often too generic ("Understanding X") or too long. This agent produces variants
anchored to the post's specific argument and hook sentence.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import retryable_llm_call
from app.prompt_loader import load_prompt, load_template


class TitleVariant(BaseModel):
    """A single title variant with quality scores."""

    text: str = Field(description="The title text — 6 to 12 words")
    formula: str = Field(
        description="Which pattern was used: OUTCOME, COUNTER-INTUITIVE, THRESHOLD, or SPECIFIC_FAILURE"
    )
    specificity_score: float = Field(
        ge=0.0,
        le=1.0,
        description="How specific the title is: named tech, number, or measurable outcome",
    )
    curiosity_gap: float = Field(
        ge=0.0,
        le=1.0,
        description="How strongly the title creates a question the reader needs the post to answer",
    )
    seo_friendliness: float = Field(
        ge=0.0,
        le=1.0,
        description="How well it targets terms a developer would search for",
    )


class TitleOptimizationResult(BaseModel):
    """3–5 title variants and the selected best title."""

    variants: list[TitleVariant] = Field(
        description="3 to 5 title variants with scores",
    )
    best_title: str = Field(
        description="The single strongest title — copied exactly from variants"
    )
    original_title_weakness: str = Field(
        description="One sentence explaining what the original title was doing wrong. Empty if original was already strong."
    )

    @field_validator("variants", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce JSON string to list, handling curly quotes and em-dashes."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                cleaned = (
                    v.replace("‘", "'")
                    .replace("’", "'")
                    .replace("“", '"')
                    .replace("”", '"')
                    .replace("—", "-")
                    .replace("–", "-")
                    .replace("…", "...")
                )
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return []
        return v


async def run_title_optimization(
    run_id: str,
    title: str,
    content: str,
    refined_angle: str = "",
) -> TitleOptimizationResult:
    """Generates stronger title variants for an approved post.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        title: The current post title (may be LLM-generated and generic).
        content: Full post content — used to extract hook sentence and excerpt.
        refined_angle: The post central argument from TopicBrief. Used to
            anchor title variants to the specific claim.

    Returns:
        TitleOptimizationResult with variants and the best_title text.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="title_optimizer",
        run_id=run_id,
        model=model_name,
    )

    words = content.split()
    hook_sentence = " ".join(words[:25])
    post_excerpt = " ".join(words[:300]) if len(words) > 300 else content

    messages = [
        SystemMessage(content=load_prompt("title_optimizer_system")),
        HumanMessage(
            content=load_template("title_optimizer_human").format(
                original_title=title,
                refined_angle=refined_angle or "Not specified.",
                hook_sentence=hook_sentence,
                post_excerpt=post_excerpt,
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> TitleOptimizationResult | None:
        chain = get_llm("worker", callbacks=[tracker]).with_structured_output(
            TitleOptimizationResult
        )
        return await chain.ainvoke(messages)  # type: ignore[return-value]

    output: TitleOptimizationResult | None = await _invoke()
    if output is None:
        raise ValueError(
            "title_optimizer: LLM returned None — structured output failed"
        )

    return output
