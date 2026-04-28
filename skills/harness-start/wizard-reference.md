# Wizard Reference — Steps 1A through 1E

This file contains the detailed wizard sub-steps for harness-start.
Read this file when in wizard mode (missing critical parameters).

Each step requires user confirmation before proceeding to the next.

**Context constraint**: Even in wizard mode, minimize file reading. Read ONLY what is needed to classify the task and ask the user good questions. Do NOT read source code to "understand the implementation" — that happens during `/harness-dev`. Limit yourself to: config files (`package.json`, `Cargo.toml`, etc.), directory listings, and test file names (not contents).

---

## Step 1A: Task Analysis & Conditional Codebase Scan

Before touching any files, **classify the task** to determine how much codebase context is needed.

**Task classification** — analyze the user's description and pick one:

| Category | Signals | Codebase read needed? |
|---|---|---|
| **Targeted change** | User names specific files, functions, or modules (e.g., "fix auth.ts login bug") | **Light**: Read only the named files/modules |
| **Feature/addition** | User describes new functionality without naming files (e.g., "add JWT auth middleware") | **Medium**: Detect tech stack + scan relevant module structure |
| **Cross-cutting refactor** | User describes system-wide change (e.g., "migrate Python to Rust", "improve error handling across all crates") | **Full**: Full tech stack + project structure + test patterns |
| **Non-code task** | Documentation, config, planning (e.g., "write API docs", "update CI config") | **None**: Skip codebase read entirely |
| **Ambiguous** | Can't tell from description alone | **Ask the user** (see below) |

**If classification is ambiguous**, ask the user a single clarifying question:

```
To scope this task correctly, do I need to read the codebase first?
- "Yes, full scan" — I'll analyze the project structure before planning
- "Yes, but only [module/directory]" — I'll read only the specified area
- "No, just plan from my description" — I'll work from your description alone
```

Then, based on the classification, perform the appropriate level of analysis:

**Full scan** (cross-cutting refactor):
1. **Detect tech stack**: Use Glob to find key config files (`package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, etc.)
2. **Scan project structure**: List top-level directories and key entry points
3. **Check existing tests**: Find test directories/files to understand test patterns

**Medium scan** (feature/addition):
1. **Detect tech stack** (same as above)
2. **Scan only the relevant module/directory** that the feature likely touches

**Light scan** (targeted change):
1. **Read only the specific files** the user named — no project-wide scanning

**None** (non-code task):
- Skip all codebase reading. Proceed directly with the task description.

After any level of scan, expand the user's task description with the gathered context:

- Add concrete scope boundaries based on the codebase structure (if scanned)
- Identify which files/modules are likely involved
- Clarify ambiguous terms using project context
- Add implementation constraints (follow existing patterns, match conventions)

Present the expanded task description to the user:

```
Based on [project analysis / file review / your description], here's the expanded task:

[Expanded description with concrete scope, affected modules, and constraints]

Affected areas:
- [module/file 1]: [what changes here]
- [module/file 2]: [what changes here]

Does this look correct? Any adjustments?
```

Wait for user confirmation. Incorporate any feedback before proceeding.

## Step 1B: Define Deliverables

From the expanded task description, enumerate concrete deliverables:

```
Based on the task scope, the deliverables will be:

1. [Deliverable 1 — e.g., "src/auth/middleware.ts: JWT authentication middleware"]
2. [Deliverable 2 — e.g., "tests/auth/middleware.test.ts: Unit tests covering token validation"]
3. [Deliverable 3 — e.g., "Updated route handlers to use middleware"]

Is this the right scope? Anything to add or remove?
```

Each deliverable must be:
- A concrete file or file section (not a vague "improve X")
- Tied to a specific module/area from Step 1A
- Independently verifiable

Wait for user confirmation.

## Step 1C: Derive Verify Instruction

Generate a `--verify` instruction from the deliverables. The instruction must be:
- **Quantified**: use numbers, not "thorough" or "complete"
- **Machine-verifiable**: eval-agent can check each condition by running commands or reading files
- **Cover all deliverables**: one check per deliverable minimum

```
Based on the deliverables, here's the proposed verify instruction:

--verify "
1. [Check for deliverable 1 — e.g., "auth middleware file exists and exports correct functions"]
2. [Check for deliverable 2 — e.g., "all unit tests pass (npm test)"]
3. [Check for deliverable 3 — e.g., "protected routes return 401 without valid token"]
"

Each check maps directly to a deliverable. Want to adjust any checks?
```

If the user already provided `--verify`, present the derived version alongside and ask which they prefer.

Wait for user confirmation. Use the final confirmed verify instruction.

## Step 1D: Recommend Skills

Based on the tech stack detected in Step 1A and the deliverables, recommend skills:

```
Based on the tech stack and task type, these skills may help:

Recommended:
- [skill-name]: [reason — e.g., "project uses React, skill provides component patterns"]

Optional:
- [skill-name]: [reason — e.g., "task involves API design, skill provides REST patterns"]

Skip:
- [skill-name]: [reason — e.g., "no database changes needed"]

Use recommended skills? Or adjust the list?
```

If the user already specified `--skills`, validate them against the tech stack and note any gaps.

Wait for user confirmation. Use the final confirmed skill list.

## Step 1E: Loop Mode Selection

Ask the user how each iteration should handle context:

```
How should each loop iteration handle conversation context?

- "continuous" (default) — Same session throughout. Faster iteration, context accumulates. Agent is instructed to ignore stale context. Good for short missions or tasks where context carry-over is helpful.
- "clean" — Same session, but auto-compress context between iterations (via /compact). Prevents stale context from misleading the agent at the cost of one extra step per iteration. Good for long missions with many steps.

Which mode?
```

**Guidelines:**
- If the task has <= 3 steps, default to "continuous" and skip this question — inform the user.
- If the task has 4+ steps OR involves review/audit cycles, ask this question explicitly.
- Store the answer as `loop_mode`: "in-session" for continuous, "clean" for auto-compressed.

Wait for user confirmation.
