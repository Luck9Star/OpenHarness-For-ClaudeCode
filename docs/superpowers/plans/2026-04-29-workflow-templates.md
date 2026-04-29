# Default Workflow Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three pre-defined JSON workflow templates that harness-start auto-selects based on task type, replacing ad-hoc playbook generation with consistent, reusable patterns.

**Architecture:** JSON files in `templates/workflows/` define step structure, cycle config, and eval standards. harness-start reads the selected template, fills `{{variable}}` placeholders from wizard output, and generates markdown workspace files (playbook.md, eval-criteria.md). The markdown is a rendered view; JSON is the authority.

**Tech Stack:** JSON templates, Bash (setup-harness-loop.sh), Markdown (SKILL.md instruction files)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `templates/workflows/review-fix-converge.json` | Create | Review→Fix→Verify cycle template |
| `templates/workflows/implement-test-review-fix-converge.json` | Create | Full development cycle with review gate |
| `templates/workflows/implement-verify.json` | Create | Simple linear template for quick tasks |
| `scripts/setup-harness-loop.sh` | Modify | Add `--template` flag |
| `skills/harness-start/templates-reference.md` | Modify | Document JSON template system and variables |
| `skills/harness-start/SKILL.md` | Modify | Update Step 1A (auto-selection), Step 5 (state init with template), Step 6 (generation from JSON) |

---

### Task 1: Create review-fix-converge.json

**Files:**
- Create: `templates/workflows/review-fix-converge.json`

- [ ] **Step 1: Create directory and write the template**

```bash
mkdir -p templates/workflows
```

```json
{
  "name": "review-fix-converge",
  "version": "1.0.0",
  "description": "For code review, security audit, or architecture review tasks. Cycles review→fix→verify until convergence.",
  "triggers": {
    "task_types": ["review", "audit"],
    "priority": 10
  },
  "steps": [
    {
      "name": "Review",
      "phase": null,
      "type": "review",
      "what": "Perform cumulative-scope review of {{review_scope}}. Spawn harness-review-agent. Focus on: correctness, security, performance, maintainability. Write findings to .claude/harness/logs/review_report.json.",
      "tools": [
        "Read → read source files in review scope",
        "Grep → search for patterns and anti-patterns",
        "Glob → enumerate files in scope"
      ],
      "completion_criteria": {
        "existence": [
          "review_report.json exists at .claude/harness/logs/review_report.json",
          "Report contains findings array with severity levels"
        ],
        "quality": [
          "Finding density >= 1 finding per 500 LOC (or explicit justification for sparse modules)",
          "Every 'no issue' claim backed by evidence of what was checked",
          "Report includes blind spot / coverage gap acknowledgment section"
        ]
      },
      "failure_handling": "If review_agent fails to produce report, retry once with narrower scope. If density check fails, re-dispatch with 'go deeper' instruction.",
      "cycle_start": true,
      "cycle_end": false
    },
    {
      "name": "Fix",
      "phase": null,
      "type": "fix",
      "what": "Apply fixes for findings from .claude/harness/logs/review_report.json. Prioritize P0 findings first, then P1. Each fix must reference the finding ID it resolves.",
      "tools": [
        "Read → read files to fix",
        "Edit → apply targeted fixes",
        "Bash → run syntax checks after fixes"
      ],
      "completion_criteria": {
        "existence": [
          "All P0 findings from review_report.json have corresponding code changes",
          "Each code change references the finding ID in commit or comment"
        ],
        "quality": [
          "Fixes address root cause, not symptoms",
          "No new lint/type errors introduced",
          "Existing tests still pass after fixes"
        ]
      },
      "failure_handling": "If fix introduces new errors, revert and retry with different approach. Max 3 retries per finding.",
      "cycle_start": false,
      "cycle_end": false
    },
    {
      "name": "Verify",
      "phase": null,
      "type": "verify",
      "what": "Spawn harness-eval-agent to validate that all fixes are correct and no regressions introduced. Eval-agent checks against numbered standards in eval-criteria.md including convergence criterion.",
      "tools": [
        "Bash → run {{verify_command}}",
        "Read → verify file changes match fix descriptions"
      ],
      "completion_criteria": {
        "existence": [
          "Eval report produced with PASS/FAIL per standard"
        ],
        "quality": [
          "All numbered standards pass",
          "Convergence criterion passes (new P0 = 0 AND new P1 < previous cycle)",
          "No regressions in previously passing tests"
        ]
      },
      "failure_handling": "If eval fails, feed failure details back to Fix step in next cycle. If circuit breaker trips, report convergence failure summary.",
      "cycle_start": false,
      "cycle_end": true
    }
  ],
  "cycle": {
    "enabled": true,
    "steps": [1, 3],
    "min_cycles": 2,
    "max_cycles": 5,
    "convergence_metric": "new P0 findings = 0 AND new P1 findings < previous cycle's new P1 count"
  },
  "eval_standards": [
    {
      "name": "Finding Density",
      "check": "Review finding density meets minimum threshold",
      "method": "Count findings per module/dimension in review_report.json. Calculate LOC / finding ratio.",
      "pass_condition": "Each module has >= 1 finding per 500 LOC, OR review explicitly justifies sparsity with evidence.",
      "on_fail": "Re-dispatch reviewer with instruction to go deeper on sparse modules"
    },
    {
      "name": "Exhaustion Evidence",
      "check": "Every 'no issue' claim is backed by evidence",
      "method": "Scan review_report.json for patterns: 'no issues', 'looks fine', 'appears correct'. Verify each has supporting evidence.",
      "pass_condition": "Every module/dimension with 0 findings includes specific evidence of what was checked and why it is genuinely clean.",
      "on_fail": "Re-dispatch reviewer to re-examine dimensions lacking evidence"
    },
    {
      "name": "Convergence",
      "check": "Finding reduction is genuine, not due to shallow review",
      "method": "Compare review_report.json findings between current cycle and previous cycle. If cycle < min_cycles, automatically FAIL.",
      "pass_condition": "cycle_iteration >= min_cycles AND new P0 findings = 0 AND new P1 findings < previous cycle's new P1 count AND review includes evidence section explaining what changed between cycles.",
      "on_fail": "Continue to next cycle. If cycle >= max_cycles, output convergence failure summary."
    },
    {
      "name": "Blind Spot Acknowledgment",
      "check": "Review acknowledges its own blind spots",
      "method": "Check review_report.json for a 'blind_spots' or 'coverage_gaps' section.",
      "pass_condition": "Review includes section listing: areas intentionally excluded (with reason), areas needing deeper analysis next iteration, known gaps in this review round.",
      "on_fail": "Append blind spot analysis before proceeding"
    },
    {
      "name": "Fix Correctness",
      "check": "All P0 findings from latest review have been addressed",
      "method": "Cross-reference review_report.json P0 findings with actual code changes. Verify each P0 has a corresponding fix.",
      "pass_condition": "Zero unresolved P0 findings. Each fix references the finding ID it resolves.",
      "on_fail": "Return to Fix step to address remaining P0 findings"
    }
  ],
  "mission_defaults": {
    "execution_mode": "single",
    "max_iterations": 0,
    "verify_command": "echo 'Review-verify: check review_report.json and code changes'"
  }
}
```

- [ ] **Step 2: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('templates/workflows/review-fix-converge.json')); print('VALID')"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add templates/workflows/review-fix-converge.json
git commit -m "feat(templates): add review-fix-converge workflow template"
```

---

### Task 2: Create implement-test-review-fix-converge.json

**Files:**
- Create: `templates/workflows/implement-test-review-fix-converge.json`

- [ ] **Step 1: Write the template**

```json
{
  "name": "implement-test-review-fix-converge",
  "version": "1.0.0",
  "description": "For feature development or refactoring tasks. Implements code, tests it, then cycles review→fix→verify until convergence. Full quality gate.",
  "triggers": {
    "task_types": ["feature", "refactor"],
    "priority": 5
  },
  "steps": [
    {
      "name": "Implement",
      "phase": null,
      "type": "implement",
      "what": "Implement {{objective}} in {{target_files}}. Follow existing project conventions and patterns. Write production code only — tests come in the next step.",
      "tools": [
        "Read → read existing code for patterns and interfaces",
        "Edit → write implementation code",
        "Bash → run syntax/type checks"
      ],
      "completion_criteria": {
        "existence": [
          "All source files mentioned in deliverables exist",
          "Each file compiles/parses without syntax errors"
        ],
        "quality": [
          "Implementation matches the design from mission.md",
          "Code follows existing project conventions",
          "No TODO or placeholder code remaining"
        ]
      },
      "failure_handling": "Fix syntax errors and retry. If design ambiguity, log and make reasonable default choice.",
      "cycle_start": false,
      "cycle_end": false
    },
    {
      "name": "Test",
      "phase": null,
      "type": "implement",
      "what": "Write tests for the implementation in Step 1. Cover: happy path, edge cases, error paths. Run {{verify_command}} to validate tests pass.",
      "tools": [
        "Read → read implementation code to understand what to test",
        "Edit → write test files",
        "Bash → run {{verify_command}}"
      ],
      "completion_criteria": {
        "existence": [
          "Test files exist for each module from Step 1",
          "{{verify_command}} exits with code 0"
        ],
        "quality": [
          "Tests cover happy path + at least 2 edge cases per function",
          "Tests cover error/failure paths",
          "No skipped or commented-out tests"
        ]
      },
      "failure_handling": "If tests fail, fix test code (not implementation). If implementation bug found, note for review step.",
      "cycle_start": false,
      "cycle_end": false
    },
    {
      "name": "Review",
      "phase": null,
      "type": "review",
      "what": "Perform cumulative-scope review of all code changes (implementation + tests). Spawn harness-review-agent. Focus on: correctness, security, performance, maintainability, test quality.",
      "tools": [
        "Read → read all changed files",
        "Grep → search for anti-patterns",
        "Glob → enumerate changed files"
      ],
      "completion_criteria": {
        "existence": [
          "review_report.json exists at .claude/harness/logs/review_report.json"
        ],
        "quality": [
          "Finding density >= 1 finding per 500 LOC",
          "Every 'no issue' claim backed by evidence",
          "Includes blind spot acknowledgment"
        ]
      },
      "failure_handling": "Re-dispatch reviewer with 'go deeper' instruction on sparse areas.",
      "cycle_start": true,
      "cycle_end": false
    },
    {
      "name": "Fix",
      "phase": null,
      "type": "fix",
      "what": "Apply fixes for findings from review_report.json. Prioritize P0 then P1. Run {{verify_command}} after each fix batch to ensure no regressions.",
      "tools": [
        "Read → read files to fix",
        "Edit → apply targeted fixes",
        "Bash → run {{verify_command}}"
      ],
      "completion_criteria": {
        "existence": [
          "All P0 findings have corresponding code changes",
          "{{verify_command}} still passes after fixes"
        ],
        "quality": [
          "Fixes address root cause",
          "No new errors introduced"
        ]
      },
      "failure_handling": "If fix breaks tests, revert and retry. Max 3 retries per finding.",
      "cycle_start": false,
      "cycle_end": false
    },
    {
      "name": "Verify",
      "phase": null,
      "type": "verify",
      "what": "Spawn harness-eval-agent for independent validation of all work. Check all numbered standards including convergence, deliverable completeness, and integration.",
      "tools": [
        "Bash → run {{verify_command}}",
        "Read → verify deliverables match mission.md"
      ],
      "completion_criteria": {
        "existence": [
          "Eval report produced with PASS/FAIL per standard"
        ],
        "quality": [
          "All numbered standards pass",
          "Convergence criterion passes",
          "Integration check passes"
        ]
      },
      "failure_handling": "Feed failure details back to Fix step. Circuit breaker at max_cycles.",
      "cycle_start": false,
      "cycle_end": true
    }
  ],
  "cycle": {
    "enabled": true,
    "steps": [3, 5],
    "min_cycles": 2,
    "max_cycles": 5,
    "convergence_metric": "{{verify_command}} passes AND new P0 = 0 AND new P1 < previous cycle"
  },
  "eval_standards": [
    {
      "name": "Deliverable Completeness",
      "check": "All deliverables from mission.md exist and have substance",
      "method": "For each deliverable listed in mission.md Output Definition, verify the file/path exists and is non-trivial (>50 LOC for code, >20 lines for config).",
      "pass_condition": "Every listed deliverable exists, is non-empty, and matches the expected format from mission.md.",
      "on_fail": "Return to Implement step to create missing deliverables"
    },
    {
      "name": "Functional Correctness",
      "check": "All tests pass",
      "method": "Run {{verify_command}} and check exit code.",
      "pass_condition": "Exit code 0, zero failing tests, zero skipped tests.",
      "on_fail": "Return to Test step to fix failing tests"
    },
    {
      "name": "Cross-Module Integration",
      "check": "Modules integrate correctly end-to-end",
      "method": "Verify data flows through all module boundaries. Check that outputs from upstream modules are valid inputs for downstream modules.",
      "pass_condition": "End-to-end pipeline produces expected output. All intermediate values are non-empty and correctly typed.",
      "on_fail": "Identify which boundary fails and return to Fix step"
    },
    {
      "name": "Finding Density",
      "check": "Review finding density meets minimum threshold",
      "method": "Count findings per module in review_report.json.",
      "pass_condition": "Each module has >= 1 finding per 500 LOC, or justified sparsity.",
      "on_fail": "Re-dispatch reviewer with 'go deeper' instruction"
    },
    {
      "name": "Convergence",
      "check": "Finding reduction is genuine across review cycles",
      "method": "Compare findings between current and previous cycle. If cycle < min_cycles, FAIL.",
      "pass_condition": "cycle_iteration >= min_cycles AND {{verify_command}} passes AND new P0 = 0 AND new P1 < previous cycle.",
      "on_fail": "Continue to next cycle. Circuit breaker at max_cycles."
    }
  ],
  "mission_defaults": {
    "execution_mode": "single",
    "max_iterations": 0,
    "verify_command": "echo 'Specify verify command via --verify flag'"
  }
}
```

- [ ] **Step 2: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('templates/workflows/implement-test-review-fix-converge.json')); print('VALID')"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add templates/workflows/implement-test-review-fix-converge.json
git commit -m "feat(templates): add implement-test-review-fix-converge workflow template"
```

---

### Task 3: Create implement-verify.json

**Files:**
- Create: `templates/workflows/implement-verify.json`

- [ ] **Step 1: Write the template**

```json
{
  "name": "implement-verify",
  "version": "1.0.0",
  "description": "For quick tasks, prototypes, or non-code tasks. Linear implement→verify with no review cycle. Minimal overhead.",
  "triggers": {
    "task_types": ["quick", "non-code"],
    "priority": 1
  },
  "steps": [
    {
      "name": "Implement",
      "phase": null,
      "type": "implement",
      "what": "Execute {{objective}}. Produce the deliverables listed in mission.md. Follow project conventions.",
      "tools": [
        "Read → read existing code for context",
        "Edit → write/modify files",
        "Bash → run build/lint/type checks",
        "Write → create new files if needed"
      ],
      "completion_criteria": {
        "existence": [
          "All deliverables from mission.md exist",
          "No syntax/parse errors in output files"
        ],
        "quality": [
          "Implementation matches mission objective",
          "Follows existing project patterns"
        ]
      },
      "failure_handling": "Fix errors and retry. If blocked by external dependency, log and skip.",
      "cycle_start": false,
      "cycle_end": false
    },
    {
      "name": "Verify",
      "phase": null,
      "type": "verify",
      "what": "Spawn harness-eval-agent for independent validation. Check deliverables exist, are non-trivial, and meet mission done definition.",
      "tools": [
        "Bash → run {{verify_command}}",
        "Read → verify deliverable content"
      ],
      "completion_criteria": {
        "existence": [
          "Eval report produced"
        ],
        "quality": [
          "All numbered standards pass",
          "No regressions detected"
        ]
      },
      "failure_handling": "If eval fails, feed details to agent for retry. Circuit breaker at 3 consecutive failures.",
      "cycle_start": false,
      "cycle_end": false
    }
  ],
  "cycle": {
    "enabled": false,
    "steps": null,
    "min_cycles": 0,
    "max_cycles": 0,
    "convergence_metric": null
  },
  "eval_standards": [
    {
      "name": "Deliverable Check",
      "check": "All deliverables from mission.md exist with correct structure",
      "method": "For each deliverable in mission.md Output Definition, verify file/path exists and is non-trivial.",
      "pass_condition": "Every listed deliverable exists, is non-empty, and matches expected format.",
      "on_fail": "Return to Implement step to create missing deliverables"
    },
    {
      "name": "Functional Correctness",
      "check": "Output passes verification",
      "method": "Run {{verify_command}} and check exit code.",
      "pass_condition": "Exit code 0 or all manual checks pass.",
      "on_fail": "Return to Implement step to fix issues"
    }
  ],
  "mission_defaults": {
    "execution_mode": "single",
    "max_iterations": 0,
    "verify_command": "echo 'Specify verify command via --verify flag'"
  }
}
```

- [ ] **Step 2: Validate JSON syntax**

Run: `python3 -c "import json; json.load(open('templates/workflows/implement-verify.json')); print('VALID')"`
Expected: `VALID`

- [ ] **Step 3: Commit**

```bash
git add templates/workflows/implement-verify.json
git commit -m "feat(templates): add implement-verify workflow template"
```

---

### Task 4: Update setup-harness-loop.sh with --template flag

**Files:**
- Modify: `scripts/setup-harness-loop.sh`

The `--template` flag selects a workflow JSON file. When provided, it auto-derives `--cycle-steps`, `--min-cycles`, `--max-cycles` from the template JSON.

- [ ] **Step 1: Add --template flag to argument parsing**

In `scripts/setup-harness-loop.sh`, add a `TEMPLATE=""` variable (after line 22, alongside other flag variables), then add a `--template)` case in the while loop (after the `--force)` case at line 113):

Add variable declaration after line 22 (`FORCE=""`):
```bash
TEMPLATE=""
```

Add case after line 116 (`shift` from `--force)`):
```bash
    --template)
      if [[ $# -lt 2 ]]; then
        echo "Error: --template requires an argument (template name without .json extension)" >&2
        exit 1
      fi
      TEMPLATE="$2"
      shift 2
      ;;
```

- [ ] **Step 2: Add template processing before state init**

After the FORCE auto-detection block (after line 133), add template processing logic that extracts cycle config from the selected JSON template:

```bash
# ---- Template processing ----
if [[ -n "$TEMPLATE" ]]; then
  TEMPLATE_FILE="${PLUGIN_ROOT}/templates/workflows/${TEMPLATE}.json"
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: Template not found: $TEMPLATE_FILE" >&2
    echo "Available templates:" >&2
    ls "${PLUGIN_ROOT}/templates/workflows/"*.json 2>/dev/null | xargs -n1 basename | sed 's/\.json$//' >&2
    exit 1
  fi

  # Extract cycle config from template if not already set by explicit flags
  if [[ -z "$CYCLE_STEPS" ]]; then
    CYCLE_STEPS_FROM_TEMPLATE=$(python3 -c "
import json, sys
t = json.load(open('$TEMPLATE_FILE'))
cycle = t.get('cycle', {})
if cycle.get('enabled') and cycle.get('steps'):
    print(f\"{cycle['steps'][0]},{cycle['steps'][1]}\")
" 2>/dev/null || true)
    if [[ -n "$CYCLE_STEPS_FROM_TEMPLATE" ]]; then
      CYCLE_STEPS="$CYCLE_STEPS_FROM_TEMPLATE"
    fi
  fi

  if [[ -z "$MIN_CYCLES" ]]; then
    MIN_CYCLES=$(python3 -c "import json; print(json.load(open('$TEMPLATE_FILE')).get('cycle',{}).get('min_cycles',0))" 2>/dev/null || echo "0")
  fi

  if [[ -z "$MAX_CYCLES" ]]; then
    MAX_CYCLES=$(python3 -c "import json; print(json.load(open('$TEMPLATE_FILE')).get('cycle',{}).get('max_cycles',0))" 2>/dev/null || echo "0")
  fi
fi
```

- [ ] **Step 3: Update usage string and success output**

Update the usage string on line 4 and line 25 to include `[--template NAME]`:

Line 4:
```bash
# Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]
```

Line 25 usage echo:
```bash
  echo "Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]" >&2
```

Add to success output block (after the "Max Iterations" line at ~182):
```bash
echo "  Template:           ${TEMPLATE:-(auto-detect)}"
```

- [ ] **Step 4: Validate the script parses correctly**

Run: `bash -n scripts/setup-harness-loop.sh && echo 'SYNTAX OK'`
Expected: `SYNTAX OK`

- [ ] **Step 5: Commit**

```bash
git add scripts/setup-harness-loop.sh
git commit -m "feat(scripts): add --template flag to setup-harness-loop.sh"
```

---

### Task 5: Update templates-reference.md

**Files:**
- Modify: `skills/harness-start/templates-reference.md`

Add a new section documenting the JSON workflow template system. This section goes before the existing `.claude/harness/mission.md` section.

- [ ] **Step 1: Add Workflow Templates section**

Insert the following at line 9 (after the `---` separator, before `## .claude/harness/mission.md`):

```markdown
## Workflow Templates (JSON Authority)

When a workflow template is selected (via `--template` flag or auto-detection from Step 1A classification), the playbook and eval-criteria are generated from JSON definitions in `templates/workflows/`.

### Auto-Selection Rules

The wizard Step 1A task classification maps to templates:

| Classification | Template | Cycle? |
|---|---|---|
| `review`, `audit` | `review-fix-converge` | Yes (steps 1-3) |
| `feature`, `refactor` | `implement-test-review-fix-converge` | Yes (steps 3-5) |
| `quick`, `non-code` | `implement-verify` | No |
| Fallback | `implement-verify` | No |

### Template Variables

JSON step `what` fields contain `{{variable}}` placeholders filled from wizard output:

| Variable | Source | Example |
|----------|--------|---------|
| `{{objective}}` | Step 1A expanded task description | "Implement user authentication" |
| `{{target_files}}` | Step 1A codebase scan result | "src/auth/*.py" |
| `{{deliverables}}` | Step 1B deliverable list | "auth module, login endpoint, tests" |
| `{{verify_command}}` | Step 1C verify instruction | "pytest tests/" |
| `{{review_scope}}` | Derived from target_files + deliverables | "src/auth/ and tests/auth/" |

### JSON → Markdown Generation

When generating workspace files from a template:

1. **playbook.md**: Render each `steps[]` entry as a Step section with Type, What, Tools, Completion Criteria, Failure Handling. Add Cycle Behavior section if `cycle.enabled` is true.
2. **eval-criteria.md**: Render each `eval_standards[]` entry as a numbered Standard. Include Validation Principles section. Add Review Task Standards if template has review steps.
3. **mission.md**: Use wizard output + `mission_defaults` from template. Same structure as current template.
4. **progress.md**: Standard initialization, same as current template.

```

---

### Task 6: Update harness-start SKILL.md

**Files:**
- Modify: `skills/harness-start/SKILL.md`

Two changes: (1) add template auto-selection to Step 1A output, (2) update Step 6 to generate from JSON when template is selected.

- [ ] **Step 1: Add template auto-selection to Step 1A**

In the Step 1A section (around line 86-92), after the task classification is complete and before presenting the expanded description, add a template selection note to the user presentation:

After the expanded task description confirmation, add:

```markdown
> **Workflow template auto-selected**: `[template-name]` (based on task type: `[classification]`).
> This template defines [brief description of steps and cycle behavior].
> To override, restart with `--template <name>` where name is one of: review-fix-converge, implement-test-review-fix-converge, implement-verify.
```

- [ ] **Step 2: Update Step 6 (Write Template Files)**

Modify Step 6 (around line 196-214) to branch based on whether a template was selected:

Replace the current Step 6 instructions with:

```markdown
#### Step 6: Generate Workspace Files

**If a workflow template was selected** (auto-detected in Step 1A or via `--template`):

1. Read the JSON template from `templates/workflows/<template-name>.json`
2. Fill `{{variable}}` placeholders in step `what` fields using values from Steps 1A-1C:
   - `{{objective}}` → expanded task description from Step 1A
   - `{{target_files}}` → affected files from Step 1A scan
   - `{{deliverables}}` → deliverable list from Step 1B
   - `{{verify_command}}` → verify instruction from Step 1C
   - `{{review_scope}}` → derived from target_files + deliverables
3. Generate playbook.md from the filled template:
   - Each `steps[]` entry → a Step section with Type, What, Tools, Completion Criteria, Failure Handling
   - If `cycle.enabled` is true → add Cycle Behavior section with min_cycles, max_cycles, convergence metric
   - Add Dependency Diagram section
4. Generate eval-criteria.md from `eval_standards[]`:
   - Each entry → a numbered Standard table
   - Include Validation Principles section
   - If template has review steps → include Review Task Standards (Density, Exhaustion, Convergence, Blind Spot)
5. Generate mission.md from wizard output + `mission_defaults`
6. Generate progress.md (standard initialization)
7. Write harness-state.json via `state-manager.py init` with cycle config from template:
   - `--cycle-steps` from `cycle.steps` (if cycle.enabled)
   - `--min-cycles` from `cycle.min_cycles`
   - `--max-cycles` from `cycle.max_cycles`

**If no template was selected** (fallback):
- Use the current dynamic generation process from templates-reference.md.
```

- [ ] **Step 3: Commit**

```bash
git add skills/harness-start/SKILL.md skills/harness-start/templates-reference.md
git commit -m "feat(harness-start): integrate workflow template auto-selection and JSON→markdown generation"
```

---

### Task 7: Validate all templates and integration

- [ ] **Step 1: Validate all three JSON files parse correctly**

Run:
```bash
for f in templates/workflows/*.json; do python3 -c "import json; json.load(open('$f')); print(\"VALID: $f\")"; done
```

Expected: Three lines, all saying `VALID`.

- [ ] **Step 2: Verify setup-harness-loop.sh --template flag works**

Run:
```bash
cd /tmp && mkdir -p test-harness-template && cd test-harness-template
bash /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/setup-harness-loop.sh test-task --template review-fix-converge --verify "echo test" 2>&1 | head -20
```

Expected: Output includes `Template: review-fix-converge` and state file created with `cycle_steps: [1, 3]`.

Run cleanup:
```bash
rm -rf /tmp/test-harness-template
```

- [ ] **Step 3: Verify invalid template name gives helpful error**

Run:
```bash
cd /tmp && mkdir -p test-harness-invalid && cd test-harness-invalid
bash /Users/yangyitian/Documents/dev/Agents/openharness-cc/scripts/setup-harness-loop.sh test-task --template nonexistent 2>&1
```

Expected: Error message listing available templates.

Run cleanup:
```bash
rm -rf /tmp/test-harness-invalid
```

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address validation issues from workflow template integration"
```

---

## Self-Review Checklist

- [x] **Spec coverage**: Three templates (review-fix-converge, implement-test-review-fix-converge, implement-verify) → Tasks 1-3. Auto-selection logic → Task 6. --template flag → Task 4. templates-reference update → Task 5. Validation → Task 7.
- [x] **Placeholder scan**: No TBD/TODO. All JSON is concrete. All SKILL.md changes have actual content.
- [x] **Type consistency**: JSON field names match across all three templates (steps[], cycle.steps uses 1-based indices matching state-manager.py convention). eval_standards[] structure identical across templates.
