#!/usr/bin/env bash
# Runs the pilot every tick-seconds (scripts/strategy-runner.py --tick-seconds: the fastest selected timeframe).
#   Usage: [PILOT_MARKET=spot|futures] [PILOT_END=<UTC ISO>|never] pilot-loop.sh [END_UTC_ISO|never]
#   spot -> data/live/pilot (LONG only); futures -> data/live/pilot-futures (LONG/SHORT, ISOLATED, leverage <= 3).
# Environment (demo testnet / real mainnet) is decided by docs/architecture/automation-config.json
# -> execution.environment and config/env.<environment>; scripts/strategy-runner.py loads it on every tick.
# Stops when <pilot dir>/STOP exists or END passes. While automation is OFF (master switch, layers.pilot,
# markets.crypto) the loop keeps running but idles -- each tick is refused inside strategy-runner.py, so
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
  # One engine (user decision 2026-09-13): scripts/strategy-runner.py. There is no profile switch any more --
  # the previous arrangement chose between this and a second, unrelated rule set on the same account, which is
  # how the planned-R:R floor came to differ between the two paths (see commit dc4a475).
  python3 "$ROOT/scripts/strategy-runner.py" --live >> "$PD/loop.log" 2>&1 \
    || echo "tick error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  # journal sync (mechanical, no model): ingest any entry/exit this tick produced, rebuild index/views/page.
  # The page is published by the journal-publish session cron when it changed (integrations/crons/journal-publish.md).
  python3 "$ROOT/scripts/journal.py" all >> "$PD/loop.log" 2>&1 || echo "journal sync error $(date -u +%FT%TZ)" >> "$PD/loop.log"
  period="$(python3 "$ROOT/scripts/strategy-runner.py" --tick-seconds 2>/dev/null || echo 1800)"
  sleep "$period"
done
