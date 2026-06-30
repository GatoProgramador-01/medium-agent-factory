# AGENTS

## Pipeline Nodes Table

Each row = one LangGraph node registered in `build_graph()`. "Can fail silently" = node returns `{}` on exception so the pipeline continues without the node's output.

| Node function | Agent module | Model (default) | Input state keys read | Output state keys written | Can fail silently |
|--------------|-------------|-----------------|----------------------|--------------------------|-------------------|
| `repo_analysis_node` | `repo_analyzer.py` | none (deterministic) | `repo_path`, `run_id` | `evidence_brief`, `completed_steps`, `errors` | Yes — returns `evidence_brief=None` on any exception |
| `research_node` | `web_researcher.py` | Haiku (worker) | `custom_topic`, `run_id` | `trend_context`, `completed_steps` | Yes — returns `trend_context=""` on exception |
| `topic_refinement_node` | `topic_refiner.py` | Sonnet (supervisor) | `custom_topic`, `trend_context`, `grounding_context`, `evidence_brief`, `run_id` | `refined_topic`, `topic_brief`, `completed_steps` | Yes — falls back to `refined_topic=custom_topic` |
| `content_generation_node` | `content_generator.py` | Haiku (worker) | `refined_topic`, `custom_topic`, `grounding_context`, `trend_context`, `topic_brief`, `series_context`, `run_id` | `post`, `revision_count` (0), `completed_steps`, `errors` | No — returns `errors` dict on failure |
| `intro_ab_testing_node` | `intro_ab_tester.py` | Haiku (worker) | `post`, `topic_brief`, `run_id` | `post` (updated content), `intro_variants`, `completed_steps` | Yes — returns `{}` on exception |
| `series_coherence_node` | `series_coherence_checker.py` | Haiku (worker) | `post`, `series_context`, `topic_brief`, `series_position`, `run_id` | `post` (optional revised body), `series_coherence_score`, `completed_steps` | Yes — no-op for standalone posts; `{}` on exception |
| `title_optimization_node` | `title_optimizer.py` | Haiku (worker) | `post`, `topic_brief`, `run_id` | `post` (updated title), `title_variants`, `completed_steps` | Yes — returns `{}` on exception |
| `fact_check_node` | `fact_checker.py` | Haiku (worker) | `post`, `run_id` | `post` (hyperlinks injected), `fact_check_issues`, `fact_check_results`, `completed_steps` | Yes — returns empty lists on exception; no-op when `fact_check_enabled=False` |
| `quality_analysis_node` | `quality_analyzer.py` + `structural_checker.py` + `read_ratio_analyzer.py` | Haiku (worker) | `post`, `revision_count`, `fact_check_issues`, `run_id` | `quality_report`, `quality_history`, `completed_steps`, `errors` | No — returns `errors` dict on failure |
| `content_revision_node` | `content_generator.py` | Haiku (worker); Sonnet upgrade path available via config | `post`, `quality_report`, `revision_count`, `quality_history`, `run_id` | `post`, `revision_count` (incremented), `completed_steps`, `errors` | No — returns `errors` dict on failure |
| `close_optimization_node` | `close_optimizer.py` | Haiku (worker) | `post`, `topic_brief`, `run_id` | `draft_content` | Yes — returns `{}` on exception |
| `image_description_enrichment_node` | `image_description_enricher.py` | Haiku (worker) | `post`, `topic_brief`, `run_id` | `post` (enriched placeholders), `image_enrichment_changes`, `completed_steps` | Yes — returns `{}` on exception |
| `format_node` | `formatter.py` | Haiku (worker) | `post`, `fact_check_results`, `revision_count`, `run_id` | `post` (formatted content), `pull_quote`, `format_changes`, `completed_steps`, `errors` | No — returns `errors` dict on failure |
| `finalize_node` | `orchestrator.py` (inline) + `post_processor.py` + `exemplar_store.py` + `publication_matcher.py` | none (DB writes) + Haiku for publication_matcher | `post`, `quality_report`, `fact_check_results`, `quality_history`, `revision_count`, `topic_brief`, `run_id` | `completed_steps`, `recommended_publication`, `publication_confidence` | Partial — exemplar save and publication match wrapped in try/except; DB write is not |

---

## Support Modules Table

Modules that are not registered as LangGraph nodes but are called by nodes or agent modules.

| Module | Purpose | Called by |
|--------|---------|-----------|
| `llm_factory.py` | Single `get_llm(role)` / `get_model_name(role)` factory; priority: local > DeepSeek > Anthropic | every agent module |
| `base.py` | `AgentTokenTracker` — LangChain callback; records tokens_in/out, cost_usd, duration_ms to MongoDB `agent_runs` | every agent module (passed as `callbacks=[tracker]`) |
| `logger.py` | `log_step()` — async; writes structured entries to MongoDB `agent_logs` for SSE frontend streaming | `orchestrator.py` (every node) |
| `retry.py` | `with_langchain_retry(chain)` and `@retryable_llm_call` decorator; handles 429/500/connection errors | `content_generator.py`, `quality_analyzer.py`, `topic_refiner.py`, `series_planner.py`, `web_researcher.py` |
| `structural_checker.py` | Deterministic regex checks: `paragraph_length`, `heading_cadence`, `intro_length`, `word_count`, `ai_pattern` (forbidden phrases), `image_missing` — zero LLM calls | `quality_analysis_node` |
| `read_ratio_analyzer.py` | Formula-based read ratio prediction: base 0.82 minus deductions; single LLM call for hook quality score only | `quality_analysis_node` |
| `exemplar_store.py` | MongoDB `exemplars` collection: `save_exemplar()` when score ≥ 0.95; `find_exemplar()` by keyword overlap; `format_exemplar_injection()` for few-shot prompt injection | `finalize_node` (save), `content_generation_node` (find+format) |
| `post_processor.py` | Deterministic string transforms: `inject_captions()` adds placeholder to image blocks missing `\| caption:`; `merge_sources_sections()` deduplicates `## Sources` + `## References` | `finalize_node` |
| `repo_analyzer.py` | `RepoAnalyzer.analyze(path)` — reads local repo, extracts stack/commands/architecture_hints/metrics/evidence; returns `EvidenceBrief`; no LLM calls | `repo_analysis_node` |
| `prompt_analyst.py` | Translates `quality_snapshots` frequency data into prompt edit suggestions; part of improvement loop (not in main pipeline) | offline tooling / `analyze_quality_snapshots.py` |

---

## Prompt Files Table

All prompts in `backend/prompts/`. Loaded via `load_prompt()` / `load_template()` from `app/prompt_loader.py`. No prompt text is hardcoded in agent `.py` files.

| Agent module | Prompt file(s) | Template variables |
|-------------|---------------|--------------------|
| `content_generator.py` (initial) | `content_generator_system.txt`, `content_generator_human_initial.txt` | `{topic}`, `{trend_context}`, `{tags}`, `{audience}`, `{series_context}`, `{exemplar_section}` |
| `content_generator.py` (revision) | `content_reviser_system.txt`, `content_generator_human_revision.txt` | `{title}`, `{content}`, `{word_count}`, `{intro_word_count}`, `{score}`, `{min_score}`, `{gate_failures_list}`, `{read_ratio_section}`, `{strengths_list}` |
| `quality_analyzer.py` | `quality_analyzer_system.txt`, `quality_analyzer_human.txt` | `{title}`, `{content}` |
| `formatter.py` | `formatter_system.txt`, `formatter_human.txt` | `{title}`, `{content}`, `{long_paragraphs}` |
| `topic_refiner.py` | `topic_refiner_system.txt`, `topic_refiner_human.txt` | `{topic}`, `{research_results}`, `{evidence_brief}`, `{grounding_context}` |
| `title_optimizer.py` | `title_optimizer_system.txt`, `title_optimizer_human.txt` | `{original_title}`, `{refined_angle}`, `{hook_sentence}`, `{post_excerpt}` |
| `intro_ab_tester.py` | `intro_ab_tester_system.txt`, `intro_ab_tester_human.txt` | `{title}`, `{content}`, `{refined_angle}` |
| `series_coherence_checker.py` | `series_coherence_checker_system.txt`, `series_coherence_checker_human.txt` | `{title}`, `{content}`, `{series_context}`, `{series_position}`, `{refined_angle}` |
| `close_optimizer.py` | `close_optimizer_system.txt`, `close_optimizer_human.txt` | `{content}`, `{refined_angle}` |
| `image_description_enricher.py` | `image_description_enricher_system.txt`, `image_description_enricher_human.txt` | `{title}`, `{content}`, `{image_suggestions}`, `{refined_angle}` |
| `publication_matcher.py` | `publication_matcher_system.txt`, `publication_matcher_human.txt` | `{title}`, `{tags}`, `{quality_score}`, `{medium_boost_eligible}`, `{refined_angle}` |
| `series_planner.py` | `series_planner_system.txt`, `series_planner_human.txt` | `{theme}`, `{context}` |
| `fact_checker.py` (claim extraction) | `claim_extractor_system.txt` | `{content}` |
| `prompt_analyst.py` | `prompt_analyst_system.txt`, `prompt_analyst_human.txt` | `{snapshot_data}`, `{prompt_contents}` |

---

## How to Add a New Agent

1. **Create agent file** — `backend/app/agents/<name>.py`. Use `get_llm(role)` + `.with_structured_output(PydanticModel)`. Never instantiate `ChatAnthropic` directly. Include unicode-normalizer fallback in every `str→list` field_validator.

2. **Add import** — in `orchestrator.py`, import the agent's public async function at the top of the file alongside the other agent imports.

3. **Add PipelineState key** — add the new output field(s) to `PipelineState(TypedDict)` in `orchestrator.py`. Use `Annotated[list[T], operator.add]` for any list that should accumulate across nodes rather than overwrite.

4. **Add prompt files** — create `backend/prompts/<name>_system.txt` and `backend/prompts/<name>_human.txt`. Target 1,700 words in the generated output (verified in tests). Use `{template_var}` syntax — `load_template()` does `.format(**kwargs)`.

5. **Wire in `build_graph()`** — add `g.add_node("<name>", <node_function>)` and the appropriate `g.add_edge(...)` or `g.add_conditional_edges(...)` call. Do not modify any other node's wiring.

6. **Write RED tests first** — create `backend/tests/test_<name>.py`. Tests must fail before implementation. Use unique test class names. No `__init__.py` in `tests/`. Mock the LLM with `AsyncMock` returning a structured Pydantic model; never hit a real API in unit tests.

7. **Add eval dataset** — create `backend/evals/datasets/<name>_evals.jsonl` with 20+ cases covering pass/fail scenarios. Layer 1 (score direction) and Layer 2 (batch regression) run in CI. Mark slow LLM-as-judge tests with `@pytest.mark.eval_deep`.

8. **Register in CI** — confirm `pytest backend/tests/test_<name>.py` is covered by the existing `pytest backend/` sweep in `.github/workflows/`. If the agent introduces a new external dependency (new API key, new env var), add it to the CI secrets and to `backend/app/config.py` with a safe default.
