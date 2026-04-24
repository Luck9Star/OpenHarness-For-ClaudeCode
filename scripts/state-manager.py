#!/usr/bin/env python3
"""State manager for OpenHarness workspace.

Reads and writes .claude/harness-state.json — the L1 pointer index
that persists across /loop iterations.

Usage:
    state-manager.py read          Print current state as JSON
    state-manager.py init [opts]   Initialize a new state file
                                      --force  Overwrite even if active workspace exists
    state-manager.py update KEY VAL  Update a field
    state-manager.py log MESSAGE   Append to execution stream (L3)
    state-manager.py report SUBTASK STRATEGY VERIFICATION STATE_TARGET
                                   Write structured round report (L3)
    state-manager.py step-advance  Advance current_step by 1
    state-manager.py fail          Increment consecutive_failures
    state-manager.py reset-fail    Reset consecutive_failures to 0
    state-manager.py trip-breaker  Set circuit_breaker to tripped
    state-manager.py archive       Archive current workspace files
"""

import sys
import json
import re
from datetime import datetime
from pathlib import Path

STATE_FILE = ".claude/harness-state.json"
LOG_FILE = ".claude/harness/logs/execution_stream.log"

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
    """Print current state as JSON."""
    path = find_state_file()
    if not path:
        print(json.dumps({"error": "no active harness workspace"}))
        sys.exit(1)
    print(json.dumps(read_state(path), indent=2))


def cmd_init(args):
    """Initialize a new state file."""
    task_name = args[0] if args else "untitled"
    execution_mode = "single"
    verify_instruction = ""
    max_iterations = 0
    worktree = "off"
    skills = ""
    force = False

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
        elif args[i] == "--force":
            force = True
            i += 1
        else:
            i += 1

    state_dir = Path.cwd() / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "harness-state.json"

    # Overwrite protection: refuse to clobber an active workspace
    if state_path.exists() and not force:
        try:
            existing = json.loads(state_path.read_text())
            existing_status = existing.get("status", "")
            existing_task = existing.get("task_name", "unknown")
            if existing_status not in ("mission_complete", "failed"):
                print(
                    f"ERROR: Active workspace exists (task: '{existing_task}', "
                    f"status: {existing_status}). Use --force to overwrite.",
                    file=sys.stderr
                )
                sys.exit(1)
        except (json.JSONDecodeError, OSError):
            pass  # corrupted file, allow overwrite

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
        "knowledge_index": [],
    }

    write_state(state, state_path)

    # Ensure log directory exists
    log_dir = Path.cwd() / ".claude/harness" / "logs"
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
    """Update a state field: state-manager.py update KEY VALUE"""
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
    """Append a log entry to execution stream (L3)."""
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
    """Advance current_step to next step number."""
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
    """Increment consecutive_failures."""
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
    """Reset consecutive_failures to 0."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    state["consecutive_failures"] = 0
    state["circuit_breaker"] = "off"
    write_state(state, path)
    print("Failures reset to 0")


def cmd_trip_breaker(args):
    """Force-trip the circuit breaker."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    state["circuit_breaker"] = "tripped"
    write_state(state, path)
    print("Circuit breaker TRIPPED")


def cmd_report(args):
    """Write a structured round report to execution stream (L3).

    Usage: state-manager.py report <subtask> <strategy> <verification> <state_target>
    """
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


def cmd_archive(args):
    """Archive current workspace files before overwrite."""
    import shutil
    state_path = find_state_file()
    if not state_path:
        print("No workspace to archive", file=sys.stderr)
        sys.exit(0)  # not an error, just nothing to archive

    state = read_state(state_path)
    task_name = state.get("task_name", "untitled")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = Path.cwd() / ".claude/harness/archive" / f"{task_name}-{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    harness_dir = Path.cwd() / ".claude/harness"
    files_to_archive = ["mission.md", "playbook.md", "eval-criteria.md", "progress.md"]

    archived = []
    for f in files_to_archive:
        src = harness_dir / f
        if src.exists():
            shutil.move(str(src), str(archive_dir / f))
            archived.append(f)

    # Archive logs directory
    logs_src = harness_dir / "logs"
    if logs_src.exists() and any(logs_src.iterdir()):
        shutil.copytree(str(logs_src), str(archive_dir / "logs"))
        # Don't remove original logs - they may be needed
        archived.append("logs/")

    if archived:
        print(json.dumps({
            "status": "archived",
            "path": str(archive_dir),
            "files": archived,
            "task_name": task_name
        }))
    else:
        # Nothing to archive, remove empty dir
        archive_dir.rmdir()
        print(json.dumps({"status": "nothing_to_archive"}))


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
    "archive": cmd_archive,
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
