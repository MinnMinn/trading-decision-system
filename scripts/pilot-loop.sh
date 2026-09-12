#!/usr/bin/env bash
# Runs the pilot every 15 minutes (legacy profile, aligned to 15m closes) or every 30 minutes (profile top5, futures).
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
  # Pilot profile (user decision 2026-09-11): execution.pilot_profile in docs/architecture/automation-config.json, read every tick
  # (read-only here; scripts/automation.py is the writer). top5 = scripts/strategy-runner.py on the FUTURES loop only.
  PROFILE="$(python3 -c 'import json;print(json.load(open("'"$ROOT"'/docs/architecture/automation-config.json")).get("execution",{}).get("pilot_profile","legacy"))' 2>/dev/null || echo legacy)"
  if [ "$PROFILE" = "top5" ] && [ "$PILOT_MARKET" = "futures" ]; then
    python3 "$ROOT/scripts/strategy-runner.py" --live >> "$PD/loop.log" 2>&1 || echo "top5 tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  elif [ "$PROFILE" = "top5" ]; then
    # one profile = one rule set: while top5 is selected the spot loop idles (the legacy spot rules would be a second, unrelated strategy)
    echo "$(date -u +%FT%TZ) profile top5: spot loop idle (top5 trades futures testnet + MT5 demo only)" >> "$PD/loop.log"
  else
    python3 "$ROOT/scripts/demo-pilot.py" --live --market "$PILOT_MARKET" >> "$PD/loop.log" 2>&1 || echo "tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  fi
  # journal sync (mechanical, no model): ingest any entry/exit this tick produced, rebuild index/views/page.
  # The page is published by the journal-publish session cron when it changed (integrations/crons/journal-publish.md).
  python3 "$ROOT/scripts/journal.py" all >> "$PD/loop.log" 2>&1 || echo "journal sync error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  # sleep to 1 minute past the next candle close: 15m for the legacy rules; for profile top5 the fastest selected timeframe (5m..1D)
  if [ "$PROFILE" = "top5" ] && [ "$PILOT_MARKET" = "futures" ]; then period="$(python3 "$ROOT/scripts/strategy-runner.py" --tick-seconds 2>/dev/null || echo 1800)"; else period=900; fi
  now=$(date -u +%s); next=$(( (now / period + 1) * period + 60 )); sleep $(( next - now ))
done
