---
description: "Show current OpenHarness workspace status"
allowed-tools: ["Bash", "Read"]
---

# /harness-status — Workspace Status Report

Display the current status of the OpenHarness workspace. Follow these steps:

## Step 1: Check Workspace Exists

Read `.claude/harness-state.local.md`. If it does not exist, report:

> No OpenHarness workspace detected in the current directory. Run `/harness-init` to create one.

Then stop.

## Step 2: Read State and Mission

Read these files:
1. `.claude/harness-state.local.md` — current state
2. `mission.md` — task name and done conditions
3. `progress.md` — execution history (if exists)

## Step 3: Display Status Report

Render the following information:

### Workspace Status

| Field | Value |
|---|---|
| Task Name | _(from mission.md Section 1)_ |
| Execution Mode | _(from state file)_ |
| Current Status | _(from state file)_ |
| Current Step | _(from state file)_ |
| Total Executions | _(from state file)_ |
| Consecutive Failures | _(from state file)_ |
| Circuit Breaker | _(from state file)_ |
| Verify Command | _(from state file)_ |
| Last Execution | _(from state file)_ |

### Completion Progress

List each done condition from mission.md Section 3 with its status:

| # | Condition | Status |
|---|---|---|
| 1 | _(condition)_ | _(met/unmet)_ |

### Execution History (last 5 entries)

Show the most recent entries from progress.md (if any exist).

## Step 4: Conditional Messages

**If circuit breaker is tripped**, display:

> **CIRCUIT BREAKER TRIPPED** — The harness has detected 3 or more consecutive failures and has halted execution. This requires manual intervention.
>
> Suggested actions:
> - Read the execution log in `logs/execution_stream.log` to diagnose the root cause
> - Fix the underlying issue manually
> - Reset the circuit breaker with: `python3 scripts/state-manager.py reset-fail`
> - Update the state to running: `python3 scripts/state-manager.py update status running`

**If mission is complete** (status: `mission_complete`), display:

> **MISSION COMPLETE** — All done conditions have been verified by the eval-agent.
>
> Summary of completed work is available in `progress.md`.

**If status is `running`**, display:

> Loop is currently active. The stop hook will trigger the next iteration automatically.

**If status is `idle`**, display:

> Workspace is idle and ready for the next iteration. Run `/harness-dev` to start the development loop.

**If status is `paused`**, display:

> **PAUSED FOR HUMAN REVIEW** — The harness paused at a human-review checkpoint.
>
> To resume: `/harness-dev --resume`
> To review progress: check `progress.md` and `logs/execution_stream.log`

**If status is `failed`**, display:

> Last iteration failed with N consecutive failure(s). The loop will retry automatically unless the circuit breaker trips (at 3 failures).
