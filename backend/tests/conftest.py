import os

# Stub env vars so pydantic-settings loads without real credentials.
# These values are never sent to any external service in unit tests.
# setdefault: only sets if NOT already in the environment (CI can override).
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-unit-tests")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")

# Force Anthropic mode for unit tests that test escalation logic.
# Without this, USE_DEEPSEEK=true from the root .env leaks in and
# breaks tests that assert Sonnet escalation at revision_number >= 2.
os.environ.setdefault("USE_DEEPSEEK", "false")
os.environ.setdefault("USE_LOCAL_LLM", "false")
