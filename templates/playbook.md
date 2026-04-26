# Playbook | Execution Steps

> This file is the "operation manual" for the agent. Each step must be independently executable and verifiable.

## Execution Steps

### Step 1: [Step Name]

**Type**: `[implement|review|fix|verify|human-review]`
**What to do**:
```
[Specific operation description]
```

**Tools to use**:
- `[e.g., Read → read source files]`
- `[e.g., Bash → run tests]`

**Completion criteria** (existence + quality):
- `[e.g., Source file created at src/module.py]` (existence)
- `[e.g., File contains >= 3 public functions matching the design]` (quality)
- `[e.g., All new functions have docstrings]` (quality)

**Failure handling**:
- `[e.g., Syntax error → fix and retry, up to 3 times]`

---

### Step 2: [Step Name]

**Type**: `[implement|review|fix|verify|human-review]`
**What to do**:
```
[Specific operation description]
```

**Tools to use**:
- `[List of tools]`

**Completion criteria** (existence + quality):
- `[Verifiable existence condition]` (existence)
- `[Verifiable quality condition]` (quality)

**Failure handling**:
- `[Exception handling rules]`

---

## Dependencies

```
Step 1 → Step 2 → Step 3
              \ (on failure) → retry Step 2
```

## Completion Criteria Guidelines

> When writing completion criteria for each step, follow these rules:
> - Every step must have at least one **existence** criterion (does the output exist?)
> - Every step must have at least one **quality** criterion (is the output good enough?)
> - Review steps must have a **density** criterion (minimum findings per module/dimension)
> - Implementation steps should have a **coverage** criterion (tests exist and pass)
> - Avoid bare existence checks like "file exists" — add depth requirements

## Cycle Behavior (for review-fix loops)

> When the task requires iterating review→fix→verify until convergence, add this section.

- **Cycle steps**: `[start, end]` (e.g., `1,3` to cycle between review and verify)
- **Min cycles**: `[N]` (minimum cycles before convergence check kicks in — typically 2)
- **Done condition**: All numbered eval criteria pass AND convergence criterion passes AND cycle >= min_cycles
- **Max cycles**: `[N]` (prevent infinite loops — typically 5)
- **Convergence metric**: `[e.g., new P0 findings = 0 AND new P1 findings < previous cycle's P1 count]`

> **Critical**: The done condition MUST reference a **numbered convergence criterion** in eval-criteria.md (e.g., Standard N: Convergence). Without it, the loop exits as soon as all other criteria pass in cycle 1.
