#!/usr/bin/env python3
"""Family VC: does the gold intraday-trend edge (H7, G9) concentrate on high-volatility days, or on early entries?
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md [VC-P1].

    python3 scripts/research/edge_vc.py manifest                                  # the code-sha256 lines for the seal
    python3 scripts/research/edge_vc.py dry-run --out <json>                      # outcome-blind: event COUNTS per half
    python3 scripts/research/edge_vc.py run --read xau-holdout --out docs/audits/<date>-edge-vc-xau-holdout.json
    python3 scripts/research/edge_vc.py run --read crypto --cx-amendment <json> --cx-closed <json> [...] \
        --spec-dir <dir> --commission <json> --out ...
    python3 scripts/research/edge_vc.py run --read forward --xau docs/audits/<date>-edge-vc-xau-holdout.json --out ...
    python3 scripts/research/edge_vc.py verdict --xau docs/audits/<date>-edge-vc-xau-holdout.json [--crypto <json>]

Each read runs ONCE, from committed code whose sha256 the SEALED pre-registration lists (scripts/research/prereg_guard.py),
to the one output name `docs/audits/<YYYY-MM-DD>-edge-vc-<read>.json`; a second run of a read is refused even to another path
(`prereg_guard.require_read_once`). A read also refuses until the committed research ledger registers the study
(`require_ledger`: VC-P1 §5.4, the seal commit), and when sys.pycache_prefix is set (bytecode outside the repository would
hide executed code from the guard). The xau-holdout read refuses unless the stored 5m XAUUSD / XAGUSD history is
byte-identical to the sealed text's `dataset-sha256` lines and the ledger entry's `dataset` (`require_dataset`): the dense
threshold is 0.8 x the median bars per day of the WHOLE loaded history (scripts/research/edge_census.py:104-107), so a
re-import, even of later years, can change the decisive window's events.

POINT IN TIME (lead decision 2026-10-04, VC-P1 §1-§2). The decisive rows are built as the live executor knows them, except
for one dataset-level choice (below):
* events: the H7 / G9 detectors on an edge_census.Series in point-in-time mode (`sigma_every_day=True`, as the paper log and
  the demo executor build it, scripts/research/fvg_forward.py `_series`). Every day has the sigma of the previous dense days,
  so no event is dropped because its day later proves sparse. A signal on a server day's last bar has no same-day trade and
  is dropped, as the paper log drops it (`pit_events`);
* (a) VR: the day's sigma over the median sigma of the previous REGIME_DAYS dense days, given >= MIN_HIST (`pit_vr_by_day`:
  F3 H5's rule, scripts/research/edge_f3.py:99-116, as known at the day's start);
* the stop: k x sigma x sqrt(nb) x price, nb = the 5m bars to the server rollover ON THE CLOCK (`bars_to_day_end`, the paper
  log's count, known at entry), walked to the day's last stored bar by scripts/research/fvg_forward.py `resolve_row`
  (book_sim's exit walk, with this stop; `pit_trade`). nb is also R_bar's horizon, T1a's and T1b's weight and the gap
  rule's bar count.
NOT point in time (disclosed, VC-P1 §1): whether a day is DENSE uses the median bars per day of the whole stored history
(edge_census.py:104-107; pinned by `require_dataset`), and the paper log's data-quality refusals (a data hole, stale
volatility history; `paper_log_refusals`) are not applied. Pre-registered REPORT-ONLY blocks of the same read, none of which
changes a pass / fail (VC-P1 §4, §6): the inherited research-mode rows (`research_mode_report_only`: book_sim.trades, a sigma
only on days that turn out dense, nb from the STORED bars); the causal-density rows (`causal_density_report_only`: the dense
rule uses the median of the days BEFORE each day, `causal_density`); every test without the trades the paper log would have
refused (`excluding_paper_log_refusals_report_only`). If a sensitivity's T1 verdict differs, the reading adds DATA-SENSITIVE:
not decisive (`with_sensitivities`).

(b) LONG HOLD (early entry): the trade's entry server-clock slot is earlier than the median entry slot of the same component's
decisive-window trades. The stop is k x sigma x sqrt(bars to the end of the day) (scripts/research/book_sim.py:59), so the
post-hoc "wide stop" mixes volatility with ENTRY TIME. The medians are computed once, on the decisive window (entry timing:
outcome-blind), recorded in its JSON and reused as constants by the report-only window, the forward read and any filter.

Outcome per trade at the stop of fvg-book v4 (k = 1.4, docs/architecture/trading-systems.json v4): R_gross = side x (exit -
entry) / stop distance, R_net = R_gross - cost / stop distance (edge_census.Costs at the read's cost profile).

Test statistic (every test): the SIDE-BALANCED difference 1/2 [(mean y True - False | long) + (same | short)].
* T2, T3: y = R_gross. Balancing by side removes an unconditional MARKET drift (side x mu x sqrt(bars) / (k sigma) is
  of opposite sign for longs and shorts; scripts/tests/test_edge_vc.py `test_constant_drift_does_not_pass_t1b`).
* T1a: y = T1b's statistic below (`T1A_VALUE`, `T1A_WEIGHT`). VC-P1 §4 fixed, before any count was seen, that T1a moves
  from R_gross to the nb-weighted R_bar when the decisive window's pooled HIGH and LOW halves differ in mean planned bars
  by more than `T1A_GAP_RULE` of the smaller; the sealing dry run measured it above the rule (VC-P1 §7). The R_gross T1a
  is report-only (`T1a_raw_R_report_only`).
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
The unbalanced pooled difference is report-only. T1a's HIGH / LOW halves are runs of consecutive days (the VR is a 20-day
sigma over a 250-day median: window B has 8 runs), so a by-day SE can understate T1a's error when R varies by regime
(VC-P1 §4, §7). Lead decision 2026-10-05 (option C): T1a passes only if the by-day test passes AND the same contrast with
the VR runs as clusters (`T1a_run_clustered`) has one-sided p <= ALPHA_T1 (`t1_verdict`).

Reads:
* xau-holdout: H7 + G9 XAUUSD pooled -- T1a (volatility) and T1b (hold), Holm m = 2 -- and G9 XAGUSD (T2), trades whose ENTRY
  server day is before HOLDOUT_END. Lead decision 2026-10-04 (VC-P1 §3): window B (before 2008-12-10; no personal-account
  replay touched it) is DECISIVE; window A (before 2018-01-01; from 2008-12-10 all personal-account replays drop or size
  trades by stop width: PARTLY EXPOSED) is report-only, with the decisive window's hold medians. Window B is UNREAD-FOR-H,
  so a pass there is DISCOVERY-GRADE for the condition; TF is its confirmation. A T1 fail reads "NOT SHOWN" (inconclusive
  for a G9-concentrated effect: VC-P1 §7's full-rule power). Silver has no trade with a VR before 2008-12-10, so T2 is
  "not run (window)" and enters its Holm family with p = 1. The post-hoc quartile table says "since 2018" and has no
  committed code (docs/audits/2026-10-04-personal-account.md:47-55): 2018 onwards is never a test. The trades themselves
  are EXPOSED (F3 / F4 selected them, A1 replayed them).
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
import bisect
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import types

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
LEDGER = "docs/architecture/research-ledger.json"
LEDGER_KEY = "vc_volatility_condition"  # the study entry the seal commit adds (VC-P1 §5.4); every read refuses without it
FAMILY = "vc"                          # read outputs: docs/audits/<YYYY-MM-DD>-edge-vc-<read>.json
READS = ("xau-holdout", "crypto", "forward")
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
#: The stored history the xau-holdout read loads (data/history/ftmo). Its digests are pinned at the seal: the dry run
#: records them, VC-P1 §7 carries them as `dataset-sha256` lines and the ledger entry as `dataset` (`require_dataset`).
DATASET_PAIRS = (("XAUUSD", "5m"), ("XAGUSD", "5m"))
DATASET_LINE = re.compile(r"(?m)^dataset-sha256 ([0-9a-f]{64}) (\S+)[ \t]*$")
HIST_END = "9999-12-31T00:00:00Z"      # every stored bar (the windows are cut by entry day)
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
#: The full T1 rule's power (VC-P1 §7, lead decision 2026-10-04): per-trade sd of R at k = 1.4
#: (docs/audits/2026-10-03-vol-schedule.md:29) and the effect shapes, as the half-split difference of each gold component
#: in R at an NB_REF-bar hold. "2018+ shape": the post-hoc quartile table's half split (G9 ~0.21, H7 ~0.04).
SD_R = 0.75
POWER_SHAPES = {"equal_0.20": {"H7_XAUUSD_eod": 0.20, "G9_XAUUSD_eod": 0.20},
                "equal_0.10": {"H7_XAUUSD_eod": 0.10, "G9_XAUUSD_eod": 0.10},
                "shape_2018_G9_0.21_H7_0.04": {"H7_XAUUSD_eod": 0.04, "G9_XAUUSD_eod": 0.21},
                "G9_only_0.21": {"H7_XAUUSD_eod": 0.0, "G9_XAUUSD_eod": 0.21}}
POWER_REPS = 20000
POWER_SEED = 7
#: Causal dense-day rule (VC-P1 §1, the "causal density" sensitivity): edge_census.Series (:104-107) calls a day dense when it
#: has >= DENSE_SHARE x the median bar count of the WHOLE loaded history (days with >= 50 bars), so a 2005 day's status depends on
#: the 2010s. `causal_density` uses the median of the days BEFORE the day instead, given CAUSAL_MIN_DAYS of them.
CAUSAL_FULL_MIN = 50
CAUSAL_MIN_DAYS = 20


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


#: T1a's statistic (VC-P1 §4). Fixed before any count was seen: T1a keeps R_gross unless the decisive window's pooled HIGH and
#: LOW halves differ in mean planned bars by more than T1A_GAP_RULE of the smaller (`power_inputs` `vr_halves_bars_gap`); then
#: it uses T1b's nb-weighted R_bar, so a per-bar edge that is the same on both halves cannot pass T1a through a timing gap.
#: The sealing dry run measured the gap above the rule (VC-P1 §7): the switch applies. Every T1a use reads these.
T1A_GAP_RULE = 0.10
T1A_VALUE, T1A_WEIGHT = "R_bar", nb_weight


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


def pit_vr_by_day(s, regime_days=REGIME_DAYS, min_hist=MIN_HIST):
    """VR of EVERY server day of `s` that has a sigma, as known at the day's start (VC-P1 §1): the day's sigma over the
    median sigma of the previous <= regime_days DENSE days that have one, given >= min_hist of them. On a dense day it equals
    `vr_by_day(research_sig_by_day(s))` (a dense day's research sigma is its point-in-time sigma,
    scripts/research/edge_census.py:131-146); a day that later proves sparse keeps its VR (no same-day completeness
    selection). On a research-mode series (sigma on dense days only) the two are identical."""
    hist_days = [d for d in s.dense_days if s._vol.get(d)]
    out = {}
    for d in s.day_rows:
        v = s._vol.get(d)
        if not v:
            continue
        k = bisect.bisect_left(hist_days, d)
        hist = [s._vol[x] for x in hist_days[max(0, k - regime_days):k]]
        if len(hist) >= min_hist:
            med = statistics.median(hist)
            if med > 0:
                out[d] = v / med
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
_FF = None


def _ff():
    """scripts/research/fvg_forward.py, loaded once: its `resolve_row` is the decisive rows' exit walk (`pit_trade`)."""
    global _FF
    if _FF is None:
        _FF = _load("fvg_forward", "scripts/research/fvg_forward.py")
    return _FF


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
_PIT = {}


def _xau_series(sym):
    """edge_census research-mode Series over all history (cached: book_sim.trades loads its own copy)."""
    if sym not in _SERIES:
        _SERIES[sym] = _ec().load(sym, end=HIST_END)
    return _SERIES[sym]


def causal_density(s):
    """Re-derive `s`'s dense-day sets with a CAUSAL threshold and rebuild its sigma history (the "causal density" sensitivity,
    VC-P1 §1): day d is dense iff it has >= DENSE_SHARE x the median bar count of the days BEFORE d that have
    >= CAUSAL_FULL_MIN bars, given >= CAUSAL_MIN_DAYS of them (no earlier history: not dense). edge_census.Series takes the
    median over the whole loaded history (scripts/research/edge_census.py:104-107). Sets dense_days, dense, prev_dense and
    split_day as Series.__init__ does (:107-116) and rebuilds `_vol` with Series._vol_by_day; no frozen file changes. The
    detectors then read the new sets. Returns `s`."""
    EC = _ec()
    seen, flags = [], {}
    for d, rows in s.day_rows.items():
        v, n = len(rows), len(seen)
        if n >= CAUSAL_MIN_DAYS:
            med = seen[n // 2] if n % 2 else (seen[n // 2 - 1] + seen[n // 2]) / 2
            flags[d] = v >= EC.DENSE_SHARE * med
        else:
            flags[d] = False
        if v >= CAUSAL_FULL_MIN:
            bisect.insort(seen, v)
    s.dense_days = sorted(d for d, f in flags.items() if f)
    dset = set(s.dense_days)
    s.dense = [d in dset for d in s.sday]
    days = list(s.day_rows)
    prev = {d: (days[k - 1] in dset) for k, d in enumerate(days) if k > 0}
    s.prev_dense = [prev.get(d, False) for d in s.sday]
    k = int(len(s.dense_days) * EC.DISCOVERY_SHARE)
    s.split_day = s.dense_days[k] if s.dense_days else datetime.date.max
    s._vol = s._vol_by_day()
    return s


def _pit_series(sym, causal=False):
    """edge_census.Series in POINT-IN-TIME mode (`sigma_every_day=True`, as scripts/research/fvg_forward.py `_series` builds
    the paper log's) over the stored 5m history (cached): every day has the sigma of the previous VOL_DAYS dense days, and
    the detectors take their live branches (H7's momentum on any day, scripts/research/edge_f3.py:125-132; G9 scans every
    bar of the day, scripts/research/edge_f4.py:88-97). `causal`: the dense-day rule is `causal_density` (the sensitivity)."""
    key = (sym, bool(causal))
    if key not in _PIT:
        import history_store as HS
        EC = _ec()
        doc, _ = HS.read_doc(sym, "5m", root=EC.HIST_ROOT)
        if doc is None:
            raise G.Refused(f"refused: no 5m history for {sym} under {EC.HIST_ROOT}")
        s = EC.Series(sym, doc["candles"], server_zone(), end=HIST_END, sigma_every_day=True)
        _PIT[key] = causal_density(s) if causal else s
    return _PIT[key]


def research_sig_by_day(s):
    """The F3 H5 sigma history: {dense day: sigma_5m} (research mode, scripts/research/edge_f3.py:100-104)."""
    return {d: s._vol[d] for d in s.dense_days if s._vol.get(d)}


def pit_events(s, det, end_day=LOAD_END):
    """The component's events as the paper log takes them (scripts/research/fvg_forward.py `signals`), on a point-in-time
    series: the detector's events whose entry bar exists, enters before `end_day`, lies on the SIGNAL's server day (a signal
    on a day's last bar has no same-day trade: dropped) and whose signal day has a sigma. Returns (events, dropped): events
    [{"i", "e", "side", "day", "entry_px"}] in detector order, `day` = the entry server day; dropped {"last_bar": [entry
    days], "no_sigma": [entry days]}. Outcome-blind (no exit, cost or R)."""
    evs, last_bar, no_sig = [], [], []
    for ev in det(s):
        e = ev["entry_i"]
        if e >= len(s.C):
            continue
        d = s.sday[e]
        if d >= end_day:
            continue
        if s.sday[ev["i"]] != d:
            last_bar.append(d)
            continue
        if not s.sigma(ev["i"]):
            no_sig.append(d)
            continue
        evs.append({"i": ev["i"], "e": e, "side": ev["side"], "day": d, "entry_px": ev.get("entry_px")})
    return evs, {"last_bar": last_bar, "no_sigma": no_sig}


def paper_log_refusals(s, evs, ff=None):
    """{entry bar index: "hole" | "stale_vol"} for the `pit_events` events the paper log WOULD refuse had it run at the
    signal's time (scripts/research/fvg_forward.py `signals`: a data hole in the 35 days before the signal, else fewer than 20
    dense days in the 40 before it), with the paper log's own `holes`, `_vol_fresh` and `HOLE_LOOKBACK`. The paper log only
    looks for holes since its forward start; this takes every hole of the history, which is what its rule means at any
    time (VC-P1 §2: a counterfactual, not applied to the decisive rows). Outcome-blind (bar times and counts only)."""
    ff = ff or _ff()
    ends = [ff._dt(h[1]) for h in ff.holes(s.T)]
    out = {}
    for ev in evs:
        t_sig = ff._dt(s.T[ev["i"]])
        j = bisect.bisect_left(ends, t_sig - ff.HOLE_LOOKBACK)
        if j < len(ends) and ends[j] <= t_sig:
            out[ev["e"]] = "hole"
        elif not ff._vol_fresh(s, ev["i"]):
            out[ev["e"]] = "stale_vol"
    return out


def vr_runs(vr, end=None):
    """{day: run index} over the days with a VR before `end`: a run is a maximal stretch of consecutive such days with the
    same label (HIGH iff VR > 1). The VR is a 20-day sigma over a 250-day median, so the label persists: the runs, not the
    days, are the independent regime blocks of T1a's contrast (VC-P1 §4, §7)."""
    out, k, prev = {}, -1, None
    for d in sorted(vr):
        if end is not None and d >= end:
            break
        h = vr[d] > 1.0
        if h != prev:
            k, prev = k + 1, h
        out[d] = k
    return out


def research_events(s, det, end_day=LOAD_END):
    """Outcome-blind: the events book_sim.trades trades on a RESEARCH-mode series (scripts/research/book_sim.py:48-57: the
    entry bar exists and the signal day has a research sigma; a signal on a day's last bar enters the next server day),
    entering before `end_day`, as {(entry bar time, side): entry day}; and the entry days of the events dropped for want of
    a research sigma (the same-day completeness selection, VC-P1 §1)."""
    keys, no_sig = {}, []
    for ev in det(s):
        e = ev["entry_i"]
        if e >= len(s.C):
            continue
        d = s.sday[e]
        if d >= end_day:
            continue
        if not s.sigma(ev["i"]):
            no_sig.append(d)
            continue
        keys[(s.T[e], ev["side"])] = d
    return keys, no_sig


def _day_view(s, e):
    """Entry e's server day plus the next stored bar (the first of a later server day), with the attributes
    fvg_forward.resolve_row reads; None when no later bar exists (the day is not over in the data). resolve_row on the
    view walks exactly the bars it walks on the whole series."""
    rows = s.day_rows[s.sday[e]]
    a, b = rows[0], rows[-1] + 2
    if b > len(s.T):
        return None
    return types.SimpleNamespace(T=s.T[a:b], O=s.O[a:b], H=s.H[a:b], L=s.L[a:b], C=s.C[a:b], dt=s.dt[a:b],
                                 sday=s.sday[a:b])


def pit_trade(s, ev, k, costs, zone, resolve):
    """One decisive row (VC-P1 §2): entry at the bar after the signal (its open), the paper log's stop k x sigma(signal
    day) x sqrt(nb) x price with nb = `bars_to_day_end` ON THE CLOCK (scripts/research/fvg_forward.py `signals`: what the
    live executor knows at entry), walked to the day's last stored bar by `resolve` (fvg_forward.resolve_row: book_sim's
    exit walk with this stop). None when the data has no later server day. nb_stored (the bars to the day's last STORED bar,
    book_sim's count) is kept for the disclosure."""
    e, side = ev["e"], ev["side"]
    px = ev["entry_px"] if ev.get("entry_px") is not None else s.O[e]
    nb = bars_to_day_end(s.dt[e], zone)
    dist = k * s.sigma(ev["i"]) * math.sqrt(nb) * px
    view = _day_view(s, e)
    if view is None:
        return None
    r = resolve(view, {"entry_time": s.T[e], "status": "open", "h": "eod", "side": side, "entry": px,
                       "stop": px - side * dist, "stop_distance": dist}, costs)
    if r.get("status") != "closed":
        return None
    gross = side * (r["exit"] - px) / dist
    return {"day": ev["day"], "side": side, "R_net": r["R"], "R_gross": gross, "R_bar": per_bar(gross, nb),
            "cost_R": gross - r["R"], "stop_bp": dist / px * 1e4, "entry_slot": slot_of(s.dt[e], zone),
            "nb_planned": nb, "nb_stored": s.day_rows[ev["day"]][-1] - e + 1, "exit": r["exit_reason"],
            "entry_time": s.T[e], "exit_time": r["exit_time"], "entry": px, "stop_distance": dist}


def pit_holdout_rows(component, k, end_day=None, series_fn=None, zone=None, costs_fn=None, resolve=None):
    """(decisive-definition rows labelled HIGH / LOW with entry day < end_day, info) for one book component: `pit_events`
    on the point-in-time series, `pit_trade` each, the point-in-time VR (`pit_vr_by_day`). Each row also carries its
    `refusal` (what the paper log would have done, `paper_log_refusals`; not applied) and its VR `run` (`vr_runs`). info:
    the trades, how many have no VR and their entry days, and the entry days of the events dropped (last-bar signals, no
    sigma, no later day)."""
    end_day = end_day or HOLDOUT_END
    BS = _load("book_sim", "scripts/research/book_sim.py")
    sym, det, _hold = BS.COMPONENTS[component]
    s = (series_fn or _pit_series)(sym)
    zone = zone or server_zone()
    evs, dropped = pit_events(s, det, end_day)
    refusals = paper_log_refusals(s, evs)
    costs = (costs_fn or _ec().Costs)(sym)
    resolve = resolve or _ff().resolve_row
    rows, unresolved = [], []
    for ev in evs:
        r = pit_trade(s, ev, k, costs, zone, resolve)
        if r is None:
            unresolved.append(ev["day"])
            continue
        r.update(symbol=sym, component=component, refusal=refusals.get(ev["e"]))
        rows.append(r)
    vr = pit_vr_by_day(s)
    runs = vr_runs(vr)
    kept, missing = label(rows, vr)
    kept = [dict(r, run=runs[_as_date(r["day"])]) for r in kept]
    return kept, {"trades_before_end": len(rows), "without_vr": missing,
                  "no_vr_days": [r["day"] for r in rows if vr.get(_as_date(r["day"])) is None],
                  "last_bar_days": dropped["last_bar"], "no_sigma_days": dropped["no_sigma"],
                  "unresolved_days": unresolved}


def book_rows(trades, s, zone):
    """book_sim.trades rows -> VC rows keyed by the ENTRY server day, with the entry's server-clock slot, the bars from the
    entry to the day's last STORED bar (book_sim's nb), R_bar, and whether the signal was on the previous server day's last
    bar (`entry_next_day`). The research-mode report only (VC-P1 §6)."""
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
    """RESEARCH MODE (report-only, VC-P1 §6): (rows labelled HIGH / LOW with entry day < end_day, info) for one book
    component from book_sim.trades (the inherited definition: a sigma only on days that turn out dense, nb from the stored
    bars). Each labelled row carries its VR `run` (`vr_runs`: T1a's run-clustered companion). info: the trades before
    end_day, how many have no VR, and their entry days (`no_vr_days`)."""
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
    runs = vr_runs(vr)
    kept = [dict(r, run=runs[_as_date(r["day"])]) for r in kept]
    return kept, {"trades_before_end": len(rows), "without_vr": missing,
                  "no_vr_days": [r["day"] for r in rows if vr.get(_as_date(r["day"])) is None]}


def t1_verdict(t1a, t1b, per_a, per_b, t1a_runs):
    """T1 = {T1a volatility, T1b hold length} on pooled gold, Holm m = 2 at ALPHA_T1 with the by-day CR1 SE; a rejected
    sub-test passes only if its True half's mean NET R > 0 and both gold components' differences are > 0. T1a ALSO needs
    its run-clustered companion `t1a_runs` (the same contrast with the VR runs as clusters, VC-P1 §4) at one-sided
    p <= ALPHA_T1 (lead decision 2026-10-05, option C): T1a's HIGH / LOW halves are runs of consecutive days, so a
    difference between regimes could pass the by-day test alone. A run-clustered test that is not computable (no t) fails
    the condition. `T1a_by_day` keeps the by-day rule's result, `T1a_run_clustered_p` the companion's p. `reading` (VC-P1
    §4, §7, §9; lead decision D1 2026-10-04): a pass is DISCOVERY-GRADE for the condition and TF on forward data is its
    confirmation; no pass is NOT SHOWN, never "lead closed"."""
    rej = holm([t1a["p_one_sided"], t1b["p_one_sided"]], ALPHA_T1)
    ok = []
    for r, t, per in zip(rej, (t1a, t1b), (per_a, per_b)):
        ok.append(bool(r and (t["net_mean_high"] or 0) > 0 and all((per[c]["diff"] or 0) > 0 for c in GOLD)))
    p_runs = t1a_runs["p_one_sided"] if t1a_runs.get("t") is not None else None
    by_day = ok[0]
    ok[0] = bool(by_day and p_runs is not None and p_runs <= ALPHA_T1)
    reading = ("PASS: DISCOVERY-GRADE for the condition; TF on forward data is its confirmation" if any(ok) else
               "NOT SHOWN (inconclusive for a G9-concentrated effect; VC-P1 §7, §9)")
    if by_day and not ok[0]:
        reading += (" T1a: the by-day test passed, its run-clustered companion did not ("
                    + ("not computable" if p_runs is None else f"p = {p_runs:.3f} > {ALPHA_T1}")
                    + "): a difference between VR regimes that window B cannot tell from regime noise is not shown "
                      "(lead decision 2026-10-05; VC-P1 §4)")
    return {"T1a_volatility": ok[0], "T1b_hold_length": ok[1], "holm_rejected": rej, "T1a_by_day": by_day,
            "T1a_run_clustered_p": p_runs, "reading": reading}


def with_sensitivities(verdict, sens):
    """VC-P1 §4 (lead decision D2 2026-10-04): the decisive T1 verdict against the pre-registered sensitivities' (`sens`:
    {name: an xau_read result}, report-only: research mode, causal density). A sensitivity whose T1a / T1b verdict differs
    makes the read DATA-SENSITIVE: not decisive; one that could not be computed is named. No pass / fail changes."""
    keys = ("T1a_volatility", "T1b_hold_length")
    differs, unavailable, seen = [], [], {}
    for name, doc in sens.items():
        v = (doc or {}).get("T1_verdict")
        if not v:
            unavailable.append(name)
            continue
        seen[name] = {k: v[k] for k in keys}
        if any(bool(v[k]) != bool(verdict[k]) for k in keys):
            differs.append(name)
    note = ""
    if differs:
        note += f" DATA-SENSITIVE: not decisive ({', '.join(differs)} give another T1 verdict; report-only blocks)"
    if unavailable:
        note += f" SENSITIVITY UNAVAILABLE: {', '.join(unavailable)}"
    return dict(verdict, sensitivities=seen, data_sensitive=bool(differs), sensitivity_unavailable=unavailable,
                reading=verdict["reading"] + note)


def _guarded(fn):
    """A report-only block never stops the decisive result: a failure is recorded in its place (and is visible in the JSON)."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def _tests_on(rows_by_c):
    """T1a and T1b on the nb-weighted R_bar (T1a: `T1A_VALUE`, the VC-P1 §4 switch), T2 on silver's R_gross; per component
    T1a's and T1b's statistics (T1's per-component condition); the R_gross T1a and T1b are report-only."""
    gold = [r for c in GOLD for r in rows_by_c.get(c, [])]
    return {"T1a_xau_volatility": split_test(gold, value=T1A_VALUE, row_weight=T1A_WEIGHT),
            "T1b_xau_hold_length": split_test(gold, key="long_hold", value="R_bar", row_weight=nb_weight),
            "T2_silver": split_test(rows_by_c.get(SILVER[0], [])),
            "T1a_raw_R_report_only": split_test(gold),
            "T1b_raw_R_report_only": split_test(gold, key="long_hold"),
            "per_component_volatility": {c: split_test(v, value=T1A_VALUE, row_weight=T1A_WEIGHT)
                                         for c, v in rows_by_c.items()},
            "per_component_hold_length": {c: split_test(v, key="long_hold", value="R_bar", row_weight=nb_weight)
                                          for c, v in rows_by_c.items()}}


def _counts(rows_all, info, end):
    """Per component, entries before `end`: trades with a VR, trades without one (excluded), labelled trades whose signal
    was the previous server day's last bar (research mode keeps them), the events the decisive definition drops (a
    signal on a day's last bar, no sigma, no later day in the data) and the labelled trades the paper log would have
    refused (`paper_log_refusable`, not applied: VC-P1 §2)."""
    def n(days):
        return sum(1 for d in days if d < end)

    def refused(c, why):
        return sum(1 for r in rows_all[c] if r["day"] < end and r.get("refusal") == why)
    return {c: {"with_vr": sum(1 for r in rows_all[c] if r["day"] < end), "without_vr": n(info[c]["no_vr_days"]),
                "entry_next_day": sum(1 for r in rows_all[c] if r["day"] < end and r.get("entry_next_day")),
                "last_bar_dropped": n(info[c].get("last_bar_days", ())), "no_sigma": n(info[c].get("no_sigma_days", ())),
                "unresolved": n(info[c].get("unresolved_days", ())),
                "paper_log_refusable": {"hole": refused(c, "hole"), "stale_vol": refused(c, "stale_vol")}}
            for c in rows_all}


def xau_read(k=K, mode="pit", trades_fn=None, series_fn=None, zone=None, keep_rows=False, medians=None, costs_fn=None,
             resolve=None):
    """The xau-holdout read: tests on the DECISIVE window (HOLDOUT), the same tests report-only on REPORT_WINDOW with the
    decisive window's hold medians. Rows are built once up to LOAD_END and split by entry day. mode "pit": the decisive
    definition (`pit_holdout_rows`); "pit_causal": the same on a `causal_density` series (sensitivity, report-only);
    "research": the inherited book_sim rows (`holdout_rows`), report-only. Every mode computes T1a with the VR runs as
    clusters (`T1a_run_clustered`): part of T1a's pass rule (lead decision 2026-10-05, `t1_verdict`), so it is not guarded
    (window A's, report-only, is).
    The point-in-time modes add, report-only, every test without the trades the paper log would have refused
    (`excluding_paper_log_refusals_report_only`); a failure there is recorded in its place (`_guarded`), never raised."""
    if mode not in ("pit", "pit_causal", "research"):
        raise ValueError(f"xau_read: unknown mode {mode!r} (pit, pit_causal or research)")
    pit = mode in ("pit", "pit_causal")
    pit_series = series_fn or (lambda sym: _pit_series(sym, causal=(mode == "pit_causal")))
    rows_all, info = {}, {}
    for c in GOLD + SILVER:
        if pit:
            rows_all[c], info[c] = pit_holdout_rows(c, k, end_day=LOAD_END, series_fn=pit_series, zone=zone,
                                                    costs_fn=costs_fn, resolve=resolve)
        else:
            rows_all[c], info[c] = holdout_rows(c, k, end_day=LOAD_END, trades_fn=trades_fn, series_fn=series_fn,
                                                zone=zone)
    rows = {c: [r for r in v if r["day"] < HOLDOUT_END] for c, v in rows_all.items()}
    hold_medians = mark_hold([r for c in GOLD + SILVER for r in rows[c]], medians)
    mark_hold([r for c in GOLD + SILVER for r in rows_all[c]], hold_medians)      # the same recorded cut everywhere
    t = _tests_on(rows)
    t2 = t["T2_silver"]
    if not (t2["n_high"] or t2["n_low"]):
        t2 = dict(t2, not_run="window: no silver trade with a VR in the decisive window")
    t1a_runs = split_test([r for c in GOLD for r in rows[c]], value=T1A_VALUE, row_weight=T1A_WEIGHT, day_key="run")
    out = {"mode": mode, "T1a_xau_volatility": t["T1a_xau_volatility"], "T1a_run_clustered": t1a_runs,
           "T1b_xau_hold_length": t["T1b_xau_hold_length"],
           "T1_verdict": t1_verdict(t["T1a_xau_volatility"], t["T1b_xau_hold_length"], t["per_component_volatility"],
                                    t["per_component_hold_length"], t1a_runs=t1a_runs),
           "T2_silver": t2, "T1a_raw_R_report_only": t["T1a_raw_R_report_only"],
           "T1b_raw_R_report_only": t["T1b_raw_R_report_only"],
           "per_component_volatility": t["per_component_volatility"],
           "per_component_hold_length": t["per_component_hold_length"],
           "hold_medians": hold_medians, "holdout": HOLDOUT, "holdout_end": str(HOLDOUT_END),
           "counts": _counts(rows_all, info, HOLDOUT_END),
           "diagnostics": {"xau": diagnostics([r for c in GOLD for r in rows[c]]), "silver": diagnostics(rows[SILVER[0]])}}
    if pit:
        kept = {c: [r for r in v if not r.get("refusal")] for c, v in rows.items()}
        out["excluding_paper_log_refusals_report_only"] = _guarded(
            lambda: dict(_tests_on(kept), trades={c: len(v) for c, v in kept.items()}))
    rep = {c: [r for r in v if r["day"] < REPORT_END] for c, v in rows_all.items()}
    out[f"report_only_window_{REPORT_WINDOW}"] = dict(
        _tests_on(rep), end=str(REPORT_END), counts=_counts(rows_all, info, REPORT_END),
        T1a_run_clustered=_guarded(lambda: split_test([r for c in GOLD for r in rep[c]], value=T1A_VALUE,
                                                      row_weight=T1A_WEIGHT, day_key="run")),
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
    point-in-time series as the decisive window's (`pit_vr_by_day`) and the entry slot. R_net is RE-PRICED here from the
    logged entry and exit times and prices with `costs` (edge_census.Costs at the profile the read records; the formula of
    fvg_forward.resolve_row), so the read reproduces from its snapshot; the log's own R (priced at resolve time, profile not
    recorded) is kept as R_net_log."""
    idx = {t: i for i, t in enumerate(series.T)}
    vr = pit_vr_by_day(series)
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
    holdout statistic ((a) `T1A_VALUE` / `T1A_WEIGHT`, (b) the nb-weighted R_bar); (b) uses the holdout's recorded
    per-component median entry slots (`medians`), never the forward rows' own."""
    keys = {"a": ("high", T1A_VALUE, T1A_WEIGHT), "b": ("long_hold", "R_bar", nb_weight)}
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
    """{"side=S|half": {"n", "bars", "days", "n2_days", "rootnb2_days"}} over events with a VR: half = high / low (VR),
    long_hold / short_hold (the event's `long_hold`, marked against its own component's median entry slot; None: no hold
    split). For `power_inputs`' same-day bound: n2_days = sum over the cell's days of (its events that day)^2, rootnb2_days
    = the sum over its days of (sum of sqrt(nb) that day)^2, rounded (ints, like every count here)."""
    acc = collections.defaultdict(lambda: {"n": 0, "bars": 0, "by_day": collections.defaultdict(lambda: [0, 0.0])})
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
            g = a["by_day"][ev["day"]]
            g[0] += 1
            g[1] += math.sqrt(ev["nb"])
    return {k: {"n": v["n"], "bars": v["bars"], "days": len(v["by_day"]),
                "n2_days": sum(g[0] ** 2 for g in v["by_day"].values()),
                "rootnb2_days": round(sum(g[1] ** 2 for g in v["by_day"].values()))} for k, v in sorted(acc.items())}


def _in_half(ev, h):
    if h in ("high", "low"):
        return ev["high"] is (h == "high")
    return ev["long_hold"] is (h == "long_hold")


def _nb_split(evs):
    """Outcome-blind (bar times only), VC-P1 §2 disclosure: over events with a VR, sides pooled, overall and per half, the
    sums of the CLOCK bar count nb (the decisive stop's) and of the STORED bars from the entry to the day's last stored bar
    (book_sim's), how many fall short by more than 12 bars; the missing bars between the entry and the day's last stored bar
    (`with_holes`: events with any, `holes_bars`: their sum); the clock bars after the day's last stored bar
    (`early_end_bars`; the gold session closes 1-2 bars before the rollover, so `early_end_gt2` counts the days whose
    stored data stops earlier than that). Ints only."""
    out = {}
    for h in ("all",) + HALVES:
        xs = [x for x in evs if x["high"] is not None and (h == "all" or _in_half(x, h))]
        out[h] = {"n": len(xs), "nb_clock": sum(x["nb"] for x in xs), "nb_stored": sum(x["nb_stored"] for x in xs),
                  "short_gt12": sum(1 for x in xs if x["nb"] - x["nb_stored"] > 12),
                  "with_holes": sum(1 for x in xs if x["holes"] > 0), "holes_bars": sum(x["holes"] for x in xs),
                  "early_end_gt2": sum(1 for x in xs if x["early_end"] > 2),
                  "early_end_bars": sum(x["early_end"] for x in xs)}
    return out


def power_inputs(cells):
    """Outcome-blind power arithmetic from `_cells` counts. se_per_sd: the side-balanced contrast's SE per unit of the
    per-trade sd of R, so MDE (80 % power, one-sided 0.025: the first Holm step) = 2.80 x sd(R) x se_per_sd. Trades
    independent: an R_gross split gives sqrt(1/4 sum_c 1 / n_c), an nb-weighted R_bar split sqrt(1/4 sum_c NB_REF / bars_c)
    (Var = NB_REF x Var(R) / sum(nb) per cell). T1a is the VR split on its statistic (`T1A_VALUE`), T1b the hold split on the
    weighted R_bar; T1a_raw_R (T2's and T3's statistic) and T1b_raw_R are the R_gross splits. `se_per_sd_same_day`: the
    same with the trades of one server day in one cell perfectly correlated (an H7 and a G9 trade of one gold day): R_gross
    sqrt(1/4 sum_c n2_days_c / n_c^2), weighted R_bar sqrt(1/4 sum_c NB_REF x rootnb2_days_c / bars_c^2). It bounds the
    within-cell clustering only; same-day trades in the two halves of T1b lower the read's SE instead. None when a cell is
    empty or lacks the sums. mean_bars per half (sides pooled) and the VR halves' gap |high - low| / min(high, low): T1a's
    switch (`T1A_GAP_RULE`). The MDE is the pooled test's alone: `rule_power` adds T1's per-component gate."""
    def get(side, h):
        return cells.get(f"side={side}|{h}", {"n": 0, "bars": 0})

    def se(hs, f):
        cs = [get(s, h) for s in SIDES for h in hs]
        if not all(c["n"] for c in cs):
            return None
        v = [f(c) for c in cs]
        return None if None in v else math.sqrt(0.25 * sum(v))

    def raw(c):
        return 1.0 / c["n"]

    def wtd(c):
        return NB_REF / c["bars"]

    def raw_day(c):
        return c["n2_days"] / c["n"] ** 2 if "n2_days" in c else None

    def wtd_day(c):
        return NB_REF * c["rootnb2_days"] / c["bars"] ** 2 if "rootnb2_days" in c else None

    mean_bars = {}
    for h in HALVES:
        n = sum(get(s, h)["n"] for s in SIDES)
        mean_bars[h] = sum(get(s, h)["bars"] for s in SIDES) / n if n else None
    gap = None
    if mean_bars["high"] and mean_bars["low"]:
        gap = abs(mean_bars["high"] - mean_bars["low"]) / min(mean_bars["high"], mean_bars["low"])
    vr, hold = ("high", "low"), ("long_hold", "short_hold")
    t1a, t1a_day = (wtd, wtd_day) if T1A_WEIGHT else (raw, raw_day)
    return {"mean_bars": mean_bars, "vr_halves_bars_gap": gap,
            "se_per_sd": {"T1a": se(vr, t1a), "T1b": se(hold, wtd), "T1a_raw_R": se(vr, raw), "T1b_raw_R": se(hold, raw)},
            "se_per_sd_same_day": {"T1a": se(vr, t1a_day), "T1b": se(hold, wtd_day), "T1a_raw_R": se(vr, raw_day),
                                   "T1b_raw_R": se(hold, raw_day)}}


def _t_crit(alpha, df):
    """One-sided Student-t critical value at `alpha` with `df` degrees of freedom: the normal quantile with the first four
    terms of its Cornish-Fisher expansion in 1 / df (error < 1e-4 for df >= 10; the decisive window's df are 70-150).
    Arithmetic only."""
    z = statistics.NormalDist().inv_cdf(1.0 - alpha)
    g = ((z ** 3 + z) / 4, (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96, (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384,
         (79 * z ** 9 + 776 * z ** 7 + 1482 * z ** 5 - 1920 * z ** 3 - 945 * z) / 92160)
    return z + sum(c / df ** (n + 1) for n, c in enumerate(g))


def rule_power(comp_cells, pooled_cells, split, effect, same_day=False, sd=SD_R, reps=None, seed=None):
    """Power of T1's FULL pass rule for sub-test `split` ("a": the VR halves, "b": the hold halves), by simulation from the
    dry run's cell counts alone (no outcome; VC-P1 §7, lead decision 2026-10-04). Each gold component's side x half cell
    mean of the nb-weighted R_bar is normal with mean +effect[c] / 2 (True half) or -effect[c] / 2 (False half) and
    variance sd^2 x NB_REF / bars (trades independent). same_day=True: the trades of one server day in one pooled cell
    perfectly correlated (the H7 / G9 covariance that gives the pooled cell the `se_per_sd_same_day` variance). The pooled
    cell mean is the bars-weighted mean of the components'. Pass: the pooled balanced difference over its SE (`se_per_sd`,
    or `se_per_sd_same_day`) beats Holm (m = 2, ALPHA_T1, Student-t with min(days per pooled cell) - 1 df; the other
    sub-test null, rejecting first with probability ALPHA_T1 / 2, independently), AND the balanced difference is > 0 in
    BOTH components; the True half's net-R condition is taken as met. Returns {pooled_alone (one-sided ALPHA_T1 / 2),
    holm, full_rule} rounded to 3; None when a pooled cell is empty; full_rule 0 when a component's cell is empty. `reps` /
    `seed` default to POWER_REPS / POWER_SEED (read at call time)."""
    reps = POWER_REPS if reps is None else reps
    seed = POWER_SEED if seed is None else seed
    halves = ("high", "low") if split == "a" else ("long_hold", "short_hold")
    pin = power_inputs(pooled_cells)
    se_p = (pin["se_per_sd_same_day"] if same_day else pin["se_per_sd"])["T1a" if split == "a" else "T1b"]
    names = [(s, t, f"side={s}|{h}") for s in SIDES for t, h in ((True, halves[0]), (False, halves[1]))]
    if se_p is None or any(not pooled_cells.get(nm, {}).get("n") for _s, _t, nm in names):
        return None
    se_p *= sd
    df = min(pooled_cells[nm]["days"] for _s, _t, nm in names) - 1
    gate = all(comp_cells[c].get(nm, {}).get("n") for c in GOLD for _s, _t, nm in names)
    spec = []
    for s, t, nm in names:
        sign = 0.5 if t else -0.5
        b = {c: comp_cells[c].get(nm, {}).get("bars", 0) for c in GOLD}
        sds = {c: sd * math.sqrt(NB_REF / b[c]) if b[c] else 0.0 for c in GOLD}
        rho = 0.0
        if same_day and all(b.values()):
            r = {c: comp_cells[c][nm]["rootnb2_days"] for c in GOLD}
            cov = sd * sd * NB_REF * (pooled_cells[nm]["rootnb2_days"] - sum(r.values())) / (2 * b[GOLD[0]] * b[GOLD[1]])
            rho = max(-1.0, min(1.0, cov / (sds[GOLD[0]] * sds[GOLD[1]])))
        spec.append((s, t, b, sds, rho, {c: sign * effect[c] for c in GOLD}))
    c1, c2 = _t_crit(ALPHA_T1 / 2, df), _t_crit(ALPHA_T1, df)
    rng = random.Random(seed)
    n1 = nh = nf = 0
    for _ in range(reps):
        dp, dc = 0.0, {c: 0.0 for c in GOLD}
        for s, t, b, sds, rho, mu in spec:
            z1, z2 = rng.gauss(0.0, 1.0), rng.gauss(0.0, 1.0)
            m = {GOLD[0]: mu[GOLD[0]] + sds[GOLD[0]] * z1,
                 GOLD[1]: mu[GOLD[1]] + sds[GOLD[1]] * (rho * z1 + math.sqrt(1.0 - rho * rho) * z2)}
            w = 0.5 if t else -0.5
            dp += w * sum(b[c] * m[c] for c in GOLD) / sum(b.values())
            for c in GOLD:
                dc[c] += w * m[c]
        tt = dp / se_p
        rej = tt > c1 or (rng.random() < ALPHA_T1 / 2 and tt > c2)
        n1 += tt > c1
        nh += rej
        nf += rej and gate and all(dc[c] > 0 for c in GOLD)
    return {"pooled_alone": round(n1 / reps, 3), "holm": round(nh / reps, 3), "full_rule": round(nf / reps, 3)}


def rule_power_table(comp_cells, pooled_cells):
    """`rule_power` of T1a and T1b for every POWER_SHAPES effect, trades independent and at the same-day bound."""
    out = {"sd_R": SD_R, "reps": POWER_REPS, "seed": POWER_SEED, "effects_R_bar": POWER_SHAPES}
    for key, split in (("T1a", "a"), ("T1b", "b")):
        out[key] = {name: {"independent": rule_power(comp_cells, pooled_cells, split, eff),
                           "same_day": rule_power(comp_cells, pooled_cells, split, eff, same_day=True)}
                    for name, eff in POWER_SHAPES.items()}
    return out


def regime_blocks(vr, end, evs, blocks=True):
    """Outcome-blind (VC-P1 §4, §7): the VR runs before `end` (`vr_runs`) -- the independent regime blocks of T1a's contrast,
    since the VR is a 20-day sigma over a 250-day median -- their number, the median length per half
    (statistics.median: the mean of the middle two for an even number of runs) and the longest; when `blocks`, every run's
    length per half (`run_days`) and each run with its label, first day, days and trades (the `evs` with a VR before `end`);
    and the trades by calendar year and half."""
    runs = vr_runs(vr, end)
    blocks_by_run = collections.OrderedDict()
    for d in sorted(runs):
        b = blocks_by_run.setdefault(runs[d], {"half": "high" if vr[d] > 1.0 else "low", "first_day": str(d), "days": 0, "trades": 0})
        b["days"] += 1
    by_year = collections.defaultdict(lambda: {"high": 0, "low": 0})
    for x in evs:
        if x["high"] is None or x["day"] >= end:
            continue
        blocks_by_run[runs[x["day"]]]["trades"] += 1
        by_year[str(x["day"].year)]["high" if x["high"] else "low"] += 1
    lens = {h: sorted(b["days"] for b in blocks_by_run.values() if b["half"] == h) for h in ("high", "low")}
    out = {"days_with_vr": len(runs), "runs": {h: len(v) for h, v in lens.items()},
           "run_days_median": {h: (statistics.median(v) if v else None) for h, v in lens.items()},
           "run_days_max": max((b["days"] for b in blocks_by_run.values()), default=0),
           "trades_by_year": dict(sorted(by_year.items()))}
    if blocks:
        out["run_days"] = lens
        out["blocks"] = list(blocks_by_run.values())
    return out


def dry_counts(series_fn=None, pit_series_fn=None, zone=None, causal_series_fn=None):
    """Outcome-blind, per component and window ({"decisive": HOLDOUT, "report_only": REPORT_WINDOW}), on the decisive
    definition: `pit_events` on the point-in-time series by VR half (`pit_vr_by_day`; per component its first day with a VR,
    `first_vr_day`); the events it drops (a signal on a day's last bar: `last_bar_signal`; no sigma); the hold halves at
    the median ENTRY slot of the decisive window (the (b) cut a read records), also split by VR half, so a timing imbalance
    between the VR halves is visible before any read; the planned bars (the CLOCK count to the rollover: the stop's horizon
    and T1b's weight) as quantiles and the count under SHORT_NB; per side x half the events, planned bars and days (`cells`)
    and their `power_inputs` (silver: T2's se_per_sd is `T1a_raw_R`). Disclosure (VC-P1 §1-§2): `research_mode` -- the
    inherited book_sim selection on the research-mode series (its events, those dropped for want of a research sigma, and
    the events in one definition only, by entry bar time and side); `nb_clock_vs_stored` (`_nb_split`); `refusable` -- the
    events with a VR the paper log would have refused (`paper_log_refusals`; hole / stale_vol, by VR half and hold half; not
    applied). Pooled gold (H7 + G9, T1's population): the summed cells, `power_inputs`, `nb_clock_vs_stored`,
    `regime_blocks` (the VR runs and trades by year) and, for the decisive window, `rule_power` (T1's full rule).
    `causal_density` (the sensitivity's sample, `causal_series_fn`): per gold component the events by VR half and each
    window's dense days under the whole-history rule and the causal one. No trade is simulated: no exit, cost or R is
    computed (`pit_trade`, `resolve_row` and book_sim.trades never run; the sealing probe traced it, VC-P1 §7)."""
    BS = _load("book_sim", "scripts/research/book_sim.py")
    zone = zone or server_zone()
    windows = (("decisive", HOLDOUT, HOLDOUT_END), ("report_only", REPORT_WINDOW, REPORT_END))
    out, pooled = {}, {name: [] for name, _w, _e in windows}
    vr_gold = None
    for c in GOLD + SILVER:
        sym, det, _hold = BS.COMPONENTS[c]
        s = (pit_series_fn or _pit_series)(sym)
        vr = pit_vr_by_day(s)
        if c in GOLD:
            vr_gold = vr
        raw_evs, dropped = pit_events(s, det, LOAD_END)
        refusals = paper_log_refusals(s, raw_evs)
        evs = []
        for ev in raw_evs:
            e, d = ev["e"], ev["day"]
            last = s.day_rows[d][-1]
            nb = bars_to_day_end(s.dt[e], zone)
            span = int((s.dt[last] - s.dt[e]).total_seconds() // 300) + 1
            v = vr.get(d)
            evs.append({"day": d, "high": None if v is None else v > 1.0, "slot": slot_of(s.dt[e], zone), "nb": nb,
                        "nb_stored": last - e + 1, "holes": span - (last - e + 1), "early_end": nb - span,
                        "side": ev["side"], "key": (s.T[e], ev["side"]), "refusal": refusals.get(e)})
        r_keys, r_no_sig = research_events((series_fn or _xau_series)(sym), det, LOAD_END)
        dec = [x["slot"] for x in evs if x["day"] < HOLDOUT_END and x["high"] is not None]
        med = statistics.median(dec) if dec else None
        for x in evs:
            x["long_hold"] = None if med is None else x["slot"] < med         # the component's own median, as the read
        res = {"median_entry_slot": med, "first_vr_day": str(min(vr)) if vr else None}
        for name, w, end in windows:
            n, rf = collections.Counter(), collections.Counter()
            inside = [x for x in evs if x["day"] < end]
            for x in inside:
                high = x["high"]
                n["no_vr" if high is None else ("high" if high else "low")] += 1
                if high is not None and x["long_hold"] is not None:
                    n[f"{'high' if high else 'low'}_{'long' if x['long_hold'] else 'short'}_hold"] += 1
                if high is not None and x["refusal"]:
                    rf[x["refusal"]] += 1
                    rf["high" if high else "low"] += 1
                    if x["long_hold"] is not None:
                        rf["long_hold" if x["long_hold"] else "short_hold"] += 1
            n["last_bar_signal"] = sum(1 for d in dropped["last_bar"] if d < end)
            n["no_sigma"] = sum(1 for d in dropped["no_sigma"] if d < end)
            mine = {x["key"] for x in inside}
            theirs = {key for key, d in r_keys.items() if d < end}
            research = {"events": len(theirs), "no_research_sigma": sum(1 for d in r_no_sig if d < end),
                        "only_point_in_time": len(mine - theirs), "only_research": len(theirs - mine)}
            cells = _cells(inside)
            res[name] = dict(n, window=w, end=str(end), research_mode=research, nb_clock_vs_stored=_nb_split(inside),
                             refusable={k: rf.get(k, 0) for k in ("hole", "stale_vol", "high", "low", "long_hold",
                                                                  "short_hold")},
                             planned_bars=_quantiles([x["nb"] for x in inside if x["high"] is not None]),
                             cells=cells, power_inputs=power_inputs(cells))
            if c in GOLD:
                pooled[name] += inside
        out[c] = res
    out["xau_pooled"] = {}
    for name, w, end in windows:
        cells = _cells(pooled[name])
        out["xau_pooled"][name] = dict(power_inputs(cells), window=w, end=str(end), cells=cells,
                                        planned_bars=_quantiles([x["nb"] for x in pooled[name] if x["high"] is not None]),
                                        nb_clock_vs_stored=_nb_split(pooled[name]),
                                        regime_blocks=regime_blocks(vr_gold, end, pooled[name], blocks=(name == "decisive")))
    out["xau_pooled"]["decisive"]["rule_power"] = rule_power_table({c: out[c]["decisive"]["cells"] for c in GOLD},
                                                                   out["xau_pooled"]["decisive"]["cells"])
    out["causal_density"] = causal = {}
    for c in GOLD:
        sym, det, _hold = BS.COMPONENTS[c]
        cs = (causal_series_fn or (lambda y: _pit_series(y, causal=True)))(sym)
        cvr = pit_vr_by_day(cs)
        cevs, cdrop = pit_events(cs, det, LOAD_END)
        causal[c] = {"first_vr_day": str(min(cvr)) if cvr else None}
        for name, w, end in windows:
            n = collections.Counter()
            for ev in cevs:
                if ev["day"] < end:
                    v = cvr.get(ev["day"])
                    n["events"] += 1
                    n["no_vr" if v is None else ("high" if v > 1.0 else "low")] += 1
            n["no_sigma"] = sum(1 for d in cdrop["no_sigma"] if d < end)
            causal[c][name] = {k: n.get(k, 0) for k in ("events", "high", "low", "no_vr", "no_sigma")}
    gs, cs = (pit_series_fn or _pit_series)("XAUUSD"), (causal_series_fn or (lambda y: _pit_series(y, causal=True)))("XAUUSD")
    causal["XAUUSD_dense_days"] = {name: {"days": sum(1 for d in gs.day_rows if d < end),
                                          "whole_history_rule": sum(1 for d in gs.dense_days if d < end),
                                          "causal_rule": sum(1 for d in cs.dense_days if d < end)}
                                   for name, _w, end in windows}
    whole, caus = set(gs.dense_days), set(cs.dense_days)
    by_year = collections.defaultdict(lambda: {"days": 0, "whole_history_rule": 0, "causal_rule": 0})
    for d in gs.day_rows:
        if d < LOAD_END:
            y = by_year[str(d.year)]
            y["days"] += 1
            y["whole_history_rule"] += d in whole
            y["causal_rule"] += d in caus
    causal["XAUUSD_dense_days"]["by_year"] = dict(sorted(by_year.items()))
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
            "definition": "point in time (VC-P1 §1-§2): sigma_every_day series, last-bar signals dropped, nb on the clock, "
                          "fvg_forward.resolve_row walk; whole-history dense threshold (edge_census.py:104-107); "
                          "report-only sensitivities: research mode, causal density, without the paper log's refusals",
            "t1a_statistic": f"{T1A_VALUE}, cell means weighted by {getattr(T1A_WEIGHT, '__name__', None)} (VC-P1 §4 "
                             f"switch, gap rule {T1A_GAP_RULE})",
            "t1b_statistic": "R_bar, cell means weighted by nb_planned (nb_weight)",
            "holdout": HOLDOUT, "holdout_end": str(HOLDOUT_END), "report_window": REPORT_WINDOW,
            "report_end": str(REPORT_END), "written_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}


def _uncommitted(paths):
    """The `paths` that differ from git HEAD (modified or untracked) now, or None when git cannot tell: a dry run on
    uncommitted code records them, because its git_head then does not hold that code (its code_sha256 does)."""
    r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", *paths], capture_output=True, text=True,
                       check=False)
    if r.returncode != 0:
        return None
    return sorted({ln[3:].strip() for ln in r.stdout.splitlines() if ln.strip()})


def cost_profile(syms):
    """The cost profile that prices the trades and the forward read's re-priced R_net (edge_census.Costs, at read time),
    with the sha256 of each symbol's spec file under it and its price_ref provenance (real_costs.price_ref_info: the
    median close, its window and the closes' sha256; CLAUDE.md §46)."""
    import real_costs as RC
    EC = _ec()
    out, ref = {}, {}
    for sym in syms:
        p = RC.spec_path(EC.COST_PROFILE, sym)
        out[sym] = G.file_sha256(p) if os.path.exists(p) else None
        ref[sym] = RC.price_ref_info(EC.COST_PROFILE, sym)
    return {"name": EC.COST_PROFILE, "spec_sha256": out, "price_ref_info": ref}


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


def require_ledger(root):
    """The research ledger registers this study before any read (VC-P1 §5.4, §10 step 5; CLAUDE.md §43-44): LEDGER is
    committed unchanged and its LEDGER_KEY entry names PREREG and TAG. Refused otherwise. Returns (the path, entry and
    sha256 recorded in the read's meta: the ledger is not code, so the manifest does not cover it; the entry itself)."""
    G.require_committed(root, [LEDGER])
    path = os.path.join(root, LEDGER)
    with open(path, encoding="utf-8") as fh:
        entry = json.load(fh).get(LEDGER_KEY) or {}
    if entry.get("preregistration") != PREREG or entry.get("tag") != TAG:
        raise G.Refused(f"refused: {LEDGER} has no {LEDGER_KEY!r} entry naming {PREREG} and {TAG} "
                        f"(the seal commit adds it, VC-P1 §10 step 5)")
    return {"path": LEDGER, "entry": LEDGER_KEY, "sha256": G.file_sha256(path)}, entry


def dataset_lines(snapshot):
    """The `dataset-sha256 <64 hex> <SYM|tf>` lines VC-P1 §7 carries for a dataset snapshot (as manifest_lines for code)."""
    return [f"dataset-sha256 {snapshot[k]} {k}" for k in sorted(snapshot)]


def require_dataset(text, snapshot, entry):
    """The xau-holdout read refuses unless the stored history it loads (`snapshot`, prereg_guard.dataset_snapshot of
    DATASET_PAIRS) is byte-identical to the sealed text's `dataset-sha256` lines, and the ledger `entry` carries the same
    digests as `dataset` (VC-P1 §7, §10; lead decision 2026-10-04). Returns the sealed {SYM|tf: sha256}."""
    want = {f"{sym}|{tf}" for sym, tf in DATASET_PAIRS}
    sealed = {}
    for sha, key in DATASET_LINE.findall(text):
        if key in sealed:
            raise G.Refused(f"refused: {key} is pinned twice in the sealed text")
        sealed[key] = sha
    if set(sealed) != want:
        raise G.Refused(f"refused: the sealed text does not pin the dataset ({', '.join(sorted(want ^ set(sealed)))}); its "
                        f"§7 carries the dry run's `dataset-sha256` lines")
    if set(snapshot) != want:
        raise G.Refused(f"refused: the dataset snapshot covers {sorted(snapshot)}, not {sorted(want)}")
    bad = [f"{k} ({snapshot[k][:12]} != sealed {sealed[k][:12]})" for k in sorted(want) if snapshot[k] != sealed[k]]
    if bad:
        raise G.Refused("refused: the stored history changed since the seal: " + "; ".join(bad)
                        + " (the decisive window's events depend on the whole history; re-seal by amendment)")
    if (entry or {}).get("dataset") != sealed:
        raise G.Refused(f"refused: {LEDGER} {LEDGER_KEY!r} does not carry the sealed dataset digests as `dataset`")
    return sealed


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
    if not os.path.exists(FF.LOG):
        raise G.Refused(f"refused: no paper log at {_rel(FF.LOG)} (the forward read runs where fvg_forward writes it)")
    with open(FF.LOG, "rb") as fh:                     # read ONCE: the snapshot hashes exactly the bytes the rows came from
        log_bytes = fh.read()
    log = [json.loads(x) for x in log_bytes.decode("utf-8").splitlines() if x.strip()]
    n_closed = sum(1 for x in log if is_forward_row(x, first, zone))
    if not forward_due(n_closed, first - datetime.timedelta(days=1), datetime.date.today()):
        raise G.Refused(f"refused: forward read not due ({n_closed} closed rows < {FWD_MIN_ROWS}, < {FWD_MAX_DAYS} days)")
    candles = FF.merged_candles("XAUUSD")
    res["meta"]["dataset"] = forward_snapshot(FF.LOG, log_bytes, candles)
    s = _ec().Series("XAUUSD", candles, zone, end=HIST_END, sigma_every_day=True)
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
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    r.add_argument("--cx-amendment")
    r.add_argument("--cx-closed", nargs="+")
    r.add_argument("--spec-dir")
    r.add_argument("--commission", help='{"BTCUSD": c_sym, ...}: commission per side, fraction of notional ([CX-P1] §2)')
    r.add_argument("--xau", help="forward: the committed xau-holdout read JSON (its T1 verdict and hold medians); the "
                                  "forward window starts after the seal commit (git), no date is typed")
    v = sub.add_parser("verdict", help="T1 as the committed xau-holdout read recorded it, and Holm over T2 / T3 (no data "
                                       "read)")
    v.add_argument("--xau", required=True)
    v.add_argument("--crypto")
    a = ap.parse_args()
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE)))
        return
    if a.cmd == "verdict":
        p = G.require_read_json(ROOT, _rel(a.xau), FAMILY, "xau-holdout", TAG)["primary"]
        c = G.require_read_json(ROOT, _rel(a.crypto), FAMILY, "crypto", TAG)["T3_crypto"] if a.crypto else None
        print(json.dumps({"T1_verdict": p.get("T1_verdict"),
                          "secondary": secondary_verdict(p["T2_silver"].get("p_one_sided"),
                                                         c.get("p_one_sided") if c else None)}, indent=1))
        return
    hist = os.path.join(ROOT, "data", "history", "ftmo")
    if a.cmd == "dry-run":
        G.refuse_overwrite(a.out)
        if any(G.read_name(FAMILY, x).match(_rel(a.out)) for x in READS):
            raise G.Refused(f"refused: {a.out} is a read's output name; a dry run there would block that read for good "
                            f"(require_read_once)")
        meta = dict(_meta("dry-run"), code_sha256={p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE},
                    code_uncommitted=_uncommitted(CODE), dataset=G.dataset_snapshot(hist, DATASET_PAIRS))
        _dump({"meta": meta, "counts": dry_counts()}, a.out)
        return
    G.refuse_overwrite(a.out)
    G.require_read_once(ROOT, _rel(a.out), FAMILY, a.read)
    text = G.require_sealed(ROOT, PREREG, TAG)
    G.require_committed(ROOT, CODE)
    man = G.require_fingerprint(ROOT, text, CODE)
    ledger, entry = require_ledger(ROOT)
    dataset = require_dataset(text, G.dataset_snapshot(hist, DATASET_PAIRS), entry) if a.read == "xau-holdout" else None
    if sys.pycache_prefix is not None:
        raise G.Refused(f"refused: sys.pycache_prefix is {sys.pycache_prefix!r} (PYTHONPYCACHEPREFIX / -X pycache_prefix): "
                        f"bytecode outside the repository would hide executed code from require_covered")
    G.trace_start(ROOT)
    res = {"meta": dict(_meta(a.read), ledger=ledger)}
    if a.read == "xau-holdout":
        res["meta"]["dataset"] = dataset
        res["meta"]["cost_profile"] = cost_profile(["XAUUSD", "XAGUSD"])
        res["primary"] = xau_read(K, keep_rows=True)
        med = res["primary"]["hold_medians"]
        res["report_k2"] = _guarded(lambda: xau_read(K_REPORT, medians=med))
        res["research_mode_report_only"] = _guarded(lambda: xau_read(K, mode="research", medians=med))
        res["causal_density_report_only"] = _guarded(lambda: xau_read(K, mode="pit_causal", medians=med))
        res["primary"]["T1_verdict"] = with_sensitivities(res["primary"]["T1_verdict"], {
            "research_mode": res["research_mode_report_only"], "causal_density": res["causal_density_report_only"]})
    elif a.read == "crypto":
        _crypto(a, res)
    else:
        _forward(a, res)
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, a.out)


if __name__ == "__main__":
    main()
