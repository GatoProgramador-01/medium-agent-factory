"""
Line Editor Node — scores prose quality at the sentence level.

The Story (El Relato):
This node measures how readable and varied the prose is by examining three
sentence-level signals: average sentence length (clarity), the ratio of
sentences exceeding 30 words (cognitive load), and the rate of passive-voice
constructions (engagement). A variety bonus rewards authors who mix short
punchy sentences with longer ones — the hallmark of confident, readable writing.

The Flow (El Flujo):
1. Extract post content and strip code blocks so code literals don't skew metrics.
2. Split prose on sentence boundaries and compute average sentence length.
3. Compute the fraction of sentences longer than 30 words (long_sentence_ratio).
4. Detect passive-voice constructions via regex and compute ratio.
5. Compute sentence length standard deviation (variety) from compute_sentence_variance.
6. Combine into a 0–1 score: 1.0 - passive_penalty - long_penalty + variety_bonus.
7. Replace (not accumulate) the poor_prose_quality issue slot in structural_check_issues.
"""

import re
import statistics
from typing import Any, Dict

from app.agents.nodes._sentence_utils import compute_sentence_variance, strip_code_blocks

# Passive voice — Part 1: regular suffix passives (auxiliary + word ending -ed/-en)
_PASSIVE_SUFFIX_RE = re.compile(
    r"\b(was|were|is|are|has been|have been|had been|will be|being)\s+\w+(ed|en)\b",
    re.IGNORECASE,
)

# Passive voice — Part 2: irregular past participles that suffix check misses
_IRREGULAR_VBN = {
    "built", "written", "known", "done", "made", "found", "sent", "sold",
    "told", "shown", "seen", "given", "brought", "caught", "kept", "left",
    "put", "set", "held", "led", "read", "run", "come", "become", "begun",
    "broken", "chosen", "driven", "fallen", "grown", "risen", "spoken",
    "stolen", "taken", "thrown", "worn", "won",
}

_PASSIVE_IRREGULAR_RE = re.compile(
    r"\b(was|were|is|are|has been|have been|had been|will be|being)\s+("
    + "|".join(sorted(_IRREGULAR_VBN))
    + r")\b",
    re.IGNORECASE,
)


def _is_passive_sentence(sentence: str) -> bool:
    """Return True if sentence contains a passive-voice construction."""
    return bool(_PASSIVE_SUFFIX_RE.search(sentence) or _PASSIVE_IRREGULAR_RE.search(sentence))


# Abbreviation protection — prevents false sentence splits on "Dr. Smith", "U.S. companies", etc.
_ABBREV_RE = re.compile(
    r"\b(Dr|Mr|Mrs|Ms|Prof|Sr|Jr|vs|Fig|etc|approx|U\.S|U\.K|e\.g|i\.e)\."
)


def _protect_abbreviations(text: str) -> str:
    """Replace abbreviation dots with a placeholder to prevent false sentence splits."""
    return _ABBREV_RE.sub(lambda m: m.group(0).replace(".", "ABBREVDOT"), text)


def _restore_abbreviations(text: str) -> str:
    return text.replace("ABBREVDOT", ".")


async def line_editor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores prose quality at the sentence level (no LLM calls).

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with line_edit_score, line_edit_passed, line_edit_metrics,
        completed_steps, and optionally updated structural_check_issues.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content:
        return {
            "line_edit_score": 0.0,
            "line_edit_passed": False,
            "line_edit_metrics": {
                "avg_sentence_length": 0.0,
                "long_sentence_ratio": 0.0,
                "passive_voice_ratio": 0.0,
                "sentence_length_stdev": 0.0,
            },
            "completed_steps": ["line_edit_check"],
        }

    # Strip code blocks so code literals don't inflate sentence metrics
    prose_content = strip_code_blocks(content)

    prose_words = len(prose_content.split())
    if prose_words == 0:
        return {
            "line_edit_score": 0.0,
            "line_edit_passed": False,
            "line_edit_metrics": {
                "avg_sentence_length": 0.0,
                "long_sentence_ratio": 0.0,
                "passive_voice_ratio": 0.0,
                "sentence_length_stdev": 0.0,
            },
            "completed_steps": ["line_edit_check"],
        }

    # 1. Split into sentences (protect abbreviations first to avoid false splits)
    protected = _protect_abbreviations(prose_content.strip())
    raw_sentences = re.split(r"[.!?]+\s+", protected)
    sentences = [_restore_abbreviations(s.strip()) for s in raw_sentences if s.strip()]
    sentence_count = len(sentences)

    word_counts = [len(s.split()) for s in sentences]

    # 2. Average sentence length
    avg_sentence_length = statistics.mean(word_counts) if word_counts else 0.0

    # 3. Long sentence ratio (> 30 words)
    long_sentences = sum(1 for wc in word_counts if wc > 30)
    long_sentence_ratio = long_sentences / sentence_count if sentence_count else 0.0

    # 4. Passive voice ratio (per-sentence check covers both suffix and irregular forms)
    passive_count = sum(1 for s in sentences if _is_passive_sentence(s))
    passive_voice_ratio = passive_count / sentence_count if sentence_count else 0.0

    # 5. Sentence length standard deviation (compute_sentence_variance already returns stdev)
    stdev_result = compute_sentence_variance(prose_content)
    stdev = stdev_result if stdev_result is not None else 0.0

    # 6. Scoring
    passive_penalty = min(0.50, passive_voice_ratio * 2.0)
    long_penalty = min(0.30, long_sentence_ratio * 0.60)
    # Suppress variety bonus when post is already dominated by long sentences (≥50%)
    variety_bonus = 0.0 if long_sentence_ratio >= 0.5 else min(0.20, (stdev / 15.0) * 0.20)

    line_edit_score = round(
        max(0.0, min(1.0, 1.0 - passive_penalty - long_penalty + variety_bonus)),
        3,
    )

    line_edit_passed = line_edit_score >= 0.50

    result: Dict[str, Any] = {
        "line_edit_score": line_edit_score,
        "line_edit_passed": line_edit_passed,
        "line_edit_metrics": {
            "avg_sentence_length": round(avg_sentence_length, 2),
            "long_sentence_ratio": round(long_sentence_ratio, 3),
            "passive_voice_ratio": round(passive_voice_ratio, 3),
            "sentence_length_stdev": round(stdev, 2),
            "sentence_count": sentence_count,
        },
        "completed_steps": ["line_edit_check"],
    }

    # 7. Replace-not-accumulate the poor_prose_quality slot
    if not line_edit_passed:
        existing = [
            i
            for i in state.get("structural_check_issues", [])
            if i.get("category") != "poor_prose_quality"
        ]
        result["structural_check_issues"] = [
            *existing,
            {
                "category": "poor_prose_quality",
                "severity": "MEDIUM",
                "suggestion": (
                    f"Prose quality score {line_edit_score:.2f} below 0.50. "
                    f"Reduce passive voice ({passive_voice_ratio:.0%} detected), "
                    f"shorten sentences > 30 words ({long_sentence_ratio:.0%} of sentences), "
                    f"vary sentence lengths."
                ),
            },
        ]

    return result
