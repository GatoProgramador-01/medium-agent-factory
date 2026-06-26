---
name: test-and-fix
description: Run the test suite and auto-fix any failing tests. Use when tests are broken or after implementing new features.
argument-hint: "[backend|frontend|all]"
disable-model-invocation: false
model: sonnet
maxTurns: 8
allowed-tools: Bash Read Edit Glob Grep
---

# Test and Fix

## Backend test status

!`cd backend && .venv/Scripts/python -m pytest tests/ --ignore=tests/e2e/ -q --tb=short 2>&1 | tail -40`

## Frontend test status

!`cd frontend && npm run test:unit -- --passWithNoTests --ci 2>&1 | tail -30`

## Instructions

Analyze the test output above. For each failure:
1. Read the failing test file to understand what behavior is being tested
2. Identify the root cause (not just the symptom)
3. Fix the implementation — never modify the test to make it pass unless the test itself is wrong
4. Re-run that specific test file to confirm it passes before moving on

TDD rules:
- Red → Green → Refactor cycle is non-negotiable
- If tests don't exist for a new function, write them first
- Cast Motor results with `cast()` in FastAPI; never `# type: ignore[return-value]`
