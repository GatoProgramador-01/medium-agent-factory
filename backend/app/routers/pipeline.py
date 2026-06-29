import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import run_pipeline
from app.agents.prompt_analyst import PromptAnalysisReport, run_prompt_analysis
from app.database import get_db
from app.limiter import limiter
from app.utils.cost_guard import check_daily_run_limit
from scripts.analyze_quality_snapshots import analyze

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    custom_topic: str = Field(min_length=10, max_length=500)
    grounding_context: str = Field(default="", max_length=12000)


@limiter.limit("2/hour")
@router.post("/run")
async def trigger_pipeline(
    request: Request,
    req: PipelineRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(check_daily_run_limit),
) -> dict[str, Any]:
    """Trigger pipeline asynchronously. Poll /runs/{run_id} for status."""
    run_id = str(uuid.uuid4())
    db = get_db()
    await db.pipeline_runs.insert_one(
        {
            "run_id": run_id,
            "custom_topic": req.custom_topic,
            "grounding_context": req.grounding_context,
            "status": "queued",
            "created_at": datetime.now(UTC),
        }
    )
    background_tasks.add_task(
        run_pipeline,
        custom_topic=req.custom_topic,
        run_id=run_id,
        grounding_context=req.grounding_context,
    )
    return {"run_id": run_id, "message": "Pipeline started"}


@limiter.limit("2/hour")
@router.post("/run/sync")
async def trigger_pipeline_sync(
    request: Request,
    req: PipelineRequest,
    _: None = Depends(check_daily_run_limit),
) -> dict[str, Any]:
    """Run pipeline synchronously — blocks until complete."""
    return await run_pipeline(
        custom_topic=req.custom_topic,
        grounding_context=req.grounding_context,
    )


@router.get("/runs")
async def list_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = 0,
) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.pipeline_runs.find(
        {}, {"_id": 0}, sort=[("created_at", -1)], skip=offset, limit=limit
    )
    return cast(list[dict[str, Any]], await cursor.to_list(length=limit))


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    db = get_db()
    run = await db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return cast(dict[str, Any], run)


@router.get("/runs/{run_id}/logs")
async def get_logs(run_id: str) -> list[dict[str, Any]]:
    """All log entries for a run, ordered by timestamp."""
    db = get_db()
    cursor = db.agent_logs.find({"run_id": run_id}, {"_id": 0}, sort=[("timestamp", 1)])
    return cast(list[dict[str, Any]], await cursor.to_list(length=500))


@router.get("/runs/{run_id}/stream")
async def stream_logs(run_id: str, request: Request) -> StreamingResponse:
    """SSE stream of agent logs for a run. Closes when pipeline finishes."""

    async def event_generator() -> AsyncGenerator[str, None]:
        db = get_db()
        seen_count = 0
        terminal = {"completed", "failed"}

        while True:
            if await request.is_disconnected():
                break

            logs = await (
                db.agent_logs.find(
                    {"run_id": run_id}, {"_id": 0}, sort=[("timestamp", 1)]
                )
                .skip(seen_count)
                .to_list(length=100)
            )

            for log in logs:
                seen_count += 1
                payload = json.dumps(log, default=str)
                yield f"data: {payload}\n\n"

            run = await db.pipeline_runs.find_one(
                {"run_id": run_id}, {"_id": 0, "status": 1}
            )
            if run and run.get("status") in terminal:
                yield 'data: {"__done__": true}\n\n'
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ImprovePromptsResponse(BaseModel):
    """Response payload for POST /pipeline/improve-prompts."""

    run_count: int
    top_issue: str
    regression_rate: float
    summary: str
    suggestions: list[dict[str, Any]]
    analyzed_at: str


@router.post("/improve-prompts", response_model=ImprovePromptsResponse)
async def improve_prompts(
    runs: int = Query(default=20, ge=5, le=100),
) -> dict[str, Any]:
    """Analyze quality_snapshots and return prioritized prompt improvement suggestions.

    Args:
        runs: Number of recent pipeline runs to include in the analysis (5–100, default 20).

    Returns:
        JSON with run_count, top_issue, regression_rate, summary, suggestions, analyzed_at.

    Raises:
        404: When no quality_snapshots exist in the database.
    """
    analysis = await analyze(n_runs=runs)

    if "error" in analysis:
        raise HTTPException(status_code=404, detail=analysis["error"])

    report: PromptAnalysisReport = await run_prompt_analysis(
        run_id=str(uuid.uuid4()),
        analysis_data=analysis,
        prompt_files={},
    )

    return {
        "run_count": report.run_count,
        "top_issue": report.top_issue,
        "regression_rate": report.regression_rate,
        "summary": report.summary,
        "suggestions": [s.model_dump() for s in report.suggestions],
        "analyzed_at": datetime.now(UTC).isoformat(),
    }
