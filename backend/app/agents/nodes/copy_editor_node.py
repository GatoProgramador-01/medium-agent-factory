"""
Copy Editor Node — scores copy-level formatting and consistency.

The Story (El Relato):
This node measures how polished the copy is at the mechanical level: heading case
consistency, exclamation mark frequency, em-dash spacing, and repeated words.
These are formatting signals that don't require LLM judgment — pure regex and rules.

The Flow (El Flujo):
1. Extract post content and strip code blocks so code literals don't skew metrics.
2. Extract all H2/H3 headings and check case consistency (Title Case vs sentence case).
3. Count exclamation marks in prose (after strip_code_blocks) and compute rate per 100 words.
4. Count em-dashes that touch word characters on both sides (improper spacing).
5. Count consecutive repeated words (\\b(\\w+)\\s+\\1\\b).
6. Combine into a 0–1 score: penalties for issues, bonus for consistent headings.
7. Replace (not accumulate) the copy_edit_issues slot in structural_check_issues.
"""

import re
from typing import Any, Dict

from app.agents.nodes._sentence_utils import strip_code_blocks


def _extract_headings(content: str) -> list[str]:
    """Extract all H2/H3 heading text from content."""
    heading_pattern = r"^#{2,3}\s+(.+)$"
    matches = re.findall(heading_pattern, content, re.MULTILINE)
    return matches


def _heading_case_style(text: str) -> str | None:
    """
    Classify a heading's case style.

    Returns:
        "title_case" if most words are capitalized (Title Case)
        "sentence_case" if only first word is capitalized
        "lowercase" if all lowercase
        None if unclear
    """
    words = text.split()
    if not words:
        return None

    capitalized = sum(1 for w in words if w[0].isupper())
    total = len(words)
    ratio = capitalized / total

    if ratio >= 0.8:
        return "title_case"
    elif capitalized == 1:  # Only first word capitalized
        return "sentence_case"
    elif capitalized == 0:
        return "lowercase"

    return None


def _compute_heading_consistency_score(headings: list[str]) -> float:
    """
    Compute heading consistency score (0.0–1.0).

    Logic: if 80%+ of headings match the same style, return 1.0.
    Otherwise, scale by the consistency ratio.
    """
    if not headings:
        return 0.5  # neutral — no data, neither bonus nor penalty

    styles = [_heading_case_style(h) for h in headings]
    valid_styles = [s for s in styles if s is not None]

    if not valid_styles or len(valid_styles) < 2:
        return 0.5  # insufficient data to determine consistency

    # Count occurrences of each style
    style_counts: Dict[str, int] = {}
    for s in valid_styles:
        style_counts[s] = style_counts.get(s, 0) + 1

    # Get most common style
    most_common_style = max(style_counts, key=lambda k: style_counts[k])
    most_common_count = style_counts[most_common_style]
    most_common_ratio = most_common_count / len(valid_styles)

    # Penalize consistently lowercase headings — consistent but wrong
    style_quality = 0.0 if most_common_style == "lowercase" else 1.0

    raw_score = 1.0 if most_common_ratio >= 0.8 else round(most_common_ratio, 3)
    return round(raw_score * style_quality, 3)


def _count_exclamation_marks(prose: str) -> tuple[int, int]:
    """Count exclamation marks and total words in prose."""
    exclamation_count = prose.count("!")
    word_count = len(prose.split())
    return exclamation_count, word_count


def _count_em_dash_spacing_issues(content: str) -> int:
    """
    Count em-dashes that touch word characters on both sides.

    Pattern: \\w—\\w (em-dash with no space on either side).
    This is often a missing space issue.
    """
    pattern = r"\w—\w"
    matches = re.findall(pattern, content)
    return len(matches)


def _count_repeated_word_pairs(content: str) -> int:
    """
    Count consecutive repeated words (the the, is is, etc.).

    Pattern: \\b(\\w+)\\s+\\1\\b (case-insensitive).
    """
    pattern = r"\b(\w+)\s+\1\b"
    matches = re.findall(pattern, content, re.IGNORECASE)
    return len(matches)


async def copy_editor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores copy quality at the formatting level (no LLM calls).

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with copy_edit_score, copy_edit_passed, copy_edit_metrics,
        completed_steps, and optionally updated structural_check_issues.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content or not content.strip():
        return {
            "copy_edit_score": 1.0,
            "copy_edit_passed": True,
            "copy_edit_metrics": {
                "heading_consistency_score": 1.0,
                "exclamation_rate": 0.0,
                "em_dash_spacing_issues": 0,
                "repeated_word_pairs": 0,
            },
            "completed_steps": ["copy_edit_check"],
        }

    # Strip code blocks so code literals don't inflate metrics
    prose_content = strip_code_blocks(content)

    # 1. Extract headings and measure consistency
    headings = _extract_headings(content)
    heading_consistency_score = _compute_heading_consistency_score(headings)

    # 2. Count exclamation marks in prose
    exclamation_count, prose_word_count = _count_exclamation_marks(prose_content)
    exclamation_rate = (
        (exclamation_count / prose_word_count * 100) if prose_word_count > 0 else 0.0
    )

    # 3. Count em-dash spacing issues
    em_dash_issues = _count_em_dash_spacing_issues(prose_content)

    # 4. Count repeated word pairs
    repeated_pairs = _count_repeated_word_pairs(prose_content)

    # 5. Compute score
    # Penalties
    exclamation_norm = min(1.0, exclamation_rate / 3.0)  # Cap at 100% when rate >= 3%
    exclamation_penalty = min(0.30, exclamation_norm * 0.30)
    repetition_penalty = min(0.20, repeated_pairs * 0.05)
    em_dash_penalty = min(0.20, em_dash_issues * 0.04)

    # Bonus for consistent headings (perfect headings add +0.15, none subtract -0.15)
    heading_bonus = heading_consistency_score * 0.30

    copy_edit_score = round(
        max(
            0.0,
            min(
                1.0,
                1.0
                - exclamation_penalty
                - repetition_penalty
                - em_dash_penalty
                + (heading_bonus - 0.15),
            ),
        ),
        3,
    )

    copy_edit_passed = copy_edit_score >= 0.55

    result: Dict[str, Any] = {
        "copy_edit_score": copy_edit_score,
        "copy_edit_passed": copy_edit_passed,
        "copy_edit_metrics": {
            "heading_consistency_score": heading_consistency_score,
            "exclamation_rate": round(exclamation_rate, 2),
            "em_dash_spacing_issues": em_dash_issues,
            "repeated_word_pairs": repeated_pairs,
        },
        "completed_steps": ["copy_edit_check"],
    }

    # 6. Replace-not-accumulate the copy_edit_issues slot
    if not copy_edit_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "copy_edit_issues"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "copy_edit_issues",
                "severity": "LOW",
                "suggestion": (
                    f"Copy quality score {copy_edit_score:.2f} below 0.55. "
                    f"Issues: {em_dash_issues} em-dash spacing issue(s), "
                    f"{repeated_pairs} repeated word pair(s), "
                    f"exclamation rate {exclamation_rate:.1f} per 100 words, "
                    f"heading consistency {heading_consistency_score:.0%}. "
                    f"Fix spacing around em-dashes, remove repeated words, reduce exclamations, "
                    f"standardize heading capitalization."
                ),
            },
        ]

    return result
