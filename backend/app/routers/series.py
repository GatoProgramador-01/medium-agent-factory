from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.agents.orchestrator import run_series
from app.database import get_db

router = APIRouter(prefix="/series", tags=["series"])


class SeriesRequest(BaseModel):
    theme: str
    context: str = ""


@router.post("/run")
async def trigger_series(
    req: SeriesRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Plan and run a multi-post series asynchronously."""
    import uuid
    from datetime import UTC, datetime

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
    from typing import cast
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
    from typing import cast
    series = await db.series.find_one({"series_id": series_id}, {"_id": 0})
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")

    # Attach posts in order
    posts_cursor = db.posts.find(
        {"series_id": series_id},
        {"_id": 0, "content": 0},
        sort=[("series_position", 1)],
    )
    posts = cast(list[dict[str, Any]], await posts_cursor.to_list(length=20))
    series["posts"] = posts
    return cast(dict[str, Any], series)
