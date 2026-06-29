from typing import Any, Dict

async def repo_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Optionally analyzes a local repository and stores structured evidence.

    The Story (El Relato):
    In the story of our pipeline, this node is the Codebase Archaeologist.
    When a post needs to be written about a specific codebase, we cannot rely on guesses.
    This node scans the actual code files to construct an "Evidence Brief"—an objective snapshot
    of the technology stack, project architecture, scanned files, and real metrics. This brief
    acts as the primary source of truth for the rest of the generation pipeline, grounding
    all subsequent arguments in actual code structures rather than hallucinated examples.

    The Flow (El Flujo):
    1. Check if a repository path (`repo_path`) was provided in the pipeline state.
    2. If not, log a skipped message and immediately exit with an empty brief.
    3. If provided, instantiate the `RepoAnalyzer` and extract stack, metrics, and architecture hints.
    4. Serialize the resulting structured `EvidenceBrief` as a dictionary.
    5. Handle and log any scanning errors, falling back gracefully to allow the pipeline to proceed.

    Args:
        state: Pipeline state — only repo_path is read.

    Returns:
        Dict with evidence_brief (dict|None) and completed_steps.
        On FileNotFoundError or any exception: evidence_brief=None, error appended.
    """
    from app.agents.orchestrator import log_step, RepoAnalyzer

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
