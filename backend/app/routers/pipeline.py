import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.orchestrator import run_pipeline
from app.database import get_db

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    custom_topic: str | None = None
    publish_live: bool = False


@router.post("/run")
async def trigger_pipeline(
    req: PipelineRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Trigger pipeline asynchronously. Poll /runs/{run_id} for status."""
    import uuid
    from datetime import UTC

    run_id = str(uuid.uuid4())
    db = get_db()
    await db.pipeline_runs.insert_one({
        "run_id": run_id,
        "custom_topic": req.custom_topic,
        "publish_live": req.publish_live,
        "status": "queued",
        "created_at": datetime.now(UTC),
    })
    background_tasks.add_task(
        run_pipeline,
        custom_topic=req.custom_topic,
        publish_live=req.publish_live,
    )
    return {"run_id": run_id, "message": "Pipeline started"}


@router.post("/run/sync")
async def trigger_pipeline_sync(req: PipelineRequest) -> dict:
    """Run pipeline synchronously — blocks until complete."""
    return await run_pipeline(
        custom_topic=req.custom_topic,
        publish_live=req.publish_live,
    )


@router.get("/runs")
async def list_runs(limit: int = 20, offset: int = 0) -> list[dict]:
    db = get_db()
    cursor = db.pipeline_runs.find({}, {"_id": 0}, sort=[("created_at", -1)],
                                   skip=offset, limit=limit)
    return await cursor.to_list(length=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    db = get_db()
    run = await db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/logs")
async def get_logs(run_id: str) -> list[dict]:
    """All log entries for a run, ordered by timestamp."""
    db = get_db()
    cursor = db.agent_logs.find({"run_id": run_id}, {"_id": 0},
                                sort=[("timestamp", 1)])
    return await cursor.to_list(length=500)


@router.get("/runs/{run_id}/stream")
async def stream_logs(run_id: str, request: Request) -> StreamingResponse:
    """
    SSE stream of agent logs for a run.
    Sends new entries as they arrive, closes when pipeline finishes.
    """
    async def event_generator():
        db = get_db()
        seen_count = 0
        terminal = {"completed", "failed"}

        while True:
            if await request.is_disconnected():
                break

            # Fetch only new log entries
            logs = await (
                db.agent_logs.find({"run_id": run_id}, {"_id": 0},
                                   sort=[("timestamp", 1)])
                .skip(seen_count)
                .to_list(length=100)
            )

            for log in logs:
                seen_count += 1
                payload = json.dumps(log, default=str)
                yield f"data: {payload}\n\n"

            # Check if done
            run = await db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0, "status": 1})
            if run and run.get("status") in terminal:
                yield "data: {\"__done__\": true}\n\n"
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
