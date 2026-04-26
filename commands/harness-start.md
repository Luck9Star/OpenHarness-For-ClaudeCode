---
description: "Initialize a new OpenHarness autonomous development task with interactive wizard"
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2] [--quick]"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Grep", "Glob"]
---

You are running the OpenHarness workspace initialization protocol. This is NOT a coding task — you are ONLY creating workspace files. DO NOT implement any features.

## MANDATORY PROTOCOL — ALL 7 gates must pass before this command completes:

1. **Workspace directory**: `mkdir -p .claude/harness/logs`
2. **mission.md**: Write to `.claude/harness/mission.md` — NO `[placeholder]` markers
3. **playbook.md**: Write to `.claude/harness/playbook.md` — concrete steps with types
4. **eval-criteria.md**: Write to `.claude/harness/eval-criteria.md` — machine-verifiable checks
5. **progress.md**: Write to `.claude/harness/progress.md`
6. **State init**: Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init` — must succeed
7. **Verify**: Re-read all 4 files, confirm NO `[placeholder]` remains

## HARD RULES (violating any of these = protocol failure):

- **NO source code reading**: Do NOT read/scan any `.py`, `.rs`, `.ts`, `.js` files. The ONLY exception is the `--from-plan` file.
- **NO other skills**: Do NOT invoke Skill tool for pua, superpowers, orch, tdd, or any other skill. `--skills` are stored for later use by harness-dev.
- **NO implementation**: Do NOT create/modify source code files. This command ONLY creates workspace files under `.claude/harness/`.
- **NO "already done" shortcut**: Even if features appear already implemented, you MUST still create all workspace files and run state-manager.py init.

## Why these rules: Reading source code fills your context with implementation details, diluting these protocol instructions. Loading other skills injects contradictory behavioral overlays that override this protocol. Both cause you to skip workspace creation entirely.

## Execution flow:

1. Parse arguments: task description, `--mode`, `--verify`, `--skills`, `--from-plan`, `--quick`
2. Quick mode: if all params provided + `--quick`, skip wizard. Otherwise, ask user for missing params.
3. For detailed wizard steps (1A-1E) and template structures, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-start/wizard-reference.md` and `${CLAUDE_PLUGIN_ROOT}/skills/harness-start/templates-reference.md`.
4. Write the 4 workspace files. Run state-manager.py init. Verify all 7 gates.
5. Report ready state.

Now execute with the user's arguments: $ARGUMENTS
