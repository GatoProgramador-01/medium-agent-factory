"""
Backend E2E tests — real HTTP + real MongoDB, no LLM calls.

Coverage:
  GET  /health
  POST /pipeline/run          (background task patched)
  GET  /pipeline/runs
  GET  /pipeline/runs/{id}
  GET  /pipeline/runs/{id}/logs
  GET  /posts
  GET  /posts/{id}
  DELETE /posts/{id}
  PATCH  /posts/{id}/status
  POST   /series/run          (background task patched)
  GET    /series
  GET    /series/{id}
  GET  /analytics/token-usage
  GET  /analytics/token-usage/by-run
  GET  /analytics/summary
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.database import get_db


class TestHealthE2E:
    async def test_health_returns_ok(self, client: AsyncClient) -> None:
        r = await client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "environment" in body


class TestPipelineRunsE2E:
    async def test_trigger_queues_run_and_writes_to_db(
        self, client: AsyncClient
    ) -> None:
        with patch("app.routers.pipeline.run_pipeline", new=AsyncMock(return_value={})):
            r = await client.post(
                "/pipeline/run", json={"custom_topic": "AI agents 2025"}
            )

        assert r.status_code == 200
        body = r.json()
        assert "run_id" in body
        assert body["message"] == "Pipeline started"

        db = get_db()
        run = await db.pipeline_runs.find_one({"run_id": body["run_id"]})
        assert run is not None
        assert run["status"] == "queued"
        assert run["custom_topic"] == "AI agents 2025"

    async def test_list_runs_empty(self, client: AsyncClient) -> None:
        r = await client.get("/pipeline/runs")
        assert r.status_code == 200
        assert r.json() == []

    async def test_list_runs_returns_inserted_records(
        self, client: AsyncClient
    ) -> None:
        db = get_db()
        await db.pipeline_runs.insert_many(
            [
                {
                    "run_id": "e2e-r1",
                    "status": "completed",
                    "created_at": datetime.now(UTC),
                },
                {
                    "run_id": "e2e-r2",
                    "status": "failed",
                    "created_at": datetime.now(UTC),
                },
            ]
        )

        r = await client.get("/pipeline/runs")
        assert r.status_code == 200
        run_ids = {run["run_id"] for run in r.json()}
        assert {"e2e-r1", "e2e-r2"}.issubset(run_ids)

    async def test_get_run_found(self, client: AsyncClient) -> None:
        db = get_db()
        await db.pipeline_runs.insert_one(
            {"run_id": "e2e-r3", "status": "completed", "created_at": datetime.now(UTC)}
        )

        r = await client.get("/pipeline/runs/e2e-r3")
        assert r.status_code == 200
        assert r.json()["run_id"] == "e2e-r3"
        assert r.json()["status"] == "completed"

    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        r = await client.get("/pipeline/runs/does-not-exist")
        assert r.status_code == 404

    async def test_get_logs_empty_for_new_run(self, client: AsyncClient) -> None:
        db = get_db()
        await db.pipeline_runs.insert_one(
            {"run_id": "e2e-r4", "status": "running", "created_at": datetime.now(UTC)}
        )

        r = await client.get("/pipeline/runs/e2e-r4/logs")
        assert r.status_code == 200
        assert r.json() == []

    async def test_get_logs_returns_ordered_entries(self, client: AsyncClient) -> None:
        db = get_db()
        await db.agent_logs.insert_many(
            [
                {
                    "run_id": "e2e-r5",
                    "agent": "quality_analyzer",
                    "message": "started",
                    "timestamp": datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
                },
                {
                    "run_id": "e2e-r5",
                    "agent": "quality_analyzer",
                    "message": "done",
                    "timestamp": datetime(2025, 1, 1, 0, 0, 2, tzinfo=UTC),
                },
            ]
        )

        r = await client.get("/pipeline/runs/e2e-r5/logs")
        assert r.status_code == 200
        logs = r.json()
        assert len(logs) == 2
        assert logs[0]["message"] == "started"
        assert logs[1]["message"] == "done"


class TestPostsE2E:
    async def test_list_posts_empty(self, client: AsyncClient) -> None:
        r = await client.get("/posts")
        assert r.status_code == 200
        assert r.json() == []

    async def test_get_post_not_found(self, client: AsyncClient) -> None:
        r = await client.get("/posts/no-such-post")
        assert r.status_code == 404

    async def test_list_posts_returns_all(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_many(
            [
                {
                    "run_id": "e2e-p1",
                    "status": "draft",
                    "title": "Draft Post",
                    "created_at": datetime.now(UTC),
                },
                {
                    "run_id": "e2e-p2",
                    "status": "published",
                    "title": "Published Post",
                    "created_at": datetime.now(UTC),
                },
            ]
        )

        r = await client.get("/posts")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_list_posts_filters_by_status(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_many(
            [
                {
                    "run_id": "e2e-p3",
                    "status": "draft",
                    "created_at": datetime.now(UTC),
                },
                {
                    "run_id": "e2e-p4",
                    "status": "published",
                    "created_at": datetime.now(UTC),
                },
            ]
        )

        r = await client.get("/posts?status=draft")
        assert r.status_code == 200
        posts = r.json()
        assert len(posts) == 1
        assert posts[0]["status"] == "draft"

    async def test_get_post_found(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {
                "run_id": "e2e-p5",
                "status": "revised",
                "title": "Specific Post",
                "created_at": datetime.now(UTC),
            }
        )

        r = await client.get("/posts/e2e-p5")
        assert r.status_code == 200
        assert r.json()["run_id"] == "e2e-p5"
        assert r.json()["title"] == "Specific Post"

    @pytest.mark.parametrize("limit,expected", [(1, 1), (5, 3)])
    async def test_list_posts_respects_limit(
        self, client: AsyncClient, limit: int, expected: int
    ) -> None:
        db = get_db()
        await db.posts.insert_many(
            [
                {
                    "run_id": f"e2e-lp{i}",
                    "status": "draft",
                    "created_at": datetime.now(UTC),
                }
                for i in range(3)
            ]
        )

        r = await client.get(f"/posts?limit={limit}")
        assert r.status_code == 200
        assert len(r.json()) == expected


    async def test_delete_post_returns_204(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-del1", "status": "draft", "title": "To Delete", "created_at": datetime.now(UTC)}
        )
        r = await client.delete("/posts/e2e-del1")
        assert r.status_code == 204

    async def test_delete_post_removes_from_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-del2", "status": "draft", "title": "Delete Me", "created_at": datetime.now(UTC)}
        )
        await client.delete("/posts/e2e-del2")
        remaining = await db.posts.find_one({"run_id": "e2e-del2"})
        assert remaining is None

    async def test_delete_post_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.delete("/posts/does-not-exist")
        assert r.status_code == 404

    async def test_get_post_returns_word_count_field(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {
                "run_id": "e2e-wc1",
                "status": "approved",
                "title": "Word Count Post",
                "content": "word " * 1750,
                "word_count": 1750,
                "created_at": datetime.now(UTC),
            }
        )
        r = await client.get("/posts/e2e-wc1")
        assert r.status_code == 200
        assert r.json()["word_count"] == 1750

    async def test_patch_status_returns_updated_doc(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-st1", "status": "draft", "title": "Draft", "created_at": datetime.now(UTC)}
        )
        r = await client.patch("/posts/e2e-st1/status", json={"status": "approved"})
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    async def test_patch_status_persists_to_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-st2", "status": "revised", "title": "Revised", "created_at": datetime.now(UTC)}
        )
        await client.patch("/posts/e2e-st2/status", json={"status": "published"})
        doc = await db.posts.find_one({"run_id": "e2e-st2"})
        assert doc is not None
        assert doc["status"] == "published"

    async def test_patch_status_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.patch("/posts/no-such/status", json={"status": "approved"})
        assert r.status_code == 404

    async def test_patch_status_invalid_value_returns_422(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-st3", "status": "draft", "created_at": datetime.now(UTC)}
        )
        r = await client.patch("/posts/e2e-st3/status", json={"status": "banana"})
        assert r.status_code == 422

    async def test_patch_medium_url_sets_url(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-mu1", "status": "published", "created_at": datetime.now(UTC)}
        )
        url = "https://medium.com/@user/my-article-abc123"
        r = await client.patch("/posts/e2e-mu1/medium_url", json={"medium_url": url})
        assert r.status_code == 200
        assert r.json()["medium_url"] == url

    async def test_patch_medium_url_persists_to_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-mu2", "status": "published", "created_at": datetime.now(UTC)}
        )
        url = "https://medium.com/@user/another-article"
        await client.patch("/posts/e2e-mu2/medium_url", json={"medium_url": url})
        doc = await db.posts.find_one({"run_id": "e2e-mu2"})
        assert doc is not None
        assert doc["medium_url"] == url

    async def test_patch_medium_url_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.patch("/posts/no-such/medium_url", json={"medium_url": "https://medium.com/x"})
        assert r.status_code == 404


class TestAnalyticsE2E:
    async def test_token_usage_empty(self, client: AsyncClient) -> None:
        r = await client.get("/analytics/token-usage")
        assert r.status_code == 200
        assert r.json() == []

    async def test_token_usage_by_run_empty(self, client: AsyncClient) -> None:
        r = await client.get("/analytics/token-usage/by-run")
        assert r.status_code == 200
        assert r.json() == []

    async def test_summary_returns_expected_fields(self, client: AsyncClient) -> None:
        r = await client.get("/analytics/summary")
        assert r.status_code == 200
        body = r.json()
        assert "pipeline_runs" in body
        assert "completed_runs" in body
        assert "total_posts" in body
        assert "published_posts" in body
        assert "total_cost_usd" in body
        assert "total_tokens" in body

    async def test_summary_counts_correctly(self, client: AsyncClient) -> None:
        db = get_db()
        await db.pipeline_runs.insert_many(
            [
                {"run_id": "s1", "status": "completed"},
                {"run_id": "s2", "status": "failed"},
                {"run_id": "s3", "status": "running"},
            ]
        )
        await db.posts.insert_many(
            [
                {"run_id": "s1", "status": "published"},
                {"run_id": "s2", "status": "draft"},
            ]
        )

        r = await client.get("/analytics/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["pipeline_runs"] == 3
        assert body["completed_runs"] == 1
        assert body["total_posts"] == 2
        assert body["published_posts"] == 1

    async def test_token_usage_aggregates_by_agent(self, client: AsyncClient) -> None:
        db = get_db()
        await db.agent_runs.insert_many(
            [
                {
                    "run_id": "a1",
                    "agent_name": "quality_analyzer",
                    "tokens_in": 100,
                    "tokens_out": 50,
                    "cost_usd": 0.001,
                    "duration_ms": 500,
                },
                {
                    "run_id": "a1",
                    "agent_name": "quality_analyzer",
                    "tokens_in": 200,
                    "tokens_out": 80,
                    "cost_usd": 0.002,
                    "duration_ms": 600,
                },
                {
                    "run_id": "a1",
                    "agent_name": "content_generator",
                    "tokens_in": 500,
                    "tokens_out": 300,
                    "cost_usd": 0.01,
                    "duration_ms": 1200,
                },
            ]
        )

        r = await client.get("/analytics/token-usage")
        assert r.status_code == 200
        rows = {row["agent_name"]: row for row in r.json()}
        assert "quality_analyzer" in rows
        assert "content_generator" in rows
        assert rows["quality_analyzer"]["total_tokens_in"] == 300
        assert rows["quality_analyzer"]["call_count"] == 2
        assert rows["content_generator"]["call_count"] == 1


class TestExemplarsE2E:
    async def test_list_exemplars_empty(self, client: AsyncClient) -> None:
        r = await client.get("/posts/exemplars/list")
        assert r.status_code == 200
        assert r.json() == []

    async def test_list_exemplars_returns_all(self, client: AsyncClient) -> None:
        db = get_db()
        await db.exemplars.insert_many(
            [
                {"run_id": "e1", "title": "Exemplar One",  "score": 0.97, "created_at": datetime.now(UTC)},
                {"run_id": "e2", "title": "Exemplar Two",  "score": 0.95, "created_at": datetime.now(UTC)},
            ]
        )
        r = await client.get("/posts/exemplars/list")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_delete_exemplar_returns_204(self, client: AsyncClient) -> None:
        db = get_db()
        await db.exemplars.insert_one({"run_id": "e-del1", "score": 0.97, "created_at": datetime.now(UTC)})
        r = await client.delete("/posts/exemplars/e-del1")
        assert r.status_code == 204

    async def test_delete_exemplar_removes_from_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.exemplars.insert_one({"run_id": "e-del2", "score": 0.96, "created_at": datetime.now(UTC)})
        await client.delete("/posts/exemplars/e-del2")
        remaining = await db.exemplars.find_one({"run_id": "e-del2"})
        assert remaining is None

    async def test_delete_exemplar_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.delete("/posts/exemplars/no-such-exemplar")
        assert r.status_code == 404

    async def test_promote_exemplar_returns_saved_status(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {
                "run_id": "e2e-promo1",
                "title": "Great Post",
                "content": "word " * 100,
                "tags": ["ai"],
                "status": "approved",
                "quality_report": {"score": 0.97, "read_ratio_prediction": 0.82,
                                   "medium_boost_eligible": True, "issues": [], "strengths": []},
                "created_at": datetime.now(UTC),
            }
        )
        r = await client.post("/posts/e2e-promo1/exemplar")
        assert r.status_code == 200
        assert r.json()["status"] == "saved_as_exemplar"

    async def test_promote_exemplar_creates_exemplar_doc(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {
                "run_id": "e2e-promo2",
                "title": "Another Great Post",
                "content": "word " * 100,
                "tags": ["llm"],
                "status": "approved",
                "quality_report": {"score": 0.96, "read_ratio_prediction": 0.80,
                                   "medium_boost_eligible": True, "issues": [], "strengths": []},
                "created_at": datetime.now(UTC),
            }
        )
        await client.post("/posts/e2e-promo2/exemplar")
        exemplar = await db.exemplars.find_one({"run_id": "e2e-promo2"})
        assert exemplar is not None

    async def test_promote_exemplar_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.post("/posts/no-such/exemplar")
        assert r.status_code == 404

    async def test_patch_tags_updates_post(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-tags1", "status": "draft", "tags": ["old"], "created_at": datetime.now(UTC)}
        )
        r = await client.patch("/posts/e2e-tags1/tags", json={"tags": ["ai", "llm", "cost"]})
        assert r.status_code == 200
        assert r.json()["tags"] == ["ai", "llm", "cost"]

    async def test_patch_tags_persists_to_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.posts.insert_one(
            {"run_id": "e2e-tags2", "status": "draft", "tags": [], "created_at": datetime.now(UTC)}
        )
        await client.patch("/posts/e2e-tags2/tags", json={"tags": ["python", "agents"]})
        doc = await db.posts.find_one({"run_id": "e2e-tags2"})
        assert doc is not None
        assert doc["tags"] == ["python", "agents"]

    async def test_patch_tags_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.patch("/posts/no-such/tags", json={"tags": ["ai"]})
        assert r.status_code == 404


class TestSeriesE2E:
    async def test_trigger_series_returns_series_id(self, client: AsyncClient) -> None:
        with patch("app.routers.series.run_series", new=AsyncMock(return_value={})):
            r = await client.post("/series/run", json={"theme": "LLM Cost Breakdown"})
        assert r.status_code == 200
        body = r.json()
        assert "series_id" in body
        assert body["message"] == "Series started"

    async def test_trigger_series_creates_db_document(self, client: AsyncClient) -> None:
        with patch("app.routers.series.run_series", new=AsyncMock(return_value={})):
            r = await client.post("/series/run", json={"theme": "Agent Patterns", "context": "2025 trends"})
        series_id = r.json()["series_id"]
        db = get_db()
        doc = await db.series.find_one({"series_id": series_id})
        assert doc is not None
        assert doc["theme"] == "Agent Patterns"
        assert doc["status"] == "queued"

    async def test_list_series_empty(self, client: AsyncClient) -> None:
        r = await client.get("/series")
        assert r.status_code == 200
        assert r.json() == []

    async def test_list_series_returns_all(self, client: AsyncClient) -> None:
        db = get_db()
        await db.series.insert_many(
            [
                {"series_id": "s1", "theme": "Theme A", "status": "completed", "created_at": datetime.now(UTC)},
                {"series_id": "s2", "theme": "Theme B", "status": "running",   "created_at": datetime.now(UTC)},
            ]
        )
        r = await client.get("/series")
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_get_series_not_found(self, client: AsyncClient) -> None:
        r = await client.get("/series/does-not-exist")
        assert r.status_code == 404

    async def test_get_series_found(self, client: AsyncClient) -> None:
        db = get_db()
        await db.series.insert_one(
            {"series_id": "s3", "theme": "AI Agents", "status": "completed", "created_at": datetime.now(UTC)}
        )
        r = await client.get("/series/s3")
        assert r.status_code == 200
        assert r.json()["series_id"] == "s3"
        assert r.json()["theme"] == "AI Agents"

    async def test_delete_series_returns_204(self, client: AsyncClient) -> None:
        db = get_db()
        await db.series.insert_one(
            {"series_id": "s-del1", "theme": "To Delete", "status": "completed", "created_at": datetime.now(UTC)}
        )
        r = await client.delete("/series/s-del1")
        assert r.status_code == 204

    async def test_delete_series_removes_from_db(self, client: AsyncClient) -> None:
        db = get_db()
        await db.series.insert_one(
            {"series_id": "s-del2", "theme": "Remove Me", "status": "completed", "created_at": datetime.now(UTC)}
        )
        await client.delete("/series/s-del2")
        remaining = await db.series.find_one({"series_id": "s-del2"})
        assert remaining is None

    async def test_delete_series_not_found_returns_404(self, client: AsyncClient) -> None:
        r = await client.delete("/series/no-such-series")
        assert r.status_code == 404

    async def test_get_series_attaches_posts_in_order(self, client: AsyncClient) -> None:
        db = get_db()
        await db.series.insert_one(
            {"series_id": "s4", "theme": "Cost Series", "status": "completed", "created_at": datetime.now(UTC)}
        )
        await db.posts.insert_many(
            [
                {"run_id": "p2", "series_id": "s4", "series_position": 2, "title": "Part Two",   "created_at": datetime.now(UTC)},
                {"run_id": "p1", "series_id": "s4", "series_position": 1, "title": "Part One",   "created_at": datetime.now(UTC)},
                {"run_id": "p3", "series_id": "s4", "series_position": 3, "title": "Part Three", "created_at": datetime.now(UTC)},
            ]
        )
        r = await client.get("/series/s4")
        assert r.status_code == 200
        posts = r.json()["posts"]
        assert len(posts) == 3
        assert posts[0]["title"] == "Part One"
        assert posts[1]["title"] == "Part Two"
        assert posts[2]["title"] == "Part Three"
