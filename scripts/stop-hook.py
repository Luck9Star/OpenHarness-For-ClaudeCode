#!/usr/bin/env python3
"""OpenHarness Stop Hook (Python).

Prevents session exit while a harness loop is active.
Checks circuit breaker, max iterations, mission completion, and the LOOP_DONE promise.
If none of the exit conditions are met, outputs a continuation prompt.

Input: JSON via stdin (hook_input with session_id, transcript_path)
Output: JSON to stdout (optional decision: block with continuation prompt)
"""

import sys
import json
import os
import re

STATE_FILE = ".claude/harness-state.json"


def read_state(cwd):
    """Read JSON state file."""
    path = os.path.join(cwd, STATE_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"OpenHarness stop-hook: State file parse error: {e}. Allowing exit.", file=sys.stderr)
        return None


def find_loop_done(transcript_path):
    """Check if the last assistant message contains <promise>LOOP_DONE</promise>."""
    if not os.path.exists(transcript_path):
        print(f"OpenHarness stop-hook: Transcript not found ({transcript_path}). Allowing exit.", file=sys.stderr)
        return None

    try:
        with open(transcript_path) as f:
            content = f.read()
    except OSError as e:
        print(f"OpenHarness stop-hook: Cannot read transcript: {e}. Allowing exit.", file=sys.stderr)
        return None

    # Transcript is JSONL format (one JSON object per line)
    assistant_texts = []
    for line in content.strip().split("\n"):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("role") == "assistant":
                message = entry.get("message", {})
                content_parts = message.get("content", [])
                if isinstance(content_parts, list):
                    for part in content_parts:
                        if isinstance(part, dict) and part.get("type") == "text":
                            assistant_texts.append(part.get("text", ""))
                elif isinstance(content_parts, str):
                    assistant_texts.append(content_parts)
        except json.JSONDecodeError:
            continue

    if not assistant_texts:
        print("OpenHarness stop-hook: No assistant messages in transcript. Allowing exit.", file=sys.stderr)
        return None

    # Check last assistant text for LOOP_DONE promise
    last_text = assistant_texts[-1]
    match = re.search(r"<promise>(.*?)</promise>", last_text, re.DOTALL)
    if match:
        return match.group(1).strip()

    return ""


def main():
    # Read hook input from stdin
    try:
        hook_input = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = os.getcwd()

    # Read state
    state = read_state(cwd)
    if state is None:
        sys.exit(0)

    # Extract fields with safe defaults
    status = state.get("status", "idle")
    execution_mode = state.get("execution_mode", "single")
    consecutive_failures = state.get("consecutive_failures", 0)
    circuit_breaker = state.get("circuit_breaker", "off")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 0)
    state_session = state.get("session_id", "")

    # Validate numeric fields
    try:
        iteration = int(iteration)
    except (ValueError, TypeError):
        print(f"OpenHarness stop-hook: Invalid 'iteration' field (got: {iteration}) — defaulting to 0", file=sys.stderr)
        iteration = 0

    try:
        max_iterations = int(max_iterations)
    except (ValueError, TypeError):
        print(f"OpenHarness stop-hook: Invalid 'max_iterations' field (got: {max_iterations}) — defaulting to 0", file=sys.stderr)
        max_iterations = 0

    # Session isolation check
    hook_session = hook_input.get("session_id", "")
    if state_session and hook_session and state_session != hook_session:
        sys.exit(0)

    # --- Exit conditions ---

    # Circuit breaker tripped
    if circuit_breaker == "tripped":
        print("OpenHarness: Circuit breaker tripped — loop stopped. Manual intervention required.", file=sys.stderr)
        try:
            os.remove(os.path.join(cwd, STATE_FILE))
        except OSError:
            pass
        sys.exit(0)

    # Max iterations reached
    if max_iterations > 0 and iteration >= max_iterations:
        print(f"OpenHarness: Max iterations ({max_iterations}) reached. Loop exiting.")
        try:
            os.remove(os.path.join(cwd, STATE_FILE))
        except OSError:
            pass
        sys.exit(0)

    # Paused for human review
    if status == "paused":
        print("OpenHarness: Paused for human review. Resume with /harness-dev --resume.")
        sys.exit(0)

    # Mission complete
    if status == "mission_complete":
        print("OpenHarness: Mission complete. Loop exiting.")
        try:
            os.remove(os.path.join(cwd, STATE_FILE))
        except OSError:
            pass
        sys.exit(0)

    # Stuck detection: status 'running' from previous crash — auto-recover
    if status == "running":
        state["status"] = "idle"
        with open(os.path.join(cwd, STATE_FILE), "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        print("OpenHarness: Detected stale 'running' status — recovered to idle", file=sys.stderr)
        status = "idle"

    # --- Check transcript for LOOP_DONE ---
    transcript_path = hook_input.get("transcript_path", "")
    promise = find_loop_done(transcript_path)

    if promise is None:
        sys.exit(0)

    if promise == "LOOP_DONE":
        print("OpenHarness: Detected <promise>LOOP_DONE</promise>. Mission complete — loop exiting.")
        try:
            os.remove(os.path.join(cwd, STATE_FILE))
        except OSError:
            pass
        sys.exit(0)

    # --- None of the exit conditions met — block exit and continue ---

    next_iteration = iteration + 1

    # Increment iteration counter
    state["iteration"] = next_iteration
    with open(os.path.join(cwd, STATE_FILE), "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    # Build continuation prompt
    continuation_prompt = "Continue harness execution. Read .claude/harness-state.json for current state, then read mission.md, playbook.md, eval-criteria.md in cache-optimal order. Execute the NEXT playbook step (only one step). After completing the step and running validation, end your turn — the loop will continue automatically."

    system_msg = f"[Harness iteration {next_iteration}] | mode: {execution_mode} | status: {status} | failures: {consecutive_failures} | To stop when genuinely done: output <promise>LOOP_DONE</promise>"

    response = {
        "decision": "block",
        "reason": continuation_prompt,
        "systemMessage": system_msg,
    }
    print(json.dumps(response))


if __name__ == "__main__":
    main()
