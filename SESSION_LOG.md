# Session Log — 2026-06-28

## Sprints completed this session

### Sprint 13 — Quality System Fixes
- **structural_checker.py**: word count severity fixed — 1000-1299 range was LOW, now HIGH (two bands: <700 "critically short", 700-1299 "below gate threshold")
- **quality_analyzer.py**: added `_STRUCTURAL_CATEGORIES` filter — LLM output can no longer inject duplicate word_count/paragraph_length/heading_cadence/intro_length/image_missing issues
- **quality_analyzer_system.txt**: added structural prohibition section, CoT scoring discipline, scoring anchors per axis, tighter revision_prompt instructions
- **content_generator_system.txt**: added structural plan Steps 1-4, most common failure modes section, concession placement instruction
- **content_reviser_system.txt**: added expansion math, regression check phrases, structural math checkbox
- **Google-style docstrings**: added to 5 agent files — structural_checker (13 functions), quality_analyzer (2), content_generator (4), exemplar_store (8), fact_checker (10)
- **finalize_node**: confirmed save_exemplar already present at lines 747-767
- **promote_latest_post.py**: new script in backend/scripts/ for manual exemplar promotion
- Tests: 51 new tests, all passing

### Sprint 14 — New Agents + Smart Escalation
- **prompt_analyst.py**: new agent that translates quality_snapshots frequency data into targeted prompt edit suggestions (PromptSuggestion + PromptAnalysisReport Pydantic models)
- **prompt_analyst_system.txt + prompt_analyst_human.txt**: new prompts for the analyst agent
- **analyze_quality_snapshots.py**: new script in backend/scripts/ that queries MongoDB for last N runs and produces structured JSON (regression rate, issue frequency, word count distribution, gate failure types, sticky issues)
- **Docstrings Sprint 2**: added to orchestrator.py (6 key node functions), read_ratio_analyzer.py (2), base.py (4), llm_factory.py (2)
- **_pick_role() escalation**: already implemented — escalates to Sonnet when score within 0.06 of min_score OR has HIGH ai_pattern issue (not just revision_number >= 2)
- **Prompt improvements confirmed**: formatter (anti-rewrite guarantee), series_planner (uniqueness mandate, specific hook_seed), claim_extractor (exclusion list for first-person claims)
- Tests: 13 new tests for revision escalation, 7 for quality snapshots, 4 for prompt analyst

### Sprint 15 — Improvement Loop + API
- **run_improvement_loop.py**: end-to-end CLI script — analyze snapshots → run prompt_analyst → write markdown report
- **POST /pipeline/improve-prompts**: new FastAPI endpoint wrapping the full improvement loop; returns JSON with suggestions
- **human templates confirmed**: content_generator_human_initial.txt (structural plan checkbox, inline citations checkbox, exemplar guidance), content_generator_human_revision.txt (expansion math, expansion math checkbox)
- **test_prompt_analyst.py**: mock wiring fixed (with_langchain_retry no-op + mock_chain.ainvoke = AsyncMock)
- **test_analyze_quality_snapshots.py**: import path fixed (app.scripts → scripts)
- Tests: 9 for improve endpoint, 2 for improvement loop

## Test counts (end of session)
- Backend unit tests: ~400+ passing
- Pre-existing failures: ~15 (eval tests need real Anthropic API key, E2E need running server)
- New failures introduced: 0

## Removed
- hookify plugin uninstalled (was failing with "No module named hookify" on every tool call)

## Sprint 16 — Planned (not started)
**TopicRefiner agent**: new pipeline node between research_node and content_generation_node.
- Takes: raw_topic + grounding_context (from UI) + research_results
- Produces: TopicBrief (refined_angle, hook_seed, target_audience, h2_structure[5], key_claims[3-5], concession)
- Model: supervisor (Sonnet) — needs editorial judgment
- New files: topic_refiner.py, topic_refiner_system.txt, topic_refiner_human.txt
- Orchestrator change: add topic_refinement_node, new state keys: refined_topic, topic_brief
- content_generator_human_initial.txt: receives structured brief instead of raw topic string

## Architecture after this session
```
Pipeline:
  research → topic_refiner[NEW] → content_generation → fact_check
          → quality_analysis → revision loop (max 6)
          → format → finalize

Improvement loop:
  quality_snapshots → analyze_quality_snapshots.py
                    → prompt_analyst.py
                    → improvement_report.md
                    → POST /pipeline/improve-prompts (API)

Exemplar system:
  finalize_node → save_exemplar (score >= 0.95)
  promote_latest_post.py → manual promotion CLI
  run_improvement_loop.py → full loop CLI
```
