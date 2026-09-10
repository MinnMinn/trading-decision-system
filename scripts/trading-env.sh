#!/usr/bin/env bash
# Trading environment loader (bash). `source` this file; it exports the variables of the ACTIVE environment.
#
#   active environment = docs/architecture/automation-config.json -> execution.environment ("demo" | "real")
#   file               = config/env.<environment>      (template: config/env.example)
#   override           = TRADING_ENV=demo|real in the caller's environment wins over the config file
#
# Secret values of the form  keychain:<service>[@<account>]  are resolved through scripts/get-secret.sh
# (macOS Keychain) at load time. Values are exported to the environment only -- never printed, never argv.
# A required secret that is empty or still "__FILL_ME__" makes this loader fail (exit 2) BEFORE any caller
# can place an order. That is a correctness check ("environment incomplete"), not a policy block.
#
# Hard rules enforced here regardless of environment: PILOT_RISK_PCT is clamped to <= 0.01 (max 1% per trade).
set -u
_TE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_TE_ROOT="$(cd "$_TE_DIR/.." && pwd)"
_TE_CFG="$_TE_ROOT/docs/architecture/automation-config.json"

trading_env_name() {
  if [ -n "${TRADING_ENV:-}" ]; then echo "$TRADING_ENV"; return; fi
  if [ -f "$_TE_CFG" ]; then
    python3 - "$_TE_CFG" <<'PY'
import json, sys
try:
    c = json.load(open(sys.argv[1], encoding="utf-8"))
    print((c.get("execution") or {}).get("environment") or "demo")
except Exception:
    print("demo")
PY
  else
    echo "demo"
  fi
}

_te_resolve() {   # $1 = raw value -> prints resolved value (Keychain-backed if keychain:...)
  case "$1" in
    keychain:*)
      local ref="${1#keychain:}" svc acct
      svc="${ref%@*}"; acct="${ref#*@}"; [ "$acct" = "$ref" ] && acct=""
      if [ -n "$acct" ]; then "$_TE_DIR/get-secret.sh" "$svc" "$acct"; else "$_TE_DIR/get-secret.sh" "$svc"; fi ;;
    *) printf '%s' "$1" ;;
  esac
}

TRADING_ENV_ACTIVE="$(trading_env_name)"
TRADING_ENV_FILE="$_TE_ROOT/config/env.$TRADING_ENV_ACTIVE"
export TRADING_ENV_ACTIVE TRADING_ENV_FILE
if [ ! -f "$TRADING_ENV_FILE" ]; then
  echo "trading-env: environment '$TRADING_ENV_ACTIVE' has no file at config/env.$TRADING_ENV_ACTIVE (copy config/env.example)" >&2
  return 2 2>/dev/null || exit 2
fi

# parse KEY=VALUE lines (no `source`: values are never evaluated as shell, and no secret enters a command line)
while IFS= read -r _line || [ -n "$_line" ]; do
  case "$_line" in ''|'#'*) continue ;; esac
  _key="${_line%%=*}"; _val="${_line#*=}"
  _key="${_key// /}"
  case "$_key" in *[!A-Z0-9_]*|'') continue ;; esac
  _val="${_val#"${_val%%[![:space:]]*}"}"; _val="${_val%"${_val##*[![:space:]]}"}"   # trim
  case "$_key" in
    *_KEY|*_SECRET_KEY|*_PASSWORD)
      # a keychain: reference that cannot be resolved becomes EMPTY, so trading_env_require fails loudly
      # instead of a connector signing requests with the literal string "keychain:..."
      _val="$(_te_resolve "$_val" 2>/dev/null)" || _val="" ;;
  esac
  export "$_key=$_val"
done < "$TRADING_ENV_FILE"
unset _line _key _val

# required for any Binance execution path
for _req in BINANCE_SPOT_BASE_URL BINANCE_FUTURES_BASE_URL; do
  if [ -z "${!_req:-}" ]; then echo "trading-env: $_req missing in config/env.$TRADING_ENV_ACTIVE" >&2; return 2 2>/dev/null || exit 2; fi
done
trading_env_require() {   # trading_env_require BINANCE_SPOT_API_KEY ...   -> exit 2 if any is empty/__FILL_ME__
  local v
  for v in "$@"; do
    if [ -z "${!v:-}" ] || [ "${!v}" = "__FILL_ME__" ]; then
      echo "trading-env: environment '$TRADING_ENV_ACTIVE' incomplete -- $v is not set in config/env.$TRADING_ENV_ACTIVE" >&2
      return 2
    fi
  done
}
# risk ceiling (hard rule: max 1% per trade)
PILOT_RISK_PCT="${PILOT_RISK_PCT:-0.005}"
PILOT_RISK_PCT="$(python3 -c "import sys; v=float(sys.argv[1]); print(min(v, 0.01))" "$PILOT_RISK_PCT")"
export PILOT_RISK_PCT
unset _req
