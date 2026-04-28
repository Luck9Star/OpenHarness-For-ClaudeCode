# First Principles Refactoring Design

**Date:** 2026-04-23
**Status:** Approved
**Scope:** S1 (state format) + S2 (authority unification) + S3 (delete eval-check.py) + S4 (stop-hook python)

## Problem Statement

OpenHarness has 4165 LOC across 20 files. First-principles analysis identified structural issues that generate recurring bugs:

1. **YAML frontmatter state format** requires 3 independent parsers (2 Python, 1 Bash), creating an entire class of escaping/parsing bugs (P0-3, P2)
2. **Command/Skill authority split** means two files describe the same execution flow, causing sync bugs (P0-1, P3)
3. **eval-check.py** is a low-value middle layer between eval-criteria.md and eval-agent — the agent can do everything the script does
4. **stop-hook.sh** is 153 lines of Bash doing JSON parsing, regex matching, and state manipulation — fragile and hard to maintain

## Design Decisions

### S1: State Format — YAML Frontmatter → JSON

**Current:** `.claude/harness-state.local.md` — YAML frontmatter in a Markdown file.
**New:** `.claude/harness-state.json` — standard JSON file.

Rationale:
- Eliminates all YAML parsing/escaping bugs (3 parsers → 0 custom parsers)
- Python reads with `json.load()`, Bash reads with `jq -r` (already a dependency)
- JSON handles quotes, backslashes, nested values natively — no custom escaping needed
- Tradeoff: loses human-readable Markdown table, but `/harness-status` command provides that view

State file schema:
```json
{
  "status": "idle",
  "execution_mode": "single",
  "worktree": "off",
  "current_step": "Step 1",
  "consecutive_failures": 0,
  "total_executions": 0,
  "circuit_breaker": "off",
  "iteration": 0,
  "max_iterations": 0,
  "session_id": "",
  "verify_instruction": "",
  "skills": "",
  "last_execution_time": "2026-04-23 19:00:00",
  "task_name": "untitled"
}
```

### S2: Authority Unification — Commands merge into Skills

**Current:** `commands/` and `skills/` both define execution logic.
**New:** Delete `commands/` directory. All behavior defined in `skills/`.

Mapping:
| Old | New | Action |
|-----|-----|--------|
| `commands/harness-start.md` | `skills/harness-start/SKILL.md` | Merge with `harness-init` skill |
| `commands/harness-dev.md` + `skills/harness-execute/SKILL.md` | `skills/harness-dev/SKILL.md` | Merge into one file |
| `commands/harness-edit.md` | `skills/harness-edit/SKILL.md` | Move |
| `commands/harness-status.md` | `skills/harness-status/SKILL.md` | Move |
| `skills/harness-init/SKILL.md` | (merged into harness-start) | Delete |
| `skills/harness-execute/SKILL.md` | (merged into harness-dev) | Delete |
| `skills/harness-core/SKILL.md` | (kept, updated references) | Update |
| `skills/harness-dream/SKILL.md` | (kept, updated references) | Update |
| `skills/harness-eval/SKILL.md` | (kept, updated references) | Update |

Rule: Each `/harness-*` command maps to exactly one `skills/harness-*/SKILL.md`.

### S3: Delete eval-check.py

**Current:** `scripts/eval-check.py` (262 lines) does heuristic file-existence and command-exit-code checks, then passes results to eval-agent.
**New:** Delete the script entirely. eval-agent reads `eval-criteria.md` directly and performs its own verification.

Rationale:
- eval-check.py's "strategies" (file exists, command exit code) are things eval-agent can do itself
- The `verify_instruction` field was already marked `passed: None` — delegated to eval-agent anyway
- Removing the middle layer eliminates P1 false-pass bugs
- eval-agent still writes `logs/eval_report.json` with the same format

### S4: stop-hook Bash → Python

**Current:** `hooks/stop-hook.sh` (153 lines) — JSON parsing, regex matching, state manipulation in Bash.
**New:** `hooks/stop-hook.sh` becomes a thin wrapper (~10 lines) that calls `scripts/stop-hook.py` (~100 lines).

Wrapper:
```bash
#!/bin/bash
HOOK_INPUT=$(cat)
echo "$HOOK_INPUT" | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stop-hook.py"
```

Python script handles:
1. Read JSON state file via `json.load()`
2. Validate fields (with sensible defaults, never delete state)
3. Read transcript, extract LOOP_DONE promise
4. Determine loop continuation
5. Output JSON response

Benefits:
- Python `json` module = zero parsing bugs
- Proper exception handling instead of `rm "$STATE_FILE"` on errors
- Single parsing logic for state file (shared with state-manager.py)

## File Change Summary

| File | Action | Est. Lines |
|------|--------|------------|
| `scripts/state-manager.py` | Rewrite — JSON read/write | 325 → ~180 |
| `hooks/stop-hook.sh` | Thin wrapper | 153 → ~10 |
| `scripts/stop-hook.py` | New — loop control logic | 0 → ~100 |
| `scripts/eval-check.py` | Delete | -262 |
| `scripts/setup-harness-loop.sh` | Simplify — call JSON init | 115 → ~60 |
| `hooks/pretooluse.py` | Update — protect `.json` instead of `.md` | 169 → ~120 |
| `hooks/session-start.sh` | Update — read JSON | 57 → ~40 |
| `scripts/cleanup.py` | Update — read/write JSON | 242 → ~180 |
| `commands/` | Delete entire directory | -398 |
| `skills/harness-start/SKILL.md` | New — merged start + init | ~200 |
| `skills/harness-dev/SKILL.md` | New — merged dev + execute | ~300 |
| `skills/harness-edit/SKILL.md` | New — from commands | ~115 |
| `skills/harness-status/SKILL.md` | New — from commands | ~90 |
| `skills/harness-init/` | Delete — merged into start | -167 |
| `skills/harness-execute/` | Delete — merged into dev | -273 |
| `skills/harness-core/SKILL.md` | Update — JSON references | ~67 |
| `skills/harness-eval/SKILL.md` | Update — JSON references | ~97 |
| `skills/harness-dream/SKILL.md` | Update — JSON references | ~127 |

**Total estimate:** 4165 → ~2900 lines (~30% reduction, eliminates YAML parsing bug class entirely)

## Out of Scope

- Functionality changes (same behavior, cleaner implementation)
- Agent prompt changes (dev-agent, eval-agent, review-agent)
- Template file changes (mission.md, playbook.md, eval-criteria.md, progress.md)
- New features
- README updates (separate task after refactoring)
