"""Tests for analyze_quality_snapshots script logic."""
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add backend/scripts to path so we can import analyze_quality_snapshots
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


def _make_run(run_id: str, snapshots: list[dict]) -> dict:
    return {"_id": run_id, "snapshots": snapshots, "last_ts": "2026-06-01T00:00:00"}


def _make_snap(
    iteration: int,
    score: float,
    word_count: int,
    issues: list[dict],
    gate_failures: list[str] | None = None,
) -> dict:
    return {
        "run_id": "r1",
        "iteration": iteration,
        "score": score,
        "word_count": word_count,
        "issues": issues,
        "gate_failures": gate_failures or [],
        "timestamp": "2026-06-01T00:00:00",
    }


MOCK_RUNS = [
    _make_run(
        "run-1",
        [
            _make_snap(
                0,
                0.60,
                1100,
                [{"category": "paragraph_length", "severity": "HIGH"}],
                ["word count 1100 below minimum 1300"],
            ),
            _make_snap(
                1,
                0.55,
                1200,
                [
                    {"category": "paragraph_length", "severity": "HIGH"},
                    {"category": "ai_pattern", "severity": "HIGH"},
                ],
                [],
            ),
            _make_snap(2, 0.72, 1450, [], []),
        ],
    ),
    _make_run(
        "run-2",
        [
            _make_snap(
                0,
                0.65,
                950,
                [{"category": "missing_data_point", "severity": "HIGH"}],
                ["word count 950 below minimum 1300"],
            ),
            _make_snap(1, 0.70, 1350, [], []),
        ],
    ),
]


def _patch_mongo(mock_runs: list[dict]):
    """Returns a context manager that patches AsyncIOMotorClient to return mock_runs."""

    class MockCursor:
        async def to_list(self, n: int) -> list[dict]:
            return mock_runs

    class MockCollection:
        def aggregate(self, pipeline: list[dict]) -> MockCursor:
            return MockCursor()

    class MockDB:
        quality_snapshots = MockCollection()

        def __getitem__(self, name: str) -> MockCollection | "MockDB":
            if name == "medium_agent":
                return self
            return MockCollection()

    class MockClient:
        def __getitem__(self, name: str) -> MockDB:
            return MockDB()

        def close(self) -> None:
            pass

    return patch(
        "app.scripts.analyze_quality_snapshots.AsyncIOMotorClient",
        return_value=MockClient(),
    )


@pytest.mark.asyncio
async def test_analyze_returns_run_count():
    """Verify run_count in result matches number of aggregated runs."""
    from analyze_quality_snapshots import analyze

    with _patch_mongo(MOCK_RUNS):
        result = await analyze(n_runs=20)
    assert result["run_count"] == 2


@pytest.mark.asyncio
async def test_analyze_detects_regression():
    """Score going down is a regression; verify count."""
    from analyze_quality_snapshots import analyze

    with _patch_mongo(MOCK_RUNS):
        result = await analyze()
    # run-1: 0.60→0.55 is regression, 0.55→0.72 is not. run-2: 0.65→0.70 is not.
    assert result["regression_events"] == 1
    assert result["transition_count"] == 3


@pytest.mark.asyncio
async def test_analyze_word_count_stats():
    """Word count min/max/avg and pct_under_1300 calculated correctly."""
    from analyze_quality_snapshots import analyze

    with _patch_mongo(MOCK_RUNS):
        result = await analyze()
    wc = result["word_count"]
    assert wc["min"] == 950
    assert wc["max"] == 1450
    assert wc["pct_under_1300"] > 0


@pytest.mark.asyncio
async def test_analyze_issue_frequency():
    """Issue categories counted and aggregated by HIGH severity."""
    from analyze_quality_snapshots import analyze

    with _patch_mongo(MOCK_RUNS):
        result = await analyze()
    cats = {i["category"]: i for i in result["top_issues"]}
    assert "paragraph_length" in cats
    assert cats["paragraph_length"]["total"] == 2
    assert cats["paragraph_length"]["high_count"] == 2


@pytest.mark.asyncio
async def test_analyze_sticky_issues():
    """Sticky = appears in >=2 iterations, span >=2 cycles."""
    from analyze_quality_snapshots import analyze

    # Make a run where paragraph_length spans 0→1→2 (span=2, sticky)
    sticky_run = _make_run(
        "run-s",
        [
            _make_snap(0, 0.60, 1100, [{"category": "paragraph_length", "severity": "HIGH"}]),
            _make_snap(1, 0.62, 1150, [{"category": "paragraph_length", "severity": "HIGH"}]),
            _make_snap(2, 0.65, 1300, [{"category": "paragraph_length", "severity": "HIGH"}]),
        ],
    )
    with _patch_mongo([sticky_run]):
        result = await analyze()
    sticky_cats = {s["category"] for s in result["top_5_sticky"]}
    assert "paragraph_length" in sticky_cats


@pytest.mark.asyncio
async def test_analyze_empty_db_returns_error():
    """Empty runs list returns error key."""
    from analyze_quality_snapshots import analyze

    with _patch_mongo([]):
        result = await analyze()
    assert "error" in result


@pytest.mark.asyncio
async def test_analyze_gate_failure_classification():
    """Gate failures classified by type (word_count, read_ratio, ai_pattern, etc)."""
    from app.scripts.analyze_quality_snapshots import analyze

    with _patch_mongo(MOCK_RUNS):
        result = await analyze()
    assert result["gate_failure_types"].get("word_count", 0) == 2
