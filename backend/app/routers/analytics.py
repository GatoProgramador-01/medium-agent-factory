from fastapi import APIRouter

from app.database import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/token-usage")
async def token_usage(run_id: str | None = None) -> list[dict]:
    """Per-agent token usage. Filter by run_id or get all."""
    db = get_db()
    query = {"run_id": run_id} if run_id else {}
    pipeline = [
        {"$match": query},
        {
            "$group": {
                "_id": "$agent_name",
                "total_tokens_in": {"$sum": "$tokens_in"},
                "total_tokens_out": {"$sum": "$tokens_out"},
                "total_cost_usd": {"$sum": "$cost_usd"},
                "avg_duration_ms": {"$avg": "$duration_ms"},
                "call_count": {"$sum": 1},
            }
        },
        {"$sort": {"total_cost_usd": -1}},
    ]
    result = await db.agent_runs.aggregate(pipeline).to_list(length=50)
    for r in result:
        r["agent_name"] = r.pop("_id")
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
        r["avg_duration_ms"] = round(r["avg_duration_ms"])
    return result


@router.get("/token-usage/by-run")
async def token_usage_by_run(limit: int = 20) -> list[dict]:
    """Total cost and tokens per pipeline run."""
    db = get_db()
    pipeline = [
        {
            "$group": {
                "_id": "$run_id",
                "total_cost_usd": {"$sum": "$cost_usd"},
                "total_tokens_in": {"$sum": "$tokens_in"},
                "total_tokens_out": {"$sum": "$tokens_out"},
                "total_duration_ms": {"$sum": "$duration_ms"},
                "agent_calls": {"$sum": 1},
                "first_call": {"$min": "$created_at"},
            }
        },
        {"$sort": {"first_call": -1}},
        {"$limit": limit},
    ]
    result = await db.agent_runs.aggregate(pipeline).to_list(length=limit)
    for r in result:
        r["run_id"] = r.pop("_id")
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
    return result


@router.get("/summary")
async def summary() -> dict:
    """Overall system stats."""
    db = get_db()

    total_runs = await db.pipeline_runs.count_documents({})
    completed = await db.pipeline_runs.count_documents({"status": "completed"})
    total_posts = await db.posts.count_documents({})
    published = await db.posts.count_documents({"status": "published"})

    cost_pipeline = [
        {
            "$group": {
                "_id": None,
                "total_cost": {"$sum": "$cost_usd"},
                "total_tokens": {"$sum": {"$add": ["$tokens_in", "$tokens_out"]}},
            }
        }
    ]
    cost_result = await db.agent_runs.aggregate(cost_pipeline).to_list(length=1)
    cost_data = cost_result[0] if cost_result else {"total_cost": 0, "total_tokens": 0}

    return {
        "pipeline_runs": total_runs,
        "completed_runs": completed,
        "total_posts": total_posts,
        "published_posts": published,
        "total_cost_usd": round(cost_data.get("total_cost", 0), 4),
        "total_tokens": cost_data.get("total_tokens", 0),
    }
