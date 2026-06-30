"""
AI Slop Detector — identifies forbidden words, em-dash excess, and uniform rhythm.

The Story (El Relato):
This node acts as a linguistic guardian, detecting patterns of lazy AI writing.
It identifies three categories of problems: overused buzzwords that signal
poor craftsmanship, excessive em-dashes that break reading flow, and uniform
sentence rhythm that betrays a machine's monotone voice.

The Flow (El Flujo):
1. Extract post content from state.
2. Scan for forbidden buzzwords and count occurrences.
3. Count em-dashes (—) in content.
4. Split content into sentences and compute word-count variance.
5. Apply scoring rules to determine quality and pass/fail status.
6. Return structured issues and updated state.
"""

import re
import statistics
from typing import Any, Dict


async def ai_slop_detector_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Detects AI slop (forbidden words, em-dashes, uniform rhythm).

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with ai_slop_issues, ai_slop_score, ai_slop_passed, and updated
        structural_check_issues if issues found.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content:
        return {}

    forbidden_words = [
        "delve",
        "tapestry",
        "leverage",
        "Moreover",
        "Furthermore",
        "Additionally",
        "game-changer",
        "cutting-edge",
        "transformative",
        "revolutionize",
        "seamless",
        "synergy",
        "cornerstone",
        "groundbreaking",
        "showcasing",
        "underscores",
        "pivotal",
    ]

    ai_slop_issues: list[dict[str, Any]] = []

    # 1. Check for forbidden words
    forbidden_word_issues = _check_forbidden_words(content, forbidden_words)
    ai_slop_issues.extend(forbidden_word_issues)

    # 2. Count em-dashes
    em_dash_count = content.count("—")
    if em_dash_count > 6:
        ai_slop_issues.append({"type": "EM_DASH_EXCESS", "count": em_dash_count})

    # 3. Compute sentence length variance
    variance = _compute_sentence_variance(content)
    if variance is not None and variance < 5.0:
        ai_slop_issues.append({"type": "UNIFORM_RHYTHM", "std_dev": round(variance, 2)})

    # 4. Determine pass/fail
    ai_slop_passed = (
        len([i for i in forbidden_word_issues if i.get("count", 0) > 2]) == 0
        and em_dash_count <= 6
        and (variance is None or variance >= 5.0)
    )

    # 5. Compute score (0-1, where 1 is clean)
    penalties = 0.0
    if forbidden_word_issues:
        penalties += min(0.4, len(forbidden_word_issues) * 0.05)
    if em_dash_count > 6:
        penalties += min(0.3, (em_dash_count - 6) * 0.02)
    if variance is not None and variance < 5.0:
        penalties += min(0.3, (5.0 - variance) * 0.01)

    ai_slop_score = max(0.0, min(1.0, 1.0 - penalties))

    # 6. Update structural issues if not passed
    result = {
        "ai_slop_issues": ai_slop_issues,
        "ai_slop_score": round(ai_slop_score, 3),
        "ai_slop_passed": ai_slop_passed,
        "completed_steps": ["ai_slop_check"],
    }

    if not ai_slop_passed:
        structural_issues = state.get("structural_check_issues", [])
        structural_issues.append(
            {
                "category": "ai_slop",
                "severity": "HIGH",
                "suggestion": "Remove forbidden buzzwords, reduce em-dashes, vary sentence length.",
            }
        )
        result["structural_check_issues"] = structural_issues

    return result


def _check_forbidden_words(
    content: str, forbidden_words: list[str]
) -> list[dict[str, Any]]:
    """Scan content for forbidden words and count occurrences.

    Args:
        content: The post content to scan.
        forbidden_words: List of words to check for.

    Returns:
        List of dicts with type, word, and count for each forbidden word found.
    """
    issues: list[dict[str, Any]] = []
    for word in forbidden_words:
        if "-" in word:
            # Hyphenated words: substring match so plurals ("game-changers") are caught
            pattern = re.escape(word)
        else:
            pattern = r"(?:^|\b|[-\s])" + re.escape(word) + r"(?:\b|[-\s]|$)"
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            issues.append({"type": "FORBIDDEN_WORD", "word": word, "count": len(matches)})
    return issues


def _compute_sentence_variance(content: str) -> float | None:
    """Compute word count variance across sentences.

    Args:
        content: The post content.

    Returns:
        Standard deviation of sentence word counts, or None if < 2 sentences.
    """
    # Split on sentence boundaries: ". ", "! ", "? "
    sentences = re.split(r"[.!?]\s+", content.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) < 2:
        return None

    word_counts = [len(s.split()) for s in sentences]
    if len(set(word_counts)) == 1:
        # All same length
        return 0.0

    try:
        variance = statistics.stdev(word_counts)
        return variance
    except statistics.StatisticsError:
        return None
