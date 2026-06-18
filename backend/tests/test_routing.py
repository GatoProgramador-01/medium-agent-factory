"""
Unit tests for route_after_quality — pure routing function, no LLM calls.
"""

from unittest.mock import patch

from app.agents.orchestrator import route_after_quality
from app.models.post import QualityReport


def _make_report(score: float, read_ratio: float = 0.75, word_count: int = 1200) -> QualityReport:
    return QualityReport(
        score=score,
        read_ratio_prediction=read_ratio,
        medium_boost_eligible=score >= 0.9,
        issues=[],
        strengths=[],
        revision_prompt="",
        word_count=word_count,
    )


def _state(
    score: float | None = None,
    revisions: int = 0,
    read_ratio: float = 0.75,
    word_count: int = 1200,
) -> dict:
    return {
        "run_id": "test-run",
        "custom_topic": "test",
        "series_context": "",
        "post": None,
        "quality_report": (
            _make_report(score, read_ratio=read_ratio, word_count=word_count)
            if score is not None
            else None
        ),
        "revision_count": revisions,
        "errors": [],
        "completed_steps": [],
    }


class TestRouteAfterQuality:
    def test_no_report_goes_to_finalize(self) -> None:
        assert route_after_quality(_state(score=None)) == "finalize"

    def _settings(self, s: object, min_score: float = 0.90, max_rev: int = 3) -> None:
        s.min_quality_score = min_score  # type: ignore[attr-defined]
        s.min_read_ratio = 0.65  # type: ignore[attr-defined]
        s.block_high_ai_patterns = True  # type: ignore[attr-defined]
        s.min_word_count = 1000  # type: ignore[attr-defined]
        s.max_revision_cycles = max_rev  # type: ignore[attr-defined]

    def test_score_above_threshold_goes_to_finalize(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            self._settings(s)
            assert route_after_quality(_state(score=0.92)) == "finalize"
            assert route_after_quality(_state(score=0.90)) == "finalize"

    def test_score_below_threshold_goes_to_revision(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            self._settings(s)
            assert route_after_quality(_state(score=0.80, revisions=0)) == "revision"
            assert route_after_quality(_state(score=0.89, revisions=2)) == "revision"

    def test_max_revisions_reached_forces_finalize(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            self._settings(s)
            # Even with a low score, if revisions >= max, finalize
            assert route_after_quality(_state(score=0.70, revisions=3)) == "finalize"
            assert route_after_quality(_state(score=0.70, revisions=4)) == "finalize"

    def test_exactly_at_max_revisions_forces_finalize(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            self._settings(s)
            assert route_after_quality(_state(score=0.75, revisions=3)) == "finalize"

    def test_one_below_max_still_revises(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            self._settings(s)
            assert route_after_quality(_state(score=0.75, revisions=2)) == "revision"
