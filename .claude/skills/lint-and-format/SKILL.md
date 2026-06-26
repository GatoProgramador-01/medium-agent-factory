---
name: lint-and-format
description: Check and fix code formatting and lint errors across backend and frontend. Use before committing.
disable-model-invocation: false
model: haiku
maxTurns: 4
allowed-tools: Bash Read Edit
---

# Lint and Format

## Backend lint status

!`cd backend && .venv/Scripts/python -m ruff check . --show-fixes 2>&1 | head -40`

## Backend format check

!`cd backend && .venv/Scripts/python -m black --check . 2>&1 | head -20`

## Backend type check

!`cd backend && .venv/Scripts/python -m mypy app/ 2>&1 | tail -30`

## Frontend lint status

!`cd frontend && npm run lint 2>&1 | head -30`

## Instructions

Fix all issues reported above:

**Python (backend/):**
- ruff errors: fix import order (I), unused imports (F401), bare excepts (E722)
- black: just run `black .` — never argue with the formatter
- mypy: use `cast()` for Motor returns, `# type: ignore[call-arg]` for LangChain constructors only

**TypeScript (frontend/):**
- ESLint: fix `any` types (use `unknown` + type guard), unused vars, missing deps in useEffect
- Never suppress eslint with `// eslint-disable` unless truly unavoidable
