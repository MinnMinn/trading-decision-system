#!/usr/bin/env bash
# Binance USDT-M FUTURES connector. (File name kept for compatibility -- it is NOT testnet-only any more.)
# Design: docs/architecture/SYSTEM-DESIGN.md §9.x (pilot) and §12 item 4.
#
# ENVIRONMENT: endpoint and credentials come from scripts/trading-env.sh, i.e. from config/env.<environment>
# where <environment> = docs/architecture/automation-config.json -> execution.environment ("demo" | "real").
#   demo -> https://testnet.binancefuture.com (fake funds)   real -> https://fapi.binance.com (REAL MONEY)
# Secrets are resolved from macOS Keychain (keychain:... references in the env file) or read from the env file;
# never in argv, never printed. An incomplete environment (placeholder keys) exits 2 before any request is signed.
#
# HARD SCOPE LIMITS (enforced below, do not silently exceed):
#   - Symbols: the EXECUTION list in docs/architecture/instruments.json (a subset of the analysis
#     allowlist -- a watch-only symbol can never be ordered here). ISOLATED margin. Leverage <= MAX_LEVERAGE.
#   - Every order here is a REAL testnet order. This script does not decide to trade; the caller
#     (demo-pilot.py --market futures, or /execute after a human confirmation) does.
#
# Usage:
#   check                                  # ping + server time + whether Keychain keys exist (never prints them)
#   exchange-info <SYM> | filters <SYM> | price <SYM> | mark-price <SYM>
#   round-qty <SYM> <QTY> | round-price <SYM> <PRICE>          # floor to LOT_SIZE / PRICE_FILTER
#   account | balance | position-risk [SYM] | open-orders [SYM] | user-trades <SYM> [LIMIT] | income <SYM> [LIMIT]
#   set-margin-type <SYM> ISOLATED | set-leverage <SYM> <N>     # N <= MAX_LEVERAGE
#   open-long <SYM> <QTY> | open-short <SYM> <QTY>              # MARKET, newOrderRespType=RESULT
#   open-long-limit <SYM> <QTY> <PRICE> [CLIENT_ID] | open-short-limit ...   # LIMIT, timeInForce=GTX (post-only: -5022 instead of taking); CLIENT_ID = idempotency key
#   order-by-client-id <SYM> <CLIENT_ID>                        # resolve a timed-out POST without re-sending it
#   stop-market <SYM> <SIDE> <STOP_PRICE>                       # closePosition=true, workingType=MARK_PRICE
#   take-profit-market <SYM> <SIDE> <PRICE>                     # closePosition=true, workingType=MARK_PRICE
#     ^ both go to the Algo Order API (POST /fapi/v1/algoOrder, algoType=CONDITIONAL) -- see the block at the
#       subcommand. Their ids are algoIds; order-status/cancel-order/cancel-all/open-orders are algo-aware and
#       alias algoId->orderId and algoStatus->status so callers keep seeing the classic order shape.
#   close-position <SYM>                                        # MARKET reduceOnly for the whole positionAmt
#   order-status <SYM> <ORDER_ID> | cancel-order <SYM> <ORDER_ID> | cancel-all <SYM>
# SIDE for the protective orders: SELL protects a LONG, BUY protects a SHORT.
# On any Binance rejection the error JSON is printed to stderr and the script exits nonzero.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=trading-env.sh
source "$SCRIPT_DIR/trading-env.sh" || exit 2
BASE_URL="$BINANCE_FUTURES_BASE_URL"
MAX_LEVERAGE=3
# shellcheck source=instruments.sh
source "$SCRIPT_DIR/instruments.sh" || exit 2
# EXECUTION list from docs/architecture/instruments.json -- the orderable subset, never the analysis allowlist.
ALLOWED_SYMBOLS="$(instruments_execution crypto)"

_check_symbol() {
  case " $ALLOWED_SYMBOLS " in *" $1 "*) ;; *) echo "Refused: symbol $1 not in allowlist ($ALLOWED_SYMBOLS)" >&2; exit 2 ;; esac
}
API_KEY=""; SECRET_KEY=""
_need_keys() {
  [ -n "$API_KEY" ] && return 0
  trading_env_require BINANCE_FUTURES_API_KEY BINANCE_FUTURES_SECRET_KEY || exit 2
  API_KEY="$BINANCE_FUTURES_API_KEY"
  SECRET_KEY="$BINANCE_FUTURES_SECRET_KEY"
}
_sign() {
  BINANCE_SECRET="$SECRET_KEY" python3 -c '
import hmac, hashlib, os, sys
print(hmac.new(os.environ["BINANCE_SECRET"].encode(), sys.argv[1].encode(), hashlib.sha256).hexdigest())' "$1"
}
_timestamp_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }
_http() {  # method url  (API key via curl config on stdin, never argv)
  local method="$1" url="$2" body
  if body="$(printf 'header = "X-MBX-APIKEY: %s"\n' "$API_KEY" | curl -sS --fail-with-body -m 15 -K - -X "$method" "$url")"; then
    printf '%s' "$body"
  else
    echo "Binance request failed (${method} ${url%%\?*}): ${body:-<no response body>}" >&2; return 1
  fi
}
_public_get() {
  local url="$1" body
  if body="$(curl -sS --fail-with-body -m 10 "$url")"; then printf '%s' "$body"; else echo "Binance request failed (GET ${url%%\?*}): ${body:-<no body>}" >&2; return 1; fi
}
_pretty() { local s; s="$(cat)"; [ -z "$s" ] || printf '%s' "$s" | python3 -m json.tool; }
_signed() {  # method path query
  _need_keys
  local method="$1" path="$2" query="$3" ts full sig
  ts="$(_timestamp_ms)"
  if [ -n "$query" ]; then full="${query}&timestamp=${ts}&recvWindow=5000"; else full="timestamp=${ts}&recvWindow=5000"; fi
  sig="$(_sign "$full")"
  _http "$method" "${BASE_URL}${path}?${full}&signature=${sig}"
}
_algo_normalize() {  # stdin: /fapi/v1/algoOrder JSON (object or array) -> same JSON plus classic /fapi/v1/order aliases.
  # Conditional orders live in a SEPARATE namespace (algoId/algoStatus/triggerPrice/actualQty), so callers that
  # speak the classic shape (strategy-runner.py) would not understand them. We alias rather than replace.
  python3 -c '
import json, sys
_MAP = {"NEW": "NEW", "WORKING": "NEW", "FINISHED": "FILLED",
        "CANCELED": "CANCELED", "CANCELLED": "CANCELED", "EXPIRED": "EXPIRED", "REJECTED": "REJECTED"}
def norm(o):
    if not isinstance(o, dict) or "algoId" not in o:
        return o
    st = _MAP.get(str(o.get("algoStatus") or "").upper(), str(o.get("algoStatus") or ""))
    if st == "FILLED" and float(o.get("actualQty") or 0) <= 0:
        st = "EXPIRED"   # triggered but filled nothing (position was already gone) -- not a close
    o.setdefault("orderId", o["algoId"])
    o["status"]      = st
    o["type"]        = o.get("orderType") or o.get("type")
    o["origType"]    = o["type"]
    o["stopPrice"]   = o.get("triggerPrice") or "0"
    o["avgPrice"]    = o.get("actualPrice") or "0"
    o["executedQty"] = o.get("actualQty") or "0"
    o["origQty"]     = o.get("quantity") or "0"
    return o
d = json.load(sys.stdin)
json.dump([norm(x) for x in d] if isinstance(d, list) else norm(d), sys.stdout, indent=4)
print()'
}
_filter_value() {  # symbol filterType field
  _public_get "${BASE_URL}/fapi/v1/exchangeInfo" | python3 -c '
import json, sys
d = json.load(sys.stdin); sym, ft, field = sys.argv[1:4]
for s in d["symbols"]:
    if s["symbol"] == sym:
        for f in s["filters"]:
            if f["filterType"] == ft: print(f[field]); sys.exit(0)
sys.exit(1)' "$1" "$2" "$3"
}
_floor_to_step() {
  python3 -c '
from decimal import Decimal
import sys
raw, step = Decimal(sys.argv[1]), Decimal(sys.argv[2])
v = (raw // step) * step
print(format(v.normalize(), "f"))' "$1" "$2"   # format(..., "f"): never scientific notation (3.86E+4 was rejected by Binance, 2026-09-11)
}

cmd="${1:-}"
case "$cmd" in
  check)
    _public_get "${BASE_URL}/fapi/v1/ping" >/dev/null && echo "ping: ok ($BASE_URL)"
    _public_get "${BASE_URL}/fapi/v1/time" | python3 -c 'import json,sys,time; t=json.load(sys.stdin)["serverTime"]; print("server time:", t, "| skew ms:", int(time.time()*1000)-t)'
    echo "environment: ${TRADING_ENV_ACTIVE} (config/env.${TRADING_ENV_ACTIVE})"
    for n in BINANCE_FUTURES_API_KEY BINANCE_FUTURES_SECRET_KEY; do   # presence only -- values are never printed
      v="${!n:-}"; if [ -n "$v" ] && [ "$v" != "__FILL_ME__" ]; then echo "$n: present"; else echo "$n: ABSENT (empty, placeholder, or an unresolvable keychain: reference)"; fi
    done ;;
  exchange-info) _check_symbol "${2:?}"; _public_get "${BASE_URL}/fapi/v1/exchangeInfo" | python3 -c '
import json,sys; d=json.load(sys.stdin); print(json.dumps([s for s in d["symbols"] if s["symbol"]==sys.argv[1]][0], indent=1))' "$2" ;;
  filters) _check_symbol "${2:?}"; _public_get "${BASE_URL}/fapi/v1/exchangeInfo" | python3 -c '
import json,sys; d=json.load(sys.stdin)
for s in d["symbols"]:
    if s["symbol"]==sys.argv[1]:
        for f in s["filters"]:
            if f["filterType"] in ("LOT_SIZE","MARKET_LOT_SIZE","PRICE_FILTER","MIN_NOTIONAL"): print(f)' "$2" ;;
  price) _check_symbol "${2:?}"; _public_get "${BASE_URL}/fapi/v1/ticker/price?symbol=$2" | _pretty ;;
  mark-price) _check_symbol "${2:?}"; _public_get "${BASE_URL}/fapi/v1/premiumIndex?symbol=$2" | _pretty ;;
  round-qty) _check_symbol "${2:?}"; _floor_to_step "${3:?}" "$(_filter_value "$2" LOT_SIZE stepSize)" ;;
  round-price) _check_symbol "${2:?}"; _floor_to_step "${3:?}" "$(_filter_value "$2" PRICE_FILTER tickSize)" ;;
  account) _signed GET /fapi/v2/account "" | _pretty ;;
  balance) _signed GET /fapi/v2/balance "" | _pretty ;;
  position-risk) if [ -n "${2:-}" ]; then _check_symbol "$2"; _signed GET /fapi/v2/positionRisk "symbol=$2" | _pretty; else _signed GET /fapi/v2/positionRisk "" | _pretty; fi ;;
  # Conditional orders do NOT appear in /fapi/v1/openOrders -- they are only in /fapi/v1/openAlgoOrders
  # (verified 2026-09-13). Merge both so reconciliation sees a resting protective stop instead of concluding
  # the position is unprotected (or that the stop is a foreign order).
  open-orders) if [ -n "${2:-}" ]; then _check_symbol "$2"; q="symbol=$2"; else q=""; fi
    reg="$(_signed GET /fapi/v1/openOrders "$q")"; algo="$(_signed GET /fapi/v1/openAlgoOrders "$q" | _algo_normalize)"
    python3 -c '
import json,sys
print(json.dumps(json.loads(sys.argv[1]) + json.loads(sys.argv[2]), indent=4))' "$reg" "$algo" ;;
  user-trades) _check_symbol "${2:?}"; _signed GET /fapi/v1/userTrades "symbol=$2&limit=${3:-50}" | _pretty ;;
  income) _check_symbol "${2:?}"; _signed GET /fapi/v1/income "symbol=$2&limit=${3:-50}" | _pretty ;;
  set-margin-type) _check_symbol "${2:?}"; [ "${3:?}" = "ISOLATED" ] || { echo "Refused: only ISOLATED margin is allowed in the demo" >&2; exit 2; }
    _signed POST /fapi/v1/marginType "symbol=$2&marginType=ISOLATED" | _pretty ;;
  set-leverage) _check_symbol "${2:?}"; lev="${3:?}"; [ "$lev" -ge 1 ] && [ "$lev" -le "$MAX_LEVERAGE" ] || { echo "Refused: leverage $lev outside 1..$MAX_LEVERAGE" >&2; exit 2; }
    _signed POST /fapi/v1/leverage "symbol=$2&leverage=$lev" | _pretty ;;
  open-long) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=BUY&type=MARKET&quantity=${3:?}&newOrderRespType=RESULT" | _pretty ;;
  open-short) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=SELL&type=MARKET&quantity=${3:?}&newOrderRespType=RESULT" | _pretty ;;
  open-long-limit) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=BUY&type=LIMIT&timeInForce=GTX&quantity=${3:?}&price=${4:?}&newOrderRespType=RESULT${5:+&newClientOrderId=$5}" | _pretty ;;
  open-short-limit) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=SELL&type=LIMIT&timeInForce=GTX&quantity=${3:?}&price=${4:?}&newOrderRespType=RESULT${5:+&newClientOrderId=$5}" | _pretty ;;
  order-by-client-id) _check_symbol "${2:?}"; _signed GET /fapi/v1/order "symbol=$2&origClientOrderId=${3:?}" | _pretty ;;
  # ALGO ORDER API. API change: announced 2025-11-06, effective 2025-12-09 -- USDS-M futures migrated
  # conditional orders (STOP_MARKET / TAKE_PROFIT_MARKET / STOP / TAKE_PROFIT / TRAILING_STOP_MARKET) to the
  # Algo Service. POST /fapi/v1/order and POST /fapi/v1/batchOrders now reject those types with
  # -4120 STOP_ORDER_SWITCH_ALGO, "Order type not supported for this endpoint. Please use the Algo Order API
  # endpoints instead." They go to POST /fapi/v1/algoOrder with algoType=CONDITIONAL, and the trigger level is
  # named triggerPrice, NOT stopPrice. Everything else (side, closePosition, workingType, priceProtect, and
  # -2021 "would immediately trigger") behaves as before. There is no batch equivalent -- one call per order.
  # Docs: https://developers.binance.com/docs/derivatives/change-log
  #       https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/New-Algo-Order
  # Verified live on testnet 2026-09-13 (long and short, SL and TP, place/query/cancel/trigger).
  # Subcommand names and argument order are unchanged, so strategy-runner.py needs no change.
  stop-market) _check_symbol "${2:?}"; side="${3:?SELL|BUY}"; _signed POST /fapi/v1/algoOrder "symbol=$2&side=$side&algoType=CONDITIONAL&type=STOP_MARKET&triggerPrice=${4:?}&closePosition=true&workingType=MARK_PRICE&priceProtect=TRUE" | _algo_normalize ;;
  take-profit-market) _check_symbol "${2:?}"; side="${3:?SELL|BUY}"; _signed POST /fapi/v1/algoOrder "symbol=$2&side=$side&algoType=CONDITIONAL&type=TAKE_PROFIT_MARKET&triggerPrice=${4:?}&closePosition=true&workingType=MARK_PRICE&priceProtect=TRUE" | _algo_normalize ;;
  close-position) _check_symbol "${2:?}"
    amt="$(_signed GET /fapi/v2/positionRisk "symbol=$2" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(float(p["positionAmt"]) for p in d))')"
    if python3 -c "import sys; sys.exit(0 if abs(float('$amt'))>0 else 1)"; then
      if python3 -c "import sys; sys.exit(0 if float('$amt')>0 else 1)"; then side=SELL; qty="$amt"; else side=BUY; qty="${amt#-}"; fi
      _signed POST /fapi/v1/order "symbol=$2&side=$side&type=MARKET&quantity=$qty&reduceOnly=true&newOrderRespType=RESULT" | _pretty
    else echo '{"note":"no open position"}'; fi ;;
  # An id may be a classic orderId or an algoId (conditional order) -- try the classic endpoint first and fall
  # back to the algo namespace on -2013 "Order does not exist" (verified 2026-09-13).
  order-status) _check_symbol "${2:?}"; id="${3:?}"
    if out="$(_signed GET /fapi/v1/order "symbol=$2&orderId=$id" 2>/dev/null)"; then printf '%s' "$out" | _pretty
    else _signed GET /fapi/v1/algoOrder "symbol=$2&algoId=$id" | _algo_normalize; fi ;;
  cancel-order) _check_symbol "${2:?}"; id="${3:?}"
    if out="$(_signed DELETE /fapi/v1/order "symbol=$2&orderId=$id" 2>/dev/null)"; then printf '%s' "$out" | _pretty
    else _signed DELETE /fapi/v1/algoOrder "symbol=$2&algoId=$id" | _pretty; fi ;;
  # DELETE /fapi/v1/allOpenOrders does NOT touch conditional/algo orders (verified 2026-09-13: it returned
  # success while both protective orders stayed NEW in openAlgoOrders). Cancel those explicitly, or cancel-all
  # would silently leave a live stop resting after the position it protected is gone.
  cancel-all) _check_symbol "${2:?}"; _signed DELETE /fapi/v1/allOpenOrders "symbol=$2" | _pretty
    _signed DELETE /fapi/v1/algoOpenOrders "symbol=$2" | _pretty ;;
  *) echo "Usage: $0 {check|exchange-info|filters|price|mark-price|round-qty|round-price|account|balance|position-risk|open-orders|user-trades|income|set-margin-type|set-leverage|open-long|open-short|open-long-limit|open-short-limit|order-by-client-id|stop-market|take-profit-market|close-position|order-status|cancel-order|cancel-all} ..." >&2; exit 1 ;;
esac
