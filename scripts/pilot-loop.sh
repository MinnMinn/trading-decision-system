#!/usr/bin/env bash
# Runs the demo pilot every 15 minutes (aligned to 15m candle closes) until <pilot dir>/STOP exists
# or the given end time passes. Binance TESTNET only. Usage: [PILOT_MARKET=spot|futures] pilot-loop.sh [END_UTC_ISO]
# spot -> data/live/pilot (LONG only); futures -> data/live/pilot-futures (LONG/SHORT, ISOLATED, leverage <= 3).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
END="${1:-$(date -u -v+24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+24 hours' +%Y-%m-%dT%H:%M:%SZ)}"
export PILOT_MARKET="${PILOT_MARKET:-spot}"
PD="$ROOT/data/live/pilot"; [ "$PILOT_MARKET" = "futures" ] && PD="$ROOT/data/live/pilot-futures"
mkdir -p "$PD"
echo "pilot loop [$PILOT_MARKET] started $(date -u +%FT%TZ), ends $END, STOP file: ${PD#$ROOT/}/STOP" | tee -a "$PD/loop.log"
while :; do
  [ -f "$PD/STOP" ] && { echo "STOP file found, exiting" | tee -a "$PD/loop.log"; break; }
  [ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \> "$END" ] && { echo "end time reached" | tee -a "$PD/loop.log"; break; }
  python3 "$ROOT/scripts/demo-pilot.py" --live --market "$PILOT_MARKET" >> "$PD/loop.log" 2>&1 || echo "tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  # sleep to 1 minute past the next quarter-hour so the 15m candle has closed
  now=$(date -u +%s); next=$(( (now / 900 + 1) * 900 + 60 )); sleep $(( next - now ))
done
