"""
RED tests for repo_analysis_node — Sprint 19 (Task 1).
These tests fail until repo_analysis_node is implemented in orchestrator.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.evidence_brief import EvidenceBrief


def _minimal_state(**overrides):
    """Build a minimal PipelineState-like dict for node tests."""
    base = {
        "run_id": "test-sprint19-001",
        "custom_topic": "AI cost optimization",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": None,
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
        "recommended_publication": False,
        "publication_confidence": 0.0,
        "draft_content": "",
        "title_variants": [],
        "intro_variants": [],
        "series_coherence_score": None,
        "image_enrichment_changes": [],
        "repo_path": None,
        "evidence_brief": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_repo_analysis_node_skips_when_repo_path_none() -> None:
    """repo_analysis_node returns evidence_brief=None when repo_path is None."""
    from app.agents.orchestrator import repo_analysis_node

    state = _minimal_state(repo_path=None)
    result = await repo_analysis_node(state)  # type: ignore[arg-type]

    assert result.get("evidence_brief") is None
    assert "repo_analysis_skipped" in result.get("completed_steps", [])


@pytest.mark.asyncio
async def test_repo_analysis_node_runs_analyzer_when_path_given() -> None:
    """repo_analysis_node calls RepoAnalyzer.analyze and returns evidence_brief as dict."""
    from app.agents.orchestrator import repo_analysis_node

    mock_brief = EvidenceBrief(
        repository_path="/c/Users/lanitaEmperadora/medium-agent-factory",
        stack=["python", "fastapi", "langgraph"],
        commands={"test": "pytest backend/tests/", "run": "docker compose up --build"},
        architecture_hints=["backend/app contains application code"],
        metrics={"files_scanned": 42, "test_files": 8},
        evidence=["backend/app/agents/orchestrator.py exists"],
    )

    with patch("app.agents.orchestrator.RepoAnalyzer") as mock_cls:
        instance = MagicMock()
        instance.analyze.return_value = mock_brief
        mock_cls.return_value = instance

        state = _minimal_state(repo_path="/c/Users/lanitaEmperadora/medium-agent-factory")
        result = await repo_analysis_node(state)  # type: ignore[arg-type]

    assert result.get("evidence_brief") is not None
    assert isinstance(result["evidence_brief"], dict)
    assert "stack" in result["evidence_brief"]
    assert "repo_analysis" in result.get("completed_steps", [])
    instance.analyze.assert_called_once_with(
        "/c/Users/lanitaEmperadora/medium-agent-factory"
    )


@pytest.mark.asyncio
async def test_repo_analysis_node_handles_invalid_path() -> None:
    """repo_analysis_node sets evidence_brief=None and appends error on bad path."""
    from app.agents.orchestrator import repo_analysis_node

    with patch("app.agents.orchestrator.RepoAnalyzer") as mock_cls, patch(
        "app.agents.orchestrator.log_step", new_callable=AsyncMock
    ):
        instance = MagicMock()
        instance.analyze.side_effect = FileNotFoundError("Path does not exist")
        mock_cls.return_value = instance

        state = _minimal_state(repo_path="/nonexistent/path")
        result = await repo_analysis_node(state)  # type: ignore[arg-type]

    assert result.get("evidence_brief") is None


@pytest.mark.asyncio
async def test_run_pipeline_accepts_repo_path_kwarg() -> None:
    """run_pipeline signature includes repo_path=None keyword argument."""
    import inspect
    from app.agents.orchestrator import run_pipeline

    sig = inspect.signature(run_pipeline)
    assert "repo_path" in sig.parameters, "run_pipeline must accept repo_path=None"
    assert sig.parameters["repo_path"].default is None


def test_pipeline_state_has_repo_path_and_evidence_brief() -> None:
    """PipelineState TypedDict includes repo_path and evidence_brief keys."""
    from app.agents.orchestrator import PipelineState
    import typing

    hints = typing.get_type_hints(PipelineState)
    assert "repo_path" in hints, "PipelineState must have repo_path"
    assert "evidence_brief" in hints, "PipelineState must have evidence_brief"
