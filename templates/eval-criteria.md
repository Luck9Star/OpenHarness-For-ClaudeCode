# Eval Criteria | Validation Standards

> Validation must be externalized — the agent cannot self-certify completion.
> Each standard must be machine-checkable.
> **Process compliance does not equal quality.** Existence checks alone are insufficient.

## Validation Principles

1. **Executor != Validator**: The agent executing the task must not also validate the result.
2. **Machine-checkable**: No subjective "looks good" judgments.
3. **Clear consequences**: Each failure has a defined action (retry, skip, escalate).
4. **Quality over existence**: Checks must verify depth and completeness, not just presence.
5. **Convergence with proof**: When metrics improve, the agent must prove WHY — not just report that they did.

## Validation Standards

### Standard 1: [Name — Deliverable Check]

| Field | Value |
|---|---|
| Check | `[e.g., Output file exists with expected structure]` |
| Method | `[e.g., Check path ./output/result.json exists, parse JSON, verify required keys present]` |
| Pass Condition | `[e.g., File exists with valid JSON containing all required keys, size > N bytes]` |
| On Fail | `[e.g., Mark failed, retry next iteration]` |

### Standard 2: [Name — Functional Correctness]

| Field | Value |
|---|---|
| Check | `[e.g., Test suite passes]` |
| Method | `[e.g., Eval-agent interprets verify_instruction from state file]` |
| Pass Condition | `[e.g., Exit code 0, no failing tests]` |
| On Fail | `[e.g., Read error output, feed back to agent]` |

### Standard 3: [Name — Integration / Service Check]

| Field | Value |
|---|---|
| Check | `[e.g., Service responds correctly]` |
| Method | `[e.g., curl http://localhost:8000/health]` |
| Pass Condition | `[e.g., HTTP 200 with valid response]` |
| On Fail | `[e.g., Restart service, retry up to 3 times]` |

## Review Task Standards (MANDATORY for review-type tasks)

> When the mission involves code review, architecture review, or security audit,
> the following additional standards are REQUIRED. Omit only for pure implementation tasks.

### Density Check

| Field | Value |
|---|---|
| Check | `Finding density meets minimum threshold` |
| Method | `Count findings per module/dimension in review report. Calculate LOC / finding ratio.` |
| Pass Condition | `Each module has >= [N] findings, OR review explicitly justifies sparsity with evidence (e.g., "this module is 200 LOC with 1 struct, no logic"). For code review: >= 1 finding / 500 LOC. For architecture review: >= 1 finding / module minimum, 3 recommended.` |
| On Fail | `Re-dispatch reviewer with instruction to go deeper on sparse modules` |

### Exhaustion Check

| Field | Value |
|---|---|
| Check | `Every "no issue" claim is backed by evidence` |
| Method | `Scan review report for patterns: "no issues", "looks fine", "appears correct". For each, verify supporting evidence is provided.` |
| Pass Condition | `Every dimension/module with 0 findings includes specific evidence of what was checked and why it is genuinely clean. No bare "no issue" statements.` |
| On Fail | `Re-dispatch reviewer to re-examine dimensions lacking evidence` |

### Convergence with Proof

| Field | Value |
|---|---|
| Check | `Finding reduction is genuine, not due to shallow review` |
| Method | `Compare finding counts across iterations. If total findings decreased > 50% from prior iteration, check for proof section.` |
| Pass Condition | `(a) No new P0 findings introduced. (b) New P1 findings <= P1 findings resolved. (c) If findings decreased > 50%, review includes an explicit section explaining: which areas were genuinely clean (with evidence), what was checked that found nothing (exhaustion log), acknowledgment of potential blind spots.` |
| On Fail | `Re-dispatch with instruction to verify whether reduction is genuine or due to insufficient depth` |

### Blind Spot Acknowledgment

| Field | Value |
|---|---|
| Check | `Review acknowledges its own blind spots` |
| Method | `Check review report for a "Blind Spots" or "Coverage Gaps" section` |
| Pass Condition | `Review includes a section listing: areas intentionally excluded (with reason), areas that should have deeper analysis next iteration, known gaps in this review round.` |
| On Fail | `Append blind spot analysis before proceeding` |

## Execution Rules

| Parameter | Value |
|---|---|
| Validation Timing | After each playbook step |
| Max Retries | `3` |
| On All Pass | Advance to next step |
| On Partial Pass | Record failures, prioritize in next iteration |
| On All Fail | Trip circuit breaker if consecutive failures >= 3 |
| On Suspected Shallow Pass | Re-dispatch eval-agent with "go deeper" instruction (does NOT count toward failure counter) |
