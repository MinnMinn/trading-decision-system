"""Dedicated point-in-time (PIT) tests for the higher-timeframe (HTF) reads of the fund engine: W7 (`fx_w7_htf_target`),
B3 (`fx_b3 = "tfa_p5"`) and B-POOL (`fx_b_pool = "on"`).  docs/audits/2026-10-02-pit-w7-b3.md has the method and numbers.

WHY THIS FILE EXISTS.  The red-team leakage probe (scripts/research/leakage_probe_fund.py, docs/audits/2026-10-02-engine-realism-census.md
"Leakage probe (I9)") mutated the future of every context series on real XAUUSD slices, but its positive control (an HTF bar read two
periods early) fired only for ICT 5m + B3 -- not for ICT 1m + B3 (25 decisions) and not for W7 (66 decisions at each of 5m and 1m).
Those PASSes therefore meant "nothing found", not "absent".  Here the sensitivity is manufactured instead of hoped for: SYNTHETIC series
with planted Wyckoff accumulation / distribution structures (Phase-D legs by the hundreds) and random-walk ICT series, and for EACH
decision time t the output is compared on

  (full)    the whole HTF series,
  (delete)  every HTF bar with availableTime > t DELETED,
  (spike)   every such bar REPLACED by an adversarial value (huge spike up, huge spike down, alternating whipsaw).

availableTime is the repo's own rule (normalized.available_time: bar OPEN + one period), and the boundary is INCLUSIVE: a bar with
availableTime == t is knowable at t, one with availableTime > t (even by one second) is not (scripts/pit.py "Boundary convention").
Every check is also run against an explicit-prefix ORACLE (the knowable bars filtered by this file's own `open + period <= t`, never the
engine's prefix code) at decision times exactly on, 1 s before and 1 s after HTF bar boundaries.

POSITIVE CONTROL INSIDE THE TEST.  `LeakyW7` / `LeakyB3` cut the HTF prefix ONE PERIOD TOO LATE (the still-forming HTF bar becomes
readable, which is what reading a bar "one period early" means).  The very same comparison, on the very same inputs, must then report
mismatches -- and the clean assertion must RAISE.  Minimum counts of decisions checked, legs exercised and controls fired are asserted, so
a vacuous run (no legs, no sensitivity) FAILS instead of passing.

Series carry the repo's server-time convention: bar-open labels are generated on a Mon-Fri grid in FTMO server time and converted with
`mt5_time.to_utc` (scripts/mt5_time.py), across a US-dates DST change (the convention's transition dates), so the HTF series have the
shifted weekend gaps a real import produces.  HTF series are also served with bars MISSING and DUPLICATED, and (W7) with out-of-order /
future-stamped rows, which take the engine's per-call fallback path (`_htf_wyckoff_target_scan`).

Run from scripts/tests (one module per invocation):  PYTHONPATH=.. python3 -W ignore -m unittest test_pit_w7_b3
No R, expectancy or win rate is computed or printed anywhere in this file."""
import contextlib
import datetime
import importlib.util
import os
import random
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
from test_wyckoff_fidelity import base_accumulation, mirror  # noqa: E402  (the planted-structure fixtures)
import mt5_time  # noqa: E402


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BT = _load("bt_pit_w7_b3", os.path.join(SCRIPTS, "backtest-methods.py"))
FS = _load("fund_search_pit_w7_b3", os.path.join(SCRIPTS, "fund-search.py"))
SYM = "XAUUSD"                                   # a tick-volume symbol, the fund's own symbol
MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60}
UTC = datetime.timezone.utc
# the key set under test is the fund's own, not a copy: every adopted key ON (W7 is one of them), fx_b3 / fx_b_pool added per test
ADOPTED_ON = {k: True for k in FS.ADOPTED_F_KEYS}
assert ADOPTED_ON["fx_w7_htf_target"]


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def period(tf):
    return datetime.timedelta(minutes=MINUTES[tf])


def avail(row, tf):
    """This file's OWN statement of the availability rule (open + one period), kept apart from the engine's code on purpose; a test
    below checks it equals normalized.available_time so the two cannot drift."""
    return parse(row["time"]) + period(tf)


# ------------------------------------------------------------------------------------------------------------- series generators --

_ZONE = None


def server_grid(start_date, step_min, n):
    """`n` bar-OPEN labels (UTC, ISO Z) of a Mon-Fri grid in FTMO SERVER time, converted with mt5_time.to_utc (the repo's one conversion).
    Sat/Sun are skipped (the broker's market is closed; the US-dates DST change falls on a Sunday), so across the change the UTC weekend
    gap is one hour shorter / longer, exactly as in the imported history."""
    global _ZONE
    if _ZONE is None:
        _ZONE = mt5_time.server_zone("mt5_bridge_ftmo")
    name, zone = _ZONE
    cur = datetime.datetime.combine(start_date, datetime.time(0))
    step = datetime.timedelta(minutes=step_min)
    out = []
    while len(out) < n:
        if cur.weekday() >= 5:
            cur = (cur + datetime.timedelta(days=7 - cur.weekday())).replace(hour=0, minute=0)
            continue
        try:
            u = mt5_time.to_utc(cur.isoformat(timespec="seconds"), zone, name, "synthetic")
        except mt5_time.Refused:                  # a nonexistent / ambiguous local time: not a bar
            cur += step
            continue
        out.append(iso(u))
        cur += step
    return out


def _unit():
    """One planted accumulation ending in a Phase-D Backup/LPS entry bar (the WY-4 fixture of test_audit_round3_wyckoff.py)."""
    b = base_accumulation()
    b += [(92.0, 116.0, 91.5, 115.0, 25.0), (115.0, 117.0, 114.0, 116.0, 20.0), (112.0, 112.5, 100.0, 111.0, 10.0),
          (111.0, 111.5, 104.0, 110.8, 10.0), (114.0, 118.0, 113.5, 117.0, 10.0)]
    return b


_UNIT, _UNIT_SHORT = _unit(), mirror(_unit(), 200.0)      # the price-inverted twin is a DISTRIBUTION (WA p101)


def planted(rnd, n_bars):
    """OHLCV tuples with planted structures back to back (random scale, side, tiny per-bar noise, 7 quiet filler bars between), at least
    `n_bars` of them; and the index of each structure's last (entry) bar."""
    rows, ends = [], []
    while len(rows) < n_bars:
        s = rnd.uniform(0.6, 1.6)
        for (o, h, l, c, v) in (_UNIT_SHORT if rnd.random() < 0.5 else _UNIT):
            e = 1 + rnd.gauss(0, 0.0003)           # one factor per bar: o/h/l/c keep their order
            rows.append((o * s * e, h * s * e, l * s * e, c * s * e, v * (1 + rnd.uniform(-0.03, 0.03))))
        ends.append(len(rows) - 1)
        p = rows[-1][3]
        rows += [(p, p * 1.0002, p * 0.9998, p, 10.0)] * 7
    return rows, ends


def candles(times, rows):
    return [dict(time=t, open=r[0], high=r[1], low=r[2], close=r[3], volume=r[4]) for t, r in zip(times, rows)]


def random_walk(rnd, times, p0=2000.0):
    """ICT-flavoured walk: drift + volatility regimes every 40 bars and ~6 % displacement candles (full bodies leave FVGs)."""
    out, p, vol, drift = [], p0, 1.0, 0.0
    for i, t in enumerate(times):
        if i % 40 == 0:
            drift, vol = rnd.gauss(0, 0.35), rnd.choice([0.5, 1.0, 2.0])
        o = p
        c = o + drift + rnd.gauss(0, 1.2) * vol
        if rnd.random() < 0.06:
            c = o + rnd.choice([-1, 1]) * rnd.uniform(3, 6) * vol
        h = max(o, c) + abs(rnd.gauss(0, 0.5)) * vol
        l = min(o, c) - abs(rnd.gauss(0, 0.5)) * vol
        out.append(dict(time=t, open=o, high=h, low=l, close=c, volume=100 + rnd.random() * 50))
        p = c
    return out


def aggregate(ltf, ltf_tf, htf_tf):
    """HTF bars built from complete groups of LTF bars (open label = the group's first LTF open, floored to the HTF grid)."""
    k = MINUTES[htf_tf] * 60
    groups = {}
    for r in ltf:
        groups.setdefault(int(parse(r["time"]).timestamp()) // k, []).append(r)
    ratio = MINUTES[htf_tf] // MINUTES[ltf_tf]
    out = []
    for g in sorted(groups):
        rs = groups[g]
        if len(rs) != ratio:                      # an incomplete group (series edge / weekend cut) is not a bar
            continue
        out.append(dict(time=iso(datetime.datetime.fromtimestamp(g * k, UTC)), open=rs[0]["open"], high=max(x["high"] for x in rs),
                        low=min(x["low"] for x in rs), close=rs[-1]["close"], volume=sum(x["volume"] for x in rs)))
    return out


# ------------------------------------------------------------------------------------------------- the future-mutation vocabulary --

SPIKES = ("up", "down", "whip")


def _spiked(row, mode, j):
    x = row["close"]
    up = mode == "up" or (mode == "whip" and j % 2 == 0)
    f = 1000.0 if up else 0.001
    return dict(row, open=x * f, high=x * f * 1.5 if up else x * f * 1.0001, low=x * f * 0.9 if up else x * f * 0.9999,
                close=x * f, volume=row.get("volume", 0) * 1e6 + 1.0)


def with_future(htf, tf, t, mode):
    """The HTF series as it would read if every bar with availableTime > t (strictly) were different: `mode` "delete" removes them,
    "up" / "down" / "whip" replaces them by adversarial values; bars knowable at t (availableTime <= t, boundary INCLUDED) are the SAME
    objects as before."""
    per = period(tf)
    out = []
    for j, r in enumerate(htf):
        if parse(r["time"]) + per <= t:
            out.append(r)
        elif mode != "delete":
            out.append(_spiked(r, mode, j))
    return out


def knowable(htf, tf, t):
    """The oracle prefix: the bars whose availableTime <= t, in series order (no sortedness assumed)."""
    per = period(tf)
    return [r for r in htf if parse(r["time"]) + per <= t]


@contextlib.contextmanager
def serving(htf_by_tf, ltf=None):
    """Serve synthetic series as SYM's loaded history (what the engine reads through bt.load), caches clean before and after."""
    real = BT.load

    def load(s, t):
        if s == SYM and t in htf_by_tf:
            return list(htf_by_tf[t]), "synthetic"
        return real(s, t)
    BT.load = load
    for d in (BT._HTF_TR_CACHE, BT._HTF_SERIES, BT._HTF_TIMES):
        d.clear()
    try:
        yield
    finally:
        BT.load = real
        for d in (BT._HTF_TR_CACHE, BT._HTF_SERIES, BT._HTF_TIMES):
            d.clear()


# ------------------------------------------------------------------------------------------------------ the deliberate leaks (controls) --

@contextlib.contextmanager
def leaky_w7(htf_tf):
    """W7 reads its HTF prefix ONE PERIOD TOO LATE: both the fast path (`_HtfSeries.prefix_len`) and the per-call fallback
    (`pit.series_as_of`) are made to see the bar still forming at the decision time."""
    per = period(htf_tf)
    real_len = BT._HtfSeries.prefix_len
    real_asof = BT._pit.series_as_of

    def prefix_len(self, decision_time):
        return real_len(self, BT._pit._aware(decision_time) + per)

    def series_as_of(c, tf, decision_time, symbol=None):
        return real_asof(c, tf, BT._pit._aware(decision_time) + per, symbol=symbol)
    with mock.patch.object(BT._HtfSeries, "prefix_len", prefix_len), mock.patch.object(BT._pit, "series_as_of", series_as_of):
        yield


@contextlib.contextmanager
def leaky_b3(htf_tf):
    """B3's HTF bars become knowable one period early (the engine's `normalized.available_time` shifted for that timeframe only)."""
    real = BT._N.available_time

    def early(candle, tf, _real=real):
        return _real(candle, tf) - (period(tf) if tf == htf_tf else datetime.timedelta(0))
    BT._HTF_TIMES.clear()
    with mock.patch.object(BT._N, "available_time", early):
        try:
            yield
        finally:
            BT._HTF_TIMES.clear()


# ------------------------------------------------------------------------------------------------------------------------- W7 harness --

W7_SIDES = ("long", "short")
MUTATIONS = ("delete",) + SPIKES
LEG_MUTATIONS = ("delete", "up", "down")         # the per-leg runs are the long ones; the boundary runs use all four


def damage(htf, rnd, kind):
    """`gappy`: ~3 % of the bars MISSING and ~1 % DUPLICATED (still non-decreasing in availableTime -> the engine's fast path);
    `disordered`: ~1 % adjacent rows swapped and one row stamped far in the FUTURE in the middle of the history (availableTime no
    longer non-decreasing -> the engine's per-call fallback `_htf_wyckoff_target_scan`)."""
    if kind == "clean":
        return list(htf)
    out = []
    for r in htf:
        x = rnd.random()
        if kind == "gappy":
            if x < 0.03:
                continue
            out.append(r)
            if x > 0.99:
                out.append(dict(r))
        else:
            out.append(r)
    if kind == "disordered":
        for j in range(5, len(out) - 5, 97):
            out[j], out[j + 1] = out[j + 1], out[j]
        mid = len(out) // 2
        t = parse(out[mid]["time"]) + datetime.timedelta(days=400)
        out.insert(mid, dict(out[mid], time=iso(t)))
    return out


class W7Scenario:
    """A synthetic decision timeframe `tf` (planted structures) and its REAL HTF rung (`BT.HTF_OF[tf]`, planted too), on a server-time
    grid.  `legs()` finds the Phase-D legs the engine itself asks W7 about (it records every `_htf_wyckoff_target` call that
    `_fires_from` makes for a Phase-D leg)."""

    def __init__(self, tf, start_date, seed, n_units, kind="clean"):
        self.tf, self.htf = tf, BT.HTF_OF[tf]
        rnd = random.Random(seed)
        rows, self.ends = planted(rnd, n_units * 100)
        self.ltf = candles(server_grid(start_date, MINUTES[tf], len(rows)), rows)
        ratio = MINUTES[self.htf] // MINUTES[tf]
        n_htf = len(rows) // ratio + 3
        hrows, _ = planted(random.Random(seed + 1), n_htf)
        clean = candles(server_grid(start_date, MINUTES[self.htf], n_htf), hrows[:n_htf])
        self.htf_rows = damage(clean, random.Random(seed + 2), kind)
        self.kind = kind
        self.win = None
        self._legs = None

    def _arrays(self):
        c = self.ltf
        return ([x["open"] for x in c], [x["high"] for x in c], [x["low"] for x in c], [x["close"] for x in c],
                [x.get("volume", 0) for x in c], [x["time"] for x in c])

    def legs(self):
        """[(side, window closes, window times, candidates)] for every structure end where the engine consulted W7 for a Phase-D leg."""
        if self._legs is not None:
            return self._legs
        O, H, L, C, V, Tm = self._arrays()
        asked, legs = [], []
        real = BT._htf_wyckoff_target

        def spy(sym, tf, side, dt):
            asked.append((side, dt))
            return real(sym, tf, side, dt)
        with serving({self.htf: self.htf_rows}), mock.patch.dict(BT.OPTS, ADOPTED_ON), mock.patch.object(BT, "_htf_wyckoff_target", spy):
            win = self.win = BT._wy_window(SYM, self.tf, len(self.ltf))
            for e in self.ends:
                k = e + 1
                a = k - win
                if a < 0:
                    continue
                for side in W7_SIDES:
                    cands = BT._wyckoff_candidates(side, O[a:k], H[a:k], L[a:k], C[a:k], V[a:k], self.tf, SYM)
                    if not cands:
                        continue
                    n0 = len(asked)
                    BT._fires_from(side, cands, C[a:k], Tm[a:k], sym=SYM, tf=self.tf)
                    for (s, dt) in asked[n0:]:
                        legs.append(dict(side=side, dt=dt, k=k, a=a, cands=cands, C=C[a:k], Tm=Tm[a:k]))
        self._legs = legs
        return legs

    @staticmethod
    def fires(leg, tf):
        out = BT._fires_from(leg["side"], leg["cands"], leg["C"], leg["Tm"], sym=SYM, tf=tf)
        return [(f["leg"], f["t0"], f["entry"], f["stop"], f["target"]) for f in out]

    def target(self, side, dt):
        return BT._htf_wyckoff_target(SYM, self.tf, side, dt)

    # ---- one decision --------------------------------------------------------------------------------------------------------

    def oracle(self, side, t):
        """W7's answer computed from an EXPLICIT prefix: the bars with availableTime <= t by this file's own rule, detection run on
        exactly them (no `_HtfSeries`, no prefix_len, no memo) -- the specification the engine's fast path has to equal."""
        pre = knowable(self.htf_rows, self.htf, t)
        if len(pre) < 2 * BT.W.PARAMS["pivot"] + 5:
            return None
        O = [x["open"] for x in pre]; H = [x["high"] for x in pre]; L = [x["low"] for x in pre]
        C = [x["close"] for x in pre]; V = [x.get("volume", 0) for x in pre]
        recs = BT._structures.wyckoff_records(O, H, L, C, V, P=BT._wy_params(BT.P[self.htf]["sob"]), volume_kind="tick", side=side)
        if not recs:
            return None
        r = recs[-1]
        return C[r["sos"]] if r["sos"] is not None else (r["tr_hi"] if side == "long" else r["tr_lo"])

    def probe(self, side, dt, leg=None, oracle=False, mutations=MUTATIONS):
        """(W7 target with the full HTF series, [mismatches]) at decision time `dt`: the target (and, with `leg`, the Phase-D leg that
        `_fires_from` builds from it) must be the same when every HTF bar with availableTime > dt is deleted or replaced, and (with
        `oracle`) equal to the explicit-prefix answer."""
        t = parse(dt)
        mism = []
        with serving({self.htf: self.htf_rows}):
            base = self.target(side, dt)
            base_f = self.fires(leg, self.tf) if leg else None
        if oracle and self.oracle(side, t) != base:
            mism.append((side, dt, "oracle", base, self.oracle(side, t)))
        for mode in mutations:
            with serving({self.htf: with_future(self.htf_rows, self.htf, t, mode)}):
                got = self.target(side, dt)
                got_f = self.fires(leg, self.tf) if leg else None
            if got != base:
                mism.append((side, dt, mode, "target", base, got))
            if got_f != base_f:
                mism.append((side, dt, mode, "leg", base_f, got_f))
        return base, mism

    def check_legs(self, limit=None, mutations=LEG_MUTATIONS):
        legs = self.legs()[:limit]
        mism, nonnull, fired = [], 0, set()
        with adopted():
            for n, leg in enumerate(legs):
                base, m = self.probe(leg["side"], leg["dt"], leg=leg, mutations=mutations)
                nonnull += base is not None
                mism += m
                if m:
                    fired.add(n)
        return dict(checked=len(legs), mism=mism, nonnull=nonnull, fired=len(fired))

    # ---- decision times exactly on HTF bar boundaries ---------------------------------------------------------------------------

    def boundary_times(self, n_samples, dst_date=None):
        """Decision times exactly at availableTime of an HTF bar (INCLUDED), 1 s before (excluded) and 1 s after, for evenly spread
        bars plus the bars on either side of the weekend gap nearest `dst_date` (the server clock's DST change)."""
        rows = self.htf_rows
        idx = set(range(40, len(rows) - 40, max(1, (len(rows) - 80) // n_samples)))
        if dst_date is not None:
            gaps = [j for j in range(len(rows) - 1)
                    if parse(rows[j + 1]["time"]) - parse(rows[j]["time"]) > datetime.timedelta(hours=12)]
            if gaps:
                g = min(gaps, key=lambda j: abs((parse(rows[j]["time"]).date() - dst_date).days))
                idx |= {j for j in range(g - 2, g + 4) if 0 <= j < len(rows)}
        out = []
        for j in sorted(idx):
            a = avail(rows[j], self.htf)
            out += [iso(a), iso(a - datetime.timedelta(seconds=1)), iso(a + datetime.timedelta(seconds=1))]
        return out

    def check_boundaries(self, n_samples, dst_date=None, mutations=MUTATIONS):
        times = self.boundary_times(n_samples, dst_date)
        mism, nonnull, n = [], 0, 0
        with adopted():
            for dt in times:
                for side in W7_SIDES:
                    base, m = self.probe(side, dt, oracle=True, mutations=mutations)
                    n += 1
                    nonnull += base is not None
                    mism += m
        return dict(checked=n, mism=mism, nonnull=nonnull, times=len(times))


@contextlib.contextmanager
def adopted():
    """Every ADOPTED_F_KEY ON in the engine's OPTS (W7 included), restored afterwards."""
    with mock.patch.dict(BT.OPTS, ADOPTED_ON):
        yield


def assert_no_leak(report, what):
    """THE assertion: no mismatch between the full-series answer and the future-mutated / explicit-prefix answers."""
    if report["mism"]:
        raise AssertionError(f"{what}: {len(report['mism'])} look-ahead mismatches, first: {report['mism'][0]}")


# ---------------------------------------------------------------------------------------------------------------------- B3 harness --

class B3Scenario:
    """B3 (`fx_b3 = "tfa_p5"`): an entry on `tf` reads its bias on the PAIRED timeframe `BT.TFA_P5_BIAS_TF[tf]` through
    `htf_bias_gate(..., h=pair)` (`_ict_candidate`).  The gate IS the HTF read, so it is probed directly at every decision time of
    interest; the HTF series is the aggregation of the LTF random walk, so the bias it reads follows the LTF's own moves."""

    def __init__(self, tf, start_date, seed, kind="clean", extra_htf=240):
        self.tf, self.pair = tf, BT.TFA_P5_BIAS_TF[tf]
        rnd = random.Random(seed)
        ratio = MINUTES[self.pair] // MINUTES[tf]
        need = BT.lr.scan_spec(self.pair)[0] + extra_htf          # a full live scan window on the paired timeframe, plus decisions
        times = server_grid(start_date, MINUTES[tf], need * ratio + ratio)
        self.ltf = random_walk(rnd, times)
        self.htf_rows = damage(aggregate(self.ltf, tf, self.pair), random.Random(seed + 1), kind)
        self.methods = BT.resolve_methods(SYM)
        self.window = BT.lr.scan_spec(self.pair)[0]

    def gate(self, side, dt):
        return BT.htf_bias_gate(SYM, self.tf, side, dt, self.methods, h=self.pair)

    def oracle(self, side, t):
        """The gate's answer from an explicit prefix (bars with availableTime <= t by this file's rule): None when no bar is knowable,
        else the live bias read on exactly that prefix."""
        pre = knowable(self.htf_rows, self.pair, t)
        if not pre:
            return None
        try:
            bias, _ = BT.lr.bias_at(pre, len(pre) - 1, self.pair, self.methods)
        except (IndexError, KeyError):
            return None
        return BT.bias_allows(bias, side)

    def times(self, n_boundaries, n_ltf, rnd, dst_date=None):
        """Decision times: HTF bar boundaries (on / 1 s before / 1 s after) among the LAST bars (so a full live window is knowable) and
        LTF bar closes in the same stretch; plus the HTF bars around the weekend gap nearest `dst_date`."""
        rows = self.htf_rows
        lo = max(self.window + 5, len(rows) - n_boundaries - 5)
        idx = set(range(lo, len(rows) - 2))
        if dst_date is not None:
            gaps = [j for j in range(self.window + 5, len(rows) - 1)
                    if parse(rows[j + 1]["time"]) - parse(rows[j]["time"]) > datetime.timedelta(hours=12)]
            if gaps:
                g = min(gaps, key=lambda j: abs((parse(rows[j]["time"]).date() - dst_date).days))
                idx |= {j for j in range(g - 1, g + 3) if 0 <= j < len(rows)}
        out = []
        for j in sorted(idx):
            a = avail(rows[j], self.pair)
            out += [a, a - datetime.timedelta(seconds=1), a + datetime.timedelta(seconds=1)]
        t_lo = avail(rows[lo], self.pair)
        ltf = [r for r in self.ltf if avail(r, self.tf) >= t_lo]
        out += [avail(r, self.tf) for r in rnd.sample(ltf, min(n_ltf, len(ltf)))]
        return [iso(x) for x in out]

    def check(self, times, mutations=("delete", "up", "down")):
        """Per (decision time, side): gate answer on the full HTF series == explicit-prefix oracle == answer on every future mutation."""
        mism, answers = [], {True: 0, False: 0, None: 0}
        for dt in times:
            t = parse(dt)
            for side in ("long", "short"):
                with serving({self.pair: self.htf_rows}):
                    base = self.gate(side, dt)
                answers[base] += 1
                exp = self.oracle(side, t)
                if exp != base:
                    mism.append((side, dt, "oracle", base, exp))
                for mode in mutations:
                    with serving({self.pair: with_future(self.htf_rows, self.pair, t, mode)}):
                        got = self.gate(side, dt)
                    if got != base:
                        mism.append((side, dt, mode, base, got))
        return dict(checked=2 * len(times), mism=mism, answers=answers)

    # ---- the engine's own B3 decision: `_ict_candidate` ------------------------------------------------------------------------

    def ctx(self):
        c = self.ltf
        return BT._ict_ctx(SYM, self.tf, c, [r["time"] for r in c], BT.P[self.tf]["H"], [r["high"] for r in c], [r["low"] for r in c],
                           [r["close"] for r in c], self.methods)

    def candidates(self, last_bars):
        """(bar index, analysis, side) of every LTF bar among the last `last_bars` where the ICT setup is complete and in the right half
        of the dealing range -- the decisions that reach the B3 gate inside `_ict_candidate`."""
        c = self.ltf
        out = []
        with adopted(), mock.patch.dict(BT.OPTS, {"fx_b3": "tfa_p5"}):
            x = self.ctx()
            for i in range(len(c) - last_bars, len(c)):
                a = BT.lr.read_at(c, i, self.tf, self.methods, opts=x.fx_opts)
                if a is None:
                    continue
                su = BT.lr.ict_scan.setup_candidate(a, BT.lr.window(c, i, self.tf), x.lookback, opts=x.fx_opts)
                if su and su.get("complete") and su.get("pd_ok"):
                    out.append((i, a, su["side"], (su["side"], su["sweep"]["time"], su["mss"]["time"])))
        return out

    def check_candidates(self, cands, mutations=("delete", "up", "down")):
        """`_ict_candidate` (setup + B3 gate on the paired timeframe) at each candidate bar: same verdict with the HTF future mutated."""
        mism, passed = [], 0
        with adopted(), mock.patch.dict(BT.OPTS, {"fx_b3": "tfa_p5"}):
            x = self.ctx()
            for (i, a, side, _key) in cands:
                t = avail(self.ltf[i], self.tf)
                with serving({self.pair: self.htf_rows}):
                    base = BT._ict_candidate(x, i, a)
                passed += base is not None
                for mode in mutations:
                    with serving({self.pair: with_future(self.htf_rows, self.pair, t, mode)}):
                        got = BT._ict_candidate(x, i, a)
                    same = (got is None) == (base is None) and (
                        got is None or (got["entry"], got["stop"], got["target"], got["side"]) == (base["entry"], base["stop"], base["target"], base["side"]))
                    if not same:
                        mism.append((i, side, mode, base is None, got is None))
        return dict(checked=len(cands), mism=mism, passed=passed, distinct=len({c[3] for c in cands}))


# -------------------------------------------------------------------------------------------------------------------- B-POOL harness --

POOL_TYPES = ("pdh", "pdl", "session_high", "session_low")


def expected_pools(rows):
    """B-POOL's levels as THIS FILE reads the rule (scripts/ict-scan.py, `fx_b_pool == "on"` block), from the bars the window holds: the
    previous trading UTC day's high/low (only if the window holds at least three distinct dates: the first may open mid-day, the last is
    still forming) and, per session of `ict_scan.SESSION_POOL_WINDOWS`, the last COMPLETE run (not the window's first bar, and left by a
    later bar).  -> {pool type: set of levels}."""
    import sessions
    out = {t: set() for t in POOL_TYPES}
    days = {}
    for r in rows:
        days.setdefault(r["time"][:10], []).append(r)
    ds = sorted(days)
    if len(ds) >= 3:
        d = days[ds[-2]]
        out["pdh"].add(max(x["high"] for x in d))
        out["pdl"].add(min(x["low"] for x in d))
    for w in ("asia", "london"):
        runs, i, n = [], 0, len(rows)
        while i < n:
            if w not in sessions.active(rows[i]["time"]):
                i += 1
                continue
            s = i
            while i < n and w in sessions.active(rows[i]["time"]):
                i += 1
            if s > 0 and i < n:
                runs.append((s, i))
        if runs:
            s, e = runs[-1]
            out["session_high"].add(max(rows[q]["high"] for q in range(s, e)))
            out["session_low"].add(min(rows[q]["low"] for q in range(s, e)))
    return out


class PoolScenario:
    """B-POOL (`fx_b_pool = "on"`) has NO higher-timeframe series: PDH/PDL and the Asia / London session extremes are aggregated from the
    decision series' own window (`lr.window(c, i, tf)` = bars up to and including bar i), and a day / session counts as COMPLETE only
    when a LATER bar inside that window has left it.  So its PIT surface is (1) that the window stops at bar i, and (2) that completion
    is judged on bars knowable at the decision (day and session boundaries, DST-shifted sessions, missing and duplicated bars)."""

    def __init__(self, tf, start_date, n_bars, seed, kind="clean"):
        self.tf = tf
        rnd = random.Random(seed)
        ltf = random_walk(rnd, server_grid(start_date, MINUTES[tf], n_bars))
        self.ltf = damage(ltf, random.Random(seed + 1), kind)
        self.methods = BT.resolve_methods(SYM)
        self.bars = BT.lr.scan_spec(tf)[0]
        self.opts = {"fx_b_pool": "on"}

    def decision_bars(self, around=1):
        """Bars whose NEXT bar changes the UTC date or the set of active sessions (the instants a day / session completes), +- `around`."""
        import sessions
        c = self.ltf
        idx = set()
        for i in range(self.bars, len(c) - 3):
            if c[i]["time"][:10] != c[i + 1]["time"][:10] or sessions.active(c[i]["time"]) != sessions.active(c[i + 1]["time"]):
                idx |= {j for j in range(i - around, i + around + 1) if self.bars <= j < len(c) - 3}
        return sorted(idx)

    def read(self, series, i):
        return BT.lr.read_at(series, i, self.tf, self.methods, opts=self.opts)

    def check(self, decisions, mutations=("delete", "up", "down")):
        """Per decision bar i: the analysis (every field) with the full series == with the future (bars with availableTime > decision)
        deleted / spiked, and every B-POOL level in `pools` is one the explicit knowable window supports."""
        mism, n_pool = [], 0
        for i in decisions:
            t = avail(self.ltf[i], self.tf)
            base = self.read(self.ltf, i)
            for mode in mutations:
                got = self.read(with_future(self.ltf, self.tf, t, mode), i)
                if got != base:
                    mism.append((i, mode, "analysis"))
            win = knowable(self.ltf, self.tf, t)[-self.bars:]
            exp = expected_pools(win)
            for p in (base or {}).get("pools", ()):
                if p["type"] in exp:
                    n_pool += 1
                    if p["level"] not in exp[p["type"]]:
                        mism.append((i, p["type"], "level not supported by the knowable window"))
        return dict(checked=len(decisions), mism=mism, pool_levels=n_pool)


@contextlib.contextmanager
def leaky_window():
    """The decision window runs ONE BAR PAST the decision bar (bar i+1, still forming, is inside it)."""
    def window(candles, i, tf):
        bars, _ = BT.lr.scan_spec(tf)
        return candles[max(0, i - bars + 2):i + 2]
    with mock.patch.object(BT.lr, "window", window):
        yield


# ---------------------------------------------------------------------------------------------------------------------------- tests --

MIN_LEGS = 200                 # Phase-D legs W7 is asked about, per decision timeframe
SEED = 20261002
_CACHE = {}


def cached(key, fn):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


class TheHelpersAreSound(unittest.TestCase):
    def test_the_availability_rule_here_is_the_engines(self):
        for tf in MINUTES:
            row = dict(time="2024-03-05T10:20:00Z")
            self.assertEqual(avail(row, tf), BT._N.available_time(row, tf), tf)

    def test_the_rungs_under_test(self):
        """1m decides against a 5m structure, 5m against 30m (next rung >= 4x); B3 pairs 1m with 15m and 5m with 1H."""
        self.assertEqual((BT.HTF_OF["1m"], BT.HTF_OF["5m"]), ("5m", "30m"))
        self.assertEqual((BT.TFA_P5_BIAS_TF["1m"], BT.TFA_P5_BIAS_TF["5m"]), ("15m", "1H"))

    def test_the_server_grid_is_dst_aware_and_strictly_increasing(self):
        """Mon-Fri server-time grid converted by mt5_time.to_utc: the weekend gap across the US-dates DST change is an hour shorter in
        UTC (spring) / longer (autumn) than a normal one, and the labels never go backwards."""
        gaps = {}
        for start, label in ((datetime.date(2024, 3, 4), "spring"), (datetime.date(2024, 10, 28), "autumn")):
            ts = [parse(x) for x in server_grid(start, 60, 24 * 11)]
            self.assertEqual(ts, sorted(set(ts)))
            gaps[label] = sorted({(b - a) for a, b in zip(ts, ts[1:]) if b - a > datetime.timedelta(hours=12)})
        self.assertEqual(len(gaps["spring"]), 2, gaps)         # the DST weekend's gap differs from the ordinary weekend's
        self.assertEqual(len(gaps["autumn"]), 2, gaps)

    def test_the_mutations_touch_only_the_future(self):
        rows = candles(server_grid(datetime.date(2024, 3, 4), 30, 60), [(10 + i, 11 + i, 9 + i, 10.5 + i, 5.0) for i in range(60)])
        t = parse(rows[29]["time"]) + period("30m")              # exactly bar 29's availableTime: bar 29 knowable, bar 30 not
        for mode in MUTATIONS:
            var = with_future(rows, "30m", t, mode)
            self.assertEqual(var[:30], rows[:30], mode)                       # the boundary bar is INCLUDED, unchanged
            if mode == "delete":
                self.assertEqual(len(var), 30)
            else:
                self.assertEqual(len(var), 60)
                self.assertTrue(all(v["close"] != r["close"] for v, r in zip(var[30:], rows[30:])), mode)
        self.assertEqual(len(knowable(rows, "30m", t - datetime.timedelta(seconds=1))), 29)   # one second earlier: bar 29 is not yet
        self.assertEqual(len(knowable(rows, "30m", t + datetime.timedelta(seconds=1))), 30)


class W7PitPhaseDLegs(unittest.TestCase):
    """W7 at 1m (HTF 5m) and 5m (HTF 30m), >= 200 planted Phase-D legs each, every leg's decision time probed."""

    @classmethod
    def report(cls, tf, control=False):
        def run():
            sc = cached(("w7", tf), lambda: W7Scenario(tf, datetime.date(2024, 3, 4), SEED + MINUTES[tf], 230))
            if not control:
                return sc, sc.check_legs()
            with leaky_w7(sc.htf):
                return sc, sc.check_legs()
        return cached(("w7-report", tf, control), run)

    def _each_tf(self, fn):
        for tf in ("1m", "5m"):
            with self.subTest(tf=tf):
                fn(tf)

    def test_the_series_exercise_enough_legs(self):
        def f(tf):
            sc, rep = self.report(tf)
            self.assertGreaterEqual(rep["checked"], MIN_LEGS, "too few Phase-D legs: the run would be vacuous")
            self.assertGreaterEqual(rep["nonnull"], MIN_LEGS * 3 // 4, "W7 found an HTF structure for too few legs")
            self.assertEqual(sc.htf, BT.HTF_OF[tf])
        self._each_tf(f)

    def test_w7_does_not_move_when_the_future_of_the_htf_series_changes(self):
        def f(tf):
            sc, rep = self.report(tf)
            assert_no_leak(rep, f"W7 {tf}->{sc.htf}")
        self._each_tf(f)

    def test_positive_control_a_prefix_cut_one_period_too_late_is_seen(self):
        def f(tf):
            sc, rep = self.report(tf, control=True)
            self.assertEqual(rep["checked"], self.report(tf)[1]["checked"])             # the same inputs
            self.assertGreaterEqual(rep["fired"], 10, "the control fired on too few legs: the test could not see a leak")
            with self.assertRaises(AssertionError):                                      # the SAME assertion fails
                assert_no_leak(rep, f"W7 {tf} control")
        self._each_tf(f)


class W7PitBoundariesAndBrokenSeries(unittest.TestCase):
    """Decision times exactly on / 1 s around HTF bar boundaries (and around the DST weekend), against an explicit-prefix oracle and the
    mutated futures; HTF series with missing and duplicated bars (fast path) and out-of-order / future-stamped rows (per-call fallback)."""

    CASES = (("1m", "clean", datetime.date(2024, 3, 4), datetime.date(2024, 3, 10)),
             ("5m", "clean", datetime.date(2024, 3, 4), datetime.date(2024, 3, 10)),
             ("1m", "gappy", datetime.date(2024, 10, 28), datetime.date(2024, 11, 3)),
             ("1m", "disordered", datetime.date(2024, 3, 4), datetime.date(2024, 3, 10)),
             ("5m", "disordered", datetime.date(2024, 10, 28), datetime.date(2024, 11, 3)))

    @classmethod
    def scenario(cls, tf, kind, start):
        return cached(("w7b", tf, kind, start), lambda: W7Scenario(tf, start, SEED + 7 + MINUTES[tf], 90, kind))

    def report(self, case, control=False):
        tf, kind, start, dst = case

        def run():
            sc = self.scenario(tf, kind, start)
            if not control:
                return sc.check_boundaries(6, dst)
            with leaky_w7(sc.htf):
                return sc.check_boundaries(6, dst)
        return cached(("w7b-report", case, control), run)

    def test_boundaries_match_the_oracle_and_ignore_the_future(self):
        for case in self.CASES:
            with self.subTest(case=case[:2]):
                rep = self.report(case)
                self.assertGreaterEqual(rep["times"], 36)
                self.assertGreaterEqual(rep["checked"], 72)
                self.assertGreaterEqual(rep["nonnull"], 40, "W7 answered None almost everywhere: the boundary check would be vacuous")
                assert_no_leak(rep, f"W7 boundaries {case[:2]}")

    def test_the_inclusive_boundary_is_pinned_exactly(self):
        """At t == availableTime(bar j) the prefix is bars[0..j] (bar j INCLUDED); 1 s earlier it is bars[0..j-1]; 1 s later, bars[0..j]."""
        sc = self.scenario("1m", "clean", datetime.date(2024, 3, 4))
        rows = sc.htf_rows
        changed = 0
        with adopted(), serving({sc.htf: rows}):
            for j in range(60, len(rows) - 5, 17):
                a = avail(rows[j], sc.htf)
                self.assertEqual([len(knowable(rows, sc.htf, a + d)) for d in (datetime.timedelta(seconds=-1), datetime.timedelta(0), datetime.timedelta(seconds=1))],
                                 [j, j + 1, j + 1])
                for side in W7_SIDES:
                    on, before = sc.target(side, iso(a)), sc.target(side, iso(a - datetime.timedelta(seconds=1)))
                    with serving({sc.htf: rows[:j + 1]}):
                        self.assertEqual(on, sc.target(side, iso(a)), (j, side))           # bar j included at t == availableTime
                    with serving({sc.htf: rows[:j]}):
                        self.assertEqual(before, sc.target(side, iso(a - datetime.timedelta(seconds=1))), (j, side))   # and not 1 s earlier
                    changed += on != before
        self.assertGreater(changed, 0, "bar inclusion never moved the target: this check could not distinguish include from exclude")

    def test_positive_control_boundaries(self):
        for case in self.CASES[:2] + self.CASES[3:4]:
            with self.subTest(case=case[:2]):
                rep = self.report(case, control=True)
                self.assertGreaterEqual(len(rep["mism"]), 5, "the control did not fire: the boundary check cannot see a leak")
                with self.assertRaises(AssertionError):
                    assert_no_leak(rep, "W7 boundary control")

    def test_legs_on_broken_series_are_unmoved(self):
        for case in self.CASES[2:]:
            with self.subTest(case=case[:2]):
                sc = self.scenario(*case[:3])
                rep = sc.check_legs(limit=40)
                self.assertGreaterEqual(rep["checked"], 40)
                assert_no_leak(rep, f"W7 legs {case[:2]}")


class B3Pit(unittest.TestCase):
    """B3 `tfa_p5`: 1m entries read their bias on 15m, 5m entries on 1H."""

    @classmethod
    def scenario(cls, tf, kind="clean", start=datetime.date(2024, 3, 4)):
        return cached(("b3", tf, kind, start), lambda: B3Scenario(tf, start, SEED + 3 + MINUTES[tf], kind))

    def gate_report(self, tf, kind, start, dst, control=False):
        def run():
            sc = self.scenario(tf, kind, start)
            times = sc.times(24, 24, random.Random(SEED), dst)
            if not control:
                return sc.check(times)
            with leaky_b3(sc.pair):
                return sc.check(times)
        return cached(("b3-gate", tf, kind, start, control), run)

    CASES = (("1m", "clean", datetime.date(2024, 3, 4), datetime.date(2024, 3, 10)),
             ("5m", "clean", datetime.date(2024, 3, 4), datetime.date(2024, 3, 10)),
             ("1m", "gappy", datetime.date(2024, 10, 28), datetime.date(2024, 11, 3)),
             ("5m", "gappy", datetime.date(2024, 10, 28), datetime.date(2024, 11, 3)))

    def test_the_gate_ignores_the_future_and_matches_the_explicit_prefix(self):
        for case in self.CASES:
            with self.subTest(case=case[:2]):
                rep = self.gate_report(*case)
                self.assertGreaterEqual(rep["checked"], 200)
                self.assertGreaterEqual(rep["answers"][True], 20, "the gate almost never agreed: vacuous")
                self.assertGreaterEqual(rep["answers"][False], 20, "the gate almost never refused: vacuous")
                assert_no_leak(rep, f"B3 gate {case[:2]}")

    def test_positive_control_gate(self):
        for case in self.CASES[:2]:
            with self.subTest(case=case[:2]):
                rep = self.gate_report(*case, control=True)
                self.assertEqual(rep["checked"], self.gate_report(*case)["checked"])
                self.assertGreaterEqual(len(rep["mism"]), 20, "the control did not fire: the gate check cannot see a leak")
                with self.assertRaises(AssertionError):
                    assert_no_leak(rep, "B3 gate control")

    def _cands(self, tf):
        sc = self.scenario(tf)
        return sc, cached(("b3-cands", tf), lambda: sc.candidates(700 if tf == "1m" else 500))

    def test_the_engines_b3_decision_is_unmoved(self):
        for tf in ("1m", "5m"):
            with self.subTest(tf=tf):
                sc, cands = self._cands(tf)
                rep = cached(("b3-cand-report", tf), lambda: sc.check_candidates(cands))
                self.assertGreaterEqual(rep["distinct"], 8, "too few distinct ICT setups reached the B3 gate")
                self.assertGreaterEqual(rep["checked"], 60)
                self.assertGreaterEqual(rep["passed"], 20, "B3 refused (almost) every setup: the accept side is unexercised")
                self.assertLessEqual(rep["passed"], rep["checked"] - 10, "B3 accepted (almost) every setup: the refuse side is unexercised")
                assert_no_leak(rep, f"B3 _ict_candidate {tf}")

    def test_positive_control_engine_decision(self):
        for tf in ("1m", "5m"):
            with self.subTest(tf=tf):
                sc, cands = self._cands(tf)
                with leaky_b3(sc.pair):
                    rep = sc.check_candidates(cands)
                self.assertGreaterEqual(len(rep["mism"]), 20)
                with self.assertRaises(AssertionError):
                    assert_no_leak(rep, "B3 _ict_candidate control")


class BPoolPit(unittest.TestCase):
    """B-POOL: PDH/PDL and Asia/London session extremes, from the decision series' own window, at day and session boundaries."""

    CASES = (("5m", datetime.date(2024, 3, 4), 1900, "clean"),      # US-dates DST change Sun 2024-03-10
             ("1m", datetime.date(2024, 3, 4), 8000, "clean"),
             ("5m", datetime.date(2024, 3, 25), 1900, "gappy"),      # UK summer time starts Sun 2024-03-31 (London session shifts vs UTC)
             ("1m", datetime.date(2024, 10, 28), 8000, "gappy"))     # US-dates DST change Sun 2024-11-03

    @classmethod
    def scenario(cls, case):
        tf, start, n, kind = case
        return cached(("pool", case), lambda: PoolScenario(tf, start, n, SEED + 11 + n, kind))

    def report(self, case, control=False):
        def run():
            sc = self.scenario(case)
            dec = sc.decision_bars()
            if not control:
                return sc.check(dec)
            with leaky_window():
                return sc.check(dec)
        return cached(("pool-report", case, control), run)

    def test_no_pool_is_built_from_bars_the_decision_could_not_know(self):
        total = 0
        for case in self.CASES:
            with self.subTest(case=case):
                rep = self.report(case)
                self.assertGreaterEqual(rep["checked"], 100)
                total += rep["pool_levels"]
                assert_no_leak(rep, f"B-POOL {case}")
        self.assertGreaterEqual(total, 100, "B-POOL levels appeared too rarely: the check would be vacuous")

    def test_positive_control_a_window_one_bar_too_long_is_seen(self):
        for case in self.CASES[:2]:
            with self.subTest(case=case):
                rep = self.report(case, control=True)
                self.assertGreaterEqual(len(rep["mism"]), 20)
                with self.assertRaises(AssertionError):
                    assert_no_leak(rep, "B-POOL control")


if __name__ == "__main__":
    unittest.main()
