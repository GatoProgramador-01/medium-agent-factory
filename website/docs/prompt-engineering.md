---
id: prompt-engineering
title: Prompt Engineering
sidebar_label: Prompt Engineering
sidebar_position: 4
---

# Prompt Engineering

Prompts in Medium Agent Factory are versioned, tested against eval fixtures, and changed through a documented process. This page records the key design decisions and the most impactful fixes made during production operation.

## Versioning discipline

Every prompt template lives in `app/prompts/` as a standalone Python file with a version constant:

```python
# app/prompts/content_generation.py
PROMPT_VERSION = "v1.4.0"

SYSTEM = """
You are a technical writer producing Medium posts for senior software engineers...
"""
```

Version changes are tracked in `app/prompts/CHANGELOG.md`. A prompt is only bumped when an eval metric changes by >= 0.02 across a minimum 5-post sample. This prevents noise-driven churn.

## The BENCHMARK CLAIM RULE fix (v1.3.0 → v1.4.0)

### Problem

Starting from v1.3.0, the `fact_check` node was flagging `unattributed_claim HIGH` on a large fraction of drafts. Analysis of 20 flagged posts showed a consistent pattern: the `content_generation` prompt was producing benchmark numbers ("X% faster", "Y ms latency") with no attribution to the Tavily research corpus that had already been retrieved.

The structural checker caught these as hard failures, routing every affected draft back through the revision loop — adding latency and cost with no quality gain, since the revision prompt wasn't targeted enough to fix the root cause reliably.

### Root cause

The original `content_generation` system prompt contained:

```
Use specific numbers and statistics where possible to increase credibility.
```

Without a constraint on attribution, the LLM hallucinated plausible-sounding benchmarks rather than pulling from the provided research context.

### Fix applied (BENCHMARK CLAIM RULE)

The instruction was replaced with:

```
BENCHMARK CLAIM RULE: Every quantitative claim (percentages, latency figures,
benchmark scores, throughput numbers) MUST be directly attributable to the
research context provided in the user message. If the research context does
not contain a specific number, hedge with qualitative language
("significantly faster", "lower latency") or omit the claim entirely.
Never invent benchmark figures.
```

Additionally, the research context block was moved to the top of the user message, before the topic instruction, to increase its salience.

### Result

`unattributed_claim HIGH` rate dropped from 34% of drafts to under 3% across the next 20-post sample. Revision cycle count for affected posts dropped from an average of 4.1 to 1.3.

## The SPECIFICITY MANDATE (v1.2.0 → v1.3.0)

### Problem

G-Eval `depth` scores were consistently the lowest dimension (averaging 0.61 across 15 posts), with the judge critique repeating: "Post stays at surface level and does not explain the why behind design decisions."

### Fix applied (SPECIFICITY MANDATE)

Added to the `content_generation` system prompt:

```
SPECIFICITY MANDATE: For every tool, library, pattern, or architectural
decision mentioned, include at least one of:
  (a) a concrete code example (even if abbreviated)
  (b) the specific reason this approach was chosen over the alternative
  (c) a measurable outcome (latency, cost, error rate) with attribution

Surface-level mentions ("you can use X") without elaboration are not
acceptable in any section of the article.
```

### Result

`depth` score average rose from 0.61 to 0.79 over the next 10 posts. Overall `quality_score` average rose from 0.74 to 0.84.

## Revision loop prompts

When `quality_analysis` routes a draft back to `content_generation`, the state carries a structured critique object. The revision prompt assembles targeted instructions from Layer 1 failures and G-Eval dimension scores:

```python
def build_revision_prompt(state: GraphState) -> str:
    instructions = []

    # Layer 1 structural issues
    for issue in state.structural_issues:
        instructions.append(STRUCTURAL_INSTRUCTIONS[issue])

    # G-Eval dimension-specific guidance
    scores = state.latest_quality_scores
    if scores.depth < 0.75:
        instructions.append(DEPTH_REVISION_INSTRUCTION)
    if scores.hook < 0.70:
        instructions.append(HOOK_REVISION_INSTRUCTION)
    if scores.clarity < 0.70:
        instructions.append(CLARITY_REVISION_INSTRUCTION)
    if scores.actionability < 0.70:
        instructions.append(ACTIONABILITY_REVISION_INSTRUCTION)

    return REVISION_SYSTEM_PROMPT.format(
        original_draft=state.current_draft,
        critique=state.latest_critique,
        targeted_instructions="\n".join(f"- {i}" for i in instructions),
        cycle=state.revision_cycle,
    )
```

### Revision instruction library (selected entries)

```python
STRUCTURAL_INSTRUCTIONS = {
    "EXPAND": (
        "The article is below the 1,300-word minimum. Expand the most "
        "technically shallow section with a concrete example or a deeper "
        "explanation of the underlying mechanism. Do not pad with filler."
    ),
    "CITE_OR_HEDGE": (
        "Every quantitative claim must either cite a source from the research "
        "context or be replaced with qualitative language. Review every "
        "paragraph containing percentages, latency figures, or benchmark scores."
    ),
    "ADD_CTA": (
        "The final section must end with a clear call to action: a repo link, "
        "a next-step recommendation, or a question for the reader. Add one now."
    ),
}

DEPTH_REVISION_INSTRUCTION = (
    "The judge scored depth below 0.75. Identify the section with the most "
    "surface-level coverage and add either a code snippet, an architectural "
    "rationale, or a measured outcome with attribution."
)

HOOK_REVISION_INSTRUCTION = (
    "The judge scored hook below 0.70. Rewrite the opening paragraph. Lead "
    "with the problem the reader has right now, not with background context. "
    "The first sentence must create urgency or curiosity."
)
```

## Prompt change process

```
1. Identify issue from quality_snapshots data or repeated structural_checker failures
2. Hypothesize root cause — trace to specific prompt instruction (or its absence)
3. Write eval fixture: 5 posts that reproduce the failure
4. Draft prompt change
5. Run eval fixture against new prompt — score must improve >= 0.02 on target dimension
6. Update version constant and CHANGELOG.md
7. Commit with message: "prompt(content_generation): <dimension> fix — v1.x.y"
8. CI runs eval regression gate on the fixture set
```

No prompt change ships without a passing eval regression. This keeps prompt iteration from accidentally regressing a dimension that was previously passing.
