#!/usr/bin/env bash
# Stage 1 order-submission connector -- Binance SPOT TESTNET only.
# Design: docs/architecture/SYSTEM-DESIGN.md section 9 (Stage 1: one-tap human-approved execution).
# Credentials: macOS Keychain via scripts/get-secret.sh -- never passed as CLI args, never printed.
#
# HARD SCOPE LIMITS (do not silently exceed these):
#   - Binance SPOT TESTNET only. Not mainnet. Not futures. No SHORT positions (spot has no margin here).
#   - Every call here is a REAL testnet order (fake funds, real order-matching engine) -- not a simulation.
#   - This script does not decide whether to trade. It only executes what it's told, after the calling
#     command (/execute) has already gotten explicit human confirmation. Never call this unattended.
#
# Usage:
#   binance-testnet-order.sh account
#   binance-testnet-order.sh filters <SYMBOL>
#   binance-testnet-order.sh market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>
#   binance-testnet-order.sh oco-sell <SYMBOL> <QUANTITY> <TAKE_PROFIT_PRICE> <STOP_PRICE> <STOP_LIMIT_PRICE>
#   binance-testnet-order.sh order-status <SYMBOL> <ORDER_ID>
#   binance-testnet-order.sh cancel-oco <SYMBOL> <ORDER_LIST_ID>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_URL="https://testnet.binance.vision"

API_KEY="$("$SCRIPT_DIR/get-secret.sh" trading-system-binance-testnet-api-key)"
SECRET_KEY="$("$SCRIPT_DIR/get-secret.sh" trading-system-binance-testnet-secret-key)"

_sign() {
  # $1 = query string (without signature). Prints the hex HMAC-SHA256 signature.
  printf '%s' "$1" | openssl dgst -sha256 -hmac "$SECRET_KEY" | sed 's/^.* //'
}

_timestamp_ms() {
  echo $(( $(date +%s%N) / 1000000 ))
}

_signed_get() {
  local path="$1" query="$2"
  local ts; ts="$(_timestamp_ms)"
  local full_query="${query}&timestamp=${ts}&recvWindow=5000"
  local sig; sig="$(_sign "$full_query")"
  curl -sf -m 15 -H "X-MBX-APIKEY: $API_KEY" "${BASE_URL}${path}?${full_query}&signature=${sig}"
}

_signed_post() {
  local path="$1" query="$2"
  local ts; ts="$(_timestamp_ms)"
  local full_query="${query}&timestamp=${ts}&recvWindow=5000"
  local sig; sig="$(_sign "$full_query")"
  curl -sf -m 15 -X POST -H "X-MBX-APIKEY: $API_KEY" "${BASE_URL}${path}?${full_query}&signature=${sig}"
}

_signed_delete() {
  local path="$1" query="$2"
  local ts; ts="$(_timestamp_ms)"
  local full_query="${query}&timestamp=${ts}&recvWindow=5000"
  local sig; sig="$(_sign "$full_query")"
  curl -sf -m 15 -X DELETE -H "X-MBX-APIKEY: $API_KEY" "${BASE_URL}${path}?${full_query}&signature=${sig}"
}

cmd="${1:-}"
case "$cmd" in

  account)
    _signed_get "/api/v3/account" "" | python3 -m json.tool
    ;;

  filters)
    symbol="${2:?Usage: filters <SYMBOL>}"
    curl -sf -m 10 "${BASE_URL}/api/v3/exchangeInfo?symbol=${symbol}" | python3 -c "
import json,sys
d = json.load(sys.stdin)
s = d['symbols'][0]
for f in s['filters']:
    if f['filterType'] in ('LOT_SIZE','MIN_NOTIONAL','NOTIONAL','PRICE_FILTER'):
        print(f)
"
    ;;

  market-buy)
    symbol="${2:?Usage: market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>}"
    quote_qty="${3:?Usage: market-buy <SYMBOL> <QUOTE_ORDER_QTY_USDT>}"
    # quoteOrderQty lets Binance compute the base-asset quantity itself and round it
    # to the correct LOT_SIZE step -- avoids us hand-rounding quantity incorrectly.
    _signed_post "/api/v3/order" "symbol=${symbol}&side=BUY&type=MARKET&quoteOrderQty=${quote_qty}" | python3 -m json.tool
    ;;

  round-qty)
    # RiskSkill's position_size is computed in base-asset units (e.g. BTC), not USDT --
    # Binance requires `quantity` on market-buy-qty/oco-sell to match LOT_SIZE's stepSize
    # exactly, or the order is rejected. This floors (never rounds up -- never risk more
    # than RiskSkill approved) to the correct step and prints the safe-to-use quantity.
    symbol="${2:?Usage: round-qty <SYMBOL> <RAW_QUANTITY>}"
    raw_qty="${3:?Usage: round-qty <SYMBOL> <RAW_QUANTITY>}"
    step="$(curl -sf -m 10 "${BASE_URL}/api/v3/exchangeInfo?symbol=${symbol}" | python3 -c "
import json,sys
d = json.load(sys.stdin)
for f in d['symbols'][0]['filters']:
    if f['filterType'] == 'LOT_SIZE':
        print(f['stepSize'])
")"
    python3 -c "
from decimal import Decimal, ROUND_DOWN
raw = Decimal('$raw_qty')
step = Decimal('$step')
floored = (raw // step) * step
print(floored.normalize() if floored == floored.to_integral() else floored)
"
    ;;

  market-buy-qty)
    # Same as market-buy but takes an exact base-asset quantity (already rounded via
    # round-qty) instead of a USDT amount -- needed when RiskSkill's position_size must
    # be honored precisely rather than re-derived from a dollar figure.
    symbol="${2:?Usage: market-buy-qty <SYMBOL> <QUANTITY>}"
    quantity="${3:?Usage: market-buy-qty <SYMBOL> <QUANTITY>}"
    _signed_post "/api/v3/order" "symbol=${symbol}&side=BUY&type=MARKET&quantity=${quantity}" | python3 -m json.tool
    ;;

  market-sell-qty)
    # Flatten/exit an exact base-asset quantity at market. Used both for manual cleanup
    # and, later, for an emergency-exit path independent of the OCO bracket.
    symbol="${2:?Usage: market-sell-qty <SYMBOL> <QUANTITY>}"
    quantity="${3:?Usage: market-sell-qty <SYMBOL> <QUANTITY>}"
    _signed_post "/api/v3/order" "symbol=${symbol}&side=SELL&type=MARKET&quantity=${quantity}" | python3 -m json.tool
    ;;

  oco-sell)
    symbol="${2:?Usage: oco-sell <SYMBOL> <QUANTITY> <TAKE_PROFIT_PRICE> <STOP_PRICE> <STOP_LIMIT_PRICE>}"
    quantity="${3:?}"
    take_profit_price="${4:?}"
    stop_price="${5:?}"
    stop_limit_price="${6:?}"
    _signed_post "/api/v3/order/oco" \
      "symbol=${symbol}&side=SELL&quantity=${quantity}&price=${take_profit_price}&stopPrice=${stop_price}&stopLimitPrice=${stop_limit_price}&stopLimitTimeInForce=GTC" \
      | python3 -m json.tool
    ;;

  order-status)
    symbol="${2:?Usage: order-status <SYMBOL> <ORDER_ID>}"
    order_id="${3:?}"
    _signed_get "/api/v3/order" "symbol=${symbol}&orderId=${order_id}" | python3 -m json.tool
    ;;

  cancel-oco)
    symbol="${2:?Usage: cancel-oco <SYMBOL> <ORDER_LIST_ID>}"
    order_list_id="${3:?}"
    _signed_delete "/api/v3/orderList" "symbol=${symbol}&orderListId=${order_list_id}" | python3 -m json.tool
    ;;

  *)
    echo "Usage: $0 {account|filters|market-buy|oco-sell|order-status|cancel-oco} ..." >&2
    exit 1
    ;;
esac
