"""
Pipeline step logger — writes structured log entries to MongoDB agent_logs.

Every node in the orchestrator calls log_step() so the frontend can
poll/stream a live feed of what each agent is doing.
"""

from datetime import UTC, datetime
from typing import Any

from app.database import get_db


async def log_step(
    run_id: str,
    step: str,
    message: str,
    level: str = "info",  # info | success | warning | error
    data: dict[str, Any] | None = None,
) -> None:
    db = get_db()
    await db.agent_logs.insert_one(
        {
            "run_id": run_id,
            "step": step,
            "level": level,
            "message": message,
            "data": data or {},
            "timestamp": datetime.now(UTC),
        }
    )
