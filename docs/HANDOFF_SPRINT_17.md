# HANDOFF SPRINT 17 - medium-agent-factory

Date: 2026-06-29

Repo: `C:\Users\lanitaEmperadora\medium-agent-factory`

## Goal

Continue Sprint 17: make `/pipeline` effective for grounded long-form article generation about:

`GatoProgramador-01/claude-code-master-prompt`

The user wants to promote the repo in English on Medium using this multi-agent content pipeline.

## Current Runtime State

Docker Compose was successfully started from the existing `docker-compose.yml`:

```powershell
cd C:\Users\lanitaEmperadora\medium-agent-factory
docker compose up --build -d
```

Containers were up:

- `medium-factory-api` on `8000`
- `medium-factory-web` on `3000`

Backend health returned:

```json
{"status":"ok"}
```

Frontend opened at:

```text
http://localhost:3000/pipeline
```

## Why This Sprint Exists

The old `/pipeline` single-post flow had only one short input:

- `custom_topic`
- backend max length: 500 chars

That is not enough for grounded promotional articles. The article needs repo facts, case-study metrics, constraints, and anti-hallucination guidance. The pipeline should receive:

1. a short topic
2. a long grounding brief / source notes pack

## Implemented Changes

### Backend

File: `backend/app/routers/pipeline.py`

- `PipelineRequest` now includes:

```python
grounding_context: str = Field(default="", max_length=12000)
```

- `POST /pipeline/run` stores `grounding_context` in `pipeline_runs`.
- Async background `run_pipeline(...)` receives `grounding_context`.
- `POST /pipeline/run/sync` also passes `grounding_context`.

File: `backend/app/agents/orchestrator.py`

- `PipelineState` now includes:

```python
grounding_context: str
```

- `run_pipeline(...)` signature now includes:

```python
grounding_context: str = ""
```

- Initial state includes `grounding_context`.
- Inserted `grounding_context` into new pipeline run docs.
- `content_generation_node` now builds `combined_context`:

```text
USER-PROVIDED GROUNDING CONTEXT (treat as source notes, not prose to copy):
...

WEB RESEARCH CONTEXT (use only when relevant and cite URLs):
...
```

- `generate_initial_post(...)` receives `combined_context` as `trend_context`.

### Frontend

File: `frontend/src/lib/api.ts`

- `triggerPipeline(topic, groundingContext = "")` now sends:

```json
{
  "custom_topic": "...",
  "grounding_context": "..."
}
```

File: `frontend/src/app/pipeline/page.tsx`

- Added `groundingContext` state.
- Added `MASTER_PROMPT_TEMPLATE`.
- Single-post card now has:
  - existing `Topic` input
  - new `Grounding brief` textarea
  - `Master Prompt repo` button that loads the template
  - character counter: `0 / 12,000`
- `handleRun()` passes `topic` and `groundingContext`.

File: `frontend/src/app/pipeline/page.test.tsx`

Added tests:

- `triggerPipeline` now expected with `(topic, "")`
- renders grounding textarea
- calls `triggerPipeline(topic, groundingContext)`
- template button loads master prompt repo context

File: `backend/tests/test_pipeline_request.py`

Added backend contract tests for `PipelineRequest` accepting/rejecting `grounding_context`.

## Validation Run

Frontend focused test:

```powershell
cd C:\Users\lanitaEmperadora\medium-agent-factory\frontend
npm run test:unit -- pipeline/page.test.tsx --runInBand
```

Result:

- PASS
- 28 tests passed
- Warnings remain about React `act(...)` in existing SSE tests, but suite passes.

Backend focused test attempted:

```powershell
cd C:\Users\lanitaEmperadora\medium-agent-factory\backend
C:\Users\lanitaEmperadora\medium-agent-factory\backend\.venv\Scripts\python.exe -m pytest tests\test_pipeline_request.py -q
```

Result:

- Failed during import:

```text
ModuleNotFoundError: No module named 'slowapi'
```

Important: `.venv` is Python 3.14.2 even though `pyproject.toml` requires `>=3.11`. The project dependency `slowapi>=0.1.9` exists in `pyproject.toml`, but this venv does not have it installed. Claude Code should either:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest tests\test_pipeline_request.py -q
```

or run tests inside Docker where dependencies are installed.

## Existing Dirty Worktree Before This Sprint

Before Sprint 17 changes, worktree already had:

- `backend/app/agents/orchestrator.py` modified from Sprint 16
- `frontend/src/components/CostComparisonPanel.tsx` modified, unrelated
- `backend/tests/test_publication_recommendation.py` untracked

Do not revert those unless explicitly asked.

## Sprint 16 Warning Still Open

`backend/app/agents/orchestrator.py` has prior Sprint 16 work for:

- `recommended_publication`
- `publication_confidence`

Adversarial review found blockers:

1. `_compute_publication_recommendation` uses `.get()` on issues, but production issues are `QualityIssue` dataclasses.
2. Structural issues are often inside `quality_report.issues`, not `state["structural_check_issues"]`.
3. Recommendation fields may not be persisted to `posts`.

If continuing Sprint 16 too, fix this before claiming it is complete.

## Recommended Next Steps For Claude Code

1. Install backend deps in venv or use Docker for tests.
2. Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest tests\test_pipeline_request.py tests\test_publication_recommendation.py -q
```

3. Run frontend focused test again:

```powershell
cd frontend
npm run test:unit -- pipeline/page.test.tsx --runInBand
```

4. Rebuild/restart Compose so frontend/backend pick up code changes:

```powershell
cd C:\Users\lanitaEmperadora\medium-agent-factory
docker compose up --build -d
```

5. Open:

```text
http://localhost:3000/pipeline
```

6. Use:

Topic:

```text
Claude Code Master Prompt: the operating system behind production AI coding workflows
```

Click:

```text
Master Prompt repo
```

Then run the pipeline.

7. Watch:

```powershell
docker compose logs -f backend
docker compose logs -f frontend
```

8. Fetch generated post:

```powershell
GET http://localhost:8000/posts/{run_id}
```

## Quality Criteria

The generated post should:

- open with the HTTP 200 empty-body soft-block story
- use the actual pj-peru-scraper metrics
- explain why generic AI assistants fail without constraints
- position the repo as an engineering control plane, not prompt magic
- mention multi-agent workflow and lazy-loaded rules
- connect to medium-agent-factory as proof of the same philosophy
- avoid hype phrases listed in the template

