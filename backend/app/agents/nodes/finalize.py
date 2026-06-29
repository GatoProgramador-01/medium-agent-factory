import asyncio
from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityReport, VerificationResult
from app.agents.logger import log_step
from app.agents.post_processor import inject_captions, merge_sources_sections
from app.agents.exemplar_store import EXEMPLAR_THRESHOLD, save_exemplar
from app.agents.publication_matcher import run_publication_matching

async def finalize_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Persists the approved post to MongoDB and computes publication recommendation.

    The Story (El Relato):
    In the story of our pipeline, this node is the Publisher and Archiver.
    Once the post is perfectly formatted, this node runs final cleanup tasks (like ensuring
    all images have captions and deduplicating reference sections). It stores the article,
    its quality reports, and its revision history permanently in the database. Crucially,
    if the post's quality score exceeds our exemplar threshold (>= 0.95), it is automatically
    saved to our Exemplar Store to teach future writer agents how to succeed. Finally, it
    analyzes the post's characteristics to recommend the best matching Medium publications.

    The Flow (El Flujo):
    1. Retrieve the approved post, quality report, and history entries.
    2. Apply deterministic post-processing: deduplicate headers (`merge_sources_sections`) and inject caption placeholders.
    3. Construct a dictionary of verified sources from the fact-checker's results.
    4. Save the finalized article metadata and content to the MongoDB `posts` collection.
    5. Check the final score: if it is >= 0.95, invoke `save_exemplar` to store it as a few-shot guide.
    6. Calculate publication alignment and score confidence levels, logging the outcomes and returning them.

    Args:
        state: Pipeline state with "post", "quality_report", "fact_check_results",
            "quality_history", "revision_count", and "run_id".

    Returns:
        Dict with "completed_steps", "recommended_publication" (bool), and
        "publication_confidence" (float 0.0–1.0).
    """
    run_id = state["run_id"]
    qr = state.get("quality_report")
    post = state.get("post")
    history = state.get("quality_history", [])
    
    # 1. Prepare quality metrics and log finalization
    quality_fields = _build_quality_database_fields(qr, history, state.get("revision_count", 0))

    # 2. In-place deterministic post-processing
    if post:
        post.content = inject_captions(post.content)
        post.content = merge_sources_sections(post.content)

    # 3. Extract fact-checked source materials
    fc_results: List[VerificationResult] = state.get("fact_check_results") or []
    quality_fields["sources"] = _extract_verified_sources(fc_results)
    if post:
        quality_fields["title"] = post.title
        quality_fields["content"] = post.content
        quality_fields["tags"] = post.tags
        quality_fields["image_suggestions"] = post.image_suggestions

    # 4. Save finalized post to MongoDB
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": quality_fields},
    )

    # 5. Save as few-shot exemplar if score is outstanding
    if qr and post:
        await _save_exemplar_if_qualified(run_id, post.title, post.content, qr.score)

    # 6. Run publication matching heuristics
    rec, confidence = _compute_publication_recommendation(state)
    
    # Try running publication matching API in the background (non-blocking)
    if qr and post:
        asyncio.create_task(
            _run_non_blocking_pub_matcher(run_id, post.title, post.tags, qr.score, qr.medium_boost_eligible, state.get("topic_brief"))
        )

    await log_step(
        run_id,
        "finalizer",
        f"Post archived successfully. Recommended for publication: {rec} (confidence {confidence:.2%})",
        level="success" if rec else "info",
    )

    return {
        "completed_steps": ["finalized"],
        "recommended_publication": rec,
        "publication_confidence": confidence,
    }


def _build_quality_database_fields(qr: Any, history: list, revision_count: int) -> dict:
    """Builds the database update fields based on the quality report."""
    fields = {
        "status": str(PostStatus.APPROVED),
        "quality_history": history,
        "revision_count": revision_count,
        "updated_at": datetime.now(UTC),
    }
    if qr:
        fields["quality_score"] = qr.score
        fields["read_ratio_prediction"] = qr.read_ratio_prediction
        fields["medium_boost_eligible"] = qr.medium_boost_eligible
        fields["word_count"] = qr.word_count
        fields["quality_report"] = {
            "score": qr.score,
            "read_ratio_prediction": qr.read_ratio_prediction,
            "medium_boost_eligible": qr.medium_boost_eligible,
            "issues": [
                {
                    "category": i.category,
                    "severity": i.severity,
                    "suggestion": i.suggestion,
                }
                for i in qr.issues
            ],
            "strengths": qr.strengths,
        }
    return fields


def _extract_verified_sources(fc_results: List[VerificationResult]) -> list:
    """Collects and groups all verified fact-check sources into database-ready documents."""
    return [
        {
            "claim_text": r.claim.text,
            "source_url": r.source_url,
            "source_title": r.source_title,
            "claim_type": r.claim.claim_type,
            "location": r.claim.location,
        }
        for r in fc_results
        if r.verdict == "SUPPORTED" and r.source_url
    ]


async def _save_exemplar_if_qualified(run_id: str, title: str, content: str, score: float) -> None:
    """Saves the article into our exemplar collection if it meets high quality metrics."""
    if score >= EXEMPLAR_THRESHOLD:
        try:
            await save_exemplar(title=title, content=content, score=score)
            await log_step(
                run_id,
                "finalizer",
                f'Outstanding quality (score {score:.2f} >= {EXEMPLAR_THRESHOLD}) '
                f'— saved as new few-shot exemplar: "{title}"',
                level="success",
            )
        except Exception as e:
            await log_step(
                run_id,
                "finalizer",
                f"Failed to save exemplar: {e} — continuing",
                level="warning",
            )


def _compute_publication_recommendation(state: dict) -> tuple[bool, float]:
    """Compute publication recommendation and confidence score.

    Returns (recommended, confidence) where:
      - recommended: True if all hard gates pass, False otherwise
      - confidence: 0.0-1.0 score weighted by quality_score (0.5), read_ratio (0.3),
                    and revision progress (0.2); capped at 0.70 when max revisions exhausted
    """
    if state.get("errors") or state.get("quality_report") is None:
        return (False, 0.0)

    qr = state["quality_report"]
    quality_score = qr.score if hasattr(qr, "score") else qr.get("score", 0.0)
    read_ratio = (
        qr.read_ratio_prediction
        if hasattr(qr, "read_ratio_prediction")
        else qr.get("read_ratio_prediction", 0.0)
    )

    if quality_score < settings.min_quality_score:
        return (False, 0.0)

    if read_ratio < settings.min_read_ratio:
        return (False, 0.0)

    def _issue_value(issue: Any, field: str) -> Any:
        if isinstance(issue, dict):
            return issue.get(field)
        return getattr(issue, field, None)

    structural_issues = state.get("structural_check_issues") or []
    blocking_structural = [
        i
        for i in structural_issues
        if (
            _issue_value(i, "severity") == "HIGH"
            and _issue_value(i, "category") != "word_count"
        )
    ]
    if blocking_structural:
        return (False, 0.0)

    fact_results = state.get("fact_check_results") or []
    if fact_results:
        fact_issues = state.get("fact_check_issues") or []
        high_fact_issues = [
            i for i in fact_issues if _issue_value(i, "severity") == "HIGH"
        ]
        if high_fact_issues:
            return (False, 0.0)

    revision_count = state.get("revision_count", 0)
    max_cycles = settings.max_revision_cycles
    revision_term = (
        max(0.0, 1.0 - (revision_count / max_cycles)) if max_cycles > 0 else 0.0
    )

    confidence = round(quality_score * 0.5 + read_ratio * 0.3 + revision_term * 0.2, 4)

    if revision_count >= max_cycles:
        confidence = min(confidence, 0.70)

    return (True, confidence)


async def _run_non_blocking_pub_matcher(
    run_id: str,
    title: str,
    tags: List[str],
    score: float,
    boost_eligible: bool,
    topic_brief: Any
) -> None:
    """Matches the post to the top-3 publications in the background."""
    try:
        refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""
        result = await run_publication_matching(
            run_id=run_id,
            title=title,
            tags=tags,
            quality_score=score,
            medium_boost_eligible=boost_eligible,
            refined_angle=refined_angle or "",
        )
        db = get_db()
        await db.posts.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "publication_recommendations": [
                        {
                            "name": pub.name,
                            "fit_score": pub.fit_score,
                            "rationale": pub.rationale,
                        }
                        for pub in result.publications
                    ]
                }
            },
        )
    except Exception as e:
        await log_step(
            run_id,
            "finalizer",
            f"Publication matching skipped/failed in background: {e}",
            level="warning",
        )
