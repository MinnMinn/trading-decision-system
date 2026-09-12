#!/usr/bin/env bash
# SessionStart hook payload (.claude/settings.json). Prints the hard safety rules with the instrument lists
# read LIVE from docs/architecture/instruments.json, so the reminder can never drift from the enforced
# allowlist -- which is the whole point (SYSTEM-DESIGN.md §1).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/instruments.sh"

ANALYSIS="$(instruments_analysis | tr ' ' '/')"
EXEC_CRYPTO="$(instruments_execution crypto | tr ' ' '/')"

TEXT="TRADING SYSTEM HARD SAFETY RULES: capital preservation first; NEVER trade Forex; \
analysis allowlist = ${ANALYSIS} and nothing else; \
EXECUTION (pilot, /execute) is narrower still -- crypto orders only on ${EXEC_CRYPTO}; \
max 1% risk per trade. The allowlist has ONE source: docs/architecture/instruments.json (never hard-code a \
symbol list; run scripts/sync-instruments.py --write after editing it). See \
docs/architecture/SYSTEM-DESIGN.md for the full architecture before making any design changes."

TEXT="$TEXT" python3 -c 'import json,os; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":os.environ["TEXT"]}}))'
