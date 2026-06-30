"""LangGraph pipeline orchestrator for Medium post generation.

Defines the pipeline state, compiled graph, and entrypoint runners.
"""

import operator
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, cast

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from app.agents.content_generator import (
    GeneratedPost as GeneratedPost,
)
from app.agents.content_generator import (
    enforce_paragraph_sentence_limit as enforce_paragraph_sentence_limit,
)
from app.agents.content_generator import (
    expand_post as expand_post,
)
from app.agents.content_generator import (
    generate_initial_post as generate_initial_post,
)
from app.agents.content_generator import (
    revise_post as revise_post,
)
from app.agents.exemplar_store import (
    EXEMPLAR_THRESHOLD as EXEMPLAR_THRESHOLD,
)
from app.agents.exemplar_store import (
    find_exemplar as find_exemplar,
)
from app.agents.exemplar_store import (
    format_exemplar_injection as format_exemplar_injection,
)
from app.agents.exemplar_store import (
    save_exemplar as save_exemplar,
)
from app.agents.fact_checker import (
    extract_claims as extract_claims,
)
from app.agents.fact_checker import (
    inject_hyperlinks as inject_hyperlinks,
)
from app.agents.fact_checker import (
    results_to_issues as results_to_issues,
)
from app.agents.fact_checker import (
    verify_claims as verify_claims,
)
from app.agents.formatter import format_post as format_post
from app.agents.intro_ab_tester import run_intro_ab_test as run_intro_ab_test
from app.agents.logger import log_step as log_step

# Imports from individual node files to preserve API compatibility
from app.agents.nodes import (
    _gate_check as _gate_check,
)
from app.agents.nodes import (
    ai_slop_detector_node as ai_slop_detector_node,
)
from app.agents.nodes import (
    close_optimization_node as close_optimization_node,
)
from app.agents.nodes import (
    human_voice_scorer_node as human_voice_scorer_node,
)
from app.agents.nodes import (
    truth_enforcer_node as truth_enforcer_node,
)
from app.agents.nodes.line_editor_node import (
    line_editor_node as line_editor_node,
)
from app.agents.nodes.structure_validator_node import (
    structure_validator_node as structure_validator_node,
)
from app.agents.nodes.copy_editor_node import (
    copy_editor_node as copy_editor_node,
)
from app.agents.nodes.sme_reviewer_node import sme_reviewer_node
from app.agents.nodes.engagement_optimizer_node import engagement_optimizer_node
from app.agents.nodes.readability_scorer_node import readability_scorer_node
from app.agents.nodes import (
    content_generation_node as content_generation_node,
)
from app.agents.nodes import (
    content_revision_node as content_revision_node,
)
from app.agents.nodes import (
    fact_check_node as fact_check_node,
)
from app.agents.nodes import (
    finalize_node as finalize_node,
)
from app.agents.nodes import (
    format_node as format_node,
)
from app.agents.nodes import (
    image_description_enrichment_node as image_description_enrichment_node,
)
from app.agents.nodes import (
    intro_ab_testing_node as intro_ab_testing_node,
)
from app.agents.nodes import (
    quality_analysis_node as quality_analysis_node,
)
from app.agents.nodes import (
    repo_analysis_node as repo_analysis_node,
)
from app.agents.nodes import (
    research_node as research_node,
)
from app.agents.nodes import (
    series_coherence_node as series_coherence_node,
)
from app.agents.nodes import (
    title_optimization_node as title_optimization_node,
)
from app.agents.nodes import (
    topic_refinement_node as topic_refinement_node,
)
from app.agents.post_processor import (
    inject_captions as inject_captions,
)
from app.agents.post_processor import (
    merge_sources_sections as merge_sources_sections,
)
from app.agents.publication_matcher import (
    run_publication_matching as run_publication_matching,
)
from app.agents.quality_analyzer import run_quality_analysis as run_quality_analysis
from app.agents.repo_analyzer import RepoAnalyzer as RepoAnalyzer
from app.agents.series_coherence_checker import (
    run_series_coherence_check as run_series_coherence_check,
)
from app.agents.series_runner import run_series as run_series
from app.agents.nodes.finalize import (
    _compute_publication_recommendation as _compute_publication_recommendation,
)
from app.agents.structural_checker import run_structural_checks as run_structural_checks
from app.agents.title_optimizer import run_title_optimization as run_title_optimization
from app.agents.topic_refiner import run_topic_refinement as run_topic_refinement

# Re-expose original imports to ensure full compatibility with unit test mocks/patches
from app.config import settings as settings
from app.database import get_db as get_db
from app.models.post import (
    PostStatus as PostStatus,
)
from app.models.post import (
    QualityIssue as QualityIssue,
)
from app.models.post import (
    QualityReport as QualityReport,
)
from app.models.post import (
    VerificationResult as VerificationResult,
)


class PipelineState(TypedDict):
    run_id: str
    custom_topic: str
    grounding_context: str
    series_id: str | None
    series_position: int | None
    series_context: str  # angle + hook_seed injected by run_series; "" for standalone runs
    trend_context: str  # populated by research_node; "" when Tavily unavailable
    refined_topic: str | None  # formatted_brief from topic_refiner; used by content_generation
    topic_brief: dict[str, Any] | None  # TopicBrief as dict for MongoDB storage
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
    evidence_brief: dict[str, Any] | None    # EvidenceBrief.model_dump() from repo_analysis_node; None when skipped
    structural_check_issues: list[dict[str, Any]]  # accumulated by ai_slop, truth_enforcer nodes
    ai_slop_issues: list[dict[str, Any]]
    ai_slop_score: float
    ai_slop_passed: bool
    unattributed_numbers: list[str]
    truth_enforcer_passed: bool
    human_voice_score: float
    human_voice_metrics: dict[str, Any]
    human_voice_passed: bool
    line_edit_score: float | None
    line_edit_metrics: dict[str, Any] | None
    line_edit_passed: bool | None
    structure_score: float | None
    structure_metrics: dict[str, Any] | None
    structure_passed: bool | None
    copy_edit_score: float | None
    copy_edit_metrics: dict[str, Any] | None
    copy_edit_passed: bool | None
    sme_score: float | None
    sme_metrics: dict[str, Any] | None
    sme_passed: bool | None
    engagement_score: float | None
    engagement_metrics: dict[str, Any] | None
    engagement_passed: bool | None
    readability_score: float | None
    readability_metrics: dict[str, Any] | None
    readability_passed: bool | None


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
    It constructs the structural blueprint of the LangGraph, wiring together all 16 node workers
    (from repo analysis to publication finalization). It establishes the execution sequence,
    defining how drafts are written, revised, tested, and stored.

    Pipeline ASCII diagram (Sprint 30):

        START
          |
        repo_analysis → research → topic_refinement → content_generation
          → intro_ab_testing → series_coherence → title_optimization
          → fact_check → ai_slop_check → truth_enforcement
          → human_voice_check → line_edit_check → structure_check
          → copy_edit_check → sme_review_check → quality_analysis
                |
          [route_after_quality]
          /              \\
      revision        close_optimization
          |                  |
       fact_check    image_description_enrichment
                             |
                           format → finalize → END

    The Flow (El Flujo):
    1. Initialize the `StateGraph` using the typed `PipelineState` schema.
    2. Register the 16 agent node functions as active nodes in the graph.
    3. Wire the linear sequence from `START` to `fact_check` using static edges.
    4. Add a conditional routing edge from `quality_analysis` based on `route_after_quality`.
    5. Wire loopback edges from `revision` back to `fact_check`.
    6. Wire the finalization path from `close_optimization` through formatting to `finalize` and `END`.
    7. Compile the graph and return the executable runner.

    Returns:
        A compiled LangGraph CompiledGraph ready for ainvoke.
    """
    g = StateGraph(PipelineState)
    g.add_node("repo_analysis", cast(Any, repo_analysis_node))
    g.add_node("research", cast(Any, research_node))
    g.add_node("topic_refinement", cast(Any, topic_refinement_node))
    g.add_node("content_generation", cast(Any, content_generation_node))
    g.add_node("intro_ab_testing", cast(Any, intro_ab_testing_node))
    g.add_node("series_coherence", cast(Any, series_coherence_node))
    g.add_node("title_optimization", cast(Any, title_optimization_node))
    g.add_node("fact_check", cast(Any, fact_check_node))
    g.add_node("ai_slop_check", cast(Any, ai_slop_detector_node))
    g.add_node("truth_enforcement", cast(Any, truth_enforcer_node))
    g.add_node("human_voice_check", cast(Any, human_voice_scorer_node))
    g.add_node("line_edit_check", cast(Any, line_editor_node))
    g.add_node("structure_check", cast(Any, structure_validator_node))
    g.add_node("copy_edit_check", cast(Any, copy_editor_node))
    g.add_node("sme_review_check", sme_reviewer_node)
    g.add_node("engagement_check", engagement_optimizer_node)
    g.add_node("readability_check", readability_scorer_node)
    g.add_node("quality_analysis", cast(Any, quality_analysis_node))
    g.add_node("revision", cast(Any, content_revision_node))
    g.add_node("close_optimization", cast(Any, close_optimization_node))
    g.add_node("image_description_enrichment", cast(Any, image_description_enrichment_node))
    g.add_node("format", cast(Any, format_node))
    g.add_node("finalize", cast(Any, finalize_node))

    g.add_edge(START, "repo_analysis")
    g.add_edge("repo_analysis", "research")
    g.add_edge("research", "topic_refinement")
    g.add_edge("topic_refinement", "content_generation")
    g.add_edge("content_generation", "intro_ab_testing")
    g.add_edge("intro_ab_testing", "series_coherence")
    g.add_edge("series_coherence", "title_optimization")
    g.add_edge("title_optimization", "fact_check")
    g.add_edge("fact_check", "ai_slop_check")
    g.add_edge("ai_slop_check", "truth_enforcement")
    g.add_edge("truth_enforcement", "human_voice_check")
    g.add_edge("human_voice_check", "line_edit_check")
    g.add_edge("line_edit_check", "structure_check")
    g.add_edge("structure_check", "copy_edit_check")
    g.add_edge("copy_edit_check", "sme_review_check")
    g.add_edge("sme_review_check", "engagement_check")
    g.add_edge("engagement_check", "readability_check")
    g.add_edge("readability_check", "quality_analysis")
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
        "structural_check_issues": [],
        "ai_slop_issues": [],
        "ai_slop_score": 0.0,
        "ai_slop_passed": None,
        "unattributed_numbers": [],
        "truth_enforcer_passed": None,
        "human_voice_score": None,
        "human_voice_metrics": None,
        "human_voice_passed": None,
        "line_edit_score": None,
        "line_edit_metrics": None,
        "line_edit_passed": None,
        "structure_score": None,
        "structure_metrics": None,
        "structure_passed": None,
        "copy_edit_score": None,
        "copy_edit_metrics": None,
        "copy_edit_passed": None,
        "sme_score": None,
        "sme_metrics": None,
        "sme_passed": None,
        "engagement_score": None,
        "engagement_metrics": None,
        "engagement_passed": None,
        "readability_score": None,
        "readability_metrics": None,
        "readability_passed": None,
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
