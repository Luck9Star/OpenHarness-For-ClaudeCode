# OpenHarness for Claude Code

Autonomous AI agent execution framework adapted from [OpenHarness](https://github.com/thu-nmrc/OpenHarness) Harness Engineering principles for Claude Code.

## What It Does

Turns Claude Code into a 24/7 autonomous development worker through **mechanical constraints, external audit, and 100% traceability**:

- **Machine-verifiable contracts** — objective "done" conditions, no subjective judgments
- **Oracle-isolated validation** — an independent agent validates your work; you cannot self-certify
- **Circuit breaker** — auto-stops after 3 consecutive failures
- **Three-layer memory** — state pointer (<2KB) + knowledge files + execution stream
- **Dual execution mode** — single (plan+code) or dual (plan → spawn coder agent)
- **`/loop` integration** — recurring execution without external cron

## Quick Start

```bash
# Install plugin
claude --plugin-dir /path/to/openharness-cc

# Initialize a new task
/harness-start "Build a REST API for user management" --verify "npm test"

# Start autonomous development loop
/harness-dev --mode single --verify "npm test"

# Check current status
/harness-status
```

## Commands

| Command | Description |
|---|---|
| `/harness-start` | Initialize a new harness task with mission, playbook, eval criteria |
| `/harness-dev` | Start the autonomous development loop (single or dual mode) |
| `/harness-status` | Show current workspace status, progress, and circuit breaker state |

## Architecture

```
openharness-cc/
  skills/          5 behavioral skills (core, init, execute, eval, dream)
  commands/        3 slash commands (start, dev, status)
  agents/          2 autonomous agents (dev-agent, eval-agent)
  hooks/           3 event hooks (SessionStart, PreToolUse, Stop)
  scripts/         4 utility scripts (state-manager, eval-check, setup-loop, cleanup)
  templates/       4 scaffold templates (mission, playbook, eval-criteria, progress)
```

## Execution Modes

### Single Mode (default)
Main agent plans AND codes. Eval-agent validates independently. Best for bug fixes, single-file changes, small features.

### Dual Mode
Main agent plans only. Spawns `harness-dev-agent` in isolated worktree for coding. Eval-agent validates. Best for multi-module development, architecture refactors.

## OpenHarness Mapping

| OpenHarness (OpenClaw/Codex) | This Plugin |
|---|---|
| `cron` + `harness_setup_cron.py` | `/loop` built-in command |
| `harness_coordinator.py` | Claude Code agent spawning + worktrees |
| `harness_eval.py` | `harness-eval-agent` (oracle isolation) |
| `harness_boot.py` circuit breaker | Stop hook + state file |
| `harness_dream.py` | `harness-dream` skill + `/loop 24h` |
| `harness_linter.py` | PreToolUse hook |
| `heartbeat.md` | `.claude/harness-state.local.md` |

## License

Based on [OpenHarness](https://github.com/thu-nmrc/OpenHarness) by thu-nmrc (BSL 1.1).
This Claude Code adaptation is provided as-is.
