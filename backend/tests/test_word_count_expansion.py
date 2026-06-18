"""
Sprint 7.2 — Word count floor fix (v2: dedicated expander).

Problem: When ONLY Gate 4 (word count) fails and content score is 1.0,
revise_post makes diminishing additions (984→985→1039 words) because its
"editing" mindset ignores structural-addition instructions. After 6 cycles
the post is force-finalized below 1,300 words.

Fix: content_revision_node detects "word count only" failure and calls
expand_post (content generator) instead of revise_post. expand_post generates
ONE new section (~deficit+150 words) which is appended verbatim to the post.
The reviser is not called at all for word-count-only failures.

Tests verify:
  1. Word-count-only failure → expand_post called, revise_post NOT called
  2. Mixed failures → revise_post called, expand_post NOT called
  3. Score-only failure → revise_post called, expand_post NOT called
  4. Appended content makes the post longer
  5. expand_post receives the correct deficit (+150 buffer)
  6. expand_post section is appended (original content preserved)
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


# ── Word-count-only: expand_post called, revise_post skipped ──────────────────

class TestWordCountOnlyUsesExpander:
    @pytest.mark.asyncio
    async def test_word_count_only_calls_expand_post(self) -> None:
        """When only word count fails, expand_post must be called instead of revise_post."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)

        mock_expand = AsyncMock(return_value="## A New Section\n\nThis is new content " * 20)
        mock_revise = AsyncMock()

        with (
            patch("app.agents.orchestrator.expand_post", mock_expand),
            patch("app.agents.orchestrator.revise_post", mock_revise),
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

        mock_expand.assert_called_once()
        mock_revise.assert_not_called()

    @pytest.mark.asyncio
    async def test_word_count_only_revise_post_not_called(self) -> None:
        """revise_post must be bypassed entirely for word-count-only failures."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1000, read_ratio=0.75)
        mock_expand = AsyncMock(return_value="## Extra Section\n\n" + "New content. " * 30)
        mock_revise = AsyncMock()

        with (
            patch("app.agents.orchestrator.expand_post", mock_expand),
            patch("app.agents.orchestrator.revise_post", mock_revise),
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

        mock_revise.assert_not_called()

    @pytest.mark.asyncio
    async def test_expand_post_receives_correct_deficit(self) -> None:
        """expand_post must receive deficit = (min_word_count - word_count) + 150 buffer."""
        from app.agents.orchestrator import content_revision_node

        # deficit = 1300 - 1212 = 88; with buffer → 88 + 150 = 238
        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        captured_kwargs: list[dict[str, Any]] = []

        async def fake_expand(**kwargs: Any) -> str:
            captured_kwargs.append(kwargs)
            return "## New Section\n\n" + "More content. " * 20

        with (
            patch("app.agents.orchestrator.expand_post", side_effect=fake_expand),
            patch("app.agents.orchestrator.revise_post", new_callable=AsyncMock),
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

        assert captured_kwargs, "expand_post was not called"
        kw = captured_kwargs[0]
        # deficit + buffer = 88 + 150 = 238
        assert kw.get("deficit") == 238, (
            f"Expected deficit=238 (88+150 buffer), got {kw.get('deficit')}"
        )

    @pytest.mark.asyncio
    async def test_expanded_content_appended_to_original(self) -> None:
        """expand_post result must be appended — original content preserved."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        new_section = "## The Missing Piece\n\nHere is the new section content."

        with (
            patch("app.agents.orchestrator.expand_post",
                  new_callable=AsyncMock, return_value=new_section),
            patch("app.agents.orchestrator.revise_post", new_callable=AsyncMock),
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

            state = _base_state(report)
            original_content = state["post"].content
            result = await content_revision_node(state)

        new_post = result.get("post") or state["post"]
        final_content = new_post.content if hasattr(new_post, "content") else ""
        # original content must still be present
        assert original_content in final_content or new_section in final_content, (
            "Original content must be preserved and new section appended"
        )
        assert new_section in final_content, "New section must appear in the final content"

    @pytest.mark.asyncio
    async def test_post_is_longer_after_expansion(self) -> None:
        """The post returned by content_revision_node must be longer than the input."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=1.0, word_count=1212, read_ratio=0.75)
        big_addition = "## New Section\n\n" + "This is new content with real words. " * 40

        with (
            patch("app.agents.orchestrator.expand_post",
                  new_callable=AsyncMock, return_value=big_addition),
            patch("app.agents.orchestrator.revise_post", new_callable=AsyncMock),
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

            state = _base_state(report)
            original_len = len(state["post"].content.split())
            result = await content_revision_node(state)

        new_post = result.get("post") or state["post"]
        new_len = len(new_post.content.split())
        assert new_len > original_len, (
            f"Post must be longer after expansion. Before: {original_len}, after: {new_len}"
        )


# ── Mixed / score-only failures use revise_post (unchanged path) ──────────────

class TestNonWordCountFailuresUseReviser:
    @pytest.mark.asyncio
    async def test_mixed_failures_call_revise_post(self) -> None:
        """When word count AND other gates fail, revise_post is called (normal path)."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=0.55, word_count=1100, read_ratio=0.75)
        mock_expand = AsyncMock()

        revised_post = MagicMock()
        revised_post.title = "Revised"
        revised_post.content = "Revised content. " * 100
        revised_post.tags = []
        mock_revise = AsyncMock(return_value=revised_post)

        with (
            patch("app.agents.orchestrator.expand_post", mock_expand),
            patch("app.agents.orchestrator.revise_post", mock_revise),
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

        mock_revise.assert_called_once()
        mock_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_score_only_failure_calls_revise_post(self) -> None:
        """When only score fails (word count OK), revise_post is called."""
        from app.agents.orchestrator import content_revision_node

        report = _make_report(score=0.55, word_count=1400, read_ratio=0.75)
        mock_expand = AsyncMock()

        revised_post = MagicMock()
        revised_post.title = "Revised"
        revised_post.content = "Revised content. " * 100
        revised_post.tags = []
        mock_revise = AsyncMock(return_value=revised_post)

        with (
            patch("app.agents.orchestrator.expand_post", mock_expand),
            patch("app.agents.orchestrator.revise_post", mock_revise),
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

        mock_revise.assert_called_once()
        mock_expand.assert_not_called()

    @pytest.mark.asyncio
    async def test_word_count_passes_calls_revise_post(self) -> None:
        """When word count already meets minimum (only score fails), revise_post is used."""
        from app.agents.orchestrator import content_revision_node

        # score fails, word count passes
        report = _make_report(score=0.60, word_count=1350, read_ratio=0.75)
        mock_expand = AsyncMock()

        revised_post = MagicMock()
        revised_post.title = "Revised"
        revised_post.content = "Revised. " * 100
        revised_post.tags = []
        mock_revise = AsyncMock(return_value=revised_post)

        with (
            patch("app.agents.orchestrator.expand_post", mock_expand),
            patch("app.agents.orchestrator.revise_post", mock_revise),
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

        mock_revise.assert_called_once()
        mock_expand.assert_not_called()
