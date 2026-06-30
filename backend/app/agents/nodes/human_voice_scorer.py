"""
Human Voice Scorer — measures personal voice through sentence rhythm, pronouns, and contractions.

The Story (El Relato):
This node scores how "human" a post sounds by measuring four linguistic signals:
the variance in sentence length (rhythm), density of personal pronouns (intimacy),
rate of contractions (conversational tone), and penalty for excessive em-dashes
(formality marker). These signals combine into a single 0–1 score reflecting
reader connection and authenticity.

The Flow (El Flujo):
1. Extract post content and compute sentence length variance.
2. Count personal pronouns and normalize to per-100-words density.
3. Count contractions and normalize to per-100-words rate.
4. Count em-dashes and compute per-100-words penalty.
5. Combine metrics with weights: variance*0.4 + pronoun*0.3 + contraction*0.2 + (1-em_dash)*0.1.
6. Return score, metrics, pass/fail, and completed steps.
"""

import re
import statistics
from typing import Any, Dict


async def human_voice_scorer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores human voice characteristics in post content.

    Args:
        state: Pipeline state with optional "post" key containing GeneratedPost.

    Returns:
        Dict with human_voice_score, human_voice_metrics, human_voice_passed,
        and completed_steps.
    """
    post = state.get("post")
    if not post:
        return {}

    content = post.content
    if not content:
        return {}

    # Count total words
    words = content.split()
    total_words = len(words)
    if total_words == 0:
        return {}

    # 1. Sentence length variance
    variance = _compute_sentence_variance(content)
    variance_norm = min(1.0, (variance / 20.0) if variance else 0.0)

    # 2. Personal pronoun density (per 100 words)
    pronoun_count = _count_personal_pronouns(content)
    pronoun_density = (pronoun_count / total_words) * 100
    pronoun_norm = min(1.0, pronoun_density / 10.0)

    # 3. Contraction rate (per 100 words)
    contraction_count = _count_contractions(content)
    contraction_rate = (contraction_count / total_words) * 100
    contraction_norm = min(1.0, contraction_rate / 5.0)

    # 4. Em-dash penalty
    em_dash_count = content.count("—")
    em_dash_per_100 = (em_dash_count / total_words) * 100
    em_dash_penalty_norm = min(1.0, em_dash_per_100 / 2.0)

    # 5. Compute weighted score
    human_voice_score = round(
        variance_norm * 0.4
        + pronoun_norm * 0.3
        + contraction_norm * 0.2
        + (1.0 - em_dash_penalty_norm) * 0.1,
        3,
    )

    # 6. Determine pass/fail
    human_voice_passed = human_voice_score >= 0.6

    return {
        "human_voice_score": human_voice_score,
        "human_voice_metrics": {
            "sentence_length_variance": round(variance if variance else 0.0, 2),
            "personal_pronoun_density": round(pronoun_density, 2),
            "contraction_rate": round(contraction_rate, 2),
            "em_dash_per_100_words": round(em_dash_per_100, 2),
        },
        "human_voice_passed": human_voice_passed,
        "completed_steps": ["human_voice_scoring"],
    }


def _compute_sentence_variance(content: str) -> float | None:
    """Compute word count variance across sentences.

    Args:
        content: The post content.

    Returns:
        Standard deviation of sentence word counts, or None if < 2 sentences.
    """
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


def _count_personal_pronouns(content: str) -> int:
    """Count occurrences of personal pronouns.

    Args:
        content: The post content.

    Returns:
        Count of personal pronouns.
    """
    # Pattern: whole-word matches for I, my, me, we, our, I've, I'm, I'd, I'll
    pattern = r"\b(I|my|me|we|our|I've|I'm|I'd|I'll)\b"
    matches = re.findall(pattern, content, re.IGNORECASE)
    return len(matches)


def _count_contractions(content: str) -> int:
    """Count occurrences of contractions (e.g., "it's", "I've", "doesn't").

    Args:
        content: The post content.

    Returns:
        Count of contractions.
    """
    # Pattern: word character(s) followed by apostrophe and one or more letters
    pattern = r"\b\w+'[a-z]+\b"
    matches = re.findall(pattern, content, re.IGNORECASE)
    return len(matches)
