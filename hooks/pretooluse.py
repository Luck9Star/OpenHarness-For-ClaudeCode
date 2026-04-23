#!/usr/bin/env python3
"""OpenHarness PreToolUse Hook.

Enforces mission.md boundaries on file write operations.
Blocks writes to prohibited paths and framework state files.

Input (via stdin): JSON with tool_name and tool_input fields.
Output: JSON with optional "decision": "block" and "reason" fields,
        or no output (exit 0) to allow the operation.
"""

import sys
import json
import re
from pathlib import Path

# Files that are always write-protected (managed by scripts only)
PROTECTED_FILES = {
    ".claude/harness-state.json",
}

# Tools that modify files and must be checked
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def find_harness_root():
    """Walk up from cwd to find a directory with .claude/harness-state.json."""
    p = Path.cwd()
    while p != p.parent:
        if (p / ".claude" / "harness-state.json").exists():
            return p
        p = p.parent
    return None


def read_prohibited_patterns(mission_path):
    """Extract prohibited operations from mission.md Section 4.

    Returns a list of glob-like patterns or path prefixes that should be blocked.
    """
    patterns = []
    try:
        text = mission_path.read_text()
    except (OSError, FileNotFoundError):
        return patterns

    # Find the Prohibited Operations section under Section 4
    in_prohibited = False
    for line in text.split("\n"):
        stripped = line.strip()
        if "Prohibited Operations" in stripped:
            in_prohibited = True
            continue
        if in_prohibited:
            # End at next section header
            if stripped.startswith("## ") or stripped.startswith("# "):
                break
            # Extract list items like "- [e.g., Do not modify ...]"
            match = re.match(r"[-*]\s+`?(.+?)`?\s*$", stripped)
            if match:
                pattern = match.group(1).strip()
                patterns.append(pattern)
    return patterns


def path_matches_prohibited(target_path, prohibited_patterns):
    """Check if a file path matches any prohibited pattern.

    Matching is prefix-based and glob-aware for common patterns like
    'files outside the project directory' or path prefixes.
    """
    target = Path(target_path)

    for pattern in prohibited_patterns:
        # Normalize pattern
        pat = pattern.lower().strip()

        # Check for "files outside the project directory" type patterns
        if "outside" in pat or "external" in pat:
            harness_root = find_harness_root()
            if harness_root:
                try:
                    target.resolve().relative_to(harness_root.resolve())
                except ValueError:
                    return True, f"Path is outside the harness workspace: {pattern}"

        # Check for specific path prefixes (e.g., "Do not modify files in /etc")
        # Extract potential paths from the pattern
        path_matches = re.findall(r'[\w./\\-]+', pat)
        for pm in path_matches:
            if len(pm) > 2 and '/' in pm:
                if str(target).lower().startswith(pm):
                    return True, f"Path matches prohibited pattern: {pattern}"

        # Check for file extension patterns (e.g., ".env files")
        ext_match = re.search(r'\.(\w+)\s+files?', pat)
        if ext_match:
            ext = "." + ext_match.group(1)
            if str(target).endswith(ext):
                return True, f"File type prohibited: {pattern}"

    return False, ""


def check_protected_file(target_path):
    """Check if the target is a protected framework file."""
    target = Path(target_path)
    target_name = target.name
    target_str = str(target)

    for protected in PROTECTED_FILES:
        # Check by filename or by relative path suffix
        if target_name == protected or target_str.endswith("/" + protected):
            return True, f"Framework file '{protected}' is read-only and managed by scripts only."
    return False, ""


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            # No input means no active harness context — allow
            sys.exit(0)

        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Cannot parse — allow by default (fail open)
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    # Only check write-type tools
    if tool_name not in WRITE_TOOLS:
        sys.exit(0)

    # Get target file path
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Check if harness workspace is active
    harness_root = find_harness_root()
    if not harness_root:
        # No active harness workspace — allow all writes
        sys.exit(0)

    # Check 1: Protected framework files
    blocked, reason = check_protected_file(file_path)
    if blocked:
        print(json.dumps({"decision": "block", "reason": reason}))
        sys.exit(0)

    # Check 2: Mission boundary enforcement
    mission_path = harness_root / "mission.md"
    if mission_path.exists():
        prohibited_patterns = read_prohibited_patterns(mission_path)
        matched, match_reason = path_matches_prohibited(file_path, prohibited_patterns)
        if matched:
            print(json.dumps({"decision": "block", "reason": match_reason}))
            sys.exit(0)

    # No violations — allow
    sys.exit(0)


if __name__ == "__main__":
    main()
