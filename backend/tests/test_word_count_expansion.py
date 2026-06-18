"""
Sprint 7.2 — Word count floor fix.

Problem: When ONLY Gate 4 (word count) fails and content score is 1.0,
the reviser makes diminishing additions (88 words → 50 → 30 → 20) because
"add ~88 words" gives no structural guidance. After 6 cycles the post is
force-finalized below 1,300 words.

Fix: content_revision_node detects "word count only" failure and injects a
MANDATORY EXPANSION PROTOCOL into the revision_prompt before calling revise_post.
The protocol mandates structural additions (sub-sections, tables, case studies)
with a 150-word buffer target — not incremental padding.

Tests verify:
  1. Word-count-only failure → expansion protocol injected into revision_prompt arg
  2. Mixed failures (word count + other) → no expansion protocol
  3. No word count failure → no expansion protocol
  4. Expansion protocol includes concrete structural directives
  5. Expansion protocol includes the numerical deficit and buffer target
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.post import QualityIssue, QualityReport, ReadRatioFactor


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_report(
    score: float = 1.0,
    word_count: int = 1212,
    read_ratio: float = 0.75,
    ai_issues: list[QualityIssue] | None = None,
) -> QualityReport:
    return QualityReport(
        score=score,
        read_ratio_prediction=read_ratio,
        medium_boost_eligible=score >= 0.9,
        issues=ai_issues or [],
        strengths=["Strong hook"],
        revision_prompt="Original LLM revision instructions.",
        word_count=word_count,
        read_ratio_factors=[],
        read_ratio_hook_score=0.9,
        hook_strength=1.0,
        specificity_score=1.0,
        voice_authenticity=1.0,
        insight_value=1.0,
    )


def _make_post() -> Any:
    post = MagicMock()
    post.title = "Why DeepSeek Cost 15% More Than Expected"
    post.content = "Content here. " * 85  # ~1,190 words
    post.tags = []
    return post


def _base_state(report: QualityReport, revision_count: int = 2) -> dict[str, Any]:
    return {
        "run_id": "test-wc-expansion",
        "custom_topic": "DeepSeek costs",
        "series_id": None,
        "series_context": "",
        "series_position": None,
        "trend_context": "",
        "post": _make_post(),
        "quality_report": report,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": revision_count,
        "quality_history": [
            {"cycle": 0, "score": 1.0, "gate_failures": ["word count 1151 below minimum 1300"], "issue_categories": []},
            {"cycle": 1, "score": 1.0, "gate_failures": ["word count 1192 below minimum 1300"], "issue_categories": []},
        ],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
    }


# ── Expansion protocol injection ──────────────────────────────────────────────

class TestWordCountOnlyExpansionProtocol:
    def _capture_revision_prompt(self) -> list[str]:
        captured: list[str] = []

        async def fake_revise_post(**kwargs: Any) -> Any:
            captured.append(kwargs.get("revision_prompt", ""))
            post = MagicMock()
            post.title = "Revised Title"
            post.content = "Revised content. " * 100
            post.tags = []
            return post

        return captured, fake_revise_post

    @pytest.mark.asyncio
    async def test_word_count_only_injects_expansion_protocol(self) -> None:
        """When only word count fails, expansion protocol must be prepended to revision_prompt."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        assert captured, "revise_post was not called"
        prompt = captured[0]
        assert "EXPANSION PROTOCOL" in prompt or "expansion" in prompt.lower(), (
            "Expansion protocol must be injected when only word count fails"
        )

    @pytest.mark.asyncio
    async def test_expansion_protocol_contains_structural_directive(self) -> None:
        """Expansion protocol must mandate structural additions, not padding."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        # Must instruct adding substance — sections, examples, tables
        has_structural_guidance = any(
            kw in prompt.lower()
            for kw in ["section", "example", "table", "case study", "sub-section", "numbered"]
        )
        assert has_structural_guidance, (
            f"Expansion protocol must mandate structural additions. Got:\n{prompt[:500]}"
        )

    @pytest.mark.asyncio
    async def test_expansion_protocol_includes_deficit_and_buffer_target(self) -> None:
        """Protocol must show exact deficit and a buffer target above the minimum."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        # deficit = 1300 - 1212 = 88; buffer target should be > 1300
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        assert "88" in prompt or "1,212" in prompt or "1212" in prompt, (
            "Protocol must include current word count or deficit"
        )
        # Buffer target: 1300 + some buffer (e.g. 150) = 1450
        has_buffer = any(str(t) in prompt for t in range(1350, 1600))
        assert has_buffer, "Protocol must set a buffer target above 1,300"

    @pytest.mark.asyncio
    async def test_expansion_protocol_warns_against_small_increments(self) -> None:
        """Protocol must warn the reviser not to make tiny additions cycle after cycle."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        has_warning = any(
            kw in prompt.lower()
            for kw in ["small", "padding", "filler", "incremental", "one big", "single addition"]
        )
        assert has_warning, "Protocol must warn against incremental padding"

    @pytest.mark.asyncio
    async def test_mixed_failures_do_not_inject_expansion_protocol(self) -> None:
        """When word count AND other gates fail, no expansion protocol — normal revision."""
        from app.agents.orchestrator import content_revision_node

        # Low score (fails Gate 1) + low word count (fails Gate 4)
        report = _make_report(score=0.55, word_count=1100, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        assert "EXPANSION PROTOCOL" not in prompt, (
            "Must not inject expansion protocol when other gates also fail"
        )

    @pytest.mark.asyncio
    async def test_score_only_failure_does_not_inject_expansion_protocol(self) -> None:
        """When only score fails (word count is fine), no expansion protocol."""
        from app.agents.orchestrator import content_revision_node

        # Score fails, word count passes
        report = _make_report(score=0.55, word_count=1400, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        assert "EXPANSION PROTOCOL" not in prompt

    @pytest.mark.asyncio
    async def test_original_revision_prompt_preserved_in_expansion(self) -> None:
        """The original LLM revision_prompt must still be present alongside the protocol."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        captured, fake_revise = self._capture_revision_prompt()

        with (
            patch("app.agents.orchestrator.revise_post", side_effect=fake_revise),
            patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
            patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
            patch("app.agents.orchestrator.settings") as s,
        ):
            s.min_quality_score = 0.70
            s.min_read_ratio = 0.65
            s.block_high_ai_patterns = True
            s.min_word_count = 1300
            s.max_revision_cycles = 6
            s.worker_model = "deepseek-chat"

            await content_revision_node(_base_state(report))

        prompt = captured[0]
        assert "Original LLM revision instructions." in prompt, (
            "Original revision_prompt must be preserved alongside the expansion protocol"
        )
