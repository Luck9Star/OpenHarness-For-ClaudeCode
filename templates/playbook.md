# Playbook | Execution Steps

> This file is the "operation manual" for the agent. Each step must be independently executable and verifiable.

## Execution Steps

### Step 1: [Step Name]

**Type**: `[implement|review|fix|verify]`
**What to do**:
```
[Specific operation description]
```

**Tools to use**:
- `[e.g., Read → read source files]`
- `[e.g., Bash → run tests]`

**Completion criteria**:
- `[e.g., Source file created at src/module.py]`

**Failure handling**:
- `[e.g., Syntax error → fix and retry, up to 3 times]`

---

### Step 2: [Step Name]

**Type**: `[implement|review|fix|verify]`
**What to do**:
```
[Specific operation description]
```

**Tools to use**:
- `[List of tools]`

**Completion criteria**:
- `[Verifiable condition]`

**Failure handling**:
- `[Exception handling rules]`

---

## Dependencies

```
Step 1 → Step 2 → Step 3
              \ (on failure) → retry Step 2
```

## Reusable Knowledge

### API Endpoints
```
[URLs, selectors, keys needed during execution]
```

### Data Format
```
[Input/output format specifications]
```
