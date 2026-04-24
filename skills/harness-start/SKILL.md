---
name: harness-start
description: Initialize a new OpenHarness autonomous development task. Interactive wizard refines task description, verify instruction, and skill selection through multi-turn dialogue. Trigger: /harness-start.
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2] [--quick]"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Grep", "Glob"]
---

# /harness-start

Initialize a new OpenHarness autonomous development task workspace.

## Step 0: Parse Arguments & Detect Mode

Parse the user's arguments from `$ARGUMENTS`:

- **Task description**: everything before any `--` flags (can supplement `--from-plan`, see below)
- **Mode**: `--mode single` (default) or `--mode dual`
- **Verify instruction**: `--verify "natural language instruction"` (optional)
- **Skills**: `--skills "skill1,skill2"` (optional)
- **From plan**: `--from-plan <file-path>` (optional)
- **Quick**: `--quick` (optional) — force skip wizard, use args as-is

**Combination rules:**
- Description only -> use description as the task
- `--from-plan` only -> derive everything from the plan file
- **Both** -> plan provides structure (steps, architecture), description provides supplementary context and clarification. Merge them: plan is the base, description adds scope clarification, priority hints, or constraints the plan doesn't cover.

**Mode detection — Quick vs Wizard:**

Quick mode activates when ALL of these are true:
1. Task description (or `--from-plan`) is provided
2. `--verify` is provided with non-empty content
3. User explicitly passes `--quick`, OR mode + skills are both specified

Wizard mode activates when ANY critical parameter is missing:
- No task description and no `--from-plan`
- No `--verify` instruction
- Or the user simply typed `/harness-start` with no arguments

If neither description nor `--from-plan` is provided and wizard mode wasn't obvious:
```
What task would you like the harness to execute? Describe it in one sentence.
```

## Step 1: Wizard — Task Refinement (Wizard Mode Only)

Skip this entire step in Quick mode — go directly to Step 2.

### Step 1A: Analyze Codebase & Expand Task Description

Before refining the task, briefly analyze the current project:

1. **Detect tech stack**: Use Glob to find key config files (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, etc.) and determine language/framework
2. **Scan project structure**: List top-level directories and key entry points
3. **Check existing tests**: Find test directories/files to understand test patterns

Then, expand the user's task description:

- Add concrete scope boundaries based on the codebase structure
- Identify which files/modules are likely involved
- Clarify ambiguous terms using project context
- Add implementation constraints (follow existing patterns, match conventions)

Present the expanded task description to the user:

```
Based on the project analysis, here's the expanded task:

[Expanded description with concrete scope, affected modules, and constraints]

Affected areas:
- [module/file 1]: [what changes here]
- [module/file 2]: [what changes here]

Does this look correct? Any adjustments?
```

Wait for user confirmation. Incorporate any feedback before proceeding.

### Step 1B: Define Deliverables

From the expanded task description, enumerate concrete deliverables:

```
Based on the task scope, the deliverables will be:

1. [Deliverable 1 — e.g., "src/auth/middleware.ts: JWT authentication middleware"]
2. [Deliverable 2 — e.g., "tests/auth/middleware.test.ts: Unit tests covering token validation"]
3. [Deliverable 3 — e.g., "Updated route handlers to use middleware"]

Is this the right scope? Anything to add or remove?
```

Each deliverable must be:
- A concrete file or file section (not a vague "improve X")
- Tied to a specific module/area from Step 1A
- Independently verifiable

Wait for user confirmation.

### Step 1C: Derive Verify Instruction

Generate a `--verify` instruction from the deliverables. The instruction must be:
- **Quantified**: use numbers, not "thorough" or "complete"
- **Machine-verifiable**: eval-agent can check each condition by running commands or reading files
- **Cover all deliverables**: one check per deliverable minimum

```
Based on the deliverables, here's the proposed verify instruction:

--verify "
1. [Check for deliverable 1 — e.g., "auth middleware file exists and exports correct functions"]
2. [Check for deliverable 2 — e.g., "all unit tests pass (npm test)"]
3. [Check for deliverable 3 — e.g., "protected routes return 401 without valid token"]
"

Each check maps directly to a deliverable. Want to adjust any checks?
```

If the user already provided `--verify`, present the derived version alongside and ask which they prefer.

Wait for user confirmation. Use the final confirmed verify instruction.

### Step 1D: Recommend Skills

Based on the tech stack detected in Step 1A and the deliverables, recommend skills:

```
Based on the tech stack and task type, these skills may help:

Recommended:
- [skill-name]: [reason — e.g., "project uses React, skill provides component patterns"]

Optional:
- [skill-name]: [reason — e.g., "task involves API design, skill provides REST patterns"]

Skip:
- [skill-name]: [reason — e.g., "no database changes needed"]

Use recommended skills? Or adjust the list?
```

If the user already specified `--skills`, validate them against the tech stack and note any gaps.

Wait for user confirmation. Use the final confirmed skill list.

## Step 1.5: Workspace Overwrite Check

Before generating any files, check if an existing harness workspace is active:

Read `.claude/harness-state.json`. If it exists:
- If status is `running` or `idle`: warn the user that an active workspace exists, show the task name and status. Ask: "This will overwrite the existing workspace. Continue? (yes/no)"
  - If the user confirms, add `--force` to the state-manager.py init command in Step 6
  - If the user declines, stop and suggest `/harness-status` or `/harness-edit`
- If status is `mission_complete` or `failed`: proceed without warning (old task is done). `--force` is not needed for terminal statuses.

**In all cases where an existing workspace is detected**, archive the old workspace immediately (before Step 5 writes new files):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" archive
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

Fill based on the task description (use the expanded version from Step 1A if wizard was used):
- **Mission Name**: the task name from Step 4
- **Mission Objective**: the user's task description (expanded version if wizard refined it)
- **Done Definition**: derive from the verified deliverables in Step 1B — each deliverable maps to a done condition
- **Boundaries**: set allowed/prohibited operations
- **Execution Parameters**: set verify_instruction and execution_mode from user input
- **Output Definition**: list the confirmed deliverables from Step 1B

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
- When wizard was used, align steps with the deliverables from Step 1B

### .claude/harness/eval-criteria.md

Create validation standards based on the verify instruction:
- Start with the verified checks from Step 1C — each check becomes a standard
- Add structural validation standards (file existence, content plausibility)
- Each standard: check name, method, pass condition, on-fail action
- Keep all checks machine-verifiable
- Ensure every deliverable from Step 1B has at least one corresponding check

**Quality enforcement rules** (prevent Goodhart's Law — process compliance != quality):

- **Every deliverable check must have a quality criterion**, not just existence. "File exists" is never sufficient alone — pair it with content depth, structure, or behavioral verification.
- **For review/audit tasks**: Include the Review Task Standards from the template (Density Check, Exhaustion Check, Convergence with Proof, Blind Spot Acknowledgment). These are MANDATORY for any task whose primary output is a review report.
- **For implementation tasks**: Each functional check should have both a positive condition (does it work?) and a depth condition (is it complete enough?). Example: not just "tests pass" but "tests cover >= N scenarios including error paths."
- **Never write a pass condition that can be trivially satisfied.** Avoid bare "file exists", "report contains N sections", "no new P0 findings" without requiring evidence of depth.

### .claude/harness/progress.md

Initialize with:
- Task name, current timestamp, conditions count from `.claude/harness/mission.md`
- All conditions set to `Not Met`
- Empty execution history section

## Step 6: Initialize State File

Run the state manager to create the JSON state file:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-instruction>" --skills "<skills>" [--force]
```

Use `--force` only if the user confirmed overwrite in Step 1.5. This creates `.claude/harness-state.json` and `.claude/harness/logs/execution_stream.log`.

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
Skills: <skills or "none">

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
- In wizard mode, each confirmation step must complete before moving to the next.
- In quick mode, skip Steps 1A-1D entirely and use the provided arguments as-is.
