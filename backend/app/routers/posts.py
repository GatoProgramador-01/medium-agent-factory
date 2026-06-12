from fastapi import APIRouter, HTTPException

from app.database import get_db

router = APIRouter(prefix="/posts", tags=["posts"])


@router.get("")
async def list_posts(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    db = get_db()
    query = {"status": status} if status else {}
    cursor = db.posts.find(query, {"_id": 0}, sort=[("created_at", -1)],
                           skip=offset, limit=limit)
    return await cursor.to_list(length=limit)


@router.get("/{run_id}")
async def get_post(run_id: str) -> dict:
    db = get_db()
    post = await db.posts.find_one({"run_id": run_id}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post
