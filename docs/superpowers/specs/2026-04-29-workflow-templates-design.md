# Design: Default Workflow Templates (JSON Authority)

**Date**: 2026-04-29
**Branch**: refactor/first-principles-json-authority
**Status**: Approved

## Problem

harness-start dynamically generates playbook.md and eval-criteria.md from scratch for every task. This means:
- Inconsistent structure across tasks of the same type
- Review tasks may miss the cycle convergence setup
- Wizard must reinvent step ordering each time
- No reusable patterns for common workflows (review-fix, implement-test-review-fix)

## Solution

Pre-defined JSON workflow templates that encode common task patterns. harness-start auto-selects the right template based on task classification, fills template variables from wizard output, and generates workspace files from the JSON authority.

## Template Schema

Each JSON file in `templates/workflows/` follows this schema:

```json
{
  "name": "string - template identifier (kebab-case)",
  "version": "semver - template version",
  "description": "string - when to use this template",
  "triggers": {
    "task_types": ["task type from wizard Step 1A"],
    "priority": "number - higher wins on conflict"
  },
  "steps": [
    {
      "name": "string - step name",
      "phase": "number|null - parallel group, null = linear",
      "type": "implement|review|fix|verify|human-review",
      "what": "string - description with {{variable}} placeholders",
      "tools": ["string - tool descriptions"],
      "completion_criteria": {
        "existence": ["output existence checks"],
        "quality": ["quality depth checks"]
      },
      "failure_handling": "string - on-failure action",
      "cycle_start": "boolean",
      "cycle_end": "boolean"
    }
  ],
  "cycle": {
    "enabled": "boolean",
    "steps": "[start_index, end_index]",
    "min_cycles": "number - minimum before convergence",
    "max_cycles": "number - circuit breaker",
    "convergence_metric": "string - convergence criteria"
  },
  "eval_standards": [
    {
      "name": "string",
      "check": "string - what to check",
      "method": "string - how to check",
      "pass_condition": "string - pass criteria",
      "on_fail": "string - action on failure"
    }
  ],
  "mission_defaults": {
    "execution_mode": "single|dual",
    "max_iterations": "number - 0 = infinite",
    "verify_command": "string"
  }
}
```

### Template Variables

Template `what` fields use `{{variable}}` syntax filled from wizard output:

| Variable | Source | Example |
|----------|--------|---------|
| `{{objective}}` | Wizard Step 1A task description | "Implement user authentication" |
| `{{target_files}}` | Wizard Step 1A codebase scan | "src/auth/*.py" |
| `{{deliverables}}` | Wizard Step 1B | "auth module, login endpoint, session tests" |
| `{{verify_command}}` | Wizard Step 1C | "pytest tests/" |
| `{{review_scope}}` | Derived from target_files | "src/auth/ and tests/auth/" |

## Three Default Templates

### 1. review-fix-converge.json

**Purpose**: Code review, security audit, architecture review
**Auto-trigger**: Task types `review`, `audit`
**Priority**: 10

Steps:
1. **Review** (type: review) — Cumulative scope review, spawn review-agent
2. **Fix** (type: fix) — Apply findings from review_report.json
3. **Verify** (type: verify) — Eval-agent validates fixes

Cycle: Steps 1→3, min 2, max 5 cycles
Convergence: new P0 = 0 AND new P1 < previous cycle

Eval standards:
- Density Check (>= 1 finding / 500 LOC)
- Exhaustion Check (every "no issue" backed by evidence)
- Convergence with Proof (numbered standard, mandatory)
- Blind Spot Acknowledgment (coverage gaps listed)

### 2. implement-test-review-fix-converge.json

**Purpose**: Full feature development with quality gate
**Auto-trigger**: Task types `feature`, `refactor`
**Priority**: 5

Steps:
1. **Implement** (type: implement) — Write code per objective
2. **Test** (type: implement) — Write and run tests
3. **Review** (type: review) — Spawn review-agent on cumulative scope
4. **Fix** (type: fix) — Apply review findings
5. **Verify** (type: verify) — Eval-agent validates everything

Cycle: Steps 3→5, min 2, max 5 cycles
Convergence: all tests pass AND new P0 = 0 AND new P1 < previous

Eval standards:
- Deliverable Check (output exists with correct structure)
- Functional Correctness (tests pass)
- Integration Check (cross-module contracts)
- Density Check
- Convergence with Proof (numbered standard, mandatory)

### 3. implement-verify.json

**Purpose**: Quick tasks, prototypes, non-code tasks
**Auto-trigger**: Task types `quick`, `non-code`, fallback default
**Priority**: 1

Steps:
1. **Implement** (type: implement) — Execute the task
2. **Verify** (type: verify) — Eval-agent validates result

Cycle: None (linear)

Eval standards:
- Deliverable Check
- Functional Correctness

## Integration with harness-start

### Auto-Selection Logic

In harness-start Step 1A, after task classification:

```
task_type:
  "review" | "audit"      -> review-fix-converge.json
  "feature" | "refactor"  -> implement-test-review-fix-converge.json
  "quick" | "non-code"    -> implement-verify.json
  fallback                 -> implement-verify.json
```

Override: `--template <name>` flag bypasses auto-selection.

### Generation Flow

Current Step 6 ("Write template files") changes to:

1. Read selected workflow JSON from `templates/workflows/<name>.json`
2. Fill template variables from wizard output (Steps 1A-1E)
3. Generate workspace files:
   - `playbook.md` — from `steps` array, rendered to markdown
   - `eval-criteria.md` — from `eval_standards` array, rendered to markdown
   - `mission.md` — from wizard output + `mission_defaults`
   - `progress.md` — standard initialization (unchanged)
4. Write `harness-state.json` with:
   - `cycle_steps` from `cycle.steps`
   - `min_cycles` / `max_cycles` from `cycle` config
   - `current_step` set to first step name

### Files Changed

| File | Change |
|------|--------|
| `templates/workflows/review-fix-converge.json` | New — template definition |
| `templates/workflows/implement-test-review-fix-converge.json` | New — template definition |
| `templates/workflows/implement-verify.json` | New — template definition |
| `skills/harness-start/SKILL.md` | Update Step 1A (auto-selection), Step 6 (generation from JSON) |
| `skills/harness-start/templates-reference.md` | Update with template variable docs and JSON schema |
| `scripts/setup-harness-loop.sh` | Add `--template` flag parsing |

### Backward Compatibility

- Existing `--mode`, `--quick`, `--from-plan` flags still work
- `--template` is additive, not replacing anything
- If no template matches and no `--template` given, falls back to current dynamic generation
- The markdown templates in `templates/` remain as fallback/override for advanced users

## Scope Boundaries

**In scope**:
- Three JSON template files
- Auto-selection logic in harness-start
- Template variable filling
- Markdown generation from JSON

**Out of scope** (future work):
- User-defined custom templates
- Template gallery / listing UI
- Template versioning / migration
- Converting the existing `templates/*.md` to JSON
- Modifying state-manager.py (it already supports cycle_steps)
