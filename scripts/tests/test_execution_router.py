"""CLAUDE.md §4 -- Data Source != Execution Venue, and the Decision Engine is not coupled to an exchange.

§4's operative sentence is the last one: *never couple the Decision Engine directly to a specific exchange.*
That is the part with teeth, and it is checkable two ways:

  1. The decision layer must not know what an exchange is. `scripts/live_rules.py` is the module both the
     live runner and the backtest read their setups through, so if a venue name appears there the two paths
     can diverge by venue and the backtest stops measuring the thing that trades.
  2. Where an order goes must be resolved from data. It used to be `"futures" if sym in CRYPTO else "mt5"` --
     a membership test whose `else` was fail-open: an unrecognised symbol resolved to MT5 instead of
     refusing. These tests pin the replacement's equivalence symbol by symbol (a refactor of an order path
     must not move where an order goes) and pin the new refusal.

Not asserted here, deliberately: that order SUBMISSION is venue-agnostic. It is not, and it should not be --
placing a post-only GTX limit on Binance futures and a pending order with attached SL/TP on MT5 are different
operations, and that difference living inside the adapter is what an adapter IS. §4 forbids the DECISION
depending on the venue, not the connector. SYSTEM-DESIGN.md §16.1 records the remaining branch sites.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import providers as P
import srcscan


def runner():
    spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class VenueResolution(unittest.TestCase):
    def setUp(self):
        self.sr = runner()

    def test_every_allowlisted_symbol_resolves_exactly_as_the_old_literal_did(self):
        """The equivalence that makes this refactor safe. The old rule is written out here ON PURPOSE -- this
        is the one place restating it is correct, because the assertion IS 'the answer did not change'."""
        old = lambda sym: "futures" if sym in self.sr.CRYPTO else "mt5"
        checked = 0
        for market in I.MARKETS:
            for sym in I.analysis(market):
                self.assertEqual(self.sr.venue_of(sym), old(sym), f"{sym} changed venue")
                checked += 1
        self.assertGreaterEqual(checked, 20, "the allowlist shrank; this equivalence check got weaker")

    def test_an_unknown_symbol_refuses_instead_of_defaulting_to_a_venue(self):
        """The fail-open that was there before: any unrecognised symbol -- a typo, or one removed from the
        allowlist -- silently resolved to MT5. In a function that decides where an order is submitted."""
        for junk in ("NOTASYMBOL", "", "BTCUSD", "btcusdt"):
            with self.assertRaises(ValueError, msg=f"{junk!r} did not refuse"):
                self.sr.venue_of(junk)

    def test_venue_comes_from_the_registry_not_from_a_symbol_set(self):
        for market, expected in (("crypto", "futures"), ("cfd", "mt5"), ("forex", "mt5")):
            self.assertEqual(P.unattended_venue_for(market), expected)

    def test_a_manual_confirmation_venue_is_never_offered_to_the_unattended_pilot(self):
        """binance_spot is /execute's venue: one explicit human confirmation per trade. Its whole safety story
        is that human, so a loop with no human in it must not be able to select it (CLAUDE.md §51)."""
        self.assertFalse(P.PROVIDERS["binance_spot"]["unattended"])
        self.assertEqual(P.unattended_venue_for("crypto"), P.alias_of("binance_futures"))
        self.assertNotEqual(P.unattended_venue_for("crypto"), P.alias_of("binance_spot"))

    def test_an_ambiguous_or_absent_unattended_provider_refuses(self):
        """Zero candidates must not silently return something, and two must not be guessed between."""
        real = P.PROVIDERS
        try:
            P.PROVIDERS = {"a": {"roles": ["execution"], "markets": ["crypto"], "unattended": True,
                                 "execution_alias": "a", "venue": "v", "external": True, "status": "connected",
                                 "adapter": "x"},
                           "b": {"roles": ["execution"], "markets": ["crypto"], "unattended": True,
                                 "execution_alias": "b", "venue": "v", "external": True, "status": "connected",
                                 "adapter": "x"}}
            with self.assertRaises(ValueError):
                P.unattended_venue_for("crypto")          # two candidates
            P.PROVIDERS["b"]["unattended"] = False
            P.PROVIDERS["a"]["unattended"] = False
            with self.assertRaises(ValueError):
                P.unattended_venue_for("crypto")          # zero candidates
        finally:
            P.PROVIDERS = real


class DecisionEngineIsNotCoupledToAnExchange(unittest.TestCase):
    """§4's operative rule. `live_rules.py` is the shared decision layer -- the runner and the backtest both
    read setups through it, which is what keeps the two measuring the same system."""

    EXCHANGE_WORDS = ("binance", "mt5", "coinglass", "testnet", "fapi", "venue", "exchange")

    def test_the_shared_decision_layer_names_no_exchange(self):
        code = srcscan.code_text("scripts/live_rules.py").lower()
        found = [w for w in self.EXCHANGE_WORDS if w in code]
        self.assertEqual(found, [], (
            f"scripts/live_rules.py -- the decision layer both the live runner and the backtest read setups "
            f"through -- names {found}. A decision that can differ by venue means the backtest stops "
            f"measuring what trades (CLAUDE.md §4, §37)."))

    def test_the_decision_functions_take_candles_not_a_venue(self):
        """Signature-level version of the same rule: a venue cannot influence a read it is not passed."""
        import inspect
        import live_rules
        for name in ("read_at", "bias_at", "window"):
            params = list(inspect.signature(getattr(live_rules, name)).parameters)
            for banned in ("venue", "exchange", "provider", "symbol", "sym"):
                self.assertNotIn(banned, params, f"live_rules.{name}() takes {banned!r}")
            self.assertIn("candles", params, f"live_rules.{name}() does not read candles")


class VenueDispatch(unittest.TestCase):
    def test_the_log_destination_is_a_lookup_with_the_old_default(self):
        """Behaviour-preserving: an unknown alias writes to the futures log exactly as the old `else` did."""
        sr = runner()
        self.assertEqual(sr.VENUE_LOG.get("mt5"), sr.MT5_LOG)
        self.assertEqual(sr.VENUE_LOG.get("futures", sr.LOG), sr.LOG)
        self.assertEqual(sr.VENUE_LOG.get("something-new", sr.LOG), sr.LOG)

    def test_every_venue_alias_the_runner_uses_is_declared_in_the_registry(self):
        """VENUES is the runner's own vocabulary; it must be a subset of what providers.json declares, or the
        engine knows a venue the registry has never heard of."""
        sr = runner()
        declared = {P.alias_of(pid) for pid in P.for_role("execution")}
        self.assertTrue(set(sr.VENUES) <= declared,
                        f"runner venues {set(sr.VENUES) - declared} are not declared in providers.json")


if __name__ == "__main__":
    unittest.main()
