---
name: deploy
description: Trigger production deployment to Railway + Vercel via GitHub Actions. Only invoke this manually after confirming all CI checks pass.
disable-model-invocation: true
model: haiku
maxTurns: 3
allowed-tools: Bash
---

# Production Deploy

## Pre-deploy checklist

!`git log --oneline -5`

!`git status`

## Instructions

Before deploying, verify:
- [ ] All CI checks are green on master (check GitHub Actions)
- [ ] No uncommitted changes (`git status` is clean above)
- [ ] `ENVIRONMENT=production` is set in Railway
- [ ] `ALLOWED_ORIGINS` points to the Vercel URL in Railway env vars
- [ ] MongoDB Atlas is reachable (check Railway deploy logs)

**To deploy:**
```bash
git commit --allow-empty -m "chore: trigger production deploy"
git push origin master
```

Then watch: https://github.com/GatoProgramador-01/medium-agent-factory/actions

**Emergency rollback:**
```bash
git revert HEAD --no-edit
git push origin master
```
