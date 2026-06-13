"""
Backend E2E test fixtures.

Uses a real MongoDB (medium_factory_test database) so tests exercise the full
request → FastAPI → Motor → MongoDB round trip. No LLM calls — run_pipeline
is patched in any test that would trigger it.

Requirements: MongoDB running at MONGODB_URI (default localhost:27017).
In CI, a mongo:7 service container is started by the workflow.

Cleanup strategy
----------------
pytest-asyncio 1.x creates a new asyncio event loop per test. Motor's
AsyncIOMotorClient is loop-bound, so reusing it across per-test loops
causes "Event loop is closed" errors. We avoid the problem entirely by
doing pre-test cleanup with a *synchronous* PyMongo client (no loop
required) and resetting the Motor singleton so it re-binds to each
test's fresh loop.
"""

import os

# Must be set before app modules are imported so pydantic-settings picks it up.
os.environ.setdefault("MONGODB_DATABASE", "medium_factory_test")

from collections.abc import AsyncGenerator

import pymongo
import pytest
from httpx import ASGITransport, AsyncClient

import app.database as _db_module
from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _clean_and_reset() -> None:
    """Wipe test collections and reset the Motor singleton before each test.

    Uses synchronous PyMongo so there are no async event-loop concerns.
    The Motor singleton reset ensures get_client() re-binds to the current
    test's event loop when the FastAPI startup event fires.
    """
    mongo = pymongo.MongoClient(settings.mongodb_uri)
    db = mongo[settings.mongodb_database]
    db.pipeline_runs.delete_many({})
    db.posts.delete_many({})
    db.agent_runs.delete_many({})
    db.agent_logs.delete_many({})
    mongo.close()
    _db_module._client = None


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
