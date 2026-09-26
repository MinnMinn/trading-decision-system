#!/usr/bin/env bash
# Verifies the MT5 file-bridge is alive: files present, valid JSON, fresh (< MAX_AGE_SEC old).
set -euo pipefail
SYMBOL="${1:-XAUUSD}"; MAX_AGE_SEC="${2:-900}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; DIR="$ROOT/data/live/mt5-bridge"
[ -d "$DIR" ] || { echo "BRIDGE UNAVAILABLE: $DIR missing"; exit 1; }
# PAR-5: EA v1.03 writes raw server time to ohlcv.<SYM>.<TF>.server.json; convert before reading (no-op for an older EA).
python3 "$ROOT/scripts/mt5_time.py" sync --symbols "$SYMBOL" >/dev/null || echo "CONVERSION REFUSED: see the reason above; the .json files were left as they were"
now=$(date -u +%s); rc=0
for tf in 1W 1D 4H 1H 15m 5m; do
  f="$DIR/ohlcv.${SYMBOL}.${tf}.json"
  if [ ! -f "$f" ]; then echo "UNAVAILABLE $tf: $f not found (EA not attached / not exporting yet)"; rc=1; continue; fi
  if ! n=$(jq '.candles | length' "$f" 2>/dev/null); then echo "UNAVAILABLE $tf: invalid JSON"; rc=1; continue; fi
  upd=$(jq -r '.last_updated' "$f"); ts=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$upd" +%s 2>/dev/null || date -u -d "$upd" +%s 2>/dev/null || echo 0)  # BSD, then GNU (Git Bash)
  age=$(( now - ts ))
  if [ "$age" -gt "$MAX_AGE_SEC" ]; then echo "STALE $tf: $n candles, last_updated $upd (${age}s old)"; rc=1; else echo "AVAILABLE $tf: $n candles, last_updated $upd (${age}s old)"; fi
done
exit $rc
