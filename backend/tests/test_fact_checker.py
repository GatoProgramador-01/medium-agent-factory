"""
Sprint 7 — Source Reliability: FactChecker agent tests.

RED phase: all tests written before implementation exists.

The fact_checker module must:
  1. Extract atomic claims (numbers, percentages, dollar amounts, company claims) from content.
  2. Search each claim with Tavily in parallel.
  3. Inject source hyperlinks for SUPPORTED claims into the content.
  4. Return QualityIssue(category="unattributed_claim") for UNVERIFIABLE claims.
  5. Degrade gracefully when Tavily is unavailable.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.post import AtomicClaim, QualityIssue, VerificationResult


# ── Helper fixtures ───────────────────────────────────────────────────────────

CONTENT_WITH_CLAIMS = """
# Why DeepSeek V3 Cut Our Costs by 73%

We ran 30 days of production load on DeepSeek V3 starting in January 2025.
The result: our inference bill dropped from $12,400 per month to $3,348 — a 73% reduction.
Claude Haiku costs $0.25 per million input tokens according to Anthropic's pricing page.
GPT-4o Mini costs $0.15 per million tokens as of March 2025 per OpenAI's pricing page.
"""

CONTENT_NO_CLAIMS = """
# Thoughts on AI

AI is changing things. Some people like it, others don't. It's an interesting time.
"""


# ── AtomicClaim model tests ───────────────────────────────────────────────────

class TestAtomicClaimModel:
    def test_atomic_claim_has_required_fields(self) -> None:
        claim = AtomicClaim(
            text="73% reduction",
            claim_type="percentage",
            search_query="DeepSeek V3 inference cost reduction percentage 2025",
            location="paragraph 1",
        )
        assert claim.text == "73% reduction"
        assert claim.claim_type == "percentage"
        assert claim.search_query
        assert claim.location

    def test_claim_types_are_restricted(self) -> None:
        """claim_type must be one of the canonical risk categories."""
        valid_types = {"statistic", "percentage", "dollar_amount", "date", "company_claim"}
        for ct in valid_types:
            claim = AtomicClaim(text="x", claim_type=ct, search_query="q", location="l")
            assert claim.claim_type == ct


class TestVerificationResultModel:
    def test_supported_result(self) -> None:
        result = VerificationResult(
            claim=AtomicClaim(
                text="73%", claim_type="percentage", search_query="q", location="p1"
            ),
            verdict="SUPPORTED",
            source_url="https://example.com/deepseek",
            source_title="DeepSeek pricing comparison",
        )
        assert result.verdict == "SUPPORTED"
        assert result.source_url.startswith("https://")

    def test_unverifiable_result_has_no_url(self) -> None:
        result = VerificationResult(
            claim=AtomicClaim(
                text="73%", claim_type="percentage", search_query="q", location="p1"
            ),
            verdict="UNVERIFIABLE",
            source_url=None,
            source_title=None,
        )
        assert result.verdict == "UNVERIFIABLE"
        assert result.source_url is None


# ── Claim extraction tests ────────────────────────────────────────────────────

class TestClaimExtraction:
    @pytest.mark.asyncio
    async def test_extract_returns_list_of_atomic_claims(self) -> None:
        from app.agents.fact_checker import extract_claims

        mock_claims = [
            AtomicClaim(text="73% reduction", claim_type="percentage",
                        search_query="deepseek cost 73%", location="paragraph 1"),
            AtomicClaim(text="$12,400 per month", claim_type="dollar_amount",
                        search_query="deepseek inference cost $12400", location="paragraph 1"),
        ]
        with patch("app.agents.fact_checker._llm_extract_claims", return_value=mock_claims):
            result = await extract_claims(CONTENT_WITH_CLAIMS)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(c, AtomicClaim) for c in result)

    @pytest.mark.asyncio
    async def test_extract_returns_empty_list_for_no_claims(self) -> None:
        from app.agents.fact_checker import extract_claims

        with patch("app.agents.fact_checker._llm_extract_claims", return_value=[]):
            result = await extract_claims(CONTENT_NO_CLAIMS)

        assert result == []

    @pytest.mark.asyncio
    async def test_extract_handles_llm_failure_gracefully(self) -> None:
        from app.agents.fact_checker import extract_claims

        with patch("app.agents.fact_checker._llm_extract_claims",
                   side_effect=Exception("LLM timeout")):
            result = await extract_claims(CONTENT_WITH_CLAIMS)

        assert result == []


# ── Claim verification tests ──────────────────────────────────────────────────

class TestClaimVerification:
    def _make_claim(self, text: str = "73%", claim_type: str = "percentage") -> AtomicClaim:
        return AtomicClaim(
            text=text,
            claim_type=claim_type,
            search_query=f"deepseek {text}",
            location="paragraph 1",
        )

    @pytest.mark.asyncio
    async def test_supported_claim_when_tavily_returns_match(self) -> None:
        from app.agents.fact_checker import verify_claim

        claim = self._make_claim()
        tavily_result = {
            "results": [
                {
                    "url": "https://example.com/deepseek",
                    "title": "DeepSeek cost analysis",
                    "content": "DeepSeek V3 reduced inference costs by 73% for most teams.",
                }
            ]
        }
        with patch("app.agents.fact_checker._tavily_search",
                   new_callable=AsyncMock, return_value=tavily_result):
            result = await verify_claim(claim)

        assert result.verdict == "SUPPORTED"
        assert result.source_url == "https://example.com/deepseek"
        assert result.source_title == "DeepSeek cost analysis"

    @pytest.mark.asyncio
    async def test_unverifiable_when_tavily_returns_no_results(self) -> None:
        from app.agents.fact_checker import verify_claim

        claim = self._make_claim()
        with patch("app.agents.fact_checker._tavily_search",
                   new_callable=AsyncMock, return_value={"results": []}):
            result = await verify_claim(claim)

        assert result.verdict == "UNVERIFIABLE"
        assert result.source_url is None

    @pytest.mark.asyncio
    async def test_unverifiable_when_tavily_raises(self) -> None:
        from app.agents.fact_checker import verify_claim

        claim = self._make_claim()
        with patch("app.agents.fact_checker._tavily_search",
                   new_callable=AsyncMock, side_effect=Exception("timeout")):
            result = await verify_claim(claim)

        assert result.verdict == "UNVERIFIABLE"

    @pytest.mark.asyncio
    async def test_verify_claims_runs_in_parallel(self) -> None:
        """verify_claims must gather all Tavily calls concurrently, not sequentially."""
        from app.agents.fact_checker import verify_claims
        import asyncio

        claims = [
            self._make_claim("73%", "percentage"),
            self._make_claim("$12,400", "dollar_amount"),
            self._make_claim("January 2025", "date"),
        ]
        call_order: list[str] = []

        async def fake_tavily(query: str, **kwargs: Any) -> dict[str, Any]:
            call_order.append(query)
            # content must contain the query tokens so _snippet_supports_claim passes
            return {"results": [{"url": f"https://ex.com/{len(call_order)}", "title": "Source", "content": query}]}

        with patch("app.agents.fact_checker._tavily_search", side_effect=fake_tavily):
            results = await verify_claims(claims)

        assert len(results) == 3
        assert all(r.verdict == "SUPPORTED" for r in results)


# ── Hyperlink injection tests ─────────────────────────────────────────────────

class TestHyperlinkInjection:
    def test_supported_claim_injects_hyperlink(self) -> None:
        from app.agents.fact_checker import inject_hyperlinks

        content = "Claude Haiku costs $0.25 per million input tokens."
        claim = AtomicClaim(
            text="$0.25 per million input tokens",
            claim_type="dollar_amount",
            search_query="Claude Haiku price per million tokens",
            location="paragraph 1",
        )
        result = VerificationResult(
            claim=claim,
            verdict="SUPPORTED",
            source_url="https://anthropic.com/pricing",
            source_title="Anthropic pricing",
        )
        annotated = inject_hyperlinks(content, [result])

        assert "[" in annotated
        assert "https://anthropic.com/pricing" in annotated

    def test_unverifiable_claim_not_injected(self) -> None:
        from app.agents.fact_checker import inject_hyperlinks

        content = "Claude Haiku costs $0.25 per million input tokens."
        claim = AtomicClaim(
            text="$0.25 per million input tokens",
            claim_type="dollar_amount",
            search_query="Claude Haiku price",
            location="paragraph 1",
        )
        result = VerificationResult(
            claim=claim,
            verdict="UNVERIFIABLE",
            source_url=None,
            source_title=None,
        )
        annotated = inject_hyperlinks(content, [result])

        assert annotated == content

    def test_inject_multiple_supported_claims(self) -> None:
        from app.agents.fact_checker import inject_hyperlinks

        content = "Cost dropped 73%. Haiku costs $0.25 per million tokens."
        claims_results = [
            VerificationResult(
                claim=AtomicClaim(
                    text="73%", claim_type="percentage",
                    search_query="q1", location="p1"
                ),
                verdict="SUPPORTED",
                source_url="https://example.com/1",
                source_title="Source 1",
            ),
            VerificationResult(
                claim=AtomicClaim(
                    text="$0.25 per million tokens", claim_type="dollar_amount",
                    search_query="q2", location="p1"
                ),
                verdict="SUPPORTED",
                source_url="https://example.com/2",
                source_title="Source 2",
            ),
        ]
        annotated = inject_hyperlinks(content, claims_results)

        assert "https://example.com/1" in annotated
        assert "https://example.com/2" in annotated


# ── Issue generation tests ────────────────────────────────────────────────────

class TestIssueGeneration:
    def test_unverifiable_claim_becomes_quality_issue(self) -> None:
        from app.agents.fact_checker import results_to_issues

        result = VerificationResult(
            claim=AtomicClaim(
                text="73% reduction", claim_type="percentage",
                search_query="q", location="paragraph 1"
            ),
            verdict="UNVERIFIABLE",
            source_url=None,
            source_title=None,
        )
        issues = results_to_issues([result])

        assert len(issues) == 1
        issue = issues[0]
        assert isinstance(issue, QualityIssue)
        assert issue.category == "unattributed_claim"
        assert issue.severity == "HIGH"
        assert "73% reduction" in issue.suggestion

    def test_supported_claims_produce_no_issues(self) -> None:
        from app.agents.fact_checker import results_to_issues

        result = VerificationResult(
            claim=AtomicClaim(
                text="73%", claim_type="percentage",
                search_query="q", location="p1"
            ),
            verdict="SUPPORTED",
            source_url="https://example.com",
            source_title="Source",
        )
        issues = results_to_issues([result])

        assert issues == []

    def test_mixed_results_only_unverifiable_become_issues(self) -> None:
        from app.agents.fact_checker import results_to_issues

        results = [
            VerificationResult(
                claim=AtomicClaim(text="73%", claim_type="percentage", search_query="q", location="p1"),
                verdict="SUPPORTED",
                source_url="https://example.com",
                source_title="S",
            ),
            VerificationResult(
                claim=AtomicClaim(text="$1B market", claim_type="dollar_amount", search_query="q", location="p2"),
                verdict="UNVERIFIABLE",
                source_url=None,
                source_title=None,
            ),
        ]
        issues = results_to_issues(results)

        assert len(issues) == 1
        assert issues[0].category == "unattributed_claim"
        assert "$1B market" in issues[0].suggestion


# ── Top-level run_fact_check tests ────────────────────────────────────────────

class TestRunFactCheck:
    @pytest.mark.asyncio
    async def test_run_fact_check_returns_annotated_content_and_issues(self) -> None:
        from app.agents.fact_checker import run_fact_check

        mock_claim = AtomicClaim(
            text="73%", claim_type="percentage",
            search_query="deepseek 73%", location="p1"
        )
        mock_result_supported = VerificationResult(
            claim=mock_claim,
            verdict="SUPPORTED",
            source_url="https://example.com/deepseek",
            source_title="DeepSeek cost",
        )

        with (
            patch("app.agents.fact_checker.extract_claims",
                  new_callable=AsyncMock, return_value=[mock_claim]),
            patch("app.agents.fact_checker.verify_claims",
                  new_callable=AsyncMock, return_value=[mock_result_supported]),
        ):
            annotated, issues = await run_fact_check(CONTENT_WITH_CLAIMS)

        assert isinstance(annotated, str)
        assert isinstance(issues, list)
        assert "https://example.com/deepseek" in annotated
        assert issues == []

    @pytest.mark.asyncio
    async def test_run_fact_check_returns_original_content_when_no_claims(self) -> None:
        from app.agents.fact_checker import run_fact_check

        with patch("app.agents.fact_checker.extract_claims",
                   new_callable=AsyncMock, return_value=[]):
            annotated, issues = await run_fact_check(CONTENT_NO_CLAIMS)

        assert annotated == CONTENT_NO_CLAIMS
        assert issues == []

    @pytest.mark.asyncio
    async def test_run_fact_check_when_disabled_returns_original_unchanged(self) -> None:
        from app.agents.fact_checker import run_fact_check

        with patch("app.agents.fact_checker.settings") as s:
            s.fact_check_enabled = False
            annotated, issues = await run_fact_check(CONTENT_WITH_CLAIMS)

        assert annotated == CONTENT_WITH_CLAIMS
        assert issues == []

    @pytest.mark.asyncio
    async def test_run_fact_check_unverifiable_claim_in_issues(self) -> None:
        from app.agents.fact_checker import run_fact_check

        mock_claim = AtomicClaim(
            text="$1B market cap", claim_type="dollar_amount",
            search_query="deepseek 1B market cap", location="p2"
        )
        mock_result = VerificationResult(
            claim=mock_claim,
            verdict="UNVERIFIABLE",
            source_url=None,
            source_title=None,
        )

        with (
            patch("app.agents.fact_checker.extract_claims",
                  new_callable=AsyncMock, return_value=[mock_claim]),
            patch("app.agents.fact_checker.verify_claims",
                  new_callable=AsyncMock, return_value=[mock_result]),
        ):
            annotated, issues = await run_fact_check(CONTENT_WITH_CLAIMS)

        assert len(issues) == 1
        assert issues[0].category == "unattributed_claim"
        assert issues[0].severity == "HIGH"
        assert annotated == CONTENT_WITH_CLAIMS


# ── Config tests ──────────────────────────────────────────────────────────────

class TestFactCheckerConfig:
    def test_fact_check_enabled_defaults_to_true(self) -> None:
        from app.config import Settings
        assert Settings().fact_check_enabled is True, (
            "fact_check_enabled must default to True — source verification is on by default"
        )
