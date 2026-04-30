#!/usr/bin/env bash
# OpenHarness Stop Hook — thin wrapper
# Delegates all logic to Python for JSON-safe processing

set -euo pipefail

# Read hook input from stdin, pass to Python
exec python3 "${CLAUDE_PLUGIN_ROOT}/scripts/stop-hook.py"
