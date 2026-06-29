# Codex Handoff — Sprint 18

**Project:** medium-agent-factory  
**Path:** `C:\Users\lanitaEmperadora\medium-agent-factory`  
**Branch:** master  
**Stack:** FastAPI + LangGraph + Motor (MongoDB) + Next.js 15 + Docker Compose

## Current pipeline state (after Sprint 17)

```
research → topic_refiner → content_generation → title_optimizer → fact_check
→ quality_analysis → [revision loop ×6] → close_optimization → format → finalize
→ publication_matcher (non-blocking in finalize)
```

**Test count:** 461 passing, 16 pre-existing failures (evals need real API key, e2e need live server)

---

## Sprint 18 — 3 agents to implement (TDD, all parallel)

All agents follow the same pattern as existing ones. See `backend/app/agents/topic_refiner.py` as the canonical reference implementation.

---

### Agent 1: IntroABTester

**File:** `backend/app/agents/intro_ab_tester.py`  
**Prompts:** `backend/prompts/intro_ab_tester_system.txt`, `backend/prompts/intro_ab_tester_human.txt`  
**Tests:** `backend/tests/test_intro_ab_tester.py`

**What it does:** Generates 2 alternative intro variants (first 100 words only), scores each using the read_ratio hook rubric, returns the stronger intro. Replaces the generator's intro in `draft_content` before `title_optimization_node` runs.

**Where in pipeline:** After `content_generation_node`, before `title_optimization_node`.  
New edge: `content_generation → intro_ab_test → title_optimization`

**Pydantic model:**
```python
class IntroVariant(BaseModel):
    intro_text: str          # 60-110 words
    hook_score: float        # 0.0-1.0 (uses read_ratio rubric internally)
    hook_type: str           # "outcome_first" | "failure" | "number" | "scene"
    rationale: str           # one sentence

class IntroABResult(BaseModel):
    variant_a: IntroVariant
    variant_b: IntroVariant
    winner: str              # "a" or "b"
    winning_intro: str       # copy of the winner's intro_text
    original_kept: bool      # True if original was better than both variants
```

**Async function signature:**
```python
async def run_intro_ab_test(
    run_id: str,
    original_intro: str,    # first 110 words of draft_content
    original_title: str,
    refined_angle: str = "",
) -> IntroABResult:
```

**Node in orchestrator:**
```python
async def intro_ab_test_node(state: PipelineState) -> dict:
    # extracts intro (before first ## or --- separator)
    # calls run_intro_ab_test
    # if not result.original_kept: replaces intro in draft_content
    # returns {"draft_content": updated_content}
    # on exception: returns {} (keep original)
```

**System prompt key points:**
- Uses the same hook rubric as quality_analyzer (outcome-first, failure, scene, number)
- Variant A: rewrites sentence 1 to be outcome-first ("My bill dropped from X to Y when...")
- Variant B: rewrites sentence 1 to open with a scene or named failure  
- If both variants score lower than original: set original_kept=True
- Model: worker (Haiku) — fast, one LLM call

**New PipelineState key:** `intro_ab_result: dict | None`

**Tests (5 minimum):**
- returns result with winner
- raises on None
- original kept when both variants worse
- node replaces intro in draft_content
- node falls back on exception

---

### Agent 2: ImageDescriptionEnricher

**File:** `backend/app/agents/image_description_enricher.py`  
**Prompts:** `backend/prompts/image_description_enricher_system.txt`, `backend/prompts/image_description_enricher_human.txt`  
**Tests:** `backend/tests/test_image_description_enricher.py`

**What it does:** Scans `[IMAGE: description | alt: alt text]` placeholders in the content. For each placeholder, reads the 50 words before and after it (context window) and rewrites the description + alt text to be specific to that section's content. Returns the full content with enriched placeholders.

**Where in pipeline:** After `close_optimization_node`, before `format_node`.  
New edge: `close_optimization → image_enrichment → format`

**Pydantic model:**
```python
class EnrichedImage(BaseModel):
    original: str       # the original [IMAGE: ...] placeholder
    enriched: str       # the new [IMAGE: ...] placeholder
    position: int       # word index where image appears

class ImageEnrichmentResult(BaseModel):
    enriched_images: list[EnrichedImage]
    updated_content: str    # full content with all placeholders replaced
```

**Async function signature:**
```python
async def run_image_enrichment(
    run_id: str,
    content: str,
    post_topic: str,
) -> ImageEnrichmentResult:
```

**Implementation note:** Use regex `r'\[IMAGE:.*?\]'` to find all placeholders. For each, extract 50-word window. Send ALL images in one LLM call (not one per image) — include all contexts in a single structured prompt. This keeps cost to one Haiku call regardless of image count.

**Node in orchestrator:**
```python
async def image_enrichment_node(state: PipelineState) -> dict:
    # calls run_image_enrichment with draft_content
    # returns {"draft_content": result.updated_content}
    # on exception: returns {} (keep original placeholders)
```

**System prompt key points:**
- Each image description must reference something specific from the surrounding text (a number, a named tool, a code pattern)
- Alt text must describe what is visually shown (10-15 words), not restate the caption
- WRONG: `[IMAGE: chart showing performance | alt: Performance chart]`
- RIGHT: `[IMAGE: bar chart comparing DeepSeek $0.27 vs Claude $3.00 per MTok input, April 2024 | alt: Side-by-side cost comparison bar chart, DeepSeek 11x cheaper than Claude Sonnet for input tokens]`

**New PipelineState key:** none needed (draft_content already exists)

**Tests (5 minimum):**
- returns enriched content with replaced placeholders
- handles content with no images (returns unchanged)
- all images processed in single LLM call
- node replaces draft_content
- node falls back on exception

---

### Agent 3: SeriesCoherenceChecker

**File:** `backend/app/agents/series_coherence_checker.py`  
**Prompts:** `backend/prompts/series_coherence_checker_system.txt`, `backend/prompts/series_coherence_checker_human.txt`  
**Tests:** `backend/tests/test_series_coherence_checker.py`

**What it does:** For series posts ONLY (when `state["series_id"]` is set), checks the current post against siblings for: consistent terminology, correct "Part N of M" references, hook that references the right outcome from the previous post. Returns issues as QualityIssue list — injected into the quality_report before gate check.

**Where in pipeline:** Conditional node. Skip if `state["series_id"]` is None.  
Runs after `fact_check_node`, before `quality_analysis_node`.  
New edge: `fact_check → series_coherence_check → quality_analysis`

**Where to get sibling posts:** Query MongoDB `posts` collection for `series_id == state["series_id"]`, get title + first 200 words of each sibling.

**Pydantic model:**
```python
class CoherenceIssue(BaseModel):
    category: str       # always "series_coherence"
    severity: str       # "HIGH" or "MEDIUM"
    location: str       # "intro" | "heading: <text>" | "section: <text>"
    suggestion: str

class SeriesCoherenceResult(BaseModel):
    is_coherent: bool
    issues: list[CoherenceIssue]
    terminology_conflicts: list[str]    # terms used differently across posts
    missing_callbacks: list[str]        # things promised in prev post not addressed
```

**Async function signature:**
```python
async def run_series_coherence_check(
    run_id: str,
    current_post_content: str,
    current_post_position: int,         # 1-indexed position in series
    sibling_summaries: list[dict],      # [{"position": 1, "title": "...", "intro": "first 200 words"}]
    series_title: str,
) -> SeriesCoherenceResult:
```

**Node in orchestrator:**
```python
async def series_coherence_node(state: PipelineState) -> dict:
    if not state.get("series_id"):
        return {}   # skip for standalone posts
    # query db for siblings
    # call run_series_coherence_check
    # append issues to state["fact_check_results"] or a new "coherence_issues" key
    # on exception: return {}
```

**Route:**  
Use a conditional edge from `fact_check`:
```python
def route_after_fact_check(state):
    if state.get("series_id"):
        return "series_coherence"
    return "quality_analysis"

graph.add_conditional_edges("fact_check", route_after_fact_check, {
    "series_coherence": "series_coherence",
    "quality_analysis": "quality_analysis",
})
graph.add_edge("series_coherence", "quality_analysis")
```

**System prompt key points:**
- Check terminology: if post 1 calls it "token budget" and post 3 calls it "context limit" → flag as conflict
- Check callbacks: if post 1 says "in the next post, I'll show the exact numbers" → post 2 must include those numbers
- Check position references: "Part 2 of 3" must match actual series length
- Model: worker (Haiku) — quick coherence scan

**New PipelineState key:** `coherence_issues: list[dict] | None`

**Tests (6 minimum):**
- returns coherent result for consistent series
- detects terminology conflict
- detects missing callback
- node skips when series_id is None
- node falls back on exception
- route_after_fact_check returns correct branch

---

## How to run tests after implementing

```bash
cd C:\Users\lanitaEmperadora\medium-agent-factory\backend

# Individual suites
python -m pytest tests/test_intro_ab_tester.py -v
python -m pytest tests/test_image_description_enricher.py -v
python -m pytest tests/test_series_coherence_checker.py -v

# Full suite (expect 16 pre-existing failures)
python -m pytest --tb=short -q
```

## Reference files (read these before implementing)

- Canonical agent pattern: `backend/app/agents/topic_refiner.py`
- Canonical node pattern: `backend/app/agents/orchestrator.py` — search for `title_optimization_node`
- Canonical test pattern: `backend/tests/test_title_optimizer.py`
- PipelineState TypedDict: `backend/app/agents/orchestrator.py` line ~67-120
- Graph wiring: `backend/app/agents/orchestrator.py` — search for `build_graph`

## After Sprint 18

1. Run `docker compose up --build` to verify full stack compiles
2. Test the pipeline end-to-end with topic: "DeepSeek V3 vs Claude cost optimization"
3. Run `python scripts/promote_latest_post.py` to add the DeepSeek series post as exemplar
4. Run `python scripts/run_improvement_loop.py` after 3+ runs to generate prompt suggestions

## Session log

Full session summary at: `C:\Users\lanitaEmperadora\medium-agent-factory\SESSION_LOG.md`
