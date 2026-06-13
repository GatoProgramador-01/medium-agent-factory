import os

# Provide stub env vars so pydantic-settings can load without real credentials.
# These values are never sent to any external service in unit tests.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-unit-tests")
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
