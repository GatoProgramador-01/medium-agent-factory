"""
Unit tests for prompt_loader — fail-fast on missing prompts, correct variable injection.
"""

import pytest

from app.prompt_loader import load_prompt, load_template


class TestLoadPrompt:
    def test_returns_string_with_content(self) -> None:
        content = load_prompt("quality_analyzer_system")
        assert isinstance(content, str)
        assert len(content) > 100

    def test_content_generator_system_prompt_loads(self) -> None:
        content = load_prompt("content_generator_system")
        assert len(content) > 100

    def test_missing_prompt_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="nonexistent_prompt"):
            load_prompt("nonexistent_prompt")

    def test_error_message_lists_available_prompts(self) -> None:
        with pytest.raises(KeyError) as exc_info:
            load_prompt("does_not_exist")
        assert "Available" in str(exc_info.value)


class TestLoadTemplate:
    def test_quality_analyzer_human_injects_variables(self) -> None:
        template = load_template("quality_analyzer_human")
        result = template.format(title="My Title", content="My content here")
        assert "My Title" in result
        assert "My content here" in result

    def test_content_generator_initial_injects_variables(self) -> None:
        template = load_template("content_generator_human_initial")
        result = template.format(
            topic="test topic",
            trend_context="no trends",
            tags="ai, writing",
            audience="developers",
            exemplar_section="",
            series_context="",
        )
        assert "test topic" in result

    def test_missing_variable_raises_key_error(self) -> None:
        template = load_template("quality_analyzer_human")
        with pytest.raises(KeyError):
            template.format(title="Only title, missing content")

    def test_missing_template_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="nonexistent"):
            load_template("nonexistent")
