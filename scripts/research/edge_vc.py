#!/usr/bin/env python3
"""Family VC: does the gold intraday-trend edge (H7, G9) concentrate on high-volatility days, or on early entries?
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md [VC-P1].

    python3 scripts/research/edge_vc.py manifest                                  # the code-sha256 lines for the seal
    python3 scripts/research/edge_vc.py dry-run --out <json>                      # outcome-blind: event COUNTS per half
    python3 scripts/research/edge_vc.py run --read xau-holdout --out docs/audits/<date>-edge-vc-xau-holdout.json
    python3 scripts/research/edge_vc.py run --read crypto --cx-amendment <json> --cx-closed <json> [...] \
        --spec-dir <dir> --commission <json> --out ...
    python3 scripts/research/edge_vc.py run --read forward --xau docs/audits/<date>-edge-vc-xau-holdout.json --out ...

Each read runs ONCE, from committed code whose sha256 the SEALED pre-registration lists (scripts/research/prereg_guard.py),
to the one output name `docs/audits/<YYYY-MM-DD>-edge-vc-<read>.json`; a second run of a read is refused even to another path
(`prereg_guard.require_read_once`).

(a) HIGH volatility day (F3 H5's own regime rule, scripts/research/edge_f3.py:30, :99-116): sigma_5m above the median sigma_5m
of the previous REGIME_DAYS (250) days that have one, given >= 125 of them; no VR when the history is shorter (counted,
excluded). VR = sigma / that median. Gold / silver use the research-mode sigma, which exists only on days that turn out
dense (scripts/research/edge_census.py:121-124): a same-day completeness selection, measured on this book in
docs/audits/2026-10-04-density-selection-check.md (it removes 55 H7 / 78 G9 gold trades of ~6,000; mean R moves <= 0.002 R).
(b) LONG HOLD (early entry): the trade's entry server-clock slot is earlier than the median entry slot of the same component's
decisive-window trades. The stop is k x sigma x sqrt(bars to the end of the day) (scripts/research/book_sim.py:59), so the
post-hoc "wide stop" mixes volatility with ENTRY TIME. The medians are computed once, on the decisive window (entry timing:
outcome-blind), recorded in its JSON and reused as constants by the report-only window, the forward read and any filter.

Outcome per trade: the book's mechanics at the stop of fvg-book v4 (k = 1.4, docs/architecture/trading-systems.json v4):
R_gross = side x (exit - entry) / stop distance, R_net = R_gross - cost / stop distance (scripts/research/book_sim.py:38-82).
book_sim keeps a signal on a server day's LAST bar: it enters at the next server day's first bar, with the signal day's
sigma; such a row takes the ENTRY day's VR, slot and bars (counted by the dry run: `entry_next_day`). The paper log drops
those signals (scripts/research/fvg_forward.py `signals`), so the forward read never has them.

Test statistic (every test): the SIDE-BALANCED difference 1/2 [(mean y True - False | long) + (same | short)].
* T1a, T2, T3: y = R_gross. Balancing by side removes an unconditional MARKET drift (side x mu x sqrt(bars) / (k sigma) is
  of opposite sign for longs and shorts; scripts/tests/test_edge_vc.py `test_constant_drift_does_not_pass_t1b`).
* T1b: y = R_bar = R_gross x sqrt(NB_REF / bars planned), each cell's mean WEIGHTED by the planned bars (`nb_weight`):
  sum(R_bar x nb) / sum(nb) = sqrt(NB_REF) x sum(R_gross x sqrt(nb)) / sum(nb). A constant per-bar EDGE in the trade's
  direction raises R by sqrt(bars) for BOTH sides, so early entries "win" a raw-R T1b with no conditional effect and side
  balancing does not remove it (synthetic, VC-P1 §7: +0.03 to +0.05 R at a pooled mean R of about 0.09). R_bar removes the
  sqrt(bars) scaling (`test_constant_edge_does_not_pass_t1b`). Its variance grows like 1 / nb, so an UNWEIGHTED mean would
  be ruled by the last-hour entries; the nb weights are its inverse variance (`test_late_entries_do_not_rule_t1b`). The
  raw-R T1b is report-only. NB_REF only rescales: the p-value does not depend on it.
Variance: CR1 cluster-robust by server day for the contrast as a whole (each day's summed influence across the four side x
half cells; for a weighted cell, a_i (y_i - mean) / sum a), so it stays valid when the halves share days (pooled crypto
symbols; H7 and G9 on one gold day in T1b). Student-t with min(days per side x half cell) - 1 df, one-sided (True > False).
The unbalanced pooled difference is report-only.

Reads:
* xau-holdout: H7 + G9 XAUUSD pooled -- T1a (volatility) and T1b (hold), Holm m = 2 -- and G9 XAGUSD (T2), trades whose ENTRY
  server day is before HOLDOUT_END. Lead decision 2026-10-04 (VC-P1 §3): window B (before 2008-12-10; no personal-account
  replay touched it) is DECISIVE; window A (before 2018-01-01; from 2008-12-10 all personal-account replays drop or size
  trades by stop width: PARTLY EXPOSED) is report-only, with the decisive window's hold medians. Window B is UNREAD-FOR-H,
  so a pass there is DISCOVERY-GRADE for the condition; TF is its confirmation. Silver has no trade with a VR before
  2008-12-10, so T2 is "not run (window)" and enters its Holm family with p = 1. The post-hoc quartile table says "since
  2018" and has no committed code (docs/audits/2026-10-04-personal-account.md:47-55): 2018 onwards is never a test. The
  trades themselves are EXPOSED (F3 / F4 selected them, A1 replayed them).
* crypto (T3): the FTMO crypto CFDs with the [CX-P1] point-in-time rules and the CX cost model (pit_trend.SpecCost), group A
  over its whole history and group B from 2024-03-01 only ([CX-P1] §3), to the CX amendment's end date. Runs only after
  every scheduled CX read is done (checked from the committed CX read JSONs, `cx_closure`).
* forward (TF): the paper log's H7 / G9 XAUUSD rows at stop_k 1.4 entering on a server day AFTER the server day of the seal
  commit (git, `prereg_guard.first_forward_day`; no date is typed), read once at >= 150 closed rows or 365 days after the
  seal; it tests only the T1 sub-test(s) that passed the holdout (Holm at 0.10), whose JSON must be the committed
  xau-holdout read (`prereg_guard.require_read_json`). R_net is re-priced from each row's logged entry / exit at the cost
  profile the read records (the log's own R, priced at resolve time with no profile recorded, is kept as `R_net_log`). Its
  JSON carries the dataset snapshot (paper-log sha256, merged-candle digest and sources, cost profile) and the rows used."""
import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PT = _load("pit_trend", "scripts/research/pit_trend.py")
G = _load("prereg_guard", "scripts/research/prereg_guard.py")

PREREG = "docs/plans/2026-10-04-vc-volatility-condition-preregistration.md"
TAG = "[VC-P1]"
FAMILY = "vc"                          # read outputs: docs/audits/<YYYY-MM-DD>-edge-vc-<read>.json
SCRIPT = "scripts/research/edge_vc.py"
TESTS_FILE = "scripts/tests/test_edge_vc.py"
#: Every file whose content can change a VC read: this script, its tests, and every repository module a read executes
#: (traced: scripts/tests/test_edge_vc.py `test_code_lists_every_module_a_read_loads`). The sealed text lists each one's
#: sha256 (`manifest`); the guard recomputes them and refuses on any difference.
CODE = (SCRIPT, TESTS_FILE, "scripts/tests/test_pit_trend.py", "scripts/tests/test_prereg_guard.py",
        "scripts/research/pit_trend.py", "scripts/research/prereg_guard.py", "scripts/research/edge_census.py",
        "scripts/research/edge_f3.py", "scripts/research/edge_f4.py", "scripts/research/book_sim.py",
        "scripts/research/fvg_book_sim.py", "scripts/research/fvg_forward.py", "scripts/real_costs.py",
        "scripts/history_store.py", "scripts/mt5_time.py", "scripts/providers.py", "scripts/instruments.py",
        "scripts/broker_symbols.py")
PROVIDER = "mt5_bridge_ftmo"
REGIME_DAYS = 250                      # == edge_f3.REGIME_DAYS
MIN_HIST = REGIME_DAYS // 2            # the H5 rule: >= 125 previous days with a sigma
#: The holdout windows (VC-P1 §3). Both end strictly before the date. Lead decision 2026-10-04: B is the DECISIVE test,
#: A is report-only (partly exposed: all personal-account replays drop or size trades by stop width from PA_SPAN_START on).
HOLDOUT_WINDOWS = {"A": datetime.date(2018, 1, 1), "B": datetime.date(2008, 12, 10)}
HOLDOUT = "B"
HOLDOUT_END = HOLDOUT_WINDOWS[HOLDOUT]
REPORT_WINDOW = "A" if HOLDOUT == "B" else "B"
REPORT_END = HOLDOUT_WINDOWS[REPORT_WINDOW]
LOAD_END = max(HOLDOUT_WINDOWS.values())          # rows are built once, up to the wider window, then split
#: First day of the personal-account replays' common span (docs/audits/2026-10-04-personal-account.json meta.common_span):
#: every personal-account replay (skip, floor, floor_cap, fixed cap) drops or sizes trades by an absolute stop width.
PA_SPAN_START = datetime.date(2008, 12, 10)
K = 1.4                                # fvg-book v4
K_REPORT = 2.0                         # v3, report-only
NB_REF = 144                           # T1b: R_bar = R_gross x sqrt(NB_REF / planned bars); half a 288-bar day (a scale)
GOLD = ("H7_XAUUSD_eod", "G9_XAUUSD_eod")
SILVER = ("G9_XAGUSD_eod",)
ALPHA_T1 = 0.05
ALPHA_SECONDARY = 0.05                 # Holm over {T2, T3}
ALPHA_FORWARD = 0.10
CRYPTO_MIN_BARS = 230                  # [CX-P1] §1: 0.8 x 288
CX_TAG = "[CX-P1]"
CX_A_READS = ("discovery", "confirmation", "exposed")
CX_B_READ = "single"
CX_B_FROM = datetime.date(2024, 3, 1)  # [CX-P1] §3: group B's development window is not used
FWD_MIN_ROWS = 150
FWD_MAX_DAYS = 365
SIDES = (1, -1)


def server_zone():
    import real_costs as RC
    return RC.server_zone(PROVIDER)[1]


def slot_of(dt, zone):
    """Server-clock minutes from midnight of an aware datetime (a bar's open)."""
    t = dt.astimezone(zone)
    return t.hour * 60 + t.minute


def bars_to_day_end(dt, zone):
    """5m bars from an entry bar opening at `dt` to the server rollover, on the clock: the bar count of the paper log's stop
    (scripts/research/fvg_forward.py `bars_to_day_end`, same arithmetic)."""
    lt = dt.astimezone(zone)
    end = datetime.datetime.combine(lt.date() + datetime.timedelta(days=1), datetime.time(0), tzinfo=zone)
    return max(1, int((end - dt).total_seconds() // 300))


def per_bar(r_gross, nb):
    """R_bar = R_gross x sqrt(NB_REF / nb): R per sqrt(bar) of the stop's own horizon nb (so, the move per bar in stop units),
    scaled to R at an NB_REF-bar hold. A constant per-bar edge gives the same mean R_bar at every entry time (T1b's
    statistic, averaged with `nb_weight`; module docstring)."""
    return r_gross * math.sqrt(NB_REF / max(1, nb))


def nb_weight(r):
    """T1b's row weight: the planned bars. Var(R_bar) = NB_REF / nb x Var(R) and Var(R) hardly depends on nb (the stop
    scales with sqrt(nb)), so nb is the inverse variance; the weighted cell mean is sqrt(NB_REF) x sum(R x sqrt(nb)) /
    sum(nb)."""
    return max(1, r["nb_planned"])


# ------------------------------------------------------------------------------------------------ condition
def vr_by_day(sig_by_day, regime_days=REGIME_DAYS, min_hist=MIN_HIST):
    """{day: sigma / median(sigma over the previous <= regime_days days that have one)} when >= min_hist such days."""
    days = sorted(d for d, v in sig_by_day.items() if v)
    out = {}
    for k, d in enumerate(days):
        hist = [sig_by_day[x] for x in days[max(0, k - regime_days):k]]
        if len(hist) >= min_hist:
            med = statistics.median(hist)
            if med > 0:
                out[d] = sig_by_day[d] / med
    return out


def _as_date(d):
    return datetime.date.fromisoformat(d) if isinstance(d, str) else d


def label(rows, vr, day_key="day"):
    """(rows with `vr` and `high`, number without a VR). HIGH iff VR > 1 (sigma above the median)."""
    kept, missing = [], 0
    for r in rows:
        v = vr.get(_as_date(r[day_key]))
        if v is None:
            missing += 1
            continue
        kept.append(dict(r, vr=v, high=v > 1.0))
    return kept, missing


def mark_hold(rows, medians=None):
    """long_hold iff the entry slot is EARLIER than the component's median entry slot (more bars left in the day). With
    `medians` None they are computed from `rows` (the decisive xau-holdout window only); every later use passes the
    recorded ones. A component without a recorded median gets long_hold None (excluded from hold tests)."""
    if medians is None:
        by_c = collections.defaultdict(list)
        for r in rows:
            by_c[r["component"]].append(r["entry_slot"])
        medians = {c: statistics.median(v) for c, v in by_c.items()}
    for r in rows:
        m = medians.get(r["component"])
        r["long_hold"] = None if m is None else r["entry_slot"] < m
    return medians


# ------------------------------------------------------------------------------------------------ statistics
def _ec():
    global _EC
    if _EC is None:
        _EC = _load("edge_census", "scripts/research/edge_census.py")
    return _EC


_EC = None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _wmean(rows, value, row_weight=None):
    """Mean of `value` over rows, weighted by `row_weight(r)` when given; None for no rows."""
    if not rows:
        return None
    a = row_weight or (lambda r: 1.0)
    return sum(a(r) * r[value] for r in rows) / sum(a(r) for r in rows)


def _contrast(rows, value, cell_of, weights, day_key="day", row_weight=None):
    """sum_c w_c x m_c, m_c the mean of `value` in cell c -- weighted by a_i = row_weight(r) when given (a ratio estimator,
    m_c = sum a_i y_i / A_c, A_c = sum of a over the cell; unweighted: a_i = 1, A_c = n_c) -- with a CR1 cluster-robust SE
    by day over the whole contrast: each day's summed influence u_g = sum_i w_c(i) a_i (y_i - m_c(i)) / A_c(i);
    var = G / (G - 1) x sum_g u_g^2. One cluster per day across all cells, so it stays valid when cells share days. None
    when a weighted cell is empty."""
    cells = collections.defaultdict(list)
    for r in rows:
        c = cell_of(r)
        if c in weights:
            cells[c].append(r)
    if any(not cells[c] for c in weights):
        return None
    a = row_weight or (lambda r: 1.0)
    tot = {c: sum(a(r) for r in cells[c]) for c in weights}
    means = {c: sum(a(r) * r[value] for r in cells[c]) / tot[c] for c in weights}
    u = collections.defaultdict(float)
    for c in weights:
        t, m, w = tot[c], means[c], weights[c]
        for r in cells[c]:
            u[str(r[day_key])] += w * a(r) * (r[value] - m) / t
    g = len(u)
    se = math.sqrt(g / (g - 1) * sum(x * x for x in u.values())) if g >= 2 else None
    return {"est": sum(weights[c] * means[c] for c in weights), "se": se, "means": means,
            "n": {c: len(cells[c]) for c in weights}, "days": {c: len({str(r[day_key]) for r in cells[c]}) for c in weights}}


def split_test(rows, key="high", value="R_gross", net="R_net", day_key="day", row_weight=None):
    """True half minus False half of `key`, SIDE-BALANCED (module docstring), CR1 by day over the whole contrast; one-sided p
    for True > False, on `value` (R_gross; T1b: R_bar with row_weight=nb_weight). Rows whose `key` is None are left out.
    mean_high / mean_low use the same weights; the net means (the tradability gate) are plain per-trade means. Report-only:
    the unbalanced pooled difference, per-cell means, days shared by the two halves, mean planned bars per half."""
    rows = [r for r in rows if r.get(key) is not None]
    hi = [r for r in rows if r[key]]
    lo = [r for r in rows if not r[key]]
    days_hi = {str(r[day_key]) for r in hi}
    days_lo = {str(r[day_key]) for r in lo}
    out = {"n_high": len(hi), "n_low": len(lo), "days_high": len(days_hi), "days_low": len(days_lo),
           "shared_days": len(days_hi & days_lo),
           "mean_high": _wmean(hi, value, row_weight), "mean_low": _wmean(lo, value, row_weight),
           "net_mean_high": (sum(r[net] for r in hi) / len(hi)) if hi and net else None,
           "net_mean_low": (sum(r[net] for r in lo) / len(lo)) if lo and net else None,
           "statistic": value, "weight": getattr(row_weight, "__name__", None) if row_weight else None,
           "mean_bars_high": _mean([r.get("nb_planned") for r in hi]),
           "mean_bars_low": _mean([r.get("nb_planned") for r in lo]),
           "diff": None, "se": None, "df": None, "t": None, "p_one_sided": 1.0, "cells": None, "pooled_report_only": None}
    pooled = _contrast(rows, value, lambda r: bool(r[key]), {True: 1.0, False: -1.0}, day_key, row_weight)
    if pooled:
        out["pooled_report_only"] = {"diff": pooled["est"], "se": pooled["se"]}
    weights = {(s, h): (0.5 if h else -0.5) for s in SIDES for h in (True, False)}
    bal = _contrast(rows, value, lambda r: (r["side"], bool(r[key])), weights, day_key, row_weight)
    if bal is None:
        return out
    out["cells"] = {f"side={s}|{'T' if h else 'F'}": {"n": bal["n"][(s, h)], "days": bal["days"][(s, h)],
                                                     "mean": bal["means"][(s, h)]} for s, h in weights}
    df = min(bal["days"].values()) - 1
    out.update(diff=bal["est"], se=bal["se"], df=df)
    if bal["se"] and bal["se"] > 0 and df > 0:
        t = bal["est"] / bal["se"]
        out.update(t=t, p_one_sided=_ec().t_sf(t, df))
    return out


def holm(pvals, alpha):
    """Holm step-down: list of booleans (rejected) in the input order."""
    order = sorted(range(len(pvals)), key=lambda k: pvals[k])
    rej = [False] * len(pvals)
    m = len(pvals)
    for rank, k in enumerate(order):
        if pvals[k] <= alpha / (m - rank):
            rej[k] = True
        else:
            break
    return rej


def diagnostics(rows):
    """Report-only (VC-P1 §6): the literal finding (stop-width quartiles, cut points from these rows' own stop_bp), VR x
    hold, long / short, per year. Means of R_gross and R_net, the nb-weighted mean of R_bar (T1b's cell mean) and the mean
    planned bars where the rows carry them."""
    def stats(rs):
        if not rs:
            return {"n": 0}
        wb = [r for r in rs if r.get("R_bar") is not None and r.get("nb_planned")]
        return {"n": len(rs), "R_gross": sum(r["R_gross"] for r in rs) / len(rs),
                "R_net": sum(r["R_net"] for r in rs) / len(rs), "R_bar": _wmean(wb, "R_bar", nb_weight),
                "bars_planned": _mean([r.get("nb_planned") for r in rs])}

    out = {}
    if not rows:
        return out
    sb = sorted(r["stop_bp"] for r in rows)
    cuts = [sb[int(len(sb) * q)] for q in (0.25, 0.5, 0.75)]
    out["stop_bp_cuts"] = cuts
    out["stop_quartiles"] = [stats([r for r in rows if (r["stop_bp"] >= (cuts[q - 1] if q else -1)) and
                                    (q == 3 or r["stop_bp"] < cuts[q])]) for q in range(4)]
    if any(r.get("long_hold") is not None for r in rows):
        out["vr_x_hold"] = {f"{'high' if h else 'low'}|{'long' if lg else 'short'}":
                            stats([r for r in rows if r["high"] == h and r.get("long_hold") is lg])
                            for h in (True, False) for lg in (True, False)}
    out["side"] = {str(s): {"high": stats([r for r in rows if r["side"] == s and r["high"]]),
                            "low": stats([r for r in rows if r["side"] == s and not r["high"]])} for s in SIDES}
    years = sorted({str(r["day"])[:4] for r in rows})
    out["by_year"] = {y: {"high": stats([r for r in rows if str(r["day"])[:4] == y and r["high"]]),
                          "low": stats([r for r in rows if str(r["day"])[:4] == y and not r["high"]])} for y in years}
    return out


# ------------------------------------------------------------------------------------------------ gold / silver holdout
_SERIES = {}


def _xau_series(sym):
    """edge_census research-mode Series over all history (cached: book_sim.trades loads its own copy)."""
    if sym not in _SERIES:
        _SERIES[sym] = _ec().load(sym, end="9999-12-31T00:00:00Z")
    return _SERIES[sym]


def research_sig_by_day(s):
    """The F3 H5 sigma history: {dense day: sigma_5m} (research mode, scripts/research/edge_f3.py:100-104)."""
    return {d: s._vol[d] for d in s.dense_days if s._vol.get(d)}


def book_rows(trades, s, zone):
    """book_sim.trades rows -> VC rows keyed by the ENTRY server day, with the entry's server-clock slot, the bars from the
    entry to the day's last bar (book_sim's nb: the stop's own horizon), R_bar, and whether the signal was on the previous
    server day's last bar (`entry_next_day`)."""
    idx = {t: i for i, t in enumerate(s.T)}
    out = []
    for t in trades:
        i = idx.get(t["entry_time"])
        if i is None:
            continue
        d = s.sday[i]
        nb = s.day_rows[d][-1] - i + 1
        gross = t["R"] + t["cost_R"]
        out.append({"symbol": t["symbol"], "day": d, "side": t["side"], "R_net": t["R"], "R_gross": gross,
                    "R_bar": per_bar(gross, nb), "cost_R": t["cost_R"], "stop_bp": t["stop_bp"],
                    "entry_slot": slot_of(s.dt[i], zone), "nb_planned": nb, "exit": t["exit"],
                    "entry_time": t["entry_time"],
                    # entry at the first bar of its server day: H7 / G9 enter at the bar after the signal, so the signal was
                    # the previous server day's last bar (the stop used that day's sigma; this row takes the entry day's VR)
                    "entry_next_day": i > 0 and i == s.day_rows[d][0]})
    return out


def holdout_rows(component, k, end_day=None, trades_fn=None, series_fn=None, zone=None):
    """(rows labelled HIGH / LOW with entry day < end_day, info) for one book component. info: the trades before end_day,
    how many have no VR, and their entry days (`no_vr_days`, for per-window counts)."""
    end_day = end_day or HOLDOUT_END
    BS = _load("book_sim", "scripts/research/book_sim.py")
    sym, det, hold = BS.COMPONENTS[component]
    trades = (trades_fn or BS.trades)(sym, det, hold, stop_k=k)
    s = (series_fn or _xau_series)(sym)
    vr = vr_by_day(research_sig_by_day(s))
    rows = [r for r in book_rows(trades, s, zone or server_zone()) if r["day"] < end_day]
    for r in rows:
        r["component"] = component
    kept, missing = label(rows, vr)
    return kept, {"trades_before_end": len(rows), "without_vr": missing,
                  "no_vr_days": [r["day"] for r in rows if vr.get(_as_date(r["day"])) is None]}


def t1_verdict(t1a, t1b, per_a, per_b):
    """T1 = {T1a volatility, T1b hold length} on pooled gold, Holm m = 2 at ALPHA_T1; a rejected sub-test passes only if
    its True half's mean NET R > 0 and both gold components' differences are > 0."""
    rej = holm([t1a["p_one_sided"], t1b["p_one_sided"]], ALPHA_T1)
    ok = []
    for r, t, per in zip(rej, (t1a, t1b), (per_a, per_b)):
        ok.append(bool(r and (t["net_mean_high"] or 0) > 0 and all((per[c]["diff"] or 0) > 0 for c in GOLD)))
    return {"T1a_volatility": ok[0], "T1b_hold_length": ok[1], "holm_rejected": rej}


def _tests_on(rows_by_c):
    """T1a on R_gross, T1b on the nb-weighted R_bar (module docstring); per component the same; the raw-R T1b is
    report-only."""
    gold = [r for c in GOLD for r in rows_by_c.get(c, [])]
    return {"T1a_xau_volatility": split_test(gold),
            "T1b_xau_hold_length": split_test(gold, key="long_hold", value="R_bar", row_weight=nb_weight),
            "T1b_raw_R_report_only": split_test(gold, key="long_hold"),
            "per_component_volatility": {c: split_test(v) for c, v in rows_by_c.items()},
            "per_component_hold_length": {c: split_test(v, key="long_hold", value="R_bar", row_weight=nb_weight)
                                          for c, v in rows_by_c.items()}}


def _counts(rows_all, no_vr, end):
    """Per component, entries before `end`: trades with a VR, trades without one (excluded), and labelled trades whose
    signal was the previous server day's last bar."""
    return {c: {"with_vr": sum(1 for r in rows_all[c] if r["day"] < end),
                "without_vr": sum(1 for d in no_vr[c] if d < end),
                "entry_next_day": sum(1 for r in rows_all[c] if r["day"] < end and r.get("entry_next_day"))}
            for c in rows_all}


def xau_read(k=K, trades_fn=None, series_fn=None, zone=None, keep_rows=False, medians=None):
    """The xau-holdout read: tests on the DECISIVE window (HOLDOUT), the same tests report-only on REPORT_WINDOW with the
    decisive window's hold medians. Rows are built once up to LOAD_END and split by entry day."""
    rows_all, no_vr = {}, {}
    for c in GOLD + SILVER:
        rows_all[c], info = holdout_rows(c, k, end_day=LOAD_END, trades_fn=trades_fn, series_fn=series_fn, zone=zone)
        no_vr[c] = info["no_vr_days"]
    rows = {c: [r for r in v if r["day"] < HOLDOUT_END] for c, v in rows_all.items()}
    hold_medians = mark_hold([r for c in GOLD + SILVER for r in rows[c]], medians)
    mark_hold([r for c in GOLD + SILVER for r in rows_all[c]], hold_medians)      # the same recorded cut everywhere
    t = _tests_on(rows)
    t2 = t["per_component_volatility"][SILVER[0]]
    if not (t2["n_high"] or t2["n_low"]):
        t2 = dict(t2, not_run="window: no silver trade with a VR in the decisive window")
    out = {"T1a_xau_volatility": t["T1a_xau_volatility"], "T1b_xau_hold_length": t["T1b_xau_hold_length"],
           "T1_verdict": t1_verdict(t["T1a_xau_volatility"], t["T1b_xau_hold_length"], t["per_component_volatility"],
                                    t["per_component_hold_length"]),
           "T2_silver": t2, "T1b_raw_R_report_only": t["T1b_raw_R_report_only"],
           "per_component_volatility": t["per_component_volatility"],
           "per_component_hold_length": t["per_component_hold_length"],
           "hold_medians": hold_medians, "holdout": HOLDOUT, "holdout_end": str(HOLDOUT_END),
           "counts": _counts(rows_all, no_vr, HOLDOUT_END),
           "diagnostics": {"xau": diagnostics([r for c in GOLD for r in rows[c]]), "silver": diagnostics(rows[SILVER[0]])}}
    rep = {c: [r for r in v if r["day"] < REPORT_END] for c, v in rows_all.items()}
    out[f"report_only_window_{REPORT_WINDOW}"] = dict(
        _tests_on(rep), end=str(REPORT_END), counts=_counts(rows_all, no_vr, REPORT_END),
        partly_exposed_from=str(PA_SPAN_START), diagnostics={"xau": diagnostics([r for c in GOLD for r in rep[c]]),
                                                             "silver": diagnostics(rep[SILVER[0]])})
    if keep_rows:
        out["rows"] = rows_all
    return out


def secondary_verdict(p_t2, p_t3=None):
    """Holm (m = 2, alpha ALPHA_SECONDARY) over T2 (silver holdout) and T3 (crypto); a test not run enters with p = 1."""
    p = [1.0 if p_t2 is None else p_t2, 1.0 if p_t3 is None else p_t3]
    rej = holm(p, ALPHA_SECONDARY)
    return {"T2_silver": rej[0], "T3_crypto": rej[1], "p": p}


# ------------------------------------------------------------------------------------------------ crypto (T3)
def cx_closure(amendment, reads):
    """({"A": [...], "B": [...]}, end date, CX windows retired unread) once every scheduled CX read is done; Refused otherwise.

    Contract with scripts/research/edge_cx.py (not written yet: the coordinator reconciles field names BEFORE sealing, VC-P1
    §5.3): the committed screening amendment carries {"tag": "[CX-P1]", "end": "YYYY-MM-DD", "members": {"A": [...],
    "B": [...]}}; each committed read JSON carries meta {"tag": "[CX-P1]", "group": "A" | "B", "read": one of CX_A_READS for
    A or CX_B_READ for B} and "verdicts" {test: {"advances": bool}}. A group-A read after one where no test advanced is
    retired unread ([CX-P1] §5) and is NOT required; VC-X still reads that window (disclosed: `retired_windows_read`)."""
    if amendment.get("tag") != CX_TAG:
        raise G.Refused(f"refused: the CX amendment does not carry {CX_TAG}")
    members = amendment.get("members") or {}
    end = datetime.date.fromisoformat(amendment["end"])
    by = {}
    for doc in reads:
        m = doc.get("meta") or {}
        if m.get("tag") != CX_TAG:
            raise G.Refused(f"refused: a --cx-closed file is not a {CX_TAG} read")
        key = (m.get("group"), m.get("read"))
        if key in by:
            raise G.Refused(f"refused: CX read {key} given twice")
        by[key] = doc
    retired = []
    if members.get("A"):
        alive = True
        for read in CX_A_READS:
            if not alive:
                retired.append(f"A|{read}")
                continue
            doc = by.get(("A", read))
            if doc is None:
                raise G.Refused(f"refused: CX group A {read} read not done; VC-X waits for every scheduled CX read")
            alive = any(v.get("advances") for v in (doc.get("verdicts") or {}).values())
    if members.get("B") and ("B", CX_B_READ) not in by:
        raise G.Refused("refused: CX group B read not done; VC-X waits for every scheduled CX read")
    return {"A": list(members.get("A") or []), "B": list(members.get("B") or [])}, end, retired


def crypto_rows(sym, candles, zone, end_iso, cost, start_day=None, k=K, min_bars=CRYPTO_MIN_BARS):
    """VC rows for one crypto CFD: [CX-P1] events (pit_trend) entering on or after `start_day`, the book's stop mechanics at
    k with the CX cost model `cost` (pit_trend.SpecCost; required), labelled by the point-in-time VR. Earlier days feed
    sigma / VR only."""
    if cost is None:
        raise ValueError("VC-X needs the CX cost model (pit_trend.SpecCost): a gross-only crypto read is refused")
    b = PT.Bars(sym, candles, zone, end=end_iso)
    ctx = PT.context(b, min_bars, prev_rule="calendar")
    vr = vr_by_day({d: c["sigma"] for d, c in ctx.items()})
    out = []
    for rule, evs in PT.events(b, ctx).items():
        for ev in evs:
            if start_day is not None and ev["day"] < start_day:
                continue
            t = PT.stop_trade(b, ev, ctx, k, cost)
            t["day"] = ev["day"]
            t["entry_slot"] = ev["slot"]
            out.append(t)
    kept, missing = label(out, vr)
    return kept, {"events": len(out), "without_vr": missing, "eligible_days": len(ctx),
                  "start_day": str(start_day) if start_day else None}


# ------------------------------------------------------------------------------------------------ forward (TF)
def _utc(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def server_day_of(stamp, zone):
    """The server day of a UTC bar stamp (as edge_census.Series.sday)."""
    return _utc(stamp).astimezone(zone).date()


def is_forward_row(r, first_day, zone, k=K):
    """A closed H7 / G9 XAUUSD paper row at stop k entering on or after `first_day` (server day): TF's population. The same
    test decides the forward read's due count and its rows."""
    return (r.get("component") in GOLD and r.get("status") == "closed" and r.get("stop_k") == k
            and server_day_of(r["entry_time"], zone) >= first_day)


def forward_rows(log_rows, series, first_day, zone, costs, k=K):
    """TF's rows (`is_forward_row`; `first_day` = prereg_guard.first_forward_day), with R_gross from the logged entry / exit
    / stop distance, R_bar at the paper stop's own bar count (`bars_to_day_end`, on the clock as the log), VR from the
    series' dense-day sigma history (the H5 construction) and the entry slot. R_net is RE-PRICED here from the logged entry
    and exit times and prices with `costs` (edge_census.Costs at the profile the read records; the formula of
    fvg_forward.resolve_row), so the read reproduces from its snapshot; the log's own R (priced at resolve time, profile not
    recorded) is kept as R_net_log."""
    idx = {t: i for i, t in enumerate(series.T)}
    vr = vr_by_day(research_sig_by_day(series))
    out = []
    for r in log_rows:
        if not is_forward_row(r, first_day, zone, k):
            continue
        i = idx.get(r["entry_time"])
        if i is None:
            continue
        dist = r["stop_distance"]
        gross_px = r["side"] * (r["exit"] - r["entry"])
        cost_px = costs.round_trip_at(_utc(r["entry_time"]), _utc(r["exit_time"])) * r["entry"]
        gross = gross_px / dist
        nb = bars_to_day_end(series.dt[i], zone)
        out.append({"component": r["component"], "day": series.sday[i], "side": r["side"], "R_gross": gross,
                    "R_bar": per_bar(gross, nb), "nb_planned": nb, "R_net": (gross_px - cost_px) / dist,
                    "cost_R": cost_px / dist, "R_net_log": r.get("R"), "entry_time": r["entry_time"],
                    "exit_time": r["exit_time"], "entry": r["entry"], "exit": r["exit"],
                    "stop_distance": dist, "entry_slot": slot_of(series.dt[i], zone)})
    return label(out, vr)


def forward_tests(rows, which, medians):
    """TF: the T1 sub-tests that PASSED the holdout (`which` subset of {"a", "b"}), Holm at ALPHA_FORWARD, each on its
    holdout statistic ((a) R_gross, (b) the nb-weighted R_bar); (b) uses the holdout's recorded per-component median entry
    slots (`medians`), never the forward rows' own."""
    keys = {"a": ("high", "R_gross", None), "b": ("long_hold", "R_bar", nb_weight)}
    if "b" in which:
        mark_hold(rows, medians)
    tests = {w: split_test(rows, key=keys[w][0], value=keys[w][1], row_weight=keys[w][2]) for w in sorted(which)}
    rej = holm([t["p_one_sided"] for t in tests.values()], ALPHA_FORWARD) if tests else []
    for (w, t), r in zip(sorted(tests.items()), rej):
        t["passed"] = bool(r and (t["net_mean_high"] or 0) > 0)
    return tests


def forward_due(n_closed, seal_date, today):
    return n_closed >= FWD_MIN_ROWS or (today - seal_date).days >= FWD_MAX_DAYS


# ------------------------------------------------------------------------------------------------ dry run (counts only)
HALVES = ("high", "low", "long_hold", "short_hold")
SHORT_NB = 24                          # dry run: entries with fewer planned bars (the last two hours) are counted


def _quantiles(xs):
    """Planned-bar quantiles (the diagnostics' index rule: the value at int(n x q) of the sorted list) and the count under
    SHORT_NB; ints only."""
    xs = sorted(xs)
    if not xs:
        return {"n": 0}
    return dict({f"q{int(q * 100)}": xs[int(len(xs) * q)] for q in (0.1, 0.25, 0.5, 0.75, 0.9)}, n=len(xs),
                under_24=sum(1 for x in xs if x < SHORT_NB))


def _cells(evs):
    """{"side=S|half": {"n", "bars", "days"}} over events with a VR: half = high / low (VR), long_hold / short_hold (the
    event's `long_hold`, marked against its own component's median entry slot; None: no hold split)."""
    acc = collections.defaultdict(lambda: {"n": 0, "bars": 0, "days": set()})
    for ev in evs:
        if ev["high"] is None:
            continue
        halves = ["high" if ev["high"] else "low"]
        if ev["long_hold"] is not None:
            halves.append("long_hold" if ev["long_hold"] else "short_hold")
        for h in halves:
            a = acc[f"side={ev['side']}|{h}"]
            a["n"] += 1
            a["bars"] += ev["nb"]
            a["days"].add(ev["day"])
    return {k: {"n": v["n"], "bars": v["bars"], "days": len(v["days"])} for k, v in sorted(acc.items())}


def power_inputs(cells):
    """Outcome-blind power arithmetic from `_cells` counts (trades treated as independent; same-day trades share a CR1
    cluster, so the read's SE can be larger -- the cells' `days` bound that). se_per_sd: the side-balanced contrast's SE
    per unit of the per-trade sd of R, so MDE (80 % power, one-sided 0.025: the first Holm step) = 2.80 x sd(R) x se_per_sd:
    T1a sqrt(1/4 sum_c 1 / n_c) over the VR cells, T1b sqrt(1/4 sum_c NB_REF / bars_c) over the hold cells (the nb-weighted
    R_bar: Var = NB_REF x Var(R) / sum(nb) per cell), and the raw-R T1b for comparison. mean_bars per half (sides pooled) and
    the VR halves' gap |high - low| / min(high, low): VC-P1 §4 amends T1a to the weighted R_bar when it exceeds 0.10."""
    def get(side, h):
        return cells.get(f"side={side}|{h}", {"n": 0, "bars": 0})

    def se(hs, f):
        cs = [get(s, h) for s in SIDES for h in hs]
        return math.sqrt(0.25 * sum(f(c) for c in cs)) if all(c["n"] for c in cs) else None

    mean_bars = {}
    for h in HALVES:
        n = sum(get(s, h)["n"] for s in SIDES)
        mean_bars[h] = sum(get(s, h)["bars"] for s in SIDES) / n if n else None
    gap = None
    if mean_bars["high"] and mean_bars["low"]:
        gap = abs(mean_bars["high"] - mean_bars["low"]) / min(mean_bars["high"], mean_bars["low"])
    return {"mean_bars": mean_bars, "vr_halves_bars_gap": gap,
            "se_per_sd": {"T1a": se(("high", "low"), lambda c: 1.0 / c["n"]),
                          "T1b": se(("long_hold", "short_hold"), lambda c: NB_REF / c["bars"]),
                          "T1b_raw_R": se(("long_hold", "short_hold"), lambda c: 1.0 / c["n"])}}


def dry_counts(series_fn=None, zone=None):
    """Outcome-blind, per component and window ({"decisive": HOLDOUT, "report_only": REPORT_WINDOW}): book_sim's events (an
    entry bar exists and the signal day has a research-mode sigma) by VR half; the events dropped because the signal day
    has no research-mode sigma (`no_research_sigma`: the density selection, docs/audits/2026-10-04-density-selection-
    check.md); the events whose signal is a server day's last bar (`entry_next_day`); the hold halves at the median ENTRY
    slot of the decisive window (the (b) cut a read records), also split by VR half, so a timing imbalance between the VR
    halves is visible before any read; the planned bars (entry to the day's last bar: the stop's horizon and T1b's weight)
    as quantiles and the count under SHORT_NB; and per side x half the events, planned bars and days (`cells`). Pooled
    gold (H7 + G9, T1's population): the summed cells and `power_inputs` (VC-P1 §7, §10.3). No trade is simulated, no price
    after the signal is read."""
    BS = _load("book_sim", "scripts/research/book_sim.py")
    zone = zone or server_zone()
    windows = (("decisive", HOLDOUT, HOLDOUT_END), ("report_only", REPORT_WINDOW, REPORT_END))
    out, pooled = {}, {name: [] for name, _w, _e in windows}
    for c in GOLD + SILVER:
        sym, det, _hold = BS.COMPONENTS[c]
        s = (series_fn or _xau_series)(sym)
        vr = vr_by_day(research_sig_by_day(s))
        evs, no_sig = [], []
        for ev in det(s):
            e = ev["entry_i"]
            if e >= len(s.C):
                continue
            d = s.sday[e]
            if d >= LOAD_END:
                continue
            if not s.sigma(ev["i"]):
                no_sig.append(d)
                continue
            v = vr.get(d)
            evs.append({"day": d, "high": None if v is None else v > 1.0, "slot": slot_of(s.dt[e], zone),
                        "next_day": s.sday[ev["i"]] != d, "nb": s.day_rows[d][-1] - e + 1, "side": ev["side"]})
        dec = [x["slot"] for x in evs if x["day"] < HOLDOUT_END and x["high"] is not None]
        med = statistics.median(dec) if dec else None
        for x in evs:
            x["long_hold"] = None if med is None else x["slot"] < med         # the component's own median, as the read
        res = {"median_entry_slot": med}
        for name, w, end in windows:
            n = collections.Counter()
            inside = [x for x in evs if x["day"] < end]
            for x in inside:
                high = x["high"]
                n["no_vr" if high is None else ("high" if high else "low")] += 1
                n["entry_next_day"] += x["next_day"]
                if high is not None and x["long_hold"] is not None:
                    n[f"{'high' if high else 'low'}_{'long' if x['long_hold'] else 'short'}_hold"] += 1
            n["no_research_sigma"] = sum(1 for d in no_sig if d < end)
            res[name] = dict(n, window=w, end=str(end),
                             planned_bars=_quantiles([x["nb"] for x in inside if x["high"] is not None]),
                             cells=_cells(inside))
            if c in GOLD:
                pooled[name] += inside
        out[c] = res
    out["xau_pooled"] = {}
    for name, w, end in windows:
        cells = _cells(pooled[name])
        out["xau_pooled"][name] = dict(power_inputs(cells), window=w, end=str(end), cells=cells,
                                        planned_bars=_quantiles([x["nb"] for x in pooled[name] if x["high"] is not None]))
    return out


# ------------------------------------------------------------------------------------------------ CLI
def _dump(res, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {path}")


def _meta(read):
    return {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "read": read, "git_head": G.git_head(ROOT),
            "k": K, "k_report": K_REPORT, "regime_days": REGIME_DAYS, "min_hist": MIN_HIST, "nb_ref": NB_REF,
            "t1b_statistic": "R_bar, cell means weighted by nb_planned (nb_weight)",
            "holdout": HOLDOUT, "holdout_end": str(HOLDOUT_END), "report_window": REPORT_WINDOW,
            "report_end": str(REPORT_END), "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def cost_profile(syms):
    """The cost profile that prices book_sim's trades and the forward read's re-priced R_net (edge_census.Costs, at read
    time), with the sha256 of each symbol's spec file under it (CLAUDE.md §46)."""
    import real_costs as RC
    EC = _ec()
    out = {}
    for sym in syms:
        p = RC.spec_path(EC.COST_PROFILE, sym)
        out[sym] = G.file_sha256(p) if os.path.exists(p) else None
    return {"name": EC.COST_PROFILE, "spec_sha256": out}


def forward_snapshot(log_path, log_bytes, candles, sym="XAUUSD", ff=None):
    """The forward read's dataset snapshot (CLAUDE.md §10, §46): the paper log (untracked, appended by fvg_forward: the
    sha256 and row count of the bytes the read parsed; the read JSON also keeps the rows it used), the merged 5m candles the
    read used (canonical digest, count, first / last bar) and their sources (history_store digest of the stored history;
    sha256 of the forward store and live bridge files), and the cost profile `forward_rows` re-prices R_net at (the log's
    own R was priced by fvg_forward.resolve_row with whatever profile was current at resolve time; none was recorded)."""
    import history_store as HS
    FF = ff or _load("fvg_forward", "scripts/research/fvg_forward.py")

    def sha_or_none(p):
        return G.file_sha256(p) if os.path.exists(p) else None

    n_rows = sum(1 for x in log_bytes.decode("utf-8").splitlines() if x.strip())
    return {"paper_log": {"path": _rel(log_path), "sha256": hashlib.sha256(log_bytes).hexdigest(), "rows": n_rows},
            "candles": {"symbol": sym, "timeframe": "5m", "sha256": G.candles_digest(candles), "bars": len(candles),
                        "first": candles[0]["time"] if candles else None, "last": candles[-1]["time"] if candles else None},
            "sources": {"history": HS.digest(sym, "5m", root=_ec().HIST_ROOT),
                        "forward_store": sha_or_none(os.path.join(FF.STORE_DIR, f"{sym}.5m.json")),
                        "live_bridge": sha_or_none(FF.live_path(sym))},
            "cost_profile": cost_profile([sym])}


def _rel(p):
    """A CLI path as a repository-relative path (what require_committed checks)."""
    return os.path.relpath(os.path.abspath(p), ROOT).replace(os.sep, "/")


def _crypto(a, res):
    amend_path, reads = a.cx_amendment, a.cx_closed or []
    if not amend_path or not reads or not a.spec_dir or not a.commission:
        raise G.Refused("refused: --cx-amendment, --cx-closed, --spec-dir and --commission are required (VC-P1 §5)")
    G.require_committed(ROOT, [_rel(x) for x in [amend_path, a.commission] + list(reads)])
    groups, end, retired = cx_closure(json.load(open(amend_path)), [json.load(open(p)) for p in reads])
    import history_store as HS
    zone = server_zone()
    com = json.load(open(a.commission))
    nxt = end + datetime.timedelta(days=1)
    end_iso = datetime.datetime(nxt.year, nxt.month, nxt.day, tzinfo=zone).astimezone(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")                 # the end of server day `end`
    hist = os.path.join(ROOT, "data", "history", "ftmo")
    rows, counts, specs = [], {}, {}
    for grp, start in (("A", None), ("B", CX_B_FROM)):
        for sym in groups[grp]:
            spec_path = os.path.join(a.spec_dir, f"symbolspec.{sym}.json")
            G.require_committed(ROOT, [_rel(spec_path)])
            spec = json.load(open(spec_path))
            m15, _ = HS.read_doc(sym, "15m", root=hist)
            doc, _ = HS.read_doc(sym, "5m", root=hist)
            if doc is None or m15 is None:
                raise G.Refused(f"refused: no FTMO 5m / 15m history for {sym}")
            cost = PT.SpecCost(spec, PT.price_ref(m15["candles"], spec, zone), com.get(sym), zone)
            kept, counts[sym] = crypto_rows(sym, doc["candles"], zone, end_iso, cost, start_day=start)
            counts[sym]["group"] = grp
            rows += kept
            specs[sym] = G.file_sha256(spec_path)
    syms = groups["A"] + groups["B"]
    res["meta"].update(cx_amendment=amend_path, cx_closed=reads, end=str(end), groups=groups, specs=specs,
                       commission=a.commission, retired_windows_read=retired,
                       dataset=G.dataset_snapshot(hist, [(x, tf) for x in syms for tf in ("5m", "15m")]))
    res["T3_crypto"] = split_test(rows)
    res["counts"] = counts
    res["diagnostics"] = diagnostics(rows)
    res["rows"] = rows


def xau_primary(doc):
    """The xau-holdout read's primary block, for TF: refused unless it was read on this code's decisive window and carries
    the T1 verdict and the recorded hold medians."""
    if (doc.get("meta") or {}).get("holdout") != HOLDOUT:
        raise G.Refused(f"refused: the xau-holdout read's window is {(doc.get('meta') or {}).get('holdout')!r}, "
                        f"not {HOLDOUT!r}")
    p = doc.get("primary") or {}
    if "T1_verdict" not in p or "hold_medians" not in p:
        raise G.Refused("refused: the xau-holdout read has no T1 verdict or hold medians")
    return p


def _forward(a, res):
    if not a.xau:
        raise G.Refused("refused: --xau (the committed xau-holdout read) is required")
    gold = xau_primary(G.require_read_json(ROOT, _rel(a.xau), FAMILY, "xau-holdout", TAG))
    which = {w for w, key in (("a", "T1a_volatility"), ("b", "T1b_hold_length")) if gold["T1_verdict"].get(key)}
    if not which:
        raise G.Refused("refused: no T1 sub-test passed the holdout; the forward read is not scheduled")
    FF = _load("fvg_forward", "scripts/research/fvg_forward.py")
    zone = server_zone()
    seal = G.seal_time(ROOT, PREREG)                   # git: the commit that added the sealed text; never typed
    first = G.first_forward_day(ROOT, PREREG, zone)
    with open(FF.LOG, "rb") as fh:                     # read ONCE: the snapshot hashes exactly the bytes the rows came from
        log_bytes = fh.read()
    log = [json.loads(x) for x in log_bytes.decode("utf-8").splitlines() if x.strip()]
    n_closed = sum(1 for x in log if is_forward_row(x, first, zone))
    if not forward_due(n_closed, first - datetime.timedelta(days=1), datetime.date.today()):
        raise G.Refused(f"refused: forward read not due ({n_closed} closed rows < {FWD_MIN_ROWS}, < {FWD_MAX_DAYS} days)")
    candles = FF.merged_candles("XAUUSD")
    res["meta"]["dataset"] = forward_snapshot(FF.LOG, log_bytes, candles)
    s = _ec().Series("XAUUSD", candles, zone, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    rows, missing = forward_rows(log, s, first, zone, _ec().Costs("XAUUSD"))
    diffs = [abs(r["R_net"] - r["R_net_log"]) for r in rows if r.get("R_net_log") is not None]
    res.update(TF_forward=forward_tests(rows, which, gold["hold_medians"]), without_vr=missing,
               rows_without_candle=n_closed - len(rows) - missing,
               seal_commit=seal.isoformat(), first_forward_day=str(first), gold=_rel(a.xau),
               hold_medians_used=gold["hold_medians"],
               r_net_repriced_vs_log={"rows": len(diffs), "differ": sum(1 for x in diffs if x > 1e-9),
                                      "max_abs_diff": max(diffs) if diffs else None},
               rows=rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print the code-sha256 lines the sealed text must carry")
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=("xau-holdout", "crypto", "forward"))
    r.add_argument("--out", required=True)
    r.add_argument("--cx-amendment")
    r.add_argument("--cx-closed", nargs="+")
    r.add_argument("--spec-dir")
    r.add_argument("--commission", help='{"BTCUSD": c_sym, ...}: commission per side, fraction of notional ([CX-P1] §2)')
    r.add_argument("--xau", help="forward: the committed xau-holdout read JSON (its T1 verdict and hold medians); the "
                                  "forward window starts after the seal commit (git), no date is typed")
    v = sub.add_parser("verdict", help="Holm over T2 / T3 from the committed read JSONs (no data read)")
    v.add_argument("--xau", required=True)
    v.add_argument("--crypto")
    a = ap.parse_args()
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE)))
        return
    if a.cmd == "verdict":
        g = G.require_read_json(ROOT, _rel(a.xau), FAMILY, "xau-holdout", TAG)["primary"]["T2_silver"]
        c = G.require_read_json(ROOT, _rel(a.crypto), FAMILY, "crypto", TAG)["T3_crypto"] if a.crypto else None
        print(json.dumps(secondary_verdict(g.get("p_one_sided"), c.get("p_one_sided") if c else None), indent=1))
        return
    if a.cmd == "dry-run":
        G.refuse_overwrite(a.out)
        meta = dict(_meta("dry-run"), code_sha256={p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE})
        _dump({"meta": meta, "counts": dry_counts()}, a.out)
        return
    G.refuse_overwrite(a.out)
    G.require_read_once(ROOT, _rel(a.out), FAMILY, a.read)
    text = G.require_sealed(ROOT, PREREG, TAG)
    G.require_committed(ROOT, CODE)
    man = G.require_fingerprint(ROOT, text, CODE)
    G.trace_start(ROOT)
    res = {"meta": _meta(a.read)}
    if a.read == "xau-holdout":
        hist = os.path.join(ROOT, "data", "history", "ftmo")
        res["meta"]["dataset"] = G.dataset_snapshot(hist, [("XAUUSD", "5m"), ("XAGUSD", "5m")])
        res["meta"]["cost_profile"] = cost_profile(["XAUUSD", "XAGUSD"])
        res["primary"] = xau_read(K, keep_rows=True)
        res["report_k2"] = xau_read(K_REPORT, medians=res["primary"]["hold_medians"])
    elif a.read == "crypto":
        _crypto(a, res)
    else:
        _forward(a, res)
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, a.out)


if __name__ == "__main__":
    main()
