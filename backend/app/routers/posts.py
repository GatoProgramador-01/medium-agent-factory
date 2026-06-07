from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.agents.logger import log_step
from app.agents.publisher import (
    check_session_status,
    publish_to_medium,
    set_session_from_cookies_json,
    set_session_from_sid,
)
from app.database import get_db

router = APIRouter(prefix="/posts", tags=["posts"])


# ── Post CRUD ──────────────────────────────────────────────────────────────────

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


# ── Publisher ──────────────────────────────────────────────────────────────────

async def _run_publish(run_id: str, publish_live: bool) -> None:
    """Background task: publish post and update status."""
    db = get_db()
    try:
        post = await db.posts.find_one({"run_id": run_id}, {"_id": 0})
        if not post:
            await log_step(run_id, "publisher", "Post not found", level="error")
            return

        await log_step(
            run_id, "publisher",
            f"Starting publish — mode: {'live' if publish_live else 'draft'}",
            data={"publish_live": publish_live},
        )
        url = await publish_to_medium(
            run_id=run_id,
            title=post["title"],
            content=post["content"],
            tags=post.get("tags", []),
            publish_live=publish_live,
        )
        await log_step(
            run_id, "publisher",
            f"Done → {url}",
            level="success",
            data={"url": url},
        )
    except Exception as exc:
        await log_step(run_id, "publisher", f"Publish failed: {exc}", level="error")
        await db.posts.update_one(
            {"run_id": run_id},
            {"$set": {"publish_error": str(exc)}},
        )


@router.post("/{run_id}/publish")
async def publish_post(
    run_id: str,
    background_tasks: BackgroundTasks,
    publish_live: bool = False,
) -> dict:
    """Trigger publishing for an approved post. Steps stream via GET /pipeline/runs/{run_id}/logs."""
    db = get_db()
    post = await db.posts.find_one({"run_id": run_id}, {"_id": 0, "status": 1})
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.get("status") not in ("approved", "draft_submitted"):
        raise HTTPException(
            status_code=409,
            detail=f"Post status is '{post.get('status')}' — must be 'approved' to publish",
        )

    background_tasks.add_task(_run_publish, run_id, publish_live)
    return {"run_id": run_id, "message": "Publishing started — watch logs for progress"}


# ── Auth flow (cookie-based session setup) ────────────────────────────────────
#
# Medium no longer issues API tokens or passwords for new accounts.
# The user pastes their `sid` cookie (or a full cookie JSON export) from an
# already-logged-in browser session. Playwright verifies it, then saves the
# full storage state to MongoDB so it persists across container restarts.

class SetSessionRequest(BaseModel):
    sid: str


class SetSessionJsonRequest(BaseModel):
    cookies: list[dict]


@router.get("/publisher/session-status")
async def publisher_session_status() -> dict:
    """Return whether a valid Medium session is stored."""
    return await check_session_status()


@router.post("/publisher/set-session")
async def publisher_set_session(req: SetSessionRequest) -> dict:
    """
    Paste the `sid` cookie value from medium.com DevTools.
    DevTools → Application → Cookies → https://medium.com → row named "sid" → Value.
    Playwright verifies the session is live before saving it to MongoDB.
    """
    message = await set_session_from_sid(req.sid)
    return {"message": message}


@router.post("/publisher/set-session-json")
async def publisher_set_session_json(req: SetSessionJsonRequest) -> dict:
    """
    Paste the full cookie JSON exported from Cookie-Editor or EditThisCookie.
    Playwright verifies and saves the session to MongoDB.
    """
    message = await set_session_from_cookies_json(req.cookies)
    return {"message": message}
