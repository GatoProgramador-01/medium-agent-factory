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

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.config import settings
from app.models.post import QualityIssue, QualityReport


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


_SYSTEM = """You are a senior human writing coach who helps AI-assisted content pass as
expert human writing. You have deep expertise in what makes Medium readers stay and finish
an article versus bounce.

Score rubric (0.0 – 1.0):
  0.9–1.0 → Indistinguishable from a seasoned human writer. Publishes as-is.
  0.75–0.89 → Mostly human. Minor polish needed.
  0.5–0.74 → Obvious AI patterns. Significant revision needed.
  0.0–0.49 → Clearly AI-generated. Rewrite required.

Red flags (mark as issues):
  AI PATTERNS:
  - Opens with "In today's world" / "In this article" / "As a [title]"
  - Overuses: Moreover, Furthermore, Additionally, In conclusion, It's worth noting
  - Perfect parallel structure in every paragraph
  - Transition sentences that summarize the previous section before starting the next
  - Lists where prose would be more natural
  - Every H2 ends with a colon

  READABILITY:
  - Sentence length never varies (all medium, or all long)
  - No contractions (sounds formal and robotic)
  - Passive voice in action-oriented sections
  - Abstract explanations with zero concrete examples

  MISSING HUMAN ELEMENTS:
  - No personal anecdote or specific story
  - No surprising fact or counterintuitive point
  - No conversational aside (a em-dash aside, a parenthetical)
  - No humor or personality
  - Reads like a Wikipedia article, not a conversation

  FORMATTING:
  - More than 4 bullet lists in a 1500-word post
  - Headers every 200 words (chopped up flow)
  - Bold text on every third sentence"""


_HUMAN = """Analyze this Medium draft:

TITLE: {title}

CONTENT:
{content}

---
Provide a detailed quality analysis with a score, specific issues, and a revision prompt
that the content generator can use to fix this post."""


async def run_quality_analysis(
    run_id: str,
    title: str,
    content: str,
) -> QualityReport:
    tracker = AgentTokenTracker(
        agent_name="quality_analyzer",
        run_id=run_id,
        model=settings.worker_model,
    )

    llm = ChatAnthropic(
        model=settings.worker_model,
        api_key=settings.anthropic_api_key,
        callbacks=[tracker],
    ).with_structured_output(_AnalysisOutput)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_HUMAN.format(title=title, content=content)),
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
