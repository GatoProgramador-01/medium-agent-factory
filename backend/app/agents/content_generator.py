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
    """
    Always use 'worker' when DeepSeek or a local LLM is configured —
    there is only one model so escalation is meaningless.
    For Anthropic only: escalate to 'supervisor' (Sonnet) on revision 2+
    as a last-resort quality upgrade over Haiku.
    """
    if settings.use_deepseek or settings.use_local_llm:
        return "worker"
    return "worker" if revision_number < 2 else "supervisor"


async def generate_initial_post(
    run_id: str,
    topic: str,
    trend_context: str,
    tags: list[str],
    audience: str,
    exemplar_section: str = "",
    series_context: str = "",
) -> GeneratedPost:
    role = _pick_role(0)
    series_block = (
        f"SERIES CONTEXT (position this post correctly within the series):\n{series_context}\n"
        if series_context
        else ""
    )
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
                    exemplar_section=exemplar_section,
                    series_context=series_block,
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
    prior_cycle_summary: str = "",
) -> GeneratedPost:
    role = _pick_role(revision_number)
    word_count = len(content.split())

    # Compute intro word count so the reviser sees it as a number before STEP 0
    intro_text = content.split("---")[0].split("## ")[0] if ("---" in content or "## " in content) else content[:500]
    intro_word_count = len(intro_text.split())

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
                    prior_cycle_summary=prior_cycle_summary,
                    intro_word_count=intro_word_count,
                )
            ),
        ],
    )


async def expand_post(
    run_id: str,
    title: str,
    content: str,
    deficit: int,
) -> str:
    """
    Generate ONE new H2 section (~deficit words) to append to a post that
    cleared all quality gates but is short of the minimum word count.
    Returns only the new section text; the caller appends it to post.content.
    Uses creation mode (not revision mode) so the LLM adds, never edits.
    """
    role = "worker"
    model_name = get_model_name(role)
    tracker = AgentTokenTracker(
        agent_name="content_generator_expand",
        run_id=run_id,
        model=model_name,
    )

    llm = with_langchain_retry(get_llm(role, max_tokens=1024, callbacks=[tracker]))

    messages: list[Any] = [
        SystemMessage(content=(
            "You are a technical writer adding one new section to an existing Medium post. "
            "Output ONLY the new section — nothing else, no preamble, no sign-off. "
            "Start with a Markdown H2 heading (## Section Title). "
            "Every sentence must contain a specific fact, number, named tool, or concrete example. "
            "Do not summarize, repeat, or conclude — add new information only."
        )),
        HumanMessage(content=(
            f"Post title: {title}\n\n"
            f"Existing content:\n{content}\n\n"
            f"---\n"
            f"The post needs approximately {deficit} more words. "
            f"Write ONE new H2 section (~{deficit} words) covering the most obvious follow-up "
            f"topic a reader would ask about after reading the existing content. "
            f"Use specific numbers, tool names, and real examples — no vague generalizations. "
            f"Output the new section only, starting with ##"
        )),
    ]

    result = await llm.ainvoke(messages)
    return result.content if hasattr(result, "content") else str(result)


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
