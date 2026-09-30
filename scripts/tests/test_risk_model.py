"""CLAUDE.md §34 -- the risk model: fees, slippage, exposure, and refusing to guess.

§34 lists eleven inputs a risk calculation must consider. Before 2026-09-18 the live path considered six.
The two that mattered most were missing in opposite ways:

  * **Fees reached no live sizing path at all**, while the backtest had charged them since it was written --
    and the 3R floor the live path enforces was MEASURED net of them (analysis-params.json's own basis line:
    "fee 0.05 %/side"). A gross-R number compared to a net-R floor is a floor that admits trades the evidence
    rejected, and the gap grows as the stop tightens. That is the defect most of this file is about.
  * **Slippage was absent in a way that read as zero.** It is now `null` and travels as UNKNOWN, so a net R:R
    is explicitly an upper bound.

The third theme is refusal. `min_notional()` used to swallow every exception and return a literal 50.0 -- a
number no venue published -- to decide whether a real order was big enough to send.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import risk_model as RM  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", filename))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


_SR = _load("stability_report", "stability-report.py")   # THE config table (side + management + htf)
_RS = _load("rank_setups", "rank-setups.py")             # the ranker, which must not keep a second copy
import providers as _P  # noqa: E402


class CostsAreDeclaredNotGuessed(unittest.TestCase):
    def test_both_venues_declare_a_maker_and_a_taker_fee(self):
        for venue in ("futures", "mt5"):
            for ot in RM.ORDER_TYPES:
                with self.subTest(venue=venue, order_type=ot):
                    c = RM.costs(venue, ot)
                    self.assertIsInstance(c["fee_pct_per_side"], float)
                    self.assertGreaterEqual(c["fee_pct_per_side"], 0)

    def test_an_unknown_venue_refuses(self):
        with self.assertRaises(RM.RiskRefused) as cm:
            RM.costs("kraken", "taker")
        self.assertIn("kraken", str(cm.exception))

    def test_an_unknown_order_type_refuses(self):
        """A post-only GTX limit pays maker and a market order pays taker; guessing mis-prices the trade."""
        with self.assertRaises(RM.RiskRefused):
            RM.costs("futures", "whatever")

    def test_a_config_with_no_costs_block_refuses(self):
        with self.assertRaises(RM.RiskRefused) as cm:
            RM.costs("futures", "taker", cfg={"max_risk_pct": 0.01})
        self.assertIn("no `costs`", str(cm.exception))

    def test_a_non_numeric_fee_refuses(self):
        bad = {"costs": {"futures": {"taker_pct_per_side": "0.05%"}}}
        with self.assertRaises(RM.RiskRefused):
            RM.costs("futures", "taker", cfg=bad)


class SlippageIsUnknownNotZero(unittest.TestCase):
    def test_the_registry_declares_it_null_on_purpose(self):
        cfg = RM._config()
        self.assertIn("slippage_pct", cfg["costs"])
        self.assertIsNone(cfg["costs"]["slippage_pct"])

    def test_every_net_figure_says_it_is_an_upper_bound(self):
        r = RM.net_r(100.0, 99.0, 110.0, "futures", "maker")
        self.assertEqual(r["slippage"], RM.UNKNOWN)
        self.assertTrue(r["net_is_upper_bound"])

    def test_a_modelled_slippage_would_flip_that_flag(self):
        """Pinning the mechanism, so filling the number in later is a config edit and not a code change."""
        cfg = dict(RM._config())
        cfg["costs"] = dict(cfg["costs"], slippage_pct=0.0001)
        r = RM.net_r(100.0, 99.0, 110.0, "futures", "maker", cfg=cfg)
        self.assertEqual(r["slippage"], "MODELLED")
        self.assertFalse(r["net_is_upper_bound"])

    def test_the_slippage_finding_does_not_block_a_trade(self):
        """It is a DISCLOSURE, not a gate. Blocking on a permanently-unmodelled cost would not be a risk
        control -- it would be a refusal to ever trade."""
        res = RM.validate(entry=100.0, stop=99.0, target=104.0, venue="futures", order_type="maker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0)
        slip = [f for f in res["checks"] if f["check"] == "slippage"]
        self.assertEqual([f["state"] for f in slip], [RM.UNKNOWN])
        self.assertFalse(slip[0]["blocking"])
        self.assertTrue(res["ok"], RM.describe(res))


class TheCostInR(unittest.TestCase):
    """The formula, and why it is the one the backtest already uses."""

    def test_round_turn_cost_is_two_sides_over_the_stop_distance(self):
        # 0.05 %/side against a 1 % stop: 2 * 0.0005 / 0.01 = 0.10R
        cr, _ = RM.cost_r(100.0, 99.0, "futures", "taker")
        self.assertAlmostEqual(cr, 0.10, places=9)

    def test_a_tighter_stop_costs_more_R(self):
        """This is the whole reason it cannot be ignored on a scalping timeframe."""
        wide, _ = RM.cost_r(100.0, 99.0, "futures", "taker")     # 1.0 % stop
        tight, _ = RM.cost_r(100.0, 99.8, "futures", "taker")    # 0.2 % stop
        self.assertAlmostEqual(tight, 0.50, places=9)
        self.assertGreater(tight, wide * 4)

    def test_it_matches_the_backtests_own_formula(self):
        """scripts/backtest-methods.py:517 charges `fee_R = 2 * fee_pct / dist`. Live and research must not
        price the same trade differently."""
        bt = _load("bt", "backtest-methods.py")
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("fee_R = 2 * fee_pct / dist", src)
        entry, stop, fee = 100.0, 99.0, 0.0005
        dist = abs(entry - stop) / entry
        self.assertAlmostEqual(RM.cost_r(entry, stop, "futures", "taker")[0], 2 * fee / dist, places=12)
        self.assertTrue(hasattr(bt, "simulate"))

    def test_maker_costs_less_than_taker_on_futures(self):
        maker, _ = RM.cost_r(100.0, 99.0, "futures", "maker")
        taker, _ = RM.cost_r(100.0, 99.0, "futures", "taker")
        self.assertLess(maker, taker)

    def test_a_zero_stop_distance_refuses_instead_of_dividing_by_zero(self):
        with self.assertRaises(RM.RiskRefused) as cm:
            RM.cost_r(100.0, 100.0, "futures", "taker")
        self.assertIn("stop distance is zero", str(cm.exception))


class TheFloorIsNowNet(unittest.TestCase):
    """The defect, stated as a test: a setup that passes gross and fails net."""

    def test_a_gross_pass_that_is_a_net_fail_is_refused(self):
        # 3.25R gross on a 0.2 % stop; fees take 0.50R; 2.75R net is below the 3R floor.
        r = RM.net_r(100.0, 99.8, 100.65, "futures", "taker")
        self.assertAlmostEqual(r["gross_r"], 3.25, places=9)
        self.assertAlmostEqual(r["net_r"], 2.75, places=9)
        res = RM.validate(entry=100.0, stop=99.8, target=100.65, venue="futures", order_type="taker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0)
        self.assertFalse(res["ok"])
        rr = next(f for f in res["checks"] if f["check"] == "planned_rr")
        self.assertEqual(rr["state"], RM.FAIL)
        self.assertIn("2.75", rr["why"])

    def test_the_same_gross_on_a_wide_stop_still_passes(self):
        """The gate did not become blanket-stricter; it became cost-aware."""
        res = RM.validate(entry=100.0, stop=97.0, target=109.75, venue="futures", order_type="taker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0)
        self.assertTrue(res["ok"], RM.describe(res))

    def test_an_unreadable_floor_is_UNKNOWN_and_blocks(self):
        res = RM.validate(entry=100.0, stop=99.0, target=110.0, venue="futures", order_type="maker",
                          equity=10000.0, risk_pct=0.01, min_rr=None)
        self.assertFalse(res["ok"])
        self.assertEqual([f["state"] for f in res["checks"] if f["check"] == "planned_rr"], [RM.UNKNOWN])

    def test_the_runners_gate_uses_the_net_number(self):
        """Through the runner's own rr_reason(), not a reimplementation of it."""
        sr = _load("sr", "strategy-runner.py")
        # entry_now=True -> MARKET order -> taker fee: on a 0.2 % stop it costs 0.50R, which is what makes
        # 2.25R gross into 1.75R net -- below the live floor (2.0 since 2026-09-19; the case was 3.25/2.75 at 3R).
        sig_gross_ok_net_bad = {"entry": 100.0, "stop": 99.8, "target": 100.45, "r_planned": 2.25,
                                "entry_now": True}
        why = sr.rr_reason(sig_gross_ok_net_bad, "futures")
        self.assertIsNotNone(why, "a 2.25R gross / 1.75R net setup must be refused")
        self.assertIn("sau phí", why)

    def test_the_runners_gate_still_passes_a_genuinely_good_setup(self):
        sr = _load("sr", "strategy-runner.py")
        self.assertIsNone(sr.rr_reason({"entry": 100.0, "stop": 97.0, "target": 110.0, "r_planned": 4.33},
                                       "futures"))

    def test_the_runners_gate_fails_closed_on_a_missing_price(self):
        sr = _load("sr", "strategy-runner.py")
        why = sr.rr_reason({"r_planned": 9.0}, "futures")
        self.assertIsNotNone(why)

    def test_entry_now_is_priced_as_taker_and_a_resting_limit_as_maker(self):
        """`entry_now` means a MARKET order at the bar close; everything else rests a post-only GTX limit.
        Pricing them the same would over-charge one family and under-charge the other."""
        sr = _load("sr", "strategy-runner.py")
        # 2.70R gross on a 0.4 % stop: taker costs 0.25R (2.45R net, below the 2.5 floor), a resting limit ~0.17R
        # (~2.53R net, clears it). Re-based from 2.20R gross when the floor moved 2.0 -> 2.5 (owner, 2026-09-30).
        sig = {"entry": 100.0, "stop": 99.6, "target": 100.0 + 0.4 * 2.7, "r_planned": 2.7}
        market = sr.rr_reason(dict(sig, entry_now=True), "futures")
        limit = sr.rr_reason(dict(sig), "futures")
        self.assertIsNotNone(market, "taker fees must make this one fail")
        self.assertIsNone(limit, "the same setup as a maker order clears the floor")


class ExistingExposureIsSummedNotCounted(unittest.TestCase):
    def test_two_positions_with_different_stops_are_not_the_same_exposure(self):
        """The count-based cap could not tell these apart; that is why §34 names exposure separately."""
        tight = {"A": {"qty": 100, "entry": 100.0, "stop": 99.9}}
        wide = {"B": {"qty": 100, "entry": 100.0, "stop": 90.0}}
        self.assertLess(RM.open_risk(tight, 10000.0)["risk_fraction"],
                        RM.open_risk(wide, 10000.0)["risk_fraction"])

    def test_an_unmeasurable_position_is_reported_not_treated_as_zero(self):
        ex = RM.open_risk({"A": {"qty": 1, "entry": 100.0, "stop": 99.0}, "B": {"qty": "?"}}, 10000.0)
        self.assertEqual(ex["unknown"], ["B"])
        self.assertFalse(ex["complete"])

    def test_the_exposure_check_blocks_when_the_book_cannot_be_measured(self):
        res = RM.validate(entry=100.0, stop=99.0, target=110.0, venue="futures", order_type="maker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0,
                          positions={"B": {"qty": None}}, max_open_risk_fraction=0.09)
        self.assertFalse(res["ok"])
        self.assertEqual([f["state"] for f in res["checks"] if f["check"] == "existing_exposure"],
                         [RM.UNKNOWN])

    def test_the_exposure_check_blocks_a_trade_that_would_breach_the_cap(self):
        book = {f"S{i}": {"qty": 100, "entry": 100.0, "stop": 99.0} for i in range(9)}   # 9 x 1 % = 9 %
        res = RM.validate(entry=100.0, stop=99.0, target=110.0, venue="futures", order_type="maker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0,
                          positions=book, max_open_risk_fraction=0.09)
        self.assertFalse(res["ok"])
        self.assertEqual([f["state"] for f in res["checks"] if f["check"] == "existing_exposure"], [RM.FAIL])

    def test_an_empty_book_passes(self):
        res = RM.validate(entry=100.0, stop=99.0, target=110.0, venue="futures", order_type="maker",
                          equity=10000.0, risk_pct=0.01, min_rr=3.0,
                          positions={}, max_open_risk_fraction=0.09)
        self.assertTrue(res["ok"], RM.describe(res))


class SizingRefusesRatherThanProducingANumber(unittest.TestCase):
    def test_a_zero_stop_distance_refuses(self):
        with self.assertRaises(RM.RiskRefused):
            RM.size(10000.0, 100.0, 100.0, 0.01)

    def test_a_non_positive_equity_refuses(self):
        with self.assertRaises(RM.RiskRefused):
            RM.size(0.0, 100.0, 99.0, 0.01)

    def test_a_risk_fraction_typed_as_a_percent_refuses(self):
        """`1` meaning '1 %' would risk the entire account on one trade."""
        with self.assertRaises(RM.RiskRefused) as cm:
            RM.size(10000.0, 100.0, 99.0, 1.5)
        self.assertIn("fraction", str(cm.exception))

    def test_the_risk_usd_target_is_unchanged_from_the_runners_own_size(self):
        """DEC-4 (2026-09-24): strategy-runner.size() now sizes on the ALL-IN loss (price distance AND the
        round-trip fee), not price distance alone -- this module's own size() still prices distance only, so
        the two functions' `qty` are now EXPECTED to diverge (see the next test). What must stay identical is
        the TARGET risk_usd itself (equity x risk_pct x risk_mult): DEC-4 changes how much of that risk a unit
        of price distance costs, not how much risk the trade is allowed to take.

        Code review fix round 1 (nit 3): risk_mult=1.0 with entry=100/stop=99/leverage=3 hits the notional
        cap (equity x NOTIONAL_CAP_PCT x leverage = 10000 x 0.25 x 3 = 7500) in BOTH the old and new sizing --
        the cap, not the fee, decided `qty` in both, so the test passed without ever exercising the fee
        arithmetic it names. risk_mult=0.1 keeps risk_usd (10.0) and both qtys (9.095 / 10.0, notional
        909.5 / 1000.0) well under the 7500 cap, so the divergence asserted below is actually the fee, and the
        notional_capped preconditions make that explicit rather than assumed."""
        sr = _load("sr", "strategy-runner.py")
        qty, risk_usd = sr.size(10000.0, 100.0, 99.0, 0.1, leverage=3)
        mine = RM.size(10000.0, 100.0, 99.0, sr.RISK_PCT, leverage=3, notional_cap_pct=sr.NOTIONAL_CAP_PCT, risk_mult=0.1)
        self.assertFalse(mine["notional_capped"], "precondition: the cap must not bind, or this test proves nothing about fees")
        self.assertLess(qty * 100.0, 10000.0 * sr.NOTIONAL_CAP_PCT * 3, "precondition: the runner's own qty must not be capped either")
        self.assertAlmostEqual(mine["risk_usd"], risk_usd, places=9)
        # DEC-4: sizing on the all-in loss (distance + fee) means a SMALLER qty than distance alone for the
        # same target risk -- the whole point of the fix (distance-only sizing let the fee push the realised
        # loss at the stop past the risk ceiling).
        self.assertLess(qty, mine["qty"])

    def test_the_notional_cap_binds(self):
        s = RM.size(10000.0, 100.0, 99.9, 0.01, leverage=3, notional_cap_pct=0.25)
        self.assertTrue(s["notional_capped"])
        self.assertLessEqual(s["notional"], 10000.0 * 0.25 * 3 + 1e-9)


class MinNotionalNoLongerGuesses(unittest.TestCase):
    """The literal 50.0 is gone from the order path."""

    def setUp(self):
        self.sr = _load("sr", "strategy-runner.py")

    def test_a_connector_failure_refuses_instead_of_returning_fifty(self):
        real = self.sr.order
        try:
            self.sr.order = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connector down"))
            self.sr._MIN_NOTIONAL.clear()
            with self.assertRaises(RM.RiskRefused) as cm:
                self.sr.min_notional("BTCUSDT")
            self.assertIn("MIN_NOTIONAL", str(cm.exception))
        finally:
            self.sr.order = real; self.sr._MIN_NOTIONAL.clear()

    def test_filters_without_a_min_notional_entry_refuse(self):
        real = self.sr.order
        try:
            self.sr.order = lambda *a, **k: "{'filters': [{'filterType': 'LOT_SIZE'}]}"
            self.sr._MIN_NOTIONAL.clear()
            with self.assertRaises(RM.RiskRefused):
                self.sr.min_notional("BTCUSDT")
        finally:
            self.sr.order = real; self.sr._MIN_NOTIONAL.clear()

    def test_a_real_filter_response_is_read(self):
        real = self.sr.order
        try:
            self.sr.order = lambda *a, **k: "{'filterType': 'MIN_NOTIONAL', 'notional': '20.0'}"
            self.sr._MIN_NOTIONAL.clear()
            self.assertEqual(self.sr.min_notional("BTCUSDT"), 20.0)
        finally:
            self.sr.order = real; self.sr._MIN_NOTIONAL.clear()

    def test_min_notional_is_read_whichever_order_the_venue_prints_the_keys(self):
        """The live defect of 2026-09-18, found by a real dry tick and not by any test here.

        The first parser was `'MIN_NOTIONAL'.*?'notional': '([0-9.]+)'` -- a span of TEXT, which silently
        requires the venue to print filterType before notional. Binance does not: BTCUSDT returns
        `{'filterType': 'MIN_NOTIONAL', 'notional': '50'}` and SOLUSDT returns
        `{'notional': '5', 'filterType': 'MIN_NOTIONAL'}`. So SOL, RENDER and ONDO -- three of the nine
        EXECUTION symbols -- refused to size against a minimum the venue had published. Every test in this
        file stubbed the connector with the one key order that happened to work.
        """
        both = [("{'filterType': 'MIN_NOTIONAL', 'notional': '50'}", 50.0),
                ("{'notional': '5', 'filterType': 'MIN_NOTIONAL'}", 5.0),
                ("{'a': 1}\n{'notional': '20', 'filterType': 'MIN_NOTIONAL'}\n{'b': 2}", 20.0)]
        real = self.sr.order
        try:
            for raw, expected in both:
                self.sr.order = lambda *a, _r=raw, **k: _r
                self.sr._MIN_NOTIONAL.clear()
                self.assertEqual(self.sr.min_notional("BTCUSDT"), expected, raw)
        finally:
            self.sr.order = real; self.sr._MIN_NOTIONAL.clear()

    def test_a_min_notional_object_with_no_notional_key_still_refuses(self):
        real = self.sr.order
        try:
            self.sr.order = lambda *a, **k: "{'filterType': 'MIN_NOTIONAL'}"
            self.sr._MIN_NOTIONAL.clear()
            with self.assertRaises(RM.RiskRefused):
                self.sr.min_notional("BTCUSDT")
        finally:
            self.sr.order = real; self.sr._MIN_NOTIONAL.clear()

    def test_the_literal_fallback_is_gone_from_the_source(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn("_MIN_NOTIONAL[sym] = 50.0", src)


class LiveAndResearchPriceTheSameTradeTheSameWay(unittest.TestCase):
    def test_every_selected_setups_assumed_fee_is_declared_for_its_venue(self):
        """`pilot-selection.json` records the fee each ranking run ASSUMED. If a setup was validated at a fee the
        account does not pay, its evidence is about a different trade -- so the two must be reconciled rather
        than each carrying its own number."""
        sel = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-selection.json"), encoding="utf-8"))
        cfg = RM._config()["costs"]
        mismatched = []
        for s in sel["setups"]:
            venue = s["execution"]
            declared = {cfg[venue]["maker_pct_per_side"], cfg[venue]["taker_pct_per_side"]}
            if s.get("fee_assumed") not in declared:
                mismatched.append((s["id"], s.get("fee_assumed"), sorted(declared)))
        self.assertEqual(mismatched, [], (
            "these setups were ranked at a fee this account does not pay, so the R-multiples behind them are "
            "not the R-multiples the live path will realise: " + repr(mismatched)))

    def test_the_min_rr_floor_and_the_fee_it_was_measured_at_are_both_recorded(self):
        params = json.load(open(os.path.join(ROOT, "docs", "architecture", "analysis-params.json"),
                                encoding="utf-8"))
        basis = params["project_defined"]["ict"]["min_rr"]["_basis"]
        self.assertIn("fee", basis.lower(),
                      "the floor's basis must say what fee it was measured at, or nothing can check that the "
                      "live gate charges the same")



class AConfigsFeeBelongsToTheVenue(unittest.TestCase):
    """Found 2026-09-18 by re-ranking on the fresh MT5 history, which selected two CFD setups for the first time.

    `stability-report.CONFIGS` used to carry the fee as a literal -- A 0.05 %, B 0.02 %, C 0.02 % -- and applied
    it to every market. Those are the Binance taker/maker numbers. On MT5 the broker prices a CFD in the spread
    and `risk-config.json` declares 0.05 % on BOTH sides, so every CFD row in config B or C had been priced
    2.5x cheaper than the account pays, and `rank-setups.py` -- carrying its own second copy of the same table
    -- stamped `fee_assumed: 0.0002` onto the two it selected.

    The config's real claim is "this rule enters at market" vs "on a limit"; what that COSTS is the venue's
    business. So the table now says `side: taker|maker` and the number comes from the one declared cost.
    """

    def test_a_config_declares_a_side_not_a_number(self):
        for name, cfg in _SR.CONFIGS.items():
            self.assertIn(cfg["side"], ("taker", "maker"), name)
            self.assertNotIn("fee", cfg, f"config {name} carries a fee literal again")

    def test_crypto_keeps_the_maker_rebate_and_cfd_does_not(self):
        self.assertEqual({c: _SR.config_fee(cfg, "crypto") for c, cfg in _SR.CONFIGS.items()},
                         {"A": 0.0005, "B": 0.0002, "C": 0.0002})
        # No maker/taker split on a spread-priced CFD: B and C differ from A by MANAGEMENT, not by price.
        self.assertEqual({c: _SR.config_fee(cfg, "cfd") for c, cfg in _SR.CONFIGS.items()},
                         {"A": 0.0005, "B": 0.0005, "C": 0.0005})

    def test_every_config_fee_is_one_the_venue_actually_declares(self):
        costs = RM._config()["costs"]
        for market in ("crypto", "cfd"):
            venue = _P.unattended_venue_for(market)
            declared = {costs[venue]["maker_pct_per_side"], costs[venue]["taker_pct_per_side"]}
            for name, cfg in _SR.CONFIGS.items():
                self.assertIn(_SR.config_fee(cfg, market), declared, f"{market}/{name}")

    def test_the_ranker_does_not_keep_a_second_copy_of_the_table(self):
        # The whole cause: two tables, one of them wrong. Identity cannot be asserted across two separately
        # loaded module objects, so the check is the one that actually matters -- the ranker's SOURCE contains
        # no table of its own, and what it exposes equals what the producer declared.
        self.assertEqual(_RS.CFG_DESC, _SR.CONFIGS)
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        body = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        self.assertNotIn('CFG_DESC = {"A"', body, "the ranker has grown its own config table again")
        self.assertIn("CFG_DESC = _SR.CONFIGS", body)

    def test_a_market_whose_venue_declares_no_cost_refuses(self):
        # Guessing a fee is how a backtest comes to describe an account nobody has.
        with self.assertRaises((SystemExit, ValueError)) as cm:
            _SR.config_fee(_SR.CONFIGS["A"], "no-such-market")
        self.assertIn("guess", str(cm.exception).lower())


if __name__ == "__main__":
    unittest.main()
