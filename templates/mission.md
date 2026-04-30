# Mission Contract

> This document is the "constitution" of the harness workspace. It defines "what to do" and "what counts as done."
> Read this file first at the start of every loop iteration.

## 1. Mission Name

**Name**: `[task-name]`

## 2. Mission Objective

```
[One-sentence description of the task objective]
```

## 3. Done Definition

> Each item must be machine-verifiable — not subjective judgments.

| # | Completion Condition | Verification Method | Required |
|---|---|---|---|
| 1 | `[e.g., All tests pass]` | `[e.g., Run pytest, exit code 0]` | Yes |
| 2 | `[e.g., Feature works in browser]` | `[e.g., HTTP GET returns 200]` | Yes |
| 3 | `[e.g., No console errors]` | `[e.g., Check browser console log]` | No |

## 4. Boundaries

**Allowed Operations**:
- `[e.g., Read/write project source files]`
- `[e.g., Run tests and dev server]`

**Prohibited Operations**:
- `[e.g., Do not modify files outside the project directory]`
- `[e.g., Do not push to remote without user confirmation]`

**Exception Escalation**:
- Stop and notify user after 3 consecutive failures
- Skip and log if blocked by external dependency

## 5. Execution Parameters

| Parameter | Value |
|---|---|
| Verify Instruction | `[e.g., npm test]` |
| Execution Mode | `single` or `dual` |
| Max Iterations | `0` (infinite) or `N` |

## 6. Output Definition

| Output | Format | Location |
|---|---|---|
| `[e.g., Working application]` | `[source code]` | `./src/` |
