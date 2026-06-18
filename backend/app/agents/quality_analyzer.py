"""
QualityAnalyzerAgent — G-Eval style 4-axis content quality scoring.

Scores ONLY content quality on 4 axes (0.0–1.0 each):
  hook_strength, specificity, voice_authenticity, insight_value

content_score = mean(4 axes) — no magic penalty weights.

Structural issues (paragraph_length, heading_cadence, intro_length, word_count,
image_missing) are detected deterministically by structural_checker.py and merged
in the orchestrator before the revision step.
"""

import json
from statistics import mean
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.read_ratio_analyzer import analyze_read_ratio
from app.agents.retry import with_langchain_retry
from app.models.post import QualityIssue, QualityReport, ReadRatioFactor
from app.prompt_loader import load_prompt, load_template


class _Issue(BaseModel):
    category: str
    severity: str
    location: str
    suggestion: str


def _compute_content_score(
    hook_strength: float,
    specificity: float,
    voice_authenticity: float,
    insight_value: float,
) -> float:
    return round(mean([hook_strength, specificity, voice_authenticity, insight_value]), 2)


class _AnalysisOutput(BaseModel):
    hook_strength: float = Field(
        ge=0.0,
        le=1.0,
        description="Hook quality: 1.0 = specific outcome in sentence 1, 0.0 = no hook",
    )
    specificity: float = Field(
        ge=0.0,
        le=1.0,
        description="Named data points: 1.0 = 3+ concrete anchors, 0.0 = fully abstract",
    )
    voice_authenticity: float = Field(
        ge=0.0,
        le=1.0,
        description="Human voice: 1.0 = contractions + anecdote + varied rhythm, 0.0 = AI slop",
    )
    insight_value: float = Field(
        ge=0.0,
        le=1.0,
        description="Original insight: 1.0 = non-obvious claim + concession + prediction, 0.0 = zero insight",
    )
    medium_boost_eligible: bool = Field(
        description=(
            "True only if ALL Medium Boost criteria are met: "
            "English, original insight, non-clickbait title, "
            "image with alt text, no self-promotion, no AI patterns, 3+ concrete anchors."
        )
    )
    issues: list[_Issue] = Field(
        description="Content issues ordered by earnings impact (AI patterns first)"
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

    rr = await analyze_read_ratio(run_id=run_id, content=content)

    issues = [
        QualityIssue(
            category=i.category,
            severity=i.severity,
            location=i.location,
            suggestion=i.suggestion,
        )
        for i in output.issues
    ]

    score = _compute_content_score(
        output.hook_strength,
        output.specificity,
        output.voice_authenticity,
        output.insight_value,
    )

    rr_factors: list[ReadRatioFactor] = [
        ReadRatioFactor(
            name=f.name,
            measured=f.measured,
            deduction=f.deduction,
            guidance=f.guidance,
        )
        for f in rr.factors
    ]

    return QualityReport(
        score=score,
        read_ratio_prediction=rr.predicted_ratio,
        medium_boost_eligible=output.medium_boost_eligible,
        issues=issues,
        strengths=output.strengths,
        revision_prompt=output.revision_prompt,
        word_count=len(content.split()),
        read_ratio_factors=rr_factors,
        read_ratio_hook_score=rr.hook_score,
        hook_strength=output.hook_strength,
        specificity_score=output.specificity,
        voice_authenticity=output.voice_authenticity,
        insight_value=output.insight_value,
    )
