import pytest
from app.prompt_loader import load_template


class TestWordCountPromptStructuralPlan:
    def test_initial_prompt_contains_structural_plan(self):
        prompt = str(load_template("content_generator_human_initial"))
        assert "STRUCTURAL PLAN" in prompt
        assert "1,700 words MINIMUM" in prompt
        assert "300 words each" in prompt

    def test_word_count_is_first_checkbox(self):
        prompt = str(load_template("content_generator_human_initial"))
        checks_section = prompt[prompt.index("□"):]
        first_check = checks_section[:checks_section.index("\n")]
        assert "WORD COUNT" in first_check or "1,700" in first_check


class TestSourcesInstruction:
    def test_sources_checkbox_in_initial_prompt(self):
        prompt = str(load_template("content_generator_human_initial"))
        assert "SOURCES SECTION" in prompt
        assert "## Sources" in prompt
