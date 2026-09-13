#!/usr/bin/env bash
# Background deterministic scanner (launchd fires this every 60 s; see integrations/launchd/com.tyme.trading.scanner.plist).
# One invocation = one pass: fetch klines + run scripts/ict-scan.py for the styles that are due, append NEW structural
# events to data/live/events.jsonl (the Claude session watches that file), log to data/live/scan-loop.log.
# This is the ONLY writer of data/live/market-data, data/live/prelim and data/live/scan-state.* once installed;
# Claude ticks read those files and copy what they need. Read-only research: never places orders.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
# scan_window <tf> -> "<bars> <recent>". THE one table (scripts/automation.py SCAN_WINDOW): this used to be
# hardcoded per call site below; this loop now reads it here. The backtest will read it too via
# scripts/live_rules.py (Task 2, not yet created).
scan_window() {
  python3 - "$1" <<'PYEOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("automation", "scripts/automation.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
w = m.SCAN_WINDOW[sys.argv[1]]
print(w["bars"], w["recent"])
PYEOF
}
LOG="data/live/scan-loop.log"; EVENTS="data/live/events.jsonl"; LOCK="data/live/.scan-loop.lock.d"
mkdir -p data/live
# Automation switch: docs/architecture/automation-config.json, written only by scripts/automation.py (/automation).
# No file = unconfigured = run as before. Master off or layers.scanner off = this pass does nothing.
# v2 (schema_version 2) is per-market: scripts/automation.py owns the (market, timeframe) -> style mapping and the
# per-market instrument lists, so this gate asks that module rather than re-deriving the vocabulary here.
eval "$(python3 - <<'GATE'
import importlib.util, os
try:
    s = importlib.util.spec_from_file_location("automation", "scripts/automation.py")
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    cfg, exists, _ = m.load()
    on = (not exists) or (cfg.get("enabled", True) and cfg.get("layers", {}).get("scanner", True))
    print("AUTO_SCANNER=%d" % (1 if on else 0))
    print("AUTO_STYLES='%s'" % ",".join(m.enabled_styles(cfg)))
    print("AUTO_CRYPTO='%s'" % ",".join(m.enabled_instruments(cfg, "crypto")))
    print("AUTO_CFD='%s'" % ",".join(m.enabled_instruments(cfg, "cfd")))
except Exception:
    pass          # unreadable module/config = UNCONFIGURED = run exactly as before the switch existed
GATE
)"
AUTO_SCANNER="${AUTO_SCANNER:-1}"
AUTO_STYLES="${AUTO_STYLES:-scalping,daytrade,1h,4h,swing,gold,gold-1h,gold-4h,gold-swing}"
# Fallback when the config is unreadable (UNCONFIGURED): the full ANALYSIS allowlist from the single source.
source "$ROOT/scripts/instruments.sh" 2>/dev/null || true
AUTO_CRYPTO="${AUTO_CRYPTO:-$(instruments_analysis crypto 2>/dev/null | tr " " ",")}"
AUTO_CRYPTO="${AUTO_CRYPTO:-BTCUSDT,ETHUSDT,SOLUSDT}"   # last resort if jq/the file is missing
AUTO_CFD="${AUTO_CFD:-XAUUSD}"
AUTO_INSTRUMENTS="${AUTO_CRYPTO}${AUTO_CFD:+,$AUTO_CFD}"
[ "$AUTO_SCANNER" = "1" ] || { echo "$(date -u +%FT%TZ) scanner disabled by /automation" >>"$LOG"; exit 0; }
# mkdir-based lock (macOS has no flock); a lock older than 5 min is considered stale
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +5 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
now() { date -u +%FT%TZ; }
# Headless model layer (user decision 2026-09-11): after a style's scanner pass, start its Sonnet local read outside the session
# (scripts/model-read.sh gates on /automation and on its own per-style interval, so calling it every tick is cheap). The daily full
# analysis is started once a day in the 07:30-07:59Z window. Both are detached so the scanner never waits for a model.
model_read() { local style=$1 kind=${2:-local}; ( nohup bash "$ROOT/scripts/model-read.sh" "$style" "$kind" >>"$ROOT/data/live/model-reads.log" 2>&1 </dev/null & ) ; }
run_style() { # tf style bars recent [symbols]   (bars/recent come from scan_window; symbols from the MT5 bridge are not fetched here: the EA writes them)
  local tf=$1 style=$2 n=$3 recent=$4 syms=${5:-$AUTO_CRYPTO} s out rc keep=""
  case ",$AUTO_STYLES," in *",$style,"*) ;; *) echo "$(now) $style disabled by /automation" >>"$LOG"; return 0 ;; esac
  for s in ${syms//,/ }; do case ",$AUTO_INSTRUMENTS," in *",$s,"*) keep="${keep:+$keep,}$s" ;; esac; done
  [ -n "$keep" ] || { echo "$(now) $style skipped: no enabled instrument (/automation instrument)" >>"$LOG"; return 0; }
  syms="$keep"
  if [ "${syms#*XAU}" = "$syms" ] && [ "${syms#*XAG}" = "$syms" ] && [ "${syms#*OIL}" = "$syms" ]; then
    for s in ${syms//,/ }; do
      bash scripts/fetch-binance-klines.sh "$s" "$tf" "$n" >/dev/null 2>>"$LOG" || echo "$(now) fetch FAIL $s $tf" >>"$LOG"
    done
  else
    # The MT5 EA is per-chart: a CFD symbol only has data once a chart running ExportOHLCV is open for it
    # (SYSTEM-DESIGN.md §12 item 6). Drop the symbols with no export rather than abandoning the whole style.
    keep=""
    for s in ${syms//,/ }; do
      if [ -s "data/live/mt5-bridge/ohlcv.$s.$tf.json" ]; then keep="${keep:+$keep,}$s"
      else echo "$(now) $style: no bridge file for $s $tf -- symbol skipped" >>"$LOG"; fi
    done
    [ -n "$keep" ] || { echo "$(now) $style skipped: no MT5 export on disk for any enabled instrument" >>"$LOG"; return 0; }
    syms="$keep"
  fi
  out="$(python3 scripts/ict-scan.py --tf "$tf" --n "$n" --style "$style" --recent "$recent" --symbols "$syms" 2>>"$LOG")"; rc=$?
  if [ "$rc" -eq 3 ]; then
    printf '%s' "$out" | STYLE="$style" python3 -c '
import json, os, sys
d = json.load(sys.stdin)
with open("data/live/events.jsonl", "a") as f:
    for e in d.get("_new_events", []):
        f.write(json.dumps({"t": d.get("_scanned_at"), "style": os.environ["STYLE"], **e}, ensure_ascii=False) + "\n")
' 2>>"$LOG"
  fi
  echo "$(now) $style rc=$rc" >>"$LOG"; case "$rc" in 0|3) model_read "$style" local ;; esac
}
FORCE="${1:-}"                       # scan-loop.sh all  -> run every style now (manual / first run)
M=$(date -u +%M); H=$(date -u +%H)
run_style 1m scalping $(scan_window 1m)
# CFD scalping on M5 (user decision 2026-09-11): one minute after each 5-minute close
case "$M" in *1|*6) run_style 5m gold-scalp $(scan_window 5m) "$AUTO_CFD" ;; esac
case "$M" in 01|16|31|46) run_style 15m daytrade $(scan_window 15m); run_style 15m gold $(scan_window 15m) "$AUTO_CFD" ;; esac
# 1h styles: minute :02 of every hour. 4h styles: minute :03 of every 4th hour (:03 not :02 so the hourly pass
# and the 4-hourly pass never contend for the same minute's lock). Swing keeps its original :02 / H%4 slot.
if [ "$M" = "02" ]; then run_style 1H 1h $(scan_window 1H); run_style 1H gold-1h $(scan_window 1H) "$AUTO_CFD"; fi
if [ "$M" = "02" ] && [ $((10#$H % 4)) -eq 0 ]; then run_style 1D swing $(scan_window 1D); run_style 1D gold-swing $(scan_window 1D) "$AUTO_CFD"; for s in ${AUTO_CRYPTO//,/ }; do bash scripts/fetch-binance-klines.sh "$s" 1W 208 >/dev/null 2>>"$LOG" || echo "$(now) fetch FAIL $s 1W" >>"$LOG"; done; fi   # 1W = swing context chart only, not scanned
if [ "$M" = "03" ] && [ $((10#$H % 4)) -eq 0 ]; then run_style 4H 4h $(scan_window 4H); run_style 4H gold-4h $(scan_window 4H) "$AUTO_CFD"; fi
if [ "$H" = "07" ] && [ "$M" -ge 30 ] && [ "$M" -le 59 ]; then for st in scalping daytrade swing gold-scalp gold gold-swing; do model_read "$st" full; done; fi   # once a day (model-read.sh keeps the 20 h interval)
if [ "$FORCE" = "all" ]; then run_style 5m gold-scalp $(scan_window 5m) "$AUTO_CFD"; run_style 15m daytrade $(scan_window 15m); run_style 1H 1h $(scan_window 1H); run_style 4H 4h $(scan_window 4H); run_style 1D swing $(scan_window 1D); run_style 15m gold $(scan_window 15m) "$AUTO_CFD"; run_style 1H gold-1h $(scan_window 1H) "$AUTO_CFD"; run_style 4H gold-4h $(scan_window 4H) "$AUTO_CFD"; run_style 1D gold-swing $(scan_window 1D) "$AUTO_CFD"; fi
# keep the log bounded
if [ "$(wc -l < "$LOG")" -gt 5000 ]; then tail -n 2000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"; fi
