#!/usr/bin/env python3
"""Wyckoff engine ablation, read ABL (docs/plans/2026-10-04-wyckoff-retest-preregistration.md §7.1-§7.2, §10 item 4; written
against its -DRAFT): which of the engine's departures from the books, and which of the past scoring choices, moved the past
absolute-R reads of WYCKOFF-BOOK. DESCRIPTIVE ONLY (§7.1): nothing here enters a BH family, nothing is selected, and no arm
can become a candidate except through a new pre-registration on forward data. ONE ARM PER PROCESS (§7.1):

    python3 scripts/research/wyckoff_ablation.py count  --arm ENGINE-BOOK --counts <R0 json> --out <json>   # OUTCOME-BLIND
    python3 scripts/research/wyckoff_ablation.py run    --arm ENGINE-BOOK --counts <R0 json> \
        --out docs/experiments/wyckoff-retest-<seal date>/ablation-ENGINE-BOOK.json           # the ABL read of ONE arm, once
    python3 scripts/research/wyckoff_ablation.py report \
        --out docs/experiments/wyckoff-retest-<seal date>/ablation-report.json               # the 13 arm records, no data

<R0 json> = the R0 counts record of scripts/research/edge_wyckoff.py, the one the sealed pre-registration names.

Data (§4, §7.1): FTMO-Demo bars (data/history/ftmo through BT_HISTORY_ROOT) of the 8 tradeable symbols (edge_census METALS +
INDICES) at 15m / 1H / 4H, cut by the engine's own load-time seam bt.pit_cutoff("2024-03-01T00:00:00Z") -- the R1 window. The
§4 dense table is the one R0 PINS ("R0 pins the exact table"), never recomputed here: each series' dense start is R0's (a
series R0 gave none is not read), its dense days follow from that start (edge_wyckoff.dense_days), and an event counts only
if the server day before its signal bar was dense and its whole detection window (the arm's fx_w6_window bars ending at the
signal bar) lies on or after the dense start -- family W's DET-PO series start there too. The higher-timeframe series the
engine's W7 target / HTF gate read inside bt.scan are not cut at the dense start (disclosed).

Signals (§10 item 4): bt.scan(sym, tf, only=("WYCKOFF-BOOK",), opts=<the arm's scan overlay>) on a FRESH backtest-methods
module. The engine fills at the signal bar's CLOSE and stamps that bar's OPEN time, so the signal bar k is the bar at the
trade's entry_time. Only the decision fields (side, leg, stop, target, entry time) of a scan trade are read; its walk outcome is
read by LEGACY-as-scored alone, which IS the engine's own scoring.

Arms (§7.2, `ARMS`): two references, ENGINE-BOOK, and A1..A10 -- each one variable away from ENGINE-BOOK.
* LEGACY-as-scored: every fx_ key at v1 (Shakeouts skipped, ceiling + 1 x TR Phase-D target), the ICT HTF gate; per (symbol,
  timeframe) bt.simulate(trades, 0.05 % flat fee per side) with its planned-R:R floor (bt.MIN_RR = 2.5) and its
  one-position-per-symbol rule; fill at the signal close; absolute R = simulate's own net_R.
* LEGACY-rescored: the trades LEGACY-as-scored admitted, scored as below (it isolates the scoring).
* ENGINE-BOOK: fx_w1/w2/w3/w5 on, fx_w_shakeout=test, no floor, no ICT gate, fx_w7_htf_target with fx_w7_contain=on; fill
  at the next open, fx_gap_fill on, real cost.

Scoring (§5 as §7.1 applies it): entry = O[k+1] (A9: C[k]); an entry at or beyond the stop or the target is skipped and
counted; A2 admits only R_planned - (entry-knowable cost) >= bt.MIN_RR. Gross R from bt.walk on the planned stop distance
(cap bt.P[tf]["H"], stop before target on one bar, the arm's mgmt / gap-fill / rollover keys). A next-open entry is walked on
arrays starting AT its own bar (`walk_from`), so walk()'s "filled at the previous close" rollover pre-check never applies to a
fill that happened at an open. Placebo: up to 200 bars p drawn without replacement (seed sha256("WY-P0|sym|tf|signal time"))
from the same series, the same server-clock slot as the event's entry bar k+1, previous server day dense, ATR20 at p-1 > 0;
each gets the event's stop and target distances in ATR20 multiples (the event's at its signal bar k, the placebo's at p-1),
the event's side, cap and walk rules. excess = R - mean(placebo R), both gross; net = excess - cost. Cost: real_costs.cost_r
(entry, stop, entry time, exit time, sym, side, "ftmo_demo_2026_09_relspread", stat) in the server-table hour frame (checked
before any data is touched), four lines {median, p90 spread} x {today's swap, zero swap}; commission 0/UNKNOWN.
Statistics (descriptive): CR1 by ISO week of the signal bar (edge_census.cr1 / t_sf). `report`: per arm, leg and timeframe n,
mean gross R, mean net R and mean net excess, and ENGINE-BOOK minus the arm with a 90 % CI from 2,000 resamples of whole weeks
(fixed seed), drawn from the union of the two arms' weeks so the pairing across arms is kept.

Guards (edge_h7x pattern): `run` and `report` refuse, ALWAYS, unless the SEALED pre-registration (PREREG, the file without
-DRAFT) exists and is committed; `count` and `run` refuse, ALWAYS, unless the R0 record passed its truncation probe. Under the
registration guard (the CLI default) the --out path must be the canonical one under docs/experiments/wyckoff-retest-<seal
date>/ with no git history, research-ledger.json must name the sealed pre-registration, every file of the study's CODE
(edge_wyckoff.CODE: both scripts, their tests, the engine, every module it loads, the configs) must be tracked and
unmodified, scripts/, docs/architecture/ and data/history/costs/ must be clean (untracked files included), every imported
repository module must be in CODE, and the R0 record must be committed, named in the sealed pre-registration and made by
this very code (same code_sha256: the sealed code SHA). A read is written ONCE (an existing --out is refused) and one
process runs one arm. `report` refuses until all 13 arm records exist with the same registered meta -- the same script and
code fingerprint and the same R0 included -- and, under the guard, were themselves written under it and committed, on the
code of now and of R0.

Read-only on repo data. Nothing here touches the fund search, the live path or any account."""
import argparse
import bisect
import collections
import contextlib
import datetime
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EC = _load("edge_census", "scripts/research/edge_census.py")   # cr1, t_sf, symbol groups, cost profile (puts scripts/ on sys.path)
EW = _load("edge_wyckoff_abl", "scripts/research/edge_wyckoff.py")   # R0 (_r0, dense_days), the study's CODE and fingerprint
import normalized as _N  # noqa: E402
import real_costs as RC  # noqa: E402

PREREG_DRAFT = "docs/plans/2026-10-04-wyckoff-retest-preregistration-DRAFT.md"
PREREG = "docs/plans/2026-10-04-wyckoff-retest-preregistration.md"      # the SEALED file: run / report refuse without it
SCRIPT = "scripts/research/wyckoff_ablation.py"
TESTS_FILE = "scripts/tests/test_wyckoff_ablation.py"
LEDGER = "docs/architecture/research-ledger.json"
ENGINE = "scripts/backtest-methods.py"
CANONICAL_DIR = "docs/experiments/wyckoff-retest-{seal}"
CANONICAL_OUT = CANONICAL_DIR + "/ablation-{arm}.json"
CANONICAL_REPORT = CANONICAL_DIR + "/ablation-report.json"
#: One sealed code SHA for the whole study (§10 items 3-4): edge_wyckoff's CODE lists this script, its tests, the engine, every
#: module it loads and the configs; the ledger and the sealed file are tracked and clean but outside the fingerprint.
CODE = EW.CODE
COMMITTED = (PREREG, LEDGER) + CODE
CLEAN_TREES = EW.CLEAN_TREES
UTC = datetime.timezone.utc
METHOD = "WYCKOFF-BOOK"
SYMBOLS = tuple(EC.METALS) + tuple(EC.INDICES)       # §4 tradeable: XAUUSD, XAGUSD; US500, US30, USTEC, DE40, FRA40, AUS200
TIMEFRAMES = ("15m", "1H", "4H")
LEGS = ("spring", "phase_d")
DEV_CUTOFF = EC.DEV_CUTOFF                            # "2024-03-01T00:00:00Z": R1 = every bar available before it
HIST_ROOT = EC.HIST_ROOT                              # data/history/ftmo
COST_PROFILE = EC.COST_PROFILE                        # "ftmo_demo_2026_09_relspread" (§5)
PROVIDER = EC.PROVIDER                                # "mt5_bridge_ftmo": whose server clock (slots, server days, rollover)
HOUR_FRAME = "server_table"                           # RC.HOUR_FRAME a read must run in (§5; erratum 2026-10-04)
SPREAD_STATS = ("median", "p90")
COST_LINES = ("median_swap", "median_noswap", "p90_swap", "p90_noswap")
LEGACY_FEE = 0.0005                                   # LEGACY-as-scored: 0.05 % per side, flat (§7.2)
N_PLACEBO = 200
ATR_N = 20
SEED_TAG = "WY-P0"
A7_DAYS = 20                                         # A7 / P2: tick volume / trailing 20-day median at the same server hour
BOOT_N = 2000
BOOT_CI = (0.05, 0.95)

# ------------------------------------------------------------------------------------------------ arms (§7.2)
_ENGINE_SCAN = dict(fx_w1_tr_low_st=True, fx_w2_st_below_sc=True, fx_w3_mSOW_spring=True, fx_w5_vp_abandon=True,
                    fx_w_shakeout="test", htf=False, fx_w7_htf_target=True, fx_w7_contain="on", fx_gap_fill=True)
_ENGINE_WALK = dict(fx_gap_fill=True)                 # mgmt "none" and no flatten: the OPTS baseline
_ROLLOVER = dict(flat_before_rollover=True, rollover_provider=PROVIDER)


def _arm(change, scan=None, walk=None, **kw):
    """ENGINE-BOOK with ONE change. Fields: scan (the bt.scan overlay), walk (the OPTS walk() reads when an event is
    re-walked), signals ("scan" | "legacy_sim"), fill ("next_open" | "signal_close"), score ("placebo" | "absolute"), floor
    (None | "entry_cost" | "legacy_sim"), volume ("raw" | "hour_norm")."""
    a = dict(change=change, scan=dict(_ENGINE_SCAN, **(scan or {})), walk=dict(_ENGINE_WALK, **(walk or {})),
             signals="scan", fill="next_open", score="placebo", floor=None, volume="raw")
    a.update(kw)
    return a


_LEGACY = dict(scan=dict(htf=True), signals="legacy_sim", floor="legacy_sim", volume="raw")
ARMS = collections.OrderedDict([
    ("LEGACY-as-scored", dict(_LEGACY, change="reference: the engine as it was judged (simulate, flat fee, floor, absolute R)",
                              walk={}, fill="signal_close", score="absolute")),
    ("LEGACY-rescored", dict(_LEGACY, change="reference: LEGACY-as-scored's admitted trades, scored with §5",
                             walk=dict(_ENGINE_WALK), fill="next_open", score="placebo")),
    ("ENGINE-BOOK", _arm("reference: the book-faithful engine")),
    ("A1", _arm("skip Shakeouts", scan=dict(fx_w_shakeout="off"))),
    ("A2", _arm("2.5R floor in the harness, cost known at entry", floor="entry_cost")),
    ("A3", _arm("ICT HTF gate", scan=dict(htf=True))),
    ("A4", _arm("Phase-D target ceiling + 1 x TR", scan=dict(fx_w7_htf_target=False, fx_w7_contain="off"))),
    ("A5", _arm("600-bar window", scan=dict(fx_w6_window=600))),
    ("A6", _arm("fx_w_stop=spring_low", scan=dict(fx_w_stop="spring_low"))),
    ("A7", _arm("tick volume normalised by hour", volume="hour_norm")),
    ("A8", _arm("fx_w_spt=ceiling", scan=dict(fx_w_spt="ceiling"))),
    ("A9", _arm("fill at the signal close", fill="signal_close")),
    ("A10", _arm("flat_before_rollover", scan=dict(_ROLLOVER), walk=dict(_ROLLOVER))),
])
REFERENCE = "ENGINE-BOOK"
#: Equal across the 13 arm records and to this code (`_check_order`): the design AND the code -- an arm made by other code,
#: or on another R0 ("counts"), is refused.
META_FIXED = ("preregistration", "preregistration_sha256", "symbols", "timeframes", "legs", "dev_cutoff", "arms",
              "parameters", "costs", "script_sha256", "code_sha256")
_PROCESS = {"used": None}                             # one arm per process (§7.1): the first command that touches the engine


# ------------------------------------------------------------------------------------------------ small helpers
def _utc(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))


def _iso(d):
    return d.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def _quantile(sorted_xs, q):
    """Linear interpolation between order statistics of an already sorted list; None when empty."""
    if not sorted_xs:
        return None
    pos = q * (len(sorted_xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _seed(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16], 16)


def server_zone():
    return RC.server_zone(PROVIDER)[1]


def placeable(side, entry, stop, target):
    """True iff `entry` lies strictly between the stop and the target (a long: stop < entry < target).
    [prereg §3.2 "Skips": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return stop < entry < target if side == "long" else target < entry < stop


def week_of(dt):
    """ISO week of a UTC instant, "YYYY-Www" -- the CR1 / bootstrap cluster (§5)."""
    y, w, _ = dt.astimezone(UTC).isocalendar()
    return f"{y}-W{w:02d}"


# ------------------------------------------------------------------------------------------------ data rules (counts only)
def r0_record(counts_path, require_clean):
    """The R0 counts record of edge_wyckoff this read rests on (edge_wyckoff._r0: ALWAYS a passing truncation probe; under
    the guard committed, named in the sealed pre-registration, made by this very code, the registered design).
    [prereg §4 R0, §10 items 4-6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return EW._r0(counts_path, require_clean)


def dense_start(r0, sym, tf):
    """The §4 dense start R0 pinned for (sym, tf) as a date, or None (R0 found none: the series is not read).
    [prereg §4 "R0 pins the exact table": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    s = ((r0.get("dense") or {}).get(f"{sym}|{tf}") or {}).get("start")
    return datetime.date.fromisoformat(s) if s else None


def atr20(H, L, C, n=ATR_N):
    """ATR at bar j = mean true range of bars j-n+1 .. j (true range needs the previous close, so the first value is at
    j = n); None before. Known at the CLOSE of j. [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    tr = [None] + [max(H[j] - L[j], abs(H[j] - C[j - 1]), abs(L[j] - C[j - 1])) for j in range(1, len(C))]
    return [sum(tr[j - n + 1:j + 1]) / n if j >= n else None for j in range(len(C))]


def hour_normalised(candles, zone, days=A7_DAYS):
    """(candles, neutral) for A7: each bar's volume divided by the median volume of the bars at the SAME server hour on the
    `days` most recent EARLIER server days that have such bars (point-in-time: the bar's own day never enters its own
    reference). A bar with no earlier same-hour bar, or a reference <= 0, gets 1.0 (its own typical level) and is counted
    in `neutral`. Prices are untouched; new dicts, the loaded ones are never written.
    [prereg §7.2 A7, §6.2 P2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    done = collections.defaultdict(collections.deque)   # hour -> deque[(day, [volumes])] of COMPLETED earlier days
    cur, memo, out, neutral = {}, {}, [], 0
    for x in candles:
        t = _utc(x["time"]).astimezone(zone)
        d, h = t.date(), t.hour
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
            vals = [v for _day, vs in done[h] for v in vs]
            memo[(h, d)] = statistics.median(vals) if vals else None
        ref = memo[(h, d)]
        v = x.get("volume", 0)
        if ref is not None and ref > 0:
            nv = v / ref
        else:
            nv, neutral = 1.0, neutral + 1
        c[1].append(v)
        out.append(dict(x, volume=nv))
    return out, neutral


class Series:
    """One (symbol, timeframe) R1 series exactly as the engine loaded it, with the per-bar facts the harness reads: server
    day and server-clock slot (minute of the server day of the bar's OPEN), the dense days from R0's dense `start`
    (edge_wyckoff.dense_days; None = nothing dense), `first_dense` (the first bar on or after the start), ATR20, and the
    placebo pools. [prereg §4, §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""

    def __init__(self, sym, tf, candles, zone, start=None):
        self.sym, self.tf, self.start = sym, tf, start
        self.group = next((g for g, syms in EC.GROUPS.items() if sym in syms), None)
        self.T = [x["time"] for x in candles]
        self.O = [x["open"] for x in candles]
        self.H = [x["high"] for x in candles]
        self.L = [x["low"] for x in candles]
        self.C = [x["close"] for x in candles]
        self.idx = {t: i for i, t in enumerate(self.T)}
        self.dt = [_utc(t) for t in self.T]
        loc = [d.astimezone(zone) for d in self.dt]
        self.sday = [x.date() for x in loc]
        self.slot = [x.hour * 60 + x.minute for x in loc]
        dense, self.prev_dense = EW.dense_days(self.sday, start)
        self.first_dense = bisect.bisect_left(self.sday, start) if start is not None else len(self.T)
        self.dense = {"start": start.isoformat() if start is not None else None, "source": "R0", "dense_days": len(dense),
                      "first_dense_bar": self.T[self.first_dense] if self.first_dense < len(self.T) else None}
        self.atr = atr20(self.H, self.L, self.C)
        self._pools = None

    def window_ok(self, k, window):
        """The `window` bars ending at signal bar k all lie on or after the dense start (family W's DET-PO series start
        there, so a window reaching into the sparse years before it is not an event of the same sample).
        [prereg §4 "Dense-data rule": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        return k - window + 1 >= self.first_dense

    def pool(self, slot):
        """Placebo candidate ENTRY bars p of one server-clock slot: previous server day dense, ATR20 at p-1 known and > 0.
        [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
        if self._pools is None:
            self._pools = collections.defaultdict(list)
            for p in range(1, len(self.C)):
                a = self.atr[p - 1]
                if self.prev_dense[p] and a is not None and a > 0:
                    self._pools[self.slot[p]].append(p)
        return self._pools.get(slot, [])

    def fill_time(self, k, fill):
        """The instant a fill for signal bar k happens: the OPEN of k+1 (its time label) or the CLOSE of k (its available
        time, open + one bar)."""
        if fill == "next_open":
            return self.T[k + 1]
        return _iso(_N.available_time({"time": self.T[k]}, self.tf))


def placebo_draw(S, slot, signal_time, n=N_PLACEBO):
    """Up to `n` placebo entry bars from the slot's pool, without replacement (all of them when fewer qualify), seeded by
    sha256("WY-P0|sym|tf|signal_time") -- the same draw for the same event in every arm.
    [prereg §5 "Placebo": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    pool = S.pool(slot)
    if len(pool) <= n:
        return list(pool)
    return sorted(random.Random(_seed(SEED_TAG, S.sym, S.tf, signal_time)).sample(pool, n))


# ------------------------------------------------------------------------------------------------ engine
def _engine():
    """A FRESH backtest-methods module (its OPTS and caches are this process's alone) on the FTMO history, cut at
    DEV_CUTOFF by its own load-time PIT seam. BT_HISTORY_ROOT is set first: the module freezes HISTORY_ROOT when it runs.
    [prereg §4, §7.1: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    os.environ["BT_HISTORY_ROOT"] = HIST_ROOT
    bt = _load("bt_wyckoff_ablation", ENGINE)
    if os.path.abspath(bt.HISTORY_ROOT) != os.path.abspath(HIST_ROOT):
        raise SystemExit(f"refusing: backtest-methods reads {bt.HISTORY_ROOT}, not {HIST_ROOT}")
    bt.pit_cutoff(DEV_CUTOFF)
    return bt


@contextlib.contextmanager
def _opts(bt, overlay):
    """bt.OPTS = the frozen baseline + `overlay` for the block (walk() and simulate() read the module global)."""
    saved = bt.OPTS
    bt.OPTS = dict(bt._OPTS_BASE, **overlay)
    try:
        yield
    finally:
        bt.OPTS = saved


@contextlib.contextmanager
def _volume(bt, mode, zone):
    """A7: every series bt.load hands out in the block (decision timeframe AND the HTF the W7 target / HTF gate read) carries
    hour-normalised volume; one normalised copy per loaded list. Yields {(sym, tf): neutral bars}. "raw": unchanged."""
    neutral = {}
    if mode == "raw":
        yield neutral
        return
    if mode != "hour_norm":
        raise SystemExit(f"unknown volume mode {mode!r}")
    real, cache = bt.load, {}

    def load(sym, tf):
        c, src = real(sym, tf)
        if not c:
            return c, src
        key = (sym, tf, len(c), c[0]["time"], c[-1]["time"])
        if key not in cache:
            cache[key], neutral[f"{sym}|{tf}"] = hour_normalised(c, zone)
        return list(cache[key]), src
    bt.load = load
    try:
        yield neutral
    finally:
        bt.load = real


def walk_from(bt, side, entry, stop, target, S, e, HZ, fill):
    """bt.walk for an event (or a placebo) whose first walked bar is e, under the CURRENT bt.OPTS. A next-open fill is
    walked on the arrays starting AT bar e (start 0): the fill happened at e's open, so walk()'s pre-check "a fill at the
    previous close carried across the rollover" cannot apply; the exit index is mapped back. A signal-close fill is the
    engine's own convention (filled at C[e-1], walked from e). Returns walk()'s dict (absolute `exit`) or None.
    [prereg §3.2 "Walk", §5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    if fill == "next_open":
        w = bt.walk(side, entry, stop, target, S.H[e:e + HZ], S.L[e:e + HZ], S.C[e:e + HZ], 0, HZ,
                    Tm=S.T[e:e + HZ], O_=S.O[e:e + HZ])
        return dict(w, exit=w["exit"] + e) if w else None
    return bt.walk(side, entry, stop, target, S.H, S.L, S.C, e, HZ, Tm=S.T, O_=S.O)


def arm_trades(bt, sym, tf, arm, legacy_admission=True):
    """(trades, sim) of one (symbol, timeframe): bt.scan(sym, tf, only=("WYCKOFF-BOOK",), opts=arm["scan"]); for the LEGACY
    arms the trades bt.simulate(trades, LEGACY_FEE) admitted under the same overlay (floor bt.MIN_RR, one position per
    symbol), sorted by entry time. `legacy_admission=False` (count) skips simulate: its admission reads exit times.
    [prereg §7.2, §10 item 4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    res = bt.scan(sym, tf, only=(METHOD,), opts=arm["scan"])
    trades = list(res["trades"].get(METHOD, [])) if res else []
    if arm["signals"] != "legacy_sim" or not legacy_admission:
        return trades, None
    with _opts(bt, arm["scan"]):
        _eq, _curve, taken = bt.simulate(trades, LEGACY_FEE)
        sim = {"scanned": len(trades), "admitted": len(taken), "ruin": bt.SIM_LAST["ruin"],
               "failed_by": bt.SIM_LAST["failed_by"], "min_rr": bt.OPTS["min_rr"]}
    return sorted(taken, key=lambda t: (t["entry_time"], t["event"])), sim


def signal(S, t):
    """The decision fields of one engine trade, at its signal bar k (the bar whose OPEN time the engine stamps; it fills at
    that bar's close). Refuses a trade that is not on this series or not filled at the signal close.
    [prereg §10 item 4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    k = S.idx.get(t["entry_time"])
    if k is None or S.C[k] != t["entry"]:
        raise SystemExit(f"refusing: {S.sym} {S.tf} engine trade {t.get('event')} at {t['entry_time']} is not filled at "
                         "a signal-bar close of the loaded series")
    return {"k": k, "side": t["side"], "leg": t["leg"], "stop": t["stop"], "target": t["target"], "event": t["event"],
            "path": t.get("path"), "signal_time": t["entry_time"]}


def _row_base(S, sig):
    k = sig["k"]
    return {"symbol": S.sym, "tf": S.tf, "group": S.group, "leg": sig["leg"], "side": sig["side"], "path": sig["path"],
            "event": sig["event"], "signal_time": S.T[k], "week": week_of(S.dt[k]), "stop": sig["stop"],
            "target": sig["target"]}


def cost_lines(cost_fn, sym, side, entry, stop, t_in, t_out):
    """The four §5 cost lines, in R: {median, p90 spread} x {today's swap, zero swap} (zero swap = total - swap_R).
    [prereg §5 "Cost (FTMO)": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {}
    for stat in SPREAD_STATS:
        c = cost_fn(entry, stop, t_in, t_out, sym, side, COST_PROFILE, stat)
        out[f"{stat}_swap"] = c["total_R"]
        out[f"{stat}_noswap"] = c["total_R"] - c["swap_R"]
    return out


def score_event(bt, S, sig, arm, cost_fn, HZ):
    """(row, None) or (None, skip reason) for one event under the CURRENT bt.OPTS (the arm's walk keys): fill, the
    placeability skip, A2's floor, gross R, the four cost lines and the ATR-multiple placebo.
    [prereg §3.2, §5, §7.2: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    k, side, fill = sig["k"], sig["side"], arm["fill"]
    e = k + 1
    if e >= len(S.C):
        return None, "no_next_bar"
    entry = S.O[e] if fill == "next_open" else S.C[k]
    stop, target = sig["stop"], sig["target"]
    if not placeable(side, entry, stop, target):
        return None, "entry_beyond_stop_or_target"
    a = S.atr[k]
    if a is None or a <= 0:
        return None, "no_atr"
    t_in = S.fill_time(k, fill)
    rr = abs(target - entry) / abs(entry - stop)
    if arm["floor"] == "entry_cost":
        # A2: the cost knowable at the entry decision -- both half-spreads at the ENTRY hour, no swap (nights held depend on
        # the exit), commission as recorded: cost_r with exit time = entry time (the O1 rule of backtest-methods.simulate).
        if rr - cost_fn(entry, stop, t_in, t_in, S.sym, side, COST_PROFILE, "median")["total_R"] < bt.MIN_RR:
            return None, "below_floor"
    w = walk_from(bt, side, entry, stop, target, S, e, HZ, fill)
    if w is None:
        return None, "no_risk"
    t_out = S.T[w["exit"]]
    costs = cost_lines(cost_fn, S.sym, side, entry, stop, t_in, t_out)
    d_stop, d_tgt = abs(entry - stop) / a, abs(target - entry) / a
    sgn = 1 if side == "long" else -1
    prs = []
    for p in placebo_draw(S, S.slot[e], S.T[k]):
        ap = S.atr[p - 1]
        ent = S.O[p] if fill == "next_open" else S.C[p - 1]
        wp = walk_from(bt, side, ent, ent - sgn * d_stop * ap, ent + sgn * d_tgt * ap, S, p, HZ, fill)
        if wp is not None:
            prs.append(wp["R"])
    if not prs:
        return None, "no_placebo"
    plc = sum(prs) / len(prs)
    excess = w["R"] - plc
    return dict(_row_base(S, sig), entry=entry, entry_time=t_in, exit_time=t_out, R_planned=rr, R=w["R"],
                outcome=w["outcome"], bars_held=w["bars_held"], atr=a, stop_atr=d_stop, target_atr=d_tgt, placebo=plc,
                n_placebo=len(prs), excess=excess, cost=costs, net_excess=excess - costs["median_swap"],
                net_abs=w["R"] - costs["median_swap"]), None


def legacy_row(S, sig, t):
    """LEGACY-as-scored: the engine's own walk (fill at the signal close, v1 stops) and simulate's own net_R (flat fee)."""
    return dict(_row_base(S, sig), entry=t["entry"], entry_time=t["entry_time"], exit_time=t["exit_time"],
                R_planned=t["R_planned"], R=t["R"], outcome=t["outcome"], bars_held=t["bars_held"], placebo=None,
                n_placebo=0, excess=None, cost=None, net_excess=None, net_abs=t["net_R"])


def arm_window(bt, arm):
    """The detection window (bars) the arm's scan uses: its fx_w6_window, else the engine's default.
    [prereg §7.2 A5: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    return arm["scan"].get("fx_w6_window", bt._OPTS_BASE["fx_w6_window"])


def symbol_rows(bt, S, arm, trades, cost_fn, HZ):
    """(rows, skipped) of one series' trades under the CURRENT bt.OPTS. An event counts only if the server day before its
    signal bar was dense and its detection window lies on or after R0's dense start (§4).
    [prereg §4, §5, §7: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rows, skipped = [], collections.Counter()
    win = arm_window(bt, arm)
    for t in trades:
        sig = signal(S, t)
        if not S.window_ok(sig["k"], win):
            skipped[f"{sig['leg']}|window_before_dense_start"] += 1
            continue
        if not S.prev_dense[sig["k"]]:
            skipped[f"{sig['leg']}|prev_day_not_dense"] += 1
            continue
        if arm["score"] == "absolute":
            rows.append(legacy_row(S, sig, t))
            continue
        row, why = score_event(bt, S, sig, arm, cost_fn, HZ)
        if row is None:
            skipped[f"{sig['leg']}|{why}"] += 1
            continue
        rows.append(row)
    return rows, skipped


# ------------------------------------------------------------------------------------------------ statistics (descriptive)
def summarise(rows):
    """One (leg, timeframe) cell: n, weeks, mean gross R, mean net R (absolute, median spread + today's swap) and, for a
    placebo arm, the mean placebo R and the net excess on each cost line with its CR1-by-week SE, t and one-sided p (edge_
    census.cr1 / t_sf) -- descriptive, no gate. [prereg §5 "Statistics", §7.1: docs/plans/2026-10-04-wyckoff-retest-
    preregistration.md]"""
    if not rows:
        return {"n": 0}
    wk = [r["week"] for r in rows]
    out = {"n": len(rows), "weeks": len(set(wk)), "mean_gross_R": _mean([r["R"] for r in rows]),
           "mean_net_abs_R": _mean([r["net_abs"] for r in rows])}
    if rows[0]["excess"] is None:
        return out
    out["mean_placebo_R"] = _mean([r["placebo"] for r in rows])
    out["mean_excess_gross"] = _mean([r["excess"] for r in rows])
    for line in COST_LINES:
        mu, se, df = EC.cr1([r["excess"] - r["cost"][line] for r in rows], wk)
        t = mu / se if se else None
        out[f"net_excess_{line}"] = {"mean": mu, "se_cr1_week": se, "df": df, "t": t,
                                     "p_one_sided": EC.t_sf(t, df) if t is not None else None}
    out["mean_net_excess"] = out["net_excess_median_swap"]["mean"]
    return out


def cells(rows):
    return {f"{leg}|{tf}": summarise([r for r in rows if r["leg"] == leg and r["tf"] == tf])
            for leg in LEGS for tf in TIMEFRAMES}


def week_bootstrap_diff(a_rows, b_rows, key, seed, n=BOOT_N, ci=BOOT_CI):
    """mean(a[key]) - mean(b[key]) and its `ci` percentile interval over `n` resamples of whole ISO weeks: each resample
    draws as many weeks as the union of both arms' weeks, with replacement, and takes both arms' events of the drawn weeks
    (an arm without an event in the draw skips that resample). Fixed seed. [prereg §7.1 "Output": docs/plans/2026-10-04-
    wyckoff-retest-preregistration.md]"""
    a = [(r["week"], r[key]) for r in a_rows if r.get(key) is not None]
    b = [(r["week"], r[key]) for r in b_rows if r.get(key) is not None]
    if not a or not b:
        return {"diff": None, "ci90": None, "n_a": len(a), "n_b": len(b)}
    sums = collections.defaultdict(lambda: [0.0, 0, 0.0, 0])
    for w, v in a:
        sums[w][0] += v
        sums[w][1] += 1
    for w, v in b:
        sums[w][2] += v
        sums[w][3] += 1
    weeks = sorted(sums)
    rows = [sums[w] for w in weeks]
    rnd = random.Random(seed)
    diffs = []
    for _ in range(n):
        sa = na = sb = nb = 0
        for x in rnd.choices(rows, k=len(rows)):
            sa += x[0]; na += x[1]; sb += x[2]; nb += x[3]
        if na and nb:
            diffs.append(sa / na - sb / nb)
    diffs.sort()
    return {"diff": _mean([v for _, v in a]) - _mean([v for _, v in b]),
            "ci90": [_quantile(diffs, ci[0]), _quantile(diffs, ci[1])] if diffs else None,
            "n_a": len(a), "n_b": len(b), "weeks": len(weeks), "resamples_used": len(diffs)}


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
    [prereg §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
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


def _seal_date():
    """The date (YYYY-MM-DD) of the commit that ADDED the sealed pre-registration, from its COMMITTER date exactly as
    edge_wyckoff._seal reads it -- the <seal date> of the canonical record directory both scripts write to (§10 item 6).
    SystemExit when git cannot say. [prereg §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rc, out = _git("log", "--diff-filter=A", "--format=%cI", "--", PREREG)
    stamps = out.split()
    if rc != 0 or not stamps:
        raise SystemExit(f"refusing: no commit adds {PREREG}; the pre-registration is not sealed")
    return datetime.datetime.fromisoformat(stamps[-1]).date().isoformat()


def _require_sealed():
    """ALWAYS before a read or a report: the SEALED pre-registration (PREREG, the file without -DRAFT) exists and is
    committed (tracked, no uncommitted change). Returns {"path", "sha256", "seal_date"}.
    [prereg header + §10 item 6: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    p = os.path.join(ROOT, PREREG)
    if not os.path.exists(p):
        raise SystemExit(f"refusing: {PREREG} does not exist -- the pre-registration is still {PREREG_DRAFT}; commit it "
                         "without -DRAFT, with the R0 table and the code SHA, before any read (§10 item 6)")
    _require_committed([PREREG])
    return {"path": PREREG, "sha256": _sha256(p), "seal_date": _seal_date()}


def _require_hour_frame():
    """§5: costs are priced in the server-table hour frame (real_costs erratum 2026-10-04); anything else refuses."""
    if RC.HOUR_FRAME != HOUR_FRAME:
        raise SystemExit(f"refusing: real_costs.HOUR_FRAME is {RC.HOUR_FRAME!r}, the read needs {HOUR_FRAME!r} (§5)")


def _require_ledger():
    """The research ledger names the sealed pre-registration (§10 item 6: the ablation count is a ledger entry)."""
    with open(os.path.join(ROOT, LEDGER), encoding="utf-8") as fh:
        if PREREG not in fh.read():
            raise SystemExit(f"refusing: {LEDGER} does not name {PREREG}; register the study (§10 item 6) before a read")


def _require_canonical(out_path, want):
    """The --out path is `want` and `want` has no git history (a read is run once)."""
    if os.path.abspath(out_path) != os.path.join(ROOT, want):
        raise SystemExit(f"refusing: this read writes {want} (got {out_path})")
    rc, log = _git("log", "--all", "--format=%H", "--", want)
    if rc != 0:
        raise SystemExit(f"refusing: cannot check the git history of {want}")
    if log.strip():
        raise SystemExit(f"refusing: {want} has git history -- this read was already run (pre-registration §4 'Reads')")


def _require_clean_trees():
    """Under the guard: nothing edited, staged or untracked under CLEAN_TREES (every module, config and cost table the engine
    can reach). [prereg §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    rc, out = _git("status", "--porcelain", "--untracked-files=all", "--", *CLEAN_TREES)
    if rc != 0 or out.strip():
        raise SystemExit(f"refusing: {', '.join(CLEAN_TREES)} must be committed and clean (untracked files included) "
                         f"before a read (pre-registration §10): " + "; ".join(out.strip().splitlines()[:8]))


def _require_code_complete():
    """Under the guard, after the engine is loaded: every repository module this process imported is in CODE.
    [prereg §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    missing = sorted(EW._loaded_code() - set(CODE))
    if missing:
        raise SystemExit(f"refusing: the engine loads {', '.join(missing)}, which CODE does not fingerprint; add it to "
                         "edge_wyckoff.CODE, re-run counts and re-seal (pre-registration §10)")


def _require_registration(arm, out_path, sealed):
    """Under the guard, before any data is touched (the engine already loaded): the canonical --out path without git
    history, the ledger entry, every file in COMMITTED tracked and clean, CLEAN_TREES clean (untracked included) and every
    imported repository module in CODE. Returns the meta fields it vouches for.
    [prereg §4 "Reads", §10: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    _require_canonical(out_path, CANONICAL_OUT.format(seal=sealed["seal_date"], arm=arm))
    _require_ledger()
    _require_committed(COMMITTED)
    _require_clean_trees()
    _require_code_complete()
    return {"committed_sha256": {p: _sha256(os.path.join(ROOT, p)) for p in COMMITTED},
            "loaded_code": sorted(EW._loaded_code())}


def _check_arm(arm):
    if arm not in ARMS:
        raise SystemExit(f"unknown arm {arm!r}; the arms are {list(ARMS)} (§7.2)")
    return ARMS[arm]


def _require_fresh_process(kind, arm):
    """One arm per process (§7.1): refuses a second engine command in the same interpreter."""
    if _PROCESS["used"]:
        raise SystemExit(f"refusing: this process already ran {_PROCESS['used']}; each arm runs in a fresh process (§7.1)")
    _PROCESS["used"] = f"{kind} {arm}"


def _check_order(arm_paths, require_clean=True):
    """{arm: record} for `report`, refusing BEFORE anything is computed unless every arm of ARMS has a record of this script
    (kind "read", its own arm) and all share the registered meta (META_FIXED: design, script and code fingerprint) and the
    same R0 ("counts"); under the guard each must also be tracked and clean, written under the guard, at a git_head that is
    an ancestor of HEAD, with the meta this code registers now, and their R0 must be unchanged and still valid (`r0_record`
    under the guard: made by this very code -- the sealed code SHA).
    [prereg §4 "Reads", §7.1, §10 item 3: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    missing = [a for a in ARMS if a not in arm_paths or not os.path.exists(arm_paths[a])]
    if missing:
        raise SystemExit(f"refusing: report needs all {len(ARMS)} arm records; missing {missing}")
    recs, cur = {}, json.loads(json.dumps(_meta("read"), default=str))
    for arm in ARMS:
        path = arm_paths[arm]
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        m = rec.get("meta", {})
        if m.get("script") != SCRIPT or m.get("kind") != "read" or m.get("arm") != arm:
            raise SystemExit(f"refusing: {path} is not the {arm} read of {SCRIPT}")
        if require_clean:
            _require_committed([_rel(path)])
            if m.get("guarded") is not True:
                raise SystemExit(f"refusing: {path} was not written under the registration guard")
            head = m.get("git_head")
            if not head or _git("merge-base", "--is-ancestor", head, "HEAD")[0] != 0:
                raise SystemExit(f"refusing: {path} was written at {head}, not an ancestor of HEAD")
            diff = [k for k in META_FIXED if m.get(k) != cur.get(k)]
            if diff:
                raise SystemExit(f"refusing: {path} was run under a different registration ({', '.join(diff)} differ)")
        recs[arm] = rec
    first = recs[next(iter(ARMS))]["meta"]
    for arm, rec in recs.items():
        diff = [k for k in META_FIXED + ("counts",) if rec["meta"].get(k) != first.get(k)]
        if diff:
            raise SystemExit(f"refusing: the {arm} record differs from the others in {', '.join(diff)}")
    if require_clean:
        c = first.get("counts")
        p = os.path.join(ROOT, c["path"]) if c else None
        if not c or not os.path.exists(p) or _sha256(p) != c["sha256"]:
            raise SystemExit(f"refusing: the arm records name no R0, or their R0 {c and c['path']} is missing or has "
                             "changed since")
        r0_record(p, True)
    return recs


def _meta(kind, arm=None):
    p = os.path.join(ROOT, PREREG)
    return {"script": SCRIPT, "script_sha256": _sha256(os.path.join(ROOT, SCRIPT)), "code_sha256": EW.code_sha256(),
            "kind": kind, "read": "ABL", "arm": arm,
            "preregistration": PREREG, "preregistration_sha256": _sha256(p) if os.path.exists(p) else None,
            "preregistration_draft": PREREG_DRAFT, "git_head": _git_head(),
            "symbols": list(SYMBOLS), "timeframes": list(TIMEFRAMES), "legs": list(LEGS), "dev_cutoff": DEV_CUTOFF,
            "history_root": os.path.relpath(HIST_ROOT, ROOT), "method": METHOD,
            "arms": {k: dict(v) for k, v in ARMS.items()},
            "parameters": {"n_placebo": N_PLACEBO, "placebo_draw": "without replacement; every candidate when fewer",
                           "placebo_seed": f"sha256('{SEED_TAG}|sym|tf|signal_time')[:16]",
                           "placebo_slot": "server-clock minute of the day of the event's ENTRY bar k+1",
                           "atr_n": ATR_N, "dense": "R0's pinned dense start per series (edge_wyckoff counts); dense "
                                                     "days by edge_wyckoff.dense_days from it; the detection window "
                                                     "must lie on or after the start",
                           "dense_share": EW.DENSE_SHARE, "dense_lookback_days": EW.DENSE_LOOKBACK_DAYS, "a7_days": A7_DAYS,
                           "cluster": "ISO week of the signal bar (UTC)", "bootstrap_resamples": BOOT_N,
                           "bootstrap_ci": list(BOOT_CI), "floor": "backtest-methods MIN_RR (analysis-params ict.min_rr)"},
            "costs": {"profile": COST_PROFILE, "hour_frame": HOUR_FRAME, "lines": list(COST_LINES),
                      "legacy_fee_per_side": LEGACY_FEE, "commission": "0/UNKNOWN (real_costs.commission_r)",
                      "times": "entry = the fill instant (next open / signal close); exit = the exit bar's open label, "
                               "the engine's own exit_time convention"},
            "disclosures": {
                "descriptive_only": "no gate, no BH family, nothing selected (§7.1)",
                "legacy_admission": "LEGACY arms' signals are bt.simulate's admitted trades per (symbol, timeframe): the "
                                    "flat-fee floor AND its one-position-per-symbol rule, which reads earlier trades' exit "
                                    "times; `count` reports the floor alone",
                "w7_contain_no_target": "fx_w7_contain keeps the engine's W7 rule 'no HTF record, no Phase-D trade'; the "
                                        "family-W time exit (§3.3) is not an engine rule",
                "shakeout_short": "fx_w_shakeout=test applies to both sides (a lingering Upthrust is entered at its test)",
                "a7_neutral": "A7 bars without an earlier same-hour reference get volume 1.0 (counted per series)",
                "engine_test_volume": "the engine's Test still needs tick volume (W:594) and its Shakeouts reclaim within "
                                      "sob, so A1 covers only that subset (§7.2 Limitation)",
                "dense_from_r0": "the dense table is R0's (family W's), never recomputed on the cut series; signals whose "
                                 "detection window reaches before the dense start are dropped (counted); the HTF series "
                                 "bt.scan reads for the W7 target / HTF gate are not cut at the dense start",
                "code_fingerprint": "code_sha256 = edge_wyckoff.code_sha256() over edge_wyckoff.CODE, equal in all 13 arms "
                                    "and to R0's"}}


# ------------------------------------------------------------------------------------------------ outcome-blind counts
COUNT_KEYS = ("signals", "window_before_dense_start", "prev_day_dense", "below_floor", "no_next_bar",
              "entry_beyond_stop_or_target", "no_atr", "placeable")


def _rr_quantiles(xs):
    s = sorted(xs)
    return {q: _quantile(s, q / 100) for q in (10, 25, 50, 75, 90)} if s else None


def count_series(bt, S, arm, trades, cost_fn):
    """OUTCOME-BLIND counts of one series under `arm`: per leg the signals, those whose window reaches before R0's dense
    start, those on a dense previous day, the entry-time
    skips (no next bar, entry beyond stop / target, no ATR), A2's floor (cost at the entry hour) or the LEGACY flat-fee floor,
    the planned R:R distribution at the arm's entry, and the median placebo pool size. Reads decision fields and bar counts
    only -- never a walk outcome. [prereg §4 "R0 COUNTS", §7: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    out = {leg: collections.Counter() for leg in LEGS}
    rr = {leg: [] for leg in LEGS}
    pools = {leg: [] for leg in LEGS}
    win = arm_window(bt, arm)
    for t in trades:
        sig = signal(S, t)
        k, side, leg, c = sig["k"], sig["side"], sig["leg"], out[sig["leg"]]
        c["signals"] += 1
        if not S.window_ok(k, win):
            c["window_before_dense_start"] += 1
            continue
        if not S.prev_dense[k]:
            continue
        c["prev_day_dense"] += 1
        if arm["floor"] == "legacy_sim":
            # simulate()'s flat-fee admission test alone, on the ENGINE's entry (the signal close), as simulate applies it:
            # R_planned - 2 x fee / stop distance >= MIN_RR. Its one-position rule reads exit times, so it is not counted.
            e0 = S.C[k]
            if abs(sig["target"] - e0) / abs(e0 - sig["stop"]) - 2 * LEGACY_FEE / (abs(e0 - sig["stop"]) / e0) < bt.MIN_RR:
                c["below_floor"] += 1
                continue
        if k + 1 >= len(S.C):
            c["no_next_bar"] += 1
            continue
        entry = S.O[k + 1] if arm["fill"] == "next_open" else S.C[k]
        if not placeable(side, entry, sig["stop"], sig["target"]):
            c["entry_beyond_stop_or_target"] += 1
            continue
        if S.atr[k] is None or S.atr[k] <= 0:
            c["no_atr"] += 1
            continue
        r = abs(sig["target"] - entry) / abs(entry - sig["stop"])
        if arm["floor"] == "entry_cost":
            t_in = S.fill_time(k, arm["fill"])
            if r - cost_fn(entry, sig["stop"], t_in, t_in, S.sym, side, COST_PROFILE, "median")["total_R"] < bt.MIN_RR:
                c["below_floor"] += 1
                continue
        c["placeable"] += 1
        rr[leg].append(r)
        pools[leg].append(len(S.pool(S.slot[k + 1])))
    return {leg: dict(out[leg], planned_rr=_rr_quantiles(rr[leg]),
                      placebo_pool_median=statistics.median(pools[leg]) if pools[leg] else None) for leg in LEGS}


def count(arm_name, out_path, counts_path=None, engine=None, cost_fn=None, symbols=SYMBOLS, timeframes=TIMEFRAMES):
    """`count`: OUTCOME-BLIND (no walk result is read): per (timeframe, symbol) the series span and R0's dense start, and
    `count_series` per leg. No registration guard (it reads no outcome), but the R0 record must pass its probe; one arm per
    process all the same. [prereg §4 "R0 COUNTS", §7: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    arm = _check_arm(arm_name)
    _require_fresh_process("count", arm_name)
    _require_hour_frame()
    r0 = r0_record(counts_path, False)
    bt = _engine() if engine is None else engine
    cost_fn = RC.cost_r if cost_fn is None else cost_fn
    zone = server_zone()
    res = {"meta": dict(_meta("count", arm_name), note="OUTCOME-BLIND: signal, skip and pool counts, planned R:R only",
                        counts={"path": _rel(counts_path), "sha256": _sha256(counts_path)}),
           "series": {}, "pooled": {leg: collections.Counter() for leg in LEGS}}
    with _volume(bt, arm["volume"], zone) as neutral:
        for tf in timeframes:
            for sym in symbols:
                start = dense_start(r0, sym, tf)
                if start is None:
                    res["series"][f"{sym}|{tf}"] = {"why": "no R0 dense start"}
                    continue
                trades, _sim = arm_trades(bt, sym, tf, arm, legacy_admission=False)
                c, src = bt.load(sym, tf)
                if not c:
                    res["series"][f"{sym}|{tf}"] = None
                    continue
                S = Series(sym, tf, c, zone, start)
                legs = count_series(bt, S, arm, trades, cost_fn)
                res["series"][f"{sym}|{tf}"] = {"source": src, "bars": len(c), "first": S.T[0], "last": S.T[-1],
                                                "dense": S.dense, "legs": legs}
                for leg in LEGS:
                    for k in COUNT_KEYS:
                        res["pooled"][leg][k] += legs[leg].get(k, 0)
                print(f"{sym} {tf}: {len(c)} bars, dense from {S.dense['start']}; "
                      + "; ".join(f"{leg} signals {legs[leg].get('signals', 0)} placeable {legs[leg].get('placeable', 0)}"
                                  for leg in LEGS), flush=True)
        res["a7_neutral_bars"] = dict(neutral)
    res["pooled"] = {leg: dict(v) for leg, v in res["pooled"].items()}
    _write(res, out_path)
    print(f"wrote {out_path}")
    return res


# ------------------------------------------------------------------------------------------------ the read
def _write(res, path):
    """The JSON with one row per line (res["rows"]), everything else indented."""
    body = json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1, default=str)
    if "rows" in res:
        assert body.endswith("\n}")
        lines = ",\n".join("  " + json.dumps(r, default=str, separators=(",", ":")) for r in res["rows"])
        body = body[:-2] + (',\n "rows": [\n' + lines + "\n ]\n}" if res["rows"] else ',\n "rows": []\n}')
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body + "\n")


def run(arm_name, out_path, counts_path=None, require_clean=True, engine=None, cost_fn=None, symbols=SYMBOLS,
        timeframes=TIMEFRAMES):
    """The ABL read of ONE arm (§7): signals, the §5 scoring (or the engine's own, LEGACY-as-scored), per (leg, timeframe)
    cells and every event row. Refuses before any data is touched unless the sealed pre-registration is committed and the
    R0 record passed its probe (always); under the guard also the canonical path / ledger / committed and clean code /
    every loaded module in CODE / R0 committed, named and made by this code. Written once; one arm per process.
    [prereg §4 "Reads", §5, §7, §10 item 4: docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    arm = _check_arm(arm_name)
    _require_fresh_process("run", arm_name)
    sealed = _require_sealed()
    _require_hour_frame()
    r0 = r0_record(counts_path, require_clean)
    bt = _engine() if engine is None else engine                # loaded BEFORE the guard: its imports are checked too
    guard = _require_registration(arm_name, out_path, sealed) if require_clean else {}
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: each read is run ONCE (pre-registration §4); refusing to overwrite")
    cost_fn = RC.cost_r if cost_fn is None else cost_fn
    zone = server_zone()
    meta = dict(_meta("read", arm_name), guarded=require_clean, sealed=sealed, min_rr=bt.MIN_RR,
                horizon_bars={tf: bt.P[tf]["H"] for tf in timeframes},
                counts={"path": _rel(counts_path), "sha256": _sha256(counts_path)}, **guard)
    res = {"meta": meta, "data": {}, "legacy_simulate": {}, "skipped": {}, "cells": {}, "rows": []}
    with _volume(bt, arm["volume"], zone) as neutral:
        for tf in timeframes:
            HZ = bt.P[tf]["H"]
            for sym in symbols:
                key = f"{sym}|{tf}"
                start = dense_start(r0, sym, tf)
                if start is None:
                    res["data"][key] = {"why": "no R0 dense start"}
                    continue
                trades, sim = arm_trades(bt, sym, tf, arm)
                c, src = bt.load(sym, tf)
                if not c:
                    res["data"][key] = None
                    continue
                S = Series(sym, tf, c, zone, start)
                with _opts(bt, arm["walk"]):
                    rows, skipped = symbol_rows(bt, S, arm, trades, cost_fn, HZ)
                res["data"][key] = {"source": src, "bars": len(c), "first": S.T[0], "last": S.T[-1], "dense": S.dense}
                if sim is not None:
                    res["legacy_simulate"][key] = sim
                res["skipped"][key] = dict(skipped)
                res["rows"] += rows
                print(f"{sym} {tf}: {len(c)} bars, signals {len(trades)}, events {len(rows)}, skipped {dict(skipped)}",
                      flush=True)
        res["a7_neutral_bars"] = dict(neutral)
    res["cells"] = cells(res["rows"])
    _write(res, out_path)
    for k, v in res["cells"].items():
        print(f"{arm_name} {k}: n {v['n']} gross {v.get('mean_gross_R')} net {v.get('mean_net_abs_R')} "
              f"net excess {v.get('mean_net_excess')}")
    print(f"wrote {out_path}")
    return res


# ------------------------------------------------------------------------------------------------ report
def _fmt(v, p=3):
    return "n/a" if v is None else f"{v:+.{p}f}"


def _ci(d):
    if not d or d.get("diff") is None:
        return "n/a"
    lo, hi = d["ci90"] or (None, None)
    return f"{_fmt(d['diff'])} [{_fmt(lo)}, {_fmt(hi)}]"


def report(out_path, arm_paths=None, require_clean=True):
    """`report`: from the 13 arm records only (no data is read): every arm's cells, and per arm, leg and timeframe ENGINE-
    BOOK minus the arm in mean net excess and in mean net R, each with its week-bootstrap 90 % CI. Writes `out_path` (JSON)
    and the same path with .md. Refuses unless the sealed pre-registration is committed and every arm record is present
    (`_check_order`); under the guard the canonical path, without git history. Written once.
    [prereg §7.1 "Output": docs/plans/2026-10-04-wyckoff-retest-preregistration.md]"""
    sealed = _require_sealed()
    if arm_paths is None:
        arm_paths = {a: os.path.join(ROOT, CANONICAL_OUT.format(seal=sealed["seal_date"], arm=a)) for a in ARMS}
    recs = _check_order(arm_paths, require_clean)
    if require_clean:
        _require_canonical(out_path, CANONICAL_REPORT.format(seal=sealed["seal_date"]))
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists: the report is written ONCE; refusing to overwrite")
    base = recs[REFERENCE]["rows"]
    out = {"meta": dict(_meta("report"), guarded=require_clean, sealed=sealed,
                        inputs={a: {"path": _rel(p), "sha256": _sha256(p)} for a, p in arm_paths.items()}),
           "cells": {a: r["cells"] for a, r in recs.items()}, "minus_reference": {}}
    for arm, rec in recs.items():
        if arm == REFERENCE:
            continue
        out["minus_reference"][arm] = {}
        for leg in LEGS:
            for tf in TIMEFRAMES:
                a = [r for r in base if r["leg"] == leg and r["tf"] == tf]
                b = [r for r in rec["rows"] if r["leg"] == leg and r["tf"] == tf]
                out["minus_reference"][arm][f"{leg}|{tf}"] = {
                    key: week_bootstrap_diff(a, b, key, _seed(SEED_TAG, "ABL", arm, leg, tf, key))
                    for key in ("net_excess", "net_abs")}
    _write(out, out_path)
    md = os.path.splitext(out_path)[0] + ".md"
    L = ["| arm | leg | tf | n | mean gross R | mean net R | mean net excess | ENGINE-BOOK - arm, net excess [90 % CI] | "
         "ENGINE-BOOK - arm, net R [90 % CI] |", "|---|---|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        for leg in LEGS:
            for tf in TIMEFRAMES:
                c = out["cells"][arm].get(f"{leg}|{tf}", {})
                d = out["minus_reference"].get(arm, {}).get(f"{leg}|{tf}", {})
                L.append(f"| {arm} | {leg} | {tf} | {c.get('n', 0)} | {_fmt(c.get('mean_gross_R'))} | "
                         f"{_fmt(c.get('mean_net_abs_R'))} | {_fmt(c.get('mean_net_excess'))} | "
                         f"{_ci(d.get('net_excess')) if arm != REFERENCE else '-'} | "
                         f"{_ci(d.get('net_abs')) if arm != REFERENCE else '-'} |")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write("Descriptive only (pre-registration §7.1): no arm is gated, selected or a candidate.\n\n"
                 + "\n".join(L) + "\n")
    print(f"wrote {out_path} and {md}")
    return out


# ------------------------------------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "run"):
        p = sub.add_parser(name)
        p.add_argument("--arm", required=True, choices=list(ARMS))
        p.add_argument("--counts", required=True)                 # the R0 record of edge_wyckoff (§4: its dense table)
        p.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "count":
        count(a.arm, a.out, counts_path=a.counts)
    elif a.cmd == "run":
        run(a.arm, a.out, counts_path=a.counts)
    else:
        report(a.out)


if __name__ == "__main__":
    main()
