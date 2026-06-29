from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from app.agents.web_researcher import (
    ResearchBrief,
    _Queries,
    _generate_queries,
    _run_search,
    _synthesize,
)


# ── TestQueriesModel ───────────────────────────────────────────────────────────


class TestQueriesModel:
    def test_queries_model_allows_five_queries(self) -> None:
        result = _Queries(queries=["q1", "q2", "q3", "q4", "q5"])
        assert len(result.queries) == 5

    def test_queries_model_rejects_seven_queries(self) -> None:
        with pytest.raises(ValidationError):
            _Queries(queries=["q"] * 7)


# ── TestRunSearch ──────────────────────────────────────────────────────────────


class TestRunSearch:
    @pytest.mark.asyncio
    async def test_run_search_uses_advanced_depth(self) -> None:
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}

        with patch("app.agents.web_researcher.TavilyClient", return_value=mock_client):
            await _run_search("test query")

        _, kwargs = mock_client.search.call_args
        assert kwargs.get("search_depth") == "advanced"

    @pytest.mark.asyncio
    async def test_run_search_fetches_five_results(self) -> None:
        mock_client = MagicMock()
        mock_client.search.return_value = {"results": []}

        with patch("app.agents.web_researcher.TavilyClient", return_value=mock_client):
            await _run_search("test query")

        _, kwargs = mock_client.search.call_args
        assert kwargs.get("max_results") == 5


# ── TestSynthesizeDedup ────────────────────────────────────────────────────────


class TestSynthesizeDedup:
    @pytest.mark.asyncio
    async def test_synthesize_passes_fifteen_results_to_llm(self) -> None:
        all_results: list[list[dict[str, Any]]] = [
            [{"url": f"https://example.com/{i}", "title": f"Title {i}", "content": f"Content {i}"}
             for i in range(20)]
        ]

        mock_brief = ResearchBrief(
            key_facts=["fact1"],
            named_examples=["ex1"],
            trend_summary="trend",
            surprising_finding="finding",
        )

        captured_messages: list[Any] = []

        async def fake_ainvoke(messages: list[Any]) -> ResearchBrief:
            captured_messages.extend(messages)
            return mock_brief

        mock_chain = AsyncMock(ainvoke=fake_ainvoke)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain

        with patch("app.agents.web_researcher.get_llm", return_value=mock_llm), \
             patch("app.agents.web_researcher.get_model_name", return_value="claude-haiku-4-5"), \
             patch("app.agents.web_researcher.AgentTokenTracker"):
            await _synthesize("run-1", "AI trends", all_results)

        human_msg = next(m for m in captured_messages if hasattr(m, "content") and "Search results:" in m.content)
        content: str = human_msg.content

        assert "[15]" in content
        assert "[16]" not in content


# ── TestResearchQueryCount ─────────────────────────────────────────────────────


class TestResearchQueryCount:
    @pytest.mark.asyncio
    async def test_generate_queries_prompts_for_five_angles(self) -> None:
        captured_messages: list[Any] = []

        async def fake_ainvoke(messages: list[Any]) -> _Queries:
            captured_messages.extend(messages)
            return _Queries(queries=["q1", "q2", "q3", "q4", "q5"])

        mock_chain = AsyncMock(ainvoke=fake_ainvoke)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain

        with patch("app.agents.web_researcher.get_llm", return_value=mock_llm), \
             patch("app.agents.web_researcher.get_model_name", return_value="claude-haiku-4-5"), \
             patch("app.agents.web_researcher.AgentTokenTracker"):
            await _generate_queries("run-1", "AI in healthcare")

        system_msg = next(m for m in captured_messages if hasattr(m, "content") and "search quer" in m.content.lower())
        content: str = system_msg.content

        angle_keywords = ["statistics", "case stud", "news", "expert", "criticism"]
        matched = sum(1 for kw in angle_keywords if kw.lower() in content.lower())
        mentions_five = "5" in content

        assert mentions_five or matched >= 5
