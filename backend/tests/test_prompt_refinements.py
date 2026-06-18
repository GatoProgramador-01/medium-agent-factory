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


class TestContentReviserSystemPrompt:
    def test_paragraph_split_instruction_present(self) -> None:
        """Reviser must have explicit 'split' instruction for long paragraphs, not just a rule."""
        system = load_prompt("content_reviser_system")
        assert "split" in system.lower(), (
            "content_reviser_system.txt must tell the reviser to SPLIT paragraphs > 4 sentences, "
            "not just list the rule — LLM needs the action verb to act on it"
        )

    def test_heading_cadence_fix_instruction_present(self) -> None:
        """Reviser must tell the LLM HOW to fix heading cadence, not just flag it."""
        system = load_prompt("content_reviser_system")
        assert ("insert" in system.lower() or "add" in system.lower() or "merge" in system.lower()) and (
            "h2" in system.lower() or "heading" in system.lower()
        ), (
            "content_reviser_system.txt must give the reviser an action for heading cadence: "
            "insert a new H2 when gap > 500 words, merge when < 200 words"
        )

    def test_word_count_floor_is_1300_not_1200(self) -> None:
        """Reviser must expand if under 1,300 — the current prompt says 'under 1,200'."""
        system = load_prompt("content_reviser_system")
        # Must NOT say expand only when under 1200
        assert "1,200" not in system or "1,300" in system, (
            "content_reviser_system.txt sets the expand threshold at 1,200 — "
            "must be raised to 1,300 to match the quality gate"
        )


class TestContentReviserHumanTemplate:
    def test_human_revision_word_count_floor_is_1300(self) -> None:
        """Human revision template must say expand if under 1,300, not 1,200."""
        text = str(load_template("content_generator_human_revision"))
        assert "1,200" not in text or "1,300" in text, (
            "content_generator_human_revision.txt sets expand threshold at 1,200 — "
            "must be raised to 1,300"
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

    def test_canonical_snake_case_category_names_enforced(self) -> None:
        """Quality analyzer must output issue categories from a fixed snake_case list."""
        system = load_prompt("quality_analyzer_system")
        assert "paragraph_length" in system and "heading_cadence" in system and "ai_pattern" in system, (
            "quality_analyzer_system.txt must specify canonical snake_case category names "
            "so quality_snapshots aggregation works correctly — "
            "data showed Platform Compliance/platform_compliance/Platform compliance as 3 different keys"
        )

    def test_all_required_category_names_present(self) -> None:
        """All canonical categories must be listed so the LLM doesn't invent new ones."""
        system = load_prompt("quality_analyzer_system")
        required = [
            "paragraph_length", "heading_cadence", "intro_length",
            "word_count", "ai_pattern", "missing_data_point",
            "generic_close", "missing_table", "missing_code_block",
        ]
        missing = [c for c in required if c not in system]
        assert not missing, (
            f"quality_analyzer_system.txt is missing canonical categories: {missing}"
        )


class TestContentReviserSelfAudit:
    def test_self_audit_section_exists(self) -> None:
        """Reviser must have a final self-audit gate to prevent introducing new violations."""
        system = load_prompt("content_reviser_system")
        assert "self-audit" in system.lower() or "SELF-AUDIT" in system or "final audit" in system.lower(), (
            "content_reviser_system.txt must include a FINAL SELF-AUDIT section — "
            "data showed Cases 2 and 3 scored lower after revision 1 because the reviser "
            "introduced new HIGH issues while fixing the reported ones"
        )

    def test_self_audit_checks_new_ai_phrases(self) -> None:
        """Self-audit must explicitly scan for newly introduced AI forbidden phrases."""
        system = load_prompt("content_reviser_system")
        assert "new" in system.lower() and "ai" in system.lower() and "audit" in system.lower(), (
            "Self-audit must tell the reviser to check for new AI phrases it may have introduced, "
            "not just the ones already flagged in the issues list"
        )

    def test_self_audit_checks_paragraph_length(self) -> None:
        """Self-audit must verify no paragraph > 4 sentences was introduced."""
        system = load_prompt("content_reviser_system")
        lower = system.lower()
        assert "audit" in lower and "paragraph" in lower and ("4 sentence" in lower or "four sentence" in lower or "4-sentence" in lower), (
            "Self-audit must verify paragraph length — the reviser introduced new paragraph violations "
            "in Case 3 while fixing an AI pattern issue"
        )

    def test_self_audit_checks_intro_length(self) -> None:
        """Self-audit must verify the intro was not pushed over 110 words."""
        system = load_prompt("content_reviser_system")
        lower = system.lower()
        assert "audit" in lower and "intro" in lower and "110" in system, (
            "Self-audit must check intro word count — Case 2 revision 1 pushed intro to 111 words "
            "creating a new HIGH issue"
        )


class TestContentGeneratorWordCountTarget:
    def test_section_level_word_count_anchor_exists(self) -> None:
        """System prompt must give per-section word count so LLM knows where to expand."""
        system = load_prompt("content_generator_system")
        assert ("200" in system and "300" in system and "section" in system.lower()) or \
               ("per section" in system.lower() or "each section" in system.lower()), (
            "content_generator_system.txt must include per-H2-section word count target "
            "(200-300 words/section) — generator consistently undershoots 1,300 because it has "
            "no section-level anchor, only a total-post target it ignores"
        )

    def test_generator_targets_1500_not_1300(self) -> None:
        """Generator should target 1,400-1,700 words to reliably land above the 1,300 floor."""
        system = load_prompt("content_generator_system")
        assert "1,400" in system or "1,500" in system, (
            "content_generator_system.txt must target 1,400–1,700 words — "
            "all 11 snapshots from 3-case test landed under 1,300 when targeting 1,300–1,700; "
            "raise the floor target so natural landing zone shifts to 1,400-1,500"
        )
