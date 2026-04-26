---
name: harness-start
description: "Initialize a new OpenHarness autonomous development task. Interactive wizard refines task description, verify instruction, and skill selection through multi-turn dialogue. Trigger: /harness-start."
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2] [--quick]"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Grep", "Glob"]
---

# /harness-start

Initialize a new OpenHarness autonomous development task workspace.

## MANDATORY PROTOCOL — DO NOT SKIP

This skill is a **workspace initialization protocol**, not a coding task. You MUST complete ALL workspace setup steps (Steps 0–8) before writing any implementation code. The workspace files are the control plane for the harness-dev loop — without them, the loop cannot function.

**Hard gates — each must pass before proceeding:**

1. **Workspace directory exists**: `mkdir -p .claude/harness/logs` — run this FIRST
2. **mission.md written**: Must exist at `.claude/harness/mission.md` with NO `[placeholder]` markers
3. **playbook.md written**: Must exist at `.claude/harness/playbook.md` with concrete steps
4. **eval-criteria.md written**: Must exist at `.claude/harness/eval-criteria.md` with machine-verifiable checks
5. **progress.md written**: Must exist at `.claude/harness/progress.md`
6. **State file initialized**: `state-manager.py init` must succeed
7. **Verification**: Re-read all 4 workspace files and confirm NO `[placeholder]` remains

**If you find yourself writing implementation code (creating Python/Rust/JS files, editing source code) BEFORE completing ALL 7 gates above — STOP. You have skipped the protocol. Go back and complete workspace setup first.**

**Context firewall — DO NOT read source code during this skill:**
- You MUST NOT read, Glob, Grep, or scan any source code files (`.py`, `.rs`, `.ts`, `.js`, etc.) in the project.
- You MUST NOT analyze existing implementations, modules, or tests.
- The ONLY file you may read is the `--from-plan` file (if specified) — and ONLY that single file.
- All information needed to write workspace files comes from: the user's task description, `--verify` instruction, `--from-plan` file, and the quality profile answers.
- Detailed codebase reading and analysis happens during `/harness-dev` execution — NOT during workspace initialization.

**Skill isolation — DO NOT load other skills during harness-start:**
- You MUST NOT invoke the Skill tool to load any other skills (pua, superpowers, orch, tdd, etc.) during harness-start execution.
- The `--skills` argument specifies skills for the `/harness-dev` execution phase — they are stored in the state file and loaded LATER by harness-dev.
- Loading personality/behavioral overlays (PUA, orch) during workspace initialization hijacks the protocol by injecting contradictory instructions. This has caused 100% of harness-start failures observed to date.

**"Already implemented" is NOT a valid reason to skip workspace setup:**
- Even if you believe all features are already implemented, you MUST still create all 4 workspace files and run state-manager.py init.
- The workspace files capture the task contract — mission.md, playbook.md, eval-criteria.md are the specification for verification.
- `/harness-dev` will verify the existing implementation against these specs and report completion. This is the correct path.

**Why these rules exist**: Reading source code causes context explosion. Loading other skills causes behavioral override. Both dilute the MANDATORY PROTOCOL instructions and lead to skipping workspace setup. These are the #1 and #2 causes of harness-start failures.

This skill DOES NOT implement features. It ONLY creates the workspace. Implementation happens when `/harness-dev` runs.

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

In wizard mode, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-start/wizard-reference.md` and follow Steps 1A–1E in order. Each step requires user confirmation before proceeding. The wizard covers: task classification & codebase scan, deliverable definition, verify instruction derivation, skill recommendation, and loop mode selection.

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

For detailed template file structure (mission.md, playbook.md, eval-criteria.md, progress.md), read `${CLAUDE_PLUGIN_ROOT}/skills/harness-start/templates-reference.md`. Key rules: every `[placeholder]` must be replaced; every deliverable must have a corresponding check; cross-module integration checks are mandatory for multi-phase tasks.

## Step 6: Initialize State File

**Derive cycle_steps** from the playbook structure (no separate user question needed):

| Condition | cycle_steps value | Reasoning |
|---|---|---|
| Task type is review/audit (from Step 1A) | `[1, N]` where N is the verify step number | Full cycle: review → fix → verify → re-review until clean |
| Task type is implementation AND `review_rounds >= 1` | `[first_review_step, last_verify_step]` | Implement linearly first, then cycle the review-fix-verify tail. Cumulative review scope ensures all implementations are re-checked each cycle. |
| Task type is implementation AND `review_rounds = 0` | omit (linear) | No review needed, standard linear execution |
| Task has 5+ implement steps | `[first_review_step, last_verify_step]` | Long implementation chains accumulate integration drift — a final review cycle catches cross-step regressions even if user didn't explicitly request review |

**Example for a 10-step implementation task with review:**
```
Step 1-8: implement (linear — each step runs once)
Step 9:   review (cumulative scope — reviews ALL code from steps 1-8)
Step 10:  fix
Step 11:  verify
cycle_steps: [9, 11]  ← only the review tail cycles
```

Run the state manager to create the JSON state file:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-instruction>" --skills "<skills>" --loop-mode <in-session|clean> [--cycle-steps <start,end>] [--force]
```

Use `--force` only if the user confirmed overwrite in Step 1.5. Use `--loop-mode` from Step 1E. Use `--cycle-steps` as derived above. This creates `.claude/harness-state.json` and `.claude/harness/logs/execution_stream.log`.

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
Loop mode: <in-session|clean>
Cycle: <yes: steps X-Y | no: linear>
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
- In quick mode, skip Steps 1A-1E entirely and use the provided arguments as-is.
