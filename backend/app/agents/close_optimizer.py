"""Close optimizer agent. Replaces the post's closing section with a more specific
question or prediction tied to the post's central argument.

Runs after quality gates pass, before format_node. The generic close ("What do you
think?" / "Drop a comment") is one of the most common patterns that signals AI content
to Medium curators and kills comment engagement.
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


class CloseVariant(BaseModel):
    """A single closing section variant."""

    text: str = Field(description="The complete closing paragraph — 2-4 sentences max")
    close_type: str = Field(description="'question' or 'prediction'")
    specificity_score: float = Field(
        ge=0.0, le=1.0, description="How tied to this post's specific argument (not generic)"
    )


class CloseOptimizationResult(BaseModel):
    """Three closing variants and the selected best close."""

    variants: list[CloseVariant] = Field(
        description="2-4 closing variants",
    )
    best_close: str = Field(description="The highest-specificity close — copied exactly from variants")
    original_close_problem: str = Field(
        description="Why the original close was weak — one sentence. Empty if original was kept."
    )

    @field_validator("variants", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        """Coerce JSON string to list, handling curly quotes and em-dashes."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Clean unicode variants that LLMs emit
                cleaned = (
                    v.replace("'", "'")
                    .replace("'", "'")
                    .replace(""", '"')
                    .replace(""", '"')
                    .replace("—", "-")
                    .replace("–", "-")
                    .replace("…", "...")
                )
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return []
        return v


async def run_close_optimization(
    run_id: str,
    content: str,
    refined_angle: str = "",
) -> CloseOptimizationResult:
    """Generates stronger closing section variants for an approved post.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        content: Full approved post content.
        refined_angle: The post's central argument from TopicBrief. Used to
            anchor the closing question/prediction to the specific claim.

    Returns:
        CloseOptimizationResult with variants and the best_close text.

    Raises:
        ValueError: If the LLM returns None.
    """
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="close_optimizer",
        run_id=run_id,
        model=model_name,
    )

    # Send last 400 words for context (the close) + first sentence for argument
    words = content.split()
    closing_section = " ".join(words[-400:]) if len(words) > 400 else content
    hook_sentence = " ".join(words[:25])

    messages = [
        SystemMessage(content=load_prompt("close_optimizer_system")),
        HumanMessage(
            content=load_template("close_optimizer_human").format(
                refined_angle=refined_angle or "Not specified.",
                hook_sentence=hook_sentence,
                closing_section=closing_section,
            )
        ),
    ]

    @retryable_llm_call(max_attempts=3)
    async def _invoke() -> CloseOptimizationResult | None:
        chain = get_llm("worker", callbacks=[tracker]).with_structured_output(
            CloseOptimizationResult
        )
        # with_structured_output is sync in LangChain; AsyncMock in tests returns a coroutine
        if inspect.isawaitable(chain):
            chain = await chain
        return await chain.ainvoke(messages)  # type: ignore[return-value]

    output: CloseOptimizationResult | None = await _invoke()
    if output is None:
        raise ValueError("close_optimizer: LLM returned None — structured output failed")

    return output
