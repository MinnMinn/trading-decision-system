"""W7 (`fx_w7_htf_target`) speed-up, byte-identity proof (docs/audits/2026-10-01-w7-speed.md).

`backtest-methods._htf_wyckoff_target` now (a) builds the higher-timeframe arrays once per series and cuts the PIT prefix by
bisect on the available-time array, (b) memoises on the prefix LENGTH, (c) hands the detector the prefix's swings and its
candidate swing indices cut from ONE series-wide index (`wyckoff_rules.swing_prefix_index` / `prefix_swings`, `pre=`).
The reference here is a FROZEN COPY of the per-call function as it was at 875fa9c, run against the FROZEN detector
fixtures/wyckoff_rules_frozen_85bbc08.py (so the reference shares none of the new code), on synthetic HTF series:

  * every exact bar-boundary decision time (and 1 s either side) of small series, both sides, in order;
  * random decision times on longer series, in two random orders (cache-hit vs cache-miss order independence);
  * a decision time before the first HTF bar, at the last bar, after the last bar;
  * a non-monotone series (duplicate / out-of-order / future-stamped row) and a series with a bar missing a field,
    which must take the original per-call path and raise/return exactly what the original did;
  * a series replaced by different content of the same length and end times (stale-cache check);
  * a detection parameter changed between calls (W.PARAMS, OPTS);
  * detector level: `prefix_swings(index, m)[0] == swings(H[:m], L[:m], k)`, the candidate list is a superset of an
    independently written downtrend test, and `detect_*(pre=)` equals the frozen detector, on random tie-heavy series.

NON-VACUITY: each mutation below (key on prefix length - 1, drop `side` / the parameter dict / the series uid from the
key, `bisect_left` for `bisect_right`, a stale last swing in `prefix_swings`) is applied to the live code and the same
comparison must then report mismatches. Run from scripts/tests:  PYTHONPATH=.. python3 -W ignore -m unittest test_w7_htf_cache"""
import contextlib
import datetime
import importlib.util
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
from test_wyckoff_detect_equivalence import gen  # noqa: E402  (the random tie-heavy series generator)

SYM, LTF, HTF = "XAUUSD", "1m", "5m"     # HTF_OF["1m"] == "5m"; XAUUSD is a tick-volume symbol
T0 = datetime.datetime(2020, 1, 6, tzinfo=datetime.timezone.utc)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BT = _load("bt_w7_cache_test", os.path.join(SCRIPTS, "backtest-methods.py"))
FROZEN = _load("wyckoff_rules_frozen_85bbc08_w7", os.path.join(HERE, "fixtures", "wyckoff_rules_frozen_85bbc08.py"))


# The frozen references predate W8 (CHoCH inside the SC-AR box, ON by default since owner 2026-10-05). These tests pin
# the W7 cache / prefix speed-up as EQUIVALENT to the per-call original, so both sides run with W8 off for the module;
# W8 itself is pinned by test_wyckoff_chart_fidelity.
_W8_SAVED = {}


def setUpModule():
    _W8_SAVED["opts"], _W8_SAVED["params"] = BT.OPTS["fx_w8_choch_in_box"], BT.W.PARAMS["fx_w8_choch_in_box"]
    BT.OPTS["fx_w8_choch_in_box"] = False
    BT.W.PARAMS["fx_w8_choch_in_box"] = False


def tearDownModule():
    BT.OPTS["fx_w8_choch_in_box"] = _W8_SAVED["opts"]
    BT.W.PARAMS["fx_w8_choch_in_box"] = _W8_SAVED["params"]
assert BT.HTF_OF[LTF] == HTF


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_series(rnd, n, kinds=("down", "stair", "noisy")):
    """n 5m bars on the grid, regime-switching so accumulation-like structures occur."""
    O, H, L, C, V = [], [], [], [], []
    while len(C) < n:
        seg = min(n - len(C), rnd.choice([60, 120, 200]))
        o, h, l, c, v = gen(rnd, rnd.choice(kinds), seg)
        O += o; H += h; L += l; C += c; V += v
    return [dict(time=iso(T0 + datetime.timedelta(minutes=5 * i)), open=O[i], high=H[i], low=L[i], close=C[i], volume=V[i])
            for i in range(n)]


def avail(bar):
    return datetime.datetime.fromisoformat(bar["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=5)


def boundary_times(series, step=1, extra=True):
    """Decision times exactly on each bar's availability (inclusive boundary), 1 s before and 1 s after, plus before
    the first bar is available and far after the last."""
    out = []
    for j in range(0, len(series), step):
        a = avail(series[j])
        out += [iso(a), iso(a - datetime.timedelta(seconds=1)), iso(a + datetime.timedelta(seconds=1))]
    if extra:
        out += [iso(T0), iso(avail(series[0]) - datetime.timedelta(seconds=1)), iso(avail(series[-1]) + datetime.timedelta(days=30))]
    return out


def frozen_target(cache, sym, tf, side, decision_time):
    """The per-call function as it was at 875fa9c (scripts/backtest-methods.py `_htf_wyckoff_target`), verbatim except
    that detection runs on the frozen 85bbc08 detector and the memo is a private dict."""
    bt = BT
    h = bt.HTF_OF.get(tf)
    if not h or not sym:
        return None
    c, _ = bt.load(sym, h)
    key = ((sym, h, decision_time, side, (len(c), c[0]["time"], c[-1]["time"]) if c else None, bt.P[h]["sob"])
           + bt._wy_detection_ck())
    if key in cache:
        return cache[key]
    target = None
    if c:
        trunc = bt._pit.series_as_of(c, h, decision_time, symbol=sym)
        if len(trunc) >= 2 * bt.W.PARAMS["pivot"] + 5:
            O_ = [x["open"] for x in trunc]; H_ = [x["high"] for x in trunc]; L_ = [x["low"] for x in trunc]
            C_ = [x["close"] for x in trunc]; V_ = [x.get("volume", 0) for x in trunc]
            vkind = "tick" if bt._I.is_tick_volume(sym) else "traded"
            wp = bt._wy_params(bt.P[h]["sob"])
            recs = (FROZEN.detect_accumulations(O_, H_, L_, C_, V_, P=wp, volume_kind=vkind) if side == "long"
                    else FROZEN.detect_distributions(O_, H_, L_, C_, V_, P=wp, volume_kind=vkind))
            if recs:
                htf_r = recs[-1]
                target = C_[htf_r["sos"]] if htf_r["sos"] is not None else (
                    htf_r["tr_hi"] if side == "long" else htf_r["tr_lo"])
    cache[key] = target
    return target


def _run(fn, *a):
    try:
        return ("ok", fn(*a))
    except Exception as e:      # compared, not swallowed
        return ("err", type(e).__name__)


@contextlib.contextmanager
def htf_series(series):
    """Serve `series` as the loaded 5m history of SYM (what `_htf_wyckoff_target` reads via bt.load), with clean caches."""
    real = BT.load
    BT.load = lambda s, t: ((list(series), "synthetic") if (s, t) == (SYM, HTF) else real(s, t))
    BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()
    try:
        yield
    finally:
        BT.load = real
        BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()


def mismatches(series, queries, detail=False):
    """Number of (side, decision_time) queries on which the live function differs from the frozen copy. `queries` is
    run in the given order (repeats included: the second time is a cache hit)."""
    bad = []
    fcache = {}
    with htf_series(series):
        for side, dt in queries:
            new = _run(BT._htf_wyckoff_target, SYM, LTF, side, dt)
            old = _run(frozen_target, fcache, SYM, LTF, side, dt)
            if new != old:
                bad.append((side, dt, new, old))
    return bad if detail else len(bad)


def all_boundary_queries(series):
    qs = []
    for dt in boundary_times(series):
        qs.append(("long", dt)); qs.append(("short", dt))
    return qs


class W7Equivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved_opts = dict(BT.OPTS)
        BT.OPTS.update({k: True for k in ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon",
                                          "fx_w7_htf_target")})
        rnd = random.Random(20261002)
        cls.small = [make_series(rnd, n) for n in (260, 380, 500)]       # exhaustive boundary sweep
        cls.large = [make_series(rnd, n) for n in (1500, 2500)]          # random decision times
        # answers must not all be None, or the comparison proves nothing
        nn = 0
        for s in cls.small:
            with htf_series(s):
                nn += sum(BT._htf_wyckoff_target(SYM, LTF, sd, dt) is not None
                          for sd in ("long", "short") for dt in boundary_times(s, step=13, extra=False))
        assert nn > 50, f"degenerate fixture: only {nn} non-None W7 answers"
        cls.non_none = nn

    @classmethod
    def tearDownClass(cls):
        BT.OPTS.clear(); BT.OPTS.update(cls.saved_opts)

    def test_every_boundary_small_series_in_order(self):
        for s in self.small:
            self.assertEqual(mismatches(s, all_boundary_queries(s), detail=True), [])

    def test_random_times_two_random_orders_cache_hit_and_miss(self):
        rnd = random.Random(7)
        for s in self.large:
            qs = [(sd, dt) for dt in boundary_times(s, step=37) for sd in ("long", "short")]
            qs += [(rnd.choice(("long", "short")),
                    iso(T0 + datetime.timedelta(seconds=rnd.randrange(0, 5 * 60 * (len(s) + 20))))) for _ in range(120)]
            for _ in range(2):
                rnd.shuffle(qs)
                self.assertEqual(mismatches(s, qs + qs[:40], detail=True), [])       # +40 repeats = cache hits

    def test_decision_time_as_datetime_and_naive_refused_like_before(self):
        s = self.small[1]
        dt = avail(s[200])
        self.assertEqual(mismatches(s, [("long", dt), ("short", dt), ("long", dt)], detail=True), [])
        naive = dt.replace(tzinfo=None)
        self.assertEqual(mismatches(s, [("long", naive)], detail=True), [])         # both raise ValueError

    def test_non_monotone_series_takes_the_original_path(self):
        rnd = random.Random(11)
        for variant in ("duplicate", "out_of_order", "future_row"):
            s = make_series(rnd, 420)
            if variant == "duplicate":
                s[200] = dict(s[199])
            elif variant == "out_of_order":
                s[300], s[301] = s[301], s[300]
            else:
                s[150] = dict(s[150], time=iso(T0 + datetime.timedelta(days=400)))   # a future-stamped row mid-series
            with htf_series(s):
                # a duplicated bar keeps the available times NON-DECREASING (equal), which the bisect path handles
                # exactly (series_as_of keeps both copies); the other two break monotonicity
                self.assertEqual(BT._htf_series(SYM, HTF, BT.load(SYM, HTF)[0]).monotone, variant == "duplicate", variant)
            self.assertEqual(mismatches(s, all_boundary_queries(s), detail=True), [], variant)

    def test_missing_field_raises_only_where_the_original_did(self):
        s = make_series(random.Random(13), 400)
        del s[320]["high"]
        qs = all_boundary_queries(s)
        self.assertEqual(mismatches(s, qs, detail=True), [])
        with htf_series(s):       # both before (fine) and after (KeyError) bar 320 occur in the sweep
            kinds = {_run(BT._htf_wyckoff_target, SYM, LTF, "long", dt)[0] for dt in boundary_times(s, step=5)}
        self.assertEqual(kinds, {"ok", "err"})

    def test_volume_field_absent_defaults_to_zero(self):
        s = make_series(random.Random(17), 300)
        for x in s:
            del x["volume"]
        self.assertEqual(mismatches(s, all_boundary_queries(s), detail=True), [])

    def test_replaced_series_same_length_and_ends_does_not_serve_stale_answers(self):
        rnd = random.Random(19)
        a = make_series(rnd, 380)
        b = make_series(rnd, 380)
        for k in ("time",):
            b[0][k] = a[0][k]; b[-1][k] = a[-1][k]
        b = [dict(x, time=y["time"]) for x, y in zip(b, a)]      # same times, different prices
        qs = all_boundary_queries(a)
        fcache = {}
        real = BT.load
        cur = {"s": a}
        BT.load = lambda s_, t_: ((list(cur["s"]), "synthetic") if (s_, t_) == (SYM, HTF) else real(s_, t_))
        BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()
        try:
            bad = []
            for cur["s"] in (a, b, a):
                fcache.clear()
                for side, dt in qs[::3]:
                    if _run(BT._htf_wyckoff_target, SYM, LTF, side, dt) != _run(frozen_target, fcache, SYM, LTF, side, dt):
                        bad.append((side, dt))
            self.assertEqual(bad, [])
        finally:
            BT.load = real
            BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()

    def test_changed_detection_parameters_are_part_of_the_key(self):
        s = self.small[2]
        qs = all_boundary_queries(s)[::2]
        real = dict(BT.W.PARAMS)
        try:
            with htf_series(s):
                fcache = {}
                bad = []
                for lookback, w2 in ((3, True), (1, True), (3, False), (1, False), (3, True)):
                    BT.W.PARAMS["chobev_needed"] = lookback
                    BT.OPTS["fx_w2_st_below_sc"] = w2
                    fcache.clear()
                    for side, dt in qs:
                        if _run(BT._htf_wyckoff_target, SYM, LTF, side, dt) != _run(frozen_target, fcache, SYM, LTF, side, dt):
                            bad.append((lookback, w2, side, dt))
                self.assertEqual(bad, [])
        finally:
            BT.W.PARAMS.clear(); BT.W.PARAMS.update(real)
            BT.OPTS["fx_w2_st_below_sc"] = True

    def test_cache_is_bounded(self):
        s = self.small[0]
        old = BT._HTF_TR_CACHE_MAX
        BT._HTF_TR_CACHE_MAX = 5
        try:
            self.assertEqual(mismatches(s, all_boundary_queries(s), detail=True), [])
            self.assertLessEqual(len(BT._HTF_TR_CACHE), 5)
        finally:
            BT._HTF_TR_CACHE_MAX = old

    def test_unknown_timeframe_and_missing_history(self):
        self.assertIsNone(BT._htf_wyckoff_target(SYM, "1W", "long", "2020-01-01T00:00:00Z"))    # no higher rung
        self.assertIsNone(BT._htf_wyckoff_target(None, LTF, "long", "2020-01-01T00:00:00Z"))
        with htf_series([]):
            self.assertIsNone(BT._htf_wyckoff_target(SYM, LTF, "long", "2020-01-01T00:00:00Z"))


class NonVacuity(unittest.TestCase):
    """Each mutation of the live code must make the same comparison fail."""

    @classmethod
    def setUpClass(cls):
        cls.saved_opts = dict(BT.OPTS)
        BT.OPTS.update({k: True for k in ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon",
                                          "fx_w7_htf_target")})
        rnd = random.Random(20261002)
        cls.series = [make_series(rnd, n) for n in (260, 380, 500)]
        cls.qs = [all_boundary_queries(s) for s in cls.series]
        for s, q in zip(cls.series, cls.qs):                      # unmutated: clean
            assert mismatches(s, q) == 0

    @classmethod
    def tearDownClass(cls):
        BT.OPTS.clear(); BT.OPTS.update(cls.saved_opts)

    def _bad(self):
        return sum(mismatches(s, q) for s, q in zip(self.series, self.qs))

    def test_prefix_length_off_by_one_is_caught(self):
        real = BT._HtfSeries.prefix_len
        BT._HtfSeries.prefix_len = lambda self, dt: real(self, dt) - 1
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT._HtfSeries.prefix_len = real

    def test_key_coarser_than_the_prefix_length_is_caught(self):
        real = BT._htf_memo_key      # an injective shift of m (e.g. m - 1) is harmless; a many-to-one key is not
        BT._htf_memo_key = lambda S, side, vkind, wp, m: real(S, side, vkind, wp, m // 3)
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT._htf_memo_key = real

    def test_key_without_side_is_caught(self):
        real = BT._htf_memo_key
        BT._htf_memo_key = lambda S, side, vkind, wp, m: real(S, "long", vkind, wp, m)
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT._htf_memo_key = real

    def test_key_without_prefix_length_is_caught(self):
        real = BT._htf_memo_key
        BT._htf_memo_key = lambda S, side, vkind, wp, m: real(S, side, vkind, wp, 0)
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT._htf_memo_key = real

    def test_key_without_parameter_dict_is_caught(self):
        real = BT._htf_memo_key
        BT._htf_memo_key = lambda S, side, vkind, wp, m: (S.uid, side, vkind, m)
        try:
            s = self.series[2]
            qs = all_boundary_queries(s)[::2]
            saved = dict(BT.W.PARAMS)
            try:
                with htf_series(s):
                    fcache, bad = {}, 0
                    for lookback in (3, 1, 3):
                        BT.W.PARAMS["chobev_needed"] = lookback
                        fcache.clear()
                        bad += sum(_run(BT._htf_wyckoff_target, SYM, LTF, sd, dt) != _run(frozen_target, fcache, SYM, LTF, sd, dt)
                                   for sd, dt in qs)
                self.assertGreater(bad, 0)
            finally:
                BT.W.PARAMS.clear(); BT.W.PARAMS.update(saved)
        finally:
            BT._htf_memo_key = real

    def test_key_without_series_uid_is_caught(self):
        real = BT._htf_memo_key
        BT._htf_memo_key = lambda S, side, vkind, wp, m: real(type("S", (), {"uid": 0})(), side, vkind, wp, m)
        try:
            rnd = random.Random(23)
            a, b = make_series(rnd, 380), make_series(rnd, 380)
            b = [dict(x, time=y["time"]) for x, y in zip(b, a)]
            qs = all_boundary_queries(a)[::3]
            fcache, bad = {}, 0
            real_load = BT.load
            cur = {"s": a}
            BT.load = lambda s_, t_: ((list(cur["s"]), "synthetic") if (s_, t_) == (SYM, HTF) else real_load(s_, t_))
            BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()
            try:
                for cur["s"] in (a, b):
                    fcache.clear()
                    bad += sum(_run(BT._htf_wyckoff_target, SYM, LTF, sd, dt) != _run(frozen_target, fcache, SYM, LTF, sd, dt)
                               for sd, dt in qs)
            finally:
                BT.load = real_load
                BT._HTF_TR_CACHE.clear(); BT._HTF_SERIES.clear()
            self.assertGreater(bad, 0)
        finally:
            BT._htf_memo_key = real

    def test_bisect_left_instead_of_right_is_caught(self):
        real = BT._HtfSeries.prefix_len
        BT._HtfSeries.prefix_len = lambda self, dt: BT.bisect.bisect_left(self.avail, BT._pit._aware(dt))
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT._HtfSeries.prefix_len = real

    def test_candidate_list_missing_a_passing_swing_is_caught(self):
        real = BT.W.prefix_swings

        def lossy(index, m):
            sw, cands = real(index, m)
            return sw, cands[::2]                       # drop every other candidate
        BT.W.prefix_swings = lossy
        try:
            self.assertGreater(self._bad(), 0)
        finally:
            BT.W.prefix_swings = real


class DetectorPre(unittest.TestCase):
    """`detect_*(pre=prefix_swings(...))` vs the frozen detector; `prefix_swings` vs `swings`; candidate superset."""

    @staticmethod
    def static_pass(sw, nd):
        """An independent, plain-loop statement of detect_accumulations' downtrend test, for every swing index."""
        need = max(nd + 1, 2)
        out = []
        for si in range(4, len(sw)):
            if sw[si][1] != "L":
                continue
            lows = [s for s in sw[:si + 1] if s[1] == "L"][-need:]
            highs = [s for s in sw[:si] if s[1] == "H"][-need:]
            if len(lows) < nd + 1 or len(highs) < nd + 1:
                continue
            if all(lows[-j][2] < lows[-j - 1][2] for j in range(1, nd + 1)) and all(highs[-j][2] < highs[-j - 1][2] for j in range(1, nd + 1)):
                out.append(si)
        return out

    def swings_mismatches(self):
        """prefix_swings(index, m)[0] != swings(prefix) count over random series/prefixes."""
        rnd = random.Random(20261004)
        W = BT.W
        bad = 0
        for _ in range(40):
            n = rnd.choice([60, 150, 300]); k = rnd.choice([1, 2, 3])
            O, H, L, C, V = gen(rnd, rnd.choice(["stair", "intpx", "down", "noisy"]), n)
            idx = W.swing_prefix_index(H, L, k, 2)
            for m in [rnd.randrange(0, n + 1) for _ in range(15)]:
                bad += W.prefix_swings(idx, m)[0] != W.swings(H[:m], L[:m], k)
        return bad

    def test_stale_last_swing_in_prefix_swings_is_caught(self):
        self.assertEqual(self.swings_mismatches(), 0)
        real = BT.W.prefix_swings

        def stale(index, m):
            sw, cands = real(index, m)
            if sw:
                sw[-1] = index["sw"][len(sw) - 1]        # the FINAL swing at that index instead of the fold state
            return sw, cands
        BT.W.prefix_swings = stale
        try:
            self.assertGreater(self.swings_mismatches(), 0)
        finally:
            BT.W.prefix_swings = real

    def test_random_series_all_prefixes(self):
        rnd = random.Random(20261003)
        W = BT.W
        checked = nonempty = 0
        for _ in range(int(os.environ.get("W7_PRE_ITERS", "60"))):
            kind = rnd.choice(["flat", "stair", "intpx", "down", "noisy"])
            n = rnd.choice([30, 80, 150, 300])
            O, H, L, C, V = gen(rnd, kind, n)
            k = rnd.choice([1, 2, 3])
            nd = rnd.choice([0, 1, 2, 3])
            P = dict(W.PARAMS, pivot=k, downtrend_swings=nd, fx_w1_tr_low_st=rnd.random() < .5, fx_w2_st_below_sc=rnd.random() < .5)
            vk = rnd.choice(["traded", "tick"])
            idx_l = W.swing_prefix_index(H, L, k, nd)
            Hi, Li = [-x for x in L], [-x for x in H]
            idx_s = W.swing_prefix_index(Hi, Li, k, nd)
            ms = sorted(set([0, 1, 2 * k, 2 * k + 1, n] + [rnd.randrange(0, n + 1) for _ in range(12)]))
            for m in ms:
                pre_l = W.prefix_swings(idx_l, m)
                self.assertEqual(pre_l[0], W.swings(H[:m], L[:m], k), (kind, n, k, m))
                self.assertEqual(pre_s := W.prefix_swings(idx_s, m), (W.swings(Hi[:m], Li[:m], k), pre_s[1]))
                for sw, cands in (pre_l, pre_s):
                    self.assertEqual(cands, sorted(set(cands)))
                    self.assertTrue(all(4 <= c < len(sw) for c in cands))
                    self.assertTrue(set(self.static_pass(sw, nd)) <= set(cands), (kind, n, k, nd, m))
                a = repr(W.detect_accumulations(O[:m], H[:m], L[:m], C[:m], V[:m], P=P, volume_kind=vk, pre=pre_l))
                b = repr(FROZEN.detect_accumulations(O[:m], H[:m], L[:m], C[:m], V[:m], P=dict(P), volume_kind=vk))
                self.assertEqual(a, b, (kind, n, k, nd, m, "long"))
                c = repr(W.detect_distributions(O[:m], H[:m], L[:m], C[:m], V[:m], P=P, volume_kind=vk, pre=pre_s))
                d = repr(FROZEN.detect_distributions(O[:m], H[:m], L[:m], C[:m], V[:m], P=dict(P), volume_kind=vk))
                self.assertEqual(c, d, (kind, n, k, nd, m, "short"))
                checked += 2
                nonempty += (a != "[]") + (c != "[]")
        self.assertGreater(nonempty, 20, "degenerate: too few prefixes produced any record")
        self.assertGreater(checked, 300)


if __name__ == "__main__":
    unittest.main()
