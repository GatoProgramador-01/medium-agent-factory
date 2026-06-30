from typing import Any, Dict

import app.agents.close_optimizer as _close_optimizer_module


async def close_optimization_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Replaces the post's last paragraph with a stronger, more specific close.

    The Story (El Relato):
    In the story of our pipeline, this node is the Closings Director.
    The final paragraph is the reader's last impression of the article and dictates whether
    they share it or execute the Call to Action (CTA). Instead of a generic summary conclusion,
    this node reviews the post content and refined angle, generates multiple alternative, high-impact
    conclusions, and substitutes the last paragraph of the article with the most compelling variant.

    The Flow (El Flujo):
    1. Retrieve the post's content and refined editorial angle from the state.
    2. Invoke the close optimizer module (`run_close_optimization`) to generate alternative closings.
    3. Split the content into paragraphs and locate the last non-empty paragraph.
    4. Replace the last paragraph with the optimized close.
    5. Save the updated content in the post object and return the updated draft content.
    6. Fall back gracefully to the original closing paragraph if an exception is encountered.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with "draft_content" (post content with replaced close) on success,
        or empty dict on any exception so the pipeline keeps the original close.
    """
    run_id = state["run_id"]
    post = state.get("post")
    content = post.content if post else state.get("draft_content", "")
    if not content:
        return {}

    topic_brief: dict[str, Any] | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    try:
        result = await _close_optimizer_module.run_close_optimization(
            run_id=run_id,
            content=content,
            refined_angle=refined_angle or "",
        )

        # Replace last non-empty paragraph with the best close
        paragraphs = content.split("\n\n")
        last_idx = len(paragraphs) - 1
        while last_idx > 0 and not paragraphs[last_idx].strip():
            last_idx -= 1
        paragraphs[last_idx] = result.best_close
        updated_content = "\n\n".join(paragraphs)

        if post:
            post.content = updated_content

        return {"draft_content": updated_content}
    except Exception:
        return {}
