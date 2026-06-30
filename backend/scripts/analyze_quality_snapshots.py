#!/usr/bin/env python3
"""CLI wrapper for quality_snapshots analysis.

Usage:
    python scripts/analyze_quality_snapshots.py
    python scripts/analyze_quality_snapshots.py --runs 20
    python scripts/analyze_quality_snapshots.py --json-only
"""
import argparse
import asyncio
import json
import sys

from app.scripts.analyze_quality_snapshots import analyze


async def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze quality_snapshots collection")
    parser.add_argument("--runs", type=int, default=20, help="Number of recent runs to analyze")
    parser.add_argument("--json-only", action="store_true", help="Output JSON only, no summary")
    args = parser.parse_args()

    result = await analyze(args.runs)
    print(json.dumps(result, indent=2))

    if args.json_only or result.get("error"):
        return

    print("\n" + "=" * 60, file=sys.stderr)
    print(f"QUALITY ANALYSIS — {result['run_count']} runs | {result['analyzed_at'][:10]}", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(
        f"Regression rate:  {result['regression_rate'] * 100:.1f}% ({result['regression_events']}/{result['transition_count']} transitions)",
        file=sys.stderr,
    )
    wc = result["word_count"]
    print(
        f"Word count:       avg={wc['avg']} min={wc['min']} max={wc['max']} | under-1300: {wc['pct_under_1300']}%",
        file=sys.stderr,
    )
    print("\nGate failures:", file=sys.stderr)
    for k, v in result["gate_failure_types"].items():
        print(f"  {k}: {v}", file=sys.stderr)
    print("\nTop 5 issue categories:", file=sys.stderr)
    for issue in result["top_issues"][:5]:
        print(
            f"  {issue['category']}: total={issue['total']} HIGH={issue['high_count']} sticky={issue['sticky_count']}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
