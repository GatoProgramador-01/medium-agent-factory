"""
RED-phase TDD tests for SME Reviewer Node.

Current state  (FAILS): sme_reviewer_node.py does not exist yet
Target state   (PASSES): deterministic SME review — penalizes absolute claims,
                          rewards hedge markers
"""
import pytest


def _make_post(content: str):
    from app.agents.content_generator import GeneratedPost

    return GeneratedPost(
        title="Test Article",
        subtitle="",
        content=content,
        tags=[],
        image_suggestions=[],
    )


class TestSmeReviewerNodeBasic:
    @pytest.mark.asyncio
    async def test_returns_empty_on_no_post(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result = await sme_reviewer_node({"run_id": "test-123", "post": None})
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_full_on_empty_content(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result = await sme_reviewer_node(
            {"run_id": "test-123", "post": _make_post("")}
        )
        assert result.get("sme_score") == 1.0
        assert result.get("sme_passed") is True

    @pytest.mark.asyncio
    async def test_returns_required_keys(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result = await sme_reviewer_node(
            {
                "run_id": "test-123",
                "post": _make_post("## Intro\nThis is clean content with no absolute claims."),
            }
        )
        assert "sme_score" in result
        assert "sme_passed" in result
        assert "sme_metrics" in result
        assert "completed_steps" in result
        assert "sme_review" in result["completed_steps"]

    @pytest.mark.asyncio
    async def test_metrics_keys_present(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result = await sme_reviewer_node(
            {
                "run_id": "test-123",
                "post": _make_post("## Section\nSome content with generally accepted practices."),
            }
        )
        metrics = result["sme_metrics"]
        assert "absolute_claim_count" in metrics
        assert "hedge_ratio" in metrics
        assert "absolute_claim_rate" in metrics


class TestSmeReviewerNodeAbsoluteClaims:
    @pytest.mark.asyncio
    async def test_clean_post_scores_well(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result = await sme_reviewer_node(
            {
                "run_id": "test-123",
                "post": _make_post(
                    "## Introduction\n"
                    "This approach typically works well in practice. "
                    "Research suggests that teams often benefit from this pattern. "
                    "In many cases, the results may exceed expectations."
                ),
            }
        )
        assert result["sme_metrics"]["absolute_claim_count"] == 0
        assert result["sme_score"] > 0.70

    @pytest.mark.asyncio
    async def test_single_absolute_claim_lowers_score(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        result_clean = await sme_reviewer_node(
            {"run_id": "t1", "post": _make_post("## Section\nThis approach works well in practice.")}
        )
        result_absolute = await sme_reviewer_node(
            {"run_id": "t2", "post": _make_post("## Section\nThis always works perfectly in practice.")}
        )
        assert result_absolute["sme_score"] < result_clean["sme_score"]
        assert result_absolute["sme_metrics"]["absolute_claim_count"] >= 1

    @pytest.mark.asyncio
    async def test_five_absolute_claims_fails(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Claims\n"
            "This always produces the best result. "
            "It never fails under any condition. "
            "All engineers agree this is the only approach. "
            "Every deployment is guaranteed to succeed. "
            "It is definitely impossible for this to break."
        )
        result = await sme_reviewer_node({"run_id": "test-123", "post": _make_post(content)})
        assert result["sme_metrics"]["absolute_claim_count"] >= 5
        assert result["sme_passed"] is False

    @pytest.mark.asyncio
    async def test_absolute_claims_in_code_blocks_ignored(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Code Example\n"
            "Here is an example:\n"
            "```python\n"
            "# This always runs\n"
            "assert never_fail() == True  # all cases guaranteed\n"
            "```\n"
            "The code above demonstrates the pattern."
        )
        result = await sme_reviewer_node({"run_id": "test-123", "post": _make_post(content)})
        assert result["sme_metrics"]["absolute_claim_count"] == 0
        assert result["sme_passed"] is True

    @pytest.mark.asyncio
    async def test_absolute_claim_rate_per_100_words(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        # ~20 words, 1 absolute claim → rate = 1/20 * 100 = 5.0
        content = "## Section\n" + ("word " * 18) + "always end."
        result = await sme_reviewer_node({"run_id": "test-123", "post": _make_post(content)})
        assert result["sme_metrics"]["absolute_claim_count"] >= 1
        assert result["sme_metrics"]["absolute_claim_rate"] > 0.0


class TestSmeReviewerNodeHedgeMarkers:
    @pytest.mark.asyncio
    async def test_hedge_markers_improve_score(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        no_hedge = await sme_reviewer_node(
            {"run_id": "t1", "post": _make_post("## Section\nThis always fails under load.")}
        )
        with_hedge = await sme_reviewer_node(
            {
                "run_id": "t2",
                "post": _make_post(
                    "## Section\nThis always fails under load. "
                    "Typically, research suggests better patterns may exist."
                ),
            }
        )
        assert with_hedge["sme_score"] > no_hedge["sme_score"]

    @pytest.mark.asyncio
    async def test_hedge_spam_cannot_rescue_five_absolute_claims(self) -> None:
        """Hedge bonus is capped — cannot rescue a post with 5+ absolute claims."""
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Section\n"
            "This always works. It never fails. Every engineer agrees. "
            "All cases are guaranteed. The only solution definitely exists. "
            "Typically typically typically often often often usually usually "
            "generally generally in many cases in many cases research suggests "
            "evidence indicates may might can could sometimes."
        )
        result = await sme_reviewer_node({"run_id": "test-123", "post": _make_post(content)})
        assert result["sme_passed"] is False, (
            "Hedge spam must not rescue 5+ absolute claims"
        )

    @pytest.mark.asyncio
    async def test_hedge_ratio_reflects_proportion(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        # 1 absolute claim + many hedges → hedge_ratio > 1
        content = (
            "## Section\n"
            "This always introduces a concern. "
            "Typically, however, research suggests that may often work. "
            "Generally it could be that teams sometimes find this useful."
        )
        result = await sme_reviewer_node({"run_id": "test-123", "post": _make_post(content)})
        assert result["sme_metrics"]["hedge_ratio"] > 1.0


class TestSmeReviewerNodeIssues:
    @pytest.mark.asyncio
    async def test_failing_post_adds_sme_issues(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Failures\n"
            "This always breaks. It never recovers. Every attempt is guaranteed to fail. "
            "All systems will definitely crash. The only outcome is impossible to avoid."
        )
        state = {
            "run_id": "test-123",
            "post": _make_post(content),
            "structural_check_issues": [],
        }
        result = await sme_reviewer_node(state)
        if not result.get("sme_passed", True):
            assert "structural_check_issues" in result
            issues = result["structural_check_issues"]
            sme_issues = [i for i in issues if i.get("category") == "sme_issues"]
            assert len(sme_issues) > 0
            assert sme_issues[0]["severity"] == "MEDIUM"

    @pytest.mark.asyncio
    async def test_passing_post_does_not_add_issues(self) -> None:
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Best Practices\n"
            "Research suggests that teams typically benefit from this approach. "
            "In many cases, the pattern may improve reliability. "
            "Generally, engineers find that this could reduce overhead."
        )
        state = {
            "run_id": "test-123",
            "post": _make_post(content),
            "structural_check_issues": [],
        }
        result = await sme_reviewer_node(state)
        if result.get("sme_passed", True):
            issues = result.get("structural_check_issues", [])
            sme_issues = [i for i in issues if i.get("category") == "sme_issues"]
            assert len(sme_issues) == 0

    @pytest.mark.asyncio
    async def test_replace_not_accumulate_on_revision_cycle(self) -> None:
        """Second call with same failing post must not double-append sme_issues."""
        from app.agents.nodes.sme_reviewer_node import sme_reviewer_node

        content = (
            "## Claims\n"
            "This always fails. It never works. Every system is guaranteed to crash."
        )
        state1 = {
            "run_id": "test-123",
            "post": _make_post(content),
            "structural_check_issues": [],
        }
        result1 = await sme_reviewer_node(state1)

        if "structural_check_issues" in result1:
            count1 = len([i for i in result1["structural_check_issues"] if i.get("category") == "sme_issues"])

            state2 = {
                "run_id": "test-123",
                "post": _make_post(content),
                "structural_check_issues": result1["structural_check_issues"],
            }
            result2 = await sme_reviewer_node(state2)

            if "structural_check_issues" in result2:
                count2 = len([i for i in result2["structural_check_issues"] if i.get("category") == "sme_issues"])
                assert count2 == count1, "sme_issues must replace, not accumulate"
