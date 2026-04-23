#!/bin/bash

# OpenHarness Stop Hook
# Prevents session exit while a harness loop is active.
# Checks circuit breaker, max iterations, mission completion, and the LOOP_DONE promise.
# If none of the exit conditions are met, blocks exit and feeds a continuation prompt.

set -euo pipefail

# Read hook input from stdin
HOOK_INPUT=$(cat)

# State file is project-scoped (NOT in plugin directory)
STATE_FILE=".claude/harness-state.local.md"

if [[ ! -f "$STATE_FILE" ]]; then
  # No active harness workspace — allow exit
  exit 0
fi

# Parse markdown frontmatter (YAML between ---) and extract values
FRONTMATTER=$(sed -n '/^---$/,/^---$/{ /^---$/d; p; }' "$STATE_FILE")

STATUS=$(echo "$FRONTMATTER" | grep '^status:' | sed 's/status: *//')
EXECUTION_MODE=$(echo "$FRONTMATTER" | grep '^execution_mode:' | sed 's/execution_mode: *//')
CONSECUTIVE_FAILURES=$(echo "$FRONTMATTER" | grep '^consecutive_failures:' | sed 's/consecutive_failures: *//')
CIRCUIT_BREAKER=$(echo "$FRONTMATTER" | grep '^circuit_breaker:' | sed 's/circuit_breaker: *//')
ITERATION=$(echo "$FRONTMATTER" | grep '^iteration:' | sed 's/iteration: *//')
MAX_ITERATIONS=$(echo "$FRONTMATTER" | grep '^max_iterations:' | sed 's/max_iterations: *//')
STATE_SESSION=$(echo "$FRONTMATTER" | grep '^session_id:' | sed 's/session_id: *//' || true)

# Session isolation: match session_id from state vs hook input
HOOK_SESSION=$(echo "$HOOK_INPUT" | jq -r '.session_id // ""')
if [[ -n "$STATE_SESSION" ]] && [[ "$STATE_SESSION" != "$HOOK_SESSION" ]]; then
  # Different session owns this harness — do not interfere
  exit 0
fi

# Validate numeric fields before arithmetic
if [[ ! "$ITERATION" =~ ^[0-9]+$ ]]; then
  echo "OpenHarness stop-hook: State file corrupted — 'iteration' is not a number (got: '$ITERATION')" >&2
  rm "$STATE_FILE"
  exit 0
fi

if [[ ! "$MAX_ITERATIONS" =~ ^[0-9]+$ ]]; then
  echo "OpenHarness stop-hook: State file corrupted — 'max_iterations' is not a number (got: '$MAX_ITERATIONS')" >&2
  rm "$STATE_FILE"
  exit 0
fi

# --- Exit conditions ---

# Circuit breaker tripped — allow exit with warning
if [[ "$CIRCUIT_BREAKER" = "tripped" ]]; then
  echo "OpenHarness: Circuit breaker tripped — loop stopped. Manual intervention required." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Max iterations reached — allow exit
if [[ $MAX_ITERATIONS -gt 0 ]] && [[ $ITERATION -ge $MAX_ITERATIONS ]]; then
  echo "OpenHarness: Max iterations ($MAX_ITERATIONS) reached. Loop exiting."
  rm "$STATE_FILE"
  exit 0
fi

# Paused for human review — allow exit
if [[ "$STATUS" = "paused" ]]; then
  echo "OpenHarness: Paused for human review. Resume with /harness-dev --resume."
  exit 0
fi

# Mission complete — allow exit
if [[ "$STATUS" = "mission_complete" ]]; then
  echo "OpenHarness: Mission complete. Loop exiting."
  rm "$STATE_FILE"
  exit 0
fi

# Stuck detection: status is 'running' from a previous crash — auto-recover to idle
if [[ "$STATUS" = "running" ]]; then
  TEMP_FILE="${STATE_FILE}.tmp.$$"
  sed 's/^status: .*/status: idle/' "$STATE_FILE" > "$TEMP_FILE"
  mv "$TEMP_FILE" "$STATE_FILE"
  echo "OpenHarness: Detected stale 'running' status — recovered to idle" >&2
fi

# --- Check last assistant message for LOOP_DONE promise ---

TRANSCRIPT_PATH=$(echo "$HOOK_INPUT" | jq -r '.transcript_path')

if [[ ! -f "$TRANSCRIPT_PATH" ]]; then
  echo "OpenHarness stop-hook: Transcript not found ($TRANSCRIPT_PATH). Allowing exit." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Check if there are any assistant messages
if ! grep -q '"role":"assistant"' "$TRANSCRIPT_PATH"; then
  echo "OpenHarness stop-hook: No assistant messages in transcript. Allowing exit." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Extract last assistant text block (last 100 assistant lines, capped for perf)
LAST_LINES=$(grep '"role":"assistant"' "$TRANSCRIPT_PATH" | tail -n 100)
if [[ -z "$LAST_LINES" ]]; then
  echo "OpenHarness stop-hook: Could not extract assistant messages. Allowing exit." >&2
  rm "$STATE_FILE"
  exit 0
fi

set +e
LAST_OUTPUT=$(echo "$LAST_LINES" | jq -rs '
  map(.message.content[]? | select(.type == "text") | .text) | last // ""
' 2>&1)
JQ_EXIT=$?
set -e

if [[ $JQ_EXIT -ne 0 ]]; then
  echo "OpenHarness stop-hook: Failed to parse assistant JSON. Allowing exit." >&2
  rm "$STATE_FILE"
  exit 0
fi

# Check for <promise>LOOP_DONE</promise>
PROMISE_TEXT=$(echo "$LAST_OUTPUT" | perl -0777 -pe 's/.*?<promise>(.*?)<\/promise>.*/$1/s; s/^\s+|\s+$//g; s/\s+/ /g' 2>/dev/null || echo "")

if [[ -n "$PROMISE_TEXT" ]] && [[ "$PROMISE_TEXT" = "LOOP_DONE" ]]; then
  echo "OpenHarness: Detected <promise>LOOP_DONE</promise>. Mission complete — loop exiting."
  rm "$STATE_FILE"
  exit 0
fi

# --- None of the exit conditions met — block exit and continue ---

NEXT_ITERATION=$((ITERATION + 1))

# Increment iteration counter in state file
TEMP_FILE="${STATE_FILE}.tmp.$$"
sed "s/^iteration: .*/iteration: $NEXT_ITERATION/" "$STATE_FILE" > "$TEMP_FILE"
mv "$TEMP_FILE" "$STATE_FILE"

# Build continuation prompt
CONTINUATION_PROMPT="Continue harness execution. Read .claude/harness-state.local.md for current state, then read mission.md, playbook.md, eval-criteria.md in cache-optimal order. Execute the current step from the playbook."

SYSTEM_MSG="[Harness iteration $NEXT_ITERATION] | mode: ${EXECUTION_MODE} | status: ${STATUS} | failures: ${CONSECUTIVE_FAILURES} | To stop when genuinely done: output <promise>LOOP_DONE</promise>"

jq -n \
  --arg prompt "$CONTINUATION_PROMPT" \
  --arg msg "$SYSTEM_MSG" \
  '{
    "decision": "block",
    "reason": $prompt,
    "systemMessage": $msg
  }'

exit 0
