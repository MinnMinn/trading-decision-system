#!/usr/bin/env python3
"""Backtest three entry methods on stored candles and report % returns per month / quarter / year at 1% risk per trade.

Usage: backtest-methods.py [--tf 15m,1H,4H,1D] [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--fee-pct 0.05] [--out docs/backtests/<file>.md] [--json PATH]
Data: data/history/ohlcv.<SYM>.<TF>.json (scripts/fetch-history.py). Everything is computed; nothing is judged by a model.

METHODS (long = accumulation side; short = the distribution mirror with the same rules):

  WYCKOFF  — knowledge/08 §2.6 (Bảng 2.1, WMT p049) + knowledge/07 §5.2 WA2-11 (WA p80) + knowledge/08 §5 Step 6 (WMT p271–273)
    Trading range  = rolling: support = min low of the previous R bars (excluding the last 6), resistance = max high of the previous R bars.
                     PROJECT PARAMETER: R (the book draws the TR from AR/SC/ST, WA p71–72; a per-bar full Wyckoff read is not codeable here).
    Spring         = low pierces support, close back above support within 0–2 bars (WA p80). Cluster guard 5 bars.
    Volume type    = Spring-bar volume vs mean of previous 20 bars: <0.7× type 1, 0.7–1.5× type 2, >1.5× type 3 (analysis-params.json project_defined.volume; typing knowledge/08 §2.6).
    Entry rule     = type 1: at the close of the reclaim bar (WA p80 "Spring khối lượng thấp … mở một phần vị thế"; WMT p049 confirmation = close back above support).
                     type 2: at the first RETEST (WMT p049 "one or more retests"): within T bars a bar whose low is in [Spring low, support + ⅓·TR], volume < Spring-bar volume, closes in its upper half → entry at that close. No retest → no trade.
                     type 3: at the reclaim close only if the reclaim bar itself is high-volume (≥1.5×, WMT p049 "reversal on high volume"); otherwise wait for the retest as type 2.
    Stop           = below the Spring low (WMT p271) − 0.05% buffer.   Target = opposite border of the TR (WMT p273; WA p80 "at least the TR upper border").
    Volume is used; no ICT concept is used.

  ICT      — knowledge/04 §2.17 (MSS by body close), §2.21 (FVG), knowledge/05 §2.2, §3.1; stop/target per .claude/skills/ict-skill "Invalidation"
    Liquidity      = the last 3-bar pivot low (SSL) / pivot high (BSL) before the bar. No volume, no trading range, no phase.
    Sweep          = low pierces the pivot low. MSS = within K bars a body close above the last 3-bar pivot high formed before the sweep.
    FVG            = bullish gap (candle1.high < candle3.low) in the leg from the sweep to MSS+1.
    Entry rule     = price returns into the FVG within K bars after the MSS: entry at the FVG's near edge (candle3.low). No return → no trade (limit not filled).
    Invalidation   = later body close below the swept low kills the read (knowledge/04 §3.6) — stop sits at the sweep low − buffer, so this is the stop.
    Target         = the next external liquidity = the highest high of the previous R bars (BSL). Same R as Wyckoff so the two are comparable.
    Timing         = none (crypto has no sourced killzone rule: knowledge/04 §6; docs/architecture/session-model.md).
    Deck-faithful switches (2026-09-12, off by default so the pilot's rule set does not change silently):
      --ict-disp      the MSS candle must be a displacement candle: body >= project_defined.ict.displacement.body_min_ratio of its range
                      and range >= range_min_median_ratio x the median range of the previous R bars (knowledge/04 §2.16).
      --ict-pd        longs only when the sweep bar closes in the discount half of the R-bar range, shorts in the premium half (knowledge/04 §3.4 R13).
      --std-origin    'pivot' = fib 0 at the last 3-bar pivot before the sweep (pre-2026-09-12); 'highest' = the highest high (long) /
                      lowest low (short) between that pivot and the sweep — Model11 p20 "the previous high which made the highest high".

  COMBINED — SYSTEM-DESIGN §6 / knowledge/10 §4: Wyckoff owns context + the excursion, ICT owns the entry structure left behind
    Condition      = a Wyckoff Spring (any volume type, as above) AND the ICT MSS + FVG confirmation within K bars.
    Entry rule     = ICT entry (return into the FVG) — else at the MSS close if price never returns (market order once the checklist is satisfied, WMT p269).
    Stop/target    = one invalidation owner (ict-skill "Invalidation"): the Spring low; target the TR opposite border.
    Volume type gate = types 1/2 always; type 3 only with the high-volume reclaim (same as WYCKOFF).
  PARTIAL  — the "vào sớm một phần" proposal: 0.5 risk at the Wyckoff entry, +0.5 risk at the COMBINED entry when it comes (same stop/target);
             when no Wyckoff entry bar exists (type 2/3 without a retest) but the ICT confirmation comes, the COMBINED entry is taken at full size.

OUTCOME — walk forward H bars: stop hit → −1R; target hit → +R_planned; both in one bar → loss; neither → mark-to-market R at bar H.
FEES    — taker fee per side (default 0.05%, Binance futures) charged on the notional; in R that is fee·2·entry/(entry−stop). Slippage not modelled.
ACCOUNT — 1% of current equity risked per trade (0.5% per half of PARTIAL), compounding, one open position per symbol, all symbols of a timeframe share one account.
          Monthly / quarterly / yearly returns are equity-curve returns (closed trades booked at exit time).
"""
import argparse, bisect, collections, importlib.util, datetime, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import wyckoff_rules as W
P = {"5m": dict(R=60, K=18, T=20, H=120, sob=8), "15m": dict(R=48, K=16, T=16, H=96, sob=6), "30m": dict(R=48, K=14, T=14, H=84, sob=5), "1H": dict(R=48, K=12, T=12, H=72, sob=4),
     "2H": dict(R=36, K=10, T=10, H=48, sob=3), "4H": dict(R=30, K=8, T=8, H=30, sob=3), "1D": dict(R=20, K=6, T=6, H=20, sob=2)}  # sob = bars a Spring may stay outside the TR (wyckoff_rules R6)
VOL = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"]["volume"]
STOP_BUFFER_PCT = 0.0005
RISK = 0.01
START = 10000.0      # account size in $ (user decision 2026-09-11: $10,000 for readability)
RUIN_FRAC = 0.10     # the account is declared BLOWN (cháy) when equity <= 10 % of START; trading stops there and the report says so
OPTS = dict(min_rr=0.0, types=(1, 2, 3), range_touches=0, htf=False, sides=("long", "short"), entry="book", mgmt="none", sloped_gate=False, st_min=None, phase_d=True, combined_entry="limit", ict_target="range",
            ict_disp=False, ict_pd=False, std_origin="pivot", rules="live", methods=None)
_ICT = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"].get("ict", {})
DISP = _ICT.get("displacement", {"body_min_ratio": 0.6, "range_min_median_ratio": 1.2})


def load(sym, tf):
    p = f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"
    if not os.path.exists(p):
        return None, None
    return json.load(open(p))["candles"], os.path.relpath(p, ROOT)


def all_pivots(X, kind):
    """All 3-bar pivot indices (high or low) over the series, computed once."""
    out = []
    for i in range(3, len(X) - 3):
        w = [X[j] for j in range(i - 3, i + 4) if j != i]
        if (kind == "high" and all(v <= X[i] for v in w)) or (kind == "low" and all(v >= X[i] for v in w)):
            out.append(i)
    return out


def last_pivot(piv, upto):
    """Index of the last pivot confirmed before bar `upto` (a pivot at i needs bar i+3, so i <= upto-4)."""
    k = bisect.bisect_left(piv, upto - 3) - 1
    return piv[k] if k >= 0 else None


def walk(side, entry, stop, target, H_, L_, C_, start, horizon):
    r = (entry - stop) if side == "long" else (stop - entry)
    if r <= 0:
        return None
    rp = abs(target - entry) / r
    be_level = (entry + r) if side == "long" else (entry - r)   # +1R reached → stop to entry (WMT p272 breakeven)
    cur_stop = stop; be = False
    for j in range(start, min(len(C_), start + horizon)):
        hit_stop = L_[j] <= cur_stop if side == "long" else H_[j] >= cur_stop
        hit_tgt = H_[j] >= target if side == "long" else L_[j] <= target
        if hit_stop:
            return dict(outcome="loss" if not be else "breakeven", R=-1.0 if not be else 0.0, exit=j, R_planned=rp)
        if hit_tgt:
            return dict(outcome="win", R=rp, exit=j, R_planned=rp)
        if OPTS["mgmt"] == "be" and not be and ((H_[j] >= be_level) if side == "long" else (L_[j] <= be_level)):
            be = True; cur_stop = entry
    j = min(len(C_) - 1, start + horizon - 1)
    return dict(outcome="timeout", R=((C_[j] - entry) if side == "long" else (entry - C_[j])) / r, exit=j, R_planned=rp)


def vtype(ratio):
    return None if ratio is None else (1 if ratio < VOL["low_max_ratio"] else (3 if ratio > VOL["high_min_ratio"] else 2))


def is_displacement(j, O, H, L, C, R=48):
    """knowledge/04 §2.16 'aggressive move with full-bodied candles' read with the project ratios (analysis-params.json project_defined.ict)."""
    rg = H[j] - L[j]
    if rg <= 0:
        return False
    a = max(0, j - R); med = statistics.median(H[q] - L[q] for q in range(a, j)) if j - a >= 5 else rg
    return abs(C[j] - O[j]) >= DISP["body_min_ratio"] * rg and rg >= DISP["range_min_median_ratio"] * med


def find_ict(side, i, rec, H, L, C, K, n, PH, PL, O=None):
    """MSS (body close beyond the last pivot before the sweep) within K bars after rec, and an FVG in the leg. Returns (mss, fvg_edge, fvg_far) or None.
    With OPTS['ict_disp'] the MSS candle must also pass is_displacement (needs O)."""
    disp_ok = (lambda j: True) if not OPTS["ict_disp"] or O is None else (lambda j: is_displacement(j, O, H, L, C))
    if side == "long":
        ph = last_pivot(PH, i)
        if ph is None:
            return None
        lvl = H[ph]
        mss = next((j for j in range(rec + 1, min(rec + 1 + K, n)) if C[j] > lvl and disp_ok(j)), None)
        if mss is None:
            return None
        # FVG must be COMPLETE by the MSS close (third candle <= mss): a gap whose third candle is mss+1 is only known
        # after that candle closed, and its low would already have "filled" the limit -- look-ahead (found 2026-09-11 parity test).
        for k in range(i + 1, min(mss, n - 1)):
            if H[k - 1] < L[k + 1]:
                return mss, L[k + 1], H[k - 1]
    else:
        pl = last_pivot(PL, i)
        if pl is None:
            return None
        lvl = L[pl]
        mss = next((j for j in range(rec + 1, min(rec + 1 + K, n)) if C[j] < lvl and disp_ok(j)), None)
        if mss is None:
            return None
        for k in range(i + 1, min(mss, n - 1)):
            if L[k - 1] > H[k + 1]:
                return mss, H[k + 1], L[k - 1]
    return None


def ict_target(side, i, mss, ext, H, L, R, PH, PL, range_target):
    """Target models for the ICT-only method (OPTS["ict_target"]):
      range    = the R-bar extreme before the sweep (this project's original proxy for the opposite liquidity)
      std2 / std25 / std4 = standard-deviation projection of the MANIPULATION LEG (knowledge/05 §2.12, R16–R18): fib 1 at the
               sweep extreme, 0 at the swing the manipulation began from (the last pivot before the sweep); -2 .. -2.5 = retrace/
               reverse zone (take profit, R17), -4 = max expansion (R18)
      erl_next = the next external liquidity beyond the swing the MSS broke: the first pivot high (long) above the MSS level within R
               bars before the sweep, else the R-bar extreme (knowledge/05 §2.13, R3/R20: after IRL, target the next ERL)
      irl      = the nearest opposing FVG above (long) the MSS level formed within R bars before the sweep, its near edge; else erl_next
    """
    mode = OPTS["ict_target"]
    if mode == "range":
        return range_target
    if side == "long":
        origin_i = last_pivot(PH, i); origin = H[origin_i] if origin_i is not None else None
        if origin is not None and OPTS["std_origin"] == "highest":
            origin = max(H[origin_i:i + 1])   # Model11 p20: "low to the previous high which made the highest high"
    else:
        origin_i = last_pivot(PL, i); origin = L[origin_i] if origin_i is not None else None
        if origin is not None and OPTS["std_origin"] == "highest":
            origin = min(L[origin_i:i + 1])
    if origin is None:
        return None
    leg = abs(origin - ext)
    if leg <= 0:
        return None
    if mode.startswith("std"):
        mult = {"std2": 2.0, "std25": 2.5, "std4": 4.0}[mode]
        return origin + mult * leg if side == "long" else origin - mult * leg
    if mode in ("erl_next", "irl"):
        if mode == "irl":
            lo_i = max(3, i - R)
            for k in range(i - 1, lo_i, -1):                      # nearest first
                if side == "long" and L[k - 1] > H[k + 1] and H[k + 1] > origin:
                    return H[k + 1]
                if side == "short" and H[k - 1] < L[k + 1] and L[k + 1] < origin:
                    return L[k + 1]
        piv = PH if side == "long" else PL
        for q in reversed([q for q in piv if i - R <= q < i]):
            if (side == "long" and H[q] > origin) or (side == "short" and L[q] < origin):
                return H[q] if side == "long" else L[q]
        return range_target
    return range_target


def fvg_fill(side, mss, edge, far, stop, H, L, K, n):
    """First bar after the MSS whose range reaches the FVG near edge without first hitting the stop. Returns bar index or None."""
    for j in range(mss + 1, min(mss + 1 + K, n)):
        if side == "long":
            if L[j] <= stop:
                return None
            if L[j] <= edge:
                return j
        else:
            if H[j] >= stop:
                return None
            if H[j] >= edge:
                return j
    return None


def range_established(H, L, a, b, support, resistance, touches, tol=0.15):
    """Trading range proxy (WA p71–72: the TR is drawn from AR and SC/ST — i.e. both borders have been tested):
    at least `touches` separate visits to within tol·TR of each border inside bars a..b (visits ≥ 3 bars apart)."""
    tr = resistance - support; lo_t = []; hi_t = []
    for j in range(a, b):
        if L[j] <= support + tol * tr and (not lo_t or j - lo_t[-1] > 3):
            lo_t.append(j)
        if H[j] >= resistance - tol * tr and (not hi_t or j - hi_t[-1] > 3):
            hi_t.append(j)
    return len(lo_t) >= touches and len(hi_t) >= touches


# Structure tier per timeframe: the next rung >= 4x (scripts/automation.py next_rung, docs/architecture/timeframe-mapping.md).
_RUNGS = ["5m", "15m", "30m", "1H", "2H", "4H", "1D"]
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
HTF_OF = {tf: _auto.next_rung(tf, _RUNGS) for tf in _RUNGS if _auto.next_rung(tf, _RUNGS)}
# The live rules seam (scripts/live_rules.py): the ICT branch calls the live scanner through this handle instead of
# re-deriving pivots/MSS/FVG itself (audit 2026-09-13 -- see docstring at the top of this file's ICT section).
_lspec = _iu.spec_from_file_location("live_rules", os.path.join(ROOT, "scripts", "live_rules.py"))
lr = _iu.module_from_spec(_lspec); _lspec.loader.exec_module(lr)


def htf_position(sym, tf):
    """Higher-timeframe context proxy for the giảm-khung rule (htf_context.py, WA p93–96, p201): where the HTF close sits
    inside its own rolling R-bar range (0 = at the low, 1 = at the high). Returns [(time, pct)] or None."""
    h = HTF_OF.get(tf)
    if not h:
        return None
    c, _ = load(sym, h)
    if not c:
        return None
    Rh = P[h]["R"]; out = []
    for i in range(Rh, len(c)):
        lo = min(x["low"] for x in c[i - Rh:i]); hi = max(x["high"] for x in c[i - Rh:i])
        out.append((c[i]["time"], (c[i]["close"] - lo) / (hi - lo) if hi > lo else 0.5))
    return out


def htf_allows(htf, t, side):
    """LEGACY: the pre-2026-09-13 rolling-percentile proxy, kept reachable via --rules legacy so it stays
    comparable against the live gate; bias_allows() below is the gate strategy-runner.py should use going forward.
    Boundary rule (htf_context.BOUNDARY_FRACTION): longs only when the HTF sits in the lower third of its range or has
    broken above it (markup); shorts the mirror. Uses the last HTF bar that CLOSED before t."""
    k = bisect.bisect_left(htf, (t,)) - 1
    if k < 0:
        return False
    pct = htf[k][1]
    return pct <= 1 / 3 or pct > 1.0 if side == "long" else pct >= 2 / 3 or pct < 0.0


def bias_allows(bias, side):
    """The giảm-khung gate read from the LIVE bias (htf_context.bias_of via live_rules.bias_at). `bias` is the
    first element of the (bias, basis) tuple that live_rules.bias_at(...) / htf_context.bias_of(...) return --
    i.e. call this as bias_allows(bias_at(...)[0], side), never with the (bias, basis) tuple itself. That first
    element is a string with exactly four possible values: "long", "short", "neutral", "unknown"
    (scripts/htf_context.py wyckoff_bias / ict_bias / bias_of).

    Only an explicit agreement opens the gate: `neutral` is a real reading that found no direction and `unknown`
    means no read was available, and neither is permission to take risk (capital preservation first). This
    replaces htf_allows, the rolling-percentile proxy, which is kept above so --rules legacy still runs."""
    return bias == side


def resolve_methods(sym):
    """The bias-reading methods engaged for `sym`, resolved from /automation the same way live does --
    htf_context.engaged_methods_for_market(automation.market_of(sym)). OPTS["methods"] holds an explicit
    --methods CLI override when one was given; None (its default) means "resolve it here", never a hardcoded
    tuple -- a backtest that guessed its own default methods would silently diverge from the run being
    reproduced (see live_rules.read_at's docstring for the same argument)."""
    if OPTS["methods"] is not None:
        return OPTS["methods"]
    return lr.htf.engaged_methods_for_market(_auto.market_of(sym))


def ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, methods):
    """ICT trades for one symbol/timeframe using the LIVE rules: at each bar, run the scanner over the window the
    live scanner would have read and ask IT for the setup. No pivot/MSS/FVG logic of our own -- that duplication is
    what made a backtest measure a system nobody trades (audit 2026-09-13).

    The entry is a LIMIT at the FVG near edge, exactly as live places it (strategy-runner.py: "LIMIT at the FVG
    near edge"). So a setup is NOT a trade: fvg_fill() decides whether price ever came back to that limit without
    first hitting the stop, and returns None when the order would simply never have filled. Skipping that check
    would enter every setup at a favourable price and make the whole backtest optimistic by construction."""
    out, seen = [], set()
    n = len(c)
    idx_of_time = {t: j for j, t in enumerate(Tm)}
    for i in range(n):
        a = lr.read_at(c, i, tf, methods)
        if a is None:            # window not yet the full live window -- live would not have scanned here at all
            continue
        su = lr.ict_scan.setup_candidate(a, lr.window(c, i, tf), lr.setup_lookback(tf))
        if not su or not su.get("complete") or not su.get("pd_ok"):
            continue
        bias, _ = lr.bias_at(c, i, tf, methods, facts=a)      # facts reused: no second analyze()
        if not bias_allows(bias, su["side"]):
            continue
        key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
        if key in seen:          # the same setup stays visible for many bars; take it once, at its first bar
            continue
        seen.add(key)
        mss_i = idx_of_time.get(su["mss"]["time"])
        if mss_i is None:
            continue
        entry = su["entry"]; stop = su["stop"]; target = su["target"]
        far = su["entry_models"]["fill"]   # ict-scan.py setup_candidate: the key is "entry_models", not "entries"
        fill = fvg_fill(su["side"], mss_i, entry, far, stop, H, L, P[tf]["K"], n)
        if fill is None:         # the limit never filled: live would hold an unfilled order, not a position
            continue
        w = walk(su["side"], entry, stop, target, H, L, C, fill + 1, HZ)
        if not w:
            continue
        out.append(dict(symbol=sym, tf=tf, side=su["side"], time=Tm[i], entry=entry, entry_time=Tm[fill],
                        stop=stop, target=target, exit_time=Tm[w["exit"]], vol_type=None, **w))
    return out


RUNNER_METHODS = ("WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL")


def scan(sym, tf, only=None):
    """`only`: which of RUNNER_METHODS to compute; None (default) computes all six -- today's behaviour, unchanged.
    A caller that needs exactly one method's trades should pass e.g. only=("COMBINED",) so scan() SKIPS the other
    methods' work rather than computing and discarding it -- in particular so it never calls the live ICT scanner
    (ict_setups_live, one ict-scan.analyze() per bar) when nobody asked for ICT trades. strategy-runner.replay()
    checks one method at a time across 9 symbols; before this, it paid the full live-scanner cost for ICT on every
    call regardless, which 27x'd the test suite for a COMBINED-only check that never touches that branch
    (code-quality review, 2026-09-13). NOT the same axis as OPTS["methods"] -- that key holds the wyckoff/ict BIAS
    DIMENSIONS the live rules read (resolve_methods/engaged_methods_for_market); `only` here names RUNNER methods
    (WYCKOFF, ICT, COMBINED, ...). Deliberately a different name (`only`, not `methods`) so the two never collide."""
    want = set(RUNNER_METHODS) if only is None else set(only)
    c, src = load(sym, tf)
    if not c:
        return None
    p = P[tf]; R, K, T, HZ = p["R"], p["K"], p["T"], p["H"]
    H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]; V = [x.get("volume", 0) for x in c]; Tm = [x["time"] for x in c]; O = [x["open"] for x in c]
    n = len(c); trades = collections.defaultdict(list); PH = all_pivots(H, "high"); PL = all_pivots(L, "low")
    # ---------- WYCKOFF and COMBINED / PARTIAL (Spring / Upthrust at the TR border) ----------
    htf = htf_position(sym, tf) if OPTS["htf"] else None
    if want & {"WYCKOFF", "COMBINED", "PARTIAL"}:
        for side in OPTS["sides"]:
            last_i = -99
            for i in range(R + 6, n - 3):
                support = min(L[i - R:i - 5]); resistance = max(H[i - R:i - 5])
                if resistance <= support or i - last_i <= 5:
                    continue
                if OPTS["range_touches"] and not range_established(H, L, i - R, i - 5, support, resistance, OPTS["range_touches"]):
                    continue
                if htf is not None and not htf_allows(htf, Tm[i], side):
                    continue
                if side == "long":
                    if not L[i] < support:
                        continue
                    rec = next((j for j in range(i, min(i + 3, n)) if C[j] > support), None)
                else:
                    if not H[i] > resistance:
                        continue
                    rec = next((j for j in range(i, min(i + 3, n)) if C[j] < resistance), None)
                if rec is None:
                    continue
                last_i = i
                ext = min(L[i:rec + 1]) if side == "long" else max(H[i:rec + 1])
                avg20 = sum(V[i - 20:i]) / 20 if i >= 20 else 0
                ratio = V[i] / avg20 if avg20 else None
                vt = vtype(ratio)
                if vt not in OPTS["types"]:
                    continue
                rec_ratio = (V[rec] / avg20) if avg20 else None
                stop = ext * (1 - STOP_BUFFER_PCT) if side == "long" else ext * (1 + STOP_BUFFER_PCT)
                target = resistance if side == "long" else support
                tr = resistance - support
                base = dict(symbol=sym, tf=tf, side=side, time=Tm[i], event=f"{sym}-{side}-{Tm[i]}", support=support, resistance=resistance, vol_type=vt, vol_ratio=round(ratio, 2) if ratio else None)
                # --- Wyckoff entry bar --- (needed for WYCKOFF trades AND for PARTIAL's early leg; skip if neither wanted)
                w = None
                if {"WYCKOFF", "PARTIAL"} & want:
                    w_bar = None
                    if OPTS["entry"] == "book" and (vt == 1 or (vt == 3 and rec_ratio is not None and rec_ratio >= VOL["high_min_ratio"])):
                        w_bar = rec
                    else:  # retest (type 2, or type 3 without high-volume reclaim)
                        for j in range(rec + 1, min(rec + 1 + T, n)):
                            if side == "long":
                                ok = ext <= L[j] <= support + tr / 3 and V[j] < V[i] and C[j] >= L[j] + 0.5 * (H[j] - L[j])
                            else:
                                ok = resistance - tr / 3 <= H[j] <= ext and V[j] < V[i] and C[j] <= H[j] - 0.5 * (H[j] - L[j])
                            if (side == "long" and L[j] <= stop) or (side == "short" and H[j] >= stop):
                                break
                            if ok:
                                w_bar = j; break
                    if w_bar is not None:
                        w = walk(side, C[w_bar], stop, target, H, L, C, w_bar + 1, HZ)
                        if w and "WYCKOFF" in want:
                            trades["WYCKOFF"].append(dict(base, entry=C[w_bar], entry_time=Tm[w_bar], stop=stop, target=target, exit_time=Tm[w["exit"]], **w))
                # --- Combined: Spring + ICT confirmation --- (needed for COMBINED trades AND PARTIAL's add leg)
                c_trade = None
                if {"COMBINED", "PARTIAL"} & want:
                    ict = find_ict(side, i, rec, H, L, C, K, n, PH, PL)
                    if ict and (vt in (1, 2) or (vt == 3 and rec_ratio is not None and rec_ratio >= VOL["high_min_ratio"])):
                        mss, edge, far = ict
                        fill = fvg_fill(side, mss, edge, far, stop, H, L, K, n)
                        # combined_entry: "limit" = limit at the FVG edge, no fill -> no trade (causal, maker fee);
                        # "market" = market at the MSS close always (causal, taker fee); "hindsight" = the pre-2026-09-11 rule
                        # (limit if the future shows a fill, else MSS close) -- NOT causal, kept only for comparison.
                        ce = OPTS["combined_entry"]
                        if ce == "limit" and fill is None:
                            e_bar = None
                        elif ce == "market":
                            e_bar, e_px = mss, C[mss]
                        else:
                            e_bar, e_px = (fill, edge) if fill is not None else (mss, C[mss])
                        cw = walk(side, e_px, stop, target, H, L, C, e_bar + 1, HZ) if e_bar is not None else None
                        if cw:
                            c_trade = dict(base, entry=e_px, entry_time=Tm[e_bar], stop=stop, target=target, exit_time=Tm[cw["exit"]], via="fvg" if fill is not None else "mss", **cw)
                            if "COMBINED" in want:
                                trades["COMBINED"].append(c_trade)
                # --- Partial: half at Wyckoff entry, half at combined entry ---
                if "PARTIAL" in want:
                    if w:
                        trades["PARTIAL"].append(dict(base, entry=C[w_bar], entry_time=Tm[w_bar], stop=stop, target=target, exit_time=Tm[w["exit"]], outcome=w["outcome"], R=w["R"], exit=w["exit"], size=0.5, leg="early"))
                        if c_trade:
                            trades["PARTIAL"].append(dict(c_trade, size=0.5, leg="add"))
                    elif c_trade:  # no early leg possible (no retest): the ICT-confirmed entry is taken at full size, as in COMBINED
                        trades["PARTIAL"].append(dict(c_trade, size=1.0, leg="add-only"))
    # ---------- WYCKOFF-BOOK / COMBINED-BOOK (scripts/wyckoff_rules.py: CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D) ----------
    if want & {"WYCKOFF-BOOK", "COMBINED-BOOK"}:
        W.PARAMS["spring_max_bars_outside"] = p["sob"]
        O = [x["open"] for x in c]
        for side, recs in (("long", W.detect_accumulations(O, H, L, C, V)), ("short", W.detect_distributions(O, H, L, C, V))):
            if side not in OPTS["sides"]:
                continue
            for r in recs:
                t0 = Tm[r["spring"] if r["spring"] is not None else r["sos"]]
                if htf is not None and not htf_allows(htf, t0, side):
                    continue
                if OPTS["sloped_gate"] and r["sloped"]:
                    continue
                if OPTS["st_min"] is not None and r["st_pct"] < OPTS["st_min"]:
                    continue
                tr = r["tr_hi"] - r["tr_lo"]
                base = dict(symbol=sym, tf=tf, side=side, time=t0, event=f"{sym}-{side}-book-{t0}", support=r["tr_lo"], resistance=r["tr_hi"], vol_type=r["vol_type"], vol_ratio=r["vol_ratio"],
                            st_pct=r["st_pct"], sot=r["sot"], path=r["path"])
                if r["path"] == "spring" and not r["shakeout"] and not r["abandon"] and not r["sot_too_strong"] and r["vol_type"] in OPTS["types"]:
                    rec = r["reclaim"]; vt = r["vol_type"]; rr = r["rec_ratio"]
                    stop = r["spring_low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + STOP_BUFFER_PCT)
                    target = r["tr_hi"] if side == "long" else r["tr_lo"]
                    if "WYCKOFF-BOOK" in want:
                        w_bar = rec if (OPTS["entry"] == "book" and (vt == 1 or (vt == 3 and rr is not None and rr >= VOL["high_min_ratio"]))) else r["test"]
                        if w_bar is not None:
                            w = walk(side, C[w_bar], stop, target, H, L, C, w_bar + 1, HZ)
                            if w:
                                trades["WYCKOFF-BOOK"].append(dict(base, entry=C[w_bar], entry_time=Tm[w_bar], stop=stop, target=target, exit_time=Tm[w["exit"]], leg="spring", **w))
                    if "COMBINED-BOOK" in want and rec is not None:
                        ict = find_ict(side, r["spring"], rec, H, L, C, K, n, PH, PL)
                        if ict:
                            mss, edge, far = ict
                            fill = fvg_fill(side, mss, edge, far, stop, H, L, K, n)
                            e_bar, e_px = (fill, edge) if fill is not None else (mss, C[mss])
                            cw = walk(side, e_px, stop, target, H, L, C, e_bar + 1, HZ)
                            if cw:
                                trades["COMBINED-BOOK"].append(dict(base, entry=e_px, entry_time=Tm[e_bar], stop=stop, target=target, exit_time=Tm[cw["exit"]], via="fvg" if fill is not None else "mss", **cw))
                if "WYCKOFF-BOOK" in want and OPTS["phase_d"] and r["bu"]:
                    b = r["bu"]["bar"]
                    stop = r["bu"]["low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["bu"]["low"] * (1 + STOP_BUFFER_PCT)
                    target = r["tr_hi"] + W.PARAMS["d_target_tr"] * tr if side == "long" else r["tr_lo"] - W.PARAMS["d_target_tr"] * tr
                    w = walk(side, C[b], stop, target, H, L, C, b + 1, HZ)
                    if w:
                        trades["WYCKOFF-BOOK"].append(dict(base, event=base["event"] + "-D", entry=C[b], entry_time=Tm[b], stop=stop, target=target, exit_time=Tm[w["exit"]], leg="phase_d", **w))
    # ---------- ICT only ----------
    # "live" (default): the LIVE scanner (scripts/ict-scan.py + scripts/htf_context.py) decides every structure --
    # pivot, sweep, MSS, FVG, dealing range, bias -- so the backtest measures the system actually traded (audit
    # 2026-09-13). "legacy": the pre-2026-09-13 in-file proxies below, kept reachable only for the old-vs-new
    # comparison a later task produces; do NOT change its behaviour. Skipped entirely (never calls the live
    # scanner) when "ICT" is not in `only` -- see scan()'s docstring.
    if "ICT" in want:
        if OPTS["rules"] == "live":
            trades["ICT"] = ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, resolve_methods(sym))
        else:
            for side in OPTS["sides"]:
                last_i = -99
                for i in range(R + 6, n - 3):
                    if i - last_i <= 5:
                        continue
                    if htf is not None and not htf_allows(htf, Tm[i], side):
                        continue
                    if side == "long":
                        pl = last_pivot(PL, i)
                        if pl is None or not L[i] < L[pl]:
                            continue
                        ext = L[i]; stop = ext * (1 - STOP_BUFFER_PCT); target = max(H[i - R:i])
                    else:
                        ph = last_pivot(PH, i)
                        if ph is None or not H[i] > H[ph]:
                            continue
                        ext = H[i]; stop = ext * (1 + STOP_BUFFER_PCT); target = min(L[i - R:i])
                    if OPTS["ict_pd"]:   # knowledge/04 §3.4 R13: longs in discount, shorts in premium of the R-bar range (proxy for the BSL<->SSL range)
                        eq_ = (max(H[i - R:i]) + min(L[i - R:i])) / 2
                        if (side == "long" and C[i] >= eq_) or (side == "short" and C[i] <= eq_):
                            continue
                    last_i = i
                    ict = find_ict(side, i, i, H, L, C, K, n, PH, PL, O=O)
                    if not ict:
                        continue
                    mss, edge, far = ict
                    # the sweep low may have extended after bar i up to the MSS: invalidation = lowest point of the excursion
                    ext2 = min(L[i:mss + 1]) if side == "long" else max(H[i:mss + 1])
                    stop = ext2 * (1 - STOP_BUFFER_PCT) if side == "long" else ext2 * (1 + STOP_BUFFER_PCT)
                    target = ict_target(side, i, mss, ext2, H, L, R, PH, PL, target)
                    if target is None:
                        continue
                    fill = fvg_fill(side, mss, edge, far, stop, H, L, K, n)
                    if fill is None:
                        continue
                    w = walk(side, edge, stop, target, H, L, C, fill + 1, HZ)
                    if w and ((side == "long" and target > edge) or (side == "short" and target < edge)):
                        trades["ICT"].append(dict(symbol=sym, tf=tf, side=side, time=Tm[i], entry=edge, entry_time=Tm[fill], stop=stop, target=target, exit_time=Tm[w["exit"]], vol_type=None, **w))
    return dict(symbol=sym, tf=tf, source=src, bars=n, first=Tm[0], last=Tm[-1], trades=trades)


def simulate(trades, fee_pct):
    """Chronological 1%-risk compounding account; one open position per symbol (a trade whose entry falls inside an open trade of the same symbol is skipped, except the second leg of the same PARTIAL event)."""
    ts = sorted(trades, key=lambda t: t["entry_time"])
    equity = START; open_pos = {}; curve = []; taken = []; ruin = None
    for t in ts:
        if t.get("R_planned", 99) < OPTS["min_rr"]:
            continue
        if equity <= RUIN_FRAC * START:
            ruin = ruin or curve[-1][0]
            break
        until, ev = open_pos.get(t["symbol"], ("", None))
        if t["entry_time"] < until and t.get("event") != ev:
            continue
        open_pos[t["symbol"]] = (max(until, t["exit_time"]) if t.get("event") == ev else t["exit_time"], t.get("event"))
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        fee_R = 2 * fee_pct / dist
        net_R = t["R"] - fee_R
        size = t.get("size", 1.0)
        pnl = equity * RISK * size * net_R
        equity += pnl
        taken.append(dict(t, net_R=round(net_R, 3), pnl=pnl))
        curve.append((t["exit_time"], equity))
    curve.sort()
    if equity <= RUIN_FRAC * START and ruin is None:
        ruin = curve[-1][0]
    SIM_LAST["ruin"] = ruin
    return equity, curve, taken


SIM_LAST = {"ruin": None}   # date of the account blow-up in the last simulate() call, or None


def period_returns(curve, first, last, key):
    """Returns per period from the equity curve (equity at end of period vs end of previous period)."""
    eq_by = {}
    for t, e in curve:
        eq_by[key(t)] = e
    periods = sorted(set(key(t) for t, _ in curve) | {key(first), key(last)})
    out = []; prev = START
    for pkey in periods:
        e = eq_by.get(pkey, prev)
        out.append((pkey, (e / prev - 1) * 100)); prev = e
    return out


def month_key(t): return t[:7]
def quarter_key(t): return f"{t[:4]}-Q{(int(t[5:7]) - 1) // 3 + 1}"
def year_key(t): return t[:4]


def max_dd(curve):
    peak = START; dd = 0.0
    for _, e in curve:
        peak = max(peak, e); dd = max(dd, (peak - e) / peak)
    return dd * 100


def summarize(taken):
    rs = [t["net_R"] * t.get("size", 1.0) for t in taken]
    if not rs:
        return dict(n=0)
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    return dict(n=len(rs), win_rate=len(wins) / len(rs) * 100, avg_R=statistics.mean(rs), sum_R=sum(rs), pf=(sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,1H,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--fee-pct", type=float, default=0.05, help="taker fee per side in percent"); ap.add_argument("--out"); ap.add_argument("--json")
    ap.add_argument("--min-rr", type=float, default=0.0, help="skip trades whose PLANNED R (target distance / stop distance) is below this")
    ap.add_argument("--types", default="1,2,3", help="Spring/Upthrust volume types allowed for WYCKOFF/COMBINED/PARTIAL")
    ap.add_argument("--range-touches", type=int, default=0, help="require this many tests of EACH border before a Spring counts (0 = off)")
    ap.add_argument("--htf", action="store_true", help="higher-timeframe boundary filter (long only when the HTF is in the lower third of its range or above it)")
    ap.add_argument("--sides", default="long,short")
    ap.add_argument("--entry", default="book", choices=["book", "test"], help="Wyckoff entry: 'book' = type-1 at reclaim, others at retest; 'test' = always wait for the retest (WA p80: Test = confirmation)")
    ap.add_argument("--mgmt", default="none", choices=["none", "be"], help="'be' = move stop to entry once +1R is reached (WMT p272)")
    ap.add_argument("--sloped-gate", action="store_true", help="book engine: skip sloped structures (WA p167)")
    ap.add_argument("--st-min", type=float, default=None, help="book engine: require ST[A] at least this fraction of the TR above the SC (WA p75: 0.5 = supply thinned)")
    ap.add_argument("--no-phase-d", action="store_true", help="book engine: no BU/LPS Phase D entries")
    ap.add_argument("--combined-entry", default="limit", choices=["limit", "market", "hindsight"], help="COMBINED entry rule (see scan); default limit = causal")
    ap.add_argument("--ict-target", default="range", choices=["range", "std2", "std25", "std4", "erl_next", "irl"], help="ICT target model (see ict_target)")
    ap.add_argument("--ict-disp", action="store_true", help="require a displacement candle for the MSS (knowledge/04 §2.16; project ratios)")
    ap.add_argument("--ict-pd", action="store_true", help="ICT-only: longs from discount / shorts from premium of the R-bar range (knowledge/04 §3.4 R13)")
    ap.add_argument("--std-origin", default="pivot", choices=["pivot", "highest"], help="std projection fib-0 anchor (see docstring)")
    ap.add_argument("--rules", choices=["live", "legacy"], default="live",
                    help="live = the rules scripts/ict-scan.py + scripts/htf_context.py run (default); "
                         "legacy = the pre-2026-09-13 in-file proxies, kept for comparison")
    ap.add_argument("--methods", default=None,
                    help="comma-separated bias-reading methods (wyckoff,ict) for the live ICT rules; "
                         "default = resolved per symbol from /automation (htf_context.engaged_methods_for_market)")
    a = ap.parse_args(); fee = a.fee_pct / 100
    OPTS.update(min_rr=a.min_rr, types=tuple(int(x) for x in a.types.split(",")), range_touches=a.range_touches, htf=a.htf, sides=tuple(a.sides.split(",")), entry=a.entry, mgmt=a.mgmt, sloped_gate=a.sloped_gate, st_min=a.st_min, phase_d=not a.no_phase_d, combined_entry=a.combined_entry, ict_target=a.ict_target,
                ict_disp=a.ict_disp, ict_pd=a.ict_pd, std_origin=a.std_origin, rules=a.rules, methods=tuple(a.methods.split(",")) if a.methods else None)
    today = datetime.date.today().isoformat()
    L = [f"# Wyckoff vs ICT vs kết hợp — lợi nhuận theo tháng/quý/năm, rủi ro 1%/lệnh — đo {today}", "",
         f"_Bộ lọc: R/R kế hoạch ≥ {a.min_rr} · loại KL {a.types} · biên TR chạm ≥ {a.range_touches} lần mỗi bên · lọc khung lớn {'bật' if a.htf else 'tắt'} · chiều {a.sides} · vào lệnh Wyckoff {a.entry} · quản lý {a.mgmt} · phí {a.fee_pct}%/chiều · target ICT {a.ict_target} · displacement {'bật' if a.ict_disp else 'tắt'} · P/D gate {'bật' if a.ict_pd else 'tắt'} · gốc STD {a.std_origin}_", "",
         f"_`scripts/backtest-methods.py` trên nến lưu tại `data/history/`; phí taker {a.fee_pct}%/chiều; mọi định nghĩa và THAM SỐ DỰ ÁN ở docstring của script. Số ở đây là của proxy bằng code, không phải của phân tích đầy đủ — đọc caveats cuối file._", ""]
    allres = {}
    for tf in a.tf.split(","):
        scans = [s for s in (scan(sym, tf) for sym in a.symbols.split(",")) if s]
        if not scans:
            continue
        first = min(s["first"] for s in scans); last = max(s["last"] for s in scans)
        L += [f"## Khung {tf} — {first[:10]} → {last[:10]} ({', '.join(f'{s['symbol']} {s['bars']} nến' for s in scans)})", ""]
        methods = ("WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK", "PARTIAL")
        res = {}
        for m in methods:
            tr = [t for s in scans for t in s["trades"][m]]
            eq, curve, taken = simulate(tr, fee)
            res[m] = dict(final=eq, curve=curve, taken=taken, stats=summarize(taken), dd=max_dd(curve), ruin=SIM_LAST["ruin"],
                          months=period_returns(curve, first, last, month_key), quarters=period_returns(curve, first, last, quarter_key), years=period_returns(curve, first, last, year_key))
        allres[tf] = res
        days = (datetime.date.fromisoformat(last[:10]) - datetime.date.fromisoformat(first[:10])).days or 1
        L += [f"| Phương pháp | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối (từ ${START:,.0f}) | %/năm (quy đổi) | Sụt giảm tối đa | Cháy |", "|---|---|---|---|---|---|---|---|---|---|"]
        for m in methods:
            r = res[m]; s = r["stats"]
            if not s["n"]:
                L.append(f"| {m} | 0 | — | — | — | — | — | — | — | — |"); continue
            ann = ((r["final"] / START) ** (365 / days) - 1) * 100
            ruin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else "—"
            L.append(f"| {m} | {s['n']} | {s['win_rate']:.0f}% | {s['avg_R']:+.2f} | {s['sum_R']:+.1f} | {s['pf']:.2f} | ${r['final']:,.0f} ({(r['final'] / START - 1) * 100:+.1f}%) | {ann:+.1f}% | −{r['dd']:.1f}% | {ruin} |" if s["pf"] else
                     f"| {m} | {s['n']} | {s['win_rate']:.0f}% | {s['avg_R']:+.2f} | {s['sum_R']:+.1f} | — | ${r['final']:,.0f} ({(r['final'] / START - 1) * 100:+.1f}%) | {ann:+.1f}% | −{r['dd']:.1f}% | {ruin} |")
        for label, key in (("năm", "years"), ("quý", "quarters"), ("tháng", "months")):
            keys = [k for k, _ in res["WYCKOFF"][key]]
            L += ["", f"**Theo {label} (% thay đổi vốn)**", "", "| Kỳ | " + " | ".join(methods) + " |", "|---|" + "---|" * len(methods)]
            for k in keys:
                L.append(f"| {k} | " + " | ".join(f"{dict(res[m][key]).get(k, 0):+.1f}%" for m in methods) + " |")
            if label == "tháng":
                L += ["", "| Tháng (thống kê) | " + " | ".join(methods) + " |", "|---|" + "---|" * len(methods)]
                L.append("| trung bình | " + " | ".join(f"{statistics.mean(v for _, v in res[m]['months']):+.1f}%" for m in methods) + " |")
                L.append("| trung vị | " + " | ".join(f"{statistics.median(v for _, v in res[m]['months']):+.1f}%" for m in methods) + " |")
                L.append("| tháng dương | " + " | ".join(f"{sum(1 for _, v in res[m]['months'] if v > 0)}/{len(res[m]['months'])}" for m in methods) + " |")
        # per symbol / side
        L += ["", "**Theo mã và chiều (R ròng)**", "", "| Mã | Chiều | " + " | ".join(methods) + " |", "|---|---|" + "---|" * len(methods)]
        for sym in a.symbols.split(","):
            for side in ("long", "short"):
                cells = []
                for m in methods:
                    s = summarize([t for t in res[m]["taken"] if t["symbol"] == sym and t["side"] == side])
                    cells.append(f"n={s['n']} · {s['win_rate']:.0f}% · {s['avg_R']:+.2f}R" if s["n"] else "—")
                L.append(f"| {sym} | {side} | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## Caveats (đọc trước khi dùng)", "",
          "- Spring/Upthrust và MSS/FVG là *proxy bằng code*; không có cổng CHoCH, không đối nhãn, không Volume Profile, không footprint. Phân tích đầy đủ sẽ lọc bớt và kết quả thật khác.",
          "- Phí taker tính cả hai chiều trên giá trị lệnh; không tính trượt giá, funding. Với stop hẹp (scalping 15m) phí ăn một phần đáng kể của R.",
          "- Một vị thế mở/mã; lệnh trùng thời gian bị bỏ. Không lọc khung lớn (để so sánh công bằng giữa ba phương pháp).",
          "- Nến chạm cả stop và target trong cùng một nến tính là thua. Lệnh chưa đóng sau H nến được đóng theo giá đóng cửa (mark-to-market).",
          "- Tài khoản bắt đầu ${START:,.0f}; khi vốn ≤ 10 % vốn ban đầu thì coi là CHÁY: dừng giao dịch tại đó, ghi ngày cháy, các kỳ sau bằng 0. Kỳ chưa đủ dữ liệu chỉ tính phần có dữ liệu; %/năm quy đổi từ tổng % theo số ngày của mẫu.",
          "- R, K, T, H và ngưỡng khối lượng là THAM SỐ DỰ ÁN (không phải số trong sách); đổi chúng sẽ đổi kết quả. Không tối ưu hoá tham số ở đây."]
    md = "\n".join(L) + "\n"
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True); open(a.out, "w", encoding="utf-8").write(md); print(f"-> {a.out}")
    if a.json:
        slim = {tf: {m: dict(final=r["final"], dd=r["dd"], ruin=r["ruin"], stats=r["stats"], months=r["months"], quarters=r["quarters"], years=r["years"],
                             trades=[{k: v for k, v in t.items() if k != "exit"} for t in r["taken"]]) for m, r in res.items()} for tf, res in allres.items()}
        json.dump(dict(generated=today, fee_pct=a.fee_pct, results=slim), open(a.json, "w"), ensure_ascii=False, indent=1); print(f"-> {a.json}")


if __name__ == "__main__":
    main()
