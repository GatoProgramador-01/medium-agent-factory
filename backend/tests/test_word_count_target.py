"""
Sprint 12 — Word count target elevation.

Problem: initial generation targets 1,500 words (200-word buffer above the 1,300 gate),
so LLMs frequently produce 1,200-1,400 word drafts that fail the gate and trigger
expensive expand_post cycles.

Fix: raise TARGET to 1,700 across all generation and revision prompts.
These tests assert the prompts are correctly configured — they fail until the
prompt files are updated.
"""

from app.prompt_loader import load_prompt, load_template


class TestWordCountPromptTargets:
    def test_initial_system_prompt_targets_1700(self) -> None:
        """Generator system prompt must name 1,700 as the TARGET, not 1,500."""
        system = load_prompt("content_generator_system")
        assert "TARGET: 1,700" in system, (
            "content_generator_system.txt still says TARGET: 1,500 — "
            "update to TARGET: 1,700 to reduce word count gate failures"
        )

    def test_initial_human_template_targets_1700(self) -> None:
        """Generator human initial template checklist must reference TARGET 1,700."""
        template = str(load_template("content_generator_human_initial"))
        assert "TARGET 1,700" in template, (
            "content_generator_human_initial.txt checklist must say TARGET 1,700"
        )

    def test_reviser_system_explicit_max_length_mandate(self) -> None:
        """Reviser system must explicitly instruct expansion toward 1,700 (not just the floor)."""
        system = load_prompt("content_reviser_system")
        assert "TARGET 1,700" in system, (
            "content_reviser_system.txt must include 'TARGET 1,700' to push "
            "revision toward maximum length, not just away from the 1,300 floor"
        )

    def test_reviser_human_template_targets_1700(self) -> None:
        """Revision human template must show 1,700 as the explicit target."""
        template = str(load_template("content_generator_human_revision"))
        assert "TARGET 1,700" in template, (
            "content_generator_human_revision.txt must say TARGET 1,700"
        )

    def test_initial_system_prompt_section_anchor_matches_target(self) -> None:
        """Section-level anchor in system prompt must align with 1,700 target (≥250 words/section)."""
        system = load_prompt("content_generator_system")
        # 5 sections × 300 words = 1,500 body + hook/close = ~1,700 total
        assert "250" in system or "300" in system, (
            "Section-level word anchor should guide LLM to 250-350 words/section "
            "to hit the 1,700 target naturally"
        )
