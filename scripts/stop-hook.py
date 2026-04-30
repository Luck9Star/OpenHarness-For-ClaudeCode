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
import shutil
from pathlib import Path

# Import shared utilities from harness_utils (same directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from harness_utils import find_state_file, read_state, write_state


def find_loop_done(transcript_path):
    """Check if the last assistant message contains <promise>LOOP_DONE</promise>."""
    if not os.path.exists(transcript_path):
        print(f"OpenHarness stop-hook: Transcript not found ({transcript_path}). Allowing exit.", file=sys.stderr)
        return None

    try:
        with open(transcript_path) as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 65536))
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

    # Read state
    state = read_state()
    if not state:
        sys.exit(0)

    # Extract fields with safe defaults
    status = state.get("status", "idle")
    execution_mode = state.get("execution_mode", "single")
    consecutive_failures = state.get("consecutive_failures", 0)
    circuit_breaker = state.get("circuit_breaker", "off")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 0)
    state_session = state.get("session_id", "")
    loop_mode = state.get("loop_mode", "in-session")  # "in-session" or "clean"

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

    # Session isolation: only the main harness session gets the loop behavior.
    # Sub-agents (different session_id) must be allowed to exit freely.
    hook_session = hook_input.get("session_id", "")

    if not state_session and hook_session:
        # First stop-hook call: claim this session as the harness owner
        state["session_id"] = hook_session
        state_session = hook_session
        write_state(state)
    elif state_session and hook_session and state_session != hook_session:
        # Different session (sub-agent) — allow exit immediately
        sys.exit(0)

    # --- Exit conditions ---

    # Helper: archive workspace before removing state file on terminal exit
    def _archive_and_remove():
        """Archive workspace files and remove state file using Python directly (no subprocess)."""
        state_path = find_state_file()
        if not state_path:
            return

        # Read state to get task_name for archive directory naming
        existing = read_state(state_path)
        task_name = existing.get("task_name", "untitled") if existing else "untitled"
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_dir = Path.cwd() / ".claude/harness/archive" / f"{task_name}-{timestamp}"

        harness_dir = Path.cwd() / ".claude/harness"
        files_to_archive = ["mission.md", "playbook.md", "eval-criteria.md", "progress.md"]

        archived = []
        for f in files_to_archive:
            src = harness_dir / f
            if src.exists():
                archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(archive_dir / f))
                archived.append(f)

        logs_src = harness_dir / "logs"
        if logs_src.exists() and any(logs_src.iterdir()):
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(logs_src), str(archive_dir / "logs"))
            archived.append("logs/")

        if archived and state_path.exists():
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(state_path), str(archive_dir / "harness-state.json"))
            archived.append("harness-state.json")

        # Remove state file if it still exists (e.g., nothing was archived)
        if state_path.exists():
            try:
                os.remove(str(state_path))
            except OSError:
                pass

    # Circuit breaker tripped (defense-in-depth: both breaker and status are checked,
    # but only breaker is the authoritative exit signal — status:"failed" is transient
    # during normal retry flow and should NOT trigger loop exit alone)
    if circuit_breaker == "tripped":
        print("OpenHarness: Circuit breaker tripped — loop stopped. Manual intervention required.", file=sys.stderr)
        _archive_and_remove()
        sys.exit(0)

    # Max iterations reached
    if max_iterations > 0 and iteration >= max_iterations:
        print(f"OpenHarness: Max iterations ({max_iterations}) reached. Loop exiting.")
        _archive_and_remove()
        sys.exit(0)

    # Paused for human review
    if status == "paused":
        print("OpenHarness: Paused for human review. Resume with /harness-dev --resume.")
        sys.exit(0)

    # Mission complete
    if status == "mission_complete":
        print("OpenHarness: Mission complete. Loop exiting.")
        _archive_and_remove()
        sys.exit(0)

    # Stuck detection: status 'running' from previous crash — auto-recover
    if status == "running":
        state["status"] = "idle"
        write_state(state)
        print("OpenHarness: Detected stale 'running' status — recovered to idle", file=sys.stderr)
        status = "idle"

    # --- Check transcript for LOOP_DONE ---
    transcript_path = hook_input.get("transcript_path", "")
    promise = find_loop_done(transcript_path)

    if promise is None:
        sys.exit(0)

    if promise == "LOOP_DONE":
        print("OpenHarness: Detected <promise>LOOP_DONE</promise>. Mission complete — loop exiting.")
        _archive_and_remove()
        sys.exit(0)

    # --- None of the exit conditions met — block exit and continue ---

    next_iteration = iteration + 1

    # Increment iteration counter
    state["iteration"] = next_iteration
    write_state(state)

    # Lightweight cleanup: remove temp files to prevent accumulation
    try:
        import glob as _glob
        state_file = find_state_file()
        if state_file:
            harness_dir = str(state_file.parent / "harness")
            for pattern in ["*.tmp", "*.bak", "*.swp"]:
                for f in _glob.glob(os.path.join(harness_dir, "**", pattern), recursive=True):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
    except Exception:
        pass  # cleanup is best-effort, never block the loop

    # Shared continuation instructions (compressed)
    _continuation_common = (
        "Read current state files for context. "
        "Continue the current step per SKILL protocol. "
        "After completing the step and running validation, end your turn — the loop will continue automatically."
    )

    # Build continuation prompt — explicitly instruct agent to ignore prior context
    # to prevent stale "completed" signals from earlier iterations
    if loop_mode == "clean":
        continuation_prompt = (
            "IMPORTANT: Run /compact FIRST to clear stale context from previous iterations.\n"
            + _continuation_common
        )
    else:
        continuation_prompt = (
            "IMPORTANT: Ignore ALL prior conversation context — it may contain stale information from previous iterations. "
            + _continuation_common
        )

    system_msg = (
        f"[Harness iteration {next_iteration}] | mode: {execution_mode} | loop: {loop_mode} | status: {status} | "
        f"failures: {consecutive_failures} | To stop when genuinely done: output <promise>LOOP_DONE</promise>\n"
        f"CRITICAL RULE: State file (.claude/harness-state.json) is the ONLY source of truth. "
        f"Prior conversation context is STALE — do NOT use it to judge whether work is already done. "
        f"Always re-read state files at the start of every iteration."
    )

    # Context health suggestions (in-session mode only — clean mode forces /compact every iteration)
    if loop_mode != "clean":
        current_step = state.get("current_step", "Step 1")
        step_match = re.search(r"Step (\d+)", current_step)
        step_num = int(step_match.group(1)) if step_match else 1
        if step_num > 1 and step_num % 4 == 1:
            system_msg += (
                f"\n\n[Context Health] You are at Step {step_num}. "
                f"Consider running /compact to compress stale context before continuing. "
                f"This prevents earlier iterations' completion messages from misleading you."
            )

    response = {
        "decision": "block",
        "reason": continuation_prompt,
        "systemMessage": system_msg,
    }
    print(json.dumps(response))


if __name__ == "__main__":
    main()
