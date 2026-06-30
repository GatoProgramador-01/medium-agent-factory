---
id: intro
title: Welcome to medium-agent-factory
sidebar_label: Introduction
sidebar_position: 1
---

# Welcome to medium-agent-factory

**medium-agent-factory** is a 16-node LangGraph pipeline that autonomously writes, evaluates, and revises Medium posts using a multi-agent architecture.

## What it does

The pipeline takes a topic string and produces a publication-ready Medium article by:

- Running **16 coordinated LangGraph nodes** from research through final formatting
- Applying **G-Eval quality gates** with structured LLM-as-judge scoring
- Executing a **conditional revision loop** (up to 6 cycles) until quality thresholds are met
- Storing **quality snapshots** in MongoDB for every iteration
- Supporting **A/B title testing** and **intro optimization**

The project has **453 passing tests** and a full CI/CD pipeline via GitHub Actions.

## Explore the docs

- [Pipeline Overview](./pipeline-overview) — all 16 nodes with a Mermaid flowchart
- [GitHub Repository](https://github.com/GatoProgramador-01/medium-agent-factory) — source code, issues, and releases

## Status

Full documentation is in progress. The pipeline is production-ready; docs coverage is expanding sprint by sprint.
