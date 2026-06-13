"""
Unit tests for route_after_quality — pure routing function, no LLM calls.
"""
from unittest.mock import patch

from app.agents.orchestrator import route_after_quality
from app.models.post import QualityIssue, QualityReport


def _make_report(score: float) -> QualityReport:
    return QualityReport(
        score=score,
        read_ratio_prediction=0.6,
        issues=[],
        strengths=[],
        revision_prompt="",
    )


def _state(score: float | None = None, revisions: int = 0) -> dict:
    return {
        "run_id": "test-run",
        "custom_topic": "test",
        "post": None,
        "quality_report": _make_report(score) if score is not None else None,
        "revision_count": revisions,
        "errors": [],
        "completed_steps": [],
    }


class TestRouteAfterQuality:
    def test_no_report_goes_to_finalize(self) -> None:
        assert route_after_quality(_state(score=None)) == "finalize"

    def test_score_above_threshold_goes_to_finalize(self) -> None:
        # Default min_quality_score is 0.75
        with patch("app.agents.orchestrator.settings") as s:
            s.min_quality_score = 0.75
            s.max_revision_cycles = 2
            assert route_after_quality(_state(score=0.80)) == "finalize"
            assert route_after_quality(_state(score=0.75)) == "finalize"

    def test_score_below_threshold_goes_to_revision(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            s.min_quality_score = 0.75
            s.max_revision_cycles = 2
            assert route_after_quality(_state(score=0.60, revisions=0)) == "revision"
            assert route_after_quality(_state(score=0.74, revisions=1)) == "revision"

    def test_max_revisions_reached_forces_finalize(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            s.min_quality_score = 0.75
            s.max_revision_cycles = 2
            # Even with a low score, if revisions >= max, finalize
            assert route_after_quality(_state(score=0.40, revisions=2)) == "finalize"
            assert route_after_quality(_state(score=0.40, revisions=3)) == "finalize"

    def test_exactly_at_max_revisions_forces_finalize(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            s.min_quality_score = 0.75
            s.max_revision_cycles = 2
            assert route_after_quality(_state(score=0.50, revisions=2)) == "finalize"

    def test_one_below_max_still_revises(self) -> None:
        with patch("app.agents.orchestrator.settings") as s:
            s.min_quality_score = 0.75
            s.max_revision_cycles = 2
            assert route_after_quality(_state(score=0.50, revisions=1)) == "revision"
