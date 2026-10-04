"""WY-P0 engine ablation (docs/plans/2026-10-04-wyckoff-retest-preregistration-DRAFT.md §7.1-§7.2, §10 items 2 and 4):

  * the two ablation-only engine keys of scripts/backtest-methods.py -- fx_w_shakeout {off, test} at the Shakeout skip of
    `_fires_from`, fx_w7_contain {off, on} at the W7 record choice of `_htf_wyckoff_target` (`recs[-1]`) -- default off,
    declared sets refused outside, registered as fx_ keys, never read by the live runner, never a detection key;
  * DEFAULT OFF IS BYTE-IDENTICAL: `_fires_from`, `scan` and `_htf_wyckoff_target` of this tree against the same functions of
    the engine as it was at PRE_CHANGE (exec'd from `git show`), on randomized records and synthetic series;
  * scripts/research/wyckoff_ablation.py: the 13 arms of §7.2 (each A-arm ONE variable from ENGINE-BOOK), the §4 dense rule,
    ATR20, A7's point-in-time hour normalisation, the §5 placebo (ATR multiples, slot, previous dense day, fixed seed), the
    next-open re-walk, the four cost lines and the hour-frame check, A2's entry-knowable floor, A9's close fill, the
    week-bootstrap difference, the outcome-blind `count`, and the guards (sealed pre-registration ALWAYS, canonical path,
    ledger, committed code, read-once, one arm per process, report needs all 13 records with one registered meta).

Every series here is hand-built or random: no real history is read and no R of any real evaluation is computed. The cost
function of the harness is a stub (real_costs.cost_r would read real prices for its price_ref).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_wyckoff_ablation"""
import contextlib
import datetime
import importlib.util
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
ROOT = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)
import test_wyckoff_fidelity as TW  # noqa: E402  (module import: its TestCases must not re-run here)
from test_wyckoff_detect_equivalence import gen  # noqa: E402  (the random tie-heavy series generator)

#: The engine before the two ablation keys existed (the WY-P0 owner-decisions commit). The byte-identity proofs below compare
#: the default-off engine of this tree with this revision's scripts/backtest-methods.py.
PRE_CHANGE = "2e2e2ee8955e1b971a106af043ec448e11fa609d"
UTC = datetime.timezone.utc


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _engine_at(rev, name):
    """scripts/backtest-methods.py as of `rev`, executed as a module whose __file__ is the real path (so its ROOT, configs
    and sibling modules resolve exactly as the live file's do). SkipTest when git cannot show it."""
    try:
        p = subprocess.run(["git", "-C", ROOT, "show", f"{rev}:scripts/backtest-methods.py"], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise unittest.SkipTest(f"git unavailable: {e}")
    if p.returncode != 0:
        raise unittest.SkipTest(f"cannot show {rev}: {p.stderr.strip()}")
    m = types.ModuleType(name)
    m.__file__ = os.path.join(SCRIPTS, "backtest-methods.py")
    exec(compile(p.stdout, m.__file__, "exec"), m.__dict__)
    return m


WA = _load("wyckoff_ablation_t", "scripts/research/wyckoff_ablation.py")
BT = _load("bt_wy_ablation_t", "scripts/backtest-methods.py")


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def candles_of(bars, start=datetime.datetime(2023, 3, 1, tzinfo=UTC), hours=4):
    return [dict(time=iso(start + datetime.timedelta(hours=hours * i)), open=b[0], high=b[1], low=b[2], close=b[3],
                 volume=b[4]) for i, b in enumerate(bars)]


def random_candles(n, seed=7, start=datetime.datetime(2023, 1, 2, tzinfo=UTC), hours=4):
    rnd = random.Random(seed)
    p, out = 100.0, []
    for i in range(n):
        o = p
        c = max(p + rnd.gauss(0, 1.0), 5.0)
        h, lo = max(o, c) + abs(rnd.gauss(0, .5)), min(o, c) - abs(rnd.gauss(0, .5))
        p = c
        out.append(dict(time=iso(start + datetime.timedelta(hours=hours * i)), open=o, high=h, low=lo, close=c,
                        volume=abs(rnd.gauss(100, 30))))
    return out


def regime_candles(seed, n, start=datetime.datetime(2020, 1, 6, tzinfo=UTC), hours=4):
    """Regime-switching series (test_wyckoff_detect_equivalence.gen) so accumulation-like structures occur."""
    rnd = random.Random(seed)
    O, H, L, C, V = [], [], [], [], []
    while len(C) < n:
        seg = min(n - len(C), rnd.choice([60, 120, 200]))
        o, h, lo, c, v = gen(rnd, rnd.choice(("down", "stair", "noisy")), seg)
        O += o; H += h; L += lo; C += c; V += v
    return [dict(time=iso(start + datetime.timedelta(hours=hours * i)), open=O[i], high=H[i], low=L[i], close=C[i],
                 volume=V[i]) for i in range(n)]


@contextlib.contextmanager
def serving(bt, series):
    """bt.load serves {(sym, tf): candles}; anything else is absent. Clean Wyckoff / W7 caches around the block."""
    with mock.patch.object(bt, "load", lambda s, t: ((list(series[(s, t)]), "synthetic") if (s, t) in series
                                                     else (None, None))), \
            mock.patch.dict(bt._WY_CANDIDATES, clear=True), mock.patch.dict(bt._HTF_TR_CACHE, clear=True), \
            mock.patch.dict(bt._HTF_SERIES, clear=True):
        yield


# ================================================================================================ engine keys
class AblationKeysAreRegisteredAndOffByDefault(unittest.TestCase):
    def test_defaults_are_off_and_the_declared_sets_put_the_baseline_first(self):
        self.assertEqual(BT.WY_ABLATION_VALUES, {"fx_w_shakeout": ("off", "test"), "fx_w7_contain": ("off", "on")})
        for k, vals in BT.WY_ABLATION_VALUES.items():
            self.assertEqual(BT._OPTS_BASE[k], vals[0], k)
            self.assertEqual(BT.OPTS[k], vals[0], k)

    def test_they_are_registered_fx_keys_so_scan_accepts_them(self):
        BT._check_fx_registered({"fx_w_shakeout": "test", "fx_w7_contain": "on"})     # no raise

    def test_a_value_outside_the_declared_set_is_refused(self):
        for k, bad in (("fx_w_shakeout", "TEST"), ("fx_w_shakeout", True), ("fx_w_shakeout", "on"),
                       ("fx_w7_contain", True), ("fx_w7_contain", "test")):
            with self.subTest(key=k, value=bad), mock.patch.dict(BT.OPTS, {k: bad, "fx_w7_htf_target": True}):
                with self.assertRaises(ValueError):
                    BT._check_wy_ablation_opts()
        BT._check_wy_ablation_opts()                                     # the baseline passes

    def test_contain_without_w7_is_a_no_op_and_is_refused(self):
        with mock.patch.dict(BT.OPTS, {"fx_w7_contain": "on", "fx_w7_htf_target": False}):
            with self.assertRaises(ValueError):
                BT._check_wy_ablation_opts()
            with self.assertRaises(ValueError):
                BT._wy_window("XAUUSD", "4H", 1000)                      # the scan / scan_many validation point
        with mock.patch.dict(BT.OPTS, {"fx_w7_contain": "on", "fx_w7_htf_target": True}):
            BT._check_wy_ablation_opts()

    def test_neither_is_a_detection_key(self):
        """Both gate or target in `_fires_from` / `_htf_wyckoff_target`; detection (and the `_WY_CANDIDATES` key) is
        unchanged by them, so one cached detection serves every ablation arm that agrees on the detection keys."""
        base = BT._wy_detection_ck()
        with mock.patch.dict(BT.OPTS, {"fx_w_shakeout": "test", "fx_w7_contain": "on", "fx_w7_htf_target": True}):
            self.assertEqual(BT._wy_detection_ck(), base)
            self.assertNotIn("fx_w_shakeout", BT._wy_params(4))
            self.assertNotIn("fx_w7_contain", BT._wy_params(4))

    def test_the_live_runner_never_references_them(self):
        src = open(os.path.join(SCRIPTS, "strategy-runner.py"), encoding="utf-8").read()
        for k in ("fx_w_shakeout", "fx_w7_contain", "WY_ABLATION_VALUES"):
            self.assertNotIn(k, src, k)


def _shake_rec(side, **kw):
    """A Shakeout on the spring path (test_v_items_wyckoff's _rec geometry), Test ON the last bar (4), reclaim at bar 2."""
    r = TW_rec(side)
    r.update(shakeout=True, reclaim=2, test=4)
    r.update(kw)
    return r


def TW_rec(side):
    if side == "long":
        r = dict(tr_hi=110.0, tr_lo=80.0, ceiling=118.0, vah=104.0, val=88.0, spring_low=85.0)
    else:
        r = dict(tr_hi=120.0, tr_lo=90.0, ceiling=82.0, vah=112.0, val=101.0, spring_low=125.0)
    r.update(st_sign="neutral", sloped=False, st_pct=0.5, spring=1, reclaim=4, test=None, sos=None, path="spring",
             shakeout=False, abandon=False, sot_too_strong=False, vol_type=1, rec_ratio=1.0, bu=None,
             phase_b_tests={"upper": 2, "lower": 2})
    return r


CLOSES = {"long": [100.0, 101.0, 102.0, 103.0, 95.0], "short": [100.0, 99.0, 98.0, 97.0, 110.0]}
TM = ["2024-01-05T0%d:00:00Z" % i for i in range(5)]


class ShakeoutAtItsTest(unittest.TestCase):
    """fx_w_shakeout (§3.2, §7.2; WA2-12 at knowledge/wyckoff/advance.md:1083): off skips every Shakeout (B:1403, v1); test
    enters it at its Test, never at the reclaim."""

    def fires(self, side, recs, closes=None, **opts):
        with mock.patch.dict(BT.OPTS, opts):
            return BT._fires_from(side, recs, closes or CLOSES[side], TM, sym="XAUUSD", tf="4H")

    def test_off_skips_and_test_enters_at_the_test_long_and_short(self):
        buf = BT.STOP_BUFFER_PCT
        for side, stop, target in (("long", 85.0 * (1 - buf), 110.0), ("short", 125.0 * (1 + buf), 90.0)):
            with self.subTest(side=side):
                self.assertEqual(self.fires(side, [_shake_rec(side)]), [])
                self.assertEqual(self.fires(side, [_shake_rec(side)], fx_w_shakeout="off"), [])
                (f,) = self.fires(side, [_shake_rec(side)], fx_w_shakeout="test")
                self.assertEqual((f["leg"], f["entry"], f["target"]), ("spring", CLOSES[side][-1], target))
                self.assertAlmostEqual(f["stop"], stop)

    def test_never_at_the_reclaim_even_for_a_type_1_long_or_short(self):
        """A type-1 Spring is entered at its reclaim (v1). A Shakeout of type 1 is not: its reclaim on the last bar with no
        Test fires nothing, and a Test elsewhere fires nothing on this bar."""
        for side in ("long", "short"):
            for kw in (dict(reclaim=4, test=None), dict(reclaim=4, test=3), dict(reclaim=2, test=None)):
                with self.subTest(side=side, **{k: str(v) for k, v in kw.items()}):
                    self.assertEqual(self.fires(side, [_shake_rec(side, **kw)], fx_w_shakeout="test"), [])

    def test_the_other_gates_still_apply(self):
        for side in ("long", "short"):
            for kw in (dict(abandon=True), dict(sot_too_strong=True), dict(path="lps_c")):
                with self.subTest(side=side, gate=list(kw)[0]):
                    self.assertEqual(self.fires(side, [_shake_rec(side, **kw)], fx_w_shakeout="test"), [])
            self.assertEqual(self.fires(side, [_shake_rec(side)], fx_w_shakeout="test", types=(2, 3)), [])

    def test_non_shakeouts_are_unchanged(self):
        for side in ("long", "short"):
            for kw in (dict(), dict(vol_type=2, reclaim=2, test=4), dict(vol_type=3, rec_ratio=5.0),
                       dict(vol_type=2, reclaim=4, test=None)):
                r = dict(TW_rec(side), **kw)
                with self.subTest(side=side, **{k: str(v) for k, v in kw.items()}):
                    self.assertEqual(self.fires(side, [r], fx_w_shakeout="test"), self.fires(side, [r]))

    def test_phase_d_leg_of_a_shakeout_structure_is_unchanged(self):
        for side, closes in (("long", [100.0, 104.0, 108.0, 112.0, 105.0]), ("short", [100.0, 96.0, 92.0, 88.0, 95.0])):
            r = _shake_rec(side, test=None, sos=3, bu=dict(bar=4, low=100.0 if side == "long" else 102.0),
                           tr_lo=80.0, tr_hi=110.0 if side == "long" else 120.0, ceiling=110.0 if side == "long" else 80.0)
            off = self.fires(side, [r], closes)
            self.assertEqual([f["leg"] for f in off], ["phase_d"])
            self.assertEqual(self.fires(side, [r], closes, fx_w_shakeout="test"), off)

    def test_scan_trades_the_w5_shakeout_at_its_test_bar_long_and_short(self):
        """test_wyckoff_fidelity's W5 fixture: Spring bar 88, closes linger below the border, reclaim at 90 (a Shakeout),
        Test at 91. v1 trades nothing; "test" trades the Spring leg at bar 91, nothing at the reclaim."""
        bars = TW.W5AbandonWithoutTheUnsourcedTwoBarClause._bars()
        for side, b in (("long", bars), ("short", TW.mirror(bars))):
            c = candles_of(b)
            with self.subTest(side=side), serving(BT, {("XAUUSD", "4H"): c}), \
                    mock.patch.object(BT, "WYCKOFF_WINDOW", len(b)):
                off = BT.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",), opts={"methods": ("WYCKOFF",)})
                on = BT.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",), opts={"methods": ("WYCKOFF",), "fx_w_shakeout": "test"})
                self.assertEqual(off["trades"].get("WYCKOFF-BOOK", []), [])
                (t,) = on["trades"]["WYCKOFF-BOOK"]
                self.assertEqual((t["leg"], t["side"], t["entry_time"], t["entry"]), ("spring", side, c[91]["time"],
                                                                                     c[91]["close"]))


def _htf_candles(n=40, start=datetime.datetime(2023, 1, 1, tzinfo=UTC)):
    """1H rows (the 15m rung's HTF), closes 100 + i."""
    return [dict(time=iso(start + datetime.timedelta(hours=i)), open=100.0 + i, high=101.0 + i, low=99.0 + i,
                 close=100.0 + i, volume=10.0) for i in range(n)]


DECISION = "2023-01-03T00:00:00Z"        # after every synthetic 1H bar has closed


class W7ContainedRecord(unittest.TestCase):
    """fx_w7_contain (§3.3, §7.2): the W7 target from the LATEST HTF record whose [tr_lo, ceiling + TR] (short: [ceiling -
    TR, tr_hi]) contains the decision close and whose target lies beyond it, instead of `recs[-1]` (B:1052, B:1078)."""
    LONG = [dict(tr_lo=80.0, tr_hi=110.0, ceiling=112.0, sos=None),    # range [80, 142], target AR 110
            dict(tr_lo=200.0, tr_hi=230.0, ceiling=235.0, sos=None)]   # range [200, 265], target AR 230 (= recs[-1])
    SHORT = [dict(tr_lo=80.0, tr_hi=110.0, ceiling=75.0, sos=None),    # range [45, 110], target AR 80
             dict(tr_lo=300.0, tr_hi=330.0, ceiling=290.0, sos=None)]  # range [260, 330], target AR 300 (= recs[-1])

    def target(self, side, recs, price=None, contain="off", series=None):
        series = _htf_candles() if series is None else series
        with serving(BT, {("XAUUSD", "1H"): series}), \
                mock.patch.object(BT._structures, "wyckoff_records", lambda *a, **k: [dict(r) for r in recs]), \
                mock.patch.dict(BT.OPTS, {"fx_w7_htf_target": True, "fx_w7_contain": contain}):
            return BT._htf_wyckoff_target("XAUUSD", "15m", side, DECISION, **({} if price is None else {"price": price}))

    def test_off_is_recs_last_whatever_the_price(self):
        self.assertEqual(self.target("long", self.LONG), 230.0)
        self.assertEqual(self.target("long", self.LONG, price=100.0), 230.0)    # price is not read when off
        self.assertEqual(self.target("short", self.SHORT, price=100.0), 300.0)

    def test_on_takes_the_latest_record_that_contains_the_price_long(self):
        for price, want in ((100.0, 110.0), (210.0, 230.0), (140.0, None), (120.0, None), (300.0, None), (79.0, None)):
            with self.subTest(price=price):
                # 140: inside [80, 142] but the target 110 is not above it; 120: same; 300 / 79: inside no record
                self.assertEqual(self.target("long", self.LONG, price, "on"), want)

    def test_on_mirrors_for_a_short(self):
        for price, want in ((100.0, 80.0), (50.0, None), (320.0, 300.0), (115.0, None)):
            with self.subTest(price=price):
                self.assertEqual(self.target("short", self.SHORT, price, "on"), want)

    def test_the_latest_containing_record_wins_and_a_sos_close_is_its_target(self):
        recs = [dict(tr_lo=80.0, tr_hi=110.0, ceiling=112.0, sos=None),
                dict(tr_lo=90.0, tr_hi=115.0, ceiling=118.0, sos=5),     # also contains 100; target C[5] = 105
                dict(tr_lo=500.0, tr_hi=530.0, ceiling=531.0, sos=None)]
        self.assertEqual(self.target("long", recs, 100.0, "on"), 105.0)
        self.assertEqual(self.target("long", recs, 100.0, "off"), 530.0)

    def test_on_without_a_price_refuses(self):
        with self.assertRaises(ValueError):
            self.target("long", self.LONG, None, "on")

    def test_the_per_call_fallback_path_selects_the_same_record(self):
        """A non-monotone HTF series takes `_htf_wyckoff_target_scan` (v1) / `_htf_w7_contained_scan` (on)."""
        s = _htf_candles()
        s[10], s[11] = s[11], s[10]
        for price, want in ((100.0, 110.0), (210.0, 230.0), (300.0, None)):
            self.assertEqual(self.target("long", self.LONG, price, "on", series=s), want)
        self.assertEqual(self.target("long", self.LONG, 100.0, "off", series=s), 230.0)

    def test_on_and_off_answers_never_share_a_cache_entry(self):
        series = _htf_candles()
        with serving(BT, {("XAUUSD", "1H"): series}), \
                mock.patch.object(BT._structures, "wyckoff_records", lambda *a, **k: [dict(r) for r in self.LONG]):
            got = []
            for contain, price in (("off", None), ("on", 100.0), ("off", None), ("on", 210.0), ("on", 100.0)):
                with mock.patch.dict(BT.OPTS, {"fx_w7_htf_target": True, "fx_w7_contain": contain}):
                    got.append(BT._htf_wyckoff_target("XAUUSD", "15m", "long", DECISION,
                                                      **({} if price is None else {"price": price})))
        self.assertEqual(got, [230.0, 110.0, 230.0, 230.0, 110.0])

    def test_fires_from_passes_the_decision_close_only_when_on(self):
        rec = dict(st_sign="neutral", sloped=False, st_pct=0.5, tr_hi=110.0, tr_lo=80.0, ceiling=110.0, spring=None, sos=3,
                   path="lps_c", shakeout=False, abandon=False, sot_too_strong=False, vol_type=None, spring_low=None,
                   bu=dict(bar=4, low=100.0), phase_b_tests={"upper": 2, "lower": 2})
        C = [100.0, 104.0, 108.0, 112.0, 105.0]
        calls = []

        def four_args(sym, tf, side, dt):                 # the signature existing spies use (test_pit_w7_b3, w7_equiv)
            calls.append(("v1", sym, tf, side, dt))
            return 125.0

        def with_price(sym, tf, side, dt, price=None):
            calls.append(("on", sym, tf, side, dt, price))
            return 125.0
        with mock.patch.dict(BT.OPTS, {"fx_w7_htf_target": True}), mock.patch.object(BT, "_htf_wyckoff_target", four_args):
            (f,) = BT._fires_from("long", [rec], C, TM, sym="XAUUSD", tf="15m")
        with mock.patch.dict(BT.OPTS, {"fx_w7_htf_target": True, "fx_w7_contain": "on"}), \
                mock.patch.object(BT, "_htf_wyckoff_target", with_price):
            (g,) = BT._fires_from("long", [rec], C, TM, sym="XAUUSD", tf="15m")
        self.assertEqual(f, g)
        self.assertEqual(calls[0][0], "v1")
        self.assertEqual(calls[1][0], "on")
        self.assertEqual(calls[1][-1], C[-1])
        self.assertEqual(calls[0][1:], calls[1][1:-1])


# ================================================================================================ default = v1, byte-identical
def _random_recs(rnd, side, n):
    last = n - 1
    out = []
    for _ in range(rnd.randint(1, 4)):
        lo = rnd.uniform(80, 95)
        hi = lo + rnd.uniform(5, 30)
        path = rnd.choice(["spring", "spring", "lps_c"])
        spring = rnd.randrange(n) if path == "spring" else None
        sos = rnd.choice([None, rnd.randrange(n)]) if spring is not None else rnd.randrange(n)
        pick = lambda: rnd.choice([None, last, last, last - 1, rnd.randrange(n)])  # noqa: E731
        bu_low = rnd.uniform(lo, hi) if side == "long" else rnd.uniform(lo, hi)
        out.append(dict(
            tr_lo=lo, tr_hi=hi, ceiling=(hi + rnd.uniform(0, 8)) if side == "long" else (lo - rnd.uniform(0, 8)),
            vah=rnd.uniform(lo, hi), val=rnd.uniform(lo, hi),
            spring_low=None if path == "lps_c" else ((lo - rnd.uniform(0.5, 6)) if side == "long" else (hi + rnd.uniform(0.5, 6))),
            st_sign=rnd.choice(["neutral", "supports", "contradicts"]), phase_b_sign=rnd.choice(["neutral", "supports", "contradicts"]),
            sloped=rnd.random() < .3, st_pct=rnd.random(), spring=spring, reclaim=pick(), test=pick(), sos=sos, path=path,
            shakeout=rnd.random() < .5, abandon=rnd.random() < .2, sot_too_strong=rnd.random() < .1,
            vol_type=rnd.choice([None, 1, 2, 3]), rec_ratio=rnd.choice([None, 0.5, 1.5, 3.0]),
            bu=rnd.choice([None, dict(bar=last, low=bu_low), dict(bar=last - 1, low=bu_low)]),
            phase_b_tests={"upper": rnd.randint(0, 3), "lower": rnd.randint(0, 3)}))
    return out


class DefaultsAreByteIdenticalToThePreChangeEngine(unittest.TestCase):
    """The default-off engine of this tree against scripts/backtest-methods.py at PRE_CHANGE (exec'd from git), on the
    three functions the keys touch. Any difference with the keys off is a v1 change the pre-registration forbids (§10 item
    2, §12.4 item 2)."""

    @classmethod
    def setUpClass(cls):
        cls.old = _engine_at(PRE_CHANGE, "bt_pre_wy_ablation")
        cls.new = BT
        src = open(os.path.join(SCRIPTS, "backtest-methods.py"), encoding="utf-8").read()
        assert "fx_w7_contain" in src and not hasattr(cls.old, "WY_ABLATION_VALUES")

    def test_fires_from_on_random_records_under_the_existing_option_sets(self):
        rnd = random.Random(20261004)
        overlays = ({}, {"fx_w_stop": "spring_low"}, {"fx_w_spt": "VAH"}, {"fx_w_spt": "ceiling"}, {"fx_w_touch": "on"},
                    {"st_gate": True, "phase_b_gate": True, "sloped_gate": True}, {"entry": "test"}, {"types": (1,)},
                    {"phase_d": False}, {"st_min": 0.5}, {"fx_w7_htf_target": True})
        stub = lambda sym, tf, side, dt: (125.0 if side == "long" else 60.0) if dt and dt[-6] in "02468" else None  # noqa: E731
        fired = 0
        for trial in range(600):
            side = rnd.choice(["long", "short"])
            n = 6
            recs = _random_recs(rnd, side, n)
            C = [rnd.uniform(70, 130) for _ in range(n)]
            Tm = ["2024-01-05T%02d:%02d:00Z" % (rnd.randrange(24), rnd.randrange(0, 60, 15)) for _ in range(n)]
            for ov in overlays:
                with mock.patch.dict(self.old.OPTS, ov), mock.patch.dict(self.new.OPTS, ov), \
                        mock.patch.object(self.old, "_htf_wyckoff_target", stub), \
                        mock.patch.object(self.new, "_htf_wyckoff_target", stub):
                    a = self.old._fires_from(side, recs, C, Tm, sym="XAUUSD", tf="15m")
                    b = self.new._fires_from(side, recs, C, Tm, sym="XAUUSD", tf="15m")
                self.assertEqual(a, b, (trial, ov))
                fired += len(a)
        self.assertGreater(fired, 200)                       # non-vacuous: both legs and many gates actually exercised

    def test_scan_on_synthetic_series(self):
        trades = 0
        for seed in (1, 2, 3):
            ltf = regime_candles(seed, 700)
            htf = regime_candles(seed + 100, 160, hours=24)
            for ov in ({"methods": ("WYCKOFF",)}, {"methods": ("WYCKOFF",), "fx_gap_fill": True, "mgmt": "be"},
                       {"methods": ("WYCKOFF",), "fx_w5_vp_abandon": True, "fx_w2_st_below_sc": True},
                       {"methods": ("WYCKOFF",), "fx_w7_htf_target": True}):
                got = []
                for m in (self.old, self.new):
                    with serving(m, {("XAUUSD", "4H"): ltf, ("XAUUSD", "1D"): htf}), \
                            mock.patch.object(m, "WYCKOFF_WINDOW", 150):
                        got.append(m.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",), opts=ov)["trades"].get("WYCKOFF-BOOK", []))
                self.assertEqual(got[0], got[1], (seed, ov))
                trades += len(got[0])
        self.assertGreater(trades, 0)

    def test_scan_on_fixtures_with_a_spring_and_a_shakeout(self):
        """Hand-built structures that DO trade (or must not): the W5 Shakeout (v1: no trade, long and short) and the W6
        type-1 Spring seen by a 600-bar window (one Spring trade per side)."""
        import test_v_items_wyckoff as TV          # module import: its TestCases must not re-run here
        w5 = TW.W5AbandonWithoutTheUnsourcedTwoBarClause._bars()
        cases = ((candles_of(w5), {}, len(w5)), (candles_of(TW.mirror(w5)), {}, len(w5)),
                 (candles_of(TV._w6_bars()), {"fx_w6_window": 600}, None),
                 (candles_of(TW.mirror(TV._w6_bars(14.0))), {"fx_w6_window": 600}, None))
        trades = []
        for c, ov, win in cases:
            got = []
            for m in (self.old, self.new):
                with serving(m, {("XAUUSD", "4H"): c}), mock.patch.object(m, "WYCKOFF_WINDOW", win or m.WYCKOFF_WINDOW):
                    got.append(m.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",),
                                      opts=dict(ov, methods=("WYCKOFF",)))["trades"].get("WYCKOFF-BOOK", []))
            self.assertEqual(got[0], got[1], ov)
            trades += got[0]
        self.assertEqual(sorted((t["leg"], t["side"]) for t in trades), [("spring", "long"), ("spring", "short")])

    def test_htf_wyckoff_target_on_synthetic_series(self):
        rnd = random.Random(5)
        series = regime_candles(9, 400, hours=1)
        times = sorted({iso(datetime.datetime(2020, 1, 6, tzinfo=UTC) + datetime.timedelta(hours=rnd.randrange(30, 420)))
                        for _ in range(60)})
        answers = [[], []]
        for j, m in enumerate((self.old, self.new)):
            with serving(m, {("XAUUSD", "1H"): series}), mock.patch.dict(m.OPTS, {"fx_w7_htf_target": True}):
                for dt in times:
                    for side in ("long", "short"):
                        answers[j].append(m._htf_wyckoff_target("XAUUSD", "15m", side, dt))
        self.assertEqual(answers[0], answers[1])
        self.assertTrue(any(a is not None for a in answers[0]))


# ================================================================================================ the harness
class Arms(unittest.TestCase):
    """§7.2: ENGINE-BOOK, the two references and A1..A10, each A-arm exactly one variable away from ENGINE-BOOK."""
    GROUPS = {"fx_w7_htf_target": "w7 target", "fx_w7_contain": "w7 target", "flat_before_rollover": "rollover",
              "rollover_provider": "rollover"}
    EXPECT = {"A1": {"fx_w_shakeout"}, "A2": {"floor"}, "A3": {"htf"}, "A4": {"w7 target"}, "A5": {"fx_w6_window"},
              "A6": {"fx_w_stop"}, "A7": {"volume"}, "A8": {"fx_w_spt"}, "A9": {"fill"}, "A10": {"rollover"}}

    def variables(self, arm):
        eng, out = WA.ARMS["ENGINE-BOOK"], set()
        for part in ("scan", "walk"):
            for k in set(arm[part]) | set(eng[part]):
                if arm[part].get(k) != eng[part].get(k):
                    out.add(self.GROUPS.get(k, k))
        for f in ("signals", "fill", "score", "floor", "volume"):
            if arm[f] != eng[f]:
                out.add(f)
        return out

    def test_the_thirteen_arms(self):
        self.assertEqual(list(WA.ARMS), ["LEGACY-as-scored", "LEGACY-rescored", "ENGINE-BOOK"] + [f"A{i}" for i in range(1, 11)])

    def test_each_one_variable_arm_changes_exactly_its_variable(self):
        for name, want in self.EXPECT.items():
            with self.subTest(arm=name):
                self.assertEqual(self.variables(WA.ARMS[name]), want)

    def test_engine_book_is_the_section_7_2_definition(self):
        e = WA.ARMS["ENGINE-BOOK"]
        self.assertEqual(e["scan"], dict(fx_w1_tr_low_st=True, fx_w2_st_below_sc=True, fx_w3_mSOW_spring=True,
                                         fx_w5_vp_abandon=True, fx_w_shakeout="test", htf=False, fx_w7_htf_target=True,
                                         fx_w7_contain="on", fx_gap_fill=True))
        self.assertEqual((e["fill"], e["floor"], e["score"], e["signals"], e["volume"], e["walk"]),
                         ("next_open", None, "placebo", "scan", "raw", {"fx_gap_fill": True}))

    def test_legacy_references(self):
        a, r = WA.ARMS["LEGACY-as-scored"], WA.ARMS["LEGACY-rescored"]
        self.assertEqual(a["scan"], {"htf": True})                 # every fx_ key at v1: Shakeouts skipped, ceiling + 1 x TR
        self.assertEqual(r["scan"], a["scan"])                     # the same signals
        self.assertEqual((a["signals"], a["floor"], a["fill"], a["score"]), ("legacy_sim", "legacy_sim", "signal_close", "absolute"))
        self.assertEqual((r["signals"], r["floor"], r["fill"], r["score"], r["walk"]),
                         ("legacy_sim", "legacy_sim", "next_open", "placebo", {"fx_gap_fill": True}))

    def test_every_scan_overlay_passes_the_engine_validators(self):
        for name, arm in WA.ARMS.items():
            with self.subTest(arm=name), mock.patch.object(BT, "OPTS", dict(BT._OPTS_BASE, **arm["scan"])):
                BT._check_fx_registered(BT.OPTS)
                BT._check_wy_v_opts()
                BT._check_wy_ablation_opts()


def _days_series(day_counts, hour0=0):
    """(sday, dts) for {date: n bars}, n hourly bars from hour0 UTC (zone UTC, so the server day is the UTC day)."""
    sday, dts = [], []
    for d in sorted(day_counts):
        for h in range(day_counts[d]):
            dts.append(datetime.datetime(d.year, d.month, d.day, hour0 + h, tzinfo=UTC))
            sday.append(d)
    return sday, dts


def _span(a, b):
    d, out = a, []
    while d <= b:
        out.append(d)
        d += datetime.timedelta(days=1)
    return out


def _r0_file(d, dense, probe=None, script=None):
    """An R0 counts record of edge_wyckoff (kind counts, a passing truncation probe unless given) at d/r0.json."""
    path = os.path.join(d, "r0.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"meta": {"script": script or WA.EW.SCRIPT, "kind": "counts"}, "dense": dense,
                   "probe": probe or {"checked": 7, "violations": 0, "ok": True}}, fh)
    return path


class DenseFromR0(unittest.TestCase):
    """§4 "R0 pins the exact table": the ablation reads R0's dense start per series and derives the dense days from it with
    edge_wyckoff.dense_days -- it never recomputes the table on its own (DEV_CUTOFF-cut) series; a signal whose detection
    window reaches before the start is not an event."""
    D = datetime.date

    def test_the_duplicate_table_is_gone(self):
        self.assertFalse(hasattr(WA, "dense_table"))
        self.assertIs(WA.EW.dense_days, WA.EW.dense_days)                         # one rule, edge_wyckoff's

    def test_the_series_takes_r0s_start_and_edge_wyckoffs_dense_days(self):
        c = random_candles(1200, start=datetime.datetime(2023, 3, 1, tzinfo=UTC))
        S = WA.Series("XAUUSD", "4H", c, WA.server_zone(), self.D(2023, 6, 1))
        dense, prev = WA.EW.dense_days(S.sday, self.D(2023, 6, 1))
        self.assertEqual(S.prev_dense, prev)
        self.assertEqual(S.dense["dense_days"], len(dense))
        self.assertEqual(S.dense["start"], "2023-06-01")
        self.assertEqual(S.first_dense, S.sday.index(self.D(2023, 6, 1)))
        self.assertFalse(any(S.prev_dense[:S.first_dense + 1]))                   # nothing before the start is dense
        self.assertTrue(S.window_ok(S.first_dense + 299, 300))
        self.assertFalse(S.window_ok(S.first_dense + 298, 300))
        none = WA.Series("XAUUSD", "4H", c, WA.server_zone())
        self.assertFalse(any(none.prev_dense))
        self.assertFalse(none.window_ok(len(c) - 1, 1))

    def test_dense_start_reads_r0_and_a_series_without_one_is_not_read(self):
        r0 = {"dense": {"XAUUSD|4H": {"start": "2021-02-01"}, "US500|4H": {"start": None}}}
        self.assertEqual(WA.dense_start(r0, "XAUUSD", "4H"), self.D(2021, 2, 1))
        self.assertIsNone(WA.dense_start(r0, "US500", "4H"))
        self.assertIsNone(WA.dense_start(r0, "DE40", "4H"))

    def test_r0_must_exist_and_pass_its_probe_for_count_and_run(self):
        d = tempfile.mkdtemp()
        WA._PROCESS["used"] = None
        with self.assertRaises(SystemExit) as cm:
            WA.count("ENGINE-BOOK", os.path.join(d, "c.json"), engine=types.SimpleNamespace())
        self.assertIn("--counts", str(cm.exception))
        for probe in ({"checked": 0, "violations": 0, "ok": False}, {"checked": 50, "violations": 2, "ok": False}):
            path = _r0_file(d, {}, probe=probe)
            WA._PROCESS["used"] = None
            with self.assertRaises(SystemExit) as cm:
                WA.count("ENGINE-BOOK", os.path.join(d, "c.json"), counts_path=path, engine=types.SimpleNamespace())
            self.assertIn("probe", str(cm.exception))
            WA._PROCESS["used"] = None
            with mock.patch.object(WA, "_require_sealed", lambda: SEALED), self.assertRaises(SystemExit) as cm:
                WA.run("ENGINE-BOOK", os.path.join(d, "r.json"), counts_path=path, require_clean=False,
                       engine=types.SimpleNamespace())
            self.assertIn("probe", str(cm.exception))
        WA._PROCESS["used"] = None
        with self.assertRaises(SystemExit):                                         # not an edge_wyckoff R0
            WA.count("ENGINE-BOOK", os.path.join(d, "c.json"), counts_path=_r0_file(d, {}, script=WA.SCRIPT),
                     engine=types.SimpleNamespace())
        WA._PROCESS["used"] = None


class Atr20AndHourNormalisation(unittest.TestCase):
    def test_atr20_is_the_mean_true_range_of_the_last_twenty_bars(self):
        rnd = random.Random(3)
        H = [100 + rnd.random() * 5 for _ in range(40)]
        L = [h - 1 - rnd.random() for h in H]
        C = [(h + l) / 2 for h, l in zip(H, L)]
        a = WA.atr20(H, L, C)
        self.assertTrue(all(v is None for v in a[:20]))
        for j in (20, 27, 39):
            tr = [max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])) for i in range(j - 19, j + 1)]
            self.assertAlmostEqual(a[j], sum(tr) / 20)

    def _hourly(self, vols):
        t0 = datetime.datetime(2023, 5, 1, tzinfo=UTC)
        return [dict(time=iso(t0 + datetime.timedelta(days=d, hours=10)), open=1.0, high=1.0, low=1.0, close=1.0,
                     volume=v) for d, v in enumerate(vols)]

    def test_volume_over_the_median_of_earlier_days_same_hour(self):
        out, neutral = WA.hour_normalised(self._hourly([10.0, 20.0, 30.0, 40.0]), UTC)
        self.assertEqual([x["volume"] for x in out], [1.0, 2.0, 2.0, 2.0])     # 20/10, 30/15, 40/20
        self.assertEqual(neutral, 1)
        out1, _ = WA.hour_normalised(self._hourly([10.0, 20.0, 30.0]), UTC, days=1)
        self.assertEqual([x["volume"] for x in out1], [1.0, 2.0, 1.5])

    def test_point_in_time_a_later_volume_never_moves_an_earlier_value(self):
        a, _ = WA.hour_normalised(self._hourly([10.0, 20.0, 30.0, 40.0]), UTC)
        b, _ = WA.hour_normalised(self._hourly([10.0, 20.0, 30.0, 4000.0]), UTC)
        self.assertEqual([x["volume"] for x in a[:3]], [x["volume"] for x in b[:3]])

    def test_prices_untouched_and_the_input_not_written(self):
        src = self._hourly([10.0, 20.0])
        out, _ = WA.hour_normalised(src, UTC)
        self.assertEqual([x["volume"] for x in src], [10.0, 20.0])
        self.assertEqual([{k: v for k, v in x.items() if k != "volume"} for x in out],
                         [{k: v for k, v in x.items() if k != "volume"} for x in src])

    def test_volume_context_normalises_every_loaded_series_and_restores_load(self):
        c = self._hourly([10.0, 20.0, 30.0])
        bt = types.SimpleNamespace(load=lambda s, t: (c, "synthetic"))
        real = bt.load
        with WA._volume(bt, "hour_norm", UTC) as neutral:
            got, _ = bt.load("XAUUSD", "1H")
            again, _ = bt.load("XAUUSD", "1D")
            self.assertEqual([x["volume"] for x in got], [1.0, 2.0, 2.0])
            self.assertEqual(again, got)
            self.assertEqual(neutral, {"XAUUSD|1H": 1, "XAUUSD|1D": 1})
        self.assertIs(bt.load, real)
        with WA._volume(bt, "raw", UTC):
            self.assertIs(bt.load, real)


def _fake_cost(calls):
    def cost(entry, stop, t_in, t_out, sym, side, profile, stat="median"):
        calls.append((entry, stop, t_in, t_out, sym, side, profile, stat))
        return {"total_R": 0.05, "swap_R": 0.01} if stat == "median" else {"total_R": 0.08, "swap_R": 0.02}
    return cost


class _SeriesCase(unittest.TestCase):
    N = 3000                                                    # 4H bars from 2023-01-02: ~500 days, 6 slots a day
    #                                                             (DST moves a UTC bar between two server slots)

    @classmethod
    def setUpClass(cls):
        cls.c = random_candles(cls.N)
        cls.S = WA.Series("XAUUSD", "4H", cls.c, WA.server_zone(), datetime.date(2023, 1, 1))

    def setUp(self):
        self.S.prev_dense = [True] * self.N                     # geometry tests: every day counts
        self.S._pools = None


class Placebo(_SeriesCase):
    def test_pool_is_slot_matched_dense_and_has_an_atr(self):
        self.S.prev_dense = [i % 7 != 0 for i in range(self.N)]
        for slot in set(self.S.slot):
            for p in self.S.pool(slot):
                self.assertEqual(self.S.slot[p], slot)
                self.assertTrue(self.S.prev_dense[p])
                self.assertGreater(self.S.atr[p - 1], 0)
        self.assertNotIn(7, self.S.pool(self.S.slot[7]))

    def test_fixed_seed_same_draw_for_the_same_event_another_for_another(self):
        slot = self.S.slot[600]
        self.assertGreater(len(self.S.pool(slot)), WA.N_PLACEBO)
        a = WA.placebo_draw(self.S, slot, self.S.T[599])
        self.assertEqual(a, WA.placebo_draw(self.S, slot, self.S.T[599]))
        self.assertNotEqual(a, WA.placebo_draw(self.S, slot, self.S.T[593]))
        self.assertEqual(len(a), WA.N_PLACEBO)
        self.assertEqual(len(set(a)), WA.N_PLACEBO)             # without replacement
        self.assertEqual(WA.placebo_draw(self.S, slot, self.S.T[599], n=10_000), self.S.pool(slot))


class ScoreEvent(_SeriesCase):
    def setUp(self):
        super().setUp()
        self.k = 700
        S, k = self.S, self.k
        e = S.O[k + 1]
        self.sig = {"k": k, "side": "long", "leg": "spring", "stop": e - 3 * S.atr[k], "target": e + 5 * S.atr[k],
                    "event": "ev", "path": "spring", "signal_time": S.T[k]}
        self.calls, self.walks = [], []
        real = BT.walk

        def spy(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=None, O_=None):
            self.walks.append(dict(side=side, entry=entry, stop=stop, target=target, H0=H_[start], start=start, n=len(H_)))
            return real(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=Tm, O_=O_)
        p = mock.patch.object(BT, "walk", spy)
        p.start()
        self.addCleanup(p.stop)

    def score(self, arm="ENGINE-BOOK", sig=None, cost=None):
        a = WA.ARMS[arm]
        with WA._opts(BT, a["walk"]):
            return WA.score_event(BT, self.S, sig or self.sig, a, cost or _fake_cost(self.calls), BT.P["4H"]["H"])

    def test_next_open_entry_walked_from_its_own_bar_with_the_atr_multiple_placebo(self):
        S, k = self.S, self.k
        row, why = self.score()
        self.assertIsNone(why)
        ev = self.walks[0]
        self.assertEqual((ev["entry"], ev["start"], ev["H0"]), (S.O[k + 1], 0, S.H[k + 1]))
        self.assertAlmostEqual(row["stop_atr"], 3.0)
        self.assertAlmostEqual(row["target_atr"], 5.0)
        plc = self.walks[1:]
        self.assertEqual(len(plc), WA.N_PLACEBO)
        by_open = {S.O[p]: p for p in range(1, self.N)}
        for w in plc:
            p = by_open[w["entry"]]
            self.assertEqual(S.slot[p], S.slot[k + 1])
            self.assertEqual(w["start"], 0)
            self.assertAlmostEqual(w["entry"] - w["stop"], 3.0 * S.atr[p - 1])
            self.assertAlmostEqual(w["target"] - w["entry"], 5.0 * S.atr[p - 1])
        self.assertEqual(row["n_placebo"], WA.N_PLACEBO)
        self.assertAlmostEqual(row["excess"], row["R"] - row["placebo"])
        self.assertAlmostEqual(row["net_excess"], row["excess"] - 0.05)
        self.assertAlmostEqual(row["net_abs"], row["R"] - 0.05)
        self.assertEqual(row["cost"], {"median_swap": 0.05, "median_noswap": 0.04, "p90_swap": 0.08, "p90_noswap": 0.06})
        self.assertEqual(row["week"], WA.week_of(S.dt[k]))

    def test_cost_lines_are_priced_at_the_fill_and_the_exit(self):
        row, _ = self.score()
        self.assertEqual([c[7] for c in self.calls], ["median", "p90"])
        for c in self.calls:
            self.assertEqual((c[2], c[3], c[4], c[5], c[6]),
                             (self.S.T[self.k + 1], row["exit_time"], "XAUUSD", "long", "ftmo_demo_2026_09_relspread"))
            self.assertEqual((c[0], c[1]), (row["entry"], self.sig["stop"]))

    def test_an_open_at_or_beyond_the_stop_or_target_is_skipped_unwalked(self):
        e = self.S.O[self.k + 1]
        for sig in (dict(self.sig, stop=e + 0.01), dict(self.sig, stop=e), dict(self.sig, target=e - 0.01)):
            self.walks.clear()
            self.assertEqual(self.score(sig=sig), (None, "entry_beyond_stop_or_target"))
            self.assertEqual(self.walks, [])

    def test_a2_floor_uses_the_cost_known_at_entry(self):
        """R:R at the next open 8 / 3 = 2.67: admitted at zero cost, refused once the entry-hour cost exceeds 0.17 R; the
        cost asked is the one knowable at entry (exit time = entry time). ENGINE-BOOK has no floor at all."""
        e, a = self.S.O[self.k + 1], self.S.atr[self.k]
        sig = dict(self.sig, target=e + 8 * a)
        calls = []

        def cost(c):
            return lambda *args: calls.append(args) or {"total_R": c, "swap_R": 0.0}
        self.assertIsNone(self.score("A2", sig=sig, cost=cost(0.0))[1])
        self.assertEqual(calls[0][2], calls[0][3])
        self.assertEqual(calls[0][2], self.S.T[self.k + 1])
        self.assertEqual(self.score("A2", sig=sig, cost=cost(0.2)), (None, "below_floor"))
        self.assertEqual(self.score("A2", cost=cost(0.0)), (None, "below_floor"))     # 5 / 3 = 1.67 < 2.5
        self.assertIsNone(self.score("ENGINE-BOOK", cost=cost(0.0))[1])

    def test_a9_fills_at_the_signal_close_and_walks_from_the_next_bar(self):
        S, k = self.S, self.k
        sig = dict(self.sig, stop=S.C[k] - 3 * S.atr[k], target=S.C[k] + 5 * S.atr[k])
        row, why = self.score("A9", sig=sig)
        self.assertIsNone(why)
        ev = self.walks[0]
        self.assertEqual((ev["entry"], ev["start"], ev["n"]), (S.C[k], k + 1, self.N))
        self.assertEqual(row["entry_time"], iso(WA._utc(S.T[k]) + datetime.timedelta(hours=4)))
        for w in self.walks[1:]:
            self.assertEqual(S.C[w["start"] - 1], w["entry"])         # a placebo's entry is the close before its bar p

    def test_next_open_is_not_flattened_by_the_rollover_pre_check(self):
        """A10: walk()'s pre-check flattens a position "filled at the previous close" when a rollover lies between that
        close and the first walked bar. A next-open fill happened AFTER that boundary, so walk_from never asks it."""
        S = self.S
        ro = WA.ARMS["A10"]["walk"]
        with WA._opts(BT, ro):
            k = next(j for j in range(600, 900) if BT._RC.crosses_rollover(S.T[j], S.T[j + 1], ro["rollover_provider"]))
            e = k + 1
            ent = S.O[e]
            stop, tgt = ent - 50 * S.atr[k], ent + 50 * S.atr[k]
            naive = BT.walk("long", ent, stop, tgt, S.H, S.L, S.C, e, BT.P["4H"]["H"], Tm=S.T, O_=S.O)
            ours = WA.walk_from(BT, "long", ent, stop, tgt, S, e, BT.P["4H"]["H"], "next_open")
        self.assertEqual((naive["outcome"], naive["exit"]), ("rollover_flat", k))     # the hazard: exit before the entry bar
        self.assertGreaterEqual(ours["exit"], e)


class Signals(_SeriesCase):
    def trade(self, k, **kw):
        S = self.S
        t = dict(symbol="XAUUSD", tf="4H", side="long", leg="spring", event=f"XAUUSD-long-book-{S.T[k]}", time=S.T[k],
                 entry=S.C[k], entry_time=S.T[k], stop=S.C[k] - 5, target=S.C[k] + 15, path="spring")
        t.update(kw)
        return t

    def test_signal_bar_is_the_bar_the_engine_stamps_and_fills_at_its_close(self):
        sig = WA.signal(self.S, self.trade(500))
        self.assertEqual((sig["k"], sig["signal_time"]), (500, self.S.T[500]))
        with self.assertRaises(SystemExit):
            WA.signal(self.S, self.trade(500, entry=self.S.O[500]))
        with self.assertRaises(SystemExit):
            WA.signal(self.S, self.trade(500, entry_time="1999-01-01T00:00:00Z"))

    def test_only_events_after_a_dense_day_count(self):
        self.S.prev_dense = [i != 500 for i in range(self.N)]
        rows, skipped = WA.symbol_rows(BT, self.S, WA.ARMS["LEGACY-as-scored"],
                                       [dict(self.trade(500), R=1.0, outcome="win", exit_time=self.S.T[510], R_planned=3.0,
                                             bars_held=10, net_R=0.9),
                                        dict(self.trade(501), R=-1.0, outcome="loss", exit_time=self.S.T[505], R_planned=3.0,
                                             bars_held=4, net_R=-1.1)], None, 30)
        self.assertEqual(skipped, {"spring|prev_day_not_dense": 1})
        self.assertEqual([(r["signal_time"], r["R"], r["net_abs"], r["excess"]) for r in rows],
                         [(self.S.T[501], -1.0, -1.1, None)])


    def test_a_window_reaching_before_the_dense_start_is_not_an_event(self):
        S = WA.Series("XAUUSD", "4H", self.c, WA.server_zone(), self.S.sday[400])
        S.prev_dense = [True] * self.N
        f = S.first_dense
        self.assertTrue(0 < f <= 400)

        def legacy(k):
            return dict(self.trade(k), R=1.0, outcome="win", exit_time=S.T[k + 5], R_planned=3.0, bars_held=5, net_R=0.9)
        trades = [legacy(f + 298), legacy(f + 299)]
        rows, skipped = WA.symbol_rows(BT, S, WA.ARMS["LEGACY-as-scored"], trades, None, 30)
        self.assertEqual(skipped, {"spring|window_before_dense_start": 1})
        self.assertEqual([r["signal_time"] for r in rows], [S.T[f + 299]])
        self.assertEqual(WA.arm_window(BT, WA.ARMS["A5"]), 600)                    # A5's own window
        rows, skipped = WA.symbol_rows(BT, S, dict(WA.ARMS["LEGACY-as-scored"], scan=dict(fx_w6_window=600)), trades,
                                       None, 30)
        self.assertEqual((rows, skipped), ([], {"spring|window_before_dense_start": 2}))


class Statistics(unittest.TestCase):
    def rows(self, vals, weeks, tf="4H", leg="spring", excess=True):
        return [dict(leg=leg, tf=tf, week=w, R=v, net_abs=v - .1, placebo=0.0 if excess else None,
                     excess=v if excess else None, cost={l: .1 for l in WA.COST_LINES} if excess else None,
                     net_excess=v - .1 if excess else None) for v, w in zip(vals, weeks)]

    def test_summarise_is_cr1_by_week_on_each_cost_line(self):
        r = self.rows([1.0, -1.0, 2.0, 0.5], ["2023-W01", "2023-W01", "2023-W02", "2023-W03"])
        s = WA.summarise(r)
        self.assertEqual((s["n"], s["weeks"]), (4, 3))
        self.assertAlmostEqual(s["mean_gross_R"], 0.625)
        self.assertAlmostEqual(s["mean_net_excess"], 0.525)
        mu, se, df = WA.EC.cr1([v - .1 for v in (1.0, -1.0, 2.0, 0.5)], ["2023-W01", "2023-W01", "2023-W02", "2023-W03"])
        self.assertAlmostEqual(s["net_excess_median_swap"]["se_cr1_week"], se)
        self.assertEqual(set(WA.COST_LINES), {k[len("net_excess_"):] for k in s if k.startswith("net_excess_")})
        self.assertNotIn("mean_net_excess", WA.summarise(self.rows([1.0], ["2023-W01"], excess=False)))
        self.assertEqual(WA.summarise([]), {"n": 0})

    def test_week_bootstrap_difference_is_deterministic_and_brackets_the_point(self):
        rnd = random.Random(1)
        wk = [f"2023-W{w:02d}" for w in range(1, 41)]
        a = self.rows([rnd.gauss(0.3, 1) for _ in range(200)], [rnd.choice(wk) for _ in range(200)])
        b = self.rows([rnd.gauss(0.0, 1) for _ in range(150)], [rnd.choice(wk) for _ in range(150)])
        d1 = WA.week_bootstrap_diff(a, b, "net_excess", seed=42)
        d2 = WA.week_bootstrap_diff(a, b, "net_excess", seed=42)
        self.assertEqual(d1, d2)
        self.assertAlmostEqual(d1["diff"], sum(r["net_excess"] for r in a) / 200 - sum(r["net_excess"] for r in b) / 150)
        self.assertLess(d1["ci90"][0], d1["diff"])
        self.assertGreater(d1["ci90"][1], d1["diff"])
        self.assertEqual((d1["n_a"], d1["n_b"], d1["weeks"], d1["resamples_used"]), (200, 150, 40, WA.BOOT_N))
        self.assertIsNone(WA.week_bootstrap_diff(a, [], "net_excess", seed=1)["diff"])
        self.assertIsNone(WA.week_bootstrap_diff(a, self.rows([1.0], ["2023-W01"], excess=False), "net_excess", 1)["diff"])


# ------------------------------------------------------------------------------------------------ guards
class FakeGit:
    """`_git` for the guards: tracked / dirty paths, whether a commit adds the sealed file, paths with history."""

    def __init__(self, tracked=(), dirty=(), added="2026-10-05T09:00:00+00:00", history=(), tree=(), all_tracked=False):
        self.tracked, self.dirty, self.added, self.history = set(tracked), set(dirty), added, set(history)
        self.tree, self.all_tracked = list(tree), all_tracked      # tree: porcelain lines, e.g. "?? scripts/new.py"

    def __call__(self, *args):
        p = args[-1]
        if args[0] == "ls-files":
            return (0, p) if p in self.tracked or self.all_tracked else (1, "")
        if args[0] == "status":
            paths = args[args.index("--") + 1:]
            lines = [" M " + q for q in paths if q in self.dirty]
            lines += [ln for ln in self.tree if any(ln[3:] == q or ln[3:].startswith(q + "/") for q in paths)]
            return 0, "".join(ln + "\n" for ln in lines)
        if args[0] == "log" and "--diff-filter=A" in args:
            assert "--format=%cI" in args, args                    # the seal is the COMMITTER date, as edge_wyckoff
            return 0, (self.added + "\n") if self.added else ""
        if args[0] == "log":
            return 0, "abc\n" if p in self.history else ""
        if args[0] == "rev-parse":
            return 0, "deadbeef\n"
        if args[0] == "merge-base":
            return 0, ""
        return 1, ""


SEALED = {"path": WA.PREREG, "sha256": "0" * 64, "seal_date": "2026-10-05"}


class Guards(unittest.TestCase):
    def setUp(self):
        WA._PROCESS["used"] = None
        self.addCleanup(WA._PROCESS.__setitem__, "used", None)

    def test_run_refuses_without_the_sealed_preregistration_before_touching_the_engine(self):
        boom = types.SimpleNamespace()                        # any attribute access would raise AttributeError
        with mock.patch.object(WA, "PREREG", "docs/plans/no-such-sealed-preregistration.md"):
            with self.assertRaises(SystemExit) as cm:
                WA.run("ENGINE-BOOK", "/tmp/never-written.json", require_clean=False, engine=boom)
        self.assertIn("-DRAFT", str(cm.exception))
        WA._PROCESS["used"] = None
        with mock.patch.object(WA, "PREREG", "docs/plans/no-such-sealed-preregistration.md"):
            with self.assertRaises(SystemExit):
                WA.report("/tmp/never-written.json", arm_paths={}, require_clean=False)

    def test_sealed_must_be_tracked_clean_and_added_by_a_commit(self):
        p = WA.PREREG_DRAFT                                    # a file that exists, standing in for the sealed one
        with mock.patch.object(WA, "PREREG", p):
            for git, msg in ((FakeGit(), "not tracked"), (FakeGit(tracked={p}, dirty={p}), "uncommitted"),
                             (FakeGit(tracked={p}, added=None), "not sealed")):
                with self.subTest(msg=msg), mock.patch.object(WA, "_git", git):
                    with self.assertRaises(SystemExit) as cm:
                        WA._require_sealed()
                    self.assertIn(msg, str(cm.exception))
            with mock.patch.object(WA, "_git", FakeGit(tracked={p})):
                got = WA._require_sealed()
        self.assertEqual((got["path"], got["seal_date"]), (p, "2026-10-05"))

    def test_registration_canonical_path_history_ledger_and_committed_code(self):
        want = WA.CANONICAL_OUT.format(seal="2026-10-05", arm="A3")
        out = os.path.join(ROOT, want)
        self.assertEqual(want, "docs/experiments/wyckoff-retest-2026-10-05/ablation-A3.json")
        with mock.patch.object(WA, "_git", FakeGit(tracked=WA.COMMITTED)), \
                mock.patch.object(WA, "_require_ledger", lambda: None), \
                mock.patch.object(WA, "_sha256", lambda p: "x"):
            with self.assertRaises(SystemExit):
                WA._require_registration("A3", "/tmp/elsewhere.json", SEALED)
            with self.assertRaises(SystemExit):
                WA._require_registration("A4", out, SEALED)                              # another arm's path
            got = WA._require_registration("A3", out, SEALED)
            self.assertEqual(set(got["committed_sha256"]), set(WA.COMMITTED))
        with mock.patch.object(WA, "_git", FakeGit(tracked=WA.COMMITTED, history={want})), \
                mock.patch.object(WA, "_require_ledger", lambda: None):
            with self.assertRaises(SystemExit) as cm:
                WA._require_registration("A3", out, SEALED)
            self.assertIn("already run", str(cm.exception))
        with mock.patch.object(WA, "_git", FakeGit(tracked=set(WA.COMMITTED) - {WA.ENGINE})), \
                mock.patch.object(WA, "_require_ledger", lambda: None):
            with self.assertRaises(SystemExit) as cm:
                WA._require_registration("A3", out, SEALED)
            self.assertIn(WA.ENGINE, str(cm.exception))
        rogue = types.ModuleType("_wy_rogue_abl")
        rogue.__file__ = os.path.join(ROOT, "scripts", "rogue_helper.py")
        for git, extra, msg in ((FakeGit(tracked=WA.COMMITTED, dirty={"scripts/risk_model.py"}), None, "uncommitted"),
                                (FakeGit(tracked=WA.COMMITTED, tree=["?? scripts/new_helper.py"]), None, "clean"),
                                (FakeGit(tracked=WA.COMMITTED, tree=[" M data/history/costs/ftmo/x.json"]), None, "clean"),
                                (FakeGit(tracked=WA.COMMITTED), {"_wy_rogue_abl": rogue}, "does not fingerprint")):
            with self.subTest(msg=msg), mock.patch.object(WA, "_git", git), \
                    mock.patch.object(WA, "_require_ledger", lambda: None), mock.patch.dict(sys.modules, extra or {}):
                with self.assertRaises(SystemExit) as cm:
                    WA._require_registration("A3", out, SEALED)
                self.assertIn(msg, str(cm.exception))
        self.assertEqual(WA.COMMITTED, (WA.PREREG, WA.LEDGER) + WA.EW.CODE)
        self.assertTrue({WA.SCRIPT, WA.ENGINE, "scripts/risk_model.py", "docs/architecture/risk-config.json",
                         "scripts/research/edge_wyckoff.py"} <= set(WA.CODE))
        self.assertTrue({"script_sha256", "code_sha256"} <= set(WA.META_FIXED))
        self.assertEqual(WA._meta("read", "A3")["code_sha256"], WA.EW.code_sha256())
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write('{"note": "no study here"}')
        self.addCleanup(os.unlink, fh.name)
        with mock.patch.object(WA, "LEDGER", fh.name):
            with self.assertRaises(SystemExit):
                WA._require_ledger()

    def test_hour_frame_must_be_the_server_table(self):
        WA._require_hour_frame()
        with mock.patch.object(WA.RC, "HOUR_FRAME", "utc_legacy"):
            with self.assertRaises(SystemExit):
                WA._require_hour_frame()
            with mock.patch.object(WA, "_require_sealed", lambda: SEALED):
                with self.assertRaises(SystemExit):
                    WA.run("ENGINE-BOOK", "/tmp/never-written.json", require_clean=False, engine=types.SimpleNamespace())

    def test_unknown_arm_and_one_arm_per_process(self):
        with self.assertRaises(SystemExit):
            WA.run("A11", "/tmp/x.json", require_clean=False)
        WA._require_fresh_process("count", "A1")
        with self.assertRaises(SystemExit):
            WA._require_fresh_process("run", "A2")

    def test_cli_run_and_report_always_run_under_the_guard(self):
        seen = []
        with mock.patch.object(WA, "run", lambda *a, **k: seen.append(("run", a, k))), \
                mock.patch.object(WA, "report", lambda *a, **k: seen.append(("report", a, k))), \
                mock.patch.object(sys, "argv", ["x", "run", "--arm", "A5", "--counts", "r0.json", "--out", "o.json"]):
            WA.main()
        with mock.patch.object(WA, "report", lambda *a, **k: seen.append(("report", a, k))), \
                mock.patch.object(sys, "argv", ["x", "report", "--out", "r.json"]):
            WA.main()
        self.assertEqual(seen, [("run", ("A5", "o.json"), {"counts_path": "r0.json"}), ("report", ("r.json",), {})])
        for cmd in ("run", "count"):                                                # no R0, no read
            with mock.patch.object(sys, "argv", ["x", cmd, "--arm", "A5", "--out", "o.json"]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                WA.main()


# ------------------------------------------------------------------------------------------------ end to end (stubbed scan)
class EndToEnd(unittest.TestCase):
    """run / count / report on a synthetic 4H series with bt.scan stubbed to a fixed list of engine trades (the engine's own
    scan is tested above; here the harness's plumbing is)."""
    N = 1500

    def setUp(self):
        WA._PROCESS["used"] = None
        self.addCleanup(WA._PROCESS.__setitem__, "used", None)
        self.tmp = tempfile.mkdtemp()
        self.c = random_candles(self.N)
        self.r0 = _r0_file(self.tmp, {"XAUUSD|4H": {"start": "2023-01-01"}})
        self.scan_calls = []
        self.bt = _load("bt_wy_ablation_e2e", "scripts/backtest-methods.py")
        S = WA.Series("XAUUSD", "4H", self.c, WA.server_zone())
        self.trades = []
        for k in range(400, 1400, 37):
            side = "long" if k % 2 else "short"
            sgn = 1 if side == "long" else -1
            t = dict(symbol="XAUUSD", tf="4H", side=side, leg="spring" if k % 3 else "phase_d",
                     event=f"XAUUSD-{side}-book-{self.c[k]['time']}", time=self.c[k]["time"], entry=S.C[k],
                     entry_time=S.T[k], stop=S.C[k] - sgn * 2 * S.atr[k], target=S.C[k] + sgn * 7 * S.atr[k], path="spring")
            w = self.bt.walk(side, t["entry"], t["stop"], t["target"], S.H, S.L, S.C, k + 1, 30, Tm=S.T, O_=S.O)
            self.trades.append(dict(t, exit_time=S.T[w["exit"]], **w))

        def scan(sym, tf, only=None, opts=None):
            self.scan_calls.append((sym, tf, only, opts))
            self.bt.load(sym, tf)                              # what the engine reads (A7: normalised)
            return {"trades": {"WYCKOFF-BOOK": [dict(t) for t in self.trades]}}
        for p in (mock.patch.object(self.bt, "scan", scan),
                  mock.patch.object(self.bt, "load", lambda s, t: ((list(self.c), "synthetic") if (s, t) == ("XAUUSD", "4H")
                                                                   else (None, None))),
                  mock.patch.object(WA, "_require_sealed", lambda: SEALED)):
            p.start()
            self.addCleanup(p.stop)

    def run_arm(self, arm, out=None):
        WA._PROCESS["used"] = None
        out = out or os.path.join(self.tmp, f"ablation-{arm}.json")
        with contextlib.redirect_stdout(io.StringIO()):
            return WA.run(arm, out, counts_path=self.r0, require_clean=False, engine=self.bt, cost_fn=_fake_cost([]),
                          symbols=("XAUUSD",), timeframes=("4H",)), out

    def test_run_engine_book_scans_once_with_the_arm_overlay_and_writes_every_event(self):
        res, out = self.run_arm("ENGINE-BOOK")
        self.assertEqual(self.scan_calls, [("XAUUSD", "4H", ("WYCKOFF-BOOK",), WA.ARMS["ENGINE-BOOK"]["scan"])])
        with open(out, encoding="utf-8") as fh:
            rec = json.load(fh)
        self.assertEqual((rec["meta"]["arm"], rec["meta"]["kind"], rec["meta"]["guarded"]), ("ENGINE-BOOK", "read", False))
        self.assertEqual(len(rec["rows"]) + sum(rec["skipped"]["XAUUSD|4H"].values()), len(self.trades))
        self.assertGreater(len(rec["rows"]), 10)
        for r in rec["rows"]:
            self.assertAlmostEqual(r["net_excess"], r["excess"] - 0.05)
            self.assertEqual(r["entry"], self.c[self.idx(r["signal_time"]) + 1]["open"])
        n = sum(v["n"] for v in rec["cells"].values())
        self.assertEqual(n, len(rec["rows"]))
        self.assertEqual(self.bt.OPTS, self.bt._OPTS_BASE)     # no OPTS leak out of the read

    def idx(self, t):
        return [x["time"] for x in self.c].index(t)

    def test_read_once_and_one_arm_per_process(self):
        _res, out = self.run_arm("A1")
        with self.assertRaises(SystemExit):                    # same process: refused before anything
            WA.run("A2", os.path.join(self.tmp, "a2.json"), counts_path=self.r0, require_clean=False, engine=self.bt,
                   cost_fn=_fake_cost([]))
        WA._PROCESS["used"] = None
        with self.assertRaises(SystemExit):                    # same --out: refused, never overwritten
            WA.run("A1", out, counts_path=self.r0, require_clean=False, engine=self.bt, cost_fn=_fake_cost([]))

    def test_legacy_as_scored_is_simulates_admission_and_net_r(self):
        res, _ = self.run_arm("LEGACY-as-scored")
        sim = res["legacy_simulate"]["XAUUSD|4H"]
        self.assertEqual(sim["scanned"], len(self.trades))
        self.assertEqual(sim["min_rr"], self.bt.MIN_RR)
        self.assertLessEqual(sim["admitted"], len(self.trades))
        self.assertEqual(len(res["rows"]) + sum(res["skipped"]["XAUUSD|4H"].values()), sim["admitted"])
        for r in res["rows"]:
            t = next(x for x in self.trades if x["entry_time"] == r["signal_time"])
            fee = 2 * WA.LEGACY_FEE / (abs(t["entry"] - t["stop"]) / t["entry"])
            self.assertAlmostEqual(r["net_abs"], round(t["R"] - fee, 3))
            self.assertIsNone(r["excess"])
            self.assertGreaterEqual(t["R_planned"] - fee, self.bt.MIN_RR)

    def test_a7_feeds_the_engine_hour_normalised_volume(self):
        seen = []
        real_scan = self.bt.scan

        def scan(sym, tf, only=None, opts=None):
            seen.append(self.bt.load(sym, tf)[0][:60])
            return real_scan(sym, tf, only=only, opts=opts)
        with mock.patch.object(self.bt, "scan", scan):
            res, _ = self.run_arm("A7")
        vols = [x["volume"] for x in seen[0]]
        self.assertNotEqual(vols, [x["volume"] for x in self.c[:60]])
        self.assertEqual([x["close"] for x in seen[0]], [x["close"] for x in self.c[:60]])
        self.assertIn("XAUUSD|4H", res["a7_neutral_bars"])
        self.assertEqual(self.bt.load("XAUUSD", "4H")[0][5]["volume"], self.c[5]["volume"])     # load restored

    def test_count_is_outcome_blind(self):
        poison = [dict(t, R="POISON", outcome="POISON", exit_time="POISON", R_planned="POISON", net_R="POISON")
                  for t in self.trades]
        out = os.path.join(self.tmp, "count.json")
        with mock.patch.object(self.bt, "scan", lambda *a, **k: {"trades": {"WYCKOFF-BOOK": [dict(t) for t in poison]}}), \
                mock.patch.object(self.bt, "simulate", mock.Mock(side_effect=AssertionError("count must not simulate"))), \
                contextlib.redirect_stdout(io.StringIO()):
            for arm in ("ENGINE-BOOK", "LEGACY-as-scored", "A2"):
                WA._PROCESS["used"] = None
                res = WA.count(arm, out, counts_path=self.r0, engine=self.bt, cost_fn=_fake_cost([]), symbols=("XAUUSD",),
                               timeframes=("4H",))
                with open(out, encoding="utf-8") as fh:
                    self.assertNotIn("POISON", fh.read())
                legs = res["series"]["XAUUSD|4H"]["legs"]
                self.assertEqual(sum(legs[g]["signals"] for g in WA.LEGS), len(self.trades))
                self.assertEqual(res["meta"]["kind"], "count")

    def test_report_ties_every_arm_to_one_code_and_one_r0(self):
        paths = {}
        for arm in WA.ARMS:
            _res, paths[arm] = self.run_arm(arm)

        def rewrite(arm, **meta):
            with open(paths[arm], encoding="utf-8") as fh:
                rec = json.load(fh)
            rec["meta"].update(meta)
            out = os.path.join(self.tmp, f"x-{arm}-{len(meta)}-{sorted(meta)[-1]}.json")
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(rec, fh)
            return out
        guarded = {a: rewrite(a, guarded=True) for a in WA.ARMS}
        seen = []
        git = FakeGit(all_tracked=True)
        anchor = lambda p, clean: seen.append((os.path.normpath(p), clean))       # noqa: E731
        rel = mock.patch.object(WA, "_rel", lambda p: "docs/experiments/wyckoff-retest-x/ablation-arm.json")
        with mock.patch.object(WA, "_git", git), mock.patch.object(WA, "r0_record", anchor), rel:
            self.assertEqual(set(WA._check_order(guarded, require_clean=True)), set(WA.ARMS))
        self.assertEqual(seen, [(os.path.normpath(self.r0), True)])               # R0 re-validated under the guard
        code = WA.EW.code_sha256()
        for arm, meta, msg in (("A4", {"code_sha256": dict(code, **{WA.ENGINE: "0" * 64})}, "code_sha256"),
                               ("A4", {"script_sha256": "0" * 64}, "script_sha256"),
                               ("A6", {"counts": {"path": "elsewhere.json", "sha256": "0" * 64}}, "counts")):
            bad = dict(guarded, **{arm: rewrite(arm, guarded=True, **meta)})
            with self.subTest(msg=msg), mock.patch.object(WA, "_git", git), mock.patch.object(WA, "r0_record", anchor), rel:
                with self.assertRaises(SystemExit) as cm:
                    WA._check_order(bad, require_clean=True)
                self.assertIn(msg, str(cm.exception))
        with open(self.r0, "a", encoding="utf-8") as fh:                          # the R0 they ran on changed since
            fh.write(" ")
        with mock.patch.object(WA, "_git", git), mock.patch.object(WA, "r0_record", anchor), rel:
            with self.assertRaises(SystemExit) as cm:
                WA._check_order(guarded, require_clean=True)
            self.assertIn("changed since", str(cm.exception))

    def test_report_needs_all_thirteen_records_and_reports_engine_minus_arm(self):
        paths = {}
        for arm in WA.ARMS:
            _res, paths[arm] = self.run_arm(arm)
        out = os.path.join(self.tmp, "report.json")
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit):
                WA.report(out, arm_paths={a: p for a, p in paths.items() if a != "A9"}, require_clean=False)
            rep = WA.report(out, arm_paths=paths, require_clean=False)
        self.assertEqual(set(rep["minus_reference"]), set(WA.ARMS) - {"ENGINE-BOOK"})
        d = rep["minus_reference"]["A1"]["spring|4H"]
        self.assertEqual(d["net_excess"]["diff"], 0.0)          # the stub scan gives A1 ENGINE-BOOK's events
        self.assertIsNone(rep["minus_reference"]["LEGACY-as-scored"]["spring|4H"]["net_excess"]["diff"])
        self.assertIsNotNone(rep["minus_reference"]["LEGACY-as-scored"]["spring|4H"]["net_abs"]["diff"])
        self.assertTrue(os.path.exists(os.path.splitext(out)[0] + ".md"))
        with self.assertRaises(SystemExit):                     # written once
            WA.report(out, arm_paths=paths, require_clean=False)
        with open(paths["A5"], encoding="utf-8") as fh:
            rec = json.load(fh)
        rec["meta"]["parameters"]["n_placebo"] = 199
        bad = os.path.join(self.tmp, "bad-A5.json")
        with open(bad, "w", encoding="utf-8") as fh:
            json.dump(rec, fh)
        with self.assertRaises(SystemExit) as cm:
            WA.report(os.path.join(self.tmp, "r2.json"), arm_paths=dict(paths, A5=bad), require_clean=False)
        self.assertIn("parameters", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
