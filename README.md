# medium-agent-factory

[![CI](https://github.com/GatoProgramador-01/medium-agent-factory/actions/workflows/ci.yml/badge.svg)](https://github.com/GatoProgramador-01/medium-agent-factory/actions/workflows/ci.yml)
[![Eval Gate](https://github.com/GatoProgramador-01/medium-agent-factory/actions/workflows/eval.yml/badge.svg)](https://github.com/GatoProgramador-01/medium-agent-factory/actions/workflows/eval.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Node 22](https://img.shields.io/badge/node-22-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

A production-grade LLM content pipeline built on **LangGraph** + **FastAPI** + **Next.js**. Give it a topic — it writes, scores, and revises a full article using a multi-agent loop, streaming every decision live to the browser.

> **The meta story:** the posts in `/posts` were written by this pipeline about this pipeline. All three scored 0.82 on the first attempt with zero revisions.

---

## System Architecture

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#111111', 'primaryTextColor': '#d4f0d4', 'primaryBorderColor': '#4ade80', 'lineColor': '#4a5a4a', 'secondaryColor': '#161616', 'tertiaryColor': '#0b0b0b', 'clusterBkg': '#0d0d0d', 'clusterBorder': '#1f1f1f', 'edgeLabelBackground': '#0b0b0b', 'titleColor': '#4ade80', 'nodeTextColor': '#d4f0d4'}}}%%
graph TB
    subgraph Browser["🌐  Browser · Next.js 15"]
        UI_PIPE["Pipeline Page\ntrigger + SSE terminal"]
        UI_POST["Posts Page\nquality scores + copy"]
        UI_ANA["Analytics Page\ncost & token charts"]
    end

    subgraph Backend["⚙️  FastAPI · BackgroundTasks"]
        API_RUN["POST /pipeline/run"]
        API_SSE["GET /runs/{id}/stream\nSSE · text/event-stream"]
        API_POST["GET /posts"]
        API_ANA["GET /analytics/*"]
    end

    subgraph LangGraph["🤖  LangGraph Orchestrator · StateGraph"]
        CG["ContentGenerator\ngenerate draft / revise"]
        QA["QualityAnalyzer\nscore 0 – 1"]
        ROUTE{"route_after_quality()\nscore ≥ 0.75 or revisions ≥ 2?"}
        FIN["Finalize\nstatus = approved"]
    end

    subgraph AI["🧠  AI Layer"]
        HAIKU["Claude Haiku 4.5\nWorker · $0.25 / M tokens"]
        SONNET["Claude Sonnet 4.6\nSupervisor · $3 / M tokens\n(last resort only)"]
        OLLAMA["Ollama · llama3.2\nFree · local · USE_LOCAL_LLM=true"]
    end

    subgraph Storage["💾  MongoDB"]
        POSTS[("posts")]
        RUNS[("pipeline_runs")]
        AGENT[("agent_runs\ntokens · cost · latency")]
        LOGS[("agent_logs\nSSE source")]
    end

    UI_PIPE -->|"POST /pipeline/run {topic}"| API_RUN
    API_RUN -->|"run_id (immediate)"| UI_PIPE
    API_RUN -->|"BackgroundTask"| CG

    CG -->|"initial draft"| HAIKU
    QA -->|"score + issues"| HAIKU
    CG -.->|"revision_count = 2\nlast resort"| SONNET
    CG & QA -.->|"USE_LOCAL_LLM=true"| OLLAMA

    CG --> ROUTE
    QA --> ROUTE
    ROUTE -->|"pass"| FIN
    ROUTE -->|"fail"| CG

    FIN --> POSTS & RUNS
    CG & QA -->|"log_step()"| LOGS

    UI_PIPE -->|"EventSource"| API_SSE
    API_SSE -->|"tails agent_logs\ndata: {...}\\n\\n"| UI_PIPE

    UI_POST -->|"GET /posts"| API_POST
    API_POST --> POSTS
    UI_ANA -->|"GET /analytics/*"| API_ANA
    API_ANA --> AGENT

    HAIKU & SONNET -->|"AgentTokenTracker\ncallback"| AGENT
```

---

## LangGraph Pipeline — State Machine

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#111111', 'primaryTextColor': '#d4f0d4', 'primaryBorderColor': '#4ade80', 'lineColor': '#4a5a4a', 'secondaryColor': '#161616', 'edgeLabelBackground': '#0b0b0b'}}}%%
stateDiagram-v2
    direction TB

    [*] --> content_generation : pipeline.ainvoke(initial_state)

    state content_generation {
        [*] --> generate_draft
        generate_draft : generate_draft\nClaude Haiku · load_template(human_initial)\nreturns GeneratedPost
        generate_draft --> [*]
    }

    content_generation --> quality_analysis : post written to state

    state quality_analysis {
        [*] --> score_post
        score_post : score_post\nClaude Haiku · load_template(human_score)\nreturns QualityReport — score · issues · revision_prompt
        score_post --> [*]
    }

    quality_analysis --> routing : quality_report written to state

    state routing <<choice>>

    routing --> finalize     : score ≥ 0.75\nOR revision_count ≥ max_revision_cycles (2)
    routing --> revision     : score < 0.75\nAND revision_count < 2

    state revision {
        [*] --> rewrite
        rewrite : rewrite\nrev 1 → Claude Haiku\nrev 2 → Claude Sonnet (escalation)\napplies revision_prompt from QualityReport
        rewrite --> [*]
    }

    revision --> quality_analysis : revised post written to state\nrevision_count += 1

    state finalize {
        [*] --> approve
        approve : approve\ndb.posts.update status = approved\nlog_step(Pipeline completed)
        approve --> [*]
    }

    finalize --> [*] : ✓ done · post approved
```

---

## Request Lifecycle — One Pipeline Run

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#111111', 'primaryTextColor': '#d4f0d4', 'primaryBorderColor': '#4ade80', 'lineColor': '#4a5a4a', 'actorBkg': '#111111', 'actorBorder': '#4ade80', 'actorTextColor': '#d4f0d4', 'noteBkgColor': '#161616', 'noteBorderColor': '#1f1f1f', 'noteTextColor': '#4a5a4a', 'signalColor': '#4a5a4a', 'signalTextColor': '#d4f0d4', 'activationBkgColor': '#161616', 'activationBorderColor': '#4ade80'}}}%%
sequenceDiagram
    autonumber
    actor Browser
    participant API       as FastAPI
    participant Graph     as LangGraph
    participant CG        as ContentGenerator
    participant QA        as QualityAnalyzer
    participant Claude    as Claude Haiku
    participant MongoDB

    Browser->>API: POST /pipeline/run { topic }
    API-->>Browser: 200 { run_id } — returns immediately

    Browser->>API: GET /pipeline/runs/{id}/stream
    Note over Browser,API: EventSource opened — SSE connection live

    activate Graph
    API->>Graph: pipeline.ainvoke(initial_state) [BackgroundTask]

    Graph->>API: log_step("Pipeline started")
    API-->>Browser: data: { step: orchestrator, level: info }

    Graph->>CG: content_generation_node(state)
    activate CG
    CG->>Claude: ainvoke([system_prompt, human_initial])
    Claude-->>CG: GeneratedPost { title, content, tags }
    CG->>MongoDB: upsert post { status: draft }
    CG->>API: log_step("Draft generated — ~1800 words")
    API-->>Browser: data: { step: content_generator, level: success }
    CG-->>Graph: { post: GeneratedPost, revision_count: 0 }
    deactivate CG

    Graph->>QA: quality_analysis_node(state)
    activate QA
    QA->>Claude: ainvoke([system_prompt, human_score])
    Claude-->>QA: { score: 0.82, issues: [...], revision_prompt }
    QA->>MongoDB: update post quality_report
    QA->>API: log_step("Quality score: 0.82 — Passed threshold")
    API-->>Browser: data: { step: quality_analyzer, level: success }
    QA-->>Graph: { quality_report: QualityReport }
    deactivate QA

    Note over Graph: route_after_quality()<br/>score 0.82 ≥ 0.75 → finalize

    Graph->>MongoDB: update post { status: approved }
    Graph->>API: log_step("Post approved. Final quality score: 0.82")
    API-->>Browser: data: { step: orchestrator, level: success }
    API-->>Browser: data: { __done__: true }
    deactivate Graph

    Note over Browser: EventSource.close()<br/>phase = done

    Browser->>API: GET /posts/{run_id}
    API->>MongoDB: find post
    MongoDB-->>API: Post + QualityReport
    API-->>Browser: 200 Post
    Note over Browser: ResultCard rendered<br/>score 82/100 · read ratio 71%
```

---

## Cost Model

The pipeline uses the cheapest model that can do the job and escalates only when needed.

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#111111', 'primaryTextColor': '#d4f0d4', 'primaryBorderColor': '#4ade80', 'lineColor': '#4a5a4a', 'edgeLabelBackground': '#0b0b0b'}}}%%
graph LR
    START(["topic"]):::start

    subgraph Attempt_0 ["Attempt 1 — always Haiku"]
        CG0["ContentGenerator\nClaude Haiku · ~$0.003"]
        QA0["QualityAnalyzer\nClaude Haiku · ~$0.002"]
        PASS0{score ≥ 0.75?}
        CG0 --> QA0 --> PASS0
    end

    subgraph Attempt_1 ["Attempt 2 — Haiku revision"]
        CG1["ContentGenerator\nClaude Haiku · ~$0.003"]
        QA1["QualityAnalyzer\nClaude Haiku · ~$0.002"]
        PASS1{score ≥ 0.75?}
        CG1 --> QA1 --> PASS1
    end

    subgraph Attempt_2 ["Attempt 3 — Sonnet escalation"]
        CG2["ContentGenerator\nClaude Sonnet · ~$0.025"]
        QA2["QualityAnalyzer\nClaude Haiku · ~$0.002"]
        CG2 --> QA2
    end

    DONE(["✓ approved"]):::done

    START --> CG0
    PASS0 -->|"✓ pass\n~$0.005 total"| DONE
    PASS0 -->|"✗ fail"| CG1
    PASS1 -->|"✓ pass\n~$0.012 total"| DONE
    PASS1 -->|"✗ fail"| CG2
    QA2 --> DONE

    NOTE["~$0.035 worst case\nvs ~$0.050 always-Sonnet"]:::note

    classDef start fill:#001a0d,stroke:#4ade80,color:#4ade80
    classDef done fill:#001a0d,stroke:#4ade80,color:#4ade80
    classDef note fill:#0b0b0b,stroke:#1f1f1f,color:#4a5a4a
```

---

## CI/CD Pipeline

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': {'primaryColor': '#111111', 'primaryTextColor': '#d4f0d4', 'primaryBorderColor': '#4ade80', 'lineColor': '#4a5a4a', 'clusterBkg': '#0d0d0d', 'clusterBorder': '#1f1f1f', 'edgeLabelBackground': '#0b0b0b'}}}%%
graph TD
    PR(["Pull Request\nor push to master"])

    subgraph CI ["ci.yml — every PR + push"]
        direction LR
        BE["Backend CI\nruff · black · mypy\npytest tests/ --timeout=30"]
        FE["Frontend CI\ntsc · eslint · jest --ci\nnext build"]
        E2E["Frontend E2E\nPlaywright · Chromium\nSSE mocked via page.route()"]
        DOCK["Docker Build\nboth images — push: false\nPR only"]

        BE & FE --> E2E
        BE & FE --> DOCK
    end

    subgraph EVAL ["eval.yml — PR touching agents/ or prompts/"]
        GATE["Eval Gate\npytest evals/ -m 'not eval_deep'\nLayer 1 + 2 · ~$0.04 · ~2 min\nblocks merge if accuracy < 75%"]
    end

    subgraph DEPLOY ["deploy.yml — push to master only"]
        direction LR
        BUILD["Build & Push Images\nGHCR backend:sha+latest\nGHCR frontend:sha+latest"]
        RW["Deploy Backend\nrailway up --service backend --detach"]
        VL["Deploy Frontend\nvercel build --prod\nvercel deploy --prebuilt --prod"]
        SUM["Step Summary\n| Service | Status |\n|---------|--------|"]

        BUILD --> RW & VL --> SUM
    end

    PR --> CI
    PR --> EVAL
    PR -->|"merge to master"| DEPLOY

    classDef trigger fill:#001a0d,stroke:#4ade80,color:#4ade80
    class PR trigger
```

---

## LLMOps Patterns

Each pattern was built, broken, debugged, and verified with tests before moving on.

| Week | Pattern | Production problem it solves |
|---|---|---|
| 1 | **3-layer eval pipeline** | Prompt regressions reach production silently — eval gate blocks them before merge |
| 2 | **Ollama local switch** | API bills during development — `USE_LOCAL_LLM=true` routes everything to a free local model |
| 2 | **SSE streaming** | Polling creates 2× DB round trips per second — SSE uses one persistent connection |
| 3 | **Prompt versioning** | Prompts buried in code can't be reviewed or rolled back — `.txt` files in git with eval gate trigger |
| 4 | **LangChain retry + tenacity** | Anthropic 529 overloaded errors fail silently — automatic backoff with jitter |

---

## Stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph with revision loop) |
| LLM — worker | Claude Haiku 4.5 ($0.25/M tokens) |
| LLM — supervisor | Claude Sonnet 4.6 ($3/M tokens, last resort only) |
| Local LLM | Ollama (`USE_LOCAL_LLM=true` — zero cost, drop-in swap) |
| Agent framework | LangChain · `.with_structured_output(PydanticModel)` |
| Observability | LangSmith tracing · per-agent token + cost tracking |
| Backend | FastAPI · Motor (async MongoDB) |
| Frontend | Next.js 15 · React 19 · TypeScript · Tailwind CSS · Recharts |
| Tests | pytest (31 unit) · Jest + RTL (15 unit) · Playwright (9 E2E) |
| CI/CD | GitHub Actions · Railway · Vercel · GHCR |
| Database | MongoDB 7 (Docker local) · MongoDB Atlas M0 (production) |

---

## Quick Start

### Prerequisites

- Python 3.11+ and Node.js 22+
- Docker (for local MongoDB) or MongoDB on port 27017
- [Anthropic API key](https://console.anthropic.com)

### 1. Clone and configure

```bash
git clone https://github.com/GatoProgramador-01/medium-agent-factory
cd medium-agent-factory
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY at minimum
```

### 2. Start MongoDB

```bash
docker run -d -p 27017:27017 --name mongo mongo:7
```

### 3. Backend

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows
# source .venv/bin/activate                      # macOS / Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload
# → http://localhost:8000/docs
```

### 4. Frontend

```bash
cd frontend
npm install && npm run dev
# → http://localhost:3000
```

### 5. Run the pipeline

Open `http://localhost:3000/pipeline`, type a topic, press Enter.

```bash
# Or via curl
curl -X POST http://localhost:8000/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{"custom_topic": "how I cut LLM costs 10x with Ollama"}'
```

---

## Docker Compose

```bash
# Full stack — backend + frontend (MongoDB must be running)
docker compose up

# With Ollama — zero Anthropic API cost
docker compose --profile local-llm up
docker compose exec ollama ollama pull llama3.2
# Set USE_LOCAL_LLM=true in .env and restart backend
```

---

## Development

### Backend

```bash
cd backend

black .                                   # format
ruff check .                              # lint
mypy app/                                 # type check (strict)
pytest tests/ -v --timeout=30            # unit tests (31 tests, no LLM calls)
pytest evals/ -v -m "not eval_deep"      # eval gate — Layer 1 + 2
pytest evals/ -v -m eval_deep            # nightly LLM-as-judge
python -m evals.langsmith_eval "v1"      # visual diff in LangSmith
```

### Frontend

```bash
cd frontend

npx tsc --noEmit                          # type check
npm run lint                              # ESLint
npm run test:unit                         # Jest + RTL (15 tests, mocked API)
npm run test:e2e                          # Playwright — requires built app running
npm run build                             # production build (catches runtime errors)
```

---

## Eval Pipeline

Quality regressions are caught in CI before they merge.

| Layer | What it checks | Cost | When |
|---|---|---|---|
| Score direction | Good posts ≥ 0.70, bad posts ≤ 0.55 per case | ~$0.002/case | Every PR |
| Cohort mean | Score distribution doesn't drift from baseline | ~$0.04 total | Every PR |
| LLM-as-judge | Revision prompts are specific and actionable | ~$0.005/case | Nightly only |

The CI path filter only triggers eval when these paths change:

```
backend/app/agents/**    backend/prompts/**
backend/evals/**         backend/pyproject.toml
```

---

## Deployment

Production stack: **Railway** (backend Docker) + **Vercel** (Next.js) + **MongoDB Atlas** (free M0).

### Required GitHub secrets

| Secret | Source |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `LANGCHAIN_API_KEY` | smith.langchain.com |
| `RAILWAY_TOKEN` | railway.app → Account Settings → Tokens |
| `VERCEL_TOKEN` | vercel.com → Account Settings → Tokens |

### Required GitHub variables

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | Your Railway service URL |
| `BACKEND_URL` | Your Railway service URL |
| `FRONTEND_URL` | Your Vercel project URL |
| `VERCEL_ORG_ID` | Vercel → Account Settings → General |
| `VERCEL_PROJECT_ID` | Vercel → Project Settings → General |

Once all secrets and variables are set, every push to `master` deploys automatically.

---

## Project Structure

```
medium-agent-factory/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── orchestrator.py      ← LangGraph StateGraph — nodes, edges, routing
│   │   │   ├── content_generator.py ← Claude writer — cheapest-first model strategy
│   │   │   ├── quality_analyzer.py  ← Claude scorer — structured QualityReport output
│   │   │   ├── llm_factory.py       ← get_llm(role) — Anthropic ↔ Ollama via env var
│   │   │   ├── retry.py             ← with_langchain_retry() + @retryable_llm_call
│   │   │   └── base.py              ← AgentTokenTracker (cost + latency → MongoDB)
│   │   ├── api/
│   │   │   ├── pipeline.py          ← trigger + SSE stream endpoint
│   │   │   ├── posts.py
│   │   │   └── analytics.py
│   │   ├── prompt_loader.py         ← loads prompts/ at startup, fail-fast cache
│   │   └── config.py                ← all settings via pydantic-settings
│   ├── prompts/                     ← all LLM prompts as .txt files — git-versioned
│   │   ├── quality_analyzer_system.txt
│   │   ├── quality_analyzer_human.txt
│   │   ├── content_generator_system.txt
│   │   ├── content_generator_human_initial.txt
│   │   └── content_generator_human_revision.txt
│   ├── evals/
│   │   ├── datasets/quality_analyzer.jsonl  ← curated test cases (good + bad posts)
│   │   ├── conftest.py              ← dataset fixtures + MongoDB mock (autouse)
│   │   ├── test_quality_analyzer.py ← Layer 1 + 2 + 3 eval tests
│   │   └── langsmith_eval.py        ← visual experiment runner for LangSmith UI
│   ├── tests/                       ← 31 unit tests — no LLM calls, no MongoDB
│   │   ├── test_routing.py          ← route_after_quality pure function
│   │   ├── test_validators.py       ← JSON coerce + curly quote normalization
│   │   ├── test_prompt_loader.py    ← fail-fast + template variable injection
│   │   └── test_llm_factory.py      ← model name selection + USE_LOCAL_LLM
│   └── Dockerfile
├── frontend/
│   └── src/app/
│       ├── pipeline/
│       │   ├── page.tsx             ← SSE EventSource live log terminal
│       │   └── page.test.tsx        ← 6 RTL unit tests (fake EventSource)
│       ├── posts/
│       │   ├── page.tsx             ← post list with ScoreBar + copy_markdown
│       │   └── page.test.tsx        ← 9 RTL unit tests (mocked api module)
│       └── analytics/page.tsx       ← per-agent token + cost Recharts
├── docs/
│   └── langgraph_explained.md       ← deep architecture walkthrough
├── .github/workflows/
│   ├── ci.yml                       ← lint · typecheck · jest · playwright · docker
│   ├── eval.yml                     ← eval gate (path-filtered, PR only)
│   └── deploy.yml                   ← GHCR → Railway + Vercel (master push)
├── docker-compose.yml               ← backend + frontend + Ollama (opt-in profile)
└── .env.example
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | **required** | Anthropic API key |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | `medium_agent_factory` | Database name |
| `SUPERVISOR_MODEL` | `claude-sonnet-4-6` | Model used on the final revision attempt |
| `WORKER_MODEL` | `claude-haiku-4-5-20251001` | Model for initial generation and first revision |
| `MIN_QUALITY_SCORE` | `0.75` | Minimum score to approve without revision |
| `MAX_REVISION_CYCLES` | `2` | Max revision attempts before forced approval |
| `USE_LOCAL_LLM` | `false` | Route entire pipeline to Ollama |
| `LOCAL_LLM_MODEL` | `llama3.2` | Ollama model name |
| `LOCAL_LLM_BASE_URL` | `http://ollama:11434` | Ollama endpoint (`localhost:11434` outside Docker) |
| `LANGCHAIN_TRACING_V2` | `false` | Enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | LangSmith API key |
| `LANGCHAIN_PROJECT` | `medium-agent-factory` | LangSmith project name |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/pipeline/run` | Trigger async pipeline, returns `run_id` immediately |
| `POST` | `/pipeline/run/sync` | Trigger blocking pipeline, waits for completion |
| `GET` | `/pipeline/runs` | List all pipeline runs |
| `GET` | `/pipeline/runs/{id}` | Get run status and metadata |
| `GET` | `/pipeline/runs/{id}/logs` | Get all log entries for a run |
| `GET` | `/pipeline/runs/{id}/stream` | SSE live log stream (closes with `__done__` event) |
| `GET` | `/posts` | List posts, optional `?status=` filter |
| `GET` | `/posts/{run_id}` | Get post with full quality report |
| `GET` | `/analytics/token-usage` | Per-agent token and cost breakdown |
| `GET` | `/analytics/summary` | Aggregate pipeline statistics |

Full interactive docs: `http://localhost:8000/docs`

---

## The Posts This Pipeline Wrote About Itself

After all four LLMOps weeks were complete, the pipeline was given topics about what it had just built:

| Title | Score | Revisions |
|---|---|---|
| How I Built a Self-Evaluating LLM Pipeline That Blocks Bad AI Writing | 0.82 | 0 |
| LLMOps Skills That Will Actually Get You Hired in 2025 | 0.82 | 0 |
| One Environment Variable Killed My LLM API Bills | 0.82 | 0 |

All three passed on the first attempt. The QualityAnalyzer's consistent feedback across all three: section headers were slightly too formulaic. The pipeline correctly diagnosed its own writing patterns.

---

## Roadmap

- [ ] Production deploy (Railway + Vercel + MongoDB Atlas)
- [ ] Redis response cache — skip API call for identical prompts
- [ ] Prompt A/B testing — run two versions against the eval set, promote the winner
- [ ] LangGraph human-in-the-loop — pause before approval for manual review
- [ ] LangGraph checkpointing (PostgresSaver) — resume interrupted runs

---

## License

MIT — see [LICENSE](LICENSE).
