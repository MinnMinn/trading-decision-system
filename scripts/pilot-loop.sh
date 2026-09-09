#!/usr/bin/env bash
# Runs the demo pilot every 15 minutes (aligned to 15m candle closes) until data/live/pilot/STOP exists
# or the given end time passes. Binance SPOT TESTNET only. Usage: pilot-loop.sh [END_UTC_ISO]
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
END="${1:-$(date -u -v+24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+24 hours' +%Y-%m-%dT%H:%M:%SZ)}"
mkdir -p "$ROOT/data/live/pilot"
echo "pilot loop started $(date -u +%FT%TZ), ends $END, STOP file: data/live/pilot/STOP" | tee -a "$ROOT/data/live/pilot/loop.log"
while :; do
  [ -f "$ROOT/data/live/pilot/STOP" ] && { echo "STOP file found, exiting" | tee -a "$ROOT/data/live/pilot/loop.log"; break; }
  [ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \> "$END" ] && { echo "end time reached" | tee -a "$ROOT/data/live/pilot/loop.log"; break; }
  python3 "$ROOT/scripts/demo-pilot.py" --live >> "$ROOT/data/live/pilot/loop.log" 2>&1 || echo "tick error $(date -u +%FT%TZ)" >> "$ROOT/data/live/pilot/loop.log"
  # sleep to 1 minute past the next quarter-hour so the 15m candle has closed
  now=$(date -u +%s); next=$(( (now / 900 + 1) * 900 + 60 )); sleep $(( next - now ))
done
