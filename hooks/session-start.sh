#!/usr/bin/env bash
# OpenHarness SessionStart Hook
# Injects harness-core context when a harness workspace is detected

set -euo pipefail

# Determine plugin root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Check if harness workspace is active
STATE_FILE=".claude/harness-state.local.md"

if [[ ! -f "$STATE_FILE" ]]; then
  # No active harness workspace — plugin stays dormant
  exit 0
fi

# Read harness-core skill content
CORE_SKILL="${PLUGIN_ROOT}/skills/harness-core/SKILL.md"
if [[ ! -f "$CORE_SKILL" ]]; then
  echo "Error: harness-core/SKILL.md not found" >&2
  exit 0
fi

CORE_CONTENT=$(cat "$CORE_SKILL")

# Read state summary (frontmatter only, first 30 lines to stay under context budget)
STATE_SUMMARY=$(head -n 30 "$STATE_FILE")

# Escape for JSON embedding
escape_for_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

CORE_ESCAPED=$(escape_for_json "$CORE_CONTENT")
STATE_ESCAPED=$(escape_for_json "$STATE_SUMMARY")

# Build context injection
CONTEXT="<EXTREMELY_IMPORTANT>\nYou are in an active OpenHarness workspace.\n\n**Below is the full content of the harness-core skill — your behavioral foundation for this session:**\n\n${CORE_ESCAPED}\n\n**Current harness state:**\n\n${STATE_ESCAPED}\n\nRead mission.md, playbook.md, and eval-criteria.md before taking any action.\n</EXTREMELY_IMPORTANT>"

# Output context injection — platform-aware
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$CONTEXT"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$CONTEXT"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$CONTEXT"
fi

exit 0
