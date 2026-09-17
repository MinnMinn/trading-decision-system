#!/usr/bin/env bash
# SessionStart hook payload (.claude/settings.json). Prints the hard safety rules with the instrument lists
# read LIVE from docs/architecture/instruments.json, so the reminder can never drift from the enforced
# allowlist -- which is the whole point (SYSTEM-DESIGN.md §1).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/scripts/instruments.sh"

ANALYSIS="$(instruments_analysis | tr ' ' '/')"
EXEC_CRYPTO="$(instruments_execution crypto | tr ' ' '/')"

# The risk ceiling is read LIVE through its one validated reader, for the same reason the instrument lists are:
# this hook announced "max 3% risk per trade" to every session while risk-config.json, risk-skill and risk-agent
# all said 1 %. A reminder that carries its own copy of a number is a reminder that can be wrong.
# One call, formatted in python: `set -euo pipefail` is on, so a second substitution doing shell-side float
# maths on an empty value aborts the whole hook and the session then starts with NO safety context at all --
# silent, and worse than a stated failure. `|| true` plus an explicit if keeps the refusal branch reachable.
RISK_LINE="$(python3 -c 'import importlib.util, sys
spec = importlib.util.spec_from_file_location("trading_env", sys.argv[1])
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
print(f"max {mod.MAX_RISK_PCT * 100:g}% risk per trade")' "$ROOT/scripts/trading_env.py" 2>/dev/null || true)"
if [ -z "$RISK_LINE" ]; then
  RISK_LINE="the per-trade risk ceiling is UNREADABLE (docs/architecture/risk-config.json max_risk_pct) -- every order path refuses until it is fixed"
fi

TEXT="TRADING SYSTEM HARD SAFETY RULES: capital preservation first; \
analysis allowlist = ${ANALYSIS} and nothing else; \
EXECUTION (pilot, /execute) is narrower still -- crypto orders only on ${EXEC_CRYPTO}; \
${RISK_LINE}. The allowlist has ONE source: docs/architecture/instruments.json (never hard-code a \
symbol list; run scripts/sync-instruments.py --write after editing it); the risk ceiling has ONE source: \
docs/architecture/risk-config.json max_risk_pct, read through trading_env.MAX_RISK_PCT. See \
docs/architecture/SYSTEM-DESIGN.md for the full architecture before making any design changes."

TEXT="$TEXT" python3 -c 'import json,os; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":os.environ["TEXT"]}}))'
