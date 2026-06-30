"""
Tests for quality_analysis_node — verifies that structural_check_issues accumulated
by upstream nodes (ai_slop_detector, truth_enforcer, human_voice_scorer) are correctly
merged into the quality report's issue list.

These are unit tests that mock the LLM-backed quality analysis so they run without
network access. Only the structural-merge path in quality_analysis_node is under test.
"""

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

@dataclass
class _FakePost:
    """Minimal GeneratedPost stand-in."""
    title: str = "Test Title"
    content: str = "This is a clean article with enough content to analyze properly."
    subtitle: str = ""
    tags: list = field(default_factory=list)
    image_suggestions: list = field(default_factory=list)


def _make_fake_quality_report():
    """Return a minimal QualityReport populated with safe defaults."""
    from app.models.post import QualityReport
    return QualityReport(
        score=0.80,
        hook_strength=0.80,
        specificity_score=0.80,
        voice_authenticity=0.80,
        insight_value=0.80,
        issues=[],
        strengths=["Good hook"],
        revision_prompt="",
        read_ratio_prediction=0.55,
        read_ratio_hook_score=0.80,
        read_ratio_factors=[],
        word_count=1200,
        medium_boost_eligible=True,
    )


def _make_base_state(**overrides: Any) -> dict:
    """Build a minimal pipeline state dict."""
    state: dict[str, Any] = {
        "run_id": "test-merge-run",
        "post": _FakePost(),
        "revision_count": 0,
        "fact_check_issues": [],
        "structural_check_issues": [],
    }
    state.update(overrides)
    return state


class _FakeSettings:
    min_quality_score = 0.70
    min_read_ratio = 0.40
    block_high_ai_patterns = True
    block_unattributed_numbers = True
    min_word_count = 800


def _build_orchestrator_patches(fake_report):
    """Return dict of patch targets and their mocks.

    quality_analysis.py does local imports from app.agents.orchestrator, so
    we patch at the orchestrator module level — that is what the function
    will find when it executes the deferred import inside the function body.
    """
    fake_db = MagicMock()
    fake_db.posts.update_one = AsyncMock(return_value=None)
    fake_db.quality_snapshots.insert_one = AsyncMock(return_value=None)

    return {
        "app.agents.orchestrator.log_step": AsyncMock(return_value=None),
        "app.agents.orchestrator.run_quality_analysis": AsyncMock(
            return_value=fake_report
        ),
        "app.agents.orchestrator.run_structural_checks": MagicMock(return_value=[]),
        "app.agents.orchestrator.settings": _FakeSettings(),
        "app.agents.orchestrator.get_db": MagicMock(return_value=fake_db),
    }


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestQualityAnalysisNodeStructuralMerge:
    """Guards the dead-gate fix: state structural_check_issues must flow into
    the quality report so the gate can block AI slop, unattributed numbers, etc."""

    async def test_ai_slop_state_issue_appears_in_report(self) -> None:
        """When state has a structural_check_issues entry with category='ai_slop',
        the quality report includes a matching QualityIssue."""
        from app.agents.nodes.quality_analysis import quality_analysis_node

        fake_report = _make_fake_quality_report()
        patches = _build_orchestrator_patches(fake_report)

        state = _make_base_state(
            structural_check_issues=[
                {
                    "category": "ai_slop",
                    "severity": "HIGH",
                    "suggestion": "Remove forbidden buzzwords.",
                }
            ]
        )

        with (
            patch("app.agents.orchestrator.log_step", patches["app.agents.orchestrator.log_step"]),
            patch("app.agents.orchestrator.run_quality_analysis", patches["app.agents.orchestrator.run_quality_analysis"]),
            patch("app.agents.orchestrator.run_structural_checks", patches["app.agents.orchestrator.run_structural_checks"]),
            patch("app.agents.orchestrator.settings", patches["app.agents.orchestrator.settings"]),
            patch("app.agents.orchestrator.get_db", patches["app.agents.orchestrator.get_db"]),
        ):
            result = await quality_analysis_node(state)

        assert "quality_report" in result, "Node must return quality_report on success"
        report = result["quality_report"]

        ai_slop_issues = [i for i in report.issues if i.category == "ai_slop"]
        assert len(ai_slop_issues) >= 1, (
            "quality_report.issues must include the ai_slop entry from state "
            "structural_check_issues — dead gate detected if this fails"
        )

    async def test_unattributed_number_state_issue_appears_in_report(self) -> None:
        """When state has a structural_check_issues entry with category='unattributed_number'
        (from truth_enforcer_node), the quality report includes a matching QualityIssue."""
        from app.agents.nodes.quality_analysis import quality_analysis_node

        fake_report = _make_fake_quality_report()
        patches = _build_orchestrator_patches(fake_report)

        state = _make_base_state(
            structural_check_issues=[
                {
                    "category": "unattributed_number",
                    "severity": "HIGH",
                    "suggestion": "Numbers 42 lack attribution.",
                }
            ]
        )

        with (
            patch("app.agents.orchestrator.log_step", patches["app.agents.orchestrator.log_step"]),
            patch("app.agents.orchestrator.run_quality_analysis", patches["app.agents.orchestrator.run_quality_analysis"]),
            patch("app.agents.orchestrator.run_structural_checks", patches["app.agents.orchestrator.run_structural_checks"]),
            patch("app.agents.orchestrator.settings", patches["app.agents.orchestrator.settings"]),
            patch("app.agents.orchestrator.get_db", patches["app.agents.orchestrator.get_db"]),
        ):
            result = await quality_analysis_node(state)

        assert "quality_report" in result
        report = result["quality_report"]

        unattr_issues = [
            i for i in report.issues if i.category == "unattributed_number"
        ]
        assert len(unattr_issues) >= 1, (
            "quality_report.issues must include the unattributed_number entry from "
            "truth_enforcer_node via state structural_check_issues"
        )

    async def test_empty_structural_check_issues_does_not_crash(self) -> None:
        """When state.structural_check_issues is empty, the node succeeds and
        adds no extra issues (no crash, no phantom entries)."""
        from app.agents.nodes.quality_analysis import quality_analysis_node

        fake_report = _make_fake_quality_report()
        patches = _build_orchestrator_patches(fake_report)

        state = _make_base_state(structural_check_issues=[])

        with (
            patch("app.agents.orchestrator.log_step", patches["app.agents.orchestrator.log_step"]),
            patch("app.agents.orchestrator.run_quality_analysis", patches["app.agents.orchestrator.run_quality_analysis"]),
            patch("app.agents.orchestrator.run_structural_checks", patches["app.agents.orchestrator.run_structural_checks"]),
            patch("app.agents.orchestrator.settings", patches["app.agents.orchestrator.settings"]),
            patch("app.agents.orchestrator.get_db", patches["app.agents.orchestrator.get_db"]),
        ):
            result = await quality_analysis_node(state)

        assert "quality_report" in result
        report = result["quality_report"]

        # With no state issues AND no local structural issues (mocked to []),
        # report.issues should be empty (LLM report also starts with [])
        assert isinstance(report.issues, list)
        assert len(report.issues) == 0, (
            "Empty structural_check_issues must not inject phantom issues"
        )

    # ------------------------------------------------------------------
    # Gate-contract tests (Codex Finding 1 — unattributed_number blind spot)
    # ------------------------------------------------------------------

    def test_unattributed_number_blocks_gate(self) -> None:
        """_gate_check must return False when a HIGH unattributed_number issue is present.

        Before the fix, category='unattributed_number' did not start with 'ai_' so the
        ai_patterns gate skipped it entirely — truth-enforcement failures silently passed.
        """
        from app.agents.nodes.quality_analysis import _gate_check
        from app.models.post import QualityIssue, QualityReport

        class _Settings:
            min_quality_score = 0.70
            min_read_ratio = 0.40
            block_high_ai_patterns = True
            block_unattributed_numbers = True
            min_word_count = 800

        report = QualityReport(
            score=0.85,
            read_ratio_prediction=0.70,
            medium_boost_eligible=True,
            issues=[
                QualityIssue(
                    category="unattributed_number",
                    severity="high",
                    location="paragraph 2",
                    suggestion="Cite the source for '42%'.",
                )
            ],
            strengths=[],
            revision_prompt="",
            word_count=1400,
        )

        with patch("app.agents.orchestrator.settings", _Settings()):
            passed, failures = _gate_check(report)

        assert passed is False, (
            "_gate_check must return False for HIGH unattributed_number — "
            "truth-enforcement failures must block publication"
        )
        assert any("unattributed" in f for f in failures), (
            "Failure message must mention unattributed numbers"
        )

    def test_ai_slop_still_blocks_gate(self) -> None:
        """Regression: HIGH ai_slop issues must still block the gate after the fix."""
        from app.agents.nodes.quality_analysis import _gate_check
        from app.models.post import QualityIssue, QualityReport

        class _Settings:
            min_quality_score = 0.70
            min_read_ratio = 0.40
            block_high_ai_patterns = True
            block_unattributed_numbers = True
            min_word_count = 800

        report = QualityReport(
            score=0.85,
            read_ratio_prediction=0.70,
            medium_boost_eligible=True,
            issues=[
                QualityIssue(
                    category="ai_slop",
                    severity="high",
                    location="paragraph 1",
                    suggestion="Remove 'in the ever-evolving landscape of'.",
                )
            ],
            strengths=[],
            revision_prompt="",
            word_count=1400,
        )

        with patch("app.agents.orchestrator.settings", _Settings()):
            passed, failures = _gate_check(report)

        assert passed is False, (
            "HIGH ai_slop must still block the gate — regression check"
        )
        assert any("AI pattern" in f for f in failures), (
            "Failure message must mention AI patterns"
        )

    def test_clean_report_passes_gate(self) -> None:
        """A report with no HIGH issues and all metrics above thresholds must pass."""
        from app.agents.nodes.quality_analysis import _gate_check
        from app.models.post import QualityIssue, QualityReport

        class _Settings:
            min_quality_score = 0.70
            min_read_ratio = 0.40
            block_high_ai_patterns = True
            block_unattributed_numbers = True
            min_word_count = 800

        report = QualityReport(
            score=0.82,
            read_ratio_prediction=0.68,
            medium_boost_eligible=True,
            issues=[
                QualityIssue(
                    category="readability",
                    severity="low",
                    location="paragraph 3",
                    suggestion="Shorten this sentence.",
                )
            ],
            strengths=["Strong hook"],
            revision_prompt="",
            word_count=1500,
        )

        with patch("app.agents.orchestrator.settings", _Settings()):
            passed, failures = _gate_check(report)

        assert passed is True, (
            "A clean report with no HIGH issues and all metrics above thresholds must pass"
        )
        assert failures == [], f"Unexpected gate failures: {failures}"
