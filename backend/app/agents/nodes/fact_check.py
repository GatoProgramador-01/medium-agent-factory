from typing import Any, Dict
from app.config import settings
from app.agents.logger import log_step
from app.agents.fact_checker import (
    extract_claims,
    verify_claims,
    inject_hyperlinks,
    results_to_issues,
)

async def fact_check_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts and verifies factual claims in the post using Tavily.

    The Story (El Relato):
    In the story of our pipeline, this node is the Fact Checker and Fact-Grounding Agent.
    In the era of AI writing, trust is the currency. We cannot afford to publish posts with
    hallucinated numbers, false claims, or fake code options. This node extracts any
    verifiable statements from the text (numbers, API structures, library names) and
    searches the web via Tavily to verify their validity. If it finds source evidence, it
    injects appropriate hyperlinks. If a claim cannot be verified, it flags it as a
    Quality Issue to force a rewrite in the revision stage.

    The Flow (El Flujo):
    1. Check if fact-checking is enabled and a post is present in the pipeline state.
    2. Invoke `extract_claims` using our extractor model to identify verifiable assertions.
    3. Parallel-query the Tavily API via `verify_claims` to gather source evidence for each claim.
    4. Ingest verification results, inject successful source hyperlinks into the post's markdown, and map failed verifications into structured quality issues.
    5. Log the verification metrics (sources injected and unverifiable claims flagged).
    6. Return the annotated post content, issues, and results. Fall back on failure.

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
