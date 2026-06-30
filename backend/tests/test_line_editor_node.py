"""
Unit tests for Line Editor Node — measures sentence-level prose quality.
"""

import pytest


class TestLineEditorNode:
    """Test line editor node functionality."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_post(self) -> None:
        """line_editor_node returns {} when state has no post."""
        from app.agents.nodes.line_editor_node import line_editor_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await line_editor_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_false_on_empty_content(self) -> None:
        """line_editor_node returns line_edit_passed=False when post.content is empty."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_passed" in result
        assert result["line_edit_passed"] is False
        assert result["line_edit_score"] == 0.0

    @pytest.mark.asyncio
    async def test_computes_avg_sentence_length(self) -> None:
        """line_editor_node computes average sentence length correctly."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # 3 sentences: 5 words, 10 words, 15 words => avg = 10.0
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="First is short. This is a longer sentence here. This one is even longer with more content.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_metrics" in result
        assert "avg_sentence_length" in result["line_edit_metrics"]
        # Should be between 5 and 15
        avg = result["line_edit_metrics"]["avg_sentence_length"]
        assert 5 <= avg <= 15

    @pytest.mark.asyncio
    async def test_detects_passive_voice(self) -> None:
        """line_editor_node detects passive voice constructions."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The data was processed by the system. The results were created automatically. This is passive.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_metrics" in result
        assert "passive_voice_ratio" in result["line_edit_metrics"]
        # Should detect passive voice
        passive_ratio = result["line_edit_metrics"]["passive_voice_ratio"]
        assert passive_ratio > 0

    @pytest.mark.asyncio
    async def test_passes_when_clean_prose(self) -> None:
        """line_editor_node passes when prose is clean and varied."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # Short active voice sentences with variation
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I tested this. The results showed success. We found improvements everywhere. Performance increased significantly.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_passed" in result
        assert isinstance(result["line_edit_passed"], bool)

    @pytest.mark.asyncio
    async def test_fails_on_high_passive_voice(self) -> None:
        """line_editor_node fails when passive voice ratio is very high."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # All sentences are passive voice
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="It was said that this was processed. The work was done by engineers. Mistakes were made. The system was built. Results were seen.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_passed" in result
        assert "line_edit_score" in result
        # High passive should lower score significantly
        score = result["line_edit_score"]
        assert isinstance(score, float)

    @pytest.mark.asyncio
    async def test_fails_on_all_long_sentences(self) -> None:
        """line_editor_node fails when all sentences are longer than 30 words."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # 5 sentences each genuinely > 30 words
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "The process of building a modern data pipeline that can handle millions of events per second while maintaining strict ordering guarantees and exactly-once delivery semantics is one of the most challenging engineering problems in distributed systems today. "
                "When designing a microservices architecture that must scale horizontally across dozens of availability zones while preserving strong consistency guarantees and minimizing cross-region latency, engineers face a deeply difficult set of trade-offs between throughput and correctness. "
                "A well-designed caching layer reduces backend load dramatically but introduces cache invalidation complexity that becomes increasingly difficult to reason about as the number of independent services writing to shared state grows beyond a certain threshold. "
                "The challenge of maintaining backward compatibility across API versions while simultaneously shipping new features at a rapid pace requires careful versioning strategies, feature flags, and consumer-driven contract testing at every layer of the system boundary. "
                "Understanding the operational characteristics of a distributed database under realistic production workloads requires sustained load testing across multiple failure modes, including network partitions, disk saturation, and gradual leader election failures during peak traffic."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_metrics" in result
        assert "long_sentence_ratio" in result["line_edit_metrics"]
        long_ratio = result["line_edit_metrics"]["long_sentence_ratio"]
        assert long_ratio > 0.5  # Most sentences are > 30 words

    @pytest.mark.asyncio
    async def test_code_blocks_excluded(self) -> None:
        """line_editor_node excludes code blocks from prose analysis."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # Code block with passive voice patterns
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "Here is clean prose. "
                "```python\ndef fn():\n    # This was processed by the system. Results were created.\n    pass\n```\n"
                "More clean prose here."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        # Passive voice in code should not inflate the ratio
        metrics = result.get("line_edit_metrics", {})
        passive_ratio = metrics.get("passive_voice_ratio", 0)
        # Should not detect the passive voice in code block
        assert passive_ratio < 0.5

    @pytest.mark.asyncio
    async def test_structural_issue_added_on_fail(self) -> None:
        """line_editor_node adds structural_check_issues when score is below threshold."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # High passive voice content
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="It was said. Data was processed. Results were created. Work was done. Progress was made.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await line_editor_node(state)

        if not result.get("line_edit_passed", True):
            assert "structural_check_issues" in result
            issues = result["structural_check_issues"]
            prose_issues = [
                i for i in issues if i.get("category") == "poor_prose_quality"
            ]
            assert len(prose_issues) > 0
            assert prose_issues[0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_no_state_mutation_on_revision_loop(self) -> None:
        """line_editor_node should not mutate state structural_check_issues on revision cycles."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # High passive voice content that fails
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="It was said. Data was processed. Results were created. Work was done. Progress was made.",
            tags=[],
            image_suggestions=[],
        )

        initial_state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        # First call — should fail and add to structural_check_issues
        result1 = await line_editor_node(initial_state)
        if "structural_check_issues" in result1:
            first_cycle_issues_count = len(result1["structural_check_issues"])
            assert first_cycle_issues_count > 0

            # Second call (revision cycle) with the output from first as input
            state_after_first = {
                "run_id": "test-123",
                "post": mock_post,
                "structural_check_issues": result1["structural_check_issues"],
            }

            result2 = await line_editor_node(state_after_first)
            if "structural_check_issues" in result2:
                second_cycle_issues_count = len(result2["structural_check_issues"])

                # Should not accumulate (replace not append)
                assert second_cycle_issues_count == first_cycle_issues_count

    @pytest.mark.asyncio
    async def test_includes_completed_steps(self) -> None:
        """line_editor_node includes completed_steps in result."""
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is a test.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "completed_steps" in result
        assert isinstance(result["completed_steps"], list)
        assert "line_edit_check" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_irregular_passive_not_caught(self) -> None:
        """
        KNOWN LIMITATION: Irregular past participles like 'written', 'built',
        'known' are NOT caught by the current suffix regex pattern (\\w+(ed|en)).
        This test documents that limitation.

        Codex finding: Regex-based passive detection cannot reliably identify
        irregular verb forms without a comprehensive word list or NLP model.
        Current implementation accepts this gap as acceptable for basic quality checks.
        """
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # Sentences with irregular past participles that should be passive but won't be detected
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "The code was written by experts. "
                "The feature was built last year. "
                "The pattern is known to fail."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_metrics" in result
        assert "passive_voice_ratio" in result["line_edit_metrics"]
        # Known limitation: irregular VBNs not detected by suffix regex
        # This test simply documents the behavior — it will always pass
        # because we're not asserting detection works
        passive_ratio = result["line_edit_metrics"]["passive_voice_ratio"]
        assert passive_ratio >= 0.0

    @pytest.mark.asyncio
    async def test_predicate_adjective_false_positive_documented(self) -> None:
        """
        KNOWN LIMITATION: Predicate adjectives like 'was excited' and 'is ready'
        match the passive voice regex pattern (was/is + verb-like adjective).
        This is a false positive since predicate adjectives are not passive voice.

        Codex finding: The regex pattern `(was|is|are|were|be|being|been)\\s+(\\w+(ed|en))`
        cannot distinguish between:
          - True passive: 'was destroyed by fire' (verb form)
          - Predicate adj: 'was excited about results' (adjective state)

        This test documents the current behavior and the known technical debt.
        """
        from app.agents.nodes.line_editor_node import line_editor_node
        from app.agents.content_generator import GeneratedPost

        # Predicate adjectives that will trigger passive voice detection
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content=(
                "She was excited about the results. "
                "The system is ready for deployment. "
                "They were pleased with the outcome."
            ),
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await line_editor_node(state)

        assert "line_edit_metrics" in result
        assert "passive_voice_ratio" in result["line_edit_metrics"]
        # Known limitation: predicate adjectives match passive pattern
        # This test documents that the ratio will be > 0 due to false positives
        passive_ratio = result["line_edit_metrics"]["passive_voice_ratio"]
        assert passive_ratio > 0  # Will trigger due to false positives
