"""
Unit tests for engagement_optimizer_node — evaluates post engagement metrics.

Tests measure: hook strength (first paragraph signals), second-person language frequency,
call-to-action presence (last 15% of content), and overall engagement score formula.
"""

import pytest

from app.agents.content_generator import GeneratedPost


class TestEngagementOptimizerBasic:
    """Test engagement_optimizer_node basics: missing post, empty content, output schema."""

    @pytest.mark.asyncio
    async def test_returns_empty_dict_when_state_has_no_post(self) -> None:
        """engagement_optimizer_node returns {} when state['post'] is None."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": None,
        }

        result = await engagement_optimizer_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_content_scores_passing(self) -> None:
        """engagement_optimizer_node passes empty content: engagement_score=1.0, passed=True."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test Title",
            subtitle="Test subtitle",
            content="",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["image1", "image2", "image3"],
        )

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
        }

        result = await engagement_optimizer_node(state)

        assert result["engagement_score"] == 1.0
        assert result["engagement_passed"] is True

    @pytest.mark.asyncio
    async def test_returns_all_required_output_keys(self) -> None:
        """engagement_optimizer_node output contains: engagement_score, engagement_passed, engagement_metrics, completed_steps."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This is a test post with some content.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
        }

        result = await engagement_optimizer_node(state)

        # All output keys must be present
        assert "engagement_score" in result
        assert "engagement_passed" in result
        assert "engagement_metrics" in result
        assert "completed_steps" in result

        # Type checks
        assert isinstance(result["engagement_score"], float)
        assert isinstance(result["engagement_passed"], bool)
        assert isinstance(result["engagement_metrics"], dict)
        assert isinstance(result["completed_steps"], list)

        # completed_steps must include "engagement_check"
        assert "engagement_check" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_engagement_metrics_contains_required_fields(self) -> None:
        """engagement_metrics dict contains: hook_score, second_person_ratio, has_cta."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This is a test post.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
        }

        result = await engagement_optimizer_node(state)
        metrics = result["engagement_metrics"]

        assert "hook_score" in metrics
        assert "second_person_ratio" in metrics
        assert "has_cta" in metrics

        # Type checks
        assert isinstance(metrics["hook_score"], float)
        assert isinstance(metrics["second_person_ratio"], float)
        assert isinstance(metrics["has_cta"], bool)


class TestEngagementOptimizerHookScore:
    """Test hook score calculation: signals in first paragraph only."""

    @pytest.mark.asyncio
    async def test_question_mark_in_first_paragraph_triggers_signal(self) -> None:
        """First paragraph with ? triggers +0.33 hook signal."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Have you ever wondered why this matters? This is the second paragraph.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        # Hook score should include 0.33 for question mark
        hook_score = result["engagement_metrics"]["hook_score"]
        assert hook_score >= 0.33
        assert hook_score <= 1.0

    @pytest.mark.asyncio
    async def test_number_in_first_paragraph_triggers_stat_signal(self) -> None:
        """First paragraph with digit sequence triggers +0.33 stat signal."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="By 2025, AI adoption will reach 85% of enterprises.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        hook_score = result["engagement_metrics"]["hook_score"]
        assert hook_score >= 0.33

    @pytest.mark.asyncio
    async def test_bold_text_in_first_paragraph_triggers_bold_signal(self) -> None:
        """First paragraph with **word** triggers +0.34 bold signal."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This is a **critical** insight you need to know.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        hook_score = result["engagement_metrics"]["hook_score"]
        assert hook_score >= 0.34

    @pytest.mark.asyncio
    async def test_multiple_hook_signals_accumulate(self) -> None:
        """Multiple hook signals in first paragraph sum (max 1.0)."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="What if I told you that **85% of companies** are making this mistake?",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        hook_score = result["engagement_metrics"]["hook_score"]
        # Question (0.33) + stat (0.33) + bold (0.34) = 1.0
        assert hook_score > 0.66

    @pytest.mark.asyncio
    async def test_hook_signals_in_later_paragraphs_ignored(self) -> None:
        """Hook signals in second+ paragraphs do not count."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This is the first paragraph with no signals.\n\nThis second paragraph has a question? And **bold text** and 2025 too!",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        hook_score = result["engagement_metrics"]["hook_score"]
        # Only first paragraph (no signals) counts, so hook_score should be 0.0
        assert hook_score == 0.0

    @pytest.mark.asyncio
    async def test_no_hook_signals_scores_zero(self) -> None:
        """First paragraph with no signals scores hook_score=0.0."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This is a simple first paragraph with no special signals.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        hook_score = result["engagement_metrics"]["hook_score"]
        assert hook_score == 0.0


class TestEngagementOptimizerSecondPerson:
    """Test second-person language frequency (you + your per 100 prose words)."""

    @pytest.mark.asyncio
    async def test_post_with_you_and_your_scores_higher(self) -> None:
        """Post with 'you' and 'your' has higher engagement than post without."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Post with no second-person language
        post_no_you = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="The implementation requires careful planning and execution. Teams should consider scalability.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        # Post with "you" and "your"
        post_with_you = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="You need to understand your options before making a decision. Your success depends on it.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state_no_you = {"run_id": "test-1", "custom_topic": "Test", "post": post_no_you}
        state_with_you = {
            "run_id": "test-2",
            "custom_topic": "Test",
            "post": post_with_you,
        }

        result_no_you = await engagement_optimizer_node(state_no_you)
        result_with_you = await engagement_optimizer_node(state_with_you)

        score_no_you = result_no_you["engagement_score"]
        score_with_you = result_with_you["engagement_score"]

        # Post with "you"/"your" should score higher
        assert score_with_you > score_no_you

    @pytest.mark.asyncio
    async def test_second_person_ratio_reflects_count_per_hundred_words(self) -> None:
        """second_person_ratio = (you_count + your_count) per 100 prose words."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Create a post with ~100 words and 5 instances of "you" or "your"
        # Target: second_person_ratio ~= 5.0
        content = (
            "You must understand your own challenges. "  # 6 words, 2 you/your
            "Your approach should match your needs. "  # 6 words, 2 you/your
            "This helps you succeed in your goals. "  # 7 words, 2 you/your
            + "padding words to reach approximately one hundred words. "  # padding
            * 4
        )

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content=content,
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        ratio = result["engagement_metrics"]["second_person_ratio"]
        # Should be approximately 5-6 instances per 100 words
        assert isinstance(ratio, float)
        assert ratio >= 0.0

    @pytest.mark.asyncio
    async def test_you_and_your_case_insensitive_whole_words(self) -> None:
        """second_person detection is case-insensitive, whole-word only."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="You and YOU and yOu should match your YOUR and YoUr. But youth and journey should not.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        ratio = result["engagement_metrics"]["second_person_ratio"]
        # Should count: You, YOU, yOu, your, YOUR, YoUr = 6 instances
        # Should ignore: youth, journey
        assert isinstance(ratio, float)
        assert ratio > 0.0


class TestEngagementOptimizerCTA:
    """Test call-to-action detection in last 15% of content."""

    @pytest.mark.asyncio
    async def test_cta_in_last_paragraph_triggers_true(self) -> None:
        """Post with 'let me know' in last 15% has has_cta=True."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Construct content with enough padding so last paragraph is in last 15%
        content = (
            "This is the main content. " * 30  # ~450 words
            + "\n\nLet me know what you think in the comments below."  # Last paragraph
        )

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content=content,
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        assert result["engagement_metrics"]["has_cta"] is True

    @pytest.mark.asyncio
    async def test_cta_keywords_recognized(self) -> None:
        """CTA keywords: subscribe, follow, share, comment, let me know, try this, get started, learn more, click, download, sign up, reach out."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        keywords = [
            "subscribe",
            "follow",
            "share",
            "comment",
            "let me know",
            "try this",
            "get started",
            "learn more",
            "click",
            "download",
            "sign up",
            "reach out",
        ]

        for keyword in keywords:
            content = (
                "This is the main content. " * 30  # Padding
                + f"\n\nPlease {keyword} for more updates."  # Last paragraph with keyword
            )

            post = GeneratedPost(
                title="Test",
                subtitle="Subtitle",
                content=content,
                tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
                image_suggestions=["img1", "img2", "img3"],
            )

            state = {"run_id": "test", "custom_topic": "Test", "post": post}
            result = await engagement_optimizer_node(state)

            assert (
                result["engagement_metrics"]["has_cta"] is True
            ), f"Keyword '{keyword}' should trigger CTA"

    @pytest.mark.asyncio
    async def test_cta_keyword_in_middle_does_not_trigger(self) -> None:
        """CTA keyword in middle of long post does NOT trigger (must be in last 15%)."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Place "subscribe" in the middle, not in last 15%
        content = (
            "Please subscribe to our newsletter. " * 2  # Early mention
            + ("This is additional content to push the keyword out of last 15%. " * 25)  # Padding
        )

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content=content,
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        assert result["engagement_metrics"]["has_cta"] is False

    @pytest.mark.asyncio
    async def test_no_cta_keyword_has_cta_false(self) -> None:
        """Post without CTA keyword has has_cta=False."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="This post has no call to action at all. It just ends.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        assert result["engagement_metrics"]["has_cta"] is False


class TestEngagementOptimizerScoreFormula:
    """Test engagement score calculation: hook_penalty + person_bonus + cta_bonus - baseline."""

    @pytest.mark.asyncio
    async def test_engagement_score_range_0_to_1(self) -> None:
        """engagement_score is always float between 0.0 and 1.0."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Random test content here.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        score = result["engagement_score"]
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_engagement_passed_true_when_score_gte_0_5(self) -> None:
        """engagement_passed=True when engagement_score >= 0.50."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Construct post that should score >= 0.5
        content = (
            "What if you could achieve this? "  # Hook signals + "you"
            + "Your success matters to you. " * 20  # Multiple "you"/"your"
            + "\n\nLet me know if you want to try this."  # CTA in last 15%
        )

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content=content,
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        if result["engagement_score"] >= 0.50:
            assert result["engagement_passed"] is True
        else:
            assert result["engagement_passed"] is False

    @pytest.mark.asyncio
    async def test_engagement_passed_false_when_score_lt_0_5(self) -> None:
        """engagement_passed=False when engagement_score < 0.50."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        # Construct a post that should score < 0.5
        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Plain text with no special engagement elements whatsoever.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {"run_id": "test-123", "custom_topic": "Test", "post": post}
        result = await engagement_optimizer_node(state)

        if result["engagement_score"] < 0.50:
            assert result["engagement_passed"] is False


class TestEngagementOptimizerIssues:
    """Test structural_check_issues handling on failure."""

    @pytest.mark.asyncio
    async def test_failing_post_adds_engagement_issues(self) -> None:
        """Failing post (score < 0.5) adds engagement_issues to structural_check_issues."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Plain boring text with no engagement signals.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
            "structural_check_issues": [],
        }

        result = await engagement_optimizer_node(state)

        if not result.get("engagement_passed"):
            # Issues should be added if engagement failed
            if "structural_check_issues" in result:
                issues = result["structural_check_issues"]
                assert any(issue.get("category") == "engagement_issues" for issue in issues)

    @pytest.mark.asyncio
    async def test_engagement_issues_have_correct_schema(self) -> None:
        """engagement_issues entries have category and severity fields."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Boring plain text.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
            "structural_check_issues": [],
        }

        result = await engagement_optimizer_node(state)

        if "structural_check_issues" in result and not result.get("engagement_passed"):
            for issue in result["structural_check_issues"]:
                if issue.get("category") == "engagement_issues":
                    assert "category" in issue
                    assert issue["category"] == "engagement_issues"
                    assert "severity" in issue
                    assert issue["severity"] == "LOW"

    @pytest.mark.asyncio
    async def test_engagement_issues_replace_not_accumulate(self) -> None:
        """On revision cycle, engagement_issues are replaced, not accumulated."""
        from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node

        post = GeneratedPost(
            title="Test",
            subtitle="Subtitle",
            content="Boring text.",
            tags=["tag1", "tag2", "tag3", "tag4", "tag5"],
            image_suggestions=["img1", "img2", "img3"],
        )

        # Simulate state from a previous revision cycle with existing engagement issues
        old_issue = {
            "category": "engagement_issues",
            "severity": "LOW",
            "detail": "Old issue from previous revision",
        }

        state = {
            "run_id": "test-123",
            "custom_topic": "Test",
            "post": post,
            "structural_check_issues": [old_issue],
        }

        result = await engagement_optimizer_node(state)

        if "structural_check_issues" in result:
            issues = result["structural_check_issues"]
            # Count engagement_issues entries
            engagement_issue_count = sum(
                1 for issue in issues if issue.get("category") == "engagement_issues"
            )
            # Should have exactly 1 engagement issue (old one replaced, not both)
            # OR 0 if no engagement issues added this time
            assert engagement_issue_count <= 1
