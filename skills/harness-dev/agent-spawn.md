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

```bash
# List all domain agents
glob: agents/domain/*.md

# For each agent, read only the YAML frontmatter
# Extract route_keywords array
# Match against: step title + step "What to do" content (case-insensitive)
```

### Routing Examples

- Step "Implement security authentication" → keywords match `security-engineer` (security, auth) → select `security-engineer`
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

```
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
```

### Parallel Mode Extra Constraints (auto-injected when Phase has >1 step)

```
## PARALLEL EXECUTION CONSTRAINTS
- You are one of {N} agents working in parallel in Phase {P}
- Your assigned scope: {step_scope_description}
- Other agents are working on: {list_of_other_steps_with_scope}
- Do NOT edit files that may be touched by other agents
- If you need to modify a shared file, STOP and report the conflict
```

### Scope Derivation

For each step, derive scope from the step's "What to do" section:
- Extract file paths, module names, or directory names mentioned
- If no explicit scope, use the step title to infer scope
- For `review` steps: scope = cumulative (all files since mission start via `git diff --name-only <branch-point>..HEAD`)

## 3. Spawn Manager

### Parallelism Inference

Before spawning, infer the optimal concurrency from task structure. Do NOT default to 1 agent — the goal is parallelism.

**Inference procedure:**

1. **Count independent steps**: Read the playbook. Count implement/fix steps that can execute without dependencies on each other (no shared output files, no sequential data flow).

2. **Assess parallel safety**: For each independent step, check if it modifies unique files. Steps modifying the same file MUST be sequential.

3. **Determine concurrency**:

| Task Structure | Inferred Concurrency | Example |
|---|---|---|
| 1 step, or all steps sequential | 1 | "Fix auth bug in login.ts" |
| 2 independent modules | 2 | "Add auth + add product API" |
| 3+ independent modules | 3 | "Implement auth, product, payment APIs" |
| 5+ independent modules | 3 (cap) | Large feature with many modules |
| Review/fix cycle steps | 1 (sequential by nature) | "Review and fix all issues" |

4. **Store in state**: Write `inferred_max_concurrency` to the execution stream log:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Parallelism inference: max_concurrency=<N>, reason=<brief justification>"
   ```

**Override**: User can pass `--max-concurrency N` to override inference. Explicit parameter always wins.

### Single Step (Phase with 1 pending step, or linear mode)

Spawn one agent, wait for completion:

```
Agent(
  name="step-{N}-{slug}",
  subagent_type="general-purpose",
  prompt="{constructed_prompt}"
)
```

### Parallel Steps (Phase with 2+ pending steps)

Spawn all agents in a single message for concurrent execution:

```
Agent(name="step-1-auth", prompt="...")    ← all 3 in one message
Agent(name="step-2-product", prompt="...") ← run concurrently
Agent(name="step-3-payment", prompt="...") ← run concurrently
```

Batch by `inferred_max_concurrency` (or `max_concurrency` from state file if explicitly set). If Phase has more steps than max_concurrency, process in batches.

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
