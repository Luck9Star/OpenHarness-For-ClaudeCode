---
name: harness-dev
description: Autonomous development loop for OpenHarness. Parses arguments, manages loop state, executes playbook steps via single or dual mode, validates via eval-agent. Trigger: /harness-dev.
argument-hint: "[--mode single|dual] [--worktree] [--max-iterations N] [--resume]"
allowed-tools: ["Bash", "Agent", "Read", "Write", "Edit"]
---

# /harness-dev -- Autonomous Development Loop

You are starting the OpenHarness autonomous development loop. Follow these steps precisely.

## Step 1: Workspace Check

Check if an OpenHarness workspace exists in the current directory:

- Look for `.claude/harness-state.json`
- Look for `mission.md`

If **no harness workspace exists**:
1. Ask the user: "No OpenHarness workspace detected. Provide a task description to initialize one, or run `/harness-start` first."
2. If the user provides a description, run `/harness-start` with that description.
3. If the user says to run `/harness-start`, invoke the harness-start skill and wait for it to complete.

## Step 2: Parse Arguments

Parse the command arguments (if any were provided):

- `--mode single` (default): Agent plans and codes directly, with oracle validation
- `--mode dual`: Agent plans only, then spawns `harness-dev-agent` for coding. Protects main agent context from explosion.
- `--worktree`: In dual mode, run dev-agent in an isolated git worktree. Without this flag, dev-agent works in the same directory.
- `--max-iterations N`: Stop the loop after N iterations (0 = infinite)
- `--resume`: Resume from a paused state (after human-review checkpoint)

If `--mode` is not specified, default to `single`.
`--worktree` only has effect in `dual` mode.

Note: The `--verify` instruction is read from the state file (set during `/harness-start`). Do not specify it here.

## Step 3: Initialize Loop State

**If `--resume` was specified, skip this step entirely and proceed to Step 5.** The existing state file will be used as-is.

**Otherwise**, run the setup script to create or reset the loop state file:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-harness-loop.sh" <task-name> --mode <mode> [--worktree] --max-iterations <N>
```

Use the task name from `mission.md` (Section 1: Mission Name).
The verify instruction is already in the state file from `/harness-start`.

Verify the output confirms successful initialization.

## Step 4: Mode Explanation

**If single mode**, explain to the user:
> Single mode active. I will plan each playbook step, implement the code directly, then spawn an eval-agent for independent verification. The loop continues until all done conditions are met or the circuit breaker trips.

**If dual mode (without --worktree)**, explain to the user:
> Dual mode active (in-place). I will plan each playbook step, then spawn `harness-dev-agent` as a subagent to implement code in the current directory. This protects my context from explosion while keeping all changes in-place.

**If dual mode (with --worktree)**, explain to the user:
> Dual mode active (worktree). I will plan each playbook step, then spawn `harness-dev-agent` in an isolated git worktree. Changes happen on a separate branch and are merged back on success.

## Step 5: Read Mission and Begin Execution

Read these files in cache-optimal order:
1. `mission.md` -- the task contract
2. `eval-criteria.md` -- validation standards
3. `playbook.md` -- execution steps
4. `.claude/harness-state.json` -- current state

Update the state file to `status: running`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status running
```

Then begin executing the playbook from the current step.

---

## Loop Iteration Workflow

Each iteration follows this exact workflow. Do not improvise -- follow it precisely.

### 5.1. Read State File

Read `.claude/harness-state.json` first. Check:

- **Circuit breaker**: If `circuit_breaker: tripped`, stop immediately. Output a message explaining that manual intervention is required and output `<promise>LOOP_DONE</promise>` so the loop can exit safely.
- **Mission complete**: If `status: mission_complete`, output `<promise>LOOP_DONE</promise>` and stop.

### 5.2. Recover from Stuck State

If `status: running` (leftover from a previous crash), recover:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Auto-recovered from stale running state"
```

### 5.3. Set Status to Running

Before doing any work, mark the state:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status running
```

### 5.4. Read Files in Cache-Optimal Order

Read these files in this exact order to maximize prompt cache hits:

1. `mission.md` -- static mission definition, rarely changes
2. `eval-criteria.md` -- acceptance criteria, rarely changes
3. `playbook.md` -- step-by-step plan, semi-static
4. `.claude/harness-state.json` -- dynamic state (re-read for current step)

Only load `knowledge/*.md` files on demand if the current step references them.

### 5.5. Execute Current Step

First, log a structured round report for traceability:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" report "<subtask>" "<strategy>" "<verification>" "<state_target>"
```

Then, check the current playbook step's **Type** field:

#### type: implement (or no type field -- backwards compatible)

Check `execution_mode` in the state file:

**Single Mode (`execution_mode: single`)**

You plan AND code directly. Use Claude Code tools (Read, Write, Edit, Bash, Grep).

If the `skills` field is set in the state file, load each specified skill using the Skill tool before starting step execution.

After completing the step:
- Log what was done: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Completed <step description>"`
- Run validation (see step 5.6)

**Dual Mode (`execution_mode: dual`)**

You plan only. Delegate coding to a sub-agent.

*Dual Mode -- In-Place (worktree: off, default)*

1. Read the current step requirements from the playbook
2. Construct a detailed prompt with: task, file paths, constraints from mission.md, eval criteria, skills to load
3. Spawn `harness-dev-agent` WITHOUT worktree isolation
4. Wait for the agent to complete
5. Log the delegation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Delegated <step> to harness-dev-agent (in-place)"`

*Dual Mode -- Worktree (worktree: on)*

1. Read the current step requirements from the playbook
2. Construct a detailed prompt
3. Spawn `harness-dev-agent` with `isolation: "worktree"` for git worktree isolation
4. Wait for the agent to complete
5. Merge the worktree changes back to the main branch
6. Log the delegation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Delegated <step> to harness-dev-agent in worktree"`

#### type: review

ALWAYS spawn `harness-review-agent` -- read-only code review.

1. Read the current step description from the playbook
2. Spawn `harness-review-agent` with the step description and scope
3. The review agent writes findings to `logs/review_report.json`
4. Read `logs/review_report.json` to check the verdict:
   - `pass` -- log and proceed
   - `conditional-pass` -- log warnings, proceed but note issues
   - `fail` -- log critical issues, next fix step will address them
5. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Review completed: <overall verdict>"`
6. Skip validation (step 5.6) for review steps -- proceed directly to step 5.7/5.8

#### type: fix

Read the review report, then apply fixes.

1. Read `logs/review_report.json`
2. If report is missing or overall verdict was `pass`, skip -- log and advance
3. Extract issue list

Then dispatch based on execution mode:
- **Single mode**: Fix yourself using Read, Edit, Write, Bash
- **Dual mode**: Spawn `harness-dev-agent` with the issue list

After fixes:
- Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Applied fixes for <N> issues from review"`
- Run validation (step 5.6) if step has completion criteria

#### type: human-review

Pause for human inspection and approval.

1. Generate a progress summary of completed steps
2. Output the summary to the user
3. **Advance the step counter BEFORE pausing** (P1 fix):
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status paused
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Human-review checkpoint: paused for user inspection"
   ```
4. Output `<promise>LOOP_PAUSE</promise>` to suspend the loop
5. When the user resumes (via `/harness-dev --resume`), the next iteration continues from the step after this one

#### type: verify

Spawn `harness-eval-agent` for independent validation.

1. Read the current step description and eval criteria
2. Spawn `harness-eval-agent` with eval criteria, step description, instructions to independently verify
3. The eval-agent reports PASS or FAIL
4. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Verify: <PASS or FAIL>"`

### 5.6. Run Validation

After step execution (except review steps), validate by spawning `harness-eval-agent` with:
- The eval criteria from `eval-criteria.md`
- The current step description
- The verify_instruction (if set in state) -- the agent interprets this independently
- Instructions to independently verify without reading your implementation

The eval-agent checks file existence, runs verify commands, and evaluates semantic criteria. It reports PASS or FAIL in `logs/eval_report.json`.

### 5.7. On PASS -- Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status completed
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" reset-fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "PASS: <step> verified"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

Check if this was the last step and all eval criteria are satisfied. If so:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status mission_complete
```

Then output: `<promise>LOOP_DONE</promise>`

### 5.8. On FAIL -- Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "FAIL: <step> -- <reason>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

If `consecutive_failures` is now >= 3, the circuit breaker trips automatically. Do NOT retry the same approach -- diagnose the root cause first.

### 5.9. Progress Check & Strategy Switching

After each successful step:

1. Calculate: `completed_steps / total_steps`
2. If progress >= 60%, apply **integration-mode constraints**:
   - Do NOT add new non-essential modules or features
   - Prioritize fixing inter-module dependencies
   - Ensure existing tests continue to pass
   - Add README updates and startup documentation
   - Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Switched to integration mode at 60% progress"`

### 5.10. Mission Completion Check

After each successful step, check:

1. Are all playbook steps marked as completed?
2. Have all eval criteria been verified by the eval-agent?
3. Is the mission.md done condition satisfied?

If ALL three are true:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status mission_complete
```

Output: `<promise>LOOP_DONE</promise>`

This signals the stop hook to allow the loop to exit. **Never output this promise unless genuinely complete and verified.**

### 5.11. Log Everything

Use the execution stream for every significant event:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "<event description>"
```

Events worth logging:
- Step start / step complete
- Validation result (PASS/FAIL)
- State transitions
- Errors encountered and how they were resolved
- Files read or modified
- Agent delegations (dual mode)

---

## Completion Signal

When ALL done conditions in mission.md Section 3 are verified by eval-agent AND all playbook steps are complete, output:

```
<promise>LOOP_DONE</promise>
```

**CRITICAL**: Only output this promise when genuinely complete. The stop hook relies on this signal to allow the loop to exit cleanly.

## Error Handling

- On any step failure: log the error, increment failure counter
- After 3 consecutive failures: the circuit breaker trips automatically
- If circuit breaker is tripped: STOP immediately, explain the situation, suggest manual intervention
- On external dependency blockage: skip the step, log it, move to the next
