# LangGraph & Multi-Agent Architecture — How This Project Works

> Read this in VS Code with Markdown Preview (`Ctrl+Shift+V`). Every code reference links to a real file.

---

## 1. What is LangGraph? (Like You're 5)

Imagine you're running a kitchen.

- The **kitchen** is LangGraph.
- The **recipe steps** are nodes.
- The **dish being cooked** is the state — it gets passed from station to station, and each station adds something to it.
- The **sous chef who decides** "does this need more salt?" is a conditional edge — a routing function.

LangGraph is a library that lets you build **pipelines where each step is an LLM call**, and the pipeline can **loop back** if the result isn't good enough. It's not a chain (chain = always goes A→B→C in order). It's a **graph** — meaning it can go A→B→A again, or B→C or B→D depending on what happened at B.

**Why not just write a `for` loop?**

You could. But LangGraph gives you:
- A shared **State object** every step reads from and writes to (no passing 10 arguments)
- **Conditional routing** declared in one place, not scattered in `if/else`
- **Checkpointing** — if something crashes, you resume from the last checkpoint (we don't use this yet, but it's there)
- A **visual graph** you can render (more on this below)

---

## 2. The Four Core Concepts

### 2a. State — the shared clipboard

```python
# backend/app/agents/orchestrator.py:40
class PipelineState(TypedDict):
    run_id: str
    custom_topic: str

    post: GeneratedPost | None          # the article being written
    quality_report: QualityReport | None # the analysis of that article
    revision_count: int                  # how many times we've revised
    errors: Annotated[list[str], operator.add]          # accumulates errors
    completed_steps: Annotated[list[str], operator.add] # accumulates step names
```

`PipelineState` is a **dictionary every node reads from and writes into**.

Think of it as a whiteboard in the middle of the room. Every agent walks up, reads what's there, does their work, and writes their result back. They never talk to each other directly — they only talk through the whiteboard.

`Annotated[list[str], operator.add]` means "when two nodes both write to `errors`, merge them by concatenating" instead of overwriting. This is how LangGraph handles **reducer functions** — you declare how to merge partial updates.

---

### 2b. Nodes — the workers

A node is **just an async function** that takes `PipelineState` and returns a **partial update** (a dict with only the fields it changed).

```python
# backend/app/agents/orchestrator.py:53
async def content_generation_node(state: PipelineState) -> dict[str, Any]:
    post = await generate_initial_post(...)
    return {"post": post, "revision_count": 0, "completed_steps": ["content_generation"]}
    #       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    #       Only the fields this node touched. LangGraph merges this into the full state.
```

The node doesn't return the whole state — it returns a **patch**. LangGraph merges the patch into the existing state automatically.

We have 4 nodes:

| Node | Function | File |
|------|----------|------|
| `content_generation` | Writes the first draft of the post | `orchestrator.py:53` |
| `quality_analysis` | Scores the draft (0.0–1.0) and finds issues | `orchestrator.py:84` |
| `revision` | Rewrites the draft based on the quality report | `orchestrator.py:143` |
| `finalize` | Marks the post as approved and saves to DB | `orchestrator.py:195` |

---

### 2c. Edges — the connections

A **normal edge** is unconditional: "always go from A to B."

```python
# backend/app/agents/orchestrator.py:231
g.add_edge(START, "content_generation")          # always start here
g.add_edge("content_generation", "quality_analysis")  # always analyze after generating
g.add_edge("revision", "quality_analysis")       # always re-analyze after revising
g.add_edge("finalize", END)                      # always end after finalizing
```

A **conditional edge** runs a function and picks the next node based on the result:

```python
# backend/app/agents/orchestrator.py:233
g.add_conditional_edges(
    "quality_analysis",       # from this node...
    route_after_quality,      # call this function to decide...
    {"finalize": "finalize",  # if it returns "finalize", go to finalize
     "revision": "revision"}  # if it returns "revision", go to revision
)
```

And here's the routing function:

```python
# backend/app/agents/orchestrator.py:212
def route_after_quality(state: PipelineState) -> str:
    report = state.get("quality_report")
    revisions = state.get("revision_count", 0)

    if not report or report.score >= settings.min_quality_score:  # score >= 0.75
        return "finalize"    # good enough, approve it
    if revisions >= settings.max_revision_cycles:                  # tried 2x already
        return "finalize"    # give up gracefully, approve anyway
    return "revision"        # needs work, send back for rewrite
```

This is the **brain of the pipeline**. A simple function. No magic.

---

### 2d. The Graph — wiring it all together

```python
# backend/app/agents/orchestrator.py:224
def build_graph() -> Any:
    g = StateGraph(PipelineState)       # "this graph uses PipelineState as its whiteboard"

    g.add_node("content_generation", content_generation_node)
    g.add_node("quality_analysis",   quality_analysis_node)
    g.add_node("revision",           content_revision_node)
    g.add_node("finalize",           finalize_node)

    g.add_edge(START, "content_generation")
    g.add_edge("content_generation", "quality_analysis")
    g.add_conditional_edges("quality_analysis", route_after_quality,
                            {"finalize": "finalize", "revision": "revision"})
    g.add_edge("revision", "quality_analysis")
    g.add_edge("finalize", END)

    return g.compile()   # validates the graph, returns an executable object
```

`g.compile()` produces a `CompiledGraph` object. You run it like this:

```python
# backend/app/agents/orchestrator.py:276
final_state = await pipeline.ainvoke(initial_state)
```

One call. LangGraph handles the node execution order, state merging, and routing internally.

---

## 3. The Full Pipeline — Visual Flow

```
POST /pipeline/run  →  run_pipeline()  →  pipeline.ainvoke(initial_state)
                                                       │
                                                       ▼
                                             ┌─────────────────────┐
                                             │   START             │
                                             └──────────┬──────────┘
                                                        │ always
                                                        ▼
                                             ┌─────────────────────┐
                                             │  content_generation │  Claude Haiku
                                             │                     │  generate_initial_post()
                                             │  Writes to state:   │  load_template("content_generator_human_initial")
                                             │  • post             │
                                             │  • revision_count=0 │
                                             └──────────┬──────────┘
                                                        │ always
                                                        ▼
                                             ┌─────────────────────┐
                                         ┌──►  quality_analysis   │  Claude Haiku
                                         │   │                     │  run_quality_analysis()
                                         │   │  Writes to state:   │  load_template("quality_analyzer_human")
                                         │   │  • quality_report   │
                                         │   └──────────┬──────────┘
                                         │              │
                                         │    route_after_quality()
                                         │    ┌─────────┴─────────┐
                                         │    │                   │
                                         │  score < 0.75        score >= 0.75
                                         │  AND revisions < 2   OR revisions >= 2
                                         │    │                   │
                                         │    ▼                   ▼
                                         │  ┌──────────────┐   ┌──────────┐
                                         │  │   revision   │   │ finalize │
                                         │  │              │   │          │  marks post
                                         │  │  rev 1→Haiku │   │  status= │  as APPROVED
                                         │  │  rev 2→Sonnet│   │  approved│
                                         │  │              │   └────┬─────┘
                                         │  │  Writes to:  │        │ always
                                         │  │  • post      │        ▼
                                         │  │  • rev_count │      END
                                         │  └──────┬───────┘
                                         │         │ always (loops back!)
                                         └─────────┘
```

**The loop is the key insight.** `revision → quality_analysis → revision → quality_analysis` can repeat up to `max_revision_cycles` (default: 2) times. After that, `route_after_quality` forces it to `finalize` regardless of score.

---

## 4. The Three Agents — What Each One Does

### Agent 1: ContentGeneratorAgent

**File:** `backend/app/agents/content_generator.py`  
**Model:** Claude Haiku (cheap) → Claude Sonnet (only if Haiku fails twice)  
**Job:** Write a complete 1500–2000 word article in Markdown

It has two modes:

```
generate_initial_post()  →  uses content_generator_human_initial.txt
                             Variables: {topic}, {trend_context}, {tags}, {audience}

revise_post()            →  uses content_generator_human_revision.txt
                             Variables: {title}, {content}, {score}, {revision_prompt}, {issues_list}
```

The model escalation logic:

```python
# backend/app/agents/content_generator.py:65
def _pick_role(revision_number: int) -> str:
    return "worker" if revision_number < 2 else "supervisor"
    #       Haiku (cheap)                       Sonnet (2× more expensive, better quality)
```

**Cost strategy:**
- Initial draft: Haiku → ~$0.005
- Haiku revision: Haiku → ~$0.007 more
- Sonnet revision (last resort only): Sonnet → ~$0.020 more
- Always Sonnet: ~$0.050

If the initial draft passes quality (score ≥ 0.75), you spend $0.005 total. That's 10× cheaper than always using Sonnet.

---

### Agent 2: QualityAnalyzerAgent

**File:** `backend/app/agents/quality_analyzer.py`  
**Model:** Always Claude Haiku  
**Job:** Read the draft and return a structured quality report

The output is a Pydantic model, not free text:

```python
# backend/app/agents/quality_analyzer.py:36
class _AnalysisOutput(BaseModel):
    score: float                      # 0.0 to 1.0 — the overall grade
    read_ratio_prediction: float      # estimated % of readers who finish
    issues: list[_Issue]             # specific problems, ordered by impact
    strengths: list[str]             # what's working well
    revision_prompt: str             # exact rewrite instruction for ContentGenerator
```

The `revision_prompt` field is what makes this multi-agent: the QualityAnalyzer **writes instructions** that the ContentGenerator **reads and follows**. They communicate through the state object, not by calling each other directly.

`.with_structured_output(_AnalysisOutput)` forces Claude to return valid JSON matching this schema every time. No regex parsing, no brittle string splitting.

---

### Agent 3: Orchestrator (the graph itself)

**File:** `backend/app/agents/orchestrator.py`  
**Model:** None — it doesn't call an LLM  
**Job:** Coordinate the other two agents by managing state and routing

The orchestrator IS the LangGraph `StateGraph`. It doesn't contain business logic — it just:
1. Calls ContentGenerator
2. Calls QualityAnalyzer
3. Decides "pass or revise?" via `route_after_quality()`
4. Calls ContentGenerator again if needed (with QualityAnalyzer's `revision_prompt`)
5. Finalizes

This is the **Workflow/Graph pattern** — one of the standard multi-agent patterns (more below).

---

## 5. Multi-Agent Patterns — The Big Picture

There are several ways to build multi-agent systems. We're using one specific pattern. Here's how all of them compare:

### Pattern 1: Sequential Chain (what we built)

```
Agent A → Agent B → Agent A → Agent B → done
```

Each agent hands off to the next. They share state. One orchestrates the routing.

**We use this.** ContentGenerator → QualityAnalyzer → maybe loop → finalize.

**Good for:** Pipelines with clear stages and a quality gate. Deterministic flow.

---

### Pattern 2: Supervisor + Sub-agents

```
                 Supervisor (LLM)
                /        |        \
           AgentA      AgentB    AgentC
```

A supervisor LLM **decides which specialist to call** by reading the task. No fixed routing — the LLM reasons about it.

**We don't use this** because our routing is deterministic (`score >= 0.75`). Using an LLM to make this decision would add cost and latency for no benefit.

**Good for:** Tasks where you don't know upfront which tools/agents will be needed.

---

### Pattern 3: Map-Reduce

```
Task → [AgentA, AgentA, AgentA, AgentA] → Reducer → Result
         (parallel, same agent, different inputs)
```

Fan out N identical agents in parallel, aggregate results.

**Example use case:** Analyze 20 articles simultaneously, then aggregate findings.

---

### Pattern 4: Swarm

No fixed hierarchy. Agents hand off to each other based on context. Think of a group chat where anyone can respond.

**Good for:** Exploration, research. Hard to predict cost and latency.

---

## 6. Supporting Infrastructure — The Three Helpers

Every agent in the project is built on three shared building blocks.

### 6a. LLM Factory — `backend/app/agents/llm_factory.py`

```python
def get_llm(role: str = "worker", **kwargs) -> BaseChatModel:
    if settings.use_local_llm:                    # USE_LOCAL_LLM=true in .env
        return ChatOllama(model="llama3.2", ...)  # free, runs on your machine
    model = supervisor_model if role == "supervisor" else worker_model
    return ChatAnthropic(model=model, ...)        # paid API
```

**Why:** Every agent calls `get_llm("worker")` instead of `ChatAnthropic(model="haiku")`. If you set `USE_LOCAL_LLM=true`, the entire pipeline switches to Ollama — zero code changes in agents. This is the **Open/Closed Principle** applied to model selection.

---

### 6b. Retry Layer — `backend/app/agents/retry.py`

```python
def with_langchain_retry(chain, max_attempts=3):
    return chain.with_retry(
        retry_if_exception_type=(ConnectionError, TimeoutError, ...),
        wait_exponential_jitter=True,   # waits 2s, then 4s, then 8s + random jitter
        stop_after_attempt=max_attempts,
    )
```

Usage in every agent:

```python
llm = with_langchain_retry(
    get_llm("worker", callbacks=[tracker]).with_structured_output(GeneratedPost)
)
```

`with_langchain_retry` wraps the entire `chain` (LLM + output parser). If Claude's API returns a 529 (overloaded) or times out, it retries automatically. The agent code never sees the failure.

---

### 6c. Token Tracker — `backend/app/agents/base.py`

```python
class AgentTokenTracker(AsyncCallbackHandler):
    async def on_llm_end(self, response: LLMResult, ...) -> None:
        # Runs automatically after every LLM call, captures:
        tokens_in, tokens_out = ...
        cost_usd = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
        await db.agent_runs.insert_one(record.to_doc())
```

**Every agent** passes a `tracker` as a callback:

```python
tracker = AgentTokenTracker(agent_name="quality_analyzer", run_id=run_id, model=model_name)
llm = get_llm("worker", callbacks=[tracker])
```

LangChain calls `on_llm_end` automatically after every completion. The tracker saves to MongoDB. The Analytics page in the frontend reads from `db.agent_runs` to show cost per run.

---

## 7. Prompt Versioning — `backend/prompts/`

```
backend/prompts/
├── quality_analyzer_system.txt          ← the LLM's persona and rules
├── quality_analyzer_human.txt           ← the template with {title} and {content}
├── content_generator_system.txt         ← writing style instructions
├── content_generator_human_initial.txt  ← {topic}, {audience}, {tags}
└── content_generator_human_revision.txt ← {title}, {content}, {score}, {issues_list}
```

These are plain text files committed to git. When you change a prompt, `git diff` shows exactly what changed. The eval CI gate (`eval.yml`) re-runs automatically when any file in `prompts/` changes, so you can't accidentally regress quality by tweaking a prompt without the test catching it.

```python
# backend/app/prompt_loader.py
_CACHE = {p.stem: p.read_text() for p in PROMPTS_DIR.glob("*.txt")}  # loaded once at startup

def load_prompt(name: str) -> str: ...          # raw text → SystemMessage
def load_template(name: str) -> _PromptTemplate: # .format(**vars) → HumanMessage
```

**Why files instead of strings in code?**
- `git blame` on a `.txt` file shows who changed the prompt and when
- Non-engineers can edit prompts without touching Python
- The eval CI path filter triggers on `prompts/**` changes — prompt changes are tested automatically

---

## 8. End-to-End: What Happens When You Click "Run Pipeline"

```
1. Browser → POST /pipeline/run  {topic: "how I built this in 4 weeks"}

2. FastAPI creates a pipeline_run document in MongoDB:
   {run_id: "abc-123", status: "running", ...}
   Then calls run_pipeline() as a BackgroundTask (returns immediately to browser)

3. Browser connects to GET /pipeline/runs/abc-123/stream (SSE)
   EventSource in React starts receiving events

4. LangGraph starts: pipeline.ainvoke(initial_state)

   Node 1 — content_generation:
     → ChatAnthropic(haiku).ainvoke([system_prompt, human_prompt])
     → Claude writes a ~1800 word draft
     → AgentTokenTracker records ~800 tokens_in, ~1200 tokens_out to agent_runs
     → State now has: post = GeneratedPost(title=..., content=...)
     → log_step() writes to agent_logs → SSE stream picks it up → browser shows it live

   Node 2 — quality_analysis:
     → ChatAnthropic(haiku).ainvoke([system_prompt, post_content])
     → Claude returns _AnalysisOutput (structured JSON, forced by .with_structured_output)
     → State now has: quality_report = QualityReport(score=0.82, issues=[...], revision_prompt=...)

   route_after_quality():
     → 0.82 >= 0.75 → returns "finalize"

   Node 3 — finalize:
     → db.posts.update_one(status="approved")
     → log_step("Post approved. Final quality score: 0.82")

5. LangGraph returns final_state

6. run_pipeline() writes {status: "completed"} to pipeline_runs
   log_step("Pipeline completed successfully.")

7. SSE stream sends:  data: {"__done__": true}
   EventSource in React closes, phase transitions to "done"

8. User navigates to /posts, sees the approved post with score bar at 82%
```

---

## 9. What "Multi-Agent" Actually Means Here

In this project, "multi-agent" doesn't mean multiple LLMs talking to each other in real time. It means:

**Two specialized LLMs with different roles**, coordinated by a graph:

| Role | Model | Knows about | Doesn't know about |
|------|-------|------------|-------------------|
| ContentGenerator | Haiku/Sonnet | Writing, storytelling, Markdown structure | Quality scoring |
| QualityAnalyzer | Haiku | AI pattern detection, readability, human voice | How to write |

The QualityAnalyzer's `revision_prompt` field is how they "communicate":

```
QualityAnalyzer writes:
  "Remove the generic opening 'In today's world...'. Start with a specific moment.
   Replace 3 instances of 'leverage' with concrete verbs. Add one personal anecdote
   about your actual experience."

ContentGenerator reads this in the next loop iteration and applies it.
```

They never call each other. They pass notes through the state. The graph decides when each one runs.

This is clean, testable, and cheap. Each agent is independently unit-testable with a mocked LLM. The routing logic (`route_after_quality`) is pure Python with no LLM — also independently testable.

---

## 10. Where to Look in the Code

| Question | File | Line |
|----------|------|------|
| "How is the graph defined?" | `orchestrator.py` | 224 |
| "What's in the state?" | `orchestrator.py` | 40 |
| "How does routing work?" | `orchestrator.py` | 212 |
| "How does the LLM get called?" | `content_generator.py` | 126 |
| "How does scoring work?" | `quality_analyzer.py` | 75 |
| "How is model selection done?" | `llm_factory.py` | 1 |
| "How are retries handled?" | `retry.py` | 1 |
| "How is cost tracked?" | `base.py` | 36 |
| "Where are the prompts?" | `backend/prompts/*.txt` | — |
| "How does SSE streaming work?" | `backend/app/api/pipeline.py` | stream endpoint |
