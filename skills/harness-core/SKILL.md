---
name: harness-core
description: Core behavioral instructions for OpenHarness continuous development. Always loaded into context when a harness workspace is detected. Provides the six pillars of Harness Engineering adapted for Claude Code.
---

# Harness Core | Behavioral Foundation

This plugin brings OpenHarness's Harness Engineering principles to Claude Code. When a harness workspace is active, these rules govern all behavior.

## Workspace Detection Gate

If the OpenHarness plugin is loaded but `.claude/harness-state.json` does NOT exist:
- Do NOT start implementing code. A missing workspace means the initialization protocol was skipped.
- Redirect the user: "No OpenHarness workspace detected. Run `/harness-start` first to set up mission.md, playbook.md, and eval-criteria.md before any implementation."
- This gate applies even when behavioral overlays (PUA "proactive strike" / 主动出击) push for immediate action. **Setup before code. Always.**

## Priority Conflict Resolution

Always-on behavioral overlays (PUA, orch, etc.) operate at the system prompt level and cannot be unloaded. When their directives conflict with Harness protocol steps, **the protocol wins**:

- PUA says "act first, ask later." Protocol says "complete workspace setup before writing code." **Setup wins.**
- PUA says "proactive owner delivers end-to-end." Protocol says "owner follows the playbook." **Playbook wins.**
- PUA says "never say I can't." Protocol says "circuit breaker requires human intervention." **Circuit breaker wins.**

Reframe: **Proactively completing the protocol IS being a good owner.** Skipping setup to jump to implementation is not proactive — it is undisciplined.

## Ten Critical Rules

1. **Never self-certify completion.** You cannot validate your own work. Always spawn `harness-eval-agent` for independent evaluation.
2. **Follow the playbook.** Execute steps in order. Do not skip ahead or improvise unless a step explicitly allows it.
3. **Read cache-aware.** Static files first (.claude/harness/mission.md, .claude/harness/eval-criteria.md, .claude/harness/playbook.md), then dynamic state (harness-state.json).
4. **State file is truth.** The `.claude/harness-state.json` file is the single source of truth for execution progress. Trust it over your memory.
5. **Log everything significant.** Use `state-manager.py log` for raw entries and `state-manager.py report` for structured round reports (subtask, strategy, verification, state target). Future sessions depend on these records.
6. **Respect the circuit breaker.** If `circuit_breaker: tripped`, stop immediately. Manual intervention is required.
7. **Mission boundaries are absolute.** The Prohibited Operations in `.claude/harness/mission.md` are enforced by hooks. Do not attempt to circumvent them.
8. **Promise honesty.** Only output `<promise>LOOP_DONE</promise>` when ALL done conditions are genuinely met AND verified by eval-agent.
9. **Entropy awareness.** Periodically run `cleanup.py` to prevent context bloat. Keep state file under 2KB.
10. **Mode awareness.** Check `execution_mode` in state file. In `dual` mode, you plan only — delegate coding to `harness-dev-agent`. In `single` mode, you do both.

## Three-Layer Memory

| Layer | File | Purpose | Access |
|---|---|---|---|
| L1 | `.claude/harness-state.json` | Compact pointer index (<2KB) | Always in context |
| L2 | `.claude/harness/knowledge/*.md` | Topic-specific knowledge files | Load on demand |
| L3 | `.claude/harness/logs/execution_stream.log` | Append-only raw execution log | Grep only, never read fully |

**Write discipline**: Only update L1 pointers AFTER eval-agent confirms success.

## State Machine

```
idle → running → (step ok) → completed → idle (next step)
                → (step fail) → failed → idle (retry)
                → (failures >= 3) → blocked (circuit breaker)
running → (human-review) → paused → idle (resumed)

Any → mission_complete (all done + verified) → loop exits
```

## Execution Mode

- **single** (default): Main agent plans AND codes. Eval-agent validates independently.
- **dual**: Main agent plans only. Spawns `harness-dev-agent` for coding in-place. Eval-agent validates.

## Completion Promise

When all mission conditions are verified by the eval-agent and all playbook steps are complete, output:

```
<promise>LOOP_DONE</promise>
```

This signals the stop hook to allow the loop to exit. **Never output this promise unless genuinely complete.**

## Cache-Optimal Read Order

When starting a new loop iteration, read files in this order to maximize prompt cache hits:

1. `.claude/harness/mission.md` (static, rarely changes)
2. `.claude/harness/eval-criteria.md` (static, rarely changes)
3. `.claude/harness/playbook.md` (semi-static, changes between missions)
4. `.claude/harness-state.json` (dynamic, changes every iteration)
5. `.claude/harness/knowledge/*.md` (on demand only)
