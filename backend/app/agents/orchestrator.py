"""
Orchestrator — LangGraph pipeline

Graph:
  START
    │
    ▼
  trend_research          (TrendResearchAgent)
    │
    ▼
  content_generation      (ContentGeneratorAgent — initial)
    │
    ▼
  quality_analysis        (QualityAnalyzerAgent)
    │
    ├─── score >= threshold ──→ finalize
    │
    └─── score < threshold AND revisions < max ──→ content_revision
                                                        │
                                                        ▼
                                                  quality_analysis (loop)
  finalize
    │
    ├─── publish=True ──→ publish ──→ END
    │
    └─── publish=False ──→ END
"""

import uuid
from datetime import datetime, UTC
from typing import Annotated, Any
import operator

from langgraph.graph import StateGraph, END, START
from typing_extensions import TypedDict

from app.agents.content_generator import GeneratedPost, generate_initial_post, revise_post
from app.agents.quality_analyzer import run_quality_analysis
from app.agents.trend_researcher import TrendReport, run_trend_research
from app.agents.publisher import publish_to_medium
from app.config import settings
from app.database import get_db
from app.models.post import PostDocument, PostStatus, QualityReport


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str | None
    publish_live: bool

    # populated by nodes
    trend_report: TrendReport | None
    post: GeneratedPost | None
    quality_report: QualityReport | None
    revision_count: int
    medium_url: str | None
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────

async def trend_research_node(state: PipelineState) -> dict[str, Any]:
    try:
        report = await run_trend_research(
            run_id=state["run_id"],
            custom_topic=state.get("custom_topic"),
        )
        return {
            "trend_report": report,
            "completed_steps": ["trend_research"],
        }
    except Exception as e:
        return {"errors": [f"trend_research failed: {e}"]}


async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    trend = state["trend_report"]
    if not trend:
        return {"errors": ["content_generation: no trend report"]}

    try:
        best = trend.opportunities[0] if trend.opportunities else None
        post = await generate_initial_post(
            run_id=state["run_id"],
            topic=state.get("custom_topic") or trend.recommended_topic,
            trend_context=trend.market_context,
            tags=trend.recommended_tags,
            audience=best.target_audience if best else "content creators",
        )

        await _upsert_post(state["run_id"], post, trend, PostStatus.DRAFT)
        return {
            "post": post,
            "revision_count": 0,
            "completed_steps": ["content_generation"],
        }
    except Exception as e:
        return {"errors": [f"content_generation failed: {e}"]}


async def quality_analysis_node(state: PipelineState) -> dict[str, Any]:
    post = state["post"]
    if not post:
        return {"errors": ["quality_analysis: no post"]}

    try:
        report = await run_quality_analysis(
            run_id=state["run_id"],
            title=post.title,
            content=post.content,
        )

        db = get_db()
        await db.posts.update_one(
            {"run_id": state["run_id"]},
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
        return {
            "quality_report": report,
            "completed_steps": ["quality_analysis"],
        }
    except Exception as e:
        return {"errors": [f"quality_analysis failed: {e}"]}


async def content_revision_node(state: PipelineState) -> dict[str, Any]:
    post = state["post"]
    report = state["quality_report"]
    if not post or not report:
        return {"errors": ["revision: missing post or quality report"]}

    try:
        revised = await revise_post(
            run_id=state["run_id"],
            title=post.title,
            content=post.content,
            score=report.score,
            revision_prompt=report.revision_prompt,
            issues=[
                {"category": i.category, "severity": i.severity, "suggestion": i.suggestion}
                for i in report.issues
            ],
        )

        await _upsert_post(
            state["run_id"],
            revised,
            state["trend_report"],
            PostStatus.REVISED,
            revision_count=state["revision_count"] + 1,
        )
        return {
            "post": revised,
            "revision_count": state["revision_count"] + 1,
            "completed_steps": [f"revision_{state['revision_count'] + 1}"],
        }
    except Exception as e:
        return {"errors": [f"revision failed: {e}"]}


async def finalize_node(state: PipelineState) -> dict[str, Any]:
    db = get_db()
    await db.posts.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": str(PostStatus.APPROVED), "updated_at": datetime.now(UTC)}},
    )
    await _update_pipeline_run(state, "approved")
    return {"completed_steps": ["finalized"]}


async def publish_node(state: PipelineState) -> dict[str, Any]:
    post = state["post"]
    if not post:
        return {"errors": ["publish: no post"]}

    try:
        url = await publish_to_medium(
            run_id=state["run_id"],
            title=post.title,
            content=post.content,
            tags=post.tags,
            publish_live=state.get("publish_live", False),
        )
        await _update_pipeline_run(state, "published")
        return {"medium_url": url, "completed_steps": ["published"]}
    except Exception as e:
        return {"errors": [f"publish failed: {e}"]}


# ── Routing ────────────────────────────────────────────────────────────────────

def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)

    if not report:
        return "finalize"

    if report.score >= settings.min_quality_score:
        return "finalize"

    if revisions >= settings.max_revision_cycles:
        return "finalize"

    return "revision"


def route_after_finalize(state: PipelineState) -> str:
    if state.get("publish_live"):
        return "publish"
    return END


# ── Graph assembly ─────────────────────────────────────────────────────────────

def build_graph() -> Any:
    g = StateGraph(PipelineState)

    g.add_node("trend_research", trend_research_node)
    g.add_node("content_generation", content_generation_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("finalize", finalize_node)
    g.add_node("publish", publish_node)

    g.add_edge(START, "trend_research")
    g.add_edge("trend_research", "content_generation")
    g.add_edge("content_generation", "quality_analysis")
    g.add_conditional_edges(
        "quality_analysis",
        route_after_quality,
        {"finalize": "finalize", "revision": "revision"},
    )
    g.add_edge("revision", "quality_analysis")
    g.add_conditional_edges(
        "finalize",
        route_after_finalize,
        {"publish": "publish", END: END},
    )
    g.add_edge("publish", END)

    return g.compile()


pipeline = build_graph()


# ── Public entrypoint ──────────────────────────────────────────────────────────

async def run_pipeline(
    custom_topic: str | None = None,
    publish_live: bool = False,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    db = get_db()

    await db.pipeline_runs.insert_one({
        "run_id": run_id,
        "custom_topic": custom_topic,
        "publish_live": publish_live,
        "status": "running",
        "created_at": datetime.now(UTC),
    })

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

async def _upsert_post(
    run_id: str,
    post: GeneratedPost,
    trend: TrendReport | None,
    status: PostStatus,
    revision_count: int = 0,
) -> None:
    db = get_db()
    doc = {
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
    }
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": doc, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
    )


async def _update_pipeline_run(state: PipelineState, status: str) -> None:
    db = get_db()
    await db.pipeline_runs.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
    )
