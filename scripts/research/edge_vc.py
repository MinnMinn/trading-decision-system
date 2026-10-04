#!/usr/bin/env python3
"""Family VC: does the gold intraday-trend edge (H7, G9) concentrate on high-volatility days, or on early entries?
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md [VC-P1].

    python3 scripts/research/edge_vc.py manifest                                  # the code-sha256 lines for the seal
    python3 scripts/research/edge_vc.py dry-run --out <json>                      # outcome-blind: event COUNTS per half
    python3 scripts/research/edge_vc.py run --read gold-holdout --out docs/audits/<date>-edge-vc-gold-holdout.json
    python3 scripts/research/edge_vc.py run --read crypto --cx-amendment <json> --cx-closed <json> [...] \
        --spec-dir <dir> --commission <json> --out ...
    python3 scripts/research/edge_vc.py run --read forward --seal-date YYYY-MM-DD --gold <gold-holdout json> --out ...

Each read runs ONCE, from committed code whose sha256 the SEALED pre-registration lists (scripts/research/prereg_guard.py).

(a) HIGH volatility day (F3 H5's own regime rule, scripts/research/edge_f3.py:30, :99-116): sigma_5m above the median sigma_5m
of the previous REGIME_DAYS (250) days that have one, given >= 125 of them; no VR when the history is shorter (counted,
excluded). VR = sigma / that median.
(b) LONG HOLD (early entry): the trade's entry server-clock slot is earlier than the median entry slot of the same component's
gold-holdout trades. The stop is k x sigma x sqrt(bars to the end of the day) (scripts/research/book_sim.py:59), so the
post-hoc "wide stop" mixes volatility with ENTRY TIME. The medians are computed once, on the holdout (entry timing:
outcome-blind), recorded in its JSON and reused as constants by the forward read and by any filter.

Outcome per trade: the book's mechanics at the stop of fvg-book v4 (k = 1.4, docs/architecture/trading-systems.json v4):
R_gross = side x (exit - entry) / stop distance, R_net = R_gross - cost / stop distance (scripts/research/book_sim.py:38-82).

Test statistic (every test): the SIDE-BALANCED difference 1/2 [(mean R_gross True - False | long) + (same | short)].
Balancing by side removes an unconditional drift: under a constant drift mu, R carries side x mu x sqrt(bars) / (k sigma),
so early entries of the majority side would "win" T1b without any conditional effect (scripts/tests/test_edge_vc.py
`test_constant_drift_does_not_pass_t1b`). Variance: CR1 cluster-robust by server day for the contrast as a whole (each day's
summed influence), exact when the two halves share days (pooled crypto symbols; H7 and G9 on one gold day in T1b).
Student-t with min(days per side x half cell) - 1 df, one-sided (True > False). The unbalanced pooled difference is
report-only.

Reads:
* gold-holdout: H7 + G9 XAUUSD pooled -- T1a (volatility) and T1b (hold), Holm m = 2 -- and G9 XAGUSD (T2), trades whose ENTRY
  server day is before HOLDOUT_END (the owner picks the window, VC-P1 §3: "A" = before 2018-01-01, "B" = before 2008-12-10).
  The post-hoc quartile table says "since 2018" and has no committed code (docs/audits/2026-10-04-personal-account.md:47-55),
  so the holdout ends at 2018-01-01, not 2018-02-26. 2008-12-10 onwards was replayed by the personal-account skip / floor
  (/ cap) cells, an absolute stop-width cut: window A is PARTLY EXPOSED; window B is not. Under A, B's sub-window is
  report-only. The trades themselves are EXPOSED (F3 / F4 selected them, A1 replayed them).
* crypto (T3): the FTMO crypto CFDs with the [CX-P1] point-in-time rules and the CX cost model (pit_trend.SpecCost), group A
  over its whole history and group B from 2024-03-01 only ([CX-P1] §3), to the CX amendment's end date. Runs only after
  every scheduled CX read is done (checked from the committed CX read JSONs, `cx_closure`).
* forward (TF): the paper log's H7 / G9 XAUUSD rows entering on or after the seal date at stop_k 1.4, read once at >= 150
  closed rows or 365 days after the seal; it tests only the T1 sub-test(s) that passed the holdout (Holm at 0.10)."""
import argparse
import collections
import datetime
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
#: The holdout window (VC-P1 §3; owner decision before sealing). Both end strictly before the date.
HOLDOUT_WINDOWS = {"A": datetime.date(2018, 1, 1), "B": datetime.date(2008, 12, 10)}
HOLDOUT = "A"
HOLDOUT_END = HOLDOUT_WINDOWS[HOLDOUT]
#: First day of the personal-account replays' common span (docs/audits/2026-10-04-personal-account.json meta.common_span):
#: their skip / floor (/ cap) cells cut trades by an absolute stop width from here on.
PA_SPAN_START = datetime.date(2008, 12, 10)
K = 1.4                                # fvg-book v4
K_REPORT = 2.0                         # v3, report-only
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
    `medians` None they are computed from `rows` (the gold-holdout read only); every later use passes the recorded ones."""
    if medians is None:
        by_c = collections.defaultdict(list)
        for r in rows:
            by_c[r["component"]].append(r["entry_slot"])
        medians = {c: statistics.median(v) for c, v in by_c.items()}
    for r in rows:
        r["long_hold"] = r["entry_slot"] < medians[r["component"]]
    return medians


# ------------------------------------------------------------------------------------------------ statistics
def _ec():
    global _EC
    if _EC is None:
        _EC = _load("edge_census", "scripts/research/edge_census.py")
    return _EC


_EC = None


def _contrast(rows, value, cell_of, weights, day_key="day"):
    """sum_c w_c x mean(value | cell c) with a CR1 cluster-robust SE by day over the whole contrast: each day's summed
    influence u_g = sum_i w_c(i) (y_i - mean_c(i)) / n_c(i); var = G / (G - 1) x sum_g u_g^2. Exact when cells share days.
    None when a weighted cell is empty."""
    cells = collections.defaultdict(list)
    for r in rows:
        c = cell_of(r)
        if c in weights:
            cells[c].append(r)
    if any(not cells[c] for c in weights):
        return None
    means = {c: sum(r[value] for r in cells[c]) / len(cells[c]) for c in weights}
    u = collections.defaultdict(float)
    for c in weights:
        n, m, w = len(cells[c]), means[c], weights[c]
        for r in cells[c]:
            u[str(r[day_key])] += w * (r[value] - m) / n
    g = len(u)
    se = math.sqrt(g / (g - 1) * sum(x * x for x in u.values())) if g >= 2 else None
    return {"est": sum(weights[c] * means[c] for c in weights), "se": se, "means": means,
            "n": {c: len(cells[c]) for c in weights}, "days": {c: len({str(r[day_key]) for r in cells[c]}) for c in weights}}


def split_test(rows, key="high", value="R_gross", net="R_net", day_key="day"):
    """True half minus False half of `key`, SIDE-BALANCED (module docstring), CR1 by day over the whole contrast; one-sided p
    for True > False. Report-only: the unbalanced pooled difference, per-cell means, days shared by the two halves."""
    hi = [r for r in rows if r[key]]
    lo = [r for r in rows if not r[key]]
    days_hi = {str(r[day_key]) for r in hi}
    days_lo = {str(r[day_key]) for r in lo}
    out = {"n_high": len(hi), "n_low": len(lo), "days_high": len(days_hi), "days_low": len(days_lo),
           "shared_days": len(days_hi & days_lo),
           "mean_high": (sum(r[value] for r in hi) / len(hi)) if hi else None,
           "mean_low": (sum(r[value] for r in lo) / len(lo)) if lo else None,
           "net_mean_high": (sum(r[net] for r in hi) / len(hi)) if hi and net else None,
           "net_mean_low": (sum(r[net] for r in lo) / len(lo)) if lo and net else None,
           "diff": None, "se": None, "df": None, "t": None, "p_one_sided": 1.0, "cells": None, "pooled_report_only": None}
    pooled = _contrast(rows, value, lambda r: bool(r[key]), {True: 1.0, False: -1.0}, day_key)
    if pooled:
        out["pooled_report_only"] = {"diff": pooled["est"], "se": pooled["se"]}
    weights = {(s, h): (0.5 if h else -0.5) for s in SIDES for h in (True, False)}
    bal = _contrast(rows, value, lambda r: (r["side"], bool(r[key])), weights, day_key)
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
    hold, long / short, per year. Means of R_gross and R_net."""
    def stats(rs):
        if not rs:
            return {"n": 0}
        return {"n": len(rs), "R_gross": sum(r["R_gross"] for r in rs) / len(rs),
                "R_net": sum(r["R_net"] for r in rs) / len(rs)}

    out = {}
    if not rows:
        return out
    sb = sorted(r["stop_bp"] for r in rows)
    cuts = [sb[int(len(sb) * q)] for q in (0.25, 0.5, 0.75)]
    out["stop_bp_cuts"] = cuts
    out["stop_quartiles"] = [stats([r for r in rows if (r["stop_bp"] >= (cuts[q - 1] if q else -1)) and
                                    (q == 3 or r["stop_bp"] < cuts[q])]) for q in range(4)]
    if all("long_hold" in r for r in rows):
        out["vr_x_hold"] = {f"{'high' if h else 'low'}|{'long' if lg else 'short'}":
                            stats([r for r in rows if r["high"] == h and r["long_hold"] == lg])
                            for h in (True, False) for lg in (True, False)}
    out["side"] = {str(s): {"high": stats([r for r in rows if r["side"] == s and r["high"]]),
                            "low": stats([r for r in rows if r["side"] == s and not r["high"]])} for s in SIDES}
    years = sorted({str(r["day"])[:4] for r in rows})
    out["by_year"] = {y: {"high": stats([r for r in rows if str(r["day"])[:4] == y and r["high"]]),
                          "low": stats([r for r in rows if str(r["day"])[:4] == y and not r["high"]])} for y in years}
    return out


# ------------------------------------------------------------------------------------------------ gold / silver holdout
_SERIES = {}


def _gold_series(sym):
    """edge_census research-mode Series over all history (cached: book_sim.trades loads its own copy)."""
    if sym not in _SERIES:
        _SERIES[sym] = _ec().load(sym, end="9999-12-31T00:00:00Z")
    return _SERIES[sym]


def research_sig_by_day(s):
    """The F3 H5 sigma history: {dense day: sigma_5m} (research mode, scripts/research/edge_f3.py:100-104)."""
    return {d: s._vol[d] for d in s.dense_days if s._vol.get(d)}


def book_rows(trades, s, zone):
    """book_sim.trades rows -> VC rows keyed by the ENTRY server day, with the entry's server-clock slot and the bars from
    the entry to the day's last bar (book_sim's nb, report-only)."""
    idx = {t: i for i, t in enumerate(s.T)}
    out = []
    for t in trades:
        i = idx.get(t["entry_time"])
        if i is None:
            continue
        d = s.sday[i]
        out.append({"symbol": t["symbol"], "day": d, "side": t["side"], "R_net": t["R"],
                    "R_gross": t["R"] + t["cost_R"], "cost_R": t["cost_R"], "stop_bp": t["stop_bp"],
                    "entry_slot": slot_of(s.dt[i], zone), "nb_planned": s.day_rows[d][-1] - i + 1, "exit": t["exit"],
                    "entry_time": t["entry_time"]})
    return out


def holdout_rows(component, k, end_day=None, trades_fn=None, series_fn=None, zone=None):
    """(rows labelled HIGH / LOW with entry day < end_day, counts) for one book component."""
    end_day = end_day or HOLDOUT_END
    BS = _load("book_sim", "scripts/research/book_sim.py")
    sym, det, hold = BS.COMPONENTS[component]
    trades = (trades_fn or BS.trades)(sym, det, hold, stop_k=k)
    s = (series_fn or _gold_series)(sym)
    vr = vr_by_day(research_sig_by_day(s))
    rows = [r for r in book_rows(trades, s, zone or server_zone()) if r["day"] < end_day]
    for r in rows:
        r["component"] = component
    kept, missing = label(rows, vr)
    return kept, {"trades_before_end": len(rows), "without_vr": missing}


def t1_verdict(t1a, t1b, per_a, per_b):
    """T1 = {T1a volatility, T1b hold length} on pooled gold, Holm m = 2 at ALPHA_T1; a rejected sub-test passes only if
    its True half's mean NET R > 0 and both gold components' differences are > 0."""
    rej = holm([t1a["p_one_sided"], t1b["p_one_sided"]], ALPHA_T1)
    ok = []
    for r, t, per in zip(rej, (t1a, t1b), (per_a, per_b)):
        ok.append(bool(r and (t["net_mean_high"] or 0) > 0 and all((per[c]["diff"] or 0) > 0 for c in GOLD)))
    return {"T1a_volatility": ok[0], "T1b_hold_length": ok[1], "holm_rejected": rej}


def _tests_on(rows_by_c):
    gold = [r for c in GOLD for r in rows_by_c.get(c, [])]
    return {"T1a_gold_volatility": split_test(gold), "T1b_gold_hold_length": split_test(gold, key="long_hold"),
            "per_component_volatility": {c: split_test(v) for c, v in rows_by_c.items()},
            "per_component_hold_length": {c: split_test(v, key="long_hold") for c, v in rows_by_c.items()}}


def gold_read(k=K, trades_fn=None, series_fn=None, zone=None, keep_rows=False, medians=None):
    rows, counts = {}, {}
    for c in GOLD + SILVER:
        rows[c], counts[c] = holdout_rows(c, k, trades_fn=trades_fn, series_fn=series_fn, zone=zone)
    hold_medians = mark_hold([r for c in GOLD + SILVER for r in rows[c]], medians)
    t = _tests_on(rows)
    out = {"T1a_gold_volatility": t["T1a_gold_volatility"], "T1b_gold_hold_length": t["T1b_gold_hold_length"],
           "T1_verdict": t1_verdict(t["T1a_gold_volatility"], t["T1b_gold_hold_length"], t["per_component_volatility"],
                                    t["per_component_hold_length"]),
           "T2_silver": t["per_component_volatility"][SILVER[0]],
           "per_component_volatility": t["per_component_volatility"],
           "per_component_hold_length": t["per_component_hold_length"],
           "hold_medians": hold_medians, "holdout": HOLDOUT, "holdout_end": str(HOLDOUT_END), "counts": counts,
           "diagnostics": {"gold": diagnostics([r for c in GOLD for r in rows[c]]), "silver": diagnostics(rows[SILVER[0]])}}
    if HOLDOUT == "A":                                  # report-only: the sub-window no personal-account replay touched
        sub = {c: [r for r in v if r["day"] < PA_SPAN_START] for c, v in rows.items()}
        out["report_only_before_pa_span"] = dict(_tests_on(sub), before=str(PA_SPAN_START),
                                                 n={c: len(v) for c, v in sub.items()})
    if keep_rows:
        out["rows"] = rows
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
def forward_rows(log_rows, series, seal_date, zone, k=K):
    """Closed paper rows of H7 / G9 XAUUSD at stop k entering on or after the seal date, with R_gross from the logged
    entry / exit / stop distance, VR from the series' dense-day sigma history (the H5 construction) and the entry slot."""
    idx = {t: i for i, t in enumerate(series.T)}
    vr = vr_by_day(research_sig_by_day(series))
    out = []
    for r in log_rows:
        if r.get("component") not in GOLD or r.get("status") != "closed" or r.get("stop_k") != k:
            continue
        i = idx.get(r["entry_time"])
        if i is None or series.sday[i] < seal_date:
            continue
        gross = r["side"] * (r["exit"] - r["entry"]) / r["stop_distance"]
        out.append({"component": r["component"], "day": series.sday[i], "side": r["side"], "R_gross": gross,
                    "R_net": r["R"], "entry_time": r["entry_time"], "entry_slot": slot_of(series.dt[i], zone)})
    return label(out, vr)


def forward_tests(rows, which, medians):
    """TF: the T1 sub-tests that PASSED the holdout (`which` subset of {"a", "b"}), Holm at ALPHA_FORWARD; (b) uses the
    holdout's recorded per-component median entry slots (`medians`), never the forward rows' own."""
    keys = {"a": "high", "b": "long_hold"}
    if "b" in which:
        mark_hold(rows, medians)
    tests = {w: split_test(rows, key=keys[w]) for w in sorted(which)}
    rej = holm([t["p_one_sided"] for t in tests.values()], ALPHA_FORWARD) if tests else []
    for (w, t), r in zip(sorted(tests.items()), rej):
        t["passed"] = bool(r and (t["net_mean_high"] or 0) > 0)
    return tests


def forward_due(n_closed, seal_date, today):
    return n_closed >= FWD_MIN_ROWS or (today - seal_date).days >= FWD_MAX_DAYS


# ------------------------------------------------------------------------------------------------ dry run (counts only)
def dry_counts(series_fn=None, zone=None):
    """Outcome-blind, per component: holdout events (book_sim's sample: an entry bar exists and the signal day has a sigma)
    by VR half, the median ENTRY slot (the (b) cut a read will record) and the hold halves, and the events before the
    personal-account span. No trade is simulated, no price after the signal is read."""
    BS = _load("book_sim", "scripts/research/book_sim.py")
    zone = zone or server_zone()
    out = {}
    for c in GOLD + SILVER:
        sym, det, _hold = BS.COMPONENTS[c]
        s = (series_fn or _gold_series)(sym)
        vr = vr_by_day(research_sig_by_day(s))
        n = collections.Counter()
        slots = []
        for ev in det(s):
            e = ev["entry_i"]
            if e >= len(s.C) or not s.sigma(ev["i"]):
                continue
            d = s.sday[e]
            if d >= HOLDOUT_END:
                continue
            v = vr.get(d)
            n["no_vr" if v is None else ("high" if v > 1 else "low")] += 1
            if v is not None:
                slots.append(slot_of(s.dt[e], zone))
                n["before_pa_span"] += d < PA_SPAN_START
        med = statistics.median(slots) if slots else None
        if med is not None:
            n["long_hold"] = sum(1 for x in slots if x < med)
            n["short_hold"] = len(slots) - n["long_hold"]
        out[c] = dict(n, median_entry_slot=med)
    return out


# ------------------------------------------------------------------------------------------------ CLI
def _dump(res, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {path}")


def _meta(read):
    return {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "read": read, "git_head": G.git_head(ROOT),
            "k": K, "k_report": K_REPORT, "regime_days": REGIME_DAYS, "min_hist": MIN_HIST, "holdout": HOLDOUT,
            "holdout_end": str(HOLDOUT_END), "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}


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


def _forward(a, res):
    if not a.seal_date or not a.gold:
        raise G.Refused("refused: --seal-date and --gold are required")
    G.require_committed(ROOT, [_rel(a.gold)])
    FF = _load("fvg_forward", "scripts/research/fvg_forward.py")
    seal = datetime.date.fromisoformat(a.seal_date)
    log = [json.loads(x) for x in open(FF.LOG) if x.strip()]
    n_closed = sum(1 for x in log if x.get("component") in GOLD and x.get("status") == "closed"
                   and x.get("stop_k") == K and x.get("entry_time", "") >= a.seal_date)
    if not forward_due(n_closed, seal, datetime.date.today()):
        raise G.Refused(f"refused: forward read not due ({n_closed} closed rows < {FWD_MIN_ROWS}, < {FWD_MAX_DAYS} days)")
    gold = json.load(open(a.gold))["primary"]
    which = {w for w, key in (("a", "T1a_volatility"), ("b", "T1b_hold_length")) if gold["T1_verdict"].get(key)}
    if not which:
        raise G.Refused("refused: no T1 sub-test passed the holdout; the forward read is not scheduled")
    zone = server_zone()
    s = _ec().Series("XAUUSD", FF.merged_candles("XAUUSD"), zone, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    rows, missing = forward_rows(log, s, seal, zone)
    res.update(TF_forward=forward_tests(rows, which, gold["hold_medians"]), without_vr=missing, seal_date=a.seal_date,
               gold=a.gold, hold_medians_used=gold["hold_medians"])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print the code-sha256 lines the sealed text must carry")
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=("gold-holdout", "crypto", "forward"))
    r.add_argument("--out", required=True)
    r.add_argument("--cx-amendment")
    r.add_argument("--cx-closed", nargs="+")
    r.add_argument("--spec-dir")
    r.add_argument("--commission", help='{"BTCUSD": c_sym, ...}: commission per side, fraction of notional ([CX-P1] §2)')
    r.add_argument("--seal-date")
    r.add_argument("--gold", help="forward: the gold-holdout read JSON (its T1 verdict and hold medians)")
    v = sub.add_parser("verdict", help="Holm over T2 / T3 from the read JSONs (no data read)")
    v.add_argument("--gold", required=True)
    v.add_argument("--crypto")
    a = ap.parse_args()
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE)))
        return
    if a.cmd == "verdict":
        g = json.load(open(a.gold))["primary"]["T2_silver"]
        c = json.load(open(a.crypto))["T3_crypto"] if a.crypto else None
        print(json.dumps(secondary_verdict(g.get("p_one_sided"), c.get("p_one_sided") if c else None), indent=1))
        return
    if a.cmd == "dry-run":
        G.refuse_overwrite(a.out)
        meta = dict(_meta("dry-run"), code_sha256={p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE})
        _dump({"meta": meta, "counts": dry_counts()}, a.out)
        return
    G.refuse_overwrite(a.out)
    text = G.require_sealed(ROOT, PREREG, TAG)
    G.require_committed(ROOT, CODE)
    man = G.require_fingerprint(ROOT, text, CODE)
    G.trace_start(ROOT)
    res = {"meta": _meta(a.read)}
    if a.read == "gold-holdout":
        hist = os.path.join(ROOT, "data", "history", "ftmo")
        res["meta"]["dataset"] = G.dataset_snapshot(hist, [("XAUUSD", "5m"), ("XAGUSD", "5m")])
        res["primary"] = gold_read(K, keep_rows=True)
        res["report_k2"] = gold_read(K_REPORT, medians=res["primary"]["hold_medians"])
    elif a.read == "crypto":
        _crypto(a, res)
    else:
        _forward(a, res)
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, a.out)


if __name__ == "__main__":
    main()
