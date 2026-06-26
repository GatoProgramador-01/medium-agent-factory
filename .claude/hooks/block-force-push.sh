#!/usr/bin/env bash
# Reads JSON from stdin, checks if the bash command is a force push
CMD=$(cat | jq -r '.tool_input.command // empty' 2>/dev/null)

# Match: git push --force, git push -f, git push origin main --force, etc.
if echo "$CMD" | grep -qE 'git[[:space:]]+(.*[[:space:]])?push[[:space:]].*(-f[[:space:]]|-f$|--force[[:space:]]|--force$)'; then
  echo "Force push blocked — this would overwrite remote history." >&2
  echo "If you really need this, run it manually in the terminal (not via Claude)." >&2
  exit 2
fi
exit 0
