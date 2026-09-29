"""Batch 1(b) Wyckoff fidelity items (docs/plans/2026-09-28-methodology-improvement-plan.md section 3), each behind
its own `fx_<item>` key per the shared contract in docs/plans/2026-09-29-execution-plan.md:

    W1 fx_w1_tr_low_st     WA p72   (knowledge/wyckoff/advance.md:302) -- TR low = min(SC low, ST low)
    W2 fx_w2_st_below_sc   WA2-06 / WA p72, p74-75, p77 -- ST below SC is not a discard, it is "expect new lows or
                           a prolonged consolidation"
    W3 fx_w3_mSOW_spring   WA p166 (knowledge/wyckoff/advance.md) -- "MSOW[B] cung la Spring tiem nang"
    W5 fx_w5_vp_abandon    WMT p243-249 Step 4 (knowledge/wyckoff/modern-tools.md) -- the "within 2 bars" clause has
                           no source and is removed
    W7 fx_w7_htf_target    WA2-19 (knowledge/wyckoff/advance.md:1090) -- Phase-D target = the HTF TR's AR/SOS;
                           built, AWAITING OWNER SIGN-OFF, not adopted

Every test builds a synthetic OHLCV window (helpers copied in shape from test_audit_round3_wyckoff.py) so the
detector finds exactly one structure, then flips ONE key and asserts the specific difference. Each item also has a
"key off == v1" assertion: the default must not change any output (the funnel doc records the on-vs-off deltas on
development data; this file proves the mechanism and that the default is inert).

A note on W1: with W2 off it is unobservable. A structure whose ST[A] dips below SC is discarded by the R1 CHoBEV
loop's `broke` exit before ST[A] is even looked up, so `tr_lo = min(SC, ST)` can only differ from `tr_lo = SC`
when W2 has let such a structure through. `test_w1_alone_is_inert_without_w2` pins that coupling.
"""
import importlib.util
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import wyckoff_rules as W  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FX_KEYS = ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon", "fx_w7_htf_target")


def leg(start, end, n, vol=10.0):
    """n bars ramping linearly start -> end, small wick each side (same helper shape as test_audit_round3_wyckoff)."""
    out = []
    for i in range(n):
        t = (i + 1) / n
        c = start + (end - start) * t
        o = start + (end - start) * (i / n)
        out.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c, vol))
    return out


def downtrend_prefix():
    """Lower lows + lower highs, ending in the SC (low 79.95 at bar 40)."""
    bars = []
    bars += leg(104, 102, 5) + leg(102, 99, 5) + leg(99, 101, 5) + leg(101, 97, 5)
    bars += leg(97, 100, 5) + leg(100, 90, 5) + leg(90, 96, 5) + leg(96, 80, 5)
    return bars


def base_through_choch():
    """Prefix -> SC(79.95) -> AR(110.05) -> ST(84.95) -> three CHoBEV up-swings (the third, ending bar 69, carries
    extra volume: the CHoBEV test is 'spread AND volume larger than the downtrend's reactions', and equal volume
    fails it -- checked while building the W3 fixture). CHoCH completes at bar 69."""
    bars = downtrend_prefix()
    bars += leg(80, 110, 6) + leg(110, 85, 6) + leg(85, 108, 6) + leg(108, 88, 6) + leg(88, 106, 6, vol=14.0)
    return bars


def base_accumulation():
    """Same shape the round-3 tests use: base_through_choch plus three Phase-B swings, ending mid-range (92)."""
    return base_through_choch() + leg(106, 90, 6) + leg(90, 100, 6) + leg(100, 92, 6)


def cols(bars):
    return ([b[0] for b in bars], [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars])


def detect(bars, **fx):
    """detect_accumulations on `bars` with the given PARAMS overrides (fx keys or test-local params)."""
    O, H, L, C, V = cols(bars)
    W.STATS.clear()
    return W.detect_accumulations(O, H, L, C, V, P=dict(W.PARAMS, **fx))


def st_below_sc_bars(final_low):
    """A structure whose ST[A] (69.95, bar 52) prints BELOW the SC (79.95). Sequence of legs after the SC:
    AR 110.05 (CHoBEV 1), X = the ST[A] low 69.95, Y 105.05 (CHoBEV 2), Z 94.95, W 112.05 (CHoBEV 3, CHoCH
    completes), then Phase-B swings inside 94-109, then one final test bar whose low is `final_low`."""
    bars = downtrend_prefix()
    bars += leg(80, 110, 6) + leg(110, 70, 6) + leg(70, 105, 6) + leg(105, 95, 6) + leg(95, 112, 6)
    bars += leg(112, 98, 6) + leg(98, 106, 6) + leg(106, 94, 6) + leg(94, 104, 6)
    bars += [(90, 91, final_low, final_low + 1, 15.0)]
    return bars


class DefaultsAreV1(unittest.TestCase):
    """The mechanism must be inert until a caller sets a key (plan section 1.6 'live safety')."""

    def test_params_default_false(self):
        for k in FX_KEYS[:4]:
            self.assertIn(k, W.PARAMS)
            self.assertIs(W.PARAMS[k], False, k)

    def test_opts_base_carries_every_key_false(self):
        bt = _load("bt_fx_defaults", "backtest-methods.py")
        for k in FX_KEYS:
            self.assertIs(bt._OPTS_BASE[k], False, k)
            self.assertIs(bt.OPTS[k], False, k)

    def test_stability_report_lists_and_states_every_key(self):
        sr = _load("sr_fx_defaults", "stability-report.py")
        for k in FX_KEYS:
            self.assertIn(k, sr._SCAN_RELEVANT_KEYS, k)
            self.assertIs(sr.config_opts(sr.CONFIGS["A"], "range").get(k, "missing"), False, k)

    def test_config_snapshot_records_every_key(self):
        bt = _load("bt_fx_snapshot", "backtest-methods.py")
        import snapshot
        fields = snapshot.backtest_config_snapshot(bt, timeframes=["15m"], methods={"WYCKOFF-BOOK"}, market="cfd")["fields"]
        cc = fields["custom_constraints"]
        for k in FX_KEYS:
            self.assertIn(k, cc, k)
            self.assertIs(cc[k], False, k)

    def test_v1_detection_is_unchanged_with_every_key_explicitly_false(self):
        """Explicit False must equal 'key absent' -- guards against a truthiness-vs-presence slip."""
        for bars in (base_accumulation(), st_below_sc_bars(75.0)):
            O, H, L, C, V = cols(bars)
            absent = W.detect_accumulations(O, H, L, C, V, P={k: v for k, v in W.PARAMS.items() if k not in FX_KEYS})
            explicit = W.detect_accumulations(O, H, L, C, V, P=dict(W.PARAMS, **{k: False for k in FX_KEYS[:4]}))
            self.assertEqual(absent, explicit)


class W1TrLowIsMinOfScAndSt(unittest.TestCase):
    """WA p72 (knowledge/wyckoff/advance.md:302): 'Nếu ST đi xuống thấp hơn SC, ... Mức thấp của SC và ST và mức cao
    của AR thiết lập ranh giới của TR.' -- the TR low is the lower of SC and ST."""

    def test_tr_lo_widens_to_the_st_low_when_on(self):
        bars = st_below_sc_bars(65.0)          # final bar breaks even the widened border, so a Spring is recorded
        off = detect(bars, fx_w2_st_below_sc=True)
        on = detect(bars, fx_w2_st_below_sc=True, fx_w1_tr_low_st=True)
        self.assertEqual(len(off), 1)
        self.assertEqual(len(on), 1)
        self.assertAlmostEqual(off[0]["tr_lo"], 79.95, places=6)   # SC low
        self.assertAlmostEqual(on[0]["tr_lo"], 69.95, places=6)    # ST low (bar 52)

    def test_st_pct_is_framed_over_the_phase_a_range_and_unaffected(self):
        """The doc says st_pct/st_sign (WA p150 thirds) are computed BEFORE the widening."""
        bars = st_below_sc_bars(65.0)
        off = detect(bars, fx_w2_st_below_sc=True)[0]
        on = detect(bars, fx_w2_st_below_sc=True, fx_w1_tr_low_st=True)[0]
        self.assertEqual(off["st_pct"], on["st_pct"])
        self.assertEqual(off["st_sign"], on["st_sign"])

    def test_a_break_between_the_two_borders_is_a_break_only_when_off(self):
        """Final bar low 75 is below SC (79.95) but above the ST low (69.95): with W1 off it is a border break
        (a Spring); with W1 on it is still inside the TR, so no Phase-C event is recorded."""
        bars = st_below_sc_bars(75.0)
        self.assertEqual(len(detect(bars, fx_w2_st_below_sc=True)), 1)
        self.assertEqual(len(detect(bars, fx_w2_st_below_sc=True, fx_w1_tr_low_st=True)), 0)

    def test_w1_alone_is_inert_without_w2(self):
        """ST below SC never reaches the ST lookup while the R1 loop still discards it (see module docstring)."""
        for final_low in (65.0, 75.0):
            bars = st_below_sc_bars(final_low)
            self.assertEqual(detect(bars), detect(bars, fx_w1_tr_low_st=True))

    def test_structure_where_st_holds_above_sc_is_unchanged(self):
        """min(SC, ST) == SC when ST holds above SC (the common case), so W1 must not change anything there."""
        bars = base_accumulation()
        self.assertEqual(detect(bars), detect(bars, fx_w1_tr_low_st=True))


class W2StBelowScIsNotADiscard(unittest.TestCase):
    """WA2-06 / WA p72 (knowledge/wyckoff/advance.md:302): 'Nếu ST đi xuống thấp hơn SC, người ta có thể dự đoán mức
    thấp mới hoặc sự củng cố kéo dài.' The book predicts a longer range; it does not say the structure is void."""

    def test_v1_discards_it_at_the_chobev_loop(self):
        recs = detect(st_below_sc_bars(75.0))
        self.assertEqual(recs, [])
        self.assertEqual(W.STATS.get("2a_new_low_before_choch"), 1)

    def test_on_keeps_it_and_reaches_the_spring(self):
        recs = detect(st_below_sc_bars(75.0), fx_w2_st_below_sc=True)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual((r["sc"], r["st"], r["path"]), (40, 52, "spring"))
        self.assertEqual(r["st_sign"], "contradicts")     # the ST sits below SC, so WA p150's lower-third sign fires
        self.assertNotIn("2a_new_low_before_choch", W.STATS)

    def test_a_structure_that_never_dips_below_sc_is_unchanged(self):
        bars = base_accumulation()
        self.assertEqual(detect(bars), detect(bars, fx_w2_st_below_sc=True))


class W3EarlyBreakIsAlsoAPotentialSpring(unittest.TestCase):
    """WA p166 boxed method summary: 'Hoặc ở vị trí MSOW[B] cũng là Spring tiềm năng trong tích lũy ...' (also WA3-08,
    p189-190). R4 discarded any border break before `min_phase_b_swings` completed Phase-B swings.

    Fixture note: with the default `min_phase_b_swings=2` and `chobev_needed=3`, the CHoBEV counting itself already
    leaves two confirmed swings after ST[A] before the CHoCH bar, so an early break cannot occur inside the default
    window on this synthetic shape. The test raises `min_phase_b_swings` (test-local, a PROJECT parameter per the
    module docstring) to make the early-break case reachable -- the funnel doc reports how often it is reachable on
    real data ('4_break_before_phase_b' / '4b_mSOW_as_spring' rows)."""

    @staticmethod
    def _bars():
        bars = base_through_choch()
        bars += [(88, 89, 70, 71, 10.0)]           # bar 70: breaks tr_lo (79.95) the bar after the CHoCH
        bars += [(71, 82, 70, 81, 12.0)]           # bar 71: closes back above tr_lo -> reclaim
        bars += leg(81, 84, 6, vol=8.0) + leg(84, 86, 6, vol=8.0)   # trailing bars so the bar-69 pivot confirms
        return bars

    def test_v1_discards_at_r4(self):
        recs = detect(self._bars(), min_phase_b_swings=10)
        self.assertEqual(recs, [])
        self.assertEqual(W.STATS.get("4_break_before_phase_b"), 1)

    def test_on_feeds_the_break_through_the_spring_pipeline(self):
        recs = detect(self._bars(), min_phase_b_swings=10, fx_w3_mSOW_spring=True)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual((r["path"], r["spring"], r["reclaim"]), ("spring", 70, 71))
        self.assertEqual(W.STATS.get("4b_mSOW_as_spring"), 1)
        self.assertNotIn("4_break_before_phase_b", W.STATS)

    def test_a_break_after_phase_b_is_unchanged(self):
        """A break that already has >= min_phase_b_swings is the ordinary Spring path; W3 must not touch it."""
        bars = base_accumulation() + leg(92, 65, 2, vol=20.0) + [(66, 86, 65, 85.0, 15.0), (85, 91, 84, 90.0, 15.0)]
        self.assertEqual(detect(bars), detect(bars, fx_w3_mSOW_spring=True))


class W5AbandonWithoutTheUnsourcedTwoBarClause(unittest.TestCase):
    """WMT p243-249 Step 4 (knowledge/wyckoff/modern-tools.md): 'If price crosses cleanly through VAH/VAL into LVN
    WITHOUT a reversal reaction, ... abandon the Spring/Upthrust plan.' No bar count is given; the code's 'close back
    above VAL within 2 bars of the reclaim' window was unsourced. With the key on, the reclaim bar itself is the test."""

    @staticmethod
    def _bars():
        # Spring excursion to 65 (crosses the LVN 80.45), reclaim bar closes 85 (inside the TR, but BELOW the VAL
        # 88.98), and the very next bar closes 90 (above VAL) -- inside the old 2-bar window, outside the reclaim bar.
        return base_accumulation() + leg(92, 65, 2, vol=20.0) + [(66, 86, 65, 85.0, 15.0), (85, 91, 84, 90.0, 15.0)]

    def test_v1_window_forgives_a_late_close_back_above_val(self):
        r = detect(self._bars())[0]
        self.assertEqual((r["spring"], r["reclaim"]), (88, 90))
        self.assertAlmostEqual(r["val"], 88.98, places=2)
        self.assertFalse(r["abandon"])

    def test_on_tests_the_reclaim_bar_itself(self):
        r = detect(self._bars(), fx_w5_vp_abandon=True)[0]
        self.assertEqual((r["spring"], r["reclaim"]), (88, 90))
        self.assertTrue(r["abandon"])                     # C[reclaim] = 85.0 < VAL 88.98
        self.assertLess(cols(self._bars())[3][r["reclaim"]], r["val"])

    def test_only_the_abandon_flag_differs(self):
        off = detect(self._bars())[0]
        on = detect(self._bars(), fx_w5_vp_abandon=True)[0]
        diff = {k for k in off if off[k] != on[k]}
        self.assertEqual(diff, {"abandon"})

    def test_a_reclaim_bar_that_closes_above_val_is_not_abandoned_either_way(self):
        bars = base_accumulation() + leg(92, 65, 2, vol=20.0) + [(66, 96, 65, 95.0, 15.0)]
        for on in (False, True):
            recs = detect(bars, fx_w5_vp_abandon=on)
            self.assertEqual(len(recs), 1)
            self.assertFalse(recs[0]["abandon"], on)


class W7HtfTargetIsBuiltButNotAdopted(unittest.TestCase):
    """WA2-19 (knowledge/wyckoff/advance.md:1090): 'move UP a timeframe to see where the current TR sits inside the
    larger TR and use the larger TR's AR/SOS as the target.' Plan section 3 W7: no HTF TR means no Phase-D trade.
    AWAITING OWNER SIGN-OFF -- these tests prove the mechanism only."""

    def setUp(self):
        self.bt = _load("bt_fx_w7", "backtest-methods.py")
        self.bt._HTF_TR_CACHE.clear()

    @staticmethod
    def _htf_candles(bars, start_hour=0):
        """1H candles (the 15m rung's companion) as history_store rows; bar i opens at start + i hours."""
        import datetime
        t0 = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=start_hour)
        return [dict(time=(t0 + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     open=b[0], high=b[1], low=b[2], close=b[3], volume=b[4]) for i, b in enumerate(bars)]

    def _patch_load(self, candles):
        self.bt.load = lambda sym, tf: ((candles, None) if candles is not None else (None, None))

    def _htf_bars(self):
        return _HtfFixture.bars()

    def test_no_higher_rung_no_symbol_or_no_history_is_none(self):
        self._patch_load(None)
        self.assertIsNone(self.bt._htf_wyckoff_target("XAUUSD", "15m", "long", "2024-02-01T00:00:00Z"))
        self.assertIsNone(self.bt._htf_wyckoff_target(None, "15m", "long", "2024-02-01T00:00:00Z"))
        self.assertIsNone(self.bt._htf_wyckoff_target("XAUUSD", "1D", "long", "2024-02-01T00:00:00Z"))  # no rung above 1D

    def test_target_is_the_htf_ar_when_no_sos_yet(self):
        bars = self._htf_bars()
        self._patch_load(self._htf_candles(bars))
        decision = "2024-01-31T00:00:00Z"                   # after every synthetic bar has closed
        # the HTF Spring structure of _HtfFixture uses the default detector params; W.PARAMS is bridged by the module
        got = self.bt._htf_wyckoff_target("XAUUSD", "15m", "long", decision)
        # HTF record for this window is the W3 fixture with default min_phase_b_swings=2 (a normal Spring path):
        # its AR / tr_hi is 110.05, and it has no SOS.
        self.assertIsNotNone(got)
        self.assertAlmostEqual(got, 110.05, places=2)

    def test_target_is_the_sos_close_when_a_sos_exists(self):
        recs = [dict(sos=5, tr_hi=110.0, tr_lo=80.0)]
        self._patch_load(self._htf_candles(self._htf_bars()))
        with mock.patch.object(self.bt._structures, "wyckoff_records", lambda *a, **k: recs):
            got = self.bt._htf_wyckoff_target("XAUUSD", "15m", "long", "2024-01-31T00:00:00Z")
        self.assertEqual(got, self._htf_bars()[5][3])       # C_[sos]

    def test_short_side_falls_back_to_tr_lo(self):
        recs = [dict(sos=None, tr_hi=110.0, tr_lo=80.0)]
        self._patch_load(self._htf_candles(self._htf_bars()))
        with mock.patch.object(self.bt._structures, "wyckoff_records", lambda *a, **k: recs):
            self.assertEqual(self.bt._htf_wyckoff_target("XAUUSD", "15m", "short", "2024-01-31T00:00:00Z"), 80.0)

    def test_pit_bars_not_yet_closed_at_decision_time_are_invisible(self):
        """CLAUDE.md section 8: the HTF series is truncated to availableTime <= decisionTime BEFORE detection. A
        decision time earlier than the structure's completion must not see it (None), and the same series with a
        later decision time must (so the None above is the truncation, not a data problem)."""
        bars = self._htf_bars()
        self._patch_load(self._htf_candles(bars))
        early = "2024-01-02T00:00:00Z"                      # only ~24 1H bars closed; the structure needs 80+
        self.assertIsNone(self.bt._htf_wyckoff_target("XAUUSD", "15m", "long", early))
        self.assertIsNotNone(self.bt._htf_wyckoff_target("XAUUSD", "15m", "long", "2024-01-31T00:00:00Z"))

    # -- the _fires_from side: drop when None, override the target otherwise, default path untouched -------------

    @staticmethod
    def _phase_d_rec():
        return dict(st_sign="neutral", sloped=False, st_pct=0.5, tr_hi=110.0, tr_lo=80.0, ceiling=110.0, spring=None,
                    sos=3, path="lps_c", shakeout=False, abandon=False, sot_too_strong=False, vol_type=None,
                    bu=dict(bar=4, low=100.0))

    C = [100.0, 104.0, 108.0, 112.0, 105.0]
    Tm = ["2024-01-05T0%d:00:00Z" % i for i in range(5)]

    def test_default_uses_ceiling_plus_multiplier(self):
        f = self.bt._fires_from("long", [self._phase_d_rec()], self.C, self.Tm, sym="XAUUSD", tf="15m")
        self.assertEqual(len(f), 1)
        self.assertAlmostEqual(f[0]["target"], 110.0 + self.bt.W.PARAMS["d_target_tr"] * 30.0)

    def test_on_and_no_htf_tr_means_no_phase_d_trade(self):
        self.bt.OPTS["fx_w7_htf_target"] = True
        self.bt._htf_wyckoff_target = lambda *a: None
        self.assertEqual(self.bt._fires_from("long", [self._phase_d_rec()], self.C, self.Tm, sym="XAUUSD", tf="15m"), [])

    def test_on_and_htf_tr_replaces_the_target(self):
        self.bt.OPTS["fx_w7_htf_target"] = True
        self.bt._htf_wyckoff_target = lambda *a: 125.0
        f = self.bt._fires_from("long", [self._phase_d_rec()], self.C, self.Tm, sym="XAUUSD", tf="15m")
        self.assertEqual([x["target"] for x in f], [125.0])

    def test_on_and_htf_target_below_entry_is_not_placeable(self):
        self.bt.OPTS["fx_w7_htf_target"] = True
        self.bt._htf_wyckoff_target = lambda *a: 104.0      # below the 105 entry: the existing placeability check applies
        self.assertEqual(self.bt._fires_from("long", [self._phase_d_rec()], self.C, self.Tm, sym="XAUUSD", tf="15m"), [])

    def test_spring_leg_is_never_affected(self):
        """W7 only re-targets Phase D; the Spring leg's target stays the opposite TR border (WMT p273)."""
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        spring = src.split('leg="spring"')[0].rsplit('if w_bar == last:', 1)[1]
        self.assertNotIn("fx_w7_htf_target", spring)


class _HtfFixture:
    """Shared HTF fixture for the W7 tests: the W3 shape with default params yields a normal Spring structure."""

    @staticmethod
    def bars():
        # 96 bars: base_accumulation() + a real Spring/reclaim + trailing bars so every pivot confirms.
        return (base_accumulation() + leg(92, 65, 2, vol=20.0) + [(66, 96, 65, 95.0, 15.0)]
                + leg(95, 98, 6, vol=8.0) + leg(98, 100, 6, vol=8.0))


class DetectionKeysSeparateTheScanCache(unittest.TestCase):
    """`_wyckoff_candidates` must stay OPTS-independent; the four detection keys widen the `_WY_CANDIDATES` key
    instead, so two configs differing only in one key never share a cached detection."""

    def test_cache_key_is_widened_by_each_detection_key(self):
        bt = _load("bt_fx_cachekey", "backtest-methods.py")
        self.assertEqual(bt._FX_WYCKOFF_DETECTION_KEYS,
                         ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon"))
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("ck = (sym, tf, n, Tm[0], Tm[-1]) + tuple(OPTS.get(_k, False) for _k in _FX_WYCKOFF_DETECTION_KEYS)", src)

    def test_wyckoff_fires_bridges_the_opts_into_the_detector(self):
        """wyckoff_fires is the live runner's entry: with OPTS at v1 it must leave PARAMS False; a scan()/caller
        that set a key gets it bridged, and it is restored to OPTS's value on the next call."""
        bt = _load("bt_fx_bridge", "backtest-methods.py")
        W.PARAMS["fx_w5_vp_abandon"] = True                  # simulate a leaked setting from an earlier scan
        bt.wyckoff_fires("long", [dict(time="2024-01-01T00:%02d:00Z" % (i % 60), open=1, high=2, low=1, close=1.5, volume=1)
                                  for i in range(30)], "15m", sym="XAUUSD")
        self.assertIs(W.PARAMS["fx_w5_vp_abandon"], False)

    def test_an_isolated_scan_does_not_leak_its_keys_into_the_shared_detector(self):
        bt = _load("bt_fx_leak", "backtest-methods.py")
        bt.load = lambda sym, tf: (None, None)               # scan() returns None right after the opts= wrapper
        self.assertIsNone(bt.scan("XAUUSD", "15m", opts={"fx_w5_vp_abandon": True}))
        self.assertIs(W.PARAMS["fx_w5_vp_abandon"], False)


if __name__ == "__main__":
    unittest.main()
