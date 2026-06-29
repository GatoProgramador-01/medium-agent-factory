"""Tests for the prompt_analyst agent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.prompt_analyst import PromptAnalysisReport, PromptSuggestion, run_prompt_analysis


SAMPLE_ANALYSIS = {
    "run_count": 20,
    "regression_rate": 0.21,
    "top_issues": [
        {"category": "paragraph_length", "total": 18, "high_count": 15, "sticky_count": 7},
        {"category": "missing_data_point", "total": 12, "high_count": 8, "sticky_count": 3},
    ],
    "word_count": {"avg": 1180, "pct_under_1300": 67.0},
    "gate_failure_types": {"word_count": 14, "quality_score": 8},
}

SAMPLE_PROMPTS = {
    "content_generator_system.txt": "You are a writer...\n## MANDATORY FORMAT SPECS\nParagraphs: 1-3 sentences.",
    "content_reviser_system.txt": "You are an editor...\n## PARAGRAPH LENGTH\nSplit paragraphs over 4 sentences.",
}

SAMPLE_REPORT = PromptAnalysisReport(
    run_count=20,
    top_issue="paragraph_length",
    regression_rate=0.21,
    suggestions=[
        PromptSuggestion(
            file="content_generator_system.txt",
            section="MANDATORY FORMAT SPECS",
            issue="paragraph_length: 18/20 runs, 15 HIGH severity",
            current_behavior="Generator writes 5-6 sentence paragraphs despite the rule",
            suggested_change='After "Maximum 4." add: "Count your sentences. If any paragraph has 5+, split it NOW before moving to the next paragraph."',
            priority=1,
        )
    ],
    summary="paragraph_length is the top issue (18/20 runs). Immediate in-generation sentence counting will cut failures.",
)


@pytest.mark.asyncio
async def test_run_prompt_analysis_calls_llm():
    with patch("app.agents.prompt_analyst.get_llm") as mock_get_llm, \
         patch("app.agents.prompt_analyst.get_model_name", return_value="claude-haiku-4-5"), \
         patch("app.agents.prompt_analyst.AgentTokenTracker"), \
         patch("app.agents.prompt_analyst.load_prompt", return_value="system prompt"), \
         patch("app.agents.prompt_analyst.load_template", return_value="{analysis_json}{prompt_files}"), \
         patch("app.agents.prompt_analyst.with_langchain_retry", side_effect=lambda x: x):
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=SAMPLE_REPORT)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain
        mock_get_llm.return_value = mock_llm

        result = await run_prompt_analysis("run-1", SAMPLE_ANALYSIS, SAMPLE_PROMPTS)

        assert result.run_count == 20
        assert result.top_issue == "paragraph_length"
        assert len(result.suggestions) == 1
        assert result.suggestions[0].priority == 1


@pytest.mark.asyncio
async def test_run_prompt_analysis_raises_on_none():
    with patch("app.agents.prompt_analyst.get_llm") as mock_get_llm, \
         patch("app.agents.prompt_analyst.get_model_name", return_value="claude-haiku-4-5"), \
         patch("app.agents.prompt_analyst.AgentTokenTracker"), \
         patch("app.agents.prompt_analyst.load_prompt", return_value=""), \
         patch("app.agents.prompt_analyst.load_template", return_value="{analysis_json}{prompt_files}"), \
         patch("app.agents.prompt_analyst.with_langchain_retry", side_effect=lambda x: x):
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=None)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.return_value = mock_chain
        mock_get_llm.return_value = mock_llm

        with pytest.raises(ValueError, match="prompt_analyst"):
            await run_prompt_analysis("run-1", SAMPLE_ANALYSIS, SAMPLE_PROMPTS)


def test_prompt_suggestion_model_validates_priority():
    with pytest.raises(Exception):
        PromptSuggestion(
            file="f.txt", section="s", issue="i",
            current_behavior="b", suggested_change="c", priority=0
        )
    with pytest.raises(Exception):
        PromptSuggestion(
            file="f.txt", section="s", issue="i",
            current_behavior="b", suggested_change="c", priority=4
        )


def test_prompt_analysis_report_coerces_json_string_suggestions():
    import json
    suggestions_json = json.dumps([{
        "file": "f.txt", "section": "s", "issue": "i",
        "current_behavior": "b", "suggested_change": "c", "priority": 2
    }])
    report = PromptAnalysisReport(
        run_count=5, top_issue="x", regression_rate=0.1,
        suggestions=suggestions_json,
        summary="test"
    )
    assert len(report.suggestions) == 1
    assert report.suggestions[0].file == "f.txt"
