#!/usr/bin/env python3
"""Edge family C1 (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md): a long/flat, volatility-targeted ensemble of
nine Donchian breakouts with ratcheting midpoint stops, per coin, on the crypto symbols the pilot backtested
(scripts/instruments.py backtested('crypto')). Signals on Binance SPOT 1d closes; fills and P&L on the open of the 00:05 UTC 5m
bar (USDT-M perp from its archive start, spot 5m before); realized funding at its actual settlement times. Each read ONCE, in
order, each in its own commit (pre-registration §6):

    python3 scripts/research/edge_c1.py dry-run --out <json>          # outcome-blind: bar counts, spans, gaps, EVENT counts
    python3 scripts/research/edge_c1.py run --read discovery    --out docs/audits/<date>-edge-c1-discovery.json
    python3 scripts/research/edge_c1.py run --read confirmation --after <discovery json>    --out ...
    python3 scripts/research/edge_c1.py run --read exposed      --after <confirmation json> --out ...

A read loads every series truncated at its END (the 00:05 UTC open after its last day, which marks the last day's close),
refuses when the data do not reach that END, and computes outcome rows ONLY for its own window. "Reach" is exact: a 5m bar
OPENING at 00:05:00 UTC on every eligible fill day up to and including the END mark (a fill never moves to a later bar), and
the realized funding settlement at 00:00 UTC after the last day (it is paid by the last day). The signal path and the 20 %
threshold path need no P&L, so they run over all history up to the END; the P&L simulation starts at the window's first day
with the positions held then carried over (an equal capital split, no fee), and nothing before the window is ever booked.

Registration guard (run(require_clean=True), the CLI default): the read refuses unless this script, its tests, the
pre-registration (carrying the implementation addendum tag PREREG_AMENDMENT) and every reused module are tracked by git and
unmodified, and the --after JSON is tracked, clean and was itself written under the guard. Every read JSON records git HEAD,
the sha256 of the guarded files and of every data file it loaded (meta.snapshot), and RESOLVED_AMBIGUITIES.

Daily return of day d = [00:05 d, 00:05 d+1): the fill at 00:05 d and its fee belong to d; every funding settlement tau with
00:05 d <= tau < 00:05 d+1 (so the 00:00 stamp of d+1) is paid by the position held after the 00:05 d fill
(pre-registration §4). Read-only on repo data. Nothing here touches the live path or any account."""
import argparse
import array
import bisect
import calendar
import collections
import datetime
import gzip
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import history_store as HS  # noqa: E402
import instruments as I  # noqa: E402


def _load(name, rel):
    """Load a sibling research module by path (repo convention;
    docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)."""
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EC = _load("edge_census", "scripts/research/edge_census.py")

PREREG = "docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md"
SPOT_ROOT = os.path.join(ROOT, "data", "history", "binance_spot")
UM_ROOT = os.path.join(ROOT, "data", "history", "binance_um")
NS = (5, 10, 20, 30, 60, 90, 150, 250, 360)                    # §3, frozen (the source's)
VOL_DAYS, ANNUAL_DAYS, VOL_TARGET, LEV_CAP = 90, 365, 0.25, 2.0
MIN_PRIOR_CLOSES = 360                                           # §3 eligibility
FILL_MINUTE = 5                                                  # 00:05:00 UTC 5m open
REBALANCE_REL = 0.20                                             # |W_target - W_held| > 0.20 x W_target (relative, frozen)
TAKER, SLIPPAGE = 0.0005, 0.0001                                 # §4, per side, on traded notional
PROXY_RATE, PROXY_HOURS = 0.0001, (0, 8, 16)                     # §2, before a symbol's first realized funding
NW_LAGS = 10
FDR_Q, CONFIRM_P, EXPOSED_P, PLACEBO_GATE = 0.10, 0.05, 0.10, 0.10
PLACEBO_DRAWS, PLACEBO_SEED, PLACEBO_MIN_SHIFT = 1000, 20261003, 60
PREREG_FAMILY_M = 4                                              # BH over T1-T4
READS = ("discovery", "confirmation", "exposed")
WINDOWS = {"discovery": (datetime.date(2018, 8, 12), datetime.date(2022, 7, 28)),
           "confirmation": (datetime.date(2022, 7, 29), datetime.date(2025, 3, 19)),
           "exposed": (datetime.date(2025, 3, 20), datetime.date(2026, 9, 30))}
N1_SYMBOLS = ("BTCUSDT", "ETHUSDT")                              # §7 N1: BTC and ETH only (a pair, not the allowlist)
N1_MAS = (5, 10, 20, 50, 100)
N2_COIN_RISK, N2_TOTAL_RISK, N2_R = 0.01, 0.03, 0.01
REGIME_SHARE, REGIME_MONTHS = 0.5, 3
DAY = datetime.timedelta(days=1)
POP = [bin(m).count("1") for m in range(1 << len(NS))]
ELIGIBLE_FROM = {"BTCUSDT": datetime.date(2018, 8, 12),        # §3 verbatim: a read refuses when the data give another date
                 "ETHUSDT": datetime.date(2018, 8, 12),
                 "SOLUSDT": datetime.date(2021, 8, 6)}
MAX_FUNDING_STEP = 8 * 3600                                      # Binance's longest settlement interval: a larger step = missing
SCRIPT = "scripts/research/edge_c1.py"
PREREG_AMENDMENT = "[C1-A1]"                                     # the pre-read implementation addendum's tag (RESOLVED_AMBIGUITIES)
GUARDED = (SCRIPT, "scripts/tests/test_edge_c1.py", PREREG, "scripts/research/edge_census.py", "scripts/history_store.py",
           "scripts/instruments.py", "scripts/research/book_sim.py")
RESOLVED_AMBIGUITIES = (
    "decide/held_at: W_held = the weight set at the coin's last trade (not the price-drifted exposure since); the 20 % rule "
    "compares W_target with it.",
    "coin_signals: a missing spot 1d close = no state update (positions and stops carry); sigma's log returns are taken between "
    "consecutive AVAILABLE closes, sample SD (n - 1); a sub-model whose n closes do not exist yet stays flat; entry needs "
    "C_t == Up exactly.",
    "build/coverage: eligible from the first fill day with 360 prior spot closes (sigma then always defined); the dates must equal "
    "ELIGIBLE_FROM (§3) and the window's first day must be a grid day, or the read refuses.",
    "simulate: benchmark r_B = equal-capital SUB-ACCOUNTS re-split on the sleeve's re-split days (first day, first UTC day of a "
    "month, a coin joining) and drifting with each coin's P1/P0 between them; N6's funded benchmark the same with P1/P0 - F/P0.",
    "simulate: positions open at the window's start are placed at an equal split of capital 1.0 without a fee; units = held "
    "weight x the coin's capital BEFORE the fee / P0, the fee then leaves the coin's cash.",
    "simulate: the one interval spanning the spot -> perp switch books the spot/perp basis in sleeve and benchmark; no switch "
    "trade is charged.",
    "coverage/price_at: every fill (every eligible day from the coin's eligibility) and the END mark need a 5m bar OPENING at "
    "00:05:00 UTC; one missing -> the read refuses (never a delayed fill).",
    "funding_mark: P_tau = the open of the 5m bar starting at tau; with no bar there, the close of the last bar ending at or "
    "before tau (never a later price), counted in meta.funding_mark_lookups.",
    "load_coin/settlements_in/coverage: REST rows before the archive, the archive from its first month (the archive wins on an "
    "equal stamp); before the first realized settlement the 0.01 %/8 h proxy at 00/08/16 UTC; the read refuses on a step > 8 h "
    "between realized settlements in the window or without the 00:00 settlement after the last day.",
    "regress: one-sided p of the Newey-West t against Student-t with n - 2 df; fewer than 12 observations -> no test.",
    "T2-T4: the coin's sub-account net daily return regressed on its own P1/P0 - 1; each read's thresholds are T1's.",
    "placebo: the shift acts on each coin's list of eligible window days (L_c of them); L_c = L -> k; a coin joining inside the "
    "window -> k_c = 60 + (k - 60) mod (L_c - 119), so 60 <= k_c <= L_c - 60; L_c < 120 -> unshifted and its own p_P is None; "
    "the carried-in weight of a shifted coin = its first eligible day's lev x the circular predecessor's mask.",
    "p_placebo: a draw whose alpha is undefined counts as alpha_k >= alpha_obs (conservative).",
    "regime: 'alpha from <= 3 months' = the 3 best calendar months' summed contribution (1/N) sum (y - beta x) / alpha.",
    "N2: the target is scaled so the coin's open risk <= 1 % and the total <= 3 % (_n2_scales), and the HELD weight is capped "
    "at the same limits (_n2_cap: a cap forces a trade inside the 20 % band).",
    "single-coin promotion: T1's label VALIDATED and the coin's own read pass in all three reads.",
)


def symbols():
    """The family's coins: scripts/instruments.py backtested('crypto'), never a literal list (pre-registration
    docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §1)."""
    return I.backtested("crypto")


def t_at(d, hour=0, minute=0):
    """Epoch seconds of UTC date d at hour:minute (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    return calendar.timegm((d.year, d.month, d.day, hour, minute, 0))


def t_fill(d):
    """Epoch of the fill instant of day d: the OPEN of the 5m bar starting 00:05:00 UTC, never inside 00:00 +/- 1 min
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    return t_at(d, 0, FILL_MINUTE)


def _epoch(iso):
    """Epoch seconds of an ISO-8601 UTC stamp (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    return int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _iso(t):
    """ISO-8601 UTC stamp of epoch t (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------------------------ data
def _read_series(sym, tf, root):
    """(times, opens, closes, path) of one OHLCV series via history_store.read_doc, as compact arrays, or None when missing.
    The history_store cache entry is released after extraction (a perp 5m document is ~0.6 GB as dicts)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    before = set(HS._LOAD_CACHE)
    doc, path = HS.read_doc(sym, tf, root=root)
    if doc is None:
        return None
    T, O, C = array.array("q"), array.array("d"), array.array("d")
    for b in doc["candles"]:
        T.append(_epoch(b["time"]))
        O.append(float(b["open"]))
        C.append(float(b["close"]))
    for k in set(HS._LOAD_CACHE) - before:
        HS._LOAD_CACHE.pop(k, None)
    return T, O, C, path


def _read_funding(path):
    """[(epoch, rate, interval_hours or None)] from a gzip JSON {rows: [{time, rate[, interval_hours]}]}, or None when missing
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    if not os.path.exists(path):
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh).get("rows") or []
    return [(_epoch(r["time"]), float(r["rate"]), r.get("interval_hours")) for r in rows]


def _gaps(T, step):
    """(number of gaps, missing bars, largest gap in hours, last bar before the largest gap) of a sorted epoch series on a
    `step`-second grid (outcome-blind data QA; docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    n = missing = 0
    big, at = 0, None
    for a, b in zip(T, T[1:]):
        if b - a > step:
            n += 1
            missing += (b - a) // step - 1
            if b - a > big:
                big, at = b - a, a
    return n, missing, big / 3600.0, (_iso(at) if at is not None else None)


class Coin:
    """One symbol's point-in-time inputs: spot 1d closes by UTC date, a spliced 5m open series (spot before the first perp bar,
    perp from it), realized funding settlements (REST before the archive, the archive after) and data facts for the dry run
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""

    def __init__(self, sym, dates, closes, T, O, C, settlements, info=None, perp_first=None):
        self.sym = sym
        self.dates, self.closes = list(dates), list(closes)
        self.T, self.O, self.C = T, O, C
        self.settlements = sorted(settlements)               # [(epoch, rate, source)]: realized only
        self.st = [x[0] for x in self.settlements]
        self.listing = self.st[0] if self.st else None        # before it: the 0.01 %/8 h proxy
        self.perp_first = perp_first
        self.info = info or {}


def _cut(s, t_last):
    """The series s = (T, O, C, path) keeping bars that open at or before t_last (all when t_last is None)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6: the read sees nothing after its END)."""
    if s is None or t_last is None:
        return s
    k = bisect.bisect_right(s[0], t_last)
    return s[0][:k], s[1][:k], s[2][:k], s[3]


def load_coin(sym, end=None):
    """Load `sym`, every series truncated at the END of a read ending on UTC date `end` (the 00:05 open of end + 1 day; spot
    1d closes dated <= end; funding stamped before the END), or untruncated when end is None (dry run). The data facts in
    info (bars, spans, gaps, funding rows and intervals) are computed AFTER truncation, so a read records nothing from beyond
    its END; they name no file path (meta.snapshot does). A missing file is recorded in info['missing'], never raised
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2, §6)."""
    t_end = t_fill(end + DAY) if end is not None else None
    info = {"missing": []}
    d1 = _cut(_read_series(sym, "1d", SPOT_ROOT), t_at(end) if end is not None else None)
    dates, closes = [], []
    if d1 is None:
        info["missing"].append(f"spot 1d (binance_spot ohlcv.{sym}.1d)")
    else:
        T, _O, C, _path = d1
        seen, dup, off = set(), 0, 0
        for t, c in zip(T, C):
            if t % 86400:
                off += 1
                continue
            d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
            if d in seen:
                dup += 1
                continue
            seen.add(d)
            dates.append(d)
            closes.append(c)
        order = sorted(range(len(dates)), key=lambda k: dates[k])
        dates, closes = [dates[k] for k in order], [closes[k] for k in order]
        span = (dates[-1] - dates[0]).days + 1 if dates else 0
        info["spot_1d"] = {"bars": len(dates), "first": str(dates[0]) if dates else None,
                           "last": str(dates[-1]) if dates else None, "duplicates_dropped": dup, "not_midnight": off,
                           "missing_days": span - len(dates),
                           "missing_dates_head": [str(d) for d in _missing_dates(dates)[:10]]}
    spot5 = _cut(_read_series(sym, "5m", SPOT_ROOT), t_end)
    perp5 = _cut(_read_series(sym, "5m", UM_ROOT), t_end)
    for name, s, venue in (("spot_5m", spot5, "binance_spot"), ("perp_5m", perp5, "binance_um")):
        if s is None:
            info["missing"].append(f"{name.replace('_', ' ')} ({venue} ohlcv.{sym}.5m)")
            continue
        g = _gaps(s[0], 300)
        info[name] = {"bars": len(s[0]), "first": _iso(s[0][0]) if len(s[0]) else None,
                      "last": _iso(s[0][-1]) if len(s[0]) else None, "gaps": g[0], "missing_bars": g[1],
                      "largest_gap_hours": g[2], "largest_gap_after": g[3]}
    perp_first = perp5[0][0] if perp5 is not None and len(perp5[0]) else None
    T, O, C = array.array("q"), array.array("d"), array.array("d")
    for s, keep in ((spot5, lambda t: perp_first is None or t < perp_first), (perp5, lambda t: True)):
        if s is None:
            continue
        for t, o, c in zip(s[0], s[1], s[2]):
            if keep(t):
                T.append(t)
                O.append(o)
                C.append(c)
    sett = []
    for name, fn, src in (("funding_rest", f"funding_rest.{sym}.json.gz", "rest"),
                          ("funding", f"funding.{sym}.json.gz", "archive")):
        rows = _read_funding(os.path.join(UM_ROOT, fn))
        if rows is None:
            info["missing"].append(f"{name} (binance_um {fn})")
            continue
        rows = [r for r in rows if t_end is None or r[0] < t_end]
        info[name] = {"rows": len(rows), "first": _iso(rows[0][0]) if rows else None,
                      "last": _iso(rows[-1][0]) if rows else None,
                      "intervals_h": dict(collections.Counter(str(r[2]) for r in rows)),
                      "off_5m_grid": sum(1 for r in rows if r[0] % 300),
                      "irregular_steps": sum(1 for a, b in zip(rows, rows[1:])
                                             if b[2] is not None and b[0] - a[0] != 3600 * b[2])}
        sett += [(t, r, src) for t, r, _h in rows]
    by_t = {}
    for t, r, src in sett:                                    # one settlement per instant; the archive wins over REST
        if t not in by_t or src == "archive":
            by_t[t] = (t, r, src)
    return Coin(sym, dates, closes, T, O, C, list(by_t.values()), info, perp_first)


def _sha256(path):
    """sha256 of one file's bytes (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2: the importer's
    checksum-verified files; CLAUDE.md §10 dataset snapshot)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _rel(path):
    """`path` relative to the repository root (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2)."""
    return os.path.relpath(os.path.abspath(path), ROOT)


def snapshot(syms):
    """The FILE inventory of the data a read loads -- untruncated identity, never used by any computation: per symbol and
    series the path and sha256 (history_store.digest for OHLCV series, the file's sha256 for funding), None when absent
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2; CLAUDE.md §10 / §46 reproducibility)."""
    out = {"note": "file inventory (untruncated, not used by the computation)",
           "roots": {"spot": _rel(SPOT_ROOT), "um": _rel(UM_ROOT)}, "series": {}}
    for s in syms:
        rec = {}
        for name, tf, root in (("spot_1d", "1d", SPOT_ROOT), ("spot_5m", "5m", SPOT_ROOT), ("perp_5m", "5m", UM_ROOT)):
            path, _shape = HS.resolve(s, tf, root=root)
            rec[name] = {"path": _rel(path), "sha256": HS.digest(s, tf, root=root)} if path else None
        for name, fn in (("funding", f"funding.{s}.json.gz"), ("funding_rest", f"funding_rest.{s}.json.gz")):
            p = os.path.join(UM_ROOT, fn)
            rec[name] = {"path": _rel(p), "sha256": _sha256(p)} if os.path.exists(p) else None
        out["series"][s] = rec
    return out


def _missing_dates(dates):
    """UTC dates absent between the first and last spot close (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md
    §2: a missing spot 1d bar means no state update that day; the count is reported)."""
    have = set(dates)
    out, d = [], dates[0] if dates else None
    while d is not None and d <= dates[-1]:
        if d not in have:
            out.append(d)
        d += DAY
    return out


def price_at(coin, t):
    """(price, 'exact'): the OPEN of the 5m bar starting exactly at t -- a fill or a day mark. Raises ValueError when no bar
    opens at t: a fill never moves to a later bar (it could land inside 00:00 +/- 1 min or days later) and a mark never falls
    back to an earlier close; coverage() refuses such a read before anything is computed
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3, §4)."""
    k = bisect.bisect_left(coin.T, t)
    if k < len(coin.T) and coin.T[k] == t:
        return coin.O[k], "exact"
    raise ValueError(f"{coin.sym}: no 5m bar opens at {_iso(t)} (next {_iso(coin.T[k]) if k < len(coin.T) else None})")


def funding_mark(coin, tau):
    """(P_tau, how) for a funding settlement at tau: the OPEN of the 5m bar starting at tau ('exact'); with no bar there, the
    CLOSE of the last bar ending at or before tau ('prior_close'; its open when that bar has not ended by tau, 'prior_open'),
    so a cost never uses a price from after tau; (None, 'none') with no earlier bar
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §4; RESOLVED_AMBIGUITIES)."""
    k = bisect.bisect_left(coin.T, tau)
    if k < len(coin.T) and coin.T[k] == tau:
        return coin.O[k], "exact"
    if k == 0:
        return None, "none"
    if coin.T[k - 1] + 300 <= tau:
        return coin.C[k - 1], "prior_close"
    return coin.O[k - 1], "prior_open"


def settlements_in(coin, a, b):
    """[(tau, rate, source)] for every funding settlement a <= tau < b: realized ones at their actual times, and before the
    symbol's first realized settlement the 0.01 %/8 h proxy at 00/08/16 UTC
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2, §4)."""
    out = []
    if coin.listing is None or a < coin.listing:
        d = datetime.datetime.fromtimestamp(a, datetime.timezone.utc).date()
        while t_at(d) < b:
            for h in PROXY_HOURS:
                tau = t_at(d, h)
                if a <= tau < b and (coin.listing is None or tau < coin.listing):
                    out.append((tau, PROXY_RATE, "proxy"))
            d += DAY
    lo, hi = bisect.bisect_left(coin.st, a), bisect.bisect_left(coin.st, b)
    return out + coin.settlements[lo:hi]


def day_prices(coin, days):
    """{day: (P0, P1, F, how0, how1, sources, marks)}: P0 = the fill/mark price at 00:05 of the day, P1 = the mark at 00:05 of
    the next day (both exact bars, price_at), F = sum over the day's settlements of rate x P_tau (P_tau = funding_mark), so the
    funding paid by q units held through the day is q x F; sources / marks count the settlements by source and by mark kind
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §4)."""
    out = {}
    for d in days:
        a, b = t_fill(d), t_fill(d + DAY)
        p0, h0 = price_at(coin, a)
        p1, h1 = price_at(coin, b)
        f, src, marks = 0.0, collections.Counter(), collections.Counter()
        for tau, rate, s in settlements_in(coin, a, b):
            pt, how = funding_mark(coin, tau)
            if pt is None:
                raise ValueError(f"{coin.sym}: no 5m price at or before the settlement {_iso(tau)}")
            f += rate * pt
            src[s] += 1
            marks[how] += 1
        out[d] = (p0, p1, f, h0, h1, src, marks)
    return out


# ------------------------------------------------------------------------------------------------ signals (no P&L)
def coin_signals(dates, closes, ns=NS, with_sigma=True):
    """Per FILL day D (every UTC date from the first close + 1 to the last close + 1), the state decided at 00:00 UTC of D from
    the closes of days <= D - 1 (pre-registration docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3):

    * Up/Dn/Mid over the last n closes, today's included; flat and C_t == Up -> long with stop TS = Mid for the next day;
      long and C_t < TS (the stop in force during day t) -> flat; else TS = max(TS, Mid) (never lowered). One transition per
      sub-model per close. A sub-model whose window is not yet full stays flat.
    * sigma = SD (sample) of the last 90 daily log returns of C x sqrt(365).
    * eligible = at least 360 closes dated before D.
    * A missing close for D - 1 means no state update (`stale`).

    Returns lists aligned with `days`: mask (bit a = sub-model ns[a] long), ts (stops in force for D, None when flat), sigma,
    eligible, stale, entered / exited (bitmasks of sub-models that changed at the close of D - 1). with_sigma=False (the
    outcome-blind dry run) computes no return statistic at all: sigma is None everywhere."""
    out = {k: [] for k in ("days", "mask", "ts", "sigma", "eligible", "stale", "entered", "exited")}
    if not dates:
        return out
    long_, ts = [False] * len(ns), [None] * len(ns)
    logs, k = [], 0
    d = dates[0] + DAY
    while d <= dates[-1] + DAY:
        ent = ext = 0
        stale = not (k < len(dates) and dates[k] == d - DAY)
        if not stale:
            c = closes[k]
            if k > 0 and with_sigma:
                logs.append(math.log(c / closes[k - 1]))
            for a, n in enumerate(ns):
                if k + 1 < n:
                    continue
                win = closes[k - n + 1:k + 1]
                up, dn = max(win), min(win)
                mid = (up + dn) / 2.0
                if long_[a]:
                    if c < ts[a]:
                        long_[a], ts[a] = False, None
                        ext |= 1 << a
                    else:
                        ts[a] = max(ts[a], mid)
                elif c == up:
                    long_[a], ts[a] = True, mid
                    ent |= 1 << a
            k += 1
        out["days"].append(d)
        out["mask"].append(sum(1 << a for a in range(len(ns)) if long_[a]))
        out["ts"].append(tuple(ts))
        out["sigma"].append(statistics.stdev(logs[-VOL_DAYS:]) * math.sqrt(ANNUAL_DAYS) if len(logs) >= VOL_DAYS else None)
        out["eligible"].append(k >= MIN_PRIOR_CLOSES)
        out["stale"].append(stale)
        out["entered"].append(ent)
        out["exited"].append(ext)
        d += DAY
    return out


def ma_signals(dates, closes, mas=N1_MAS):
    """N1 (Detzel MA arms): per fill day D, S_L = 1 if C_{D-1} > MA_L (the mean of the last L closes, today's included), for
    each L; a missing close keeps the previous state (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7)."""
    out = {"days": [], **{L: [] for L in mas}}
    if not dates:
        return out
    state, k = dict.fromkeys(mas, 0), 0
    d = dates[0] + DAY
    while d <= dates[-1] + DAY:
        if k < len(dates) and dates[k] == d - DAY:
            for L in mas:
                if k + 1 >= L:
                    state[L] = 1 if closes[k] > sum(closes[k - L + 1:k + 1]) / L else 0
            k += 1
        out["days"].append(d)
        for L in mas:
            out[L].append(state[L])
        d += DAY
    return out


def lev(sigma):
    """min(0.25 / sigma, 2.0): the volatility-target multiplier of every sub-model weight (None without a sigma)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    if sigma is None:
        return None
    return LEV_CAP if sigma <= 0 else min(VOL_TARGET / sigma, LEV_CAP)


def decide(target, changed, held):
    """(new held weight, trade?): any sub-model entry or exit trades straight to the target; a volatility-only change trades
    only when |W_target - W_held| > 0.20 x W_target (the relative reading, frozen)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    if changed or abs(target - held) > REBALANCE_REL * target:
        return target, True
    return held, False


def build(coins, end):
    """(grid, arrays): the UTC fill-day grid from the earliest eligibility day to `end`, and per coin per grid day: elig, mask,
    lev, target W = lev x (longs / 9), changed (any sub-model entry/exit), ts, entered, exited, stale, and for eligible days
    P0, P1, F, the price-lookup kind and the funding sources, plus the N2 open-risk fraction
    sum_n (w_n / 9) x max(0, (P0 - TS_n) / P0) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3, §4, §7)."""
    sigs = {s: coin_signals(c.dates, c.closes) for s, c in coins.items()}
    first = {}
    for s, sg in sigs.items():
        first[s] = next((d for d, e in zip(sg["days"], sg["eligible"]) if e), None)
        if first[s] is None:
            raise SystemExit(f"{s}: never eligible ({MIN_PRIOR_CLOSES} prior spot closes) in the loaded data")
    g0 = min(first.values())
    grid = [g0 + k * DAY for k in range((end - g0).days + 1)]
    arrs = {}
    for s, c in coins.items():
        sg = sigs[s]
        at = {d: k for k, d in enumerate(sg["days"])}
        A = collections.defaultdict(list)
        el = []
        for d in grid:
            k = at.get(d)
            if k is None:
                for key, v in (("elig", False), ("mask", 0), ("lev", None), ("target", 0.0), ("changed", False),
                               ("ts", None), ("entered", 0), ("exited", 0), ("stale", False)):
                    A[key].append(v)
                continue
            m = sg["mask"][k]
            lv = lev(sg["sigma"][k])
            A["elig"].append(bool(sg["eligible"][k] and lv is not None))
            A["mask"].append(m)
            A["lev"].append(lv)
            A["target"].append(lv * POP[m] / len(NS) if lv is not None else 0.0)
            A["changed"].append(m != (sg["mask"][k - 1] if k else 0))
            A["ts"].append(sg["ts"][k])
            A["entered"].append(sg["entered"][k])
            A["exited"].append(sg["exited"][k])
            A["stale"].append(sg["stale"][k])
            if A["elig"][-1]:
                el.append(d)
        px = day_prices(c, el)
        for key, i in (("P0", 0), ("P1", 1), ("F", 2), ("how0", 3), ("how1", 4), ("fsrc", 5), ("fmark", 6)):
            A[key] = [px[d][i] if d in px else None for d in grid]
        A["risk"] = []
        for j in range(len(grid)):
            p0, ts, lv = A["P0"][j], A["ts"][j], A["lev"][j]
            if p0 is None or ts is None or lv is None:
                A["risk"].append(0.0)
                continue
            A["risk"].append(lv / len(NS) * sum(max(0.0, (p0 - x) / p0) for x in ts if x is not None))
        arrs[s] = dict(A)
    return grid, arrs


def _n2_scales(syms, risk, shares):
    """Owner sizing (N2): per coin scale = min(1, 1 % / open risk), open risk = risk fraction x capital_i / equity; then all
    coins scaled so the total open risk <= 3 % (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N2)."""
    r = {s: risk[s] * shares[s] for s in syms}
    sc = {s: (min(1.0, N2_COIN_RISK / r[s]) if r[s] > 0 else 1.0) for s in syms}
    tot = sum(r[s] * sc[s] for s in syms)
    if tot > N2_TOTAL_RISK:
        sc = {s: sc[s] * N2_TOTAL_RISK / tot for s in syms}
    return sc


def _n2_cap(w, target, risk, shares):
    """N2 on the HELD weight: each coin's open risk at weight w = risk fraction at its full target x (w / target) x capital_i /
    equity, capped at 1 %, then every coin scaled so the total <= 3 %. The 20 % threshold rule could otherwise keep a held
    weight up to 1.2x the scaled target (open risk up to ~1.2 % / 3.6 %), breaking '1 % = the maximum loss at the stop'
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N2; RESOLVED_AMBIGUITIES)."""
    r = {s: (risk[s] * shares[s] * w[s] / target[s] if target[s] > 0 else 0.0) for s in w}
    out = dict(w)
    for s in w:
        if r[s] > N2_COIN_RISK:
            out[s], r[s] = w[s] * N2_COIN_RISK / r[s], N2_COIN_RISK
    tot = sum(r.values())
    if tot > N2_TOTAL_RISK:
        out = {s: v * N2_TOTAL_RISK / tot for s, v in out.items()}
    return out


def decide_all(now, target, changed, held, risk=None, shares=None):
    """{coin: (new held weight, trade?)} for one fill day: `decide` per coin; with risk and shares (N2 owner sizing) the
    targets are scaled by _n2_scales first and the held weights then capped by _n2_cap (a cap that binds is a trade)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3, §7 N2)."""
    if risk is None:
        return {s: decide(target[s], changed[s], held[s]) for s in now}
    sc = _n2_scales(now, risk, shares)
    dec = {s: decide(sc[s] * target[s], changed[s], held[s]) for s in now}
    cap = _n2_cap({s: dec[s][0] for s in now}, target, risk, shares)
    return {s: (cap[s], dec[s][1] or cap[s] < dec[s][0] * (1.0 - 1e-12)) for s in now}


def held_at(arrs, syms, j0, tkey="target", ckey="changed", n2=False):
    """The weight each coin holds entering grid day j0: the 20 % threshold rule run over every earlier grid day (no P&L; for N2
    the capital share is the equal split) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3, §6: positions
    open at the window's start carry over)."""
    held = dict.fromkeys(syms, 0.0)
    for j in range(j0):
        now = [s for s in syms if arrs[s]["elig"][j]]
        if not now:
            continue
        dec = decide_all(now, {s: arrs[s][tkey][j] for s in now}, {s: arrs[s][ckey][j] for s in now}, held,
                         *(({s: arrs[s]["risk"][j] for s in now}, dict.fromkeys(now, 1.0 / len(now))) if n2 else ()))
        for s in now:
            held[s] = dec[s][0]
    return held


def window_inputs(arrs, syms, j0, j1, held0, tkey="target", ckey="changed"):
    """Per coin, the simulator's inputs over grid days j0..j1 (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md
    §3-§5)."""
    sl = slice(j0, j1 + 1)
    return {s: {"elig": arrs[s]["elig"][sl], "target": arrs[s][tkey][sl], "changed": arrs[s][ckey][sl], "held0": held0[s],
                "P0": arrs[s]["P0"][sl], "P1": arrs[s]["P1"][sl], "F": arrs[s]["F"][sl], "risk": arrs[s]["risk"][sl],
                "mask": arrs[s]["mask"][sl], "lev": arrs[s]["lev"][sl],
                "carried": j0 > 0 and arrs[s]["elig"][j0 - 1]} for s in syms}


# ------------------------------------------------------------------------------------------------ simulation (P&L)
def simulate(days, inp, cost_rate, n2=False):
    """The equal-capital sleeve over `days` (pre-registration docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md
    §3-§5). Each coin is a sub-account (cash, units q). Day d:

    * mark at P0 (00:05 d open); on the first active day the carried positions are placed at an equal split without a fee;
      on the first UTC day of a month and when a coin becomes eligible, the equity is re-split equally (those trades charged);
    * decide (`decide_all`) and trade to the held weight x the coin's capital / P0 when trading or re-splitting; fee =
      cost_rate x |traded units| x P0;
    * funding = q x F (every settlement in [00:05 d, 00:05 d+1), paid by the position held after the 00:05 d fill);
    * mark at P1 (00:05 d+1). r_S = equity ratio - 1; coin r_i = its sub-account ratio - 1; benchmark r_B = the return of
      equal-capital benchmark sub-accounts (no cost, no funding) re-split on the SAME days as the sleeve and drifting with
      each coin's P1/P0 between them; the funded benchmark (N6) does the same with P1/P0 - F/P0.

    Returns lists keyed by day plus per-coin lists (only days with at least one eligible coin)."""
    syms = list(inp)
    cash, q, held = dict.fromkeys(syms, 0.0), dict.fromkeys(syms, 0.0), dict.fromkeys(syms, 0.0)
    bk, bkf = dict.fromkeys(syms, 0.0), dict.fromkeys(syms, 0.0)
    inside = ()
    out = {k: [] for k in ("date", "r", "gross", "fees", "funding", "bench", "bench_funded", "equity", "turnover")}
    out["coin"] = {s: {k: [] for k in ("date", "r", "rc", "rcf", "w", "gross")} for s in syms}
    started = False
    for j, d in enumerate(days):
        now = tuple(s for s in syms if inp[s]["elig"][j])
        if not now:
            continue
        if set(inside) - set(now):
            raise ValueError(f"{d}: {sorted(set(inside) - set(now))} left the sleeve (coverage gap)")
        P0 = {s: inp[s]["P0"][j] for s in now}
        if not started:
            started, E = True, 1.0
            for s in now:
                held[s] = inp[s]["held0"]
                k = E / len(now)
                q[s] = held[s] * k / P0[s]
                cash[s] = k - q[s] * P0[s]
                bk[s] = bkf[s] = 1.0 / len(now)
            resplit = False
        else:
            E = sum(cash[s] + q[s] * P0[s] for s in inside)
            resplit = d.day == 1 or now != inside
            if resplit:
                B, Bf = sum(bk[s] for s in inside), sum(bkf[s] for s in inside)
                for s in now:
                    cash[s] = E / len(now) - q[s] * P0[s]
                    bk[s], bkf[s] = B / len(now), Bf / len(now)
        Kp = {s: cash[s] + q[s] * P0[s] for s in now}
        dec = decide_all(now, {s: inp[s]["target"][j] for s in now}, {s: inp[s]["changed"][j] for s in now}, held,
                         *(({s: inp[s]["risk"][j] for s in now}, {s: Kp[s] / E for s in now}) if n2 else ()))
        fees = fund = turn = E1 = 0.0
        B0, Bf0, B1, Bf1 = sum(bk[s] for s in now), sum(bkf[s] for s in now), 0.0, 0.0
        for s in now:
            x = inp[s]
            w, trade = dec[s]
            qn = w * Kp[s] / P0[s] if (trade or resplit) else q[s]
            fee = cost_rate * abs(qn - q[s]) * P0[s]
            f = qn * x["F"][j]
            turn += abs(qn - q[s]) * P0[s]
            cash[s] -= (qn - q[s]) * P0[s] + fee + f
            q[s], held[s] = qn, w
            k1 = cash[s] + qn * x["P1"][j]
            rc = x["P1"][j] / P0[s] - 1.0
            rcf = rc - x["F"][j] / P0[s]
            c = out["coin"][s]
            c["date"].append(d)
            c["r"].append(k1 / Kp[s] - 1.0 if Kp[s] > 0 else 0.0)
            c["gross"].append((k1 + fee + f) / Kp[s] - 1.0 if Kp[s] > 0 else 0.0)
            c["rc"].append(rc)
            c["rcf"].append(rcf)
            c["w"].append(w)
            fees += fee
            fund += f
            E1 += k1
            bk[s] *= 1.0 + rc
            bkf[s] *= 1.0 + rcf
            B1 += bk[s]
            Bf1 += bkf[s]
        out["date"].append(d)
        out["r"].append(E1 / E - 1.0)
        out["gross"].append((E1 + fees + fund) / E - 1.0)
        out["fees"].append(fees / E)
        out["funding"].append(fund / E)
        out["turnover"].append(turn / E)
        out["bench"].append(B1 / B0 - 1.0)
        out["bench_funded"].append(Bf1 / Bf0 - 1.0)
        out["equity"].append(E1)
        inside = now
    return out


# ------------------------------------------------------------------------------------------------ statistics (stdlib)
def ols(y, x):
    """(alpha, beta, residuals) of y = alpha + beta x + e, or None when x has no variance
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    n = len(y)
    if n < 3:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx <= 0:
        return None
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx
    a = my - b * mx
    return a, b, [c - a - b * v for v, c in zip(x, y)]


def hac_v00(x, u, lags):
    """Var(alpha-hat) of an OLS on [1, x] with residuals u: (X'X)^-1 S (X'X)^-1, S = sum u_t^2 X_t X_t' + sum_{l=1..L}
    (1 - l/(L+1)) sum_t u_t u_{t-l} (X_t X_{t-l}' + X_{t-l} X_t') (Newey-West, Bartlett; L = 0 is White HC0)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    n = len(x)
    s00 = s01 = s11 = 0.0
    for xt, ut in zip(x, u):
        e = ut * ut
        s00 += e
        s01 += e * xt
        s11 += e * xt * xt
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        for t in range(lag, n):
            e = u[t] * u[t - lag]
            s00 += w * 2.0 * e
            s01 += w * e * (x[t] + x[t - lag])
            s11 += w * 2.0 * e * x[t] * x[t - lag]
    sx, sxx = sum(x), sum(v * v for v in x)
    det = n * sxx - sx * sx
    a, b = sxx / det, -sx / det                              # first row of (X'X)^-1
    return a * a * s00 + 2.0 * a * b * s01 + b * b * s11


def regress(y, x, lags=NW_LAGS):
    """alpha, beta, Newey-West (10 lags) SE / t / one-sided p (H1 alpha > 0, Student-t with n - 2 df) and CR1-by-date (one
    observation per date: HC1) SE / p (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    n = len(y)
    fit = ols(y, x) if n >= max(3, lags + 2) else None
    if fit is None:
        return {"n": n, "alpha": None, "p_one_sided": None}
    a, b, u = fit
    v_nw, v_cr1 = hac_v00(x, u, lags), hac_v00(x, u, 0) * n / (n - 2)
    se_nw = math.sqrt(v_nw) if v_nw > 0 else None
    se_c = math.sqrt(v_cr1) if v_cr1 > 0 else None
    t_nw = a / se_nw if se_nw else None
    t_c = a / se_c if se_c else None
    return {"n": n, "alpha": a, "alpha_annual": a * ANNUAL_DAYS, "beta": b, "se_nw": se_nw, "t_nw": t_nw,
            "p_one_sided": EC.t_sf(t_nw, n - 2) if t_nw is not None else None, "se_cr1": se_c, "t_cr1": t_c,
            "p_one_sided_cr1": EC.t_sf(t_c, n - 2) if t_c is not None else None}


def month_contrib(dates, y, x, beta):
    """{YYYY-MM: (1/N) sum_{d in month} (y_d - beta x_d)} -- the months' shares of alpha-hat (they sum to it)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6 regime flag, §7 N4)."""
    out = collections.defaultdict(float)
    for d, a, b in zip(dates, y, x):
        out[f"{d.year:04d}-{d.month:02d}"] += (a - beta * b) / len(y)
    return dict(out)


def regime(dates, y, x, reg):
    """Best-3-calendar-months share of alpha and the 'regime-driven' flag (> 50 % of alpha from <= 3 months)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6)."""
    if reg.get("alpha") is None or reg["alpha"] <= 0:
        return {"best3_share": None, "regime_driven": False, "best3_months": []}
    mc = month_contrib(dates, y, x, reg["beta"])
    top = sorted(mc.items(), key=lambda kv: kv[1], reverse=True)[:REGIME_MONTHS]
    share = sum(v for _k, v in top) / reg["alpha"]
    return {"best3_share": share, "regime_driven": share > REGIME_SHARE, "best3_months": [k for k, _v in top]}


def net_line(dates, r):
    """Mean net daily return with its CR1-by-date SE (edge_census.cr1)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md
    §6: 'mean net daily return > 0')."""
    mu, se, _df = EC.cr1(r, dates)
    return {"mean": mu, "se_cr1": se, "annual": mu * ANNUAL_DAYS if mu is not None else None}


# ------------------------------------------------------------------------------------------------ placebo
def shift(lst, k):
    """Circular shift: out[m] = lst[(m - k) mod len] (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    if not lst:
        return []
    k %= len(lst)
    return lst[-k:] + lst[:-k] if k else list(lst)


def coin_shift(k, L, L_c):
    """The offset applied to a coin with L_c eligible days in a window of L days for the shared draw k ~ U{60 .. L-60}: k
    itself when the coin is eligible all window long; for a coin joining inside the window k_c = 60 + (k - 60) mod
    (L_c - 119), so 60 <= k_c <= L_c - 60 (a plain k mod L_c could fall below 60 or on 0 -- the observed path); None (left
    unshifted) when L_c < 120 (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5; RESOLVED_AMBIGUITIES)."""
    if L_c == L:
        return k
    if L_c < 2 * PLACEBO_MIN_SHIFT:
        return None
    return PLACEBO_MIN_SHIFT + (k - PLACEBO_MIN_SHIFT) % (L_c - 2 * PLACEBO_MIN_SHIFT + 1)


def placebo_inputs(base, inp, kmap):
    """The window inputs with every coin's nine Pos_n series shifted jointly by its offset kmap[coin] (coin_shift of the shared
    draw; None or 0 = unshifted) over the coin's eligible window days, the weights recomputed with the DESTINATION day's sigma
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    out = {}
    for s, x in inp.items():
        idx, masks, levs = base[s]
        L = len(idx)
        target, changed = [0.0] * len(x["elig"]), [False] * len(x["elig"])
        held0 = 0.0
        if L:
            sh = shift(masks, kmap.get(s) or 0)
            for m, j in enumerate(idx):
                target[j] = levs[m] * POP[sh[m]] / len(NS)
                changed[j] = sh[m] != sh[m - 1]                  # m = 0: the circular predecessor
            if x["carried"]:
                held0 = levs[0] * POP[sh[-1]] / len(NS)
        out[s] = dict(x, target=target, changed=changed, held0=held0)
    return out


def placebo(days, inp, cost_rate, draws=None, seed=PLACEBO_SEED):
    """Circular-shift placebo: `draws` offsets k ~ U{60 .. L-60} (L = window days), one shared k per draw, mapped per coin by
    coin_shift; fees and funding recomputed by the same simulator. Returns {'k': [...], 'k_coin': {sym: [k_c]}, 'sleeve':
    [alpha_k], 'coins': {sym: [alpha_k] or None (an unshifted coin)}} or None when L < 120
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    draws = PLACEBO_DRAWS if draws is None else draws
    L = len(days)
    if L - PLACEBO_MIN_SHIFT < PLACEBO_MIN_SHIFT:
        return None
    base = {}
    for s, x in inp.items():
        idx = [j for j, e in enumerate(x["elig"]) if e]
        base[s] = (idx, [x["mask"][j] for j in idx], [x["lev"][j] for j in idx])
    rng = random.Random(seed)
    out = {"k": [], "k_coin": {s: [] for s in inp}, "sleeve": [], "coins": {s: [] for s in inp}}
    for _ in range(draws):
        k = rng.randint(PLACEBO_MIN_SHIFT, L - PLACEBO_MIN_SHIFT)
        kmap = {s: coin_shift(k, L, len(base[s][0])) for s in inp}
        sim = simulate(days, placebo_inputs(base, inp, kmap), cost_rate)
        out["k"].append(k)
        out["sleeve"].append(regress(sim["r"], sim["bench"]).get("alpha"))
        for s, c in sim["coin"].items():
            out["k_coin"][s].append(kmap[s])
            out["coins"][s].append(regress(c["r"], c["rc"]).get("alpha"))
    for s in inp:
        if any(v is None for v in out["k_coin"][s]):
            out["coins"][s] = None
    return out


def p_placebo(alpha_obs, alphas):
    """p_P = (1 + #{alpha_k >= alpha_obs}) / (draws + 1); a draw whose alpha is undefined counts as an exceedance
    (conservative) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5)."""
    if alpha_obs is None or not alphas:
        return None
    return (1 + sum(1 for a in alphas if a is None or a >= alpha_obs)) / (len(alphas) + 1)


# ------------------------------------------------------------------------------------------------ verdicts
def read_pass(read, reg, net, net2x, p_pl, bh_rejected):
    """The read's own pass (pre-registration docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6):
    DISCOVERY = BH rejects + mean net daily > 0 + p_P <= 0.10; CONFIRMATION = one-sided p < 0.05 + net > 0 + net > 0 at 2x
    slippage + p_P <= 0.10; EXPOSED = one-sided p < 0.10 + net > 0."""
    p = reg.get("p_one_sided")
    pos = lambda v: v is not None and v > 0                                          # noqa: E731
    gate = p_pl is not None and p_pl <= PLACEBO_GATE
    if read == "discovery":
        return bool(bh_rejected and pos(net) and gate)
    if read == "confirmation":
        return bool(p is not None and p < CONFIRM_P and pos(net) and pos(net2x) and gate)
    return bool(p is not None and p < EXPOSED_P and pos(net))


def label(hist):
    """The family label from the reads done so far (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6):
    DEAD = alpha <= 0 in discovery or confirmation; VALIDATED = all three pass; PROMISING = discovery + confirmation pass and
    exposed net > 0 with p >= 0.10 (forward paper only); INCONCLUSIVE otherwise. A discovery + confirmation pass is never
    called validated (source in-sample)."""
    d, c, x = (hist.get(r) for r in READS)
    if any(h is not None and h.get("alpha") is not None and h["alpha"] <= 0 for h in (d, c)):
        return "DEAD"
    if x is None:
        if c is not None:
            return ("PENDING EXPOSED: discovery + confirmation pass (NOT validated: source in-sample)"
                    if d["pass"] and c["pass"] else "PENDING EXPOSED: not both in-sample reads passed")
        return "PENDING: discovery CANDIDATE" if d and d["pass"] else "PENDING: discovery not a candidate"
    if d["pass"] and c["pass"] and x["pass"]:
        return "VALIDATED"
    p = x.get("p_one_sided")
    if d["pass"] and c["pass"] and (x.get("net") or 0) > 0 and p is not None and p >= EXPOSED_P:
        return "PROMISING (forward paper only)"
    return "INCONCLUSIVE (inconclusive at this power)"


def server_day(d):
    """N5: UTC day d -> the FTMO server day that ends on d; Saturday and Sunday -> the next server day (Monday)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N5)."""
    return d + DAY * ((7 - d.weekday()) % 7 if d.weekday() >= 5 else 0)


def _book_daily():
    """(daily R by server day, corr) of fvg-book v3 = H7 + G9 on XAUUSD, via scripts/research/book_sim.py (the other families'
    already-read trades) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N5)."""
    BS = _load("book_sim", "scripts/research/book_sim.py")
    comps = ["H7_XAUUSD_eod", "G9_XAUUSD_eod"]
    return BS.daily_r([t for c in comps for t in BS.trades(*BS.COMPONENTS[c])]), BS.corr


def n5(dates, r, book):
    """Pearson correlation of the sleeve's net daily return (summed by FTMO server day) with the book's daily R over the
    window's server days (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N5)."""
    if book is None:
        return {"corr": None, "why": "book unavailable"}
    daily, corr = book
    a = collections.defaultdict(float)
    for d, v in zip(dates, r):
        a[str(server_day(d))] += v
    lo, hi = (min(a), max(a)) if a else ("", "")
    b = {k: v for k, v in daily.items() if lo <= k <= hi}
    return {"corr": corr(dict(a), b) if a else None, "server_days": len(a), "book_days": len(b),
            "book": "fvg-book v3 = H7_XAUUSD_eod + G9_XAUUSD_eod (scripts/research/book_sim.py)"}


def drawdown(eq):
    """Maximum drawdown of an equity path starting at 1.0
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7)."""
    peak, mdd = 1.0, 0.0
    for v in eq:
        peak = max(peak, v)
        mdd = max(mdd, 1.0 - v / peak)
    return mdd


def exit_ratios(arrs, syms, j0, j1):
    """N2 'realized loss / planned stop loss per ensemble exit': for each sub-model exit filled on day j (close of j-1 below
    the stop in force), (P0_{j-1} - P0_j) / (P0_{j-1} - TS_{j-1}) when the planned distance is positive; > 1 = a loss beyond
    the planned stop (stops act on daily closes) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N2)."""
    out = []
    for s in syms:
        A = arrs[s]
        for j in range(max(j0, 1), j1 + 1):
            if not A["exited"][j] or not A["elig"][j] or not A["elig"][j - 1] or A["ts"][j - 1] is None:
                continue
            p_prev, p = A["P0"][j - 1], A["P0"][j]
            for a in range(len(NS)):
                ts = A["ts"][j - 1][a]
                if A["exited"][j] >> a & 1 and ts is not None and p_prev > ts:
                    out.append((p_prev - p) / (p_prev - ts))
    return out


def _q(v, p):
    """The p-quantile (nearest rank) of v (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7)."""
    if not v:
        return None
    s = sorted(v)
    return s[min(len(s) - 1, max(0, math.ceil(p * len(s)) - 1))]


def n2_report(sim, ratios):
    """N2 owner sizing (1 % at the stop): CAGR, max drawdown, R / yr, months to +10 %, exit loss ratios, worst day
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N2)."""
    eq, r = sim["equity"], sim["r"]
    if not r:
        return {"n": 0}
    yrs = len(r) / ANNUAL_DAYS
    hit = next((k for k, v in enumerate(eq) if v >= 1.10), None)
    return {"n": len(r), "net_mean": sum(r) / len(r), "cagr": eq[-1] ** (1.0 / yrs) - 1.0 if eq[-1] > 0 else -1.0,
            "max_drawdown": drawdown(eq), "R_per_year": sum(r) / len(r) * ANNUAL_DAYS / N2_R,
            "months_to_plus_10pct": (hit + 1) / (ANNUAL_DAYS / 12.0) if hit is not None else None,
            "worst_day": min(r), "worst_day_R": min(r) / N2_R, "worst_day_date": str(sim["date"][r.index(min(r))]),
            "exit_loss_over_planned": {"exits": len(ratios), "median": _q(ratios, 0.5), "p90": _q(ratios, 0.9),
                                       "max": max(ratios) if ratios else None,
                                       "share_above_1": sum(1 for v in ratios if v > 1) / len(ratios) if ratios else None}}


def n3_report(sim, sim2x):
    """N3: gross vs net, fee and funding drag by calendar year, 2x slippage; plus edge_census.summarise on day rows (excess =
    net - benchmark, net_bp_p90 = the same path at 2x slippage) (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md
    §7 N3)."""
    by = collections.defaultdict(lambda: {"days": 0, "fees": 0.0, "funding": 0.0, "gross": 0.0, "net": 0.0})
    for d, f, fu, g, r in zip(sim["date"], sim["fees"], sim["funding"], sim["gross"], sim["r"]):
        y = by[str(d.year)]
        y["days"] += 1
        y["fees"] += f
        y["funding"] += fu
        y["gross"] += g
        y["net"] += r
    k2 = (TAKER + 2 * SLIPPAGE) / (TAKER + SLIPPAGE)
    rows = [{"date": str(d), "r": g, "cost": f + fu, "cost90": f * k2 + fu, "excess": r - b, "scale": 1.0}
            for d, g, f, fu, r, b in zip(sim["date"], sim["gross"], sim["fees"], sim["funding"], sim["r"], sim["bench"])]
    n = len(sim["r"]) or 1
    return {"gross_mean": sum(sim["gross"]) / n, "net_mean": sum(sim["r"]) / n, "fees_mean": sum(sim["fees"]) / n,
            "funding_mean": sum(sim["funding"]) / n, "turnover_mean": sum(sim["turnover"]) / n,
            "net_mean_2x_slippage": sum(sim2x["r"]) / (len(sim2x["r"]) or 1), "by_year_sums": dict(by),
            "daily_rows_summary_edge_census": EC.summarise(rows) if rows else {"n": 0}}


def n4_report(dates, y, x, reg):
    """N4: alpha by calendar year (OLS per year, Newey-West) and each year's share of the window alpha; best-3-months share
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N4)."""
    years = collections.defaultdict(list)
    for k, d in enumerate(dates):
        years[d.year].append(k)
    mc = month_contrib(dates, y, x, reg["beta"]) if reg.get("beta") is not None else {}
    out = {}
    for yr, ks in sorted(years.items()):
        rg = regress([y[k] for k in ks], [x[k] for k in ks])
        share = sum(v for m, v in mc.items() if m.startswith(f"{yr:04d}-"))
        out[str(yr)] = {"alpha": rg.get("alpha"), "alpha_annual": rg.get("alpha_annual"),
                        "p_one_sided": rg.get("p_one_sided"), "n": len(ks),
                        "share_of_window_alpha": share / reg["alpha"] if reg.get("alpha") else None}
    return {"by_year": out, "regime": regime(dates, y, x, reg)}


def n1_report(syms, grid, arrs, coins, j0, j1, days):
    """N1 Detzel MA arms (BTC, ETH): S_L = 1 if C > MA_L, L in {5, 10, 20, 50, 100}, long/flat 1x, and their mean; the same
    execution, costs and funding; each coin alone and the equal-capital pair
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §7 N1)."""
    n1 = [s for s in N1_SYMBOLS if s in syms]
    if not n1:
        return {"why": "no N1 symbol among the family's coins"}
    ext = {}
    for s in n1:
        ms = ma_signals(coins[s].dates, coins[s].closes)
        at = {d: k for k, d in enumerate(ms["days"])}
        A = dict(arrs[s])
        for arm in [f"MA{L}" for L in N1_MAS] + ["mean"]:
            tgt, ch, prev = [], [], None
            for d in grid:
                k = at.get(d)
                key = tuple(ms[L][k] for L in N1_MAS) if k is not None else (0,) * len(N1_MAS)
                sel = key if arm == "mean" else key[N1_MAS.index(int(arm[2:]))]
                tgt.append(sum(key) / len(N1_MAS) if arm == "mean" else float(sel))
                ch.append(prev is not None and sel != prev)      # an arm entry / exit; the first grid day has no change
                prev = sel
            A[f"t_{arm}"], A[f"c_{arm}"] = tgt, ch
        ext[s] = A
    out = {}
    for arm in [f"MA{L}" for L in N1_MAS] + ["mean"]:
        row = {}
        for group in [[s] for s in n1] + ([n1] if len(n1) > 1 else []):
            held = held_at(ext, group, j0, f"t_{arm}", f"c_{arm}")
            inp = window_inputs(ext, group, j0, j1, held, f"t_{arm}", f"c_{arm}")
            sim = simulate(days, inp, TAKER + SLIPPAGE)
            rg = regress(sim["r"], sim["bench"])
            row["+".join(group)] = {"alpha": rg.get("alpha"), "alpha_annual": rg.get("alpha_annual"),
                                    "p_one_sided": rg.get("p_one_sided"), "n": rg["n"],
                                    "net_mean": sum(sim["r"]) / len(sim["r"]) if sim["r"] else None,
                                    "gross_mean": sum(sim["gross"]) / len(sim["gross"]) if sim["gross"] else None}
        out[arm] = row
    return out


# ------------------------------------------------------------------------------------------------ reads
def coverage(coins, start, end):
    """Problems that make a read on [start, end] impossible to run faithfully (any one -> the read refuses, nothing computed):

    * spot 1d not reaching end - 1, or an eligibility date other than §3's (ELIGIBLE_FROM);
    * a fill day (every eligible day from the coin's eligibility, pre-window days included: the carried 20 % path and N2 use
      their prices) or the END mark (00:05 of end + 1) without a 5m bar OPENING at 00:05:00 UTC -- a fill never moves;
    * no realized funding, realized funding not reaching the 00:00 settlement after the last day (it is paid by the last day),
      or a step > 8 h between realized settlements inside the window (a missing settlement would be charged as 0).

    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2-§4, §6)."""
    out = []
    for s, c in coins.items():
        if not c.dates:
            out.append(f"{s}: spot 1d missing")
            continue
        if c.dates[-1] < end - DAY:
            out.append(f"{s}: spot 1d ends {c.dates[-1]}, the read needs closes to {end - DAY}")
        first = eligible_from(c.dates)
        want = ELIGIBLE_FROM.get(s)
        if want is None:
            out.append(f"{s}: no pre-registered eligibility date (§3)")
        elif first != want:
            out.append(f"{s}: eligible from {first} in the loaded data, the pre-registration (§3) says {want}")
        if first is not None and first <= end:
            bad, d = [], first
            while d <= end + DAY:
                t = t_fill(d)
                k = bisect.bisect_left(c.T, t)
                if not (k < len(c.T) and c.T[k] == t):
                    bad.append(f"{_iso(t)} (next bar {_iso(c.T[k]) if k < len(c.T) else None})")
                d += DAY
            if bad:
                out.append(f"{s}: no 5m bar opens at 00:05 UTC on {len(bad)} required day(s) (fills never move; END mark "
                           f"{_iso(t_fill(end + DAY))}): " + "; ".join(bad[:8]) + (" ..." if len(bad) > 8 else ""))
        if c.listing is None:
            out.append(f"{s}: no realized funding loaded")
            continue
        need = t_at(end + DAY)
        if c.st[-1] < need:
            out.append(f"{s}: realized funding ends {_iso(c.st[-1])}, the read needs the settlement at {_iso(need)} "
                       f"(paid by {end})")
        lo = max(c.listing, t_fill(max(start, first)) if first else t_fill(start))
        seq = c.st[bisect.bisect_left(c.st, lo - MAX_FUNDING_STEP):bisect.bisect_right(c.st, need)]
        gaps = [(a, b) for a, b in zip(seq, seq[1:]) if b - a > MAX_FUNDING_STEP]
        if gaps:
            out.append(f"{s}: {len(gaps)} step(s) > 8 h between realized funding settlements in the window: "
                       + "; ".join(f"{_iso(a)} -> {_iso(b)}" for a, b in gaps[:5]))
    return out


def eligible_from(dates):
    """The first fill day with MIN_PRIOR_CLOSES spot closes dated before it, or None
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    return dates[MIN_PRIOR_CLOSES - 1] + DAY if len(dates) >= MIN_PRIOR_CLOSES else None


def _git(*args):
    """(returncode, stdout) of `git -C ROOT <args>`; (None, "") when git cannot run (the guard then refuses)
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md header: committed BEFORE any read)."""
    try:
        p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _git_head():
    """The commit the read runs from, or None (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6; CLAUDE.md
    §46 code version)."""
    rc, out = _git("rev-parse", "HEAD")
    return (out.strip() or None) if rc == 0 else None


def _prereg_text():
    """The committed pre-registration's text (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)."""
    with open(os.path.join(ROOT, PREREG), encoding="utf-8") as fh:
        return fh.read()


def _require_committed(paths):
    """{path: sha256} when every path is tracked by git and has no uncommitted change; SystemExit otherwise
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md header and §6: each read from committed code)."""
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
        raise SystemExit("refusing: a read runs from committed code, tests and pre-registration (nothing computed): "
                         + "; ".join(bad))
    return {p: _sha256(os.path.join(ROOT, p)) for p in paths}


def _guard(after, prior, draws):
    """The registration guard, BEFORE any data is touched: the full placebo, every GUARDED file tracked and clean, the
    pre-registration carrying the implementation addendum PREREG_AMENDMENT, and the --after JSON tracked, clean and written
    under the guard. Returns the sha256 of the guarded files
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md header, §5, §6)."""
    if draws not in (None, PLACEBO_DRAWS):
        raise SystemExit(f"refusing: a registered read uses the pre-registered {PLACEBO_DRAWS} placebo draws (got {draws})")
    committed = _require_committed(list(GUARDED))
    if PREREG_AMENDMENT not in _prereg_text():
        raise SystemExit(f"refusing: {PREREG} lacks the pre-read implementation addendum {PREREG_AMENDMENT} "
                         "(RESOLVED_AMBIGUITIES); commit it, outcome-blind, before any read")
    if after:
        _require_committed([_rel(after)])
        if prior.get("meta", {}).get("guarded") is not True:
            raise SystemExit(f"refusing: {after} was not written under the registration guard")
    return committed


def run(read, out_path, after=None, draws=None, require_clean=True):
    """One pre-registered read (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §5-§7): the registration guard
    (require_clean, the CLI default), data truncated at the read's END, outcome rows for the read's window only, T1-T4 with
    BH, the placebo gate, the label, diagnostics N1-N6. Tests on synthetic files pass require_clean=False."""
    if read not in READS:
        raise SystemExit(f"unknown read {read}")
    prior = json.load(open(after)) if after else None
    k = READS.index(read)
    if read == "discovery" and prior is not None:
        raise SystemExit("--read discovery takes no --after")
    if read != "discovery" and (prior is None or prior.get("meta", {}).get("read") != READS[k - 1]
                                or prior.get("meta", {}).get("script") != SCRIPT):
        raise SystemExit(f"--read {read} needs --after <the {READS[k - 1]} json of {SCRIPT}>")
    committed = _guard(after, prior, draws) if require_clean else None
    head = _git_head()                                          # the code version, fixed before any data is read
    syms = symbols()
    if len(syms) + 1 != PREREG_FAMILY_M:
        raise SystemExit(f"backtested('crypto') = {syms}: the pre-registered BH family is m = {PREREG_FAMILY_M} (T1 + one test "
                         f"per coin); a different coin set is a protocol change")
    start, end = WINDOWS[read]
    coins = {s: load_coin(s, end) for s in syms}
    problems = coverage(coins, start, end)
    if problems:
        raise SystemExit("data not ready for the " + read + " read (nothing computed):\n  " + "\n  ".join(problems))
    try:
        book = _book_daily()                                   # before any outcome: a failure here reads nothing
    except Exception as exc:                                    # noqa: BLE001 -- N5 is outside the BH family
        raise SystemExit(f"N5 book unavailable ({exc!r}); fix it before the read (nothing computed)")
    snap = snapshot(syms)
    grid, arrs = build(coins, end)
    j0, j1 = (start - grid[0]).days, (end - grid[0]).days
    if j0 < 0 or grid[j0] != start:
        raise SystemExit(f"data not ready for the {read} read (nothing computed): the first eligible day {grid[0]} is after "
                         f"the window's first day {start}")
    days = grid[j0:j1 + 1]
    held = held_at(arrs, syms, j0)
    inp = window_inputs(arrs, syms, j0, j1, held)
    cost, cost2 = TAKER + SLIPPAGE, TAKER + 2 * SLIPPAGE
    sim, sim2 = simulate(days, inp, cost), simulate(days, inp, cost2)
    pl = placebo(days, inp, cost, draws)
    tests = []
    reg = regress(sim["r"], sim["bench"])
    tests.append({"id": "T1", "series": "sleeve", "regression": reg, "net": net_line(sim["date"], sim["r"]),
                  "net_mean_2x_slippage": sum(sim2["r"]) / len(sim2["r"]) if sim2["r"] else None,
                  "p_placebo": p_placebo(reg.get("alpha"), pl["sleeve"] if pl else None),
                  "regime": regime(sim["date"], sim["r"], sim["bench"], reg)})
    for n_, s in enumerate(syms, 2):
        c, c2 = sim["coin"][s], sim2["coin"][s]
        rg = regress(c["r"], c["rc"])
        tests.append({"id": f"T{n_}", "series": s, "regression": rg, "net": net_line(c["date"], c["r"]),
                      "net_mean_2x_slippage": sum(c2["r"]) / len(c2["r"]) if c2["r"] else None,
                      "p_placebo": p_placebo(rg.get("alpha"), pl["coins"][s] if pl else None),
                      "first_day": str(c["date"][0]) if c["date"] else None,
                      "regime": regime(c["date"], c["r"], c["rc"], rg)})
    rej = EC.bh([t["regression"].get("p_one_sided") if t["regression"].get("p_one_sided") is not None else 1.0
                 for t in tests], FDR_Q)
    for i, t in enumerate(tests):
        t["bh_rejected"] = i in rej
        t["read_pass"] = read_pass(read, t["regression"], t["net"]["mean"], t["net_mean_2x_slippage"], t["p_placebo"], i in rej)
    hist = dict(prior.get("history", {})) if prior else {}
    t1 = tests[0]
    hist[read] = {"pass": t1["read_pass"], "alpha": reg.get("alpha"), "p_one_sided": reg.get("p_one_sided"),
                  "net": t1["net"]["mean"], "p_placebo": t1["p_placebo"], "regime_driven": t1["regime"]["regime_driven"],
                  "coins": {t["series"]: t["read_pass"] for t in tests[1:]}}
    lab = label(hist)
    flagged = [r for r in READS if r in hist and hist[r].get("regime_driven")]
    if flagged:
        lab += f"; regime-driven ({', '.join(flagged)})"
    promoted = {s: bool(lab.startswith("VALIDATED") and all(hist[r]["coins"].get(s) for r in READS))
                for s in syms} if all(r in hist for r in READS) else {}
    held2 = held_at(arrs, syms, j0, n2=True)
    sim_n2 = simulate(days, window_inputs(arrs, syms, j0, j1, held2), cost, n2=True)
    diag = {"N1": n1_report(syms, grid, arrs, coins, j0, j1, days),
            "N2": n2_report(sim_n2, exit_ratios(arrs, syms, j0, j1)),
            "N3": n3_report(sim, sim2),
            "N4": n4_report(sim["date"], sim["r"], sim["bench"], reg) if reg.get("alpha") is not None else {},
            "N5": n5(sim["date"], sim["r"], book),
            "N6": regress(sim["r"], sim["bench_funded"])}
    win = [(s, j) for s in syms for j in range(j0, j1 + 1) if arrs[s]["elig"][j]]
    fills = collections.Counter(arrs[s]["how0"][j] for s, j in win)
    marks = collections.Counter(arrs[s]["how1"][j] for s, j in win)
    stale = {s: sum(1 for s2, j in win if s2 == s and arrs[s]["stale"][j]) for s in syms}
    fsrc, fmark = collections.Counter(), collections.Counter()
    for s, j in win:
        fsrc.update(arrs[s]["fsrc"][j])
        fmark.update(arrs[s]["fmark"][j])
    res = {"meta": {"script": SCRIPT, "read": read, "preregistration": PREREG,
                    "preregistration_amendment": PREREG_AMENDMENT, "guarded": bool(require_clean),
                    "git_head": head, "committed_sha256": committed,
                    "window": [str(start), str(end)], "window_days": len(days), "symbols": syms,
                    "eligible_from": {s: str(eligible_from(coins[s].dates)) for s in syms},
                    "data_truncated_at": _iso(t_fill(end + DAY)), "pre_window_pnl_computed": False,
                    "params": {"ns": NS, "vol_days": VOL_DAYS, "vol_target": VOL_TARGET, "lev_cap": LEV_CAP,
                               "rebalance_rel": REBALANCE_REL, "taker": TAKER, "slippage": SLIPPAGE,
                               "proxy_rate_8h": PROXY_RATE, "nw_lags": NW_LAGS, "fdr_q": FDR_Q,
                               "placebo_draws": len(pl["k"]) if pl else 0, "placebo_seed": PLACEBO_SEED},
                    "resolved_ambiguities": list(RESOLVED_AMBIGUITIES),
                    "fill_price_lookups": dict(fills), "end_mark_lookups": dict(marks),
                    "funding_mark_lookups": dict(fmark),
                    "stale_signal_days": stale, "funding_settlements_by_source": dict(fsrc),
                    "data": {s: coins[s].info for s in syms},
                    "snapshot": snap,
                    "notes": ["P&L on spot 5m opens before a coin's first perp 5m bar, on perp from it: the one interval that "
                              "spans the switch books the spot/perp basis in the sleeve AND the benchmark; no switch trade "
                              "is charged",
                              "every fill and day mark is the open of a 5m bar starting exactly at 00:05:00 UTC (the read "
                              "refuses otherwise); a funding settlement with no bar at its stamp is marked at the last close "
                              "before it (funding_mark_lookups)",
                              "sizing: units = held weight x the coin's capital BEFORE the fee / P0; the fee is then "
                              "deducted from the coin's cash",
                              "meta.data = facts of the data AFTER truncation at the END; meta.snapshot = the untruncated "
                              "file inventory (identity only)"],
                    "after": after},
           "tests": tests, "bh": {"m": len(tests), "q": FDR_Q, "rejected": sorted(tests[i]["id"] for i in rej)},
           "history": hist, "label": lab, "single_coin_promoted": promoted, "diagnostics": diag,
           "placebo": {"k": pl["k"], "k_coin": pl["k_coin"], "sleeve_alpha": pl["sleeve"],
                       "coin_alpha": pl["coins"]} if pl else None,
           "daily": [{"date": str(d), "r": r, "gross": g, "fees": f, "funding": fu, "bench": b, "bench_funded": bf}
                     for d, r, g, f, fu, b, bf in zip(sim["date"], sim["r"], sim["gross"], sim["fees"], sim["funding"],
                                                       sim["bench"], sim["bench_funded"])]}
    with open(out_path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    for t in tests:
        g = t["regression"]
        print(f"{t['id']} {t['series']:10s} n {g['n']:5d} alpha/yr {_f(g.get('alpha_annual'))} "
              f"p1(NW) {_f(g.get('p_one_sided'))} "
              f"net/day {_f(t['net']['mean'], 6)} 2x {_f(t['net_mean_2x_slippage'], 6)} p_P {_f(t['p_placebo'])} "
              f"BH {'yes' if t['bh_rejected'] else 'no'} pass {t['read_pass']}")
    print(f"label: {lab}\nwrote {out_path}")
    return res


def _f(v, p=4):
    """A number for the console, or n/a (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)."""
    return "n/a" if v is None else f"{v:+.{p}f}"


# ------------------------------------------------------------------------------------------------ dry run (outcome-blind)
def dry_run(out_path):
    """Outcome-blind data QA (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §2, §6): which files exist, bar
    counts, spans, gaps, funding rows, and per read window: readiness (coverage(): exact 00:05 fill bars from eligibility,
    the END mark, the 00:00 settlement after the last day, funding steps, §3 eligibility dates), eligible days, fill-bar
    availability (times only), the END mark, funding settlements by source and by mark kind, and Donchian sub-model
    ENTRY/EXIT counts. No price change, return, P&L or volatility is computed."""
    res = {"meta": {"script": SCRIPT, "mode": "dry-run (outcome-blind)", "preregistration": PREREG,
                    "preregistration_amendment": PREREG_AMENDMENT, "git_head": _git_head(),
                    "symbols": symbols(), "windows": {r: [str(a), str(b)] for r, (a, b) in WINDOWS.items()},
                    "snapshot": snapshot(symbols())},
           "symbols": {}, "reads": {r: {} for r in READS}}
    for s in symbols():
        c = load_coin(s, None)
        rec = dict(c.info)
        rec["first_realized_funding"] = _iso(c.listing) if c.listing else None
        res["symbols"][s] = rec
        first_el = eligible_from(c.dates)
        rec["eligible_from"] = str(first_el) if first_el else None
        rec["eligible_from_preregistered"] = str(ELIGIBLE_FROM[s]) if s in ELIGIBLE_FROM else None
        events = _event_days(c.dates, c.closes)
        for r, (a, b) in WINDOWS.items():
            probs = coverage({s: c}, a, b) if c.dates else [f"{s}: spot 1d missing"]
            w = {"window_days": (b - a).days + 1, "ready": not probs, "problems": probs}
            t_end_mark = t_fill(b + DAY)
            k = bisect.bisect_left(c.T, t_end_mark)
            w["end_mark"] = {"at": _iso(t_end_mark), "exact_bar": bool(k < len(c.T) and c.T[k] == t_end_mark),
                             "last_5m_bar": _iso(c.T[-1]) if len(c.T) else None}
            last = settlements_in(c, t_fill(b), t_fill(b + DAY))
            w["last_day_settlements"] = {"count": len(last), "stamps": [_iso(x[0]) for x in last],
                                         "has_0000_after_last_day": any(x[0] == t_at(b + DAY) for x in last)}
            if first_el:
                lo = max(a, first_el)
                el = [lo + k * DAY for k in range(max(0, (b - lo).days + 1))]
                w["eligible_days"] = len(el)
                how, late = collections.Counter(), []
                for d in el:
                    k = bisect.bisect_left(c.T, t_fill(d))
                    kind = ("exact_0005_bar" if k < len(c.T) and c.T[k] == t_fill(d) else
                            ("later_bar" if k < len(c.T) else "no_bar"))
                    how[kind] += 1
                    if kind != "exact_0005_bar":
                        late.append(f"{d} -> {_iso(c.T[k]) if k < len(c.T) else None}")
                w["fill_bars"] = dict(how)
                w["non_exact_fill_days"] = late[:20]
                src, marks = collections.Counter(), collections.Counter()
                if el:
                    for tau, _r, sname in settlements_in(c, t_fill(el[0]), t_fill(el[-1] + DAY)):
                        src[sname] += 1
                        marks[funding_mark(c, tau)[1]] += 1
                w["funding_settlements"] = dict(src)
                w["funding_mark_lookups"] = dict(marks)
                ent, ext = collections.Counter(), collections.Counter()
                chg = stale = 0
                for d in el:
                    e = events.get(d)
                    if e is None:
                        continue
                    for a_, n in enumerate(NS):
                        ent[n] += e[0] >> a_ & 1
                        ext[n] += e[1] >> a_ & 1
                    chg += bool(e[0] or e[1])
                    stale += e[2]
                w["submodel_entries"] = {str(n): ent[n] for n in NS}
                w["submodel_exits"] = {str(n): ext[n] for n in NS}
                w["signal_change_days"] = chg
                w["stale_signal_days"] = stale
            res["reads"][r][s] = w
    with open(out_path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    for s, rec in res["symbols"].items():
        print(f"{s}: missing {rec['missing'] or 'none'}; spot 1d {rec.get('spot_1d', {}).get('bars')} bars "
              f"{rec.get('spot_1d', {}).get('first')} -> {rec.get('spot_1d', {}).get('last')}; "
              f"eligible from {rec['eligible_from']} (pre-registered {rec['eligible_from_preregistered']})")
    for r in READS:
        for s, w in res["reads"][r].items():
            print(f"  {r:12s} {s}: ready {w['ready']} eligible days {w.get('eligible_days')} "
                  f"entries {sum(w.get('submodel_entries', {}).values())} exits {sum(w.get('submodel_exits', {}).values())} "
                  f"fills {w.get('fill_bars')} END mark exact {w['end_mark']['exact_bar']} "
                  f"last-day settlements {w['last_day_settlements']['count']} funding {w.get('funding_settlements')} "
                  f"marks {w.get('funding_mark_lookups')}")
            for p in w["problems"]:
                print(f"      {p}")
    print(f"wrote {out_path}")
    return res


def _event_days(dates, closes):
    """{fill day: (entered mask, exited mask, stale)} from the signal path -- event counts only
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §3)."""
    sg = coin_signals(dates, closes, with_sigma=False)
    return {d: (e, x, st) for d, e, x, st in zip(sg["days"], sg["entered"], sg["exited"], sg["stale"])}


def main():
    """CLI: run --read {discovery|confirmation|exposed} --out <json> [--after <previous read json>]; dry-run --out <json>
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md §6)."""
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
