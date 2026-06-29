"""
Unit tests for _compute_publication_recommendation in orchestrator.

Tests the publication recommendation logic that determines whether a post should
be recommended for publication based on quality gates and revision history.

The function returns a tuple[bool, float] where:
  - bool: True if all hard gates pass, False otherwise
  - float: confidence score 0.0-1.0 (capped at 0.70 if revisions exhausted)
"""

from unittest.mock import MagicMock, patch

from app.models.post import QualityIssue, QualityReport, VerificationResult, AtomicClaim


def _make_quality_report(
    score: float = 0.85,
    read_ratio_prediction: float = 0.75,
    **overrides,
) -> QualityReport:
    """Helper to construct a QualityReport with sensible defaults."""
    base = {
        "score": score,
        "read_ratio_prediction": read_ratio_prediction,
        "medium_boost_eligible": True,
        "issues": [],
        "strengths": ["good hook", "clear voice"],
        "revision_prompt": "Improve specificity",
        "word_count": 1500,
    }
    return QualityReport(**{**base, **overrides})


_UNSET = object()


def _make_state(
    errors: list[str] | None = None,
    quality_report: object = _UNSET,
    structural_check_issues: list[dict] | None = None,
    fact_check_results: list[dict] | None = None,
    fact_check_issues: list[dict] | None = None,
    revision_count: int = 0,
    **extra,
) -> dict:
    """Helper to construct a pipeline state dict with defaults."""
    state = {
        "errors": errors or [],
        "quality_report": _make_quality_report() if quality_report is _UNSET else quality_report,
        "structural_check_issues": structural_check_issues or [],
        "fact_check_results": fact_check_results or [],
        "fact_check_issues": fact_check_issues or [],
        "revision_count": revision_count,
    }
    state.update(extra)
    return state


class TestPublicationRecommendation:
    """Tests for _compute_publication_recommendation."""

    def test_returns_false_when_errors_present(self) -> None:
        """Non-empty errors list triggers early return (False, 0.0)."""
        from app.agents.orchestrator import _compute_publication_recommendation

        state = _make_state(errors=["Network timeout", "API error"])
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_returns_false_when_quality_report_none(self) -> None:
        """quality_report=None triggers early return (False, 0.0)."""
        from app.agents.orchestrator import _compute_publication_recommendation

        state = _make_state(quality_report=None)
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_all_gates_pass_returns_true(self) -> None:
        """Happy path: all gates pass returns (True, confidence > 0)."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report(score=0.85, read_ratio_prediction=0.75)
        state = _make_state(
            quality_report=qr,
            structural_check_issues=[],
            fact_check_results=[],
            revision_count=0,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is True
        assert 0.0 < confidence <= 1.0

    def test_quality_score_below_min_blocks(self) -> None:
        """Quality score below min_quality_score threshold blocks publication."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report(score=0.65)  # below default 0.70
        state = _make_state(quality_report=qr)
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_structural_high_issue_blocks(self) -> None:
        """HIGH severity structural issue (non-word_count) blocks publication."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        structural_issues = [
            {
                "severity": "HIGH",
                "category": "readability",
                "location": "paragraph 2",
                "suggestion": "Break up long sentence",
            }
        ]
        state = _make_state(
            quality_report=qr,
            structural_check_issues=structural_issues,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_structural_word_count_issue_does_not_block(self) -> None:
        """HIGH word_count issue is an exception — does NOT block."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        structural_issues = [
            {
                "severity": "HIGH",
                "category": "word_count",
                "location": "overall",
                "suggestion": "Expand to 1500+ words",
            }
        ]
        state = _make_state(
            quality_report=qr,
            structural_check_issues=structural_issues,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is True
        assert confidence > 0.0

    def test_read_ratio_below_min_blocks(self) -> None:
        """read_ratio_prediction below min_read_ratio blocks publication."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report(read_ratio_prediction=0.60)  # below default 0.65
        state = _make_state(quality_report=qr)
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_fact_check_high_blocks_when_results_present(self) -> None:
        """HIGH severity fact-check issue blocks if fact_check_results is non-empty."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        fact_issues = [{"severity": "HIGH", "verdict": "UNVERIFIABLE"}]
        fact_results = [
            {
                "claim": {"text": "90% of X", "claim_type": "statistic"},
                "verdict": "UNVERIFIABLE",
            }
        ]
        state = _make_state(
            quality_report=qr,
            fact_check_issues=fact_issues,
            fact_check_results=fact_results,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_fact_check_gate_skipped_when_no_results(self) -> None:
        """HIGH fact issue but empty fact_check_results → does NOT block."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        fact_issues = [{"severity": "HIGH", "verdict": "UNVERIFIABLE"}]
        state = _make_state(
            quality_report=qr,
            fact_check_issues=fact_issues,
            fact_check_results=[],  # empty = skip the gate
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is True
        assert confidence > 0.0

    def test_confidence_capped_at_0_70_when_max_revisions(self) -> None:
        """When revision_count == max_revision_cycles, cap confidence at 0.70."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report(score=0.95, read_ratio_prediction=0.95)
        with patch("app.agents.orchestrator.settings") as mock_settings:
            mock_settings.min_quality_score = 0.70
            mock_settings.min_read_ratio = 0.65
            mock_settings.max_revision_cycles = 6
            state = _make_state(
                quality_report=qr,
                revision_count=6,  # exhausted
            )
            recommended, confidence = _compute_publication_recommendation(state)
            assert recommended is True
            assert confidence <= 0.70

    def test_confidence_formula_weighted_correctly(self) -> None:
        """Verify confidence = score*0.5 + read*0.3 + rev_term*0.2."""
        from app.agents.orchestrator import _compute_publication_recommendation

        quality_score = 0.80
        read_ratio = 0.70
        revision_count = 2
        max_revision_cycles = 6

        qr = _make_quality_report(
            score=quality_score,
            read_ratio_prediction=read_ratio,
        )
        with patch("app.agents.orchestrator.settings") as mock_settings:
            mock_settings.min_quality_score = 0.70
            mock_settings.min_read_ratio = 0.65
            mock_settings.max_revision_cycles = max_revision_cycles
            state = _make_state(
                quality_report=qr,
                revision_count=revision_count,
            )
            recommended, confidence = _compute_publication_recommendation(state)

            # Expected calculation:
            # revision_term = max(0.0, 1.0 - (2 / 6)) = 0.6667
            # confidence = 0.80*0.5 + 0.70*0.3 + 0.6667*0.2
            #           = 0.40 + 0.21 + 0.1333 = 0.7433
            revision_term = max(0.0, 1.0 - (revision_count / max_revision_cycles))
            expected_confidence = (
                quality_score * 0.5 + read_ratio * 0.3 + revision_term * 0.2
            )

            assert recommended is True
            assert abs(confidence - expected_confidence) < 0.001  # float precision

    def test_multiple_structural_high_issues_block(self) -> None:
        """Multiple HIGH structural issues (non-word_count) block publication."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        structural_issues = [
            {
                "severity": "HIGH",
                "category": "readability",
                "location": "paragraph 2",
                "suggestion": "Break up long sentence",
            },
            {
                "severity": "HIGH",
                "category": "formatting",
                "location": "section 1",
                "suggestion": "Add more whitespace",
            },
        ]
        state = _make_state(
            quality_report=qr,
            structural_check_issues=structural_issues,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0

    def test_medium_severity_structural_issues_do_not_block(self) -> None:
        """MEDIUM or LOW severity structural issues do NOT block."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report()
        structural_issues = [
            {
                "severity": "MEDIUM",
                "category": "readability",
                "location": "paragraph 2",
                "suggestion": "Consider shortening",
            },
            {
                "severity": "LOW",
                "category": "formatting",
                "location": "paragraph 5",
                "suggestion": "Improve spacing",
            },
        ]
        state = _make_state(
            quality_report=qr,
            structural_check_issues=structural_issues,
        )
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is True
        assert confidence > 0.0

    def test_confidence_zero_when_recommendation_false(self) -> None:
        """When recommended=False, confidence is always 0.0."""
        from app.agents.orchestrator import _compute_publication_recommendation

        qr = _make_quality_report(score=0.60)  # below min
        state = _make_state(quality_report=qr)
        recommended, confidence = _compute_publication_recommendation(state)
        assert recommended is False
        assert confidence == 0.0
