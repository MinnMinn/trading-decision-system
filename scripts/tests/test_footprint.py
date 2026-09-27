"""CLAUDE.md §22 -- footprint is derived analytics, and the derivation exists.

§22 states a chain and a field list:

    Raw Trades -> Trade Classification -> Aggregation -> Footprint
    Preserve: source trades, provider, source venue, market type, timestamp, aggregation rule,
              price level, bid/ask classification, timeframe.

Neither existed. There was no footprint record type, so not one of the nine fields was preserved anywhere, and
the repo's only footprint -- `mock/coinglass/footprint-history.BTCUSDT.json` -- was **unparseable JSON**
(`"delta": +176`). Nothing had ever loaded it; it is read as text by an agent. That is fixed here, and
`test_every_mock_fixture_parses` exists so the next one cannot sit undetected.

**What is deliberately NOT built.** `providers.json` declares `trades_raw` and records that no provider
supplies it, and `methods.live_sourced("footprint", …)` is False for every market. Building a trades FEED to
supply a switched-off dimension is the speculative work §0 and §57 forbid. What is built is the part that is
§22's actual subject and needs no feed: classification and aggregation as pure functions, and a record type
that makes the nine fields required. `test_the_chain_has_no_live_input_and_that_is_recorded` pins that
reasoning so the omission reads as a decision rather than an oversight.
"""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import footprint as F
import methods as M
import providers as P
import spec

PROV = {"provider": "binance_public", "source_venue": "binance", "market_type": "SPOT"}
TRADES = [
    {"time": "2026-09-08T14:00:05Z", "price": 64800, "size": 3, "buyer_is_maker": False},   # taker BUY
    {"time": "2026-09-08T14:00:07Z", "price": 64800, "size": 2, "buyer_is_maker": True},    # taker SELL
    {"time": "2026-09-08T14:02:00Z", "price": 64820, "size": 5, "buyer_is_maker": False},   # taker BUY
    {"time": "2026-09-08T14:16:00Z", "price": 64850, "size": 1, "buyer_is_maker": True},    # next bar
]


def build(rule=F.VENUE_RULE, trades=None):
    return F.build(trades or TRADES, "15m", tick_size=20, bar_seconds=900, provenance=PROV, rule=rule)


class TheChainExists(unittest.TestCase):
    """Raw Trades -> Classification -> Aggregation -> Footprint, each step separately testable."""

    def test_classification_is_its_own_step(self):
        sides = [s for _, s in F.classify(TRADES)]
        self.assertEqual(sides, [F.BUY, F.SELL, F.BUY, F.SELL])

    def test_aggregation_buckets_trades_into_bars_and_price_levels(self):
        bars = build()
        self.assertEqual([b["timestamp"] for b in bars],
                         ["2026-09-08T14:00:00Z", "2026-09-08T14:15:00Z"])
        self.assertEqual([lv["price"] for lv in bars[0]["price_levels"]], [64800, 64820])

    def test_bid_and_ask_volume_land_on_the_right_side(self):
        lv = build()[0]["price_levels"][0]
        self.assertEqual((lv["buy_vol"], lv["sell_vol"]), (3.0, 2.0))

    def test_delta_is_computed_not_copied(self):
        self.assertEqual(build()[0]["delta"], 6.0)      # 3 + 5 buy - 2 sell

    def test_the_bar_counts_the_trades_it_was_built_from(self):
        self.assertEqual([b["source_trades"] for b in build()], [3, 1])


class TheRuleIsRecordedBecauseItChangesTheAnswer(unittest.TestCase):
    """§22 names 'trade classification' without saying how, because a trade's side is a fact only the venue
    knows and everything else is inference. An aggregation whose rule is not recorded cannot be reproduced
    (§10, §46) -- and here the two rules genuinely disagree, which is the whole argument."""

    def test_the_two_rules_produce_different_deltas_on_the_same_trades(self):
        self.assertNotEqual([b["delta"] for b in build(F.VENUE_RULE)],
                            [b["delta"] for b in build(F.TICK_RULE)])

    def test_each_bar_names_the_rule_that_produced_it(self):
        for rule in (F.VENUE_RULE, F.TICK_RULE):
            self.assertTrue(all(b["classification_rule"] == rule for b in build(rule)))

    def test_the_aggregation_rule_is_recorded_too(self):
        self.assertIn("tick_size=20", build()[0]["aggregation_rule"])

    def test_an_unnamed_rule_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            F.classify(TRADES, rule="vibes")
        self.assertIn("recorded", str(cm.exception))

    def test_the_tick_rule_repeats_the_last_side_on_an_unchanged_price(self):
        """The classical rule. Stated as a test because 'unchanged' is where implementations differ."""
        sides = [s for _, s in F.classify(
            [{"time": "2026-09-08T14:00:00Z", "price": 100},
             {"time": "2026-09-08T14:00:01Z", "price": 101},
             {"time": "2026-09-08T14:00:02Z", "price": 101}], rule=F.TICK_RULE)]
        self.assertEqual(sides[1], sides[2])


class UnknownStaysUnknown(unittest.TestCase):
    """§9. A trade whose side cannot be determined must not be counted as a buy -- that puts a fabricated
    imbalance into every bar containing it, and an imbalance is what the dimension exists to report."""

    def test_a_trade_with_no_venue_flag_is_unknown(self):
        self.assertEqual(F.classify([{"time": "2026-09-08T14:00:00Z", "price": 1}])[0][1], F.UNKNOWN)

    def test_unknown_volume_is_kept_in_its_own_column(self):
        bars = build(trades=[{"time": "2026-09-08T14:00:00Z", "price": 64800, "size": 7}])
        self.assertEqual(bars[0]["price_levels"][0]["unknown_vol"], 7.0)
        self.assertEqual(bars[0]["delta"], 0.0, "unknown volume leaked into the delta")

    def test_the_bar_reports_how_much_it_could_not_classify(self):
        bars = build(trades=[{"time": "2026-09-08T14:00:00Z", "price": 64800, "size": 7}])
        self.assertEqual(bars[0]["unknown_vol"], 7.0)


class TheNineFieldsAreRequired(unittest.TestCase):
    def test_every_field_section_22_lists_is_present(self):
        bar = build()[0]
        for f in F.REQUIRED_FIELDS:
            self.assertIn(f, bar)

    def test_a_record_missing_one_is_refused(self):
        for drop in F.REQUIRED_FIELDS:
            good = dict(build()[0])
            good.pop(drop)
            with self.assertRaises(ValueError, msg=f"a record with no {drop} was accepted"):
                F._seal(good)

    def test_provenance_is_not_defaulted(self):
        """A default for 'which venue was this' is a guess about provenance, which is what §7 exists to stop."""
        for thin in ({}, {"provider": "coinglass"}, {"provider": "x", "source_venue": "y"}):
            with self.assertRaises(ValueError):
                F.build(TRADES, "15m", tick_size=20, bar_seconds=900, provenance=thin)

    def test_a_bar_is_immutable(self):
        with self.assertRaises(TypeError):
            build()[0]["delta"] = 0


class AVendorBarIsNotADerivedOne(unittest.TestCase):
    """§22: 'Never pretend provider-native footprint exists if it does not.'"""

    def setUp(self):
        with open(os.path.join(ROOT, "mock", "coinglass", "footprint-history.BTCUSDT.json"),
                  encoding="utf-8") as fh:
            self.fix = json.load(fh)
        self.rec = F.from_vendor(self.fix["bars"][0], timeframe=self.fix["timeframe"],
                                 provenance={"provider": "coinglass", "source_venue": "MULTI",
                                             "market_type": "PERPETUAL"})

    def test_the_two_carry_different_derivations(self):
        self.assertEqual(self.rec["derivation"], F.VENDOR)
        self.assertEqual(build()[0]["derivation"], F.DERIVED)
        self.assertFalse(F.is_native(self.rec))
        self.assertTrue(F.is_native(build()[0]))

    def test_a_vendor_bar_names_no_source_trades_and_does_not_claim_zero(self):
        """None means 'not knowable from here'. A 0 would read as 'we looked and there were none'."""
        self.assertIsNone(self.rec["source_trades"])
        self.assertNotEqual(self.rec["source_trades"], 0)

    def test_a_vendor_bar_admits_its_aggregation_rule_is_undisclosed(self):
        self.assertIn("not disclosed", self.rec["aggregation_rule"])

    def test_a_vendor_bar_names_no_classification_rule(self):
        self.assertIsNone(self.rec["classification_rule"])

    def test_a_derivation_that_will_not_say_where_it_came_from_is_refused(self):
        bad = dict(build()[0])
        bad["derivation"] = "somewhere"
        with self.assertRaises(ValueError) as cm:
            F._seal(bad)
        self.assertIn("pretence", str(cm.exception))

    def test_the_vendors_bid_and_ask_columns_map_to_taker_sides(self):
        """A taker BUY lifts the ask; a taker SELL hits the bid. Getting this backwards inverts every delta."""
        src = self.fix["bars"][0]["price_levels"][0]
        got = self.rec["price_levels"][0]
        self.assertEqual(got["buy_vol"], float(src["ask_vol"]))
        self.assertEqual(got["sell_vol"], float(src["bid_vol"]))


class TheFixtureIsLoadable(unittest.TestCase):
    def test_every_mock_fixture_parses(self):
        """The footprint fixture carried `"delta": +176` -- not JSON. It is read as TEXT by an agent, so
        nothing ever noticed. This is the check that would have."""
        bad = []
        for f in sorted(glob.glob(os.path.join(ROOT, "mock", "**", "*.json"), recursive=True)):
            try:
                with open(f, encoding="utf-8") as fh:
                    json.load(fh)
            except Exception as exc:
                bad.append(f"{os.path.relpath(f, ROOT)}: {exc}")
        self.assertEqual(bad, [])

    def test_the_footprint_fixture_still_declares_itself_synthetic(self):
        with open(os.path.join(ROOT, "mock", "coinglass", "footprint-history.BTCUSDT.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertTrue(d["_mock"])
        self.assertIn("SYNTHETIC", d["_disclaimer"])


class TheMissingFeedIsRecordedNotForgotten(unittest.TestCase):
    def test_the_chain_has_no_live_input_and_that_is_recorded(self):
        """§22's chain is implemented; its raw input has no provider. The registry says so in the capability's
        own description, which is why building a feed here would be speculative rather than overdue."""
        with open(os.path.join(ROOT, "docs", "architecture", "providers.json"), encoding="utf-8") as fh:
            desc = json.load(fh)["capabilities"]["trades_raw"]
        self.assertIn("NO PROVIDER DECLARES THIS", desc)

    def test_no_provider_secretly_declares_raw_trades(self):
        with open(os.path.join(ROOT, "docs", "architecture", "providers.json"), encoding="utf-8") as fh:
            provs = json.load(fh)["providers"]
        for name, p in provs.items():
            if name.startswith("_"):
                continue
            self.assertNotIn("trades_raw", p.get("capabilities") or [],
                             f"{name} declares trades_raw -- wire footprint.build() to it")

    def test_the_footprint_dimension_is_not_live_sourced_anywhere(self):
        for market in ("crypto", "cfd"):
            self.assertFalse(M.live_sourced("footprint", market), market)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_22_states_the_chain(self):
        body = spec.body(22)
        for step in ("Raw Trades", "Trade Classification", "Aggregation", "Footprint"):
            self.assertIn(step, body)

    def test_section_22_lists_the_fields_this_preserves(self):
        body = spec.body(22)
        for f in ("source trades", "provider", "source venue", "market type", "timestamp",
                  "aggregation rule", "price level", "bid/ask classification", "timeframe"):
            self.assertIn(f, body)

    def test_section_22_forbids_the_pretence(self):
        self.assertIn("Never pretend provider-native footprint exists if it does not", spec.body(22))


if __name__ == "__main__":
    unittest.main()
