#!/usr/bin/env python3
"""OpenHarness External Validation Checker.

Runs eval_criteria.md validation standards against the workspace.
Outputs JSON report to logs/eval_report.json.

Usage:
    eval-check.py [--workspace PATH]

If --workspace is not provided, uses current working directory.
"""

import sys
import re
import json
import subprocess
from datetime import datetime
from pathlib import Path


def find_workspace(path=None):
    """Find workspace root by looking for eval-criteria.md."""
    if path:
        p = Path(path).resolve()
    else:
        p = Path.cwd()

    # Check current dir first
    if (p / "eval-criteria.md").exists():
        return p

    # Check for .claude dir
    if (p / ".claude" / "harness-state.local.md").exists():
        return p

    return p


def read_state_file(workspace):
    """Read frontmatter from state file."""
    state_path = workspace / ".claude" / "harness-state.local.md"
    if not state_path.exists():
        return {}
    text = state_path.read_text()
    match = re.match(r'^---\n(.*?)\n---', text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).split('\n'):
        if ':' in line:
            key, val = line.split(':', 1)
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def parse_eval_criteria(workspace):
    """Parse eval-criteria.md to extract validation standards."""
    eval_path = workspace / "eval-criteria.md"
    if not eval_path.exists():
        print(f"Warning: eval-criteria.md not found at {eval_path}", file=sys.stderr)
        return []

    text = eval_path.read_text()
    standards = []

    # Split by "### Standard" headers
    sections = re.split(r'### Standard \d+:', text)

    for section in sections[1:]:  # Skip preamble
        name_match = re.match(r'\s*(.+?)[\n\r]', section)
        name = name_match.group(1).strip() if name_match else f"Standard"

        check = extract_field(section, "Check")
        method = extract_field(section, "Method")
        pass_condition = extract_field(section, "Pass Condition")
        on_fail = extract_field(section, "On Fail")

        standards.append({
            "name": name,
            "check": check,
            "method": method,
            "pass_condition": pass_condition,
            "on_fail": on_fail,
        })

    return standards


def extract_field(section, field_name):
    """Extract a field value from a table row in a section."""
    pattern = rf'\|\s*{field_name}\s*\|\s*`?(.*?)`?\s*\|'
    match = re.search(pattern, section, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return ""


def run_shell_command(command, workspace, timeout=120):
    """Run a shell command and return result. Used for method-based checks only."""
    if not command:
        return None

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
            "passed": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "passed": False,
        }
    except Exception as e:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "passed": False,
        }


def check_standard(standard, workspace):
    """Evaluate a single validation standard. Returns (passed, detail)."""
    method = standard.get("method", "").lower()
    check = standard.get("check", "").lower()

    # Strategy 1: File existence check
    # Look for path-like patterns in method or check
    path_patterns = re.findall(r'[`"]([^\s`"]+/\S+)[`"\s]', method)
    if not path_patterns:
        path_patterns = re.findall(r'[`"](\./?\S+)[`"\s]', method)

    if path_patterns:
        for file_pattern in path_patterns:
            target = workspace / file_pattern
            if target.exists():
                size = target.stat().st_size
                return True, f"File {file_pattern} exists ({size} bytes)"
            else:
                return False, f"File {file_pattern} not found at {workspace}"

    # Strategy 2: Command exit code check
    if "exit code" in method or "command" in method.lower():
        # Extract command from method text
        cmd_match = re.search(r'`([^`]+)`', method)
        if cmd_match:
            cmd = cmd_match.group(1)
            result = run_shell_command(cmd, workspace)
            if result:
                if result["passed"]:
                    return True, f"Command `{cmd}` exited with code 0"
                else:
                    detail = f"Command `{cmd}` failed (exit {result['exit_code']})"
                    if result["stderr"]:
                        detail += f": {result['stderr'][:200]}"
                    return False, detail

    # Strategy 3: Generic "exists and size" check
    if "exists" in method or "exists" in check:
        # Try to find any file path mentioned
        all_paths = re.findall(r'[\w./\-]+\.\w+', method)
        for p in all_paths:
            target = workspace / p
            if target.exists():
                return True, f"Found {p}"
            else:
                return False, f"Path {p} does not exist"

    # Strategy 4: Fallback — cannot auto-verify
    return False, f"Could not auto-verify: {standard.get('name', 'unknown')} — requires manual check"


def main():
    workspace = None
    args = sys.argv[1:]

    i = 0
    while i < len(args):
        if args[i] == "--workspace" and i + 1 < len(args):
            workspace = args[i + 1]
            i += 2
        else:
            i += 1

    workspace = find_workspace(workspace)

    # Read state file for verify instruction
    state = read_state_file(workspace)
    verify_instruction = state.get("verify_instruction", "")

    # Parse eval criteria
    standards = parse_eval_criteria(workspace)

    if not standards:
        print("No validation standards found in eval-criteria.md", file=sys.stderr)
        report = {
            "checks": [],
            "overall": False,
            "timestamp": datetime.now().isoformat(),
            "error": "No standards found in eval-criteria.md",
        }
    else:
        checks = []

        # Run verify instruction if available (logged for eval-agent to interpret)
        if verify_instruction:
            checks.append({
                "name": "verify_instruction",
                "instruction": verify_instruction,
                "passed": None,  # Delegated to eval-agent for AI interpretation
                "detail": f"Verify instruction: '{verify_instruction}' — requires eval-agent interpretation",
            })

        # Check each standard
        for standard in standards:
            passed, detail = check_standard(standard, workspace)
            checks.append({
                "name": standard["name"],
                "passed": passed,
                "detail": detail,
            })

        overall = all(c["passed"] is True for c in checks)

        report = {
            "checks": checks,
            "overall": overall,
            "timestamp": datetime.now().isoformat(),
        }

    # Write report to logs/
    logs_dir = workspace / "logs"
    logs_dir.mkdir(exist_ok=True)
    report_path = logs_dir / "eval_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    # Print report to stdout
    print(json.dumps(report, indent=2))

    # Exit with 0 if all passed, 1 otherwise
    sys.exit(0 if report.get("overall", False) else 1)


if __name__ == "__main__":
    main()
