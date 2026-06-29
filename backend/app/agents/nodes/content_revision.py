from typing import Any, Dict
from app.models.post import PostStatus
from app.agents.nodes.quality_analysis import _gate_check
from app.agents.read_ratio_analyzer import format_factors_breakdown
from app.agents.llm_factory import get_model_name as _get_model_name

async def content_revision_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Revises the post based on quality gate failures and the analyzer's feedback.

    The Story (El Relato):
    In the story of our pipeline, this node is the Post Editor & Rewriter.
    When an article fails the quality gates, we don't discard it. Instead, this node acts as the editor,
    refining the draft. It selects between two revision paths: if the post is simply too short, it runs
    an "Expansion Strategy" to safely append new grounded sections. If there are style, voice, or factual
    errors, it does a targeted rewrite. Crucially, it tracks previous revision history to identify
    "sticky" issues that the LLM failed to fix in prior cycles, highlighting them so the next revision is
    uniquely focused on breaking through those specific quality blocks.

    The Flow (El Flujo):
    1. Log the initiation of the revision cycle (e.g., Cycle 2 of 6).
    2. Analyze the gate failures. If ONLY word count is failing, calculate the word deficit and call `expand_post` to append a new section.
    3. If other quality criteria fail, aggregate prior cycle history into a warning block about unresolved ("sticky") issues.
    4. Call `revise_post` with the full feedback, prior history warning, and original draft.
    5. Save the revised draft to the database and return the updated post and incremented revision count.
    6. Return compilation errors if the model fails.

    Args:
        state: Pipeline state with "post", "quality_report", "revision_count",
            "run_id", and "quality_history".

    Returns:
        Dict with "post" (revised GeneratedPost), "revision_count" (incremented),
        and "completed_steps". Or "errors" dict on failure.
    """
    from app.agents.orchestrator import log_step, settings, expand_post, revise_post
    run_id = state["run_id"]
    post = state["post"]
    report = state["quality_report"]
    revision_number = state["revision_count"] + 1

    if not post or not report:
        await log_step(
            run_id,
            "content_generator",
            "Missing post or report for revision",
            level="error",
        )
        return {"errors": ["revision: missing post or quality report"]}

    model = _get_model_name("worker")
    max_rev = settings.max_revision_cycles

    await log_step(
        run_id,
        "content_generator",
        f"Revision {revision_number}/{max_rev} — rewriting with {model}...",
        data={
            "revision_number": revision_number,
            "model": model,
            "score_before": report.score,
        },
    )

    _, gate_failures = _gate_check(report)
    word_count_only = len(gate_failures) == 1 and "word count" in gate_failures[0]

    try:
        if word_count_only:
            # 1. Word count is the only deficit — apply expansion strategy
            post = await _execute_expansion_strategy(run_id, post, report, revision_number)
            return {
                "post": post,
                "revision_count": revision_number,
                "completed_steps": [f"revision_{revision_number}"],
            }
        else:
            # 2. General content or style issues — apply full rewrite strategy
            prior_cycle_summary = _build_sticky_issues_summary(state)
            revised_post = await _execute_rewrite_strategy(
                run_id, post, report, gate_failures, revision_number, prior_cycle_summary
            )
            return {
                "post": revised_post,
                "revision_count": revision_number,
                "completed_steps": [f"revision_{revision_number}"],
            }
    except Exception as e:
        await log_step(
            run_id,
            "content_generator",
            f"Revision {revision_number} failed: {e}",
            level="error",
        )
        return {"errors": [f"revision failed: {e}"]}


def _build_sticky_issues_summary(state: Dict[str, Any]) -> str:
    """Builds a summary of what previous cycles failed to fix to alert the reviser."""
    quality_history: list = state.get("quality_history", [])
    prior_cycle_summary = ""
    if len(quality_history) >= 2:
        lines = ["\u26a0 PRIOR REVISION HISTORY — THESE ISSUES WERE NOT RESOLVED:\n"]
        for entry in quality_history[:-1]:
            persisted = entry.get("issue_categories", [])
            if persisted:
                lines.append(
                    f"  Cycle {entry['cycle']}: score {entry['score']:.2f} — "
                    f"HIGH issues still present: {', '.join(persisted)}"
                )
        if len(lines) > 1:
            lines.append(
                "Fix the above categories FIRST in this revision — they have already "
                "survived at least one revision attempt and are blocking the quality gate.\n"
            )
            prior_cycle_summary = "\n".join(lines) + "\n"
    return prior_cycle_summary


async def _execute_expansion_strategy(run_id: str, post: Any, report: Any, revision_number: int) -> Any:
    """Generates a new paragraph section to append to the post for meeting word count targets."""
    from app.agents.orchestrator import expand_post, settings
    deficit = settings.min_word_count - report.word_count + 150  # 150-word buffer
    
    new_section = await expand_post(
        run_id=run_id,
        title=post.title,
        content=post.content,
        deficit=deficit,
    )
    post.content = post.content + "\n\n" + new_section
    word_count_new = len(post.content.split())
    
    from app.agents.orchestrator import log_step, _upsert_post
    await log_step(
        run_id,
        "content_generator",
        f"Revision {revision_number} complete (expand): "
        f'"{post.title}" (~{word_count_new} words)',
        level="success",
        data={"title": post.title, "word_count": word_count_new, "mode": "expand"},
    )
    await _upsert_post(run_id, post, PostStatus.REVISED, revision_count=revision_number)
    return post


async def _execute_rewrite_strategy(
    run_id: str,
    post: Any,
    report: Any,
    gate_failures: list,
    revision_number: int,
    prior_cycle_summary: str
) -> Any:
    """Applies targeted LLM edits based on quality and style failures."""
    rr_breakdown_text = format_factors_breakdown(
        report.read_ratio_prediction, report.read_ratio_factors
    )
    
    from app.agents.orchestrator import revise_post
    revised = await revise_post(
        run_id=run_id,
        title=post.title,
        content=post.content,
        score=report.score,
        revision_prompt=report.revision_prompt,
        issues=[
            {
                "category": i.category,
                "severity": i.severity,
                "location": i.location,
                "suggestion": i.suggestion,
            }
            for i in report.issues
        ],
        strengths=report.strengths,
        gate_failures=gate_failures,
        read_ratio_breakdown=rr_breakdown_text,
        revision_number=revision_number,
        prior_cycle_summary=prior_cycle_summary,
    )
    word_count = len(revised.content.split())
    
    from app.agents.orchestrator import log_step, _upsert_post
    await log_step(
        run_id,
        "content_generator",
        f"Revision {revision_number} complete: "
        f'"{revised.title}" (~{word_count} words)',
        level="success",
        data={"title": revised.title, "word_count": word_count},
    )
    await _upsert_post(run_id, revised, PostStatus.REVISED, revision_count=revision_number)
    return revised
