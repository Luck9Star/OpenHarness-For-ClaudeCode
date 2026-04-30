---
description: "Initialize a new OpenHarness autonomous development task. With --quick, auto-chains into harness-dev after workspace init."
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2] [--template TEMPLATE_NAME] [--quick]"
allowed-tools: ["Bash", "Read", "Write", "Edit", "Grep", "Glob"]
---

You are running the OpenHarness workspace initialization protocol. Delegate to SKILL.md for full context firewall and behavioral isolation rules.

## Execution flow:

1. Parse arguments: task description, `--mode`, `--verify`, `--skills`, `--from-plan`, `--template`, `--quick`
2. Quick mode: if `--quick` is passed, infer all missing params from task description (no wizard), then auto-chain into harness-dev after workspace init. Without `--quick`, use LLM inference for params + brief confirmation with user.
3. For workspace file structures and generation rules, read `${CLAUDE_PLUGIN_ROOT}/skills/harness-start/templates-reference.md`.
4. Write the 4 workspace files. Run state-manager.py init. Verify all 7 gates.
5. If `--quick`: immediately begin harness-dev execution (read state, start loop). Otherwise: report ready and instruct user to run `/harness-dev`.

Now execute with the user's arguments: $ARGUMENTS
