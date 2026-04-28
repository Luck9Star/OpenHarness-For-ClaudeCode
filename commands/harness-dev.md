---
description: "Run the OpenHarness autonomous development loop — plan, code, evaluate, iterate"
argument-hint: "[--mode single|dual] [--max-iterations N] [--resume]"
allowed-tools: ["Bash", "Task", "Read", "Write", "Edit"]
---

You are running the OpenHarness autonomous development loop. This is a loop execution protocol — you MUST follow every step below.

## PRE-FLIGHT CHECKS — ALL must pass before doing any work:

1. `.claude/harness-state.json` MUST exist — if not, tell user to run `/harness-start` first
2. `.claude/harness/mission.md` MUST exist
3. `.claude/harness/playbook.md` MUST exist
4. `.claude/harness/eval-criteria.md` MUST exist

If ANY check fails, STOP and tell the user to run `/harness-start` first. Do NOT start implementing.

## HARD RULES (violating any = protocol failure):

- **NO other skills**: Do NOT invoke Skill tool for pua, superpowers, orch, or any other skill during this loop. If `skills` are set in state, load them with Skill tool at the START of each step, then follow the step.
- **MUST use state-manager.py** for all state transitions. Manual status updates are forbidden.
- **MUST spawn harness-eval-agent** for validation. Running tests yourself is NOT validation.
- **MUST NOT output `<promise>LOOP_DONE</promise>`** unless ALL eval criteria pass AND all playbook steps complete AND pre-completion integration gate passes.
- **ONE step per iteration**. Do not execute multiple steps in one turn.

## Execution flow:

1. Parse args: `--mode single|dual`, `--max-iterations N`, `--resume`
2. If not `--resume`, run setup-harness-loop.sh to init loop state
3. Read mission, eval-criteria, playbook, state file in order
4. Begin loop: for each step, check type and execute. For detailed step type instructions, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-dev/loop-reference.md`.
5. After each step: spawn eval-agent → check PASS/FAIL → update state → advance step
6. When all steps done + all criteria verified: output `<promise>LOOP_DONE</promise>`

Now execute with the user's arguments: $ARGUMENTS
