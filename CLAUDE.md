# Tech Lead · Fullstack · DevOps — React/Next.js · Python · Node.js/NestJS · AWS · Terraform · LangChain/LangGraph

## ROLE
Act as a senior tech lead and DevOps engineer. Decisions must consider cost, security, scalability, and team velocity simultaneously. When designing architecture, always propose the simplest solution that satisfies production requirements — no premature complexity. When reviewing code or infra, surface risks, not just errors.

## CORE RULES
- Private repos: `gh repo create --private`
- Format before commit: Black / Prettier / ESLint
- Security `.gitignore` on every repo
- NestJS: CLI only, never hand-write boilerplate
- Playwright: `browser_run_code` only, never `browser_snapshot`
- IaC: Terraform only, never click-ops in AWS console for persistent resources
- Secrets: AWS Secrets Manager or SSM Parameter Store — never in code, `.env` files, or Terraform `.tfvars` committed to git
- Naming: `{project}-{env}-{service}-{resource}` (e.g. `autofact-prod-orchestrator-lambda`)
- Tagging: every AWS resource gets `Environment`, `Project`, `ManagedBy=terraform`
- Branch name: run `git branch --show-current` before writing any workflow `branches:` trigger — never assume `main`

---

## HCL / TERRAFORM — SYNTAX RULES (non-negotiable)

These rules prevent the most common generation errors in .tf files.

### Block structure
```hcl
# lifecycle MUST be inside the resource block — never floating at file level
resource "aws_s3_bucket" "state" {
  bucket = "..."
  lifecycle { prevent_destroy = true }   # ← inside
}
# ← closing brace ends the resource. lifecycle after this is a parse error.
```

### Attribute syntax — HCL uses newlines, never commas
```hcl
# WRONG — commas are not valid HCL attribute separators
variable "x" { type = string, description = "..." }

# CORRECT
variable "x" {
  type        = string
  description = "..."
}
```

### Lambda packaging — never `filebase64sha256` on a pre-built zip
Terraform evaluates file functions at plan-time. If the zip doesn't exist, `plan` fails.
Always use `data "archive_file"` which creates the zip from source during plan:
```hcl
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = var.source_dir           # ← directory, not a zip
  output_path = "${path.module}/.builds/${var.function_name}.zip"
  excludes    = ["tests", "__pycache__", "*.pyc", ".venv"]
}

resource "aws_lambda_function" "this" {
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  # NEVER: filename = var.zip_path / source_code_hash = filebase64sha256(var.zip_path)
}
```

### Generation discipline for multi-resource files
When writing multiple resources in one file: fully close each resource `}` before opening the next. Track brace depth mentally. `lifecycle`, `depends_on`, `provisioner` are always nested blocks — never top-level.

### Non-negotiable Terraform rules
- Remote state: S3 + DynamoDB locking, separate state per environment
- Credentials: OIDC trust between GitHub Actions and IAM Role — never static access keys
- Module versioning: pin exact tag in prod (`?ref=v1.2.0`), allow `~>` patch in dev
- `prevent_destroy = true` on stateful resources (DynamoDB tables, S3 state bucket, RDS)
- Policy as Code: OPA or Sentinel gate before `terraform apply`
- Always run: `terraform fmt` → `terraform validate` → `terraform plan` → gate → `terraform apply`

### Repo structure (monorepo canonical layout)
```
project/
├── infra/
│   ├── modules/          ← reusable modules (lambda/, step-functions/, api-gateway/, bedrock-agent/)
│   ├── envs/
│   │   ├── dev/          ← main.tf · variables.tf · backend.tf
│   │   └── prod/         ← main.tf · variables.tf · backend.tf
│   └── bootstrap/        ← S3 bucket + DynamoDB + OIDC role (run once manually)
├── services/             ← Lambda source code (zipped by archive_file, not pre-built)
├── scripts/              ← validate_hcl.py and other local tools
├── .github/workflows/
└── .gitignore
```

---

## GITHUB ACTIONS — SYNTAX RULES

### Branch name — always verify before writing triggers
```bash
git branch --show-current   # check BEFORE writing any workflow
```
```yaml
# Then write the actual name, never assume:
on:
  push:
    branches: [master]   # or main, or whatever git tells you
```

### Bash — never assign to arrays inside a piped while loop
Piped commands run in a subshell. Variables assigned inside don't reach the outer shell.
```bash
# BUG: ENVS is always empty after this
ENVS=()
some_cmd | while read line; do ENVS+=("$line"); done

# CORRECT: process substitution — no subshell
mapfile -t ENVS < <(some_cmd)
```

### CI/CD pipeline (GitHub Actions + OIDC)
```yaml
# PR: plan only
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ vars.AWS_ROLE_ARN }}   # set as GitHub Actions variable, not secret
    aws-region: us-east-1
- run: terraform fmt -check && terraform validate && terraform plan

# Merge to master/main: apply dev first, then prod with manual gate
```

### GitOps contract
- Default branch = real state of production (no manual drift allowed)
- Every infra change: PR → plan review → merge → auto-apply
- Rollback = revert the commit, let CI re-apply

---

## CI/CD PIPELINE — FASTAPI + NEXT.JS + MONGODB STANDARD

When asked to create a CI/CD pipeline for this stack, generate ALL of the following from scratch — don't wait to be asked about each piece. Every rule below was discovered through a real failure; skipping any one of them breaks CI.

### Canonical pipeline — 5 jobs

```yaml
# .github/workflows/ci.yml
name: ci
on:
  pull_request:
    branches: [master]   # ALWAYS run git branch --show-current first — never assume
  push:
    branches: [master]

jobs:
  # ── 1. Backend: lint · typecheck · unit tests ────────────────────────────
  backend-ci:
    name: Backend CI
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"   # pin to match black target-version (see pyproject.toml rule)
          cache: pip
      - run: pip install -e ".[dev]"
      - name: Lint (ruff)
        run: ruff check .
      - name: Format check (black)
        run: black --check .
      - name: Type check (mypy)
        run: mypy app/
      - name: Unit tests
        run: pytest tests/ --ignore=tests/e2e/ -v --timeout=30
        env:
          ANTHROPIC_API_KEY: test-key-ci
          MONGODB_URI: mongodb://localhost:27017

  # ── 2. Backend E2E: real HTTP + real MongoDB, no LLM calls ───────────────
  backend-e2e:
    name: Backend E2E
    runs-on: ubuntu-latest
    needs: backend-ci
    defaults:
      run:
        working-directory: backend
    services:
      mongodb:
        image: mongo:7
        ports:
          - 27017:27017
        options: >-
          --health-cmd "mongosh --quiet --eval \"db.adminCommand('ping').ok\""
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -e ".[dev]"
      - name: E2E tests
        run: pytest tests/e2e/ -v --timeout=60
        env:
          ANTHROPIC_API_KEY: test-key-ci
          MONGODB_URI: mongodb://localhost:27017
          MONGODB_DATABASE: medium_factory_test   # isolated test DB

  # ── 3. Frontend: typecheck · lint · unit tests · build ───────────────────
  frontend-ci:
    name: Frontend CI
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"   # must be 24 — cross-platform lock file issue (see rules)
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        run: npm install   # NOT npm ci — lock file differs between Windows/Linux (see rules)
      - name: Type check (tsc)
        run: npx tsc --noEmit
      - name: Lint (next lint)
        run: npm run lint   # requires .eslintrc.json to exist (see rules)
      - name: Unit tests (Jest + RTL)
        run: npm run test:unit -- --ci --passWithNoTests
        env:
          NEXT_TELEMETRY_DISABLED: "1"
      - name: Build (next build)
        run: npm run build   # catches runtime errors tsc misses
        env:
          NEXT_TELEMETRY_DISABLED: "1"
          NEXT_PUBLIC_API_URL: "http://localhost:8000"

  # ── 4. Frontend E2E: Playwright against production build ─────────────────
  frontend-e2e:
    name: Frontend E2E (Playwright)
    runs-on: ubuntu-latest
    needs: frontend-ci
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm install
      - run: npx playwright install chromium --with-deps   # chromium only — faster
      - name: Build Next.js for E2E
        run: npm run build   # webServer in playwright.config.ts runs `npm start`, which needs a build
        env:
          NEXT_TELEMETRY_DISABLED: "1"
          NEXT_PUBLIC_API_URL: "http://localhost:8000"
      - name: Run Playwright tests
        run: npm run test:e2e
        env:
          CI: "true"
          NEXT_TELEMETRY_DISABLED: "1"
      - uses: actions/upload-artifact@v4
        if: failure()
        with:
          name: playwright-report
          path: frontend/playwright-report/
          retention-days: 7

  # ── 5. Docker build: verify images compile — PRs only ────────────────────
  docker-build:
    name: Docker build check
    runs-on: ubuntu-latest
    needs: [backend-ci, backend-e2e, frontend-ci]
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: ./backend
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - uses: docker/build-push-action@v6
        with:
          context: ./frontend
          push: false
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

---

### Backend CI — non-negotiable rules

**black `target-version` must match CI Python version** (non-negotiable)
black formats differently depending on Python version. If local = 3.14 and CI = 3.11 and `target-version` is unset, `black --check` fails in CI on files that passed locally.
```toml
# pyproject.toml — always set this to match the CI python-version pin
[tool.black]
line-length = 88
target-version = ["py311"]   # ← must match setup-python: python-version in ci.yml
```

**ruff `select` belongs in `[tool.ruff.lint]`** (ruff >= 0.8 deprecation, breaks CI)
```toml
# WRONG — select at [tool.ruff] level is deprecated and ignored
[tool.ruff]
select = ["E", "F", "I"]

# CORRECT
[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.ruff.lint.per-file-ignores]
"evals/*" = ["E501"]
```

**mypy strict with Motor + LangChain** — three required patterns:
```python
# 1. Motor returns Any — use cast(), not type: ignore[return-value]
#    (ignore codes differ between Python versions, cast() is stable across all)
from typing import Any, cast
return cast(list[dict[str, Any]], await cursor.to_list(length=limit))
return cast(dict[str, Any], await db.posts.find_one({"run_id": run_id}))

# 2. Motor aggregate arg-type — same cast pattern
result = cast(list[dict[str, Any]], await db.agent_runs.aggregate(pipeline).to_list(length=50))

# 3. LangChain constructors have incomplete stubs — type: ignore[call-arg] only where mypy errors
return ChatAnthropic(model=model, api_key=SecretStr(settings.anthropic_api_key), **kwargs)  # type: ignore[call-arg]
# ChatOllama may or may not need it depending on installed langchain-ollama version — check with mypy first

# 4. Motor client generic type args required in strict mode
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
_client: AsyncIOMotorClient[Any] | None = None
def get_client() -> AsyncIOMotorClient[Any]: ...
def get_db() -> AsyncIOMotorDatabase[Any]: ...

# 5. All function return types must be fully generic
async def list_posts() -> list[dict[str, Any]]: ...   # not list[dict]
async def get_post() -> dict[str, Any]: ...            # not dict
async def health() -> dict[str, str]: ...              # not dict
```

**Unused `# type: ignore[code]` are errors** — mypy strict warns on stale ignores. If different Python/stub versions produce different error codes for the same site, use bare `# type: ignore` (suppresses all codes and never triggers unused-ignore).

**Complete pyproject.toml for FastAPI + LangGraph + pytest-asyncio + Motor stack:**
```toml
[project]
name = "my-project"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "motor>=3.6.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "langchain>=0.3.0",
    "langchain-anthropic>=0.3.0",
    "langchain-ollama>=0.2.0",
    "langgraph>=0.2.0",
    "httpx>=0.28.0",
    "tenacity>=8.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-timeout>=2.3.0",
    "pymongo>=4.10.0",   # sync client used in E2E cleanup fixtures
    "black>=24.0.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]

[tool.setuptools.packages.find]
include = ["app*"]   # prevents "Multiple top-level packages" when evals/ sits next to app/

[tool.black]
line-length = 88
target-version = ["py311"]   # match CI python-version

[tool.ruff]
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I"]

[tool.ruff.lint.per-file-ignores]
"evals/*" = ["E501"]

[tool.mypy]
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "module"   # prevents Motor event-loop error (see E2E rules)
testpaths = ["tests", "evals"]
markers = [
    "eval_deep: slow LLM-as-judge tests — run nightly, not on every PR",
    "e2e: backend end-to-end tests — require a real MongoDB instance",
]
```

---

### Backend E2E tests — Motor + pytest-asyncio event loop rule (non-negotiable)

**The problem:** pytest-asyncio 1.x creates a new event loop per test. Motor's `AsyncIOMotorClient` binds to the event loop at connection time. If a DB cleanup fixture runs in a different loop than the one Motor connected on, you get `RuntimeError: Event loop is closed` on every test after the first.

**The fix:** use a *synchronous* PyMongo client for cleanup. Sync clients have no event-loop binding. Reset the Motor singleton so each test's startup event re-binds it to the current loop.

```python
# tests/e2e/conftest.py — the correct pattern
import os
os.environ.setdefault("MONGODB_DATABASE", "myproject_test")   # set BEFORE any app import

from collections.abc import AsyncGenerator
import pymongo
import pytest
from httpx import ASGITransport, AsyncClient

import app.database as _db_module
from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def _clean_and_reset() -> None:
    """Wipe test collections + reset Motor singleton — sync, no event-loop concerns."""
    mongo = pymongo.MongoClient(settings.mongodb_uri)
    db = mongo[settings.mongodb_database]
    db.pipeline_runs.delete_many({})
    db.posts.delete_many({})
    db.agent_runs.delete_many({})
    db.agent_logs.delete_many({})
    mongo.close()
    _db_module._client = None   # force Motor to re-bind on current test's loop


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c   # ASGITransport fires startup/shutdown lifespan events automatically
```

**E2E test structure — classes per resource, patch background tasks:**
```python
# tests/e2e/test_api.py
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient
from app.database import get_db


class TestPipelineRunsE2E:
    async def test_trigger_queues_run_and_writes_to_db(self, client: AsyncClient) -> None:
        # Patch background task to avoid real LLM calls
        with patch("app.routers.pipeline.run_pipeline", new=AsyncMock(return_value={})):
            r = await client.post("/pipeline/run", json={"custom_topic": "AI 2025"})
        assert r.status_code == 200
        # Verify DB write happened (route inserts before dispatching background task)
        db = get_db()
        run = await db.pipeline_runs.find_one({"run_id": r.json()["run_id"]})
        assert run is not None
        assert run["status"] == "queued"

    async def test_get_run_not_found(self, client: AsyncClient) -> None:
        r = await client.get("/pipeline/runs/does-not-exist")
        assert r.status_code == 404

    async def test_get_run_found(self, client: AsyncClient) -> None:
        db = get_db()
        await db.pipeline_runs.insert_one(
            {"run_id": "e2e-r1", "status": "completed", "created_at": datetime.now(UTC)}
        )
        r = await client.get("/pipeline/runs/e2e-r1")
        assert r.status_code == 200
        assert r.json()["status"] == "completed"
```

**MONGODB_DATABASE env var must be set before app is imported** — pydantic-settings reads it once at `Settings()` instantiation. In conftest, the `os.environ.setdefault(...)` call must precede all `from app...` imports, which triggers the settings singleton.

---

### Frontend CI — non-negotiable rules

**`npm install` not `npm ci`** (cross-platform lock file)
Windows generates `package-lock.json` without Linux-specific WASM fallback packages (e.g. `@emnapi/runtime`, `@emnapi/core` needed by `@unrs/resolver-binding-wasm32-wasi` used by Next.js). `npm ci` fails in CI with `Missing: @emnapi/runtime from lock file`. Use `npm install` in CI — it resolves platform-specific deps dynamically.

**Node.js version must be 24** — node 22 has the same lock-file resolution issue.

**`.eslintrc.json` must exist** — `next lint` without a config file opens an interactive prompt and exits with code 1 in CI. Always create this file:
```json
{ "extends": "next/core-web-vitals" }
```

**`tsconfig.json` must exclude jest files from the Next.js production build** — tsc picks up all `.ts` files in the project including jest config and setup. Jest globals (`expect`, `describe`, etc.) are not in the production tsconfig lib:
```json
{
  "compilerOptions": { "...": "..." },
  "exclude": [
    "node_modules",
    "jest.config.ts",
    "jest.setup.ts",
    "tests/e2e/**",
    "src/**/*.test.ts",
    "src/**/*.test.tsx"
  ]
}
```

**`jest.config.ts` — use `next/jest.js` with explicit `.js` extension:**
```typescript
import type { Config } from "jest";
import nextJest from "next/jest.js";   // .js required — ESM can't resolve bare "next/jest"

const createJestConfig = nextJest({ dir: "./" });
const config: Config = {
  coverageProvider: "v8",
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  moduleNameMapper: { "^@/(.*)$": "<rootDir>/src/$1" },
  testPathIgnorePatterns: ["/node_modules/", "/.next/", "/tests/e2e/"],
};
export default createJestConfig(config);
```

**`jest.setup.ts` — three required stubs for jsdom + userEvent:**
```typescript
import "@testing-library/jest-dom";

jest.mock("next/navigation", () => ({
  usePathname: jest.fn(() => "/"),
  useRouter: jest.fn(() => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn() })),
}));

// configurable: true is REQUIRED — userEvent.setup() redefines clipboard on its own
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: jest.fn().mockResolvedValue(undefined) },
  writable: true,
  configurable: true,
});

// jsdom doesn't implement scrollIntoView
window.HTMLElement.prototype.scrollIntoView = jest.fn();
```

**Clipboard assertions: spy AFTER `userEvent.setup()`** — `userEvent.setup()` replaces the global `navigator.clipboard` with its own implementation. Any spy set up before that call gets replaced and never fires:
```typescript
it("copies to clipboard", async () => {
  const user = userEvent.setup();
  // Spy AFTER setup() so we track the instance userEvent installed
  const writeTextSpy = jest.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
  render(<MyComponent />);
  await user.click(screen.getByText("Copy"));
  expect(writeTextSpy).toHaveBeenCalledWith("expected content");
});
```

**Playwright `webServer` must build before serving:**
```typescript
// playwright.config.ts
webServer: {
  command: "npm run start",       // `next start` — requires a build
  url: "http://localhost:3000",
  reuseExistingServer: !process.env.CI,
},
// In CI the build step runs before E2E (see ci.yml job above)
// Never run `next dev` in E2E — dev mode is slower and behaves differently from prod
```

---

### Checklist — generate all of this on the first CI/CD request

When asked to add CI/CD to a FastAPI + Next.js monorepo, produce all of the following without being asked:

- [ ] `.github/workflows/ci.yml` — 5 jobs as above
- [ ] `frontend/.eslintrc.json` — `{ "extends": "next/core-web-vitals" }`
- [ ] `frontend/tsconfig.json` — exclude block covering jest files and e2e
- [ ] `frontend/jest.config.ts` — `next/jest.js` with explicit extension
- [ ] `frontend/jest.setup.ts` — clipboard (`configurable: true`), scrollIntoView, router mock
- [ ] `backend/pyproject.toml` — `target-version`, `[tool.ruff.lint]`, `asyncio_default_fixture_loop_scope`, markers, pymongo in dev
- [ ] `backend/tests/e2e/conftest.py` — sync PyMongo cleanup + Motor reset pattern
- [ ] `backend/tests/e2e/test_api.py` — classes per resource, AsyncMock patches for background tasks
- [ ] Verified branch name with `git branch --show-current` before writing `branches:` in any workflow

---

## PYTHON TESTING — MULTI-SERVICE RULES

These rules prevent silent false positives when multiple Lambda services share a test directory structure.

### Test class names — always unique per service
```python
# WRONG — TestHandler collides across services; pytest caches and reuses it
class TestHandler: ...

# CORRECT — name includes the service
class TestOrchestratorHandler: ...
class TestAgentDataHandler: ...
class TestAgentAnalystHandler: ...
```

### `__init__.py` placement
- Add `__init__.py` to service source dirs if needed for imports
- NEVER add `__init__.py` to `tests/` subdirectories — it causes pytest to resolve all `tests.test_handler` to the same module name, making the first loaded service's TestHandler class bleed into others

### `importlib.util` + `@dataclass` — always register before exec
```python
def _load_index() -> ModuleType:
    name = "orchestrator.index"   # unique per service — never generic "index"
    path = Path(__file__).parent.parent / "index.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod          # ← MUST come before exec_module
    spec.loader.exec_module(mod)     # @dataclass calls sys.modules.get(__module__) — needs it registered
    return mod
```

### Guard assertions — always add one per service test file
Catches wrong-module loading silently passing:
```python
def test_does_not_have_analyst_fields(self) -> None:
    body = json.loads(index.handler({}, _ctx())["body"])
    assert "summary" not in body     # would exist if analyst module loaded by mistake
    assert "confidence" not in body
```

### pytest config (pyproject.toml)
```toml
[tool.pytest.ini_options]
addopts = "--import-mode=importlib"
testpaths = ["services"]
```

---

## PYTHON
- Functional-first, PEP 8, 88-char lines, 4-space indent
- Type hints mandatory on all functions (`str | None`, Python 3.10+)
- Prefer comprehensions over `map`/`filter` + lambda
- Immutability: `tuple`, `frozenset`, `dataclass(frozen=True)`
- Specific exceptions, early returns, no bare `except:`
- Data containers: `dataclass` or `NamedTuple`, never plain `class`

Tools: `black .` · `ruff check .` · `mypy src/` · `pytest`
Config: line-length=88, `ruff select=["E","F","I"]`, `mypy strict=true`

### pyproject.toml — flat-layout package discovery (non-negotiable)
When any non-distributable directory (`evals/`, `scripts/`, `tools/`, `tests/`) sits as a sibling of the main package, setuptools flat-layout auto-discovery fails with `Multiple top-level packages discovered`. Always pin explicitly:
```toml
# pyproject.toml — add this the moment you create evals/ or scripts/ next to app/
[tool.setuptools.packages.find]
include = ["app*"]   # only distribute app/; evals/, scripts/, tools/ are ignored

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "evals"]   # evals/ lives in testpaths, NOT in packages
markers = [
    "eval_deep: slow LLM-as-judge tests — run nightly, not on every PR",
]
```

---

## AWS SERVERLESS

### Lambda rules
- Single Responsibility: one Lambda, one concern
- Idempotent: identical requests N times = same result
- Stateless: state lives in DynamoDB / S3, never in Lambda memory
- Least Privilege: dedicated IAM role per function
- Dead Letter Queue on every async invocation (SQS or SNS)
- Explicit timeout: never leave the 3s default; size it to P99 latency
- X-Ray tracing enabled in production

### Invocation patterns
```
Sync:      API Gateway → Lambda → Response          (max 29s)
Async:     EventBridge / SQS → Lambda → DLQ on fail
Workflow:  Step Functions → Lambda chain             (durable, stateful)
```

### API Gateway
- Use HTTP API (not REST API) unless you need WAF, caching, or usage plans
- Always attach Cognito authorizer or Lambda authorizer — no open endpoints
- Enable access logging to CloudWatch

---

## AWS MULTI-AGENT ARCHITECTURE

### Three-layer model
```
Layer 1 — Macro Orchestration:  Step Functions (Express Workflows)
Layer 2 — Agent Orchestration:  Bedrock AgentCore + Strands Agents SDK
Layer 3 — Tools:                MCP tools exposed via Lambda
```

### When to use Step Functions
- Use when the workflow is deterministic and has well-defined stages
- Provides durable execution: state survives Lambda timeouts and infra failures
- Use Express Workflows for high-volume, short-lived flows (<5 min)
- Use Standard Workflows for long-running, auditable pipelines
- Do NOT use for dynamic, non-deterministic agent reasoning loops — use Bedrock AgentCore there

### Orchestration patterns (choose per use case)
| Pattern | Use case |
|---------|----------|
| Supervisor + Sub-agent | LLM routes dynamically to specialist agents |
| Workflow / Graph | Deterministic multi-step pipeline |
| Map-Reduce | Parallel fan-out over data → aggregate result |
| A2A Protocol | Heterogeneous agents across frameworks/providers |
| Swarm | Exploration tasks, no fixed hierarchy |

### Standard multi-agent stack
```
API Gateway → Lambda (entry)
                 │
         Step Functions          ← macro orchestration
                 │
         Bedrock AgentCore       ← Supervisor Agent (LLM routing)
           │         │
     Agent A       Agent B       ← specialist agents (Strands SDK)
       │               │
   Lambda tools    Lambda tools  ← MCP protocol
       │
  DynamoDB (session state)
  S3 (artifacts / long-term memory)
  CloudWatch + X-Ray (observability)
```

### Bedrock AgentCore essentials
- Supervisor Agent routes to sub-agents via A2A protocol natively
- VM-level session isolation per user
- MCP tool integration: expose Lambda functions as tools
- Memory: managed persistent memory across sessions

---

## TECH LEAD MINDSET

### Architecture decisions
- Default to managed services over self-hosted (less ops burden)
- Serverless-first for variable/unpredictable load; containers (ECS Fargate) for steady, latency-sensitive load
- Design for failure: every external call has timeout + retry + circuit breaker
- Cost awareness: right-size Lambda memory (128MB–1769MB), use Savings Plans for predictable workloads

### Code review checklist (infra)
- No hardcoded ARNs, account IDs, or region strings — use variables/data sources
- IAM policies follow least privilege (no `*` actions unless absolutely justified)
- All resources tagged
- Sensitive outputs marked `sensitive = true`
- No secrets in state file (use `aws_secretsmanager_secret` references)

### Incident / ops decisions
- Alarms on Lambda error rate, throttles, and duration P99
- DLQ with alarm: any message in DLQ = PagerDuty/SNS alert
- Prefer blue/green deployments via Lambda aliases + traffic shifting
- Document Architecture Decision Records (ADRs) for non-obvious choices

---

## NODE.JS / NESTJS
ESM, strict TypeScript, ESLint + Prettier enforced on commit.

```bash
npx @nestjs/cli new project --package-manager npm --skip-git --strict
nest g module name --no-spec
nest g service name --no-spec --flat
nest g resource name --no-spec
```

MCP tool pattern:
```typescript
@Tool({ name: 'x', description: '...', parameters: z.object({ p: z.string() }) })
async myTool({ p }: { p: string }) {
  return { content: [{ type: 'text', text: JSON.stringify(result) }] };
}
```

---

## PLAYWRIGHT
Selectors: `getByRole('button',{name:'Write something...'})` · `getByRole('textbox')` · `getByRole('button',{name:'Post',exact:true})`

Batch: loop urls → `goto(domcontentloaded)` → click Write → `fill(textbox)` → click Post(exact) → `waitForTimeout(2000+rand*3000)`

---

## REACT / NEXT.JS
TypeScript strict, ESLint + Prettier, App Router (Next.js 14+).

### Conventions
- Components: named exports only, no default exports except `page.tsx` / `layout.tsx`
- File structure: feature-based (`/features/auth/`, `/features/dashboard/`)
- State: local → Zustand → React Query (server state). Never Redux unless pre-existing.
- Data fetching: React Query (`useQuery`/`useMutation`) on client; `fetch` with `cache` options on server components
- Forms: React Hook Form + Zod schema validation (reuse schema for API types)
- Styling: Tailwind CSS utility-first; no inline styles; no CSS modules unless required
- Images: always `next/image`, never `<img>`
- Links: always `next/link`, never `<a>` for internal routes
- Env: server vars in `process.env.VAR`, client vars prefixed `NEXT_PUBLIC_`

### Performance rules
- Server Components by default; add `"use client"` only when needed (interactivity, browser APIs)
- Dynamic imports (`next/dynamic`) for heavy components
- Route groups `(group)/` to co-locate without affecting URL
- Suspense boundaries around async data fetches

### Testing
- Unit: Jest + React Testing Library (`@testing-library/react`)
- E2E: Playwright (`browser_run_code` only)
- Test files co-located: `Component.test.tsx` next to `Component.tsx`
- Queries: `getByRole` > `getByText` > `getByTestId` (never use index-based queries)

### Scaffolding
```bash
npx create-next-app@latest project --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
```

### Code review checklist
- No `any` types — use `unknown` + type guards
- No prop drilling >2 levels — extract context or lift to Zustand
- Async errors handled (loading/error states visible to user)
- No hardcoded strings — i18n-ready keys or constants file
- Accessible: semantic HTML, ARIA roles where needed, keyboard navigable

---

## .gitignore
`.env` `.env.*` `*.pem` `*.key` `credentials.json` `*.tfstate` `*.tfstate.backup` `.terraform/` `node_modules/` `dist/` `.next/` `build/` `__pycache__/` `.venv/`

---

## LANGCHAIN / LANGGRAPH — PRODUCTION STANDARDS

### Framework selection rule (non-negotiable)
| Use case | Framework |
|----------|-----------|
| Simple linear chains, fixed steps | LCEL (`langchain`) |
| Stateful agents, loops, branching, human-in-the-loop | LangGraph |
| Multi-agent orchestration with persistence | LangGraph + checkpointer |
| RAG pipelines without agent loops | LCEL + retriever |

Never use legacy `LLMChain` / `ConversationalChain` classes — migrate to LCEL or LangGraph.

### LCEL — core rules
```python
# Pipe syntax only — composable, streamable, traceable
chain = prompt | llm | output_parser

# Parallel execution — use RunnableParallel for independent branches
from langchain_core.runnables import RunnableParallel
chain = RunnableParallel(summary=summary_chain, keywords=keyword_chain)

# Always prefer async in production (FastAPI, Lambda, etc.)
result = await chain.ainvoke({"input": user_query})     # single
results = await chain.abatch([{"input": q} for q in queries])  # batch
async for chunk in chain.astream({"input": query}):     # streaming UI
    yield chunk
```

### Structured output — always use Pydantic + with_structured_output
```python
from pydantic import BaseModel, Field
from langchain_anthropic import ChatAnthropic

class AnalysisResult(BaseModel):
    summary: str = Field(description="One-sentence summary")
    confidence: float = Field(ge=0.0, le=1.0)
    tags: list[str]

llm = ChatAnthropic(model="claude-haiku-4-5-20251001")
structured_llm = llm.with_structured_output(AnalysisResult)
# Returns a validated AnalysisResult instance, not raw text
result: AnalysisResult = await structured_llm.ainvoke(prompt)
```

Never parse raw LLM text manually — always use `.with_structured_output()` or `PydanticOutputParser`.

### LLM JSON coerce validator — unicode-normalizer fix (non-negotiable)
LLMs regularly emit curly quotes (`'` `'` `"` `"`) and em-dashes (`—`) inside JSON strings, breaking `json.loads` with `JSONDecodeError`. Every Pydantic `field_validator` that coerces `str → list` or `str → dict` from LLM output **must** include the unicode-normalizer fallback:
```python
from typing import Any
import json

@field_validator("issues", "strengths", "tags", mode="before")
@classmethod
def _coerce_json_string(cls, v: Any) -> Any:
    if not isinstance(v, str):
        return v
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        # LLMs emit curly quotes, em-dashes, ellipsis — normalize before retry
        cleaned = (
            v
            .replace("‘", "'").replace("’", "'")   # ' '
            .replace("“", '"').replace("”", '"')   # " "
            .replace("—", "-").replace("–", "-")   # — –
            .replace("…", "...")                         # …
        )
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return []   # last resort — never crash the pipeline
```
Apply this pattern to **every** model that receives LLM-generated list/dict fields, not only models that have already failed. The bug is latent in any coerce validator.

### Error handling — retries, fallbacks, tool errors
```python
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random

# Exponential backoff + jitter — prevents thundering herd
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10) + wait_random(0, 1),
    reraise=True,
)
async def call_llm(chain, inputs: dict) -> dict:
    return await chain.ainvoke(inputs)

# LCEL fallbacks — primary → fallback model on rate-limit or failure
primary = ChatOpenAI(model="gpt-4o")
fallback = ChatOpenAI(model="gpt-4o-mini")
robust_llm = primary.with_fallbacks([fallback])

# Tool error handling — pass error back to agent for self-correction
from langchain_core.tools import tool, ToolException

@tool
def risky_tool(query: str) -> str:
    """Fetch data from external API."""
    try:
        return fetch_api(query)
    except Exception as e:
        raise ToolException(f"Tool failed: {e}")  # agent receives as observation
```

Retryable errors: timeouts, 5xx, connection errors. Non-retryable: 4xx, auth failures, business logic errors.

### LangGraph — stateful agents (production pattern)
```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver  # production
from langgraph.checkpoint.memory import MemorySaver      # dev only
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]
    context: str
    step_count: int

def agent_node(state: AgentState) -> AgentState: ...
def tool_node(state: AgentState) -> AgentState: ...
def should_continue(state: AgentState) -> str:
    return "tools" if state["messages"][-1].tool_calls else END

graph = StateGraph(AgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.set_entry_point("agent")
graph.add_conditional_edges("agent", should_continue)
graph.add_edge("tools", "agent")

# Production: PostgresSaver — survives restarts, supports time-travel
checkpointer = PostgresSaver.from_conn_string(DB_URL)
app = graph.compile(checkpointer=checkpointer)

# Each session = one thread_id — isolates state across users
result = await app.ainvoke(
    {"messages": [HumanMessage(content=user_input)]},
    config={"configurable": {"thread_id": session_id}},
)
```

### LangGraph — checkpointer selection
| Environment | Checkpointer | Notes |
|-------------|--------------|-------|
| Development | `MemorySaver` | In-process, lost on restart |
| Production (PostgreSQL) | `PostgresSaver` | JSONB, transactional, time-travel |
| Production (AWS) | `DynamoDBSaver` | Metadata in DynamoDB, large payloads in S3 |
| Production (MongoDB) | `MongoDBStore` | Good for document-heavy state |

### LangGraph — supervisor multi-agent pattern
```python
from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor
from langgraph.prebuilt import create_react_agent

# Use capable model for supervisor, cheap model for workers
supervisor_llm = ChatOpenAI(model="gpt-4o")       # routing decisions
worker_llm = ChatOpenAI(model="gpt-4o-mini")       # 60-70% cost reduction

research_agent = create_react_agent(
    model=worker_llm,
    tools=[web_search, read_document],
    name="research_expert",
    prompt="You are a research specialist...",
)
analyst_agent = create_react_agent(
    model=worker_llm,
    tools=[run_analysis, generate_chart],
    name="analyst_expert",
    prompt="You are a data analyst...",
)

workflow = create_supervisor(
    [research_agent, analyst_agent],
    model=supervisor_llm,
    prompt="Route tasks to the appropriate specialist...",
)
app = workflow.compile(checkpointer=PostgresSaver.from_conn_string(DB_URL))
```

Supervisor cost note: every supervisor turn = one full LLM call. If you have 2 agents doing simple sequential work, a plain LCEL pipeline is cheaper and more predictable.

### LangGraph — fault tolerance (RetryPolicy + TimeoutPolicy)
```python
from langgraph.pregel import RetryPolicy

# Per-node retry with backoff — catches transient API failures
graph.add_node(
    "llm_call",
    llm_node,
    retry=RetryPolicy(
        max_attempts=3,
        initial_interval=1.0,
        backoff_factor=2.0,
        jitter=True,
        retry_on=(RateLimitError, APIConnectionError),
    ),
)
```

### Observability — LangSmith (mandatory in production)
```python
import os
# Set these in environment — never hardcode
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "..."          # from AWS Secrets Manager
os.environ["LANGCHAIN_PROJECT"] = "proj-prod"

# Custom metadata on runs — enables filtering and dashboards
from langchain_core.callbacks import LangChainTracer
tracer = LangChainTracer(
    project_name="proj-prod",
    tags=["environment:prod", "service:orchestrator"],
)
result = await chain.ainvoke(inputs, config={"callbacks": [tracer]})
```

Tracing strategy:
- **Dev**: full tracing on every run — debug prompts and logic
- **Prod**: sampled tracing (10–20% of traffic) + full tracing on errors
- Set alerts in LangSmith on error rate, latency P99, and eval score thresholds
- Online evals run on sampled production traces — detect drift before users report it
- LangSmith integrates with OpenTelemetry if team already has Grafana/Datadog

### LLMOps / CI-CD pipeline for LLM apps

#### 3-layer eval architecture (run cheapest-first)

```
Layer 1 — Score direction     ~$0.002/case  Haiku      CI gate: block PR on fail
Layer 2 — Batch regression    ~$0.04 total  Haiku      Catches global calibration drift
Layer 3 — LLM-as-judge        ~$0.005/case  Sonnet     Nightly only (@pytest.mark.eval_deep)
```

```python
# evals/test_quality.py — complete 3-layer pattern
import statistics
from typing import Any
import pytest
from app.agents.quality_analyzer import run_quality_analysis

# ── Layer 1: one test per direction ───────────────────────────────────────────
@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"]) for c in [
        {"id": "good-1", "min_score": 0.70,
         "title": "...", "content": "..."},   # personal story, specific numbers
    ]
])
@pytest.mark.asyncio
async def test_good_posts_score_high(case: dict[str, Any]) -> None:
    report = await run_quality_analysis(run_id=f"eval-{case['id']}",
                                        title=case["title"], content=case["content"])
    assert report.score >= case["min_score"]

@pytest.mark.parametrize("case", [
    pytest.param(c, id=c["id"]) for c in [
        {"id": "bad-1", "max_score": 0.55,
         "title": "In This Article: ...", "content": "..."},  # buzzword soup
    ]
])
@pytest.mark.asyncio
async def test_bad_posts_score_low(case: dict[str, Any]) -> None:
    report = await run_quality_analysis(run_id=f"eval-{case['id']}",
                                        title=case["title"], content=case["content"])
    assert report.score <= case["max_score"]

# ── Layer 2: cohort means — use fixture from conftest.py ──────────────────────
@pytest.mark.asyncio
async def test_good_cohort_mean(good_cases: list[dict]) -> None:
    """Mean >= 0.68 (0.02 slack from 0.70 target — catches drift not one outlier)."""
    scores = [(await run_quality_analysis(run_id=f"eval-{c['id']}",
               title=c["title"], content=c["content"])).score
              for c in good_cases[:4]]
    assert statistics.mean(scores) >= 0.68

@pytest.mark.asyncio
async def test_cohort_separation(good_cases: list[dict], bad_cases: list[dict]) -> None:
    """Gap >= 0.15 — if this fails, the analyzer can't distinguish quality."""
    good = [... for c in good_cases[:3]]   # same pattern
    bad  = [... for c in bad_cases[:3]]
    assert statistics.mean(good) - statistics.mean(bad) >= 0.15

# ── Layer 3: LLM-as-judge (nightly) ───────────────────────────────────────────
@pytest.mark.eval_deep
@pytest.mark.asyncio
async def test_revision_prompt_is_specific(bad_cases: list[dict]) -> None:
    generic = ["improve your writing", "make it better", "be more engaging"]
    report = await run_quality_analysis(run_id="eval-deep-0", **bad_cases[0])
    hits = [p for p in generic if p in report.revision_prompt.lower()]
    assert len(hits) == 0
    assert len(report.revision_prompt) >= 100
```

```python
# evals/conftest.py — dataset fixtures + stateless DB mock
import json
from pathlib import Path
from unittest.mock import AsyncMock
import pytest

_DS = Path(__file__).parent / "datasets" / "quality_analyzer.jsonl"
DATASET = [json.loads(l) for l in _DS.read_text().splitlines() if l.strip()]

@pytest.fixture
def good_cases() -> list[dict]:
    return [c for c in DATASET if c["label"] == "good"]

@pytest.fixture
def bad_cases() -> list[dict]:
    return [c for c in DATASET if c["label"] == "bad"]

@pytest.fixture(autouse=True)
def mock_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip MongoDB writes — evals must be stateless."""
    monkeypatch.setattr("app.agents.base.get_db", AsyncMock(return_value=AsyncMock()))
```

```toml
# pyproject.toml — eval gate config
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "evals"]
markers = [
    "eval_deep: slow LLM-as-judge tests — run nightly, not on every PR",
]

[tool.setuptools.packages.find]
include = ["app*"]   # evals/ is not a distributable package — prevents multi-package error
```

```yaml
# .github/workflows/eval.yml — CI gate (path-filtered, cheap)
name: eval-gate
on:
  pull_request:
    branches: [master]
    paths:
      - "backend/app/agents/**"
      - "backend/evals/**"
      - "backend/pyproject.toml"

jobs:
  eval:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest evals/ -v -m "not eval_deep" --timeout=120
        env:
          ANTHROPIC_API_KEY:      ${{ secrets.ANTHROPIC_API_KEY }}
          LANGCHAIN_TRACING_V2:   "true"
          LANGCHAIN_API_KEY:      ${{ secrets.LANGCHAIN_API_KEY }}
          LANGCHAIN_PROJECT:      "project-name-ci"
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: pytest-cache
          path: backend/.pytest_cache/
```

```python
# evals/langsmith_eval.py — visual eval in LangSmith UI
import asyncio, json, sys
from pathlib import Path
from langsmith import Client
from langsmith.evaluation import evaluate
from app.agents.quality_analyzer import run_quality_analysis

DATASET_NAME = "quality-analyzer-v1"

def upload_dataset_if_missing(client: Client) -> None:
    if any(d.name == DATASET_NAME for d in client.list_datasets()):
        return
    ds_path = Path(__file__).parent / "datasets" / "quality_analyzer.jsonl"
    cases = [json.loads(l) for l in ds_path.read_text().splitlines() if l.strip()]
    dataset = client.create_dataset(DATASET_NAME)
    client.create_examples(
        inputs=[{"title": c["title"], "content": c["content"]} for c in cases],
        outputs=[{"label": c["label"], "threshold": c.get("min_score", c.get("max_score"))} for c in cases],
        dataset_id=dataset.id,
    )

def run_analyzer_sync(inputs: dict) -> dict:
    report = asyncio.run(run_quality_analysis(run_id="langsmith-eval",
                                              title=inputs["title"], content=inputs["content"]))
    return {"score": report.score, "issues": len(report.issues)}

def score_direction_evaluator(run, example) -> dict:
    score = run.outputs["score"]
    label = example.outputs["label"]
    threshold = example.outputs["threshold"]
    if label == "good":
        passed = score >= threshold
    else:
        passed = score <= threshold
    return {"key": "score_direction", "score": 1.0 if passed else 0.0}

def run_eval(experiment_prefix: str = "manual") -> None:
    client = Client()
    upload_dataset_if_missing(client)
    results = evaluate(
        run_analyzer_sync,
        data=DATASET_NAME,
        evaluators=[score_direction_evaluator],
        experiment_prefix=experiment_prefix,
    )
    mean = results.stats["score_direction"]["mean"]
    print(f"Score direction accuracy: {mean:.2%}")
    assert mean >= 0.75, f"Eval failed — {mean:.2%} below 0.75 threshold"

if __name__ == "__main__":
    run_eval(sys.argv[1] if len(sys.argv) > 1 else "manual")
```

CI/CD rules:
- Curated dataset of 20–200 cases per agent committed as JSONL in `evals/datasets/`
- CI gate runs Layer 1 + 2 only (`-m "not eval_deep"`) — keeps runs under 5 min, cost under $0.05
- Layer 3 (`eval_deep`) runs nightly or on prompt file changes only
- Path filter in workflow — don't run evals on docs/config-only PRs
- `autouse` mock_db fixture in conftest — evals must never depend on a running database
- Gate threshold: score_direction accuracy >= 75% (not 100% — LLM output has variance)
- Upload eval results to LangSmith for visual diff between experiments

### RAG — production architecture
```python
# RULE: always separate ingestion pipeline from retrieval pipeline
# Combining them causes re-indexing latency to hit query paths

# Ingestion service (runs on schedule or event trigger)
async def ingest_document(doc: Document) -> None:
    chunks = text_splitter.split_documents([doc])
    embeddings = await embed_model.aembed_documents([c.page_content for c in chunks])
    await vector_store.aadd_documents(chunks)

# Retrieval chain (query path — never triggers ingestion)
retriever = vector_store.as_retriever(
    search_type="mmr",           # max marginal relevance for diversity
    search_kwargs={"k": 6, "fetch_k": 20},
)
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | llm
    | StrOutputParser()
)
```

RAG production rules:
- Hybrid search (dense + BM25 sparse) outperforms pure vector search for precise entity lookup
- Cache embeddings at application layer — avoid recomputing for identical strings
- Use `ConversationSummaryBufferMemory` for long sessions — compresses history to stay under token limit
- Redis (`RedisChatMessageHistory`) for high-throughput session memory; PostgreSQL for complex queries
- Never store raw PII in vector store — hash or pseudonymize before chunking

### Security — LangChain production hardening
```python
# Rule: treat ALL LLM output as untrusted — same as user input
# CVE-2025-68664 (LangGrinch, CVSS 9.3): prompt injection via additional_kwargs
# can exfiltrate env vars through serialized streaming responses

# Guardrails as middleware — intercept before LLM processing
from langchain_core.runnables import RunnableLambda

def input_guardrail(inputs: dict) -> dict:
    text = inputs.get("question", "")
    if contains_injection_pattern(text) or detect_pii(text):
        raise ValueError("Input blocked by guardrail")
    return inputs

safe_chain = RunnableLambda(input_guardrail) | rag_chain

# Human-in-the-loop for high-stakes tool calls
from langgraph.checkpoint.memory import MemorySaver
app = graph.compile(
    checkpointer=checkpointer,
    interrupt_before=["send_email", "delete_record", "charge_payment"],
)
```

Security rules:
- Treat `additional_kwargs`, `response_metadata`, tool outputs, and retrieved docs as untrusted
- Each tool gets minimum permissions — never share IAM roles or DB credentials across tools
- Execute risky tools in sandboxed environments (Docker, Lambda, E2B)
- Input validation before LLM call (saves cost + prevents injection)
- Output filtering before sending to users (prevents data leakage)
- Patch `langchain-core` promptly — check installed version matches pinned requirements

### Repo structure (LangChain / LangGraph monorepo)
```
project/
├── agents/
│   ├── supervisor/         ← supervisor graph definition
│   ├── research/           ← research specialist agent
│   └── analyst/            ← analyst specialist agent
├── chains/                 ← LCEL chains (RAG, summarization, etc.)
├── tools/                  ← @tool-decorated functions (one file per domain)
├── memory/                 ← checkpointer setup, store configuration
├── evals/
│   ├── datasets/           ← JSONL evaluation datasets (committed)
│   └── test_quality.py     ← LangSmith eval + pytest thresholds
├── prompts/                ← prompt templates (versioned, never inline)
├── config.py               ← model selection, env vars — no hardcoding
└── tests/                  ← unit tests (mock LLM with deterministic output)
```

### Model selection by role (cost discipline)
| Role | Model tier | Rationale |
|------|-----------|-----------|
| Supervisor / orchestrator | GPT-4o / Claude Sonnet | Complex routing, reasoning |
| Specialist workers | GPT-4o-mini / Claude Haiku | Focused tasks, 60-70% cheaper |
| Embedding | text-embedding-3-small | Cost-effective, sufficient accuracy |
| Eval judge | GPT-4o | Accuracy matters for eval signal |

Always parameterize model names — never hardcode `"gpt-4o"` inline in chain files.

### Local LLM — Ollama cost-control switch (production pattern)

Single env var `USE_LOCAL_LLM=true` routes the entire pipeline to a local model via Ollama.
All agents call `get_llm(role)` — never instantiate `ChatAnthropic` directly.

```python
# app/agents/llm_factory.py
from langchain_core.language_models import BaseChatModel
from app.config import settings

def get_model_name(role: str = "worker") -> str:
    if settings.use_local_llm:
        return settings.local_llm_model          # e.g. "llama3.2"
    return settings.supervisor_model if role == "supervisor" else settings.worker_model

def get_llm(role: str = "worker", **kwargs: object) -> BaseChatModel:
    if settings.use_local_llm:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.local_llm_model,
            base_url=settings.local_llm_base_url,
            **kwargs,
        )
    from langchain_anthropic import ChatAnthropic
    model = settings.supervisor_model if role == "supervisor" else settings.worker_model
    return ChatAnthropic(model=model, api_key=settings.anthropic_api_key, **kwargs)
```

```python
# Every agent — same pattern, zero branching in business logic
model_name = get_model_name("worker")
tracker    = AgentTokenTracker(agent_name="...", run_id=run_id, model=model_name)
llm        = get_llm("worker", callbacks=[tracker]).with_structured_output(MyModel)
result     = await llm.ainvoke(messages)
```

```yaml
# docker-compose.yml — Ollama as opt-in profile
  ollama:
    image: ollama/ollama
    ports: ["11434:11434"]
    volumes: [ollama_data:/root/.ollama]
    profiles: [local-llm]   # only starts with: docker compose --profile local-llm up

volumes:
  ollama_data:
```

```toml
# pyproject.toml
dependencies = [
    "langchain-anthropic>=0.3.0",
    "langchain-ollama>=0.2.0",    # only imported when USE_LOCAL_LLM=true
]
```

```bash
# Workflow to test locally with llama3.2
docker compose --profile local-llm up ollama -d
docker compose exec ollama ollama pull llama3.2
USE_LOCAL_LLM=true uvicorn app.main:app --reload
```

Rules:
- `_DEFAULT_PRICING = (0.0, 0.0)` in cost tracker — local/unknown models never report phantom costs
- `langchain-ollama` is always installed but only imported at call time (lazy import in factory)
- `local_llm_base_url = "http://ollama:11434"` inside Docker, `"http://localhost:11434"` outside
- `USE_LOCAL_LLM` is the **only** code path that changes — never add `if use_local_llm:` branches inside agents

---

### FastAPI SSE — live streaming from background task to browser

Pattern: `BackgroundTasks` triggers the long-running pipeline, `EventSource` on the frontend
consumes a MongoDB-backed SSE stream. No WebSocket, no polling.

```python
# backend — FastAPI SSE endpoint (already in pipeline.py)
@router.get("/pipeline/runs/{run_id}/stream")
async def stream_logs(run_id: str, request: Request) -> StreamingResponse:
    async def event_generator():
        db = get_db()
        seen_count = 0
        terminal = {"completed", "failed"}
        while True:
            if await request.is_disconnected():
                break
            logs = await (
                db.agent_logs
                  .find({"run_id": run_id}, {"_id": 0}, sort=[("timestamp", 1)])
                  .skip(seen_count).to_list(length=100)
            )
            for log in logs:
                seen_count += 1
                yield f"data: {json.dumps(log, default=str)}\n\n"
            run = await db.pipeline_runs.find_one({"run_id": run_id}, {"_id": 0, "status": 1})
            if run and run.get("status") in terminal:
                yield 'data: {"__done__": true}\n\n'
                break
            await asyncio.sleep(1.5)
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

```typescript
// frontend — api.ts: expose EventSource as first-class method
streamLogs: (runId: string): EventSource =>
  new EventSource(`${BASE}/pipeline/runs/${runId}/stream`),
```

```typescript
// frontend — React hook: EventSource replaces setInterval polling
const esRef = useRef<EventSource | null>(null);

useEffect(() => {
  if (phase !== "running" || !runId) return;

  const es = api.streamLogs(runId);
  esRef.current = es;

  es.onmessage = (event: MessageEvent<string>) => {
    const data = JSON.parse(event.data) as Record<string, unknown>;
    if (data.__done__) {
      es.close(); esRef.current = null;
      setPhase("done");
      return;
    }
    setLogs((prev) => [...prev, data as AgentLog]);
  };

  es.onerror = () => {
    es.close(); esRef.current = null;
    setPhase("done");    // connection dropped — pipeline already finished or crashed
  };

  return () => { es.close(); esRef.current = null; };  // cleanup on unmount
}, [phase, runId]);
```

SSE rules:
- `__done__: true` sentinel closes the stream — never rely on connection drop to detect completion
- `X-Accel-Buffering: no` header is required when Nginx sits in front (otherwise it buffers the stream)
- `EventSource` does NOT support custom headers — if you need auth, pass token as query param
- `onerror` fires on network drop AND when server closes — always close + transition state in handler
- Never use `setInterval` polling when an SSE stream is available — polling creates N×2 DB round trips per minute; SSE uses one open connection

---

### Prompt versioning — git-native (production standard)

Prompts are code. Store them as `.txt` files in `prompts/`, version in git, and gate every
change through the eval CI pipeline. Never hardcode prompt strings inside agent files.

```
backend/
├── prompts/
│   ├── quality_analyzer_system.txt
│   ├── quality_analyzer_human.txt
│   ├── content_generator_system.txt
│   ├── content_generator_human_initial.txt
│   └── content_generator_human_revision.txt   ← {title}, {content}, {score} etc.
└── app/
    └── prompt_loader.py                        ← loads all .txt at startup, caches in dict
```

```python
# app/prompt_loader.py — startup loader with fail-fast and template wrapper
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_CACHE: dict[str, str] = {p.stem: p.read_text(encoding="utf-8") for p in _PROMPTS_DIR.glob("*.txt")}

if not _CACHE:
    raise RuntimeError(f"No prompt files found in {_PROMPTS_DIR}")

def load_prompt(name: str) -> str:
    """Raw text — use as SystemMessage content."""
    try:
        return _CACHE[name]
    except KeyError:
        raise KeyError(f"Prompt '{name}' not found. Available: {sorted(_CACHE.keys())}") from None

class _PromptTemplate:
    def __init__(self, text: str, name: str) -> None:
        self._text, self._name = text, name
    def format(self, **kwargs: object) -> str:
        try:
            return self._text.format(**kwargs)
        except KeyError as e:
            raise KeyError(f"Prompt '{self._name}' missing variable {e}") from e

def load_template(name: str) -> _PromptTemplate:
    """Formattable template — call .format(**vars) to inject variables."""
    return _PromptTemplate(load_prompt(name), name)
```

```python
# In any agent — clean, no inline strings
messages = [
    SystemMessage(content=load_prompt("quality_analyzer_system")),
    HumanMessage(content=load_template("quality_analyzer_human").format(
        title=title, content=content,
    )),
]
```

```yaml
# .github/workflows/eval.yml — prompt change triggers eval gate automatically
paths:
  - "backend/app/agents/**"
  - "backend/prompts/**"        # ← any .txt change runs the full eval suite
  - "backend/evals/**"
  - "backend/pyproject.toml"
```

**LangChain Hub** — the cloud/team-collaboration layer on top of local files:
```python
from langchain import hub
# Push a new version (creates a content-hash version ID)
hub.push("your-org/quality-analyzer-system", ChatPromptTemplate.from_template(text))
# Pull a specific version by hash — reproducible, pinned
prompt = hub.pull("your-org/quality-analyzer-system:abc123f")
```

| Approach | Where prompts live | Version ID | Works offline | When to use |
|---|---|---|---|---|
| Local `.txt` + git | `prompts/` in repo | git commit SHA | Yes | Solo or small team |
| LangChain Hub | LangSmith cloud | content hash | No | Multi-team, non-engineer editors |

Rules:
- One file per prompt — never combine system + human in the same file
- Template variables use Python `.format()` syntax: `{title}`, `{content}` — not Jinja2 or f-strings
- `load_prompt` raises `KeyError` on missing file at startup — fail fast, never silently return wrong prompt
- When a prompt changes, the CI gate re-runs automatically via the path filter — you get a score diff in LangSmith before merge
- The git diff of a prompt file IS the changelog — no separate docs needed

---

### Code review checklist (LangChain/LangGraph)
- No legacy `LLMChain` / `ConversationChain` — use LCEL or LangGraph
- Structured output via `.with_structured_output(PydanticModel)` — no raw text parsing
- Async methods used in async contexts (`.ainvoke`, `.astream`) — no blocking `.invoke` in FastAPI handlers
- Each LangGraph node is a pure function — no side effects beyond returning new state
- Thread IDs are user/session scoped — never reuse across users
- Checkpointer configured for production (not `MemorySaver`)
- LangSmith tracing enabled and project name set per environment
- All prompts in `prompts/` directory — none hardcoded in agent files
- Eval dataset updated when new edge cases are discovered
- `get_llm(role)` factory used everywhere — no direct `ChatAnthropic` instantiation in agents
- `load_prompt()` / `load_template()` used in agents — no inline prompt strings
