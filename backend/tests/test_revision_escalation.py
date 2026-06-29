"""Tests for smart revision model escalation in _pick_role."""

import pytest

from app.agents.content_generator import _pick_role


class TestRevisionEscalation:
    def test_revision_0_with_low_score_uses_worker(self) -> None:
        assert _pick_role(revision_number=0, score=0.50) == "worker"

    def test_revision_0_close_to_passing_escalates_to_supervisor(self) -> None:
        # 0.67 is within 0.06 of 0.70
        assert _pick_role(revision_number=0, score=0.67) == "supervisor"

    def test_revision_0_exactly_at_boundary_escalates(self) -> None:
        # 0.64 is exactly 0.06 below 0.70
        assert _pick_role(revision_number=0, score=0.64) == "supervisor"

    def test_revision_0_far_below_uses_worker(self) -> None:
        # 0.50 is well below 0.70 - use cheap model first
        assert _pick_role(revision_number=0, score=0.50) == "worker"

    def test_revision_1_far_below_uses_worker(self) -> None:
        assert _pick_role(revision_number=1, score=0.50) == "worker"

    def test_revision_2_always_supervisor(self) -> None:
        assert _pick_role(revision_number=2, score=0.40) == "supervisor"

    def test_revision_3_always_supervisor(self) -> None:
        assert _pick_role(revision_number=3, score=0.80) == "supervisor"

    def test_high_ai_pattern_escalates_on_revision_0(self) -> None:
        assert (
            _pick_role(revision_number=0, score=0.40, has_high_ai_pattern=True)
            == "supervisor"
        )

    def test_high_ai_pattern_escalates_on_revision_1(self) -> None:
        assert (
            _pick_role(revision_number=1, score=0.40, has_high_ai_pattern=True)
            == "supervisor"
        )

    def test_no_score_and_revision_0_uses_worker(self) -> None:
        assert _pick_role(revision_number=0, score=None) == "worker"

    def test_no_score_revision_2_uses_supervisor(self) -> None:
        assert _pick_role(revision_number=2, score=None) == "supervisor"

    def test_custom_min_score_escalates_when_close(self) -> None:
        # With min_score=0.80, score=0.75 is within 0.06 → escalate
        assert _pick_role(revision_number=0, score=0.75, min_score=0.80) == "supervisor"

    def test_custom_min_score_uses_worker_when_far(self) -> None:
        # With min_score=0.80, score=0.50 is far below → worker
        assert (
            _pick_role(revision_number=0, score=0.50, min_score=0.80) == "worker"
        )
