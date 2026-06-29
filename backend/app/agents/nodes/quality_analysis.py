from datetime import UTC, datetime
from typing import Any, Dict, List, Tuple
from app.config import settings
from app.database import get_db
from app.models.post import QualityIssue, QualityReport, ReadRatioFactor
from app.agents.logger import log_step
from app.agents.quality_analyzer import run_quality_analysis, _STRUCTURAL_CATEGORIES
from app.agents.structural_checker import run_structural_checks
from app.agents.read_ratio_analyzer import analyze_read_ratio

async def quality_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Scores the current post using structural checks and an LLM quality rubric.

    The Story (El Relato):
    In the story of our pipeline, this node represents the Quality Control Gatekeeper.
    Every article must pass strict standards before publication. This node acts as an auditor,
    combining deterministic rule-based checks (like paragraph lengths, word count, and forbidden AI expressions)
    with a multi-axis G-Eval rubric scored by an LLM (hook strength, specificity, voice, and insight).
    It also merges any factual validation failures and produces a final quality report. If the article fails
    to meet our minimum quality metrics, it is directed to the revision node.

    The Flow (El Flujo):
    1. Log the initiation of quality analysis.
    2. Call `run_quality_analysis` using the LLM analyzer to evaluate the rubric scores.
    3. Run local regex checks (`run_structural_checks`) and import fact-checking issues from the state.
    4. Merge all structural, factual, and quality issues into a single sorted list.
    5. Evaluate all gate thresholds (overall score, read ratio, minimum word count, and high-severity issues).
    6. Record a detailed quality snapshot and update the database record.
    7. Return the updated quality report and history entry. If errors occur, log and return them to halt the execution.

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
        # 1. Run LLM rubric evaluation
        report = await run_quality_analysis(
            run_id=run_id, title=post.title, content=post.content
        )

        # 2. Add local structural and factual checks
        structural_issues = run_structural_checks(post.content)
        fact_issues: List[QualityIssue] = state.get("fact_check_issues") or []
        report.issues = structural_issues + fact_issues + report.issues

        # 3. Evaluate quality gates
        passed, gate_failures = _gate_check(report)

        # 4. Log audit results and write database records
        await _log_and_persist_quality_metrics(state, report, passed, gate_failures)

        history_entry = {
            "cycle": state.get("revision_count", 0),
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


def _gate_check(report: QualityReport) -> Tuple[bool, List[str]]:
    """Four independent quality gates — ALL must pass to approve the post.

    The Story (El Relato):
    In the story of our quality control, these gates are the Editorial Standards.
    An article might be incredibly insightful but too short for partnership monetization,
    or it might have a high score but contain highly recognizable AI-generated cliches.
    This function verifies the post against four barriers: minimum composite quality score,
    predicted read ratio, presence of severe AI patterns, and minimum word count limit.

    Args:
        report: The QualityReport to evaluate.

    Returns:
        Tuple of (passed, list of failure reasons).
    """
    failures: List[str] = []

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


async def _log_and_persist_quality_metrics(
    state: Dict[str, Any],
    report: QualityReport,
    passed: bool,
    gate_failures: List[str]
) -> None:
    """Logs the audit summary to state logger and writes records to MongoDB."""
    run_id = state["run_id"]
    level = "success" if passed else "warning"
    boost_label = "Boost-eligible" if report.medium_boost_eligible else "NOT Boost-eligible"
    
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
    
    snapshot = {
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
