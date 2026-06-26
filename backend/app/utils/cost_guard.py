from datetime import UTC, datetime

from fastapi import Header, HTTPException

from app.config import settings
from app.database import get_db


async def check_daily_run_limit(x_admin_key: str = Header(default="")) -> None:
    """Raise 429 if the global daily run cap is reached.

    Requests with a valid X-Admin-Key header bypass the cap entirely.
    """
    if settings.admin_api_key and x_admin_key == settings.admin_api_key:
        return

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    db = get_db()
    result = await db.daily_counters.find_one_and_update(
        {"date": today},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=True,
    )
    if result["count"] > settings.daily_run_limit:
        await db.daily_counters.update_one(
            {"date": today}, {"$inc": {"count": -1}}
        )
        raise HTTPException(
            status_code=429,
            detail=(
                f"Daily capacity of {settings.daily_run_limit} runs reached. "
                "Please try again tomorrow."
            ),
        )
