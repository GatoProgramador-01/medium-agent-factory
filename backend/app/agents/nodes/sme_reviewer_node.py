"""
SME Reviewer Node — deterministic Subject Matter Expert quality check.

The Story (El Relato):
Technical content lives or dies on epistemic precision. Absolute claims ("always",
"never", "guaranteed") erode trust when readers — who are practitioners — know that
edge cases exist. Hedge markers ("typically", "research suggests", "may") signal
intellectual honesty. This node penalizes overconfidence and rewards calibration,
purely through regex counting — no LLM calls, O(n) on content length.

The Flow (El Flujo):
1. Extract post content and strip code blocks so code literals don't skew metrics.
2. Count absolute claim phrases in prose (whole-word, case-insensitive).
3. Count hedge markers in prose (multiword phrases matched first to avoid double-count).
4. Compute absolute_claim_rate (per 100 prose words) and hedge_ratio (hedges per claim+1).
5. Score: penalty for absolute claims, bonus for hedge density — capped so hedge
   spam cannot rescue a post with 5+ absolute claims.
6. Replace (not accumulate) the sme_issues slot in structural_check_issues on failure.
"""

import re
from typing import Any, Dict

from app.agents.nodes._sentence_utils import strip_code_blocks

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Multiword phrases must appear BEFORE their component words to avoid double-count.
_ABSOLUTE_CLAIM_PATTERN = re.compile(
    r"\b(always|never|all|every|the\s+only|guaranteed|proven\s+fact|definitely|certainly|impossible)\b",
    re.IGNORECASE,
)

# Hedge markers — multiword phrases anchored before single-word alternatives.
# Using a single alternation so the regex engine tries longer phrases first in
# left-to-right order within the same pass.
_HEDGE_PATTERN = re.compile(
    r"\b("
    r"in\s+many\s+cases"
    r"|research\s+suggests"
    r"|evidence\s+indicates"
    r"|tends\s+to"
    r"|typically"
    r"|often"
    r"|generally"
    r"|usually"
    r"|sometimes"
    r"|may"
    r"|might"
    r"|can"
    r"|could"
    r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _count_absolute_claims(prose: str) -> int:
    """Count absolute claim phrases in prose (whole-word, case-insensitive)."""
    return len(_ABSOLUTE_CLAIM_PATTERN.findall(prose))


def _count_hedge_markers(prose: str) -> int:
    """Count hedge markers in prose.

    Multiword phrases are matched before their individual tokens because they appear
    earlier in the alternation, so regex picks the longest match first in each
    non-overlapping scan.
    """
    return len(_HEDGE_PATTERN.findall(prose))


def _compute_sme_score(absolute_claim_count: int, hedge_ratio: float) -> float:
    """Compute the final SME score (0.0–1.0, rounded to 3 decimal places).

    Penalty: up to 0.40 for absolute claims (5 claims → max penalty).
    Bonus: up to 0.15 for hedge density, shifted by −0.075 baseline so a post
    with zero hedges pays a small cost rather than being neutral.
    Hard gate: when absolute_claim_count ≥ 5, hedge bonus is suppressed entirely —
    5+ unsourced absolutes are too severe for hedging language to rehabilitate.
    Without the gate, max penalty (0.40) + max net bonus (0.075) still yields 0.675
    which passes the 0.55 threshold — the gate is the only way to guarantee failure.
    """
    absolute_claim_penalty = min(0.40, absolute_claim_count * 0.08)
    # Suppress hedge bonus when claim count is severe enough to fail regardless
    if absolute_claim_count >= 5:
        effective_hedge_bonus = 0.0
    else:
        effective_hedge_bonus = min(0.15, hedge_ratio * 0.15)
    raw = 1.0 - absolute_claim_penalty + (effective_hedge_bonus - 0.075)
    return round(max(0.0, min(1.0, raw)), 3)


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def sme_reviewer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores SME quality by penalizing absolute claims and rewarding hedged language.

    Deterministic — no LLM calls. Runs in O(n) on content length.

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with sme_score, sme_passed, sme_metrics, completed_steps, and
        optionally updated structural_check_issues when the post fails.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content or not content.strip():
        return {
            "sme_score": 1.0,
            "sme_passed": True,
            "sme_metrics": {
                "absolute_claim_count": 0,
                "hedge_ratio": 0.0,
                "absolute_claim_rate": 0.0,
            },
            "completed_steps": ["sme_review"],
        }

    # Strip code blocks so code literals don't inflate metrics
    prose = strip_code_blocks(content)

    # --- counts ---
    prose_word_count = len(prose.split())
    absolute_claim_count = _count_absolute_claims(prose)
    hedge_count = _count_hedge_markers(prose)

    # --- derived metrics ---
    absolute_claim_rate = (
        (absolute_claim_count / prose_word_count * 100) if prose_word_count > 0 else 0.0
    )
    # Denominator always ≥ 1 to avoid division-by-zero and to bias hedge_ratio down
    # when there are no absolute claims (avoids falsely inflating the bonus).
    hedge_ratio = hedge_count / (absolute_claim_count + 1)

    # --- score ---
    sme_score = _compute_sme_score(absolute_claim_count, hedge_ratio)
    sme_passed = sme_score >= 0.55

    result: Dict[str, Any] = {
        "sme_score": sme_score,
        "sme_passed": sme_passed,
        "sme_metrics": {
            "absolute_claim_count": absolute_claim_count,
            "hedge_ratio": round(hedge_ratio, 4),
            "absolute_claim_rate": round(absolute_claim_rate, 4),
        },
        "completed_steps": ["sme_review"],
    }

    # Replace-not-accumulate the sme_issues slot so revision cycles don't stack
    if not sme_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "sme_issues"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "sme_issues",
                "severity": "MEDIUM",
                "suggestion": (
                    f"SME score {sme_score:.2f} below 0.55. "
                    f"Found {absolute_claim_count} absolute claim(s) "
                    f"(rate {absolute_claim_rate:.1f} per 100 words) and "
                    f"{hedge_count} hedge marker(s) (hedge ratio {hedge_ratio:.2f}). "
                    f"Replace absolute language ('always', 'never', 'guaranteed', etc.) "
                    f"with hedged equivalents ('typically', 'research suggests', 'may', etc.)."
                ),
            },
        ]

    return result
