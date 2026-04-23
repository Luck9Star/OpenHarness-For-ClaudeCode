---
name: harness-execute
description: Main execution workflow for OpenHarness loop iterations. Reads state, executes current playbook step, runs validation, updates state. Supports single and dual execution modes.
---

# Harness Execute | Loop Iteration Workflow

You are inside an OpenHarness loop iteration. Execute exactly one step of the playbook, then validate and update state. Do not improvise — follow this workflow precisely.

## Step-by-Step Workflow

### 1. Read State File

Read `.claude/harness-state.local.md` first. Check:

- **Circuit breaker**: If `circuit_breaker: tripped`, stop immediately. Output a message explaining that manual intervention is required and output `<promise>LOOP_DONE</promise>` so the loop can exit safely.
- **Mission complete**: If `status: mission_complete`, output `<promise>LOOP_DONE</promise>` and stop.

### 2. Recover from Stuck State

If `status: running` (leftover from a previous crash), recover:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Auto-recovered from stale running state"
```

### 3. Set Status to Running

Before doing any work, mark the state:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status running
```

### 4. Read Files in Cache-Optimal Order

Read these files in this exact order to maximize prompt cache hits:

1. `mission.md` — static mission definition, rarely changes
2. `eval-criteria.md` — acceptance criteria, rarely changes
3. `playbook.md` — step-by-step plan, semi-static
4. `.claude/harness-state.local.md` — dynamic state (re-read for current step)

Only load `knowledge/*.md` files on demand if the current step references them.

### 5. Execute Current Step

First, check the current playbook step's **Type** field to determine how to execute it:

#### type: implement (or no type field — backwards compatible)

Default behavior. Check `execution_mode` in the state file:

##### Single Mode (`execution_mode: single`)

You plan AND code directly. Use Claude Code tools (Read, Write, Edit, Bash, Grep) to execute the current playbook step. Work inside the project workspace.

If the `skills` field is set in the state file, load each specified skill using the Skill tool before starting step execution.

After completing the step:
- Log what was done: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Completed <step description>"`
- Run validation (see step 6)

##### Dual Mode (`execution_mode: dual`)

You plan only. Delegate coding to a sub-agent. Check `worktree` field in state file for isolation mode:

**Dual Mode — In-Place (worktree: off, default)**

Spawn `harness-dev-agent` as a regular subagent — it works in the same directory. The main benefit is **context protection**: coding details stay in the subagent's context, keeping yours clean.

1. Read the current step requirements from the playbook
2. Construct a detailed prompt that includes:
   - The exact task to perform
   - File paths to read and modify
   - Constraints from mission.md (especially Prohibited Operations)
   - The eval criteria this step must satisfy
   - The skills to load (if `skills` field is set in state file) — format as: "Use skills: skill1, skill2"
3. Spawn `harness-dev-agent` WITHOUT worktree isolation
4. Wait for the agent to complete
5. Log the delegation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Delegated <step> to harness-dev-agent (in-place)"`

**Dual Mode — Worktree (worktree: on)**

Spawn `harness-dev-agent` with git worktree isolation — code changes happen on a separate branch.

1. Read the current step requirements from the playbook
2. Construct a detailed prompt (same as above)
3. Spawn `harness-dev-agent` with `isolation: "worktree"` for git worktree isolation
4. Wait for the agent to complete
5. Merge the worktree changes back to the main branch
6. Log the delegation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Delegated <step> to harness-dev-agent in worktree"`

#### type: review

ALWAYS spawn `harness-review-agent` — read-only code review, regardless of execution mode (both single and dual).

1. Read the current step description from the playbook to understand what was implemented
2. Spawn `harness-review-agent` with:
   - The step description and scope
   - Instructions to examine the relevant files and produce a review report
3. The review agent writes its findings to `logs/review_report.json` — it does NOT modify any source files
4. After the review agent completes, read `logs/review_report.json` to check the verdict:
   - `pass` — log and proceed to the next step
   - `conditional-pass` — log warnings, proceed but note issues for the next fix step
   - `fail` — log critical issues, the next step (expected to be a `fix` step) will address them
5. Log the result: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Review completed: <overall verdict>"`
6. Skip validation (step 6) for review steps — proceed directly to step 7/8 state updates

#### type: fix

Read the review report from the previous review step, then apply fixes.

1. Read `logs/review_report.json` to get the list of issues from the review
2. If the report is missing or the overall verdict was `pass`, skip this step — log and advance
3. Extract the issue list and format fix instructions

Then dispatch based on execution mode:

- **Single mode**: Fix the issues yourself. Use Read, Edit, Write, Bash to address each issue from the report. Work through critical and major issues first, then minor ones.
- **Dual mode**: Spawn `harness-dev-agent` with a prompt that includes:
  - The full list of issues from `logs/review_report.json`
  - Specific file paths, line numbers, and suggested fixes for each issue
  - Instructions to address critical and major issues, then minor ones

After fixes are applied:
- Log what was fixed: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Applied fixes for <N> issues from review"`
- Run validation (see step 6) if the step has completion criteria

#### type: verify

Spawn `harness-eval-agent` for independent validation — regardless of execution mode.

1. Read the current step description and eval criteria
2. Spawn `harness-eval-agent` with:
   - The eval criteria from `eval-criteria.md`
   - The current step description
   - Instructions to independently verify without reading implementation details
3. The eval-agent reports PASS or FAIL
4. Log the result: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Verify: <PASS or FAIL>"`
5. Proceed to step 6 for additional verify_instruction handling, or directly to step 7/8

### 6. Run Validation

After step execution, validate the result:

#### If `verify_instruction` is set in state:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/eval-check.py"
```

This runs the configured verify command and reports pass/fail.

#### For oracle-isolated evaluation:

Spawn `harness-eval-agent` with:
- The eval criteria from `eval-criteria.md`
- The current step description
- Instructions to independently verify without reading your implementation

The eval-agent reports PASS or FAIL.

### 7. On PASS — Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status completed
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" reset-fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "PASS: <step> verified"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

Check if this was the last step in the playbook and all eval criteria are satisfied. If so:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status mission_complete
```

Then output: `<promise>LOOP_DONE</promise>`

### 8. On FAIL — Update State

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" fail
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "FAIL: <step> — <reason>"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status idle
```

Review the failure reason. If `consecutive_failures` is now >= 3, the circuit breaker will trip automatically (handled by `state-manager.py fail`). Do NOT retry the same approach — diagnose the root cause first.

### 9. Mission Completion Check

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

### 10. Log Everything

Use the execution stream for every significant event:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "<event description>"
```

Events worth logging:
- Step start / step complete
- Validation result (PASS/FAIL)
- State transitions (idle -> running -> completed/failed -> idle)
- Errors encountered and how they were resolved
- Files read or modified
- Agent delegations (dual mode)

The execution stream is the L3 memory layer — future sessions and debugging depend on these records.
