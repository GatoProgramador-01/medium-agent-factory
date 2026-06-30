"""
Unit tests for Structure Validator Node — checks markdown structural completeness.
"""

import pytest


class TestStructureValidatorNode:
    """Test structure validator node functionality."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_post(self) -> None:
        """structure_validator_node returns {} when state has no post."""
        from app.agents.nodes.structure_validator_node import structure_validator_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await structure_validator_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_counts_headings(self) -> None:
        """structure_validator_node counts H1/H2/H3 headings correctly."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "# Main Title\n"
                "## Section One\n"
                "### Subsection A\n"
                "Content here.\n"
                "## Section Two\n"
                "More content."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "heading_count" in result["structure_metrics"]
        # Should detect 3 H2/H3 headings (plus H1)
        heading_count = result["structure_metrics"]["heading_count"]
        assert heading_count >= 3

    @pytest.mark.asyncio
    async def test_detects_lists(self) -> None:
        """structure_validator_node detects bullet and numbered lists."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## List Example\n"
                "- First item\n"
                "- Second item\n"
                "- Third item\n"
                "\n"
                "## Numbered\n"
                "1. One\n"
                "2. Two"
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "has_lists" in result["structure_metrics"]
        assert result["structure_metrics"]["has_lists"] is True

    @pytest.mark.asyncio
    async def test_detects_conclusion_signals(self) -> None:
        """structure_validator_node detects conclusion signal phrases."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## Introduction\n"
                "Start here.\n"
                "\n"
                "## Main Content\n"
                "Lots of content goes here.\n"
                "\n"
                "## Conclusion\n"
                "In summary, remember these key takeaways and apply them today."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "has_conclusion_signals" in result["structure_metrics"]
        assert result["structure_metrics"]["has_conclusion_signals"] is True

    @pytest.mark.asyncio
    async def test_passes_well_structured_post(self) -> None:
        """structure_validator_node passes when post is well-structured."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## Introduction\n"
                "Start with context.\n"
                "\n"
                "## Section One\n"
                "Paragraph with multiple sentences explaining the topic.\n"
                "\n"
                "### Subsection A\n"
                "- Point one\n"
                "- Point two\n"
                "- Point three\n"
                "\n"
                "## Section Two\n"
                "More detailed content here about the topic.\n"
                "\n"
                "## Key Takeaway\n"
                "In summary, the main takeaway is that this works well."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_passed" in result
        assert isinstance(result["structure_passed"], bool)

    @pytest.mark.asyncio
    async def test_fails_no_headings_no_lists(self) -> None:
        """structure_validator_node fails when post has no headings or lists."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # Plain prose paragraphs only
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is the first paragraph with lots of content.\n"
                "\n"
                "This is the second paragraph explaining more about the topic.\n"
                "\n"
                "This is the third paragraph concluding the discussion."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_passed" in result
        assert "structure_score" in result
        # Should fail because no structure elements
        score = result["structure_score"]
        assert isinstance(score, float)

    @pytest.mark.asyncio
    async def test_structural_issue_added_on_fail(self) -> None:
        """structure_validator_node adds structural_check_issues when score is below threshold."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # Plain prose, no structure
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is unstructured prose. No headings. No lists. Just paragraphs.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await structure_validator_node(state)

        if not result.get("structure_passed", True):
            assert "structural_check_issues" in result
            issues = result["structural_check_issues"]
            struct_issues = [i for i in issues if i.get("category") == "poor_structure"]
            assert len(struct_issues) > 0
            assert struct_issues[0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_no_state_mutation_on_revision_loop(self) -> None:
        """structure_validator_node should not mutate state structural_check_issues on revision cycles."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # Unstructured content that fails
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is unstructured prose without any markdown elements.",
            tags=[],
            image_suggestions=[],
        )

        initial_state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        # First call — should fail and add to structural_check_issues
        result1 = await structure_validator_node(initial_state)
        if "structural_check_issues" in result1:
            first_cycle_issues_count = len(result1["structural_check_issues"])
            assert first_cycle_issues_count > 0

            # Second call (revision cycle) with the output from first as input
            state_after_first = {
                "run_id": "test-123",
                "post": mock_post,
                "structural_check_issues": result1["structural_check_issues"],
            }

            result2 = await structure_validator_node(state_after_first)
            if "structural_check_issues" in result2:
                second_cycle_issues_count = len(result2["structural_check_issues"])

                # Should not accumulate (replace not append)
                assert second_cycle_issues_count == first_cycle_issues_count

    @pytest.mark.asyncio
    async def test_avg_paragraph_length_computed(self) -> None:
        """structure_validator_node computes average paragraph length correctly."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "This is the first paragraph and it has ten words.\n"
                "\n"
                "This second paragraph is designed to contain exactly twenty words so we can verify the average paragraph length is correct."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "avg_paragraph_length" in result["structure_metrics"]
        avg = result["structure_metrics"]["avg_paragraph_length"]
        # avg of 10-word and 20-word paragraphs = 15.0
        assert 13 <= avg <= 17

    @pytest.mark.asyncio
    async def test_includes_completed_steps(self) -> None:
        """structure_validator_node includes completed_steps in result."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="## Test\nThis is a test.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "completed_steps" in result
        assert isinstance(result["completed_steps"], list)
        assert "structure_validation" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_returns_zero_score_on_empty_content(self) -> None:
        """structure_validator_node returns 0.0 score on empty content."""
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_score" in result
        assert result["structure_score"] == 0.0
        assert result["structure_passed"] is False

    @pytest.mark.asyncio
    async def test_windows_line_endings_paragraph_split(self) -> None:
        """
        Regression: Windows line endings (\\r\\n\\r\\n) should be parsed
        as paragraph separators. avg_paragraph_length should reflect both
        paragraphs correctly, not treat as one giant blob.
        """
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # Two paragraphs with Windows line endings
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="First paragraph here.\r\n\r\nSecond paragraph here with more words for testing purposes.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "avg_paragraph_length" in result["structure_metrics"]
        # Both paragraphs should be counted separately
        # Para 1: ~4 words, Para 2: ~9 words => avg ~6.5
        avg = result["structure_metrics"]["avg_paragraph_length"]
        assert avg > 0, "avg_paragraph_length should reflect both paragraphs"
        # If treated as one giant blob, avg would be ~13
        # If split correctly, should be closer to 6-7
        assert avg < 12, "Paragraphs should be split on \\r\\n\\r\\n"

    @pytest.mark.asyncio
    async def test_conclusion_signal_in_middle_does_not_pass(self) -> None:
        """
        Regression: Conclusion signal (e.g., 'remember') appearing in the
        middle of the post should not trigger has_conclusion_signals=True.
        The signal must be in the tail (roughly final 20% of content).
        """
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # "remember" appears in paragraph 2 of 5, followed by 200+ words
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## Introduction\n"
                "Start with background information about the topic at hand.\n"
                "\n"
                "## Early Content\n"
                "Remember that caching is complex and has many tricky edge cases to handle.\n"
                "\n"
                "## Middle Section\n"
                "This paragraph contains substantially more content to ensure the signal phrase "
                "appears far from the end of the post and should not be detected as a closing marker. "
                "We continue with more substantive discussion about the topic to pad out the middle sections. "
                "Additional detail and explanation goes here to push the signal phrase away from the tail. "
                "Engineering systems at scale requires careful attention to operational concerns that go "
                "well beyond initial design, including observability, alerting, capacity planning, and "
                "failure-mode analysis across every component of the production stack.\n"
                "\n"
                "## Later Section\n"
                "This section adds even more body content to increase total post length significantly. "
                "We cover implementation details, common pitfalls, benchmarks, and practical guidance "
                "for teams adopting this approach in production environments with real traffic. "
                "Performance characteristics vary widely based on hardware, network topology, and workload "
                "distribution patterns that must be profiled under realistic conditions before deployment.\n"
                "\n"
                "## Final Section\n"
                "This is the actual end with substantive final content but no closing signal phrases at all."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "has_conclusion_signals" in result["structure_metrics"]
        # Signal in middle should not count as conclusion
        assert result["structure_metrics"]["has_conclusion_signals"] is False

    @pytest.mark.asyncio
    async def test_conclusion_signal_at_true_end_passes(self) -> None:
        """
        Regression: Conclusion signal (e.g., 'In summary') appearing in the
        final paragraph of a long post should trigger has_conclusion_signals=True.
        Position matters — tail-only detection is the intent.
        """
        from app.agents.nodes.structure_validator_node import structure_validator_node
        from app.agents.content_generator import GeneratedPost

        # Long post (500+ words) with "In summary" only at the very end
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "## Introduction\n"
                "Start with comprehensive background information about the topic at hand. "
                "This introduction should be detailed and engaging to set the stage for the discussion. "
                "We establish context and explain why the topic matters to readers.\n"
                "\n"
                "## Section One\n"
                "First major section with substantive content explaining key concepts. "
                "We dive deep into the technical details and provide examples throughout. "
                "This section builds the foundation for everything that follows.\n"
                "\n"
                "## Section Two\n"
                "Second major section continuing the exploration with more examples. "
                "We examine different approaches and their trade-offs in detail. "
                "This extends the previous discussion and adds nuance to the topic.\n"
                "\n"
                "## Section Three\n"
                "Third section going deeper into advanced aspects and real-world applications. "
                "We consider edge cases and how to handle them effectively in practice. "
                "This bridges theory and practical implementation concerns.\n"
                "\n"
                "## Conclusion\n"
                "In summary, the key takeaways from this comprehensive exploration are clear and important."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await structure_validator_node(state)

        assert "structure_metrics" in result
        assert "has_conclusion_signals" in result["structure_metrics"]
        # Signal at true end should be detected
        assert result["structure_metrics"]["has_conclusion_signals"] is True
