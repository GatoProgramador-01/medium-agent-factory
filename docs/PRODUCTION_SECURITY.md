# Production Security Checklist

This document covers security hardening, cost controls, rate limits, and incident response for the medium-agent-factory deployment on Railway + Vercel + MongoDB Atlas.

---

## Before Going Live

Complete every item before exposing the service to the public internet.

- [ ] Generate `ADMIN_API_KEY` with `openssl rand -hex 32` and set it as a Railway environment variable — never commit it to git
- [ ] Set `ALLOWED_ORIGINS` to your Vercel URL only (e.g. `https://medium-agent-factory.vercel.app`) — remove all `localhost` entries
- [ ] Set `ENVIRONMENT=production` — this disables the `/docs` and `/redoc` endpoints so your API schema is not publicly browsable
- [ ] Confirm `DAILY_RUN_LIMIT` is set (default 20 = ~$12/day max spend at current model pricing)
- [ ] Set an Anthropic monthly spend cap: `console.anthropic.com` → Billing → Limits
- [ ] Set a Railway spend limit: Railway dashboard → Project Settings → Spending Limit
- [ ] Set MongoDB Atlas IP allowlist to Railway's egress IPs only — do not leave it as `0.0.0.0/0`
- [ ] Rotate `ANTHROPIC_API_KEY` if it was ever present in a git commit, CI log, or error message
- [ ] Verify `/health` returns only `{"status": "ok"}` — it must not leak environment name, version, or config values

---

## Cost Architecture

### Cost per operation

| Operation | Cost estimate | Driver |
|---|---|---|
| Single pipeline run | ~$0.61 | Haiku drafting + Sonnet quality eval + Tavily × 8 searches |
| Single series (3 posts) | ~$1.83 | 3 × pipeline run |
| Daily cap at 20 runs | ~$12.20 max | `DAILY_RUN_LIMIT=20` |
| Monthly worst-case at 20 runs/day | ~$366 | All days at full cap |

### How cost is controlled

`MAX_CLAIMS_PER_RUN` limits the number of Tavily fact-check searches per pipeline run. At $0.001 per search, setting `MAX_CLAIMS_PER_RUN=8` caps Tavily cost to $0.008 per run. The primary cost driver is the Sonnet quality evaluation pass; the Anthropic monthly cap is the last line of defense if the daily counter is bypassed.

---

## Rate Limits in Effect

The API enforces the following limits at the application layer:

| Endpoint | Limit | Scope |
|---|---|---|
| `POST /pipeline/run` | 2 per hour | Per IP address |
| `POST /series/run` | 1 per hour | Per IP address |
| Global daily cap | 20 runs total | All users combined |

The global daily cap is stored in the `daily_counters` MongoDB collection and is keyed by calendar date (UTC). Requests that include a valid `X-Admin-Key` header bypass the global daily cap but are still subject to per-IP rate limits.

---

## If You Get Exploited

Follow these steps in order. Speed matters — Anthropic charges accrue in real time.

1. **Rotate `ANTHROPIC_API_KEY` immediately**: go to `console.anthropic.com` → API Keys → revoke the current key and generate a new one. Update the Railway environment variable and redeploy.
2. **Hard-stop all runs**: set `DAILY_RUN_LIMIT=0` in Railway environment variables. The pipeline will reject every run attempt until you raise it again.
3. **Check Railway logs** for abnormal traffic patterns — look for high-frequency requests from a single IP or burst patterns outside normal hours.
4. **Inspect the daily counter** in MongoDB to understand the scope of the abuse:
   ```js
   db.daily_counters.find().sort({ date: -1 })
   ```
5. **Block the IP** at the Railway level or add stricter per-IP rate limits in your reverse proxy if the attacker's IP is identifiable.
6. **Review MongoDB Atlas access logs** to confirm no unauthorized database access occurred alongside the API abuse.

---

## Monitoring Queries

Run these in the MongoDB shell (`mongosh`) or MongoDB Atlas Data Explorer.

### Today's run count

```js
db.daily_counters.findOne({ date: new Date().toISOString().slice(0, 10) })
```

### Runs by day for the last 7 days

```js
db.pipeline_runs.aggregate([
  {
    $group: {
      _id: { $dateToString: { format: "%Y-%m-%d", date: "$created_at" } },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: -1 } },
  { $limit: 7 }
])
```

### Most expensive topics (by revision cycles)

```js
db.pipeline_runs.aggregate([
  { $project: { topic: 1, revision_cycles: 1, status: 1, created_at: 1 } },
  { $sort: { revision_cycles: -1 } },
  { $limit: 10 }
])
```

---

## Environment Variable Reference

| Variable | Required in prod | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Rotate immediately if leaked |
| `MONGODB_URI` | Yes | Use Atlas connection string with credentials |
| `ENVIRONMENT` | Yes | Set to `production` |
| `ALLOWED_ORIGINS` | Yes | Vercel URL only, no localhost |
| `ADMIN_API_KEY` | Yes | 32-byte hex; never commit to git |
| `DAILY_RUN_LIMIT` | Yes | Recommended: 20 |
| `MAX_CLAIMS_PER_RUN` | Yes | Recommended: 8 |
| `LANGCHAIN_TRACING_V2` | Optional | Set to `true` with valid `LANGCHAIN_API_KEY` for production tracing |
| `USE_LOCAL_LLM` | No | Always `false` in production |
