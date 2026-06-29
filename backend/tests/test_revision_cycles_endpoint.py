import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestRevisionCyclesEndpoint:
    @pytest.mark.asyncio
    async def test_revision_cycles_returns_snapshots(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        fake_snapshots = [
            {
                "run_id": "run-abc",
                "iteration": 0,
                "score": 0.82,
                "read_ratio": 0.61,
                "word_count": 1350,
                "medium_boost_eligible": False,
                "passed": False,
                "gate_failures": ["word count below minimum"],
                "issue_summary": {"high": 2, "medium": 1, "low": 0, "total": 3},
                "strengths": ["strong hook"],
            },
            {
                "run_id": "run-abc",
                "iteration": 1,
                "score": 0.91,
                "read_ratio": 0.68,
                "word_count": 1720,
                "medium_boost_eligible": True,
                "passed": True,
                "gate_failures": [],
                "issue_summary": {"high": 0, "medium": 1, "low": 0, "total": 1},
                "strengths": ["strong hook", "good specificity"],
            },
        ]

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=fake_snapshots)

        mock_db = MagicMock()
        mock_db.quality_snapshots.find = MagicMock(return_value=mock_cursor)

        with patch("app.routers.analytics.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/analytics/revision-cycles?run_id=run-abc")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["iteration"] == 0
        assert data[1]["passed"] is True
        # Verify the actual MongoDB query — projection must exclude heavy fields
        mock_db.quality_snapshots.find.assert_called_once_with(
            {"run_id": "run-abc"},
            {"_id": 0, "issues": 0, "revision_prompt": 0},
            sort=[("run_id", 1), ("iteration", 1)],
        )

    @pytest.mark.asyncio
    async def test_revision_cycles_empty_for_unknown_run(self):
        from httpx import AsyncClient, ASGITransport
        from app.main import app

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db = MagicMock()
        mock_db.quality_snapshots.find = MagicMock(return_value=mock_cursor)

        with patch("app.routers.analytics.get_db", return_value=mock_db):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/analytics/revision-cycles?run_id=nonexistent")

        assert response.status_code == 200
        assert response.json() == []
