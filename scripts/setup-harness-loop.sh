#!/usr/bin/env bash
# Initialize OpenHarness loop state file
# Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]

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
LOOP_MODE="in-session"
CYCLE_STEPS=""
MIN_CYCLES=""
MAX_CYCLES=""
FORCE=""
TEMPLATE=""

if [[ $# -lt 1 ]]; then
  echo "Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]" >&2
  exit 1
fi

TASK_NAME="$1"
shift

# Reject flag-like task names (e.g. "--mission")
if [[ "$TASK_NAME" == -* ]]; then
  echo "Error: task_name must not start with '-', got '$TASK_NAME'. Provide the task name as the first positional argument." >&2
  echo "Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]" >&2
  exit 1
fi

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
    --loop-mode)
      if [[ $# -lt 2 ]]; then
        echo "Error: --loop-mode requires an argument (in-session|clean)" >&2
        exit 1
      fi
      LOOP_MODE="$2"
      if [[ "$LOOP_MODE" != "in-session" && "$LOOP_MODE" != "clean" ]]; then
        echo "Error: --loop-mode must be 'in-session' or 'clean', got: $LOOP_MODE" >&2
        exit 1
      fi
      shift 2
      ;;
    --cycle-steps)
      if [[ $# -lt 2 ]]; then
        echo "Error: --cycle-steps requires an argument (e.g., 1,3)" >&2
        exit 1
      fi
      CYCLE_STEPS="$2"
      shift 2
      ;;
    --min-cycles)
      if [[ $# -lt 2 ]]; then
        echo "Error: --min-cycles requires an argument (number)" >&2
        exit 1
      fi
      MIN_CYCLES="$2"
      shift 2
      ;;
    --max-cycles)
      if [[ $# -lt 2 ]]; then
        echo "Error: --max-cycles requires an argument (number)" >&2
        exit 1
      fi
      MAX_CYCLES="$2"
      shift 2
      ;;
    --force)
      FORCE="--force"
      shift
      ;;
    --template)
      if [[ $# -lt 2 ]]; then
        echo "Error: --template requires an argument (template name without .json extension)" >&2
        exit 1
      fi
      TEMPLATE="$2"
      shift 2
      ;;
    *)
      echo "Error: Unknown argument: $1" >&2
      echo "Usage: setup-harness-loop.sh <task-name> [--mode single|dual] [--verify INSTRUCTION] [--max-iterations N] [--skills SKILL1,SKILL2] [--loop-mode in-session|clean] [--template NAME] [--force]" >&2
      exit 1
      ;;
  esac
done

# ---- Initialize state file ----
echo "Initializing OpenHarness loop state..."

# Auto-detect existing workspace and add --force if needed.
# This prevents "Active workspace exists" errors when re-running
# harness-dev on an already-initialized workspace (the common case).
if [[ -z "$FORCE" && -f ".claude/harness-state.json" ]]; then
  FORCE="--force"
fi

# ---- Template processing ----
if [[ -n "$TEMPLATE" ]]; then
  TEMPLATE_FILE="${PLUGIN_ROOT}/templates/workflows/${TEMPLATE}.json"
  if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo "Error: Template not found: $TEMPLATE_FILE" >&2
    echo "Available templates:" >&2
    ls "${PLUGIN_ROOT}/templates/workflows/"*.json 2>/dev/null | xargs -n1 basename | sed 's/\.json$//' >&2
    exit 1
  fi

  # Extract cycle config from template if not already set by explicit flags
  if [[ -z "$CYCLE_STEPS" ]]; then
    CYCLE_STEPS_FROM_TEMPLATE=$(python3 -c "
import json
t = json.load(open('$TEMPLATE_FILE'))
cycle = t.get('cycle', {})
if cycle.get('enabled') and cycle.get('steps'):
    print(f\"{cycle['steps'][0]},{cycle['steps'][1]}\")
" 2>/dev/null || true)
    if [[ -n "$CYCLE_STEPS_FROM_TEMPLATE" ]]; then
      CYCLE_STEPS="$CYCLE_STEPS_FROM_TEMPLATE"
    fi
  fi

  if [[ -z "$MIN_CYCLES" ]]; then
    MIN_CYCLES=$(python3 -c "import json; print(json.load(open('$TEMPLATE_FILE')).get('cycle',{}).get('min_cycles',0))" 2>/dev/null || echo "0")
  fi

  if [[ -z "$MAX_CYCLES" ]]; then
    MAX_CYCLES=$(python3 -c "import json; print(json.load(open('$TEMPLATE_FILE')).get('cycle',{}).get('max_cycles',0))" 2>/dev/null || echo "0")
  fi
fi

INIT_ARGS=("$TASK_NAME" --mode "$EXECUTION_MODE")
if [[ -n "$VERIFY_INSTRUCTION" ]]; then
  INIT_ARGS+=(--verify "$VERIFY_INSTRUCTION")
fi
if [[ -n "$SKILLS" ]]; then
  INIT_ARGS+=(--skills "$SKILLS")
fi
INIT_ARGS+=(--max-iterations "$MAX_ITERATIONS")
if [[ -n "$LOOP_MODE" ]]; then
  INIT_ARGS+=(--loop-mode "$LOOP_MODE")
fi
if [[ -n "$CYCLE_STEPS" ]]; then
  INIT_ARGS+=(--cycle-steps "$CYCLE_STEPS")
fi
if [[ -n "$MIN_CYCLES" ]]; then
  INIT_ARGS+=(--min-cycles "$MIN_CYCLES")
fi
if [[ -n "$MAX_CYCLES" ]]; then
  INIT_ARGS+=(--max-cycles "$MAX_CYCLES")
fi
if [[ -n "$FORCE" ]]; then
  INIT_ARGS+=("$FORCE")
fi

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
echo "  Loop Mode:         $LOOP_MODE"
echo "  Verify Instruction: ${VERIFY_INSTRUCTION:-(none)}"
echo "  Skills:            ${SKILLS:-(none)}"
echo "  Max Iterations:     ${MAX_ITERATIONS:-0 (infinite)}"
echo "  Template:           ${TEMPLATE:-(auto-detect)}"
echo "  State File:         $(pwd)/$STATE_FILE"
echo ""
echo "Ready to begin development loop."
