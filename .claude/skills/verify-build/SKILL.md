---
name: verify-build
description: Verify both backend (mypy strict) and frontend (next build) compile cleanly. Use before creating a PR or deploying.
disable-model-invocation: false
allowed-tools: Bash Read Edit
---

# Build Verification

## Backend type check (mypy strict)

!`cd backend && .venv/Scripts/python -m mypy app/ --strict 2>&1 | tail -30`

## Frontend production build

!`cd frontend && NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build 2>&1 | tail -40`

## Instructions

Analyze the output above and fix all blockers:

**mypy failures:**
- Missing return type → add return annotation
- `Any` type → use explicit type or `cast()`
- `# type: ignore[call-arg]` is acceptable ONLY for LangChain/ChatAnthropic constructors
- Unused `# type: ignore` codes → remove the specific code or the whole comment

**Next.js build failures:**
- Import errors → check relative paths and barrel exports
- TypeScript errors → fix the type, don't cast to `any`
- Missing env vars → add to `NEXT_PUBLIC_*` in next.config.ts or hardcode a safe default

Both must pass clean before reporting done.
