"""Series coherence checker agent for multi-part Medium posts.

Reviews a generated draft against the series plan and can provide a minimal
revised content body when the post drifts from its assigned role.
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


class SeriesCoherenceIssue(BaseModel):
    """A continuity or positioning issue found in a series installment."""

    category: str = Field(description="continuity, repetition, spoiler, or missing_callback")
    severity: str = Field(description="LOW, MEDIUM, or HIGH")
    location: str = Field(description="Where the issue appears")
    suggestion: str = Field(description="Specific fix")


class SeriesCoherenceResult(BaseModel):
    """Series coherence assessment and optional revised content."""

    coherence_score: float = Field(ge=0.0, le=1.0)
    issues: list[SeriesCoherenceIssue] = Field(default_factory=list, max_length=6)
    continuity_notes: list[str] = Field(default_factory=list, max_length=5)
    revised_content: str = Field(
        default="",
        description="Full revised post content only when a targeted rewrite is needed",
    )

    @field_validator("issues", "continuity_notes", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce JSON strings from LLM structured output."""
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []


async def run_series_coherence_check(
    run_id: str,
    title: str,
    content: str,
    series_context: str,
    series_position: int | None = None,
    refined_angle: str = "",
) -> SeriesCoherenceResult:
    """Check whether a draft fits its assigned position in a series.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        title: Current post title.
        content: Full draft content.
        series_context: Series plan/context injected by run_series.
        series_position: One-based position in the series, if known.
        refined_angle: TopicRefiner central argument, when available.

    Returns:
        SeriesCoherenceResult with score, issues, notes, and optional rewrite.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="series_coherence_checker",
        run_id=run_id,
        model=model_name,
    )

    excerpt = " ".join(content.split()[:900])
    messages = [
        SystemMessage(content=load_prompt("series_coherence_checker_system")),
        HumanMessage(
            content=load_template("series_coherence_checker_human").format(
                title=title,
                series_position=series_position or "unknown",
                refined_angle=refined_angle or "Not specified.",
                series_context=series_context,
                post_excerpt=excerpt,
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> SeriesCoherenceResult | None:
        chain = get_llm("worker", callbacks=[tracker]).with_structured_output(
            SeriesCoherenceResult
        )
        if inspect.isawaitable(chain):
            chain = await chain  # type: ignore[assignment]
        return await chain.ainvoke(messages)  # type: ignore[return-value]

    output = await _invoke()
    if output is None:
        raise ValueError(
            "series_coherence_checker: LLM returned None - structured output failed"
        )
    return output
