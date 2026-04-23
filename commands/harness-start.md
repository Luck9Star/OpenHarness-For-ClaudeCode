---
description: "Initialize a new OpenHarness autonomous development task"
argument-hint: "TASK_DESCRIPTION [--mode single|dual] [--verify INSTRUCTION] [--from-plan PATH] [--skills SKILL1,SKILL2]"
allowed-tools: ["Bash", "Read", "Write", "Edit"]
---

# /harness-start

Initialize a new OpenHarness autonomous development task workspace.

## Instructions

Parse the user's arguments from `$ARGUMENTS`:

- **Task description**: everything before any `--` flags (can supplement `--from-plan`, see below)
- **Mode**: `--mode single` (default) or `--mode dual`
- **Verify instruction**: `--verify "natural language instruction"` (optional) — an AI instruction for the eval-agent to interpret, e.g., `--verify "确保所有测试通过"` or `--verify "API endpoints return correct status codes"`
- **Skills**: `--skills "skill1,skill2"` (optional) — comma-separated list of skill names for the dev-agent to load during implementation
- **From plan**: `--from-plan <file-path>` (optional) — use a plan file as the task source

**Combination rules:**
- Description only → use description as the task
- `--from-plan` only → derive everything from the plan file
- **Both** → plan provides structure (steps, architecture), description provides supplementary context and clarification. Merge them: plan is the base, description adds scope clarification, priority hints, or constraints the plan doesn't cover.

If neither is provided, prompt the user:

```
What task would you like the harness to execute? Describe it in one sentence.
```

Then proceed with the init workflow.

## Workflow

1. **Parse arguments** from `$ARGUMENTS`:
   - Extract task description (text before any flags)
   - Extract `--mode` value (default: `single`)
   - Extract `--verify` value (default: empty)
   - Extract `--skills` value (comma-separated skill names, optional)
   - Extract `--from-plan` value (file path, optional)

2. **If `--from-plan` is provided**:
   - Read the specified plan file
   - Extract key information:
     - Title/summary → task name and mission objective
     - Implementation steps → playbook steps
     - Architecture/design → mission boundaries and output definition
     - Verification/validation criteria → eval-criteria.md content
   - **If a task description was also provided**, merge it with the plan:
     - Plan provides the structural foundation (steps, architecture, components)
     - Description supplements with scope clarification, priority hints, additional constraints
     - Incorporate description into mission.md objective and playbook context
   - If `--verify` is not also provided, derive a reasonable verify instruction from the plan
   - Continue to step 3

3. **Load the harness-init skill**: read `${CLAUDE_PLUGIN_ROOT}/skills/harness-init/SKILL.md`

4. **Follow the init workflow** from that skill file exactly:
   - If arguments provided all required info, skip the collection step and use what was given
   - Generate the task name from the description (or plan title)
   - Write mission.md, playbook.md, eval-criteria.md, progress.md — all fully filled, no placeholders
   - If using `--from-plan`, the playbook should mirror the plan's implementation sequence
   - Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py init <task-name> --mode <mode> --verify "<verify-instruction>" --skills "<skills>"`
   - Verify all files are created correctly

5. **After initialization**, report the ready state and suggest:

```
Harness workspace is ready. Start the development loop with /harness-dev
```

## Important Rules

- Never leave `[placeholder]` text in any generated file. All content must be concrete and task-specific.
- If the task description is ambiguous, make reasonable assumptions and fill in concrete details.
- The verify instruction is a natural language AI instruction (not a shell command). It tells the eval-agent what to check, in plain language.
- Always run state-manager.py as the last step — it creates the `.claude/` directory and state file.
- When using `--from-plan`, faithfully reflect the plan's structure. Do not invent steps not in the plan or omit steps that are.
- When both description and `--from-plan` are provided, the plan is the base. The description adds supplementary context — it should refine, not contradict.
