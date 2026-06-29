#!/usr/bin/env python3
"""Runs the full standard improvement loop: analyze snapshots → LLM suggestions → markdown report.

This script is the entry point for the monthly/on-demand prompt improvement cycle.
Output is a markdown file with prioritized suggestions, ready for human review.

Usage:
    python scripts/run_improvement_loop.py
    python scripts/run_improvement_loop.py --runs 20 --output /tmp/suggestions.md
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from backend/ dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analyze_quality_snapshots import analyze
from app.agents.prompt_analyst import run_prompt_analysis

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = [
    "content_generator_system.txt",
    "content_reviser_system.txt",
    "quality_analyzer_system.txt",
    "formatter_system.txt",
    "series_planner_system.txt",
    "claim_extractor_system.txt",
]


def _load_prompt_files() -> dict[str, str]:
    """Loads all prompt files from the prompts directory."""
    result = {}
    for fname in PROMPT_FILES:
        path = PROMPTS_DIR / fname
        if path.exists():
            result[fname] = path.read_text(encoding="utf-8")
    return result


def _render_markdown(report: object, analysis: dict) -> str:
    """Renders the PromptAnalysisReport as a markdown document."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Prompt Improvement Report — {now}",
        "",
        "## Executive Summary",
        "",
        report.summary,
        "",
        "## Data Overview",
        "",
        f"- Runs analyzed: **{report.run_count}**",
        f"- Regression rate: **{report.regression_rate * 100:.1f}%**",
        f"- Top issue: **{report.top_issue}**",
        f"- Word count avg: {analysis.get('word_count', {}).get('avg', '?')} | under-1300: {analysis.get('word_count', {}).get('pct_under_1300', '?')}%",
        "",
        "## Suggestions (priority order)",
        "",
    ]

    for i, s in enumerate(report.suggestions, 1):
        priority_label = {
            1: "P1 — Blocks posts",
            2: "P2 — Degrades quality",
            3: "P3 — Optimization",
        }.get(s.priority, f"P{s.priority}")
        lines += [
            f"### {i}. {s.file} — {s.section}",
            "",
            f"**Priority:** {priority_label}",
            f"**Issue:** {s.issue}",
            f"**Current behavior:** {s.current_behavior}",
            "",
            "**Suggested change:**",
            "```",
            s.suggested_change,
            "```",
            "",
        ]

    return "\n".join(lines)


async def main() -> None:
    """CLI entry point for the improvement loop."""
    parser = argparse.ArgumentParser(description="Run prompt improvement loop")
    parser.add_argument(
        "--runs", type=int, default=20, help="Snapshots runs to analyze"
    )
    parser.add_argument(
        "--output",
        default=str(Path(__file__).parent.parent / "improvement_report.md"),
        help="Output markdown file path",
    )
    args = parser.parse_args()

    print(f"Step 1/3 — Analyzing last {args.runs} runs from quality_snapshots...")
    analysis = await analyze(n_runs=args.runs)

    if analysis.get("error"):
        print(f"Error: {analysis['error']}")
        sys.exit(1)

    print(
        f"  Found {analysis['run_count']} runs | regression rate: {analysis['regression_rate'] * 100:.1f}%"
    )
    print(
        f"  Top issue: {analysis['top_issues'][0]['category'] if analysis['top_issues'] else 'none'}"
    )

    print("Step 2/3 — Running PromptAnalyst...")
    prompt_files = _load_prompt_files()
    report = await run_prompt_analysis(
        run_id="improvement-loop",
        analysis_data=analysis,
        prompt_files=prompt_files,
    )
    print(
        f"  {len(report.suggestions)} suggestions generated | top issue: {report.top_issue}"
    )

    print(f"Step 3/3 — Writing report to {args.output}...")
    md = _render_markdown(report, analysis)
    Path(args.output).write_text(md, encoding="utf-8")
    print(f"  Done. Review {args.output} and apply suggestions with TDD.")


if __name__ == "__main__":
    asyncio.run(main())
