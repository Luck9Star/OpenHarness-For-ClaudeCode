---
name: harness-eval
description: External validation workflow for OpenHarness. Spawns harness-eval-agent for oracle-isolated verification. The agent cannot self-certify completion.
---

# Harness Eval | Validation Workflow

You are running the validation phase of an OpenHarness task. This is the gate that determines whether execution was successful. Follow these steps in order.

## Step 1: Spawn Oracle Evaluation Agent

Spawn `harness-eval-agent` as an independent evaluator. This agent:

- Cannot see your reasoning or planning
- Reads `.claude/harness/mission.md` done conditions and `.claude/harness/eval-criteria.md` independently
- Checks each condition against workspace artifacts
- Interprets verify_instruction (natural language AI instruction) independently
- Performs its own file-existence, command-exit-code, and semantic checks
- Produces its verdict in `.claude/harness/logs/eval_report.json`

Spawn the agent:

```
Use the Agent tool to spawn harness-eval-agent
```

The agent will write its verdict to `.claude/harness/logs/eval_report.json`.

## Step 2: Read Oracle Verdict

Read `.claude/harness/logs/eval_report.json` produced by the eval agent.

**If `overall: true`:**
- Validation has passed
- All mission conditions have been verified by an independent evaluator
- Report success to the user
- The executor may now output `<promise>LOOP_DONE</promise>` if all playbook steps are complete

**If `overall: false`:**
- Read the `checks` array to see which conditions failed
- Note the `evidence` field for each failure — this is what the independent evaluator observed
- Proceed to Step 3

## Step 3: Handle Failures

When validation fails:

1. **Collect failure details** from `.claude/harness/logs/eval_report.json`:
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

- **Never accept executor self-assessment as final.** The executor saying "I'm done" is not validation.
- **Never modify `.claude/harness/logs/eval_report.json` yourself.** Only harness-eval-agent writes to it.
- **Tripped circuit breaker overrides everything.** If the state file shows `circuit_breaker: tripped`, do not run evaluation. Report the blockage to the user instead.

## Quality Enforcement (Goodhart's Law Defense)

When evaluating, apply these checks in addition to the explicit standards:

### Density Verification
For review/audit tasks: verify that findings have adequate density. If a review report shows very few findings relative to the codebase size (e.g., < 1 finding per 500 LOC for code review), flag this as a potential shallow review — even if all explicit checks PASS. Report as:
```json
{"check": "finding_density", "passed": false, "evidence": "Only 2 findings for 10K LOC codebase (5000 LOC/finding). Threshold is 500 LOC/finding."}
```

### Exhaustion Evidence
For every dimension/module where the executor claims "no issues found" or "looks clean", verify that supporting evidence is provided. A bare "no issues" without explanation of what was checked is NOT acceptable.

### Shallow Pass Detection
If ALL checks pass but the evidence for each check is suspiciously thin (e.g., each check's evidence is under 20 words, no file:line references, no command output), flag the overall evaluation as `PASS_WITH_CONCERN` and include a note:
```json
{"overall": true, "confidence": "low", "concern": "All checks passed but evidence is thin. Recommend re-dispatching with deeper scope."}
```

### Convergence Proof
When comparing results across iterations (if historical data is available): if the number of findings dropped significantly (> 50%), verify that the executor provided an explanation for WHY — not just that it dropped. Absent an explanation, flag it.
