---
id: intro
title: Welcome to Medium Agent Factory
sidebar_label: Introduction
sidebar_position: 1
---

# Medium Agent Factory

**Medium Agent Factory** is a 16-node LangGraph pipeline that autonomously researches, writes, evaluates, and revises Medium posts using a multi-agent architecture. Built as a production-grade LLMOps project, it demonstrates the full spectrum from prompt engineering and structured output to eval-in-CI and quality observability.

## What it does

The pipeline takes a topic string and produces a publication-ready Medium article by:

- Running **16 coordinated LangGraph nodes** from research through final formatting
- Applying a **3-layer quality system**: deterministic structural checks, G-Eval LLM-judge scoring, and config-driven thresholds
- Executing a **conditional revision loop** (up to 6 cycles) until quality thresholds are met
- Storing **quality snapshots** in MongoDB for every iteration — enabling score-over-time analysis
- Supporting **A/B title testing** and **intro variant optimization**
- Enforcing **prompt versioning discipline** with documented fixes tracked in version history

The project has **463 passing tests** across unit, integration, and evaluation layers, with a full CI/CD pipeline via GitHub Actions.

## Recent pipeline results

All four posts produced in the last sprint cleared the 0.90 quality threshold without manual editing:

| Post title | Quality score | Read ratio | Revisions |
|---|---|---|---|
| DeepSeek Series — Post 1 | 0.96 | 0.94 | 2 |
| DeepSeek Series — Post 2 | 0.97 | 0.95 | 1 |
| DeepSeek Series — Post 3 | 1.00 | 0.98 | 1 |
| Standalone (LLMOps topic) | 0.91 | 0.88 | 3 |

All posts were flagged **Boost-eligible** by Medium's internal distribution model.

## Explore the docs

- [Pipeline Overview](./pipeline-overview) — all 16 nodes with a Mermaid flowchart
- [Quality Gates](./quality-gates) — 3-layer quality architecture and threshold config
- [Prompt Engineering](./prompt-engineering) — versioned prompt fixes and the revision loop design
- [GitHub Repository](https://github.com/GatoProgramador-01/medium-agent-factory) — source code, issues, and releases

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (StateGraph, conditional edges) |
| LLM calls | LangChain `.with_structured_output(PydanticModel)` |
| Search grounding | Tavily API |
| Evaluation | G-Eval (LLM-as-judge) + custom structural checker |
| Storage | MongoDB (articles + quality snapshots) |
| API | FastAPI + async Motor driver |
| Frontend | Next.js 15 (App Router) + React Query + SSE streaming |
| Tests | pytest (backend) + Jest + RTL (frontend) — 463 total |
| CI/CD | GitHub Actions (5-job matrix) |
