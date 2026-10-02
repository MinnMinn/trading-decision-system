#!/usr/bin/env python3
"""I9 (red-team 2026-10-02): the point-in-time leakage probe (scripts/leakage.py, CLAUDE.md §37) run on the FUND engine
configuration at the fund decision timeframes (1m, 5m), with every ADOPTED_F_KEYS key ON and with the HTF-dependent values
(W7 `fx_w7_htf_target`, B3 `fx_b3=tfa_p5`, B-POOL `fx_b_pool=on`).

What the repo's existing probe tests do NOT cover (scripts/tests/test_backtesting.py, `TheRealEngineIsPointInTime`): they run
BTCUSDT 15m with the default OPTS and replace the future of the DECISION series only, through a `bt.load` stub that hands the
same candles to every timeframe. Here the future of EVERY context series (30m .. 1W) is replaced too, from the first bar that
had not CLOSED by the cut bar's close (`normalized.available_time`, the engine's own availability rule), so a higher-timeframe
bar read before it closed shows up as a moved decision. Same three mutations as the probe (scale, freeze, invert); the same
decision fields; records entered after the cut are excluded by the probe itself.

A probe that examined no decision passes vacuously, so every row reports `checked`; a row with checked == 0 is NOT a pass.
A positive control (`--variant control|b3control`) makes the engine read every higher-timeframe bar TWO periods early (a full
future bar: available_time - 2 x period); where a
decision depends on the HTF series it must be DETECTED, otherwise the sample is too small to be evidence of sensitivity.

Counts and pass/fail only: no R, no expectancy, no win rate is computed or printed.

  python3 scripts/research/leakage_probe_fund.py --hist /tmp/gapslices/xau-5m ...   # one slice root per run
"""
import argparse
import bisect
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import datetime  # noqa: E402
import leakage  # noqa: E402

CONTEXT_TFS = ("30m", "1H", "4H", "1D", "1W")
_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "4H": 240, "1D": 1440, "1W": 10080}


def bar_delta(tf):
    return datetime.timedelta(minutes=_MINUTES[tf])


DECISION_FIELDS = ("entry", "stop", "target", "side", "event", "R_planned")      # §37: the future may not move these
FIXED = {"flat_before_rollover": True, "rollover_provider": "mt5_bridge_ftmo"}


def adopted_keys():
    spec = importlib.util.spec_from_file_location("fund_search_probe", os.path.join(ROOT, "scripts", "fund-search.py"))
    fs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fs)
    return fs.ADOPTED_F_KEYS, fs.fixed_opts()


def fresh_bt():
    spec = importlib.util.spec_from_file_location("bt_leak_probe", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    return bt


def _key(rec):
    return (rec.get("symbol"), rec.get("side"), rec.get("event"), rec.get("entry_time"))


def probe_one(sym, tf, method, overlay, bars, cut_frac=0.7, control=False, n_cuts=0):
    """leakage.probe over the last `bars` decision bars of the slice root selected by BT_HISTORY_ROOT.

    `n_cuts == 0`: one cut at `cut_frac` of the series. `n_cuts > 0`: that many cuts, each placed AT a decision the baseline run
    produced (entry bar == cut bar), so a read of a higher-timeframe bar that had not closed by that decision (one still
    forming, whose later part is mutated) can move exactly that decision. A probe cut in the middle of nowhere only has
    power for the few decisions within one HTF bar of the cut, which is why the cuts are anchored on decisions."""
    bt0 = fresh_bt()
    full, _src = bt0.load(sym, tf)
    series = full[-bars:]
    delta = bar_delta(tf)
    ctx_real = {}
    for t in CONTEXT_TFS:
        if bar_delta(t) > delta:
            cs, _ = bt0.load(sym, t)
            if cs:
                ctx_real[t] = cs
    ctx_avail = {t: [bt0._N.available_time(b, t) for b in cs] for t, cs in ctx_real.items()}
    state = {}                                 # per cut: mutated decision series and context cut indices

    def run(candles):
        bt = fresh_bt()                       # fresh caches (_HTF_TIMES, _HTF_TR_CACHE, _WY_CANDIDATES) for every run
        if candles is series:
            ctx = ctx_real
        else:
            mode = next(m for m in leakage.MODES if candles == state["mutated"][m])
            ctx = {t: leakage.mutate_future(cs, state["ctx_cut"][t], mode) for t, cs in ctx_real.items()}
        if control:                           # POSITIVE CONTROL: every HTF bar becomes readable 2 periods early (a full future bar)
            real_av = bt._N.available_time

            def early(c, t, _real=real_av):
                return _real(c, t) - 2 * bar_delta(t) if t in ctx_real else _real(c, t)
            bt._N.available_time = early
        real_load = bt.load

        def load(s, t):
            if s == sym and t == tf:
                return candles, "injected"
            if s == sym and t in ctx:
                return ctx[t], "injected"
            return real_load(s, t)
        bt.load = load
        try:
            sc = bt.scan(sym, tf, only=(method,), opts=overlay)
            return list(sc["trades"][method]) if sc else []
        finally:
            if control:
                bt._N.available_time = real_av

    base_cache = {}

    def run_cached(candles):                  # the baseline (unmutated) run is identical for every cut: do it once
        if candles is series:
            if "r" not in base_cache:
                base_cache["r"] = run(candles)
            return list(base_cache["r"])
        return run(candles)

    if n_cuts:
        entries = sorted({leakage.index_of_time(series, r["entry_time"]) for r in run_cached(series)} - {None})
        entries = [i for i in entries if i >= int(len(series) * 0.3) and i < len(series) - 1]
        step = max(1, len(entries) // n_cuts)
        cuts = entries[::step][:n_cuts]
    else:
        cuts = [int(len(series) * cut_frac)]
    checked = violations = 0
    first = None
    for cut in cuts:
        cut_close = bt0._N.available_time(series[cut], tf)
        state["mutated"] = {m: leakage.mutate_future(series, cut, m) for m in leakage.MODES}
        state["ctx_cut"] = {t: bisect.bisect_right(av, cut_close) - 1 for t, av in ctx_avail.items()}
        rep = leakage.probe(run_cached, series, cut, key=_key, decision_fields=DECISION_FIELDS)
        checked += rep["checked"]
        violations += len(rep["violations"])
        if not rep["ok"] and first is None:
            first = leakage.describe(rep)
    return {"sym": sym, "tf": tf, "method": method, "bars": len(series), "cuts": cuts, "checked": checked,
            "ok": violations == 0, "violations": violations, "first_violation": first,
            "context_series_mutated": sorted(ctx_real)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--hist", required=True, help="a BT_HISTORY_ROOT slice holding the symbol on every timeframe")
    ap.add_argument("--sym", required=True)
    ap.add_argument("--tf", required=True, choices=("1m", "5m"))
    ap.add_argument("--bars", type=int, default=3000)
    ap.add_argument("--cuts", type=int, default=0, help="0 = one cut at 70%% of the series; N = N cuts anchored on decisions")
    ap.add_argument("--method", choices=("ICT", "WYCKOFF-BOOK"), required=True)
    ap.add_argument("--variant", default="adopted",
                    help="adopted | b3 | pool | control | b3control (the two controls read HTF bars 2 periods early and "
                         "must be DETECTED where a decision depends on the HTF series: B3 tfa_p5, W7)")
    a = ap.parse_args(argv)
    os.environ["BT_HISTORY_ROOT"] = a.hist
    adopted, fixed = adopted_keys()
    overlay = dict(fixed)                                            # flat_before_rollover + every ADOPTED key ON (incl. fx_gap_fill)
    if a.variant in ("b3", "b3control"):
        overlay["fx_b3"] = "tfa_p5"
    elif a.variant == "pool":
        overlay["fx_b_pool"] = "on"
    assert all(overlay.get(k) is True for k in adopted), "an ADOPTED key is not ON in the probe overlay"
    row = probe_one(a.sym, a.tf, a.method, overlay, a.bars, control=a.variant in ("control", "b3control"), n_cuts=a.cuts)
    row.update(variant=a.variant, adopted_keys_on=list(adopted))
    print(json.dumps(row, sort_keys=True))
    return 0 if (row["ok"] and row["checked"] > 0) or a.variant in ("control", "b3control") else 1


if __name__ == "__main__":
    sys.exit(main())
