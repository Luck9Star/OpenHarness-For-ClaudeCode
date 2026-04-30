#!/usr/bin/env python3
"""Shared utilities for OpenHarness CLI scripts and hooks.

Provides common state file operations: find, read, write (atomic), and
file locking. All CLI scripts in scripts/ and hooks/ should import from
here instead of re-implementing these functions.
"""

import sys
import json
import os
import fcntl
from pathlib import Path

# Project boundary markers: stop upward search when one is found
BOUNDARY_MARKERS = [".git", "CLAUDE.md", ".claude-plugin"]

STATE_FILE = ".claude/harness-state.json"


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


def _with_lock(path, operation):
    """Execute operation with exclusive file lock."""
    lock_path = str(path) + ".lock"
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            return operation()
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            try:
                os.unlink(lock_path)
            except OSError:
                pass
