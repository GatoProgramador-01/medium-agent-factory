from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import run_pipeline
from app.database import get_db

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class PipelineRequest(BaseModel):
    custom_topic: str | None = None
    publish_live: bool = False


class PipelineResponse(BaseModel):
    run_id: str
    message: str


@router.post("/run", response_model=PipelineResponse)
async def trigger_pipeline(
    req: PipelineRequest,
    background_tasks: BackgroundTasks,
) -> PipelineResponse:
    """Trigger the full agent pipeline asynchronously."""
    import uuid
    from datetime import datetime, UTC

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

    return PipelineResponse(run_id=run_id, message="Pipeline started")


@router.post("/run/sync")
async def trigger_pipeline_sync(req: PipelineRequest) -> dict:
    """Run pipeline synchronously — use for testing or small loads."""
    return await run_pipeline(
        custom_topic=req.custom_topic,
        publish_live=req.publish_live,
    )


@router.get("/runs")
async def list_runs(limit: int = 20, offset: int = 0) -> list[dict]:
    db = get_db()
    cursor = db.pipeline_runs.find(
        {},
        {"_id": 0},
        sort=[("created_at", -1)],
        skip=offset,
        limit=limit,
    )
    return await cursor.to_list(length=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    db = get_db()
    run = await db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
