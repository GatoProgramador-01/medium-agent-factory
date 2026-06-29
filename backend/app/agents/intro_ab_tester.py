"""Intro A/B tester agent for strengthening the opening of a Medium post.

Generates alternate opening paragraphs, selects the strongest one, and leaves
the caller to replace only the first paragraph. This keeps the pass focused on
hook quality without rewriting the body.
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


class IntroVariant(BaseModel):
    """A candidate opening paragraph with hook quality scores."""

    text: str = Field(description="Opening paragraph, 2-5 sentences, no heading")
    hook_type: str = Field(description="outcome, contradiction, scene, or data_point")
    specificity_score: float = Field(ge=0.0, le=1.0)
    curiosity_gap: float = Field(ge=0.0, le=1.0)
    voice_authenticity: float = Field(ge=0.0, le=1.0)


class IntroABTestResult(BaseModel):
    """Intro variants and the selected best opening paragraph."""

    variants: list[IntroVariant] = Field(
        min_length=2,
        max_length=4,
        description="2-4 distinct opening paragraph variants",
    )
    best_intro: str = Field(description="The selected opening paragraph")
    original_intro_problem: str = Field(
        description="One sentence explaining why the original intro was weak; empty if kept"
    )

    @field_validator("variants", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce JSON-string variants from structured-output edge cases."""
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


async def run_intro_ab_test(
    run_id: str,
    title: str,
    content: str,
    refined_angle: str = "",
) -> IntroABTestResult:
    """Generate alternate intros and select the strongest opening.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        title: Current post title.
        content: Full draft content.
        refined_angle: TopicRefiner central argument, when available.

    Returns:
        IntroABTestResult containing variants and best_intro.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="intro_ab_tester",
        run_id=run_id,
        model=model_name,
    )

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    original_intro = paragraphs[0] if paragraphs else content[:800]
    post_excerpt = " ".join(content.split()[:450])

    messages = [
        SystemMessage(content=load_prompt("intro_ab_tester_system")),
        HumanMessage(
            content=load_template("intro_ab_tester_human").format(
                title=title,
                refined_angle=refined_angle or "Not specified.",
                original_intro=original_intro,
                post_excerpt=post_excerpt,
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> IntroABTestResult | None:
        chain = get_llm("worker", callbacks=[tracker]).with_structured_output(
            IntroABTestResult
        )
        if inspect.isawaitable(chain):
            chain = await chain  # type: ignore[assignment]
        return await chain.ainvoke(messages)  # type: ignore[return-value]

    output = await _invoke()
    if output is None:
        raise ValueError("intro_ab_tester: LLM returned None - structured output failed")
    return output
