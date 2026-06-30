import uuid
from datetime import UTC, datetime
from typing import Any, Dict

from app.agents.logger import log_step
from app.agents.series_planner import plan_series
from app.database import get_db


async def run_series(
    theme: str,
    context: str = "",
    series_id: str | None = None,
) -> Dict[str, Any]:
    """Plan and run a multi-post series. Posts execute sequentially.

    The Story (El Relato):
    In the story of our pipeline, this function is the Campaign Manager.
    Instead of writing isolated articles, it designs a cohesive multi-part content series
    tied together by a common theme. It begins by requesting a full series plan from the
    series planner agent, which determines the topic, angle, and hooks for each post.
    Then, it executes the pipeline sequentially for each post, feeding each subsequent run
    with the proper series context, and tracking the campaign status in the database.

    The Flow (El Flujo):
    1. Generate a series ID and log the start of the campaign planning.
    2. Invoke the series planner agent (`plan_series`) to outline the titles and hooks.
    3. Persist the planned series metadata in the MongoDB `series` collection.
    4. Iterate over the planned posts sequentially, compiling the series context for each post.
    5. Dynamically import and run `run_pipeline` for each post, pushing each run ID to the database.
    6. Record the completion status of the entire campaign and return the final report.
    """
    from app.agents.orchestrator import run_pipeline

    db = get_db()
    series_id = series_id or str(uuid.uuid4())

    plan_run_id = f"{series_id}-planner"
    await log_step(plan_run_id, "series_planner", f'Planning series for theme: "{theme}"')

    plan = await plan_series(run_id=plan_run_id, theme=theme, context=context)

    await log_step(
        plan_run_id,
        "series_planner",
        f'Series planned: "{plan.series_title}" — {len(plan.posts)} posts',
        level="success",
        data={
            "series_title": plan.series_title,
            "series_description": plan.series_description,
            "posts": [{"position": p.position, "angle": p.angle} for p in plan.posts],
        },
    )

    await db.series.update_one(
        {"series_id": series_id},
        {
            "$set": {
                "theme": theme,
                "series_title": plan.series_title,
                "series_description": plan.series_description,
                "post_count": len(plan.posts),
                "status": "running",
            },
            "$setOnInsert": {"run_ids": [], "created_at": datetime.now(UTC)},
        },
        upsert=True,
    )

    results = []
    for post_plan in sorted(plan.posts, key=lambda p: p.position):
        await log_step(
            plan_run_id,
            "series_planner",
            f"Starting post {post_plan.position}/{len(plan.posts)}: {post_plan.angle}",
        )
        post_series_context = (
            f'SERIES: Post {post_plan.position} of {len(plan.posts)} — "{plan.series_title}"\n'
            f"SERIES DESCRIPTION: {plan.series_description}\n"
            f"THIS POST'S ANGLE: {post_plan.angle}\n"
            f"HOOK SEED: {post_plan.hook_seed}\n"
            f"NOTE: Each post in this series is self-contained. Do not reference other posts "
            f"directly (e.g. no 'In part 1...'). The series context is for tone and positioning only."
        )
        result = await run_pipeline(
            custom_topic=post_plan.topic,
            series_id=series_id,
            series_position=post_plan.position,
            series_context=post_series_context,
        )
        results.append(result)

        await db.series.update_one(
            {"series_id": series_id},
            {"$push": {"run_ids": result["run_id"]}},
        )

        await log_step(
            plan_run_id,
            "series_planner",
            f'Post {post_plan.position} done: "{result.get("title","")}" '
            f'(score={result.get("quality_score","?")}, boost={result.get("medium_boost_eligible","?")})',
            level="success" if result["status"] == "completed" else "error",
        )

    series_status = "completed" if all(r["status"] == "completed" for r in results) else "failed"
    await db.series.update_one(
        {"series_id": series_id},
        {"$set": {"status": series_status, "completed_at": datetime.now(UTC)}},
    )

    return {
        "series_id": series_id,
        "series_title": plan.series_title,
        "series_description": plan.series_description,
        "status": series_status,
        "posts": results,
    }
