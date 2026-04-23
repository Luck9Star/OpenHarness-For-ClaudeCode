---
description: "Modify an existing OpenHarness task (verify instruction, mission, playbook, eval criteria)"
argument-hint: "[--verify INSTRUCTION] [--mission TEXT] [--playbook-step N TEXT] [--append-step TEXT] [--mode single|dual]"
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# /harness-edit — Modify Existing Harness Task

Modify an existing OpenHarness task's configuration without reinitializing the workspace.

## Instructions

Parse the user's arguments from `$ARGUMENTS`. All flags are optional — only specified flags are applied.

### Available Flags

| Flag | Description |
|---|---|
| `--verify INSTRUCTION` | Update the verify instruction (natural language AI instruction for eval-agent) |
| `--mission TEXT` | Append or update mission description |
| `--playbook-step N TEXT` | Replace playbook step N with new text |
| `--append-step TEXT` | Append a new step to the playbook |
| `--mode single\|dual` | Switch execution mode |
| `--from-file PATH` | Load task modifications from a file (e.g., superpowers plan) |

### Interactive Mode

If no flags are provided, enter interactive mode:

1. Read the current task state: `.claude/harness-state.local.md`
2. Read `mission.md` for current mission
3. Ask the user what they want to modify:
   ```
   Current task: <task-name>
   Current mode: <mode>
   Current verify: <instruction>
   
   What would you like to modify?
   1. Verify instruction
   2. Mission description/objective
   3. Playbook steps (add/remove/modify)
   4. Eval criteria
   5. Execution mode
   6. Load from file
   ```
4. Apply the selected modification

## Workflow

1. **Check workspace exists** — verify `.claude/harness-state.local.md` and `mission.md` exist. If not, tell the user to run `/harness-start` first.

2. **Parse arguments** — determine which modifications to apply.

3. **Apply modifications**:

   ### --verify
   Update the verify instruction in the state file:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py update verify_instruction "NEW INSTRUCTION"
   ```
   Also update the `Verify Instruction` row in the state file's System Status table.

   ### --mission
   Read the current `mission.md`, update the Mission Objective section with the new text while preserving the rest. Use the Edit tool to make targeted changes.

   ### --playbook-step
   Read `playbook.md`, locate step N, replace its content with the provided text. Preserve step numbering and format.

   ### --append-step
   Read `playbook.md`, add a new step at the end with the provided description. Update the dependency diagram if one exists.

   ### --mode
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py update execution_mode <single|dual>
   ```

   ### --from-file
   Read the specified file and extract:
   - Task description / objectives → update mission.md
   - Implementation steps → update playbook.md
   - Verification criteria → update eval-criteria.md
   - If the file is a superpowers plan, parse its sections (architecture, components, implementation sequence) to populate the harness workspace files.

4. **Log the change**:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py log "Task modified: <summary of changes>"
   ```

5. **Report changes**:
   ```
   Harness task updated:
    - <list each change applied>
   
   Current state: <status>
   Current step: <step>
   ```

## Important Rules

- Do NOT reset the execution state (status, step, failures) unless the user explicitly requests it.
- Do NOT modify `progress.md` — it's a log, not editable.
- Preserve existing content when making targeted updates — don't rewrite entire files for small changes.
- If the task is currently `running`, warn the user and ask for confirmation before modifying.
