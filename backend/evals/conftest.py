import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Dataset loader ─────────────────────────────────────────────────────────────

def _load_dataset() -> list[dict[str, Any]]:
    path = Path(__file__).parent / "datasets" / "quality_analyzer.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


DATASET = _load_dataset()
GOOD_CASES   = [c for c in DATASET if c["label"] == "good"]
BAD_CASES    = [c for c in DATASET if c["label"] == "bad"]
MEDIUM_CASES = [c for c in DATASET if c["label"] == "medium"]


@pytest.fixture
def good_cases() -> list[dict]:
    return GOOD_CASES


@pytest.fixture
def bad_cases() -> list[dict]:
    return BAD_CASES


@pytest.fixture
def medium_cases() -> list[dict]:
    return MEDIUM_CASES


@pytest.fixture
def all_cases() -> list[dict]:
    return DATASET


# ── DB mock — evals test LLM quality, not MongoDB writes ──────────────────────

@pytest.fixture(autouse=True)
def mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Patch get_db so AgentTokenTracker doesn't need a running MongoDB.
    The tracker still records tokens in memory; we just skip the DB insert.
    """
    mock_col = AsyncMock()
    mock_col.insert_one = AsyncMock(return_value=None)
    mock_col.update_one = AsyncMock(return_value=None)

    mock_db_obj = MagicMock()
    mock_db_obj.agent_runs = mock_col
    mock_db_obj.posts = mock_col

    monkeypatch.setattr("app.agents.base.get_db", lambda: mock_db_obj)
    monkeypatch.setattr("app.agents.quality_analyzer.get_db", lambda: mock_db_obj, raising=False)
