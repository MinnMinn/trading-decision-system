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
COMPONENTS = {"XAUUSD": 24, "US500": 48}
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


def signals(s, sym, h):
    """Every E5 signal of `s` entering at/after FORWARD_START, as log rows (unresolved)."""
    out = []
    for ev in EC.ev_fvg(s):
        e = ev["entry_i"]
        if s.T[e] < FORWARD_START:
            continue
        row = {"symbol": sym, "h": h, "side": ev["side"], "signal_time": s.T[ev["i"]], "entry_time": s.T[e],
               "entry": ev["entry_px"], "far_edge": ev["far"], "status": "open"}
        sig = s.sigma(ev["i"])
        if not sig or not _vol_fresh(s, ev["i"]):
            row.update(status="refused", reason="volatility history stale or missing (re-export the 5m history)")
        else:
            dist = 2.0 * sig * math.sqrt(h) * ev["entry_px"]
            row.update(stop=ev["entry_px"] - ev["side"] * dist, stop_distance=dist)
        out.append(row)
    return out


def cmd_scan(live_dir=LIVE_DIR, log=LOG):
    have = {(r["symbol"], r["entry_time"], r["side"]) for r in _read_log(log)}
    new = []
    for sym, h in COMPONENTS.items():
        s = EC.Series(sym, merged_candles(sym, live_dir), _zone(), end="9999-12-31T00:00:00Z", sigma_every_day=True)
        for r in signals(s, sym, h):
            if (sym, r["entry_time"], r["side"]) not in have:
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
    series = {sym: EC.Series(sym, merged_candles(sym, live_dir), _zone(), end="9999-12-31T00:00:00Z", sigma_every_day=True) for sym in COMPONENTS}
    costs = {sym: EC.Costs(sym) for sym in COMPONENTS}
    out = [resolve_row(series[r["symbol"]], r, costs[r["symbol"]]) for r in rows]
    with open(log, "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print(f"resolved {sum(1 for a, b in zip(rows, out) if a != b)} row(s)")


def cmd_status(log=LOG):
    rows = _read_log(log)
    today = datetime.datetime.now(datetime.timezone.utc)
    started = datetime.datetime.fromisoformat(FORWARD_START.replace("Z", "+00:00"))
    for sym in COMPONENTS:
        mine = [r for r in rows if r["symbol"] == sym]
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
