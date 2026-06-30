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

from app.agents.nodes._sentence_utils import strip_code_blocks, compute_sentence_variance


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
        "moreover",
        "furthermore",
        "additionally",
        "game-changer",
        "cutting-edge",
        "transformative",
        "revolutionize",
        "seamless",
        "synergy",
        "cornerstone",
        "groundbreaking",
        "showcasing",
        "pivotal",
    ]

    ai_slop_issues: list[dict[str, Any]] = []

    # 1. Strip code fences from content before scanning
    stripped_content = strip_code_blocks(content)

    # 2. Check for forbidden words
    forbidden_word_issues = _check_forbidden_words(stripped_content, forbidden_words)
    ai_slop_issues.extend(forbidden_word_issues)

    # 3. Count em-dashes (use stripped content)
    em_dash_count = stripped_content.count("—")
    if em_dash_count > 6:
        ai_slop_issues.append({"type": "EM_DASH_EXCESS", "count": em_dash_count})

    # 4. Compute sentence length variance (use stripped content)
    variance = compute_sentence_variance(stripped_content)
    if variance is not None and variance < 5.0:
        ai_slop_issues.append({"type": "UNIFORM_RHYTHM", "std_dev": round(variance, 2)})

    # 5. Determine pass/fail based on total forbidden hits <= 3
    total_forbidden_hits = sum(i.get("count", 0) for i in forbidden_word_issues)
    ai_slop_passed = (
        total_forbidden_hits <= 3
        and em_dash_count <= 6
        and (variance is None or variance >= 5.0)
    )

    # 6. Compute score (0-1, where 1 is clean)
    penalties = 0.0
    if forbidden_word_issues:
        penalties += min(0.4, len(forbidden_word_issues) * 0.05)
    if em_dash_count > 6:
        penalties += min(0.3, (em_dash_count - 6) * 0.02)
    if variance is not None and variance < 5.0:
        penalties += min(0.3, (5.0 - variance) * 0.01)

    ai_slop_score = max(0.0, min(1.0, 1.0 - penalties))

    # 7. Update structural issues if not passed (avoid state mutation)
    result = {
        "ai_slop_issues": ai_slop_issues,
        "ai_slop_score": round(ai_slop_score, 3),
        "ai_slop_passed": ai_slop_passed,
        "completed_steps": ["ai_slop_check"],
    }

    if not ai_slop_passed:
        existing = [i for i in state.get("structural_check_issues", []) if i.get("category") != "ai_slop"]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "ai_slop",
                "severity": "HIGH",
                "suggestion": "Remove forbidden buzzwords, reduce em-dashes, vary sentence length.",
            },
        ]

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
