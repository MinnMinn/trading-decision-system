#!/usr/bin/env bash
# Bash reader for docs/architecture/instruments.json -- the single source of truth for the instrument
# allowlist (SYSTEM-DESIGN.md §1). Source it; never hard-code a symbol list in a shell script.
#   source "$SCRIPT_DIR/instruments.sh"
#   instruments_analysis crypto    # space-separated, e.g. "BTCUSDT ETHUSDT ..."
#   instruments_execution crypto
# Requires jq (already a dependency of the Binance connectors). `tr -d '\r'`: jq.exe on Windows ends lines with
# CRLF, and a symbol carrying a trailing CR never matches the allowlist (every order refused).
_INSTRUMENTS_JSON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/docs/architecture/instruments.json"

_instruments_get() { # <analysis|execution> [market]
  local kind=$1 market=${2:-}
  if [ -n "$market" ]; then jq -r --arg k "$kind" --arg m "$market" '.[$k][$m][]' "$_INSTRUMENTS_JSON" | tr -d '\r' | tr '\n' ' ' | sed 's/ $//'
  else jq -r --arg k "$kind" '.[$k] | to_entries[].value[]' "$_INSTRUMENTS_JSON" | tr -d '\r' | tr '\n' ' ' | sed 's/ $//'; fi
}
instruments_analysis()  { _instruments_get analysis  "${1:-}"; }
instruments_execution() { _instruments_get execution "${1:-}"; }
