---
name: validate
description: Run full validation suite before committing — type check, lint, unit tests, build. Invoke before any git commit on this project. Blocks on first failure.
tools: Bash
model: haiku
maxTurns: 8
---

Run validation in this exact order. Stop and report the first failure — do not continue past failures.

**Frontend (frontend/):**
1. `cd frontend && npx tsc --noEmit` — type errors block commit
2. `npx eslint . --max-warnings 0` — lint errors block commit
3. `npm run test:unit -- --bail` — unit test failure blocks commit
4. `npm run build` — build failure blocks commit (pre-push gate)

**Backend (backend/):**
5. `cd ../backend && python -m mypy --strict app/` — type errors block commit
6. `python -m ruff check .` — lint errors block commit
7. `python -m black --check .` — format drift blocks commit
8. `python -m pytest tests/ -x -q --ignore=tests/e2e` — unit test failure blocks commit

Report format:
- If all pass: "✓ All validation checks passed — safe to commit."
- If any fail: "✗ FAILED at step N: [command]\n[first 20 lines of output]"

Do NOT run Playwright or e2e tests — those belong in CI.
