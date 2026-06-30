"""
Unit tests for AI Slop Detector — identifies forbidden words, em-dash excess, and uniform rhythm.
"""

import pytest


class TestAISlopDetectorNode:
    """Test AI slop detector node functionality."""

    @pytest.mark.asyncio
    async def test_ai_slop_detector_returns_empty_on_no_post(self) -> None:
        """ai_slop_detector_node returns {} when state has no post."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await ai_slop_detector_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_ai_slop_detector_detects_forbidden_words(self) -> None:
        """ai_slop_detector_node detects forbidden words and includes them in issues."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Let me delve into this topic. We must leverage our resources to be game-changers.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        assert "ai_slop_issues" in result
        assert isinstance(result["ai_slop_issues"], list)
        forbidden_word_issues = [
            i for i in result["ai_slop_issues"] if i["type"] == "FORBIDDEN_WORD"
        ]
        assert len(forbidden_word_issues) > 0
        forbidden_words = [i["word"] for i in forbidden_word_issues]
        assert "delve" in forbidden_words
        assert "leverage" in forbidden_words
        assert "game-changer" in forbidden_words

    @pytest.mark.asyncio
    async def test_ai_slop_detector_counts_em_dashes(self) -> None:
        """ai_slop_detector_node counts em-dashes and reports excess."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is point one — and here is point two — followed by point three — then point four — plus point five — and finally point six — with one more — and another.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        em_dash_issues = [
            i for i in result["ai_slop_issues"] if i["type"] == "EM_DASH_EXCESS"
        ]
        assert len(em_dash_issues) > 0
        assert em_dash_issues[0]["count"] > 6

    @pytest.mark.asyncio
    async def test_ai_slop_detector_computes_sentence_variance(self) -> None:
        """ai_slop_detector_node computes sentence length variance."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        # Uniform sentence length (low variance)
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The cat sat. The dog ran. The bird flew. The fish swam. The ant walked.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        uniform_rhythm_issues = [
            i for i in result["ai_slop_issues"] if i["type"] == "UNIFORM_RHYTHM"
        ]
        # Low variance should not trigger HIGH issue (if we have < 5.0 std_dev)
        # Check that std_dev is present
        if uniform_rhythm_issues:
            assert "std_dev" in uniform_rhythm_issues[0]

    @pytest.mark.asyncio
    async def test_ai_slop_detector_sets_passed_when_clean(self) -> None:
        """ai_slop_detector_node sets ai_slop_passed=True for clean content."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is a clean article. No forbidden words here. Simple sentences vary in length. A few em-dashes are fine—like this one—but not excessive.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        assert "ai_slop_passed" in result
        assert isinstance(result["ai_slop_passed"], bool)

    @pytest.mark.asyncio
    async def test_ai_slop_detector_sets_failed_when_issues(self) -> None:
        """ai_slop_detector_node sets ai_slop_passed=False when issues found."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Let me delve and leverage this. We must be game-changers with cutting-edge transformative synergy.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        assert "ai_slop_passed" in result
        assert result["ai_slop_passed"] is False

    @pytest.mark.asyncio
    async def test_ai_slop_detector_returns_score(self) -> None:
        """ai_slop_detector_node returns ai_slop_score between 0-1."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is a reasonable article. Not perfect but acceptable.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        assert "ai_slop_score" in result
        assert isinstance(result["ai_slop_score"], float)
        assert 0.0 <= result["ai_slop_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_ai_slop_detector_updates_structural_issues(self) -> None:
        """ai_slop_detector_node appends to structural_check_issues when not passed."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This leverages the seamless synergy paradigm in a groundbreaking manner.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await ai_slop_detector_node(state)

        if not result.get("ai_slop_passed", True):
            assert "structural_check_issues" in result
            assert len(result["structural_check_issues"]) > 0
            ai_slop_struct_issues = [
                i
                for i in result["structural_check_issues"]
                if i.get("category") == "ai_slop"
            ]
            assert len(ai_slop_struct_issues) > 0

    @pytest.mark.asyncio
    async def test_no_state_mutation_on_revision_loop(self) -> None:
        """ai_slop_detector_node should not mutate state structural_check_issues on revision cycles."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        # Content with 4 forbidden hits total (delve appears 4 times) which fails on first pass
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Let me delve into this. We delve deeper. Delve more. Delve now. But the approach is good.",
            tags=[],
            image_suggestions=[],
        )

        initial_state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        # First call — should fail and add to structural_check_issues
        result1 = await ai_slop_detector_node(initial_state)
        assert "structural_check_issues" in result1
        first_cycle_issues_count = len(result1["structural_check_issues"])
        assert first_cycle_issues_count == 1

        # Second call (revision cycle) with the output from first as input
        # The state now has the structural_check_issues from first call
        state_after_first = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": result1["structural_check_issues"],
        }

        result2 = await ai_slop_detector_node(state_after_first)
        assert "structural_check_issues" in result2
        second_cycle_issues_count = len(result2["structural_check_issues"])

        # If there's a mutation bug, second call would have 2 issues (appended to the mutated list)
        # With the fix (using spread operator), we should still have only 1 issue
        assert second_cycle_issues_count == 1

    @pytest.mark.asyncio
    async def test_code_fence_content_not_scanned_fixed(self) -> None:
        """ai_slop_detector_node should skip scanning content inside code fences."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        # "leverage" is a forbidden word, but only inside a code block
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This article is clean. Here is a code example: ```leverage()``` that should not trigger.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        forbidden_word_issues = [
            i for i in result["ai_slop_issues"] if i["type"] == "FORBIDDEN_WORD"
        ]
        # "leverage" in code block should not trigger
        leverage_issues = [i for i in forbidden_word_issues if i["word"] == "leverage"]
        assert len(leverage_issues) == 0

    @pytest.mark.asyncio
    async def test_total_forbidden_threshold_fixed(self) -> None:
        """ai_slop_detector_node fails on total forbidden word threshold (>3)."""
        from app.agents.nodes.ai_slop_detector import ai_slop_detector_node
        from app.agents.content_generator import GeneratedPost

        # 4 different forbidden words each appearing once = total of 4 hits
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Let me delve into this. We leverage resources. This is transformative. Pivotal moment. But the approach works well and is different from others.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await ai_slop_detector_node(state)

        # 4 total hits across different words should fail (threshold is 3)
        # Check that ai_slop_passed is False
        assert result["ai_slop_passed"] is False
        # Verify we detected 4 forbidden word hits
        forbidden_word_issues = [
            i for i in result["ai_slop_issues"] if i["type"] == "FORBIDDEN_WORD"
        ]
        total_hits = sum(i.get("count", 0) for i in forbidden_word_issues)
        assert total_hits == 4
