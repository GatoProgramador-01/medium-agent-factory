"""
LangSmith visual eval — run manually or nightly (not in every PR).

What this gives you (visible at smith.langchain.com):
  - Side-by-side comparison of runs across prompt versions
  - Per-case score timeline (detect drift over time)
  - Dataset versioning and filtering
  - Eval experiment history

Setup:
  1. Set LANGCHAIN_API_KEY in .env
  2. Set LANGCHAIN_TRACING_V2=true
  3. Run: python -m evals.langsmith_eval

First run uploads the dataset to LangSmith.
Subsequent runs compare against the baseline experiment.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from langsmith import Client, evaluate
from langsmith.schemas import Example, Run

from app.agents.quality_analyzer import run_quality_analysis


# ── Dataset management ─────────────────────────────────────────────────────────

DATASET_NAME = "quality-analyzer-v1"
_JSONL_PATH  = Path(__file__).parent / "datasets" / "quality_analyzer.jsonl"


def _load_local_dataset() -> list[dict]:
    return [json.loads(l) for l in _JSONL_PATH.read_text().splitlines() if l.strip()]


def upload_dataset_if_missing(client: Client) -> str:
    """Upload the JSONL dataset to LangSmith once. Returns dataset id."""
    existing = [d for d in client.list_datasets() if d.name == DATASET_NAME]
    if existing:
        print(f"Dataset '{DATASET_NAME}' already exists — skipping upload.")
        return str(existing[0].id)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="QualityAnalyzer eval — 20 posts (good/bad/medium) with expected score bands",
    )

    cases = _load_local_dataset()
    client.create_examples(
        inputs=[{"title": c["title"], "content": c["content"]} for c in cases],
        outputs=[{
            "label":     c["label"],
            "min_score": c.get("min_score"),
            "max_score": c.get("max_score"),
        } for c in cases],
        dataset_id=dataset.id,
    )
    print(f"Uploaded {len(cases)} examples to '{DATASET_NAME}'.")
    return str(dataset.id)


# ── Target function — what LangSmith will call for each example ───────────────

async def run_analyzer(inputs: dict[str, Any]) -> dict[str, Any]:
    """Wraps run_quality_analysis for the LangSmith evaluate() harness."""
    report = await run_quality_analysis(
        run_id="langsmith-eval",
        title=inputs["title"],
        content=inputs["content"],
    )
    return {
        "score":               report.score,
        "read_ratio":          report.read_ratio_prediction,
        "issue_count":         len(report.issues),
        "revision_prompt":     report.revision_prompt,
        "top_issues":          [i.suggestion for i in report.issues[:3]],
    }


def run_analyzer_sync(inputs: dict[str, Any]) -> dict[str, Any]:
    """Sync wrapper required by langsmith.evaluate()."""
    return asyncio.run(run_analyzer(inputs))


# ── Evaluators — each returns a score between 0 and 1 ────────────────────────

def score_direction_evaluator(run: Run, example: Example) -> dict[str, Any]:
    """
    Checks whether the analyzer scored the post in the expected direction.
    Returns 1.0 for correct direction, 0.0 for wrong.
    """
    actual_score  = run.outputs.get("score", 0)
    label         = example.outputs.get("label")
    min_score     = example.outputs.get("min_score")
    max_score     = example.outputs.get("max_score")

    if label == "good" and min_score is not None:
        correct = actual_score >= min_score
    elif label == "bad" and max_score is not None:
        correct = actual_score <= max_score
    else:  # medium — just check it's in range
        lo = example.outputs.get("min_score", 0.0)
        hi = example.outputs.get("max_score", 1.0)
        correct = lo <= actual_score <= hi

    return {
        "key":   "score_direction",
        "score": 1.0 if correct else 0.0,
        "comment": (
            f"{label} post: score={actual_score:.2f} "
            f"(expected {'≥'+str(min_score) if min_score else '≤'+str(max_score)})"
        ),
    }


def issue_count_evaluator(run: Run, example: Example) -> dict[str, Any]:
    """Bad posts should surface more issues than good posts."""
    count = run.outputs.get("issue_count", 0)
    label = example.outputs.get("label")

    if label == "bad":
        score = min(count / 3, 1.0)   # 3+ issues → full score
    elif label == "good":
        score = 1.0 if count <= 2 else 0.5
    else:
        score = 1.0

    return {"key": "issue_count_alignment", "score": score}


# ── Run eval ───────────────────────────────────────────────────────────────────

def run_eval(experiment_prefix: str = "manual") -> None:
    api_key = os.getenv("LANGCHAIN_API_KEY")
    if not api_key:
        raise RuntimeError("Set LANGCHAIN_API_KEY in .env before running LangSmith evals.")

    client = Client()
    upload_dataset_if_missing(client)

    print(f"\nRunning eval experiment '{experiment_prefix}' on dataset '{DATASET_NAME}'...")
    results = evaluate(
        run_analyzer_sync,
        data=DATASET_NAME,
        evaluators=[score_direction_evaluator, issue_count_evaluator],
        experiment_prefix=experiment_prefix,
        max_concurrency=3,
    )

    stats = results.stats          # type: ignore[attr-defined]
    direction_mean = stats.get("score_direction", {}).get("mean", 0)
    print(f"\n── Results ──────────────────────────────────────")
    print(f"  score_direction mean : {direction_mean:.2f}  (pass threshold: 0.75)")
    print(f"  View in LangSmith    : https://smith.langchain.com")
    print(f"─────────────────────────────────────────────────\n")

    if direction_mean < 0.75:
        raise SystemExit(
            f"Eval failed: score_direction mean {direction_mean:.2f} < 0.75. "
            "Check LangSmith for per-case breakdowns."
        )


if __name__ == "__main__":
    import sys
    prefix = sys.argv[1] if len(sys.argv) > 1 else "manual"
    run_eval(experiment_prefix=prefix)
