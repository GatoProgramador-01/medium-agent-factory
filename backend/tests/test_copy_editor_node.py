"""
Unit tests for Copy Editor Node — measures copy-level formatting and consistency.
"""

import pytest


class TestCopyEditorNode:
    """Test copy editor node functionality."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_post(self) -> None:
        """copy_editor_node returns {} when state has no post."""
        from app.agents.nodes.copy_editor_node import copy_editor_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await copy_editor_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_passing_on_empty_content(self) -> None:
        """copy_editor_node returns copy_edit_passed=True, score=1.0 when post.content is empty."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_passed" in result
        assert result["copy_edit_passed"] is True
        assert result["copy_edit_score"] == 1.0

    @pytest.mark.asyncio
    async def test_detects_mixed_heading_case(self) -> None:
        """copy_editor_node detects inconsistent heading capitalization."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## The Quick Brown Fox\n\n"
                "Some content here.\n\n"
                "## go faster now\n\n"
                "More content."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "heading_consistency_score" in result["copy_edit_metrics"]
        # Mixed case should result in lower consistency score
        assert result["copy_edit_metrics"]["heading_consistency_score"] < 1.0

    @pytest.mark.asyncio
    async def test_consistent_headings_score_high(self) -> None:
        """copy_editor_node gives high score to consistently formatted headings."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## The Quick Brown Fox\n\n"
                "Some content here.\n\n"
                "## The Faster Option\n\n"
                "## The Best Solution\n\n"
                "More content."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "heading_consistency_score" in result["copy_edit_metrics"]
        # All Title Case headings should score high
        assert result["copy_edit_metrics"]["heading_consistency_score"] == 1.0

    @pytest.mark.asyncio
    async def test_counts_exclamation_marks(self) -> None:
        """copy_editor_node counts exclamation marks in prose content."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is great! The results are amazing! We found improvements! "
                "Here is one more! And another!"
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "exclamation_rate" in result["copy_edit_metrics"]
        # Should have detected 5 exclamation marks in approximately 30 words
        # exclamation_rate = (count / prose_words) * 100, should be > 0
        assert result["copy_edit_metrics"]["exclamation_rate"] > 0

    @pytest.mark.asyncio
    async def test_high_exclamation_rate_lowers_score(self) -> None:
        """copy_editor_node penalizes high exclamation mark rate."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is amazing! Results are great! Everything works! "
                "So excited! Perfect solution! Nothing else matters!"
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_score" in result
        # High exclamation rate should lower the score
        assert result["copy_edit_score"] < 1.0

    @pytest.mark.asyncio
    async def test_detects_em_dash_no_spaces(self) -> None:
        """copy_editor_node detects em-dashes without proper spacing."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is word—word without spaces. "
                "Another bad—example here. "
                "Normal content continues."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "em_dash_spacing_issues" in result["copy_edit_metrics"]
        # Should detect em-dashes touching words on both sides
        assert result["copy_edit_metrics"]["em_dash_spacing_issues"] > 0

    @pytest.mark.asyncio
    async def test_proper_em_dash_spacing_not_flagged(self) -> None:
        """copy_editor_node does not flag properly spaced em-dashes."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is word — word with proper spaces. "
                "Another good — example here. "
                "Normal content continues."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "em_dash_spacing_issues" in result["copy_edit_metrics"]
        # Properly spaced em-dashes should not be flagged
        assert result["copy_edit_metrics"]["em_dash_spacing_issues"] == 0

    @pytest.mark.asyncio
    async def test_detects_repeated_words(self) -> None:
        """copy_editor_node detects consecutive repeated words."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This the the same thing. "
                "We is is working on it. "
                "Results results show improvement."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_metrics" in result
        assert "repeated_word_pairs" in result["copy_edit_metrics"]
        # Should detect at least one repeated word pair
        assert result["copy_edit_metrics"]["repeated_word_pairs"] >= 1

    @pytest.mark.asyncio
    async def test_passes_clean_copy(self) -> None:
        """copy_editor_node passes well-formatted content."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## Introduction\n\n"
                "This is clean prose. "
                "The formatting is consistent. "
                "No repeated words appear here.\n\n"
                "## Main Point\n\n"
                "Well spaced em-dashes appear like this — with spaces. "
                "Exclamation marks are minimal and tasteful. "
                "The copy is polished and professional."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "copy_edit_passed" in result
        assert result["copy_edit_passed"] is True

    @pytest.mark.asyncio
    async def test_structural_issue_added_on_fail(self) -> None:
        """copy_editor_node adds structural_check_issues when score is below threshold."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        # Content with multiple issues: mixed headings, high exclamation rate, repeated words
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## the quick fox\n\n"
                "This is great! Amazing! Wonderful! "
                "The the same thing is is very confusing."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await copy_editor_node(state)

        if not result.get("copy_edit_passed", True):
            assert "structural_check_issues" in result
            issues = result["structural_check_issues"]
            copy_issues = [i for i in issues if i.get("category") == "copy_edit_issues"]
            assert len(copy_issues) > 0
            assert copy_issues[0]["severity"] == "LOW"

    @pytest.mark.asyncio
    async def test_no_state_mutation_on_revision_loop(self) -> None:
        """copy_editor_node should not mutate state structural_check_issues on revision cycles."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        # Content that fails
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## the mixed case\n\n"
                "This is great! Amazing! "
                "Repeated repeated words here."
            ),
            tags=[],
            image_suggestions=[],
        )

        initial_state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        # First call — should fail and add to structural_check_issues
        result1 = await copy_editor_node(initial_state)
        if "structural_check_issues" in result1:
            first_cycle_issues_count = len(result1["structural_check_issues"])
            assert first_cycle_issues_count > 0

            # Second call (revision cycle) with the output from first as input
            state_after_first = {
                "run_id": "test-123",
                "post": mock_post,
                "structural_check_issues": result1["structural_check_issues"],
            }

            result2 = await copy_editor_node(state_after_first)
            if "structural_check_issues" in result2:
                second_cycle_issues_count = len(result2["structural_check_issues"])

                # Should not accumulate (replace not append)
                assert second_cycle_issues_count == first_cycle_issues_count

    @pytest.mark.asyncio
    async def test_includes_completed_steps(self) -> None:
        """copy_editor_node includes completed_steps in result."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is a test.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await copy_editor_node(state)

        assert "completed_steps" in result
        assert isinstance(result["completed_steps"], list)
        assert "copy_edit_check" in result["completed_steps"]


class TestCopyEditorScoreCap:
    """Test that the heading bonus cap prevents bad copy from passing via heading consistency."""

    @pytest.mark.asyncio
    async def test_high_penalty_cannot_be_rescued_by_heading_bonus(self) -> None:
        """Post with em_dash=4, repeated_pairs=3, exclamation_rate>=3%, heading_consistency=1.0
        must score below 0.55 — the heading bonus cap (0.10 when total_penalties>0.30) prevents
        a genuinely bad post from passing on heading consistency alone."""
        from app.agents.nodes.copy_editor_node import copy_editor_node
        from app.agents.content_generator import GeneratedPost

        # Build content that produces:
        #   em_dash_issues    = 4  → penalty = 4 * 0.04 = 0.16
        #   repeated_pairs    = 3  → penalty = 3 * 0.05 = 0.15
        #   exclamation_rate >= 3% → penalty = 0.30 (capped)
        #   total_penalties   = 0.61  (> 0.30 → cap kicks in)
        #   heading_bonus     capped at 0.10 (not 0.15)
        #   score = 1.0 - 0.61 + (0.10 - 0.15) = 0.34  → FAIL
        # Headings are all Title Case (heading_consistency_score = 1.0).
        words = " ".join(["word"] * 100)  # 100 filler words to control rate denominator
        exclamations = "Amazing! " * 5    # 5 exclamation marks in ~10 words → high rate
        em_dashes = (
            "first—second third—fourth fifth—sixth seventh—eighth "  # 4 \w—\w patterns
        )
        repeated = "the the same same is is "  # 3 repeated word pairs

        content = (
            "## The First Heading\n\n"
            "## The Second Heading\n\n"
            "## The Third Heading\n\n"
            f"{exclamations}{em_dashes}{repeated}{words}"
        )

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=content,
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-cap-123", "post": mock_post}

        result = await copy_editor_node(state)

        metrics = result["copy_edit_metrics"]
        # Verify the post actually has the three issues we designed it to have
        assert metrics["em_dash_spacing_issues"] >= 4, (
            f"Expected >= 4 em-dash issues, got {metrics['em_dash_spacing_issues']}"
        )
        assert metrics["repeated_word_pairs"] >= 3, (
            f"Expected >= 3 repeated pairs, got {metrics['repeated_word_pairs']}"
        )
        assert metrics["exclamation_rate"] >= 3.0, (
            f"Expected exclamation_rate >= 3.0, got {metrics['exclamation_rate']}"
        )
        assert metrics["heading_consistency_score"] == 1.0, (
            f"Expected perfect heading consistency, got {metrics['heading_consistency_score']}"
        )
        assert metrics["total_penalties"] > 0.30, (
            f"Expected total_penalties > 0.30 to trigger cap, got {metrics['total_penalties']}"
        )

        # The critical assertion: heading bonus cap must prevent this post from passing
        assert result["copy_edit_score"] < 0.55, (
            f"Expected copy_edit_score < 0.55 but got {result['copy_edit_score']}. "
            f"The heading bonus cap is not working — bad copy is passing via heading consistency."
        )
        assert result["copy_edit_passed"] is False
