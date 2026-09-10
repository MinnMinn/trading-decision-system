#!/usr/bin/env bash
# Background deterministic scanner (launchd fires this every 60 s; see integrations/launchd/com.tyme.trading.scanner.plist).
# One invocation = one pass: fetch klines + run scripts/ict-scan.py for the styles that are due, append NEW structural
# events to data/live/events.jsonl (the Claude session watches that file), log to data/live/scan-loop.log.
# This is the ONLY writer of data/live/market-data, data/live/prelim and data/live/scan-state.* once installed;
# Claude ticks read those files and copy what they need. Read-only research: never places orders.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
LOG="data/live/scan-loop.log"; EVENTS="data/live/events.jsonl"; LOCK="data/live/.scan-loop.lock.d"
mkdir -p data/live
# mkdir-based lock (macOS has no flock); a lock older than 5 min is considered stale
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +5 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
now() { date -u +%FT%TZ; }
run_style() { # tf n style recent
  local tf=$1 n=$2 style=$3 recent=$4 s out rc
  for s in BTCUSDT ETHUSDT SOLUSDT; do
    bash scripts/fetch-binance-klines.sh "$s" "$tf" "$n" >/dev/null 2>>"$LOG" || echo "$(now) fetch FAIL $s $tf" >>"$LOG"
  done
  out="$(python3 scripts/ict-scan.py --tf "$tf" --n "$n" --style "$style" --recent "$recent" 2>>"$LOG")"; rc=$?
  if [ "$rc" -eq 3 ]; then
    printf '%s' "$out" | STYLE="$style" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
with open("data/live/events.jsonl", "a") as f:
    for e in d.get("_new_events", []):
        f.write(json.dumps({"t": d.get("_scanned_at"), "style": os.environ["STYLE"], **e}, ensure_ascii=False) + "\n")
' 2>>"$LOG"
  fi
  echo "$(now) $style rc=$rc" >>"$LOG"
}
FORCE="${1:-}"                       # scan-loop.sh all  -> run every style now (manual / first run)
M=$(date -u +%M); H=$(date -u +%H)
run_style 1m 180 scalping 4
case "$M" in 01|16|31|46) run_style 15m 288 daytrade 2 ;; esac
if [ "$M" = "02" ] && [ $((10#$H % 4)) -eq 0 ]; then run_style 1D 120 swing 1; fi
if [ "$FORCE" = "all" ]; then run_style 15m 288 daytrade 2; run_style 1D 120 swing 1; fi
# keep the log bounded
if [ "$(wc -l < "$LOG")" -gt 5000 ]; then tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
