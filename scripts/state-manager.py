#!/usr/bin/env python3
"""State manager for OpenHarness workspace.

Reads and writes .claude/harness-state.json — the L1 pointer index
that persists across /loop iterations.

Usage:
    state-manager.py read          Print current state as JSON
    state-manager.py init [opts]   Initialize a new state file
                                      --force  Overwrite even if active workspace exists
                                      --loop-mode in-session|clean  Context strategy per iteration
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
import os
import re
from datetime import datetime
from pathlib import Path

STATE_FILE = ".claude/harness-state.json"
LOG_FILE = ".claude/harness/logs/execution_stream.log"

MAX_STATE_SIZE = 2048


# Project boundary markers: stop upward search when one is found
BOUNDARY_MARKERS = [".git", "CLAUDE.md", ".claude-plugin"]


def find_state_file():
    """Find state file, searching up from cwd. Stops at project boundaries."""
    p = Path.cwd()
    while p != p.parent:
        candidate = p / STATE_FILE
        if candidate.exists():
            return candidate
        # Stop at project boundaries (avoids crossing into parent projects)
        if any((p / m).exists() for m in BOUNDARY_MARKERS):
            return None
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
    """Write JSON state file atomically (temp + rename)."""
    target = path or find_state_file()
    if not target:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    os.replace(tmp, target)


def cmd_read(args):
    """Print current state as JSON."""
    path = find_state_file()
    if not path:
        print(json.dumps({"error": "no active harness workspace"}))
        sys.exit(1)
    print(json.dumps(read_state(path), indent=2))


def _auto_archive(state_path, existing_state):
    """Auto-archive workspace files when force-overwriting via init.

    This is a structural safety net: regardless of whether the agent
    follows the SKILL.md protocol's Step 1.5, the workspace files
    are archived before they can be overwritten.
    """
    import shutil
    task_name = existing_state.get("task_name", "untitled")
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

    logs_src = harness_dir / "logs"
    if logs_src.exists() and any(logs_src.iterdir()):
        shutil.copytree(str(logs_src), str(archive_dir / "logs"))
        archived.append("logs/")

    if archived:
        if state_path.exists():
            shutil.move(str(state_path), str(archive_dir / "harness-state.json"))
            archived.append("harness-state.json")
        print(json.dumps({
            "status": "auto-archived",
            "path": str(archive_dir),
            "files": archived,
            "task_name": task_name
        }))
    else:
        archive_dir.rmdir()


def cmd_init(args):
    """Initialize a new state file."""
    # Validate task_name: reject flag-like values (e.g. "--mission")
    if args and args[0].startswith("-"):
        print(f"Error: task_name must not start with '-', got '{args[0]}'. "
              f"Usage: state-manager.py init \"TASK_NAME\" [--force] [--mode MODE] ...", file=sys.stderr)
        sys.exit(1)
    task_name = args[0] if args else "untitled"
    execution_mode = "single"
    verify_instruction = ""
    max_iterations = 0
    skills = ""
    loop_mode = "in-session"
    cycle_steps = None
    min_cycles = 0
    max_cycles = 0
    max_concurrency = 3
    force = False

    def _validate_value(flag, value):
        if value.startswith("--"):
            print(f"Error: {flag} requires a value, got flag-like '{value}'", file=sys.stderr)
            sys.exit(1)

    i = 1
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            _validate_value("--mode", args[i + 1])
            execution_mode = args[i + 1]
            i += 2
        elif args[i] == "--verify" and i + 1 < len(args):
            _validate_value("--verify", args[i + 1])
            verify_instruction = args[i + 1]
            i += 2
        elif args[i] == "--max-iterations" and i + 1 < len(args):
            _validate_value("--max-iterations", args[i + 1])
            try:
                max_iterations = int(args[i + 1])
            except ValueError:
                print(f"Error: --max-iterations requires a number, got '{args[i+1]}'", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--skills" and i + 1 < len(args):
            _validate_value("--skills", args[i + 1])
            skills = args[i + 1]
            i += 2
        elif args[i] == "--loop-mode" and i + 1 < len(args):
            _validate_value("--loop-mode", args[i + 1])
            if args[i + 1] not in ("in-session", "clean"):
                print(f"Error: --loop-mode must be 'in-session' or 'clean', got '{args[i+1]}'", file=sys.stderr)
                sys.exit(1)
            loop_mode = args[i + 1]
            i += 2
        elif args[i] == "--cycle-steps" and i + 1 < len(args):
            _validate_value("--cycle-steps", args[i + 1])
            try:
                parts = args[i + 1].split(",")
                if len(parts) != 2:
                    raise ValueError("need exactly 2 numbers separated by comma")
                cycle_steps = [int(parts[0]), int(parts[1])]
                if cycle_steps[0] < 1 or cycle_steps[1] <= cycle_steps[0]:
                    raise ValueError("cycle_end must be > cycle_start, both >= 1")
            except ValueError as e:
                print(f"Error: --cycle-steps requires 'start,end' (e.g., '1,3'), got '{args[i+1]}': {e}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--min-cycles" and i + 1 < len(args):
            _validate_value("--min-cycles", args[i + 1])
            try:
                min_cycles = int(args[i + 1])
                if min_cycles < 0:
                    raise ValueError("must be >= 0")
            except ValueError as e:
                print(f"Error: --min-cycles requires a non-negative integer, got '{args[i+1]}': {e}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--max-cycles" and i + 1 < len(args):
            _validate_value("--max-cycles", args[i + 1])
            try:
                max_cycles = int(args[i + 1])
                if max_cycles < 0:
                    raise ValueError("must be >= 0")
            except ValueError as e:
                print(f"Error: --max-cycles requires a non-negative integer, got '{args[i+1]}': {e}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--max-concurrency" and i + 1 < len(args):
            _validate_value("--max-concurrency", args[i + 1])
            try:
                max_concurrency = int(args[i + 1])
                if max_concurrency < 1:
                    raise ValueError("must be >= 1")
            except ValueError as e:
                print(f"Error: --max-concurrency requires a positive integer, got '{args[i+1]}': {e}", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif args[i] == "--force":
            force = True
            i += 1
        else:
            i += 1

    state_dir = Path.cwd() / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_path = state_dir / "harness-state.json"

    # Check if we are overwriting a previous mission (for log reset below)
    is_reinit = False
    if state_path.exists():
        try:
            existing = json.loads(state_path.read_text())
            existing_status = existing.get("status", "")
            existing_task = existing.get("task_name", "unknown")
            is_reinit = force or existing_status in ("mission_complete", "failed")
            if not force and existing_status not in ("mission_complete", "failed"):
                print(
                    f"ERROR: Active workspace exists (task: '{existing_task}', "
                    f"status: {existing_status}). Use --force to overwrite.",
                    file=sys.stderr
                )
                sys.exit(1)
            # Auto-archive: when force-overwriting, archive old workspace FIRST
            # so old data is never lost regardless of agent protocol compliance.
            # NOTE: We archive whenever force=True and workspace exists, even if
            # the task name is the same (re-init is the most common scenario).
            if force and state_path.exists():
                _auto_archive(state_path, existing)
        except (json.JSONDecodeError, OSError):
            pass  # corrupted file, allow overwrite

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    state = {
        "status": "idle",
        "execution_mode": execution_mode,
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
        "started_at": now,
        "loop_mode": loop_mode,
        "cycle_steps": cycle_steps,
        "cycle_iteration": 0,
        "min_cycles": min_cycles,
        "max_cycles": max_cycles,
        "knowledge_index": [],
        "current_phase": None,
        "step_statuses": {},
        "max_concurrency": max_concurrency,
    }

    write_state(state, state_path)

    # Ensure log directory exists
    log_dir = Path.cwd() / ".claude/harness" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "execution_stream.log"

    # When overwriting a previous mission, reset the execution_stream.log
    # and clean ALL stale deliverable files from logs/ to prevent old reports
    # from confusing the agent into thinking work is done.
    # This is the authoritative cleanup point — runs AFTER state file is written,
    # so there's no risk of mid-process data loss.
    if is_reinit:
        # Clean all files in logs/ directory (archive already copied them for safekeeping)
        for stale_file in log_dir.iterdir():
            if stale_file.is_file():
                stale_file.unlink()
        log_path.write_text(f"# Execution Stream Log\n# Initialized {now}\n\n")
    elif not log_path.exists():
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


def _log_path():
    """Derive log path from state file location (not CWD-dependent)."""
    state_path = find_state_file()
    if state_path:
        return state_path.parent / "harness" / "logs" / "execution_stream.log"
    return Path.cwd() / LOG_FILE


def cmd_log(args):
    """Append a log entry to execution stream (L3)."""
    if not args:
        print("Usage: state-manager.py log MESSAGE", file=sys.stderr)
        sys.exit(1)
    message = " ".join(args)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path = _log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[{now}] {message}\n")


def cmd_step_advance(args):
    """Advance current_step to next step number, cycling if cycle_steps is set."""
    path = find_state_file()
    if not path:
        sys.exit(1)
    state = read_state(path)
    current = state.get("current_step", "Step 1")
    match = re.search(r"Step (\d+)", current)
    if match:
        current_num = int(match.group(1))
        next_num = current_num + 1

        # Cycle logic: if cycle_steps is set (e.g., [1, 3]) and we've passed
        # the cycle end, wrap back to cycle start instead of advancing past it
        cycle_steps = state.get("cycle_steps", None)
        if cycle_steps and isinstance(cycle_steps, list) and len(cycle_steps) == 2:
            cycle_start, cycle_end = int(cycle_steps[0]), int(cycle_steps[1])
            if current_num == cycle_end:
                # Enforce max_cycles: prevent infinite looping
                max_cycles = int(state.get("max_cycles", 0))
                cycle_iter = int(state.get("cycle_iteration", 0)) + 1
                if max_cycles > 0 and cycle_iter >= max_cycles:
                    state["circuit_breaker"] = "tripped"
                    state["status"] = "failed"
                    write_state(state, path)
                    print(f"Max cycles ({max_cycles}) reached. Circuit breaker tripped.")
                    return

                next_num = cycle_start
                # Track cycle iterations
                state["cycle_iteration"] = cycle_iter

        state["current_step"] = f"Step {next_num}"
        write_state(state, path)
        print(f"Advanced to Step {next_num}")
    else:
        print(f"Cannot parse step from: {current}", file=sys.stderr)
        sys.exit(1)


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
    state["status"] = "failed"
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
    log_path = _log_path()
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

    # Archive logs directory — COPY (not move) for safety.
    # The authoritative cleanup happens in cmd_init (is_reinit block).
    # We use copy here so that if init fails after archive, the original
    # workspace is still intact and recoverable.
    logs_src = harness_dir / "logs"
    if logs_src.exists() and any(logs_src.iterdir()):
        shutil.copytree(str(logs_src), str(archive_dir / "logs"))
        archived.append("logs/")

    if archived:
        # Archive the state file itself — prevents zombie state where
        # archive removed workspace files but state file still claims active task
        if state_path.exists():
            shutil.move(str(state_path), str(archive_dir / "harness-state.json"))
            archived.append("harness-state.json")

        print(json.dumps({
            "status": "archived",
            "path": str(archive_dir),
            "files": archived,
            "task_name": task_name
        }))
    else:
        # Nothing to archive, remove empty dir
        archive_dir.rmdir()
        # Still remove state file if it exists with no workspace files
        if state_path.exists():
            state_path.unlink()
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
    if cmd in ("--help", "-h"):
        print(__doc__)
        sys.exit(0)
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        print(f"Available: {', '.join(COMMANDS.keys())}", file=sys.stderr)
        sys.exit(1)
    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
