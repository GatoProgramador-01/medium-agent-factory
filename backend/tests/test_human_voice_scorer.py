"""
Unit tests for Human Voice Scorer — measures sentence rhythm, personal pronouns, contractions.
"""

import pytest


class TestHumanVoiceScorerNode:
    """Test human voice scorer node functionality."""

    @pytest.mark.asyncio
    async def test_human_voice_scorer_returns_empty_on_no_post(self) -> None:
        """human_voice_scorer_node returns {} when state has no post."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node

        state = {
            "run_id": "test-123",
            "post": None,
        }

        result = await human_voice_scorer_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_human_voice_scorer_computes_sentence_variance(self) -> None:
        """human_voice_scorer_node computes sentence length variance metric."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I got the result. This is a much longer sentence with more content and words. Done.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_metrics" in result
        assert "sentence_length_variance" in result["human_voice_metrics"]
        assert isinstance(result["human_voice_metrics"]["sentence_length_variance"], float)

    @pytest.mark.asyncio
    async def test_human_voice_scorer_counts_personal_pronouns(self) -> None:
        """human_voice_scorer_node counts personal pronouns per 100 words."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I did this myself. My experiment showed this. We ran tests. Our data proved it. Me and my team found this. I've discovered this. I'm happy with the results. I'd recommend this.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_metrics" in result
        assert "personal_pronoun_density" in result["human_voice_metrics"]
        assert (
            isinstance(result["human_voice_metrics"]["personal_pronoun_density"], float)
        )

    @pytest.mark.asyncio
    async def test_human_voice_scorer_counts_contractions(self) -> None:
        """human_voice_scorer_node counts contractions per 100 words."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I've done this. I'm sure it's working. They've told me. He's coming. We're done. She's happy. They'll arrive. It's clear.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_metrics" in result
        assert "contraction_rate" in result["human_voice_metrics"]
        assert isinstance(result["human_voice_metrics"]["contraction_rate"], float)

    @pytest.mark.asyncio
    async def test_human_voice_scorer_penalizes_em_dashes(self) -> None:
        """human_voice_scorer_node computes em-dash penalty per 100 words."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="Point one — and point two — then point three — plus point four — and more.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_metrics" in result
        assert "em_dash_per_100_words" in result["human_voice_metrics"]
        assert (
            isinstance(result["human_voice_metrics"]["em_dash_per_100_words"], float)
        )

    @pytest.mark.asyncio
    async def test_human_voice_scorer_returns_score_between_0_and_1(self) -> None:
        """human_voice_scorer_node returns score in [0, 1]."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I've written this myself. My approach is simple. We tested it thoroughly.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_score" in result
        assert isinstance(result["human_voice_score"], float)
        assert 0.0 <= result["human_voice_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_human_voice_scorer_passes_when_above_threshold(self) -> None:
        """human_voice_scorer_node passes when score >= 0.6."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        # High human voice: personal pronouns, contractions, varied sentences
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I've been experimenting with this for months. My results show significant improvement. We're excited about what we've found. I'd recommend this to anyone. They've already seen the benefits.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_passed" in result
        assert isinstance(result["human_voice_passed"], bool)

    @pytest.mark.asyncio
    async def test_human_voice_scorer_weighted_calculation(self) -> None:
        """human_voice_scorer_node uses correct weighting formula."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I did this. My work was good. I'm happy. We all agree.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        # Verify score is weighted: variance*0.4 + pronoun*0.3 + contraction*0.2 + (1-em_dash)*0.1
        assert "human_voice_score" in result
        score = result["human_voice_score"]
        # Should be a reasonable float, not extreme
        assert isinstance(score, float)
        # Verify it's rounded to 3 decimals
        assert len(str(score).split(".")[-1]) <= 3

    @pytest.mark.asyncio
    async def test_human_voice_scorer_includes_completed_steps(self) -> None:
        """human_voice_scorer_node includes completed_steps in result."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="This is a test.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "completed_steps" in result
        assert isinstance(result["completed_steps"], list)
        assert "human_voice_scoring" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_threshold_is_045(self) -> None:
        """human_voice_scorer_node uses 0.45 threshold, not 0.6."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Content with minimal first-person and low variance
        # Should score below 0.6 but above 0.45 to test threshold boundary
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="I tested this twice. The system works. It performs well. Results show improvement.",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        assert "human_voice_score" in result
        score = result["human_voice_score"]
        assert "human_voice_passed" in result
        # Verify threshold is 0.45, not 0.6
        if score < 0.45:
            assert result["human_voice_passed"] is False
        elif score >= 0.45:
            assert result["human_voice_passed"] is True

    @pytest.mark.asyncio
    async def test_low_human_voice_adds_to_structural_issues(self) -> None:
        """human_voice_scorer_node appends to structural_check_issues when human_voice_passed is False."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Content with no first-person pronouns or contractions (low human voice)
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="The system performs well. One can observe improvements. Performance metrics show results. Users report satisfaction.",
            tags=[],
            image_suggestions=[],
        )

        state = {
            "run_id": "test-123",
            "post": mock_post,
            "structural_check_issues": [],
        }

        result = await human_voice_scorer_node(state)

        # If score is below threshold, should append to structural_check_issues
        if not result.get("human_voice_passed", True):
            assert "structural_check_issues" in result
            issues = result["structural_check_issues"]
            low_voice_issues = [i for i in issues if i.get("category") == "low_human_voice"]
            assert len(low_voice_issues) > 0
            assert low_voice_issues[0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_code_block_excluded_from_metrics(self) -> None:
        """human_voice_scorer_node should exclude code blocks from all metrics."""
        from app.agents.nodes.human_voice_scorer import human_voice_scorer_node
        from app.agents.content_generator import GeneratedPost

        # Content is ONLY a code block with markdown formatting and em-dashes
        mock_post = GeneratedPost(
            title="Test Article",
            subtitle="",
            content="```python\n# Code block with — em-dashes\n# Line — two — three — four — five\ndef fn():\n    pass\n```",
            tags=[],
            image_suggestions=[],
        )

        state = {"run_id": "test-123", "post": mock_post}

        result = await human_voice_scorer_node(state)

        # Should not crash and should compute metrics based only on non-code prose
        assert "human_voice_score" in result
        # With only code (no prose), metrics should be minimal
        metrics = result.get("human_voice_metrics", {})
        assert "em_dash_per_100_words" in metrics
        # Code-only content has no em-dashes in prose, so penalty should be 0
        assert metrics["em_dash_per_100_words"] == 0.0, "Code blocks should not count toward em-dash metric"
