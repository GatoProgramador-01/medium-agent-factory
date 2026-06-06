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

import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.base import AgentTokenTracker
from app.config import settings


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


_SYSTEM = """You are a professional human content writer who has published 200+ successful
articles on Medium and earns $2000+/month from the platform. Your writing voice is:

TONE: Conversational but authoritative. You explain complex topics the way a smart
friend would — with genuine enthusiasm, occasional humor, and zero corporate-speak.

STRUCTURE rules you always follow:
1. Open with a specific story, shocking stat, or provocative question — NEVER "In this article"
2. Vary sentence length: short punchy sentences after long complex ones
3. Use contractions naturally (you're, it's, don't, I've)
4. Include at least one personal anecdote or "I remember when" moment
5. Add one em-dash aside or parenthetical per 300 words for personality
6. Earn every H2 header — only use one when the topic genuinely shifts
7. Bullet lists: max 2 per post, 3-5 items each. Prose > lists
8. End with a specific call to action, not "I hope this helps"
9. Mark image spots as [IMAGE: what would go here] — editors will add real images later

The goal: readers who start this post FINISH it. 35%+ read ratio is the target."""


_HUMAN_INITIAL = """Write a complete Medium post on this topic.

TOPIC: {topic}

TREND CONTEXT (use this to make the content timely and relevant):
{trend_context}

RECOMMENDED TAGS: {tags}
TARGET AUDIENCE: {audience}

Write the full post now. Remember: open with a hook, not an introduction."""


_HUMAN_REVISION = """Revise this Medium post based on the quality analysis below.

ORIGINAL TITLE: {title}
ORIGINAL CONTENT:
{content}

QUALITY SCORE: {score}/1.0 (needs to reach {min_score})

REVISION BRIEF (apply ALL of these):
{revision_prompt}

SPECIFIC ISSUES TO FIX:
{issues_list}

Rewrite the full post incorporating every correction. Keep what's strong."""


def _pick_model(revision_number: int) -> str:
    """Haiku for attempts 0 and 1, Sonnet only on attempt 2+ (last resort)."""
    return settings.worker_model if revision_number < 2 else settings.supervisor_model


async def generate_initial_post(
    run_id: str,
    topic: str,
    trend_context: str,
    tags: list[str],
    audience: str,
) -> GeneratedPost:
    model = _pick_model(0)
    return await _call_generator(
        run_id=run_id,
        agent_label="content_generator_initial",
        model=model,
        messages=[
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=_HUMAN_INITIAL.format(
                topic=topic,
                trend_context=trend_context,
                tags=", ".join(tags),
                audience=audience,
            )),
        ],
    )


async def revise_post(
    run_id: str,
    title: str,
    content: str,
    score: float,
    revision_prompt: str,
    issues: list[dict],
    revision_number: int = 1,
) -> GeneratedPost:
    model = _pick_model(revision_number)
    issues_list = "\n".join(
        f"- [{i['severity'].upper()}] {i['category']}: {i['suggestion']}"
        for i in issues
    )
    return await _call_generator(
        run_id=run_id,
        agent_label=f"content_generator_revision_{revision_number}",
        model=model,
        messages=[
            SystemMessage(content=_SYSTEM),
            HumanMessage(content=_HUMAN_REVISION.format(
                title=title,
                content=content,
                score=round(score, 2),
                min_score=settings.min_quality_score,
                revision_prompt=revision_prompt,
                issues_list=issues_list,
            )),
        ],
    )


async def _call_generator(
    run_id: str,
    agent_label: str,
    model: str,
    messages: list,
) -> GeneratedPost:
    tracker = AgentTokenTracker(
        agent_name=agent_label,
        run_id=run_id,
        model=model,
    )

    llm = ChatAnthropic(
        model=model,
        api_key=settings.anthropic_api_key,
        max_tokens=4096,
        callbacks=[tracker],
    ).with_structured_output(GeneratedPost)

    result: GeneratedPost = await llm.ainvoke(messages)
    return result
