#!/usr/bin/env python3
"""B24 (2026-10-02): W7 (`fx_w7_htf_target`) point-in-time probe on REAL data, with enough Phase-D decisions to have power.

The red-team probe (scripts/research/leakage_probe_fund.py) checked 66 W7 decisions per timeframe and its positive control (an HTF bar read
two periods early) did NOT fire for W7, so its PASS meant "nothing found". This probe asks W7 itself, on real XAUUSD / index slices:

  1. run the fund engine configuration (every ADOPTED_F_KEYS key ON, flat-before-rollover) through `bt.scan(only=("WYCKOFF-BOOK",))` on a
     slice of the decision timeframe, with the REAL higher-timeframe rung (`bt.HTF_OF[tf]`: 1m -> 5m, 5m -> 30m) served from the same
     years, and RECORD every `_htf_wyckoff_target(sym, tf, side, decision_time)` call the engine makes for a Phase-D leg (the baseline
     answer);
  2. for each such decision time t, serve the HTF series with every bar whose availableTime (open + one period, normalized.available_time)
     is > t (strictly) (a) DELETED, (b) replaced by a huge spike UP, (c) replaced by a spike DOWN, and require the SAME answer;
  3. POSITIVE CONTROL on the same decisions: the HTF prefix is cut one period too late (the still-forming HTF bar becomes readable); the
     same comparison must then report mismatches.

Counts and pass/fail only: no R, no expectancy, no win rate is computed or printed.  Nothing is copied: the history parts are read in
place (read-only) and only the years named are loaded; the decision series' own past before the slice is simply absent (dropping the early
past cannot leak the future, CLAUDE.md §8).

  python3 scripts/research/pit_w7_real.py --sym XAUUSD --tf 5m --years 2022,2023 --max-legs 400
"""
import argparse
import bisect
import contextlib
import datetime
import gzip
import importlib.util
import json
import os
import sys
import time
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
UTC = datetime.timezone.utc
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "2H": 120, "4H": 240, "1D": 1440}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read_years(root, sym, tf, years, until):
    """The candles of the named year parts of a split-gz history series (read-only), ascending, strictly increasing in time, whose OPEN
    label is before `until` (the development cutoff by default: no bar of the held-out period is ever loaded)."""
    d = os.path.join(root, f"ohlcv.{sym}.{tf}")
    out, prev = [], None
    for y in years:
        with gzip.open(os.path.join(d, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
            for c in json.load(fh)["candles"]:
                if c["time"] >= until:
                    break
                if prev is not None and c["time"] <= prev:
                    raise ValueError(f"{d} {y}: bar {c['time']} is not after {prev}")
                prev = c["time"]
                out.append(c)
    return out


def spiked(row, up):
    x = row["close"]
    f = 1000.0 if up else 0.001
    return dict(row, open=x * f, high=x * f * 1.5 if up else x * f * 1.0001, low=x * f * 0.9 if up else x * f * 0.9999, close=x * f,
                volume=row.get("volume", 0) * 1e6 + 1.0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.join(ROOT, "data", "history", "ftmo"))
    ap.add_argument("--sym", required=True)
    ap.add_argument("--tf", required=True, choices=("1m", "5m"))
    ap.add_argument("--years", required=True, help="comma separated year parts of the decision series (and of its HTF rung)")
    ap.add_argument("--max-legs", type=int, default=400, help="check at most this many Phase-D decisions (the first ones in time)")
    ap.add_argument("--control-legs", type=int, default=0, help="positive control on the first N checked decisions (0 = all of them)")
    ap.add_argument("--until", default=None, help="exclusive upper bound of every loaded bar (default: fund_stats.DEV_CUTOFF, the development cutoff)")
    ap.add_argument("--warm-bars", type=int, default=0, help="drop the first N decision bars (none by default)")
    a = ap.parse_args(argv)
    years = [int(y) for y in a.years.split(",")]
    bt = _load("bt_pit_w7_real", "scripts/backtest-methods.py")
    fs = _load("fund_search_pit_w7_real", "scripts/fund-search.py")
    htf = bt.HTF_OF[a.tf]
    import fund_stats
    until = a.until or fund_stats.DEV_CUTOFF
    ltf_rows = read_years(a.root, a.sym, a.tf, years, until)[a.warm_bars:]
    htf_rows = read_years(a.root, a.sym, htf, years, until)
    per = datetime.timedelta(minutes=MINUTES[htf])
    parse = lambda s: datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    # the engine's own availability rule, evaluated once per HTF bar (normalized.available_time)
    avail = [bt._N.available_time(r, htf) for r in htf_rows]
    assert all(avail[i] <= avail[i + 1] for i in range(len(avail) - 1)), "the HTF slice is not non-decreasing in availableTime"
    overlay = fs.fixed_opts()
    assert all(overlay.get(k) is True for k in fs.ADOPTED_F_KEYS)
    served = {a.tf: ltf_rows, htf: htf_rows}
    real_load = bt.load

    def load(s, t):
        if s == a.sym and t in served:
            return list(served[t]), "injected"
        return real_load(s, t)
    bt.load = load

    # ---- 1. baseline scan, recording every W7 call made for a Phase-D leg --------------------------------------------------------------
    asked = []
    real_target = bt._htf_wyckoff_target

    def spy(sym, tf, side, dt):
        ans = real_target(sym, tf, side, dt)
        asked.append((side, dt, ans))
        return ans
    bt._htf_wyckoff_target = spy
    t0 = time.time()
    sc = bt.scan(a.sym, a.tf, only=("WYCKOFF-BOOK",), opts=overlay)
    bt._htf_wyckoff_target = real_target
    scan_s = time.time() - t0
    n_trades = len(sc["trades"]["WYCKOFF-BOOK"]) if sc else 0
    legs = asked[:a.max_legs]

    # ---- 2./3. per decision: the answer with the future of the HTF series deleted / spiked, clean and under the control ------------------
    def answer(series, side, dt, leaky):
        served[htf] = series
        for d in (bt._HTF_TR_CACHE, bt._HTF_SERIES, bt._HTF_TIMES):
            d.clear()
        ctx = mock.patch.multiple(bt._HtfSeries, prefix_len=_leaky_len(bt, per)) if leaky else contextlib.nullcontext()
        with ctx, (mock.patch.object(bt._pit, "series_as_of", _leaky_asof(bt, per)) if leaky else contextlib.nullcontext()):
            return real_target(a.sym, a.tf, side, dt)

    def variants(t):
        """the HTF rows as they would read were every bar with availableTime > t different: (delete, spike up, spike down)."""
        m = bisect.bisect_right(avail, t)
        keep = htf_rows[:m]
        return {"delete": keep,
                "up": keep + [spiked(r, True) for r in htf_rows[m:]],
                "down": keep + [spiked(r, False) for r in htf_rows[m:]]}

    def run(leaky, limit):
        mism, nonnull, n = [], 0, 0
        for (side, dt, ans) in legs[:limit]:
            t = parse(dt)
            base = answer(htf_rows, side, dt, True) if leaky else ans
            nonnull += base is not None
            n += 1
            for mode, series in variants(t).items():
                got = answer(series, side, dt, leaky)
                if got != base:
                    mism.append((side, dt, mode))
        served[htf] = htf_rows
        return n, nonnull, mism

    bt.OPTS = dict(bt._OPTS_BASE, **overlay)       # scan(opts=) restores OPTS on exit; the per-decision answers use the same overlay
    t0 = time.time()
    n, nonnull, mism = run(False, len(legs))
    clean_s = time.time() - t0
    t0 = time.time()
    cn, cnonnull, cmism = run(True, a.control_legs or len(legs))
    control_s = time.time() - t0
    row = {"sym": a.sym, "tf": a.tf, "htf": htf, "years": years, "until": until, "first_bar": ltf_rows[0]["time"], "last_bar": ltf_rows[-1]["time"], "ltf_bars": len(ltf_rows), "htf_bars": len(htf_rows),
           "phase_d_decisions_asked": len(asked), "decisions_checked": n, "target_not_none": nonnull,
           "mutations_per_decision": 3, "violations": len(mism), "first_violation": mism[0] if mism else None,
           "ok": not mism and n > 0,
           "control": {"decisions": cn, "target_not_none": cnonnull, "mismatches": len(cmism),
                       "decisions_with_a_mismatch": len({(s, d) for (s, d, _m) in cmism}), "fired": bool(cmism)},
           "scan_trades_found": n_trades, "seconds": {"scan": round(scan_s), "clean": round(clean_s), "control": round(control_s)}}
    print(json.dumps(row, sort_keys=True, default=str))
    return 0 if row["ok"] and row["control"]["fired"] else 1


def _leaky_len(bt, per):
    real_len = bt._HtfSeries.prefix_len

    def prefix_len(self, decision_time):
        return real_len(self, bt._pit._aware(decision_time) + per)
    return prefix_len


def _leaky_asof(bt, per):
    real_asof = bt._pit.series_as_of

    def series_as_of(c, tf, decision_time, symbol=None):
        return real_asof(c, tf, bt._pit._aware(decision_time) + per, symbol=symbol)
    return series_as_of


if __name__ == "__main__":
    sys.exit(main())
