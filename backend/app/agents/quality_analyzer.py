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
import time
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
    score: float = Field(ge=0.0, le=1.0, description="Overall human-likeness score")
    read_ratio_prediction: float = Field(
        ge=0.0, le=1.0,
        description="Estimated fraction of viewers who will finish reading",
    )
    issues: list[_Issue] = Field(description="Specific problems found, ordered by impact")
    strengths: list[str] = Field(description="What the post does well")
    revision_prompt: str = Field(
        description=(
            "A precise rewrite instruction for the content generator. "
            "Include the specific patterns to remove and the specific voice/style to add."
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
                v
                .replace("‘", "'").replace("’", "'")   # curly single quotes
                .replace("“", '"').replace("”", '"')   # curly double quotes
                .replace("—", "-").replace("–", "-")   # em/en dashes
                .replace("…", "...")                         # ellipsis char
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []   # last resort: empty list, don't crash the pipeline



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
        HumanMessage(content=load_template("quality_analyzer_human").format(
            title=title, content=content,
        )),
    ]

    start = time.perf_counter()
    output: _AnalysisOutput = await llm.ainvoke(messages)
    duration_ms = int((time.perf_counter() - start) * 1000)

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
        issues=issues,
        strengths=output.strengths,
        revision_prompt=output.revision_prompt,
    )
