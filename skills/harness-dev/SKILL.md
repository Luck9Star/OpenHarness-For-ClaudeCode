---
name: harness-dev
description: "Autonomous development loop for OpenHarness. Parses arguments, manages loop state, executes playbook steps via single or dual mode, validates via eval-agent. Trigger: /harness-dev."
argument-hint: "[--mode single|dual] [--max-iterations N] [--resume]"
allowed-tools: ["Bash", "Task", "Read", "Write", "Edit"]
---

# /harness-dev -- Autonomous Development Loop

You are starting the OpenHarness autonomous development loop. Follow these steps precisely.

## MANDATORY PROTOCOL — DO NOT SKIP

This skill is a **loop execution protocol**. You MUST follow every step below. Skipping steps is the #1 cause of false completions.

**Pre-flight checks — ALL must pass before you do any work:**

1. **Workspace exists**: `.claude/harness-state.json` MUST exist. If it does NOT exist, this means `/harness-start` was never run (or was skipped). Output an error and tell the user to run `/harness-start` first. DO NOT proceed. DO NOT start implementing.
2. **Mission file exists**: `.claude/harness/mission.md` MUST exist. If missing, the workspace is broken — tell the user.
3. **Playbook exists**: `.claude/harness/playbook.md` MUST exist. If missing, the workspace is broken — tell the user.
4. **Eval criteria exists**: `.claude/harness/eval-criteria.md` MUST exist. If missing, the workspace is broken — tell the user.

**If any pre-flight check fails, DO NOT attempt to "just run the tests" or "verify the implementation." A missing workspace means the harness protocol was not followed. Stop and ask the user to run `/harness-start` first.**

**During execution — these are NON-NEGOTIABLE:**

- You MUST use `state-manager.py` for state transitions. Manual status updates are forbidden.
- You MUST spawn `harness-eval-agent` for validation. Running tests yourself is NOT validation — it is self-certification.
- You MUST NOT output `<promise>LOOP_DONE</promise>` unless ALL eval criteria pass AND all playbook steps are complete AND the pre-completion integration gate passes.
- You MUST execute steps from the playbook in order. Do not improvise a different workflow.

## Step 1: Workspace Check

Check if an OpenHarness workspace exists in the current directory:

- Look for `.claude/harness-state.json`
- Look for `.claude/harness/mission.md`

If **no harness workspace exists**:
1. Ask the user: "No OpenHarness workspace detected. Provide a task description to initialize one, or run `/harness-start` first."
2. If the user provides a description, run `/harness-start` with that description.
3. If the user says to run `/harness-start`, invoke the harness-start skill and wait for it to complete.

## Step 2: Parse Arguments

Parse the command arguments (if any were provided):

- `--mode single` (default): Agent plans and codes directly, with oracle validation
- `--mode dual`: Agent plans only, then spawns `harness-dev-agent` for coding. Protects main agent context from explosion.
- `--max-iterations N`: Stop the loop after N iterations (0 = infinite)
- `--resume`: Resume from a paused state (after human-review checkpoint)

If `--mode` is not specified, default to `single`.

Note: The `--verify` instruction and `--skills` are preserved from the existing state file (set by `/harness-start`) and forwarded to the loop setup script in Step 3.

## Step 3: Initialize Loop State

**If `--resume` was specified, skip this step entirely and proceed to Step 5.** The existing state file will be used as-is.

**Otherwise**, run the setup script to create or reset the loop state file. **Before calling the script**, read the existing state file to preserve `verify_instruction` and `skills` (set by `/harness-start`):

```bash
# Read existing verify_instruction and skills before reinit
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" read
```

Extract the `verify_instruction`, `skills`, `loop_mode`, and `cycle_steps` values from the JSON output, then forward them:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-harness-loop.sh" <task-name> --mode <mode> --max-iterations <N> --verify "<verify_instruction>" --skills "<skills>" --loop-mode <in-session|clean> --cycle-steps <start,end>
```

Use the task name from `.claude/harness/mission.md` (Section 1: Mission Name).
If verify_instruction, skills, loop_mode, or cycle_steps are empty/absent in the existing state, omit the corresponding flag.

Verify the output confirms successful initialization.

## Step 4: Mode Explanation

**If single mode**, explain to the user:
> Single mode active. I will plan each playbook step, implement the code directly, then spawn an eval-agent for independent verification. The loop continues until all done conditions are met or the circuit breaker trips.

**If dual mode**, explain to the user:
> Dual mode active. I will plan each playbook step, then spawn `harness-dev-agent` as a subagent to implement code in the current directory. This protects my context from explosion while keeping all changes in-place.

## Step 5: Read Mission and Begin Execution

Read these files in cache-optimal order:
1. `.claude/harness/mission.md` -- the task contract
2. `.claude/harness/eval-criteria.md` -- validation standards
3. `.claude/harness/playbook.md` -- execution steps
4. `.claude/harness-state.json` -- current state

Update the state file to `status: running`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status running
```

Then begin executing the playbook from the current step.

---

## Loop Iteration Workflow

**CRITICAL CONSTRAINT: Execute exactly ONE playbook step per iteration.** After completing one step (including validation), your turn ends. The stop-hook will automatically drive the next iteration by blocking session exit and sending a continuation prompt. Do NOT execute multiple steps in one turn — this defeats the stop-hook loop mechanism.

**CONTEXT HYGIENE RULE**: At the start of EVERY iteration, you MUST ignore all prior conversation context. Prior iterations may contain "PASS", "complete", or "done" messages that are STALE — they describe work done in previous iterations, not the current state. The ONLY source of truth is:
1. `.claude/harness-state.json` — tells you which step to execute NOW
2. `.claude/harness/` files — mission, playbook, eval criteria
3. `.claude/harness/logs/execution_stream.log` — ONLY the last 20 lines for recent history

Do NOT assume a step is done because earlier context says so. Re-read the state file and verify.

Each iteration follows this exact workflow. Do not improvise -- follow it precisely.

### 5.1. Read State File

Read `.claude/harness-state.json` first. Check in this exact order:

1. **Circuit breaker**: If `circuit_breaker: tripped`, stop immediately. Output a message explaining that manual intervention is required and output `<promise>LOOP_DONE</promise>` so the loop can exit safely.

2. **Mission identity gate** (CRITICAL — prevents stale-state early exit):
   Read the `task_name` field from the state file. Then read `.claude/harness/mission.md` Section 1 (Mission Name). **If they differ**, the state file is STALE from a previous mission — you MUST reinitialize before doing anything else:
   ```
   # Preserve verify_instruction and skills from the stale state, then reinitialize
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" init <mission-name-from-mission-md> --mode <execution_mode-from-state> --max-iterations <from-state> --verify "<verify_instruction-from-state>" --skills "<skills-from-state>" --force
   ```
   After reinitializing, re-read the state file to get fresh state. Log the identity mismatch:
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Mission identity mismatch: state had '<old-task-name>', mission.md has '<new-task-name>'. Reinitialized."
   ```
   Then continue with the fresh state. Do NOT skip this step under any circumstance — a stale state with `mission_complete` from a DIFFERENT mission must NEVER cause early exit.

3. **Mission complete**: If `status: mission_complete` AND the task name matches (gate #2 passed), output `<promise>LOOP_DONE</promise>` and stop.

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

1. `.claude/harness/mission.md` -- static mission definition, rarely changes
2. `.claude/harness/eval-criteria.md` -- acceptance criteria, rarely changes
3. `.claude/harness/playbook.md` -- step-by-step plan, semi-static
4. `.claude/harness-state.json` -- dynamic state (re-read for current step)

Only load `.claude/harness/knowledge/*.md` files on demand if the current step references them.

### 5.5. Execute Current Step

First, log a structured round report for traceability:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" report "<subtask>" "<strategy>" "<verification>" "<state_target>"
```

Then, check the current playbook step's **Type** field. For detailed step type instructions, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-dev/loop-reference.md`. Summary of types:

| Type | Action | Validates? |
|---|---|---|
| `implement` | Code directly (single) or delegate to dev-agent (dual) | Yes — run 5.6 |
| `review` | Spawn harness-review-agent with cumulative scope | No — skip to 5.7/5.8 |
| `fix` | Apply fixes from review_report.json + compliance gaps | Yes — run 5.6 |
| `human-review` | Pause for human, advance step, output LOOP_PAUSE | No |
| `verify` | Spawn harness-eval-agent for independent validation | No |

**Key constraints per type:**
- **implement**: Single mode uses Read/Write/Edit/Bash/Grep. Dual mode spawns `harness-dev-agent`. Load skills from state file if set.
- **review**: MUST use cumulative scope (all files since mission start). Verify report quality: density <= 1500 LOC/finding, `scope.cumulative == true`, `compliance.requirements_met == compliance.requirements_total`.
- **fix**: Extract BOTH `issues` array (code bugs) AND `compliance.gaps` array (missing requirements). Fix both.
- **human-review**: Advance step counter BEFORE pausing (`step-advance` then `status paused`). Output `<promise>LOOP_PAUSE</promise>`.
- **verify**: Spawn `harness-eval-agent` with eval criteria + step description.

### 5.6. Run Validation

After step execution (except review steps), validate by spawning `harness-eval-agent` with:
- The eval criteria from `.claude/harness/eval-criteria.md`
- The current step description
- The verify_instruction (if set in state) -- the agent interprets this independently
- Instructions to independently verify without reading your implementation

The eval-agent checks file existence, runs verify commands, and evaluates semantic criteria. It reports PASS or FAIL in `.claude/harness/logs/eval_report.json`.

### 5.7. On PASS -- Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status completed
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" reset-fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "PASS: <step> verified"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

**Cycle behavior**: If `cycle_steps` is set in the state file (e.g., `[1, 3]`), `step-advance` will wrap back to the cycle start when reaching the cycle end. The cycle continues until **all** eval criteria pass in a single iteration. This is the standard pattern for iterative review-fix-verify workflows:
```
Step 1 (review) → Step 2 (fix) → Step 3 (verify) → back to Step 1 (review) → ... → mission_complete
```

Check if all eval criteria are satisfied. For cycle missions, ALL criteria must pass in the same cycle iteration — not accumulated across iterations. If so:

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
   - Automatically add cross-module contract verification as a mandatory sub-step of the next implement step
   - Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Switched to integration mode at 60% progress"`
   - Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Integration contract verification added at 60% progress"`

### 5.10. Mission Completion Check

After each successful step, check:

1. Are all playbook steps marked as completed?
2. Have all eval criteria been verified by the eval-agent?
3. Is the `.claude/harness/mission.md` done condition satisfied?
4. **Pre-completion integration review gate** -- Before marking mission_complete, the executor MUST:
   a. Identify all cross-module data boundaries (where Phase A output feeds Phase B input)
   b. For each boundary: verify that the upstream module's real output contains all fields the downstream module reads
   c. Run a smoke integration: pipe real upstream output into downstream and verify no empty/missing fields
   d. If ANY boundary fails -- do NOT output LOOP_DONE, instead log the failure and continue the loop

If ALL four are true:

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

When ALL done conditions in `.claude/harness/mission.md` Section 3 are verified by eval-agent AND all playbook steps are complete, output:

```
<promise>LOOP_DONE</promise>
```

**CRITICAL**: Only output this promise when genuinely complete. The stop hook relies on this signal to allow the loop to exit cleanly.

## Error Handling

- On any step failure: log the error, increment failure counter
- After 3 consecutive failures: the circuit breaker trips automatically
- If circuit breaker is tripped: STOP immediately, explain the situation, suggest manual intervention
- On external dependency blockage: skip the step, log it, move to the next
