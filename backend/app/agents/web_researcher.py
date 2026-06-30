"""
Web Researcher — Tavily search + LLM synthesis.

Pipeline role: runs before content_generation. Gathers real statistics,
named sources, and current context so the writer never has to invent data.

Failure model: any exception (missing key, Tavily error, LLM error) returns ""
and the pipeline continues exactly as before — no hard dependency.
"""

import asyncio
import json
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator, model_validator

from app.agents.base import AgentTokenTracker
from app.agents.llm_factory import get_llm, get_model_name
from app.agents.logger import log_step
from app.config import settings

try:
    from tavily import TavilyClient
except ImportError:  # pragma: no cover
    TavilyClient = None


# ── Pydantic models ────────────────────────────────────────────────────────────


class _Queries(BaseModel):
    queries: list[str] = Field(min_length=2, max_length=5)

    @model_validator(mode="before")
    @classmethod
    def _wrap_bare_list(cls, v: Any) -> Any:
        # json_mode can return a raw JSON array instead of {"queries": [...]}
        if isinstance(v, list):
            return {"queries": v}
        return v

    @field_validator("queries", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return []


class ResearchBrief(BaseModel):
    key_facts: list[str] = Field(
        description=(
            "3-6 concrete statistics with source and year. "
            "Example: 'In 2024, Medium reported 65% of Boost earnings went to posts under 1,700 words'"
        )
    )
    named_examples: list[str] = Field(
        description="Named companies, people, studies, or products found in results"
    )
    trend_summary: str = Field(
        description="2-3 sentences describing the current landscape around this topic"
    )
    surprising_finding: str = Field(
        description="One counterintuitive or unexpected finding from the search results"
    )

    @field_validator("key_facts", "named_examples", mode="before")
    @classmethod
    def _coerce_list(cls, v: Any) -> Any:
        if not isinstance(v, str):
            return v
        cleaned = (
            v.replace("‘", "'").replace("’", "'")
             .replace("“", '"').replace("”", '"')
             .replace("—", "-").replace("–", "-")
             .replace("…", "...")
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []


# ── Steps ─────────────────────────────────────────────────────────────────────


async def _generate_queries(run_id: str, topic: str) -> list[str]:
    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(agent_name="web_researcher", run_id=run_id, model=model_name)
    llm = get_llm("worker", callbacks=[tracker]).with_structured_output(_Queries)

    messages = [
        SystemMessage(content=(
            "You generate 5 web search queries to find real data for a Medium article. "
            "Query 1: statistics and data about the topic. "
            "Query 2: named case studies or real-world examples. "
            "Query 3: recent news or trend related to the topic. "
            "Query 4: expert opinion or authoritative source on the topic. "
            "Query 5: criticism, challenges, or counterarguments related to the topic. "
            "Keep each query under 10 words. Return only the queries list."
        )),
        HumanMessage(content=f"Article topic: {topic}"),
    ]
    result: _Queries = await llm.ainvoke(messages)  # type: ignore[assignment]
    return result.queries


async def _run_search(query: str) -> list[dict[str, Any]]:
    if TavilyClient is None:
        raise RuntimeError("tavily package not installed")
    client = TavilyClient(api_key=settings.tavily_api_key)
    response: dict[str, Any] = await asyncio.to_thread(
        client.search,
        query=query,
        search_depth="advanced",
        max_results=5,
        include_answer=False,
    )
    return cast(list[dict[str, Any]], response.get("results", []))


async def _synthesize(
    run_id: str,
    topic: str,
    all_results: list[list[dict[str, Any]]],
) -> ResearchBrief:
    seen: set[str] = set()
    flat: list[dict[str, Any]] = []
    for batch in all_results:
        for r in batch:
            url: str = r.get("url", "")
            if url not in seen:
                seen.add(url)
                flat.append(r)

    snippets = "\n\n".join(
        f"[{i+1}] {r.get('title', '')}\n"
        f"URL: {r.get('url', '')}\n"
        f"{str(r.get('content', ''))[:500]}"
        for i, r in enumerate(flat[:15])
    )

    model_name = get_model_name("worker")
    tracker = AgentTokenTracker(agent_name="web_researcher", run_id=run_id, model=model_name)
    llm = get_llm("worker", callbacks=[tracker]).with_structured_output(ResearchBrief)

    messages = [
        SystemMessage(content=(
            "Extract factual research from these search results to help a writer "
            "ground their Medium article. Only include facts that appear in the results — "
            "never invent data. Focus on numbers, named sources, and surprising findings."
        )),
        HumanMessage(content=f"Article topic: {topic}\n\nSearch results:\n{snippets}"),
    ]
    brief: ResearchBrief = await llm.ainvoke(messages)  # type: ignore[assignment]
    return brief


def _format_brief(
    brief: ResearchBrief,
    queries: list[str],
    source_urls: list[str] | None = None,
) -> str:
    facts = (
        "\n".join(f"• {f}" for f in brief.key_facts)
        if brief.key_facts
        else "  (no specific statistics found)"
    )
    examples = (
        "\n".join(f"• {e}" for e in brief.named_examples)
        if brief.named_examples
        else "  (no named examples found)"
    )
    query_list = " | ".join(f'"{q}"' for q in queries)

    sources_block = (
        "\n\nSOURCE URLS (add a ## Sources section at the end of your post with these):\n"
        + "\n".join(f"- {url}" for url in (source_urls or [])[:8])
    ) if source_urls else ""

    return (
        "RESEARCH FINDINGS — ground your post with these verified data points "
        "(do not cite anything not listed here):\n\n"
        f"KEY STATISTICS & DATA POINTS:\n{facts}\n\n"
        f"NAMED EXAMPLES (companies, people, studies, products):\n{examples}\n\n"
        f"CURRENT TREND:\n{brief.trend_summary}\n\n"
        f"SURPRISING FINDING:\n{brief.surprising_finding}\n\n"
        f"Search queries used: {query_list}"
        f"{sources_block}"
    )


# ── Public entrypoint ──────────────────────────────────────────────────────────


async def research_topic(run_id: str, topic: str) -> str:
    """
    Search the web for facts related to the topic and return a formatted
    research brief for injection into the content generator's trend_context slot.

    Returns "" on any failure — the pipeline continues unchanged.
    """
    if not settings.tavily_api_key:
        return ""
    if TavilyClient is None:
        await log_step(
            run_id, "web_researcher",
            "tavily package not installed — set TAVILY_API_KEY and install tavily",
            level="error",
        )
        return ""

    queries = await _generate_queries(run_id, topic)

    results = await asyncio.gather(
        *[_run_search(q) for q in queries],
        return_exceptions=True,
    )
    successful = [r for r in results if isinstance(r, list) and r]
    if not successful:
        return ""

    source_urls: list[str] = list(
        dict.fromkeys(
            r.get("url", "").rstrip("/").replace("http://", "https://")
            for batch in successful
            for r in batch
            if r.get("url")
        )
    )[:8]

    brief = await _synthesize(run_id, topic, successful)
    return _format_brief(brief, queries, source_urls)
