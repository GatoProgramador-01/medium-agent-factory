import pytest
from app.agents.post_processor import inject_captions, merge_sources_sections


class TestInjectCaptions:
    def test_adds_caption_when_missing(self):
        content = "[IMAGE: bar chart showing costs | alt: Bar chart of costs]"
        result = inject_captions(content)
        assert "| caption:" in result

    def test_preserves_existing_caption(self):
        content = "[IMAGE: chart | alt: Chart | caption: My custom caption]"
        result = inject_captions(content)
        assert result.count("| caption:") == 1
        assert "My custom caption" in result

    def test_handles_multiple_images(self):
        content = "[IMAGE: chart1 | alt: alt1]\n\n[IMAGE: chart2 | alt: alt2 | caption: cap2]"
        result = inject_captions(content)
        assert result.count("| caption:") == 2


class TestMergeSourcesSections:
    def test_merges_when_both_exist(self):
        content = "Body text.\n\n## Sources\n- https://a.com\n\n## References\n1. Author — Title https://b.com\n"
        result = merge_sources_sections(content)
        assert "## Sources" in result
        assert "## References" not in result
        assert "a.com" in result

    def test_no_change_when_only_sources(self):
        content = "Body.\n\n## Sources\n- https://a.com\n"
        result = merge_sources_sections(content)
        assert result == content

    def test_no_change_when_neither_exists(self):
        content = "Body text with no sources.\n"
        result = merge_sources_sections(content)
        assert result == content

    def test_deduplicates_entries(self):
        content = "Body.\n\n## Sources\n- https://a.com\n\n## References\n1. https://a.com\n"
        result = merge_sources_sections(content)
        assert result.count("a.com") == 1
