---
description: "Initialize a new OpenHarness autonomous development task"
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify COMMAND]"
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# /harness-start

Initialize a new OpenHarness autonomous development task workspace.

## Instructions

Parse the user's arguments from `$ARGUMENTS`:

- **Task description**: everything before any `--` flags
- **Mode**: `--mode single` (default) or `--mode dual`
- **Verify command**: `--verify "command"` (optional)

If no task description is provided, prompt the user:

```
What task would you like the harness to execute? Describe it in one sentence.
```

Then proceed with the init workflow.

## Workflow

1. **Parse arguments** from `$ARGUMENTS`:
   - Extract task description (text before any flags)
   - Extract `--mode` value (default: `single`)
   - Extract `--verify` value (default: empty)

2. **Load the harness-init skill**: read `${CLAUDE_PLUGIN_ROOT}/skills/harness-init/SKILL.md`

3. **Follow the init workflow** from that skill file exactly:
   - If arguments provided all required info, skip the collection step and use what was given
   - Generate the task name from the description
   - Write mission.md, playbook.md, eval-criteria.md, progress.md — all fully filled, no placeholders
   - Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-command>"`
   - Verify all files are created correctly

4. **After initialization**, report the ready state and suggest:

```
Harness workspace is ready. Start the development loop with /harness-dev
```

## Important Rules

- Never leave `[placeholder]` text in any generated file. All content must be concrete and task-specific.
- If the task description is ambiguous, make reasonable assumptions and fill in concrete details.
- The verify command should match the project's test runner if detectable, otherwise leave it to user input.
- Always run state-manager.py as the last step — it creates the `.claude/` directory and state file.
