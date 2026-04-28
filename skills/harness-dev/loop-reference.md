# Loop Reference — Step Type Details

This file contains detailed instructions for each playbook step type.
Read this when executing a step in section 5.5 of harness-dev.

---

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

## type: human-review

Pause for human inspection and approval.

1. Generate a progress summary of completed steps
2. Output the summary to the user
3. **Advance the step counter BEFORE pausing** (P1 fix):
   ```
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" step-advance
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" update status paused
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Human-review checkpoint: paused for user inspection"
   ```
4. Output `<promise>LOOP_PAUSE</promise>` to suspend the loop
5. When the user resumes (via `/harness-dev --resume`), the next iteration continues from the step after this one

## type: verify

Spawn an evaluation agent for independent validation. Agent selection via unified Router (see `agent-spawn.md`):

1. Read the current step description and eval criteria
2. Select agent via Router:
   - Step `specialist:` field → use that agent (e.g., API verification → `api-tester`)
   - Auto-discovery: match step description against domain agent `route_keywords`
   - Fallback: `harness-eval-agent`
3. Spawn the selected agent with eval criteria, step description, instructions to independently verify

**ABSOLUTE RULE: eval-agent MUST be spawned. Self-assessment of verification or convergence is NEVER valid.**

The agent MUST NOT:
- Read review reports and reason about convergence internally
- Skip eval-agent spawn because "findings look reduced"
- Check eval criteria mentally and declare PASS/FAIL without independent agent validation
- Combine verify with a preceding step (review or fix) in a single turn

4. The eval-agent reports PASS or FAIL
5. **Post-spawn verification**: After eval-agent completes, confirm the spawn actually happened by checking:
   ```bash
   grep -q "eval-agent" .claude/harness/logs/execution_stream.log && echo "CONFIRMED: eval-agent spawned" || echo "WARNING: No eval-agent spawn evidence found"
   ```
   If no evidence is found, the verify step is INCOMPLETE — re-spawn eval-agent.
6. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Verify: <PASS or FAIL> (eval-agent spawned and confirmed)"`
