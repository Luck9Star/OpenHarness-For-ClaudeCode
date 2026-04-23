---
description: "Start autonomous development loop for an OpenHarness task"
argument-hint: "[--mode single|dual] [--worktree] [--max-iterations N]"
allowed-tools: ["Bash", "Agent", "Read", "Write", "Edit"]
---

# /harness-dev — Autonomous Development Loop

You are starting the OpenHarness autonomous development loop. Follow these steps precisely.

## Step 1: Workspace Check

Check if an OpenHarness workspace exists in the current directory:

- Look for `.claude/harness-state.local.md`
- Look for `mission.md`

If **no harness workspace exists**:
1. Ask the user: "No OpenHarness workspace detected. Provide a task description to initialize one, or run `/harness-start` first."
2. If the user provides a description, run `/harness-start` with that description.
3. If the user says to run `/harness-start`, invoke the harness-init skill and wait for it to complete.

## Step 2: Parse Arguments

Parse the command arguments (if any were provided):

- `--mode single` (default): Agent plans and codes directly, with oracle validation
- `--mode dual`: Agent plans only, then spawns `harness-dev-agent` for coding. Protects main agent context from explosion.
- `--worktree`: In dual mode, run dev-agent in an isolated git worktree (code changes in separate branch, merge on success). Without this flag, dev-agent works in the same directory — still protects main agent context but without git isolation.
- `--max-iterations N`: Stop the loop after N iterations (0 = infinite)

If `--mode` is not specified, default to `single`.
`--worktree` only has effect in `dual` mode (ignored in single mode).

Note: The `--verify` instruction is read from the state file (set during `/harness-start`). Do not specify it here.

## Step 3: Initialize Loop State

Run the setup script to create or reset the loop state file:

```bash
bash .claude-plugin-path/scripts/setup-harness-loop.sh <task-name> --mode <mode> [--worktree] --max-iterations <N>
```

Use the task name from `mission.md` (Section 1: Mission Name).
The verify instruction is already in the state file from `/harness-start` — no need to pass it again.

Verify the output confirms successful initialization.

## Step 4: Mode Explanation

**If single mode**, explain to the user:
> Single mode active. I will plan each playbook step, implement the code directly, then spawn an eval-agent for independent verification. The loop continues until all done conditions are met or the circuit breaker trips.

**If dual mode (without --worktree)**, explain to the user:
> Dual mode active (in-place). I will plan each playbook step, then spawn `harness-dev-agent` as a subagent to implement code in the current directory. This protects my context from explosion while keeping all changes in-place. After each coding pass, an eval-agent validates independently.

**If dual mode (with --worktree)**, explain to the user:
> Dual mode active (worktree). I will plan each playbook step, then spawn `harness-dev-agent` in an isolated git worktree to implement code. Changes happen on a separate branch and are merged back on success. After each coding pass, an eval-agent validates independently.

## Step 5: Read Mission and Begin Execution

Read these files in cache-optimal order:
1. `mission.md` — the task contract
2. `eval-criteria.md` — validation standards
3. `playbook.md` — execution steps
4. `.claude/harness-state.local.md` — current state

Update the state file to `status: running`:

```bash
python3 scripts/state-manager.py update status running
```

Then begin executing the playbook from the current step.

### Execution Loop (each iteration):

1. **Read state** — Load current step, failure count, circuit breaker status
2. **Check circuit breaker** — If `tripped`, STOP and report to user
3. **Check completion** — If all done conditions verified, output `<promise>LOOP_DONE</promise>` and stop
4. **Plan** — Analyze the current step from playbook.md, determine what code changes are needed
5. **Execute**:
   - **Single mode**: Write/edit the code yourself
   - **Dual mode (without --worktree)**: Spawn `harness-dev-agent` via the Agent tool (no worktree isolation, agent works in same directory)
   - **Dual mode (with --worktree)**: Spawn `harness-dev-agent` via the Agent tool with `isolation: "worktree"` for git worktree isolation
6. **Verify** — If a `--verify` command was provided, run it
7. **Validate** — Spawn `harness-eval-agent` to independently validate against eval-criteria.md
8. **Update state**:
   - If step succeeded: `state-manager.py step-advance` and `state-manager.py reset-fail`
   - If step failed: `state-manager.py fail`
9. **Log** — `state-manager.py log "Step N: result description"`
10. **Continue** — The stop hook will trigger the next loop iteration

### Completion Signal

When ALL done conditions in mission.md Section 3 are verified by eval-agent AND all playbook steps are complete, output:

```
<promise>LOOP_DONE</promise>
```

**CRITICAL**: Only output this promise when genuinely complete. The stop hook relies on this signal to allow the loop to exit cleanly. Never output it if work remains or verification has not passed.

### Error Handling

- On any step failure: log the error, increment failure counter
- After 3 consecutive failures: the circuit breaker trips automatically
- If circuit breaker is tripped: STOP immediately, explain the situation, and suggest manual intervention
- On external dependency blockage: skip the step, log it, move to the next
