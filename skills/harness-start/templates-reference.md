# Template Reference — Workspace File Structure

This file contains detailed instructions for filling workspace template files.
Read this when generating `.claude/harness/` files in Step 5.

---

## .claude/harness/mission.md

Fill based on the task description (use the expanded version from Step 1A if wizard was used):
- **Mission Name**: the task name from Step 4
- **Mission Objective**: the user's task description (expanded version if wizard refined it)
- **Done Definition**: derive from the verified deliverables in Step 1B — each deliverable maps to a done condition
- **Boundaries**: set allowed/prohibited operations
- **Execution Parameters**: set verify_instruction and execution_mode from user input
- **Output Definition**: list the confirmed deliverables from Step 1B

## .claude/harness/playbook.md

Create a concrete step-by-step plan using the quality profile from Step 2.

**Step types** (each step must have a `Type` field):
- `implement` -- write/create/modify code
- `review` -- spawn harness-review-agent for read-only code review
- `fix` -- apply fixes based on review feedback (reads `.claude/harness/logs/review_report.json`)
- `verify` -- spawn harness-eval-agent for validation
- `human-review` -- pause loop for human inspection and approval

**Dynamic step generation rules based on quality profile**:

- **User wants review (review_rounds > 0)**: After each `implement` step, insert a `review` step followed by a `fix` step.
- **User wants TDD**: For each logical unit of work: `verify` (write tests first) -> `implement` (make tests pass).
- **User wants quick (no review, no TDD)**: Just `implement` + final `verify`.
- **Simple task (auto-detected)**: Minimal: `implement` followed by a single `verify`.

**Human-review insertion rules** (only if user explicitly requests checkpoints):
- **1-2 implement steps**: No human-review needed
- **3-4 implement steps**: Insert one `human-review` after the midpoint
- **5+ implement steps**: Insert at 33%, 66%, and before final `verify`

**By default, do NOT insert human-review steps.**

**General playbook rules**:
- Each step must have: type, what to do, tools to use, completion criteria, failure handling
- Steps should be ordered by dependency
- Add a dependency diagram at the bottom
- The final step should always be a `verify` step
- When wizard was used, align steps with the deliverables from Step 1B

**Cycle playbook** (for iterative review-fix-verify tasks):
- If the task type is "review" or "iterative improvement" (e.g., "review codebase and fix all issues"), use a cycle playbook:
  ```
  Step 1: review (cumulative scope)
  Step 2: fix (apply findings)
  Step 3: verify (eval-agent validation)
  ```
  Set `--cycle-steps 1,3` in the init command so the loop cycles: review -> fix -> verify -> review -> ... until all criteria pass.
- The done condition should be: "All review findings resolved, all tests pass, convergence criterion passes"
- **MANDATORY**: Add a "Cycle Behavior" section to the playbook with: `min_cycles`, `max_cycles`, `convergence metric`, and `done condition`
- **MANDATORY**: The eval-criteria MUST include a **numbered convergence check** (see eval-criteria section below). Without it, the loop exits after cycle 1 when all non-convergence criteria pass.

## .claude/harness/eval-criteria.md

Create validation standards based on the verify instruction:
- Start with the verified checks from Step 1C — each check becomes a standard
- Add structural validation standards (file existence, content plausibility)
- Each standard: check name, method, pass condition, on-fail action
- Keep all checks machine-verifiable
- Ensure every deliverable from Step 1B has at least one corresponding check

**Quality enforcement rules** (prevent Goodhart's Law — process compliance != quality):

- **Every deliverable check must have a quality criterion**, not just existence. "File exists" is never sufficient alone — pair it with content depth, structure, or behavioral verification.
- **For review/audit tasks**: Include the Review Task Standards from the template (Density Check, Exhaustion Check, Convergence with Proof, Blind Spot Acknowledgment). These are MANDATORY for any task whose primary output is a review report.
- **For implementation tasks**: Each functional check should have both a positive condition (does it work?) and a depth condition (is it complete enough?). Example: not just "tests pass" but "tests cover >= N scenarios including error paths."
- **Never write a pass condition that can be trivially satisfied.** Avoid bare "file exists", "report contains N sections", "no new P0 findings" without requiring evidence of depth.

**Convergence Check (MANDATORY for cycle playbooks)**

When the playbook includes a `Cycle Behavior` section (review-fix loops), the eval-criteria MUST include a **numbered Standard** for convergence — not just the guideline section. Without this, the loop exits after cycle 1 because the eval-agent only checks numbered standards.

Required convergence standard format:
```
### Standard N: Convergence
- **Check**: `review_convergence`
- **Method**: Compare review_report.json findings between current cycle and previous cycle. If cycle < min_cycles, automatically FAIL.
- **Pass Condition**:
  - Cycle iteration >= min_cycles (from playbook Cycle Behavior section)
  - New P0 findings in this cycle = 0
  - New P1 findings in this cycle < previous cycle's new P1 count (or <= 3 if first comparison)
  - Review includes evidence section explaining what changed between cycles
- **On Fail**: Continue to next cycle. If cycle >= max_cycles, output convergence failure summary.
```

**Cross-Module Integration Verification (MANDATORY for multi-phase tasks)**

When the task spans multiple phases or modules (any playbook with 3+ implement steps that produce outputs consumed by later steps):
- The eval-criteria MUST include a check that verifies end-to-end data flow through ALL module boundaries
- Each module boundary check MUST:
  1. Run the upstream module to produce real output
  2. Feed that output to the downstream module
  3. Assert all fields the downstream reads are present and non-empty in the upstream output
- At least one check MUST be an integration test that exercises the full pipeline from first module to last
- Checks that only verify individual module behavior (unit tests) are INSUFFICIENT alone

Example criterion:
```
- check: "cross_module_pipeline_integrity"
  method: "Run importer -> profile_loader -> assemble_prompt with real data"
  pass_condition: "All intermediate outputs contain non-empty values for all fields consumed by the next module"
  on_fail: "Identify which field is missing at which boundary"
```

**Test Data Provenance (MANDATORY)**

For each test file referenced in eval criteria:
- If the test file constructs input data manually (hardcoded dicts, mock objects), the eval MUST ALSO require:
  1. At least one additional test using real upstream module output
  2. A comment or docstring explaining which upstream module produces this data
- If no real-data tests exist for modules with upstream dependencies, the eval criterion should FAIL
- This prevents the "tests pass but real pipeline fails" pattern

## .claude/harness/progress.md

Initialize with:
- Task name, current timestamp, conditions count from `.claude/harness/mission.md`
- All conditions set to `Not Met`
- Empty execution history section
