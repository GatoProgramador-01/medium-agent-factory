"""Unit tests for POST /pipeline/improve-prompts endpoint.

Tests the improvement loop: analyze quality_snapshots → run prompt_analyst → return suggestions.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.agents.prompt_analyst import ImprovementSuggestion, PromptAnalysisReport


class TestImprovePromptsEndpoint:
    """HTTP endpoint tests for POST /pipeline/improve-prompts."""

    def test_improve_prompts_calls_analyze_and_prompt_analyst(self) -> None:
        """Mock both analyze() and run_prompt_analysis(), POST /pipeline/improve-prompts, assert 200 with correct fields."""
        mock_analysis = {
            "run_count": 15,
            "regression_rate": 0.25,
            "top_issues": [
                {"issue": "Hyperlink retention", "count": 12}
            ],
            "gate_failure_types": {"word_count": 5, "read_ratio": 3},
        }

        mock_suggestions = [
            ImprovementSuggestion(
                file="content_generator_system.txt",
                section="Hyperlink Strategy",
                issue="Hyperlink retention below 80% in 12 of 15 runs",
                current_behavior="URLs stripped during revisions",
                suggested_change="Add explicit instruction: 'Preserve all source URLs exactly as written'",
                priority=1,
            ),
            ImprovementSuggestion(
                file="quality_analyzer_system.txt",
                section="Gate Thresholds",
                issue="Word count gate failing 5 times",
                current_behavior="Strict 800-1200 word range enforced",
                suggested_change="Relax to 750-1300 word range for flexibility",
                priority=2,
            ),
        ]

        mock_report = PromptAnalysisReport(
            run_count=15,
            top_issue="Hyperlink retention below threshold",
            regression_rate=0.25,
            summary="Hyperlinks are the primary blocker. Revise content_generator to preserve URLs explicitly.",
            suggestions=mock_suggestions,
        )

        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze, \
             patch("app.routers.pipeline.run_prompt_analysis", new_callable=AsyncMock) as mock_run_analyst:
            mock_analyze.return_value = mock_analysis
            mock_run_analyst.return_value = mock_report

            client = TestClient(app)
            response = client.post("/pipeline/improve-prompts?runs=15")

            assert response.status_code == 200
            body = response.json()

            # Check all required fields exist
            assert "run_count" in body
            assert "top_issue" in body
            assert "regression_rate" in body
            assert "summary" in body
            assert "suggestions" in body
            assert "analyzed_at" in body

            # Verify values
            assert body["run_count"] == 15
            assert body["top_issue"] == "Hyperlink retention below threshold"
            assert body["regression_rate"] == 0.25
            assert len(body["suggestions"]) == 2

            # Verify first suggestion
            first = body["suggestions"][0]
            assert first["file"] == "content_generator_system.txt"
            assert first["priority"] == 1

            # Verify analyze was called with runs=15
            mock_analyze.assert_called_once_with(n_runs=15)

    def test_improve_prompts_returns_404_on_empty_db(self) -> None:
        """Mock analyze to return error, assert 404 response."""
        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = {"error": "No quality_snapshots found in database"}

            client = TestClient(app)
            response = client.post("/pipeline/improve-prompts?runs=20")

            assert response.status_code == 404
            assert "No quality_snapshots" in response.json()["detail"]

    def test_improve_prompts_runs_param_default(self) -> None:
        """Default runs parameter is 20."""
        mock_analysis = {
            "run_count": 20,
            "regression_rate": 0.0,
            "top_issues": [],
            "gate_failure_types": {},
        }
        mock_report = PromptAnalysisReport(
            run_count=20,
            top_issue="None",
            regression_rate=0.0,
            summary="No issues found.",
            suggestions=[],
        )

        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze, \
             patch("app.routers.pipeline.run_prompt_analysis", new_callable=AsyncMock) as mock_run_analyst:
            mock_analyze.return_value = mock_analysis
            mock_run_analyst.return_value = mock_report

            client = TestClient(app)
            response = client.post("/pipeline/improve-prompts")

            assert response.status_code == 200
            # Verify default runs=20 was passed
            mock_analyze.assert_called_once_with(n_runs=20)

    def test_improve_prompts_runs_param_valid_range(self) -> None:
        """runs parameter must be between 5 and 100."""
        client = TestClient(app)

        # Test minimum: 5
        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze, \
             patch("app.routers.pipeline.run_prompt_analysis", new_callable=AsyncMock) as mock_run_analyst:
            mock_report = PromptAnalysisReport(
                run_count=5,
                top_issue="None",
                regression_rate=0.0,
                summary="No issues.",
                suggestions=[],
            )
            mock_analyze.return_value = {"run_count": 5}
            mock_run_analyst.return_value = mock_report

            response = client.post("/pipeline/improve-prompts?runs=5")
            assert response.status_code == 200

        # Test maximum: 100
        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze, \
             patch("app.routers.pipeline.run_prompt_analysis", new_callable=AsyncMock) as mock_run_analyst:
            mock_report = PromptAnalysisReport(
                run_count=100,
                top_issue="None",
                regression_rate=0.0,
                summary="No issues.",
                suggestions=[],
            )
            mock_analyze.return_value = {"run_count": 100}
            mock_run_analyst.return_value = mock_report

            response = client.post("/pipeline/improve-prompts?runs=100")
            assert response.status_code == 200

    def test_improve_prompts_runs_param_too_low_rejected(self) -> None:
        """runs < 5 should be rejected."""
        client = TestClient(app)
        response = client.post("/pipeline/improve-prompts?runs=4")
        assert response.status_code == 422  # Validation error

    def test_improve_prompts_runs_param_too_high_rejected(self) -> None:
        """runs > 100 should be rejected."""
        client = TestClient(app)
        response = client.post("/pipeline/improve-prompts?runs=101")
        assert response.status_code == 422  # Validation error

    def test_improve_prompts_analyzed_at_is_iso_timestamp(self) -> None:
        """analyzed_at field must be ISO8601 timestamp."""
        mock_analysis = {"run_count": 10}
        mock_report = PromptAnalysisReport(
            run_count=10,
            top_issue="Test issue",
            regression_rate=0.1,
            summary="Test summary",
            suggestions=[],
        )

        with patch("app.routers.pipeline.analyze", new_callable=AsyncMock) as mock_analyze, \
             patch("app.routers.pipeline.run_prompt_analysis", new_callable=AsyncMock) as mock_run_analyst:
            mock_analyze.return_value = mock_analysis
            mock_run_analyst.return_value = mock_report

            client = TestClient(app)
            response = client.post("/pipeline/improve-prompts?runs=10")

            assert response.status_code == 200
            body = response.json()
            analyzed_at = body["analyzed_at"]

            # Should parse as ISO8601
            try:
                dt = datetime.fromisoformat(analyzed_at.replace("Z", "+00:00"))
                assert dt.tzinfo is not None
            except ValueError:
                pytest.fail(f"analyzed_at '{analyzed_at}' is not ISO8601 format")

    def test_improvement_suggestion_required_fields(self) -> None:
        """ImprovementSuggestion must have all required fields."""
        sugg = ImprovementSuggestion(
            file="test.txt",
            section="Section 1",
            issue="Test issue",
            current_behavior="Current behavior",
            suggested_change="Suggested change",
            priority=1,
        )

        assert sugg.file == "test.txt"
        assert sugg.section == "Section 1"
        assert sugg.issue == "Test issue"
        assert sugg.current_behavior == "Current behavior"
        assert sugg.suggested_change == "Suggested change"
        assert sugg.priority == 1

    def test_improvement_suggestion_priority_validation(self) -> None:
        """ImprovementSuggestion priority must be 1-3."""
        from pydantic import ValidationError

        # Valid priority 1-3
        for p in [1, 2, 3]:
            sugg = ImprovementSuggestion(
                file="test.txt",
                section="Section",
                issue="Issue",
                current_behavior="Behavior",
                suggested_change="Change",
                priority=p,
            )
            assert sugg.priority == p

        # Invalid priority 0
        with pytest.raises(ValidationError):
            ImprovementSuggestion(
                file="test.txt",
                section="Section",
                issue="Issue",
                current_behavior="Behavior",
                suggested_change="Change",
                priority=0,
            )

        # Invalid priority 4
        with pytest.raises(ValidationError):
            ImprovementSuggestion(
                file="test.txt",
                section="Section",
                issue="Issue",
                current_behavior="Behavior",
                suggested_change="Change",
                priority=4,
            )
