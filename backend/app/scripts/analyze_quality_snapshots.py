"""Analyzes quality_snapshots MongoDB collection to surface recurring failure patterns.

Outputs structured JSON to stdout. Human-readable summary to stderr.
Feed the JSON output directly to run_prompt_analysis() for automated prompt improvement.
"""
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient


async def analyze(n_runs: int = 20) -> dict[str, Any]:
    """Aggregates quality_snapshots for the last N runs.

    Args:
        n_runs: Number of distinct pipeline runs to include.

    Returns:
        Dict with keys: run_count, regression_rate, word_count stats,
        gate_failure_types, top_issues (10), top_5_sticky.
    """
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client: AsyncIOMotorClient[Any] = AsyncIOMotorClient(uri)
    db = client["medium_agent"]

    pipeline: list[dict[str, Any]] = [
        {"$sort": {"timestamp": -1}},
        {
            "$group": {
                "_id": "$run_id",
                "snapshots": {"$push": "$$ROOT"},
                "last_ts": {"$first": "$timestamp"},
            }
        },
        {"$sort": {"last_ts": -1}},
        {"$limit": n_runs},
    ]

    runs = await db.quality_snapshots.aggregate(pipeline).to_list(n_runs)
    client.close()

    if not runs:
        return {"error": "No quality_snapshots found in database", "run_count": 0}

    issue_total: Counter[str] = Counter()
    issue_high: Counter[str] = Counter()
    issue_sticky: Counter[str] = Counter()
    regression_count = 0
    transition_count = 0
    word_counts: list[int] = []
    gate_failures: Counter[str] = Counter()

    for run in runs:
        snapshots = sorted(run["snapshots"], key=lambda s: s.get("iteration", 0))

        for snap in snapshots:
            wc = snap.get("word_count", 0)
            if wc:
                word_counts.append(wc)

        scores = [s.get("score", 0.0) for s in snapshots]
        for i in range(1, len(scores)):
            transition_count += 1
            if scores[i] < scores[i - 1]:
                regression_count += 1

        for snap in snapshots:
            for gf in snap.get("gate_failures", []):
                gf_lower = gf.lower()
                if "word count" in gf_lower:
                    gate_failures["word_count"] += 1
                elif "read ratio" in gf_lower:
                    gate_failures["read_ratio"] += 1
                elif "ai pattern" in gf_lower:
                    gate_failures["ai_pattern"] += 1
                else:
                    gate_failures["quality_score"] += 1

        cat_iterations: dict[str, list[int]] = defaultdict(list)
        for snap in snapshots:
            iteration = snap.get("iteration", 0)
            for issue in snap.get("issues", []):
                cat = issue.get("category", "unknown")
                sev = issue.get("severity", "LOW")
                issue_total[cat] += 1
                if sev == "HIGH":
                    issue_high[cat] += 1
                cat_iterations[cat].append(iteration)

        for cat, iters in cat_iterations.items():
            if len(iters) >= 2 and (max(iters) - min(iters)) >= 2:
                issue_sticky[cat] += 1

    top_issues = [
        {
            "category": cat,
            "total": issue_total[cat],
            "high_count": issue_high.get(cat, 0),
            "sticky_count": issue_sticky.get(cat, 0),
        }
        for cat in sorted(issue_total, key=lambda c: -issue_total[c])
    ][:10]

    wc_avg = round(sum(word_counts) / len(word_counts)) if word_counts else 0
    wc_under = sum(1 for w in word_counts if w < 1300)

    return {
        "run_count": len(runs),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "regression_rate": round(regression_count / max(transition_count, 1), 3),
        "regression_events": regression_count,
        "transition_count": transition_count,
        "word_count": {
            "min": min(word_counts) if word_counts else 0,
            "max": max(word_counts) if word_counts else 0,
            "avg": wc_avg,
            "pct_under_1300": round(wc_under / max(len(word_counts), 1) * 100, 1),
        },
        "gate_failure_types": dict(gate_failures.most_common()),
        "top_issues": top_issues,
        "top_5_sticky": [
            {"category": cat, "sticky_count": issue_sticky[cat]}
            for cat in sorted(issue_sticky, key=lambda c: -issue_sticky[c])
        ][:5],
    }
