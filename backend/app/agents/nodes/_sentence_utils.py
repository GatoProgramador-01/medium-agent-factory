"""Shared utilities for sentence analysis across multiple nodes."""

import re
import statistics


def strip_code_blocks(content: str) -> str:
    """Remove fenced and inline code blocks before text analysis.

    Prevents false positives from code literals (ports, versions, variable names).
    """
    # Single-pass: matches all ``` forms regardless of language tag or newline position
    content = re.sub(r"```[\s\S]*?```", "", content)
    # Remove inline code
    content = re.sub(r"`[^`\n]+`", "", content)
    return content


def compute_sentence_variance(content: str) -> float | None:
    """Compute word count standard deviation across sentences.

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
