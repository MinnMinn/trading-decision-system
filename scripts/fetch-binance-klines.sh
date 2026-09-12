#!/usr/bin/env bash
# Real (non-mock) crypto market-data connector for the institutional trading system.
# Fetches Binance's public REST klines (no API key required) and normalizes them into
# the exact shape defined in docs/architecture/data-sources.md's "Crypto market-data contract".
#
# Usage: fetch-binance-klines.sh <SYMBOL> <TIMEFRAME> [LIMIT]
#   SYMBOL:    e.g. BTCUSDT, ETHUSDT, SOLUSDT
#   TIMEFRAME: 1W | 1D | 4H | 2H | 1H | 30m | 15m | 5m | 1m  (mapped to Binance's own interval codes below)
#   LIMIT:     number of candles, default 100, max 1000 (Binance limit)
#
# Output: data/live/market-data/ohlcv.<SYMBOL>.<TIMEFRAME>.json (same field shape as mock/market-data/*.json), or
#         $KLINES_OUT_DIR/ohlcv.<SYMBOL>.<TIMEFRAME>.json when that variable is set (pilot-private copies).
#
# Requires: curl, jq. No auth/API key needed -- Binance's klines endpoint is public.

set -euo pipefail

SYMBOL="${1:?Usage: fetch-binance-klines.sh <SYMBOL> <TIMEFRAME> [LIMIT]}"
TIMEFRAME="${2:?Usage: fetch-binance-klines.sh <SYMBOL> <TIMEFRAME> [LIMIT]}"
LIMIT="${3:-100}"

case "$TIMEFRAME" in
  1W)  BINANCE_INTERVAL="1w" ;;
  1D)  BINANCE_INTERVAL="1d" ;;
  4H)  BINANCE_INTERVAL="4h" ;;
  2H)  BINANCE_INTERVAL="2h" ;;
  1H)  BINANCE_INTERVAL="1h" ;;
  30m) BINANCE_INTERVAL="30m" ;;
  15m) BINANCE_INTERVAL="15m" ;;
  5m)  BINANCE_INTERVAL="5m" ;;
  1m)  BINANCE_INTERVAL="1m" ;;
  *) echo "Unsupported timeframe: $TIMEFRAME (expected one of 1W 1D 4H 2H 1H 30m 15m 5m 1m)" >&2; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="${KLINES_OUT_DIR:-$PROJECT_ROOT/data/live/market-data}"   # KLINES_OUT_DIR: a private copy for a pilot (one writer per file, SYSTEM-DESIGN §13)
OUT_FILE="$OUT_DIR/ohlcv.${SYMBOL}.${TIMEFRAME}.json"
mkdir -p "$OUT_DIR"

# --fail-with-body keeps Binance's error JSON (e.g. {"code":-1121,"msg":"Invalid symbol."}) so the
# failure is loud; a bare `curl -sf` would abort under set -e with nothing on stderr.
if ! RAW=$(curl -sS --fail-with-body -m 15 "https://api.binance.com/api/v3/klines?symbol=${SYMBOL}&interval=${BINANCE_INTERVAL}&limit=${LIMIT}") || [ -z "$RAW" ]; then
  echo "ERROR: Binance klines fetch failed for ${SYMBOL} ${TIMEFRAME}: ${RAW:-<no response body>} -- treat crypto_market_data as UNAVAILABLE, do not proceed as if this succeeded." >&2
  exit 1
fi

NOW_ISO="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "$RAW" | jq \
  --arg symbol "$SYMBOL" \
  --arg timeframe "$TIMEFRAME" \
  --arg now "$NOW_ISO" \
  '{
    symbol: $symbol,
    timeframe: $timeframe,
    candles: [ .[] | {
      time: (.[0] / 1000 | strftime("%Y-%m-%dT%H:%M:%SZ")),
      open: (.[1] | tonumber),
      high: (.[2] | tonumber),
      low: (.[3] | tonumber),
      close: (.[4] | tonumber),
      volume: (.[5] | tonumber)
    } ],
    last_updated: $now,
    _source: "binance_public_rest_live"
  }' > "$OUT_FILE"

echo "Wrote $(jq '.candles | length' "$OUT_FILE") candles to $OUT_FILE"
