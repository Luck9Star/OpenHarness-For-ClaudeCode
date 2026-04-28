# Phase-Based Parallel Execution for OpenHarness

**Date**: 2026-04-28
**Status**: Approved
**Branch**: refactor/first-principles-json-authority

## Problem

OpenHarness `harness-dev` executes playbook steps strictly sequentially — one step per loop iteration. When a task has independent steps (e.g., "implement auth" and "implement product API" have no dependencies), they still run one after another, wasting time.

By contrast, the superpowers `dispatching-parallel-agents` skill demonstrates that independent tasks can be solved concurrently by multiple agents. The harness loop does not leverage this capability.

Additionally, agent routing logic is scattered across SKILL.md prose with no unified abstraction. Domain specialists (`agents/domain/*.md`) with `route_keywords` are only consulted for `implement`/`fix` steps, not `review`/`verify` steps.

## Solution: Phase-Aware Loop + Unified Agent Spawn

### Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Parallelism layer | harness-dev built-in | No external dependency on superpowers |
| Dependency expression | `Phase: N` field in playbook | Simpler than DAG, easy for agent to generate |
| Failure strategy | Partial failure, retry failed steps individually | Preserves completed work |
| Max concurrency | 3 (default, configurable) | Matches orchestrator protocol in CLAUDE.md |
| Agent routing | Unified for ALL step types | Domain specialists can handle review/verify too |

---

## Section 1: Data Model

### 1.1 Playbook Template — `Phase` Field

Each step in `playbook.md` gets an optional `Phase: N` field:

```markdown
## Step 1: Implement User Auth
Phase: 1
Type: implement
...

## Step 2: Implement Product API
Phase: 1
Type: implement
...

## Step 3: Integration Test
Phase: 2
Type: verify
...
```

**Rules:**

- Phase values are positive integers, ascending.
- Steps in the same Phase execute in parallel.
- Phase N+1 waits for Phase N to fully complete.
- Steps without a `Phase` field = implicit Phase 0 (linear execution, backward compatible).
- `review`/`fix`/`verify` steps are typically in their own Phase, separate from `implement` steps.
- Steps within the same Phase MUST be truly independent (not editing the same files).

### 1.2 State File — Per-Step Tracking

New fields added to `.claude/harness-state.json`:

```json
{
  "current_phase": 1,
  "step_statuses": {
    "Step 1": "running",
    "Step 2": "pending",
    "Step 3": "pending"
  },
  "max_concurrency": 3
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `current_phase` | int | `null` | Current executing Phase number. `null` = linear mode. |
| `step_statuses` | object | `{}` | `{step_name: pending \| running \| completed \| failed}` |
| `max_concurrency` | int | `3` | Max parallel agents per Phase |

**Backward compatibility**: When `step_statuses` is empty or absent, the loop falls back to linear `current_step` mode.

### 1.3 state-manager.py — New Commands

| Command | Usage | Description |
|---------|-------|-------------|
| `step-status` | `step-status <step_name> <status>` | Update a single step's status in `step_statuses` |
| `phase-advance` | `phase-advance` | Increment `current_phase` after all Phase steps pass |
| `phase-status` | `phase-status` | Print current Phase step status summary |

---

## Section 2: Execution Flow

### 2.1 Loop Iteration Rewrite

The current `5.5 Execute Current Step` in `harness-dev/SKILL.md` becomes `5.5 Execute Current Phase`:

```
5.5a. Read state → get current_phase and step_statuses
5.5b. Extract all pending steps for current Phase from playbook
5.5c. Batch by max_concurrency (≤ 3 parallel)
5.5d. Parallel spawn Agent (one per step, via Agent tool in same message)
5.5e. Await all agent returns → collect results
5.5f. Validate each completed step (spawn eval-agent per step)
5.5g. Update step_statuses via state-manager
5.5h. Determine Phase completion state
```

### 2.2 Agent Spawn Pattern

Multiple Agent tool calls in a single message trigger parallel execution in Claude Code:

```
Agent(name="step-1-auth", prompt="...self-contained...")
Agent(name="step-2-product", prompt="...self-contained...")
Agent(name="step-3-payment", prompt="...self-contained...")
# All 3 dispatched concurrently
```

Each agent prompt MUST include:
- Step description (from playbook)
- Constraints (from mission.md Boundaries)
- Completion criteria (from playbook Completion criteria)
- Parallel execution constraints (scope isolation, no overlap)

### 2.3 Phase Completion Logic

```
if ALL steps in current_phase == "completed":
    → phase-advance
    → log "Phase N complete: all steps PASS"

elif ANY step == "failed":
    → Retry failed steps individually (serial execution)
    → Retries count toward consecutive_failures
    → If consecutive_failures >= 3: circuit breaker trips

elif ANY step == "running":
    → Wait (should not occur; Agent tool is blocking)
```

### 2.4 Stop-Hook Interaction

**No changes needed to `stop-hook.py`.**

Each Phase executes within a single turn. The stop-hook sees one turn doing one Phase's work, then sends a continuation prompt for the next turn (next Phase). `current_step` during parallel execution reflects the Phase, not an individual step.

Edge case: Phase retry for failed steps may span a turn. If `consecutive_failures >= 3`, the circuit breaker triggers normally.

---

## Section 3: Unified Agent Spawn System

### 3.1 Architecture

```
┌──────────────────────────────────────────┐
│         Unified Agent Spawn              │
├──────────┬───────────┬───────────────────┤
│  Router  │  Prompt   │  Spawn Manager   │
│(select)  │(construct)│(serial/parallel)  │
└──────────┴───────────┴───────────────────┘
     ↑           ↑              ↑
  route_keywords  step context   Phase info
  specialist:     mission bounds  max_concurrency
```

### 3.2 Agent Router

All step types use the same routing logic. No exceptions.

**Priority:**

1. **Manual override**: Step has `specialist:` field → use that agent directly.
2. **Auto-discovery**: Match step description against `route_keywords` in `agents/domain/*.md` frontmatter. Best match (most keyword hits) wins.
3. **Fallback by step type**:

| Step Type | Fallback Meta Agent |
|-----------|-------------------|
| `implement` | `harness-dev-agent` |
| `fix` | `harness-dev-agent` |
| `review` | `harness-review-agent` |
| `verify` | `harness-eval-agent` |
| `human-review` | No spawn |

**Examples:**

```
Step: "Review security implementation" + specialist: security-engineer
→ Router selects security-engineer (domain expert does security review)

Step: "Verify API contracts" (no specialist, keywords match api-tester)
→ Router selects api-tester (API specialist does verification)

Step: "Review code quality" (no specialist, keywords match code-reviewer)
→ Router selects code-reviewer (domain specialist reviews code)

Step: "Verify integration" (no specialist, no keyword match)
→ Fallback harness-eval-agent (meta agent handles generic verification)
```

### 3.3 Prompt Builder

Each spawned agent receives a self-contained prompt following the `dispatching-parallel-agents` best practices:

```markdown
# Task: {step_title}

## Context
- Mission: {mission_objective}
- Boundaries: {mission_boundaries}
- Step type: {step_type}
- Phase: {current_phase}

## What to do
{step_description}

## Constraints
- Do NOT modify files outside your assigned scope: {step_file_scope}
- Do NOT modify .claude/harness/ or .claude/harness-state.json
- {additional_constraints_from_mission}

## Completion criteria
{step_completion_criteria}

## Output format
{agent_template_output_format}
```

**Parallel mode auto-injects:**

```markdown
## PARALLEL EXECUTION CONSTRAINTS
- You are one of {N} agents working in parallel in Phase {P}
- Your assigned scope: {scope_description}
- Other agents are working on: {other_steps_summary}
- Do NOT edit files that may be touched by other agents
```

### 3.4 Agent Frontmatter Schema

All `agents/**/*.md` use this unified schema:

```yaml
name: string               # Required. Agent identifier slug.
description: string        # Required. One-line purpose.
category: meta | domain    # Required. Meta = framework, domain = specialist.
tools: [string]            # Required. Allowed tool names.
model: string              # Optional. Model override (default: inherit parent).
route_keywords: [string]   # Domain: required. Meta: absent.
parallel_safe: bool        # Optional. Default true. Can run in parallel with other agents.
```

New `parallel_safe` field:
- `true` (default): Can execute in parallel with other agents.
- `false`: Must execute serially (e.g., needs exclusive resource access).
- If any step's agent has `parallel_safe: false`, that step is extracted from the parallel group and executed serially.

### 3.5 Code Organization

| Current Location | After Refactor |
|-----------------|----------------|
| `harness-dev/SKILL.md` Section 5.5 Domain Agent Routing | Move to `skills/harness-dev/agent-spawn.md` (standalone reference) |
| `agents/domain/*.md` `route_keywords` | Keep. Router reads frontmatter directly. |
| `agents/meta/harness-dev-agent.md` | Keep. Serves as fallback agent. |
| `harness-dev/loop-reference.md` implement/fix sections | Update to reference `agent-spawn.md`. |

---

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `templates/playbook.md` | Modify | Add `Phase: N` field per step |
| `scripts/state-manager.py` | Modify | Add `step-status`, `phase-advance`, `phase-status` commands; `step_statuses`, `current_phase`, `max_concurrency` fields |
| `skills/harness-dev/SKILL.md` | Modify | Rewrite Section 5.5 for Phase-aware execution |
| `skills/harness-dev/loop-reference.md` | Modify | Update implement/fix/review sections for parallel + unified routing |
| `skills/harness-dev/agent-spawn.md` | Create | Unified agent spawn reference (Router + Prompt Builder + Spawn Manager) |
| `skills/harness-start/templates-reference.md` | Modify | Guide agents to generate Phase groupings in playbook |
| `agents/meta/harness-dev-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/meta/harness-eval-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/meta/harness-review-agent.md` | Modify | Add `parallel_safe: true` to frontmatter |
| `agents/domain/*.md` (all 6) | Modify | Add `parallel_safe: true` to frontmatter |

**Files NOT changed:**
- `scripts/stop-hook.py` — No changes needed (Phase executes within a single turn).
- `scripts/setup-harness-loop.sh` — No changes needed (Phase config lives in state file).
- `scripts/cleanup.py` — No changes needed.

---

## Backward Compatibility

1. **Playbooks without Phase fields**: All steps assigned to Phase 0, executed sequentially. Identical to current behavior.
2. **State files without step_statuses**: Loop detects empty `step_statuses` and falls back to linear `current_step` mode.
3. **Agent templates without parallel_safe**: Treated as `parallel_safe: true` (default).
4. **single mode**: Works with parallel execution — the main agent spawns multiple Agent tool calls in one message.
5. **dual mode**: Works with parallel execution — same pattern, multiple dev-agent spawns.

---

## Out of Scope

- DAG-based dependency resolution (Phase grouping is simpler and sufficient).
- Multi-session parallel execution (each Phase runs in a single turn).
- Dynamic concurrency adjustment based on step complexity.
- Worktree isolation for parallel agents (all agents work in the same directory).
