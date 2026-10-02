#!/usr/bin/env python3
"""Forward PAPER log for the two F2 survivors (docs/plans/2026-10-02-edge-followup-preregistration.md §4, stage (a); design in
docs/audits/2026-10-02-fvg-book-sim.md). PAPER ONLY: it places no order anywhere and touches no account.

    python3 scripts/research/fvg_forward.py scan      # append NEW signals (entry after the last logged one) to the log
    python3 scripts/research/fvg_forward.py resolve   # fill in the outcome of logged signals whose exit bar now exists
    python3 scripts/research/fvg_forward.py status    # counts per component, and whether stage (a) may be judged yet

Bars: the stored FTMO-Demo history (data/history/ftmo, re-export it with ExportHistory.mq5 + import-mt5-history.py) MERGED
with the live bridge file `data/live/mt5-bridge/ohlcv.<SYM>.5m.json` (ExportOHLCV.mq5 v1.03+, converted by mt5_time.py sync),
deduplicated by bar time (the live bar wins). Detection is `edge_census.ev_fvg` itself (same code as the census and stage (b)).
Signals are logged only for entries at/after FORWARD_START, so the log is a pure forward record.

The paper trade per signal: entry at the FVG edge on the touch bar, the `sigma2` protective stop (2 x sigma_5m x sqrt(h)),
time exit after h bars (XAUUSD 24, US500 48), flat before the rollover -- the design of fvg_book_sim.py. A signal whose
20-day volatility history is stale (fewer than 20 dense days within the 40 calendar days before it) is logged as REFUSED with
the reason, never traded on a guessed sigma (CLAUDE.md §20, §52)."""
import argparse
import datetime
import importlib.util
import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("edge_census", os.path.join(ROOT, "scripts", "research", "edge_census.py"))
EC = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(EC)

FORWARD_START = "2026-09-29T00:00:00Z"
COMPONENTS = {"XAUUSD": 24, "US500": 48}          # the two F2 E5 survivors (symbol -> hold bars), kept for callers
#: every component on forward watch: name -> (symbol, detector kind, hold). H7 joined after F3
#: (docs/audits/2026-10-02-edge-f3.md, docs/plans/2026-10-02-edge-f3-preregistration.md: same forward rule as F2 §4).
WATCH = {"E5_XAUUSD_24": ("XAUUSD", "E5", 24), "E5_US500_48": ("US500", "E5", 48), "H7_XAUUSD_eod": ("XAUUSD", "H7", "eod")}
_F3 = None


def _f3():
    global _F3
    if _F3 is None:
        spec = importlib.util.spec_from_file_location("edge_f3", os.path.join(ROOT, "scripts", "research", "edge_f3.py"))
        _F3 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_F3)
    return _F3


def bars_to_day_end(s, e):
    """Bars from entry bar e to the last bar before the server rollover, counted on the clock (live: the day is not over)."""
    import real_costs as RC
    z = RC.server_zone(EC.PROVIDER)[1]
    lt = s.dt[e].astimezone(z)
    end = datetime.datetime.combine(lt.date() + datetime.timedelta(days=1), datetime.time(0), tzinfo=z)
    return max(1, int((end - s.dt[e]).total_seconds() // 300))
LIVE_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
LOG = os.path.join(ROOT, "data", "live", "forward", "fvg-paper.jsonl")
STAGE_A_MIN_EVENTS = 100
STAGE_A_MAX_DAYS = 274            # 9 calendar months


def merged_candles(sym, live_dir=LIVE_DIR):
    import history_store as HS
    doc, _ = HS.read_doc(sym, "5m", root=EC.HIST_ROOT)
    bars = {b["time"]: b for b in (doc["candles"] if doc else [])}
    p = os.path.join(live_dir, f"ohlcv.{sym}.5m.json")
    if os.path.exists(p):
        live = json.load(open(p))
        for b in live.get("candles", []):
            if isinstance(b.get("time"), str) and b["time"].endswith("Z"):
                bars[b["time"]] = b
    return [bars[t] for t in sorted(bars)]


def _read_log(path=LOG):
    if not os.path.exists(path):
        return []
    return [json.loads(l) for l in open(path) if l.strip()]


def _vol_fresh(s, i):
    d = s.sday[i]
    recent = [x for x in s.dense_days if d - datetime.timedelta(days=40) <= x < d]
    return len(recent) >= EC.VOL_DAYS


def signals(s, sym, h, kind="E5", name=None):
    """Every signal of component `kind` on `s` entering at/after FORWARD_START, as log rows (unresolved)."""
    out = []
    evs = EC.ev_fvg(s) if kind == "E5" else _f3().ev_breakout_trend(s)
    for ev in evs:
        e = ev["entry_i"]
        if e >= len(s.T) or s.T[e] < FORWARD_START:
            continue
        px = ev["entry_px"] if ev.get("entry_px") is not None else s.O[e]
        row = {"component": name or f"E5_{sym}_{h}", "symbol": sym, "h": h, "side": ev["side"], "signal_time": s.T[ev["i"]],
               "entry_time": s.T[e], "entry": px, "status": "open"}
        if "far" in ev:
            row["far_edge"] = ev["far"]
        sig = s.sigma(ev["i"])
        if not sig or not _vol_fresh(s, ev["i"]):
            row.update(status="refused", reason="volatility history stale or missing (re-export the 5m history)")
        else:
            nb = bars_to_day_end(s, e) if h == "eod" else h
            dist = 2.0 * sig * math.sqrt(nb) * px
            row.update(stop=px - ev["side"] * dist, stop_distance=dist)
        out.append(row)
    return out


def _series(sym, live_dir):
    return EC.Series(sym, merged_candles(sym, live_dir), _zone(), end="9999-12-31T00:00:00Z", sigma_every_day=True)


def cmd_scan(live_dir=LIVE_DIR, log=LOG):
    have = {(r.get("component", f"E5_{r['symbol']}_{r['h']}"), r["entry_time"], r["side"]) for r in _read_log(log)}
    new, cache = [], {}
    for name, (sym, kind, h) in WATCH.items():
        s = cache.setdefault(sym, _series(sym, live_dir))
        for r in signals(s, sym, h, kind, name):
            if (name, r["entry_time"], r["side"]) not in have:
                new.append(r)
    os.makedirs(os.path.dirname(log), exist_ok=True)
    with open(log, "a") as fh:
        for r in new:
            fh.write(json.dumps(r) + "\n")
    print(f"{len(new)} new signal(s) logged to {log}")
    return new


def resolve_row(s, r, costs):
    """Fill the outcome of one open row when its exit bar exists; unchanged otherwise."""
    idx = {t: j for j, t in enumerate(s.T)}
    e = idx.get(r["entry_time"])
    if e is None or r["status"] != "open":
        return r
    if r["h"] == "eod":
        later = [j for j in range(e, len(s.C)) if s.sday[j] != s.sday[e]]
        if not later:
            return r                                   # the server day is not over yet
        x = later[0] - 1
    else:
        x = e + r["h"] - 1
    if x >= len(s.C):
        return r
    if s.sday[x] != s.sday[e]:
        x = max(j for j in range(e, x + 1) if s.sday[j] == s.sday[e])      # flat before the rollover
    side, stop, px = r["side"], r["stop"], r["entry"]
    exit_px, how, j_exit = s.C[x], "time", x
    for j in range(e, x + 1):
        if (s.L[j] <= stop) if side > 0 else (s.H[j] >= stop):
            exit_px = (min(stop, s.O[j]) if side > 0 else max(stop, s.O[j])) if j > e else stop
            how, j_exit = "stop", j
            break
    cost = costs.round_trip(s.dt[e].hour, s.dt[j_exit].hour) * px
    gross = side * (exit_px - px)
    return dict(r, status="closed", exit_time=s.T[j_exit], exit=exit_px, exit_reason=how,
                net_bp=(gross - cost) / px * 1e4, R=(gross - cost) / r["stop_distance"])


def cmd_resolve(live_dir=LIVE_DIR, log=LOG):
    rows = _read_log(log)
    syms = {v[0] for v in WATCH.values()}
    series = {sym: _series(sym, live_dir) for sym in syms}
    costs = {sym: EC.Costs(sym) for sym in syms}
    out = [resolve_row(series[r["symbol"]], r, costs[r["symbol"]]) for r in rows]
    with open(log, "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print(f"resolved {sum(1 for a, b in zip(rows, out) if a != b)} row(s)")


def cmd_status(log=LOG):
    rows = _read_log(log)
    today = datetime.datetime.now(datetime.timezone.utc)
    started = datetime.datetime.fromisoformat(FORWARD_START.replace("Z", "+00:00"))
    for sym in WATCH:
        mine = [r for r in rows if r.get("component", f"E5_{r['symbol']}_{r['h']}") == sym]
        closed = [r for r in mine if r["status"] == "closed"]
        due = len(closed) >= STAGE_A_MIN_EVENTS or (today - started).days >= STAGE_A_MAX_DAYS
        mean = sum(r["net_bp"] for r in closed) / len(closed) if closed else None
        print(f"{sym}: logged {len(mine)}, closed {len(closed)}, refused {sum(r['status'] == 'refused' for r in mine)}; "
              f"stage (a) {'DUE: evaluate with edge_followup.py --stage forward' if due else 'not yet due'}"
              + (f"; paper mean net {mean:.2f} bp (information only, not the stage-(a) statistic)" if mean is not None else ""))


def _zone():
    import real_costs as RC
    return RC.server_zone(EC.PROVIDER)[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("scan", "resolve", "status"))
    a = ap.parse_args()
    {"scan": cmd_scan, "resolve": cmd_resolve, "status": cmd_status}[a.cmd]()


if __name__ == "__main__":
    main()
