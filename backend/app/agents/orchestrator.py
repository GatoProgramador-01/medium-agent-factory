"""LangGraph pipeline orchestrator for Medium post generation. Defines all node functions, gate check logic, routing decisions, and the compiled graph. Server restart required after any node change.

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

import asyncio
import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.content_generator import (
    GeneratedPost,
    enforce_paragraph_sentence_limit,
    expand_post,
    generate_initial_post,
    revise_post,
)
from app.agents.post_processor import inject_captions, merge_sources_sections
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
from app.agents.image_description_enricher import run_image_description_enrichment
from app.agents.intro_ab_tester import run_intro_ab_test
from app.agents.read_ratio_analyzer import format_factors_breakdown
import app.agents.close_optimizer as _close_optimizer_module
from app.agents.series_coherence_checker import run_series_coherence_check
from app.agents.title_optimizer import run_title_optimization
from app.agents.formatter import format_post
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis
from app.agents.structural_checker import run_structural_checks
from app.agents.publication_matcher import run_publication_matching
from app.agents.series_planner import plan_series
from app.agents.web_researcher import research_topic
from app.config import settings
from app.database import get_db
from app.models.post import PostStatus, QualityIssue, QualityReport, VerificationResult
from app.agents.repo_analyzer import RepoAnalyzer


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str
    grounding_context: str
    series_id: str | None
    series_position: int | None
    series_context: (
        str  # angle + hook_seed injected by run_series; "" for standalone runs
    )
    trend_context: str  # populated by research_node; "" when Tavily unavailable
    refined_topic: str | None  # formatted_brief from topic_refiner; used by content_generation
    topic_brief: dict | None  # TopicBrief as dict for MongoDB storage

    post: GeneratedPost | None
    quality_report: QualityReport | None
    pull_quote: str | None
    format_changes: Annotated[list[str], operator.add]
    revision_count: int
    quality_history: Annotated[list[dict[str, Any]], operator.add]  # score per cycle
    fact_check_issues: list[QualityIssue]  # unverifiable claims from fact_checker_node
    fact_check_results: list[
        VerificationResult
    ]  # all results; re-injected in format_node
    errors: Annotated[list[str], operator.add]
    completed_steps: Annotated[list[str], operator.add]
    recommended_publication: bool
    publication_confidence: float
    draft_content: str  # approved post content; populated by close_optimization_node before format
    title_variants: list[str]  # candidate titles from title_optimization_node
    intro_variants: list[str]  # candidate openings from intro_ab_testing_node
    series_coherence_score: float | None
    image_enrichment_changes: list[str]
    repo_path: str | None          # optional local repo for RepoAnalyzer grounding; None = skip
    evidence_brief: dict | None    # EvidenceBrief.model_dump() from repo_analysis_node; None when skipped


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def research_node(state: PipelineState) -> dict[str, Any]:
    """Performs web research for the post topic using Tavily search.

    Queries Tavily with topic + trend signals, aggregates results into
    structured trend_context for the content generator. Sets state["research_results"].
    Skips gracefully if Tavily is unavailable.

    Args:
        state: Pipeline state containing "topic" and "run_id".

    Returns:
        Dict with "trend_context" key containing aggregated Tavily output, and
        "completed_steps" log entry. Empty trend_context on error.
    """
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
        await log_step(
            run_id, "web_researcher", f"Research skipped: {e}", level="warning"
        )
        return {"trend_context": "", "completed_steps": ["research"]}


async def repo_analysis_node(state: PipelineState) -> dict[str, Any]:
    """Optionally analyzes a local repository and stores structured evidence.

    Runs before research_node. When repo_path is None the node is a no-op —
    returns evidence_brief=None without calling the analyzer. When repo_path
    is set the EvidenceBrief is serialized to a dict so downstream nodes can
    inject it into topic_refiner as grounding context.

    Args:
        state: Pipeline state — only repo_path is read.

    Returns:
        Dict with evidence_brief (dict|None) and completed_steps.
        On FileNotFoundError or any exception: evidence_brief=None, error appended.
    """
    run_id = state["run_id"]
    repo_path = state.get("repo_path")

    if not repo_path:
        return {
            "evidence_brief": None,
            "completed_steps": ["repo_analysis_skipped"],
        }

    await log_step(run_id, "repo_analyzer", f"Analyzing repository: {repo_path}")

    try:
        brief = RepoAnalyzer().analyze(repo_path)
        await log_step(
            run_id,
            "repo_analyzer",
            f"Evidence extracted: {len(brief.stack)} stack items, {brief.metrics.get('files_scanned', 0)} files scanned",
            level="success",
        )
        return {
            "evidence_brief": brief.model_dump(),
            "completed_steps": ["repo_analysis"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "repo_analyzer",
            f"Repo analysis failed: {e} — continuing without evidence",
            level="warning",
        )
        return {
            "evidence_brief": None,
            "errors": [f"repo_analysis failed: {e}"],
            "completed_steps": ["repo_analysis_skipped"],
        }


async def topic_refinement_node(state: PipelineState) -> dict[str, Any]:
    """Refines raw topic + research into a structured editorial brief.

    Runs after research_node, before content_generation_node. Uses Sonnet (supervisor
    model) to synthesize the raw topic, web research, and user grounding context into
    a TopicBrief with refined angle, hook seed, H2 structure, and key claims.

    Args:
        state: Pipeline state with "custom_topic", "trend_context", and optionally
            "grounding_context".

    Returns:
        Dict with "refined_topic" (formatted_brief string) and "topic_brief" (dict).
        On error, falls back: "refined_topic" = custom_topic, "topic_brief" = None.
    """
    from app.agents.topic_refiner import run_topic_refinement

    run_id = state.get("run_id", "unknown")
    topic = state.get("custom_topic", "")
    research_results = state.get("trend_context", "")
    grounding_context = state.get("grounding_context", "")
    raw_brief = state.get("evidence_brief") or {}
    evidence_brief_str = (
        "\n".join(f"- {k}: {v}" for k, v in raw_brief.items()) if raw_brief else ""
    )

    await log_step(
        run_id,
        "topic_refiner",
        f'Refining topic and research into editorial brief: "{topic}"...',
        data={"topic": topic},
    )

    try:
        brief = await run_topic_refinement(
            run_id=run_id,
            topic=topic,
            research_results=research_results,
            grounding_context=grounding_context,
            evidence_brief=evidence_brief_str,
        )
        await log_step(
            run_id,
            "topic_refiner",
            f'Topic brief generated: angle="{brief.refined_angle[:50]}...", target_audience="{brief.target_audience}"',
            level="success",
            data={"refined_angle": brief.refined_angle, "hook_seed": brief.hook_seed},
        )
        return {
            "refined_topic": brief.formatted_brief,
            "topic_brief": brief.model_dump(),
            "completed_steps": ["topic_refinement"],
        }
    except Exception as e:
        # Fallback: if refinement fails, use raw topic (pipeline must not stop)
        await log_step(
            run_id,
            "topic_refiner",
            f"Topic refinement skipped: {e} — using raw topic",
            level="warning",
        )
        return {
            "refined_topic": topic,
            "topic_brief": None,
            "completed_steps": ["topic_refinement_skipped"],
        }


async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    """Generates the initial draft Medium post using Claude Haiku.

    Queries exemplar store for similar high-scoring posts as few-shot references.
    Combines user-provided grounding_context and web research_context to produce
    a GeneratedPost with title, subtitle, content, and tags. Auto-appends Sources
    section if research included URLs but LLM omitted it.

    Args:
        state: Pipeline state with "custom_topic", "grounding_context",
            "trend_context", and "series_context" (if series post).

    Returns:
        Dict with "post" (GeneratedPost), "revision_count" (0), and
        "completed_steps" log. Or "errors" dict on failure.
    """
    run_id = state["run_id"]
    topic = state.get("refined_topic") or state["custom_topic"]

    await log_step(
        run_id,
        "content_generator",
        f'Generating initial draft (Claude Haiku)...',
        data={"model": settings.worker_model, "topic": state["custom_topic"]},
    )
    try:
        exemplar = await find_exemplar(topic)
        exemplar_section = format_exemplar_injection(exemplar) if exemplar else ""
        if exemplar:
            await log_step(
                run_id,
                "content_generator",
                f'Exemplar found: "{exemplar["title"]}" '
                f'(score {exemplar["score"]:.2f}) — injecting as few-shot reference',
                data={
                    "exemplar_title": exemplar["title"],
                    "exemplar_score": exemplar["score"],
                },
            )
        grounding_context = state.get("grounding_context", "").strip()
        trend_context = state.get("trend_context", "").strip()
        combined_context = "\n\n".join(
            part
            for part in (
                (
                    "USER-PROVIDED GROUNDING CONTEXT (treat as source notes, "
                    "not prose to copy):\n"
                    f"{grounding_context}"
                )
                if grounding_context
                else "",
                (
                    "WEB RESEARCH CONTEXT (use only when relevant and cite URLs):\n"
                    f"{trend_context}"
                )
                if trend_context
                else "",
            )
            if part
        )
        post = await generate_initial_post(
            run_id=run_id,
            topic=topic,
            trend_context=combined_context,
            tags=[],
            audience="software engineers and developers building LLM agents and AI pipelines",
            exemplar_section=exemplar_section,
            series_context=state.get("series_context", ""),
        )
        # Deterministic guard: if research included source URLs but the LLM
        # skipped the Sources section, append it rather than relying on revision.
        if "SOURCE URLS" in trend_context and "## Sources" not in post.content:
            url_block = trend_context.split("SOURCE URLS")[1].strip()
            source_lines = [
                ln.strip()
                for ln in url_block.splitlines()
                if ln.strip().startswith("- http")
            ]
            if source_lines:
                post.content += "\n\n## Sources\n" + "\n".join(source_lines)
                await log_step(
                    run_id,
                    "content_generator",
                    f"Sources section auto-appended ({len(source_lines)} URLs — LLM skipped it)",
                    level="warning",
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


async def title_optimization_node(state: PipelineState) -> dict[str, Any]:
    """Generates 3–5 optimised title variants and selects the strongest one.

    Runs after content_generation_node, before fact_check_node. Replaces the
    LLM-generated title with the highest-scoring variant anchored to the post's
    central argument and hook sentence.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with "post" (updated title), "title_variants" (list of candidate
        title strings), and "completed_steps". Returns empty dict on exception
        so the pipeline keeps the original title.
    """
    run_id = state["run_id"]
    post = state.get("post")
    if not post:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "title_optimizer",
        f'Optimising title: "{post.title}"...',
        data={"original_title": post.title},
    )

    try:
        result = await run_title_optimization(
            run_id=run_id,
            title=post.title,
            content=post.content,
            refined_angle=refined_angle or "",
        )

        original_title = post.title
        post.title = result.best_title
        title_variants = [v.text for v in result.variants]

        await log_step(
            run_id,
            "title_optimizer",
            f'Title optimised: "{original_title}" → "{result.best_title}" '
            f"({len(result.variants)} variants generated)",
            level="success",
            data={
                "original_title": original_title,
                "best_title": result.best_title,
                "variants": title_variants,
                "original_title_weakness": result.original_title_weakness,
            },
        )

        return {
            "post": post,
            "title_variants": title_variants,
            "completed_steps": ["title_optimization"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "title_optimizer",
            f"Title optimization skipped: {e} — keeping original title",
            level="warning",
        )
        return {}


async def intro_ab_testing_node(state: PipelineState) -> dict[str, Any]:
    """Replaces the draft opening with the strongest A/B-tested intro.

    Runs after content_generation_node and before series/title polish so the
    downstream agents see the improved hook. The node only swaps the first
    non-empty paragraph and fails open on any model error.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with updated "post", "intro_variants", and "completed_steps".
        Returns empty dict on error so the original intro is preserved.
    """
    run_id = state["run_id"]
    post = state.get("post")
    if not post or not post.content:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "intro_ab_tester",
        "Testing alternate openings for hook strength...",
        data={"title": post.title},
    )

    try:
        result = await run_intro_ab_test(
            run_id=run_id,
            title=post.title,
            content=post.content,
            refined_angle=refined_angle or "",
        )

        post = post.model_copy(deep=True)
        paragraphs = post.content.split("\n\n")
        first_idx = next((i for i, p in enumerate(paragraphs) if p.strip()), 0)
        original_intro = paragraphs[first_idx]
        paragraphs[first_idx] = result.best_intro
        post.content = enforce_paragraph_sentence_limit("\n\n".join(paragraphs))
        intro_variants = [v.text for v in result.variants]

        await log_step(
            run_id,
            "intro_ab_tester",
            f"Opening strengthened ({len(result.variants)} variants tested).",
            level="success",
            data={
                "original_intro": original_intro[:500],
                "best_intro": result.best_intro,
                "original_intro_problem": result.original_intro_problem,
            },
        )
        return {
            "post": post,
            "intro_variants": intro_variants,
            "completed_steps": ["intro_ab_testing"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "intro_ab_tester",
            f"Intro A/B test skipped: {e} - keeping original opening",
            level="warning",
        )
        return {}


async def series_coherence_node(state: PipelineState) -> dict[str, Any]:
    """Checks whether a series installment fits its assigned series role.

    Runs only when series_context is present. If the checker returns revised
    content, the node patches the post body before title and fact-check passes.

    Args:
        state: Pipeline state with optional "series_context" and "post".

    Returns:
        Dict with "series_coherence_score", optional updated "post", and
        "completed_steps". Returns empty dict for standalone posts or errors.
    """
    run_id = state["run_id"]
    post = state.get("post")
    series_context = state.get("series_context", "")
    if not post or not series_context:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "series_coherence_checker",
        "Checking series continuity and installment scope...",
        data={"series_position": state.get("series_position")},
    )

    try:
        result = await run_series_coherence_check(
            run_id=run_id,
            title=post.title,
            content=post.content,
            series_context=series_context,
            series_position=state.get("series_position"),
            refined_angle=refined_angle or "",
        )
        if result.revised_content.strip():
            post = post.model_copy(deep=True)
            post.content = enforce_paragraph_sentence_limit(result.revised_content)

        await log_step(
            run_id,
            "series_coherence_checker",
            f"Series coherence score: {result.coherence_score:.2f}",
            level="success" if result.coherence_score >= 0.75 else "warning",
            data={
                "coherence_score": result.coherence_score,
                "issues": [i.model_dump() for i in result.issues],
                "continuity_notes": result.continuity_notes,
                "content_revised": bool(result.revised_content.strip()),
            },
        )
        return {
            "post": post,
            "series_coherence_score": result.coherence_score,
            "completed_steps": ["series_coherence"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "series_coherence_checker",
            f"Series coherence check skipped: {e}",
            level="warning",
        )
        return {}


async def fact_check_node(state: PipelineState) -> dict[str, Any]:
    """Extracts and verifies factual claims in the post using Tavily.

    Runs in parallel: extract_claims identifies verifiable assertions, verify_claims
    searches the web to validate each claim. Injects hyperlinks to sources where
    available. Flags unverifiable claims as QualityIssues for later revision.

    Args:
        state: Pipeline state containing "post" (GeneratedPost).

    Returns:
        Dict with "post" (updated with hyperlinks), "fact_check_issues" (unverifiable
        claims), "fact_check_results" (all verification results), and "completed_steps".
        Returns empty lists if fact_check_enabled is False or no post.
    """
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
            await log_step(
                run_id,
                "fact_checker",
                "No verifiable claims found — skipping",
                level="info",
            )
            return {
                "fact_check_issues": [],
                "fact_check_results": [],
                "completed_steps": ["fact_check"],
            }

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
            data={
                "hyperlinks_injected": hyperlinks,
                "unverifiable_count": unverifiable,
            },
        )
        return {
            "post": post,
            "fact_check_issues": issues,
            "fact_check_results": all_results,  # stored for re-injection in format_node
            "completed_steps": ["fact_check"],
        }
    except Exception as e:
        await log_step(
            run_id, "fact_checker", f"Fact check skipped: {e}", level="warning"
        )
        return {
            "fact_check_issues": [],
            "fact_check_results": [],
            "completed_steps": ["fact_check_skipped"],
        }


async def quality_analysis_node(state: PipelineState) -> dict[str, Any]:
    """Scores the current post using structural checks and an LLM quality rubric.

    Runs three parallel evaluations: run_structural_checks (deterministic regex
    patterns), run_quality_analysis (G-Eval rubric via Haiku), and merges any
    fact_check_issues from the prior fact_check_node. Writes a quality snapshot
    to MongoDB for every iteration and evaluates all four quality gates via
    _gate_check.

    Args:
        state: Pipeline state with "post", "run_id", "revision_count",
            and "fact_check_issues".

    Returns:
        Dict with "quality_report" (QualityReport), "quality_history" list entry,
        and "completed_steps". Or "errors" dict on failure.
    """
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
        boost_label = (
            "Boost-eligible" if report.medium_boost_eligible else "NOT Boost-eligible"
        )

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
            "issue_summary": {
                "high": high_c,
                "medium": med_c,
                "low": low_c,
                "total": len(report.issues),
            },
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
            "issue_categories": [
                i.category for i in report.issues if i.severity.lower() == "high"
            ],
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
    """Revises the post based on quality gate failures and the analyzer's feedback.

    Selects between two revision strategies: expand_post (additive) when only
    word count fails, or revise_post (full rewrite) for all other gate failures.
    Injects a prior-cycle summary when multiple revision cycles have run so the
    LLM knows which issues are "sticky". Increments revision_count and persists
    the revised post to MongoDB.

    Args:
        state: Pipeline state with "post", "quality_report", "revision_count",
            "run_id", and "quality_history".

    Returns:
        Dict with "post" (revised GeneratedPost), "revision_count" (incremented),
        and "completed_steps". Or "errors" dict on failure.
    """
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
    word_count_only = len(gate_failures) == 1 and "word count" in gate_failures[0]

    try:
        if word_count_only:
            deficit = (
                settings.min_word_count - report.word_count + 150
            )  # 150-word buffer
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


async def close_optimization_node(state: PipelineState) -> dict[str, Any]:
    """Replaces the post's last paragraph with a stronger, more specific close.

    Runs after quality gates pass, before format_node. Generates 2-4 alternative
    closing paragraphs tied to the post's central argument and substitutes the
    best one in place of the original last paragraph.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with "draft_content" (post content with replaced close) on success,
        or empty dict on any exception so the pipeline keeps the original close.
    """
    run_id = state["run_id"]
    post = state.get("post")
    content = post.content if post else state.get("draft_content", "")
    if not content:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    try:
        result = await _close_optimizer_module.run_close_optimization(
            run_id=run_id,
            content=content,
            refined_angle=refined_angle or "",
        )

        # Replace last non-empty paragraph with the best close
        paragraphs = content.split("\n\n")
        # Find last non-empty paragraph index
        last_idx = len(paragraphs) - 1
        while last_idx > 0 and not paragraphs[last_idx].strip():
            last_idx -= 1
        paragraphs[last_idx] = result.best_close
        updated_content = "\n\n".join(paragraphs)

        # Patch post in-place if it exists so downstream nodes see updated content
        if post:
            post.content = updated_content

        return {"draft_content": updated_content}
    except Exception:
        # Fallback: keep original close; pipeline continues uninterrupted
        return {}


async def image_description_enrichment_node(state: PipelineState) -> dict[str, Any]:
    """Improves image placeholders and image suggestions before formatting.

    Runs after close_optimization_node, before format_node. Replaces exact
    [IMAGE: ...] placeholders when the enricher supplies an exact match and
    updates post.image_suggestions for downstream persistence. The node fails
    open so image polish never blocks publication.

    Args:
        state: Pipeline state with "post", "topic_brief", and "run_id".

    Returns:
        Dict with updated "post", "image_enrichment_changes", and
        "completed_steps". Returns empty dict on error.
    """
    run_id = state["run_id"]
    post = state.get("post")
    if not post or not post.content:
        return {}

    topic_brief: dict | None = state.get("topic_brief")
    refined_angle = (topic_brief or {}).get("refined_angle", "") if topic_brief else ""

    await log_step(
        run_id,
        "image_description_enricher",
        "Enriching image placeholders and alt text...",
        data={"suggestion_count": len(post.image_suggestions or [])},
    )

    try:
        result = await run_image_description_enrichment(
            run_id=run_id,
            title=post.title,
            content=post.content,
            image_suggestions=post.image_suggestions or [],
            refined_angle=refined_angle or "",
        )

        changes: list[str] = []
        updated_content = post.content
        for image in result.images:
            original = image.original_placeholder.strip()
            if not original or original not in updated_content:
                continue
            replacement = (
                f"[IMAGE: {image.description} | alt: {image.alt_text}"
                + (f" | caption: {image.caption}" if image.caption else "")
                + "]"
            )
            updated_content = updated_content.replace(original, replacement, 1)
            changes.append(f"enriched image: {image.description[:80]}")

        if result.image_suggestions:
            post.image_suggestions = result.image_suggestions
            changes.append("updated image suggestions")

        post.content = updated_content

        await log_step(
            run_id,
            "image_description_enricher",
            f"Image enrichment complete ({len(changes)} change(s)).",
            level="success",
            data={"changes": changes},
        )
        return {
            "post": post,
            "image_enrichment_changes": changes,
            "completed_steps": ["image_description_enrichment"],
        }
    except Exception as e:
        await log_step(
            run_id,
            "image_description_enricher",
            f"Image enrichment skipped: {e}",
            level="warning",
        )
        return {}


async def format_node(state: PipelineState) -> dict[str, Any]:
    """Applies deterministic formatting to the final approved post version.

    Re-injects source hyperlinks from fact_check_results (revision cycles may
    have rewritten phrasing that contained them), then calls format_post to
    split long paragraphs, add separators, and extract a pull quote. Runs
    exactly once on the approved content — not inside the revision loop.

    Args:
        state: Pipeline state with "post", "fact_check_results", "run_id",
            and "revision_count".

    Returns:
        Dict with "post" (formatted), "pull_quote" (str), "format_changes"
        (list of applied changes), and "completed_steps". Or "errors" on failure.
    """
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

        result = await format_post(
            run_id=run_id, title=post.title, content=post.content
        )

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
    """Persists the approved post to MongoDB and computes publication recommendation.

    Runs deterministic post-processing (inject_captions, merge_sources_sections),
    writes the final quality report and quality_history to the posts collection,
    and auto-saves the post as a few-shot exemplar when score >= EXEMPLAR_THRESHOLD.
    Calls _compute_publication_recommendation for the final recommended_publication
    flag and publication_confidence score.

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
        quality_fields["quality_report"] = {
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
    # Deterministic post-processing: inject caption placeholders + merge duplicate source sections
    if post:
        post.content = inject_captions(post.content)
        post.content = merge_sources_sections(post.content)

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
    if state.get("topic_brief"):
        quality_fields["topic_brief"] = state["topic_brief"]
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": quality_fields},
    )
    await _update_pipeline_run(state, "approved")
    score_msg = f" Final quality score: {qr.score:.2f}" if qr else ""
    cycles_msg = f" Revision cycles: {state.get('revision_count', 0)}/{settings.max_revision_cycles}."
    await log_step(
        run_id,
        "orchestrator",
        f"Post approved and saved.{score_msg}{cycles_msg}",
        level="success",
    )

    # Auto-save as exemplar when score clears the threshold
    if qr and post and qr.score >= EXEMPLAR_THRESHOLD:
        try:
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
                run_id,
                "orchestrator",
                f"Post saved as few-shot exemplar (score {qr.score:.2f} >= {EXEMPLAR_THRESHOLD}).",
                level="success",
                data={"exemplar_saved": True, "score": qr.score},
            )
        except Exception:
            # Exemplar saving should never crash the pipeline
            pass

    # Non-blocking publication matching — runs after pipeline finalize, never blocks.
    # Suggestions are stored in the post document for frontend sidebar display.
    if post and qr:
        try:
            pub_match = await asyncio.wait_for(
                run_publication_matching(
                    run_id=run_id,
                    title=post.title,
                    tags=post.tags,
                    quality_score=qr.score,
                    medium_boost_eligible=qr.medium_boost_eligible,
                    refined_angle=(
                        state.get("topic_brief", {}).get("refined_angle", "")
                        if state.get("topic_brief")
                        else ""
                    ),
                ),
                timeout=30.0,
            )
            await db.posts.update_one(
                {"run_id": run_id},
                {
                    "$set": {
                        "publication_matches": [m.model_dump() for m in pub_match.matches],
                        "publication_top_pick": pub_match.top_pick,
                        "publication_strategy": pub_match.strategy,
                    }
                },
            )
            await log_step(
                run_id,
                "publication_matcher",
                f"Publication match complete. Top pick: {pub_match.top_pick}.",
                level="success",
                data={"top_pick": pub_match.top_pick, "match_count": len(pub_match.matches)},
            )
        except Exception:
            # Publication matching is non-blocking — a failure here must never
            # stop the pipeline or cause the post to be marked as failed.
            pass

    recommended, pub_confidence = _compute_publication_recommendation(state)

    return {
        "completed_steps": ["finalized"],
        "recommended_publication": recommended,
        "publication_confidence": pub_confidence,
    }


# ── Publication recommendation ─────────────────────────────────────────────────


def _compute_publication_recommendation(state: dict) -> tuple[bool, float]:
    """
    Compute publication recommendation and confidence score.

    Returns (recommended, confidence) where:
      - recommended: True if all hard gates pass, False otherwise
      - confidence: 0.0-1.0 score weighted by quality_score (0.5), read_ratio (0.3),
                    and revision progress (0.2); capped at 0.70 when max revisions exhausted
    """
    # Guard: error path or missing data
    if state.get("errors") or state.get("quality_report") is None:
        return (False, 0.0)

    qr = state["quality_report"]
    quality_score = qr.score if hasattr(qr, "score") else qr.get("score", 0.0)
    read_ratio = (
        qr.read_ratio_prediction
        if hasattr(qr, "read_ratio_prediction")
        else qr.get("read_ratio_prediction", 0.0)
    )

    # Hard gate 1: quality score
    if quality_score < settings.min_quality_score:
        return (False, 0.0)

    # Hard gate 2: read ratio
    if read_ratio < settings.min_read_ratio:
        return (False, 0.0)

    def _issue_value(issue: Any, field: str) -> Any:
        """Read issue fields from either dicts or Pydantic model instances."""
        if isinstance(issue, dict):
            return issue.get(field)
        return getattr(issue, field, None)

    # Hard gate 3: structural HIGH issues (exclude word_count category)
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

    # Hard gate 4: fact-check HIGH issues — ONLY if fact_check_results ran
    fact_results = state.get("fact_check_results") or []
    if fact_results:
        fact_issues = state.get("fact_check_issues") or []
        high_fact_issues = [
            i for i in fact_issues if _issue_value(i, "severity") == "HIGH"
        ]
        if high_fact_issues:
            return (False, 0.0)

    # All gates passed — compute confidence
    revision_count = state.get("revision_count", 0)
    max_cycles = settings.max_revision_cycles
    revision_term = (
        max(0.0, 1.0 - (revision_count / max_cycles)) if max_cycles > 0 else 0.0
    )

    confidence = round(quality_score * 0.5 + read_ratio * 0.3 + revision_term * 0.2, 4)

    # Cap confidence if revisions exhausted
    if revision_count >= max_cycles:
        confidence = min(confidence, 0.70)

    return (True, confidence)


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
            i
            for i in report.issues
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
    """LangGraph conditional edge: decide next node after quality_analysis_node.

    Checks gate results and revision budget. Routes to "revision" when gates
    fail and cycles remain; routes to "finalize" (which triggers format then
    finalize via static edges) in all other cases — pass, error, or exhausted
    revision budget.

    Args:
        state: Pipeline state with "quality_report", "revision_count", and "errors".

    Returns:
        "revision" to run content_revision_node, or "finalize" to proceed to
        format_node → finalize_node.
    """
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
    """Compile and return the LangGraph StateGraph for the Medium post pipeline.

    Registers all node functions, wires static edges, and attaches the
    route_after_quality conditional edge on the quality_analysis node.
    The compiled graph is module-level singleton `pipeline` — call
    run_pipeline() rather than invoking the graph directly.

    Returns:
        A compiled LangGraph CompiledGraph ready for ainvoke.
    """
    g = StateGraph(PipelineState)
    g.add_node("repo_analysis", repo_analysis_node)
    g.add_node("research", research_node)
    g.add_node("topic_refinement", topic_refinement_node)
    g.add_node("content_generation", content_generation_node)
    g.add_node("intro_ab_testing", intro_ab_testing_node)
    g.add_node("series_coherence", series_coherence_node)
    g.add_node("title_optimization", title_optimization_node)
    g.add_node("fact_check", fact_check_node)
    g.add_node("quality_analysis", quality_analysis_node)
    g.add_node("revision", content_revision_node)
    g.add_node("close_optimization", close_optimization_node)
    g.add_node("image_description_enrichment", image_description_enrichment_node)
    g.add_node("format", format_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "repo_analysis")
    g.add_edge("repo_analysis", "research")
    g.add_edge("research", "topic_refinement")
    g.add_edge("topic_refinement", "content_generation")
    g.add_edge("content_generation", "intro_ab_testing")
    g.add_edge("intro_ab_testing", "series_coherence")
    g.add_edge("series_coherence", "title_optimization")
    g.add_edge("title_optimization", "fact_check")
    g.add_edge("fact_check", "quality_analysis")
    g.add_conditional_edges(
        "quality_analysis",
        route_after_quality,
        {"finalize": "close_optimization", "revision": "revision"},
    )
    g.add_edge("revision", "fact_check")
    g.add_edge("close_optimization", "image_description_enrichment")
    g.add_edge("image_description_enrichment", "format")
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
    grounding_context: str = "",
    repo_path: str | None = None,
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
                "grounding_context": grounding_context,
                "status": "running",
                "created_at": datetime.now(UTC),
            }
        )
    await log_step(run_id, "orchestrator", f'Pipeline started. Topic: "{custom_topic}"')

    initial_state: PipelineState = {
        "run_id": run_id,
        "custom_topic": custom_topic,
        "grounding_context": grounding_context,
        "series_id": series_id,
        "series_position": series_position,
        "series_context": series_context,
        "trend_context": "",
        "refined_topic": None,
        "topic_brief": None,
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
        "recommended_publication": False,
        "publication_confidence": 0.0,
        "draft_content": "",
        "title_variants": [],
        "intro_variants": [],
        "series_coherence_score": None,
        "image_enrichment_changes": [],
        "repo_path": repo_path,
        "evidence_brief": None,
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
        "recommended_publication": final_state.get("recommended_publication", False),
        "publication_confidence": final_state.get("publication_confidence", 0.0),
        "title_variants": final_state.get("title_variants", []),
        "intro_variants": final_state.get("intro_variants", []),
        "series_coherence_score": final_state.get("series_coherence_score"),
        "image_enrichment_changes": final_state.get("image_enrichment_changes", []),
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
    await log_step(
        plan_run_id, "series_planner", f'Planning series for theme: "{theme}"'
    )

    plan = await plan_series(run_id=plan_run_id, theme=theme, context=context)

    await log_step(
        plan_run_id,
        "series_planner",
        f'Series planned: "{plan.series_title}" — {len(plan.posts)} posts',
        level="success",
        data={
            "series_title": plan.series_title,
            "series_description": plan.series_description,
            "posts": [{"position": p.position, "angle": p.angle} for p in plan.posts],
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
            f'SERIES: Post {post_plan.position} of {len(plan.posts)} — "{plan.series_title}"\n'
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

    series_status = (
        "completed" if all(r["status"] == "completed" for r in results) else "failed"
    )
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
