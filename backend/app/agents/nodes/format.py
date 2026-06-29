from typing import Any, Dict
from app.agents.logger import log_step
from app.models.post import PostStatus
from app.agents.fact_checker import inject_hyperlinks
from app.agents.formatter import format_post

async def format_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Applies deterministic formatting to the final approved post version.

    The Story (El Relato):
    In the story of our pipeline, this node is the Post Typographer and Formatter.
    After the content has passed all quality checks, it needs to look like a professionally
    published article. Revision loops often rewrite phrases and disrupt hyperlinks, so this
    node starts by re-injecting the verified source links into the final text. Then, it applies
    formatting: it splits overly long paragraphs to keep the reader engaged, adds visual section
    separators, and extracts a key pull quote for highlighting. It commits these final formatting
    changes to the state.

    The Flow (El Flujo):
    1. Retrieve the post and verification results from the state.
    2. Re-inject fact-checked hyperlinks into the final approved text.
    3. Run `format_post` using the formatting agent to structure paragraphs and extract a pull quote.
    4. Apply the formatted content back to the post object.
    5. Log the applied changes and the extracted pull quote.
    6. Save the final formatted post with an `APPROVED` status and return it.

    Args:
        state: Pipeline state with "post", "fact_check_results", "run_id",
            and "revision_count".

    Returns:
        Dict with "post" (formatted), "pull_quote" (str), "format_changes"
        (list of applied changes), and "completed_steps". Or "errors" on failure.
    """
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "formatter", "No post to format", level="error")
        return {"errors": ["format: no post"]}

    await log_step(
        run_id,
        "formatter",
        "Formatting final approved version: splitting long paragraphs, adding separator, extracting pull quote...",
    )
    try:
        # Re-inject source hyperlinks into the final approved content.
        fc_results = state.get("fact_check_results") or []
        if fc_results:
            post.content = inject_hyperlinks(post.content, fc_results)

        result = await format_post(
            run_id=run_id, title=post.title, content=post.content
        )

        post.content = result.formatted_content

        changes_summary = (
            f"{len(result.changes_applied)} change(s) applied"
            if result.changes_applied
            else "no structural changes needed"
        )
        await log_step(
            run_id,
            "formatter",
            f'Formatting complete — {changes_summary}. Pull quote: "{result.pull_quote[:80]}..."',
            level="success",
            data={
                "changes_applied": result.changes_applied,
                "pull_quote": result.pull_quote,
            },
        )
        from app.agents.orchestrator import _upsert_post
        await _upsert_post(
            run_id,
            post,
            PostStatus.APPROVED,
            revision_count=state.get("revision_count", 0),
            pull_quote=result.pull_quote,
            format_changes=result.changes_applied,
        )
        return {
            "post": post,
            "pull_quote": result.pull_quote,
            "format_changes": result.changes_applied,
            "completed_steps": ["formatted"],
        }
    except Exception as e:
        await log_step(run_id, "formatter", f"Failed: {e}", level="error")
        return {"errors": [f"format failed: {e}"]}
