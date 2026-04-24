#!/usr/bin/env bash
# Initialize OpenHarness loop state file
# Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2]

set -euo pipefail

# Determine plugin root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
STATE_MANAGER="${PLUGIN_ROOT}/scripts/state-manager.py"

# ---- Argument parsing ----
TASK_NAME=""
EXECUTION_MODE="single"
VERIFY_INSTRUCTION=""
MAX_ITERATIONS=0
SKILLS=""

if [[ $# -lt 1 ]]; then
  echo "Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2]" >&2
  exit 1
fi

TASK_NAME="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      if [[ $# -lt 2 ]]; then
        echo "Error: --mode requires an argument (single|dual)" >&2
        exit 1
      fi
      EXECUTION_MODE="$2"
      if [[ "$EXECUTION_MODE" != "single" && "$EXECUTION_MODE" != "dual" ]]; then
        echo "Error: --mode must be 'single' or 'dual', got: $EXECUTION_MODE" >&2
        exit 1
      fi
      shift 2
      ;;
    --verify)
      if [[ $# -lt 2 ]]; then
        echo "Error: --verify requires an argument (natural language instruction)" >&2
        exit 1
      fi
      VERIFY_INSTRUCTION="$2"
      shift 2
      ;;
    --max-iterations)
      if [[ $# -lt 2 ]]; then
        echo "Error: --max-iterations requires an argument (number)" >&2
        exit 1
      fi
      MAX_ITERATIONS="$2"
      shift 2
      ;;
    --skills)
      if [[ $# -lt 2 ]]; then
        echo "Error: --skills requires an argument (comma-separated skill names)" >&2
        exit 1
      fi
      SKILLS="$2"
      shift 2
      ;;
    *)
      echo "Warning: Unknown argument: $1" >&2
      shift
      ;;
  esac
done

# ---- Initialize state file ----
echo "Initializing OpenHarness loop state..."

INIT_ARGS=("$TASK_NAME" --mode "$EXECUTION_MODE")
if [[ -n "$VERIFY_INSTRUCTION" ]]; then
  INIT_ARGS+=(--verify "$VERIFY_INSTRUCTION")
fi
if [[ -n "$SKILLS" ]]; then
  INIT_ARGS+=(--skills "$SKILLS")
fi
INIT_ARGS+=(--max-iterations "$MAX_ITERATIONS")

python3 "$STATE_MANAGER" init "${INIT_ARGS[@]}"

# ---- Ensure harness directory structure ----
mkdir -p .claude/harness/logs

# ---- Verify state file was created ----
STATE_FILE=".claude/harness-state.json"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "Error: State file was not created at $STATE_FILE" >&2
  exit 1
fi

# ---- Print success ----
echo ""
echo "=== OpenHarness Loop Initialized ==="
echo "  Task Name:         $TASK_NAME"
echo "  Execution Mode:    $EXECUTION_MODE"
echo "  Verify Instruction: ${VERIFY_INSTRUCTION:-(none)}"
echo "  Skills:            ${SKILLS:-(none)}"
echo "  Max Iterations:     ${MAX_ITERATIONS:-0 (infinite)}"
echo "  State File:         $(pwd)/$STATE_FILE"
echo ""
echo "Ready to begin development loop."
