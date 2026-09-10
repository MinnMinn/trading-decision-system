#!/usr/bin/env python3
"""Debounce guard for the scalping local read (integrations/crons/scalping-local-read.md).

Prints ONE line: either  NONE  (no scalping event in data/live/events.jsonl newer than the last local read)
or a short Vietnamese summary of the new events, deduplicated by (symbol, kind, level) -- the scanner re-emits
the same MSS every minute as its window slides, so raw line counts overstate what actually happened.

"Last local read" = the oldest mtime among data/live/prelim/scalping.<SYM>.model.html (missing file = never read).
Usage: scalping-events-since.py [--min-events N]      exit 0 always; the caller reads the first line.
"""
import json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(ROOT, "data", "live", "events.jsonl")
SYMS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
KIND_VI = {"sweep": "quét", "erl_low": "chạm ERL-low", "erl_high": "chạm ERL-high",
           "mss_bull": "MSS tăng", "mss_bear": "MSS giảm"}


def last_read():
    ts = []
    for s in SYMS:
        p = os.path.join(ROOT, "data", "live", "prelim", f"scalping.{s}.model.html")
        ts.append(os.path.getmtime(p) if os.path.exists(p) else 0.0)
    return min(ts)


def main():
    min_events = 1
    if "--min-events" in sys.argv:
        min_events = int(sys.argv[sys.argv.index("--min-events") + 1])
    since = last_read()
    if not os.path.exists(EVENTS):
        print("NONE"); return 0
    seen, out = set(), []
    for line in open(EVENTS, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("style") != "scalping":
            continue
        try:
            t = datetime.datetime.fromisoformat(e["t"].replace("Z", "+00:00")).timestamp()
        except (KeyError, ValueError):
            continue
        if t <= since:
            continue
        key = (e.get("symbol"), e.get("kind"), e.get("level"))
        if key in seen:
            continue
        seen.add(key)
        sym = (e.get("symbol") or "").replace("USDT", "")
        kind = KIND_VI.get(e.get("kind"), e.get("kind"))
        pool = f" {e['pool']}" if e.get("pool") else ""
        lvl = e.get("level")
        when = (e.get("time") or e.get("t") or "")[11:16]
        out.append(f"{sym} {kind}{pool} {lvl} @{when}Z")
    if len(out) < min_events:
        print("NONE"); return 0
    print("; ".join(out[-12:]))   # newest last, capped so the brief stays short
    return 0


if __name__ == "__main__":
    sys.exit(main())
