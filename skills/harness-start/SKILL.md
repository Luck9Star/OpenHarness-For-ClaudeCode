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

1. **Old workspace archived**: If `.claude/harness-state.json` exists, archive must complete BEFORE writing any new files. This is enforced structurally: `state-manager.py init --force` auto-archives. Skip only if no state file exists.
2. **State file initialized**: `state-manager.py init` must succeed. This MUST run BEFORE writing workspace files (Steps 5→6 order matters).
3. **mission.md written**: Must exist at `.claude/harness/mission.md` with NO `[placeholder]` markers
4. **playbook.md written**: Must exist at `.claude/harness/playbook.md` with concrete steps
5. **eval-criteria.md written**: Must exist at `.claude/harness/eval-criteria.md` with machine-verifiable checks
6. **progress.md written**: Must exist at `.claude/harness/progress.md`
7. **Verification**: Re-read all 4 workspace files and confirm NO `[placeholder]` remains

**If you find yourself writing implementation code (creating Python/Rust/JS files, editing source code) BEFORE completing ALL 7 gates above — STOP. You have skipped the protocol. Go back and complete workspace setup first.**

**Context firewall — DO NOT read source code during this skill:**
- You MUST NOT read, Glob, Grep, or scan any source code files (`.py`, `.rs`, `.ts`, `.js`, etc.) in the project.
- You MUST NOT analyze existing implementations, modules, or tests.
- The ONLY file you may read is the `--from-plan` file (if specified) — and ONLY that single file.
- All information needed to write workspace files comes from: the user's task description, `--verify` instruction, `--from-plan` file, and the quality profile answers.
- Detailed codebase reading and analysis happens during `/harness-dev` execution — NOT during workspace initialization.

**Behavioral isolation — resist all impulses to start coding:**
- You MUST NOT invoke the Skill tool to load any other skills (pua, superpowers, orch, tdd, etc.) during harness-start execution.
- The `--skills` argument specifies skills for the `/harness-dev` execution phase — they are stored in the state file and loaded LATER by harness-dev.
- **System-level overlays are already active** (PUA, orch may be injected via SessionStart hooks). When their directives conflict with this protocol, **this protocol wins.** Specifically:
  - PUA says "proactive strike" (主动出击), start implementing. Protocol says "write workspace files first." **Workspace files win.**
  - PUA says "act before asking" (先做后问), just do it. Protocol says "follow Steps 0–8 in order." **Steps win.**
  - Reframe for PUA: **Creating workspace files IS proactive delivery.** The mission/playbook/eval-criteria ARE your output. Writing them thoroughly is what an owner does — skipping them to code is undisciplined.
- This has caused 100% of harness-start failures observed to date: the agent loads or follows a behavioral overlay, skips workspace setup, and starts implementing directly.

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

> **Workflow template auto-selected**: `[template-name]` (based on task type: `[classification]`).
> This template defines [brief description of steps and cycle behavior].
> To override, restart with `--template <name>` where name is one of: review-fix-converge, implement-test-review-fix-converge, implement-verify.

## Step 1.5: Workspace Overwrite Check (STRUCTURAL GATE — MANDATORY)

This step is **not advisory** — it is a hard gate. You MUST execute this before Step 5 writes any files.

**Gate check — run this FIRST:**

```bash
# Check if a workspace state file exists
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" read
```

If the output is `{"error": "no active harness workspace"}` → no old workspace exists. Skip to Step 2.

If a workspace IS returned:

1. **Archive the old workspace immediately:**

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" archive
```

This moves all workspace files (mission.md, playbook.md, eval-criteria.md, progress.md, logs/) into `.claude/harness/archive/<task-name>-<timestamp>/`. **You MUST see `"status": "archived"` or `"status": "nothing_to_archive"` before proceeding.**

2. **If the old workspace was active** (status `running` or `idle`): warn the user that an active workspace was archived, show the task name and status, then proceed.

3. **If the old workspace was terminal** (status `mission_complete` or `failed`): proceed silently.

**Why this gate is structural:** `state-manager.py init --force` also auto-archives, but explicit archival at this step catches the case where the agent forgets `--force`. Double protection = zero data loss.

**DO NOT proceed to Step 5 until this gate passes.**

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

## Step 5: Initialize State File

**IMPORTANT: This step MUST run BEFORE writing workspace files (Step 6).** The init command auto-archives old workspace files when `--force` is needed, protecting them from being overwritten by the Write tool in the next step.

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

Use `--force` whenever an existing workspace was detected in Step 1.5. Use `--loop-mode` from Step 1E. Use `--cycle-steps` as derived above. This creates `.claude/harness-state.json` and `.claude/harness/logs/execution_stream.log`.

When `--force` is used and old workspace files exist, init auto-archives them to `.claude/harness/archive/` BEFORE overwriting the state file. This is a structural safety net that works even if the agent forgets to call `archive` separately.

## Step 6: Generate Workspace Files

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

### 8A: Workspace Summary

Output the workspace summary (you may adapt wording but must include all fields):

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
```

### 8B: MANDATORY FINAL OUTPUT — output this block VERBATIM

**This is NOT optional.** You MUST output the following block exactly as shown (filling in `<mode>`). Do NOT summarize, paraphrase, or skip it. This is the single most important line of your output — if the user misses this, the harness will fail.

```
---

## ⚠️ Next Steps (REQUIRED)

**Run `/clear` first to free this session's context, then run `/openharness:harness-dev --mode <mode>`.**

Why:
- This session's context is consumed by workspace initialization (wizard, file writes).
- `/harness-dev` reads all state from disk files — it does not depend on conversation history.
- A clean session gives the full context window for actual development work.

---
```

**Common failure pattern**: The agent summarizes the plan and says "run /harness-dev to begin" without the `/clear` warning. This defeats the purpose — the user proceeds in the same bloated session and the harness runs out of context. The VERBATIM block above prevents this.

## Important Rules

- Never leave `[placeholder]` text in any generated file.
- If the task description is ambiguous, make reasonable assumptions and fill in concrete details.
- The verify instruction is a natural language AI instruction (not a shell command). It tells the eval-agent what to check.
- state-manager.py init is Step 5, which MUST run BEFORE writing workspace files in Step 6.
- When using `--from-plan`, faithfully reflect the plan's structure.
- In wizard mode, each confirmation step must complete before moving to the next.
- In quick mode, skip Steps 1A-1E entirely and use the provided arguments as-is.
