"""
Readability Scorer Node â€” scores prose readability via Gunning Fog approximation.

The Story (El Relato):
Dense prose kills technical articles. Long sentences and polysyllabic vocabulary
exhaust readers before the insight lands. This node approximates two classic
readability indices â€” Flesch-Kincaid and Gunning Fog â€” using only vowel-group
counting and sentence splitting. No dictionaries, no LLM calls, O(n) on length.

The Flow (El Flujo):
1. Extract post content and strip code blocks so code literals don't inflate metrics.
2. Split prose into sentences on `.`, `!`, `?` boundaries.
3. Estimate syllables per word by counting vowel groups (consecutive vowels = 1 syllable).
4. Classify complex words (3+ syllable groups) and compute complex_word_ratio.
5. Compute Gunning Fog: 0.4 Ã— (avg_words_per_sentence + 100 Ã— complex_word_ratio).
6. Apply three graduated penalties â€” long sentences, high fog, dense syllables.
7. Replace (not accumulate) the readability_issues slot in structural_check_issues.
"""

import re
from typing import Any, Dict

from app.agents.nodes._sentence_utils import strip_code_blocks

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")
_VOWEL_GROUP_RE = re.compile(r"[aeiouAEIOU]+")
_WORD_RE = re.compile(r"\b[a-zA-Z]+\b")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _count_syllables(word: str) -> int:
    """Estimate syllable count via vowel groups (minimum 1)."""
    groups = _VOWEL_GROUP_RE.findall(word)
    return max(1, len(groups))


def _analyze_prose(prose: str) -> Dict[str, float]:
    """Return readability metrics dict for stripped prose."""
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(prose) if s.strip()]
    sentence_count = len(sentences)

    words = _WORD_RE.findall(prose)
    word_count = len(words)

    if word_count == 0 or sentence_count == 0:
        return {
            "avg_words_per_sentence": 0.0,
            "avg_syllables_per_word": 0.0,
            "gunning_fog": 0.0,
            "complex_word_ratio": 0.0,
        }

    avg_words_per_sentence = word_count / sentence_count

    syllable_counts = [_count_syllables(w) for w in words]
    avg_syllables_per_word = sum(syllable_counts) / word_count

    complex_word_count = sum(1 for s in syllable_counts if s >= 3)
    complex_word_ratio = complex_word_count / word_count

    gunning_fog = 0.4 * (avg_words_per_sentence + 100 * complex_word_ratio)

    return {
        "avg_words_per_sentence": round(avg_words_per_sentence, 3),
        "avg_syllables_per_word": round(avg_syllables_per_word, 3),
        "gunning_fog": round(gunning_fog, 3),
        "complex_word_ratio": round(complex_word_ratio, 4),
    }


def _compute_readability_score(metrics: Dict[str, float]) -> float:
    """Convert metrics into a 0â€“1 readability score."""
    aws = metrics["avg_words_per_sentence"]
    fog = metrics["gunning_fog"]
    asw = metrics["avg_syllables_per_word"]

    # Penalty kicks in above 20 words/sentence, maxes at 0.35
    sentence_penalty = min(0.35, max(0.0, (aws - 20) / 20) * 0.35)
    # Penalty kicks in above Fog=12, maxes at 0.35
    fog_penalty = min(0.35, max(0.0, (fog - 12) / 12) * 0.35)
    # Penalty kicks in above 1.5 syllables/word, maxes at 0.15
    syllable_penalty = min(0.15, max(0.0, (asw - 1.5) / 1.0) * 0.15)

    return round(max(0.0, min(1.0, 1.0 - sentence_penalty - fog_penalty - syllable_penalty)), 3)


# ---------------------------------------------------------------------------
# Main node
# ---------------------------------------------------------------------------


async def readability_scorer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores prose readability via Gunning Fog approximation (no LLM calls).

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with readability_score, readability_passed, readability_metrics,
        completed_steps, and optionally updated structural_check_issues.
    """
    post = state.get("post")
    if post is None:
        return {}

    content = post.content
    if not content or not content.strip():
        return {
            "readability_score": 1.0,
            "readability_passed": True,
            "readability_metrics": {
                "avg_words_per_sentence": 0.0,
                "avg_syllables_per_word": 0.0,
                "gunning_fog": 0.0,
                "complex_word_ratio": 0.0,
            },
            "completed_steps": ["readability_check"],
        }

    prose = strip_code_blocks(content)
    metrics = _analyze_prose(prose)
    readability_score = _compute_readability_score(metrics)
    readability_passed = readability_score >= 0.50

    result: Dict[str, Any] = {
        "readability_score": readability_score,
        "readability_passed": readability_passed,
        "readability_metrics": metrics,
        "completed_steps": list(state.get("completed_steps", [])) + ["readability_check"],
    }

    if not readability_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "readability_issues"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "readability_issues",
                "severity": "LOW",
                "suggestion": (
                    f"Readability score {readability_score:.2f} below 0.50. "
                    f"Avg sentence length {metrics['avg_words_per_sentence']:.1f} words "
                    f"(target â‰¤20). Gunning Fog {metrics['gunning_fog']:.1f} (target â‰¤12). "
                    f"Complex word ratio {metrics['complex_word_ratio']:.1%}. "
                    f"Shorten sentences and replace polysyllabic words with simpler alternatives."
                ),
            },
        ]

    return result
