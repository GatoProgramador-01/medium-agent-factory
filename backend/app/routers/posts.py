from typing import Any, cast

from fastapi import APIRouter, HTTPException

from app.agents.exemplar_store import promote_post_to_exemplar
from app.database import get_db

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
async def list_posts(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    db = get_db()
    query: dict[str, Any] = {"status": status} if status else {}
    cursor = db.posts.find(
        query, {"_id": 0}, sort=[("created_at", -1)], skip=offset, limit=limit
    )
    return cast(list[dict[str, Any]], await cursor.to_list(length=limit))


@router.get("/{run_id}")
async def get_post(run_id: str) -> dict[str, Any]:
    db = get_db()
    post = await db.posts.find_one({"run_id": run_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return cast(dict[str, Any], post)


@router.delete("/{run_id}", status_code=204)
async def delete_post(run_id: str) -> None:
    db = get_db()
    result = await db.posts.delete_one({"run_id": run_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Post not found")


@router.post("/{run_id}/exemplar")
async def promote_exemplar(run_id: str) -> dict[str, Any]:
    """Promote an existing post to exemplar status for few-shot injection."""
    saved = await promote_post_to_exemplar(run_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"run_id": run_id, "status": "saved_as_exemplar"}


@router.get("/exemplars/list")
async def list_exemplars() -> list[dict[str, Any]]:
    """List all stored exemplars."""
    db = get_db()
    exemplars = await db.exemplars.find(
        {}, {"_id": 0, "intro": 0, "code_block": 0}, sort=[("score", -1)]
    ).to_list(length=50)
    return cast(list[dict[str, Any]], exemplars)
