from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongodb_database]


async def close_client() -> None:
    global _client
    if _client:
        _client.close()
        _client = None


async def create_indexes() -> None:
    db = get_db()
    await db.posts.create_index("run_id")
    await db.posts.create_index("status")
    await db.posts.create_index([("created_at", -1)])
    await db.agent_runs.create_index("run_id")
    await db.agent_runs.create_index("agent_name")
    await db.agent_runs.create_index([("created_at", -1)])
    await db.trends.create_index([("created_at", -1)])
    await db.pipeline_runs.create_index([("created_at", -1)])
    await db.pipeline_runs.create_index("status")
    await db.agent_logs.create_index("run_id")
    await db.agent_logs.create_index([("timestamp", 1)])
