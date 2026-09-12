#!/usr/bin/env bash
# Headless model layer (user decision 2026-09-11): run the layer-2 local read or the layer-3 daily full analysis for ONE style with
# `claude -p` (Sonnet), outside any Claude Code session, so every style runs in parallel and the artifacts stay fresh even when no
# session is open. Started by scripts/scan-loop.sh right after the scanner refreshed that style (data/live/prelim), gated by
# `scripts/automation.py allows local_read <style>`. The session only builds + publishes (integrations/crons/publish-tick.md).
#
#   model-read.sh <style> [local|full]     local = <style>-local-read prompt (default), full = <style>-daily-full prompt
#   env: MODEL_READ_INTERVAL=<seconds> (min gap between two runs of the same style/kind; default per kind below),
#        MODEL_READ_MAX_TURNS (default 40), MODEL_READ_MODEL (default sonnet), MODEL_READ_FORCE=1 (ignore the interval)
# Prompts: integrations/headless/<style>-local-read.md / <style>-daily-full.md (extracted from the cron templates; {{SCRATCHPAD}} ->
# a per-run directory under data/live/model-reads/<style>/). Logs: data/live/model-reads/<style>.<kind>.log (json result per run).
# Permissions: --allowedTools limits Bash to the project's own analysis scripts and Write to the files that layer owns
# (SYSTEM-DESIGN §13 one-writer rule); the Artifact tool is not available headless, so the model cannot publish.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STYLE="${1:?style}"; KIND="${2:-local}"
CLAUDE="${CLAUDE_BIN:-$(ls "$HOME"/.nvm/versions/node/*/bin/claude 2>/dev/null | tail -1)}"
[ -x "${CLAUDE:-}" ] || CLAUDE="$(command -v claude || true)"
[ -x "${CLAUDE:-}" ] || { echo "$(date -u +%FT%TZ) $STYLE $KIND: claude binary not found" >&2; exit 2; }
case "$KIND" in local) PROMPT="$ROOT/integrations/headless/$STYLE-local-read.md" ;; full) PROMPT="$ROOT/integrations/headless/$STYLE-daily-full.md" ;; *) echo "kind must be local|full" >&2; exit 1 ;; esac
[ -f "$PROMPT" ] || { echo "$(date -u +%FT%TZ) $STYLE $KIND: no prompt file $PROMPT" >&2; exit 2; }
DIR="$ROOT/data/live/model-reads/$STYLE"; mkdir -p "$DIR"
LOG="$DIR/../$STYLE.$KIND.log"; LOCK="$DIR/.lock-$KIND"; STAMP="$DIR/.last-$KIND"
# default intervals (seconds): local reads follow the old cron cadence, full = once a day
if [ -z "${MODEL_READ_INTERVAL:-}" ]; then
  if [ "$KIND" = full ]; then MODEL_READ_INTERVAL=72000; else
    case "$STYLE" in scalping|gold-scalp) MODEL_READ_INTERVAL=600 ;; daytrade|gold) MODEL_READ_INTERVAL=900 ;; 1h|gold-1h) MODEL_READ_INTERVAL=3600 ;; 4h|gold-4h) MODEL_READ_INTERVAL=14400 ;; *) MODEL_READ_INTERVAL=21600 ;; esac
  fi
fi
now=$(date -u +%s)
if [ "${MODEL_READ_FORCE:-0}" != 1 ] && [ -f "$STAMP" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0); if [ $((now - last)) -lt "$MODEL_READ_INTERVAL" ]; then exit 0; fi
fi
# permission gate: the /automation switch (any session may have turned it off)
python3 "$ROOT/scripts/automation.py" allows local_read "$STYLE" >/dev/null 2>&1 || exit 0
if ! mkdir "$LOCK" 2>/dev/null; then
  if [ -n "$(find "$LOCK" -maxdepth 0 -mmin +45 2>/dev/null)" ]; then rmdir "$LOCK" 2>/dev/null; mkdir "$LOCK" 2>/dev/null || exit 0; else exit 0; fi
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
echo "$now" > "$STAMP"
RUN="$DIR/run-$(date -u +%Y%m%dT%H%M%SZ)-$KIND"; mkdir -p "$RUN"
sed "s#{{SCRATCHPAD}}#$RUN#g" "$PROMPT" > "$RUN/prompt.md"
# scalping local read is event-driven (scripts/scalping-events-since.py): NONE = nothing new since the last read -> skip; else the
# events line replaces the EVENTS placeholder of the prompt (the same guard the old cron had).
if [ "$STYLE" = scalping ] && [ "$KIND" = local ]; then
  EVENTS="$(cd "$ROOT" && python3 scripts/scalping-events-since.py 2>/dev/null || echo NONE)"
  if [ "$EVENTS" = NONE ] || [ -z "$EVENTS" ]; then rm -rf "$RUN"; rm -f "$STAMP"; exit 0; fi
  python3 - "$RUN/prompt.md" "$EVENTS" <<'PY'
import sys; p, ev = sys.argv[1], sys.argv[2]; s = open(p, encoding="utf-8").read().replace('\\"EVENTS\\"', '\\"' + ev.replace('"', "'") + '\\"'); open(p, "w", encoding="utf-8").write(s)
PY
fi
# tools: the analysis scripts + writing the files this layer owns. Everything else is denied (headless = no permission prompts).
# (one comma-separated argument: the patterns contain spaces)
if [ "$KIND" = full ]; then
  ALLOWED="Bash(python3 scripts/local-eval-brief.py*),Bash(python3 scripts/check-narrative.py*),Bash(python3 scripts/ict-scan.py*),Bash(python3 scripts/event-ledger.py*),Write(data/live/narrative/**),Write(data/live/anchors.*),Write(data/live/prelim/**),Write($RUN/**),Read,Glob,Grep"
else
  ALLOWED="Bash(python3 scripts/local-eval-brief.py*),Bash(python3 scripts/check-model-prose.py*),Write(data/live/prelim/**),Write($RUN/**),Read,Glob,Grep"
fi
echo "$(date -u +%FT%TZ) $STYLE $KIND: start (run dir ${RUN#$ROOT/})" >> "$LOG"
cd "$ROOT" && "$CLAUDE" -p "$(cat "$RUN/prompt.md")" --model "${MODEL_READ_MODEL:-sonnet}" --max-turns "${MODEL_READ_MAX_TURNS:-40}" \
  --allowedTools "$ALLOWED" --disallowedTools "Artifact,WebFetch,WebSearch,Agent,Edit,NotebookEdit" --output-format json < /dev/null > "$RUN/result.json" 2> "$RUN/stderr.log"
rc=$?
python3 - "$RUN/result.json" "$rc" >> "$LOG" 2>&1 <<'PY'
import json, sys, datetime
p, rc = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(p)); res = d.get("result") or ""
    print(f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} rc={rc} turns={d.get('num_turns')} cost_usd={d.get('total_cost_usd')} duration_ms={d.get('duration_ms')} is_error={d.get('is_error')} | {res[-300:].replace(chr(10), ' ')}")
except Exception as e:
    print(f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} rc={rc} result unreadable: {e}")
PY
exit $rc
