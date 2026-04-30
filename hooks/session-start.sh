#!/usr/bin/env bash
# OpenHarness SessionStart Hook
# Injects harness-core context when a harness workspace is detected

set -euo pipefail

# Determine plugin root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Check if harness workspace is active
STATE_FILE=".claude/harness-state.json"

# Sub-agent detection: compare session_id from hook input against state file.
# If state already has a different session_id claimed, this is a sub-agent — skip injection.
if [[ -f "$STATE_FILE" ]]; then
  HOOK_INPUT=$(cat 2>/dev/null || true)
  if [[ -n "$HOOK_INPUT" ]]; then
    HOOK_SESSION=$(printf '%s' "$HOOK_INPUT" | jq -r '.session_id // empty' 2>/dev/null || true)
    STATE_SESSION=$(jq -r '.session_id // empty' "$STATE_FILE" 2>/dev/null || true)
    if [[ -n "$HOOK_SESSION" && -n "$STATE_SESSION" && "$STATE_SESSION" != "$HOOK_SESSION" ]]; then
      # Sub-agent: state already claimed by main harness session
      exit 0
    fi
  fi
fi

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

# Read state summary as formatted JSON (compact for context budget)
STATE_SUMMARY=$(jq -c '.' "$STATE_FILE" 2>/dev/null || cat "$STATE_FILE")

# Build context injection template
CONTEXT_TEMPLATE='<EXTREMELY_IMPORTANT>
You are in an active OpenHarness workspace.

**Below is the full content of the harness-core skill — your behavioral foundation for this session:**

CORE_CONTENT_PLACEHOLDER

**Current harness state:**

STATE_SUMMARY_PLACEHOLDER

Read .claude/harness/mission.md, .claude/harness/playbook.md, and .claude/harness/eval-criteria.md before taking any action.
</EXTREMELY_IMPORTANT>'

# Use jq for safe JSON construction — no manual escaping needed
CONTEXT=$(printf '%s' "$CONTEXT_TEMPLATE" | jq -Rs . | jq -r --arg core "$CORE_CONTENT" --arg state "$STATE_SUMMARY" 'gsub("CORE_CONTENT_PLACEHOLDER"; $core) | gsub("STATE_SUMMARY_PLACEHOLDER"; $state)')

# Output context injection — platform-aware, using jq for safe JSON construction
if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  jq -n --arg ctx "$CONTEXT" '{"additional_context": $ctx}'
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  jq -n --arg ctx "$CONTEXT" '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": $ctx}}'
else
  jq -n --arg ctx "$CONTEXT" '{"additionalContext": $ctx}'
fi

exit 0
