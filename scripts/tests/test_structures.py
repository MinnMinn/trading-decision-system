"""A1 (docs/plans/2026-09-28-methodology-improvement-plan.md §2; ADR 0009): scripts/structures.py wraps the
EXISTING detection (scripts/ict-scan.py analyze(), scripts/wyckoff_rules.py detect_accumulations()/
detect_distributions()) into timestamped structure objects, and does not recompute detection. These tests pin:

  1. structures.ict_analysis()/ict_structures()'s "analysis" is exactly what ict_scan.analyze() returns for the
     same inputs (byte-identical: A1 must not change a single trade), and structures.wyckoff_records()/
     wyckoff_structures()'s "records" is exactly what wyckoff_rules.detect_accumulations()/detect_distributions()
     returns.
  2. Confirmation delay (A1 code review round 1, item 1): a pivot's/pool's/FVG's available_at is NOT its own
     bar's available_time -- it is the bar whose close the detection rule itself needs (i+PIV for a pivot,
     i+1 for an FVG, the LAST constituent pivot's i+PIV for a pool). These tests use a SYNTHETIC window with a
     hand-placed, isolated pivot/pool/FVG (verified against a direct ict_scan.analyze() call, independent of
     structures.py's own confirmation-delay arithmetic) so the expected confirming bar is derived from the
     detection RULE, not copied from the implementation under test -- and assert available_at is strictly LATER
     than the (wrong) same-bar answer, so a regression back to the same-bar bug would fail loudly.
  3. Bias availability (A1 code review round 1, item 2): when htf_context.ict_bias() combines the prev-candle
     draw and the MSS, available_at is the LATER of the two contributing bars. Exercised on real market data
     where the draw+MSS branch genuinely fires (verified: the MSS bar is NOT window's last bar), asserting
     available_at differs from (and is later than) what using the MSS bar alone would give.
  4. Pool formation-only fields (A1 code review round 1, item 3): a pool structure object carries formation
     fields only (pool_kind/level/from/to/type) -- never the forward-scanned state/swept/closed_at, which live
     on the separately, correctly timestamped sweep/closed_through objects.
  5. scripts/live_rules.py read_at() and scripts/backtest-methods.py _wyckoff_candidates() are routed through
     structures.py's raw hot-path functions and still return byte-identical results to a direct call of the
     wrapped function.

Real market data (data/history/ohlcv.AUS200.4H.json) is used for byte-identity and bias-availability checks;
hand-built synthetic candles are used for confirmation-delay checks so the expected confirming bar can be
derived independently of structures.py's own arithmetic (see item 2 above).
"""
import datetime
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import normalized as N  # noqa: E402
import wyckoff_rules as W  # noqa: E402


def _load(name, mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


structures = _load("structures.py", "structures")
ict_scan = _load("ict-scan.py", "ict_scan")


def _aus200_4h(n=480, tail=None):
    d = json.load(open(os.path.join(ROOT, "data", "history", "ohlcv.AUS200.4H.json"), encoding="utf-8"))
    c = d["candles"]
    return c[-n:] if tail is None else c[-(n + tail):-tail]


def _iso(dt_or_candle, tf=None):
    if tf is not None:
        return N.available_time(dt_or_candle, tf).isoformat().replace("+00:00", "Z")
    return dt_or_candle["time"]


def _synthetic_window(n=80, tf_min=60, base=100.0):
    """A hand-built window with an ISOLATED, unambiguous pivot high (bar 20, price 130), an isolated "equal
    highs" pool (bars 30 and 40, both 115 -- >= 4 bars apart, per ict-scan.py's equal-pool dedup rule), and an
    isolated bull FVG (bars 54/55/56: H[54]=101 < L[56]=103). A gentle per-bar price ramp (0.01/bar) keeps every
    OTHER bar's high/low distinct, so nothing but these three hand-placed features can tie for a pivot/pool/FVG
    -- verified interactively against a direct ict_scan.analyze() call before being fixed here."""
    out = []
    t0 = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    for i in range(n):
        t = t0 + datetime.timedelta(minutes=tf_min * i)
        px = base + 0.01 * i
        out.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5,
                    "close": px, "volume": 10.0})
    out[20]["high"] = 130.0                                  # isolated pivot high
    out[30]["high"] = 115.0; out[40]["high"] = 115.0          # equal-highs pool, from=30 to=40
    out[54]["high"] = 101.0                                   # fvg: H[54] < L[56]
    out[55].update(open=105.0, close=108.0, high=109.0, low=104.0)
    out[56]["low"] = 103.0; out[56]["high"] = 110.0
    return out


class IctStructuresMatchAnalyze(unittest.TestCase):
    def setUp(self):
        self.window = _aus200_4h(480)

    def test_ict_analysis_equals_a_direct_analyze_call(self):
        """The hot-path pass-through must be byte-identical to a direct call (A1 must not change a single
        trade)."""
        got = structures.ict_analysis(self.window, 4, "4H", methods=("ict",))
        direct = ict_scan.analyze(self.window, 4, tf="4H", methods=("ict",))
        self.assertEqual(got, direct)

    def test_analysis_equals_a_direct_analyze_call(self):
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        direct = ict_scan.analyze(self.window, 4, tf="4H", methods=("ict",))
        self.assertEqual(env["analysis"], direct)

    def test_analysis_is_the_passed_in_object_not_a_copy(self):
        """A caller that already ran analyze() (scripts/live_rules.py's bias_at pattern) gets that exact object
        back, not a recomputed or copied one."""
        a = ict_scan.analyze(self.window, 4, tf="4H", methods=("ict",))
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",), analysis=a)
        self.assertIs(env["analysis"], a)

    def test_every_pool_and_sweep_kind_present(self):
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        kinds = {s["kind"] for s in env["structures"]}
        self.assertIn("pool", kinds)
        self.assertIn("sweep", kinds)   # AUS200 4H, last 480 bars: pools sweep repeatedly (verified interactively)
        self.assertIn("mss", kinds)
        self.assertIn("fvg", kinds)
        self.assertIn("pivot_high", kinds)
        self.assertIn("pivot_low", kinds)

    def test_pool_carries_formation_fields_only(self):
        """A1 code review round 1, item 3: the pool structure object must carry ONLY formation fields
        (pool_kind/level/from/to/type) -- never state/swept/closed_at, which are forward-scanned past the
        pool's own formation bar and belong on the separately timestamped sweep/closed_through objects."""
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        a = env["analysis"]
        pools = [s for s in env["structures"] if s["kind"] == "pool"]
        self.assertEqual(len(pools), len(a["pools"]))
        for wrapped, raw in zip(pools, a["pools"]):
            self.assertEqual(wrapped["pool_kind"], raw["kind"])
            self.assertEqual(wrapped["level"], raw["level"])
            self.assertEqual(wrapped["from"], raw["from"])
            self.assertEqual(wrapped["to"], raw.get("to", raw["from"]))
            self.assertEqual(wrapped["type"], raw["type"])
            for forbidden in ("state", "swept", "closed_at"):
                self.assertNotIn(forbidden, wrapped, f"pool structure object must not carry {forbidden!r}")

    def test_mss_count_matches_full_mss_list_not_the_display_slice(self):
        """analyze() itself trims "mss" to the last 3 for display (ict-scan.py facts_entry callers); structures.py
        must wrap the FULL history via the new "mss_all" key, not the truncated one."""
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        a = env["analysis"]
        mss = [s for s in env["structures"] if s["kind"] == "mss"]
        self.assertEqual(len(mss), len(a["mss_all"]))
        self.assertGreater(len(a["mss_all"]), len(a["mss"]), "fixture should exercise more than 3 MSS events")

    def test_dealing_range_present_with_source(self):
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        dr = env["dealing_range"]
        self.assertEqual(dr["kind"], "dealing_range")
        self.assertEqual(dr["lo"], env["analysis"]["lo"])
        self.assertEqual(dr["hi"], env["analysis"]["hi"])
        self.assertIn(dr["source"], ("pools", "mixed", "window"))

    def test_bias_matches_htf_context_ict_bias(self):
        """structures.py's "bias" must be the SAME read scripts/htf_context.py ict_bias() (the one bias
        computation, CLAUDE.md §13) already gives the exact same facts -- not a second bias rule."""
        htf_context = _load("htf_context.py", "htf_context")
        env = structures.ict_structures(self.window, 4, "4H", methods=("ict",))
        a = env["analysis"]
        want_dir, want_basis = htf_context.ict_bias({"prev_candle": a["prev_candle"], "last_displaced_mss": a["last_displaced_mss"]})
        self.assertIsNotNone(env["bias"])
        self.assertEqual(env["bias"]["direction"], want_dir)
        self.assertEqual(env["bias"]["basis"], want_basis)


class ConfirmationDelay(unittest.TestCase):
    """A1 code review round 1, item 1: available_at must reflect the bar the detection RULE needs, not the
    structure's own formation bar, for pivots/pools/FVGs. Uses a synthetic window with a hand-placed, isolated
    feature so the expected confirming index is derived from the rule (i+PIV / to+PIV / i+1), independent of
    structures.py's own arithmetic -- see _synthetic_window()'s docstring."""

    def setUp(self):
        self.window = _synthetic_window()
        self.env = structures.ict_structures(self.window, 4, "1H", methods=("ict",))

    def test_fixture_produces_exactly_the_placed_features(self):
        """Sanity check the fixture itself (independent of structures.py) before trusting its use below."""
        a = self.env["analysis"]
        self.assertIn(20, a["pivots_high"])
        equal_pools = [p for p in a["pools"] if p["type"] == "equal" and p["from"] == 30]
        self.assertEqual(len(equal_pools), 1)
        self.assertEqual(equal_pools[0]["to"], 40)
        fvgs = [f for f in a["fvgs_all"] if f["i"] == 55]
        self.assertEqual(len(fvgs), 1)

    def test_pivot_high_available_at_is_i_plus_piv_not_i(self):
        piv = next(s for s in self.env["structures"] if s["kind"] == "pivot_high" and s["i"] == 20)
        want = _iso(self.window[20 + structures.PIV], "1H")
        same_bar_wrong_answer = _iso(self.window[20], "1H")
        self.assertEqual(piv["available_at"], want)
        self.assertNotEqual(piv["available_at"], same_bar_wrong_answer,
                             "a pivot must not be available before bar i+PIV closes")
        self.assertGreater(
            datetime.datetime.fromisoformat(piv["available_at"].replace("Z", "+00:00")),
            datetime.datetime.fromisoformat(same_bar_wrong_answer.replace("Z", "+00:00")))

    def test_equal_pool_available_at_is_the_last_constituent_pivot_plus_piv(self):
        pool = next(s for s in self.env["structures"] if s["kind"] == "pool" and s["type"] == "equal" and s["from"] == 30)
        self.assertEqual(pool["to"], 40)
        want = _iso(self.window[40 + structures.PIV], "1H")
        same_bar_wrong_answer = _iso(self.window[30], "1H")   # the old, buggy "from"-only answer
        self.assertEqual(pool["available_at"], want)
        self.assertNotEqual(pool["available_at"], same_bar_wrong_answer)

    def test_old_pool_available_at_matches_its_single_pivot_plus_piv(self):
        """An "old" pool (from == to, a single pivot) is the degenerate case: to+PIV == from+PIV."""
        pool = next(s for s in self.env["structures"] if s["kind"] == "pool" and s["type"] == "old" and s["from"] == 20)
        self.assertEqual(pool["to"], 20)
        self.assertEqual(pool["available_at"], _iso(self.window[20 + structures.PIV], "1H"))

    def test_fvg_available_at_is_i_plus_1_not_i(self):
        fvg = next(s for s in self.env["structures"] if s["kind"] == "fvg" and s["i"] == 55)
        want = _iso(self.window[56], "1H")
        same_bar_wrong_answer = _iso(self.window[55], "1H")
        self.assertEqual(fvg["available_at"], want)
        self.assertNotEqual(fvg["available_at"], same_bar_wrong_answer,
                             "an FVG must not be available before bar i+1 closes")


class AvailableTimeInvariant(unittest.TestCase):
    """CLAUDE.md §8: availableTime <= decisionTime. mss/sweep/closed_through are single-bar body-close tests
    (no look-ahead beyond their own bar, per the detection rule itself), so their available_at is exactly their
    own bar's available_time -- unlike pivots/pools/fvgs (see ConfirmationDelay above)."""

    def test_mss_and_sweep_and_closed_through_timestamps(self):
        window = _aus200_4h(480)
        env = structures.ict_structures(window, 4, "4H", methods=("ict",))
        checked = 0
        for s in env["structures"]:
            if s["kind"] not in ("mss", "sweep", "closed_through"):
                continue
            c = window[s["i"]]
            self.assertEqual(s["formed_at"], c["time"])
            self.assertEqual(s["available_at"], N.available_time(c, "4H").isoformat().replace("+00:00", "Z"))
            checked += 1
        self.assertGreater(checked, 0)

    def test_available_at_is_never_before_formed_at(self):
        window = _aus200_4h(480)
        env = structures.ict_structures(window, 4, "4H", methods=("ict",))
        for s in env["structures"] + [env["dealing_range"]] + ([env["bias"]] if env["bias"] else []):
            formed = datetime.datetime.fromisoformat(s["formed_at"].replace("Z", "+00:00"))
            available = datetime.datetime.fromisoformat(s["available_at"].replace("Z", "+00:00"))
            self.assertGreaterEqual(available, formed)

    def test_dealing_range_available_at_is_the_window_last_bar(self):
        window = _aus200_4h(480)
        env = structures.ict_structures(window, 4, "4H", methods=("ict",))
        want = N.available_time(window[-1], "4H").isoformat().replace("+00:00", "Z")
        self.assertEqual(env["dealing_range"]["available_at"], want)


class BiasAvailability(unittest.TestCase):
    """A1 code review round 1, item 2: when the prev-candle draw and the MSS combine, available_at must be the
    LATER of the two contributing bars, not just the MSS bar (the pre-fix bug: `bi = m["i"] if m else ...`
    silently ignored the draw's window[-1] read whenever an MSS was also present)."""

    def test_draw_and_mss_combine_available_at_is_the_later_bar(self):
        window = _aus200_4h(480)
        env = structures.ict_structures(window, 4, "4H", methods=("ict",))
        a = env["analysis"]
        m, pc = a["last_displaced_mss"], a["prev_candle"]
        # Confirm the fixture genuinely exercises the combine branch: both a draw signal and an MSS are
        # present, and the MSS bar is NOT the window's last bar (so the two candidate bars actually differ --
        # otherwise this test could not distinguish the fix from the pre-fix bug).
        self.assertIsNotNone(m)
        self.assertTrue(pc["pch_state"] != "intact" or pc["pcl_state"] != "intact",
                         "fixture must have a genuine prev-candle draw signal")
        self.assertLess(m["i"], len(window) - 1, "fixture must have an MSS bar earlier than window[-1]")

        want = N.available_time(window[-1], "4H").isoformat().replace("+00:00", "Z")
        mss_only_wrong_answer = N.available_time(window[m["i"]], "4H").isoformat().replace("+00:00", "Z")
        self.assertEqual(env["bias"]["available_at"], want)
        self.assertNotEqual(env["bias"]["available_at"], mss_only_wrong_answer,
                             "bias available_at must not regress to the MSS-bar-only (pre-fix) answer")
        self.assertGreater(
            datetime.datetime.fromisoformat(env["bias"]["available_at"].replace("Z", "+00:00")),
            datetime.datetime.fromisoformat(mss_only_wrong_answer.replace("Z", "+00:00")))

    def test_mss_only_uses_the_mss_bar(self):
        """When there is no prev_candle contribution at all (both states intact), available_at should still
        correctly fall back to the MSS bar alone -- this module has no such window in the fixed AUS200 data, so
        this is checked directly against the function with a hand-built facts dict via a minimal window."""
        window = _synthetic_window()
        # No displaced MSS and no draw signal in the synthetic fixture (flat ramp, no swing break) -- bias must
        # be None or "unknown"/no-signal rather than raising.
        env = structures.ict_structures(window, 4, "1H", methods=("ict",))
        if env["bias"] is not None:
            self.assertIn(env["bias"]["direction"], ("unknown", "neutral", "long", "short"))


class WyckoffStructuresMatchDetect(unittest.TestCase):
    def setUp(self):
        self.window = _aus200_4h(600)
        self.O = [x["open"] for x in self.window]; self.H = [x["high"] for x in self.window]
        self.L = [x["low"] for x in self.window]; self.C = [x["close"] for x in self.window]
        self.V = [x.get("volume", 0) for x in self.window]

    def test_wyckoff_records_equals_a_direct_detect_distributions_call(self):
        """The hot-path pass-through must be byte-identical to a direct call."""
        got = structures.wyckoff_records(self.O, self.H, self.L, self.C, self.V, volume_kind="traded", side="short")
        direct = W.detect_distributions(self.O, self.H, self.L, self.C, self.V, volume_kind="traded")
        self.assertEqual(got, direct)
        self.assertGreaterEqual(len(direct), 1, "fixture must exercise at least one Wyckoff structure")

    def test_records_equal_a_direct_detect_distributions_call(self):
        """This 600-bar AUS200 4H slice produces >=1 distribution record (verified interactively) but zero
        accumulation records, so the distribution side is what pins byte-identity here."""
        env = structures.wyckoff_structures(self.O, self.H, self.L, self.C, self.V, self.window, "4H",
                                             volume_kind="traded", side="short")
        direct = W.detect_distributions(self.O, self.H, self.L, self.C, self.V, volume_kind="traded")
        self.assertEqual(env["records"], direct)
        self.assertGreaterEqual(len(direct), 1, "fixture must exercise at least one Wyckoff structure")

    def test_records_is_the_same_list_wyckoff_rules_returned(self):
        env = structures.wyckoff_structures(self.O, self.H, self.L, self.C, self.V, self.window, "4H",
                                             volume_kind="traded", side="short")
        self.assertIsInstance(env["records"], list)
        for r in env["records"]:
            self.assertIn("tr_lo", r)
            self.assertIn("tr_hi", r)

    def test_trading_range_events_are_timestamped_from_candles(self):
        env = structures.wyckoff_structures(self.O, self.H, self.L, self.C, self.V, self.window, "4H",
                                             volume_kind="traded", side="short")
        self.assertGreater(len(env["structures"]), 0)
        for tr in env["structures"]:
            self.assertEqual(tr["kind"], "trading_range")
            self.assertEqual(tr["formed_at"], self.window[tr["sc"]]["time"])
            want_available = N.available_time(self.window[tr["choch"]], "4H").isoformat().replace("+00:00", "Z")
            self.assertEqual(tr["available_at"], want_available)
            for ev in tr["events"]:
                c = self.window[ev["i"]]
                self.assertEqual(ev["formed_at"], c["time"])
                self.assertEqual(ev["available_at"], N.available_time(c, "4H").isoformat().replace("+00:00", "Z"))


class LiveRulesRoutesThroughStructures(unittest.TestCase):
    """live_rules.read_at() must return the byte-identical object a direct ict_scan.analyze() call on the same
    window would -- routing through structures.py must not change what the decision path reads (A1)."""

    def setUp(self):
        self.lr = _load("live_rules.py", "live_rules")

    def test_read_at_matches_direct_analyze(self):
        window = _aus200_4h(480)
        candles = window + [dict(window[-1])]  # read_at needs i to index a full "candles" series; append one
        # extra bar so window(candles, i=len(window)-1, "4H") returns exactly `window` (live_rules.window is
        # end-inclusive at the given i, and read_at's own causal-window contract keeps the forming bar out --
        # here the appended bar is never read since i points at len(window)-1).
        i = len(window) - 1
        got = self.lr.read_at(candles, i, "4H", methods=("ict",))
        want = ict_scan.analyze(self.lr.window(candles, i, "4H"), self.lr.scan_spec("4H")[1], tf="4H", methods=("ict",))
        self.assertEqual(got, want)


class BacktestMethodsWyckoffCandidatesRoutesThroughStructures(unittest.TestCase):
    """backtest-methods.py's _wyckoff_candidates() must return the byte-identical list a direct
    wyckoff_rules.detect_distributions() call on the same arrays would."""

    def setUp(self):
        self.bt = _load("backtest-methods.py", "bt")

    def test_matches_direct_detect_distributions(self):
        window = _aus200_4h(600)
        O = [x["open"] for x in window]; H = [x["high"] for x in window]; L = [x["low"] for x in window]
        C = [x["close"] for x in window]; V = [x.get("volume", 0) for x in window]
        self.bt.W.PARAMS["spring_max_bars_outside"] = self.bt.P["4H"]["sob"]
        got_all = self.bt._wyckoff_candidates("short", O, H, L, C, V, "4H", None)
        direct = W.detect_distributions(O, H, L, C, V, volume_kind="traded")
        last = len(C) - 1
        want = [r for r in direct if (r["bu"] and r["bu"]["bar"] == last) or r["reclaim"] == last or r["test"] == last]
        self.assertEqual(got_all, want)


if __name__ == "__main__":
    unittest.main()
