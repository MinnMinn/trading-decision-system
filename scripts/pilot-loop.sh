#!/usr/bin/env bash
# Runs the pilot every 15 minutes (aligned to 15m candle closes).
#   Usage: [PILOT_MARKET=spot|futures] [PILOT_END=<UTC ISO>|never] pilot-loop.sh [END_UTC_ISO|never]
#   spot -> data/live/pilot (LONG only); futures -> data/live/pilot-futures (LONG/SHORT, ISOLATED, leverage <= 3).
# Environment (demo testnet / real mainnet) is decided by docs/architecture/automation-config.json
# -> execution.environment and config/env.<environment>; scripts/demo-pilot.py loads it on every tick.
# Stops when <pilot dir>/STOP exists or END passes. While automation is OFF (master switch, layers.pilot,
# markets.crypto) the loop keeps running but idles -- each tick is refused inside demo-pilot.py, so
# `/automation on` resumes it without a restart. Started/stopped by `/automation on|off` through launchd
# (integrations/launchd/com.tyme.trading.pilot.plist) or by a human in a terminal.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
END="${1:-${PILOT_END:-$(date -u -v+24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+24 hours' +%Y-%m-%dT%H:%M:%SZ)}}"
export PILOT_MARKET="${PILOT_MARKET:-spot}"
PD="$ROOT/data/live/pilot"; [ "$PILOT_MARKET" = "futures" ] && PD="$ROOT/data/live/pilot-futures"
mkdir -p "$PD"
ENVNAME="$(TRADING_ENV="${TRADING_ENV:-}" python3 "$ROOT/scripts/trading_env.py" 2>/dev/null | sed -n 's/^active environment: \([a-z]*\).*/\1/p')"
echo "pilot loop [$PILOT_MARKET] env=${ENVNAME:-?} started $(date -u +%FT%TZ), ends $END, STOP file: ${PD#$ROOT/}/STOP" | tee -a "$PD/loop.log"
while :; do
  [ -f "$PD/STOP" ] && { echo "STOP file found, exiting" | tee -a "$PD/loop.log"; break; }
  if [ "$END" != "never" ] && [ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \> "$END" ]; then echo "end time reached" | tee -a "$PD/loop.log"; break; fi
  python3 "$ROOT/scripts/demo-pilot.py" --live --market "$PILOT_MARKET" >> "$PD/loop.log" 2>&1 || echo "tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  # sleep to 1 minute past the next quarter-hour so the 15m candle has closed
  now=$(date -u +%s); next=$(( (now / 900 + 1) * 900 + 60 )); sleep $(( next - now ))
done
