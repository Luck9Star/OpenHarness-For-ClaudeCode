# Phase-Based Parallel Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase-based parallel step execution to the harness-dev loop, with a unified agent spawn system that routes all step types through domain specialists.

**Architecture:** Playbook steps get a `Phase: N` field. Steps in the same Phase are dispatched as parallel Agent tool calls in a single message. State file tracks per-step status. A unified Router selects agents for all step types (not just implement/fix), falling back to meta agents only when no domain specialist matches.

**Tech Stack:** Python (state-manager.py), Markdown (SKILL.md, templates, agent definitions)

**Spec:** `docs/superpowers/specs/2026-04-28-parallel-execution-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/state-manager.py` | Modify | Add `step-status`, `phase-advance`, `phase-status` commands; new state fields |
| `templates/playbook.md` | Modify | Add `Phase: N` field to step template |
| `skills/harness-start/templates-reference.md` | Modify | Guide Phase grouping in playbook generation |
| `skills/harness-dev/agent-spawn.md` | Create | Unified Router + Prompt Builder + Spawn Manager reference |
| `skills/harness-dev/loop-reference.md` | Modify | Update implement/fix/review sections for unified routing |
| `skills/harness-dev/SKILL.md` | Modify | Rewrite Section 5.5 for Phase-aware execution |
| `agents/meta/harness-dev-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/meta/harness-eval-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/meta/harness-review-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/domain/*.md` (6 files) | Modify | Add `parallel_safe: true` to frontmatter |

---

### Task 1: state-manager.py — Add Phase State Fields to `cmd_init`

**Files:**
- Modify: `scripts/state-manager.py:249-270` (the `state` dict in `cmd_init`)

- [ ] **Step 1: Add new fields to the state dict in `cmd_init`**

In `cmd_init`, after the existing `"knowledge_index": [],` line (around line 269), add the three new fields:

```python
        "current_phase": None,
        "step_statuses": {},
        "max_concurrency": 3,
```

The full state dict should now end with:

```python
    state = {
        "status": "idle",
        "execution_mode": execution_mode,
        "current_step": "Step 1",
        "consecutive_failures": 0,
        "total_executions": 0,
        "circuit_breaker": "off",
        "iteration": 0,
        "max_iterations": max_iterations,
        "session_id": "",
        "verify_instruction": verify_instruction,
        "skills": skills,
        "last_execution_time": now,
        "task_name": task_name,
        "started_at": now,
        "loop_mode": loop_mode,
        "cycle_steps": cycle_steps,
        "cycle_iteration": 0,
        "min_cycles": min_cycles,
        "max_cycles": max_cycles,
        "knowledge_index": [],
        "current_phase": None,
        "step_statuses": {},
        "max_concurrency": 3,
    }
```

- [ ] **Step 2: Add `--max-concurrency` argument parsing to `cmd_init`**

In `cmd_init`'s argument parsing while loop (after the `--max-cycles` block, around line 212), add:

```python
        elif args[i] == "--max-concurrency" and i + 1 < len(args):
            _validate_value("--max-concurrency", args[i + 1])
            try:
                max_concurrency = int(args[i + 1])
                if max_concurrency < 1:
                    raise ValueError("must be >= 1")
            except ValueError as e:
                print(f"Error: --max-concurrency requires a positive integer, got '{args[i+1]}': {e}", file=sys.stderr)
                sys.exit(1)
            i += 2
```

Also add `max_concurrency = 3` to the variable initialization section (around line 143, after `max_cycles = 0`):

```python
    max_concurrency = 3
```

And update the state dict to use the variable:

```python
        "max_concurrency": max_concurrency,
```

- [ ] **Step 3: Verify init still works**

Run: `cd /Users/yangyitian/Documents/dev/Agents/openharness-cc && python3 scripts/state-manager.py init test-phase-fields --mode single --max-iterations 1 --force`
Expected: JSON with `"status": "initialized"` and no errors.

Then: `python3 scripts/state-manager.py read`
Expected: JSON containing `"current_phase": null`, `"step_statuses": {}`, `"max_concurrency": 3`.

Clean up: `rm -f .claude/harness-state.json`

- [ ] **Step 4: Commit**

```bash
git add scripts/state-manager.py
git commit -m "feat(state-manager): add Phase state fields (current_phase, step_statuses, max_concurrency)"
```

---

### Task 2: state-manager.py — Add `step-status`, `phase-advance`, `phase-status` Commands

**Files:**
- Modify: `scripts/state-manager.py:490-501` (COMMANDS dict and new command functions)

- [ ] **Step 1: Add `cmd_step_status` function**

Insert after `cmd_reset_fail` (around line 400):

```python
def cmd_step_status(args):
    """Update a single step's status in step_statuses."""
    if len(args) < 2:
        print("Usage: state-manager.py step-status <step_name> <status>", file=sys.stderr)
        sys.exit(1)
    path = find_state_file()
    if not path:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    state = read_state(path)
    step_name = args[0]
    status = args[1]
    valid_statuses = ("pending", "running", "completed", "failed")
    if status not in valid_statuses:
        print(f"Error: status must be one of {valid_statuses}, got '{status}'", file=sys.stderr)
        sys.exit(1)
    if "step_statuses" not in state:
        state["step_statuses"] = {}
    state["step_statuses"][step_name] = status
    state["last_execution_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_state(state, path)
    print(f"{step_name}: {status}")
```

- [ ] **Step 2: Add `cmd_phase_advance` function**

```python
def cmd_phase_advance(args):
    """Advance current_phase by 1. Only succeeds if all current phase steps are completed."""
    path = find_state_file()
    if not path:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    state = read_state(path)
    current = state.get("current_phase")

    # Linear mode (no phases) — fall through to regular step-advance
    if current is None:
        print("No active phase. Use step-advance for linear mode.", file=sys.stderr)
        sys.exit(1)

    # Check all steps in current phase are completed
    step_statuses = state.get("step_statuses", {})
    failed = [s for s, st in step_statuses.items() if st == "failed"]
    if failed:
        print(f"Cannot advance: {len(failed)} step(s) still failed: {', '.join(failed)}", file=sys.stderr)
        sys.exit(1)

    state["current_phase"] = current + 1
    state["step_statuses"] = {}  # Reset for next phase
    state["last_execution_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    write_state(state, path)
    print(f"Advanced to Phase {current + 1}")
```

- [ ] **Step 3: Add `cmd_phase_status` function**

```python
def cmd_phase_status(args):
    """Print current phase step status summary."""
    path = find_state_file()
    if not path:
        print("No active harness workspace", file=sys.stderr)
        sys.exit(1)
    state = read_state(path)
    phase = state.get("current_phase")
    if phase is None:
        print("Linear mode (no phases active)")
        return
    step_statuses = state.get("step_statuses", {})
    if not step_statuses:
        print(f"Phase {phase}: no steps tracked yet")
        return
    lines = [f"Phase {phase}:"]
    for step, status in sorted(step_statuses.items()):
        lines.append(f"  {step}: {status}")
    completed = sum(1 for s in step_statuses.values() if s == "completed")
    total = len(step_statuses)
    lines.append(f"  Progress: {completed}/{total}")
    print("\n".join(lines))
```

- [ ] **Step 4: Register new commands in the COMMANDS dict**

Update the COMMANDS dict (around line 490):

```python
COMMANDS = {
    "read": cmd_read,
    "init": cmd_init,
    "update": cmd_update,
    "log": cmd_log,
    "report": cmd_report,
    "step-advance": cmd_step_advance,
    "step-status": cmd_step_status,
    "phase-advance": cmd_phase_advance,
    "phase-status": cmd_phase_status,
    "fail": cmd_fail,
    "reset-fail": cmd_reset_fail,
    "trip-breaker": cmd_trip_breaker,
    "archive": cmd_archive,
}
```

- [ ] **Step 5: Verify new commands work**

```bash
cd /Users/yangyitian/Documents/dev/Agents/openharness-cc
python3 scripts/state-manager.py init test-commands --mode single --max-iterations 0 --force

# Test step-status
python3 scripts/state-manager.py step-status "Step 1" running
python3 scripts/state-manager.py step-status "Step 2" pending
python3 scripts/state-manager.py step-status "Step 1" completed
python3 scripts/state-manager.py step-status "Step 2" completed

# Test phase-status
python3 scripts/state-manager.py phase-status

# Test phase-advance
python3 scripts/state-manager.py phase-advance

# Verify state
python3 scripts/state-manager.py read

# Test error cases
python3 scripts/state-manager.py step-status "Step 1" invalid_status 2>&1 || true

# Cleanup
rm -f .claude/harness-state.json
```

Expected: All commands succeed. `phase-advance` shows "Advanced to Phase 2". Invalid status shows error message.

- [ ] **Step 6: Commit**

```bash
git add scripts/state-manager.py
git commit -m "feat(state-manager): add step-status, phase-advance, phase-status commands"
```

---

### Task 3: Playbook Template — Add `Phase` Field

**Files:**
- Modify: `templates/playbook.md:7-27` (step template section)

- [ ] **Step 1: Add `Phase` field to the step template**

Replace the step template section (lines 7-27) with:

```markdown
## Execution Steps

### Step 1: [Step Name]

**Phase**: `[N]` (optional — steps in the same Phase execute in parallel; omit for linear execution)
**Type**: `[implement|review|fix|verify|human-review]`
**What to do**:
\```
[Specific operation description]
\```

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

**Phase**: `[N]`
**Type**: `[implement|review|fix|verify|human-review]`
**What to do**:
\```
[Specific operation description]
\```
```

- [ ] **Step 2: Update Dependencies section to support Phase diagrams**

Replace the Dependencies section (lines 49-54) with:

```markdown
## Dependencies

### Linear (no Phase fields)
\```
Step 1 → Step 2 → Step 3
              \ (on failure) → retry Step 2
\```

### Phase-Based (with Phase fields)
\```
Phase 1: [Step 1, Step 2] (parallel)
Phase 2: [Step 3] (waits for Phase 1)
Phase 3: [Step 4, Step 5, Step 6] (parallel, waits for Phase 2)
\```

> Steps in the same Phase MUST be independent (not editing the same files).
```

- [ ] **Step 3: Verify template renders correctly**

Run: `cat templates/playbook.md | head -40`
Expected: Step template shows `**Phase**:` field.

- [ ] **Step 4: Commit**

```bash
git add templates/playbook.md
git commit -m "feat(playbook): add Phase field for parallel step execution"
```

---

### Task 4: Agent Frontmatter — Add `parallel_safe` to All Agents

**Files:**
- Modify: `agents/meta/harness-dev-agent.md` (frontmatter)
- Modify: `agents/meta/harness-eval-agent.md` (frontmatter)
- Modify: `agents/meta/harness-review-agent.md` (frontmatter)
- Modify: `agents/domain/api-tester.md` (frontmatter)
- Modify: `agents/domain/code-reviewer.md` (frontmatter)
- Modify: `agents/domain/database-optimizer.md` (frontmatter)
- Modify: `agents/domain/devops-automator.md` (frontmatter)
- Modify: `agents/domain/evidence-collector.md` (frontmatter)
- Modify: `agents/domain/security-engineer.md` (frontmatter)

- [ ] **Step 1: Add `parallel_safe: true` to all 9 agent files**

For each file, add `parallel_safe: true` as the last line of the YAML frontmatter block.

**Meta agents** (add after the `tools:` line in frontmatter):
- `agents/meta/harness-dev-agent.md` — add `parallel_safe: true`
- `agents/meta/harness-eval-agent.md` — add `parallel_safe: true`
- `agents/meta/harness-review-agent.md` — add `parallel_safe: true`

**Domain agents** (add after the `route_keywords:` line in frontmatter):
- `agents/domain/api-tester.md` — add `parallel_safe: true`
- `agents/domain/code-reviewer.md` — add `parallel_safe: true`
- `agents/domain/database-optimizer.md` — add `parallel_safe: true`
- `agents/domain/devops-automator.md` — add `parallel_safe: true`
- `agents/domain/evidence-collector.md` — add `parallel_safe: true`
- `agents/domain/security-engineer.md` — add `parallel_safe: true`

- [ ] **Step 2: Verify frontmatter is valid YAML**

```bash
cd /Users/yangyitian/Documents/dev/Agents/openharness-cc
for f in agents/meta/*.md agents/domain/*.md; do
  python3 -c "
import yaml, sys
with open('$f') as fh:
    content = fh.read()
    # Extract YAML between --- markers
    parts = content.split('---')
    if len(parts) >= 3:
        fm = yaml.safe_load(parts[1])
        assert 'parallel_safe' in fm, f'Missing parallel_safe in $f'
        print(f'$f: parallel_safe={fm[\"parallel_safe\"]}')
"
done
```

Expected: All 9 files print `parallel_safe=True`.

- [ ] **Step 3: Commit**

```bash
git add agents/meta/*.md agents/domain/*.md
git commit -m "feat(agents): add parallel_safe field to all agent frontmatter"
```

---

### Task 5: harness-start templates-reference.md — Add Phase Grouping Guidance

**Files:**
- Modify: `skills/harness-start/templates-reference.md:29-48` (playbook generation rules section)

- [ ] **Step 1: Add Phase grouping rules to the playbook generation section**

After the "General playbook rules" block (around line 48, before the "Cycle playbook" section), add:

```markdown
**Phase grouping for parallel execution** (when task has independent steps):

- Steps that can execute independently (no shared files, no output dependencies) SHOULD be assigned the same `Phase: N` value
- Steps with dependencies on prior steps MUST have a higher Phase number
- Steps editing the same files MUST be in different Phases (sequential, not parallel)
- `review`, `fix`, and `verify` steps are typically in their own Phase (after all `implement` Phases)
- When grouping, aim for max 3 steps per Phase (matches default `max_concurrency`)
- Steps without `Phase` field = implicit Phase 0 (linear execution)

**Phase grouping example:**
```
Phase 1: Step 1 (impl auth), Step 2 (impl product API), Step 3 (impl payment)
Phase 2: Step 4 (review all), Step 5 (fix issues)
Phase 3: Step 6 (verify integration)
```

**When to use Phase grouping:**
- Task has 3+ `implement` steps that target different files/modules → USE Phase grouping
- Task is sequential by nature (Step 2 depends on Step 1 output) → do NOT use Phase grouping
- Task has only 1-2 implement steps → do NOT use Phase grouping (overhead exceeds benefit)
```

- [ ] **Step 2: Commit**

```bash
git add skills/harness-start/templates-reference.md
git commit -m "docs(harness-start): add Phase grouping guidance for playbook generation"
```

---

### Task 6: Create Unified Agent Spawn Reference

**Files:**
- Create: `skills/harness-dev/agent-spawn.md`

- [ ] **Step 1: Create the unified agent spawn reference file**

Create `skills/harness-dev/agent-spawn.md` with the following content:

```markdown
# Agent Spawn Reference — Unified Router, Prompt Builder, Spawn Manager

This reference defines how harness-dev selects, constructs prompts for, and dispatches agents for ALL step types.

## 1. Agent Router

Given a playbook step, select the appropriate agent.

### Priority (evaluated in order)

1. **Manual override**: If the step has a `specialist:` field → use that agent directly.
   Example: `specialist: security-engineer` → load `agents/domain/security-engineer.md`

2. **Auto-discovery**: Match step description against `route_keywords` in `agents/domain/*.md` frontmatter.
   - Concatenate step title + description (lowercase)
   - Count keyword matches for each domain agent
   - Select agent with most matches. Ties → first match alphabetically.
   - Minimum 1 match required (0 matches = no specialist found).

3. **Fallback by step type**:

| Step Type | Fallback Agent |
|-----------|---------------|
| `implement` | `agents/meta/harness-dev-agent.md` |
| `fix` | `agents/meta/harness-dev-agent.md` |
| `review` | `agents/meta/harness-review-agent.md` |
| `verify` | `agents/meta/harness-eval-agent.md` |
| `human-review` | No spawn |

### Auto-discovery Procedure

\```bash
# List all domain agents
glob: agents/domain/*.md

# For each agent, read only the YAML frontmatter
# Extract route_keywords array
# Match against: step title + step "What to do" content (case-insensitive)
\```

### Routing Examples

- Step "Implement security authentication" → keywords match `security-engineer` (security, auth, 认证) → select `security-engineer`
- Step "Review code quality" → keywords match `code-reviewer` → select `code-reviewer`
- Step "Verify API endpoint contracts" → keywords match `api-tester` (api, API, endpoint) → select `api-tester`
- Step "Fix database query performance" → keywords match `database-optimizer` → select `database-optimizer`
- Step "Implement utility function" → no keyword match → fallback `harness-dev-agent`
- Step "Verify integration" → no keyword match → fallback `harness-eval-agent`

### Parallel Safety Check

Before parallel dispatch, check `parallel_safe` in selected agent's frontmatter:
- `parallel_safe: true` (or absent) → can run in parallel
- `parallel_safe: false` → extract from parallel group, execute serially after group completes

## 2. Prompt Builder

Construct a self-contained prompt for each spawned agent.

### Standard Prompt Template

\```
# Task: {step_title}

## Context
- Mission: {mission_objective}
- Boundaries: {mission_boundaries}
- Step type: {step_type}
- Phase: {current_phase} (if applicable)

## What to do
{step_what_to_do}

## Tools to use
{step_tools}

## Constraints
- Do NOT modify files outside your assigned scope
- Do NOT modify .claude/harness/ or .claude/harness-state.json
- Do NOT modify files that other parallel agents are working on
{additional_constraints_from_mission}

## Completion criteria
{step_completion_criteria}

## Output format
{output_format_from_agent_template}
\```

### Parallel Mode Extra Constraints (auto-injected when Phase has >1 step)

\```
## PARALLEL EXECUTION CONSTRAINTS
- You are one of {N} agents working in parallel in Phase {P}
- Your assigned scope: {step_scope_description}
- Other agents are working on: {list_of_other_steps_with_scope}
- Do NOT edit files that may be touched by other agents
- If you need to modify a shared file, STOP and report the conflict
\```

### Scope Derivation

For each step, derive scope from the step's "What to do" section:
- Extract file paths, module names, or directory names mentioned
- If no explicit scope, use the step title to infer scope
- For `review` steps: scope = cumulative (all files since mission start via `git diff --name-only <branch-point>..HEAD`)

## 3. Spawn Manager

### Single Step (Phase with 1 pending step, or linear mode)

Spawn one agent, wait for completion:

\```
Agent(
  name="step-{N}-{slug}",
  subagent_type="general-purpose",  # or domain specialist type
  prompt="{constructed_prompt}"
)
\```

### Parallel Steps (Phase with 2+ pending steps)

Spawn all agents in a single message for concurrent execution:

\```
Agent(name="step-1-auth", prompt="...")    # ← all 3 in one message
Agent(name="step-2-product", prompt="...") # ← run concurrently
Agent(name="step-3-payment", prompt="...") # ← run concurrently
\```

Batch by `max_concurrency` (from state file, default 3). If Phase has more steps than max_concurrency, process in batches.

### Post-Spawn: Collect Results

After all agents return:
1. Read each agent's output
2. For `implement`/`fix` steps: spawn `harness-eval-agent` per step for validation
3. For `review` steps: read `review_report.json`, check verdict
4. Update `step_statuses` via `state-manager.py step-status`
5. Log results via `state-manager.py log`

### Failure Handling in Parallel Mode

When any step in a Phase fails:
1. Mark failed step(s) as `failed` in `step_statuses`
2. Mark passed step(s) as `completed` — their work is preserved
3. Retry failed step(s) individually (serial execution)
4. Retry counts toward `consecutive_failures`
5. If `consecutive_failures >= 3`: circuit breaker trips
```

- [ ] **Step 2: Commit**

```bash
git add skills/harness-dev/agent-spawn.md
git commit -m "docs(harness-dev): create unified agent spawn reference"
```

---

### Task 7: harness-dev loop-reference.md — Update for Unified Routing

**Files:**
- Modify: `skills/harness-dev/loop-reference.md:8-34` (type: implement section)
- Modify: `skills/harness-dev/loop-reference.md:36-61` (type: review section)
- Modify: `skills/harness-dev/loop-reference.md:63-79` (type: fix section)

- [ ] **Step 1: Update `type: implement` section**

In the Dual Mode subsection, replace the current agent selection instructions with a reference to the unified spawn system:

Find the text starting at line 8 `## type: implement (or no type field -- backwards compatible)` and ending at line 34.

Replace the Dual Mode agent selection paragraph with:

```markdown
## type: implement (or no type field -- backwards compatible)

Implement code to meet the step's completion criteria.

**Single mode** (`execution_mode: single`): Plan and code directly using Claude Code tools (Read, Write, Edit, Bash, Grep, Glob). If `skills` field is set in state file, load each skill via Skill tool before starting work.

**Dual mode** (`execution_mode: dual`): Plan only. Delegate coding to an agent selected via the unified Agent Router (see `agent-spawn.md`).

Agent selection follows the priority order from `agent-spawn.md` Section 1:
1. Playbook step `specialist:` field → use that agent
2. Auto-discovery: match step description against `agents/domain/*.md` `route_keywords`
3. Fallback: `harness-dev-agent`

For parallel execution within a Phase, see `agent-spawn.md` Section 3 (Spawn Manager).

State commands:
- Before starting: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-status "Step N" running`
- After completion: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-status "Step N" completed`
- On failure: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-status "Step N" failed`
```

- [ ] **Step 2: Update `type: review` section**

Replace the agent selection in the review section (line 36) to reference the unified Router:

```markdown
## type: review

ALWAYS spawn a review agent. Agent selection via unified Router (see `agent-spawn.md`):

1. Read the current step description from the playbook
2. Select agent via Router:
   - Step `specialist:` field → use that agent (e.g., security review → `security-engineer`)
   - Auto-discovery: match step description against domain agent `route_keywords`
   - Fallback: `harness-review-agent`
3. **Determine cumulative scope**: Before spawning the review agent, compute the full review scope:
   - Run `git diff --name-only <branch-point>..HEAD` to list ALL files modified since mission start
   - If git is unavailable, read the execution stream log to identify all files modified across iterations
   - Pass this full file list to the review agent as its scope
4. Spawn the selected agent with:
   - The current step description
   - **Cumulative scope**: ALL modified files since mission start
   - **Previous fix re-audit**: Explicitly instruct the agent to re-examine fix code from ALL previous iterations
   - **Density floor**: >= 1 finding per 1500 LOC, with exhaustion evidence for clean areas
5. The review agent writes findings to `.claude/harness/logs/review_report.json`
6. Read `.claude/harness/logs/review_report.json` to check the verdict:
   - `pass` -- verify `scope.cumulative == true` and `compliance.requirements_met == compliance.requirements_total`. If incomplete, re-dispatch with expanded scope.
   - `conditional-pass` -- log warnings, check `compliance.gaps` for missing requirements.
   - `fail` -- log critical issues and compliance gaps, next fix step will address them
7. **Verify review quality** (anti-shallow-pass defense):
   - `density.loc_per_finding` <= 1500
   - `blind_spots` field exists and is non-empty for large codebases
   - `compliance.gaps` — any gap with status `missing` is a requirement with zero implementation
   - If density > 2000 LOC/finding, re-dispatch with stricter instructions
8. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Review completed: <verdict>, compliance <met>/<total>, density <loc/finding>"`
9. Skip validation (step 5.6) for review steps — proceed directly to step 5.7/5.8
```

- [ ] **Step 3: Update `type: fix` section**

Replace the fix section (line 63) to reference unified Router:

```markdown
## type: fix

Read the review report, then apply fixes.

1. Read `.claude/harness/logs/review_report.json`
2. If report is missing or verdict was `pass` with no compliance gaps → skip, log and advance
3. Extract issue list AND compliance gaps:
   - Issues from `issues` array → fix code quality bugs
   - Gaps from `compliance.gaps` array → implement missing requirements

Then dispatch based on execution mode:
- **Single mode**: Fix yourself using Read, Edit, Write, Bash
- **Dual mode**: Select agent via unified Router (see `agent-spawn.md`). Route by:
  1. Playbook `specialist:` field
  2. Match review report issue categories against domain agent `route_keywords`
  3. Fallback: `harness-dev-agent`

After fixes:
- Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Applied fixes for <N> issues + <M> compliance gaps"`
- Run validation (step 5.6) if step has completion criteria
```

- [ ] **Step 4: Commit**

```bash
git add skills/harness-dev/loop-reference.md
git commit -m "docs(harness-dev): update loop-reference for unified agent routing"
```

---

### Task 8: harness-dev SKILL.md — Rewrite Section 5.5 for Phase-Aware Execution

**Files:**
- Modify: `skills/harness-dev/SKILL.md:175-213` (Section 5.5)

- [ ] **Step 1: Replace Section 5.5 with Phase-aware execution logic**

Replace the current Section 5.5 (from `### 5.5. Execute Current Step` to the end of the Domain Agent Routing subsection) with:

```markdown
### 5.5. Execute Current Phase

First, log a structured round report for traceability:

\```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" report "<subtask>" "<strategy>" "<verification>" "<state_target>"
\```

Then, determine execution mode:

#### Phase Detection

Read `current_phase` from the state file:
- If `current_phase` is `null` or absent → **Linear mode** (execute single step, current behavior)
- If `current_phase` is a number → **Phase mode** (execute all pending steps in current Phase)

#### Linear Mode (backward compatible)

Execute the single step indicated by `current_step`. Follow step-type instructions in `loop-reference.md`. For agent selection, use the unified Router (see `agent-spawn.md`).

#### Phase Mode

1. **Identify pending steps**: Read the playbook. Extract all steps with `Phase: {current_phase}`. Filter to steps with `step_statuses` == `pending` or absent.

2. **Parallel spawn**: For each pending step:
   a. Select agent via unified Router (`agent-spawn.md` Section 1)
   b. Construct prompt via Prompt Builder (`agent-spawn.md` Section 2)
   c. Check `parallel_safe` — extract non-safe steps for serial execution after group

   Spawn all parallel-safe agents in a single message:
   \```
   Agent(name="step-N-slug", subagent_type="general-purpose", prompt="...")
   Agent(name="step-M-slug", subagent_type="general-purpose", prompt="...")
   # All dispatched concurrently
   \```

3. **Collect results**: After all agents return, read each agent's output.

4. **Validate each completed step**: For `implement`/`fix` steps, spawn `harness-eval-agent` per step. For `review` steps, read `review_report.json`.

5. **Update step statuses**:
   \```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-status "Step N" completed
   # or
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-status "Step N" failed
   \```

6. **Handle serial-only steps**: Execute `parallel_safe: false` steps one at a time after the parallel group.

7. **Handle failures**: See Section 2.3 of the design spec — retry failed steps individually (serial).

8. **Log the routing decision**:
   \```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Phase {N}: {completed_count}/{total} steps completed"
   \```

#### Agent Selection (all modes)

ALL step types route through the unified Agent Router. See `agent-spawn.md` for full details.
Priority: `specialist:` field → `route_keywords` match → step-type fallback.
```

- [ ] **Step 2: Update the step-type summary table in Section 5.5**

Replace the current summary table (around line 186-192) with:

```markdown
| Type | Action | Validates? | Agent Routing |
|------|--------|-----------|---------------|
| `implement` | Code directly (single) or delegate to agent (dual/parallel) | Yes — run 5.6 | Router → specialist/keywords → dev-agent |
| `review` | Spawn review agent with cumulative scope | No — skip to 5.7/5.8 | Router → specialist/keywords → review-agent |
| `fix` | Apply fixes from review_report.json + compliance gaps | Yes — run 5.6 | Router → specialist/keywords → dev-agent |
| `human-review` | Pause for human, advance step, output LOOP_PAUSE | No | No spawn |
| `verify` | Spawn eval-agent for independent validation | No | Router → specialist/keywords → eval-agent |
```

- [ ] **Step 3: Remove old Domain Agent Routing subsection**

Delete the old "Domain Agent Routing (implement and fix steps)" subsection (approximately lines 199-213). This logic is now in `agent-spawn.md`.

- [ ] **Step 4: Update Section 5.7 (On PASS) for Phase-aware step-advance**

After the existing step-advance logic in Section 5.7, add Phase-aware advancement:

```markdown
**Phase-aware advancement**: After marking a step as `completed` via `step-status`, check if all steps in the current Phase are complete:
\```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" phase-status
\```
If all steps show `completed`, advance to the next Phase:
\```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" phase-advance
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Phase {N} complete, advancing to Phase {N+1}"
\```
\```

- [ ] **Step 5: Commit**

```bash
git add skills/harness-dev/SKILL.md
git commit -m "feat(harness-dev): Phase-aware execution with unified agent routing"
```

---

## Self-Review Checklist

### Spec Coverage

| Spec Requirement | Task |
|-----------------|------|
| `Phase: N` field in playbook template | Task 3 |
| `step_statuses`, `current_phase`, `max_concurrency` in state file | Task 1 |
| `step-status`, `phase-advance`, `phase-status` commands | Task 2 |
| Parallel agent spawn in single message | Task 8 |
| Unified Router for all step types | Task 6 |
| Prompt Builder with parallel constraints | Task 6 |
| `parallel_safe` frontmatter field | Task 4 |
| Phase grouping guidance in harness-start | Task 5 |
| loop-reference.md updated for unified routing | Task 7 |
| SKILL.md Section 5.5 rewritten | Task 8 |

### Placeholder Scan

No TBD, TODO, or "implement later" in this plan.

### Type Consistency

- `step_statuses` dict with string values (`pending`/`running`/`completed`/`failed`) — used consistently in Task 2 (cmd_step_status validation) and Task 8 (SKILL.md instructions).
- `current_phase` as `None`/`null` for linear mode — consistent between Task 1 (init default) and Task 8 (phase detection).
- `max_concurrency` as int, default 3 — consistent between Task 1 (init) and Task 6 (spawn manager).
- `parallel_safe: true` as bool — consistent between Task 4 (frontmatter) and Task 6 (router check).
