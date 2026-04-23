#!/usr/bin/env python3
"""State manager for OpenHarness workspace.

Reads and writes .claude/harness-state.local.md — the L1 pointer index
that persists across /loop iterations.

Usage:
    state-manager.py read          Print current state as JSON
    state-manager.py init [opts]   Initialize a new state file
    state-manager.py update KEY VAL  Update a frontmatter field
    state-manager.py log MESSAGE   Append to execution stream (L3)
    state-manager.py step-advance  Advance current_step by 1
    state-manager.py fail          Increment consecutive_failures
    state-manager.py reset-fail    Reset consecutive_failures to 0
    state-manager.py trip-breaker  Set circuit_breaker to tripped
"""

import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path

STATE_FILE = ".claude/harness-state.local.md"
LOG_FILE = "logs/execution_stream.log"

# Maximum state file size in bytes (2KB target)
MAX_STATE_SIZE = 2048


def find_state_file():
    """Find state file, searching up from cwd."""
    p = Path.cwd()
    while p != p.parent:
        candidate = p / STATE_FILE
        if candidate.exists():
            return candidate
        p = p.parent
    return None


def read_frontmatter(path):
    """Parse YAML-like frontmatter from markdown file."""
    text = path.read_text()
    match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def write_frontmatter(path, fm):
    """Write frontmatter back to state file, preserving body."""
    text = path.read_text()
    # Remove existing frontmatter
    body = re.sub(r'^---\n.*?\n---\n?', '', text, count=1, flags=re.DOTALL)
    # Build new frontmatter
    lines = ['---']
    for key, val in fm.items():
        if ' ' in str(val) or '"' in str(val):
            lines.append(f'{key}: "{val}"')
        else:
            lines.append(f'{key}: {val}')
    lines.append('---')
    new_text = '\n'.join(lines) + '\n' + body
    path.write_text(new_text)


def cmd_read(args):
    """Print current state as JSON."""
    path = find_state_file()
    if not path:
        print(json.dumps({"error": "no active harness workspace"}))
        sys.exit(1)
    fm = read_frontmatter(path)
    print(json.dumps(fm, indent=2))


def cmd_init(args):
    """Initialize a new state file."""
    task_name = args[0] if args else "untitled"
    execution_mode = "single"
    verify_command = ""
    max_iterations = 0

    i = 1
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            execution_mode = args[i + 1]
            i += 2
        elif args[i] == "--verify" and i + 1 < len(args):
            verify_command = args[i + 1]
            i += 2
        elif args[i] == "--max-iterations" and i + 1 < len(args):
            max_iterations = int(args[i + 1])
            i += 2
        else:
            i += 1

    state_dir = Path.cwd() / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "harness-state.local.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f'''---
status: idle
execution_mode: {execution_mode}
current_step: "Step 1"
consecutive_failures: 0
total_executions: 0
circuit_breaker: off
iteration: 0
max_iterations: {max_iterations}
session_id: ""
verify_command: "{verify_command}"
last_execution_time: "{now}"
---

# Harness State

## System Status

| Field | Value |
|---|---|
| Task Name | `{task_name}` |
| Execution Mode | `{execution_mode}` |
| Current Status | `idle` |
| Verify Command | `{verify_command}` |
| Last Execution | `{now}` |
| Total Executions | `0` |
| Consecutive Failures | `0` |
| Circuit Breaker | `off` |

## Execution Pointer

| Field | Value |
|---|---|
| Current Step | `Step 1 (Not started)` |
| Completed Steps | `None` |

## Knowledge Index

| Topic | Path | Updated |
|---|---|---|
| _(none yet)_ | - | - |
'''

    state_path.write_text(content)

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
    """Update a frontmatter field: state-manager.py update KEY VALUE"""
    if len(args) < 2:
        print("Usage: state-manager.py update KEY VALUE", file=sys.stderr)
        sys.exit(1)
    path = find_state_file()
    if not path:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    fm = read_frontmatter(path)
    fm[args[0]] = ' '.join(args[1:])
    write_frontmatter(path, fm)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fm["last_execution_time"] = now
    write_frontmatter(path, fm)


def cmd_log(args):
    """Append a log entry to execution stream (L3)."""
    if not args:
        print("Usage: state-manager.py log MESSAGE", file=sys.stderr)
        sys.exit(1)
    message = ' '.join(args)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = Path.cwd() / LOG_FILE
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, 'a') as f:
        f.write(f"[{now}] {message}\n")


def cmd_step_advance(args):
    """Advance current_step to next step number."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    fm = read_frontmatter(path)
    current = fm.get("current_step", "Step 1")
    match = re.search(r'Step (\d+)', current)
    if match:
        next_num = int(match.group(1)) + 1
        fm["current_step"] = f"Step {next_num}"
        write_frontmatter(path, fm)
        print(f"Advanced to Step {next_num}")
    else:
        print(f"Cannot parse step from: {current}", file=sys.stderr)


def cmd_fail(args):
    """Increment consecutive_failures."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    fm = read_frontmatter(path)
    failures = int(fm.get("consecutive_failures", 0)) + 1
    fm["consecutive_failures"] = str(failures)
    if failures >= 3:
        fm["circuit_breaker"] = "tripped"
    fm["status"] = "failed"
    write_frontmatter(path, fm)
    print(f"Failures: {failures}, Circuit breaker: {fm.get('circuit_breaker', 'off')}")


def cmd_reset_fail(args):
    """Reset consecutive_failures to 0."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    fm = read_frontmatter(path)
    fm["consecutive_failures"] = "0"
    fm["circuit_breaker"] = "off"
    write_frontmatter(path, fm)
    print("Failures reset to 0")


def cmd_trip_breaker(args):
    """Force-trip the circuit breaker."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    fm = read_frontmatter(path)
    fm["circuit_breaker"] = "tripped"
    write_frontmatter(path, fm)
    print("Circuit breaker TRIPPED")


COMMANDS = {
    "read": cmd_read,
    "init": cmd_init,
    "update": cmd_update,
    "log": cmd_log,
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
