from typing import Any, Dict

async def series_coherence_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Checks whether a series installment fits its assigned series role.

    The Story (El Relato):
    In the story of our pipeline, this node is the Series Continuity Director.
    When publishing a multi-part series, individual posts must connect seamlessly.
    This node checks if the current post matches the surrounding context of siblings,
    ensures terminology is used consistently across posts, verifies that callbacks to
    previous parts are correctly addressed, and checks if position numbering is correct.
    If it detects discrepancies, it suggests inline adjustments to preserve narrative
    cohesion.

    The Flow (El Flujo):
    1. Verify if the post is part of a series (`series_context` is set). If not, skip as a no-op.
    2. Extract position, context, and refined angle from the state.
    3. Run `run_series_coherence_check` against sibling posts.
    4. If the check returns revised content, replace the draft body with the revised version.
    5. Log the series coherence score, issues found, and continuity notes.
    6. Return the updated post and coherence score, falling back to original if errors occur.

    Args:
        state: Pipeline state with optional "series_context" and "post".

    Returns:
        Dict with "series_coherence_score", optional updated "post", and
        "completed_steps". Returns empty dict for standalone posts or errors.
    """
    from app.agents.orchestrator import (
        log_step,
        run_series_coherence_check,
        enforce_paragraph_sentence_limit,
    )

    run_id = state["run_id"]
    post = state.get("post")
    series_context = state.get("series_context", "")
    if not post or not series_context:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "series_coherence_checker",
        "Checking series continuity and installment scope...",
        data={"series_position": state.get("series_position")},
    )

    try:
        result = await run_series_coherence_check(
            run_id=run_id,
            title=post.title,
            content=post.content,
            series_context=series_context,
            series_position=state.get("series_position"),
            refined_angle=refined_angle or "",
        )
        if result.revised_content.strip():
            post = post.model_copy(deep=True)
            post.content = enforce_paragraph_sentence_limit(result.revised_content)

        await log_step(
            run_id,
            "series_coherence_checker",
            f"Series coherence score: {result.coherence_score:.2f}",
            level="success" if result.coherence_score >= 0.75 else "warning",
            data={
                "coherence_score": result.coherence_score,
                "issues": [i.model_dump() for i in result.issues],
                "continuity_notes": result.continuity_notes,
                "content_revised": bool(result.revised_content.strip()),
            },
        )
        return {
            "post": post,
            "series_coherence_score": result.coherence_score,
            "completed_steps": ["series_coherence"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "series_coherence_checker",
            f"Series coherence check skipped: {e}",
            level="warning",
        )
        return {}
