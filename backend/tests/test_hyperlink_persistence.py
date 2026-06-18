"""
Sprint 7.1 — Hyperlink persistence fix.

Problem: fact_check_node injects hyperlinks into the initial draft, but revision
cycles rewrite those sections and strip the links. The approved content has no sources.

Fix:
  - fact_check_node stores the VerificationResult list in PipelineState["fact_check_results"]
  - format_node re-applies inject_hyperlinks to the final approved content before format_post

Tests cover:
  1. fact_check_node returns fact_check_results in its state dict
  2. fact_check_results contains the full VerificationResult list (SUPPORTED + UNVERIFIABLE)
  3. format_node calls inject_hyperlinks with fact_check_results before format_post
  4. Hyperlinks appear in the content passed to format_post
  5. Claims no longer in final content are skipped gracefully
  6. Empty fact_check_results: format_node runs unchanged
  7. UNVERIFIABLE results do not inject hyperlinks
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.post import AtomicClaim, QualityIssue, VerificationResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_result(
    text: str,
    verdict: str = "SUPPORTED",
    url: str = "https://example.com/source",
    title: str = "Example Source",
) -> VerificationResult:
    return VerificationResult(
        claim=AtomicClaim(
            text=text,
            claim_type="percentage",
            search_query=f"search for {text}",
            location="paragraph 1",
        ),
        verdict=verdict,
        source_url=url if verdict == "SUPPORTED" else None,
        source_title=title if verdict == "SUPPORTED" else None,
    )


def _post_mock(content: str = "We reduced costs by 73%. Haiku costs $0.25 per million tokens.") -> Any:
    post = MagicMock()
    post.title = "Test Post"
    post.content = content
    post.tags = []
    return post


def _base_state(
    fact_check_results: list[VerificationResult] | None = None,
    content: str = "We reduced costs by 73%. Haiku costs $0.25 per million tokens.",
) -> dict[str, Any]:
    return {
        "run_id": "test-run-hyperlink",
        "custom_topic": "DeepSeek cost savings",
        "series_id": None,
        "series_context": "",
        "series_position": None,
        "trend_context": "",
        "post": _post_mock(content),
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 2,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": fact_check_results if fact_check_results is not None else [],
        "errors": [],
        "completed_steps": [],
    }


# ── fact_check_node stores VerificationResults ────────────────────────────────

class TestFactCheckNodeStoresResults:
    @pytest.mark.asyncio
    async def test_fact_check_node_returns_fact_check_results_key(self) -> None:
        """fact_check_node must return 'fact_check_results' in the state dict."""
        from app.agents.orchestrator import fact_check_node

        supported = _make_result("73%", verdict="SUPPORTED", url="https://ex.com/1")
        unverifiable = _make_result("$1B", verdict="UNVERIFIABLE")

        with (
            patch("app.agents.orchestrator.extract_claims",
                  new_callable=AsyncMock, return_value=[supported.claim, unverifiable.claim]),
            patch("app.agents.orchestrator.verify_claims",
                  new_callable=AsyncMock, return_value=[supported, unverifiable]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.fact_check_enabled = True
            result = await fact_check_node(_base_state())

        assert "fact_check_results" in result

    @pytest.mark.asyncio
    async def test_fact_check_node_results_include_all_verdicts(self) -> None:
        """fact_check_results must include both SUPPORTED and UNVERIFIABLE entries."""
        from app.agents.orchestrator import fact_check_node

        supported = _make_result("73%", verdict="SUPPORTED", url="https://ex.com/report")
        unverifiable = _make_result("$1B market", verdict="UNVERIFIABLE")

        with (
            patch("app.agents.orchestrator.extract_claims",
                  new_callable=AsyncMock, return_value=[supported.claim, unverifiable.claim]),
            patch("app.agents.orchestrator.verify_claims",
                  new_callable=AsyncMock, return_value=[supported, unverifiable]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.fact_check_enabled = True
            result = await fact_check_node(_base_state())

        results = result.get("fact_check_results", [])
        assert len(results) == 2
        verdicts = {r.verdict for r in results}
        assert "SUPPORTED" in verdicts
        assert "UNVERIFIABLE" in verdicts

    @pytest.mark.asyncio
    async def test_fact_check_node_disabled_returns_empty_results(self) -> None:
        """When fact_check_enabled=False, fact_check_results must be empty list."""
        from app.agents.orchestrator import fact_check_node

        with (
            patch("app.agents.orchestrator.settings") as s,
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
        ):
            s.fact_check_enabled = False
            result = await fact_check_node(_base_state())

        assert result.get("fact_check_results") == []

    @pytest.mark.asyncio
    async def test_fact_check_node_no_claims_returns_empty_results(self) -> None:
        """When no claims are extracted, fact_check_results must be empty list."""
        from app.agents.orchestrator import fact_check_node

        with (
            patch("app.agents.orchestrator.extract_claims",
                  new_callable=AsyncMock, return_value=[]),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.fact_check_enabled = True
            result = await fact_check_node(_base_state())

        assert result.get("fact_check_results") == []


# ── format_node re-injects hyperlinks ────────────────────────────────────────

class TestFormatNodeReInjectsHyperlinks:
    def _fake_format_result(self, content: str) -> Any:
        r = MagicMock()
        r.formatted_content = content
        r.pull_quote = "savings"
        r.changes_applied = []
        return r

    @pytest.mark.asyncio
    async def test_format_node_calls_inject_hyperlinks_with_results_from_state(self) -> None:
        """format_node must call inject_hyperlinks(content, fact_check_results) before format_post."""
        from app.agents.orchestrator import format_node

        result_73 = _make_result("73%", verdict="SUPPORTED", url="https://ex.com/source")
        state = _base_state(fact_check_results=[result_73])

        with (
            patch("app.agents.orchestrator.format_post",
                  new_callable=AsyncMock,
                  return_value=self._fake_format_result(state["post"].content)),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db") as mock_get_db,
            patch("app.agents.orchestrator.inject_hyperlinks") as mock_inject,
        ):
            mock_inject.side_effect = lambda content, results: content
            mock_db = MagicMock()
            mock_db.posts.update_one = AsyncMock()
            mock_get_db.return_value = mock_db

            await format_node(state)

        mock_inject.assert_called_once()
        _, results_arg = mock_inject.call_args[0]
        assert results_arg == [result_73]

    @pytest.mark.asyncio
    async def test_format_node_hyperlink_present_in_content_passed_to_format_post(self) -> None:
        """The content reaching format_post must contain the injected hyperlink URL."""
        from app.agents.orchestrator import format_node

        result_73 = _make_result("73%", verdict="SUPPORTED", url="https://deepseek.com/report")
        captured_content: list[str] = []

        async def fake_format_post(run_id: str, title: str, content: str) -> Any:
            captured_content.append(content)
            return self._fake_format_result(content)

        state = _base_state(fact_check_results=[result_73])

        with (
            patch("app.agents.orchestrator.format_post", side_effect=fake_format_post),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db") as mock_get_db,
        ):
            mock_db = MagicMock()
            mock_db.posts.update_one = AsyncMock()
            mock_get_db.return_value = mock_db

            await format_node(state)

        assert captured_content, "format_post was never called"
        assert "https://deepseek.com/report" in captured_content[0]
        assert "[73%]" in captured_content[0]

    @pytest.mark.asyncio
    async def test_format_node_skips_claims_no_longer_in_final_content(self) -> None:
        """Claims rewritten by the reviser must be silently skipped — not an error."""
        from app.agents.orchestrator import format_node

        result_gone = _make_result("3x faster", verdict="SUPPORTED", url="https://ex.com/bench")
        captured_content: list[str] = []

        async def fake_format_post(run_id: str, title: str, content: str) -> Any:
            captured_content.append(content)
            return self._fake_format_result(content)

        # Final content doesn't have "3x faster" — reviser rewrote it
        final_content = "We reduced costs significantly. Latency improved."
        state = _base_state(fact_check_results=[result_gone], content=final_content)

        with (
            patch("app.agents.orchestrator.format_post", side_effect=fake_format_post),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db") as mock_get_db,
        ):
            mock_db = MagicMock()
            mock_db.posts.update_one = AsyncMock()
            mock_get_db.return_value = mock_db

            await format_node(state)

        assert captured_content
        assert "https://ex.com/bench" not in captured_content[0]

    @pytest.mark.asyncio
    async def test_format_node_empty_results_runs_unchanged(self) -> None:
        """Empty fact_check_results must not break format_node."""
        from app.agents.orchestrator import format_node

        captured_content: list[str] = []

        async def fake_format_post(run_id: str, title: str, content: str) -> Any:
            captured_content.append(content)
            return self._fake_format_result(content)

        state = _base_state(fact_check_results=[])

        with (
            patch("app.agents.orchestrator.format_post", side_effect=fake_format_post),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db") as mock_get_db,
        ):
            mock_db = MagicMock()
            mock_db.posts.update_one = AsyncMock()
            mock_get_db.return_value = mock_db

            result = await format_node(state)

        assert "errors" not in result or result.get("errors") == []
        assert captured_content

    @pytest.mark.asyncio
    async def test_format_node_does_not_inject_unverifiable_hyperlinks(self) -> None:
        """UNVERIFIABLE results must not add any hyperlink to the final content."""
        from app.agents.orchestrator import format_node

        unverifiable = _make_result("$1B market", verdict="UNVERIFIABLE")
        captured_content: list[str] = []

        async def fake_format_post(run_id: str, title: str, content: str) -> Any:
            captured_content.append(content)
            return self._fake_format_result(content)

        state = _base_state(
            fact_check_results=[unverifiable],
            content="The $1B market is growing fast.",
        )

        with (
            patch("app.agents.orchestrator.format_post", side_effect=fake_format_post),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator.get_db") as mock_get_db,
        ):
            mock_db = MagicMock()
            mock_db.posts.update_one = AsyncMock()
            mock_get_db.return_value = mock_db

            await format_node(state)

        assert captured_content
        # No markdown hyperlink syntax should be injected for unverifiable claims
        assert "](http" not in captured_content[0]
