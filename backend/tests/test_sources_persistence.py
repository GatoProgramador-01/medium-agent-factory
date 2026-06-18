"""
Sprint 8 — Sources persistence.

Problem: fact_check_results (VerificationResult list) live only in LangGraph
state and are discarded after the run. The posts MongoDB document never gets
the verified source URLs, so the frontend has nothing to show.

Fix: finalize_node saves a 'verified_sources' list to the posts collection
containing only SUPPORTED claims with a source_url.

Tests verify:
  1. finalize_node writes 'verified_sources' to the posts document
  2. Only SUPPORTED results are included (UNVERIFIABLE are excluded)
  3. Each entry has claim_text, source_url, source_title, claim_type
  4. Empty fact_check_results → 'verified_sources' not written (or empty list)
  5. finalize_node also writes quality_score, read_ratio_prediction, medium_boost_eligible
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.post import AtomicClaim, QualityIssue, QualityReport, ReadRatioFactor, VerificationResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_report(score: float = 1.0, word_count: int = 1400) -> QualityReport:
    return QualityReport(
        score=score,
        read_ratio_prediction=0.78,
        medium_boost_eligible=score >= 0.9,
        issues=[],
        strengths=["Strong hook"],
        revision_prompt="No revision needed.",
        word_count=word_count,
        read_ratio_factors=[],
        read_ratio_hook_score=0.9,
        hook_strength=1.0,
        specificity_score=1.0,
        voice_authenticity=1.0,
        insight_value=1.0,
    )


def _make_result(
    text: str,
    verdict: str = "SUPPORTED",
    url: str | None = "https://example.com/source",
    title: str | None = "Example Source",
    claim_type: str = "percentage",
) -> VerificationResult:
    return VerificationResult(
        claim=AtomicClaim(
            text=text,
            claim_type=claim_type,
            search_query=f"search {text}",
            location="paragraph 1",
        ),
        verdict=verdict,
        source_url=url if verdict == "SUPPORTED" else None,
        source_title=title if verdict == "SUPPORTED" else None,
    )


def _base_state(
    fact_check_results: list[VerificationResult] | None = None,
    report: QualityReport | None = None,
) -> dict[str, Any]:
    post = MagicMock()
    post.title = "DeepSeek Cost Analysis"
    post.content = "Content " * 200
    post.tags = ["ai", "cost"]
    post.image_suggestions = []
    post.subtitle = "A deep dive"

    return {
        "run_id": "test-sources-persist",
        "custom_topic": "DeepSeek costs",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "post": post,
        "quality_report": report or _make_report(),
        "pull_quote": "Key insight here.",
        "format_changes": ["split long paragraph"],
        "revision_count": 1,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": fact_check_results if fact_check_results is not None else [],
        "errors": [],
        "completed_steps": ["formatted"],
    }


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestSourcesPersistence:
    @pytest.mark.asyncio
    async def test_finalize_writes_verified_sources(self) -> None:
        """finalize_node must write 'verified_sources' to the posts document."""
        from app.agents.orchestrator import finalize_node

        supported = _make_result("73%", verdict="SUPPORTED", url="https://ex.com/1")
        state = _base_state(fact_check_results=[supported])

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        assert written, "update_one was never called"
        assert "verified_sources" in written[0], (
            "'verified_sources' must be written to the posts document"
        )

    @pytest.mark.asyncio
    async def test_only_supported_claims_are_saved(self) -> None:
        """UNVERIFIABLE results must not appear in verified_sources."""
        from app.agents.orchestrator import finalize_node

        supported = _make_result("73%", verdict="SUPPORTED", url="https://ex.com/1")
        unverifiable = _make_result("$1B", verdict="UNVERIFIABLE")
        state = _base_state(fact_check_results=[supported, unverifiable])

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        sources = written[0].get("verified_sources", [])
        assert len(sources) == 1, f"Expected 1 source (SUPPORTED only), got {len(sources)}"
        assert sources[0]["claim_text"] == "73%"

    @pytest.mark.asyncio
    async def test_verified_source_has_required_fields(self) -> None:
        """Each verified_source entry must have claim_text, source_url, source_title, claim_type."""
        from app.agents.orchestrator import finalize_node

        supported = _make_result(
            "73% reduction",
            verdict="SUPPORTED",
            url="https://deepseek.com/report",
            title="DeepSeek Cost Report",
            claim_type="percentage",
        )
        state = _base_state(fact_check_results=[supported])

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        source = written[0]["verified_sources"][0]
        assert source["claim_text"] == "73% reduction"
        assert source["source_url"] == "https://deepseek.com/report"
        assert source["source_title"] == "DeepSeek Cost Report"
        assert source["claim_type"] == "percentage"

    @pytest.mark.asyncio
    async def test_empty_fact_check_results_writes_empty_sources(self) -> None:
        """When there are no verified claims, verified_sources should be [] or absent."""
        from app.agents.orchestrator import finalize_node

        state = _base_state(fact_check_results=[])
        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        # Either not present or empty list — both are acceptable
        sources = written[0].get("verified_sources", [])
        assert sources == [], f"Expected empty list, got {sources}"

    @pytest.mark.asyncio
    async def test_finalize_writes_quality_score(self) -> None:
        """finalize_node must persist quality_score, read_ratio_prediction, medium_boost_eligible."""
        from app.agents.orchestrator import finalize_node

        report = _make_report(score=0.97, word_count=1450)
        state = _base_state(report=report)

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        doc = written[0]
        assert doc.get("quality_score") == pytest.approx(0.97)
        assert doc.get("read_ratio_prediction") == pytest.approx(0.78)
        assert doc.get("medium_boost_eligible") is True


class TestQualityReportPersistence:
    @pytest.mark.asyncio
    async def test_finalize_writes_quality_report_subdocument(self) -> None:
        """finalize_node must write a 'quality_report' sub-document for QualityPanel."""
        from app.agents.orchestrator import finalize_node

        report = _make_report(score=0.92, word_count=1500)
        report.issues = [
            QualityIssue(
                category="readability",
                severity="low",
                location="paragraph 3",
                suggestion="Shorten.",
            )
        ]
        report.strengths = ["Great hook"]
        state = _base_state(report=report)

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        assert written, "update_one was never called"
        qr = written[0].get("quality_report")
        assert qr is not None, "'quality_report' sub-document must be written to posts"
        assert qr["score"] == pytest.approx(0.92)
        assert qr["read_ratio_prediction"] == pytest.approx(0.78)
        assert qr["medium_boost_eligible"] is True
        assert qr["issues"][0]["category"] == "readability"
        assert qr["strengths"] == ["Great hook"]

    @pytest.mark.asyncio
    async def test_quality_report_subdocument_has_required_shape(self) -> None:
        """quality_report sub-document must have score, issues, strengths, read_ratio_prediction, medium_boost_eligible."""
        from app.agents.orchestrator import finalize_node

        report = _make_report(score=0.85, word_count=1350)
        state = _base_state(report=report)

        written: list[dict[str, Any]] = []

        async def fake_update_one(filter: Any, update: Any, **kw: Any) -> None:
            written.append(update.get("$set", {}))

        mock_db = MagicMock()
        mock_db.posts.update_one = fake_update_one
        mock_db.quality_snapshots.insert_one = AsyncMock()

        with (
            patch("app.agents.orchestrator.get_db", return_value=mock_db),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._update_pipeline_run", new_callable=AsyncMock),
            patch("app.agents.orchestrator.save_exemplar", new_callable=AsyncMock),
        ):
            await finalize_node(state)

        qr = written[0].get("quality_report", {})
        for key in ("score", "read_ratio_prediction", "medium_boost_eligible", "issues", "strengths"):
            assert key in qr, f"quality_report missing required key: '{key}'"
