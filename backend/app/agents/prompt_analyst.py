"""Prompt analyst agent. Translates quality_snapshots frequency data into targeted prompt edits.

Consumes output from analyze_quality_snapshots.py and the current prompt file contents.
Returns prioritized suggestions for which prompt sections to edit and how.
Part of the standard improvement loop: analyze → suggest → TDD edit → validate.
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.prompt_loader import load_prompt, load_template


class PromptSuggestion(BaseModel):
    """A single targeted prompt improvement suggestion backed by snapshot data."""

    file: str = Field(description="Prompt filename, e.g. content_generator_system.txt")
    section: str = Field(description="Section header in the file where the change belongs")
    issue: str = Field(description="Data pattern that motivated this suggestion, with counts")
    current_behavior: str = Field(description="What the current prompt produces (observed)")
    suggested_change: str = Field(
        description="Exact text to add or replace — max 60 words. Quote the current text if replacing."
    )
    priority: int = Field(ge=1, le=3, description="1=blocks posts, 2=degrades quality, 3=optimization")


# Alias used by the HTTP endpoint layer and its tests
ImprovementSuggestion = PromptSuggestion


class PromptAnalysisReport(BaseModel):
    """Complete analysis report with prioritized prompt improvement suggestions."""

    run_count: int = Field(description="Number of runs analyzed")
    top_issue: str = Field(description="Single most frequent issue category across all runs")
    regression_rate: float = Field(
        ge=0.0, le=1.0, description="Fraction of revision transitions where score dropped"
    )
    suggestions: list[PromptSuggestion] = Field(
        description="Improvement suggestions ordered by priority (1 first), max 8"
    )
    summary: str = Field(description="2-sentence executive summary: top finding + highest-priority action")

    @field_validator("suggestions", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
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


async def run_prompt_analysis(
    run_id: str,
    analysis_data: dict[str, Any],
    prompt_files: dict[str, str],
) -> PromptAnalysisReport:
    """Analyzes quality snapshot data and returns targeted prompt improvement suggestions.

    Args:
        run_id: Pipeline run identifier for cost tracking.
        analysis_data: JSON output from analyze_quality_snapshots.py — contains issue
            frequencies, regression rate, word count distribution, gate failure types.
        prompt_files: Mapping of filename to content for all prompt .txt files
            (content_generator_system.txt, content_reviser_system.txt, etc.).

    Returns:
        PromptAnalysisReport with prioritized suggestions, top issue, and executive summary.

    Raises:
        ValueError: If the LLM returns None (structured output failure).
    """
    model_name = get_model_name("supervisor")
    tracker = AgentTokenTracker(
        agent_name="prompt_analyst",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm("supervisor", callbacks=[tracker]).with_structured_output(PromptAnalysisReport)
    )

    # Cap each file at 3,000 chars to avoid context overflow
    prompt_context = "\n\n".join(
        f"=== {fname} ===\n{content[:3000]}"
        for fname, content in prompt_files.items()
    )

    messages = [
        SystemMessage(content=load_prompt("prompt_analyst_system")),
        HumanMessage(
            content=load_template("prompt_analyst_human").format(
                analysis_json=json.dumps(analysis_data, indent=2),
                prompt_files=prompt_context,
            )
        ),
    ]

    output: PromptAnalysisReport | None = await llm.ainvoke(messages)
    if output is None:
        raise ValueError("prompt_analyst: LLM returned None — structured output failed")

    return output
