#!/usr/bin/env bash
# Blocks a git commit if dependency/Dockerfile files changed but docker compose build fails.
# Triggered by Claude Code PreToolUse hook (matcher: Bash(git commit*)).

CHANGED=$(git diff --cached --name-only 2>/dev/null)

NEEDS_BUILD=false
for f in $CHANGED; do
  case "$f" in
    *pyproject.toml|*requirements*.txt|*Dockerfile*|*package.json|*package-lock.json|*docker-compose*.yml)
      NEEDS_BUILD=true
      break
      ;;
  esac
done

if [ "$NEEDS_BUILD" = "true" ]; then
  echo "Dependency/Dockerfile change detected — running docker compose build..."
  docker compose build
  exit_code=$?
  if [ $exit_code -ne 0 ]; then
    echo "Docker build failed — commit blocked. Fix the build error first." >&2
    exit 2
  fi
  echo "Docker build passed."
fi
