#!/usr/bin/env python3
"""Wyckoff re-test, families W, V and L1 (docs/plans/2026-10-04-wyckoff-retest-preregistration.md §3-§6, §7.3, §10 item 3;
written against its -DRAFT): do the book's Wyckoff trades -- the Phase-C Spring/Shakeout, the Phase-D BU/LPS(Y), the same
shake inside a higher-timeframe range, the full campaign -- predict forward return in the book's direction, net of real
FTMO cost, against a placebo with the same trade geometry? Each read ONCE, in order, ONE read per process:

    python3 scripts/research/edge_wyckoff.py counts --out <R0 json>                     # R0: OUTCOME-BLIND counts only
    python3 scripts/research/edge_wyckoff.py run --read R1 --counts <R0 json> --out <dir>/edge-wyckoff-R1.json
    python3 scripts/research/edge_wyckoff.py run --read R1 --perturb P1 --after <dir>/edge-wyckoff-R1.json \
        --out <dir>/edge-wyckoff-R1-P1.json          # P1..P6, each in a fresh process, only if a cell meets §6.2 gates 1-3
    python3 scripts/research/edge_wyckoff.py run --read R2 --after <dir>/edge-wyckoff-R1.json \
        --out <dir>/edge-wyckoff-R2.json                 # R2 / R3 read R1 SURVIVOR cells only
    python3 scripts/research/edge_wyckoff.py run --read R3 --after <dir>/edge-wyckoff-R1.json \
        --out <dir>/edge-wyckoff-R3.json
    python3 scripts/research/edge_wyckoff.py run --read V  --counts <R0 json> --out <dir>/edge-wyckoff-V.json
    python3 scripts/research/edge_wyckoff.py run --read L1 --counts <R0 json> --out <dir>/edge-wyckoff-L1.json
    python3 scripts/research/edge_wyckoff.py forward --cell <cell> --out <dir>/edge-wyckoff-R4-<cell>.json   # from the seal
    python3 scripts/research/edge_wyckoff.py report --out <dir>/edge-wyckoff-report.json            # (+ the .md beside it)

<dir> = docs/experiments/wyckoff-retest-<seal date>, the (committer) date of the commit that ADDS the sealed pre-
registration (the file without -DRAFT). `counts` is outcome-blind and runs BEFORE sealing (its JSON is committed with the
sealed file, which must name its path). Every other command refuses, ALWAYS, unless the sealed pre-registration exists and
is committed, and unless the R0 record passed its truncation probe. Under the guard (the CLI default) every read runs on
the code R0 recorded (`code_sha256` over CODE: the sealed code SHA), from a clean tree, and every prior record it builds
on carries the same code.

Detector DET-PO (§3.1): one window per decision bar k, the WINDOW (backtest-methods WYCKOFF_WINDOW = 300) bars ending at k;
wyckoff_rules.detect_accumulations (longs) / detect_distributions (shorts) on it, pivots from wyckoff_rules.window_pivots of
one series-wide pivot index; P = wyckoff_rules.PARAMS with price_only=True, spring_max_bars_outside=12, every fx_ key off.
Harness gates, fixed: cause (phase_b_tests upper + lower >= 1) and horizontal (sloped False). One event per (symbol,
timeframe, side, absolute SC bar, absolute AR bar) and leg: a later window that re-detects the structure does not fire again.
An event counts only if the server day before its signal bar was dense. Every series (decision and higher timeframe) starts
at its R0 dense start (§4); a read's events are the ones whose ENTRY bar lies in the read's window.

Events (§3.2-§3.6): W-C-long (break s = the record's spring; reclaim r = the first close above tr_lo in [s, s+12]; SPRING iff
r - s <= sob[tf] and the closes below tr_lo in [s, r) are <= (r - s + 1) / 2, else SHAKEOUT; a SPRING signals at r, a
SHAKEOUT at its Test t in (r, r+12] -- L <= tr_lo + TR/3 and close in the upper half -- cancelled by any low below the Spring
low; stop Spring low - 0.05 %, target tr_hi); W-D (bu.bar == k, both paths, both sides; stop Spring low / tr_lo (lps_c) -/+
0.05 %; target = the latest same-side DET-PO record on the HTF prefix knowable at the close of k whose [tr_lo, ceiling + TR]
(short: [ceiling - TR, tr_hi]) contains C[k] and whose target -- C[sos], else tr_hi / tr_lo -- lies beyond the entry; none:
time exit); W-CTX (W-C-long whose signal close an HTF accumulation record contains and no HTF distribution record contains);
W-CAMP (T1 the W-C-long entry, T2 the SPRING's Test, T3 the same structure's W-D long; one stop, the W-D target at T1's
signal close; R = sum(X - e_k) / sum(e_k - stop)); G-C (the plain sweep-and-reclaim control, diagnostic). Entry: the open of
the bar after the signal bar; skipped (and counted) when that open is at or beyond the stop or the target. Walks:
backtest-methods walk() with fx_gap_fill on, mgmt none, stop before target on one bar, cap H = backtest-methods P[tf]["H"].

Measurement (§5): gross R from the walk (planned stop distance, so a gap can lose more than 1R); placebo = up to 200 entry
bars drawn without replacement (seed sha256("WY-P0|sym|tf|signal_time")[:16]) from the same series and read, the same
server-clock slot as the entry bar, previous server day dense, each given the event's stop / target distances in ATR20
multiples (the event's at its signal bar, the placebo's at p-1), the event's side, cap and walk; excess = R - mean(placebo
R), net = excess - cost. Cost: real_costs.cost_r(..., "ftmo_demo_2026_09_relspread", stat) in the server-table hour frame
(asserted before any data is touched), four lines {median, p90 spread} x {today's swap, zero swap}; commission 0/UNKNOWN.
Family V: 12 bp round trip (stress 14 bp) to R through the stop distance, plus realized perp funding (edge_h7x.funding_paid).
Statistics: CR1 by ISO week of the signal bar, Student-t with G-1 df (edge_census.cr1 / t_sf), BH (edge_census.bh), the
one-sided 95 % upper bound with the same SE and t quantile, week-cluster bootstraps (2,000 resamples, fixed seed).

Verdicts (§6.2): R1 SURVIVOR = BH rejection + net > 0 on all four cost lines + breadth (metals and indices each >= 20 events
with net excess > 0) + net excess > 0 in >= 5 of the 6 perturbations; EDGE-CANDIDATE = survivor + R2 pass + no R3 veto;
AGAINST THE BOOK = two-sided p < 0.05 with a negative mean; NO MECHANICAL EDGE = upper bound < DELTA (owner-signed 0.20R) or
AGAINST; INCONCLUSIVE otherwise. Family V: its own BH (EDGE-CANDIDATE / AGAINST THE BOOK / INCONCLUSIVE). L1: one test.

Read-only on repo data. Nothing here touches the fund search, the live path or any account."""
import argparse
import bisect
import collections
import contextlib
import datetime
import functools
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


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


H7 = _load("edge_h7x", "scripts/research/edge_h7x.py")   # Binance loaders, funding, the read-JSON writer; its edge_census
EC = H7.EC                                       # cr1, t_sf, bh, METALS / INDICES / GROUPS (puts scripts/ on sys.path)
import history_store as HS  # noqa: E402
import instruments as I  # noqa: E402
import normalized as _N  # noqa: E402
import real_costs as RC  # noqa: E402
import wyckoff_rules as W  # noqa: E402

PREREG_DRAFT = "docs/plans/2026-10-04-wyckoff-retest-preregistration-DRAFT.md"
PREREG = "docs/plans/2026-10-04-wyckoff-retest-preregistration.md"      # the SEALED file: every read refuses without it
SCRIPT = "scripts/research/edge_wyckoff.py"
TESTS_FILE = "scripts/tests/test_edge_wyckoff.py"
LEDGER = "docs/architecture/research-ledger.json"
ENGINE = "scripts/backtest-methods.py"
REPRICE = "scripts/research/reprice_real_costs.py"                   # L1's config A, exactly as committed (§7.3)
CANONICAL_DIR = "docs/experiments/wyckoff-retest-{seal}"
CANONICAL_OUT = CANONICAL_DIR + "/edge-wyckoff-{name}.json"
ABLATION = "scripts/research/wyckoff_ablation.py"                     # §10 item 4: the same sealed code SHA covers it
#: Every file whose content can change a read of this study (families W and V, L1, the ablation): the two scripts and the
#: §10 item 1 / 5 tests, the engine and EVERY module it, reprice_real_costs and the reused research scripts load (the
#: plain imports are checked against sys.modules at the guard, `_require_code_complete`), and the configs they read.
#: `code_sha256` fingerprints it per file: R0 records it, and every read and record must carry the same one (META_FIXED).
CODE = (SCRIPT, TESTS_FILE, ABLATION, "scripts/tests/test_wyckoff_ablation.py", "scripts/tests/test_wyckoff_price_only.py",
        ENGINE, REPRICE, "scripts/wyckoff_rules.py", "scripts/structures.py", "scripts/real_costs.py",
        "scripts/research/edge_census.py", "scripts/research/edge_h7x.py", "scripts/research/edge_f3.py",
        "scripts/research/edge_f4.py", "scripts/research/book_sim.py", "scripts/research/fvg_book_sim.py",
        "scripts/pit.py", "scripts/normalized.py", "scripts/history_store.py", "scripts/instruments.py",
        "scripts/mt5_time.py", "scripts/live_rules.py", "scripts/ict-scan.py", "scripts/htf_context.py",
        "scripts/automation.py", "scripts/trading_env.py", "scripts/methods.py", "scripts/account_profile.py",
        "scripts/event_risk.py", "scripts/i18n.py", "scripts/performance.py", "scripts/providers.py", "scripts/quality.py",
        "scripts/repo_paths.py", "scripts/research_validity.py", "scripts/risk_model.py", "scripts/sessions.py",
        "scripts/snapshot.py", "scripts/trader_constraints.py", "scripts/trading_system.py",
        "docs/architecture/analysis-params.json", "docs/architecture/instruments.json",
        "docs/architecture/providers.json", "docs/architecture/account-profiles.json", "docs/architecture/i18n.json",
        "docs/architecture/methods.json", "docs/architecture/performance-metrics.json",
        "docs/architecture/research-validity.json", "docs/architecture/risk-config.json",
        "docs/architecture/sessions.json", "docs/architecture/trader-constraints.json",
        "docs/architecture/trading-systems.json")
#: Tracked and clean under the guard. The ledger is not in CODE: other studies append to it between reads.
COMMITTED = (PREREG, LEDGER) + CODE
#: No uncommitted or untracked file anywhere under these (every module and config the engine can reach, the cost tables
#: real_costs reads): an edit outside COMMITTED cannot reach a read either.
CLEAN_TREES = ("scripts", "docs/architecture", "data/history/costs")
UTC = datetime.timezone.utc

# ------------------------------------------------------------------------------------------------ the registered design
TRADEABLE = tuple(EC.METALS) + tuple(EC.INDICES)        # §4 R1 / R3: XAUUSD, XAGUSD; US500, US30, USTEC, DE40, FRA40, AUS200
GROUPS = {g: tuple(s) for g, s in EC.GROUPS.items()}    # §6.2 item 3 breadth: metals / indices
REPLICATION = collections.OrderedDict([("metals", ("XPTUSD", "XPDUSD")), ("US", ("US2000",)), ("EU", ("EU50", "UK100")),
                                       ("Asia", ("JP225", "HK50"))])          # §4 R2 symbols and §4 R2 clusters
EXCLUDED = {"N25": "about 260 bars a month and a 376-day hole from 2022-08-05", "SPN35": "half-session coverage"}
L1_SYMBOLS = tuple(EC.INDICES)                          # §7.3: the 6 indices pooled
L1_DESCRIPTIVE = ("DE40", "US500", "XAUUSD")            # §7.3: reported separately, descriptive
TIMEFRAMES = ("15m", "1H", "4H")
TIMEFRAMES_DESC = ("1D",)                               # §3.7 / §4: 1D descriptive only (R1, never a cell or a pool)
V_TIMEFRAMES = ("15m", "1H")                            # §6.3: 15m and 1H pooled
HIST_ROOT = EC.HIST_ROOT                                # data/history/ftmo
PROVIDER = EC.PROVIDER                                  # mt5_bridge_ftmo: whose server clock (server day, slot)
COST_PROFILE = EC.COST_PROFILE                          # "ftmo_demo_2026_09_relspread" (§5)
HOUR_FRAME = "server_table"                             # RC.HOUR_FRAME every read asserts (§5; erratum 2026-10-04)
DEV_CUTOFF = EC.DEV_CUTOFF                              # "2024-03-01T00:00:00Z": R1 / R2 before it, R3 from it
V_START, V_END = "2017-08-17T00:00:00Z", "2022-08-01T00:00:00Z"   # §4 family V: 2017-08-17 -> 2022-07-31
FRA40_SESSION_CUT = "2024-12-01T00:00:00Z"              # §4 R3: FRA40 rows from 2024-12 are flagged
W_CELLS = ("W-C-long-15m", "W-C-long-1H", "W-C-long-4H", "W-D-15m", "W-D-1H", "W-D-4H", "W-CTX", "W-CAMP")
V_CELLS = ("V1", "V2", "V3", "V4")
NO_EDGE_CELLS = ("W-C-long-15m", "W-C-long-1H", "W-CAMP")   # §6.2 closing rule
GC_CONTRAST = {"W-C-long-15m": "G-C-15m", "W-C-long-1H": "G-C-1H", "W-C-long-4H": "G-C-4H", "W-CTX": "G-C"}
#: §3.6 (sealed 2026-10-04): the attribution control is G-C-known -- a control is excluded only on W-C-long events already
#: signalled at its decision bar r (point in time, CLAUDE.md §8). The literal "+-N bars" reading also excludes on W-C-long
#: breaks AFTER r, i.e. it selects controls with later information; it is reported beside it as a diagnostic only.
GC_CONTRAST_KNOWN = {c: g.replace("G-C", "G-C-known") for c, g in GC_CONTRAST.items()}
ATTR_UNDETERMINED = "UNDETERMINED: G-C not read out (no G-C rows, so no delta)"
COUNT_GATE = 30                                        # §6.1: fewer R1 events -> descriptive (R0 decides)
FDR_Q = 0.10
DELTA = 0.20                                            # §12.4 item 1, owner-signed 2026-10-04: 0.20R net per trade
BREADTH_MIN = 20
PERTURB_NEED = 5
AGAINST_P = 0.05
R2_CLUSTER_MIN, R2_EVALUABLE_MIN, R2_AGREE = 10, 2, 3
L1_P = FORWARD_P = 0.10
FORWARD_EVENTS, FORWARD_MONTHS = 100, 12
CAUSE_MIN = 1                                           # §3.1 cause gate: >= 1 confirmed Phase-B swing in an outer third
TEST_ZONE = 1 / 3                                       # §3.2 Test: L <= tr_lo + TR/3 (= wyckoff_rules test_zone_tr)
GC_RECLAIM = 12                                         # §3.6: s in [r-12, r]
V4_LOOKBACK, V4_MOM, V4_VOL_X, V4_SPACING = 20, 21, 2.0, 20   # §6.3 V4 (effort vs result)
N_PLACEBO, ATR_N, SEED_TAG = 200, 20, "WY-P0"
DENSE_SHARE, DENSE_REF_YEAR, DENSE_LOOKBACK_DAYS, HOLE_DAYS = 0.80, 2023, 60, 7
HOUR_NORM_DAYS = 20                                     # P2 / V4: same-hour median volume over the previous 20 days
TREND_DAYS = 20                                         # §3.7 / §11 item 9: the trend-matched placebo's 20-day trend sign
BOOT_N = 2000
FTMO_LINES = ("median_swap", "median_noswap", "p90_swap", "p90_noswap")
V_LINES = ("base", "stress")
COST_RT, COST_STRESS = H7.COST_RT, H7.COST_STRESS       # 12 bp / 14 bp round trip (edge_h7x)
PROBE_N = 200
HTF_MEMO = 256                                          # speed only: HTF candidate lists kept per series (no effect on output)

#: DET-PO and its six perturbations (§3.1, §6.2 item 4). Each perturbation changes ONE thing and can only veto.
BASE_CFG = dict(window=300, pivot=3, reclaim=12, test_bars=12, cap_mult=1, price_only=True, fx_w123=False, volume="raw")
PERTURBATIONS = collections.OrderedDict([
    ("P1", dict(fx_w123=True, change="fx_w1/w2/w3 on (the owner-adopted fixes)")),
    ("P2", dict(price_only=False, volume="hour_norm",
                change="tick-volume clauses on, tick volume / its trailing 20-day median at the same server hour")),
    ("P3", dict(window=600, change="600-bar window")),
    ("P4", dict(pivot=4, change="pivot 4")),
    ("P5", dict(reclaim=24, change="Shakeout reclaim window 24")),
    ("P6", dict(cap_mult=2, change="time cap 2 x H")),
])
READS = ("R1", "R2", "R3", "V", "L1")
#: (lo, hi) of a read: an event (or placebo) entry bar e belongs to it iff lo <= open(e) and close(e) <= hi.
READ_WINDOWS = {"R1": (None, DEV_CUTOFF), "R2": (None, DEV_CUTOFF), "R3": (DEV_CUTOFF, None), "V": (V_START, V_END)}
#: Compared across a read chain (`_tie`): the registered design AND the code -- a record made by other code is refused.
META_FIXED = ("preregistration", "preregistration_sha256", "symbols", "timeframes", "cells", "parameters", "costs",
              "script_sha256", "code_sha256")
_PROCESS = {"used": None}                               # one read per process (§6.2 item 4, §10)
_ENGINE = {}


# ------------------------------------------------------------------------------------------------ small helpers
def _utc(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))


@functools.lru_cache(maxsize=64)
def _bound(t):
    """A read-window bound (ISO "...Z" or None) as an aware instant, parsed once.
    [prereg §4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return None if t is None else _utc(t)


def _iso(d):
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def _quantile(sorted_xs, q):
    if not sorted_xs:
        return None
    pos = q * (len(sorted_xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _seed(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16], 16)


def week_of(dt):
    """ISO week of a UTC instant, "YYYY-Www": the CR1 / bootstrap cluster.
    [prereg §5 "Statistics": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    y, w, _ = dt.astimezone(UTC).isocalendar()
    return f"{y}-W{w:02d}"


def v_symbols():
    return I.backtested("crypto")


def group_of(sym):
    for g, syms in GROUPS.items():
        if sym in syms:
            return g
    for c, syms in REPLICATION.items():
        if sym in syms:
            return f"replication:{c}"
    return "crypto" if sym in v_symbols() else None


def engine():
    """The backtest-methods module this process walks with, loaded fresh once: walk(), P[tf] (H, sob), STOP_BUFFER_PCT,
    WYCKOFF_WINDOW, HTF_OF -- the engine's own numbers, never restated here.
    [prereg §3.2 "Walk", §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if "bt" not in _ENGINE:
        _ENGINE["bt"] = _load("bt_edge_wyckoff", ENGINE)
    return _ENGINE["bt"]


def htf_of(tf):
    return engine().HTF_OF.get(tf)


# ------------------------------------------------------------------------------------------------ data (counts only)
def load_ftmo(sym, tf, root=HIST_ROOT):
    """(candles, provenance) of one FTMO-Demo series (data/history/ftmo through history_store); ([], ...) when absent.
    [prereg §4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    doc, path = HS.read_doc(sym, tf, root=root)
    if doc is None:
        return [], {"path": None, "bars": 0}
    c = doc["candles"]
    return c, {"path": os.path.relpath(path, ROOT), "source": doc.get("_source"), "server": doc.get("_server"),
               "volume": doc.get("_volume_caveat"), "sha256": HS.digest(sym, tf, root=root), "bars": len(c),
               "first": c[0]["time"] if c else None, "last": c[-1]["time"] if c else None}


def resample(candles, minutes, sub_minutes):
    """Complete UTC-aligned buckets of `minutes` from bars of `sub_minutes` (every sub-bar present, on its grid): first open,
    max high, min low, last close, summed volume. An incomplete bucket is dropped (a hole), never half-filled.
    [prereg §4 family V "resampled from 5m where needed": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    need = minutes // sub_minutes
    out, cur, key = [], [], None
    for c in candles:
        t = _utc(c["time"])
        k = int(t.timestamp()) // (minutes * 60)
        if k != key:
            if cur and len(cur) == need:
                out.append(_bucket(cur, key, minutes))
            cur, key = [], k
        if (int(t.timestamp()) // (sub_minutes * 60)) * sub_minutes * 60 == int(t.timestamp()):
            cur.append(c)
    if cur and len(cur) == need:
        out.append(_bucket(cur, key, minutes))
    return out


def _bucket(cur, key, minutes):
    return {"time": _iso(datetime.datetime.fromtimestamp(key * minutes * 60, UTC)), "open": cur[0]["open"],
            "high": max(c["high"] for c in cur), "low": min(c["low"] for c in cur), "close": cur[-1]["close"],
            "volume": sum(c["volume"] for c in cur)}


def load_binance(sym, tf):
    """(candles, provenance) for family V: edge_h7x.load_candles (spot 5m before 2020-01-01, USDT-M perp 5m from it,
    de-duplicated) with each bar's REAL traded volume joined back by time from the same two files (load_candles keeps OHLC
    only). 15m = resampled from that 5m; 1H = the perp 1h file from 2020-01-01 and resampled spot 5m before; 4H = resampled
    1H. A bar without volume refuses (a missing volume is never zero).
    [prereg §4 family V, §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    five, prov = H7.load_candles(sym)
    vol = {}
    for root, spot in ((H7.SPOT_ROOT, True), (H7.PERP_ROOT, False)):
        doc, _ = HS.read_doc(sym, "5m", root=root)
        for c in (doc or {}).get("candles", ()):
            if (c["time"] < H7.PERP_FROM) == spot:
                vol.setdefault(c["time"], c.get("volume"))
    five = [dict(c, volume=vol.get(c["time"])) for c in five]
    missing = sum(1 for c in five if c["volume"] is None)
    if missing:
        raise SystemExit(f"refusing: {sym} has {missing} 5m bars without volume; family V reads real volume (§6.3)")
    if tf == "15m":
        return resample(five, 15, 5), dict(prov, tf=tf, built="resampled from 5m")
    doc, path = HS.read_doc(sym, "1h", root=H7.PERP_ROOT)
    if doc is None:
        raise SystemExit(f"no perp 1h history for {sym} under {H7.PERP_ROOT}")
    native = [{k: c[k] for k in ("time", "open", "high", "low", "close", "volume")} for c in doc["candles"]
              if c["time"] >= H7.PERP_FROM]
    one = resample([c for c in five if c["time"] < H7.PERP_FROM], 60, 5) + native
    prov = dict(prov, tf=tf, perp_1h={"path": os.path.relpath(path, ROOT),
                                      "sha256": HS.digest(sym, "1h", root=H7.PERP_ROOT)})
    if tf == "1H":
        return one, dict(prov, built="perp 1h from 2020-01-01, spot 5m resampled before")
    if tf == "4H":
        return resample(one, 240, 60), dict(prov, built="resampled from the 1H series")
    raise SystemExit(f"family V has no {tf} series")


def dense_start(sday, dts, ref_year=DENSE_REF_YEAR):
    """§4 dense START on bar COUNTS per server day (no price is read). ref = the median bars per server day over `ref_year`.
    The start is the first month from which every later calendar month (none missing) has a median daily count >=
    DENSE_SHARE x ref, and no hole (consecutive bars more than HOLE_DAYS apart) ends after its first day -- a hole ending
    inside a month restarts the clock at the next month. Returns {"ref_median", "start" ("YYYY-MM-DD" | None), "holes",
    "last_hole_end", "months": {"YYYY-MM": median}}. No `ref_year` bars, or no qualifying month: start None.
    [prereg §4 "Dense-data rule": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    per_day = collections.Counter(sday)
    days = sorted(per_day)
    by_month = collections.defaultdict(list)
    for d in days:
        by_month[(d.year, d.month)].append(per_day[d])
    out = {"ref_median": None, "start": None, "holes": 0, "last_hole_end": None,
           "months": {f"{y:04d}-{m:02d}": statistics.median(v) for (y, m), v in sorted(by_month.items())}}
    ref = [per_day[d] for d in days if d.year == ref_year]
    if not ref:
        return out
    ref_med = statistics.median(ref)
    out["ref_median"] = ref_med
    hole_ends = [sday[j] for j in range(1, len(dts)) if dts[j] - dts[j - 1] > datetime.timedelta(days=HOLE_DAYS)]
    out["holes"] = len(hole_ends)
    last_hole = max(hole_ends) if hole_ends else None
    out["last_hole_end"] = last_hole.isoformat() if last_hole else None
    y, m = days[-1].year, days[-1].month
    first = (days[0].year, days[0].month)
    start = None
    while (y, m) >= first:
        m1 = datetime.date(y, m, 1)
        cnt = by_month.get((y, m))
        if not cnt or statistics.median(cnt) < DENSE_SHARE * ref_med or (last_hole is not None and last_hole > m1):
            break
        start = m1
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    out["start"] = start.isoformat() if start else None
    return out


def dense_days(sday, start):
    """§4 dense DAYS from `start` (point in time): a server day on or after the start is dense iff its bar count >=
    DENSE_SHARE x the median count of the series' days with bars in the previous DENSE_LOOKBACK_DAYS calendar days (its own
    count never enters its reference). Returns (dense set, prev_dense per bar): prev_dense[i] = the series' previous server
    day with bars is dense (edge_census Series.prev_dense) -- what an event may use.
    [prereg §4 "Dense days", "Which events count": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    per_day = collections.Counter(sday)
    days = sorted(per_day)
    dense = set()
    for i, d in enumerate(days):
        if start is None or d < start:
            continue
        lo = bisect.bisect_left(days, d - datetime.timedelta(days=DENSE_LOOKBACK_DAYS))
        prior = [per_day[x] for x in days[lo:i]]
        if prior and per_day[d] >= DENSE_SHARE * statistics.median(prior):
            dense.add(d)
    prev = {d: (days[k - 1] in dense) for k, d in enumerate(days) if k > 0}
    return dense, [prev.get(d, False) for d in sday]


def atr20(H, L, C, n=ATR_N):
    """ATR at bar j = mean true range of bars j-n+1 .. j (the true range needs the previous close, so the first value is at
    j = n); None before. Known at the CLOSE of j.
    [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    tr = [None] + [max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1])) for j in range(1, len(C))]
    return [sum(tr[j - n + 1:j + 1]) / n if j >= n else None for j in range(len(C))]


def hour_reference(dts, V, zone, days=HOUR_NORM_DAYS):
    """Per bar, the median volume of the bars at the SAME clock hour (in `zone`) on the `days` most recent EARLIER days
    that have such bars -- point in time: the bar's own day never enters its own reference; None without history.
    [prereg §6.2 P2, §6.3 V4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    done = collections.defaultdict(collections.deque)
    cur, memo, out = {}, {}, []
    for t, v in zip(dts, V):
        loc = t.astimezone(zone)
        d, h = loc.date(), loc.hour
        c = cur.get(h)
        if c is not None and c[0] != d:
            q = done[h]
            q.append(c)
            if len(q) > days:
                q.popleft()
            c = None
        if c is None:
            c = cur[h] = (d, [])
        if (h, d) not in memo:
            vals = [x for _day, xs in done[h] for x in xs]
            memo[(h, d)] = statistics.median(vals) if vals else None
        out.append(memo[(h, d)])
        c[1].append(v)
    return out


class Series:
    """One (symbol, timeframe) series exactly as a read uses it: cut at its R0 dense start (server day >= `start`) and, for
    a read with an end, at bars whose CLOSE (normalized.available_time) is <= `until`; with the per-bar facts the harness
    reads -- server day and server-clock slot (minute of the day of the bar's OPEN), prev_dense, ATR20, the available
    instants, the volume (raw, or P2's hour-normalised one) and the placebo pools.
    [prereg §4, §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self, sym, tf, candles, zone, start, until=None, venue="ftmo", volume="raw"):
        self.sym, self.tf, self.zone, self.venue, self.start = sym, tf, zone, venue, start
        self.group = group_of(sym)
        self.vkind = "traded" if venue == "binance" else ("tick" if I.is_tick_volume(sym) else "traded")
        self.bar = datetime.timedelta(seconds=_N.tf_seconds(tf))
        lim = _utc(until) if isinstance(until, str) else until
        src, dts, loc = [], [], []
        for c in candles:
            d = _utc(c["time"])
            if lim is not None and d + self.bar > lim:
                break
            x = d.astimezone(zone)
            if start is None or x.date() < start:
                continue
            src.append(c)
            dts.append(d)
            loc.append(x)
        self.src = src
        self.T = [c["time"] for c in src]
        self.O = [c["open"] for c in src]
        self.H = [c["high"] for c in src]
        self.L = [c["low"] for c in src]
        self.C = [c["close"] for c in src]
        self.missing_volume = sum(1 for c in src if c.get("volume") is None)
        raw = [c.get("volume") or 0.0 for c in src]
        self.dt = dts
        self.avail = [d + self.bar for d in dts]
        self.sday = [x.date() for x in loc]
        self.slot = [x.hour * 60 + x.minute for x in loc]
        self.neutral_volume = 0
        if volume == "hour_norm":
            ref = hour_reference(dts, raw, zone)
            self.V = []
            for v, r in zip(raw, ref):
                if r is not None and r > 0:
                    self.V.append(v / r)
                else:
                    self.V.append(1.0)
                    self.neutral_volume += 1
        elif volume == "raw":
            self.V = raw
        else:
            raise SystemExit(f"unknown volume mode {volume!r}")
        self.dense, self.prev_dense = dense_days(self.sday, start)
        self.atr = atr20(self.H, self.L, self.C)
        self._pools = {}
        self._trend = None

    def __len__(self):
        return len(self.C)

    def trend(self, j):
        """Sign (+1 / 0 / -1) of the TREND_DAYS-day trend known at the CLOSE of bar j: C[j] against the close of the latest
        bar that opens at or before dt[j] - TREND_DAYS days; None when the series has no such bar.
        [prereg §3.7 "a placebo matched on the sign of the 20-day trend", §11 item 9:
        docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        if self._trend is None:
            span, out = datetime.timedelta(days=TREND_DAYS), []
            for i, d in enumerate(self.dt):
                j0 = bisect.bisect_right(self.dt, d - span) - 1
                out.append(None if j0 < 0 else (self.C[i] > self.C[j0]) - (self.C[i] < self.C[j0]))
            self._trend = out
        return self._trend[j]

    def in_window(self, i, lo, hi):
        """Bar i of a read whose window is (lo, hi): its OPEN >= lo and its CLOSE <= hi (None = unbounded).
        [prereg §4 "Reads": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        a, b = _bound(lo), _bound(hi)
        return (a is None or self.dt[i] >= a) and (b is None or self.avail[i] <= b)

    def pool(self, slot, lo, hi):
        """Placebo candidate ENTRY bars p of one server-clock slot inside the read's window: previous server day dense,
        ATR20 at p-1 known and > 0.
        [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        key = (lo, hi)
        if key not in self._pools:
            pools = collections.defaultdict(list)
            for p in range(1, len(self.C)):
                a = self.atr[p - 1]
                if self.prev_dense[p] and a is not None and a > 0 and self.in_window(p, lo, hi):
                    pools[self.slot[p]].append(p)
            self._pools[key] = pools
        return self._pools[key].get(slot, [])


def series_zone(venue):
    return UTC if venue == "binance" else RC.server_zone(PROVIDER)[1]


def make_series(sym, tf, loader, dense, cfg, venue="ftmo", until=None):
    """The read's Series for (sym, tf), cut at its R0 dense start; None when R0 found no dense start or no bars.
    [prereg §4 "Dense-data rule": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    ent = dense.get(f"{sym}|{tf}") or {}
    if not ent.get("start"):
        return None
    candles, _prov = loader(sym, tf)
    S = Series(sym, tf, candles, series_zone(venue), datetime.date.fromisoformat(ent["start"]), until=until, venue=venue,
               volume=cfg["volume"])
    return S if len(S) else None


# ------------------------------------------------------------------------------------------------ detection (DET-PO)
def det_params(cfg, family="W"):
    """The per-call copy of wyckoff_rules.PARAMS: DET-PO (family W) -- price_only True, spring_max_bars_outside = the
    reclaim window, every fx_ key off -- with the perturbation's change; family V: the engine's own volume reading
    (price_only off). Nothing global is written.
    [prereg §3.1 "Parameters", §6.2 item 4, §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    fx = bool(cfg["fx_w123"])
    return dict(W.PARAMS, pivot=cfg["pivot"], spring_max_bars_outside=cfg["reclaim"],
                price_only=bool(cfg["price_only"]) if family == "W" else False,
                fx_w1_tr_low_st=fx, fx_w2_st_below_sc=fx, fx_w3_mSOW_spring=fx, fx_w5_vp_abandon=False,
                fx_w4a_linger_closes=None)


def gate(rec):
    """§3.1 harness gates, fixed: the cause gate (>= CAUSE_MIN confirmed Phase-B swings in an outer third of the TR before
    the Phase-C event, the record's phase_b_tests) and the horizontal gate (not sloped).
    [prereg §3.1 "Gates added in the harness": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    t = rec["phase_b_tests"]
    return t["upper"] + t["lower"] >= CAUSE_MIN and not rec["sloped"]


def test_after(H, L, C, r, low, tr_lo, tr, last, bars):
    """The §3.2 Test after a reclaim at r, read bar by bar up to `last`: ("test", q) for the first q in (r, r+bars] with
    L[q] <= tr_lo + TR/3 and C[q] >= (H[q] + L[q]) / 2; ("cancelled", q) when a bar in (r, q] has a low below `low` first;
    ("none", None) when the window passed; ("pending", None) when it has not.
    [prereg §3.2 "Signal bar": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    for q in range(r + 1, min(r + bars, last) + 1):
        if L[q] < low:
            return "cancelled", q
        if L[q] <= tr_lo + TEST_ZONE * tr and C[q] >= (H[q] + L[q]) / 2:
            return "test", q
    return ("none", None) if r + bars <= last else ("pending", None)


def shake(H, L, C, s, tr_lo, tr, last, sob, reclaim, test_bars):
    """§3.2 on one window (long frame; a short is read on the price-inverted arrays): reclaim r = the first bar in [s,
    s+reclaim] closing above tr_lo; SPRING iff r - s <= sob and #{q in [s, r): C[q] < tr_lo} <= (r - s + 1) / 2, typed at
    the CLOSE of r, else SHAKEOUT; spring_low = min L[s..r]; a SPRING signals at r, a SHAKEOUT at its Test. Returns {status:
    signal | pending | no_reclaim | cancelled | no_test, r, type, spring_low, t, signal}.
    [prereg §3.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    r = next((q for q in range(s, min(s + reclaim, last) + 1) if C[q] > tr_lo), None)
    if r is None:
        return {"status": "no_reclaim" if s + reclaim <= last else "pending", "r": None, "type": None}
    d = r - s
    below = sum(1 for q in range(s, r) if C[q] < tr_lo)
    typ = "SPRING" if d <= sob and below <= (d + 1) / 2 else "SHAKEOUT"
    out = {"r": r, "type": typ, "spring_low": min(L[s:r + 1]), "t": None, "signal": None}
    if typ == "SPRING":
        return dict(out, status="signal", signal=r)
    what, q = test_after(H, L, C, r, out["spring_low"], tr_lo, tr, last, test_bars)
    if what == "test":
        return dict(out, status="signal", t=q, signal=q)
    return dict(out, status={"cancelled": "cancelled", "none": "no_test", "pending": "pending"}[what])


def htf_candidate(rec, C, side):
    """(lo, hi, target) of one HTF record (backtest-methods _w7_candidates): [tr_lo, ceiling + TR] for a long, [ceiling -
    TR, tr_hi] for a short (real prices); target = C[sos] when a SOS exists, else tr_hi / tr_lo.
    [prereg §3.3 "Target": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    tr = rec["tr_hi"] - rec["tr_lo"]
    tgt = C[rec["sos"]] if rec["sos"] is not None else (rec["tr_hi"] if side == "long" else rec["tr_lo"])
    return (rec["tr_lo"], rec["ceiling"] + tr, tgt) if side == "long" else (rec["ceiling"] - tr, rec["tr_hi"], tgt)


def target_for(cands, side, entry):
    """The target of the LATEST contained candidate whose target lies beyond the entry; None (time exit) when none does.
    [prereg §3.3 "Target": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    for _lo, _hi, tgt in reversed(cands):
        if (tgt > entry) if side == "long" else (tgt < entry):
            return tgt
    return None


class Htf:
    """DET-PO (with the §3.1 gates) on the higher-timeframe PREFIX knowable at a decision instant: the HTF bars whose close
    (available_time) is <= that instant -- pit.series_as_of's rule, by bisection on a strictly increasing series -- and
    detection re-run on that prefix (wyckoff_rules.prefix_swings over one series-wide swing index, the engine's W7 speed-up).
    Candidates are memoised per (side, prefix length), the HTF_MEMO most recent only (events arrive in time order).
    [prereg §3.3, §3.4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self, S, P):
        self.S, self.P = S, P
        self._idx, self._memo = {}, collections.OrderedDict()

    def prefix_len(self, when):
        return bisect.bisect_right(self.S.avail, when)

    def cands(self, side, m):
        key = (side, m)
        if key in self._memo:
            self._memo.move_to_end(key)
            return self._memo[key]
        S, P, out = self.S, self.P, ()
        if m >= 2 * P["pivot"] + 5:
            idx = self._idx.get(side)
            if idx is None:
                H_, L_ = (S.H, S.L) if side == "long" else ([-x for x in S.L], [-x for x in S.H])
                idx = self._idx[side] = W.swing_prefix_index(H_, L_, P["pivot"], P["downtrend_swings"])
            pre = W.prefix_swings(idx, m)
            if side == "long":
                recs = W.detect_accumulations(S.O[:m], S.H[:m], S.L[:m], S.C[:m], S.V[:m], P=P, volume_kind=S.vkind,
                                              side="long", pre=pre)
            else:
                recs = W.detect_distributions(S.O[:m], S.H[:m], S.L[:m], S.C[:m], S.V[:m], P=P, volume_kind=S.vkind, pre=pre)
            out = tuple(htf_candidate(r, S.C, side) for r in recs if gate(r))
        self._memo[key] = out
        if len(self._memo) > HTF_MEMO:
            self._memo.popitem(last=False)
        return out

    def contained(self, side, when, price):
        return [c for c in self.cands(side, self.prefix_len(when)) if c[0] <= price <= c[1]]


def _inverted(Hw, Lw, Cw):
    return [-x for x in Lw], [-x for x in Hw], [-x for x in Cw]


def window_fire(S, k, cfg, P, sob, pidx=None):
    """(events, logs) of the ONE window ending at decision bar k: every leg whose signal bar is k, before de-duplication and
    before the HTF reads. `pidx` = the series-wide pivot index (wyckoff_rules.pivot_index); None = the detector finds the
    window's pivots itself (the truncation probe uses that path). logs = [(leg, key, status)] for structures whose
    W-C decision ended without a trade (no reclaim, Test cancelled, no Test).
    [prereg §3.1-§3.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    WIN, kp = cfg["window"], P["pivot"]
    a = k - WIN + 1
    if a < 0:
        return [], []
    last = WIN - 1
    Ow, Hw, Lw, Cw, Vw = S.O[a:k + 1], S.H[a:k + 1], S.L[a:k + 1], S.C[a:k + 1], S.V[a:k + 1]
    B = engine().STOP_BUFFER_PCT
    events, logs, inv = [], [], None
    for side in ("long", "short"):
        if side == "long":
            pv = W.window_pivots(pidx, a, WIN, kp) if pidx is not None else None
            recs = W.detect_accumulations(Ow, Hw, Lw, Cw, Vw, P=P, volume_kind=S.vkind, side="long", pivots=pv)
        else:
            pv = W.window_pivots(pidx, a, WIN, kp, swap=True) if pidx is not None else None
            recs = W.detect_distributions(Ow, Hw, Lw, Cw, Vw, P=P, volume_kind=S.vkind, pivots=pv)
        for rec in recs:
            if not gate(rec):
                continue
            key = (side, a + rec["sc"], a + rec["ar"])
            base = {"sym": S.sym, "tf": S.tf, "side": side, "k": k, "e": k + 1, "key": key, "sc": a + rec["sc"],
                    "ar": a + rec["ar"], "tr_lo": rec["tr_lo"], "tr_hi": rec["tr_hi"], "ceiling": rec["ceiling"],
                    "phase_b_tests": dict(rec["phase_b_tests"]), "sloped": rec["sloped"], "path": rec["path"],
                    "vol_type": rec["vol_type"]}
            if rec["bu"] and rec["bu"]["bar"] == last:                 # W-D (§3.3): both paths, both sides
                if rec["path"] == "spring":
                    sb = rec["spring_low"]
                else:
                    sb = rec["tr_lo"] if side == "long" else rec["tr_hi"]
                stop = sb * (1 - B) if side == "long" else sb * (1 + B)
                events.append(dict(base, leg="W-D", stop=stop, target=None, s=None, r=None, t=None, type=None,
                                   spring_low=rec["spring_low"]))
            if rec["path"] != "spring":
                continue
            tr = rec["tr_hi"] - rec["tr_lo"]
            if side == "long":
                st = shake(Hw, Lw, Cw, rec["spring"], rec["tr_lo"], tr, last, sob, cfg["reclaim"], cfg["test_bars"])
            else:                                                      # the mirror, read in the inverted frame
                if inv is None:
                    inv = _inverted(Hw, Lw, Cw)
                st = shake(inv[0], inv[1], inv[2], rec["spring"], -rec["tr_hi"], tr, last, sob, cfg["reclaim"],
                           cfg["test_bars"])
                if st.get("spring_low") is not None:
                    st["spring_low"] = -st["spring_low"]                # back to real prices: the UT high
            if st["status"] in ("no_reclaim", "cancelled", "no_test"):
                logs.append(("W-C" if side == "long" else "W-C-short", key, st["status"]))
            if st.get("r") is None:
                continue
            sl = st["spring_low"]
            wc = dict(base, s=a + rec["spring"], r=a + st["r"], t=a + st["t"] if st["t"] is not None else None,
                      type=st["type"], spring_low=sl, stop=sl * (1 - B) if side == "long" else sl * (1 + B),
                      target=rec["tr_hi"] if side == "long" else rec["tr_lo"])
            if st["status"] == "signal" and st["signal"] == last:
                events.append(dict(wc, leg="W-C" if side == "long" else "W-C-short"))
            if side == "long" and st["type"] == "SHAKEOUT" and st["r"] == last:     # §3.7: the Shakeout at its reclaim
                events.append(dict(wc, leg="W-C-SOR", t=None))
    return events, logs


def enrich(ev, S, htf):
    """The HTF reads at the signal CLOSE (§3.3, §3.4): `htf_cands` = the same-side candidates containing C[k] (a W-D target,
    and a W-C long's W-CAMP target) in detection order; `ctx` (W-C long) = an HTF accumulation contains C[k] and no HTF
    distribution does. Without an HTF series: no candidates, ctx False, flagged.
    [prereg §3.3-§3.5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    k = ev["k"]
    when, px = S.avail[k], S.C[k]
    if htf is None:
        ev["htf_cands"], ev["ctx"], ev["no_htf"] = [], False, True
        return ev
    if ev["leg"] == "W-D":
        ev["htf_cands"] = [list(c) for c in htf.contained(ev["side"], when, px)]
    elif ev["leg"] == "W-C":
        acc = htf.contained("long", when, px)
        ev["htf_cands"] = [list(c) for c in acc]
        ev["ctx"] = bool(acc) and not htf.contained("short", when, px)
    return ev


def detect_series(S, cfg, P, sob, htf=None):
    """Every DET-PO event of one series, window by window (k from WINDOW-1 to the last bar), de-duplicated per leg on (side,
    absolute SC, absolute AR), then enriched with the HTF reads. Returns {leg: [events]} and "logs" (Counter of logged
    no-trade W-C decisions, once per structure).
    [prereg §3.1 "De-duplication", §3.2-§3.4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    pidx = W.pivot_index(S.H, S.L, P["pivot"])
    seen = collections.defaultdict(set)
    out = {"W-C": [], "W-C-short": [], "W-C-SOR": [], "W-D": [], "logs": collections.Counter()}
    logged = set()
    for k in range(cfg["window"] - 1, len(S)):
        evs, logs = window_fire(S, k, cfg, P, sob, pidx)
        for ev in evs:
            if ev["key"] in seen[ev["leg"]]:
                continue
            seen[ev["leg"]].add(ev["key"])
            out[ev["leg"]].append(enrich(ev, S, htf))
        for leg, key, status in logs:
            if (leg, key) not in logged and key not in seen[leg]:
                logged.add((leg, key))
                out["logs"][f"{leg}|{status}"] += 1
    return out


def campaigns(S, wc_long, wd, cfg):
    """W-CAMP structures (§3.5): one per W-C-long event. Tranche signals: T1 = the W-C-long signal; T2 (SPRING only) = the
    §3.2 Test within cfg test_bars bars of r (read bar by bar, cancelled by a low below the Spring low); T3 = the W-D long
    event of the same structure (same key) after T1. Each tranche enters at the open after its signal bar.
    [prereg §3.5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    by_key = {ev["key"]: ev for ev in wd if ev["side"] == "long"}
    out = []
    for ev in wc_long:
        tr = [("T1", ev["k"])]
        if ev["type"] == "SPRING":
            what, q = test_after(S.H, S.L, S.C, ev["r"], ev["spring_low"], ev["tr_lo"], ev["tr_hi"] - ev["tr_lo"],
                                 len(S) - 1, cfg["test_bars"])
            if what == "test":
                tr.append(("T2", q))
        d = by_key.get(ev["key"])
        if d is not None and d["k"] > ev["k"]:
            tr.append(("T3", d["k"]))
        tr.sort(key=lambda x: x[1])
        out.append(dict(ev, leg="W-CAMP", tranches=[[name, k, k + 1] for name, k in tr]))
    return out


def gc_events(S, N, wc_breaks, wc_known=None):
    """G-C (§3.6), the plain sweep-and-reclaim control, long: a break bar s with L[s] < l_s = min L[s-N, s); the control
    fires at r = the first bar in [s, s+GC_RECLAIM] closing above l_s (for one r, the earliest such s); excluded when any
    W-C-long event of the series has its break bar within +-N bars of s; at most one per N bars (r - previous r >= N).
    Stop min L[s..r] - 0.05 %, target max H[s-N, s). The exclusion reads every W-C-long event of the series (a sample
    definition, disclosed: not a decision input) -- so it also reads W-C breaks AFTER r, i.e. later bars.
    `wc_known` = [(break bar, signal bar)] of the same W-C-long events: when given, also the diagnostic variant "known"
    whose exclusion reads only the W-C-long events already signalled at r (signal bar <= r), with its own spacing.
    Each event lists the variants it belongs to in "gc" ("literal" = §3.6 as written; "known"); stats count each
    variant's exclusions (the known variant's keys prefixed "known:").
    [prereg §3.6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    n, B = len(S), engine().STOP_BUFFER_PCT
    out, stats = [], collections.Counter()
    if N is None or N < 1 or n <= N:
        return out, stats
    ell = [None] * n
    dq = collections.deque()
    for s in range(n):
        if s >= N:
            while dq and dq[0] < s - N:
                dq.popleft()
            ell[s] = S.L[dq[0]]
        while dq and S.L[dq[-1]] >= S.L[s]:
            dq.pop()
        dq.append(s)
    first = {}
    for s in range(N, n):
        if S.L[s] < ell[s]:
            q = next((q for q in range(s, min(s + GC_RECLAIM, n - 1) + 1) if S.C[q] > ell[s]), None)
            if q is not None and q not in first:
                first[q] = s
    breaks = sorted(wc_breaks)

    def literal(s, r):
        j = bisect.bisect_left(breaks, s - N)
        return j < len(breaks) and breaks[j] <= s + N

    rules = [("literal", "", literal)]
    if wc_known is not None:
        kb = sorted(wc_known)

        def known(s, r):
            for b, k in kb[bisect.bisect_left(kb, (s - N,)):]:
                if b > s + N:
                    return False
                if k <= r:
                    return True
            return False
        rules.append(("known", "known:", known))
    member = collections.defaultdict(list)
    for name, tag, excluded in rules:
        last_r = None
        for r in sorted(first):
            s = first[r]
            if excluded(s, r):
                stats[tag + "excluded_wc_within_N"] += 1
                continue
            if last_r is not None and r - last_r < N:
                stats[tag + "spaced_out"] += 1
                continue
            last_r = r
            member[r].append(name)
    for r in sorted(member):
        s = first[r]
        out.append({"leg": "G-C", "sym": S.sym, "tf": S.tf, "side": "long", "k": r, "e": r + 1, "s": s,
                    "key": ("long", s, r), "gc": member[r],
                    "stop": min(S.L[s:r + 1]) * (1 - B), "target": max(S.H[s - N:s]), "type": None, "path": None})
    return out, stats


def v4_events(S):
    """V4, effort vs result (§6.3): long at bar i when C[i-1] < C[i-21], V[i] >= 2 x the median volume of the same UTC hour
    over the previous 20 days, range(i) <= the median range of the previous 20 bars and C[i] > min C[i-20, i); shorts
    mirrored; at most one per 20 bars per side. Stop L[i] - 0.05 % (short H[i] + 0.05 %), no target, time exit at H.
    [prereg §6.3 V4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    B = engine().STOP_BUFFER_PCT
    ref = hour_reference(S.dt, S.V, UTC)
    out, last = [], {"long": None, "short": None}
    for i in range(V4_MOM, len(S) - 1):
        if ref[i] is None or S.V[i] < V4_VOL_X * ref[i]:
            continue
        if S.H[i] - S.L[i] > statistics.median(S.H[j] - S.L[j] for j in range(i - V4_LOOKBACK, i)):
            continue
        prior = S.C[i - V4_LOOKBACK:i]
        for side, ok in (("long", S.C[i - 1] < S.C[i - V4_MOM] and S.C[i] > min(prior)),
                         ("short", S.C[i - 1] > S.C[i - V4_MOM] and S.C[i] < max(prior))):
            if ok and (last[side] is None or i - last[side] >= V4_SPACING):
                last[side] = i
                stop = S.L[i] * (1 - B) if side == "long" else S.H[i] * (1 + B)
                out.append({"leg": "V4", "sym": S.sym, "tf": S.tf, "side": side, "k": i, "e": i + 1, "key": (side, i),
                            "stop": stop, "target": None, "type": None, "path": None})
    return out


def kept(S, ev, lo, hi):
    """An event counts in a read iff its entry bar exists and lies in the read's window and the server day before its signal
    bar was dense. [prereg §4 "Which events count": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    e = ev["e"]
    return e < len(S) and S.prev_dense[ev["k"]] and S.in_window(e, lo, hi)


def series_events(S, htf, cfg, family="W", gc_n=None):
    """{leg: [events]} of one series: DET-PO legs, W-CAMP, G-C (family W, when N is known) and V4 (family V), before the
    read's window and dense filters. [prereg §3, §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    P = det_params(cfg, family)
    out = detect_series(S, cfg, P, engine().P[S.tf]["sob"], htf)
    out["W-CAMP"] = campaigns(S, out["W-C"], out["W-D"], cfg) if family == "W" else []
    out["G-C"], out["gc_stats"] = (gc_events(S, gc_n.get(S.tf), [e["s"] for e in out["W-C"]],
                                             [(e["s"], e["k"]) for e in out["W-C"]])
                                   if family == "W" and gc_n else ([], collections.Counter()))
    out["V4"] = v4_events(S) if family == "V" else []
    return out


# ------------------------------------------------------------------------------------------------ outcomes (a read only)
@contextlib.contextmanager
def walk_opts(bt, flatten=False):
    """bt.OPTS = the frozen baseline + fx_gap_fill on, mgmt none, no flatten (§3.2 "Walk") for the block: walk() reads it.
    `flatten` = the §3.7 descriptive variant: flat_before_rollover on the FTMO server's own rollover.
    [prereg §3.2 "Walk", §3.7 "Variants": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    saved = bt.OPTS
    bt.OPTS = dict(bt._OPTS_BASE, fx_gap_fill=True, mgmt="none", flat_before_rollover=bool(flatten),
                   rollover_provider=PROVIDER if flatten else None)
    try:
        yield
    finally:
        bt.OPTS = saved


def walk_from(bt, side, entry, stop, target, S, e, HZ):
    """backtest-methods walk() for a trade filled at the OPEN of bar e, walked on the arrays starting AT e (so the bar it was
    filled on is walked, and walk()'s "filled at the previous close" pre-check never applies). target None = stop and cap
    only. Returns walk()'s dict with an absolute `exit`, or None (no risk).
    [prereg §3.2 "Walk": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    tgt = target if target is not None else (math.inf if side == "long" else -math.inf)
    w = bt.walk(side, entry, stop, tgt, S.H[e:e + HZ], S.L[e:e + HZ], S.C[e:e + HZ], 0, HZ, Tm=S.T[e:e + HZ],
                O_=S.O[e:e + HZ])
    return dict(w, exit=w["exit"] + e) if w else None


def placeable(side, entry, stop, target):
    """True iff the entry open lies strictly between the stop and the target (target None: beyond the stop only).
    [prereg §3.2 "Skips": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if side == "long":
        return stop < entry and (target is None or entry < target)
    return entry < stop and (target is None or target < entry)


def placebo_draw(S, pool, signal_time, n=N_PLACEBO):
    """Up to `n` entry bars from `pool`, without replacement (every one when fewer), seeded by sha256("WY-P0|sym|tf|
    signal_time")[:16] -- the same draw for the same event in every read and perturbation.
    [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if len(pool) <= n:
        return list(pool)
    return sorted(random.Random(_seed(SEED_TAG, S.sym, S.tf, signal_time)).sample(pool, n))


class Pricer:
    """The cost lines of one venue, in R. FTMO: real_costs.cost_r(entry, stop, entry time, exit time, sym, side, the
    relspread profile, stat) at entry and exit bar times (the engine's convention), four lines {median, p90} x {today's swap,
    zero swap = total - swap_R}. Binance: 12 bp (stress 14 bp) round trip x entry / |entry - stop| plus realized perp funding
    over [entry, exit) in the same units (edge_h7x.funding_paid; a gap fills at the bar's open, a touch or time exit after
    it).
    [prereg §5 "Cost (FTMO)", "Cost (Binance, family V)": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self, venue, cost_r=None, funding=None):
        self.venue = venue
        self.lines = V_LINES if venue == "binance" else FTMO_LINES
        self.primary = self.lines[0]
        self.cost_r = cost_r or RC.cost_r
        self.funding = funding or {}

    def ftmo(self, sym, side, entry, stop, t_in, t_out):
        out = {}
        for stat in ("median", "p90"):
            c = self.cost_r(entry, stop, t_in, t_out, sym, side, COST_PROFILE, stat)
            out[f"{stat}_swap"] = c["total_R"]
            out[f"{stat}_noswap"] = c["total_R"] - c["swap_R"]
        return out

    def binance(self, S, side, entry, stop, e, end):
        dist = abs(entry - stop)
        fund, _n = H7.funding_paid(S, +1 if side == "long" else -1, e, end, self.funding.get(S.sym))
        if fund is None:
            return None
        f = fund * entry / dist
        return {"base": COST_RT * entry / dist + f, "stress": COST_STRESS * entry / dist + f}

    def trade(self, S, side, entry, stop, e, x, outcome):
        if self.venue != "binance":
            return self.ftmo(S.sym, side, entry, stop, S.T[e], S.T[x])
        gap = outcome == "loss" and ((S.O[x] < stop) if side == "long" else (S.O[x] > stop))
        return self.binance(S, side, entry, stop, e, S.dt[x] if gap else S.dt[x] + S.bar)


def score(bt, S, ev, HZ, pricer, lo, hi, target=None, trend=False):
    """(row, None) or (None, skip reason) for one single-entry event: entry O[e], the placeability skip, gross R from the
    walk, the cost lines and the ATR-multiple placebo. A W-D target is chosen here, at the fill (§3.3 "beyond the entry").
    `trend` (R1, descriptive): also the trend-matched placebo -- the drawn placebo bars p whose 20-day trend sign at p-1
    equals the event's at its signal bar k (a uniform draw of the matched sub-pool; no extra walk): placebo_trend,
    n_placebo_trend, excess_trend (None when none matches).
    [prereg §3.2, §3.3, §3.7, §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    k, e, side = ev["k"], ev["e"], ev["side"]
    if e >= len(S):
        return None, "no_next_bar"
    entry, stop = S.O[e], ev["stop"]
    tgt = target if target is not None else (target_for(ev.get("htf_cands") or [], side, entry) if ev["leg"] == "W-D"
                                             else ev.get("target"))
    if not placeable(side, entry, stop, tgt):
        return None, "entry_beyond_stop_or_target"
    a = S.atr[k]
    if a is None or a <= 0:
        return None, "no_atr"
    w = walk_from(bt, side, entry, stop, tgt, S, e, HZ)
    if w is None:
        return None, "no_risk"
    cost = pricer.trade(S, side, entry, stop, e, w["exit"], w["outcome"])
    if cost is None:
        return None, "no_funding_coverage"
    d_stop = abs(entry - stop) / a
    d_tgt = abs(tgt - entry) / a if tgt is not None else None
    sgn = 1 if side == "long" else -1
    prs, ptr = [], []
    tk = S.trend(k) if trend else None
    for p in placebo_draw(S, S.pool(S.slot[e], lo, hi), S.T[k]):
        ap, ent = S.atr[p - 1], S.O[p]
        wp = walk_from(bt, side, ent, ent - sgn * d_stop * ap, ent + sgn * d_tgt * ap if d_tgt is not None else None,
                       S, p, HZ)
        if wp is not None:
            prs.append(wp["R"])
            if tk is not None and S.trend(p - 1) == tk:
                ptr.append(wp["R"])
    if not prs:
        return None, "no_placebo"
    plc = sum(prs) / len(prs)
    excess = w["R"] - plc
    extra = {}
    if trend:
        pt = sum(ptr) / len(ptr) if ptr else None
        extra = dict(trend=tk, placebo_trend=pt, n_placebo_trend=len(ptr),
                     excess_trend=w["R"] - pt if pt is not None else None)
    return _row(S, ev, entry=entry, target=tgt, entry_time=S.T[e], exit_time=S.T[w["exit"]], R=w["R"],
                outcome=w["outcome"], bars_held=w["bars_held"], truncated=e + HZ > len(S) and w["outcome"] == "timeout",
                R_planned=abs(tgt - entry) / abs(entry - stop) if tgt is not None else None, atr=a, stop_atr=d_stop,
                target_atr=d_tgt, placebo=plc, n_placebo=len(prs), excess=excess, cost=cost,
                net_excess=excess - cost[pricer.primary], **extra), None


def _row(S, ev, **kw):
    k = ev["k"]
    row = {"symbol": S.sym, "tf": S.tf, "group": S.group, "leg": ev["leg"], "side": ev["side"], "type": ev.get("type"),
           "path": ev.get("path"), "signal_time": S.T[k], "week": week_of(S.dt[k]), "stop": ev["stop"],
           "ctx": ev.get("ctx"), "vol_type": ev.get("vol_type"), "flag": None}
    if S.sym == "FRA40" and S.T[k] >= FRA40_SESSION_CUT:
        row["flag"] = "fra40_session_cut"
    row.update(kw)
    return row


def campaign_walk(S, stop, target, tranches, HZ):
    """The W-CAMP walk (§3.5), backtest-methods walk()'s per-bar rules for several entries: bar by bar from T1's entry bar,
    a pending tranche fills at its entry bar's OPEN unless that open is at or beyond the stop or the target (skipped); then
    the stop (a bar opening beyond it fills at its open, fx_gap_fill), then the target (at its own price), then the cap --
    H bars after the LAST filled tranche, at that bar's close. Returns {"filled": [[e, price]], "skipped": [e], "exit",
    "X", "outcome"}, or None when T1 cannot fill.
    [prereg §3.5 "Shared exits", "Order of events": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    n = len(S)
    pend = sorted(tranches)
    e1 = pend[0]
    if e1 >= n or not placeable("long", S.O[e1], stop, target):
        return None
    filled, skipped, cap = [], [], None
    for j in range(e1, n):
        while pend and pend[0] == j:
            pend.pop(0)
            o = S.O[j]
            if placeable("long", o, stop, target):
                filled.append([j, o])
                cap = j + HZ - 1
            else:
                skipped.append(j)
        if S.L[j] <= stop:
            X = S.O[j] if S.O[j] < stop else stop
            return {"filled": filled, "skipped": skipped, "exit": j, "X": X, "outcome": "loss"}
        if target is not None and S.H[j] >= target:
            return {"filled": filled, "skipped": skipped, "exit": j, "X": target, "outcome": "win"}
        if j >= cap or j == n - 1:
            return {"filled": filled, "skipped": skipped, "exit": j, "X": S.C[j], "outcome": "timeout"}
    return None


def campaign_R(filled, X, stop):
    """R = sum_k (X - e_k) / sum_k (e_k - stop) over the filled tranches (§3.5 "Score").
    [prereg §3.5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return sum(X - p for _e, p in filled) / sum(p - stop for _e, p in filled)


def campaign_cost(costs, filled, stop, lines):
    """Cost = sum_k cost_k x (e_k - stop) / sum_k (e_k - stop), per cost line (§3.5 "Score").
    [prereg §3.5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    den = sum(p - stop for _e, p in filled)
    return {ln: sum(c[ln] * (p - stop) for c, (_e, p) in zip(costs, filled)) / den for ln in lines}


def score_campaign(S, ev, HZ, pricer, lo, hi):
    """(row, None) or (None, skip reason) for one W-CAMP structure: the campaign walk, R and cost aggregated over the filled
    tranches, and a placebo campaign at each placebo bar with the event's FILLED tranche offsets, its stop and W-D target in
    ATR multiples of T1's entry (ATR20 at T1's signal bar / at p-1).
    [prereg §3.5, §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    k, e1 = ev["k"], ev["e"]
    if e1 >= len(S):
        return None, "no_next_bar"
    entry, stop = S.O[e1], ev["stop"]
    tgt = target_for(ev.get("htf_cands") or [], "long", entry)
    if not placeable("long", entry, stop, tgt):
        return None, "entry_beyond_stop_or_target"
    a = S.atr[k]
    if a is None or a <= 0:
        return None, "no_atr"
    w = campaign_walk(S, stop, tgt, [t[2] for t in ev["tranches"]], HZ)
    if w is None:
        return None, "no_fill"
    R = campaign_R(w["filled"], w["X"], stop)
    costs = [pricer.trade(S, "long", p, stop, eb, w["exit"], w["outcome"]) for eb, p in w["filled"]]
    cost = campaign_cost(costs, w["filled"], stop, pricer.lines)
    offs = [eb - e1 for eb, _p in w["filled"]]
    d_stop = (entry - stop) / a
    d_tgt = (tgt - entry) / a if tgt is not None else None
    prs = []
    for p in placebo_draw(S, S.pool(S.slot[e1], lo, hi), S.T[k]):
        ap, ent = S.atr[p - 1], S.O[p]
        pst = ent - d_stop * ap
        wp = campaign_walk(S, pst, ent + d_tgt * ap if d_tgt is not None else None, [p + o for o in offs], HZ)
        if wp is not None and wp["filled"]:
            prs.append(campaign_R(wp["filled"], wp["X"], pst))
    if not prs:
        return None, "no_placebo"
    plc = sum(prs) / len(prs)
    excess = R - plc
    return _row(S, ev, entry=entry, target=tgt, entry_time=S.T[e1], exit_time=S.T[w["exit"]], R=R, outcome=w["outcome"],
                bars_held=w["exit"] - e1 + 1, tranches=[[t[0], t[2]] for t in ev["tranches"]], filled=w["filled"],
                skipped_tranches=w["skipped"], R_planned=(tgt - entry) / (entry - stop) if tgt is not None else None,
                atr=a, stop_atr=d_stop, target_atr=d_tgt, placebo=plc, n_placebo=len(prs), excess=excess, cost=cost,
                net_excess=excess - cost[pricer.primary]), None


# ------------------------------------------------------------------------------------------------ cells
def cells_of(ev, family="W"):
    """The cells one event's row belongs to (§6.1, §6.3; descriptive cells carry a "|" or a "desc:" prefix).
    [prereg §3.7, §6.1, §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    leg, tf = ev["leg"], ev["tf"]
    if family == "V":
        if leg == "W-C":                                 # V3's two arms are counted (R0), never scored as cells
            vt = ev.get("vol_type")
            return ["V1"] + (["V3:type1"] if vt == 1 else ["V3:type23"] if vt in (2, 3) else [])
        return {"W-D": ["V2"], "V4": ["V4"]}.get(leg, [])
    desc = tf in TIMEFRAMES_DESC                         # 1D: descriptive cells only, never pooled into W-CTX / W-CAMP
    if leg == "W-C":
        out = [("desc:" if desc else "") + f"W-C-long-{tf}", f"desc:W-C-long-{tf}|{ev['type']}"]
        return out + (["W-CTX"] if ev.get("ctx") and not desc else [])
    if leg == "W-D":
        return [("desc:" if desc else "") + f"W-D-{tf}"]
    if leg == "W-CAMP":
        return [f"desc:W-CAMP-{tf}"] if desc else ["W-CAMP"]
    if leg == "G-C":
        sets = ev.get("gc", ("literal",))
        return (([f"G-C-{tf}", "G-C"] if "literal" in sets else [])
                + ([f"G-C-known-{tf}", "G-C-known"] if "known" in sets else []))
    if leg == "W-C-short":
        return [f"desc:W-C-short-{tf}"]
    if leg == "W-C-SOR":
        return [f"desc:W-C-long-{tf}|SHAKEOUT@reclaim"]
    return []


def summarise(rows, lines, primary=None):
    """One cell: n, weeks, mean gross R, mean placebo R, mean excess and, per cost line, the mean net excess with its CR1-by-
    ISO-week SE, Student-t with G-1 df, one- and two-sided p and the one-sided 95 % upper bound (same SE, t quantile).
    [prereg §5 "Statistics", §6.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    primary = primary or lines[0]
    if not rows:
        return {"n": 0}
    wk = [r["week"] for r in rows]
    out = {"n": len(rows), "weeks": len(set(wk)), "mean_R": _mean(r["R"] for r in rows),
           "mean_placebo_R": _mean(r["placebo"] for r in rows), "mean_excess": _mean(r["excess"] for r in rows),
           "lines": {}}
    for line in lines:
        mu, se, df = EC.cr1([r["excess"] - r["cost"][line] for r in rows], wk)
        t = mu / se if se else None
        p1 = EC.t_sf(t, df) if t is not None else 1.0
        tq = t_quantile(0.95, df) if se else None
        out["lines"][line] = {"mean": mu, "se": se, "df": df, "t": t, "p_one_sided": p1,
                              "p_two_sided": 2 * min(p1, 1 - p1) if t is not None else 1.0,
                              "upper_95": mu + tq * se if tq is not None else None}
    pl = out["lines"][primary]
    out.update(net_excess=pl["mean"], p_one_sided=pl["p_one_sided"], p_two_sided=pl["p_two_sided"], upper_95=pl["upper_95"])
    return out


def t_quantile(q, df):
    """t with P(T <= t) = q for Student-t with df degrees of freedom (bisection on edge_census.t_sf); None when df <= 0.
    [prereg §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if df is None or df <= 0:
        return None
    lo, hi = 0.0, 1.0
    while EC.t_sf(hi, df) > 1 - q and hi < 1e6:
        hi *= 2
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if EC.t_sf(mid, df) > 1 - q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def by(rows, key, lines):
    acc = collections.defaultdict(list)
    for r in rows:
        acc[r[key]].append(r)
    return {k: summarise(v, lines) for k, v in sorted(acc.items(), key=lambda kv: str(kv[0]))}


def week_bootstrap(a_rows, b_rows, val, seed, n=BOOT_N):
    """mean(a) - mean(b) of `val` and its one-sided p (the share of resamples <= 0) and 90 % interval over `n` resamples of
    whole ISO weeks drawn from the union of both sets' weeks (each draw takes both sets' events of the drawn weeks; a draw
    with an empty side is not used). Fixed seed.
    [prereg §3.6 "Attribution", §5 "Statistics", §6.3 V3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    a = [(r["week"], val(r)) for r in a_rows]
    b = [(r["week"], val(r)) for r in b_rows]
    if not a or not b:
        return {"diff": None, "p_one_sided": None, "ci90": None, "n_a": len(a), "n_b": len(b)}
    sums = collections.defaultdict(lambda: [0.0, 0, 0.0, 0])
    for w, v in a:
        sums[w][0] += v
        sums[w][1] += 1
    for w, v in b:
        sums[w][2] += v
        sums[w][3] += 1
    rows = [sums[w] for w in sorted(sums)]
    rnd = random.Random(seed)
    diffs = []
    for _ in range(n):
        sa = na = sb = nb = 0
        for x in rnd.choices(rows, k=len(rows)):
            sa += x[0]
            na += x[1]
            sb += x[2]
            nb += x[3]
        if na and nb:
            diffs.append(sa / na - sb / nb)
    diffs.sort()
    return {"diff": _mean(v for _, v in a) - _mean(v for _, v in b),
            "p_one_sided": sum(1 for d in diffs if d <= 0) / len(diffs) if diffs else None,
            "ci90": [_quantile(diffs, 0.05), _quantile(diffs, 0.95)] if diffs else None,
            "n_a": len(a), "n_b": len(b), "weeks": len(rows), "resamples_used": len(diffs)}


def w_test(cell, rows, confirmatory, lines=FTMO_LINES):
    """One family-W cell of a read: the pooled summary, the metals / indices breadth groups, per-symbol tables
    (descriptive) and whether it is confirmatory (R0's count gate).
    [prereg §6.1, §6.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return {"cell": cell, "confirmatory": confirmatory, "summary": summarise(rows, lines),
            "groups": by(rows, "group", lines), "per_symbol": by(rows, "symbol", lines)}


def r1_verdicts(tests, delta=DELTA):
    """Gates 1-3 of §6.2 per confirmatory cell (BH at FDR_Q over the confirmatory cells on the primary one-sided p; net > 0
    on all four cost lines; breadth: metals and indices each >= BREADTH_MIN events with net excess > 0), and the labels
    that need no other read: AGAINST THE BOOK (two-sided p < AGAINST_P, negative), below_delta (upper bound < delta).
    [prereg §6.1, §6.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    conf = [c for c in W_CELLS if tests.get(c, {}).get("confirmatory")]
    ps = [tests[c]["summary"].get("p_one_sided", 1.0) if tests[c]["summary"].get("n") else 1.0 for c in conf]
    rej = EC.bh(ps, FDR_Q) if conf else set()
    for j, c in enumerate(conf):
        s, g = tests[c]["summary"], tests[c]["groups"]
        n = s.get("n", 0)
        lines_pos = bool(n) and all((s["lines"][ln]["mean"] or 0) > 0 for ln in FTMO_LINES)
        gm, gi = g.get("metals", {"n": 0}), g.get("indices", {"n": 0})
        meetable = gm.get("n", 0) >= BREADTH_MIN and gi.get("n", 0) >= BREADTH_MIN
        breadth = meetable and gm["net_excess"] > 0 and gi["net_excess"] > 0
        against = bool(n) and s["net_excess"] < 0 and s["p_two_sided"] < AGAINST_P
        below = bool(n) and s["upper_95"] is not None and s["upper_95"] < delta
        tests[c]["verdict"] = {"bh_rejected": j in rej, "bh_m": len(conf), "cost_lines_positive": lines_pos,
                               "breadth_meetable": meetable, "breadth": breadth,
                               "gates_1_3": bool(j in rej and lines_pos and breadth), "against_the_book": against,
                               "upper_95": s.get("upper_95"), "below_delta": below, "delta": delta}
    return tests


def r2_pass(rows, lines=FTMO_LINES):
    """§4 R2 pass for one cell: pooled net excess > 0, and of the evaluable clusters (>= R2_CLUSTER_MIN events; at least
    R2_EVALUABLE_MIN of them) at least min(R2_AGREE, evaluable) show net excess > 0. Reading: with only two evaluable
    clusters both must agree (the "at least 2 evaluable" clause would otherwise be void).
    [prereg §4 R2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    pooled = summarise(rows, lines)
    cl = {}
    for c, syms in REPLICATION.items():
        cl[c] = summarise([r for r in rows if r["symbol"] in syms], lines)
    ev = [c for c, s in cl.items() if s.get("n", 0) >= R2_CLUSTER_MIN]
    agree = [c for c in ev if cl[c]["net_excess"] > 0]
    ok = bool(pooled.get("n")) and pooled["net_excess"] > 0 and len(ev) >= R2_EVALUABLE_MIN \
        and len(agree) >= min(R2_AGREE, len(ev))
    return {"summary": pooled, "clusters": cl, "evaluable": ev, "agree": agree, "r2_pass": bool(ok)}


def survivors(r1, perts):
    """{cell: perturbation record} for the cells meeting gates 1-3 in R1 and the sign (net excess > 0) in >= PERTURB_NEED of
    the six perturbations; a perturbation missing for a cell counts as not holding the sign.
    [prereg §6.2 item 4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    for c in W_CELLS:
        v = r1["tests"].get(c, {}).get("verdict") or {}
        if not v.get("gates_1_3"):
            continue
        signs = {}
        for p in PERTURBATIONS:
            s = ((perts.get(p) or {}).get("tests", {}).get(c) or {}).get("summary", {})
            signs[p] = bool(s.get("n")) and s["net_excess"] > 0
        out[c] = {"signs": signs, "positive": sum(signs.values()), "survivor": sum(signs.values()) >= PERTURB_NEED}
    return out


def final_label(cell, r1, perts, r2, r3):
    """§6.2 label of one family-W cell from the reads present: EDGE-CANDIDATE (survivor + R2 pass + no R3 veto) > AGAINST THE
    BOOK > NO MECHANICAL EDGE (upper bound < delta) > INCONCLUSIVE; a cell still waiting on a read says PENDING; a cell the
    count gate made descriptive says DESCRIPTIVE. An EDGE-CANDIDATE with a G-C contrast (GC_CONTRAST) is Wyckoff-attributed
    iff delta >= 0 against G-C as §3.6 is written, else "the shake works..."; with no delta (G-C or the cell had no rows)
    it is ATTR_UNDETERMINED -- never credited by default. The known-at-r delta is reported beside it, never used.
    [prereg §3.6 "Attribution", §6.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    t = r1["tests"].get(cell)
    if not t or not t.get("confirmatory"):
        return {"label": "DESCRIPTIVE", "why": "fewer than COUNT_GATE R1 events (R0)"}
    v = t["verdict"]
    out = {"r1": v}
    if v["gates_1_3"]:
        if perts is None or any(p not in perts for p in PERTURBATIONS):
            return dict(out, label="PENDING", why="R1 gates 1-3 met; perturbations not all read")
        sv = survivors(r1, perts)[cell]
        out["perturbations"] = sv
        if sv["survivor"]:
            if r2 is None or r3 is None:
                return dict(out, label="PENDING", why="R1 SURVIVOR; R2 / R3 not read")
            out["r2"] = bool(r2["tests"].get(cell, {}).get("r2_pass"))
            out["r3_veto"] = r3["tests"].get(cell, {}).get("r3_veto", True)       # a cell R3 did not read cannot pass it
            if out["r2"] and not out["r3_veto"]:
                gc = t.get("gc_contrast_known") or {}            # §3.6: the point-in-time control decides
                if cell not in GC_CONTRAST:
                    attr = None                                  # W-D / W-CAMP: §12.3 gives them no G-C contrast
                elif gc.get("diff") is None:
                    attr = ATTR_UNDETERMINED
                else:
                    attr = ("Wyckoff-attributed" if gc["diff"] >= 0
                            else "the shake works, but the Wyckoff range adds nothing measurable")
                return dict(out, label="EDGE-CANDIDATE", attribution=attr,
                            gc_delta={"literal": (t.get("gc_contrast") or {}).get("diff"),
                                      "known_at_r": gc.get("diff")})
    if v["against_the_book"]:
        return dict(out, label="AGAINST THE BOOK")
    if v["below_delta"]:
        return dict(out, label="NO MECHANICAL EDGE")
    return dict(out, label="INCONCLUSIVE")


def closing_rule(labels, r1):
    """§6.2 closing rule: W-C-long-15m, W-C-long-1H and W-CAMP each NO MECHANICAL EDGE (AGAINST THE BOOK counts as no edge),
    no cell EDGE-CANDIDATE, and G-C read out (R1 carries its rows). "Closed overall" also needs family V null at its own
    power, which this study cannot reach (§6.3), so it is never claimed.
    [prereg §6.2 "Closing rule": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    none = ("NO MECHANICAL EDGE", "AGAINST THE BOOK")
    gc = bool(r1 and r1.get("descriptive", {}).get("G-C", {}).get("n"))
    ok = all(labels.get(c, {}).get("label") in none for c in NO_EDGE_CELLS) and \
        not any(v.get("label") == "EDGE-CANDIDATE" for v in labels.values()) and gc
    return {"closed_price_mechanical_on_cfds": bool(ok), "gc_read_out": gc, "closed_overall": False,
            "why_not_overall": "family V cannot reach a closing bound at its power (§6.3, §8)"}


def v_verdicts(tests):
    """Family V (§6.3): its own BH at FDR_Q over the confirmatory V cells; EDGE-CANDIDATE = BH rejection and net excess > 0
    on both cost lines (base, 2 x slippage stress); AGAINST THE BOOK = two-sided p < AGAINST_P with a negative mean (V3: the
    bootstrap's two-sided p); INCONCLUSIVE otherwise -- never a closing label.
    [prereg §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    conf = [c for c in V_CELLS if tests.get(c, {}).get("confirmatory")]
    ps = [tests[c]["p_one_sided"] if tests[c]["p_one_sided"] is not None else 1.0 for c in conf]
    rej = EC.bh(ps, FDR_Q) if conf else set()
    for c in V_CELLS:
        t = tests.get(c)
        if t is None:
            continue
        if c not in conf:
            t["verdict"] = {"label": "DESCRIPTIVE"}
            continue
        j = conf.index(c)
        pos, neg, p2 = t["positive_all_lines"], t["negative"], t["p_two_sided"]
        label = ("EDGE-CANDIDATE" if j in rej and pos else
                 "AGAINST THE BOOK" if neg and p2 is not None and p2 < AGAINST_P else "INCONCLUSIVE")
        t["verdict"] = {"bh_rejected": j in rej, "bh_m": len(conf), "label": label}
    return tests


# ------------------------------------------------------------------------------------------------ registration guard
def _git(*args):
    """(returncode, stdout) of `git -C ROOT <args>`; (None, "") when git cannot run (the guard then refuses).
    [prereg §10: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    try:
        p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _git_head():
    rc, out = _git("rev-parse", "HEAD")
    return out.strip() or None if rc == 0 else None


def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT)


def _require_committed(paths):
    """None when every path is tracked by git and has no uncommitted change; SystemExit otherwise.
    [prereg §10 item 3 "_require_committed": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
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
        raise SystemExit("refusing: a read must run from committed code, tests and pre-registration (pre-registration "
                         "§10): " + "; ".join(bad))


def _require_clean_trees():
    """Under the guard: `git status --porcelain --untracked-files=all` is empty under every CLEAN_TREES path -- no edited,
    staged or untracked module, config or cost table anywhere the engine can reach.
    [prereg §10 item 3 "committed at the sealed SHA": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rc, out = _git("status", "--porcelain", "--untracked-files=all", "--", *CLEAN_TREES)
    if rc != 0 or out.strip():
        raise SystemExit(f"refusing: {', '.join(CLEAN_TREES)} must be committed and clean (untracked files included) "
                         f"before a read (pre-registration §10): " + "; ".join(out.strip().splitlines()[:8]))


def _loaded_code():
    """The repository modules this process has imported (sys.modules files under scripts/, tests excepted), relative.
    [prereg §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = set()
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if not f:
            continue
        rel = os.path.relpath(os.path.abspath(f), ROOT).replace(os.sep, "/")
        if rel.startswith("scripts/") and not rel.startswith("scripts/tests/") and rel.endswith(".py"):
            out.add(rel)
    return out


def _require_code_complete():
    """Under the guard, after the engine (and L1's reprice module) is loaded: every repository module the process imported
    is fingerprinted in CODE -- a new import cannot change a read without changing `code_sha256`.
    [prereg §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    missing = sorted(_loaded_code() - set(CODE))
    if missing:
        raise SystemExit(f"refusing: the engine loads {', '.join(missing)}, which CODE does not fingerprint; add it to "
                         "CODE, re-run counts and re-seal (pre-registration §10)")


def code_sha256():
    """{path: sha256, or None when absent} of every CODE file: the code fingerprint R0 records and every read carries.
    [prereg §10 item 3 "the code SHA": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return {p: (_sha256(os.path.join(ROOT, p)) if os.path.exists(os.path.join(ROOT, p)) else None) for p in CODE}


def _seal():
    """(date, instant) of the commit that ADDED the sealed pre-registration -- its COMMITTER date (a rebase or cherry-pick
    keeps the author date, not this): the <seal date> of the record directory and the instant forward bars start from.
    SystemExit when git cannot say.
    [prereg §4 R4, §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rc, out = _git("log", "--diff-filter=A", "--format=%cI", "--", PREREG)
    stamps = out.split()
    if rc != 0 or not stamps:
        raise SystemExit(f"refusing: no commit adds {PREREG}; the pre-registration is not sealed")
    t = datetime.datetime.fromisoformat(stamps[-1])
    return t.date().isoformat(), _iso(t)


def _prereg_text():
    with open(os.path.join(ROOT, PREREG), encoding="utf-8") as fh:
        return fh.read()


def _require_sealed():
    """ALWAYS before a read, a forward read or a report: the SEALED pre-registration (the file without -DRAFT) exists and
    is committed. Returns {"path", "sha256", "seal_date", "seal_instant"}.
    [prereg header + §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    p = os.path.join(ROOT, PREREG)
    if not os.path.exists(p):
        raise SystemExit(f"refusing: {PREREG} does not exist -- the pre-registration is still {PREREG_DRAFT}; commit it "
                         "without -DRAFT, with the R0 table and the code SHA, before any read (§10 item 6)")
    _require_committed([PREREG])
    date, instant = _seal()
    return {"path": PREREG, "sha256": _sha256(p), "seal_date": date, "seal_instant": instant}


def _require_hour_frame():
    """§5: the harness asserts real_costs.HOUR_FRAME == "server_table" (erratum 2026-10-04) before any data is touched.
    [prereg §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if RC.HOUR_FRAME != HOUR_FRAME:
        raise SystemExit(f"refusing: real_costs.HOUR_FRAME is {RC.HOUR_FRAME!r}, the reads need {HOUR_FRAME!r} (§5)")


def _require_ledger():
    """§10 item 6: research-ledger.json names the sealed pre-registration (families W, V and L1, the perturbations).
    [prereg §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    with open(os.path.join(ROOT, LEDGER), encoding="utf-8") as fh:
        if PREREG not in fh.read():
            raise SystemExit(f"refusing: {LEDGER} does not name {PREREG}; register the study (§10 item 6) before a read")


def _require_canonical(out_path, want):
    """The --out path is `want` and `want` has no git history (a read is run once).
    [prereg §4 "Reads": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if os.path.abspath(out_path) != os.path.join(ROOT, want):
        raise SystemExit(f"refusing: this read writes {want} (got {out_path})")
    rc, log = _git("log", "--all", "--format=%H", "--", want)
    if rc != 0:
        raise SystemExit(f"refusing: cannot check the git history of {want}")
    if log.strip():
        raise SystemExit(f"refusing: {want} has git history -- this read was already run (pre-registration §4 'Reads')")


def out_name(read, perturb=None):
    return f"{read}-{perturb}" if perturb else read


def _require_registration(name, out_path, sealed):
    """Under the guard, before any data is touched (the engine already loaded): the canonical --out path without git
    history, the ledger entry, every file in COMMITTED tracked and clean, CLEAN_TREES clean (untracked included) and every
    imported repository module in CODE. Returns the meta fields it vouches for.
    [prereg §10 item 3 "_require_registration": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    _require_canonical(out_path, CANONICAL_OUT.format(seal=sealed["seal_date"], name=name))
    _require_ledger()
    _require_committed(COMMITTED)
    _require_clean_trees()
    _require_code_complete()
    return {"committed_sha256": {p: _sha256(os.path.join(ROOT, p)) for p in COMMITTED},
            "loaded_code": sorted(_loaded_code())}


def _require_fresh_process(what):
    """One read per process (§6.2 item 4: each perturbation in a fresh process): refuses a second read here.
    [prereg §6.2 item 4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if _PROCESS["used"]:
        raise SystemExit(f"refusing: this process already ran {_PROCESS['used']}; each read runs in a fresh process")
    _PROCESS["used"] = what


def _read_json(path, script_kind, read=None, perturb="any"):
    with open(path, encoding="utf-8") as fh:
        rec = json.load(fh)
    m = rec.get("meta", {})
    if m.get("script") != SCRIPT or m.get("kind") != script_kind or (read is not None and m.get("read") != read) \
            or (perturb != "any" and m.get("perturb") != perturb):
        raise SystemExit(f"refusing: {path} is not the {script_kind} {read or ''} {perturb if perturb != 'any' else ''} "
                         f"record of {SCRIPT}")
    return rec


def _tie(path, rec, require_clean):
    """Under the guard a prior record must be tracked and clean, written under the guard, at a git_head that is an ancestor
    of HEAD, with this code's registered meta -- META_FIXED, so also the same script and code fingerprint -- and, when it
    names the R0 record it ran on (R1, V, L1), that R0 unchanged and still valid (`_r0`): the chain stays on the sealed
    code. [prereg §10 item 3 "_check_order": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if not require_clean:
        return
    m = rec["meta"]
    _require_committed([_rel(path)])
    if m.get("guarded") is not True:
        raise SystemExit(f"refusing: {path} was not written under the registration guard")
    head = m.get("git_head")
    if not head or _git("merge-base", "--is-ancestor", head, "HEAD")[0] != 0:
        raise SystemExit(f"refusing: {path} was written at {head}, not an ancestor of HEAD")
    cur = json.loads(json.dumps(_meta("read"), default=str))
    diff = [k for k in META_FIXED if m.get(k) != cur.get(k)]
    if diff:
        raise SystemExit(f"refusing: {path} was run under a different registration ({', '.join(diff)} differ)")
    c = m.get("counts")
    if c:
        p = os.path.join(ROOT, c["path"])
        if not os.path.exists(p) or _sha256(p) != c["sha256"]:
            raise SystemExit(f"refusing: {path} ran on the R0 record {c['path']}, which is missing or has changed since")
        _r0(p, True)


def _r0(counts_path, require_clean):
    """The R0 counts record a read needs (dense table, N, confirmatory cells). Always: an R0 of this script whose point-in-
    time truncation probe checked events and found no violation. Under the guard also: committed, named in the sealed
    pre-registration, produced by THIS code (same script_sha256 and code_sha256: the sealed code SHA) with this registered
    design. [prereg §4 R0, §10 items 5-6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if not counts_path:
        raise SystemExit("this read needs --counts <the R0 counts json> (§4: R0 fixes the confirmatory cells)")
    rec = _read_json(counts_path, "counts")
    pr = rec.get("probe") or {}
    if pr.get("ok") is not True or pr.get("violations") != 0 or not pr.get("checked"):
        raise SystemExit(f"refusing: the R0 point-in-time truncation probe did not pass (checked {pr.get('checked')}, "
                         f"violations {pr.get('violations')}); no outcome is read on a leaking detector (§4 R0, §10 item 5)")
    if require_clean:
        _require_committed([_rel(counts_path)])
        if _rel(counts_path) not in _prereg_text():
            raise SystemExit(f"refusing: the sealed pre-registration does not name the R0 record {_rel(counts_path)}")
        m, cur = rec["meta"], json.loads(json.dumps(_meta("counts"), default=str))
        code = [k for k in ("script_sha256", "code_sha256") if m.get(k) != cur.get(k)]
        if code:
            raise SystemExit(f"refusing: the R0 counts were produced by different code ({', '.join(code)} differ); re-run "
                             "counts and re-seal (§10)")
        diff = [k for k in ("symbols", "timeframes", "cells", "parameters", "costs") if m.get(k) != cur.get(k)]
        if diff:
            raise SystemExit(f"refusing: the R0 counts were made under a different design ({', '.join(diff)} differ)")
    return rec


def _perturbation_paths(r1_path):
    d = os.path.dirname(os.path.abspath(r1_path))
    return {p: os.path.join(d, f"edge-wyckoff-{out_name('R1', p)}.json") for p in PERTURBATIONS}


def _check_order(read, counts_path=None, after=None, perturb=None, require_clean=True, perturb_paths=None):
    """Refuses an out-of-order read BEFORE any data is touched, and returns what the read needs: R1 needs the R0 counts; a
    perturbation needs R1 with a cell meeting gates 1-3; R2 / R3 need R1 and all six perturbation records (beside it) and at
    least one SURVIVOR -- they read survivor cells only; V needs the R0 counts; L1 needs the R0 counts too (it reads no
    R0 number, but R0 is what ties a read to the sealed code: `_r0`). Records named by --after are `_tie`d.
    [prereg §4 "Reads", §6.2, §10 item 3 "_check_order": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if read not in READS:
        raise SystemExit(f"unknown read {read}")
    if perturb is not None and (read != "R1" or perturb not in PERTURBATIONS):
        raise SystemExit(f"--perturb {perturb} applies to R1 only, one of {list(PERTURBATIONS)} (§6.2 item 4)")
    if read in ("R1", "V", "L1") and perturb is None:
        return {"r0": _r0(counts_path, require_clean)}
    if not after:
        raise SystemExit(f"--read {read}{' --perturb ' + perturb if perturb else ''} needs --after <the R1 json>")
    r1 = _read_json(after, "read", "R1", None)
    _tie(after, r1, require_clean)
    if perturb is not None:
        cells = [c for c in W_CELLS if (r1["tests"].get(c, {}).get("verdict") or {}).get("gates_1_3")]
        if not cells:
            raise SystemExit("refusing: no R1 cell meets gates 1-3 of §6.2 -- perturbations only veto, there is nothing to "
                             "perturb")
        return {"r1": r1, "cells": cells}
    paths = perturb_paths or _perturbation_paths(after)
    perts = {}
    for p, path in paths.items():
        if not os.path.exists(path):
            raise SystemExit(f"refusing: --read {read} needs all six perturbation records; {p} is missing ({path})")
        perts[p] = _read_json(path, "read", "R1", p)
        _tie(path, perts[p], require_clean)
    sv = {c: v for c, v in survivors(r1, perts).items() if v["survivor"]}
    if not sv:
        raise SystemExit(f"refusing: no R1 SURVIVOR -- {read} is read only for survivors (§4)")
    return {"r1": r1, "perts": perts, "cells": sorted(sv, key=W_CELLS.index)}


def _meta(kind, read=None, perturb=None):
    """The registered design (META_FIXED fields are compared across a read chain) plus run provenance.
    [prereg §10, §12: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    p = os.path.join(ROOT, PREREG)
    d = os.path.join(ROOT, PREREG_DRAFT)
    bt = engine()
    return {"script": SCRIPT, "script_sha256": _sha256(os.path.join(ROOT, SCRIPT)), "code_sha256": code_sha256(),
            "kind": kind, "read": read, "perturb": perturb, "preregistration": PREREG,
            "preregistration_sha256": _sha256(p) if os.path.exists(p) else None,
            "preregistration_draft": PREREG_DRAFT, "draft_sha256": _sha256(d) if os.path.exists(d) else None,
            "git_head": _git_head(),
            "symbols": {"tradeable": list(TRADEABLE), "groups": {g: list(v) for g, v in GROUPS.items()},
                        "replication": {c: list(v) for c, v in REPLICATION.items()}, "excluded": EXCLUDED,
                        "v": list(v_symbols()), "l1": list(L1_SYMBOLS), "l1_descriptive": list(L1_DESCRIPTIVE)},
            "timeframes": {"W": list(TIMEFRAMES), "W_descriptive": list(TIMEFRAMES_DESC), "V": list(V_TIMEFRAMES)},
            "cells": {"W": list(W_CELLS), "V": list(V_CELLS), "closing": list(NO_EDGE_CELLS), "gc_contrast": GC_CONTRAST,
                      "gc_contrast_known": GC_CONTRAST_KNOWN},
            "parameters": {"det_po": dict(BASE_CFG), "perturbations": {k: dict(v) for k, v in PERTURBATIONS.items()},
                           "engine": {"H": {tf: bt.P[tf]["H"] for tf in TIMEFRAMES}, "sob": {tf: bt.P[tf]["sob"]
                                                                                             for tf in TIMEFRAMES},
                                      "stop_buffer": bt.STOP_BUFFER_PCT, "wyckoff_window": bt.WYCKOFF_WINDOW,
                                      "htf_of": {tf: bt.HTF_OF.get(tf) for tf in TIMEFRAMES}},
                           "cause_min": CAUSE_MIN, "test_zone": TEST_ZONE, "gc_reclaim": GC_RECLAIM,
                           "v4": {"lookback": V4_LOOKBACK, "mom": V4_MOM, "vol_x": V4_VOL_X, "spacing": V4_SPACING},
                           "n_placebo": N_PLACEBO, "atr_n": ATR_N,
                           "placebo_seed": f"sha256('{SEED_TAG}|sym|tf|signal_time')[:16]",
                           "placebo_slot": "server-clock minute of the day of the event's ENTRY bar",
                           "dense": {"share": DENSE_SHARE, "ref_year": DENSE_REF_YEAR,
                                     "lookback_days": DENSE_LOOKBACK_DAYS, "hole_days": HOLE_DAYS},
                           "hour_norm_days": HOUR_NORM_DAYS, "trend_days": TREND_DAYS, "count_gate": COUNT_GATE,
                           "fdr_q": FDR_Q, "delta": DELTA,
                           "breadth_min": BREADTH_MIN, "perturb_need": PERTURB_NEED, "against_p": AGAINST_P,
                           "r2": {"cluster_min": R2_CLUSTER_MIN, "evaluable_min": R2_EVALUABLE_MIN, "agree": R2_AGREE},
                           "l1_p": L1_P, "forward": {"p": FORWARD_P, "events": FORWARD_EVENTS, "months": FORWARD_MONTHS},
                           "bootstrap_resamples": BOOT_N, "cluster": "ISO week of the signal bar (UTC)",
                           "windows": READ_WINDOWS, "fra40_session_cut": FRA40_SESSION_CUT},
            "costs": {"profile": COST_PROFILE, "hour_frame": HOUR_FRAME, "lines": list(FTMO_LINES),
                      "commission": "0/UNKNOWN (real_costs.commission_r)", "binance_round_trip": COST_RT,
                      "binance_stress": COST_STRESS, "binance_lines": list(V_LINES), "funding": H7.FUNDING_RULE},
            "disclosures": {
                "price_only": "DET-PO drops the volume legs of CHoBEV, SOS and BU (WA:274-277): price patterns, not the "
                              "book's effort reading (§3.1, §11 item 3)",
                "dense_start": "every series (decision and higher timeframe) starts at its R0 dense start",
                "read_membership": "an event belongs to a read by its ENTRY bar: open >= lo and close <= hi",
                "cost_times": "cost_r at the entry bar's and exit bar's time labels (the engine's convention)",
                "gc_exclusion": "G-C's +-N exclusion (§3.6 as written) reads every W-C-long event of the series, including "
                                "breaks AFTER the control's decision bar r -- a sample definition that conditions on "
                                "later bars and can drop losing controls; G-C-known (diagnostic, gc_contrast_known, "
                                "never the attribution's) excludes only on W-C-long events signalled by r. The owner "
                                "confirms which §3.6 means before sealing",
                "attribution": "no G-C delta (no rows on either side) -> attribution UNDETERMINED, never Wyckoff by "
                               "default",
                "htf_gates": "the §3.1 cause and horizontal gates apply to the higher-timeframe records too (DET-PO)",
                "camp_cap": "W-CAMP exits on time H bars after the last filled tranche whether or not it has a target",
                "camp_placebo": "placebo campaigns use the event's FILLED tranche offsets",
                "v_harness": "family V uses the same harness (gates, de-dup, §3.2 builders); only the volume reading "
                             "differs (price_only off, traded volume)",
                "descriptive_built": "R1 only, never gated: the Phase-B raised-ceiling target on W-C-long (|ceiling-"
                                     "target), the flatten-before-rollover walk on W-C-long and W-D (|flatten), the "
                                     "trend-matched placebo on the single-entry W cells (|trend-placebo: the drawn "
                                     "placebo bars whose 20-day trend sign at p-1 equals the event's at k), and 1D "
                                     "(desc:*-1D, no HTF: W-D / W-CAMP exit on time)",
                "descriptive_not_built": "§3.7 lower-timeframe Shakeout entry (WA2-18) and sigma-unit time exit: §3.7 "
                                         "gives no point-in-time definition this script can implement without "
                                         "inventing one (the census' sigma unit drops any hold that crosses a server "
                                         "day, i.e. nearly every hold of H bars); to be defined or struck before "
                                         "sealing",
                "code_fingerprint": "code_sha256 covers CODE; the ledger is outside it (other studies append to it)"}}


# ------------------------------------------------------------------------------------------------ R0: counts (no outcome)
def _rr_quantiles(xs):
    xs = sorted(x for x in xs if x is not None)
    return {"n": len(xs), "mean": _mean(xs), "q10": _quantile(xs, 0.1), "median": _quantile(xs, 0.5),
            "q90": _quantile(xs, 0.9)} if xs else {"n": 0}


def count_series(S, evs, lo, hi, family="W"):
    """OUTCOME-BLIND counts of one series in one read window: per cell events, the entry-time skips, the planned R:R
    (target distance / stop distance at the entry open), no-target events, the HTF containment rate (W-D with a target,
    W-C with context) and the W-C break-to-SC distances (G-C's N). Reads O[e] (the fill price) and nothing after it.
    [prereg §4 R0: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = collections.defaultdict(lambda: {"signals": 0, "kept": 0, "placeable": 0, "skips": collections.Counter(),
                                           "rr": [], "no_target": 0, "htf_target": 0, "ctx": 0})
    breaks = []
    for leg in ("W-C", "W-C-short", "W-C-SOR", "W-D", "W-CAMP", "G-C", "V4"):
        for ev in evs.get(leg, ()):
            cells = cells_of(ev, family)
            if ev["e"] >= len(S) or not S.in_window(ev["e"], lo, hi):
                continue                                         # another read's event
            if not S.prev_dense[ev["k"]]:
                for c in cells:
                    out[c]["signals"] += 1
                    out[c]["skips"]["previous_server_day_not_dense"] += 1
                continue
            entry = S.O[ev["e"]]
            tgt = (target_for(ev.get("htf_cands") or [], ev["side"], entry) if leg in ("W-D", "W-CAMP")
                   else ev.get("target"))
            ok = placeable(ev["side"], entry, ev["stop"], tgt)
            for c in cells:
                o = out[c]
                o["signals"] += 1
                o["kept"] += 1
                if not ok:
                    o["skips"]["entry_beyond_stop_or_target"] += 1
                    continue
                o["placeable"] += 1
                if tgt is None:
                    o["no_target"] += 1
                else:
                    o["rr"].append(abs(tgt - entry) / abs(entry - ev["stop"]))
                    if leg in ("W-D", "W-CAMP"):
                        o["htf_target"] += 1
                o["ctx"] += bool(ev.get("ctx"))
            if ok and leg == "W-C":
                breaks.append(ev["s"] - ev["sc"])
    return out, breaks


def _merge_counts(acc, part, sym, group):
    for c, o in part.items():
        a = acc.setdefault(c, {"signals": 0, "kept": 0, "placeable": 0, "skips": collections.Counter(), "rr": [],
                               "no_target": 0, "htf_target": 0, "ctx": 0, "by_symbol": collections.Counter(),
                               "by_group": collections.Counter()})
        for k in ("signals", "kept", "placeable", "no_target", "htf_target", "ctx"):
            a[k] += o[k]
        a["skips"].update(o["skips"])
        a["rr"] += o["rr"]
        a["by_symbol"][sym] += o["placeable"]
        a["by_group"][group] += o["placeable"]


def _finish_counts(acc):
    out = {}
    for c, a in sorted(acc.items()):
        out[c] = {k: a[k] for k in ("signals", "kept", "placeable", "no_target", "htf_target", "ctx")}
        htf = c.startswith("W-D") or c in ("W-CAMP", "V2")    # the cells whose target is the contained HTF record
        wc = c.startswith("W-C-long") or c == "W-CTX"
        out[c].update(skips=dict(a["skips"]), by_symbol=dict(a["by_symbol"]), by_group=dict(a["by_group"]),
                      planned_rr=_rr_quantiles(a["rr"]),
                      htf_containment_rate=(a["htf_target"] / a["placeable"]) if htf and a["placeable"] else None,
                      htf_context_rate=(a["ctx"] / a["placeable"]) if wc and a["placeable"] else None)
    return out


def power_table(cells):
    """§8 restated from R0 counts (no outcome): n, n_eff = n / 2 (design effect 2), the null SD sqrt(mean planned R:R) and
    the 1.4 / 2.0 planning SDs, the MDE at 3.08 SE and the bound half-width at 1.645 SE, and whether delta is reachable.
    [prereg §8: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    for c, o in cells.items():
        n = o["placeable"]
        neff = n / 2
        rr = (o["planned_rr"] or {}).get("mean")
        row = {"n": n, "n_eff": neff, "sd_null": math.sqrt(rr) if rr else None}
        for name, sd in (("sd_1.4", 1.4), ("sd_2.0", 2.0), ("sd_null", row["sd_null"])):
            if sd and neff > 0:
                row[name] = {"mde": 3.08 * sd / math.sqrt(neff), "half_width": 1.645 * sd / math.sqrt(neff),
                             "can_close_at_zero": 1.645 * sd / math.sqrt(neff) < DELTA}
        out[c] = row
    return out


def dense_table(syms_tfs, loader, venue):
    """{"SYM|tf": dense_start record} over full series (R0 pins it; every read starts each series there).
    [prereg §4 R0: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    zone = series_zone(venue)
    for sym, tf in syms_tfs:
        candles, prov = loader(sym, tf)
        if not candles:
            out[f"{sym}|{tf}"] = {"start": None, "why": "no history", "provenance": prov}
            continue
        dts = [_utc(c["time"]) for c in candles]
        out[f"{sym}|{tf}"] = dict(dense_start([d.astimezone(zone).date() for d in dts], dts), provenance=prov)
    return out


def probe(samples, loader, dense, cfg, family="W", until=None, fire=None):
    """The point-in-time truncation probe (§10 item 5, the leakage_probe_fund pattern): each sampled event is re-detected on
    its series CUT at the signal bar (and the higher timeframe cut at the signal close), with the window's own pivots, and
    every decision field must be identical -- the record (incl. phase_b_tests, the cause and horizontal gates), the
    Spring/Shakeout typing at the reclaim, the stop / target, the HTF candidates and context, prev_dense and ATR. A probe
    that checked nothing is not a pass. Counts only: no R.
    [prereg §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    fire = fire or window_fire
    P = det_params(cfg, family)
    fields = ("leg", "side", "k", "e", "key", "sc", "ar", "s", "r", "t", "type", "spring_low", "stop", "target", "tr_lo",
              "tr_hi", "ceiling", "phase_b_tests", "sloped", "path", "htf_cands", "ctx")
    checked, bad, first = 0, 0, None
    groups = collections.defaultdict(list)
    for ev in samples:
        groups[(ev["sym"], ev["tf"])].append(ev)
    venue = "binance" if family == "V" else "ftmo"
    for (sym, tf), evs in sorted(groups.items()):
        S = make_series(sym, tf, loader, dense, cfg, venue, until=until)
        h = htf_of(tf)
        Hs = make_series(sym, h, loader, dense, cfg, venue, until=until) if h else None
        for ev in evs:
            k = ev["k"]
            cut = Series(sym, tf, S.src[:k + 1], S.zone, S.start, venue=venue, volume=cfg["volume"])
            hcut = (Htf(Series(sym, h, Hs.src, Hs.zone, Hs.start, until=S.avail[k], venue=venue, volume=cfg["volume"]), P)
                    if Hs is not None else None)
            checked += 1
            try:
                got = [enrich(x, cut, hcut) for x in fire(cut, k, cfg, P, engine().P[tf]["sob"])[0]
                       if x["leg"] == ev["leg"] and x["key"] == ev["key"]]
                ok = len(got) == 1 and all(json.dumps(got[0].get(f), default=str) == json.dumps(ev.get(f), default=str)
                                           for f in fields) and cut.prev_dense[k] == S.prev_dense[k] \
                    and cut.atr[k] == S.atr[k]
                why = None if ok else {"event": {f: ev.get(f) for f in fields},
                                       "re_detected": [{f: g.get(f) for f in fields} for g in got]}
            except Exception as exc:  # noqa: BLE001 -- a read beyond the cut is exactly what this probe looks for
                ok, why = False, {"event": {f: ev.get(f) for f in fields}, "error": repr(exc)}
            if not ok:
                bad += 1
                first = first or json.loads(json.dumps(why, default=str))
    return {"checked": checked, "violations": bad, "ok": checked > 0 and bad == 0, "first_violation": first}


def counts(out_path, loader=load_ftmo, vloader=load_binance, symbols=None, replication=None, vsyms=None,
           timeframes=TIMEFRAMES, v_timeframes=V_TIMEFRAMES, probe_n=PROBE_N):
    """R0 (§4): OUTCOME-BLIND. The dense table; per read (R1, R2, R3, V) and cell the events, entry-time skips, planned R:R,
    no-target and HTF-containment counts by symbol and group; G-C's N per timeframe (median break bar - SC bar over R1's
    W-C-long events) and the G-C counts; the truncation probe; the confirmatory cells (>= COUNT_GATE R1 / V events) and the
    §8 power table. No walk, exit, cost or return is computed.
    [prereg §4 R0, §6.1, §8, §10 item 5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists; refusing to overwrite an R0 record")
    _require_fresh_process("counts")
    symbols = TRADEABLE if symbols is None else tuple(symbols)
    replication = [s for syms in REPLICATION.values() for s in syms] if replication is None else list(replication)
    vsyms = v_symbols() if vsyms is None else list(vsyms)
    cfg = dict(BASE_CFG)
    ftfs = list(timeframes) + sorted({htf_of(tf) for tf in timeframes if htf_of(tf)} - set(timeframes))
    vtfs = list(v_timeframes) + sorted({htf_of(tf) for tf in v_timeframes if htf_of(tf)} - set(v_timeframes))
    dense = dense_table([(s, tf) for s in list(symbols) + replication for tf in ftfs], loader, "ftmo")
    dense.update(dense_table([(s, tf) for s in vsyms for tf in vtfs], vloader, "binance"))
    res = {"meta": dict(_meta("counts"), note="OUTCOME-BLIND R0: counts, planned R:R known at entry, dense table, probe"),
           "dense": dense, "reads": {}, "logs": {}, "gc_n": {}, "gc_stats": {}}
    # One detection per series: R1 and R3 are windows of the SAME tradeable series (an event belongs to a read by its entry
    # bar), R2 the replication series, V the Binance ones.
    plan = [(symbols, "W", ("R1", "R3")), (replication, "W", ("R2",)), (vsyms, "V", ("V",))]
    accs = {r: {} for _s, _f, reads in plan for r in reads}
    breaks, wc_breaks, r1_events = collections.defaultdict(list), {}, []
    for syms, family, reads in plan:
        tfs = timeframes if family == "W" else v_timeframes
        ld, venue = (loader, "ftmo") if family == "W" else (vloader, "binance")
        until = V_END if family == "V" else None
        for sym in syms:
            for tf in tfs:
                S = make_series(sym, tf, ld, dense, cfg, venue, until=until)
                if S is None:
                    res["logs"][f"{sym}|{tf}"] = "no dense start or no bars"
                    continue
                h = htf_of(tf)
                Hs = make_series(sym, h, ld, dense, cfg, venue, until=until) if h else None
                evs = series_events(S, Htf(Hs, det_params(cfg, family)) if Hs is not None else None, cfg, family)
                res["logs"][f"{sym}|{tf}"] = dict(evs["logs"])
                wc_breaks[(sym, tf)] = [(e["s"], e["k"]) for e in evs["W-C"]]
                for read in reads:
                    lo, hi = READ_WINDOWS[read]
                    part, br = count_series(S, evs, lo, hi, family)
                    _merge_counts(accs[read], part, sym, S.group)
                    if read == "R1":
                        breaks[tf] += br
                        r1_events += [dict(ev) for leg in ("W-C", "W-C-short", "W-C-SOR", "W-D") for ev in evs[leg]
                                      if kept(S, ev, lo, hi)]
                del S, Hs, evs
            print(f"R0 {'/'.join(reads)} {sym}: counted", flush=True)
    for tf in timeframes:
        med = statistics.median(breaks[tf]) if breaks[tf] else None
        res["gc_n"][tf] = int(math.floor(med + 0.5)) if med is not None else None
    for syms, family, reads in plan[:2]:                # G-C needs N: a second pass on the stored W-C break bars
        for sym in syms:
            for tf in timeframes:
                S = make_series(sym, tf, loader, dense, cfg, "ftmo")
                if S is None:
                    continue
                wb = wc_breaks.get((sym, tf), [])
                gc, st = gc_events(S, res["gc_n"].get(tf), [b for b, _k in wb], wb)
                res["gc_stats"][f"{sym}|{tf}"] = dict(st)
                for read in reads:
                    lo, hi = READ_WINDOWS[read]
                    part, _ = count_series(S, {"G-C": gc}, lo, hi)
                    _merge_counts(accs[read], part, sym, S.group)
    for read in accs:
        res["reads"][read] = _finish_counts(accs[read])
    rnd = random.Random(_seed(SEED_TAG, "probe"))
    sample = rnd.sample(r1_events, min(probe_n, len(r1_events))) if r1_events else []
    res["probe"] = probe(sample, loader, dense, cfg)
    r1c, vc = res["reads"]["R1"], res["reads"]["V"]
    res["confirmatory"] = {"W": [c for c in W_CELLS if r1c.get(c, {}).get("placeable", 0) >= COUNT_GATE],
                           "V": [c for c in V_CELLS if _v_count(vc, c) >= COUNT_GATE]}
    res["power"] = {"W": power_table({c: r1c[c] for c in W_CELLS if c in r1c}),
                    "V": power_table({c: vc[c] for c in ("V1", "V2", "V4") if c in vc})}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"R0: confirmatory W {res['confirmatory']['W']} V {res['confirmatory']['V']}; probe {res['probe']['checked']} "
          f"checked, {res['probe']['violations']} violations; wrote {out_path}")
    return res


def _v_count(vc, cell):
    """The count gate's n of a family-V cell; V3 is a contrast inside V1, so it counts the SMALLER of its two arms
    (vol_type 1 vs 2-3). [prereg §6.1 count gate, §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if cell != "V3":
        return vc.get(cell, {}).get("placeable", 0)
    return min(vc.get("V3:type1", {}).get("placeable", 0), vc.get("V3:type23", {}).get("placeable", 0))


# ------------------------------------------------------------------------------------------------ reads
def desc_variants(ev):
    """[(cell, variant)] of the §3.7 descriptive variants an R1 event is scored again under: the Phase-B raised-ceiling
    target ("ceiling", W-C-long) and the flatten-before-rollover walk ("flatten", W-C-long and W-D); none on 1D.
    [prereg §3.2 "a descriptive variant", §3.7 "Variants": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    tf = ev["tf"]
    if tf not in TIMEFRAMES:
        return []
    if ev["leg"] == "W-C":
        return [(f"desc:W-C-long-{tf}|ceiling-target", "ceiling"), (f"desc:W-C-long-{tf}|flatten", "flatten")]
    if ev["leg"] == "W-D":
        return [(f"desc:W-D-{tf}|flatten", "flatten")]
    return []


def score_events(bt, S, evs, cells_wanted, HZ, pricer, lo, hi, family="W", extras=False):
    """{cell: [rows]} and skipped Counter for one series in one read: only events of cells in `cells_wanted` (a read touches
    its own cells only), each scored once. `extras` (R1): every single-entry row also carries the trend-matched placebo,
    and each event of a `desc_variants` cell is scored again under that variant (its own row and skip count).
    [prereg §3.7, §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rows, skipped = collections.defaultdict(list), collections.Counter()
    for leg in ("W-C", "W-C-short", "W-C-SOR", "W-D", "W-CAMP", "G-C", "V4"):
        for ev in evs.get(leg, ()):
            cells = [c for c in cells_of(ev, family) if c in cells_wanted]
            if not cells or not kept(S, ev, lo, hi):
                continue
            r, why = (score_campaign(S, ev, HZ, pricer, lo, hi) if leg == "W-CAMP"
                      else score(bt, S, ev, HZ, pricer, lo, hi, trend=extras and leg != "G-C"))
            if r is None:
                skipped[f"{leg}|{why}"] += 1
            else:
                for c in cells:
                    rows[c].append(r)
            for c, how in (desc_variants(ev) if extras and family == "W" else ()):
                if c not in cells_wanted:
                    continue
                if how == "ceiling":
                    r, why = score(bt, S, ev, HZ, pricer, lo, hi, target=ev["ceiling"])
                else:
                    with walk_opts(bt, flatten=True):
                        r, why = score(bt, S, ev, HZ, pricer, lo, hi)
                if r is None:
                    skipped[f"{c}|{why}"] += 1
                else:
                    rows[c].append(dict(r, variant=how))
    return rows, skipped


def _w_cells_wanted(read, cells):
    """The cells a family-W read scores: R1 all of family W, G-C (both variants) and every §3.7 descriptive cell (1D
    included); any other read exactly `cells`. [prereg §3.7, §4, §12.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if read == "R1" and cells is None:
        tfs = TIMEFRAMES + TIMEFRAMES_DESC
        desc = {f"desc:W-C-long-{tf}|{t}" for tf in tfs for t in ("SPRING", "SHAKEOUT", "SHAKEOUT@reclaim")}
        desc |= {f"desc:W-C-short-{tf}" for tf in tfs}
        desc |= {f"desc:{c}-{tf}" for c in ("W-C-long", "W-D", "W-CAMP") for tf in TIMEFRAMES_DESC}
        desc |= {f"desc:W-C-long-{tf}|{v}" for tf in TIMEFRAMES for v in ("ceiling-target", "flatten")}
        desc |= {f"desc:W-D-{tf}|flatten" for tf in TIMEFRAMES}
        gc = {f"{g}-{tf}" for g in ("G-C", "G-C-known") for tf in TIMEFRAMES} | {"G-C", "G-C-known"}
        return set(W_CELLS) | gc | desc
    return set(cells)


def run_w(read, cfg, symbols, timeframes, loader, dense, gc_n, cells, pricer, bt):
    """{cell: rows}, skipped, data provenance for a family-W read (R1, a perturbation, R2, R3, or a forward window passed as
    `read`=(lo, hi)). [prereg §4, §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    lo, hi = READ_WINDOWS[read] if isinstance(read, str) else read
    until = hi if read in ("R1", "R2") else None
    wanted = _w_cells_wanted(read, cells)
    extras = read == "R1" and cells is None                     # §3.7 descriptive variants: R1 only
    pooled, skipped, data = collections.defaultdict(list), {}, {}
    P = det_params(cfg)
    with walk_opts(bt):
        for sym in symbols:
            for tf in timeframes:
                S = make_series(sym, tf, loader, dense, cfg, "ftmo", until=until)
                if S is None:
                    data[f"{sym}|{tf}"] = {"bars": 0, "why": "no dense start or no bars"}
                    continue
                h = htf_of(tf)
                Hs = make_series(sym, h, loader, dense, cfg, "ftmo", until=until) if h else None
                evs = series_events(S, Htf(Hs, P) if Hs is not None else None, cfg, "W",
                                    gc_n if read == "R1" and cells is None else None)
                rows, sk = score_events(bt, S, evs, wanted, bt.P[tf]["H"] * cfg["cap_mult"], pricer, lo, hi,
                                        extras=extras)
                for c, rs in rows.items():
                    pooled[c] += rs
                skipped[f"{sym}|{tf}"] = dict(sk)
                data[f"{sym}|{tf}"] = {"bars": len(S), "first": S.T[0], "last": S.T[-1], "dense_start": S.start.isoformat(),
                                       "htf_bars": len(Hs) if Hs is not None else 0, "logs": dict(evs["logs"]),
                                       "gc_stats": dict(evs["gc_stats"]), "missing_volume": S.missing_volume,
                                       "neutral_volume": S.neutral_volume}
                print(f"{read} {sym} {tf}: {len(S)} bars, rows " + ", ".join(f"{c} {len(r)}" for c, r in sorted(rows.items())
                                                                             if not c.startswith("desc:")), flush=True)
                del S, Hs, evs
    return pooled, skipped, data


def run_v(cfg, vloader, funding_loader, dense, bt, symbols=None, window=None):
    """{cell: rows}, skipped, data for family V: the engine's detector on real volume (price_only off), 15m and 1H pooled;
    V1 W-C-long, V2 W-D, V3 = V1 split by vol_type (1 vs 2-3), V4 effort vs result. Refuses before any outcome when a
    perp-era event's cap window lacks funding coverage (never charged zero).
    [prereg §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    lo, hi = window or READ_WINDOWS["V"]
    syms = v_symbols() if symbols is None else symbols
    funding = {}
    for sym in syms:
        funding[sym], _ = funding_loader(sym)
    pricer = Pricer("binance", funding=funding)
    pooled, skipped, data = collections.defaultdict(list), {}, {}
    P = det_params(cfg, "V")
    with walk_opts(bt):
        for sym in syms:
            for tf in V_TIMEFRAMES:
                S = make_series(sym, tf, vloader, dense, cfg, "binance", until=hi)
                if S is None:
                    data[f"{sym}|{tf}"] = {"bars": 0}
                    continue
                Hs = make_series(sym, htf_of(tf), vloader, dense, cfg, "binance", until=hi)
                evs = series_events(S, Htf(Hs, P) if Hs is not None else None, cfg, "V")
                HZ = bt.P[tf]["H"] * cfg["cap_mult"]
                unc = [ev for leg in ("W-C", "W-D", "V4") for ev in evs[leg] if kept(S, ev, lo, hi)
                       and S.T[ev["e"]] >= H7.PERP_FROM and not funding[sym].covers(S.dt[ev["e"]],
                                                                                   S.dt[ev["e"]] + HZ * S.bar)]
                if unc:
                    raise SystemExit(f"refusing: {sym} {tf} has {len(unc)} perp-era V events without funding coverage of "
                                     "their cap window; fix the funding history first")
                rows, sk = score_events(bt, S, evs, set(V_CELLS), HZ, pricer, lo, hi, family="V")
                for c, rs in rows.items():
                    pooled[c] += rs
                skipped[f"{sym}|{tf}"] = dict(sk)
                data[f"{sym}|{tf}"] = {"bars": len(S), "first": S.T[0], "last": S.T[-1], "logs": dict(evs["logs"])}
                print(f"V {sym} {tf}: {len(S)} bars, rows " + ", ".join(f"{c} {len(r)}" for c, r in sorted(rows.items())),
                      flush=True)
    pooled["V3"] = [r for r in pooled.get("V1", []) if r.get("vol_type") in (1, 2, 3)]
    return pooled, skipped, data


def v_tests(rows, confirmatory):
    """Family-V tests: V1 / V2 / V4 by CR1-by-week t on the base cost line; V3 = mean net excess of vol_type 1 minus types
    2-3 within V1, one-sided by a week-cluster bootstrap.
    [prereg §6.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    for c in ("V1", "V2", "V4"):
        s = summarise(rows.get(c, []), V_LINES)
        out[c] = {"cell": c, "confirmatory": c in confirmatory, "summary": s, "p_one_sided": s.get("p_one_sided"),
                  "p_two_sided": s.get("p_two_sided"),
                  "positive_all_lines": bool(s.get("n")) and all(s["lines"][ln]["mean"] > 0 for ln in V_LINES),
                  "negative": bool(s.get("n")) and s["net_excess"] < 0}
    v3 = rows.get("V3", [])
    a = [r for r in v3 if r["vol_type"] == 1]
    b = [r for r in v3 if r["vol_type"] in (2, 3)]
    bs = week_bootstrap(a, b, lambda r: r["excess"] - r["cost"]["base"], _seed(SEED_TAG, "V3"))
    bs_s = week_bootstrap(a, b, lambda r: r["excess"] - r["cost"]["stress"], _seed(SEED_TAG, "V3", "stress"))
    p1 = bs["p_one_sided"]
    out["V3"] = {"cell": "V3", "confirmatory": "V3" in confirmatory, "type1": summarise(a, V_LINES),
                 "type23": summarise(b, V_LINES), "bootstrap": bs, "bootstrap_stress": bs_s, "p_one_sided": p1,
                 "p_two_sided": 2 * min(p1, 1 - p1) if p1 is not None else None,
                 "positive_all_lines": (bs["diff"] or 0) > 0 and (bs_s["diff"] or 0) > 0,
                 "negative": (bs["diff"] or 0) < 0}
    return out


def l1_engine():
    """reprice_real_costs loaded fresh (it sets BT_HISTORY_ROOT = the FTMO history and loads its own backtest-methods with
    the development cutoff); the cutoff is then lifted -- L1 reads the EXPOSED window. Config A, PROFILE, FEE and the
    simulate call are the committed script's own (§7.3 "exactly as in reprice_real_costs.py at the sealed SHA").
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    RP = _load("reprice_real_costs_l1", REPRICE)
    RP.bt.pit_cutoff(None)
    return RP


def l1_trades(RP, sym, start, end=None):
    """Config A WYCKOFF-BOOK scan trades of one symbol whose entry is in [start, end) -- reprice_real_costs' own scan call
    (15m, no flatten). Only their entry fields are read before l1_rows admits them.
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    RP.bt.reset_opts()
    RP.bt.OPTS.update(RP.CONFIG_A)
    s0 = RP.bt.scan(sym, RP.TF, opts=RP.CONFIG_A)
    return [t for t in (s0["trades"]["WYCKOFF-BOOK"] if s0 else [])
            if t["entry_time"] >= start and (end is None or t["entry_time"] < end)]


def l1_rows(RP, sym, trades):
    """`trades` admitted and costed exactly as reprice_real_costs._cell does (bt.simulate with config A's fee and the
    real-cost profile, entry order type from methods.RUNNER_METHODS), one row per taken trade. Trades are filtered to the
    window BEFORE simulate, so its account state starts in the window.
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    RP.bt.reset_opts()
    eot = "maker" if RP._M.RUNNER_METHODS["WYCKOFF-BOOK"]["entry"] == "limit" else "taker"
    _eq, _curve, taken = RP.bt.simulate(trades, RP.FEE, entry_order_type=eot, live_parity_sizing=False,
                                        cost_profile=RP.PROFILE)
    return [{"symbol": sym, "date": t["entry_time"][:10], "entry_time": t["entry_time"], "exit_time": t["exit_time"],
             "side": t["side"], "leg": t.get("leg"), "R": t["R"], "net_R": t["net_R"]} for t in taken]


def l1_summary(rows):
    """Mean net R per trade with CR1 by date, Student-t one-sided (§7.3 gate: p < L1_P and net > 0).
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if not rows:
        return {"n": 0, "pass": False}
    mu, se, df = EC.cr1([r["net_R"] for r in rows], [r["date"] for r in rows])
    t = mu / se if se else None
    p1 = EC.t_sf(t, df) if t is not None else 1.0
    return {"n": len(rows), "days": len(set(r["date"] for r in rows)), "mean_gross_R": _mean(r["R"] for r in rows),
            "mean_net_R": mu, "se_cr1_date": se, "df": df, "t": t, "p_one_sided": p1, "pass": bool(mu > 0 and p1 < L1_P)}


def run_l1(RP, start=DEV_CUTOFF, end=None, symbols=None, descriptive=True, gate=None):
    """(rows, descriptive) of L1 over [start, end): the 6 indices pooled; DE40, US500 and XAUUSD summarised apart
    (descriptive). `gate(n_trades)` (the forward read) runs on the scan trade count BEFORE any trade is admitted or costed.
    [prereg §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    syms = list(L1_SYMBOLS if symbols is None else symbols)
    extra = [s for s in L1_DESCRIPTIVE if descriptive and s not in syms]
    trades = {sym: l1_trades(RP, sym, start, end) for sym in syms + extra}
    if gate is not None:
        gate(sum(len(trades[s]) for s in syms))
    rows = [r for sym in syms for r in l1_rows(RP, sym, trades[sym])]
    desc = {}
    for sym in (L1_DESCRIPTIVE if descriptive else ()):
        desc[sym] = l1_summary([r for r in rows if r["symbol"] == sym] if sym in syms else l1_rows(RP, sym, trades[sym]))
    return rows, desc


def _dump(res, path):
    """The read JSON with one trade row per line (edge_h7x's writer).
    [prereg §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    H7._dump(res, path)


def run(read, out_path, counts_path=None, after=None, perturb=None, require_clean=True, loader=load_ftmo,
        vloader=load_binance, funding_loader=H7.load_funding, cost_r=None, l1=None, symbols=None, timeframes=TIMEFRAMES,
        perturb_paths=None, desc_timeframes=TIMEFRAMES_DESC):
    """One registered read, ONCE: R1 (all of family W, G-C and the descriptive cells, 1D included), a perturbation of R1
    (the cells meeting gates 1-3 only), R2 / R3 (survivor cells only), V, or L1. Refuses -- before any data is touched --
    unless the sealed pre-registration is committed (always), costs are in the server-table hour frame, the read is in
    order on a passing R0 and, under the guard (the CLI default), the --out path is canonical without history, the ledger
    names the study, every file in COMMITTED is tracked and clean, CLEAN_TREES are clean, every loaded module is in CODE
    and the code is R0's. One read per process.
    [prereg §4 "Reads", §6, §7.3, §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    sealed = _require_sealed()
    _require_hour_frame()
    chain = _check_order(read, counts_path, after, perturb, require_clean, perturb_paths)
    name = out_name(read, perturb)
    engine()
    RP = (l1 or l1_engine()) if read == "L1" else None        # loaded BEFORE the guard: its imports are checked too
    guard = _require_registration(name, out_path, sealed) if require_clean else {}
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: each read is run ONCE (§4); refusing to overwrite")
    _require_fresh_process(f"run {name}")
    bt = engine()
    meta = dict(_meta("read", read, perturb), guarded=require_clean, sealed=sealed, **guard)
    for k, v in (("counts", counts_path), ("after", after)):
        if v:
            meta[k] = {"path": _rel(v), "sha256": _sha256(v)}
    res = {"meta": meta, "data": {}, "skipped": {}, "tests": {}, "descriptive": {}}
    if read == "L1":
        rows, desc = run_l1(RP, symbols=symbols)
        res["tests"]["L1"] = dict(l1_summary(rows), exposed=True, pooled_over=list(L1_SYMBOLS))
        res["tests"]["L1"]["label"] = ("PASS: forward stage only" if res["tests"]["L1"]["pass"]
                                       else "FAIL: the DE40/US500 lead is closed")
        res["descriptive"] = desc
        res["rows"] = {"L1": rows}
        _dump(res, out_path)
        print(f"L1 n {res['tests']['L1']['n']} net {res['tests']['L1'].get('mean_net_R')} "
              f"p1 {res['tests']['L1'].get('p_one_sided')} | {res['tests']['L1']['label']}\nwrote {out_path}")
        return res
    if read == "V":
        r0 = chain["r0"]
        cfg = dict(BASE_CFG)
        rows, skipped, data = run_v(cfg, vloader, funding_loader, r0["dense"], bt, symbols=symbols)
        res["tests"] = v_verdicts(v_tests(rows, r0["confirmatory"]["V"]))
        res["registered"] = {"dense": r0["dense"], "confirmatory": r0["confirmatory"]["V"]}
        res.update(data=data, skipped=skipped, family={"cells": list(V_CELLS), "bh_q": FDR_Q,
                                                        "confirmatory": r0["confirmatory"]["V"]})
        res["rows"] = {c: rows.get(c, []) for c in ("V1", "V2", "V4")}
        _dump(res, out_path)
        for c in V_CELLS:
            print(f"{c}: {res['tests'][c].get('verdict')}")
        print(f"wrote {out_path}")
        return res
    syms = symbols or (TRADEABLE if read in ("R1", "R3") else [s for v in REPLICATION.values() for s in v])
    if read == "R1" and perturb is None:
        r0 = chain["r0"]
        dense, gc_n, conf = r0["dense"], {k: v for k, v in r0["gc_n"].items()}, r0["confirmatory"]["W"]
        cfg, cells = dict(BASE_CFG), None
    else:
        r1 = chain["r1"]
        dense, gc_n, conf = r1["registered"]["dense"], r1["registered"]["gc_n"], r1["registered"]["confirmatory"]
        cfg = dict(BASE_CFG, **{k: v for k, v in PERTURBATIONS[perturb].items() if k != "change"}) if perturb \
            else dict(BASE_CFG)
        cells = chain["cells"]
    pricer = Pricer("ftmo", cost_r=cost_r)
    tfs = list(timeframes) + (list(desc_timeframes) if cells is None else [])   # 1D: R1, descriptive only
    rows, skipped, data = run_w(read, cfg, syms, tfs, loader, dense, gc_n, cells, pricer, bt)
    res.update(data=data, skipped=skipped)
    res["registered"] = {"dense": dense, "gc_n": gc_n, "confirmatory": conf}
    for c in (W_CELLS if cells is None else cells):
        res["tests"][c] = w_test(c, rows.get(c, []), c in conf)
    if read == "R1" and perturb is None:
        r1_verdicts(res["tests"])
        for c, g in GC_CONTRAST.items():
            res["tests"][c]["gc_contrast"] = week_bootstrap(rows.get(c, []), rows.get(g, []),
                                                            lambda r: r["net_excess"], _seed(SEED_TAG, "GC", c))
            res["tests"][c]["gc_contrast_known"] = week_bootstrap(rows.get(c, []), rows.get(GC_CONTRAST_KNOWN[c], []),
                                                                  lambda r: r["net_excess"],
                                                                  _seed(SEED_TAG, "GC-known", c))
        for c in sorted(set(rows) - set(W_CELLS)):
            res["descriptive"][c] = summarise(rows[c], FTMO_LINES)
        for c in W_CELLS:                               # §3.7 / §11 item 9: the same rows against the trend-matched placebo
            tr = [dict(r, placebo=r["placebo_trend"], excess=r["excess_trend"],
                       net_excess=r["excess_trend"] - r["cost"][FTMO_LINES[0]])
                  for r in rows.get(c, []) if r.get("excess_trend") is not None]
            if c != "W-CAMP":
                res["descriptive"][f"desc:{c}|trend-placebo"] = dict(
                    summarise(tr, FTMO_LINES), rows_without_a_matched_placebo=len(rows.get(c, [])) - len(tr))
        res["family"] = {"cells": list(W_CELLS), "confirmatory": conf, "bh_m": len(conf), "q": FDR_Q, "delta": DELTA}
    elif read == "R2":
        for c in cells:
            res["tests"][c].update(r2_pass(rows.get(c, [])))
    elif read == "R3":
        for c in cells:
            s = res["tests"][c]["summary"]
            res["tests"][c]["r3_veto"] = not (s.get("n") and s["net_excess"] > 0)
            res["tests"][c]["flagged_rows"] = sum(1 for r in rows.get(c, []) if r["flag"])
    res["rows"] = {c: rows.get(c, []) for c in res["tests"]}
    if read == "R1" and perturb is None:
        res["rows"].update({c: rows[c] for c in rows if c.startswith("G-C")})
    _dump(res, out_path)
    for c, t in res["tests"].items():
        s = t["summary"]
        print(f"{name} {c}: n {s.get('n', 0)} net excess {s.get('net_excess')} p1 {s.get('p_one_sided')} "
              f"| {t.get('verdict') or t.get('r2_pass') or t.get('r3_veto')}")
    print(f"wrote {out_path}")
    return res


# ------------------------------------------------------------------------------------------------ R4 forward
def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def forward(cell, out_path, since=None, require_clean=True, loader=load_ftmo, vloader=load_binance,
            funding_loader=H7.load_funding, cost_r=None, l1=None, chain_paths=None, symbols=None):
    """R4: one forward read of one surviving cell on bars after sealing, ONCE, when it first has >= FORWARD_EVENTS forward
    events (counted outcome-blind first) or FORWARD_MONTHS months of forward bars, whichever comes first. Family-W cells
    need EDGE-CANDIDATE from R1 + the perturbations + R2 + R3; V cells EDGE-CANDIDATE in V; "L1" a passed L1. PASS iff
    mean net > 0 and one-sided p < FORWARD_P. The forward window starts AT the seal instant (`_seal`, the sealing commit's
    committer date) -- nobody chooses it: under the guard any other `since` refuses (the CLI has no --since).
    [prereg §4 R4, §6.2, §6.3, §7.3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    sealed = _require_sealed()
    _require_hour_frame()
    since = sealed["seal_instant"] if since is None else since
    if require_clean and since != sealed["seal_instant"]:
        raise SystemExit(f"refusing: the forward window starts at the seal ({sealed['seal_instant']}), not {since} (§4 R4)")
    d = os.path.join(ROOT, CANONICAL_DIR.format(seal=sealed["seal_date"]))
    paths = chain_paths or {n: os.path.join(d, f"edge-wyckoff-{n}.json")
                            for n in ["R1", "R2", "R3", "V", "L1"] + [f"R1-{p}" for p in PERTURBATIONS]}
    recs = {}
    for n, p in paths.items():
        if os.path.exists(p):
            rd, pt = (n.split("-", 1) + [None])[:2] if n.startswith("R1-") else (n, None)
            recs[n] = _read_json(p, "read", rd, pt)
            _tie(p, recs[n], require_clean)
    if cell in W_CELLS:
        need = ["R1", "R2", "R3"] + [f"R1-{p}" for p in PERTURBATIONS]
        if any(n not in recs for n in need):
            raise SystemExit(f"refusing: {cell} has no complete R1 / perturbation / R2 / R3 chain")
        lab = final_label(cell, recs["R1"], {p: recs[f"R1-{p}"] for p in PERTURBATIONS}, recs["R2"], recs["R3"])
        ok = lab["label"] == "EDGE-CANDIDATE"
    elif cell in V_CELLS:
        ok = "V" in recs and (recs["V"]["tests"].get(cell, {}).get("verdict") or {}).get("label") == "EDGE-CANDIDATE"
    elif cell == "L1":
        ok = "L1" in recs and recs["L1"]["tests"]["L1"]["pass"]
    else:
        raise SystemExit(f"unknown cell {cell}")
    if not ok:
        raise SystemExit(f"refusing: {cell} is not a surviving cell; R4 reads survivors only (§4)")
    name = f"R4-{cell}"
    engine()
    RP = (l1 or l1_engine()) if cell == "L1" else None       # loaded BEFORE the guard: its imports are checked too
    guard = _require_registration(name, out_path, sealed) if require_clean else {}
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: each forward read is run ONCE (§4); refusing to overwrite")
    _require_fresh_process(f"forward {cell}")
    bt = engine()
    res = {"meta": dict(_meta("forward", name), guarded=require_clean, sealed=sealed, since=since, **guard),
           "cell": cell, "data": {}}
    if cell == "L1":
        last = _last_bar(loader, symbols or L1_SYMBOLS, "15m", since)
        rows, _ = run_l1(RP, start=since, symbols=symbols, descriptive=False,
                         gate=lambda n: _forward_gate(n, since, last))
        s = l1_summary(rows)
        res.update(summary=s, rows={"L1": rows}, verdict={"pass": bool(s["n"] and s["mean_net_R"] > 0
                                                                       and s["p_one_sided"] < FORWARD_P)})
    elif cell in V_CELLS:
        dense = _dense_from_chain(recs, "V")
        cnt = _forward_count(cell, symbols or v_symbols(), vloader, dense, since, "V")
        _forward_gate(cnt["events"], since, cnt["last_bar"])
        rows, _sk, data = run_v(dict(BASE_CFG), vloader, funding_loader, dense, bt, symbols=symbols, window=(since, None))
        rs = rows.get(cell, [])
        res.update(data=data, rows={cell: rs}, summary=summarise(rs, V_LINES), forward_count=cnt)
        res["verdict"] = _forward_verdict(res["summary"])
    else:
        dense, gc_n = recs["R1"]["registered"]["dense"], recs["R1"]["registered"]["gc_n"]
        cnt = _forward_count(cell, symbols or TRADEABLE, loader, dense, since, "W")
        _forward_gate(cnt["events"], since, cnt["last_bar"])
        rows, _sk, data = run_w((since, None), dict(BASE_CFG), symbols or TRADEABLE, TIMEFRAMES, loader, dense, gc_n,
                                [cell], Pricer("ftmo", cost_r=cost_r), bt)
        rs = rows.get(cell, [])
        res.update(data=data, rows={cell: rs}, summary=summarise(rs, FTMO_LINES), forward_count=cnt)
        res["verdict"] = _forward_verdict(res["summary"])
    _dump(res, out_path)
    print(f"R4 {cell}: {res.get('verdict')}\nwrote {out_path}")
    return res


def _dense_from_chain(recs, family):
    """The dense table a forward read reuses: the one R1 (family W) or V registered from R0.
    [prereg §4 "Dense-data rule": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if family == "V":
        return recs["V"]["registered"]["dense"]
    return recs["R1"]["registered"]["dense"]


def _last_bar(loader, symbols, tf, since):
    """The latest bar time over `symbols` (bar times only), for the forward months clause.
    [prereg §4 R4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    last = since
    for sym in symbols:
        c, _ = loader(sym, tf)
        if c:
            last = max(last, c[-1]["time"])
    return last


def _forward_count(cell, symbols, loader, dense, lo, family="W"):
    """OUTCOME-BLIND: the cell's forward events (entry open >= lo, counted as the read counts them) and the last forward
    bar time. [prereg §4 R4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    n, last = collections.Counter(), lo
    cfg = dict(BASE_CFG)
    P = det_params(cfg, family)
    venue = "binance" if family == "V" else "ftmo"
    for sym in symbols:
        for tf in (V_TIMEFRAMES if family == "V" else TIMEFRAMES):
            S = make_series(sym, tf, loader, dense, cfg, venue)
            if S is None:
                continue
            last = max(last, S.T[-1])
            h = htf_of(tf)
            Hs = make_series(sym, h, loader, dense, cfg, venue) if h else None
            evs = series_events(S, Htf(Hs, P) if Hs is not None else None, cfg, family)
            for leg in ("W-C", "W-D", "W-CAMP", "V4"):
                for ev in evs[leg]:
                    if kept(S, ev, lo, None):
                        n.update(cells_of(ev, family))
    events = min(n["V3:type1"], n["V3:type23"]) if cell == "V3" else n[cell]
    return {"events": events, "last_bar": last, "by_cell": dict(n)}


def _forward_gate(n, since, last):
    """§4 R4: read once at >= FORWARD_EVENTS forward events or FORWARD_MONTHS months, whichever comes first.
    [prereg §4 R4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if n < FORWARD_EVENTS and _months(_utc(since), _utc(last)) < FORWARD_MONTHS:
        raise SystemExit(f"refusing: {n} forward events and {_months(_utc(since), _utc(last))} months since {since}; the "
                         f"forward read waits for {FORWARD_EVENTS} events or {FORWARD_MONTHS} months (§4 R4)")


def _forward_verdict(s):
    return {"pass": bool(s.get("n")) and s["net_excess"] > 0 and s["p_one_sided"] < FORWARD_P, "p_threshold": FORWARD_P}


# ------------------------------------------------------------------------------------------------ report
def report(out_path, paths=None, require_clean=True, r4_paths=None):
    """The verdict table of every read present (no data is read): per family-W cell its §6.2 label (and attribution), the
    closing rule, family V's labels, L1's label and any R4 verdicts; JSON at --out and Markdown beside it. Every record --
    the R4 ones (edge-wyckoff-R4-<cell>.json in the record directory, or `r4_paths` {cell: path}) included -- is read as
    this script's record of its kind and `_tie`d; one that is not refuses the report.
    [prereg §6, §9: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    sealed = _require_sealed()
    d = os.path.join(ROOT, CANONICAL_DIR.format(seal=sealed["seal_date"]))
    if require_clean:
        _require_canonical(out_path, CANONICAL_OUT.format(seal=sealed["seal_date"], name="report"))
    names = ["R1", "R2", "R3", "V", "L1"] + [f"R1-{p}" for p in PERTURBATIONS]
    paths = paths or {n: os.path.join(d, f"edge-wyckoff-{n}.json") for n in names}
    recs = {}
    for n, p in paths.items():
        if os.path.exists(p):
            rd, pt = (n.split("-", 1) + [None])[:2] if n.startswith("R1-") else (n, None)
            recs[n] = _read_json(p, "read", rd, pt)
            _tie(p, recs[n], require_clean)
    out = {"meta": dict(_meta("report"), guarded=require_clean, sealed=sealed, reads=sorted(recs)), "W": {}, "V": {},
           "L1": None, "R4": {}}
    if "R1" in recs:
        perts = {p: recs[f"R1-{p}"] for p in PERTURBATIONS if f"R1-{p}" in recs} or None
        for c in W_CELLS:
            out["W"][c] = final_label(c, recs["R1"], perts, recs.get("R2"), recs.get("R3"))
        out["closing"] = closing_rule(out["W"], recs["R1"])
    if "V" in recs:
        out["V"] = {c: recs["V"]["tests"].get(c, {}).get("verdict") for c in V_CELLS}
    if "L1" in recs:
        out["L1"] = {k: recs["L1"]["tests"]["L1"].get(k) for k in ("n", "mean_net_R", "p_one_sided", "pass", "label")}
    if r4_paths is None:
        pre, ext = "edge-wyckoff-R4-", ".json"
        r4_paths = {f[len(pre):-len(ext)]: os.path.join(d, f) for f in (sorted(os.listdir(d)) if os.path.isdir(d) else ())
                    if f.startswith(pre) and f.endswith(ext)}
    for cell, p in sorted(r4_paths.items()):
        rec = _read_json(p, "forward", f"R4-{cell}")
        if rec.get("cell") != cell:
            raise SystemExit(f"refusing: {p} is the R4 record of {rec.get('cell')!r}, not of {cell!r}")
        _tie(p, rec, require_clean)
        out["R4"][cell] = rec.get("verdict")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, default=str)
    md = ["| cell | label | detail |", "|---|---|---|"]
    for c, v in out["W"].items():
        md.append(f"| {c} | {v['label']} | {v.get('attribution') or v.get('why') or ''} |")
    for c, v in out["V"].items():
        md.append(f"| {c} | {(v or {}).get('label')} | family V |")
    if out["L1"]:
        md.append(f"| L1 | {out['L1']['label']} | exposed window |")
    if "closing" in out:
        md.append("")
        md.append(f"Closing rule (price-mechanical, CFDs): {out['closing']['closed_price_mechanical_on_cfds']}; "
                  "closed overall: never in this study (family V cannot close at its power).")
    with open(os.path.splitext(out_path)[0] + ".md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    print(f"wrote {out_path}")
    return out


# ------------------------------------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("counts")
    c.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    r.add_argument("--counts")
    r.add_argument("--after")
    r.add_argument("--perturb", choices=list(PERTURBATIONS))
    f = sub.add_parser("forward")                     # no --since: the window starts at the seal instant (§4 R4)
    f.add_argument("--cell", required=True, choices=list(W_CELLS) + list(V_CELLS) + ["L1"])
    f.add_argument("--out", required=True)
    p = sub.add_parser("report")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "counts":
        counts(a.out)
    elif a.cmd == "run":
        run(a.read, a.out, counts_path=a.counts, after=a.after, perturb=a.perturb)
    elif a.cmd == "forward":
        forward(a.cell, a.out)
    else:
        report(a.out)


if __name__ == "__main__":
    main()
