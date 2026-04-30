---
description: "Run the OpenHarness autonomous development loop — plan, code, evaluate, iterate"
argument-hint: "[--mode single|dual] [--max-iterations N] [--max-concurrency N] [--resume]"
allowed-tools: ["Bash", "Agent", "Read", "Write", "Edit", "Grep", "Glob"]
---

You are running the OpenHarness autonomous development loop. Delegate to the SKILL file for full protocol.

## Execution flow:

1. Parse args: `--mode single|dual` (inferred if absent), `--max-iterations N`, `--max-concurrency N` (inferred if absent), `--resume`
2. If not `--resume`, run setup-harness-loop.sh to init loop state
3. Read mission, eval-criteria, playbook, state file in order
4. Begin loop: for each step, check type and execute. For detailed step type instructions, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-dev/loop-reference.md`.
5. After each step: spawn eval-agent → check PASS/FAIL → update state → advance step
6. When all steps done + all criteria verified: output `<promise>LOOP_DONE</promise>`

Now execute with the user's arguments: $ARGUMENTS
