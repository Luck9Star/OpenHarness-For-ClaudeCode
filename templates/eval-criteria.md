# Eval Criteria | Validation Standards

> Validation must be externalized — the agent cannot self-certify completion.
> Each standard must be machine-checkable.

## Validation Principles

1. **Executor != Validator**: The agent executing the task must not also validate the result.
2. **Machine-checkable**: No subjective "looks good" judgments.
3. **Clear consequences**: Each failure has a defined action (retry, skip, escalate).

## Validation Standards

### Standard 1: [Name]

| Field | Value |
|---|---|
| Check | `[e.g., Output file exists]` |
| Method | `[e.g., Check path ./output/result.json exists and size > 0]` |
| Pass Condition | `[e.g., File exists with valid JSON]` |
| On Fail | `[e.g., Mark failed, retry next iteration]` |

### Standard 2: [Name]

| Field | Value |
|---|---|
| Check | `[e.g., Test suite passes]` |
| Method | `[e.g., Eval-agent interprets verify_instruction from state file]` |
| Pass Condition | `[e.g., Exit code 0, no failing tests]` |
| On Fail | `[e.g., Read error output, feed back to agent]` |

### Standard 3: [Name]

| Field | Value |
|---|---|
| Check | `[e.g., Service responds]` |
| Method | `[e.g., curl http://localhost:8000/health]` |
| Pass Condition | `[e.g., HTTP 200 with valid response]` |
| On Fail | `[e.g., Restart service, retry up to 3 times]` |

## Execution Rules

| Parameter | Value |
|---|---|
| Validation Timing | After each playbook step |
| Max Retries | `3` |
| On All Pass | Advance to next step |
| On Partial Pass | Record failures, prioritize in next iteration |
| On All Fail | Trip circuit breaker if consecutive failures >= 3 |
