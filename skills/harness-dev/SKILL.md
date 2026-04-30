---
name: harness-dev
description: "Autonomous development loop for OpenHarness. Parses arguments, manages loop state, executes playbook steps via single or dual mode, validates via eval-agent. Trigger: /harness-dev."
argument-hint: "[--mode single|dual] [--max-iterations N] [--max-concurrency N] [--resume]"
allowed-tools: ["Bash", "Agent", "Read", "Write", "Edit", "Grep", "Glob"]
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
5. **Overlap protection (cron safety)**: Read the state file. If `status: running`, check `last_execution_time`:
   - If `last_execution_time` is within the last 10 minutes: another agent is likely active. Log and exit: `"Overlap detected: status is 'running' and last_execution_time is recent (<10 min). Another agent may be active. Exiting to prevent concurrent state corruption."` Format: ISO 8601. Compare using Python datetime parsing.
   - If `last_execution_time` is older than 10 minutes: treat as crash recovery (section 5.2 will handle it).

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

- `--mode single`: Agent plans and codes directly, with oracle validation
- `--mode dual`: Agent plans only, then spawns sub-agents for coding. Protects main agent context from explosion.
- `--max-iterations N`: Stop the loop after N iterations (0 = infinite)
- `--resume`: Resume from a paused state (after human-review checkpoint)
- `--max-concurrency N`: Override inferred parallelism (see agent-spawn.md)

If `--mode` is not specified, infer from task complexity:
- **Single**: targeted change, 1-2 files, simple fix
- **Dual**: 3+ files, multi-module, feature addition, cross-cutting change

Note: The `--verify` instruction and `--skills` are preserved from the existing state file (set by `/harness-start`) and forwarded to the loop setup script in Step 3.

## Step 3: Initialize Loop State

**If `--resume` was specified, skip this step entirely and proceed to Step 5.** The existing state file will be used as-is.

**Otherwise**, check if the existing state is reusable before reinitializing:

```bash
# Read current state
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" read
```

Then read `.claude/harness/mission.md` Section 1 (Mission Name). Compare with the state's `task_name`:

- **If state `task_name` matches mission name** AND state is in a non-terminal status (`idle` or `running`) → **Skip reinitialization.** The state is valid for this mission. Proceed to Step 4.

- **If state `task_name` does NOT match** OR state is in a terminal status (`mission_complete` or `failed`) → Reinitialize with `--force`:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/setup-harness-loop.sh" <task-name> --mode <mode> --max-iterations <N> --verify "<verify_instruction>" --skills "<skills>" --loop-mode <in-session|clean> --cycle-steps <start,end> --min-cycles <N> --max-cycles <N> --force
```

Extract `verify_instruction`, `skills`, `loop_mode`, `cycle_steps`, `min_cycles`, and `max_cycles` from the existing state JSON before reinitializing. Use the task name from `.claude/harness/mission.md` Section 1. If any field is empty/absent, omit the corresponding flag.

**Always include `--force`** when reinitializing — you've already preserved the important values and the old state needs overwriting.

Verify the output confirms successful initialization.

## Step 4: Mode Explanation

**If single mode**, explain to the user:
> Single mode active. I will plan each playbook step, implement the code directly, then spawn an eval-agent for independent verification. The loop continues until all done conditions are met or the circuit breaker trips.

**If dual mode**, explain to the user:
> Dual mode active. I will plan each playbook step, then spawn sub-agents for implementation. Multiple agents run in parallel when steps are independent (inferred concurrency from task structure). This protects my context while maximizing throughput.

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

**Context Hygiene Rule**: Treat the state file as the single source of truth for step status and completion. Do NOT assume a step is complete because earlier context says 'PASS' or 'done' — always re-read the state file. Recent tool output (error messages, file contents) from the current turn is valid context.

Each iteration follows this exact workflow. Do not improvise -- follow it precisely.

### 5.1. Read State File

Read `.claude/harness-state.json` first. Check in this exact order:

1. **Circuit breaker**: If `circuit_breaker: tripped`, stop immediately. Output a message explaining that manual intervention is required and output `<promise>LOOP_DONE</promise>` so the loop can exit safely.

2. **Mission identity gate** (CRITICAL — prevents stale-state early exit):
   Read the `task_name` field from the state file. Then read `.claude/harness/mission.md` Section 1 (Mission Name). **If they differ**, the state file is STALE from a previous mission — you MUST reinitialize before doing anything else:
   ```
   # Preserve ALL cycle-related fields from the stale state, then reinitialize
   mkdir -p .claude/harness/logs
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" init <mission-name-from-mission-md> --mode <execution_mode-from-state> --max-iterations <from-state> --verify "<verify_instruction-from-state>" --skills "<skills-from-state>" --loop-mode <loop_mode-from-state> --cycle-steps <cycle_steps-from-state> --min-cycles <min_cycles-from-state> --max-cycles <max_cycles-from-state> --force
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

Then, check the current playbook step's **Type** field. For step-type instructions, follow these rules:

- **For `implement` and `fix` steps**: Follow standard patterns (read existing code, make targeted edits, verify with build/test). No additional reference needed.
- **For `review`, `verify`, and `human-review` steps**: Read `${CLAUDE_PLUGIN_ROOT}/skills/harness-dev/loop-reference.md` for detailed step-type instructions.

Step-type summary:
- `implement` — Code directly (single mode) or delegate to agent (dual/parallel)
- `review` — Spawn review agent with cumulative scope
- `fix` — Apply fixes from review_report.json + compliance gaps
- `human-review` — Pause for human, advance step, output LOOP_PAUSE
- `verify` — Spawn eval-agent for independent validation

**Agent Selection (all modes)**

ALL step types route through the unified Agent Router. See `agent-spawn.md` for full details.
Priority: `specialist:` field → `route_keywords` match → step-type fallback.

**Phase Detection**

Read `current_phase` from the state file:
- If `current_phase` is `null` or absent → **Linear mode** (execute single step, current behavior)
- If `current_phase` is a number → **Phase mode** (execute all pending steps in current Phase)

**Linear Mode** (backward compatible)

Execute the single step indicated by `current_step`. Follow step-type rules above (implement/fix use standard patterns; review/verify/human-review read loop-reference.md). For agent selection, use the unified Router (see `agent-spawn.md`).

### Phase Mode (Parallel Execution)

When the playbook assigns steps the same Phase number, they execute in parallel. See `${CLAUDE_PLUGIN_ROOT}/skills/harness-dev/agent-spawn.md` Section 3 for the detailed spawn procedure.

Key rules:
- Spawn all parallel agents in a single message block
- Each agent gets step-specific instructions from loop-reference.md
- On any agent failure in a parallel phase, mark failed steps as failed but PRESERVE completed steps — their work is valid. Do not re-run completed steps.
- After all agents complete, run state-manager step-advance for each

### 5.6. Run Validation

**MANDATORY: eval-agent MUST be spawned. Self-assessment is NEVER valid.**

After step execution (except review steps), validate by spawning `harness-eval-agent` with:
- The eval criteria from `.claude/harness/eval-criteria.md`
- The current step description
- The verify_instruction (if set in state) -- the agent interprets this independently
- Instructions to independently verify without reading your implementation

The eval-agent checks file existence, runs verify commands, and evaluates semantic criteria. It reports PASS or FAIL in `.claude/harness/logs/eval_report.json`.

**Anti-shortcut guard**: You MUST NOT skip eval-agent spawning and reason about results yourself. This includes:
- Reading review_report.json and mentally checking criteria
- Comparing finding counts between cycles without eval-agent
- Declaring convergence because "findings look reduced"

If you are in a cycle loop and considering whether to skip the verify step — DON'T. Every cycle iteration requires an independent eval-agent spawn.

### 5.7. On PASS -- Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status completed
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" reset-fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "PASS: <step> verified"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

**Cycle behavior**: If `cycle_steps` is set in the state file (e.g., `[1, 3]`), `step-advance` will wrap back to the cycle start when reaching the cycle end. The cycle continues until **all** eval criteria pass in a single iteration AND `cycle_iteration >= min_cycles` (if set in state file). This is the standard pattern for iterative review-fix-verify workflows:
```
Step 1 (review) → Step 2 (fix) → Step 3 (verify) → back to Step 1 (review) → ... → mission_complete
```

**Convergence enforcement** (state-file driven):
- `min_cycles` in state file: The eval-agent convergence criterion MUST check `cycle_iteration >= min_cycles` before allowing PASS. If `min_cycles > 0` and cycle < min_cycles, convergence FAILS automatically.
- `max_cycles` in state file: `step-advance` will trip the circuit breaker when `cycle_iteration >= max_cycles`, preventing infinite loops. No manual playbook reading needed.

**Note**: The eval-agent convergence standard is authoritative — it may require additional conditions beyond dimension counts (e.g., evidence sections). The description above is informational; the actual convergence check is defined in eval-criteria.md.

**Phase-aware advancement**: After marking a step as `completed` via `step-status`, check if all steps in the current Phase are complete:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" phase-status
```
If all steps show `completed`, advance to the next Phase:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" phase-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Phase {N} complete, advancing to Phase {N+1}"
```

Check if all eval criteria are satisfied. For cycle missions, ALL criteria must pass in the same cycle iteration AND convergence criterion must pass (which includes min_cycles check) — not accumulated across iterations. If so:

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
   **Skip condition**: If the task has only one implement step or is a non-code task, skip this integration gate entirely.
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
