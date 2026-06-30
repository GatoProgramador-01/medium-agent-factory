from typing import Any, Dict

from app.agents.image_description_enricher import run_image_description_enrichment
from app.agents.logger import log_step


async def image_description_enrichment_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Improves image placeholders and image suggestions before formatting.

    The Story (El Relato):
    In the story of our pipeline, this node is the Visual Illustrator.
    Articles without relevant visual guides fail to keep the reader's attention. Throughout the draft,
    the writer inserts simple image placeholders. This node scans those placeholders, reads the context window
    around them, and rewrites the descriptions, alt texts, and captions to be specific, professional, and visually
    descriptive of the surrounding concepts. It also enriches visual suggestions to feed future image generators.

    The Flow (El Flujo):
    1. Log the initiation of image description enrichment.
    2. Retrieve the post, its image suggestions list, and the refined topic angle.
    3. Call the image enrichment runner (`run_image_description_enrichment`) in a single LLM call.
    4. Iterate over the resulting enriched image descriptors, replacing the simple placeholders in the post's content with detailed specifications.
    5. Update the post's global image suggestions list.
    6. Return the modified post and a log of the changes. Fails open to preserve placeholders on error.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with updated "post", "image_enrichment_changes", and
        "completed_steps". Returns empty dict on error.
    """
    run_id = state["run_id"]
    post = state.get("post")
    if not post or not post.content:
        return {}

    topic_brief: dict[str, Any] | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "image_description_enricher",
        "Enriching image placeholders and alt text...",
        data={"suggestion_count": len(post.image_suggestions or [])},
    )

    try:
        result = await run_image_description_enrichment(
            run_id=run_id,
            title=post.title,
            content=post.content,
            image_suggestions=post.image_suggestions or [],
            refined_angle=refined_angle or "",
        )

        changes: list[str] = []
        updated_content = post.content
        for image in result.images:
            original = image.original_placeholder.strip()
            if not original or original not in updated_content:
                continue
            replacement = (
                f"[IMAGE: {image.description} | alt: {image.alt_text}"
                + (f" | caption: {image.caption}" if image.caption else "")
                + "]"
            )
            updated_content = updated_content.replace(original, replacement, 1)
            changes.append(f"enriched image: {image.description[:80]}")

        if result.image_suggestions:
            post.image_suggestions = result.image_suggestions
            changes.append("updated image suggestions")

        post.content = updated_content

        await log_step(
            run_id,
            "image_description_enricher",
            f"Image enrichment complete ({len(changes)} change(s)).",
            level="success",
            data={"changes": changes},
        )
        return {
            "post": post,
            "image_enrichment_changes": changes,
            "completed_steps": ["image_description_enrichment"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "image_description_enricher",
            f"Image enrichment skipped: {e}",
            level="warning",
        )
        return {}
