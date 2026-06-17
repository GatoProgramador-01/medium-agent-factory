"""
Orchestrator — LangGraph pipeline

Graph:
  START
    │
    ▼
  research                (WebResearcher — Tavily search + LLM synthesis; skips gracefully)
    │
    ▼
  content_generation      (ContentGeneratorAgent — Haiku initial draft)
    │
    ▼
  quality_analysis        (QualityAnalyzerAgent — Haiku, scores raw content)
    │
    ├─── score >= 0.90 ──→ format ──→ finalize → END
    │
    └─── score < 0.90 AND revisions < max
              revision_count=1 → Haiku revision
              revision_count=2 → Sonnet revision
              revision_count=3 → Sonnet final attempt
                │
                ▼
          quality_analysis (loop back)
                │
          score >= 0.90 OR revisions exhausted
                │
                ▼
             format (runs ONCE on the final approved version)
                │
                ▼
           finalize → END

Cost note: format (Haiku ~$0.002) runs exactly once regardless of revision count.
"""

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.content_generator import (
    GeneratedPost,
    generate_initial_post,
    revise_post,
)
from app.agents.formatter import format_post
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis
from app.agents.series_planner import plan_series
from app.agents.web_researcher import research_topic
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityReport


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str
    series_id: str | None
    series_position: int | None
    trend_context: str  # populated by research_node; "" when Tavily unavailable

    post: GeneratedPost | None
    quality_report: QualityReport | None
    pull_quote: str | None
    format_changes: Annotated[list[str], operator.add]
    revision_count: int
    quality_history: Annotated[list[dict[str, Any]], operator.add]  # score per cycle
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def research_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    topic = state["custom_topic"]

    await log_step(
        run_id,
        "web_researcher",
        f'Searching web for grounded data on: "{topic}"...',
        data={"topic": topic},
    )
    try:
        trend_context = await research_topic(run_id=run_id, topic=topic)
        if trend_context:
            fact_count = trend_context.count("•")
            await log_step(
                run_id,
                "web_researcher",
                f"Research complete — {fact_count} data points ready for the writer",
                level="success",
                data={"preview": trend_context[:300]},
            )
        else:
            await log_step(
                run_id,
                "web_researcher",
                "No web context available (Tavily key missing or no results) — continuing",
                level="warning",
            )
        return {"trend_context": trend_context, "completed_steps": ["research"]}
    except Exception as e:
        await log_step(run_id, "web_researcher", f"Research skipped: {e}", level="warning")
        return {"trend_context": "", "completed_steps": ["research"]}


async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    topic = state["custom_topic"]

    await log_step(
        run_id,
        "content_generator",
        f'Generating initial draft for topic: "{topic}" (Claude Haiku)...',
        data={"model": settings.worker_model, "topic": topic},
    )
    try:
        post = await generate_initial_post(
            run_id=run_id,
            topic=topic,
            trend_context=state.get("trend_context", ""),
            tags=[],
            audience="content creators and professionals",
        )
        word_count = len(post.content.split())
        await log_step(
            run_id,
            "content_generator",
            f'Draft generated: "{post.title}" (~{word_count} words)',
            level="success",
            data={"title": post.title, "word_count": word_count, "tags": post.tags},
        )
        await _upsert_post(
            run_id,
            post,
            PostStatus.DRAFT,
            series_id=state.get("series_id"),
            series_position=state.get("series_position"),
        )
        return {
            "post": post,
            "revision_count": 0,
            "completed_steps": ["content_generation"],
        }
    except Exception as e:
        await log_step(run_id, "content_generator", f"Failed: {e}", level="error")
        return {"errors": [f"content_generation failed: {e}"]}


async def quality_analysis_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "quality_analyzer", "No post to analyze", level="error")
        return {"errors": ["quality_analysis: no post"]}

    await log_step(
        run_id,
        "quality_analyzer",
        "Analyzing post for AI patterns and readability issues...",
    )
    try:
        report = await run_quality_analysis(
            run_id=run_id, title=post.title, content=post.content
        )

        passed = report.score >= settings.min_quality_score
        level = "success" if passed else "warning"
        boost_label = "Boost-eligible" if report.medium_boost_eligible else "NOT Boost-eligible"
        verdict = (
            f"Passed threshold ({settings.min_quality_score}). "
            f"Predicted read ratio: {report.read_ratio_prediction * 100:.0f}%. {boost_label}."
            if passed
            else f"Below threshold ({settings.min_quality_score}). "
            f"Found {len(report.issues)} issues. {boost_label}. Queuing revision."
        )
        await log_step(
            run_id,
            "quality_analyzer",
            f"Quality score: {report.score:.2f}/1.0 — {verdict}",
            level=level,
            data={
                "score": report.score,
                "read_ratio_prediction": report.read_ratio_prediction,
                "medium_boost_eligible": report.medium_boost_eligible,
                "passed": passed,
                "issue_count": len(report.issues),
                "top_issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues[:3]
                ],
                "strengths": report.strengths,
            },
        )

        db = get_db()
        await db.posts.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "quality_report": {
                        "score": report.score,
                        "read_ratio_prediction": report.read_ratio_prediction,
                        "medium_boost_eligible": report.medium_boost_eligible,
                        "issues": [
                            {
                                "category": i.category,
                                "severity": i.severity,
                                "location": i.location,
                                "suggestion": i.suggestion,
                            }
                            for i in report.issues
                        ],
                        "strengths": report.strengths,
                        "revision_prompt": report.revision_prompt,
                    }
                }
            },
        )
        cycle = state.get("revision_count", 0)
        history_entry: dict[str, Any] = {
            "cycle": cycle,
            "score": report.score,
            "read_ratio": report.read_ratio_prediction,
            "boost_eligible": report.medium_boost_eligible,
            "issue_count": len(report.issues),
            "passed": report.score >= settings.min_quality_score,
        }
        return {
            "quality_report": report,
            "quality_history": [history_entry],
            "completed_steps": ["quality_analysis"],
        }
    except Exception as e:
        await log_step(run_id, "quality_analyzer", f"Failed: {e}", level="error")
        return {"errors": [f"quality_analysis failed: {e}"]}


async def content_revision_node(state: PipelineState) -> dict[str, Any]:
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

    # revision_number determines model: 1 → Haiku, 2 → Sonnet
    model = settings.worker_model if revision_number < 2 else settings.supervisor_model
    model_label = (
        "Claude Haiku" if revision_number < 2 else "Claude Sonnet (quality upgrade)"
    )
    max_rev = settings.max_revision_cycles

    await log_step(
        run_id,
        "content_generator",
        f"Revision {revision_number}/{max_rev} — rewriting with {model_label}...",
        data={
            "revision_number": revision_number,
            "model": model,
            "score_before": report.score,
        },
    )
    try:
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
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
            revision_number=revision_number,
        )
        word_count = len(revised.content.split())
        await log_step(
            run_id,
            "content_generator",
            f"Revision {revision_number} complete: "
            f'"{revised.title}" (~{word_count} words)',
            level="success",
            data={"title": revised.title, "word_count": word_count},
        )
        await _upsert_post(
            run_id, revised, PostStatus.REVISED, revision_count=revision_number
        )
        return {
            "post": revised,
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


async def format_node(state: PipelineState) -> dict[str, Any]:
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
        result = await format_post(run_id=run_id, title=post.title, content=post.content)

        # Patch the post content in-place so finalize_node sees the formatted version
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


async def finalize_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    qr = state.get("quality_report")
    history = state.get("quality_history", [])
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": {
            "status": str(PostStatus.APPROVED),
            "quality_history": history,
            "revision_count": state.get("revision_count", 0),
            "updated_at": datetime.now(UTC),
        }},
    )
    await _update_pipeline_run(state, "approved")
    score_msg = f" Final quality score: {qr.score:.2f}" if qr else ""
    cycles_msg = f" Revision cycles: {state.get('revision_count', 0)}/{settings.max_revision_cycles}."
    await log_step(
        run_id, "orchestrator", f"Post approved and saved.{score_msg}{cycles_msg}", level="success"
    )
    return {"completed_steps": ["finalized"]}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)
    errors = state.get("errors", [])
    # Any accumulated errors (e.g. failed revision or quality call) → bail to finalize
    if errors:
        return "finalize"
    if not report or report.score >= settings.min_quality_score:
        return "finalize"
    if revisions >= settings.max_revision_cycles:
        return "finalize"
    return "revision"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_graph() -> Any:
    g = StateGraph(PipelineState)
    g.add_node("research", research_node)
    g.add_node("content_generation", content_generation_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("format", format_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "research")
    g.add_edge("research", "content_generation")
    g.add_edge("content_generation", "quality_analysis")
    g.add_conditional_edges(
        "quality_analysis",
        route_after_quality,
        {"finalize": "format", "revision": "revision"},
    )
    g.add_edge("revision", "quality_analysis")
    g.add_edge("format", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


pipeline = build_graph()


# ── Public entrypoint ──────────────────────────────────────────────────────────


async def run_pipeline(
    custom_topic: str,
    run_id: str | None = None,
    series_id: str | None = None,
    series_position: int | None = None,
) -> dict[str, Any]:
    db = get_db()

    if run_id:
        await db.pipeline_runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "running", "started_at": datetime.now(UTC)}},
        )
    else:
        run_id = str(uuid.uuid4())
        await db.pipeline_runs.insert_one(
            {
                "run_id": run_id,
                "custom_topic": custom_topic,
                "status": "running",
                "created_at": datetime.now(UTC),
            }
        )
    await log_step(run_id, "orchestrator", f'Pipeline started. Topic: "{custom_topic}"')

    initial_state: PipelineState = {
        "run_id": run_id,
        "custom_topic": custom_topic,
        "series_id": series_id,
        "series_position": series_position,
        "trend_context": "",
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "errors": [],
        "completed_steps": [],
    }

    final_state = await pipeline.ainvoke(initial_state)

    status = "failed" if final_state.get("errors") else "completed"
    await db.pipeline_runs.update_one(
        {"run_id": run_id},
        {"$set": {"status": status, "completed_at": datetime.now(UTC)}},
    )

    if status == "failed":
        await log_step(
            run_id,
            "orchestrator",
            f"Pipeline failed: {'; '.join(final_state.get('errors', []))}",
            level="error",
        )
    else:
        await log_step(
            run_id, "orchestrator", "Pipeline completed successfully.", level="success"
        )

    post = final_state.get("post")
    qr = final_state.get("quality_report")
    return {
        "run_id": run_id,
        "status": status,
        "title": post.title if post else None,
        "quality_score": qr.score if qr else None,
        "read_ratio_prediction": qr.read_ratio_prediction if qr else None,
        "medium_boost_eligible": qr.medium_boost_eligible if qr else None,
        "pull_quote": final_state.get("pull_quote"),
        "format_changes": final_state.get("format_changes", []),
        "revision_count": final_state.get("revision_count", 0),
        "errors": final_state.get("errors", []),
        "steps": final_state.get("completed_steps", []),
    }


async def run_series(
    theme: str,
    context: str = "",
    series_id: str | None = None,
) -> dict[str, Any]:
    """Plan and run a multi-post series. Posts execute sequentially."""
    db = get_db()
    series_id = series_id or str(uuid.uuid4())

    # ── Step 1: plan ──────────────────────────────────────────────────────────
    plan_run_id = f"{series_id}-planner"
    await log_step(plan_run_id, "series_planner", f'Planning series for theme: "{theme}"')

    plan = await plan_series(run_id=plan_run_id, theme=theme, context=context)

    await log_step(
        plan_run_id,
        "series_planner",
        f'Series planned: "{plan.series_title}" — {len(plan.posts)} posts',
        level="success",
        data={
            "series_title": plan.series_title,
            "series_description": plan.series_description,
            "posts": [
                {"position": p.position, "angle": p.angle} for p in plan.posts
            ],
        },
    )

    await db.series.update_one(
        {"series_id": series_id},
        {
            "$set": {
                "theme": theme,
                "series_title": plan.series_title,
                "series_description": plan.series_description,
                "post_count": len(plan.posts),
                "status": "running",
            },
            "$setOnInsert": {"run_ids": [], "created_at": datetime.now(UTC)},
        },
        upsert=True,
    )

    # ── Step 2: generate each post sequentially ───────────────────────────────
    results = []
    run_ids = []

    for post_plan in sorted(plan.posts, key=lambda p: p.position):
        await log_step(
            plan_run_id,
            "series_planner",
            f"Starting post {post_plan.position}/{len(plan.posts)}: {post_plan.angle}",
        )
        result = await run_pipeline(
            custom_topic=post_plan.topic,
            series_id=series_id,
            series_position=post_plan.position,
        )
        results.append(result)
        run_ids.append(result["run_id"])

        await db.series.update_one(
            {"series_id": series_id},
            {"$push": {"run_ids": result["run_id"]}},
        )

        await log_step(
            plan_run_id,
            "series_planner",
            f'Post {post_plan.position} done: "{result.get("title","")}" '
            f'(score={result.get("quality_score","?")}, boost={result.get("medium_boost_eligible","?")})',
            level="success" if result["status"] == "completed" else "error",
        )

    series_status = "completed" if all(r["status"] == "completed" for r in results) else "failed"
    await db.series.update_one(
        {"series_id": series_id},
        {"$set": {"status": series_status, "completed_at": datetime.now(UTC)}},
    )

    return {
        "series_id": series_id,
        "series_title": plan.series_title,
        "series_description": plan.series_description,
        "status": series_status,
        "posts": results,
    }


# ── DB helpers ─────────────────────────────────────────────────────────────────


async def _upsert_post(
    run_id: str,
    post: GeneratedPost,
    status: PostStatus,
    revision_count: int = 0,
    pull_quote: str | None = None,
    format_changes: list[str] | None = None,
    series_id: str | None = None,
    series_position: int | None = None,
) -> None:
    db = get_db()
    fields: dict[str, Any] = {
        "run_id": run_id,
        "topic": post.title,
        "title": post.title,
        "subtitle": post.subtitle,
        "content": post.content,
        "tags": post.tags,
        "image_suggestions": post.image_suggestions,
        "status": str(status),
        "revision_count": revision_count,
        "updated_at": datetime.now(UTC),
    }
    if pull_quote is not None:
        fields["pull_quote"] = pull_quote
    if format_changes is not None:
        fields["format_changes"] = format_changes
    if series_id is not None:
        fields["series_id"] = series_id
    if series_position is not None:
        fields["series_position"] = series_position
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": fields, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
    )


async def _update_pipeline_run(state: PipelineState, status: str) -> None:
    db = get_db()
    await db.pipeline_runs.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
    )
