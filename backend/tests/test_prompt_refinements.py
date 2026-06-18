"""
Tests for prompt refinements derived from the 1.0-scoring Post 3 analysis.

RED phase: these describe the improved prompt content before the changes are made.
Each test is tied to a specific structural pattern the 1.0 post used that was
not yet codified in the prompts.
"""

from app.prompt_loader import load_prompt, load_template


class TestContentGeneratorSystemPrompt:
    def test_structural_tools_section_exists(self) -> None:
        """Prompt must teach data tables and code blocks as structural tools."""
        system = load_prompt("content_generator_system")
        assert "STRUCTURAL TOOLS" in system, (
            "content_generator_system.txt must include a STRUCTURAL TOOLS section "
            "teaching when to use data tables and code blocks — derived from Post 3 analysis"
        )

    def test_data_table_guidance_present(self) -> None:
        """Prompt must explain when to use a Markdown table."""
        system = load_prompt("content_generator_system")
        assert "DATA TABLE" in system or "Markdown table" in system, (
            "Prompt must teach data table usage for quantitative comparisons"
        )

    def test_code_block_guidance_present(self) -> None:
        """Prompt must explain when to include a code block."""
        system = load_prompt("content_generator_system")
        assert "CODE BLOCK" in system or "code block" in system, (
            "Prompt must teach code block usage tied to dollar/time savings"
        )

    def test_concession_pattern_present(self) -> None:
        """Prompt must codify the 'one scenario where X still wins' pattern."""
        system = load_prompt("content_generator_system")
        assert "CONCESSION" in system or "one scenario" in system.lower() or "still wins" in system.lower(), (
            "Prompt must teach the counter-intuitive concession section — "
            "the 'one case where the alternative wins' pattern from Post 3"
        )

    def test_outcome_first_hook_pattern_present(self) -> None:
        """Prompt must codify the outcome-first hook structure."""
        system = load_prompt("content_generator_system")
        assert "outcome" in system.lower() or "OUTCOME-FIRST" in system, (
            "Prompt must teach outcome-first hook: give the result in sentence 1, "
            "tension comes from HOW and AT WHAT COST"
        )

    def test_specific_close_rule_present(self) -> None:
        """Prompt must require a specific closing question, not a generic one."""
        system = load_prompt("content_generator_system")
        # Check it explicitly forbids generic closes or requires specificity
        assert "specific" in system.lower() and ("question" in system.lower() or "close" in system.lower()), (
            "Prompt must require the closing question to be specific to the argument, "
            "not a generic 'what do you think?' prompt"
        )


class TestContentGeneratorHumanInitialTemplate:
    def test_table_checkbox_present(self) -> None:
        """Human template must include a checkbox for data tables on quantitative posts."""
        text = str(load_template("content_generator_human_initial"))
        assert "table" in text.lower() or "TABLE" in text, (
            "content_generator_human_initial.txt must include a mandatory check "
            "for data tables when making quantitative comparisons"
        )

    def test_code_block_checkbox_present(self) -> None:
        """Human template must include a checkbox for code blocks on technical posts."""
        text = str(load_template("content_generator_human_initial"))
        assert "code block" in text.lower() or "CODE BLOCK" in text, (
            "content_generator_human_initial.txt must include a mandatory check "
            "for code blocks when describing technical solutions"
        )

    def test_specific_close_checkbox_present(self) -> None:
        """Human template must include a checkbox requiring a specific close."""
        text = str(load_template("content_generator_human_initial"))
        assert "specific" in text.lower() and (
            "close" in text.lower() or "question" in text.lower()
        ), (
            "Human template must remind the writer to close with a specific question "
            "or prediction, not a generic engagement prompt"
        )


class TestQualityAnalyzerSystemPrompt:
    def test_suboptimal_word_count_flagged(self) -> None:
        """Quality analyzer must flag 1000-1299 word posts as LOW severity."""
        system = load_prompt("quality_analyzer_system")
        assert "1,000" in system and "1,299" in system or "1000" in system and "1299" in system or (
            "LOW" in system and "word" in system.lower() and "1,3" in system
        ), (
            "quality_analyzer_system.txt must flag posts in 1,000-1,299 word range as LOW — "
            "they pass the gate but earn less than the 1,300-1,700 optimal range"
        )

    def test_missing_table_flagged_as_medium(self) -> None:
        """Quality analyzer must flag missing data table on quantitative posts as MEDIUM."""
        system = load_prompt("quality_analyzer_system")
        assert "table" in system.lower() or "TABLE" in system, (
            "quality_analyzer_system.txt must flag missing data table "
            "on quantitative comparison posts as MEDIUM severity"
        )

    def test_missing_code_block_flagged_as_medium(self) -> None:
        """Quality analyzer must flag missing code block on technical solution posts as MEDIUM."""
        system = load_prompt("quality_analyzer_system")
        assert "code block" in system.lower() or "CODE BLOCK" in system, (
            "quality_analyzer_system.txt must flag missing code block "
            "on technical solution posts as MEDIUM severity"
        )

    def test_generic_close_flagged_as_medium(self) -> None:
        """Quality analyzer must flag a generic closing question as MEDIUM severity."""
        system = load_prompt("quality_analyzer_system")
        # The existing prompt already flags "I hope you found this helpful" but not generic questions
        assert "generic" in system.lower() or (
            "close" in system.lower() and "specific" in system.lower()
        ), (
            "quality_analyzer_system.txt must flag generic closing questions as MEDIUM — "
            "e.g. 'What do you think?' vs 'What context-length threshold would make you switch back?'"
        )
