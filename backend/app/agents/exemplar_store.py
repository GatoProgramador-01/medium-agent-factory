"""
Exemplar store — few-shot examples for content generation.

High-scoring posts (>= EXEMPLAR_THRESHOLD) are compressed and stored.
When generating a new post, the closest exemplar by topic keyword overlap
is injected into the generation prompt as a structural reference.

What gets injected (compressed blueprint, NOT the full post):
  - Hook (sentence 1 — the element with highest leverage on read ratio)
  - Intro section (first 150 words — the 30-second survival zone)
  - First code block if present (for technical posts)
  - Achieved metrics (score, read ratio, word count)

Why compressed: full-post injection is too many tokens and risks the LLM
copying structure verbatim. Blueprint injection sets the quality bar without
prescribing the exact form.
"""

import re
from datetime import UTC, datetime
from typing import Any

from app.database import get_db

EXEMPLAR_THRESHOLD = 0.95

_STOP_WORDS = {
    "with", "that", "this", "from", "your", "have", "will", "using",
    "into", "when", "what", "about", "more", "each", "they", "their",
    "some", "been", "also", "just", "than", "then", "over", "only",
    "make", "made", "most", "much", "such", "very", "well",
}


def _extract_intro(content: str, max_words: int = 150) -> tuple[str, int]:
    """Extract intro section before first H2 or frontmatter separator.

    Args:
        content: Post markdown content.
        max_words: Maximum words to include (default 150).

    Returns:
        Tuple of (intro_text, actual_word_count).
    """
    split = re.split(r"\n##\s|\n---\n", content, maxsplit=1)
    raw = split[0].strip()
    words = raw.split()
    capped = " ".join(words[:max_words])
    return capped, min(len(words), max_words)


def _extract_hook(intro: str) -> str:
    """Extract first sentence from intro text.

    Args:
        intro: Intro section text.

    Returns:
        First sentence (up to first period/exclamation/question mark).
    """
    parts = re.split(r"(?<=[.!?])\s+", intro.replace("\n", " "), maxsplit=1)
    return parts[0].strip()


def _extract_first_code_block(content: str, max_chars: int = 600) -> str | None:
    """Extract first code block from content.

    Args:
        content: Post markdown content.
        max_chars: Maximum characters to include (default 600).

    Returns:
        Code block with triple backticks, or None if not found.
    """
    match = re.search(r"```[\s\S]*?```", content)
    return match.group(0)[:max_chars] if match else None


def _topic_keywords(title: str) -> list[str]:
    """Extract keywords from title (words > 3 chars, excluding stop words).

    Args:
        title: Post title.

    Returns:
        List of lowercase keywords.
    """
    return list({
        w.lower().strip(".,!?:;\"'")
        for w in title.split()
        if len(w) > 3 and w.lower() not in _STOP_WORDS
    })


async def save_exemplar(
    run_id: str,
    title: str,
    content: str,
    tags: list[str],
    score: float,
    read_ratio: float,
    hook_score: float,
) -> None:
    """Compress and upsert a high-scoring post as few-shot exemplar.

    Extracts hook, intro, and code block for efficient prompt injection.
    Called when post score >= EXEMPLAR_THRESHOLD (0.95).

    Args:
        run_id: Unique post identifier.
        title: Post title.
        content: Full markdown content.
        tags: Medium tags list.
        score: Quality score (0.0-1.0).
        read_ratio: Predicted read ratio (0.0-1.0).
        hook_score: Hook effectiveness score.
    """
    intro, intro_word_count = _extract_intro(content)
    hook = _extract_hook(intro)
    code_block = _extract_first_code_block(content)

    db = get_db()
    await db.exemplars.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "run_id": run_id,
                "title": title,
                "tags": tags,
                "topic_keywords": _topic_keywords(title),
                "score": score,
                "read_ratio": read_ratio,
                "hook_score": hook_score,
                "hook": hook,
                "intro": intro,
                "intro_word_count": intro_word_count,
                "code_block": code_block,
                "word_count": len(content.split()),
                "updated_at": datetime.now(UTC),
            },
            "$setOnInsert": {"created_at": datetime.now(UTC)},
        },
        upsert=True,
    )


async def promote_post_to_exemplar(run_id: str) -> bool:
    """Retroactively promote an existing post to exemplar status.

    Retrieves post from MongoDB and saves as exemplar if found.

    Args:
        run_id: Unique post identifier.

    Returns:
        True if post found and promoted, False if not found.
    """
    db = get_db()
    post = await db.posts.find_one({"run_id": run_id}, {"_id": 0})
    if not post:
        return False

    qr = post.get("quality_report") or {}
    await save_exemplar(
        run_id=run_id,
        title=post.get("title", ""),
        content=post.get("content", ""),
        tags=post.get("tags", []),
        score=float(qr.get("score", 0)),
        read_ratio=float(qr.get("read_ratio_prediction", 0)),
        hook_score=float(qr.get("read_ratio_hook_score", 0)),
    )
    return True


async def find_exemplar(
    topic: str,
    tags: list[str] | None = None,
    min_overlap: float = 0.10,
) -> dict[str, Any] | None:
    """Find best-matching exemplar by topic and tag overlap.

    Scores exemplars by (keyword_overlap × 0.7 + tag_overlap × 0.3) × exemplar_score.

    Args:
        topic: Post topic to find exemplar for.
        tags: List of Medium tags (optional).
        min_overlap: Minimum score threshold (default 0.10).

    Returns:
        Best exemplar dict if score >= min_overlap, else None.
    """
    db = get_db()
    exemplars = await db.exemplars.find({}, {"_id": 0}).to_list(length=200)
    if not exemplars:
        return None

    topic_words = {
        w.lower().strip(".,!?:;\"'")
        for w in topic.split()
        if len(w) > 3 and w.lower() not in _STOP_WORDS
    }
    tags_set = {t.lower() for t in (tags or [])}

    def _match(ex: dict[str, Any]) -> float:
        kw = set(ex.get("topic_keywords", []))
        ex_tags = {t.lower() for t in ex.get("tags", [])}
        kw_overlap = len(topic_words & kw) / max(1, len(topic_words))
        tag_overlap = len(tags_set & ex_tags) / max(1, len(tags_set)) if tags_set else 0.0
        return (kw_overlap * 0.7 + tag_overlap * 0.3) * float(ex.get("score", 0.0))

    ranked = sorted(exemplars, key=_match, reverse=True)
    best = ranked[0]
    return best if _match(best) >= min_overlap else None


def format_exemplar_injection(ex: dict[str, Any]) -> str:
    """Format exemplar as annotated blueprint for prompt injection.

    Shows quality bar, hook pattern, and structure reference without prescribing
    verbatim copying. Emphasizes patterns, not templates.

    Args:
        ex: Exemplar dict from MongoDB (with title, hook, intro, code_block, etc).

    Returns:
        Formatted blueprint string for injection into generation prompt.
    """
    parts = [
        "━━━ QUALITY REFERENCE — this is your hook and structure target ━━━━━━━━━",
        f'Related post: "{ex["title"]}"',
        f'Achieved: score {ex["score"]:.2f} | read ratio {ex["read_ratio"]:.0%} | {ex["word_count"]} words',
        "",
        "HOOK — sentence 1 of that post (the single line that locked in the read ratio):",
        f'  ✓ GOOD: "{ex["hook"]}"',
        f"     ↳ Why it works: leads with a specific number/result/failure — reader knows the",
        f"       payoff before reading word 10. No topic-setting. No 'X is changing everything.'",
        "",
        "  ✗ BAD hooks (do NOT write anything like these):",
        '     "Artificial intelligence is transforming the way we work."',
        '     "In this post, I\'ll show you how to improve your workflow."',
        '     "Have you ever wondered why some developers are more productive?"',
        '     "Today I want to talk about a technique that changed my career."',
        "",
        "CONSTRAINT: Your first sentence MUST follow the GOOD hook pattern above.",
        "Lead with a specific number, dollar amount, failure, or surprising result.",
        "The topic name belongs in sentence 2 — never sentence 1.",
        "",
        f"INTRO ({ex['intro_word_count']} words — core insight lands before word 80):",
        ex["intro"],
    ]

    if ex.get("code_block"):
        parts += [
            "",
            "CODE INTEGRATION (this post had runnable examples — match this depth):",
            ex["code_block"],
        ]

    parts += [
        "",
        "Match this level of specificity, hook strength, and structural depth.",
        "Different topic — same quality bar. The hook constraint above is mandatory.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(parts)
