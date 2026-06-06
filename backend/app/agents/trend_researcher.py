"""
TrendResearchAgent

Searches for profitable Medium post topics using Tavily web search,
then synthesizes a structured trend report with Claude.

Focus areas: monetization, content creator guides, passive income —
the categories with the highest Medium earnings per read.
"""

import time
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.agents.base import AgentTokenTracker
from app.config import settings
from app.database import get_db


class TrendOpportunity(BaseModel):
    title: str = Field(description="Suggested post title")
    angle: str = Field(description="Unique angle that separates this from generic posts")
    search_volume_signal: str = Field(description="Why this topic is trending right now")
    monetization_potential: str = Field(description="HIGH | MEDIUM | LOW with brief reason")
    target_audience: str = Field(description="Specific reader persona")
    estimated_read_time_min: int = Field(description="Target article read time in minutes")


class TrendReport(BaseModel):
    opportunities: list[TrendOpportunity] = Field(
        description="Top 3 ranked post opportunities"
    )
    market_context: str = Field(
        description="Brief summary of current content creator monetization landscape"
    )
    recommended_topic: str = Field(
        description="The single best topic to write about right now"
    )
    recommended_tags: list[str] = Field(
        description="5 Medium tags for maximum discoverability"
    )


_SYSTEM = """You are a content strategist specializing in Medium monetization.
Your job is to identify post topics that:
1. Have high search demand right now
2. Are underserved by quality content
3. Target creators wanting to earn money online
4. Can be written as a 7-9 minute read (1500-2000 words)
5. Will achieve 35%+ read ratio due to genuine practical value

Analyze the search results and produce actionable topic recommendations.
Be specific — "Ko-fi Setup Guide 2025" beats "make money online"."""

_HUMAN = """Research results for trending monetization and content creator topics:

{search_results}

Today's date: {date}

Based on these results, identify the top 3 post opportunities.
Pick the single best one as your recommendation."""


async def run_trend_research(run_id: str, custom_topic: str | None = None) -> TrendReport:
    tracker = AgentTokenTracker(
        agent_name="trend_researcher",
        run_id=run_id,
        model=settings.worker_model,
    )

    llm = ChatAnthropic(
        model=settings.worker_model,
        api_key=settings.anthropic_api_key,
        callbacks=[tracker],
    ).with_structured_output(TrendReport)

    search_results = await _search_trends(custom_topic)

    from datetime import date
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_HUMAN.format(
            search_results=search_results,
            date=date.today().isoformat(),
        )),
    ])

    start = time.perf_counter()
    report: TrendReport = await (prompt | llm).ainvoke({})
    duration_ms = int((time.perf_counter() - start) * 1000)

    db = get_db()
    await db.trends.insert_one({
        "run_id": run_id,
        "report": report.model_dump(),
        "duration_ms": duration_ms,
        "search_query": custom_topic or "auto",
    })

    return report


async def _search_trends(custom_topic: str | None) -> str:
    queries = [
        custom_topic or "best medium post topics 2025 monetization content creators",
        "ko-fi patreon substack earnings guide 2025",
        "passive income content creator strategies trending 2025",
        "medium partner program earnings tips 2025",
    ]

    if settings.tavily_api_key:
        return await _tavily_search(queries)
    return await _duckduckgo_search(queries[0])


async def _tavily_search(queries: list[str]) -> str:
    from tavily import TavilyClient

    client = TavilyClient(api_key=settings.tavily_api_key)
    results: list[str] = []

    for query in queries[:3]:
        try:
            resp = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=True,
            )
            if resp.get("answer"):
                results.append(f"Query: {query}\nAnswer: {resp['answer']}")
            for r in resp.get("results", [])[:3]:
                results.append(f"- {r['title']}: {r['content'][:300]}")
        except Exception:
            pass

    return "\n\n".join(results) if results else "No search results available."


async def _duckduckgo_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=10))
        return "\n".join(
            f"- {h['title']}: {h['body'][:250]}" for h in hits
        )
    except Exception:
        return (
            "Search unavailable. Focus on evergreen monetization topics: "
            "Ko-fi setup, Substack growth, Medium partner program optimization, "
            "Patreon tier strategy, newsletter monetization."
        )
