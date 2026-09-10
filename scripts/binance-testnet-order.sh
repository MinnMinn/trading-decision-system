#!/usr/bin/env bash
# Binance SPOT order-submission connector. (File name kept for compatibility -- it is NOT testnet-only any more.)
# Design: docs/architecture/SYSTEM-DESIGN.md section 9 (Stage 1 /execute) and section 9.x (pilot).
#
# ENVIRONMENT: endpoint and credentials come from scripts/trading-env.sh, i.e. from config/env.<environment>
# where <environment> = docs/architecture/automation-config.json -> execution.environment ("demo" | "real").
#   demo -> https://testnet.binance.vision (fake funds)      real -> https://api.binance.com (REAL MONEY)
# Secrets are resolved from macOS Keychain (keychain:... references) or read from the env file; they are never
# passed as CLI args (argv is visible to every process via `ps`) and never printed. An incomplete environment
# (placeholder keys) makes this script exit 2 before any request is signed.
#
# HARD SCOPE LIMITS (do not silently exceed these):
#   - SPOT only. No SHORT positions (spot has no margin here). Symbols are validated by the caller's allowlist.
#   - Every call here is a REAL order on whichever environment is active -- never a simulation.
#   - This script does not decide whether to trade. It only executes what it's told by /execute (after a human
#     confirmation) or by scripts/demo-pilot.py (rules-only pilot permitted by /automation).
#
# Usage:
#   binance-testnet-order.sh account
#   binance-testnet-order.sh filters <SYMBOL>
#   binance-testnet-order.sh round-qty <SYMBOL> <RAW_QUANTITY>        # floor to LOT_SIZE stepSize
#   binance-testnet-order.sh round-price <SYMBOL> <RAW_PRICE>         # floor to PRICE_FILTER tickSize
#   binance-testnet-order.sh market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>
#   binance-testnet-order.sh market-buy-qty <SYMBOL> <QUANTITY>
#   binance-testnet-order.sh market-sell-qty <SYMBOL> <QUANTITY>
#   binance-testnet-order.sh oco-sell <SYMBOL> <QUANTITY> <TAKE_PROFIT_PRICE> <STOP_PRICE> <STOP_LIMIT_PRICE>
#   binance-testnet-order.sh price <SYMBOL> | open-orders [SYMBOL] | my-trades <SYMBOL> [LIMIT] | cancel-order <SYMBOL> <ORDER_ID>
#   binance-testnet-order.sh order-status <SYMBOL> <ORDER_ID>
#   binance-testnet-order.sh cancel-oco <SYMBOL> <ORDER_LIST_ID>
#
# On any Binance rejection the error JSON (e.g. {"code":-1013,"msg":"Filter failure: LOT_SIZE"}) is
# printed to stderr and the script exits nonzero -- it never fails silently.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=trading-env.sh
source "$SCRIPT_DIR/trading-env.sh" || exit 2
trading_env_require BINANCE_SPOT_API_KEY BINANCE_SPOT_SECRET_KEY || exit 2
BASE_URL="$BINANCE_SPOT_BASE_URL"
API_KEY="$BINANCE_SPOT_API_KEY"
SECRET_KEY="$BINANCE_SPOT_SECRET_KEY"

_sign() {
  # $1 = query string (without signature). Prints the hex HMAC-SHA256 signature.
  # Secret is handed to python via the environment, not argv.
  BINANCE_SECRET="$SECRET_KEY" python3 -c '
import hmac, hashlib, os, sys
print(hmac.new(os.environ["BINANCE_SECRET"].encode(), sys.argv[1].encode(), hashlib.sha256).hexdigest())
' "$1"
}

_timestamp_ms() {
  python3 -c 'import time; print(int(time.time() * 1000))'
}

_http() {
  # $1 = HTTP method, $2 = full URL. API key goes in via a curl config file on stdin (not argv).
  # --fail-with-body: on HTTP >= 400 curl still returns the body, so Binance's error JSON is shown.
  local method="$1" url="$2" body
  if body="$(printf 'header = "X-MBX-APIKEY: %s"\n' "$API_KEY" | curl -sS --fail-with-body -m 15 -K - -X "$method" "$url")"; then
    printf '%s' "$body"
  else
    echo "Binance request failed (${method} ${url%%\?*}): ${body:-<no response body>}" >&2
    return 1
  fi
}

_public_get() {
  local url="$1" body
  if body="$(curl -sS --fail-with-body -m 10 "$url")"; then
    printf '%s' "$body"
  else
    echo "Binance request failed (GET ${url%%\?*}): ${body:-<no response body>}" >&2
    return 1
  fi
}

_pretty() {
  # Pretty-print JSON only if there is a body (a failed request already printed its error).
  local s; s="$(cat)"; [ -z "$s" ] || printf '%s' "$s" | python3 -m json.tool
}

_signed() {
  local method="$1" path="$2" query="$3"
  local ts; ts="$(_timestamp_ms)"
  local full_query
  if [ -n "$query" ]; then full_query="${query}&timestamp=${ts}&recvWindow=5000"; else full_query="timestamp=${ts}&recvWindow=5000"; fi
  local sig; sig="$(_sign "$full_query")"
  _http "$method" "${BASE_URL}${path}?${full_query}&signature=${sig}"
}

_filter_value() {
  # $1 = symbol, $2 = filterType, $3 = field. Prints the field from exchangeInfo.
  _public_get "${BASE_URL}/api/v3/exchangeInfo?symbol=$1" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for f in d["symbols"][0]["filters"]:
    if f["filterType"] == sys.argv[1]:
        print(f[sys.argv[2]])
' "$2" "$3"
}

_floor_to_step() {
  # $1 = raw value, $2 = step. Floors (never rounds up) to the step grid.
  python3 -c '
from decimal import Decimal, ROUND_DOWN
import sys
raw, step = Decimal(sys.argv[1]), Decimal(sys.argv[2])
floored = (raw // step) * step
print(floored.normalize() if floored == floored.to_integral() else floored)
' "$1" "$2"
}

cmd="${1:-}"
case "$cmd" in

  account)
    _signed GET "/api/v3/account" "" | _pretty
    ;;

  filters)
    symbol="${2:?Usage: filters <SYMBOL>}"
    _public_get "${BASE_URL}/api/v3/exchangeInfo?symbol=${symbol}" | python3 -c '
import json, sys
d = json.load(sys.stdin)
for f in d["symbols"][0]["filters"]:
    if f["filterType"] in ("LOT_SIZE", "MIN_NOTIONAL", "NOTIONAL", "PRICE_FILTER"):
        print(f)
'
    ;;

  round-qty)
    # RiskSkill's position_size is in base-asset units (e.g. BTC). Binance requires `quantity`
    # to sit exactly on LOT_SIZE's stepSize grid or the order is rejected. Floors, never rounds
    # up -- never risk more than RiskSkill approved.
    symbol="${2:?Usage: round-qty <SYMBOL> <RAW_QUANTITY>}"
    raw_qty="${3:?Usage: round-qty <SYMBOL> <RAW_QUANTITY>}"
    _floor_to_step "$raw_qty" "$(_filter_value "$symbol" LOT_SIZE stepSize)"
    ;;

  round-price)
    # OCO prices must sit on PRICE_FILTER's tickSize grid or the order is rejected.
    symbol="${2:?Usage: round-price <SYMBOL> <RAW_PRICE>}"
    raw_price="${3:?Usage: round-price <SYMBOL> <RAW_PRICE>}"
    _floor_to_step "$raw_price" "$(_filter_value "$symbol" PRICE_FILTER tickSize)"
    ;;

  market-buy)
    symbol="${2:?Usage: market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>}"
    quote_qty="${3:?Usage: market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>}"
    # quoteOrderQty lets Binance compute and LOT_SIZE-round the base quantity itself.
    _signed POST "/api/v3/order" "symbol=${symbol}&side=BUY&type=MARKET&quoteOrderQty=${quote_qty}" | _pretty
    ;;

  market-buy-qty)
    symbol="${2:?Usage: market-buy-qty <SYMBOL> <QUANTITY>}"
    quantity="${3:?Usage: market-buy-qty <SYMBOL> <QUANTITY>}"
    _signed POST "/api/v3/order" "symbol=${symbol}&side=BUY&type=MARKET&quantity=${quantity}" | _pretty
    ;;

  market-sell-qty)
    # Flatten an exact base-asset quantity at market -- manual cleanup or emergency exit.
    symbol="${2:?Usage: market-sell-qty <SYMBOL> <QUANTITY>}"
    quantity="${3:?Usage: market-sell-qty <SYMBOL> <QUANTITY>}"
    _signed POST "/api/v3/order" "symbol=${symbol}&side=SELL&type=MARKET&quantity=${quantity}" | _pretty
    ;;

  oco-sell)
    symbol="${2:?Usage: oco-sell <SYMBOL> <QUANTITY> <TAKE_PROFIT_PRICE> <STOP_PRICE> <STOP_LIMIT_PRICE>}"
    quantity="${3:?}"
    take_profit_price="${4:?}"
    stop_price="${5:?}"
    stop_limit_price="${6:?}"
    _signed POST "/api/v3/order/oco" \
      "symbol=${symbol}&side=SELL&quantity=${quantity}&price=${take_profit_price}&stopPrice=${stop_price}&stopLimitPrice=${stop_limit_price}&stopLimitTimeInForce=GTC" \
      | _pretty
    ;;

  price)
    symbol="${2:?Usage: price <SYMBOL>}"
    _public_get "${BASE_URL}/api/v3/ticker/price?symbol=${symbol}" | _pretty
    ;;

  open-orders)
    symbol="${2:-}"
    if [ -n "$symbol" ]; then _signed GET "/api/v3/openOrders" "symbol=${symbol}" | _pretty; else _signed GET "/api/v3/openOrders" "" | _pretty; fi
    ;;

  my-trades)
    # Fills for a symbol (read-only) -- the source of truth for realised P&L.
    symbol="${2:?Usage: my-trades <SYMBOL> [LIMIT]}"
    limit="${3:-50}"
    _signed GET "/api/v3/myTrades" "symbol=${symbol}&limit=${limit}" | _pretty
    ;;

  cancel-order)
    symbol="${2:?Usage: cancel-order <SYMBOL> <ORDER_ID>}"
    order_id="${3:?}"
    _signed DELETE "/api/v3/order" "symbol=${symbol}&orderId=${order_id}" | _pretty
    ;;

  order-status)
    symbol="${2:?Usage: order-status <SYMBOL> <ORDER_ID>}"
    order_id="${3:?}"
    _signed GET "/api/v3/order" "symbol=${symbol}&orderId=${order_id}" | _pretty
    ;;

  cancel-oco)
    symbol="${2:?Usage: cancel-oco <SYMBOL> <ORDER_LIST_ID>}"
    order_list_id="${3:?}"
    _signed DELETE "/api/v3/orderList" "symbol=${symbol}&orderListId=${order_list_id}" | _pretty
    ;;

  *)
    echo "Usage: $0 {account|filters|price|open-orders|my-trades|round-qty|round-price|market-buy|market-buy-qty|market-sell-qty|oco-sell|order-status|cancel-order|cancel-oco} ..." >&2
    exit 1
    ;;
esac
