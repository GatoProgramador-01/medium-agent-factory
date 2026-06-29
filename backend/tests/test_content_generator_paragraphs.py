"""Paragraph-length guardrails for generated posts."""

from unittest.mock import patch

import pytest

from app.agents.content_generator import (
    GeneratedPost,
    enforce_paragraph_sentence_limit,
    expand_post,
    generate_initial_post,
    revise_post,
)
from app.agents.structural_checker import run_structural_checks


class TestEnforceParagraphSentenceLimit:
    def test_splits_five_sentence_paragraph_before_structural_check(self) -> None:
        content = (
            "This paragraph starts with a concrete claim. "
            "The second sentence adds the first detail. "
            "The third sentence adds a named tool. "
            "The fourth sentence closes the first thought. "
            "The fifth sentence should move into a new paragraph."
        )

        fixed = enforce_paragraph_sentence_limit(content)

        assert "\n\n" in fixed
        issues = run_structural_checks(fixed)
        assert not any(issue.category == "paragraph_length" for issue in issues)

    def test_keeps_four_sentence_paragraph_unchanged(self) -> None:
        content = (
            "This paragraph starts with a concrete claim. "
            "The second sentence adds the first detail. "
            "The third sentence adds a named tool. "
            "The fourth sentence closes the thought."
        )

        assert enforce_paragraph_sentence_limit(content) == content

    def test_splits_each_long_paragraph_independently(self) -> None:
        first = (
            "First paragraph sentence one. "
            "First paragraph sentence two. "
            "First paragraph sentence three. "
            "First paragraph sentence four. "
            "First paragraph sentence five."
        )
        second = (
            "Second paragraph sentence one. "
            "Second paragraph sentence two. "
            "Second paragraph sentence three. "
            "Second paragraph sentence four. "
            "Second paragraph sentence five."
        )

        fixed = enforce_paragraph_sentence_limit(f"{first}\n\n{second}")

        assert fixed.count("\n\n") == 3
        assert not any(
            issue.category == "paragraph_length"
            for issue in run_structural_checks(fixed)
        )

    def test_skips_markdown_structures(self) -> None:
        content = "\n\n".join(
            [
                (
                    "## Heading. With punctuation. That should be ignored. "
                    "By splitter. Always."
                ),
                "[IMAGE: chart. with. punctuation. | alt: chart showing costs]",
                "---",
                "```python\nprint('one. two. three. four. five.')\n```",
                (
                    "| Tool | Notes |\n"
                    "|------|-------|\n"
                    "| A | One. Two. Three. Four. Five. |"
                ),
                (
                    "- First item has enough words.\n"
                    "- Second item has enough words.\n"
                    "- Third item has enough words.\n"
                    "- Fourth item has enough words.\n"
                    "- Fifth item has enough words."
                ),
            ]
        )

        assert enforce_paragraph_sentence_limit(content) == content

    def test_rejects_invalid_sentence_limit(self) -> None:
        with pytest.raises(ValueError, match="max_sentences"):
            enforce_paragraph_sentence_limit("One sentence.", max_sentences=0)


class TestGeneratorAppliesParagraphLimit:
    @pytest.mark.asyncio
    async def test_initial_generation_splits_llm_long_paragraph(self) -> None:
        long_content = (
            "This paragraph starts with a concrete claim. "
            "The second sentence adds the first detail. "
            "The third sentence adds a named tool. "
            "The fourth sentence closes the first thought. "
            "The fifth sentence should move before quality analysis."
        )

        class FakeLLM:
            def with_structured_output(self, schema):
                return self

            async def ainvoke(self, messages):
                return GeneratedPost(
                    title="Test Title",
                    subtitle="A subtitle",
                    content=long_content,
                    tags=["ai", "writing", "python", "llm", "tools"],
                    image_suggestions=["img1", "img2", "img3"],
                )

        with (
            patch("app.agents.content_generator.get_llm", return_value=FakeLLM()),
            patch(
                "app.agents.content_generator.with_langchain_retry",
                side_effect=lambda llm: llm,
            ),
            patch("app.agents.content_generator.AgentTokenTracker"),
            patch(
                "app.agents.content_generator.get_model_name",
                return_value="test-model",
            ),
        ):
            post = await generate_initial_post(
                run_id="test-run",
                topic="paragraph guard",
                trend_context="",
                tags=[],
                audience="software engineers",
            )

        assert "\n\n" in post.content
        assert not any(
            issue.category == "paragraph_length"
            for issue in run_structural_checks(post.content)
        )

    @pytest.mark.asyncio
    async def test_expansion_splits_long_generated_section(self) -> None:
        long_section = (
            "## The Cost Threshold Nobody Measures\n\n"
            "This section starts with a concrete claim. "
            "The second sentence adds the first detail. "
            "The third sentence names the tool. "
            "The fourth sentence closes the first thought. "
            "The fifth sentence should move before the next quality pass."
        )

        class FakeLLM:
            async def ainvoke(self, messages):
                class Result:
                    content = long_section

                return Result()

        with (
            patch("app.agents.content_generator.get_llm", return_value=FakeLLM()),
            patch(
                "app.agents.content_generator.with_langchain_retry",
                side_effect=lambda llm: llm,
            ),
            patch("app.agents.content_generator.AgentTokenTracker"),
            patch(
                "app.agents.content_generator.get_model_name",
                return_value="test-model",
            ),
        ):
            section = await expand_post(
                run_id="test-run",
                title="Test Title",
                content="Existing content.",
                deficit=250,
            )

        assert "\n\n" in section
        assert not any(
            issue.category == "paragraph_length"
            for issue in run_structural_checks(section)
        )

    @pytest.mark.asyncio
    async def test_revision_splits_llm_long_paragraph(self) -> None:
        revised_content = (
            "This revised paragraph starts with a concrete claim. "
            "The second sentence adds the first detail. "
            "The third sentence names the tool. "
            "The fourth sentence closes the first thought. "
            "The fifth sentence should move before the next quality pass."
        )

        class FakeLLM:
            def with_structured_output(self, schema):
                return self

            async def ainvoke(self, messages):
                return GeneratedPost(
                    title="Test Title",
                    subtitle="A subtitle",
                    content=revised_content,
                    tags=["ai", "writing", "python", "llm", "tools"],
                    image_suggestions=["img1", "img2", "img3"],
                )

        with (
            patch("app.agents.content_generator.get_llm", return_value=FakeLLM()),
            patch(
                "app.agents.content_generator.with_langchain_retry",
                side_effect=lambda llm: llm,
            ),
            patch("app.agents.content_generator.AgentTokenTracker"),
            patch(
                "app.agents.content_generator.get_model_name",
                return_value="test-model",
            ),
        ):
            post = await revise_post(
                run_id="test-run",
                title="Test Title",
                content="Original content.",
                score=0.72,
                revision_prompt="Fix specificity.",
                issues=[],
            )

        assert "\n\n" in post.content
        assert not any(
            issue.category == "paragraph_length"
            for issue in run_structural_checks(post.content)
        )
