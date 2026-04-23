---
name: harness-init
description: Guided workflow for creating a new OpenHarness task workspace. Creates mission.md, playbook.md, eval-criteria.md, progress.md from templates and initializes state file. Trigger when user wants to start a new harness task.
---

# Harness Init | Workspace Setup Workflow

You are setting up a new OpenHarness task workspace. Follow these steps precisely. All instructions are directed at you, Claude — execute them directly.

## Step 1: Collect Task Information

Ask the user (only once, combine into a single prompt):

1. **Task description** — a single sentence describing what to accomplish (required)
2. **Execution mode** — `single` (default, you plan and code) or `dual` (you plan only, a separate agent codes)
3. **Verify instruction** — a natural language instruction for the eval-agent to validate work (e.g., `确保所有测试通过`, `API endpoints return correct status codes`). Optional — press enter to skip.

Wait for the user's response before proceeding. Parse their input:
- The first part (or whole input) is the task description
- `--mode single` or `--mode dual` selects execution mode (default: `single`)
- `--verify INSTRUCTION` sets the verify instruction (default: none)

## Step 2: Quality Preference Discovery

Based on the task description, ask 2-3 targeted quality questions. Combine them into a single prompt:

1. **Code review** — "Need code review? If yes, how many rounds? (0 = no review, 1 = review once, 2+ = multiple review-fix cycles)"
2. **TDD** — "Need TDD (write tests before implementation)? (yes/no)"
3. **Auto-fix on failure** — "Should the system auto-fix and retry when verification fails? (yes/no)"

Guidelines for asking:
- For simple/trivial tasks (e.g., "fix a typo", "update a config value"), you may skip this step and auto-set all answers to "no" — inform the user you are doing so.
- For medium-to-complex tasks, ask all three questions.
- Parse answers into a quality profile: `{ review_rounds: int, tdd: bool, auto_fix: bool }`

## Step 3: Determine Workspace Path

The workspace is the current project directory. The harness files will be created at the project root:

```
<project-root>/
  mission.md
  playbook.md
  eval-criteria.md
  progress.md
  .claude/
    harness-state.local.md
  logs/
```

Use the current working directory as the project root. If the user specified a different directory, use that instead.

## Step 4: Generate Task Name

Derive a concise task name from the task description:
- Take the first 3-5 significant words
- Convert to lowercase, hyphen-separated
- Example: "Add user authentication with JWT" -> `user-authentication-jwt`

## Step 5: Write Template Files

Copy the templates from `${CLAUDE_PLUGIN_ROOT}/templates/` and fill them completely based on the task description. Every `[placeholder]` must be replaced with concrete, task-specific content. Do not leave any template markers.

### mission.md

Fill these fields based on the task description:
- **Mission Name**: the task name from Step 4
- **Mission Objective**: the user's task description
- **Done Definition**: derive 2-4 concrete, machine-verifiable completion conditions from the objective. For each, specify a verification method.
- **Boundaries**: set reasonable allowed/prohibited operations:
  - Allowed: read/write project source files, run tests and dev tools, install dependencies
  - Prohibited: modify files outside project, push to remote without confirmation, delete non-generated files
- **Execution Parameters**: set verify_instruction and execution_mode from user input
- **Output Definition**: describe the expected output artifacts

### playbook.md

Create a concrete step-by-step execution plan. Use the quality profile from Step 2 to dynamically generate step types.

**Step types** (each step must have a `Type` field):
- `implement` — write/create/modify code
- `review` — spawn harness-review-agent for read-only code review
- `fix` — apply fixes based on review feedback (reads `logs/review_report.json`)
- `verify` — spawn harness-eval-agent for validation

**Dynamic step generation rules based on quality profile**:

- **User wants review (review_rounds > 0)**: After each `implement` step, insert a `review` step followed by a `fix` step. Repeat for the requested number of review rounds. Pattern: `implement → review → fix → review → fix → ...` (last fix step omitted if review passes).
- **User wants TDD**: For each logical unit of work, order steps as: `verify` (write tests first) → `implement` (make tests pass). The verify step here writes tests; the implement step makes them pass.
- **User wants quick (no review, no TDD)**: Just `implement` + final `verify` for each major unit.
- **Simple task (auto-detected)**: AI simplifies to minimal steps: `implement` followed by a single `verify` at the end.

**General playbook rules**:
- Break the task into the appropriate number of steps based on the above rules
- Each step must have: type, what to do, tools to use, completion criteria, failure handling
- Steps should be ordered by dependency (earlier steps produce artifacts later steps need)
- Add a dependency diagram at the bottom
- Be specific about file paths, commands, and expected outcomes
- The final step in the playbook should always be a `verify` step that validates overall completion

### eval-criteria.md

Create validation standards:
- At least 2-3 standards covering the task's key outputs
- Include a "verify_instruction passes" standard if a verify instruction was provided
- Each standard must have: check name, method, pass condition, on-fail action
- Keep all checks machine-verifiable — no subjective assessments

### progress.md

Initialize with:
- Task name, current timestamp, and conditions count from mission.md
- All conditions set to `Not Met`
- Empty execution history section

## Step 6: Initialize State File

Run the state manager to create the state file:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-instruction>"
```

This creates `.claude/harness-state.local.md` and `logs/execution_stream.log`.

## Step 7: Verify Initialization

After all files are written, confirm:
1. `mission.md` exists at project root and has no `[placeholder]` markers
2. `playbook.md` exists at project root and has no `[placeholder]` markers
3. `eval-criteria.md` exists at project root and has no `[placeholder]` markers
4. `progress.md` exists at project root
5. `.claude/harness-state.local.md` exists
6. `logs/` directory exists

If any file is missing or contains `[placeholder]`, fix it before reporting ready.

## Step 8: Report Ready State

Report to the user:

```
Harness workspace initialized.

Task: <task-name>
Mode: <single|dual>
Verify: <instruction or "none">

Files created:
  mission.md        — objective, done conditions, boundaries
  playbook.md       — <N> execution steps
  eval-criteria.md  — <N> validation standards
  progress.md       — blank tracking log
  .claude/harness-state.local.md — state file

Ready to start execution. Run /harness-dev to begin.
```
