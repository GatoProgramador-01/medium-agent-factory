---
name: explain-diff
description: Summarize uncommitted changes and flag security risks, missing tests, or breaking changes. Use before committing or creating a PR.
disable-model-invocation: false
allowed-tools: Bash Read Grep
---

# Explain Changes

## Files changed

!`git diff HEAD --stat`

## Full diff

!`git diff HEAD`

## Staged-only diff (if any)

!`git diff --cached`

## Instructions

Summarize the changes in 2–3 bullet points, then audit for risks:

**Security risks:**
- Hardcoded secrets, API keys, or credentials?
- New endpoints missing auth or rate limiting?
- User input reaching shell commands, SQL, or file paths unvalidated?
- CORS, CSP, or security headers weakened?

**Quality risks:**
- New functions without test coverage?
- Error handling missing on new API calls or DB operations?
- Breaking API contract changes (renamed fields, changed response shape)?
- `Any` types or raw `# type: ignore` without justification?

**Cost risks (for this project):**
- New LLM calls not going through `get_llm(role)` factory?
- Tavily searches not capped by `max_claims_per_run`?
- New pipeline entry points bypassing `check_daily_run_limit`?

If diff is empty, say "No uncommitted changes."
