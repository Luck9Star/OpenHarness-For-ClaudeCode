---
name: harness-eval
description: External validation workflow for OpenHarness. Runs eval-check.py then spawns harness-eval-agent for oracle isolation. The agent cannot self-certify completion.
---

# Harness Eval | Validation Workflow

You are running the validation phase of an OpenHarness task. This is the gate that determines whether execution was successful. Follow these steps in order.

## Step 1: Run Objective Checks

Execute the external validation script:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/eval-check.py
```

This reads `eval-criteria.md` and the state file, checks each standard, and logs any `verify_instruction` for the eval-agent to interpret. It writes results to `logs/eval_report.json`.

Read the output. If the script exits with code 0, all objective checks passed. If it exits with code 1, some checks failed.

## Step 2: Evaluate Objective Check Results

**If any objective checks failed:**

- Read `logs/eval_report.json` to see which checks failed and why
- Record the failure details
- Skip to Step 5 — feed failures back to the execution loop
- Do NOT proceed to oracle evaluation if objective checks fail

**If all objective checks passed:**

- Proceed to Step 3 for oracle-isolated subjective evaluation

## Step 3: Spawn Oracle Evaluation Agent

Spawn `harness-eval-agent` as an independent evaluator. This agent:

- Cannot see your reasoning or planning
- Reads mission.md done conditions and eval-criteria.md independently
- Checks each condition against workspace artifacts
- Interprets verify_instruction (natural language AI instruction) independently
- Produces its own verdict in `logs/eval_report.json`

Spawn the agent:

```
Use the Agent tool to spawn harness-eval-agent
```

The agent will overwrite `logs/eval_report.json` with its own verdict.

## Step 4: Read Oracle Verdict

Read `logs/eval_report.json` produced by the eval agent.

**If `overall: true`:**
- Validation has passed
- All mission conditions have been verified by an independent evaluator
- Report success to the user
- The executor may now output `<promise>LOOP_DONE</promise>` if all playbook steps are complete

**If `overall: false`:**
- Read the `checks` array to see which conditions failed
- Note the `evidence` field for each failure — this is what the independent evaluator observed
- Proceed to Step 5

## Step 5: Handle Failures

When validation fails (either objective or subjective):

1. **Collect failure details** from `logs/eval_report.json`:
   - Which checks failed
   - What evidence was observed
   - What the expected condition was

2. **Do NOT accept the executor's own assessment.** The whole point of oracle isolation is that the executor cannot self-certify. If the executor claims success but the eval agent says failure, the eval agent's verdict takes precedence.

3. **Feed failures back** into the execution loop:
   - Update the state file with failure status: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py fail`
   - Log the failure: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py log "Validation failed: <details>"`
   - The next loop iteration should prioritize the failed conditions

4. **Report the failure** to the user with specific details:
   ```
   Validation FAILED. The following conditions were not met:
   - [Condition name]: [evidence from eval agent]
   
   These will be prioritized in the next execution iteration.
   ```

## Critical Rules

- **Never skip oracle evaluation.** Even if objective checks pass, the eval agent must independently verify.
- **Never accept executor self-assessment as final.** The executor saying "I'm done" is not validation.
- **Never modify eval_report.json yourself.** Only eval-check.py and harness-eval-agent write to it.
- **Tripped circuit breaker overrides everything.** If the state file shows `circuit_breaker: tripped`, do not run evaluation. Report the blockage to the user instead.
