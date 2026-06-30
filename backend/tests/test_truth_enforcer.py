"""
Unit tests for Truth Enforcer — ensures numbers > 10 are attributed to sources.
"""

import pytest


class TestTruthEnforcerNode:
    """Test truth enforcer node functionality."""

    @pytest.mark.asyncio
    async def test_truth_enforcer_returns_empty_on_no_post(self) -> None:
        """truth_enforcer_node returns {} when state has no post."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await truth_enforcer_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_truth_enforcer_detects_unattributed_numbers(self) -> None:
        """truth_enforcer_node detects numbers > 10 without attribution anchors."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="My costs dropped by 94%. The bill went from 2,800 dollars to 178 dollars. This is a major saving.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "unattributed_numbers" in result
        assert isinstance(result["unattributed_numbers"], list)

    @pytest.mark.asyncio
    async def test_truth_enforcer_ignores_small_numbers(self) -> None:
        """truth_enforcer_node ignores numbers <= 10."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I tested this 3 times and got 5 results. The answer is 2.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        unattributed = result.get("unattributed_numbers", [])
        # Small numbers should not be in unattributed list
        assert all(float(n) > 10 for n in unattributed if n)

    @pytest.mark.asyncio
    async def test_truth_enforcer_passes_when_all_attributed(self) -> None:
        """truth_enforcer_node passes when all numbers have attribution anchors."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="In my test, I measured 94% improvement. I found that 2,800 dropped to 178. My experiment showed this.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is True

    @pytest.mark.asyncio
    async def test_truth_enforcer_fails_when_unattributed(self) -> None:
        """truth_enforcer_node fails when numbers lack attribution."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The performance jumped by 94%. Costs dropped from 2,800 to 178. This proves everything.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is False

    @pytest.mark.asyncio
    async def test_truth_enforcer_recognizes_multiple_attribution_anchors(self) -> None:
        """truth_enforcer_node recognizes various attribution phrases."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Per my tests, costs were 2,800. I ran an experiment and got 94%. I observed this in my setup. I profiled the system and found 178.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is True

    @pytest.mark.asyncio
    async def test_truth_enforcer_detects_url_attribution(self) -> None:
        """truth_enforcer_node recognizes URLs as attribution."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="According to https://example.com, the score was 94%. Check http://data.org for the 2,800 figure.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is True

    @pytest.mark.asyncio
    async def test_truth_enforcer_updates_structural_issues_on_fail(self) -> None:
        """truth_enforcer_node appends to structural_check_issues when failing."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The bill was 2,800 dollars and I saved 94%. This happened automatically.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await truth_enforcer_node(state)

        if not result.get("truth_enforcer_passed", True):
            assert "structural_check_issues" in result
            truth_issues = [
                i
                for i in result["structural_check_issues"]
                if i.get("category") == "unattributed_number"
            ]
            assert len(truth_issues) > 0

    @pytest.mark.asyncio
    async def test_no_state_mutation_on_revision_loop(self) -> None:
        """truth_enforcer_node does not mutate state.structural_check_issues (no state aliasing)."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The bill was 2,800 dollars and I saved 94%. This happened automatically.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        # Call truth_enforcer_node twice with the same state
        result1 = await truth_enforcer_node(state)
        result2 = await truth_enforcer_node(state)

        # Both should have exactly 1 unattributed_number issue, not 2
        if not result1.get("truth_enforcer_passed", True):
            issues1 = result1.get("structural_check_issues", [])
            truth_issues1 = [i for i in issues1 if i.get("category") == "unattributed_number"]
            assert len(truth_issues1) == 1

        if not result2.get("truth_enforcer_passed", True):
            issues2 = result2.get("structural_check_issues", [])
            truth_issues2 = [i for i in issues2 if i.get("category") == "unattributed_number"]
            assert len(truth_issues2) == 1

    @pytest.mark.asyncio
    async def test_code_block_numbers_not_flagged(self) -> None:
        """truth_enforcer_node ignores numbers inside fenced code blocks (e.g., 8080 in ```python block)."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="My server runs on this configuration. ```python\nport = 8080\nmax_workers = 16\n``` These are defaults.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is True
        # 8080 and 16 inside the code block should not be in unattributed_numbers
        unattributed = result.get("unattributed_numbers", [])
        assert "8080" not in unattributed
        assert "16" not in unattributed

    @pytest.mark.asyncio
    async def test_inline_code_numbers_not_flagged(self) -> None:
        """truth_enforcer_node ignores numbers inside inline code (e.g., `3.11` in backticks)."""
        from app.agents.nodes.truth_enforcer_node import truth_enforcer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I use Python `3.11` which requires `2048` MB. This is the standard.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await truth_enforcer_node(state)

        assert "truth_enforcer_passed" in result
        assert result["truth_enforcer_passed"] is True
        # 3.11 and 2048 inside inline code should not be in unattributed_numbers
        unattributed = result.get("unattributed_numbers", [])
        assert "3.11" not in unattributed
        assert "2048" not in unattributed
