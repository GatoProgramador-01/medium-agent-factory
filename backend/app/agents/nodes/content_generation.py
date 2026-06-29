from typing import Any, Dict
from app.config import settings
from app.agents.logger import log_step
from app.models.post import PostStatus
from app.agents.content_generator import (
    generate_initial_post,
    enforce_paragraph_sentence_limit,
)
from app.agents.exemplar_store import find_exemplar, format_exemplar_injection

async def content_generation_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generates the initial draft Medium post using Claude Haiku.

    The Story (El Relato):
    In the story of our pipeline, this node represents the Staff Writer.
    Equipped with the structured editorial brief from the Chief Editor, this node writes
    the very first full draft. It looks through our store of previous high-scoring articles
    (exemplars) to learn the tone, pacing, and formatting styles that perform best.
    It then combines the repository evidence and web research to write a complete post,
    enforcing specific structural guidelines, claims, and concessions, and ensuring that
    no forbidden AI filler words find their way into the text.

    The Flow (El Flujo):
    1. Log that the writer is starting the initial draft.
    2. Query the exemplar store for past articles similar to the refined topic to use as few-shot guides.
    3. Merge grounding context, web research context, and the editorial structure locks (hook seed, H2 order, claims, and concession).
    4. Call `generate_initial_post` with the target audience and prompt templates.
    5. Save the generated post to MongoDB and return it in the pipeline state.
    6. Catch failures, logging details and returning errors to stop the pipeline if drafting fails.

    Args:
        state: Pipeline state with "custom_topic", "grounding_context",
            "trend_context", and "series_context" (if series post).

    Returns:
        Dict with "post" (GeneratedPost), "revision_count" (0), and
        "completed_steps" log. Or "errors" dict on failure.
    """
    run_id = state["run_id"]
    topic = state.get("refined_topic") or state["custom_topic"]

    await log_step(
        run_id,
        "content_generator",
        f'Generating initial draft (Claude Haiku)...',
        data={"model": settings.worker_model, "topic": state["custom_topic"]},
    )
    try:
        # 1. Look for high-performing few-shot examples
        exemplar_section = await _fetch_and_format_exemplar(topic, run_id)

        # 2. Extract and compile editorial locks from topic brief
        topic_brief_dict = state.get("topic_brief") or {}
        editorial_block = _build_editorial_locks_block(topic_brief_dict)

        # 3. Combine user notes and web research with editorial locks
        combined_context = _merge_context_sources(state, editorial_block)

        # 4. Generate post via model
        audience = topic_brief_dict.get("target_audience") or "software engineers and developers building LLM agents and AI pipelines"
        post = await generate_initial_post(
            run_id=run_id,
            topic=topic,
            trend_context=combined_context,
            tags=[],
            audience=audience,
            exemplar_section=exemplar_section,
            series_context=state.get("series_context", ""),
        )

        # 5. Save the post draft to MongoDB
        from app.agents.orchestrator import _upsert_post
        await _upsert_post(run_id, post, PostStatus.DRAFT, revision_count=0)

        return {
            "post": post,
            "revision_count": 0,
            "completed_steps": ["content_generation"],
        }
    except Exception as e:
        await log_step(run_id, "content_generator", f"Failed: {e}", level="error")
        return {"errors": [f"content_generation failed: {e}"]}


async def _fetch_and_format_exemplar(topic: str, run_id: str) -> str:
    """Finds and formats a past high-scoring post as few-shot context."""
    exemplar = await find_exemplar(topic)
    if exemplar:
        await log_step(
            run_id,
            "content_generator",
            f'Exemplar found: "{exemplar["title"]}" '
            f'(score {exemplar["score"]:.2f}) — injecting as few-shot reference',
            data={
                "exemplar_title": exemplar["title"],
                "exemplar_score": exemplar["score"],
            },
        )
        return format_exemplar_injection(exemplar)
    return ""


def _build_editorial_locks_block(topic_brief: dict) -> str:
    """Compiles the Chief Editor's non-negotiable structural constraints."""
    parts = []
    if topic_brief.get("hook_seed"):
        parts.append(
            "HOOK SEED (use as opening sentence — adapt slightly, preserve the specific outcome/number):\n"
            f"{topic_brief['hook_seed']}"
        )
    if topic_brief.get("h2_structure"):
        h2_lines = "\n".join(
            f"  {i + 1}. {h}" for i, h in enumerate(topic_brief["h2_structure"])
        )
        parts.append(f"H2 STRUCTURE (use in this exact order):\n{h2_lines}")
    if topic_brief.get("key_claims"):
        claims_lines = "\n".join(f"  - {c}" for c in topic_brief["key_claims"])
        parts.append(
            f"KEY CLAIMS (cite at least 3 — never invent statistics outside this list):\n{claims_lines}"
        )
    if topic_brief.get("concession"):
        parts.append(
            "REQUIRED CONCESSION (place in section 3 or 4 — name the exact threshold):\n"
            f"{topic_brief['concession']}"
        )
    if parts:
        return "EDITORIAL STRUCTURE (non-negotiable):\n\n" + "\n\n".join(parts)
    return ""


def _merge_context_sources(state: dict, editorial_block: str) -> str:
    """Merges grounding context and research results with editorial brief blocks."""
    grounding_context = state.get("grounding_context", "").strip()
    trend_context = state.get("trend_context", "").strip()
    
    parts = []
    if grounding_context:
        parts.append(
            "USER-PROVIDED GROUNDING CONTEXT (treat as source notes, not prose to copy):\n"
            f"{grounding_context}"
        )
    if trend_context:
        parts.append(
            "WEB RESEARCH CONTEXT (use only when relevant and cite URLs):\n"
            f"{trend_context}"
        )
        
    combined = "\n\n".join(parts)
    if editorial_block:
        combined = "\n\n".join(filter(None, [editorial_block, combined]))
    return combined
