from typing import Any, Dict
from app.agents.logger import log_step
from app.agents.topic_refiner import run_topic_refinement

async def topic_refinement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Refines raw topic + research into a structured editorial brief.

    The Story (El Relato):
    In the story of our pipeline, this node acts as the Chief Editor.
    A raw topic and random web search results are too disorganized for direct writing.
    This node calls upon Claude Sonnet (our supervisor model) to synthesize the raw topic,
    user-provided source notes, and web research into a cohesive "Topic Brief". It decides the
    optimal contrarian angle, determines the target audience, designs the exact H2 heading outline,
    identifies key claims to support, and creates a compelling hook seed. This ensures the
    downstream writer is constrained by a professional, strategic editorial plan.

    The Flow (El Flujo):
    1. Log the initiation of topic refinement.
    2. Extract custom topic, trend context, grounding context, and repository evidence brief.
    3. Invoke `run_topic_refinement` using the supervisor model (Sonnet) to construct the structured editorial plan.
    4. Log the generated brief's details (such as the target audience and refined angle).
    5. Return the formatted brief string and the structured dictionary to the pipeline state.
    6. Fall back gracefully to the raw topic if refinement fails.

    Args:
        state: Pipeline state with "custom_topic", "trend_context", and optionally
            "grounding_context".

    Returns:
        Dict with "refined_topic" (formatted_brief string) and "topic_brief" (dict).
        On error, falls back: "refined_topic" = custom_topic, "topic_brief" = None.
    """
    run_id = state.get("run_id", "unknown")
    topic = state.get("custom_topic", "")
    research_results = state.get("trend_context", "")
    grounding_context = state.get("grounding_context", "")
    raw_brief = state.get("evidence_brief") or {}
    evidence_brief_str = (
        "\n".join(f"- {k}: {v}" for k, v in raw_brief.items()) if raw_brief else ""
    )

    await log_step(
        run_id,
        "topic_refiner",
        f'Refining topic and research into editorial brief: "{topic}"...',
        data={"topic": topic},
    )

    try:
        brief = await run_topic_refinement(
            run_id=run_id,
            topic=topic,
            research_results=research_results,
            grounding_context=grounding_context,
            evidence_brief=evidence_brief_str,
        )
        await log_step(
            run_id,
            "topic_refiner",
            f'Topic brief generated: angle="{brief.refined_angle[:50]}...", target_audience="{brief.target_audience}"',
            level="success",
            data={"refined_angle": brief.refined_angle, "hook_seed": brief.hook_seed},
        )
        return {
            "refined_topic": brief.formatted_brief,
            "topic_brief": brief.model_dump(),
            "completed_steps": ["topic_refinement"],
        }
    except Exception as e:
        # Fallback: if refinement fails, use raw topic (pipeline must not stop)
        await log_step(
            run_id,
            "topic_refiner",
            f"Topic refinement skipped: {e} — using raw topic",
            level="warning",
        )
        return {
            "refined_topic": topic,
            "topic_brief": None,
            "completed_steps": ["topic_refinement_skipped"],
        }
