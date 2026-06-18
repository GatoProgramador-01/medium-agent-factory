"""
Tests for series_context injection through the content generation pipeline.

RED phase: these tests describe the desired behavior BEFORE implementation.
They will fail until generate_initial_post accepts series_context and the
template renders it, and until PipelineState carries series_context.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.content_generator import GeneratedPost, generate_initial_post
from app.prompt_loader import load_template


class TestSeriesContextTemplate:
    def test_template_renders_series_context_when_provided(self) -> None:
        """series_context section appears in the rendered template."""
        template = load_template("content_generator_human_initial")
        rendered = template.format(
            topic="DeepSeek cost optimization",
            trend_context="DeepSeek V4 Flash: $0.14/M tokens",
            tags="deepseek, llm, agents",
            audience="software engineers",
            exemplar_section="",
            series_context=(
                "SERIES: Post 1 of 3 — 'DeepSeek: The $0.003 AI Pipeline'\n"
                "ANGLE: The economic failure that drove the switch\n"
                "HOOK SEED: Opening with the $84 Claude API bill"
            ),
        )
        assert "SERIES:" in rendered
        assert "Post 1 of 3" in rendered

    def test_template_renders_empty_series_context_cleanly(self) -> None:
        """Empty series_context produces no stray section in rendered output."""
        template = load_template("content_generator_human_initial")
        rendered = template.format(
            topic="test topic",
            trend_context="some context",
            tags="",
            audience="engineers",
            exemplar_section="",
            series_context="",
        )
        # When empty, no SERIES frame noise in the output
        assert "SERIES CONTEXT" not in rendered or rendered.count("SERIES CONTEXT") == 0


class TestGenerateInitialPostSignature:
    def test_generate_initial_post_accepts_series_context_parameter(self) -> None:
        """generate_initial_post must accept a series_context keyword argument."""
        import inspect
        sig = inspect.signature(generate_initial_post)
        assert "series_context" in sig.parameters, (
            "generate_initial_post must accept series_context — "
            "it is not yet implemented"
        )

    def test_series_context_has_empty_string_default(self) -> None:
        """series_context defaults to '' so existing callers need no changes."""
        import inspect
        sig = inspect.signature(generate_initial_post)
        param = sig.parameters["series_context"]
        assert param.default == "", (
            "series_context must default to '' to keep backward compatibility"
        )


class TestPipelineStateHasSeriesContext:
    def test_pipeline_state_includes_series_context_field(self) -> None:
        """PipelineState TypedDict must carry series_context for series runs."""
        from app.agents.orchestrator import PipelineState
        import typing
        hints = typing.get_type_hints(PipelineState)
        assert "series_context" in hints, (
            "PipelineState must have a series_context field — "
            "it is not yet implemented"
        )


class TestGenerateInitialPostPassesSeriesContext:
    @pytest.mark.asyncio
    async def test_series_context_injected_into_llm_messages(self) -> None:
        """When series_context is non-empty, the LLM receives it in the prompt."""
        series_ctx = "SERIES: Post 2 of 3 — method post\nANGLE: LangGraph architecture"

        captured_messages: list = []

        class FakeLLM:
            def with_structured_output(self, schema):
                return self

            async def ainvoke(self, messages):
                captured_messages.extend(messages)
                return GeneratedPost(
                    title="Test Title",
                    subtitle="A subtitle",
                    content="Content body " * 200,
                    tags=["deepseek", "llm", "agents", "python", "langchain"],
                    image_suggestions=["img1", "img2", "img3"],
                )

        with (
            patch("app.agents.content_generator.get_llm", return_value=FakeLLM()),
            patch("app.agents.content_generator.with_langchain_retry", side_effect=lambda x: x),
            patch("app.agents.content_generator.AgentTokenTracker"),
            patch("app.agents.content_generator.get_model_name", return_value="test-model"),
        ):
            await generate_initial_post(
                run_id="test-run",
                topic="DeepSeek cost guide",
                trend_context="",
                tags=[],
                audience="engineers",
                series_context=series_ctx,
            )

        human_msg_content = next(
            m.content for m in captured_messages if hasattr(m, "content") and "TOPIC:" in m.content
        )
        assert series_ctx in human_msg_content, (
            "series_context must appear in the human prompt sent to the LLM"
        )
