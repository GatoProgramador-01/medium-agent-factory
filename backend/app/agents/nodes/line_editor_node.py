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

# Passive voice: auxiliary verb + past participle pattern
_PASSIVE_PATTERN = re.compile(
    r"\b(was|were|is|are|has been|have been|had been|will be|being)\s+\w+(ed|en)\b",
    re.IGNORECASE,
)


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

    # 1. Split into sentences
    sentences = [s.strip() for s in re.split(r"[.!?]+\s+", prose_content.strip()) if s.strip()]
    sentence_count = len(sentences)

    word_counts = [len(s.split()) for s in sentences]

    # 2. Average sentence length
    avg_sentence_length = statistics.mean(word_counts) if word_counts else 0.0

    # 3. Long sentence ratio (> 30 words)
    long_sentences = sum(1 for wc in word_counts if wc > 30)
    long_sentence_ratio = long_sentences / sentence_count if sentence_count else 0.0

    # 4. Passive voice ratio
    passive_matches = len(_PASSIVE_PATTERN.findall(prose_content))
    passive_voice_ratio = passive_matches / sentence_count if sentence_count else 0.0

    # 5. Sentence length standard deviation (compute_sentence_variance already returns stdev)
    stdev_result = compute_sentence_variance(prose_content)
    stdev = stdev_result if stdev_result is not None else 0.0

    # 6. Scoring
    passive_penalty = min(0.50, passive_voice_ratio * 2.0)
    long_penalty = min(0.30, long_sentence_ratio * 0.60)
    variety_bonus = min(0.20, (stdev / 15.0) * 0.20)

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
