"""
Engagement Optimizer Node — scores reader engagement signals deterministically.

The Story (El Relato):
Medium articles live or die in the first paragraph. A strong hook — a question,
a surprising stat, bold text — signals to the reader that something worth reading
follows. Second-person voice ("you", "your") creates intimacy and relevance.
A clear call-to-action at the end converts passive readers into followers. This
node measures all three engagement levers with zero LLM calls.

The Flow (El Flujo):
1. Extract post content and strip code blocks so code literals don't skew metrics.
2. Isolate the first paragraph to score hook signals (question / stat / bold).
3. Count "you"/"your" occurrences across all prose, compute rate per 100 words.
4. Check last 15% of prose for any recognized CTA keyword/phrase.
5. Combine into 0–1 score: penalty for missing hook, bonus for second-person and CTA.
6. Replace (not accumulate) the engagement_issues slot in structural_check_issues.
"""

import re
from typing import Any, Dict

from app.agents.nodes._sentence_utils import strip_code_blocks

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CTA_PHRASES = [
    "let me know",
    "try this",
    "get started",
    "learn more",
    "sign up",
    "reach out",
    "subscribe",
    "follow",
    "share",
    "comment",
    "click",
    "download",
]

_CTA_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in _CTA_PHRASES) + r")\b",
    re.IGNORECASE,
)

_SECOND_PERSON_RE = re.compile(r"\b(you|your)\b", re.IGNORECASE)
_QUESTION_RE = re.compile(r"\?")
_STAT_RE = re.compile(r"\d+")
_BOLD_RE = re.compile(r"\*\*\w")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_first_paragraph(prose: str) -> str:
    """Return the first non-empty paragraph from prose."""
    paragraphs = re.split(r"\r?\n[ \t]*\r?\n", prose.strip())
    for para in paragraphs:
        stripped = para.strip()
        if stripped:
            return stripped
    return ""


def _score_hook(first_paragraph: str) -> float:
    """Score hook signals in the first paragraph (0.0–1.0)."""
    score = 0.0
    if _QUESTION_RE.search(first_paragraph):
        score += 0.33
    if _STAT_RE.search(first_paragraph):
        score += 0.33
    if _BOLD_RE.search(first_paragraph):
        score += 0.34
    return round(min(1.0, score), 3)


def _second_person_ratio(prose: str) -> float:
    """Count 'you'/'your' per 100 prose words."""
    word_count = len(prose.split())
    if word_count == 0:
        return 0.0
    matches = len(_SECOND_PERSON_RE.findall(prose))
    return round(matches / word_count * 100, 3)


def _has_cta(prose: str) -> bool:
    """Return True if a CTA phrase appears in the last 15% of prose."""
    if not prose:
        return False
    cutoff = max(0, int(len(prose) * 0.85))
    tail = prose[cutoff:]
    return bool(_CTA_PATTERN.search(tail))


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def engagement_optimizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores reader engagement: hook strength, second-person voice, CTA presence.

    Deterministic — no LLM calls. Runs in O(n) on content length.

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with engagement_score, engagement_passed, engagement_metrics,
        completed_steps, and optionally updated structural_check_issues.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content or not content.strip():
        return {
            "engagement_score": 1.0,
            "engagement_passed": True,
            "engagement_metrics": {
                "hook_score": 1.0,
                "second_person_ratio": 0.0,
                "has_cta": False,
            },
            "completed_steps": ["engagement_check"],
        }

    prose = strip_code_blocks(content)

    # 1. Hook — first paragraph only
    first_para = _extract_first_paragraph(prose)
    hook_score = _score_hook(first_para)

    # 2. Second-person ratio across all prose
    sp_ratio = _second_person_ratio(prose)

    # 3. CTA in last 15%
    cta_present = _has_cta(prose)

    # 4. Score
    # No hook → -0.30 penalty; partial hook → proportional reduction
    hook_penalty = max(0.0, 0.30 - hook_score * 0.30)
    # Up to +0.20 for second-person density (5 per 100 words → max)
    person_bonus = min(0.20, sp_ratio / 5.0 * 0.20)
    cta_bonus = 0.15 if cta_present else 0.0
    # Baseline -0.15 so neutral content (no hook, no CTA, no second-person) fails
    engagement_score = round(
        max(0.0, min(1.0, 1.0 - hook_penalty + person_bonus + cta_bonus - 0.15)),
        3,
    )

    engagement_passed = engagement_score >= 0.50

    result: Dict[str, Any] = {
        "engagement_score": engagement_score,
        "engagement_passed": engagement_passed,
        "engagement_metrics": {
            "hook_score": hook_score,
            "second_person_ratio": sp_ratio,
            "has_cta": cta_present,
        },
        "completed_steps": ["engagement_check"],
    }

    if not engagement_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "engagement_issues"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "engagement_issues",
                "severity": "LOW",
                "suggestion": (
                    f"Engagement score {engagement_score:.2f} below 0.50. "
                    f"Hook score {hook_score:.2f} (add a question, stat, or bold text "
                    f"in the first paragraph). "
                    f"Second-person ratio {sp_ratio:.1f} per 100 words "
                    f"(use 'you'/'your' to speak directly to readers). "
                    f"CTA present: {cta_present} (add a call-to-action in the closing section)."
                ),
            },
        ]

    return result
