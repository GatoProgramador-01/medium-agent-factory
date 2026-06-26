"""
FactChecker agent — Sprint 7: Source Reliability

Public API:
    run_fact_check(content: str) -> tuple[str, list[QualityIssue]]

Pipeline:
  1. extract_claims   — LLM (Haiku) extracts every numeric/company claim as AtomicClaim list
  2. verify_claims    — parallel Tavily search, one call per claim
  3. inject_hyperlinks — SUPPORTED claims get source hyperlink injected in-place
  4. results_to_issues — UNVERIFIABLE claims become QualityIssue(category="unattributed_claim")

Degrades gracefully:
  - LLM extraction failure     → returns [], original content unchanged
  - Tavily unavailable/timeout → verdict becomes UNVERIFIABLE (not an error)
  - fact_check_enabled = False → returns original content + empty issue list immediately
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.agents.llm_factory import get_llm
from app.config import settings
from app.models.post import AtomicClaim, QualityIssue, VerificationResult


# ── Pydantic output model for LLM extraction ──────────────────────────────────

class _ClaimList(BaseModel):
    claims: list[_ClaimItem] = Field(default_factory=list)


class _ClaimItem(BaseModel):
    text: str = Field(description="Exact phrase from the post containing the claim")
    claim_type: str = Field(
        description="One of: statistic, percentage, dollar_amount, date, company_claim"
    )
    search_query: str = Field(description="Optimized Tavily search query to verify this claim")
    location: str = Field(description="Where in the post this claim appears, e.g. 'paragraph 2'")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _build_extraction_chain() -> Any:
    parser = PydanticOutputParser(pydantic_object=_ClaimList)
    system = (
        "You are a fact-checking assistant. Extract every verifiable factual claim from the "
        "provided text that falls into one of these categories:\n"
        "  - percentage: any percentage or ratio (e.g. '73% reduction', '3× faster')\n"
        "  - dollar_amount: any dollar figure or cost (e.g. '$0.25 per million tokens')\n"
        "  - statistic: numeric claim with a source or study (e.g. '120× more in AI text')\n"
        "  - date: specific year or date tied to a claim (e.g. 'January 2025')\n"
        "  - company_claim: product name + attributed capability (e.g. 'GPT-4o Mini costs X')\n\n"
        "Do NOT extract:\n"
        "  - Opinions, hedges, or qualitative claims\n"
        "  - First-person experiences (I tried, we saw)\n"
        "  - Generic statements without numbers\n\n"
        "For each claim, write a search_query that would find the primary source on the web.\n\n"
        "{format_instructions}"
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system),
        ("human", "Extract all verifiable claims from this post content:\n\n{content}"),
    ]).partial(format_instructions=parser.get_format_instructions())
    llm = get_llm("worker")
    return prompt | llm | parser


async def _llm_extract_claims(content: str) -> list[AtomicClaim]:
    chain = _build_extraction_chain()
    result: _ClaimList = await chain.ainvoke({"content": content[:4000]})
    return [
        AtomicClaim(
            text=item.text,
            claim_type=item.claim_type,
            search_query=item.search_query,
            location=item.location,
        )
        for item in result.claims
    ]


async def _tavily_search(query: str, max_results: int = 3) -> dict[str, Any]:
    if not settings.tavily_api_key:
        return {"results": []}
    from tavily import AsyncTavilyClient  # type: ignore[import-untyped]
    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    raw = await client.search(query=query, max_results=max_results)
    return raw if isinstance(raw, dict) else {"results": []}


def _snippet_supports_claim(claim_text: str, snippet: str) -> bool:
    """Lightweight entailment check: key tokens from claim appear in the snippet."""
    tokens = [t.lower() for t in re.split(r"[\s,]+", claim_text) if len(t) >= 3]
    if not tokens:
        return False
    snippet_lower = snippet.lower()
    matches = sum(1 for t in tokens if t in snippet_lower)
    return matches >= max(1, len(tokens) // 2)


# ── Public primitives ──────────────────────────────────────────────────────────

async def extract_claims(content: str) -> list[AtomicClaim]:
    try:
        return await _llm_extract_claims(content)
    except Exception:
        return []


async def verify_claim(claim: AtomicClaim) -> VerificationResult:
    try:
        raw = await _tavily_search(claim.search_query)
        for result in raw.get("results", []):
            snippet = result.get("content", "") + " " + result.get("title", "")
            if snippet.strip() and _snippet_supports_claim(claim.text, snippet):
                return VerificationResult(
                    claim=claim,
                    verdict="SUPPORTED",
                    source_url=result.get("url"),
                    source_title=result.get("title"),
                )
        return VerificationResult(claim=claim, verdict="UNVERIFIABLE",
                                  source_url=None, source_title=None)
    except Exception:
        return VerificationResult(claim=claim, verdict="UNVERIFIABLE",
                                  source_url=None, source_title=None)


async def verify_claims(claims: list[AtomicClaim]) -> list[VerificationResult]:
    return list(await asyncio.gather(*[verify_claim(c) for c in claims]))


def inject_hyperlinks(content: str, results: list[VerificationResult]) -> str:
    annotated = content
    for result in results:
        if result.verdict != "SUPPORTED" or not result.source_url:
            continue
        claim_text = result.claim.text
        title = result.source_title or result.source_url
        linked = f"[{claim_text}]({result.source_url})"
        if claim_text in annotated and f"]({result.source_url})" not in annotated:
            annotated = annotated.replace(claim_text, linked, 1)
    return annotated


def results_to_issues(results: list[VerificationResult]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for result in results:
        if result.verdict == "UNVERIFIABLE":
            issues.append(QualityIssue(
                severity="HIGH",
                category="unattributed_claim",
                location=result.claim.location,
                suggestion=(
                    f'Unverifiable claim: "{result.claim.text}". '
                    "Either find and link a primary source (peer-reviewed paper, official dataset, "
                    "company pricing page) or rewrite as a first-person observation."
                ),
            ))
    return issues


# ── Top-level entry point ──────────────────────────────────────────────────────

async def run_fact_check(content: str) -> tuple[str, list[QualityIssue]]:
    if not settings.fact_check_enabled:
        return content, []

    claims = await extract_claims(content)
    if not claims:
        return content, []

    claims = claims[: settings.max_claims_per_run]  # cap Tavily cost per run

    results = await verify_claims(claims)
    annotated = inject_hyperlinks(content, results)
    issues = results_to_issues(results)
    return annotated, issues
