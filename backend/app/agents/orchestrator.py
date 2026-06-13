"""
Orchestrator — LangGraph pipeline

Graph:
  START
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
  finalize → END
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
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityReport


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str

    post: GeneratedPost | None
    quality_report: QualityReport | None
    revision_count: int
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────


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
            trend_context="",
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
        await _upsert_post(run_id, post, PostStatus.DRAFT)
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
        verdict = (
            f"Passed threshold ({settings.min_quality_score}). Predicted read ratio: "
            f"{report.read_ratio_prediction * 100:.0f}%"
            if passed
            else f"Below threshold ({settings.min_quality_score}). "
            f"Found {len(report.issues)} issues. Queuing revision."
        )
        await log_step(
            run_id,
            "quality_analyzer",
            f"Quality score: {report.score:.2f}/1.0 — {verdict}",
            level=level,
            data={
                "score": report.score,
                "read_ratio_prediction": report.read_ratio_prediction,
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
    await log_step(
        run_id, "orchestrator", f"Post approved and saved.{score_msg}", level="success"
    )
    return {"completed_steps": ["finalized"]}


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)
    if not report or report.score >= settings.min_quality_score:
        return "finalize"
    if revisions >= settings.max_revision_cycles:
        return "finalize"
    return "revision"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_graph() -> Any:
    g = StateGraph(PipelineState)
    g.add_node("content_generation", content_generation_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "content_generation")
    g.add_edge("content_generation", "quality_analysis")
    g.add_conditional_edges(
        "quality_analysis",
        route_after_quality,
        {"finalize": "finalize", "revision": "revision"},
    )
    g.add_edge("revision", "quality_analysis")
    g.add_edge("finalize", END)
    return g.compile()


pipeline = build_graph()


# ── Public entrypoint ──────────────────────────────────────────────────────────


async def run_pipeline(
    custom_topic: str,
    run_id: str | None = None,
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
        "post": None,
        "quality_report": None,
        "revision_count": 0,
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
        "revision_count": final_state.get("revision_count", 0),
        "errors": final_state.get("errors", []),
        "steps": final_state.get("completed_steps", []),
    }


# ── DB helpers ─────────────────────────────────────────────────────────────────


async def _upsert_post(
    run_id: str, post: GeneratedPost, status: PostStatus, revision_count: int = 0
) -> None:
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {
            "$set": {
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
            },
            "$setOnInsert": {"created_at": datetime.now(UTC)},
        },
        upsert=True,
    )


async def _update_pipeline_run(state: PipelineState, status: str) -> None:
    db = get_db()
    await db.pipeline_runs.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
    )
