#!/usr/bin/env python3
"""Edge family H7x (docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md): the gold intraday-trend rules H7 (F3) and G9 (F4)
transferred, parameters unchanged, to the crypto symbols of scripts/instruments.py backtested("crypto"), on the UTC day.
Each read ONCE, in order, each in its own commit, from a CLEAN tree whose committed pre-registration carries amendment
[H7x-A1] (realized funding, the venue-switch day, on-grid completeness -- see PREREG_AMENDMENT):

    python3 scripts/research/edge_h7x.py dry-run --out <json>        # outcome-blind: bars, spans, gaps, EVENT COUNTS only
    python3 scripts/research/edge_h7x.py run --read discovery    --out docs/audits/2026-10-03-edge-h7x-discovery.json
    python3 scripts/research/edge_h7x.py run --read confirmation --after docs/audits/2026-10-03-edge-h7x-discovery.json \
        --out docs/audits/2026-10-03-edge-h7x-confirmation.json
    python3 scripts/research/edge_h7x.py run --read exposed      --after docs/audits/2026-10-03-edge-h7x-confirmation.json \
        --out docs/audits/2026-10-03-edge-h7x-exposed.json

A read computes outcome rows (and its placebo, comparator, sizing and correlation diagnostics) ONLY for events and days of its
own period. Registration guard (run(require_clean=True), the CLI default): the --out path is the canonical one above and has
no git history; this script, its tests, the pre-registration (with the amendment tag) and every reused module are tracked and
unmodified; the --after JSON is tracked and clean, was itself written under the guard, its git_head is an ancestor of HEAD and
its registered meta (pre-registration + sha256, periods, parameters, costs, tests) equals this run's. Data: Binance SPOT 5m
before 2020-01-01 (BTC, ETH), USDT-M PERP 5m from 2020-01-01 (SOL perp starts 2020-09-14), concatenated per symbol and
de-duplicated by bar time; realized funding from data/history/binance_um/funding.{SYM}.json.gz; one edge_census.Series with
zone = UTC, so the "server day" is the UTC day 00:00 -> 24:00.

Rules (pre-registration §1; MOM_DAYS and VB_K are F3's and F4's own constants, not re-chosen):
* H7x: the first 5m bar of UTC day D whose close is above the previous complete UTC day's high (below its low) when MOM20 > 0
  (< 0); MOM20 = close of D-1's last bar / close of the last bar of the 21st previous complete UTC day - 1. Continuation.
* G9x: the first 5m close beyond open(D) +/- 0.5 x the previous complete UTC day's range; either side; continuation.
* Entry: the OPEN of the next bar. Exit: the OPEN of the 23:55 bar, or of the last available bar of D when bars are missing
  after the signal (counted as exit_not_2355 and warned about). An entry bar opening at or after 23:55 is not an event. One
  event per (symbol, day, rule): the first.
* Point-in-time completeness: D is eligible iff D-1 is COMPLETE (exactly 288 distinct on-grid 5m bars: second 0, minute % 5
  == 0) and at least 21 complete days precede D (MOM20 lookback; sigma uses the previous 20). D's OWN completeness is never
  consulted -- which is why F3's ev_breakout_trend and F4's ev_vol_breakout are NOT reused: both key their momentum / previous
  day on edge_census "dense" days (>= 80 % of the median day, a same-day completeness selection for D itself in F3's research
  mode) and F4 drops a signal on the day's last bar. The venue-switch day 2020-01-01 (D-1 spot, D perp) is not eligible;
  MOM20 / sigma of 2020-01-02 .. ~2020-01-22 still span both venues (disclosed in meta, counted as venue_mixed_lookback_days).

Measurement (§3): r = side x (O(exit) / O(entry) - 1); cost 12 bp round trip (taker 5 bp + slippage 1 bp per side), stress
14 bp (2 x slippage), PLUS realized funding on perp-era trades: side x rate_tau (a fraction of entry notional; longs pay a
positive rate) for every settlement entry_time <= tau < exit_time (00/08/16 UTC, every 2 h on some SOL days; the next day's
00:00 is never reached). placebo = mean O(exit)/O(slot)-1 over every eligible day of the same symbol, period, entry 5m slot,
weekday and MOM20 sign, signed by side (a leave-own-day-out version is reported alongside, report-only); scale = sigma_5m x
sqrt(bars held), sigma = RMS of 5m log returns over the previous 20 complete UTC days. Tests T1 = H7x pooled over the symbols,
T2 = G9x pooled (edge_census.summarise, CR1 by UTC date), BH m = 2, q = 0.10 on the DISCOVERY one-sided p. Per-symbol rows
are report-only. Diagnostics (§5, outside the family): owner sizing (stop at the opposite prior-day boundary, 1 % risk, funding
to the stop / exit), the MOM20-only comparator (with its own slot-matched funding), the daily correlation with fvg-book v3
(scripts/research/book_sim.py H7_XAUUSD_eod + G9_XAUUSD_eod), raw net returns per symbol and year; trade-level rows are
persisted in the read JSON."""
import argparse
import bisect
import collections
import datetime
import gzip
import hashlib
import importlib.util
import json
import math
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


F4 = _load("edge_f4", "scripts/research/edge_f4.py")
F3 = F4.F3
EC = F3.EC                                   # edge_census: Series, cr1, t_sf, bh, summarise (it puts scripts/ on sys.path)
import history_store as HS  # noqa: E402
import instruments as I  # noqa: E402
import real_costs as RC  # noqa: E402

PREREG = "docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md"
PREREG_AMENDMENT = "[H7x-A1]"                # the committed pre-registration must carry this amendment tag before a read
SCRIPT = "scripts/research/edge_h7x.py"
TESTS_FILE = "scripts/tests/test_edge_h7x.py"
CANONICAL_OUT = "docs/audits/2026-10-03-edge-h7x-{read}.json"
COMMITTED = (SCRIPT, TESTS_FILE, PREREG, "scripts/research/edge_census.py", "scripts/research/edge_f3.py",
             "scripts/research/edge_f4.py", "scripts/research/book_sim.py", "scripts/research/fvg_book_sim.py",
             "scripts/instruments.py", "scripts/history_store.py", "scripts/real_costs.py", "scripts/mt5_time.py",
             "docs/architecture/instruments.json", "docs/architecture/providers.json")
UTC = datetime.timezone.utc
SPOT_ROOT = os.path.join(ROOT, "data", "history", "binance_spot")
PERP_ROOT = os.path.join(ROOT, "data", "history", "binance_um")
PERP_FROM = "2020-01-01T00:00:00Z"           # spot strictly before, perp from here (pre-registration §2)
SWITCH_DAY = datetime.date.fromisoformat(PERP_FROM[:10])   # D-1 spot, D perp: not eligible (amendment [H7x-A1])
END = "9999-12-31T00:00:00Z"
BAR = datetime.timedelta(minutes=5)
BARS_PER_DAY = 288                           # a UTC day is complete iff it has all 288 on-grid 5m bars
EXIT_SLOT = BARS_PER_DAY - 1                 # the 23:55 bar
MOM_DAYS = F3.MOM_DAYS                       # 20 -- gold's H7 lookback, kept literal
VOL_DAYS = 20                                # sigma: previous 20 complete UTC days (§3)
VB_K = F4.VB_K                               # 0.5 -- gold's G9 multiplier, kept literal
RULES = ("H7x", "G9x")
TESTS = (("T1", "H7x"), ("T2", "G9x"))       # BH m = 2
READS = ("discovery", "confirmation", "exposed")
VERDICT_KEY = {"discovery": "candidate", "confirmation": "confirmed", "exposed": "survives"}
PERIODS = {"discovery": ("2017-08-17", "2021-07-18"), "confirmation": ("2021-07-19", "2024-02-29"),
           "exposed": ("2024-03-01", "2026-09-30")}
TAKER_FEE, SLIPPAGE = 0.0005, 0.0001         # per side
COST_RT = 2 * (TAKER_FEE + SLIPPAGE)         # 12 bp round trip
COST_STRESS = 2 * (TAKER_FEE + 2 * SLIPPAGE)  # 14 bp: 2 x slippage
DEFAULT_FUNDING_HOURS = 8                    # a settlement row without interval_hours (Binance's standard interval)
FUNDING_RULE = ("realized (amendment [H7x-A1]): a perp-era trade (entry >= 2020-01-01T00:00Z) pays side x rate_tau, a "
                "fraction of ENTRY notional (longs pay a positive rate), for every settlement tau in "
                "data/history/binance_um/funding.{SYM}.json.gz with entry_time <= tau < exit_time, at whatever interval the "
                "file gives; owner sizing charges the settlements before its stop fill; spot era (< 2020-01-01): none")
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
OWNER_RISK, GAP_THROUGH_R = 0.01, -1.05
BOOK_V3 = ("H7_XAUUSD_eod", "G9_XAUUSD_eod")
META_FIXED = ("preregistration", "preregistration_sha256", "preregistration_amendment", "symbols", "periods", "rules",
              "tests", "parameters", "costs", "bh", "confirm_p", "exposed_p")
ROW_FIELDS = ("symbol", "rule", "date", "side", "slot", "weekday", "mom_sign", "entry_time", "exit_time", "nb", "r",
              "placebo", "excess", "placebo_loo", "excess_loo", "scale", "funding", "funding_stamps", "cost", "cost90",
              "comparator_r", "comparator_funding")


def symbols():
    return I.backtested("crypto")


def day_period(d):
    """The read a UTC date belongs to, or None outside the three periods.
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    s = d.isoformat()
    for p, (lo, hi) in PERIODS.items():
        if lo <= s <= hi:
            return p
    return None


def venue(d):
    return "spot" if d < SWITCH_DAY else "perp"


def slot(s, i):
    return (s.dt[i].hour * 60 + s.dt[i].minute) // 5


def _on_grid(t):
    return t.second == 0 and t.microsecond == 0 and t.minute % 5 == 0


def _is_2355(s, x):
    return _on_grid(s.dt[x]) and slot(s, x) == EXIT_SLOT


def _utc(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------------------------------------ data
def merge_candles(spot, perp):
    """(candles, duplicates dropped): spot bars strictly before PERP_FROM, perp bars from it, sorted and de-duplicated by
    time (the first occurrence is kept).
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    rows = [c for c in (spot or []) if c["time"] < PERP_FROM] + [c for c in perp if c["time"] >= PERP_FROM]
    rows.sort(key=lambda c: c["time"])
    out, dup = [], 0
    for c in rows:
        if out and out[-1]["time"] == c["time"]:
            dup += 1
            continue
        out.append({k: c[k] for k in ("time", "open", "high", "low", "close")})
    return out, dup


def load_candles(sym, spot_root=SPOT_ROOT, perp_root=PERP_ROOT):
    """(candles, provenance) for `sym`: spot 5m (if any) + perp 5m, merged by merge_candles. Data only, no outcome.
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    spot, sp = HS.read_doc(sym, "5m", root=spot_root)
    perp, pp = HS.read_doc(sym, "5m", root=perp_root)
    if perp is None:
        raise SystemExit(f"no perp 5m history for {sym} under {perp_root}")
    candles, dup = merge_candles(spot["candles"] if spot else None, perp["candles"])
    prov = {"duplicates_dropped": dup, "bars": len(candles),
            "first": candles[0]["time"] if candles else None, "last": candles[-1]["time"] if candles else None}
    for name, doc, path, root in (("spot", spot, sp, spot_root), ("perp", perp, pp, perp_root)):
        if doc is None:
            prov[name] = None
            continue
        used = [c for c in doc["candles"] if (c["time"] < PERP_FROM) == (name == "spot")]
        prov[name] = {"path": os.path.relpath(path, ROOT), "source": doc.get("_source"), "venue": doc.get("_venue"),
                      "sha256": HS.digest(sym, "5m", root=root), "bars_used": len(used),
                      "first_used": used[0]["time"] if used else None, "last_used": used[-1]["time"] if used else None}
    return candles, prov


class Funding:
    """Realized funding settlements of one perp, sorted by time and de-duplicated: t (aware UTC), rate (charged on the
    position notional at t; longs pay a positive rate), iv (interval hours). A window [a, b) is COVERED iff the first
    settlement <= a, b <= the last settlement + its interval, and no gap (consecutive settlements further apart than both
    their intervals) overlaps it -- an uncovered perp-era trade is never silently charged zero.
    [prereg §1, §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""

    def __init__(self, stamps):
        self.t, self.rate, self.iv, self.duplicates = [], [], [], 0
        for t, rate, iv in sorted(stamps, key=lambda x: x[0]):
            if self.t and self.t[-1] == t:
                self.duplicates += 1
                continue
            self.t.append(t)
            self.rate.append(float(rate))
            self.iv.append(iv or DEFAULT_FUNDING_HOURS)
        hours = datetime.timedelta(hours=1)
        self.gaps = [(self.t[k - 1], self.t[k]) for k in range(1, len(self.t))
                     if self.t[k] - self.t[k - 1] > max(self.iv[k - 1], self.iv[k]) * hours]
        self.hi = self.t[-1] + self.iv[-1] * hours if self.t else None

    def window(self, a, b):
        """Indices of the settlements a <= tau < b.
        [prereg §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
        return range(bisect.bisect_left(self.t, a), bisect.bisect_left(self.t, b))

    def covers(self, a, b):
        if not self.t or a < self.t[0] or b > self.hi:
            return False
        return not any(a < g1 and b > g0 for g0, g1 in self.gaps)


def load_funding(sym, root=PERP_ROOT):
    """(Funding, provenance) from `root`/funding.{sym}.json.gz ({rows: [{time, interval_hours, rate}]} or a bare list).
    A missing file is an EMPTY table (every perp-era window uncovered: a read refuses). Provenance has no rate.
    [prereg §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    path = os.path.join(root, f"funding.{sym}.json.gz")
    if not os.path.exists(path):
        return Funding([]), {"path": os.path.relpath(path, ROOT), "sha256": None, "rows": 0}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    rows = doc["rows"] if isinstance(doc, dict) else doc
    f = Funding([(_utc(r["time"]), r["rate"], r.get("interval_hours")) for r in rows])
    meta = doc if isinstance(doc, dict) else {}
    return f, {"path": os.path.relpath(path, ROOT), "sha256": _sha256(path), "source": meta.get("_source"),
               "meaning": meta.get("_meaning"), "fetched_at_utc": meta.get("_fetched_at_utc"), "rows": len(rows),
               "duplicates_dropped": f.duplicates, "gaps": len(f.gaps),
               "first": f.t[0].isoformat() if f.t else None, "last": f.t[-1].isoformat() if f.t else None,
               "interval_hours": dict(collections.Counter(str(h) for h in f.iv))}


def series(sym, candles):
    return EC.Series(sym, candles, UTC, end=END)


# ------------------------------------------------------------------------------------------------ point-in-time day context
def _complete_days(s):
    """{complete UTC day: (high, low, last close, mean squared within-day 5m log return)}. Complete = exactly 288 bars, all
    on the 5m grid (second 0, minute % 5 == 0), 288 distinct slots: a shifted or duplicated bar never passes.
    [prereg §1, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    out = {}
    for d, rows in s.day_rows.items():
        if len(rows) != BARS_PER_DAY or not all(_on_grid(s.dt[j]) for j in rows):
            continue
        if len({slot(s, j) for j in rows}) != BARS_PER_DAY:
            continue
        rs = [math.log(s.C[j] / s.C[j - 1]) for j in rows[1:] if s.C[j - 1] > 0 and s.C[j] > 0]
        out[d] = (max(s.H[j] for j in rows), min(s.L[j] for j in rows), s.C[rows[-1]],
                  sum(r * r for r in rs) / len(rs) if rs else 0.0)
    return out


def _context(s):
    """(ctx, excluded): ctx = {UTC day D: inputs known at D's first bar} for every ELIGIBLE day: D-1 complete and >= MOM_DAYS
    + 1 complete days before D, D not the venue-switch day; excluded = {D: reason} for days that pass the lookback but are
    the venue-switch day (D-1 spot, D perp: a prev high / low on another venue). D's own bars are never counted -- only D's
    first bar's open (G9x's open(D)) is read.
    [prereg §1, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    info = _complete_days(s)
    complete = sorted(info)
    out, excluded = {}, {}
    for d, rows in s.day_rows.items():
        y = d - datetime.timedelta(days=1)
        if y not in info:
            continue                                         # D-1 incomplete or absent
        k = bisect.bisect_left(complete, d)                  # complete days strictly before D; complete[k-1] == y
        if k < MOM_DAYS + 1:
            continue                                         # MOM20 lookback incomplete
        if d == SWITCH_DAY:
            excluded[d] = "venue_switch_day"
            continue
        anchor = complete[k - 1 - MOM_DAYS]
        mom = info[complete[k - 1]][2] / info[anchor][2] - 1.0
        sig = math.sqrt(sum(info[x][3] for x in complete[k - VOL_DAYS:k]) / VOL_DAYS)
        hi, lo = info[y][0], info[y][1]
        out[d] = {"prev_high": hi, "prev_low": lo, "prev_range": hi - lo, "mom": mom, "mom_sign": (mom > 0) - (mom < 0),
                  "sigma": sig, "open": s.O[rows[0]], "weekday": d.weekday(), "lookback_from": anchor}
    return out, excluded


def day_context(s):
    return _context(s)[0]


# ------------------------------------------------------------------------------------------------ detection
def _entry(s, i, d):
    """Entry bar for a signal at the close of bar i of day d: the next available bar, if it is in d and opens before 23:55.
    [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    e = i + 1
    if e >= len(s.C) or s.sday[e] != d or slot(s, e) >= EXIT_SLOT:
        return None
    return e


def _event(s, rule, d, i, side, e, c):
    return {"rule": rule, "day": d, "i": i, "side": side, "entry_i": e, "entry_px": None, "slot": slot(s, e),
            "weekday": c["weekday"], "mom_sign": c["mom_sign"], "prev_high": c["prev_high"], "prev_low": c["prev_low"]}


def _first(s, rule, d, c, test):
    """The day's event from its FIRST qualifying close (a later close would enter even later), or None.
    [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    for i in s.day_rows[d]:
        side = test(s.C[i])
        if side:
            e = _entry(s, i, d)
            return _event(s, rule, d, i, side, e, c) if e is not None else None
    return None


def ev_h7x(s, ctx=None):
    ctx = day_context(s) if ctx is None else ctx
    out = []
    for d in s.day_rows:
        c = ctx.get(d)
        if c is None or not c["mom_sign"]:
            continue
        if c["mom_sign"] > 0:
            ev = _first(s, "H7x", d, c, lambda x, h=c["prev_high"]: 1 if x > h else 0)
        else:
            ev = _first(s, "H7x", d, c, lambda x, l=c["prev_low"]: -1 if x < l else 0)
        if ev:
            out.append(ev)
    return out


def ev_g9x(s, ctx=None):
    ctx = day_context(s) if ctx is None else ctx
    out = []
    for d in s.day_rows:
        c = ctx.get(d)
        if c is None:
            continue
        hi, lo = c["open"] + VB_K * c["prev_range"], c["open"] - VB_K * c["prev_range"]
        ev = _first(s, "G9x", d, c, lambda x: 1 if x > hi else (-1 if x < lo else 0))
        if ev:
            out.append(ev)
    return out


DETECTORS = {"H7x": ev_h7x, "G9x": ev_g9x}


def events(s, ctx=None):
    ctx = day_context(s) if ctx is None else ctx
    return {rule: det(s, ctx) for rule, det in DETECTORS.items()}


def exit_index(s, ev):
    """The exit bar (its OPEN is the exit price): the day's last available bar -- the 23:55 bar, or the last one before it
    when bars are missing after the signal. None when the entry bar is itself the day's last available bar.
    [prereg §1: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    x = s.day_rows[ev["day"]][-1]
    return x if x > ev["entry_i"] else None


def funding_paid(s, side, e, end, funding):
    """(paid, settlements) for a position of `side` opened at the OPEN of bar e and closed at instant `end`: side x the sum of
    the rates of every settlement s.dt[e] <= tau < end (a fraction of entry notional; > 0 = a cost). Spot era (entry before
    PERP_FROM): (0.0, 0). Perp era without a covering funding table: (None, None).
    [prereg §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    if s.T[e] < PERP_FROM:
        return 0.0, 0
    if funding is None or not funding.covers(s.dt[e], end):
        return None, None
    ks = funding.window(s.dt[e], end)
    return side * sum(funding.rate[k] for k in ks), len(ks)


# ------------------------------------------------------------------------------------------------ outcomes (a read only)
def outcome(s, ev, sigma, funding=None):
    """(row, None) or (None, reason). cost = 12 bp + realized funding over [entry, exit); cost90 = 14 bp + the same funding.
    [prereg §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    x = exit_index(s, ev)
    if x is None:
        return None, "no_exit_bar"
    if not sigma:
        return None, "no_vol_history"
    e = ev["entry_i"]
    fund, n_f = funding_paid(s, ev["side"], e, s.dt[x], funding)
    if fund is None:
        return None, "no_funding_coverage"
    nb = (s.dt[x] - s.dt[e]) // BAR                       # 5m bars held, clock time
    return {"symbol": s.sym, "rule": ev["rule"], "date": ev["day"].isoformat(), "year": ev["day"].year,
            "side": ev["side"], "slot": ev["slot"], "weekday": ev["weekday"], "mom_sign": ev["mom_sign"],
            "r": ev["side"] * (s.O[x] / s.O[e] - 1.0), "funding": fund, "funding_stamps": n_f,
            "cost": COST_RT + fund, "cost90": COST_STRESS + fund,
            "scale": sigma * math.sqrt(nb), "nb": nb, "entry_i": e, "exit_i": x,
            "entry_time": s.T[e], "exit_time": s.T[x]}, None


def placebo_tables(s, ctx, read, funding=None):
    """(placebo, comparator, aux) over every eligible day of `read` for this symbol:
    placebo    {(slot, weekday, MOM20 sign): mean O(exit)/O(slot) - 1}  (unsigned; signed by the trade's side later)
    comparator {slot: mean MOM20-sign x (O(exit)/O(slot) - 1)} over days with MOM20 != 0 (the H1-crypto comparator)
    aux        {"cells": {placebo key: (sum, n)} (for the leave-own-day-out placebo), "comparator_funding": {slot: mean
               MOM20-sign x funding over [slot, exit)}, "comparator_days_without_funding": n}. The comparator uses only days
               whose funding is known (spot era, or a covering table), for its return and its funding alike.
    [prereg §3, 5, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    plc = collections.defaultdict(lambda: [0.0, 0])
    cmp_ = collections.defaultdict(lambda: [0.0, 0])
    cmpf = collections.defaultdict(lambda: [0.0, 0])
    unfunded = 0
    for d, c in ctx.items():
        if day_period(d) != read:
            continue
        rows = s.day_rows[d]
        x = rows[-1]
        sign = c["mom_sign"]
        taus, suffix, known = [], [0.0], True
        if sign and s.T[rows[0]] >= PERP_FROM:
            if funding is None or not funding.covers(s.dt[rows[0]], s.dt[x]):
                known = False
                unfunded += 1
            else:
                ks = funding.window(s.dt[rows[0]], s.dt[x])
                taus = [funding.t[k] for k in ks]
                suffix = [0.0] * (len(taus) + 1)
                for q in range(len(taus) - 1, -1, -1):
                    suffix[q] = suffix[q + 1] + funding.rate[ks[q]]
        for j in rows:
            if j >= x:
                break
            r = s.O[x] / s.O[j] - 1.0
            sl = slot(s, j)
            a = plc[(sl, c["weekday"], sign)]
            a[0] += r
            a[1] += 1
            if sign and known:
                b = cmp_[sl]
                b[0] += sign * r
                b[1] += 1
                f = cmpf[sl]
                f[0] += sign * suffix[bisect.bisect_left(taus, s.dt[j])]
                f[1] += 1
    return ({k: v[0] / v[1] for k, v in plc.items()}, {k: v[0] / v[1] for k, v in cmp_.items()},
            {"cells": {k: (v[0], v[1]) for k, v in plc.items()}, "comparator_funding": {k: v[0] / v[1] for k, v in cmpf.items()},
             "comparator_days_without_funding": unfunded})


def owner_trade(s, ev, x, cost=COST_RT, funding=None):
    """Owner sizing (§5): stop at the opposite prior-day boundary (previous low for a long, high for a short), sized so the
    loss at the stop is OWNER_RISK of equity. {"R", "stop", "stop_bp", "funding"}, or None when the entry is already beyond
    the stop. The stop is checked on the bars HELD (entry bar .. the bar before the exit bar). Funding: the settlements
    before the fill -- a gap through fills at the bar's open (a settlement AT that open is not paid), a touch inside the bar
    fills after its open (a settlement at the open is paid); a time exit pays [entry, exit).
    [prereg §5, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    e, side = ev["entry_i"], ev["side"]
    px = s.O[e]
    stop = ev["prev_low"] if side > 0 else ev["prev_high"]
    dist = side * (px - stop)
    if dist <= 0:
        return None
    exit_px, hit, end = s.O[x], False, s.dt[x]
    for j in range(e, x):                                   # the bars held: entry at O[e], exit at O[x]
        if (s.L[j] <= stop) if side > 0 else (s.H[j] >= stop):
            gap = (s.O[j] <= stop) if side > 0 else (s.O[j] >= stop)
            exit_px, end = (s.O[j], s.dt[j]) if gap else (stop, s.dt[j] + BAR)   # a gap through fills at the open
            hit = True
            break
    fund, _ = funding_paid(s, side, e, end, funding)
    if fund is None:
        raise ValueError(f"{s.sym} {ev['day']}: a perp-era owner trade needs a covering funding table")
    return {"R": (side * (exit_px - px) - (cost + fund) * px) / dist, "stop": hit, "stop_bp": dist / px * 1e4,
            "funding": fund}


def symbol_rows(s, read, ctx=None, funding=None):
    """({rule: [outcome rows]}, skipped Counter) for ONE symbol and ONE read: only events whose UTC day is in `read`.
    Counter keys "<rule>|<reason>" are skipped events; "<rule>|flag:exit_not_2355" counts KEPT trades whose exit is not the
    23:55 bar (bars missing at the end of the day).
    [prereg §3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    ctx = day_context(s) if ctx is None else ctx
    plc, comp, aux = placebo_tables(s, ctx, read, funding)
    rows, skipped = {r: [] for r in RULES}, collections.Counter()
    for rule, evs in events(s, ctx).items():
        for ev in evs:
            if day_period(ev["day"]) != read:
                continue                                    # this read touches its own period only
            o, why = outcome(s, ev, ctx[ev["day"]]["sigma"], funding)
            if o is None:
                skipped[f"{rule}|{why}"] += 1
                continue
            if not _is_2355(s, o["exit_i"]):
                skipped[f"{rule}|flag:exit_not_2355"] += 1
            key = (o["slot"], o["weekday"], o["mom_sign"])
            o["placebo"] = plc[key]                          # never empty: the event's own day is in it
            o["excess"] = o["r"] - o["side"] * o["placebo"]
            tot, n = aux["cells"][key]
            own = s.O[o["exit_i"]] / s.O[o["entry_i"]] - 1.0  # exactly the event day's own term in that cell
            o["placebo_loo"] = (tot - own) / (n - 1) if n > 1 else None
            o["excess_loo"] = o["r"] - o["side"] * o["placebo_loo"] if n > 1 else None
            o["comparator_r"] = comp.get(o["slot"]) if rule == "H7x" else None
            o["comparator_funding"] = aux["comparator_funding"].get(o["slot"]) if rule == "H7x" else None
            o["owner"] = owner_trade(s, ev, o["exit_i"], COST_RT, funding)
            rows[rule].append(o)
    return rows, skipped


# ------------------------------------------------------------------------------------------------ statistics
def summarise(rows):
    """edge_census.summarise in the FIXED continuation direction (+1, one-sided); its p90 cost line is the 2x-slippage
    stress here, renamed. Costs include realized funding (cost_bp); funding_bp is its mean share.
    [prereg §3: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    out = EC.summarise(rows, +1)
    if rows:
        out["net_bp_2x_slippage"] = out.pop("net_bp_p90")
        out["placebo_signed_bp"] = sum(r["side"] * r["placebo"] for r in rows) / len(rows) * 1e4
        out["funding_bp"] = sum(r["funding"] for r in rows) / len(rows) * 1e4
    return out


def loo_summary(rows):
    """Report-only (outside the family): the excess z against the LEAVE-OWN-DAY-OUT placebo (the registered placebo includes
    the event's own day, which pulls excess toward 0 by about 1 / cell size). Rows whose cell has a single day are dropped.
    [prereg §3: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    rs = [dict(r, excess=r["excess_loo"]) for r in rows if r.get("excess_loo") is not None]
    out = EC.summarise(rs, +1)
    return {"n": out["n"], "excess_z_loo": out.get("excess_z"), "t_excess_loo": out.get("t_excess"),
            "p_one_sided_loo": out.get("p_one_sided"), "dropped_single_day_cell": len(rows) - len(rs), "report_only": True}


def owner_summary(rows):
    sized = [(r, r["owner"]) for r in rows if r.get("owner")]
    out = {"risk_pct": OWNER_RISK, "n": len(sized), "unsizable_entry_beyond_stop": len(rows) - len(sized),
           "report_only": True}
    if not sized:
        return out
    Rs = sorted(o["R"] for _, o in sized)
    worst_r, worst = min(sized, key=lambda t: t[1]["R"])
    n = len(Rs)
    out.update({"mean_R": sum(Rs) / n, "median_R": Rs[n // 2] if n % 2 else 0.5 * (Rs[n // 2 - 1] + Rs[n // 2]),
                "sum_R": sum(Rs), "stop_share": sum(1 for _, o in sized if o["stop"]) / n,
                "gap_through_n": sum(1 for x in Rs if x < GAP_THROUGH_R),
                "gap_through_share": sum(1 for x in Rs if x < GAP_THROUGH_R) / n,
                "mean_stop_bp": sum(o["stop_bp"] for _, o in sized) / n,
                "worst": {"symbol": worst_r["symbol"], "date": worst_r["date"], "side": worst_r["side"], "R": worst["R"]}})
    return out


def comparator_summary(rows):
    """H1-crypto comparator (§5): the MOM20 sign alone, traded from each H7x trade's slot to 23:55 on every eligible day of
    the period (slot-matched), with its own slot-matched realized funding. H7x must beat it: paired difference r - comparator
    (gross; and net of fees + each side's funding), CR1 by UTC date, one-sided. Report-only.
    [prereg §5, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    rs = [r for r in rows if r.get("comparator_r") is not None]
    if not rs:
        return {"n": 0, "report_only": True}
    dates = [r["date"] for r in rs]
    out = {"n": len(rs), "report_only": True}
    for name, diff in (("", [(r["r"] - r["comparator_r"]) * 1e4 for r in rs]),
                       ("_net", [((r["r"] - r["cost"]) - (r["comparator_r"] - COST_RT - r["comparator_funding"])) * 1e4
                                 for r in rs])):
        mu, se, df = EC.cr1(diff, dates)
        t = mu / se if se else None
        out.update({f"h7x_minus_comparator{name}_bp": mu, f"t{name}": t,
                    f"p_one_sided{name}": EC.t_sf(t, df) if t is not None else 1.0})
    comp = sum(r["comparator_r"] for r in rs) / len(rs) * 1e4
    cfund = sum(r["comparator_funding"] for r in rs) / len(rs) * 1e4
    out.update({"comparator_gross_bp": comp, "comparator_funding_bp": cfund,
                "comparator_net_bp": comp - COST_RT * 1e4 - cfund,
                "h7x_funding_bp": sum(r["funding"] for r in rs) / len(rs) * 1e4,
                "h7x_net_bp": sum((r["r"] - r["cost"]) for r in rs) / len(rs) * 1e4})
    return out


def by_symbol_year(rows):
    acc = collections.defaultdict(list)
    for r in rows:
        acc[(r["symbol"], r["year"])].append(r)
    out = collections.defaultdict(dict)
    for (sym, y), rs in sorted(acc.items()):
        out[sym][str(y)] = {"n": len(rs), "gross_bp": sum(r["r"] for r in rs) / len(rs) * 1e4,
                            "funding_bp": sum(r["funding"] for r in rs) / len(rs) * 1e4,
                            "net_bp": sum(r["r"] - r["cost"] for r in rs) / len(rs) * 1e4}
    return dict(out)


def server_day_ending(d):
    """The FTMO server-day label of the server day that ENDS on UTC day d (17:00 New York = 21:00 / 22:00 UTC on d): the
    server date of d 20:55 UTC, an instant inside that server day in both DST states.
    [prereg §5: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    t = datetime.datetime(d.year, d.month, d.day, 20, 55, tzinfo=UTC)
    return t.astimezone(RC.server_zone(EC.PROVIDER)[1]).date().isoformat()


def corr_with_book(rows, book_daily, corr, read):
    """Daily P&L correlation with fvg-book v3 on the read's dates: crypto owner-sized R summed per UTC day -> the FTMO server
    day ending that day; the book's daily R restricted to the same date range; days without trades are 0.
    [prereg §5: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    lo, hi = PERIODS[read]
    daily = collections.defaultdict(float)
    for r in rows:
        if r.get("owner"):
            daily[server_day_ending(datetime.date.fromisoformat(r["date"]))] += r["owner"]["R"]
    book = {d: v for d, v in book_daily.items() if lo <= d <= hi}
    return {"corr_daily_R": corr(dict(daily), book) if daily else None, "crypto_days": len(daily), "book_days": len(book),
            "report_only": True}


def verdicts(read, tests, prior=None):
    """Sets t["verdict"] on every test (pre-registration §4). Discovery: BH (m = len(tests), q = FDR_Q) on the one-sided p;
    CANDIDATE iff rejected and mean net > 0. Confirmation: a candidate with p < 0.05, net > 0 and net > 0 at 2x slippage.
    Exposed: a confirmed test with p < 0.10 and net > 0. Net is after fees, slippage AND realized funding.
    [prereg §4: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    if read == "discovery":
        rej = EC.bh([t[read].get("p_one_sided", 1.0) if t[read].get("n") else 1.0 for t in tests], FDR_Q)
        for k, t in enumerate(tests):
            d = t[read]
            t["verdict"] = {"bh_rejected": k in rej, "candidate": bool(k in rej and d.get("n") and d["net_bp"] > 0)}
        return tests
    before = {x["test"]: x["verdict"] for x in prior["tests"]}
    for t in tests:
        prev, d = before[t["test"]], t[read]
        if read == "confirmation":
            ok = (prev.get("candidate") and d.get("n") and d["p_one_sided"] < CONFIRM_P and d["net_bp"] > 0
                  and d["net_bp_2x_slippage"] > 0)
            t["verdict"] = dict(prev, confirmed=bool(ok))
        else:
            ok = prev.get("confirmed") and d.get("n") and d["p_one_sided"] < EXPOSED_P and d["net_bp"] > 0
            t["verdict"] = dict(prev, survives=bool(ok))
    return tests


def result_label(read, tests):
    """'not found at this power' when no test passes this read's gate (pre-registration §4), else the passing tests.
    [prereg §4: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    key = VERDICT_KEY[read]
    hit = [t["test"] for t in tests if t["verdict"].get(key)]
    return f"{key}: {', '.join(hit)}" if hit else "not found at this power"


# ------------------------------------------------------------------------------------------------ registration guard
def _git(*args):
    """(returncode, stdout) of `git -C ROOT <args>`; (None, "") when git cannot run (the guard then refuses).
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    try:
        p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _git_head():
    rc, out = _git("rev-parse", "HEAD")
    return out.strip() or None if rc == 0 else None


def _prereg_text():
    with open(os.path.join(ROOT, PREREG), encoding="utf-8") as fh:
        return fh.read()


def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT)


def _require_committed(paths):
    """None when every path is tracked by git and has no uncommitted change; SystemExit otherwise.
    [prereg header + §2 (committed BEFORE any read): docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    bad = []
    for p in paths:
        if p.startswith(".."):
            bad.append(f"{p}: outside the repository")
            continue
        if _git("ls-files", "--error-unmatch", "--", p)[0] != 0:
            bad.append(f"{p}: not tracked")
            continue
        rc, out = _git("status", "--porcelain", "--", p)
        if rc != 0 or out.strip():
            bad.append(f"{p}: uncommitted changes")
    if bad:
        raise SystemExit("refusing: a read must run from committed code, tests and pre-registration (pre-registration §2): "
                         + "; ".join(bad))


def _require_registration(read, out_path):
    """Before any data is touched: the canonical --out path without git history, the amendment tag in the pre-registration,
    and every file in COMMITTED tracked and clean. Returns the meta fields it vouches for.
    [prereg §2, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    want = CANONICAL_OUT.format(read=read)
    if os.path.abspath(out_path) != os.path.join(ROOT, want):
        raise SystemExit(f"refusing: --read {read} writes {want} (got {out_path})")
    rc, log = _git("log", "--all", "--format=%H", "--", want)
    if rc != 0:
        raise SystemExit(f"refusing: cannot check the git history of {want}")
    if log.strip():
        raise SystemExit(f"refusing: {want} has git history -- the {read} read was already run (pre-registration §2)")
    if PREREG_AMENDMENT not in _prereg_text():
        raise SystemExit(f"refusing: {PREREG} lacks amendment {PREREG_AMENDMENT} (realized funding, venue-switch day, "
                         "on-grid completeness); commit it, outcome-blind, before any read")
    _require_committed(COMMITTED)
    return {"committed_sha256": {p: _sha256(os.path.join(ROOT, p)) for p in COMMITTED}}


def _check_order(read, after, require_clean=True):
    """Refuses an out-of-order read BEFORE any data is touched. Under the guard the --after JSON must also be tracked and
    clean, written under the guard, at a git_head that is an ancestor of HEAD, with the same registered meta as this run.
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    if read not in READS:
        raise SystemExit(f"unknown read {read}")
    if read == "discovery":
        return None
    need = READS[READS.index(read) - 1]
    if not after:
        raise SystemExit(f"--read {read} needs --after <the {need} json>")
    with open(after, encoding="utf-8") as fh:
        prior = json.load(fh)
    m = prior.get("meta", {})
    if m.get("script") != SCRIPT or m.get("read") != need:
        raise SystemExit(f"--read {read} needs --after <the {need} json of {SCRIPT}>; got {m.get('script')} / {m.get('read')}")
    if require_clean:
        _require_committed([_rel(after)])
        if m.get("guarded") is not True:
            raise SystemExit(f"refusing: {after} was not written under the registration guard")
        head = m.get("git_head")
        if not head or _git("merge-base", "--is-ancestor", head, "HEAD")[0] != 0:
            raise SystemExit(f"refusing: {after} was written at {head}, not an ancestor of HEAD")
        cur = json.loads(json.dumps(_meta("read", read), default=str))
        diff = [k for k in META_FIXED if m.get(k) != cur.get(k)]
        if diff:
            raise SystemExit(f"refusing: {after} was run under a different registration ({', '.join(diff)} differ)")
    return prior


def _meta(kind, read=None):
    return {"script": SCRIPT, "script_sha256": _sha256(os.path.join(ROOT, SCRIPT)), "kind": kind, "read": read,
            "preregistration": PREREG, "preregistration_sha256": _sha256(os.path.join(ROOT, PREREG)),
            "preregistration_amendment": PREREG_AMENDMENT, "git_head": _git_head(),
            "symbols": symbols(), "periods": PERIODS, "rules": list(RULES), "tests": dict(TESTS),
            "parameters": {"mom_days": MOM_DAYS, "vol_days": VOL_DAYS, "vb_k": VB_K, "bars_per_day": BARS_PER_DAY,
                           "exit_slot_utc": "23:55", "complete_day": "exactly 288 distinct on-grid 5m bars",
                           "venue_switch_day_not_eligible": SWITCH_DAY.isoformat()},
            "costs": {"taker_fee_per_side": TAKER_FEE, "slippage_per_side": SLIPPAGE, "round_trip": COST_RT,
                      "stress_2x_slippage_round_trip": COST_STRESS, "funding": FUNDING_RULE},
            "bh": {"m": len(TESTS), "q": FDR_Q}, "confirm_p": CONFIRM_P, "exposed_p": EXPOSED_P,
            "disclosures": {
                "venue_mixed_lookback": "MOM20 and sigma of the first ~21 eligible perp days (2020-01-02 ..) divide perp "
                                        "closes by spot closes / mix spot and perp 5m returns (counted per period as "
                                        "venue_mixed_lookback_days)",
                "exit_not_2355": "bars missing at the end of D: exit at the day's last available open (counted, warned)",
                "funding_notional": "funding is charged on entry notional; the mark-price drift to tau is second order"}}


# ------------------------------------------------------------------------------------------------ outcome-blind counts
def _gaps(s):
    """{period: {"missing_5m_slots", "gap_runs", "longest_gap_min"}} between consecutive bars (attributed to the period of
    the first missing slot's UTC day).
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    out = collections.defaultdict(lambda: {"missing_5m_slots": 0, "gap_runs": 0, "longest_gap_min": 0})
    for j in range(1, len(s.dt)):
        miss = (s.dt[j] - s.dt[j - 1]) // BAR - 1
        if miss > 0:
            g = out[str(day_period((s.dt[j - 1] + BAR).date()))]
            g["missing_5m_slots"] += miss
            g["gap_runs"] += 1
            g["longest_gap_min"] = max(g["longest_gap_min"], miss * 5)
    return dict(out)


def period_flags(s, ctx, excluded, evs, funding, period):
    """OUTCOME-BLIND counts for one period, from bar TIMES and settlement TIMES only (no price, rate or return is read):
    events, events without an exit bar, kept events whose exit is not the 23:55 bar, eligible days whose last bar is not
    23:55 (placebo / comparator exits), venue-switch days excluded, eligible days whose lookback spans both venues, off-grid
    bars (all days / eligible days), and per rule the funding settlements a perp-era trade would cross ("0", "1", "2", "3+")
    or that its window is not covered by the funding table.
    [prereg §1-3, amendment [H7x-A1]: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    days = [d for d in s.day_rows if str(day_period(d)) == period]
    elig = [d for d in days if d in ctx]
    out = {"events": {}, "events_without_exit_bar": {}, "exit_not_2355": {}, "spot_era_events": {},
           "funding_stamps_crossed": {}, "funding_uncovered_events": {},
           "placebo_days_last_bar_not_2355": sum(1 for d in elig if not _is_2355(s, s.day_rows[d][-1])),
           "venue_switch_day": sum(1 for d in days if excluded.get(d) == "venue_switch_day"),
           "venue_mixed_lookback_days": sum(1 for d in elig if venue(ctx[d]["lookback_from"]) != venue(d)),
           "off_grid_bars": sum(1 for d in days for j in s.day_rows[d] if not _on_grid(s.dt[j])),
           "off_grid_bars_in_eligible_days": sum(1 for d in elig for j in s.day_rows[d] if not _on_grid(s.dt[j]))}
    for r in RULES:
        mine = [e for e in evs[r] if str(day_period(e["day"])) == period]
        hist, unc, spot, no_x, not55 = collections.Counter({"0": 0, "1": 0, "2": 0, "3+": 0}), 0, 0, 0, 0
        for e in mine:
            x = exit_index(s, e)
            if x is None:
                no_x += 1
                continue
            not55 += not _is_2355(s, x)
            if s.T[e["entry_i"]] < PERP_FROM:
                spot += 1
            elif funding is None or not funding.covers(s.dt[e["entry_i"]], s.dt[x]):
                unc += 1
            else:
                n = len(funding.window(s.dt[e["entry_i"]], s.dt[x]))
                hist[str(n) if n < 3 else "3+"] += 1
        out["events"][r], out["events_without_exit_bar"][r], out["exit_not_2355"][r] = len(mine), no_x, not55
        out["spot_era_events"][r], out["funding_uncovered_events"][r], out["funding_stamps_crossed"][r] = spot, unc, dict(hist)
    return out


def dry_counts(s, funding=None):
    """OUTCOME-BLIND counts for one series: per period, days with bars / complete / incomplete / eligible, gaps, and the
    period_flags counts (events per rule, exits, venue switch, off-grid bars, funding settlements crossed). No price, return,
    rate or P&L is read beyond the detectors' own decision inputs.
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    ctx, excluded = _context(s)
    evs = events(s, ctx)
    gaps = _gaps(s)
    complete = set(_complete_days(s))
    out = {"bars": len(s.C), "first": s.T[0] if s.T else None, "last": s.T[-1] if s.T else None, "periods": {}}
    for p in list(READS) + ["None"]:
        days = [d for d in s.day_rows if str(day_period(d)) == p]
        if not days and p == "None":
            continue
        absent = 0
        if days and p != "None":                              # calendar days inside the data's span with no bar at all
            lo = max(datetime.date.fromisoformat(PERIODS[p][0]), s.sday[0])
            hi = min(datetime.date.fromisoformat(PERIODS[p][1]), s.sday[-1])
            absent = (hi - lo).days + 1 - len(days)
        row = {"days_with_bars": len(days), "absent_days": absent,
               "complete_days": sum(1 for d in days if d in complete),
               "incomplete_days": sum(1 for d in days if d not in complete),
               "eligible_days": sum(1 for d in days if d in ctx),
               "first_day": days[0].isoformat() if days else None, "last_day": days[-1].isoformat() if days else None,
               "gaps": gaps.get(p, {"missing_5m_slots": 0, "gap_runs": 0, "longest_gap_min": 0})}
        row.update(period_flags(s, ctx, excluded, evs, funding, p))
        out["periods"][p] = row
    return out


# ------------------------------------------------------------------------------------------------ CLI
def _dump(res, path):
    """The read JSON with one trade row per line (res["rows"]), everything else indented.
    [prereg §2: docs/plans/2026-10-03-edge-h7x-crypto-preregistration.md]"""
    body = json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=str)
    if "rows" in res:
        assert body.endswith("\n}")
        parts = []
        for rule, rs in res["rows"].items():
            lines = ",\n".join("  " + json.dumps(r, default=str, separators=(",", ":")) for r in rs)
            parts.append(f" {json.dumps(rule)}: [\n{lines}\n ]" if rs else f" {json.dumps(rule)}: []")
        body = body[:-2] + ',\n "rows": {\n' + ",\n".join(parts) + "\n }\n}"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n")


def _row_out(x):
    return dict({k: x[k] for k in ROW_FIELDS}, owner=x["owner"])


def run(read, out_path, after=None, loader=load_candles, book=None, funding_loader=None, require_clean=True):
    prior = _check_order(read, after, require_clean)
    guard = _require_registration(read, out_path) if require_clean else {}
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: each read is run ONCE (pre-registration §2); refusing to overwrite")
    funding_loader = load_funding if funding_loader is None else funding_loader
    if book is None:
        BS = _load("book_sim", "scripts/research/book_sim.py")
        book = (BS.daily_r([t for c in BOOK_V3 for t in BS.trades(*BS.COMPONENTS[c])]), BS.corr)
    meta = dict(_meta("read", read), book_v3_components=list(BOOK_V3), guarded=require_clean, **guard)
    if prior is not None:
        pm = prior["meta"]
        meta["after"] = {"path": _rel(after), "sha256": _sha256(after), "git_head": pm.get("git_head"),
                         "script_sha256": pm.get("script_sha256"),
                         "script_changed_since": pm.get("script_sha256") != meta["script_sha256"]}
    res = {"meta": meta,
           "family": {"tests": [n for n, _ in TESTS], "bh_m": len(TESTS), "q": FDR_Q,
                      "note": "only tests[] is the registered family; per_symbol, diagnostics and rows are report-only"},
           "data": {}, "skipped": {}, "flags": {}, "tests": [], "per_symbol": {r: {} for r in RULES}, "diagnostics": {}}
    pooled = {r: [] for r in RULES}
    warnings = []
    for sym in symbols():
        candles, prov = loader(sym)
        fund, fprov = funding_loader(sym)
        s = series(sym, candles)
        ctx, excluded = _context(s)
        flags = period_flags(s, ctx, excluded, events(s, ctx), fund, read)     # outcome-blind preflight
        if flags["off_grid_bars_in_eligible_days"]:
            raise SystemExit(f"refusing: {sym} has {flags['off_grid_bars_in_eligible_days']} off-grid bars in eligible "
                             f"{read} days; fix the data first")
        if any(flags["funding_uncovered_events"].values()):
            raise SystemExit(f"refusing: {sym} {read} events without funding coverage {flags['funding_uncovered_events']}; "
                             "fix the funding history first")
        rows, skipped = symbol_rows(s, read, ctx, fund)
        res["data"][sym] = dict(prov, funding_source=fprov, eligible_days_in_read=sum(1 for d in ctx if day_period(d) == read))
        res["skipped"][sym] = dict(skipped)
        res["flags"][sym] = flags
        for k in ("exit_not_2355",):
            if any(flags[k].values()):
                warnings.append(f"{sym}: {k} {flags[k]}")
        if flags["placebo_days_last_bar_not_2355"]:
            warnings.append(f"{sym}: placebo_days_last_bar_not_2355 {flags['placebo_days_last_bar_not_2355']}")
        for r in RULES:
            pooled[r] += rows[r]
            res["per_symbol"][r][sym] = dict(summarise(rows[r]), loo_placebo=loo_summary(rows[r]), report_only=True)
        print(f"{sym}: {len(candles)} bars, {read} rows " + ", ".join(f"{r} {len(rows[r])}" for r in RULES), flush=True)
        del s, candles
    for name, rule in TESTS:
        res["tests"].append({"test": name, "rule": rule, "pooled_over": symbols(), read: summarise(pooled[rule])})
    verdicts(read, res["tests"], prior)
    res["result_label"] = result_label(read, res["tests"])
    for r in RULES:
        res["diagnostics"][r] = {"owner_sizing": owner_summary(pooled[r]),
                                 "owner_sizing_by_symbol": {sym: owner_summary([x for x in pooled[r] if x["symbol"] == sym])
                                                            for sym in symbols()},
                                 "corr_with_fvg_book_v3": corr_with_book(pooled[r], book[0], book[1], read),
                                 "raw_net_by_symbol_year": by_symbol_year(pooled[r]),
                                 "loo_placebo_pooled": loo_summary(pooled[r])}
    res["diagnostics"]["H7x"]["mom20_comparator"] = comparator_summary(pooled["H7x"])
    res["diagnostics"]["H7x"]["mom20_comparator_by_symbol"] = {
        sym: comparator_summary([x for x in pooled["H7x"] if x["symbol"] == sym]) for sym in symbols()}
    res["warnings"] = warnings
    res["rows"] = {r: [_row_out(x) for x in pooled[r]] for r in RULES}
    _dump(res, out_path)
    for w in warnings:
        print(f"WARNING {w}")
    nan = lambda v: float("nan") if v is None else v  # noqa: E731
    for t in res["tests"]:
        d = t[read]
        print(f"{t['test']} {t['rule']} pooled n {d.get('n', 0):5d} excess z {nan(d.get('excess_z')):+.4f} "
              f"p1 {nan(d.get('p_one_sided')):.4f} net {nan(d.get('net_bp')):+.2f} bp "
              f"net@2x {nan(d.get('net_bp_2x_slippage')):+.2f} bp | {t['verdict']}")
    print(f"result: {res['result_label']}")
    print(f"wrote {out_path}")
    return res


def dry_run(out_path, loader=load_candles, funding_loader=None):
    funding_loader = load_funding if funding_loader is None else funding_loader
    res = {"meta": dict(_meta("dry-run"), note="OUTCOME-BLIND: bar counts, spans, gaps, settlement and event counts only"),
           "symbols": {}, "pooled_events": {p: {r: 0 for r in RULES} for p in READS}}
    for sym in symbols():
        candles, prov = loader(sym)
        fund, fprov = funding_loader(sym)
        s = series(sym, candles)
        c = dry_counts(s, fund)
        c["data"] = dict(prov, funding_source=fprov)
        res["symbols"][sym] = c
        for p in READS:
            for r in RULES:
                res["pooled_events"][p][r] += c["periods"].get(p, {}).get("events", {}).get(r, 0)
        print(f"{sym}: {c['bars']} bars {c['first']} -> {c['last']}; funding rows {fprov.get('rows')} "
              f"{fprov.get('first')} -> {fprov.get('last')} gaps {fprov.get('gaps')}", flush=True)
        for p, row in c["periods"].items():
            print(f"  {p:12s} days {row['days_with_bars']:5d} (absent {row['absent_days']}) complete "
                  f"{row['complete_days']:5d} incomplete {row['incomplete_days']:3d} eligible {row['eligible_days']:5d} "
                  f"missing slots {row['gaps']['missing_5m_slots']:6d} ({row['gaps']['gap_runs']} gaps) off-grid "
                  f"{row['off_grid_bars']} (eligible {row['off_grid_bars_in_eligible_days']}) switch {row['venue_switch_day']} "
                  f"mixed-lookback {row['venue_mixed_lookback_days']}", flush=True)
            print("      events " + " ".join(f"{r} {row['events'][r]}" for r in RULES)
                  + " | no exit bar " + " ".join(f"{r} {row['events_without_exit_bar'][r]}" for r in RULES)
                  + " | exit not 23:55 " + " ".join(f"{r} {row['exit_not_2355'][r]}" for r in RULES)
                  + f" | placebo days last bar not 23:55 {row['placebo_days_last_bar_not_2355']}"
                  + " | settlements crossed " + " ".join(f"{r} {row['funding_stamps_crossed'][r]}" for r in RULES)
                  + " | uncovered " + " ".join(f"{r} {row['funding_uncovered_events'][r]}" for r in RULES), flush=True)
        del s, candles
    print("pooled events: " + json.dumps(res["pooled_events"]))
    with open(out_path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {out_path}")
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    r.add_argument("--after")
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.read, a.out, a.after)
    else:
        dry_run(a.out)


if __name__ == "__main__":
    main()
