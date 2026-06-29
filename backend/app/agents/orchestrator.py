"""LangGraph pipeline orchestrator for Medium post generation.

Defines the pipeline state, compiled graph, and entrypoint runners.
"""

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

# Imports from individual node files to preserve API compatibility
from app.agents.nodes import (
    research_node,
    repo_analysis_node,
    topic_refinement_node,
    content_generation_node,
    title_optimization_node,
    intro_ab_testing_node,
    series_coherence_node,
    fact_check_node,
    quality_analysis_node,
    content_revision_node,
    close_optimization_node,
    image_description_enrichment_node,
    format_node,
    finalize_node,
    _gate_check,
    _compute_publication_recommendation,
)

# Export run_series from its standalone runner module
from app.agents.series_runner import run_series

# Re-expose original imports to ensure full compatibility with unit test mocks/patches
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
from app.agents.topic_refiner import run_topic_refinement

class PipelineState(TypedDict):
    run_id: str
    custom_topic: str
    grounding_context: str
    series_id: str | None
    series_position: int | None
    series_context: str  # angle + hook_seed injected by run_series; "" for standalone runs
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
    fact_check_results: list[VerificationResult]  # all results; re-injected in format_node
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


def route_after_quality(state: PipelineState) -> str:
    """LangGraph conditional edge: decide next node after quality_analysis_node.

    The Story (El Relato):
    In the story of our workflow routing, this function represents the Quality Inspector's Verdict.
    Once quality analysis is complete, we must choose the next step. If errors are present
    or all quality gates pass, we route directly to close optimization and finalization.
    If gates fail and we still have revision cycles left in our budget, we loop back to
    revising the draft content.

    The Flow (El Flujo):
    1. Retrieve the quality report, revision count, and errors from the pipeline state.
    2. If errors are present, route to "finalize" (bypassing revisions).
    3. If no quality report is found, route to "finalize".
    4. Call the gate check helper (`_gate_check`) to evaluate if the content meets all gates.
    5. If all gates pass, route to "finalize" (proceeding to close optimization).
    6. If revision cycles have reached the maximum budget threshold, route to "finalize".
    7. Otherwise, route to "revision" to perform a targeted rewrite.

    Args:
        state: The current pipeline state.

    Returns:
        "revision" to run content_revision_node, or "finalize" to proceed to finalization.
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


def build_graph() -> Any:
    """Compile and return the LangGraph StateGraph for the Medium post pipeline.

    The Story (El Relato):
    In the story of our pipeline architecture, this function is the System Architect.
    It constructs the structural blueprint of the LangGraph, wiring together all 14 node workers
    (from repo analysis to publication finalization). It establishes the execution sequence,
    defining how drafts are written, revised, tested, and stored.

    The Flow (El Flujo):
    1. Initialize the `StateGraph` using the typed `PipelineState` schema.
    2. Register the 14 agent node functions as active nodes in the graph.
    3. Wire the linear sequence from `START` to `fact_check` using static edges.
    4. Add a conditional routing edge from `quality_analysis` based on `route_after_quality`.
    5. Wire loopback edges from `revision` back to `fact_check`.
    6. Wire the finalization path from `close_optimization` through formatting to `finalize` and `END`.
    7. Compile the graph and return the executable runner.

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


async def run_pipeline(
    custom_topic: str,
    run_id: str | None = None,
    series_id: str | None = None,
    series_position: int | None = None,
    series_context: str = "",
    grounding_context: str = "",
    repo_path: str | None = None,
) -> dict[str, Any]:
    """Run a single Medium post pipeline iteration.

    The Story (El Relato):
    In the story of our pipeline, this function is the Executive Producer.
    It initiates a new post generation run, assigns a unique run ID, initializes the
    LangGraph pipeline state, and triggers the asynchronous graph execution. Upon
    completion, it records the final completion or failure status in MongoDB and returns
    a detailed summary report to the caller.

    The Flow (El Flujo):
    1. Initialize the MongoDB database helper client.
    2. Assign a unique pipeline `run_id` (UUIDv4) if not supplied, and create/update the database run entry.
    3. Log the pipeline initiation with the target topic.
    4. Construct the initial dictionary state matching `PipelineState` requirements.
    5. Asynchronously invoke the compiled LangGraph pipeline.
    6. Determine run status (completed or failed) based on state errors.
    7. Update MongoDB and write execution history log steps.
    8. Extract the final post title, quality scores, boost eligibility, and publication confidence, returning a summary report.

    Args:
        custom_topic: Raw topic string.
        run_id: Optional existing run ID to resume.
        series_id: Optional series identifier if run is part of a series.
        series_position: Optional installment position in the series.
        series_context: Optional tone and topic notes for series installments.
        grounding_context: Optional user grounding notes.
        repo_path: Optional repository path for local scans.

    Returns:
        Dict detailing the final status, quality score, title, and metrics.
    """
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
