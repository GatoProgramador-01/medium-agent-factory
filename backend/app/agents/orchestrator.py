"""
Orchestrator — LangGraph pipeline

Graph:
  START
    │
    ▼
  trend_research          (TrendResearchAgent — Haiku)
    │
    ▼
  content_generation      (ContentGeneratorAgent — Haiku initial)
    │
    ▼
  quality_analysis        (QualityAnalyzerAgent — Haiku)
    │
    ├─── score >= threshold ──→ finalize
    │
    └─── score < threshold AND revisions < max
              revision_count=1 → Haiku revision
              revision_count=2 → Sonnet revision (last resort)
                │
                ▼
          quality_analysis (loop back)
  finalize → [publish] → END
"""

import uuid
from datetime import datetime, UTC
from typing import Annotated, Any
import operator

from langgraph.graph import StateGraph, END, START
from typing_extensions import TypedDict

from app.agents.content_generator import GeneratedPost, generate_initial_post, revise_post
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis
from app.agents.trend_researcher import TrendReport, run_trend_research
from app.agents.publisher import publish_to_medium
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityReport


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str | None
    publish_live: bool

    trend_report: TrendReport | None
    post: GeneratedPost | None
    quality_report: QualityReport | None
    revision_count: int
    medium_url: str | None
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def trend_research_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    topic = state.get("custom_topic")

    await log_step(run_id, "trend_researcher", "Searching for trending monetization topics...",
                   data={"custom_topic": topic})
    try:
        report = await run_trend_research(run_id=run_id, custom_topic=topic)
        await log_step(
            run_id, "trend_researcher",
            f"Found {len(report.opportunities)} opportunities. "
            f"Recommended: \"{report.recommended_topic}\"",
            level="success",
            data={
                "recommended_topic": report.recommended_topic,
                "tags": report.recommended_tags,
                "opportunities": [o.title for o in report.opportunities],
            },
        )
        return {"trend_report": report, "completed_steps": ["trend_research"]}
    except Exception as e:
        await log_step(run_id, "trend_researcher", f"Failed: {e}", level="error")
        return {"errors": [f"trend_research failed: {e}"]}


async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    trend = state["trend_report"]
    if not trend:
        await log_step(run_id, "content_generator", "No trend report — skipping", level="error")
        return {"errors": ["content_generation: no trend report"]}

    await log_step(
        run_id, "content_generator",
        "Generating initial draft with Claude Haiku (cheapest model)...",
        data={"model": settings.worker_model},
    )
    try:
        best = trend.opportunities[0] if trend.opportunities else None
        post = await generate_initial_post(
            run_id=run_id,
            topic=state.get("custom_topic") or trend.recommended_topic,
            trend_context=trend.market_context,
            tags=trend.recommended_tags,
            audience=best.target_audience if best else "content creators",
        )
        word_count = len(post.content.split())
        await log_step(
            run_id, "content_generator",
            f"Draft generated: \"{post.title}\" (~{word_count} words)",
            level="success",
            data={"title": post.title, "word_count": word_count, "tags": post.tags},
        )
        await _upsert_post(run_id, post, trend, PostStatus.DRAFT)
        return {"post": post, "revision_count": 0, "completed_steps": ["content_generation"]}
    except Exception as e:
        await log_step(run_id, "content_generator", f"Failed: {e}", level="error")
        return {"errors": [f"content_generation failed: {e}"]}


async def quality_analysis_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "quality_analyzer", "No post to analyze", level="error")
        return {"errors": ["quality_analysis: no post"]}

    await log_step(run_id, "quality_analyzer",
                   "Analyzing post for AI patterns and readability issues...")
    try:
        report = await run_quality_analysis(run_id=run_id, title=post.title, content=post.content)

        passed = report.score >= settings.min_quality_score
        level = "success" if passed else "warning"
        verdict = (
            f"Passed threshold ({settings.min_quality_score}). Predicted read ratio: "
            f"{report.read_ratio_prediction * 100:.0f}%"
            if passed
            else f"Below threshold ({settings.min_quality_score}). "
            f"Found {len(report.issues)} issues. Queuing revision."
        )
        await log_step(
            run_id, "quality_analyzer",
            f"Quality score: {report.score:.2f}/1.0 — {verdict}",
            level=level,
            data={
                "score": report.score,
                "read_ratio_prediction": report.read_ratio_prediction,
                "passed": passed,
                "issue_count": len(report.issues),
                "top_issues": [
                    {"severity": i.severity, "category": i.category, "suggestion": i.suggestion}
                    for i in report.issues[:3]
                ],
                "strengths": report.strengths,
            },
        )

        db = get_db()
        await db.posts.update_one(
            {"run_id": run_id},
            {"$set": {"quality_report": {
                "score": report.score,
                "read_ratio_prediction": report.read_ratio_prediction,
                "issues": [
                    {"category": i.category, "severity": i.severity,
                     "location": i.location, "suggestion": i.suggestion}
                    for i in report.issues
                ],
                "strengths": report.strengths,
                "revision_prompt": report.revision_prompt,
            }}},
        )
        return {"quality_report": report, "completed_steps": ["quality_analysis"]}
    except Exception as e:
        await log_step(run_id, "quality_analyzer", f"Failed: {e}", level="error")
        return {"errors": [f"quality_analysis failed: {e}"]}


async def content_revision_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    report = state["quality_report"]
    revision_number = state["revision_count"] + 1

    if not post or not report:
        await log_step(run_id, "content_generator", "Missing post or report for revision", level="error")
        return {"errors": ["revision: missing post or quality report"]}

    # revision_number determines model: 1 → Haiku, 2 → Sonnet
    model = settings.worker_model if revision_number < 2 else settings.supervisor_model
    model_label = "Claude Haiku" if revision_number < 2 else "Claude Sonnet (quality upgrade)"
    max_rev = settings.max_revision_cycles

    await log_step(
        run_id, "content_generator",
        f"Revision {revision_number}/{max_rev} — rewriting with {model_label}...",
        data={"revision_number": revision_number, "model": model, "score_before": report.score},
    )
    try:
        revised = await revise_post(
            run_id=run_id,
            title=post.title,
            content=post.content,
            score=report.score,
            revision_prompt=report.revision_prompt,
            issues=[
                {"category": i.category, "severity": i.severity, "suggestion": i.suggestion}
                for i in report.issues
            ],
            revision_number=revision_number,
        )
        word_count = len(revised.content.split())
        await log_step(
            run_id, "content_generator",
            f"Revision {revision_number} complete: \"{revised.title}\" (~{word_count} words)",
            level="success",
            data={"title": revised.title, "word_count": word_count},
        )
        await _upsert_post(run_id, revised, state["trend_report"], PostStatus.REVISED,
                           revision_count=revision_number)
        return {
            "post": revised,
            "revision_count": revision_number,
            "completed_steps": [f"revision_{revision_number}"],
        }
    except Exception as e:
        await log_step(run_id, "content_generator", f"Revision {revision_number} failed: {e}",
                       level="error")
        return {"errors": [f"revision failed: {e}"]}


async def finalize_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    qr = state.get("quality_report")
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": {"status": str(PostStatus.APPROVED), "updated_at": datetime.now(UTC)}},
    )
    await _update_pipeline_run(state, "approved")
    score_msg = f" Final quality score: {qr.score:.2f}" if qr else ""
    await log_step(run_id, "orchestrator", f"Post approved and saved.{score_msg}",
                   level="success")
    return {"completed_steps": ["finalized"]}


async def publish_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "publisher", "No post to publish", level="error")
        return {"errors": ["publish: no post"]}

    await log_step(run_id, "publisher", "Publishing to Medium via Playwright...")
    try:
        url = await publish_to_medium(
            run_id=run_id,
            title=post.title,
            content=post.content,
            tags=post.tags,
            publish_live=state.get("publish_live", False),
        )
        await log_step(run_id, "publisher", f"Published successfully: {url}",
                       level="success", data={"url": url})
        await _update_pipeline_run(state, "published")
        return {"medium_url": url, "completed_steps": ["published"]}
    except Exception as e:
        await log_step(run_id, "publisher", f"Publish failed: {e}", level="error")
        return {"errors": [f"publish failed: {e}"]}


# ── Routing ────────────────────────────────────────────────────────────────────

def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)
    if not report or report.score >= settings.min_quality_score:
        return "finalize"
    if revisions >= settings.max_revision_cycles:
        return "finalize"
    return "revision"


def route_after_finalize(state: PipelineState) -> str:
    # Publishing is always user-triggered (POST /posts/{run_id}/publish).
    # The pipeline itself always stops here so it can never get stuck on Playwright.
    return END


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_graph() -> Any:
    g = StateGraph(PipelineState)
    g.add_node("trend_research", trend_research_node)
    g.add_node("content_generation", content_generation_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "trend_research")
    g.add_edge("trend_research", "content_generation")
    g.add_edge("content_generation", "quality_analysis")
    g.add_conditional_edges("quality_analysis", route_after_quality,
                            {"finalize": "finalize", "revision": "revision"})
    g.add_edge("revision", "quality_analysis")
    g.add_edge("finalize", END)
    return g.compile()


pipeline = build_graph()


# ── Public entrypoint ──────────────────────────────────────────────────────────

async def run_pipeline(
    custom_topic: str | None = None,
    publish_live: bool = False,
    run_id: str | None = None,
) -> dict[str, Any]:
    db = get_db()

    if run_id:
        # Caller pre-created the doc as "queued" — update to running
        await db.pipeline_runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "running", "started_at": datetime.now(UTC)}},
        )
    else:
        run_id = str(uuid.uuid4())
        await db.pipeline_runs.insert_one({
            "run_id": run_id,
            "custom_topic": custom_topic,
            "publish_live": publish_live,
            "status": "running",
            "created_at": datetime.now(UTC),
        })
    await log_step(run_id, "orchestrator",
                   f"Pipeline started. Topic: {custom_topic or 'auto (trend research)'}",
                   data={"publish_live": publish_live})

    initial_state: PipelineState = {
        "run_id": run_id,
        "custom_topic": custom_topic,
        "publish_live": publish_live,
        "trend_report": None,
        "post": None,
        "quality_report": None,
        "revision_count": 0,
        "medium_url": None,
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
        await log_step(run_id, "orchestrator",
                       f"Pipeline failed: {'; '.join(final_state.get('errors', []))}",
                       level="error")
    else:
        await log_step(run_id, "orchestrator", "Pipeline completed successfully.",
                       level="success")

    post = final_state.get("post")
    qr = final_state.get("quality_report")
    return {
        "run_id": run_id,
        "status": status,
        "title": post.title if post else None,
        "quality_score": qr.score if qr else None,
        "read_ratio_prediction": qr.read_ratio_prediction if qr else None,
        "revision_count": final_state.get("revision_count", 0),
        "medium_url": final_state.get("medium_url"),
        "errors": final_state.get("errors", []),
        "steps": final_state.get("completed_steps", []),
    }


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _upsert_post(run_id, post, trend, status, revision_count=0):
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "topic": post.title,
                "trend_context": trend.market_context if trend else "",
                "title": post.title,
                "subtitle": post.subtitle,
                "content": post.content,
                "tags": post.tags,
                "image_suggestions": post.image_suggestions,
                "status": str(status),
                "revision_count": revision_count,
                "updated_at": datetime.now(UTC),
            },
            "$setOnInsert": {"created_at": datetime.now(UTC)},
        },
        upsert=True,
    )


async def _update_pipeline_run(state, status):
    db = get_db()
    await db.pipeline_runs.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
    )
