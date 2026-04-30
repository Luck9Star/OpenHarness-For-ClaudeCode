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

These checks are MANDATORY — not advisory. The eval-agent MUST enforce every one of them. Apply these in addition to the explicit standards.

### Density Verification (MANDATORY)
For review/audit tasks: verify that findings have adequate density. If a review report shows very few findings relative to the codebase size (e.g., < 1 finding per 500 LOC for code review), flag this as a potential shallow review — even if all explicit checks PASS. Report as:
```json
{"check": "finding_density", "passed": false, "evidence": "Only 2 findings for 10K LOC codebase (5000 LOC/finding). Threshold is 500 LOC/finding."}
```

**Density floors** (per eval-criteria.md — the authority):
| Report type | Minimum density |
|---|---|
| Code review | >= 1 finding / 500 LOC |
| Architecture review | >= 1 finding / module minimum, 3 recommended |
| Security-focused review | <= 500 LOC/finding |

If a report's density exceeds the threshold, FAIL the check. The only exception is if the `blind_spots` field contains exhaustive evidence of what was checked.

### Exhaustion Evidence (MANDATORY)
For every dimension/module where the executor claims "no issues found" or "looks clean", verify that supporting evidence is provided. A bare "no issues" without explanation of what was checked is NOT acceptable. Each "clean" claim MUST include:
- What functions/paths were examined
- What specific checks were performed
- What edge cases were considered

### Shallow Pass Detection (MANDATORY)
If ALL checks pass but the evidence for each check is suspiciously thin (e.g., each check's evidence is under 20 words, no file:line references, no command output), flag the overall evaluation as `PASS_WITH_CONCERN` and include a note:
```json
{"overall": true, "confidence": "low", "concern": "All checks passed but evidence is thin. Recommend re-dispatching with deeper scope."}
```

### Convergence Proof (MANDATORY for multi-iteration missions)
When comparing results across iterations (if historical data is available):

1. **>50% drop requires explanation**: If findings dropped > 50% between adjacent iterations, the review MUST explain WHY (e.g., "5 bugs fixed, 3 new test patterns prevent regressions"). A bare "fewer findings" is NOT sufficient.

2. **New-code coverage check**: Each iteration's review MUST cover ALL new code written in previous iterations. If iteration 2's review scope excludes code written in iteration 1, FAIL the convergence check — the review is incomplete, not the code better.

3. **Convergence directionality**: Convergence is only valid when:
   - The REVIEW SCOPE stays the same or grows (reviewing MORE code, not less)
   - The REVIEW DENSITY stays above floor (findings per LOC reviewed stays above minimum)
   - NEW issues found are <= previous iteration's severity (no new criticals in later iterations)
   A "convergence" achieved by narrowing scope or reducing review depth is FALSE convergence.

### False Convergence Detection (MANDATORY)
If the eval-agent observes ANY of these patterns, it MUST flag the convergence claim as FALSE:

| Pattern | Detection | Verdict |
|---|---|---|
| Scope narrowing | iter1 reviewed 50 files, iter2 reviewed 10 files | FAIL convergence |
| Density collapse | iter1: 500 LOC/finding, iter2: 5000 LOC/finding | FAIL convergence |
| Fix-code skip | iter2 report has no re-audit of iter1 fixes | FAIL convergence |
| Test-only "convergence" | convergence claimed via test pass rate, no review evidence | FAIL convergence |
| Metric gaming | findings decrease but LOC reviewed also decreased proportionally | FAIL convergence |

### Cross-Module Contract Verification (MANDATORY)

The eval-agent MUST verify data flow integrity across module boundaries. For each pair of modules where one produces output consumed by another:

1. Identify the interface: upstream module's output schema vs downstream module's input expectations
2. Run the upstream module to produce real output (or read real output from artifacts)
3. Feed that output to the downstream module
4. Assert: ALL fields the downstream reads are present and non-empty in the upstream output
5. If using manually constructed test fixtures: ALSO require at least one test that uses real upstream output

If cross-module boundaries exist in the mission but no integration test covers them, FAIL the check:

```json
{"check": "cross_module_integration", "passed": false, "evidence": "Module B (profile_loader) reads 'body' and 'vibe' from Module A (importer) output, but importer output does not contain these fields. No integration test found."}
```

### Test Fixture Quality Gate (MANDATORY)

When evaluating test suites, the eval-agent MUST check:

1. **Real data ratio**: For each test file, count tests using manually constructed data vs tests using real upstream output. If ratio of real-data tests / total tests < 0.3 for ANY module that has an upstream dependency, FAIL this check.
2. **Cross-module coverage**: If the mission spans multiple phases/modules, at least one test MUST exercise the full pipeline end-to-end using real module outputs.
3. **Golden path bias**: If ALL tests only test happy paths (no error cases, no missing fields, no empty inputs), flag as `PASS_WITH_CONCERN`.
