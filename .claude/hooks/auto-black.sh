#!/usr/bin/env bash
# Reads JSON from stdin (Claude Code hook payload), extracts file path, runs black if .py
INPUT=$(cat)
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

case "$FILE" in
  *.py)
    [ -f "$FILE" ] || exit 0
    # Prefer project venv; fall back to system python
    if [ -f "backend/.venv/Scripts/python" ]; then
      PYTHON="backend/.venv/Scripts/python"
    elif [ -f "backend/.venv/bin/python" ]; then
      PYTHON="backend/.venv/bin/python"
    else
      PYTHON="python"
    fi
    "$PYTHON" -m black --quiet "$FILE" 2>/dev/null
    ;;
esac
exit 0
