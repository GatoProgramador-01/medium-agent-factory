"""
Orchestrator — LangGraph pipeline

Graph:
  START
    │
    ▼
  research                (WebResearcher — Tavily search + LLM synthesis; skips gracefully)
    │
    ▼
  content_generation      (ContentGeneratorAgent — Haiku initial draft)
    │
    ▼
  quality_analysis        (QualityAnalyzerAgent — Haiku, scores raw content)
    │
    ├─── score >= 0.90 ──→ format ──→ finalize → END
    │
    └─── score < 0.90 AND revisions < max
              revision_count=1 → Haiku revision
              revision_count=2 → Sonnet revision
              revision_count=3 → Sonnet final attempt
                │
                ▼
          quality_analysis (loop back)
                │
          score >= 0.90 OR revisions exhausted
                │
                ▼
             format (runs ONCE on the final approved version)
                │
                ▼
           finalize → END

Cost note: format (Haiku ~$0.002) runs exactly once regardless of revision count.
"""

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.content_generator import (
    GeneratedPost,
    expand_post,
    generate_initial_post,
    revise_post,
)
from app.agents.exemplar_store import (
    EXEMPLAR_THRESHOLD,
    find_exemplar,
    format_exemplar_injection,
    save_exemplar,
)
from app.agents.fact_checker import (
    extract_claims,
    inject_hyperlinks,
    results_to_issues,
    run_fact_check,
    verify_claims,
)
from app.agents.read_ratio_analyzer import format_factors_breakdown
from app.agents.formatter import format_post
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis
from app.agents.structural_checker import run_structural_checks
from app.agents.series_planner import plan_series
from app.agents.web_researcher import research_topic
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityIssue, QualityReport, VerificationResult


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str
    series_id: str | None
    series_position: int | None
    series_context: str  # angle + hook_seed injected by run_series; "" for standalone runs
    trend_context: str  # populated by research_node; "" when Tavily unavailable

    post: GeneratedPost | None
    quality_report: QualityReport | None
    pull_quote: str | None
    format_changes: Annotated[list[str], operator.add]
    revision_count: int
    quality_history: Annotated[list[dict[str, Any]], operator.add]  # score per cycle
    fact_check_issues: list[QualityIssue]      # unverifiable claims from fact_checker_node
    fact_check_results: list[VerificationResult]  # all results; re-injected in format_node
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def research_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    topic = state["custom_topic"]

    await log_step(
        run_id,
        "web_researcher",
        f'Searching web for grounded data on: "{topic}"...',
        data={"topic": topic},
    )
    try:
        trend_context = await research_topic(run_id=run_id, topic=topic)
        if trend_context:
            fact_count = trend_context.count("•")
            await log_step(
                run_id,
                "web_researcher",
                f"Research complete — {fact_count} data points ready for the writer",
                level="success",
                data={"preview": trend_context[:300]},
            )
        else:
            await log_step(
                run_id,
                "web_researcher",
                "No web context available (Tavily key missing or no results) — continuing",
                level="warning",
            )
        return {"trend_context": trend_context, "completed_steps": ["research"]}
    except Exception as e:
        await log_step(run_id, "web_researcher", f"Research skipped: {e}", level="warning")
        return {"trend_context": "", "completed_steps": ["research"]}


async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    topic = state["custom_topic"]

    await log_step(
        run_id,
        "content_generator",
        f'Generating initial draft for topic: "{topic}" (Claude Haiku)...',
        data={"model": settings.worker_model, "topic": topic},
    )
    try:
        exemplar = await find_exemplar(topic)
        exemplar_section = format_exemplar_injection(exemplar) if exemplar else ""
        if exemplar:
            await log_step(
                run_id, "content_generator",
                f'Exemplar found: "{exemplar["title"]}" '
                f'(score {exemplar["score"]:.2f}) — injecting as few-shot reference',
                data={"exemplar_title": exemplar["title"], "exemplar_score": exemplar["score"]},
            )
        post = await generate_initial_post(
            run_id=run_id,
            topic=topic,
            trend_context=state.get("trend_context", ""),
            tags=[],
            audience="software engineers and developers building LLM agents and AI pipelines",
            exemplar_section=exemplar_section,
            series_context=state.get("series_context", ""),
        )
        word_count = len(post.content.split())
        await log_step(
            run_id,
            "content_generator",
            f'Draft generated: "{post.title}" (~{word_count} words)',
            level="success",
            data={"title": post.title, "word_count": word_count, "tags": post.tags},
        )
        await _upsert_post(
            run_id,
            post,
            PostStatus.DRAFT,
            series_id=state.get("series_id"),
            series_position=state.get("series_position"),
        )
        return {
            "post": post,
            "revision_count": 0,
            "completed_steps": ["content_generation"],
        }
    except Exception as e:
        await log_step(run_id, "content_generator", f"Failed: {e}", level="error")
        return {"errors": [f"content_generation failed: {e}"]}


async def fact_check_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        return {"fact_check_issues": [], "fact_check_results": []}

    if not settings.fact_check_enabled:
        return {
            "fact_check_issues": [],
            "fact_check_results": [],
            "completed_steps": ["fact_check_skipped"],
        }

    await log_step(
        run_id,
        "fact_checker",
        "Extracting and verifying factual claims (parallel Tavily searches)...",
    )
    try:
        claims = await extract_claims(post.content)
        if not claims:
            await log_step(run_id, "fact_checker", "No verifiable claims found — skipping", level="info")
            return {"fact_check_issues": [], "fact_check_results": [], "completed_steps": ["fact_check"]}

        all_results = await verify_claims(claims)
        annotated = inject_hyperlinks(post.content, all_results)
        issues = results_to_issues(all_results)

        hyperlinks = annotated.count("](http") - post.content.count("](http")
        unverifiable = len(issues)
        post.content = annotated

        await log_step(
            run_id,
            "fact_checker",
            f"Fact check complete — {hyperlinks} source(s) injected, {unverifiable} unverifiable claim(s) flagged",
            level="success" if unverifiable == 0 else "warning",
            data={"hyperlinks_injected": hyperlinks, "unverifiable_count": unverifiable},
        )
        return {
            "post": post,
            "fact_check_issues": issues,
            "fact_check_results": all_results,  # stored for re-injection in format_node
            "completed_steps": ["fact_check"],
        }
    except Exception as e:
        await log_step(run_id, "fact_checker", f"Fact check skipped: {e}", level="warning")
        return {"fact_check_issues": [], "fact_check_results": [], "completed_steps": ["fact_check_skipped"]}


async def quality_analysis_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "quality_analyzer", "No post to analyze", level="error")
        return {"errors": ["quality_analysis: no post"]}

    await log_step(
        run_id,
        "quality_analyzer",
        "Analyzing post quality (structural checks + content rubric)...",
    )
    try:
        report = await run_quality_analysis(
            run_id=run_id, title=post.title, content=post.content
        )

        structural_issues = run_structural_checks(post.content)
        fact_issues: list[QualityIssue] = state.get("fact_check_issues") or []
        all_prepend = structural_issues + fact_issues
        if all_prepend:
            report.issues = all_prepend + report.issues

        passed, gate_failures = _gate_check(report)
        level = "success" if passed else "warning"
        boost_label = "Boost-eligible" if report.medium_boost_eligible else "NOT Boost-eligible"

        high_count = sum(1 for i in report.issues if i.severity.lower() == "high")
        med_count = sum(1 for i in report.issues if i.severity.lower() == "medium")
        low_count = sum(1 for i in report.issues if i.severity.lower() == "low")
        score_breakdown = (
            f"hook={report.hook_strength:.2f} "
            f"spec={report.specificity_score:.2f} "
            f"voice={report.voice_authenticity:.2f} "
            f"insight={report.insight_value:.2f}"
        )
        rr_breakdown = (
            " | ".join(
                f"{f.name} {f.measured} (-{f.deduction:.0%})"
                for f in report.read_ratio_factors
            )
            if report.read_ratio_factors
            else "no structural issues"
        )

        if passed:
            verdict = (
                f"All gates passed. "
                f"Score: {report.score:.2f} [{score_breakdown}] | "
                f"Read ratio: {report.read_ratio_prediction:.0%} "
                f"[hook={report.read_ratio_hook_score:.2f}, {rr_breakdown}] | "
                f"Words: {report.word_count} | "
                f"{boost_label}."
            )
        else:
            verdict = (
                f"Gate(s) failed — queuing revision. "
                f"Score: {report.score:.2f} [{score_breakdown}] | "
                f"Read ratio: {report.read_ratio_prediction:.0%} "
                f"[hook={report.read_ratio_hook_score:.2f}, {rr_breakdown}]. "
                + " | ".join(gate_failures)
            )

        await log_step(
            run_id,
            "quality_analyzer",
            f"Quality score: {report.score:.2f}/1.0 — {verdict}",
            level=level,
            data={
                "score": report.score,
                "score_breakdown": score_breakdown,
                "read_ratio_prediction": report.read_ratio_prediction,
                "read_ratio_hook_score": report.read_ratio_hook_score,
                "read_ratio_factors": [
                    {"name": f.name, "measured": f.measured, "deduction": f.deduction}
                    for f in report.read_ratio_factors
                ],
                "word_count": report.word_count,
                "medium_boost_eligible": report.medium_boost_eligible,
                "passed": passed,
                "gate_failures": gate_failures,
                "issue_count": len(report.issues),
                "top_issues": [
                    {
                        "severity": i.severity,
                        "category": i.category,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues[:3]
                ],
                "strengths": report.strengths,
            },
        )

        db = get_db()
        await db.posts.update_one(
            {"run_id": run_id},
            {
                "$set": {
                    "quality_report": {
                        "score": report.score,
                        "word_count": report.word_count,
                        "read_ratio_prediction": report.read_ratio_prediction,
                        "medium_boost_eligible": report.medium_boost_eligible,
                        "issues": [
                            {
                                "category": i.category,
                                "severity": i.severity,
                                "location": i.location,
                                "suggestion": i.suggestion,
                            }
                            for i in report.issues
                        ],
                        "strengths": report.strengths,
                        "revision_prompt": report.revision_prompt,
                    }
                }
            },
        )
        cycle = state.get("revision_count", 0)
        high_c = sum(1 for i in report.issues if i.severity.lower() == "high")
        med_c = sum(1 for i in report.issues if i.severity.lower() == "medium")
        low_c = sum(1 for i in report.issues if i.severity.lower() == "low")
        snapshot: dict[str, Any] = {
            "run_id": run_id,
            "series_id": state.get("series_id"),
            "topic": state.get("custom_topic", ""),
            "iteration": cycle,
            "score": report.score,
            "read_ratio": report.read_ratio_prediction,
            "word_count": report.word_count,
            "medium_boost_eligible": report.medium_boost_eligible,
            "passed": passed,
            "gate_failures": gate_failures,
            "issue_summary": {"high": high_c, "medium": med_c, "low": low_c, "total": len(report.issues)},
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "location": i.location,
                    "suggestion": i.suggestion,
                }
                for i in report.issues
            ],
            "strengths": report.strengths,
            "revision_prompt": report.revision_prompt,
        }
        await db.quality_snapshots.insert_one(snapshot)
        history_entry: dict[str, Any] = {
            "cycle": cycle,
            "score": report.score,
            "read_ratio": report.read_ratio_prediction,
            "boost_eligible": report.medium_boost_eligible,
            "issue_count": len(report.issues),
            "passed": passed,
            "gate_failures": gate_failures,
            "issue_categories": [i.category for i in report.issues if i.severity.lower() == "high"],
        }
        return {
            "quality_report": report,
            "quality_history": [history_entry],
            "completed_steps": ["quality_analysis"],
        }
    except Exception as e:
        await log_step(run_id, "quality_analyzer", f"Failed: {e}", level="error")
        return {"errors": [f"quality_analysis failed: {e}"]}


async def content_revision_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    report = state["quality_report"]
    revision_number = state["revision_count"] + 1

    if not post or not report:
        await log_step(
            run_id,
            "content_generator",
            "Missing post or report for revision",
            level="error",
        )
        return {"errors": ["revision: missing post or quality report"]}

    from app.agents.llm_factory import get_model_name as _get_model_name
    model = _get_model_name("worker")
    model_label = model
    max_rev = settings.max_revision_cycles

    await log_step(
        run_id,
        "content_generator",
        f"Revision {revision_number}/{max_rev} — rewriting with {model_label}...",
        data={
            "revision_number": revision_number,
            "model": model,
            "score_before": report.score,
        },
    )
    _, gate_failures = _gate_check(report)

    rr_breakdown_text = format_factors_breakdown(
        report.read_ratio_prediction, report.read_ratio_factors
    )

    # Build a summary of what previous cycles failed to fix so the reviser
    # knows which HIGH issues are "sticky" and must be prioritised.
    quality_history: list[dict[str, Any]] = state.get("quality_history", [])
    prior_cycle_summary = ""
    if len(quality_history) >= 2:
        lines = ["⚠ PRIOR REVISION HISTORY — THESE ISSUES WERE NOT RESOLVED:\n"]
        for entry in quality_history[:-1]:  # all cycles except the current one
            persisted = entry.get("issue_categories", [])
            if persisted:
                lines.append(
                    f"  Cycle {entry['cycle']}: score {entry['score']:.2f} — "
                    f"HIGH issues still present: {', '.join(persisted)}"
                )
        if len(lines) > 1:
            lines.append(
                "Fix the above categories FIRST in this revision — they have already "
                "survived at least one revision attempt and are blocking the quality gate.\n"
            )
            prior_cycle_summary = "\n".join(lines) + "\n"

    # When ONLY word count fails, use expand_post (additive) instead of revise_post (editing).
    # revise_post ignores structural-addition instructions — empirically adds only 1-54 words
    # per cycle. expand_post generates a new section in creation mode and appends it verbatim.
    word_count_only = (
        len(gate_failures) == 1
        and "word count" in gate_failures[0]
    )

    try:
        if word_count_only:
            deficit = settings.min_word_count - report.word_count + 150  # 150-word buffer
            new_section = await expand_post(
                run_id=run_id,
                title=post.title,
                content=post.content,
                deficit=deficit,
            )
            post.content = post.content + "\n\n" + new_section
            word_count = len(post.content.split())
            await log_step(
                run_id,
                "content_generator",
                f"Revision {revision_number} complete (expand): "
                f'"{post.title}" (~{word_count} words)',
                level="success",
                data={"title": post.title, "word_count": word_count, "mode": "expand"},
            )
            await _upsert_post(
                run_id, post, PostStatus.REVISED, revision_count=revision_number
            )
            return {
                "post": post,
                "revision_count": revision_number,
                "completed_steps": [f"revision_{revision_number}"],
            }
        else:
            revised = await revise_post(
                run_id=run_id,
                title=post.title,
                content=post.content,
                score=report.score,
                revision_prompt=report.revision_prompt,
                issues=[
                    {
                        "category": i.category,
                        "severity": i.severity,
                        "location": i.location,
                        "suggestion": i.suggestion,
                    }
                    for i in report.issues
                ],
                strengths=report.strengths,
                gate_failures=gate_failures,
                read_ratio_breakdown=rr_breakdown_text,
                revision_number=revision_number,
                prior_cycle_summary=prior_cycle_summary,
            )
            word_count = len(revised.content.split())
            await log_step(
                run_id,
                "content_generator",
                f"Revision {revision_number} complete: "
                f'"{revised.title}" (~{word_count} words)',
                level="success",
                data={"title": revised.title, "word_count": word_count},
            )
            await _upsert_post(
                run_id, revised, PostStatus.REVISED, revision_count=revision_number
            )
            return {
                "post": revised,
                "revision_count": revision_number,
                "completed_steps": [f"revision_{revision_number}"],
            }
    except Exception as e:
        await log_step(
            run_id,
            "content_generator",
            f"Revision {revision_number} failed: {e}",
            level="error",
        )
        return {"errors": [f"revision failed: {e}"]}


async def format_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    post = state["post"]
    if not post:
        await log_step(run_id, "formatter", "No post to format", level="error")
        return {"errors": ["format: no post"]}

    await log_step(
        run_id,
        "formatter",
        "Formatting final approved version: splitting long paragraphs, adding separator, extracting pull quote...",
    )
    try:
        # Re-inject source hyperlinks into the final approved content.
        # Hyperlinks were injected into the initial draft by fact_check_node but revision
        # cycles rewrite those phrases. Re-applying here ensures sources survive.
        fc_results: list[VerificationResult] = state.get("fact_check_results") or []
        if fc_results:
            post.content = inject_hyperlinks(post.content, fc_results)

        result = await format_post(run_id=run_id, title=post.title, content=post.content)

        # Patch the post content in-place so finalize_node sees the formatted version
        post.content = result.formatted_content

        changes_summary = (
            f"{len(result.changes_applied)} change(s) applied"
            if result.changes_applied
            else "no structural changes needed"
        )
        await log_step(
            run_id,
            "formatter",
            f'Formatting complete — {changes_summary}. Pull quote: "{result.pull_quote[:80]}..."',
            level="success",
            data={
                "changes_applied": result.changes_applied,
                "pull_quote": result.pull_quote,
            },
        )
        await _upsert_post(
            run_id,
            post,
            PostStatus.APPROVED,
            revision_count=state.get("revision_count", 0),
            pull_quote=result.pull_quote,
            format_changes=result.changes_applied,
        )
        return {
            "post": post,
            "pull_quote": result.pull_quote,
            "format_changes": result.changes_applied,
            "completed_steps": ["formatted"],
        }
    except Exception as e:
        await log_step(run_id, "formatter", f"Failed: {e}", level="error")
        return {"errors": [f"format failed: {e}"]}


async def finalize_node(state: PipelineState) -> dict[str, Any]:
    run_id = state["run_id"]
    qr = state.get("quality_report")
    post = state.get("post")
    history = state.get("quality_history", [])
    db = get_db()
    quality_fields: dict[str, Any] = {
        "status": str(PostStatus.APPROVED),
        "quality_history": history,
        "revision_count": state.get("revision_count", 0),
        "updated_at": datetime.now(UTC),
    }
    if qr:
        quality_fields["quality_score"] = qr.score
        quality_fields["read_ratio_prediction"] = qr.read_ratio_prediction
        quality_fields["medium_boost_eligible"] = qr.medium_boost_eligible
        quality_fields["word_count"] = qr.word_count
    verified_sources = [
        {
            "claim_text": r.claim.text,
            "source_url": r.source_url,
            "source_title": r.source_title,
            "claim_type": r.claim.claim_type,
        }
        for r in (state.get("fact_check_results") or [])
        if r.verdict == "SUPPORTED" and r.source_url
    ]
    quality_fields["verified_sources"] = verified_sources
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": quality_fields},
    )
    await _update_pipeline_run(state, "approved")
    score_msg = f" Final quality score: {qr.score:.2f}" if qr else ""
    cycles_msg = f" Revision cycles: {state.get('revision_count', 0)}/{settings.max_revision_cycles}."
    await log_step(
        run_id, "orchestrator", f"Post approved and saved.{score_msg}{cycles_msg}", level="success"
    )

    # Auto-save as exemplar when score clears the threshold
    if qr and post and qr.score >= EXEMPLAR_THRESHOLD:
        await save_exemplar(
            run_id=run_id,
            title=post.title,
            content=post.content,
            tags=post.tags,
            score=qr.score,
            read_ratio=qr.read_ratio_prediction,
            hook_score=qr.read_ratio_hook_score,
        )
        await log_step(
            run_id, "orchestrator",
            f"Post saved as few-shot exemplar (score {qr.score:.2f} >= {EXEMPLAR_THRESHOLD}).",
            level="success",
            data={"exemplar_saved": True, "score": qr.score},
        )

    return {"completed_steps": ["finalized"]}


# ── Quality gate ───────────────────────────────────────────────────────────────


def _gate_check(report: QualityReport) -> tuple[bool, list[str]]:
    """
    Four independent quality gates — ALL must pass to approve the post.

    Returns (passed, failure_reasons).

    Gate 1 — Overall score    : earnings potential, composite of all rubric axes
    Gate 2 — Read ratio       : predicted 30-sec read rate; drives revenue directly
    Gate 3 — AI pattern block : any HIGH-severity AI issue (forbidden phrases, structural
                                slop) disqualifies regardless of overall score
    Gate 4 — Word count       : under 1,200 words is too short for Partner Program earnings
    """
    failures: list[str] = []

    if report.score < settings.min_quality_score:
        failures.append(
            f"score {report.score:.2f} below minimum {settings.min_quality_score}"
        )

    if report.read_ratio_prediction < settings.min_read_ratio:
        failures.append(
            f"read ratio {report.read_ratio_prediction:.0%} below minimum "
            f"{settings.min_read_ratio:.0%} — intro or hook needs work"
        )

    if settings.block_high_ai_patterns:
        # Only block on structural AI pattern issues (ai_pattern from structural_checker).
        # "ai" in i.category is too broad — it matches "unattributed_claim" ("cl**ai**m")
        # which would incorrectly prevent word-count-only expansion path from running.
        ai_blocks = [
            i for i in report.issues
            if i.severity.lower() == "high" and i.category.startswith("ai_")
        ]
        if ai_blocks:
            failures.append(
                f"{len(ai_blocks)} high-severity AI pattern(s): "
                + "; ".join(i.category for i in ai_blocks[:2])
            )

    if report.word_count < settings.min_word_count:
        needed = settings.min_word_count - report.word_count
        failures.append(
            f"word count {report.word_count} below minimum {settings.min_word_count} "
            f"— add ~{needed} words of specific detail to the shortest sections"
        )

    return len(failures) == 0, failures


# ── Routing ────────────────────────────────────────────────────────────────────


def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)
    errors = state.get("errors", [])
    if errors:
        return "finalize"
    if not report:
        return "finalize"
    passed, _ = _gate_check(report)
    if passed:
        return "finalize"
    if revisions >= settings.max_revision_cycles:
        return "finalize"
    return "revision"


# ── Graph ──────────────────────────────────────────────────────────────────────


def build_graph() -> Any:
    g = StateGraph(PipelineState)
    g.add_node("research", research_node)
    g.add_node("content_generation", content_generation_node)
    g.add_node("fact_check", fact_check_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("format", format_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "research")
    g.add_edge("research", "content_generation")
    g.add_edge("content_generation", "fact_check")
    g.add_edge("fact_check", "quality_analysis")
    g.add_conditional_edges(
        "quality_analysis",
        route_after_quality,
        {"finalize": "format", "revision": "revision"},
    )
    g.add_edge("revision", "quality_analysis")
    g.add_edge("format", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


pipeline = build_graph()


# ── Public entrypoint ──────────────────────────────────────────────────────────


async def run_pipeline(
    custom_topic: str,
    run_id: str | None = None,
    series_id: str | None = None,
    series_position: int | None = None,
    series_context: str = "",
) -> dict[str, Any]:
    db = get_db()

    if run_id:
        await db.pipeline_runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "running", "started_at": datetime.now(UTC)}},
        )
    else:
        run_id = str(uuid.uuid4())
        await db.pipeline_runs.insert_one(
            {
                "run_id": run_id,
                "custom_topic": custom_topic,
                "status": "running",
                "created_at": datetime.now(UTC),
            }
        )
    await log_step(run_id, "orchestrator", f'Pipeline started. Topic: "{custom_topic}"')

    initial_state: PipelineState = {
        "run_id": run_id,
        "custom_topic": custom_topic,
        "series_id": series_id,
        "series_position": series_position,
        "series_context": series_context,
        "trend_context": "",
        "post": None,
        "quality_report": None,
        "pull_quote": None,
        "format_changes": [],
        "revision_count": 0,
        "quality_history": [],
        "fact_check_issues": [],
        "fact_check_results": [],
        "errors": [],
        "completed_steps": [],
    }

    final_state = await pipeline.ainvoke(initial_state)

    status = "failed" if final_state.get("errors") else "completed"
    await db.pipeline_runs.update_one(
        {"run_id": run_id},
        {"$set": {"status": status, "completed_at": datetime.now(UTC)}},
    )

    if status == "failed":
        await log_step(
            run_id,
            "orchestrator",
            f"Pipeline failed: {'; '.join(final_state.get('errors', []))}",
            level="error",
        )
    else:
        await log_step(
            run_id, "orchestrator", "Pipeline completed successfully.", level="success"
        )

    post = final_state.get("post")
    qr = final_state.get("quality_report")
    return {
        "run_id": run_id,
        "status": status,
        "title": post.title if post else None,
        "quality_score": qr.score if qr else None,
        "read_ratio_prediction": qr.read_ratio_prediction if qr else None,
        "medium_boost_eligible": qr.medium_boost_eligible if qr else None,
        "pull_quote": final_state.get("pull_quote"),
        "format_changes": final_state.get("format_changes", []),
        "revision_count": final_state.get("revision_count", 0),
        "errors": final_state.get("errors", []),
        "steps": final_state.get("completed_steps", []),
    }


async def run_series(
    theme: str,
    context: str = "",
    series_id: str | None = None,
) -> dict[str, Any]:
    """Plan and run a multi-post series. Posts execute sequentially."""
    db = get_db()
    series_id = series_id or str(uuid.uuid4())

    # ── Step 1: plan ──────────────────────────────────────────────────────────
    plan_run_id = f"{series_id}-planner"
    await log_step(plan_run_id, "series_planner", f'Planning series for theme: "{theme}"')

    plan = await plan_series(run_id=plan_run_id, theme=theme, context=context)

    await log_step(
        plan_run_id,
        "series_planner",
        f'Series planned: "{plan.series_title}" — {len(plan.posts)} posts',
        level="success",
        data={
            "series_title": plan.series_title,
            "series_description": plan.series_description,
            "posts": [
                {"position": p.position, "angle": p.angle} for p in plan.posts
            ],
        },
    )

    await db.series.update_one(
        {"series_id": series_id},
        {
            "$set": {
                "theme": theme,
                "series_title": plan.series_title,
                "series_description": plan.series_description,
                "post_count": len(plan.posts),
                "status": "running",
            },
            "$setOnInsert": {"run_ids": [], "created_at": datetime.now(UTC)},
        },
        upsert=True,
    )

    # ── Step 2: generate each post sequentially ───────────────────────────────
    results = []
    run_ids = []

    for post_plan in sorted(plan.posts, key=lambda p: p.position):
        await log_step(
            plan_run_id,
            "series_planner",
            f"Starting post {post_plan.position}/{len(plan.posts)}: {post_plan.angle}",
        )
        post_series_context = (
            f"SERIES: Post {post_plan.position} of {len(plan.posts)} — \"{plan.series_title}\"\n"
            f"SERIES DESCRIPTION: {plan.series_description}\n"
            f"THIS POST'S ANGLE: {post_plan.angle}\n"
            f"HOOK SEED: {post_plan.hook_seed}\n"
            f"NOTE: Each post in this series is self-contained. Do not reference other posts "
            f"directly (e.g. no 'In part 1...'). The series context is for tone and positioning only."
        )
        result = await run_pipeline(
            custom_topic=post_plan.topic,
            series_id=series_id,
            series_position=post_plan.position,
            series_context=post_series_context,
        )
        results.append(result)
        run_ids.append(result["run_id"])

        await db.series.update_one(
            {"series_id": series_id},
            {"$push": {"run_ids": result["run_id"]}},
        )

        await log_step(
            plan_run_id,
            "series_planner",
            f'Post {post_plan.position} done: "{result.get("title","")}" '
            f'(score={result.get("quality_score","?")}, boost={result.get("medium_boost_eligible","?")})',
            level="success" if result["status"] == "completed" else "error",
        )

    series_status = "completed" if all(r["status"] == "completed" for r in results) else "failed"
    await db.series.update_one(
        {"series_id": series_id},
        {"$set": {"status": series_status, "completed_at": datetime.now(UTC)}},
    )

    return {
        "series_id": series_id,
        "series_title": plan.series_title,
        "series_description": plan.series_description,
        "status": series_status,
        "posts": results,
    }


# ── DB helpers ─────────────────────────────────────────────────────────────────


async def _upsert_post(
    run_id: str,
    post: GeneratedPost,
    status: PostStatus,
    revision_count: int = 0,
    pull_quote: str | None = None,
    format_changes: list[str] | None = None,
    series_id: str | None = None,
    series_position: int | None = None,
) -> None:
    db = get_db()
    fields: dict[str, Any] = {
        "run_id": run_id,
        "topic": post.title,
        "title": post.title,
        "subtitle": post.subtitle,
        "content": post.content,
        "tags": post.tags,
        "image_suggestions": post.image_suggestions,
        "status": str(status),
        "revision_count": revision_count,
        "updated_at": datetime.now(UTC),
    }
    if pull_quote is not None:
        fields["pull_quote"] = pull_quote
    if format_changes is not None:
        fields["format_changes"] = format_changes
    if series_id is not None:
        fields["series_id"] = series_id
    if series_position is not None:
        fields["series_position"] = series_position
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": fields, "$setOnInsert": {"created_at": datetime.now(UTC)}},
        upsert=True,
    )


async def _update_pipeline_run(state: PipelineState, status: str) -> None:
    db = get_db()
    await db.pipeline_runs.update_one(
        {"run_id": state["run_id"]},
        {"$set": {"status": status, "updated_at": datetime.now(UTC)}},
    )
