#!/usr/bin/env bash
# Stage-2 DEMO connector -- Binance USDT-M FUTURES TESTNET only (https://testnet.binancefuture.com).
# Design: docs/architecture/SYSTEM-DESIGN.md §9.x (Stage-2 demo pilot) and §12 item 4.
# Credentials: macOS Keychain via scripts/get-secret.sh, account "binance-futures-testnet":
#   security add-generic-password -a binance-futures-testnet -s trading-system-binance-futures-testnet-api-key    -w '<KEY>'
#   security add-generic-password -a binance-futures-testnet -s trading-system-binance-futures-testnet-secret-key -w '<SECRET>'
# (keys come from https://testnet.binancefuture.com -> API Key; never paste them into chat). Never in argv, never printed.
#
# HARD SCOPE LIMITS (enforced below, do not silently exceed):
#   - FUTURES TESTNET only (fake funds, real matching engine). Never fapi.binance.com.
#   - Symbols: BTCUSDT / ETHUSDT / SOLUSDT only. ISOLATED margin. Leverage <= MAX_LEVERAGE.
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
#   stop-market <SYM> <SIDE> <STOP_PRICE>                       # closePosition=true, workingType=MARK_PRICE
#   take-profit-market <SYM> <SIDE> <PRICE>                     # closePosition=true, workingType=MARK_PRICE
#   close-position <SYM>                                        # MARKET reduceOnly for the whole positionAmt
#   order-status <SYM> <ORDER_ID> | cancel-order <SYM> <ORDER_ID> | cancel-all <SYM>
# SIDE for the protective orders: SELL protects a LONG, BUY protects a SHORT.
# On any Binance rejection the error JSON is printed to stderr and the script exits nonzero.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://testnet.binancefuture.com"
KEYCHAIN_ACCOUNT="binance-futures-testnet"
MAX_LEVERAGE=3
ALLOWED_SYMBOLS="BTCUSDT ETHUSDT SOLUSDT"

_check_symbol() {
  case " $ALLOWED_SYMBOLS " in *" $1 "*) ;; *) echo "Refused: symbol $1 not in allowlist ($ALLOWED_SYMBOLS)" >&2; exit 2 ;; esac
}
API_KEY=""; SECRET_KEY=""
_need_keys() {
  [ -n "$API_KEY" ] && return 0
  API_KEY="$("$SCRIPT_DIR/get-secret.sh" trading-system-binance-futures-testnet-api-key "$KEYCHAIN_ACCOUNT" 2>/dev/null)" || { echo "No futures-testnet API key in Keychain (account $KEYCHAIN_ACCOUNT). See header of this script." >&2; exit 3; }
  SECRET_KEY="$("$SCRIPT_DIR/get-secret.sh" trading-system-binance-futures-testnet-secret-key "$KEYCHAIN_ACCOUNT" 2>/dev/null)" || { echo "No futures-testnet secret key in Keychain." >&2; exit 3; }
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
print(v.normalize() if v == v.to_integral() else v)' "$1" "$2"
}

cmd="${1:-}"
case "$cmd" in
  check)
    _public_get "${BASE_URL}/fapi/v1/ping" >/dev/null && echo "ping: ok ($BASE_URL)"
    _public_get "${BASE_URL}/fapi/v1/time" | python3 -c 'import json,sys,time; t=json.load(sys.stdin)["serverTime"]; print("server time:", t, "| skew ms:", int(time.time()*1000)-t)'
    for n in trading-system-binance-futures-testnet-api-key trading-system-binance-futures-testnet-secret-key; do
      if security find-generic-password -a "$KEYCHAIN_ACCOUNT" -s "$n" >/dev/null 2>&1; then echo "keychain $n: present"; else echo "keychain $n: ABSENT"; fi
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
  open-orders) if [ -n "${2:-}" ]; then _check_symbol "$2"; _signed GET /fapi/v1/openOrders "symbol=$2" | _pretty; else _signed GET /fapi/v1/openOrders "" | _pretty; fi ;;
  user-trades) _check_symbol "${2:?}"; _signed GET /fapi/v1/userTrades "symbol=$2&limit=${3:-50}" | _pretty ;;
  income) _check_symbol "${2:?}"; _signed GET /fapi/v1/income "symbol=$2&limit=${3:-50}" | _pretty ;;
  set-margin-type) _check_symbol "${2:?}"; [ "${3:?}" = "ISOLATED" ] || { echo "Refused: only ISOLATED margin is allowed in the demo" >&2; exit 2; }
    _signed POST /fapi/v1/marginType "symbol=$2&marginType=ISOLATED" | _pretty ;;
  set-leverage) _check_symbol "${2:?}"; lev="${3:?}"; [ "$lev" -ge 1 ] && [ "$lev" -le "$MAX_LEVERAGE" ] || { echo "Refused: leverage $lev outside 1..$MAX_LEVERAGE" >&2; exit 2; }
    _signed POST /fapi/v1/leverage "symbol=$2&leverage=$lev" | _pretty ;;
  open-long) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=BUY&type=MARKET&quantity=${3:?}&newOrderRespType=RESULT" | _pretty ;;
  open-short) _check_symbol "${2:?}"; _signed POST /fapi/v1/order "symbol=$2&side=SELL&type=MARKET&quantity=${3:?}&newOrderRespType=RESULT" | _pretty ;;
  stop-market) _check_symbol "${2:?}"; side="${3:?SELL|BUY}"; _signed POST /fapi/v1/order "symbol=$2&side=$side&type=STOP_MARKET&stopPrice=${4:?}&closePosition=true&workingType=MARK_PRICE&priceProtect=TRUE" | _pretty ;;
  take-profit-market) _check_symbol "${2:?}"; side="${3:?SELL|BUY}"; _signed POST /fapi/v1/order "symbol=$2&side=$side&type=TAKE_PROFIT_MARKET&stopPrice=${4:?}&closePosition=true&workingType=MARK_PRICE&priceProtect=TRUE" | _pretty ;;
  close-position) _check_symbol "${2:?}"
    amt="$(_signed GET /fapi/v2/positionRisk "symbol=$2" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(sum(float(p["positionAmt"]) for p in d))')"
    if python3 -c "import sys; sys.exit(0 if abs(float('$amt'))>0 else 1)"; then
      if python3 -c "import sys; sys.exit(0 if float('$amt')>0 else 1)"; then side=SELL; qty="$amt"; else side=BUY; qty="${amt#-}"; fi
      _signed POST /fapi/v1/order "symbol=$2&side=$side&type=MARKET&quantity=$qty&reduceOnly=true&newOrderRespType=RESULT" | _pretty
    else echo '{"note":"no open position"}'; fi ;;
  order-status) _check_symbol "${2:?}"; _signed GET /fapi/v1/order "symbol=$2&orderId=${3:?}" | _pretty ;;
  cancel-order) _check_symbol "${2:?}"; _signed DELETE /fapi/v1/order "symbol=$2&orderId=${3:?}" | _pretty ;;
  cancel-all) _check_symbol "${2:?}"; _signed DELETE /fapi/v1/allOpenOrders "symbol=$2" | _pretty ;;
  *) echo "Usage: $0 {check|exchange-info|filters|price|mark-price|round-qty|round-price|account|balance|position-risk|open-orders|user-trades|income|set-margin-type|set-leverage|open-long|open-short|stop-market|take-profit-market|close-position|order-status|cancel-order|cancel-all} ..." >&2; exit 1 ;;
esac
