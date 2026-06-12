"""
Eval pipeline — QualityAnalyzerAgent
=====================================

Three test layers (run cheapest-first in CI):

  Layer 1 — Score direction  (fast, ~$0.002/case with Haiku)
    Verifies the analyzer scores good posts high and bad posts low.
    This is the CI gate: if these fail, block the PR.

  Layer 2 — Batch regression  (~$0.04 total for 20 cases)
    Verifies mean scores for good/bad cohorts don't drift from baseline.
    Catches prompt regressions that affect calibration globally.

  Layer 3 — Feedback quality  (slow, ~$0.005/case, run with -m eval_deep)
    LLM-as-judge: verifies revision_prompt is specific and actionable.
    Run nightly or on prompt file changes, not every PR.

Run all:         pytest evals/ -v
Run CI gate:     pytest evals/ -v -m "not eval_deep"
Run deep only:   pytest evals/ -v -m eval_deep
"""

import statistics
from typing import Any

import pytest

from app.agents.quality_analyzer import run_quality_analysis
from app.models.post import QualityReport

# ── Helpers ────────────────────────────────────────────────────────────────────

async def _analyze(case: dict[str, Any]) -> QualityReport:
    return await run_quality_analysis(
        run_id=f"eval-{case['id']}",
        title=case["title"],
        content=case["content"],
    )


# ── Layer 1: Score direction — one test per case ───────────────────────────────

@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"]) for c in [
        {"id": "good-1", "label": "good", "min_score": 0.70,
         "title": "How I Made $1,847 From Ko-fi in 6 Months (And What Almost Killed It)",
         "content": "March 14th, I had $23 in my bank account and rent was due in three days. I opened Ko-fi on a whim — I'd been ignoring the \"support me\" button my designer friend kept bugging me about.\n\nSix months later, Ko-fi is paying more than my old day job.\n\nHere's what I wish someone had told me: the platform doesn't make you money. Your email list does. Ko-fi is just the checkout page.\n\nI spent my first two months doing everything backwards. I posted on Ko-fi. I waited. I refreshed the dashboard seventeen times a day. My first membership went to my mom — she only did it because she felt bad.\n\nThe shift happened when I stopped thinking about Ko-fi as a platform and started treating it as a product. I moved my newsletter over, mentioned the membership in every third email, and wrote a pinned post about exactly what members were getting.\n\nThirty-seven days later: $400/month recurring. Not life-changing, but rent-covering. I cried a little. Don't judge me."},
        {"id": "good-3", "label": "good", "min_score": 0.70,
         "title": "I Charged $50/Hour for Two Years Before I Realized I Was Cheap",
         "content": "A client asked me to raise my rates last Tuesday. I thought he was being weird. He was being honest.\n\n\"You charge like someone who doesn't believe they're worth more,\" he said. \"Your work is worth more.\" Then he referred me to two other clients at double my rate.\n\nI'd been freelancing for six years. Six years of scope creep, late payments, and that familiar sick feeling when a prospect asks \"what's your rate?\" Six years of dropping my number and then quickly adding \"but that's negotiable\" before they could respond.\n\nThe problem wasn't that I didn't know my value. I'd built an entire freelance practice on the assumption that I'd get caught — caught being not-that-good, not worthy of the number I was about to say.\n\nI raised my rates six weeks ago. Lost two clients. Gained three. Net revenue up 40%. The math was always there."},
    ]
])
@pytest.mark.asyncio
async def test_good_posts_score_high(case: dict[str, Any]) -> None:
    report = await _analyze(case)
    assert report.score >= case["min_score"], (
        f"[{case['id']}] Expected score >= {case['min_score']}, got {report.score:.2f}. "
        f"Top issue: {report.issues[0].suggestion if report.issues else 'none'}"
    )


@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"]) for c in [
        {"id": "bad-1", "label": "bad", "max_score": 0.55,
         "title": "In This Article: 7 Ways to Monetize Your Content",
         "content": "In this article, I will be exploring some of the most effective ways that content creators can monetize their work in today's digital landscape.\n\nFirst and foremost, it is important to understand the various options available. Moreover, each platform has its own unique set of opportunities. Furthermore, it is worth considering your audience before making any decisions.\n\nMethod 1: Subscriptions. Subscriptions are a great way to generate recurring revenue. There are many platforms that support subscription models.\n\nMethod 2: Sponsorships. Sponsorships can provide significant income. It is worth noting that finding the right sponsors takes time.\n\nIn conclusion, there are many ways to monetize content. By implementing these strategies, you can build a sustainable income. I hope this article has been helpful in your content monetization journey."},
        {"id": "bad-2", "label": "bad", "max_score": 0.55,
         "title": "In Today's Fast-Paced World: A Guide to Passive Income",
         "content": "In today's fast-paced world, more and more people are seeking ways to generate passive income. The concept of earning money while you sleep has never been more relevant than it is today.\n\nPassive income is defined as income that requires minimal effort to maintain after an initial investment of time or money. It is important to understand this distinction as we explore the various strategies available.\n\nMoreover, having multiple income streams allows you to weather periods of lower performance. Furthermore, it enables you to take advantage of different monetization opportunities. Additionally, it gives you more financial freedom.\n\nIt is worth noting that passive income does not happen overnight. Moreover, it requires dedication and commitment. In conclusion, passive income is an achievable goal for those willing to put in the initial work."},
        {"id": "bad-4", "label": "bad", "max_score": 0.55,
         "title": "How to Build Multiple Income Streams as a Content Creator",
         "content": "Building multiple income streams is an important strategy for content creators. Diversification provides stability and reduces risk. Moreover, having multiple income streams allows you to weather periods of lower performance. Furthermore, it enables you to take advantage of different opportunities. Additionally, it gives you more financial freedom.\n\nThe first income stream to consider is brand partnerships. It is worth noting that authentic partnerships tend to perform better. The second income stream is digital products. Furthermore, digital products have excellent margins. Moreover, they establish your expertise. The third income stream is community monetization. Additionally, communities generate recurring revenue.\n\nIn conclusion, multiple income streams provide financial security. By following these strategies, you can build a sustainable content business."},
    ]
])
@pytest.mark.asyncio
async def test_bad_posts_score_low(case: dict[str, Any]) -> None:
    report = await _analyze(case)
    assert report.score <= case["max_score"], (
        f"[{case['id']}] Expected score <= {case['max_score']}, got {report.score:.2f}. "
        f"Strengths found: {report.strengths[:2]}"
    )


# ── Layer 2: Batch regression — cohort mean must stay within bounds ────────────

@pytest.mark.asyncio
async def test_good_cohort_mean(good_cases: list[dict]) -> None:
    """
    Mean score for the 'good' cohort must stay >= 0.68.
    Drop of 0.02 from target (0.70) before we alert — catches global calibration drift.
    """
    scores = [
        (await _analyze(c)).score
        for c in good_cases[:4]          # first 4 to keep CI cost low
    ]
    mean = statistics.mean(scores)
    assert mean >= 0.68, (
        f"Good-cohort mean {mean:.2f} below floor 0.68. "
        f"Individual scores: {[round(s, 2) for s in scores]}"
    )


@pytest.mark.asyncio
async def test_bad_cohort_mean(bad_cases: list[dict]) -> None:
    """Mean score for the 'bad' cohort must stay <= 0.57."""
    scores = [
        (await _analyze(c)).score
        for c in bad_cases[:4]
    ]
    mean = statistics.mean(scores)
    assert mean <= 0.57, (
        f"Bad-cohort mean {mean:.2f} above ceiling 0.57 — analyzer is too lenient. "
        f"Individual scores: {[round(s, 2) for s in scores]}"
    )


@pytest.mark.asyncio
async def test_cohort_separation(good_cases: list[dict], bad_cases: list[dict]) -> None:
    """
    Good cohort mean must be at least 0.15 higher than bad cohort mean.
    If this fails, the analyzer can't distinguish quality — useless as a gate.
    """
    good_scores = [(await _analyze(c)).score for c in good_cases[:3]]
    bad_scores  = [(await _analyze(c)).score for c in bad_cases[:3]]

    gap = statistics.mean(good_scores) - statistics.mean(bad_scores)
    assert gap >= 0.15, (
        f"Score separation gap {gap:.2f} is below minimum 0.15. "
        f"Good mean: {statistics.mean(good_scores):.2f}, "
        f"Bad mean: {statistics.mean(bad_scores):.2f}"
    )


# ── Layer 3: Feedback quality — LLM-as-judge (slow, mark as eval_deep) ────────

@pytest.mark.eval_deep
@pytest.mark.asyncio
async def test_revision_prompt_is_specific(bad_cases: list[dict]) -> None:
    """
    The revision_prompt for a bad post should name specific patterns to fix,
    not give generic advice. We check this with keyword heuristics — cheap
    and fast. For LLM-as-judge version, see langsmith_eval.py.
    """
    generic_phrases = [
        "improve your writing",
        "make it better",
        "be more engaging",
        "add more value",
        "write more clearly",
    ]

    case = bad_cases[0]
    report = await _analyze(case)

    prompt_lower = report.revision_prompt.lower()
    generic_hits = [p for p in generic_phrases if p in prompt_lower]

    assert len(generic_hits) == 0, (
        f"revision_prompt contains generic advice: {generic_hits}. "
        f"Full prompt: {report.revision_prompt[:300]}"
    )
    assert len(report.revision_prompt) >= 100, (
        f"revision_prompt too short ({len(report.revision_prompt)} chars) — likely not actionable"
    )


@pytest.mark.eval_deep
@pytest.mark.asyncio
async def test_issues_have_specific_locations(bad_cases: list[dict]) -> None:
    """Each issue should reference a specific location in the post, not 'throughout'."""
    case = bad_cases[1]
    report = await _analyze(case)

    assert len(report.issues) >= 2, "Expected at least 2 issues on a clearly bad post"

    for issue in report.issues[:3]:
        assert len(issue.location) >= 10, (
            f"Issue location '{issue.location}' is too vague — "
            f"should quote a specific excerpt"
        )

