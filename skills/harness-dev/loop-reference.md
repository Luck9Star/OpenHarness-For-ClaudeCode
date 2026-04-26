# Loop Reference — Step Type Details

This file contains detailed instructions for each playbook step type.
Read this when executing a step in section 5.5 of harness-dev.

---

## type: implement (or no type field -- backwards compatible)

Check `execution_mode` in the state file:

**Single Mode (`execution_mode: single`)**

You plan AND code directly. Use Claude Code tools (Read, Write, Edit, Bash, Grep).

If the `skills` field is set in the state file, load each specified skill using the Skill tool before starting step execution.

After completing the step:
- Log what was done: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Completed <step description>"`
- Run validation (see step 5.6)

**Dual Mode (`execution_mode: dual`)**

You plan only. Delegate coding to a sub-agent.

1. Read the current step requirements from the playbook
2. Construct a detailed prompt with: task, file paths, constraints from `.claude/harness/mission.md`, eval criteria, skills to load
3. Spawn `harness-dev-agent` in the current directory
4. Wait for the agent to complete
5. Log the delegation: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Delegated <step> to harness-dev-agent"`

## type: review

ALWAYS spawn `harness-review-agent` -- read-only code review.

1. Read the current step description from the playbook
2. **Determine cumulative scope**: Before spawning the review agent, compute the full review scope:
   - Run `git diff --name-only <branch-point>..HEAD` to list ALL files modified since mission start
   - If git is unavailable, read the execution stream log to identify all files modified across iterations
   - Pass this full file list to the review agent as its scope
3. Spawn `harness-review-agent` with:
   - The current step description
   - **Cumulative scope**: ALL modified files since mission start (not just current step's diff)
   - **Previous fix re-audit**: Explicitly instruct the agent to re-examine fix code from ALL previous iterations, not just current changes
   - **Density floor**: Instruct the agent that the review must have >= 1 finding per 1500 LOC, with exhaustion evidence for clean areas
4. The review agent writes findings to `.claude/harness/logs/review_report.json`
5. Read `.claude/harness/logs/review_report.json` to check the verdict:
   - `pass` -- verify the `scope.cumulative` field is `true` and `scope.files_reviewed` covers all modified files. Also verify `compliance.requirements_met == compliance.requirements_total` (no spec gaps). If either is incomplete, re-dispatch with expanded scope.
   - `conditional-pass` -- log warnings, check `compliance.gaps` for missing requirements. Proceed but note issues.
   - `fail` -- log critical issues and compliance gaps, next fix step will address them
6. **Verify review quality** (anti-shallow-pass defense):
   - Check the `density` field in the report: `loc_per_finding` should be <= 1500
   - Check `blind_spots` field exists and is non-empty for large codebases
   - Check `compliance.gaps` — if any gap has status `missing`, it's a requirement with zero implementation
   - If density is suspiciously low (e.g., > 2000 LOC per finding), re-dispatch with stricter instructions
7. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Review completed: <overall verdict>, compliance <met>/<total>, density <loc_per_finding> LOC/finding, <N> files reviewed (cumulative)"`
8. Skip validation (step 5.6) for review steps -- proceed directly to step 5.7/5.8

## type: fix

Read the review report, then apply fixes.

1. Read `.claude/harness/logs/review_report.json`
2. If report is missing or overall verdict was `pass` with no compliance gaps, skip -- log and advance
3. Extract issue list AND compliance gaps:
   - Issues from `issues` array -> fix code quality bugs
   - Gaps from `compliance.gaps` array -> implement missing requirements or complete partial implementations

Then dispatch based on execution mode:
- **Single mode**: Fix yourself using Read, Edit, Write, Bash
- **Dual mode**: Spawn `harness-dev-agent` with the issue list and compliance gaps

After fixes:
- Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Applied fixes for <N> issues + <M> compliance gaps from review"`
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

Spawn `harness-eval-agent` for independent validation.

**ABSOLUTE RULE: eval-agent MUST be spawned via Bash. Self-assessment of verification or convergence is NEVER valid.**

The agent MUST NOT:
- Read review reports and reason about convergence internally
- Skip eval-agent spawn because "findings look reduced"
- Check eval criteria mentally and declare PASS/FAIL without independent agent validation
- Combine verify with a preceding step (review or fix) in a single turn

1. Read the current step description and eval criteria
2. Spawn `harness-eval-agent` with eval criteria, step description, instructions to independently verify
3. The eval-agent reports PASS or FAIL
4. **Post-spawn verification**: After eval-agent completes, confirm the spawn actually happened by checking:
   ```bash
   grep -q "eval-agent" .claude/harness/logs/execution_stream.log && echo "CONFIRMED: eval-agent spawned" || echo "WARNING: No eval-agent spawn evidence found"
   ```
   If no evidence is found, the verify step is INCOMPLETE — re-spawn eval-agent.
5. Log: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/state-manager.py" log "Verify: <PASS or FAIL> (eval-agent spawned and confirmed)"`
