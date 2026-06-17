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
    """Return (intro_text, word_count) before the first ## or --- separator."""
    split = re.split(r"\n##\s|\n---\n", content, maxsplit=1)
    raw = split[0].strip()
    words = raw.split()
    capped = " ".join(words[:max_words])
    return capped, min(len(words), max_words)


def _extract_hook(intro: str) -> str:
    """Return the first sentence."""
    parts = re.split(r"(?<=[.!?])\s+", intro.replace("\n", " "), maxsplit=1)
    return parts[0].strip()


def _extract_first_code_block(content: str, max_chars: int = 600) -> str | None:
    match = re.search(r"```[\s\S]*?```", content)
    return match.group(0)[:max_chars] if match else None


def _topic_keywords(title: str) -> list[str]:
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
    """Compress and upsert a high-scoring post as a few-shot exemplar."""
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
    """
    Retroactively promote an existing post to exemplar status.
    Returns True if the post was found and saved, False if not found.
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
    """
    Find the best-matching exemplar for this topic.
    Scores by (keyword overlap × 0.7 + tag overlap × 0.3) × exemplar_score.
    Returns None if no exemplar meets min_overlap.
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
    """
    Return an annotated blueprint for injection into the generation prompt.
    Shows structure and quality bar — not a template to copy word-for-word.
    """
    parts = [
        "━━━ REFERENCE EXEMPLAR — study this quality bar, write something new ━━━",
        f'Related post: "{ex["title"]}"',
        f'Achieved: score {ex["score"]:.2f} | read ratio {ex["read_ratio"]:.0%} | {ex["word_count"]} words',
        "",
        "HOOK (sentence 1 — the element that most determines whether readers stay):",
        f'  "{ex["hook"]}"',
        f"  ↳ What made it work: opens with a specific number/failure, not context-setting.",
        "",
        f"INTRO ({ex['intro_word_count']} words — core insight is clear before word 80):",
        ex["intro"],
    ]

    if ex.get("code_block"):
        parts += [
            "",
            "CODE INTEGRATION (this post included runnable examples — match this level):",
            ex["code_block"],
        ]

    parts += [
        "",
        "Write your post at this level of specificity, hook strength, and depth.",
        "Your topic is different — the structure and quality bar are the reference.",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    return "\n".join(parts)
