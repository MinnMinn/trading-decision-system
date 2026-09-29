#!/usr/bin/env python3
"""Read-only METHOD DIAGNOSIS on DEVELOPMENT data: where do ICT / WYCKOFF-BOOK candidates die, and how do the
surviving trades lose?

Why this exists: the pre-registered prop-challenge search (scripts/prop-search.py, 2026-09-28) evaluated 180
candidates and 0 passed -- 130/180 had too few validation trades and every candidate's expectancy lower bound
was negative. The owner chose to improve the methodology. Step 1 is this diagnosis, and it may ONLY look at the
development window (everything available before DEV_CUTOFF), because the validation window is exposed and must
not influence method changes (CLAUDE.md §9, §44).

What it does, and what it deliberately does NOT do:
  * It runs the UNMODIFIED engine (scripts/backtest-methods.py `scan()`), loaded fresh via
    scripts/stability-report.py exactly as prop-search's `_load_sr()` does, under `bt.pit_cutoff(DEV_CUTOFF)`
    (the engine's own load-time PIT seam, CLAUDE.md §8). A cutoff later than DEV_CUTOFF is refused.
  * The gate funnel is obtained by wrapping engine / scanner functions FROM OUTSIDE, in this process only
    (module attributes replaced by counting pass-through wrappers, restored in `finally`). No engine file is
    edited. Each wrapper returns exactly what the wrapped function returned, so the trades are unchanged --
    `check_equality()` proves that against a plain `bt.scan()` (scripts/tests/test_diagnose_methods.py).
  * Two kinds of numbers appear and are labelled as such:
      - OBSERVED: counted from a wrapped call's arguments / return value.
      - INFERRED: a gate that runs inline inside an engine function with no call to wrap (ICT's dedup /
        MSS-index / expiry checks; WYCKOFF-BOOK's per-record leg conditions inside `_fires_from`). These are
        re-derived from the engine's own record fields with the same conditions, and every inferred count is
        cross-checked against an observed one (`consistency` block): a non-zero mismatch means the inference
        is wrong and that stage must not be trusted.
  * It changes no methodology, proposes no rule, and writes nothing outside the output path it is given.

Usage:
  diagnose-methods.py run   --symbol XAUUSD --tf 1H --method ICT --config A --out PATH.json
  diagnose-methods.py batch --out-dir DIR [--timeout 1800]      # the audit's slice list, one subprocess each
  diagnose-methods.py equality --symbol XAUUSD --tf 4H --method ICT --config C
  diagnose-methods.py report --in-dir DIR                         # markdown tables from DIR/*.json
"""
import argparse, bisect, collections, importlib.util, json, os, statistics, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEV_CUTOFF = "2024-03-01T00:00:00Z"   # prop-search VALIDATION_START: development ends here (exclusive)
METHODS = ("ICT", "WYCKOFF-BOOK")

# The audit's slice list (task 2026-09-28): both methods x config A x 15m/1H/4H x XAUUSD/US500/DE40, plus
# configs B and C on 1H only.
AUDIT_SYMBOLS = ("XAUUSD", "US500", "DE40")


def audit_slices():
    out = []
    for method in METHODS:
        for tf in ("15m", "1H", "4H"):
            for cfg in (("A", "B", "C") if tf == "1H" else ("A",)):
                for sym in AUDIT_SYMBOLS:
                    out.append((sym, tf, method, cfg))
    return out


def load_sr():
    """A fresh stability-report module (and with it a fresh backtest-methods `bt`), as prop-search._load_sr()."""
    spec = importlib.util.spec_from_file_location("sr_diag", os.path.join(ROOT, "scripts", "stability-report.py"))
    sr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sr)
    return sr


def _check_cutoff(cutoff):
    # ISO-8601 Z strings compare chronologically; refuse anything that would reach into validation.
    if not isinstance(cutoff, str) or not cutoff.endswith("Z") or cutoff > DEV_CUTOFF:
        raise ValueError(f"cutoff {cutoff!r} refused: this diagnosis may only read data before {DEV_CUTOFF}")


# Engine options to switch on for this run (the fx_ fidelity keys), set by `run --set KEY`. Empty = v1.
EXTRA_OVERLAY = {}


def _overlay(sr, cfg):
    return {**sr.config_opts(sr.CONFIGS[cfg], ict_target="range"), **EXTRA_OVERLAY}


# ------------------------------------------------------------------------------------------ instrumentation

class _Patch:
    """Replace attributes on module objects for the duration of a `with`, restore them afterwards."""

    def __init__(self):
        self._saved = []

    def set(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def restore(self):
        while self._saved:
            obj, name, value = self._saved.pop()
            setattr(obj, name, value)


ICT_STAGES = (
    "bars_scanned",            # OBSERVED  lr.read_at called
    "full_live_window",        # OBSERVED  read_at returned facts (live never scans a partial window)
    "sweep_mss_candidate",     # OBSERVED  setup_candidate returned a candidate (recent sweep -> same-direction MSS, target exists)
    "mss_displacement",        # OBSERVED  candidate not refused for missing displacement
    "fvg_complete",            # OBSERVED  candidate complete (same-direction FVG after the sweep)
    "pd_ok",                   # OBSERVED  entry in discount (long) / premium (short) of the dealing range
    "ltf_bias_agrees",         # OBSERVED  bias_allows(bias_at(...)) True
    "htf_gate",                # OBSERVED  htf_bias_gate True (config C only; otherwise pass-through)
    "new_setup",               # INFERRED  not already taken at an earlier bar (engine's own `seen` key)
    "not_expired",             # INFERRED  MSS bar found and i <= mss_i + K
    "not_already_triggered",   # OBSERVED  first fvg_fill (to bar i) returned None
    "limit_filled",            # OBSERVED  second fvg_fill returned a fill
    "booked",                  # OBSERVED  walk returned a trade, or same-bar fill+stop booked as -1R
)

WY_LEGS = ("spring", "phase_d")


class IctProbe:
    """Counting wrappers around the functions ict_setups_live() calls, in the order it calls them."""

    def __init__(self, bt):
        self.bt = bt
        self.bar_stage = collections.Counter()      # furthest stage reached per bar
        self.setup_stage = {}                       # (side, sweep_t, mss_t) -> furthest stage index
        self.incomplete = collections.Counter()     # why a candidate was incomplete (first words of `missing`)
        self.bias_refused = collections.Counter()   # bias value when bias_allows refused (per bar)
        self.bias_refused_setups = {}               # key -> set of bias values seen while refused
        self.htf_results = collections.Counter()
        self.side_booked = collections.Counter()
        self.inconsistent = collections.Counter()
        self.seen = set()
        self.ctx = None
        self.in_htf = 0
        self.Tm = None; self.idx = None; self.K = None; self.n = None

    # --- per-bar context -------------------------------------------------------------------------------
    def _finish(self):
        c = self.ctx
        self.ctx = None
        if c is None:
            return
        st = c["stage"]
        key = c.get("key")
        I = ICT_STAGES.index
        if st == I("htf_gate"):
            # passed bias (and htf when asked): the engine now runs its inline dedup / MSS / expiry checks,
            # re-derived here (INFERRED) and cross-checked against whether fvg_fill was then called (OBSERVED).
            if key not in self.seen:
                self.seen.add(key)
                st = I("new_setup")
                mss_i = self.idx.get(c["su"]["mss"]["time"])
                if mss_i is not None and c["i"] <= mss_i + self.K:
                    st = I("not_expired")
            calls = c["fvg_calls"]
            if bool(calls) != (st == I("not_expired")):
                self.inconsistent["inferred_dedup_expiry_vs_fvg_fill_call"] += 1
            if calls:
                st = I("not_expired")
                if calls[0] is None:
                    st = I("not_already_triggered")
                    if len(calls) > 1 and calls[1] is not None:
                        st = I("limit_filled")
                        if calls[1][1] == "filled_and_stopped" or c.get("walked"):
                            st = I("booked")
                            self.side_booked[c["su"]["side"]] += 1
        self.bar_stage[ICT_STAGES[st]] += 1
        if key is not None:
            self.setup_stage[key] = max(self.setup_stage.get(key, -1), st)

    # --- wrappers ---------------------------------------------------------------------------------------
    def install(self, patch):
        bt = self.bt; lr = bt.lr; iscan = lr.ict_scan
        o_setups, o_read, o_cand = bt.ict_setups_live, lr.read_at, iscan.setup_candidate
        o_bias_at, o_allows, o_htf = lr.bias_at, bt.bias_allows, bt.htf_bias_gate
        o_fill, o_walk = bt.fvg_fill, bt.walk
        probe = self

        def ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, methods):
            probe.Tm = Tm; probe.idx = {t: j for j, t in enumerate(Tm)}; probe.K = bt.P[tf]["K"]; probe.n = len(c)
            try:
                return o_setups(sym, tf, c, Tm, HZ, H, L, C, methods)
            finally:
                probe._finish()

        def read_at(candles, i, tf, methods, opts=None):
            # B1/Batch-1a (docs/plans/2026-09-29-execution-plan.md "Shared contract"): the probe must pass the
            # fx_ overlay through unchanged, not silently drop it back to v1 -- ict_setups_live() (o_setups,
            # unwrapped) is the one that actually builds fx_opts and calls this wrapper with it.
            r = o_read(candles, i, tf, methods, opts=opts)
            if probe.in_htf:
                return r
            probe._finish()
            probe.ctx = dict(i=i, stage=ICT_STAGES.index("bars_scanned" if r is None else "full_live_window"),
                             fvg_calls=[])
            return r

        def setup_candidate(a, c, lookback, opts=None):
            su = o_cand(a, c, lookback, opts=opts)
            ctx = probe.ctx
            if ctx is not None and not probe.in_htf and su:
                ctx["su"] = su
                ctx["key"] = (su["side"], su["sweep"]["time"], su["mss"]["time"])
                if not su.get("complete"):
                    miss = (su.get("missing") or "?")
                    if miss.startswith("displacement"):
                        ctx["stage"] = ICT_STAGES.index("sweep_mss_candidate"); probe.incomplete["no_displacement"] += 1
                    else:
                        ctx["stage"] = ICT_STAGES.index("mss_displacement"); probe.incomplete["no_fvg"] += 1
                elif not su.get("pd_ok"):
                    ctx["stage"] = ICT_STAGES.index("fvg_complete")
                else:
                    ctx["stage"] = ICT_STAGES.index("pd_ok")
            return su

        def bias_at(candles, i, tf, methods, facts=None):
            r = o_bias_at(candles, i, tf, methods, facts=facts)
            if not probe.in_htf and probe.ctx is not None:
                probe.ctx["bias"] = r[0]
            return r

        def bias_allows(bias, side):
            ok = o_allows(bias, side)
            if not probe.in_htf and probe.ctx is not None:
                if ok:
                    probe.ctx["stage"] = ICT_STAGES.index("ltf_bias_agrees")
                    if not bt.OPTS["htf"]:
                        probe.ctx["stage"] = ICT_STAGES.index("htf_gate")
                else:
                    probe.bias_refused[str(bias)] += 1
                    probe.bias_refused_setups.setdefault(probe.ctx.get("key"), set()).add(str(bias))
            return ok

        def htf_bias_gate(sym, tf, side, decision_time, methods):
            probe.in_htf += 1
            try:
                r = o_htf(sym, tf, side, decision_time, methods)
            finally:
                probe.in_htf -= 1
            probe.htf_results[repr(r)] += 1
            if probe.ctx is not None and r is True:
                probe.ctx["stage"] = ICT_STAGES.index("htf_gate")
            return r

        def fvg_fill(side, mss, edge, far, stop, H, L, K, n):
            r = o_fill(side, mss, edge, far, stop, H, L, K, n)
            if probe.ctx is not None:
                probe.ctx["fvg_calls"].append(r)
            return r

        def walk(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=None):
            r = o_walk(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=Tm)
            if probe.ctx is not None and r:
                probe.ctx["walked"] = True
            return r

        patch.set(bt, "ict_setups_live", ict_setups_live)
        patch.set(lr, "read_at", read_at)
        patch.set(iscan, "setup_candidate", setup_candidate)
        patch.set(lr, "bias_at", bias_at)
        patch.set(bt, "bias_allows", bias_allows)
        patch.set(bt, "htf_bias_gate", htf_bias_gate)
        patch.set(bt, "fvg_fill", fvg_fill)
        patch.set(bt, "walk", walk)

    def summary(self, htf_on):
        per_bar_reached = _reached(self.bar_stage, ICT_STAGES)
        setups = collections.Counter(ICT_STAGES[s] for s in self.setup_stage.values())
        per_setup_reached = _reached(setups, ICT_STAGES)
        refused_by_bias = collections.Counter()
        for k, s in self.setup_stage.items():
            if s == ICT_STAGES.index("pd_ok"):
                for b in self.bias_refused_setups.get(k, ()):
                    refused_by_bias[b] += 1
        return dict(
            stages=list(ICT_STAGES),
            bars_reaching=per_bar_reached,
            unique_setups_reaching=per_setup_reached,
            unique_setups_note="unique (side, sweep time, MSS time); a setup is visible on many bars, so bar "
                               "counts from sweep_mss_candidate to htf_gate are inflated by persistence. From "
                               "new_setup on, each setup is counted once, at its first qualifying bar.",
            incomplete_reason_bars=dict(self.incomplete),
            bias_refused_bars=dict(self.bias_refused),
            bias_values_on_setups_stopped_at_bias=dict(refused_by_bias),
            htf_gate_results=dict(self.htf_results) if htf_on else "not applied (config has htf=False)",
            booked_by_side=dict(self.side_booked),
            observed=[s for s in ICT_STAGES if s not in ("new_setup", "not_expired")],
            inferred=["new_setup", "not_expired"],
            not_observable=["setup_candidate returning None is ONE stage: 'no recent sweep', 'no MSS after it', "
                            "'MSS direction does not match the sweep' and 'no target above/below entry' all "
                            "return None inside ict-scan.setup_candidate with no distinguishing call"],
            consistency=dict(self.inconsistent),
        )


def _reached(counter_of_furthest, stages):
    """Counter of furthest stage -> {stage: number that reached AT LEAST that stage}."""
    out, run = {}, 0
    for s in reversed(stages):
        run += counter_of_furthest.get(s, 0)
        out[s] = run
    return {s: out[s] for s in stages}


class WyProbe:
    """Counting wrappers for scan()'s WYCKOFF-BOOK branch: detection, candidates, _fires_from, htf gate, walk."""

    def __init__(self, bt):
        self.bt = bt
        self.W = bt.W
        self.Tm = None; self.win = bt.WYCKOFF_WINDOW
        self.calls = collections.Counter()           # side -> _wyckoff_candidates calls (= windows)
        self.win_with_cand = collections.Counter()   # side -> windows with >= 1 candidate
        self.structures = {}                          # (side, sc_t, ar_t) -> latest record summary
        self.cand_structs = {}                        # (side, sc_t, ar_t) -> spring-leg fate
        self.fires = collections.Counter()           # leg -> fire events (pre-dedup)
        self.fire_keys = {}                           # (side, t0, leg) -> "fired"
        self.inconsistent = collections.Counter()
        self.htf_results = collections.Counter()
        self.walk_calls = collections.Counter()
        self.pending_leg = None
        self._last_recs = None
        self._in_dist = 0

    def _summ(self, r, a, Tm):
        g = lambda j: Tm[a + j] if j is not None else None
        return dict(path=r["path"], shakeout=r["shakeout"], abandon=r["abandon"], sot_too_strong=r["sot_too_strong"],
                    vol_type=r["vol_type"], reclaim=r["reclaim"] is not None, test=r["test"] is not None,
                    sos=r["sos"] is not None, bu=r["bu"] is not None, sloped=r["sloped"], st_sign=r["st_sign"],
                    phase_b_sign=r["phase_b_sign"], spring_t=g(r["spring"]))

    def _leg_reason(self, side, r, C):
        """Replicates _fires_from's SPRING-leg conditions for one record on this window's last bar (INFERRED)."""
        bt = self.bt; O = bt.OPTS; last = len(C) - 1
        if O["st_gate"] and r.get("st_sign") == "contradicts": return "st_gate"
        if O["phase_b_gate"] and r.get("phase_b_sign") == "contradicts": return "phase_b_gate"
        if O["sloped_gate"] and r["sloped"]: return "sloped_gate"
        if O["st_min"] is not None and r["st_pct"] < O["st_min"]: return "st_min"
        if r["path"] != "spring": return "lps_c_path(no spring leg)"
        if r["shakeout"]: return "shakeout"
        if r["abandon"]: return "abandon(VP/LVN)"
        if r["sot_too_strong"]: return "sot_too_strong"
        if r["vol_type"] not in O["types"]: return f"vol_type_{r['vol_type']}_excluded"
        vt, rr = r["vol_type"], r["rec_ratio"]
        reclaim_entry = O["entry"] == "book" and (
            (side == "long" and (vt == 1 or (vt == 3 and rr is not None and rr >= bt.VOL["high_min_ratio"])))
            or (side == "short" and vt in (1, 2)))
        w_bar = r["reclaim"] if reclaim_entry else r["test"]
        if w_bar is None: return "no_test(entry bar never exists)"
        if w_bar != last: return "_not_entry_bar"
        stop = r["spring_low"] * (1 - bt.STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + bt.STOP_BUFFER_PCT)
        target = r["tr_hi"] if side == "long" else r["tr_lo"]
        ok = (target > C[last] > stop) if side == "long" else (target < C[last] < stop)
        return "fired" if ok else "not_placeable(close beyond stop/target)"

    def install(self, patch):
        bt, W = self.bt, self.W; probe = self
        o_cands, o_fires, o_htf, o_walk = bt._wyckoff_candidates, bt._fires_from, bt.htf_bias_gate, bt.walk
        o_acc, o_dist = W.detect_accumulations, W.detect_distributions

        def detect_accumulations(*a, **k):
            r = o_acc(*a, **k)
            if not probe._in_dist:
                probe._last_recs = r
            return r

        def detect_distributions(*a, **k):
            probe._in_dist += 1
            try:
                r = o_dist(*a, **k)
            finally:
                probe._in_dist -= 1
            probe._last_recs = r
            return r

        def _wyckoff_candidates(side, O, H, L, C, V, tf, sym):
            # A1 (docs/plans/2026-09-28-methodology-improvement-plan.md §2, ADR 0009): bt._wyckoff_candidates()
            # is routed through scripts/structures.py's raw `wyckoff_records()` pass-through (A1 code review
            # round 1, item 4 -- the hot path builds no enriched/timestamped envelope), so its signature is
            # unchanged from before A1. This wrapper's own signature therefore needed no change either.
            probe._last_recs = None
            out = o_cands(side, O, H, L, C, V, tf, sym)
            k = probe.win + probe.calls[side]; probe.calls[side] += 1; a = k - probe.win
            Tm = probe.Tm
            for r in probe._last_recs or ():
                key = (side, Tm[a + r["sc"]], Tm[a + r["ar"]])
                probe.structures[key] = probe._summ(r, a, Tm)
            if out:
                probe.win_with_cand[side] += 1
            return out

        def _fires_from(side, recs, C, Tm, sym=None, tf=None):
            # W7 (fx_w7_htf_target, docs/plans/2026-09-28-methodology-improvement-plan.md §3): backtest-methods
            # now passes sym/tf through to `_fires_from` so its Phase-D branch can load the HTF companion
            # series -- forwarded unchanged here; this probe's own SPRING-leg replication (`_leg_reason`) does
            # not need either (phase_d is observed-only in this probe, per its own docstring).
            out = o_fires(side, recs, C, Tm, sym=sym, tf=tf)
            n_spring_inferred = 0
            for r in recs:
                key = (side, Tm[r["sc"]], Tm[r["ar"]])
                reason = probe._leg_reason(side, r, C)
                if reason == "fired":
                    n_spring_inferred += 1
                if reason != "_not_entry_bar":
                    prev = probe.cand_structs.get(key)
                    if prev != "fired":
                        probe.cand_structs[key] = reason
                else:
                    probe.cand_structs.setdefault(key, "_not_entry_bar")
            n_spring_obs = sum(1 for f in out if f["leg"] == "spring")
            if n_spring_obs != n_spring_inferred:
                probe.inconsistent["spring_leg_inferred_vs_observed"] += 1
            for f in out:
                probe.fires[f["leg"]] += 1
                probe.fire_keys.setdefault((side, f["t0"], f["leg"]), f["leg"])
            return out

        def htf_bias_gate(sym, tf, side, decision_time, methods):
            r = o_htf(sym, tf, side, decision_time, methods)
            probe.htf_results[repr(r)] += 1
            return r

        def walk(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=None):
            r = o_walk(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=Tm)
            probe.walk_calls["trade" if r else "none"] += 1
            return r

        patch.set(W, "detect_accumulations", detect_accumulations)
        patch.set(W, "detect_distributions", detect_distributions)
        patch.set(bt, "_wyckoff_candidates", _wyckoff_candidates)
        patch.set(bt, "_fires_from", _fires_from)
        patch.set(bt, "htf_bias_gate", htf_bias_gate)
        patch.set(bt, "walk", walk)

    def summary(self, trades, htf_on):
        by_side = collections.defaultdict(collections.Counter)
        for (side, _sc, _ar), s in self.structures.items():
            c = by_side[side]; c["structures"] += 1; c["path_" + s["path"]] += 1
            if s["path"] == "spring":
                for f in ("shakeout", "abandon", "sot_too_strong", "reclaim", "test", "sos", "bu", "sloped"):
                    c[f] += bool(s[f])
                c[f"vol_type_{s['vol_type']}"] += 1
            else:
                c["lps_c_bu"] += bool(s["bu"])
        fate = collections.defaultdict(collections.Counter)
        for (side, _sc, _ar), reason in self.cand_structs.items():
            fate[side]["entry_bar_not_in_any_window" if reason == "_not_entry_bar" else reason] += 1
        dedup = collections.Counter(leg for (_s, _t, leg) in self.fire_keys)
        booked = collections.Counter(t.get("leg") for t in trades)
        return dict(
            windows_scanned=dict(self.calls),
            structures_detected_by_side={k: dict(v) for k, v in by_side.items()},
            structures_note="unique (side, SC time, AR time) over every live 300-bar window; field counts are "
                            "from the LAST window that still contained the structure (all <= the cutoff).",
            windows_with_fireable_candidate=dict(self.win_with_cand),
            candidate_structures=len(self.cand_structs),
            spring_leg_fate_by_side={k: dict(v) for k, v in fate.items()},
            fire_events_pre_dedup=dict(self.fires),
            fires_after_dedup=dict(dedup),
            htf_gate_results=dict(self.htf_results) if htf_on else "not applied (config has htf=False)",
            walk_calls=dict(self.walk_calls),
            booked_by_leg=dict(booked),
            booked_by_side=dict(collections.Counter(t["side"] for t in trades)),
            observed=["windows_scanned", "structures_detected_by_side", "windows_with_fireable_candidate",
                      "fire_events_pre_dedup", "htf_gate_results", "walk_calls", "booked_by_leg"],
            inferred=["spring_leg_fate_by_side (replicates _fires_from's spring-leg conditions on the engine's "
                      "own records; cross-checked per window against the observed spring fires)",
                      "fires_after_dedup (the engine's own (side, t0, leg) key)"],
            not_observable=["phase_d leg: why a BU bar did not fire (placeability) is not separated -- only "
                            "'structure has a BU' (detection) and 'phase_d fired' (observed) are reported"],
            consistency=dict(self.inconsistent),
        )


# ------------------------------------------------------------------------------------------ outcome summary

def _q(xs, p):
    if not xs:
        return None
    xs = sorted(xs); k = (len(xs) - 1) * p; f = int(k); c = min(f + 1, len(xs) - 1)
    return round(xs[f] + (xs[c] - xs[f]) * (k - f), 3)


def _dist(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return dict(n=0)
    return dict(n=len(xs), mean=round(statistics.fmean(xs), 3), p10=_q(xs, .1), p25=_q(xs, .25),
                median=_q(xs, .5), p75=_q(xs, .75), p90=_q(xs, .9))


def exit_type(t, horizon):
    """Classify one trade dict (as walk()/ict_setups_live() return it) by how it ended."""
    o = t.get("outcome")
    if o == "loss" and t.get("bars_held") == 1 and t.get("exit_time") == t.get("entry_time") and t.get("mfe") == 0.0:
        return "same_bar_fill_and_stop"
    if o == "loss":
        return "stop"
    if o == "breakeven":
        return "breakeven_stop"
    if o == "win":
        return "target"
    if o == "timeout":
        return "time_stop" if (t.get("bars_held") or 0) >= horizon else "truncated_at_cutoff"
    return "other"


def summarize_outcomes(trades, horizon, min_rr=None):
    """Outcome statistics of booked trades. Gross R, exactly as the engine records it (fees are charged later,
    by simulate()). `horizon` = bt.P[tf]["H"]; `min_rr` = the planned-R:R floor, for the share below it."""
    n = len(trades)
    if n == 0:
        return dict(n=0)
    Rs = [t["R"] for t in trades]
    kinds = collections.Counter(exit_type(t, horizon) for t in trades)
    losers = [t for t in trades if t["R"] < 0]
    lost_mfe1 = sum(1 for t in losers if (t.get("mfe") or 0) >= 1.0)
    lost_mfe_tgt = sum(1 for t in losers if t.get("R_planned") and (t.get("mfe") or 0) >= t["R_planned"])
    non_win_mfe1 = sum(1 for t in trades if t.get("outcome") != "win" and (t.get("mfe") or 0) >= 1.0)
    sides = {}
    for s in ("long", "short"):
        ts = [t for t in trades if t["side"] == s]
        sides[s] = dict(n=len(ts), mean_R=round(statistics.fmean([t["R"] for t in ts]), 3) if ts else None,
                        win_rate=round(sum(t["R"] > 0 for t in ts) / len(ts), 3) if ts else None)
    rp = [t.get("R_planned") for t in trades if t.get("R_planned") is not None]
    out = dict(
        n=n,
        exit_types=dict(kinds),
        mean_R=round(statistics.fmean(Rs), 3), median_R=_q(Rs, .5),
        win_rate=round(sum(r > 0 for r in Rs) / n, 3),
        sum_R=round(sum(Rs), 2),
        R=_dist(Rs), mfe=_dist([t.get("mfe") for t in trades]), mae=_dist([t.get("mae") for t in trades]),
        R_planned=_dist(rp),
        bars_held=_dist([t.get("bars_held") for t in trades]),
        losers=len(losers),
        losers_with_mfe_ge_1R=lost_mfe1,
        losers_with_mfe_ge_planned_R=lost_mfe_tgt,
        non_winners_with_mfe_ge_1R=non_win_mfe1,
        by_side=sides,
    )
    if min_rr is not None and rp:
        out["share_R_planned_below_floor"] = round(sum(x < min_rr for x in rp) / len(rp), 3)
        out["min_rr_floor"] = min_rr
    return out


def after_floor(bt, sr, cfg, method, trades):
    """The planned-R:R floor simulate() applies (net of fees, CLAUDE.md §34) and the admitted account run.
    Uses bt.simulate itself for the admitted set; the floor count alone re-derives fee_R with the same
    risk_model.cost_r call simulate() makes (INFERRED, labelled)."""
    if not trades:
        return dict(booked=0)
    fee = sr.config_fee(sr.CONFIGS[cfg], "cfd")
    eot = sr.entry_order_type_for(sr.CONFIGS[cfg], method)
    final, curve, taken = bt.simulate(trades, fee, entry_order_type=eot, live_parity_sizing=True)
    passing = 0
    for t in trades:
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        venue = bt._venue_for_symbol(t["symbol"])
        try:
            fee_R = bt._RM.cost_r(t["entry"], t["stop"], venue, eot, exit_order_type="taker")[0] if venue else 2 * fee / dist
        except bt._RM.RiskRefused:
            fee_R = 2 * fee / dist
        passing += (t.get("R_planned", 99) - fee_R) >= bt.OPTS["min_rr"] if bt.OPTS.get("min_rr") is not None else True
    nets = [t["net_R"] for t in taken]
    return dict(booked=len(trades), pass_rr_floor_net_inferred=passing, simulate_taken=len(taken),
                simulate_taken_mean_net_R=round(statistics.fmean(nets), 3) if nets else None,
                simulate_taken_win_rate=round(sum(x > 0 for x in nets) / len(nets), 3) if nets else None,
                simulate_ruin=bt.SIM_LAST.get("ruin"), fee_per_side=fee, entry_order_type=eot)


# ------------------------------------------------------------------------------------------ one slice

def _compact(t):
    keep = ("symbol", "tf", "side", "leg", "time", "entry_time", "exit_time", "entry", "stop", "target", "outcome",
            "R", "R_planned", "mfe", "mae", "bars_held", "vol_type")
    return {k: t.get(k) for k in keep if k in t}


def instrumented_scan(sr, sym, tf, method, cfg, cutoff=DEV_CUTOFF):
    """bt.scan(sym, tf, only=(method,), opts=config overlay) under the PIT cutoff, with the probe installed.
    Returns (scan_result, probe)."""
    _check_cutoff(cutoff)
    bt = sr.bt
    bt.pit_cutoff(cutoff)
    probe = IctProbe(bt) if method == "ICT" else WyProbe(bt)
    if method == "WYCKOFF-BOOK":
        c, _ = bt.load(sym, tf)
        if not c:
            return None, probe
        probe.Tm = [x["time"] for x in c]
        bt._WY_CANDIDATES = {}      # force detection to run so the detection wrappers see it
    patch = _Patch()
    try:
        probe.install(patch)
        res = bt.scan(sym, tf, only=(method,), opts=_overlay(sr, cfg))
    finally:
        patch.restore()
    return res, probe


def plain_scan(sr, sym, tf, method, cfg, cutoff=DEV_CUTOFF):
    _check_cutoff(cutoff)
    sr.bt.pit_cutoff(cutoff)
    return sr.bt.scan(sym, tf, only=(method,), opts=_overlay(sr, cfg))


def run_slice(sym, tf, method, cfg, cutoff=DEV_CUTOFF, sr=None):
    sr = sr or load_sr(); bt = sr.bt
    t0 = time.time()
    res, probe = instrumented_scan(sr, sym, tf, method, cfg, cutoff)
    if not res:
        return dict(symbol=sym, tf=tf, method=method, config=cfg, cutoff=cutoff, status="no data")
    trades = list(res["trades"].get(method, []))
    late = [t for t in trades if t["entry_time"] >= cutoff or t["exit_time"] >= cutoff]
    if late or res["last"] >= cutoff:
        raise RuntimeError(f"PIT breach: {len(late)} trades / last bar {res['last']} at or after {cutoff}")
    htf_on = bool(_overlay(sr, cfg)["htf"])
    funnel = probe.summary(htf_on) if method == "ICT" else probe.summary(trades, htf_on)
    H = bt.P[tf]["H"]
    return dict(
        symbol=sym, tf=tf, method=method, config=cfg, cutoff=cutoff, status="ok",
        overlay={k: v for k, v in _overlay(sr, cfg).items() if k in ("mgmt", "htf", "sides", "types", "entry", "phase_d") or k.startswith("fx_")},
        params=bt.P[tf], bars=res["bars"], first_bar=res["first"], last_bar=res["last"], source=res["source"],
        bias_methods=list(bt.resolve_methods(sym)),
        elapsed_s=round(time.time() - t0, 1),
        funnel=funnel,
        outcomes=summarize_outcomes(trades, H, bt.MIN_RR),
        outcomes_by_leg=({leg: summarize_outcomes([t for t in trades if t.get("leg") == leg], H, bt.MIN_RR)
                          for leg in WY_LEGS} if method == "WYCKOFF-BOOK" else None),
        account=after_floor(bt, sr, cfg, method, trades),
        trades=[_compact(t) for t in trades],
    )


def check_equality(sym, tf, method, cfg, cutoff=DEV_CUTOFF, sr=None):
    """Instrumented trades == plain bt.scan trades, same process, same cutoff. Returns (equal, n_plain, n_instr)."""
    sr = sr or load_sr()
    plain = plain_scan(sr, sym, tf, method, cfg, cutoff)
    instr, _ = instrumented_scan(sr, sym, tf, method, cfg, cutoff)
    a = (plain or {}).get("trades", {}).get(method, []) if plain else []
    b = (instr or {}).get("trades", {}).get(method, []) if instr else []
    return a == b, len(a), len(b)


# ------------------------------------------------------------------------------------------ report

def _fmt(v):
    return "–" if v is None else (f"{v:g}" if isinstance(v, float) else str(v))


def report(in_dir):
    rows = []
    for fn in sorted(os.listdir(in_dir)):
        if fn.endswith(".json"):
            rows.append(json.load(open(os.path.join(in_dir, fn), encoding="utf-8")))
    out = []
    for r in rows:
        out.append(f"#### {r['method']} · {r['symbol']} · {r['tf']} · config {r['config']}")
        if r.get("status") != "ok":
            out.append(f"not run ({r.get('status')})\n"); continue
        out.append(f"bars {r['bars']} ({r['first_bar']} → {r['last_bar']}), {r['elapsed_s']} s")
        f = r["funnel"]
        if r["method"] == "ICT":
            out.append("| stage | bars reaching | unique setups reaching |\n|---|---:|---:|")
            for s in f["stages"]:
                us = f["unique_setups_reaching"][s] if s not in ("bars_scanned", "full_live_window") else "–"
                out.append(f"| {s} | {f['bars_reaching'][s]} | {us} |")
            out.append(f"incomplete (bars): {f['incomplete_reason_bars']}; bias refused (bars): {f['bias_refused_bars']}; "
                       f"bias on setups stopped at bias: {f['bias_values_on_setups_stopped_at_bias']}; htf: {f['htf_gate_results']}; "
                       f"consistency: {f['consistency'] or 'ok'}")
        else:
            out.append(f"windows {f['windows_scanned']}; structures {f['structures_detected_by_side']}")
            out.append(f"windows with fireable candidate {f['windows_with_fireable_candidate']}; candidate structures {f['candidate_structures']}")
            out.append(f"spring-leg fate {f['spring_leg_fate_by_side']}")
            out.append(f"fires pre-dedup {f['fire_events_pre_dedup']} → after dedup {f['fires_after_dedup']} → htf {f['htf_gate_results']} → walk {f['walk_calls']} → booked {f['booked_by_leg']}; consistency: {f['consistency'] or 'ok'}")
        o = r["outcomes"]
        if o.get("n"):
            out.append(f"outcomes: n={o['n']} exits={o['exit_types']} meanR={o['mean_R']} medianR={o['median_R']} win={o['win_rate']} "
                       f"MFE med={o['mfe'].get('median')} p75={o['mfe'].get('p75')} MAE med={o['mae'].get('median')} "
                       f"Rplanned med={o['R_planned'].get('median')} bars med={o['bars_held'].get('median')} "
                       f"losers={o['losers']} (MFE≥1R {o['losers_with_mfe_ge_1R']}, MFE≥planned {o['losers_with_mfe_ge_planned_R']}) "
                       f"sides={o['by_side']} below-floor={o.get('share_R_planned_below_floor')}")
        else:
            out.append("outcomes: n=0")
        out.append(f"account: {r['account']}\n")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------ CLI

def _slug(sym, tf, method, cfg):
    return f"{method}_{sym}_{tf}_{cfg}".replace("-", "")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("run", "equality"):
        p = sub.add_parser(name)
        p.add_argument("--symbol", required=True); p.add_argument("--tf", required=True)
        p.add_argument("--method", required=True, choices=METHODS); p.add_argument("--config", required=True, choices=("A", "B", "C"))
        p.add_argument("--cutoff", default=DEV_CUTOFF)
        if name == "run":
            p.add_argument("--out", required=True)
            p.add_argument("--set", action="append", default=[], metavar="FX_KEY",
                           help="switch on a bool fx_ fidelity key (repeatable); default is v1 with none set")
    b = sub.add_parser("batch"); b.add_argument("--out-dir", required=True); b.add_argument("--timeout", type=int, default=1800)
    b.add_argument("--only", help="comma list of slugs to run (default: all audit slices)")
    r = sub.add_parser("report"); r.add_argument("--in-dir", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "run":
        # Validated against the engine's own fx_ keys (every ICT and Wyckoff item), not just the prefix: a typo
        # would otherwise run as v1, be echoed in `overlay` as if active, and still count toward N.
        valid = sorted(k for k in load_sr().bt._OPTS_BASE if k.startswith("fx_"))
        for k in a.set:
            if k not in valid:
                ap.error(f"--set takes one of the engine's fx_ keys {valid}, got {k!r}")
            EXTRA_OVERLAY[k] = True
        res = run_slice(a.symbol, a.tf, a.method, a.config, a.cutoff)
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1, default=str)
        print(f"{a.method} {a.symbol} {a.tf} {a.config}: {res.get('status')} trades={res.get('outcomes', {}).get('n')} "
              f"elapsed={res.get('elapsed_s')}s -> {a.out}")
    elif a.cmd == "equality":
        eq, n1, n2 = check_equality(a.symbol, a.tf, a.method, a.config, a.cutoff)
        print(f"EQUALITY {a.method} {a.symbol} {a.tf} config {a.config} cutoff {a.cutoff}: "
              f"plain={n1} instrumented={n2} equal={eq}")
        return 0 if eq else 1
    elif a.cmd == "batch":
        os.makedirs(a.out_dir, exist_ok=True)
        only = set(a.only.split(",")) if a.only else None
        for sym, tf, method, cfg in audit_slices():
            slug = _slug(sym, tf, method, cfg)
            if only and slug not in only:
                continue
            out = os.path.join(a.out_dir, slug + ".json")
            if os.path.exists(out):
                print(f"{slug}: exists, skipped", flush=True); continue
            t0 = time.time()
            cmd = [sys.executable, os.path.abspath(__file__), "run", "--symbol", sym, "--tf", tf, "--method", method,
                   "--config", cfg, "--out", out]
            status = None
            for attempt in (1, 2):
                try:
                    p = subprocess.run(cmd, timeout=a.timeout, capture_output=True, text=True)
                    if p.returncode == 0:
                        status = "ok"; break
                    status = f"crash (rc={p.returncode}): {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else ''}"
                except subprocess.TimeoutExpired:
                    status = f"time (> {a.timeout} s)"; break
            if status != "ok":
                json.dump(dict(symbol=sym, tf=tf, method=method, config=cfg, status=status),
                          open(out, "w", encoding="utf-8"), indent=1)
            print(f"{slug}: {status} in {round(time.time() - t0)} s", flush=True)
    elif a.cmd == "report":
        print(report(a.in_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
