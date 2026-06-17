"""
ContentGeneratorAgent — cheapest-first model strategy

revision_number 0 (initial):   Haiku  — cheap draft, good enough ~60% of the time
revision_number 1:              Haiku  — apply corrections, often sufficient
revision_number 2+ (last):      Sonnet — quality upgrade, only when Haiku fails twice

Cost comparison vs always-Sonnet:
  Best case  (Haiku initial passes):      ~$0.005/post  (was $0.05)
  Common     (one Haiku revision):        ~$0.012/post  (was $0.05)
  Worst case (Sonnet revision needed):    ~$0.035/post  (was $0.05)
"""

import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.retry import with_langchain_retry
from app.config import settings
from app.prompt_loader import load_prompt, load_template


class GeneratedPost(BaseModel):
    title: str = Field(description="Compelling title, 6-12 words, no clickbait")
    subtitle: str = Field(description="One-sentence hook under the title")
    content: str = Field(
        description=(
            "Full Medium post in Markdown. "
            "1500-2000 words. No H1 (title is separate). "
            "Image placeholders as: [IMAGE: description of what would go here]"
        )
    )
    tags: list[str] = Field(description="Exactly 5 Medium tags, lowercase")
    image_suggestions: list[str] = Field(
        description="3 image ideas with suggested search terms for Unsplash/Pexels"
    )

    @field_validator("tags", "image_suggestions", mode="before")
    @classmethod
    def _coerce_json_string(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            cleaned = (
                v.replace("‘", "'")
                .replace("’", "'")  # ' '
                .replace("“", '"')
                .replace("”", '"')  # " "
                .replace("—", "-")
                .replace("–", "-")  # — –
                .replace("…", "...")  # …
            )
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return []


def _pick_role(revision_number: int) -> str:
    """worker (Haiku) for revision 0–1, supervisor (Sonnet) on revision 2+ only."""
    return "worker" if revision_number < 2 else "supervisor"


async def generate_initial_post(
    run_id: str,
    topic: str,
    trend_context: str,
    tags: list[str],
    audience: str,
) -> GeneratedPost:
    role = _pick_role(0)
    return await _call_generator(
        run_id=run_id,
        agent_label="content_generator_initial",
        role=role,
        messages=[
            SystemMessage(content=load_prompt("content_generator_system")),
            HumanMessage(
                content=load_template("content_generator_human_initial").format(
                    topic=topic,
                    trend_context=trend_context,
                    tags=", ".join(tags),
                    audience=audience,
                )
            ),
        ],
    )


async def revise_post(
    run_id: str,
    title: str,
    content: str,
    score: float,
    revision_prompt: str,
    issues: list[dict[str, Any]],
    strengths: list[str] | None = None,
    gate_failures: list[str] | None = None,
    read_ratio_breakdown: str | None = None,
    revision_number: int = 1,
) -> GeneratedPost:
    role = _pick_role(revision_number)
    word_count = len(content.split())

    issues_list = "\n".join(
        f"- [{i['severity'].upper()}] {i['category']}: {i['suggestion']}"
        + (f"\n  LOCATION: {i['location']}" if i.get("location") else "")
        for i in issues
    )
    strengths_list = (
        "\n".join(f"• {s}" for s in strengths)
        if strengths
        else "  (no specific strengths identified)"
    )
    gate_failures_list = (
        "\n".join(f"✗ {f}" for f in gate_failures)
        if gate_failures
        else "  (no hard gate failures — score improvement only)"
    )
    read_ratio_section = (
        read_ratio_breakdown
        if read_ratio_breakdown
        else "  (no read ratio breakdown available)"
    )

    return await _call_generator(
        run_id=run_id,
        agent_label=f"content_generator_revision_{revision_number}",
        role=role,
        messages=[
            SystemMessage(content=load_prompt("content_reviser_system")),
            HumanMessage(
                content=load_template("content_generator_human_revision").format(
                    title=title,
                    content=content,
                    word_count=word_count,
                    score=round(score, 2),
                    min_score=settings.min_quality_score,
                    revision_prompt=revision_prompt,
                    issues_list=issues_list,
                    strengths_list=strengths_list,
                    gate_failures_list=gate_failures_list,
                    read_ratio_section=read_ratio_section,
                )
            ),
        ],
    )


async def _call_generator(
    run_id: str,
    agent_label: str,
    role: str,
    messages: list[Any],
) -> GeneratedPost:
    model_name = get_model_name(role)
    tracker = AgentTokenTracker(
        agent_name=agent_label,
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(
        get_llm(role, max_tokens=4096, callbacks=[tracker]).with_structured_output(
            GeneratedPost
        )
    )

    result: GeneratedPost = await llm.ainvoke(messages)
    return result
