"""CLAUDE.md §6 -- the provider capability registry.

§6's four rules, and what holds each:

  "Capabilities must be explicit"            -> every provider declares a `capabilities` list; an absent one
                                               refuses to load. "none" is written `[]`, never left implicit.
  "Never invent capabilities"                -> a capability not in the vocabulary refuses to load, so one
                                               cannot be conjured at the point of use.
  "Never assume capability merely because a
   provider exists"                          -> declared != live. CoinGlass DECLARES footprint bars and has no
                                               API key; `live_only` is the difference, and this file's central
                                               test is that a mock provider cannot satisfy a live requirement.
  "Never silently switch providers when a
   capability is unavailable"                -> `capability_report()` returns the REASON, and the three
                                               distinguishable causes are asserted separately below.

The vocabulary deliberately contains five capabilities NO provider declares -- `ohlcv_realtime`, `trades_raw`,
`orderbook_depth`, `economic_calendar`, `news`. That is not an oversight to be tidied away: it is the registry
stating, in a machine-readable place, that this system has no source for realtime candles (§52), no raw trades
to build a footprint from (§22), and no economic calendar feed (§24-§32). A test pins them so that "we have no
calendar" cannot quietly stop being written down.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import methods as M
import providers as P


class Vocabulary(unittest.TestCase):
    def test_every_provider_declares_a_capability_list(self):
        for pid in P.ALL:
            self.assertIsInstance(P.provider(pid)["capabilities"], list, f"{pid} has no capabilities list")

    def test_a_capability_outside_the_vocabulary_refuses_to_load(self):
        bad = {"roles": {"market_data": ""}, "status_values": {"connected": ""},
               "capabilities": {"ohlcv_historical": ""},
               "providers": {"p": {"roles": ["market_data"], "markets": ["crypto"], "adapter": None,
                                   "status": "connected", "capabilities": ["telepathy"],
                                   "venue": "v", "external": True}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("telepathy", str(cm.exception))

    def test_a_provider_with_no_capability_list_refuses_to_load(self):
        """Absent is not 'none'. An unanswered question about a dependency must not read as a benign default."""
        bad = {"roles": {"market_data": ""}, "status_values": {"connected": ""}, "capabilities": {},
               "providers": {"p": {"roles": ["market_data"], "markets": ["crypto"], "adapter": None,
                                   "status": "connected", "venue": "v", "external": True}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("capabilities", str(cm.exception))

    def test_the_execution_role_and_the_order_submission_capability_must_agree(self):
        bad = {"roles": {"execution": ""}, "status_values": {"connected": ""},
               "capabilities": {"funding": ""},
               "providers": {"p": {"roles": ["execution"], "markets": ["crypto"], "adapter": "scripts/instruments.py",
                                   "status": "connected", "capabilities": ["funding"],
                                   "venue": "v", "external": True}}}
        with self.assertRaises(ValueError) as cm:
            P._validate(bad)
        self.assertIn("order_submission", str(cm.exception))

    def test_the_capabilities_this_system_has_no_source_for_stay_written_down(self):
        """These five are the honest gaps. If one silently acquires a provider, this test should be UPDATED
        deliberately -- and if one is deleted from the vocabulary to make a list look shorter, it fails."""
        unsourced = {c for c in P.CAPABILITIES if not P.providers_with(c)}
        self.assertEqual(unsourced,
                         {"ohlcv_realtime", "trades_raw", "orderbook_depth", "economic_calendar", "news"})


class DeclaredIsNotLive(unittest.TestCase):
    """§6's sharpest rule: a provider existing is not a capability being available."""

    def test_coinglass_declares_footprint_and_cannot_supply_it_live(self):
        self.assertIn("coinglass", P.providers_with("footprint_bars", "crypto"))
        self.assertEqual(P.providers_with("footprint_bars", "crypto", live_only=True), [],
                         "a mock_only provider was reported as a live source")

    def test_a_dimension_backed_only_by_a_mock_provider_is_not_live_sourced(self):
        """The trap this closes: nothing in production passed `unavailable` to dispatch_plan, so under the
        `full` preset a CoinGlass-backed dimension would have counted as engaged with no API key configured --
        a fixture satisfying a live decision requirement, which SYSTEM-DESIGN.md §6.1 forbids by name."""
        for dim in ("footprint", "heatmap"):
            self.assertIn("crypto", M.DIMENSIONS[dim]["markets"], f"{dim} should be structurally possible")
            self.assertFalse(M.live_sourced(dim, "crypto"), f"{dim} reported live with CoinGlass mock_only")

    def test_the_candle_backed_dimensions_are_live_sourced(self):
        for dim in ("wyckoff", "ict"):
            for market in ("crypto", "cfd"):
                self.assertTrue(M.live_sourced(dim, market), f"{dim}/{market} should be live")

    def test_structural_and_live_availability_are_different_questions(self):
        self.assertIn("crypto", P.markets_with_capability("footprint_bars"))
        self.assertNotIn("crypto", P.markets_with_capability("footprint_bars", live_only=True))


class UnavailabilityPreservesItsReason(unittest.TestCase):
    """§6: expose the unavailable state AND preserve the reason. Three causes that must not read alike."""

    def test_a_live_capability_reports_its_providers(self):
        r = P.capability_report("ohlcv_historical", "crypto")
        self.assertTrue(r["live"])
        self.assertEqual(r["providers"], ["binance_public"])
        self.assertIsNone(r["reason"])

    def test_a_source_that_exists_but_is_not_connected_says_which_and_why(self):
        r = P.capability_report("footprint_bars", "crypto")
        self.assertFalse(r["live"])
        self.assertIn("coinglass", r["reason"])
        self.assertIn("mock_only", r["reason"])

    def test_a_capability_with_no_source_at_all_says_so_distinctly(self):
        """'CoinGlass is down' and 'there has never been a source' are different answers to 'should I wait?'"""
        r = P.capability_report("footprint_bars", "cfd")
        self.assertFalse(r["live"])
        self.assertIn("no provider supplies", r["reason"])
        self.assertNotIn("mock_only", r["reason"])

    def test_the_event_calendar_gap_is_visible_through_the_registry(self):
        """CLAUDE.md §24-§32's root cause, stated by the registry rather than only in prose."""
        for market in I.MARKETS:
            r = P.capability_report("economic_calendar", market)
            self.assertFalse(r["live"])
            self.assertIn("no provider supplies", r["reason"])


class DimensionsAreTiedToCapabilities(unittest.TestCase):
    def test_every_dimension_declares_its_data_sources(self):
        """_validate() skips this block when the key is absent so the minimal fixtures in test_methods.py can
        omit what they are not testing -- which means the REAL registry needs its own assertion."""
        for dim in M.ALL_DIMENSIONS:
            self.assertTrue(M.DIMENSIONS[dim].get("data_sources"), f"dimension {dim} declares no data_sources")

    def test_dimension_data_sources_are_capability_ids_not_vendor_names(self):
        for dim in M.ALL_DIMENSIONS:
            for src in M.DIMENSIONS[dim]["data_sources"]:
                self.assertIn(src, P.CAPABILITIES, f"{dim} needs {src!r}, not a declared capability")
                self.assertNotIn("coinglass", src.lower(),
                                 f"{dim} names a vendor in a domain field (CLAUDE.md §2, §6)")

    def test_a_dimension_may_not_claim_a_market_no_provider_serves(self):
        """The drift check: `markets[]` is authored but must equal what the capability registry implies."""
        for dim in M.ALL_DIMENSIONS:
            implied = set.intersection(*[set(P.markets_with_capability(c))
                                         for c in M.DIMENSIONS[dim]["data_sources"]])
            self.assertEqual(set(M.DIMENSIONS[dim]["markets"]), implied, f"{dim} markets drifted")

    def test_source_status_names_the_capability_and_the_reason(self):
        rows = M.source_status("footprint", "crypto")
        self.assertEqual([r["capability"] for r in rows], ["footprint_bars"])
        self.assertTrue(rows[0]["reason"])


if __name__ == "__main__":
    unittest.main()
