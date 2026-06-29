from typing import Any, Dict

async def intro_ab_testing_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Replaces the draft opening with the strongest A/B-tested intro.

    The Story (El Relato):
    In the story of our pipeline, this node is the Hook Optimization Lab.
    Even with a great title, readers will click away within seconds if the opening
    paragraph fails to grab their attention. This node takes the initial paragraph of
    the draft and tests it against outcomes, scenes, and failures. It runs a fast
    A/B test using our worker model to score alternative intros against the read-ratio
    rubric, ensuring the post begins with an immediate, high-impact hook.

    The Flow (El Flujo):
    1. Extract the draft post and its refined editorial angle from the pipeline state.
    2. Split the content into paragraphs to isolate the first non-empty introductory paragraph.
    3. Run the introductory A/B test agent (`run_intro_ab_test`) to generate alternative variations.
    4. Select the highest-performing intro variant and swap it with the original opening paragraph.
    5. Re-enforce sentence lengths and log the optimization outcomes.
    6. Return the updated post with intro variants. If a failure occurs, fall back to the original draft.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with updated "post", "intro_variants", and "completed_steps".
        Returns empty dict on error so the original intro is preserved.
    """
    from app.agents.orchestrator import log_step, run_intro_ab_test, enforce_paragraph_sentence_limit

    run_id = state["run_id"]
    post = state.get("post")
    if not post or not post.content:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "intro_ab_tester",
        "Testing alternate openings for hook strength...",
        data={"title": post.title},
    )

    try:
        result = await run_intro_ab_test(
            run_id=run_id,
            title=post.title,
            content=post.content,
            refined_angle=refined_angle or "",
        )

        post = post.model_copy(deep=True)
        paragraphs = post.content.split("\n\n")
        first_idx = next((i for i, p in enumerate(paragraphs) if p.strip()), 0)
        original_intro = paragraphs[first_idx]
        paragraphs[first_idx] = result.best_intro
        post.content = enforce_paragraph_sentence_limit("\n\n".join(paragraphs))
        intro_variants = [v.text for v in result.variants]

        await log_step(
            run_id,
            "intro_ab_tester",
            f"Opening strengthened ({len(result.variants)} variants tested).",
            level="success",
            data={
                "original_intro": original_intro[:500],
                "best_intro": result.best_intro,
                "original_intro_problem": result.original_intro_problem,
            },
        )
        return {
            "post": post,
            "intro_variants": intro_variants,
            "completed_steps": ["intro_ab_testing"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "intro_ab_tester",
            f"Intro A/B test skipped: {e} - keeping original opening",
            level="warning",
        )
        return {}
