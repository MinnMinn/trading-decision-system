"""Batch 2(a): the Wyckoff V items (docs/plans/2026-09-28-methodology-improvement-plan.md section 3, the V grid;
docs/plans/2026-09-29-execution-plan.md "Shared contract"), each behind ONE OPTS key whose default is the baseline
(v1), plus the machine-readable grid docs/architecture/v-grid-wyckoff.json that scripts/fund-search.py reads.

    W-STOP   fx_w_stop              current | spring_low   WMT p271  (knowledge/wyckoff/modern-tools.md)
    W4a      fx_w4a_linger_closes   2 | 3 | 4              WA2-12, WA p80, p83 (knowledge/wyckoff/advance.md:1083)
    W4b      (not implemented)      off | on               WA2-12, WA2-18 -- needs LTF trade placement the sources do not define
    W6       fx_w6_window           300 | 600              fidelity section 3.3 B1 (project); coupled to ICT SCAN_WINDOW
    W-MGMT   mgmt (existing knob)   none | be              WMT p272
    W-SPT    fx_w_spt               AR | ceiling | VAH     WA p85; WMT p273
    W-TOUCH  fx_w_touch             off | on               advance.md 2.11.2 (WA p154)
    W-TW     fx_w_tw                (test window, Phase-B swings) in {12, 8, 20} x {2, 3}   project

Every item: default == v1; each non-baseline value changes behaviour on a hand-built fixture, long AND short; PARAMS is
never written; detection-affecting keys widen the caches; registered in the four places; the live runner never sets
them; and the grid's N arithmetic is 16 for Wyckoff (plan section 3).
"""
import copy
import datetime
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import wyckoff_rules as W  # noqa: E402
import test_wyckoff_fidelity as TW  # noqa: E402  (module import, not class import: its TestCases must not re-run here)

GRID = os.path.join(ROOT, "docs", "architecture", "v-grid-wyckoff.json")
V_KEYS = ("fx_w_stop", "fx_w4a_linger_closes", "fx_w6_window", "fx_w_spt", "fx_w_touch", "fx_w_tw")
BASELINE = dict(fx_w_stop="current", fx_w4a_linger_closes=None, fx_w6_window=300, fx_w_spt="AR", fx_w_touch="off",
                fx_w_tw=(12, 2))
_load = TW._load


def _grid():
    with open(GRID, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------------------------------------ grid file / N
class GridFile(unittest.TestCase):
    def test_parses_with_the_contract_shape(self):
        g = _grid()
        self.assertEqual(g["method"], "WYCKOFF-BOOK")
        self.assertEqual([i["id"] for i in g["items"]],
                         ["W-STOP", "W4a", "W4b", "W6", "W-MGMT", "W-SPT", "W-TOUCH", "W-TW"])
        for i in g["items"]:
            for f in ("id", "key", "existing_opts_key", "values", "joint_group", "source", "implemented"):
                self.assertIn(f, i, (i["id"], f))
            self.assertIsInstance(i["implemented"], bool)
            self.assertGreaterEqual(len(i["values"]), 2, i["id"])
            self.assertTrue(i["source"], i["id"])
            self.assertIsNone(i["joint_group"], i["id"])

    def test_n_is_16_one_baseline_plus_non_baseline_values_plus_one_combined(self):
        """plan section 3: Wyckoff N = 1 + 14 + 1 = 16. W-TW is a two-factor item: its grid is the full cross
        {12, 8, 20} x {2, 3} = 6 cells, one of them the baseline, so it contributes 5 (not 2 + 1 = 3). W4a's baseline
        is the grid's first value (2), so it contributes 2 (3 and 4); W4b is declared (it counts toward N and the
        pre-registration) even though it is not implemented."""
        g = _grid()
        per = {i["id"]: len(i["values"]) - 1 for i in g["items"]}
        self.assertEqual(per, {"W-STOP": 1, "W4a": 2, "W4b": 1, "W6": 1, "W-MGMT": 1, "W-SPT": 2, "W-TOUCH": 1,
                               "W-TW": 5})
        w_tw = next(i for i in g["items"] if i["id"] == "W-TW")
        self.assertEqual(len(w_tw["values"]), 3 * 2)
        self.assertEqual(len({tuple(v) for v in w_tw["values"]}), 6)
        self.assertEqual(sum(per.values()), 14)
        self.assertEqual(1 + sum(per.values()) + 1, 16)

    def test_values_match_the_engine_declared_sets(self):
        bt = _load("bt_v_wy_grid", "backtest-methods.py")
        for i in _grid()["items"]:
            if not i["implemented"] or i["key"] == "mgmt":
                continue
            declared = [list(v) if isinstance(v, tuple) else v for v in bt.WY_V_VALUES[i["key"]] if v is not None]
            self.assertEqual(i["values"], declared, i["id"])
        self.assertEqual({i["key"] for i in _grid()["items"] if i["implemented"] and i["key"] != "mgmt"},
                         set(bt.WY_V_VALUES))

    def test_baseline_is_first_and_the_engine_default_is_the_baseline(self):
        bt = _load("bt_v_wy_grid2", "backtest-methods.py")
        by_id = {i["id"]: i for i in _grid()["items"]}
        for id_, key in (("W-STOP", "fx_w_stop"), ("W6", "fx_w6_window"), ("W-SPT", "fx_w_spt"),
                         ("W-TOUCH", "fx_w_touch")):
            self.assertEqual(bt.OPTS[key], by_id[id_]["values"][0], id_)
        self.assertEqual(tuple(by_id["W-TW"]["values"][0]), bt.OPTS["fx_w_tw"])
        # W4a: the grid's first value (2) is the plan's declared baseline; the engine's v1 is the un-numbered rule.
        self.assertIsNone(bt.OPTS["fx_w4a_linger_closes"])
        self.assertEqual(by_id["W4a"]["values"][0], 2)

    def test_existing_knob_is_mapped_not_duplicated_and_w4b_has_no_dead_key(self):
        bt = _load("bt_v_wy_grid3", "backtest-methods.py")
        by_id = {i["id"]: i for i in _grid()["items"]}
        self.assertEqual(by_id["W-MGMT"]["existing_opts_key"], "mgmt")
        self.assertEqual(by_id["W-MGMT"]["values"], ["none", "be"])
        self.assertIn("mgmt", bt._OPTS_BASE)
        self.assertFalse([k for k in bt._OPTS_BASE if k.startswith("fx_w") and "mgmt" in k])
        w4b = by_id["W4b"]
        self.assertFalse(w4b["implemented"])
        self.assertTrue(w4b.get("note"), "an unimplemented item must say why")
        self.assertNotIn(w4b["key"], bt._OPTS_BASE)     # no registered-but-unread key (A0b)
        self.assertNotIn("W7", {i["id"] for i in _grid()["items"]})


# ------------------------------------------------------------------------------------------------ registration
class Registration(unittest.TestCase):
    def test_defaults_are_the_baseline_in_opts_base_and_opts(self):
        bt = _load("bt_v_wy_reg", "backtest-methods.py")
        for k, v in BASELINE.items():
            self.assertEqual(bt._OPTS_BASE[k], v, k)
            self.assertEqual(bt.OPTS[k], v, k)
        self.assertIsNone(W.PARAMS["fx_w4a_linger_closes"])

    def test_key_is_in_scan_relevant_keys_and_config_opts(self):
        sr = _load("sr_v_wy_reg", "stability-report.py")
        overlay = sr.config_opts(sr.CONFIGS["A"], "range")
        for k, v in BASELINE.items():
            self.assertIn(k, sr._SCAN_RELEVANT_KEYS, k)
            self.assertEqual(overlay[k], v, k)

    def test_scan_cache_key_separates_each_key(self):
        sr = _load("sr_v_wy_cache", "stability-report.py")
        base = sr.config_opts(sr.CONFIGS["A"], "range")
        alt = dict(fx_w_stop="spring_low", fx_w4a_linger_closes=3, fx_w6_window=600, fx_w_spt="VAH", fx_w_touch="on",
                   fx_w_tw=(8, 3))
        k0 = sr._scan_cache_key("XAUUSD", "4H", base, ("wyckoff",))
        seen = {k0}
        for k, v in alt.items():
            k1 = sr._scan_cache_key("XAUUSD", "4H", dict(base, **{k: v}), ("wyckoff",))
            self.assertNotIn(k1, seen, k)
            seen.add(k1)
        # a JSON round trip turns the tuple into a list; the key must still hash and equal the tuple's
        self.assertEqual(sr._scan_cache_key("XAUUSD", "4H", dict(base, fx_w_tw=[8, 3]), ("wyckoff",)),
                         sr._scan_cache_key("XAUUSD", "4H", dict(base, fx_w_tw=(8, 3)), ("wyckoff",)))

    def test_config_snapshot_records_every_key(self):
        bt = _load("bt_v_wy_snap", "backtest-methods.py")
        import snapshot
        cc = snapshot.backtest_config_snapshot(bt, timeframes=["4H"], methods={"WYCKOFF-BOOK"},
                                               market="cfd")["fields"]["custom_constraints"]
        for k, v in BASELINE.items():
            self.assertIn(k, cc, k)
            self.assertEqual(cc[k], v, k)

    def test_live_runner_never_references_a_v_key(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        for k in V_KEYS + ("WY_V_VALUES", "fx_w4b"):
            self.assertNotIn(k, src, k)

    def test_a_value_outside_the_declared_set_is_refused_not_run_as_baseline(self):
        bt = _load("bt_v_wy_valid", "backtest-methods.py")
        for k, bad in (("fx_w_stop", "below"), ("fx_w4a_linger_closes", 5), ("fx_w6_window", 450),
                       ("fx_w_spt", "vah"), ("fx_w_touch", True), ("fx_w_tw", (12, 4))):
            with self.subTest(key=k), mock.patch.dict(bt.OPTS, {k: bad}):
                with self.assertRaises(ValueError):
                    bt._check_wy_v_opts()
        bt._check_wy_v_opts()                                          # the baseline passes
        with mock.patch.dict(bt.OPTS, {"fx_w_tw": [8, 3]}):            # a JSON list is accepted
            bt._check_wy_v_opts()


# ------------------------------------------------------------------------------------------------ gating items
def _rec(side, **kw):
    """A hand-built wyckoff_rules record for `_fires_from` (the W7 tests' pattern). Spring path, reclaim ON the last
    bar (bar 4), volume type 1 -> the book enters at the reclaim. Long: TR 80-110, ceiling 118, VAH 104, Spring low
    85, entry 95. Short (REAL prices, as detect_distributions returns them): TR 90-120, floor 82, VAL 101, VAH 112,
    Upthrust high 125, entry 110."""
    if side == "long":
        r = dict(tr_hi=110.0, tr_lo=80.0, ceiling=118.0, vah=104.0, val=88.0, spring_low=85.0)
    else:
        r = dict(tr_hi=120.0, tr_lo=90.0, ceiling=82.0, vah=112.0, val=101.0, spring_low=125.0)
    r.update(st_sign="neutral", sloped=False, st_pct=0.5, spring=2, reclaim=4, test=None, sos=None, path="spring",
             shakeout=False, abandon=False, sot_too_strong=False, vol_type=1, rec_ratio=1.0, bu=None,
             phase_b_tests={"upper": 2, "lower": 2})
    r.update(kw)
    return r


def _phase_d_rec(side, **kw):
    """Phase-D record whose BU/LPS bar is the last bar: long BU low 100, entry 105; short BU (pullback high) 102,
    entry 95; both with a Spring low (85 / 118) unless `spring_low=None` (the LPS[C] path)."""
    if side == "long":
        r = dict(tr_hi=110.0, tr_lo=80.0, ceiling=110.0, spring_low=85.0, bu=dict(bar=4, low=100.0))
    else:
        r = dict(tr_hi=120.0, tr_lo=80.0, ceiling=80.0, spring_low=118.0, bu=dict(bar=4, low=102.0))
    r.update(st_sign="neutral", sloped=False, st_pct=0.5, spring=2, reclaim=None, test=None, sos=3, path="spring",
             shakeout=True, abandon=False, sot_too_strong=False, vol_type=None,
             phase_b_tests={"upper": 2, "lower": 2})
    r.update(kw)
    return r


CLOSES = {"long": [100.0, 101.0, 102.0, 103.0, 95.0], "short": [100.0, 99.0, 98.0, 97.0, 110.0]}
CLOSES_D = {"long": [100.0, 104.0, 108.0, 112.0, 105.0], "short": [100.0, 96.0, 92.0, 88.0, 95.0]}
TM = ["2024-01-05T0%d:00:00Z" % i for i in range(5)]


class _BtCase(unittest.TestCase):
    def setUp(self):
        self.bt = _load("bt_v_wy_gate", "backtest-methods.py")

    def fires(self, side, recs, closes=None, **opts):
        with mock.patch.dict(self.bt.OPTS, opts):
            return self.bt._fires_from(side, recs, closes or CLOSES[side], TM, sym="XAUUSD", tf="4H")


class WStopBelowTheSpringLow(_BtCase):
    """WMT p271: the stop sits beyond the Spring low. Only the BU/LPS (Phase-D) stop is the V item; the Spring leg's
    stop is already the Spring low."""
    buf = property(lambda self: self.bt.STOP_BUFFER_PCT)

    def test_default_is_the_pullback_low_long_and_short(self):
        (l,) = self.fires("long", [_phase_d_rec("long")], CLOSES_D["long"])
        (s,) = self.fires("short", [_phase_d_rec("short")], CLOSES_D["short"])
        self.assertAlmostEqual(l["stop"], 100.0 * (1 - self.buf))
        self.assertAlmostEqual(s["stop"], 102.0 * (1 + self.buf))
        self.assertEqual(self.fires("long", [_phase_d_rec("long")], CLOSES_D["long"], fx_w_stop="current"), [l])

    def test_spring_low_moves_only_the_stop_long_and_short(self):
        for side, sl, sign in (("long", 85.0, -1), ("short", 118.0, 1)):
            with self.subTest(side=side):
                (off,) = self.fires(side, [_phase_d_rec(side)], CLOSES_D[side])
                (on,) = self.fires(side, [_phase_d_rec(side)], CLOSES_D[side], fx_w_stop="spring_low")
                self.assertAlmostEqual(on["stop"], sl * (1 + sign * self.buf))
                self.assertNotAlmostEqual(on["stop"], off["stop"])
                self.assertEqual({k: v for k, v in on.items() if k != "stop"},
                                 {k: v for k, v in off.items() if k != "stop"})

    def test_a_structure_without_a_spring_keeps_the_bu_stop(self):
        """The LPS[C] path has no Spring low: nothing to move the stop to."""
        for side in ("long", "short"):
            r = _phase_d_rec(side, spring_low=None, path="lps_c", spring=None)
            self.assertEqual(self.fires(side, [r], CLOSES_D[side], fx_w_stop="spring_low"),
                             self.fires(side, [r], CLOSES_D[side]))

    def test_the_spring_leg_stop_is_not_affected(self):
        for side in ("long", "short"):
            self.assertEqual(self.fires(side, [_rec(side)], fx_w_stop="spring_low"), self.fires(side, [_rec(side)]))


class WSptSpringTarget(_BtCase):
    """WA p85 / WMT p273: Spring target = AR (current, faithful to WA p72) | the Phase-B ceiling | the VAH (the VAL
    for a short: the mirror)."""

    def test_default_is_ar_long_and_short(self):
        (l,) = self.fires("long", [_rec("long")]); (s,) = self.fires("short", [_rec("short")])
        self.assertEqual((l["target"], s["target"]), (110.0, 90.0))
        self.assertEqual(self.fires("long", [_rec("long")], fx_w_spt="AR"), [l])

    def test_ceiling_and_vah_change_only_the_target(self):
        expect = {("long", "ceiling"): 118.0, ("long", "VAH"): 104.0, ("short", "ceiling"): 82.0,
                  ("short", "VAH"): 101.0}
        for (side, mode), tgt in expect.items():
            with self.subTest(side=side, mode=mode):
                (off,) = self.fires(side, [_rec(side)])
                (on,) = self.fires(side, [_rec(side)], fx_w_spt=mode)
                self.assertEqual(on["target"], tgt)
                self.assertEqual({k: v for k, v in on.items() if k != "target"},
                                 {k: v for k, v in off.items() if k != "target"})

    def test_a_target_the_entry_has_already_passed_is_not_placeable(self):
        """The existing placeability check applies to the new targets: a VAH below the entry is no trade."""
        self.assertEqual(self.fires("long", [_rec("long", vah=94.0)], fx_w_spt="VAH"), [])
        self.assertEqual(self.fires("short", [_rec("short", val=111.0)], fx_w_spt="VAH"), [])

    def test_the_phase_d_target_is_not_affected(self):
        for side in ("long", "short"):
            self.assertEqual(self.fires(side, [_phase_d_rec(side)], CLOSES_D[side], fx_w_spt="VAH"),
                             self.fires(side, [_phase_d_rec(side)], CLOSES_D[side]))


class WTouchTwoTestsOfEachBorder(_BtCase):
    """advance.md 2.11.2 (WA p154): a Spring counts only after the TR's borders were each tested twice in Phase B (the
    R3b `phase_b_tests`). A sign in the book, not a requirement -- hence a V item, off by default."""

    def test_default_off_ignores_the_counts(self):
        for side in ("long", "short"):
            r = _rec(side, phase_b_tests={"upper": 0, "lower": 0})
            self.assertEqual(len(self.fires(side, [r])), 1)

    def test_on_needs_two_of_each_border_long_and_short(self):
        for side in ("long", "short"):
            for tests, fires in (({"upper": 2, "lower": 2}, 1), ({"upper": 5, "lower": 1}, 0),
                                 ({"upper": 1, "lower": 5}, 0), ({"upper": 0, "lower": 0}, 0),
                                 ({"upper": 3, "lower": 2}, 1)):
                with self.subTest(side=side, tests=tests):
                    self.assertEqual(len(self.fires(side, [_rec(side, phase_b_tests=tests)], fx_w_touch="on")), fires)

    def test_it_also_gates_the_phase_d_leg_of_a_spring_structure_but_not_the_lps_c_path(self):
        for side in ("long", "short"):
            few = {"upper": 1, "lower": 0}
            self.assertEqual(self.fires(side, [_phase_d_rec(side, phase_b_tests=few)], CLOSES_D[side],
                                        fx_w_touch="on"), [])
            lps = _phase_d_rec(side, phase_b_tests=few, path="lps_c", spring=None, spring_low=None)
            self.assertEqual(len(self.fires(side, [lps], CLOSES_D[side], fx_w_touch="on")), 1)


# ------------------------------------------------------------------------------------------------ detection items
class W4aLingeringCloses(unittest.TestCase):
    """WA2-12 / WA p80, p83: a break whose closes linger below the border is a Shakeout, not a Spring. The count is the
    V threshold. Fixture (the W5 one): Spring bar 88 and bar 89 both close below the border (79.95), the reclaim closes
    back inside at bar 90 -> two lingering closes."""

    bars = TW.W5AbandonWithoutTheUnsourcedTwoBarClause._bars()

    def test_default_is_the_v1_typing_and_unchanged_by_none(self):
        v1 = TW.detect(self.bars)
        self.assertEqual(TW.detect(self.bars, fx_w4a_linger_closes=None), v1)
        self.assertEqual([r["shakeout"] for r in v1], [True])

    def test_threshold_two_three_four_long(self):
        got = {n: [r["shakeout"] for r in TW.detect(self.bars, fx_w4a_linger_closes=n)] for n in (2, 3, 4)}
        self.assertEqual(got, {2: [True], 3: [False], 4: [False]})

    def test_threshold_two_three_four_short(self):
        bars = TW.mirror(self.bars)
        self.assertEqual([r["shakeout"] for r in TW.detect_short(bars)], [True])
        got = {n: [r["shakeout"] for r in TW.detect_short(bars, fx_w4a_linger_closes=n)] for n in (2, 3, 4)}
        self.assertEqual(got, {2: [True], 3: [False], 4: [False]})

    def test_only_the_shakeout_flag_differs(self):
        off = TW.detect(self.bars)[0]; on = TW.detect(self.bars, fx_w4a_linger_closes=3)[0]
        self.assertEqual({k for k in off if off[k] != on[k]}, {"shakeout"})

    def test_no_reclaim_is_a_shakeout_at_every_threshold(self):
        bars = TW.base_accumulation() + TW.leg(92, 70, 4, vol=20.0) + TW.leg(70, 68, 2, vol=20.0)
        for n in (None, 2, 3, 4):
            recs = TW.detect(bars, fx_w4a_linger_closes=n)
            self.assertEqual([(r["reclaim"], r["shakeout"]) for r in recs], [(None, True)], n)

    def test_a_break_that_closes_straight_back_inside_is_never_a_shakeout(self):
        bars = TW.base_accumulation() + [(92, 93, 70, 88, 5.0), (88, 90, 86, 89, 10.0)]
        for n in (None, 2, 3, 4):
            self.assertEqual([r["shakeout"] for r in TW.detect(bars, fx_w4a_linger_closes=n)], [False], n)

    def test_a_shakeout_is_not_a_spring_entry(self):
        """`_fires_from` reads the record's flag: the shakeout record is refused, the relabelled one fires."""
        bt = _load("bt_v_wy_w4a", "backtest-methods.py")
        for side, bars, det in (("long", self.bars, TW.detect), ("short", TW.mirror(self.bars), TW.detect_short)):
            with self.subTest(side=side):
                self.assertTrue(det(bars)[0]["shakeout"])
                self.assertFalse(det(bars, fx_w4a_linger_closes=3)[0]["shakeout"])


class WTwTestWindowAndPhaseBSwings(unittest.TestCase):
    """W-TW (project parameters `test_window` = 12 and `min_phase_b_swings` = 2, wyckoff_rules.PARAMS): the grid is the
    cross {12, 8, 20} x {2, 3}. Applied through the per-call copy, `_fx_v_detection_opts()`."""

    @staticmethod
    def _late_test_bars():
        """Spring 88 / reclaim 90, then nine quiet bars above the test zone, then the qualifying Test on bar 100 =
        reclaim + 10: inside a 12- or 20-bar window, outside an 8-bar one."""
        return (TW.base_accumulation() + TW.leg(92, 65, 2, vol=20.0) + [(66, 86, 65, 85.0, 15.0)]
                + [(100, 101, 99, 100, 10.0)] * 9 + [(88, 92, 86, 91, 8.0)])

    def test_test_window_long_and_short(self):
        for name, bars, det in (("long", self._late_test_bars(), TW.detect),
                                ("short", TW.mirror(self._late_test_bars()), TW.detect_short)):
            with self.subTest(side=name):
                got = {w: [r["test"] for r in det(bars, test_window=w)] for w in (12, 8, 20)}
                self.assertEqual(got, {12: [100], 8: [None], 20: [100]})

    def test_phase_b_swings_long_and_short(self):
        bars = TW.W3EarlyBreakIsAlsoAPotentialSpring._bars()      # the break arrives with exactly 2 Phase-B swings
        for name, b, det in (("long", bars, TW.detect), ("short", TW.mirror(bars), TW.detect_short)):
            with self.subTest(side=name):
                two = det(b, min_phase_b_swings=2); three = det(b, min_phase_b_swings=3)
                self.assertEqual([r["phase_b_swings"] for r in two], [2])
                self.assertEqual(three, [])

    def test_the_v_opts_reach_the_detector_through_a_per_call_copy(self):
        bt = _load("bt_v_wy_tw", "backtest-methods.py")
        self.assertEqual(bt._fx_v_detection_opts(), {})                       # baseline: no override at all
        with mock.patch.dict(bt.OPTS, {"fx_w_tw": (8, 3)}):
            self.assertEqual(bt._fx_v_detection_opts(), {"test_window": 8, "min_phase_b_swings": 3})
            wp = bt._wy_params(3)
            self.assertEqual((wp["test_window"], wp["min_phase_b_swings"]), (8, 3))
        with mock.patch.dict(bt.OPTS, {"fx_w_tw": [20, 2], "fx_w4a_linger_closes": 4}):
            self.assertEqual(bt._fx_v_detection_opts(), {"test_window": 20, "min_phase_b_swings": 2,
                                                         "fx_w4a_linger_closes": 4})

    def test_baseline_params_copy_is_exactly_the_v1_copy(self):
        bt = _load("bt_v_wy_tw2", "backtest-methods.py")
        self.assertEqual(bt._wy_params(3), dict(W.PARAMS, spring_max_bars_outside=3, **bt._fx_detection_opts()))
        # Baseline: W1-W5 False (v1); W8 True since owner 2026-10-05 ("bật cho cả setup hiện tại của Wyckoff").
        self.assertEqual(bt._fx_detection_opts(),
                         {k: k == "fx_w8_choch_in_box" for k in bt._FX_WYCKOFF_DETECTION_KEYS})
        self.assertEqual(bt._wy_params(3), dict(W.PARAMS, spring_max_bars_outside=3), "baseline copy == PARAMS")


class WMgmtBreakeven(unittest.TestCase):
    """W-MGMT is the EXISTING `mgmt` knob (WMT p272: "move to entry once price has moved favorably"; the +1R trigger is
    a project parameter). Long and short: a trade that reaches +1R and then returns to the entry is a loss with
    mgmt none and a breakeven with mgmt be."""

    def setUp(self):
        self.bt = _load("bt_v_wy_mgmt", "backtest-methods.py")

    def _walk(self, side, mgmt):
        if side == "long":   # entry 100, stop 90, target 130; +1R = 110, then back through the entry to 90
            H = [105.0, 111.0, 101.0, 95.0]; L = [99.0, 104.0, 99.0, 89.0]; C = [104.0, 108.0, 100.0, 90.0]
            args = ("long", 100.0, 90.0, 130.0)
        else:                # mirror: entry 100, stop 110, target 70
            H = [101.0, 96.0, 101.0, 111.0]; L = [95.0, 89.0, 99.0, 105.0]; C = [96.0, 92.0, 100.0, 110.0]
            args = ("short", 100.0, 110.0, 70.0)
        with mock.patch.dict(self.bt.OPTS, {"mgmt": mgmt}):
            return self.bt.walk(*args, H, L, C, 0, 10)

    def test_none_is_a_loss_be_is_a_breakeven_long_and_short(self):
        for side in ("long", "short"):
            with self.subTest(side=side):
                a = self._walk(side, "none"); b = self._walk(side, "be")
                self.assertEqual((a["outcome"], a["R"]), ("loss", -1.0))
                self.assertEqual((b["outcome"], b["R"]), ("breakeven", 0.0))

    def test_default_is_none(self):
        self.assertEqual(self.bt._OPTS_BASE["mgmt"], "none")


# ------------------------------------------------------------------------------------------------ scan-level items
def _drift(n):
    """n bars oscillating inside the TR (92-106): no new structure, just time."""
    out = []
    for i in range(n):
        f = (i % 10 + 1) / 10
        s, e = (106, 92) if (i // 10) % 2 == 0 else (92, 106)
        c = s + (e - s) * f; o = s + (e - s) * (i % 10) / 10
        out.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c, 10.0))
    return out


def _w6_bars(spring_vol=5.0):
    """601 bars: the accumulation's SC/AR/ST/CHoBEV sit in bars 0-87, 511 bars of range follow, and the type-1 Spring
    that closes straight back inside is bar 599 = the last bar of the 600-bar window [0, 600). A 300-bar window never
    sees the SC, so only the 600-bar window can call the structure. `spring_vol` 5 is a low-volume (type 1) Spring for
    a long; a short needs the Upthrust table's 'volume increases at the touch' (ratio >= 1.0), so its mirror uses 14."""
    return TW.base_accumulation() + _drift(511) + [(92, 93, 70, 88, spring_vol)] + [(88, 90, 86, 89, 10.0)]


def _candles(bars, hours=4):
    t0 = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
    return [dict(time=(t0 + datetime.timedelta(hours=hours * i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 open=b[0], high=b[1], low=b[2], close=b[3], volume=b[4]) for i, b in enumerate(bars)]


class W6StructureWindow(unittest.TestCase):
    """W6 (fidelity 3.3 B1, project): the bars one WYCKOFF-BOOK read sees, 300 (WYCKOFF_WINDOW, what the live runner
    reads) or 600. Decided TOGETHER with the ICT SCAN_WINDOW (docs/architecture: automation.py SCAN_WINDOW): this is only
    the Wyckoff side; the coupling is the fund-search agent's / owner's decision, not a rule implemented here."""

    def setUp(self):
        self.bt = _load("bt_v_wy_w6", "backtest-methods.py")

    def scan(self, bars, **opts):
        c = _candles(bars)
        with mock.patch.object(self.bt, "load", lambda s, t: (c, None)), \
                mock.patch.dict(self.bt.OPTS, dict({"methods": ("WYCKOFF",)}, **opts)), \
                mock.patch.dict(self.bt._WY_CANDIDATES, clear=True):
            return self.bt.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",))["trades"].get("WYCKOFF-BOOK", [])

    def test_the_default_window_is_the_live_one(self):
        self.assertEqual(self.bt.OPTS["fx_w6_window"], 300)
        self.assertEqual(self.bt.WYCKOFF_WINDOW, 300)

    def test_a_structure_older_than_300_bars_is_seen_only_by_600_long_and_short(self):
        for side, bars in (("long", _w6_bars()), ("short", TW.mirror(_w6_bars(14.0)))):
            with self.subTest(side=side):
                v1 = self.scan(bars)
                self.assertEqual(v1, [])
                self.assertEqual(self.scan(bars, fx_w6_window=300), v1)
                wide = self.scan(bars, fx_w6_window=600)
                self.assertEqual([t["side"] for t in wide], [side])

    def test_window_longer_than_the_history_is_refused_not_an_empty_result(self):
        """Review round 1 (I3): 600 on a 400-bar series must raise, while the default window never does."""
        short = _w6_bars()[:400]
        with self.assertRaises(ValueError):
            self.scan(short, fx_w6_window=600)
        self.scan(short)                                  # baseline: no refusal (v1 behaviour)

    def test_the_trade_record_carries_volume_kind_the_split_seam_for_fund_search(self):
        """Plan section 6 item 4: every WYCKOFF-BOOK trade already carries `volume_kind` (backtest-methods.py, the
        `base` trade dict). No new code was needed; this pins the seam a per-volume_kind split will read. XAUUSD is a
        tick-volume CFD (scripts/instruments.py is_tick_volume)."""
        (t,) = self.scan(_w6_bars(), fx_w6_window=600)
        self.assertTrue(self.bt._I.is_tick_volume("XAUUSD"))
        self.assertEqual(t["volume_kind"], "tick")

    def test_explicit_baseline_values_reproduce_the_default_trades_exactly(self):
        for bars in (_w6_bars(), TW.mirror(_w6_bars(14.0))):
            self.assertEqual(self.scan(bars, **BASELINE), self.scan(bars))
            self.assertEqual(self.scan(bars, **dict(BASELINE, fx_w6_window=600)), self.scan(bars, fx_w6_window=600))


class DetectionKeysSeparateTheCaches(unittest.TestCase):
    """The keys that change detection (or the window) must widen `_WY_CANDIDATES`' key and `_HTF_TR_CACHE`'s key:
    two configs differing only in one of them never share a cached detection, a repeat of either is a hit."""

    def setUp(self):
        self.bt = _load("bt_v_wy_ck", "backtest-methods.py")
        bars = TW.W5AbandonWithoutTheUnsourcedTwoBarClause._bars()
        self.c = _candles(bars, hours=1)
        for p in (mock.patch.object(self.bt, "load", lambda s, t: (self.c, None)),
                  mock.patch.object(self.bt, "WYCKOFF_WINDOW", 60),
                  mock.patch.dict(self.bt.OPTS, {"methods": ("WYCKOFF",)}),
                  mock.patch.dict(self.bt._WY_CANDIDATES, clear=True),
                  mock.patch.dict(self.bt.WY_V_VALUES, {"fx_w6_window": (300, 40)})):
            p.start(); self.addCleanup(p.stop)
        self.calls = []
        real = self.bt._structures.wyckoff_records

        def spy(*a, **k):
            self.calls.append(k.get("P"))
            return real(*a, **k)
        p = mock.patch.object(self.bt._structures, "wyckoff_records", spy)
        p.start(); self.addCleanup(p.stop)

    def _scan(self):
        self.bt.scan("XAUUSD", "15m", only=("WYCKOFF-BOOK",))

    def test_each_key_re_detects_once_and_repeats_hit_the_cache(self):
        for k, v, check in (("fx_w4a_linger_closes", 3, lambda P: P["fx_w4a_linger_closes"] == 3),
                            ("fx_w_tw", (8, 3), lambda P: (P["test_window"], P["min_phase_b_swings"]) == (8, 3)),
                            ("fx_w6_window", 40, None)):
            with self.subTest(key=k):
                self.bt._WY_CANDIDATES.clear(); del self.calls[:]
                self._scan(); n_off = len(self.calls)
                self.assertGreater(n_off, 0)
                with mock.patch.dict(self.bt.OPTS, {k: v}):
                    self._scan(); n_on = len(self.calls)
                    self._scan()
                self._scan()
                self.assertGreater(n_on, n_off, k)              # the key change re-detected
                self.assertEqual(len(self.calls), n_on, k)      # and both repeats were cache hits
                if check:
                    self.assertTrue(check(self.calls[-1]), k)
                    self.assertIsNone(self.calls[0]["fx_w4a_linger_closes"])   # the baseline copy: v1 default, no override
                    self.assertEqual(self.calls[0]["test_window"], 12)

    def test_the_w6_window_size_changes_which_windows_are_detected(self):
        self._scan(); n60 = len(self.calls)                     # baseline 300 -> the mocked WYCKOFF_WINDOW (60)
        with mock.patch.dict(self.bt.OPTS, {"fx_w6_window": 40}):
            self._scan()
        n40 = len(self.calls) - n60
        n = len(self.c)
        self.assertEqual((n60, n40), (2 * (n - 60 + 1), 2 * (n - 40 + 1)))

    def test_the_w7_htf_cache_is_keyed_on_the_v_detection_keys_and_detects_under_them(self):
        bt = self.bt
        bt._HTF_TR_CACHE.clear(); del self.calls[:]
        htf = TW.W7HtfTargetIsBuiltButNotAdopted._htf_candles(TW._HtfFixture.bars())
        with mock.patch.object(bt, "load", lambda s, t: (htf, None)):
            ask = lambda: bt._htf_wyckoff_target("XAUUSD", "15m", "long", "2024-01-31T00:00:00Z")   # noqa: E731
            ask(); n0 = len(self.calls)
            for k, v, check in (("fx_w4a_linger_closes", 2, lambda P: P["fx_w4a_linger_closes"] == 2),
                                ("fx_w_tw", (20, 3), lambda P: (P["test_window"], P["min_phase_b_swings"]) == (20, 3))):
                with self.subTest(key=k), mock.patch.dict(bt.OPTS, {k: v}):
                    before = len(self.calls)
                    ask(); ask()
                    self.assertEqual(len(self.calls), before + 1, k)
                    self.assertTrue(check(self.calls[-1]), k)
            self.assertGreater(n0, 0)


class ParamsAreNeverWritten(unittest.TestCase):
    """The global wyckoff_rules.PARAMS must be identical after any call, including one that raises."""

    def setUp(self):
        self.bt = _load("bt_v_wy_params", "backtest-methods.py")
        self.before = copy.deepcopy(W.PARAMS)
        self.addCleanup(lambda: self.assertEqual(W.PARAMS, self.before))
        self.everything = dict(fx_w_stop="spring_low", fx_w4a_linger_closes=3, fx_w6_window=600, fx_w_spt="VAH",
                               fx_w_touch="on", fx_w_tw=(8, 3), fx_w1_tr_low_st=True)

    def test_scan_and_wyckoff_fires_leave_params_alone(self):
        bars = _w6_bars()
        c = _candles(bars)
        with mock.patch.object(self.bt, "load", lambda s, t: (c, None)), \
                mock.patch.dict(self.bt.OPTS, dict({"methods": ("WYCKOFF",)}, **self.everything)), \
                mock.patch.dict(self.bt._WY_CANDIDATES, clear=True):
            self.bt.scan("XAUUSD", "4H", only=("WYCKOFF-BOOK",))
            self.bt.wyckoff_fires("long", c[-300:], "4H", "XAUUSD")
        self.assertEqual(W.PARAMS, self.before)

    def test_params_unchanged_when_detection_raises(self):
        with mock.patch.dict(self.bt.OPTS, self.everything), \
                mock.patch.object(self.bt._structures, "wyckoff_records", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.bt._wyckoff_candidates("long", [1.0] * 20, [1.0] * 20, [1.0] * 20, [1.0] * 20, [1.0] * 20, "4H", "XAUUSD")
        self.assertEqual(W.PARAMS, self.before)
        self.assertEqual(W.PARAMS["test_window"], 12)
        self.assertIsNone(W.PARAMS["fx_w4a_linger_closes"])

    def test_the_params_copy_is_a_distinct_dict(self):
        with mock.patch.dict(self.bt.OPTS, self.everything):
            wp = self.bt._wy_params(3)
        self.assertIsNot(wp, W.PARAMS)
        self.assertEqual((wp["test_window"], wp["min_phase_b_swings"], wp["fx_w4a_linger_closes"]), (8, 3, 3))
        self.assertEqual(W.PARAMS, self.before)


class DefaultsAreV1(unittest.TestCase):
    """Every key at its default is byte-identical to the key being absent -- on the gate, the detector and the scan."""

    def test_gate_output_is_identical_with_the_defaults_or_explicit_baseline_values(self):
        bt = _load("bt_v_wy_v1", "backtest-methods.py")
        for side in ("long", "short"):
            for recs, closes in (([_rec(side)], CLOSES[side]), ([_phase_d_rec(side)], CLOSES_D[side])):
                with mock.patch.dict(bt.OPTS, BASELINE):
                    explicit = bt._fires_from(side, recs, closes, TM, sym="XAUUSD", tf="4H")
                default = bt._fires_from(side, recs, closes, TM, sym="XAUUSD", tf="4H")
                self.assertEqual(len(default), 1)
                self.assertEqual(explicit, default)

    def test_detection_with_the_baseline_tw_is_identical_to_v1(self):
        for bars in (TW.base_accumulation(), TW.W5AbandonWithoutTheUnsourcedTwoBarClause._bars()):
            self.assertEqual(TW.detect(bars, test_window=12, min_phase_b_swings=2, fx_w4a_linger_closes=None),
                             TW.detect(bars))


if __name__ == "__main__":
    unittest.main()
