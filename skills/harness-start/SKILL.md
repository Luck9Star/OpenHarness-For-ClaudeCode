---
name: harness-start
description: Initialize a new OpenHarness autonomous development task. Parses arguments, discovers quality preferences, generates workspace files from templates, initializes JSON state. Trigger: /harness-start.
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2]"
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# /harness-start

Initialize a new OpenHarness autonomous development task workspace.

## Step 1: Parse Arguments

Parse the user's arguments from `$ARGUMENTS`:

- **Task description**: everything before any `--` flags (can supplement `--from-plan`, see below)
- **Mode**: `--mode single` (default) or `--mode dual`
- **Verify instruction**: `--verify "natural language instruction"` (optional) -- an AI instruction for the eval-agent to interpret, e.g., `--verify "ensure all tests pass"` or `--verify "API endpoints return correct status codes"`
- **Skills**: `--skills "skill1,skill2"` (optional) -- comma-separated list of skill names for the dev-agent to load during implementation
- **From plan**: `--from-plan <file-path>` (optional) -- use a plan file as the task source

**Combination rules:**
- Description only -> use description as the task
- `--from-plan` only -> derive everything from the plan file
- **Both** -> plan provides structure (steps, architecture), description provides supplementary context and clarification. Merge them: plan is the base, description adds scope clarification, priority hints, or constraints the plan doesn't cover.

If neither is provided, prompt the user:

```
What task would you like the harness to execute? Describe it in one sentence.
```

## Step 2: Quality Preference Discovery

Ask the user (combine into a single prompt):

1. **Code review** -- "Need code review? If yes, how many rounds? (0 = no review, 1 = review once, 2+ = multiple review-fix cycles)"
2. **TDD** -- "Need TDD (write tests before implementation)? (yes/no)"
3. **Auto-fix on failure** -- "Should the system auto-fix and retry when verification fails? (yes/no)"
4. **Human checkpoints** -- "Insert pause points for human review? (yes/no, default: no for fully autonomous execution)"

Guidelines:
- For simple/trivial tasks (e.g., "fix a typo", "update a config value"), skip this step and auto-set all answers to "no" -- inform the user.
- For medium-to-complex tasks, ask all questions.
- Parse answers into a quality profile: `{ review_rounds: int, tdd: bool, auto_fix: bool }`

If arguments provided all required info (mode, verify, etc.), use what was given and only ask the quality questions.

## Step 3: Determine Workspace Path

The workspace is the current project directory. Harness files will be created under `.claude/harness/`:

```
<project-root>/
  .claude/
    harness-state.json
    harness/
      mission.md
      playbook.md
      eval-criteria.md
      progress.md
      logs/
```

Use the current working directory as the project root.

## Step 4: Generate Task Name

Derive a concise task name from the task description:
- Take the first 3-5 significant words
- Convert to lowercase, hyphen-separated
- Example: "Add user authentication with JWT" -> `user-authentication-jwt`

## Step 5: Write Template Files

Copy the templates from `${CLAUDE_PLUGIN_ROOT}/templates/` and fill them completely. Every `[placeholder]` must be replaced with concrete, task-specific content.

**All files must be written to `.claude/harness/` directory** — create the directory first:
```bash
mkdir -p .claude/harness/logs
```

### .claude/harness/mission.md

Fill based on the task description:
- **Mission Name**: the task name from Step 4
- **Mission Objective**: the user's task description
- **Done Definition**: derive 2-4 concrete, machine-verifiable completion conditions
- **Boundaries**: set allowed/prohibited operations
- **Execution Parameters**: set verify_instruction and execution_mode from user input
- **Output Definition**: describe expected output artifacts

### .claude/harness/playbook.md

Create a concrete step-by-step plan using the quality profile from Step 2.

**Step types** (each step must have a `Type` field):
- `implement` -- write/create/modify code
- `review` -- spawn harness-review-agent for read-only code review
- `fix` -- apply fixes based on review feedback (reads `.claude/harness/logs/review_report.json`)
- `verify` -- spawn harness-eval-agent for validation
- `human-review` -- pause loop for human inspection and approval

**Dynamic step generation rules based on quality profile**:

- **User wants review (review_rounds > 0)**: After each `implement` step, insert a `review` step followed by a `fix` step.
- **User wants TDD**: For each logical unit of work: `verify` (write tests first) -> `implement` (make tests pass).
- **User wants quick (no review, no TDD)**: Just `implement` + final `verify`.
- **Simple task (auto-detected)**: Minimal: `implement` followed by a single `verify`.

**Human-review insertion rules** (only if user explicitly requests checkpoints):
- **1-2 implement steps**: No human-review needed
- **3-4 implement steps**: Insert one `human-review` after the midpoint
- **5+ implement steps**: Insert at 33%, 66%, and before final `verify`

**By default, do NOT insert human-review steps.**

**General playbook rules**:
- Each step must have: type, what to do, tools to use, completion criteria, failure handling
- Steps should be ordered by dependency
- Add a dependency diagram at the bottom
- The final step should always be a `verify` step

### .claude/harness/eval-criteria.md

Create validation standards:
- At least 2-3 standards covering key outputs
- Include a "verify_instruction passes" standard if a verify instruction was provided
- Each standard: check name, method, pass condition, on-fail action
- Keep all checks machine-verifiable

### .claude/harness/progress.md

Initialize with:
- Task name, current timestamp, conditions count from `.claude/harness/mission.md`
- All conditions set to `Not Met`
- Empty execution history section

## Step 6: Initialize State File

Run the state manager to create the JSON state file:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-instruction>" --skills "<skills>"
```

This creates `.claude/harness-state.json` and `.claude/harness/logs/execution_stream.log`.

## Step 7: Verify Initialization

After all files are written, confirm:
1. `.claude/harness/mission.md` exists and has no `[placeholder]` markers
2. `.claude/harness/playbook.md` exists and has no `[placeholder]` markers
3. `.claude/harness/eval-criteria.md` exists and has no `[placeholder]` markers
4. `.claude/harness/progress.md` exists
5. `.claude/harness-state.json` exists
6. `.claude/harness/logs/` directory exists

If any file is missing or contains `[placeholder]`, fix it before reporting ready.

## Step 8: Report Ready State

Report to the user:

```
Harness workspace initialized.

Task: <task-name>
Mode: <single|dual>
Verify: <instruction or "none">

Files created:
  .claude/harness/mission.md        -- objective, done conditions, boundaries
  .claude/harness/playbook.md       -- <N> execution steps
  .claude/harness/eval-criteria.md  -- <N> validation standards
  .claude/harness/progress.md       -- blank tracking log
  .claude/harness-state.json        -- state file

Ready to start execution. Run /harness-dev to begin.
```

## Important Rules

- Never leave `[placeholder]` text in any generated file.
- If the task description is ambiguous, make reasonable assumptions and fill in concrete details.
- The verify instruction is a natural language AI instruction (not a shell command). It tells the eval-agent what to check.
- Always run state-manager.py as the last step -- it creates the `.claude/` directory and state file.
- When using `--from-plan`, faithfully reflect the plan's structure.
