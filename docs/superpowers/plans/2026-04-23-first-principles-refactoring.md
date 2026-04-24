# First Principles Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor OpenHarness from YAML-frontmatter state + split authority to JSON state + unified skill authority, eliminating an entire class of parsing bugs and reducing ~30% code.

**Architecture:** Replace `.claude/harness-state.local.md` (YAML frontmatter) with `.claude/harness-state.json` (JSON). Merge `commands/` into `skills/` for single authority. Replace 153-line bash stop-hook with Python. Delete eval-check.py.

**Tech Stack:** Python 3 (json, subprocess), Bash (thin wrappers), Claude Code plugin system

**Dep graph:** T1 → T2, T1 → T3, T1 → T4, T5 independent, T6 depends on T1+T2+T3+T4+T5

---

## Task 1: Rewrite state-manager.py for JSON state

**Files:**
- Rewrite: `scripts/state-manager.py`
- New test: (inline verification — no test framework in this project)

This is the foundation. All other tasks depend on the state file being JSON.

- [ ] **Step 1: Rewrite state-manager.py**

Replace the entire file. Key changes:
- `STATE_FILE` → `.claude/harness-state.json`
- `read_frontmatter()` → `read_state()` using `json.load()`
- `write_frontmatter()` → `write_state()` using `json.dump()`
- `cmd_init()` writes JSON instead of YAML-frontmatter-in-markdown
- `cmd_update()` updates a JSON key
- All other commands (`read`, `log`, `report`, `step-advance`, `fail`, `reset-fail`, `trip-breaker`) adapted for JSON
- No more escaping logic — JSON handles it natively

```python
#!/usr/bin/env python3
"""State manager for OpenHarness workspace.

Reads and writes .claude/harness-state.json — the L1 pointer index
that persists across /loop iterations.

Usage:
    state-manager.py read          Print current state as JSON
    state-manager.py init [opts]   Initialize a new state file
    state-manager.py update KEY VAL  Update a field
    state-manager.py log MESSAGE   Append to execution stream (L3)
    state-manager.py report SUBTASK STRATEGY VERIFICATION STATE_TARGET
                                   Write structured round report (L3)
    state-manager.py step-advance  Advance current_step by 1
    state-manager.py fail          Increment consecutive_failures
    state-manager.py reset-fail    Reset consecutive_failures to 0
    state-manager.py trip-breaker  Set circuit_breaker to tripped
"""

import sys
import json
import re
from datetime import datetime
from pathlib import Path

STATE_FILE = ".claude/harness-state.json"
LOG_FILE = "logs/execution_stream.log"

MAX_STATE_SIZE = 2048


def find_state_file():
    p = Path.cwd()
    while p != p.parent:
        candidate = p / STATE_FILE
        if candidate.exists():
            return candidate
        p = p.parent
    return None


def read_state(path=None):
    """Read JSON state file."""
    target = path or find_state_file()
    if not target:
        return {}
    try:
        return json.loads(target.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def write_state(state, path=None):
    """Write JSON state file."""
    target = path or find_state_file()
    if not target:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, indent=2) + "\n")


def cmd_read(args):
    path = find_state_file()
    if not path:
        print(json.dumps({"error": "no active harness workspace"}))
        sys.exit(1)
    print(json.dumps(read_state(path), indent=2))


def cmd_init(args):
    task_name = args[0] if args else "untitled"
    execution_mode = "single"
    verify_instruction = ""
    max_iterations = 0
    worktree = "off"
    skills = ""

    i = 1
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            execution_mode = args[i + 1]
            i += 2
        elif args[i] == "--verify" and i + 1 < len(args):
            verify_instruction = args[i + 1]
            i += 2
        elif args[i] == "--max-iterations" and i + 1 < len(args):
            max_iterations = int(args[i + 1])
            i += 2
        elif args[i] == "--worktree":
            worktree = "on"
            i += 1
        elif args[i] == "--skills" and i + 1 < len(args):
            skills = args[i + 1]
            i += 2
        else:
            i += 1

    state_dir = Path.cwd() / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "harness-state.json"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    state = {
        "status": "idle",
        "execution_mode": execution_mode,
        "worktree": worktree,
        "current_step": "Step 1",
        "consecutive_failures": 0,
        "total_executions": 0,
        "circuit_breaker": "off",
        "iteration": 0,
        "max_iterations": max_iterations,
        "session_id": "",
        "verify_instruction": verify_instruction,
        "skills": skills,
        "last_execution_time": now,
        "task_name": task_name,
    }

    write_state(state, state_path)

    # Ensure log directory exists
    log_dir = Path.cwd() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "execution_stream.log"
    if not log_path.exists():
        log_path.write_text(f"# Execution Stream Log\n# Initialized {now}\n\n")

    print(json.dumps({
        "status": "initialized",
        "path": str(state_path),
        "execution_mode": execution_mode
    }))


def cmd_update(args):
    if len(args) < 2:
        print("Usage: state-manager.py update KEY VALUE", file=sys.stderr)
        sys.exit(1)
    path = find_state_file()
    if not path:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    state = read_state(path)
    state[args[0]] = " ".join(args[1:])
    state["last_execution_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_state(state, path)


def cmd_log(args):
    if not args:
        print("Usage: state-manager.py log MESSAGE", file=sys.stderr)
        sys.exit(1)
    message = " ".join(args)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = Path.cwd() / LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{now}] {message}\n")


def cmd_step_advance(args):
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    current = state.get("current_step", "Step 1")
    match = re.search(r"Step (\d+)", current)
    if match:
        next_num = int(match.group(1)) + 1
        state["current_step"] = f"Step {next_num}"
        write_state(state, path)
        print(f"Advanced to Step {next_num}")
    else:
        print(f"Cannot parse step from: {current}", file=sys.stderr)


def cmd_fail(args):
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    failures = int(state.get("consecutive_failures", 0)) + 1
    state["consecutive_failures"] = failures
    if failures >= 3:
        state["circuit_breaker"] = "tripped"
    state["status"] = "failed"
    write_state(state, path)
    print(f"Failures: {failures}, Circuit breaker: {state.get('circuit_breaker', 'off')}")


def cmd_reset_fail(args):
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    state["consecutive_failures"] = 0
    state["circuit_breaker"] = "off"
    write_state(state, path)
    print("Failures reset to 0")


def cmd_trip_breaker(args):
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    state["circuit_breaker"] = "tripped"
    write_state(state, path)
    print("Circuit breaker TRIPPED")


def cmd_report(args):
    if len(args) < 4:
        print("Usage: state-manager.py report <subtask> <strategy> <verification> <state_target>", file=sys.stderr)
        sys.exit(1)
    subtask, strategy, verification, state_target = args[0], args[1], args[2], args[3]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = Path.cwd() / LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{now}] ## Round Report\n")
        f.write(f"[{now}] - Subtask: {subtask}\n")
        f.write(f"[{now}] - Strategy: {strategy}\n")
        f.write(f"[{now}] - Verification: {verification}\n")
        f.write(f"[{now}] - State Target: {state_target}\n")


COMMANDS = {
    "read": cmd_read,
    "init": cmd_init,
    "update": cmd_update,
    "log": cmd_log,
    "report": cmd_report,
    "step-advance": cmd_step_advance,
    "fail": cmd_fail,
    "reset-fail": cmd_reset_fail,
    "trip-breaker": cmd_trip_breaker,
}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(1)
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('scripts/state-manager.py', doraise=True)" && echo "OK"`
Expected: `OK`

- [ ] **Step 3: Test init command**

Run:
```bash
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py init test-task --mode single --verify 'ensure output contains "OK"' --max-iterations 5
```
Expected: JSON output with `"status": "initialized"`, `"execution_mode": "single"`

- [ ] **Step 4: Verify JSON state file is valid**

Run: `cat /tmp/.claude/harness-state.json | python3 -m json.tool`
Expected: Valid JSON with all fields, `verify_instruction` containing escaped quotes

- [ ] **Step 5: Test read/update/step-advance/fail round-trip**

```bash
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py read
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py update status running
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py step-advance
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py fail
cd /tmp && python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py read
```
Expected: After all commands, `status: failed`, `current_step: Step 2`, `consecutive_failures: 1`, verify_instruction still has quotes intact.

- [ ] **Step 6: Clean up test state**

Run: `rm -rf /tmp/.claude`

- [ ] **Step 7: Commit**

```bash
git add scripts/state-manager.py
git commit -m "refactor: rewrite state-manager.py for JSON state format

Replace YAML-frontmatter-in-markdown state file with standard JSON.
Eliminates all YAML parsing/escaping bugs (3 custom parsers → 0).
State file changes from .claude/harness-state.local.md to .claude/harness-state.json.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Rewrite stop-hook — bash thin wrapper + Python logic

**Files:**
- Rewrite: `hooks/stop-hook.sh` (thin wrapper)
- Create: `scripts/stop-hook.py`
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Write scripts/stop-hook.py**

The Python script receives hook input JSON via stdin, reads state, checks transcript, outputs hook response JSON.

```python
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
        return None  # Can't determine, allow exit

    try:
        with open(transcript_path) as f:
            content = f.read()
    except OSError as e:
        print(f"OpenHarness stop-hook: Cannot read transcript: {e}. Allowing exit.", file=sys.stderr)
        return None

    # Find all assistant message text blocks
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
        # No valid input, allow exit
        sys.exit(0)

    cwd = os.getcwd()

    # Read state
    state = read_state(cwd)
    if state is None:
        # No state file or parse error — allow exit
        sys.exit(0)

    # Extract fields with safe defaults
    status = state.get("status", "idle")
    execution_mode = state.get("execution_mode", "single")
    consecutive_failures = state.get("consecutive_failures", 0)
    circuit_breaker = state.get("circuit_breaker", "off")
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 0)
    state_session = state.get("session_id", "")

    # Validate numeric fields — default to safe values instead of deleting state
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
        # Different session owns this harness — do not interfere
        sys.exit(0)

    # --- Exit conditions ---

    # Circuit breaker tripped
    if circuit_breaker == "tripped":
        print("OpenHarness: Circuit breaker tripped — loop stopped. Manual intervention required.", file=sys.stderr)
        # Remove state file on definitive exit
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
        # Couldn't read transcript — allow exit without deleting state
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
    continuation_prompt = "Continue harness execution. Read .claude/harness-state.json for current state, then read mission.md, playbook.md, eval-criteria.md in cache-optimal order. Execute the current step from the playbook."

    system_msg = f"[Harness iteration {next_iteration}] | mode: {execution_mode} | status: {status} | failures: {consecutive_failures} | To stop when genuinely done: output <promise>LOOP_DONE</promise>"

    response = {
        "decision": "block",
        "reason": continuation_prompt,
        "systemMessage": system_msg,
    }
    print(json.dumps(response))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write thin wrapper hooks/stop-hook.sh**

```bash
#!/bin/bash
# OpenHarness Stop Hook — thin wrapper
# Delegates all logic to Python for JSON-safe processing

set -euo pipefail

# Read hook input from stdin, pass to Python
exec python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stop-hook.py"
```

- [ ] **Step 3: Update hooks/hooks.json**

The Stop hook command changes from `bash` to still call the wrapper (which execs python):
```json
{
  "Stop": [
    {
      "matcher": "",
      "hooks": [
        {
          "type": "command",
          "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/stop-hook.sh\""
        }
      ]
    }
  ]
}
```
Note: hooks.json doesn't change — the wrapper script path is the same, it just delegates to Python now.

- [ ] **Step 4: Verify syntax**

Run:
```bash
python3 -c "import py_compile; py_compile.compile('scripts/stop-hook.py', doraise=True)" && echo "stop-hook.py OK"
bash -n hooks/stop-hook.sh && echo "stop-hook.sh OK"
```
Expected: Both `OK`

- [ ] **Step 5: Test stop-hook with simulated input**

Create a test state file and transcript, then run the hook:
```bash
cd /tmp
mkdir -p .claude
echo '{"status":"running","execution_mode":"single","consecutive_failures":0,"circuit_breaker":"off","iteration":0,"max_iterations":0,"session_id":"","current_step":"Step 1"}' > .claude/harness-state.json
echo '{"session_id":"","transcript_path":"/tmp/test_transcript.jsonl"}' | python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/stop-hook.py
```
Expected: JSON output with `"decision": "block"` (no transcript = allow exit, but status "running" was auto-recovered to idle). Actually, with no transcript the hook returns `None` from `find_loop_done` and exits 0. Let's also test with a transcript containing assistant messages.

- [ ] **Step 6: Test with mock transcript**

```bash
cd /tmp
echo '{"role":"user","message":{"content":[{"type":"text","text":"go"}]}}' > /tmp/test_transcript.jsonl
echo '{"role":"assistant","message":{"content":[{"type":"text","text":"Working on step 1..."}]}}' >> /tmp/test_transcript.jsonl
echo '{"session_id":"","transcript_path":"/tmp/test_transcript.jsonl"}' | python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/stop-hook.py
```
Expected: JSON output with `"decision": "block"`, iteration incremented to 1.

- [ ] **Step 7: Test LOOP_DONE detection**

```bash
cd /tmp
echo '{"role":"assistant","message":{"content":[{"type":"text","text":"Done! <promise>LOOP_DONE</promise>"}]}}' > /tmp/test_transcript.jsonl
# Re-init state for this test
echo '{"status":"idle","execution_mode":"single","consecutive_failures":0,"circuit_breaker":"off","iteration":1,"max_iterations":0,"session_id":"","current_step":"Step 2"}' > .claude/harness-state.json
echo '{"session_id":"","transcript_path":"/tmp/test_transcript.jsonl"}' | python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/stop-hook.py
```
Expected: `OpenHarness: Detected <promise>LOOP_DONE</promise>` printed to stderr, exit 0, state file deleted.

- [ ] **Step 8: Clean up test files**

```bash
rm -rf /tmp/.claude /tmp/test_transcript.jsonl
```

- [ ] **Step 9: Commit**

```bash
git add hooks/stop-hook.sh scripts/stop-hook.py hooks/hooks.json
git commit -m "refactor: rewrite stop-hook from bash to python

153 lines of bash (grep/sed/perl for JSON) replaced by ~150 lines of python
with native json module. Thin bash wrapper delegates to python script.
State is preserved (never deleted) on transient errors.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Update remaining scripts for JSON state

**Files:**
- Modify: `scripts/setup-harness-loop.sh`
- Modify: `hooks/pretooluse.py`
- Modify: `hooks/session-start.sh`
- Modify: `scripts/cleanup.py`

- [ ] **Step 1: Update setup-harness-loop.sh**

Change all references from `harness-state.local.md` to `harness-state.json`. The script already calls `state-manager.py init`, so the change is mainly in the verification step at the end:

Find and replace in `scripts/setup-harness-loop.sh`:
- `STATE_FILE=".claude/harness-state.local.md"` → `STATE_FILE=".claude/harness-state.json"`
- The `if [[ ! -f "$STATE_FILE" ]]` check and any validation logic remains the same

- [ ] **Step 2: Update pretooluse.py**

Change `PROTECTED_FILES` to reference the new JSON file name:
```python
PROTECTED_FILES = {
    ".claude/harness-state.json",
}
```
Note: `mission.md` is removed from PROTECTED_FILES — the hook's protection was easily bypassed via Bash and blocked legitimate `/harness-edit --mission` use. Mission boundary enforcement moves to agent instructions (already in harness-core SKILL.md Rule 7).

Also update `find_harness_root()`:
```python
def find_harness_root():
    p = Path.cwd()
    while p != p.parent:
        if (p / ".claude" / "harness-state.json").exists():
            return p
        p = p.parent
    return None
```

- [ ] **Step 3: Update session-start.sh**

This script checks if a harness workspace exists and outputs status info. Change the state file reference from `.claude/harness-state.local.md` to `.claude/harness-state.json` and use `jq` instead of `grep`/`sed` for field extraction. Replace frontmatter parsing with `jq -r` calls.

- [ ] **Step 4: Update cleanup.py**

Change all references from `harness-state.local.md` to `harness-state.json`. The cleanup script reads the state file, so update the read logic to use `json.load()` instead of the custom frontmatter parser.

- [ ] **Step 5: Verify all scripts parse**

```bash
python3 -c "import py_compile; py_compile.compile('hooks/pretooluse.py', doraise=True)" && echo "pretooluse.py OK"
python3 -c "import py_compile; py_compile.compile('scripts/cleanup.py', doraise=True)" && echo "cleanup.py OK"
bash -n scripts/setup-harness-loop.sh && echo "setup-harness-loop.sh OK"
bash -n hooks/session-start.sh && echo "session-start.sh OK"
```

- [ ] **Step 6: Commit**

```bash
git add scripts/setup-harness-loop.sh hooks/pretooluse.py hooks/session-start.sh scripts/cleanup.py
git commit -m "refactor: update scripts for JSON state format

All references to harness-state.local.md changed to harness-state.json.
pretooluse.py no longer protects mission.md (easily bypassed, blocked /harness-edit).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Delete eval-check.py and update references

**Files:**
- Delete: `scripts/eval-check.py`
- Modify: `skills/harness-eval/SKILL.md` (if it references eval-check.py)

- [ ] **Step 1: Check who references eval-check.py**

```bash
grep -r "eval-check" --include="*.md" --include="*.py" --include="*.sh" .
```

Review each reference and update. The eval-agent already handles verification independently — remove any `eval-check.py` invocations from skill/agent files.

- [ ] **Step 2: Delete eval-check.py**

```bash
git rm scripts/eval-check.py
```

- [ ] **Step 3: Update skill/agent files that reference eval-check.py**

Search and update each file found in Step 1. Replace `eval-check.py` invocations with instructions for eval-agent to perform the checks directly.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: delete eval-check.py middle layer

eval-agent performs all verification independently. The heuristic
file-existence and command-exit-code checks in eval-check.py added
no value beyond what eval-agent can do, and caused false-pass bugs.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Merge commands into skills (authority unification)

**Files:**
- Create: `skills/harness-start/SKILL.md`
- Create: `skills/harness-dev/SKILL.md`
- Create: `skills/harness-edit/SKILL.md`
- Create: `skills/harness-status/SKILL.md`
- Delete: `commands/` directory (entire)
- Delete: `skills/harness-init/SKILL.md`
- Delete: `skills/harness-execute/SKILL.md`

This is the largest structural change. Each new SKILL.md merges the content from its command file and any related skill file, with all references updated for JSON state format.

- [ ] **Step 1: Create skills/harness-start/SKILL.md**

Merge content from:
- `commands/harness-start.md` (argument parsing, from-plan handling)
- `skills/harness-init/SKILL.md` (workspace setup workflow)

The merged file handles: argument parsing → quality preference discovery → template generation → state initialization (via `state-manager.py init`).

Key changes during merge:
- All `harness-state.local.md` → `harness-state.json`
- All `setup-harness-loop.sh` references updated
- Single authoritative source for the /harness-start workflow
- Add frontmatter: `description`, `argument-hint`, `allowed-tools`

- [ ] **Step 2: Create skills/harness-dev/SKILL.md**

Merge content from:
- `commands/harness-dev.md` (argument parsing, mode selection, loop skeleton)
- `skills/harness-execute/SKILL.md` (step-by-step execution workflow, step types)

Key changes during merge:
- All `harness-state.local.md` → `harness-state.json`
- Fix P0-1: `--resume` skips state init (from the earlier bug fix)
- Fix P1: human-review calls `step-advance` before pause (from the earlier bug fix)
- Single authoritative source for the /harness-dev loop

- [ ] **Step 3: Create skills/harness-edit/SKILL.md**

Move content from `commands/harness-edit.md`.

Key changes:
- All `harness-state.local.md` → `harness-state.json`
- P0-2 fix: mission.md edit via Bash+python (from the earlier bug fix)

- [ ] **Step 4: Create skills/harness-status/SKILL.md**

Move content from `commands/harness-status.md`.

Key changes:
- P3 fix: reference `/harness-start` not `/harness-init` (from the earlier bug fix)
- `harness-state.local.md` → `harness-state.json`

- [ ] **Step 5: Delete old directories**

```bash
rm -rf commands/
rm -rf skills/harness-init/
rm -rf skills/harness-execute/
```

- [ ] **Step 6: Update skills/harness-core/SKILL.md**

Change all references:
- `harness-state.local.md` → `harness-state.json`
- "YAML frontmatter" language → "JSON state file"
- Update cache-optimal read order to reference `.json` file

- [ ] **Step 7: Update skills/harness-dream/SKILL.md**

Change all `harness-state.local.md` references to `harness-state.json`.

- [ ] **Step 8: Update skills/harness-eval/SKILL.md**

Change all `harness-state.local.md` references to `harness-state.json`.

- [ ] **Step 9: Update agents/ files**

Check all three agent files for `harness-state.local.md` references:
- `agents/harness-dev-agent.md`
- `agents/harness-eval-agent.md`
- `agents/harness-review-agent.md`

Update any references to the new state file name.

- [ ] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: unify commands into skills, single authority per feature

commands/ directory deleted. Each /harness-* command now maps to exactly
one skills/harness-*/SKILL.md. harness-init merged into harness-start,
harness-execute merged into harness-dev. All state references updated
from .md to .json.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Final verification and cleanup

**Files:**
- Verify all files across the project

- [ ] **Step 1: Verify no stale references remain**

```bash
grep -r "harness-state\.local\.md" --include="*.md" --include="*.py" --include="*.sh" .
grep -r "eval-check\.py" --include="*.md" --include="*.py" --include="*.sh" .
grep -r "frontmatter" --include="*.py" .
```
Expected: Zero matches for all three searches.

- [ ] **Step 2: Verify all Python scripts compile**

```bash
python3 -c "
import py_compile
from pathlib import Path
for f in Path('.').rglob('*.py'):
    py_compile.compile(str(f), doraise=True)
    print(f'{f} OK')
"
```

- [ ] **Step 3: Verify all bash scripts parse**

```bash
bash -n hooks/stop-hook.sh && echo "stop-hook.sh OK"
bash -n hooks/session-start.sh && echo "session-start.sh OK"
bash -n scripts/setup-harness-loop.sh && echo "setup-harness-loop.sh OK"
```

- [ ] **Step 4: Run full init → read → update → advance → fail round-trip**

```bash
cd /tmp && rm -rf .claude logs
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py init round-trip-test --mode dual --verify 'ensure "quotes" work with \\backslashes\\' --max-iterations 10
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py read
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py update status running
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py step-advance
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py fail
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py reset-fail
python3 /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/state-manager.py read
```
Verify: `verify_instruction` contains `ensure "quotes" work with \backslashes\`, `current_step` is `Step 2`, `consecutive_failures` is 0.

- [ ] **Step 5: Verify project line count reduction**

```bash
find . -name '*.py' -o -name '*.sh' -o -name '*.md' | grep -v node_modules | grep -v .git | xargs wc -l | tail -1
```
Expected: ~2900 lines (down from 4165).

- [ ] **Step 6: Final commit if any cleanup needed**

```bash
git add -A
git commit -m "refactor: final cleanup after first-principles refactoring

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```
