"""
QualityAnalyzerAgent

Reads a post draft and scores it on human-likeness and readability.
Returns a structured QualityReport with specific, actionable corrections.

Detects:
  - AI writing patterns (transition word overuse, generic openings)
  - Non-human rhythm (uniform sentence length, no voice variation)
  - Formatting issues (bullet hell, excessive headers)
  - Readability problems (passive voice, jargon without explanation)
  - Missing human elements (no anecdote, no personal take, no specificity)
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.models.post import QualityIssue, QualityReport
from app.prompt_loader import load_prompt, load_template


class _Issue(BaseModel):
    category: str
    severity: str
    location: str
    suggestion: str


class _AnalysisOutput(BaseModel):
    score: float = Field(ge=0.0, le=1.0, description="Overall earnings potential score")
    read_ratio_prediction: float = Field(
        ge=0.0,
        description="Estimated fraction of viewers who will read 30+ seconds (0-1 or 0-100)",
    )

    @field_validator("score", "read_ratio_prediction", mode="before")
    @classmethod
    def _normalize_ratio(cls, v: Any) -> Any:
        # Small models sometimes return percentages (e.g. 67.4) instead of decimals (0.674)
        try:
            f = float(v)
            return f / 100.0 if f > 1.0 else f
        except (TypeError, ValueError):
            return v
    medium_boost_eligible: bool = Field(
        description=(
            "True only if ALL six Medium Boost criteria are met: "
            "English language, original insight, non-clickbait title, "
            "at least one image with alt text, no self-promotion, no AI patterns."
        )
    )
    issues: list[_Issue] = Field(
        description="Specific problems ordered by earnings impact (platform violations first)"
    )
    strengths: list[str] = Field(description="What the post does well — preserve in revision")
    revision_prompt: str = Field(
        description=(
            "Precise rewrite instructions for the content generator. "
            "Name the exact patterns to remove and the specific fixes to apply."
        )
    )

    @field_validator("issues", "strengths", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            # LLMs sometimes embed smart-quotes or em-dashes in JSON strings,
            # breaking strict parsing. Normalize the most common offenders.
            cleaned = (
                v.replace("‘", "'")
                .replace("’", "'")  # curly single quotes
                .replace("“", '"')
                .replace("”", '"')  # curly double quotes
                .replace("—", "-")
                .replace("–", "-")  # em/en dashes
                .replace("…", "...")  # ellipsis char
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []  # last resort: empty list, don't crash the pipeline


async def run_quality_analysis(
    run_id: str,
    title: str,
    content: str,
) -> QualityReport:
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(
        agent_name="quality_analyzer",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm("worker", callbacks=[tracker]).with_structured_output(_AnalysisOutput)
    )

    messages = [
        SystemMessage(content=load_prompt("quality_analyzer_system")),
        HumanMessage(
            content=load_template("quality_analyzer_human").format(
                title=title,
                content=content,
            )
        ),
    ]

    output: _AnalysisOutput | None = await llm.ainvoke(messages)
    if output is None:
        raise ValueError("quality_analyzer: LLM returned None — structured output failed")

    issues = [
        QualityIssue(
            category=i.category,
            severity=i.severity,
            location=i.location,
            suggestion=i.suggestion,
        )
        for i in output.issues
    ]

    return QualityReport(
        score=output.score,
        read_ratio_prediction=output.read_ratio_prediction,
        medium_boost_eligible=output.medium_boost_eligible,
        issues=issues,
        strengths=output.strengths,
        revision_prompt=output.revision_prompt,
    )
