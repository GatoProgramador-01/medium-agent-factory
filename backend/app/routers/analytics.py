from typing import Any, cast

from fastapi import APIRouter

from app.database import get_db

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Claude Sonnet rates used as the reference benchmark for savings calculations
_SONNET_PRICE_IN = 3.00   # USD per 1M input tokens
_SONNET_PRICE_OUT = 15.00  # USD per 1M output tokens


def _compute_savings(
    deepseek_tokens_in: int,
    deepseek_tokens_out: int,
    deepseek_cost_usd: float,
) -> tuple[float, float, float]:
    """Return (equivalent_claude_cost_usd, savings_usd, savings_pct)."""
    equivalent = (
        deepseek_tokens_in * _SONNET_PRICE_IN
        + deepseek_tokens_out * _SONNET_PRICE_OUT
    ) / 1_000_000
    savings = equivalent - deepseek_cost_usd
    pct = (savings / equivalent * 100) if equivalent > 0 else 0.0
    return equivalent, savings, pct


@router.get("/token-usage")
async def token_usage(run_id: str | None = None) -> list[dict[str, Any]]:
    """Per-agent token usage. Filter by run_id or get all."""
    db = get_db()
    query: dict[str, Any] = {"run_id": run_id} if run_id else {}
    pipeline: list[dict[str, Any]] = [
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
    result = cast(
        list[dict[str, Any]],
        await db.agent_runs.aggregate(pipeline).to_list(length=50),
    )
    for r in result:
        r["agent_name"] = r.pop("_id")
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
        r["avg_duration_ms"] = round(r["avg_duration_ms"])
    return result


@router.get("/token-usage/by-run")
async def token_usage_by_run(limit: int = 20) -> list[dict[str, Any]]:
    """Total cost and tokens per pipeline run."""
    db = get_db()
    pipeline: list[dict[str, Any]] = [
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
    result = cast(
        list[dict[str, Any]],
        await db.agent_runs.aggregate(pipeline).to_list(length=limit),
    )
    for r in result:
        r["run_id"] = r.pop("_id")
        r["total_cost_usd"] = round(r["total_cost_usd"], 6)
    return result


@router.get("/summary")
async def summary() -> dict[str, Any]:
    """Overall system stats."""
    db = get_db()

    total_runs = await db.pipeline_runs.count_documents({})
    completed = await db.pipeline_runs.count_documents({"status": "completed"})
    total_posts = await db.posts.count_documents({})
    published = await db.posts.count_documents({"status": "published"})

    cost_pipeline: list[dict[str, Any]] = [
        {
            "$group": {
                "_id": None,
                "total_cost": {"$sum": "$cost_usd"},
                "total_tokens": {"$sum": {"$add": ["$tokens_in", "$tokens_out"]}},
            }
        }
    ]
    cost_result = cast(
        list[dict[str, Any]],
        await db.agent_runs.aggregate(cost_pipeline).to_list(length=1),
    )
    cost_data: dict[str, Any] = (
        cost_result[0] if cost_result else {"total_cost": 0, "total_tokens": 0}
    )

    return {
        "pipeline_runs": total_runs,
        "completed_runs": completed,
        "total_posts": total_posts,
        "published_posts": published,
        "total_cost_usd": round(cost_data.get("total_cost", 0), 4),
        "total_tokens": cost_data.get("total_tokens", 0),
    }


@router.get("/cost-comparison")
async def cost_comparison() -> dict[str, Any]:
    """Claude historical cost vs DeepSeek current cost with savings calculation.

    Old records without a ``provider`` field are classified on the fly by
    inspecting the ``model`` string so the endpoint is backwards-compatible.
    """
    db = get_db()

    pipeline: list[dict[str, Any]] = [
        # Derive effective_provider from model name so legacy docs (no
        # provider field) are bucketed correctly.
        {
            "$addFields": {
                "effective_provider": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {
                                    "$regexMatch": {
                                        "input": "$model",
                                        "regex": "^claude",
                                    }
                                },
                                "then": "anthropic",
                            },
                            {
                                "case": {
                                    "$regexMatch": {
                                        "input": "$model",
                                        "regex": "^deepseek",
                                    }
                                },
                                "then": "deepseek",
                            },
                        ],
                        "default": "local",
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$effective_provider",
                "cost_usd": {"$sum": "$cost_usd"},
                "tokens_in": {"$sum": "$tokens_in"},
                "tokens_out": {"$sum": "$tokens_out"},
                "runs": {"$sum": 1},
            }
        },
    ]

    rows = cast(
        list[dict[str, Any]],
        await db.agent_runs.aggregate(pipeline).to_list(length=10),
    )

    # Index by provider name for easy lookup
    by_provider: dict[str, dict[str, Any]] = {r["_id"]: r for r in rows}

    claude = by_provider.get("anthropic", {})
    deepseek = by_provider.get("deepseek", {})

    claude_cost = float(claude.get("cost_usd", 0.0))
    claude_tokens_in = int(claude.get("tokens_in", 0))
    claude_tokens_out = int(claude.get("tokens_out", 0))
    claude_runs = int(claude.get("runs", 0))

    ds_cost = float(deepseek.get("cost_usd", 0.0))
    ds_tokens_in = int(deepseek.get("tokens_in", 0))
    ds_tokens_out = int(deepseek.get("tokens_out", 0))
    ds_runs = int(deepseek.get("runs", 0))

    equivalent, savings, savings_pct = _compute_savings(
        ds_tokens_in, ds_tokens_out, ds_cost
    )

    return {
        "claude_cost_usd": round(claude_cost, 6),
        "claude_tokens_in": claude_tokens_in,
        "claude_tokens_out": claude_tokens_out,
        "claude_runs": claude_runs,
        "deepseek_cost_usd": round(ds_cost, 6),
        "deepseek_tokens_in": ds_tokens_in,
        "deepseek_tokens_out": ds_tokens_out,
        "deepseek_runs": ds_runs,
        "equivalent_claude_cost_usd": round(equivalent, 6),
        "savings_usd": round(savings, 6),
        "savings_pct": round(savings_pct, 2),
        "has_claude_data": claude_runs > 0,
        "has_deepseek_data": ds_runs > 0,
    }
