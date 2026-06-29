"""
RED tests for Sprint 20 — content_generation_node editorial structure injection
and dynamic audience fix.

Tests verify:
  - target_audience from topic_brief is passed to generate_initial_post (not hardcoded)
  - fallback to default audience string when topic_brief is absent
  - hook_seed / h2_structure / key_claims / concession are injected into combined_context
  - no EDITORIAL STRUCTURE block when topic_brief is None
  - EDITORIAL STRUCTURE precedes USER-PROVIDED GROUNDING CONTEXT in combined_context
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.content_generator import GeneratedPost

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_AUDIENCE = (
    "software engineers and developers building LLM agents and AI pipelines"
)


def _minimal_state(**overrides):
    """Build a minimal PipelineState-like dict for content_generation_node tests."""
    base = {
        "run_id": "test-sprint20-cg-001",
        "custom_topic": "LLM cost optimization for production pipelines",
        "grounding_context": "",
        "series_id": None,
        "series_position": None,
        "series_context": "",
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": None,
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
        "recommended_publication": False,
        "publication_confidence": 0.0,
        "draft_content": "",
        "title_variants": [],
        "intro_variants": [],
        "series_coherence_score": None,
        "image_enrichment_changes": [],
        "repo_path": None,
        "evidence_brief": None,
    }
    base.update(overrides)
    return base


def _mock_post() -> GeneratedPost:
    return GeneratedPost(
        title="Cut Your LLM Costs by 80%",
        subtitle="A practical guide",
        content="First paragraph.\n\nSecond paragraph.",
        tags=["llm", "cost", "production", "ai", "optimization"],
        image_suggestions=["cost chart", "before/after", "token usage graph"],
    )


def _patch_content_generation_deps(mock_post: GeneratedPost | None = None):
    """Return a context-manager stack patching all external calls in content_generation_node."""
    if mock_post is None:
        mock_post = _mock_post()

    return (
        patch(
            "app.agents.orchestrator.generate_initial_post",
            new_callable=AsyncMock,
            return_value=mock_post,
        ),
        patch("app.agents.orchestrator.log_step", new_callable=AsyncMock),
        patch(
            "app.agents.orchestrator.find_exemplar",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("app.agents.orchestrator._upsert_post", new_callable=AsyncMock),
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestContentGenerationNodeSprint20:
    """Sprint 20: editorial structure injection + dynamic audience in content_generation_node."""

    @pytest.mark.asyncio
    async def test_content_generation_uses_topic_brief_audience(self) -> None:
        """When topic_brief has target_audience, it is forwarded to generate_initial_post — not the hardcoded fallback."""
        from app.agents.orchestrator import content_generation_node

        custom_audience = "CTOs and VP Engs at Series-A startups"
        state = _minimal_state(
            topic_brief={
                "target_audience": custom_audience,
                "refined_angle": "cost focus",
            },
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            actual_audience = kwargs.get("audience") or mock_gen.call_args[0][3]
            assert (
                actual_audience == custom_audience
            ), f"Expected custom audience '{custom_audience}', got '{actual_audience}'"
            assert actual_audience != _DEFAULT_AUDIENCE

    @pytest.mark.asyncio
    async def test_content_generation_falls_back_to_default_audience(self) -> None:
        """When topic_brief is None, generate_initial_post receives the default audience string."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(topic_brief=None)

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            actual_audience = kwargs.get("audience")
            assert actual_audience == _DEFAULT_AUDIENCE

    @pytest.mark.asyncio
    async def test_content_generation_injects_hook_seed_into_context(self) -> None:
        """When topic_brief has hook_seed, combined_context passed to generate_initial_post contains 'HOOK SEED'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(
            topic_brief={
                "hook_seed": "I dropped my monthly LLM bill from $4,200 to $310 in one afternoon.",
            }
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")
            assert (
                "HOOK SEED" in combined_context
            ), f"Expected 'HOOK SEED' in combined_context, got: {combined_context[:300]}"

    @pytest.mark.asyncio
    async def test_content_generation_injects_h2_structure_into_context(self) -> None:
        """When topic_brief has h2_structure list, combined_context contains 'H2 STRUCTURE'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(
            topic_brief={
                "h2_structure": [
                    "The Token Budget Trap",
                    "Prompt Caching Done Right",
                    "When to Route to Haiku vs Sonnet",
                    "Measuring Real Cost per Run",
                ],
            }
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")
            assert (
                "H2 STRUCTURE" in combined_context
            ), f"Expected 'H2 STRUCTURE' in combined_context, got: {combined_context[:300]}"

    @pytest.mark.asyncio
    async def test_content_generation_injects_key_claims_into_context(self) -> None:
        """When topic_brief has key_claims, combined_context contains 'KEY CLAIMS'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(
            topic_brief={
                "key_claims": [
                    "Prompt caching reduces input token cost by 90% on cache hits.",
                    "Haiku is 10× cheaper than Sonnet for the same token count.",
                    "Batch API reduces cost by 50% for non-real-time workloads.",
                ],
            }
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")
            assert (
                "KEY CLAIMS" in combined_context
            ), f"Expected 'KEY CLAIMS' in combined_context, got: {combined_context[:300]}"

    @pytest.mark.asyncio
    async def test_content_generation_injects_concession_into_context(self) -> None:
        """When topic_brief has concession, combined_context contains 'REQUIRED CONCESSION'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(
            topic_brief={
                "concession": "Prompt caching only activates above 1,024 input tokens — below that threshold you get no benefit.",
            }
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")
            assert (
                "REQUIRED CONCESSION" in combined_context
            ), f"Expected 'REQUIRED CONCESSION' in combined_context, got: {combined_context[:300]}"

    @pytest.mark.asyncio
    async def test_content_generation_no_editorial_block_when_no_topic_brief(
        self,
    ) -> None:
        """When topic_brief is None, combined_context does NOT contain 'EDITORIAL STRUCTURE'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(topic_brief=None)

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")
            assert (
                "EDITORIAL STRUCTURE" not in combined_context
            ), f"'EDITORIAL STRUCTURE' must not appear when topic_brief is None, got: {combined_context[:300]}"

    @pytest.mark.asyncio
    async def test_content_generation_editorial_block_precedes_grounding(self) -> None:
        """When both topic_brief and grounding_context are set, 'EDITORIAL STRUCTURE' appears before 'USER-PROVIDED GROUNDING CONTEXT'."""
        from app.agents.orchestrator import content_generation_node

        state = _minimal_state(
            grounding_context="Real data: we run 50k LLM calls/day on Haiku with p95 latency of 1.2s.",
            topic_brief={
                "hook_seed": "Our infra bill dropped 78% after one config change.",
                "key_claims": [
                    "Prompt caching yields 90% cost reduction on cache hits."
                ],
            },
        )

        p_gen, p_log, p_exemplar, p_upsert = _patch_content_generation_deps()
        with p_gen as mock_gen, p_log, p_exemplar, p_upsert:
            await content_generation_node(state)  # type: ignore[arg-type]

            mock_gen.assert_awaited_once()
            _, kwargs = mock_gen.call_args
            combined_context = kwargs.get("trend_context", "")

            assert (
                "EDITORIAL STRUCTURE" in combined_context
            ), "combined_context must contain EDITORIAL STRUCTURE when topic_brief is set"
            assert (
                "USER-PROVIDED GROUNDING CONTEXT" in combined_context
            ), "combined_context must contain USER-PROVIDED GROUNDING CONTEXT when grounding_context is set"

            editorial_pos = combined_context.index("EDITORIAL STRUCTURE")
            grounding_pos = combined_context.index("USER-PROVIDED GROUNDING CONTEXT")
            assert editorial_pos < grounding_pos, (
                f"EDITORIAL STRUCTURE (pos {editorial_pos}) must precede "
                f"USER-PROVIDED GROUNDING CONTEXT (pos {grounding_pos})"
            )
