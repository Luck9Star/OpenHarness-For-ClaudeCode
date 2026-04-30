# Wizard Reference — Steps 1A through 1E

This file contains the detailed sub-steps for harness-start task analysis.
Read this when you need to perform task classification, deliverable definition, or skill inference.

**Context constraint**: Minimize file reading. Read ONLY what is needed to classify the task. Do NOT read source code to "understand the implementation" — that happens during `/harness-dev`. Limit yourself to: config files (`package.json`, `Cargo.toml`, etc.), directory listings, and test file names (not contents).

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

In `--quick` mode: silently expand and proceed.
In standard mode: present the expanded task description for user confirmation before proceeding.

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

In `--quick` mode: silently define deliverables and proceed.
In standard mode: present deliverables for user confirmation.

## Step 1C: Verify Instruction Inference (Automated)

Generate a `--verify` instruction from the deliverables and project context. No user interaction needed.

**Inference procedure:**

1. **Detect verification tools**: Check project for test runner config (package.json scripts, Makefile targets, pyproject.toml, pytest.ini, etc.)
2. **Map deliverables to checks**: For each deliverable from Step 1B, generate one machine-verifiable check
3. **Generate instruction**: Combine into a natural language instruction

The instruction must be:
- **Quantified**: use numbers, not "thorough" or "complete"
- **Machine-verifiable**: eval-agent can check each condition by running commands or reading files
- **Cover all deliverables**: one check per deliverable minimum

**User override**: If the user passed `--verify`, use their instruction instead. Do not re-derive.

## Step 1D: Skill Inference (Automated)

Infer applicable skills from the task description and available skill catalog. No user interaction needed.

**Inference procedure:**

1. **Scan available skills**:
   ```
   Glob: ${CLAUDE_PLUGIN_ROOT}/skills/*/SKILL.md
   ```

2. **For each skill**, read the YAML frontmatter `description` field only (do NOT read full SKILL.md content — that happens during harness-dev execution).

3. **Match against task**: Compare task description + deliverables + tech stack (from Step 1A) against each skill's description. A skill is relevant when:
   - Its description mentions technologies/patterns used in the task
   - Its domain overlaps with the task's scope
   - It provides verification or quality checks the task would benefit from

4. **Include/exclude**:
   - Include: skills with clear relevance (>= 2 keyword/concept matches)
   - Exclude: skills with no overlap
   - Borderline: include — skills are lightweight and harmless to load

5. **Store result**: Write the selected skill names as a comma-separated list for the state file's `--skills` field.

**Example inference:**
- Task: "Add JWT authentication to Express API"
- Available skills: harness-core, harness-dev, harness-start, harness-eval, harness-status, harness-dream, harness-edit
- Inference: No domain-specific skills match. Store empty list.
- If a skill `api-security` existed with description "REST API security patterns, JWT, OAuth": it would be included.

**User override**: If the user passed `--skills`, use their list instead of inference. Validate against available skills and warn about invalid names.

## Step 1E: Loop Mode Inference (Automated)

Infer loop mode from task complexity. No user interaction needed.

| Task Structure | Inferred loop_mode | Reasoning |
|---|---|---|
| <= 3 steps | `in-session` | Short missions, context accumulation is harmless |
| 4-6 steps | `in-session` | Medium missions, still manageable |
| 7+ steps or review cycles | `clean` | Long missions, stale context risk is real |

Store the answer as `loop_mode`: "in-session" for continuous, "clean" for auto-compressed.
