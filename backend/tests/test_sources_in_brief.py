import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFormatBriefSourceUrls:
    def test_format_brief_includes_source_urls(self):
        from app.agents.web_researcher import _format_brief, ResearchBrief
        brief = ResearchBrief(
            key_facts=["Fact 1"],
            named_examples=["Example 1"],
            trend_summary="Trend summary here",
            surprising_finding="Surprising finding",
        )
        urls = ["https://example.com/a", "https://example.com/b"]
        result = _format_brief(brief, ["query1"], source_urls=urls)
        assert "SOURCE URLS" in result
        assert "https://example.com/a" in result
        assert "https://example.com/b" in result

    def test_format_brief_without_urls_omits_section(self):
        from app.agents.web_researcher import _format_brief, ResearchBrief
        brief = ResearchBrief(
            key_facts=[],
            named_examples=[],
            trend_summary="Trend",
            surprising_finding="Finding",
        )
        result = _format_brief(brief, ["q"], source_urls=None)
        assert "SOURCE URLS" not in result

    def test_format_brief_caps_at_eight_urls(self):
        from app.agents.web_researcher import _format_brief, ResearchBrief
        brief = ResearchBrief(
            key_facts=[],
            named_examples=[],
            trend_summary="T",
            surprising_finding="F",
        )
        urls = [f"https://example.com/{i}" for i in range(12)]
        result = _format_brief(brief, ["q"], source_urls=urls)
        # Count occurrences of "https://example.com/" in result
        assert result.count("https://example.com/") == 8


class TestResearchTopicCollectsUrls:
    @pytest.mark.asyncio
    async def test_research_topic_includes_urls_in_brief(self):
        from app.agents.web_researcher import research_topic
        from app.config import settings

        fake_results = [
            {"url": "https://source1.com", "title": "T1", "content": "Content 1"},
            {"url": "https://source2.com", "title": "T2", "content": "Content 2"},
        ]
        with patch.object(settings, "tavily_api_key", "fake-key"):
            with patch("app.agents.web_researcher.TavilyClient", MagicMock()):
                with patch("app.agents.web_researcher._generate_queries", new=AsyncMock(return_value=["q1"])):
                    with patch("app.agents.web_researcher._run_search", new=AsyncMock(return_value=fake_results)):
                        with patch("app.agents.web_researcher._synthesize") as mock_syn:
                            from app.agents.web_researcher import ResearchBrief
                            mock_syn.return_value = ResearchBrief(
                                key_facts=["Fact"],
                                named_examples=["Ex"],
                                trend_summary="Trend",
                                surprising_finding="Find",
                            )
                            result = await research_topic("run-123", "test topic")
        assert "SOURCE URLS" in result
        assert "https://source1.com" in result
        assert "https://source2.com" in result
