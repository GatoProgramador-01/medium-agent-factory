import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.orchestrator import run_series
from app.database import get_db
from app.limiter import limiter
from app.utils.cost_guard import check_daily_run_limit

router = APIRouter(prefix="/series", tags=["series"])


class SeriesRequest(BaseModel):
    theme: str = Field(min_length=10, max_length=500)
    context: str = Field(default="", max_length=1000)


@limiter.limit("1/hour")  # type: ignore[untyped-decorator]
@router.post("/run")
async def trigger_series(
    request: Request,
    req: SeriesRequest,
    background_tasks: BackgroundTasks,
    _: None = Depends(check_daily_run_limit),
) -> dict[str, Any]:
    """Plan and run a multi-post series asynchronously."""
    series_id = str(uuid.uuid4())
    db = get_db()
    await db.series.insert_one(
        {
            "series_id": series_id,
            "theme": req.theme,
            "status": "queued",
            "run_ids": [],
            "created_at": datetime.now(UTC),
        }
    )
    background_tasks.add_task(
        run_series,
        theme=req.theme,
        context=req.context,
        series_id=series_id,
    )
    return {"series_id": series_id, "message": "Series started"}


@router.get("")
async def list_series(limit: int = 20) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db.series.find({}, {"_id": 0}, sort=[("created_at", -1)], limit=limit)
    return cast(list[dict[str, Any]], await cursor.to_list(length=limit))


@router.delete("/{series_id}", status_code=204)
async def delete_series(series_id: str) -> None:
    db = get_db()
    result = await db.series.delete_one({"series_id": series_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Series not found")


@router.get("/{series_id}")
async def get_series(series_id: str) -> dict[str, Any]:
    db = get_db()
    series = await db.series.find_one({"series_id": series_id}, {"_id": 0})
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    posts_cursor = db.posts.find(
        {"series_id": series_id},
        {"_id": 0, "content": 0},
        sort=[("series_position", 1)],
    )
    posts = cast(list[dict[str, Any]], await posts_cursor.to_list(length=20))
    series["posts"] = posts
    return cast(dict[str, Any], series)
