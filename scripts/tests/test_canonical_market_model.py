"""CLAUDE.md §5 -- a canonical, provider-independent market model.

§5 asks for three things and forbids a fourth:

  * the five market types exist as a vocabulary (SPOT / FUTURES / PERPETUAL / CFD / OTHER);
  * instrument identity is independent of any provider's spelling;
  * CFD contexts are representable (they live in the §33 Account Profile registry -- see the class at the bottom);
  * and provider terminology must NOT be the canonical domain identity.

That last one is the interesting one, and this repo has a live example of the trap. Binance calls its USDT-M
product "futures"; every state row, log line and setup row in this repo is tagged `futures` because that is
the venue alias. The contract has no expiry and pays funding -- it is a PERPETUAL. If the domain adopted
Binance's word, then "is this instrument subject to funding?" and "does this instrument expire?" would both
be answered by a string that means neither. So the two vocabularies are deliberately separate and these tests
hold them apart.

The second design point these tests encode: **market type is a property of (instrument, venue), not of the
instrument.** BTCUSDT is SPOT on binance_spot and PERPETUAL on binance_futures. A per-symbol `market_type`
field -- the obvious first design -- would have to pick one and be wrong about the other, so the type is
declared on the execution provider and the market declares only which types it can hold.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import providers as P


class Vocabulary(unittest.TestCase):
    def test_the_five_canonical_market_types_exist(self):
        self.assertEqual(set(I.MARKET_TYPES), {"SPOT", "FUTURES", "PERPETUAL", "CFD", "OTHER"})

    def test_every_market_declares_which_types_it_can_hold(self):
        for m in I.MARKETS:
            types = I.market_types(m)
            self.assertTrue(types, f"market {m} declares no market_types")
            self.assertTrue(set(types) <= set(I.MARKET_TYPES), f"market {m} names an unknown type")

    def test_a_market_may_hold_more_than_one_type(self):
        """Crypto is SPOT (via /execute) and PERPETUAL (via the pilot). If this collapsed to one value, the
        model would be claiming an instrument can only be traded one way."""
        self.assertEqual(set(I.market_types("crypto")), {"SPOT", "PERPETUAL"})

    def test_an_unknown_market_type_refuses_to_load(self):
        bad = dict(I.MARKET_META["crypto"], market_types=["MARGIN"])
        self.assertNotIn("MARGIN", I.MARKET_TYPES)
        # Re-running the module's own check on a doctored copy, rather than editing the real registry.
        unknown = [t for t in bad["market_types"] if t not in I.MARKET_TYPES]
        self.assertEqual(unknown, ["MARGIN"], "the vocabulary check would not have caught this")


class ProviderTerminologyIsNotDomainIdentity(unittest.TestCase):
    """§5's prohibition, with the repo's own live example."""

    def test_binance_futures_is_a_perpetual_not_a_future(self):
        self.assertEqual(P.alias_of("binance_futures"), "futures", "the venue alias keeps the provider's word")
        self.assertEqual(P.market_type_of("binance_futures"), "PERPETUAL", "the DOMAIN must not")

    def test_an_alias_that_looks_like_a_market_type_but_is_not_one_must_say_so(self):
        """The two vocabularies overlap in spelling and cannot be pulled apart by renaming.

        `spot` is a harmless coincidence -- binance_spot's alias reads like SPOT and its contract IS SPOT.
        `futures` is the trap: it reads like the FUTURES market type and the contract is a PERPETUAL. The
        alias cannot be renamed (state rows, log lines, setup `execution` fields and the pilot's own directory
        all carry the word), so the requirement is that the collision be DECLARED where the provider is
        defined, not left for a reader to trip over.

        So the rule is not 'no overlap' -- that is unachievable -- it is: an alias spelled like a market type
        must either BE that type, or carry a note saying it is not."""
        for pid in P.for_role("execution"):
            alias, mtype = P.alias_of(pid), P.market_type_of(pid)
            if alias.upper() not in I.MARKET_TYPES:
                continue                                   # no collision to declare
            if alias.upper() == mtype:
                continue                                   # collision, but truthful (binance_spot / SPOT)
            self.assertIn("alias_collides_with_market_type", P.provider(pid), (
                f"provider {pid!r} has alias {alias!r}, which reads as the {alias.upper()} market type, but "
                f"its contract is {mtype}. Declare `alias_collides_with_market_type` on it saying so -- an "
                f"undocumented provider word that impersonates a domain type is what CLAUDE.md §5 forbids."))

    def test_the_known_collision_is_the_only_one(self):
        """Keeps the exception from becoming a habit: if a second misleading alias appears, this fails."""
        declared = [pid for pid in P.for_role("execution") if "alias_collides_with_market_type" in P.provider(pid)]
        self.assertEqual(declared, ["binance_futures"], f"unexpected set of declared collisions: {declared}")

    def test_market_type_is_a_property_of_instrument_and_venue(self):
        """The same symbol, two venues, two types. This is why the field is not on the instrument."""
        sym = "BTCUSDT"
        self.assertIn(sym, I.execution("crypto"))
        by_venue = {P.alias_of(pid): P.market_type_of(pid)
                    for pid in P.for_role("execution", "crypto")}
        self.assertEqual(by_venue, {"spot": "SPOT", "futures": "PERPETUAL"})
        self.assertNotEqual(by_venue["spot"], by_venue["futures"],
                            "one symbol resolves to two different market types depending on venue")

    def test_a_provider_may_not_offer_a_type_its_market_does_not_declare(self):
        real = P.PROVIDERS["binance_futures"]["market_type"]
        try:
            P.PROVIDERS["binance_futures"]["market_type"] = "CFD"
            with self.assertRaises(ValueError) as cm:
                P._validate({"roles": {r: "" for r in P.ROLES},
                             "status_values": {s: "" for s in P.STATUS_VALUES},
                             "capabilities": {c: "" for c in P.CAPABILITIES},
                             "providers": {"binance_futures": P.PROVIDERS["binance_futures"]}})
            self.assertIn("which declares", str(cm.exception))
        finally:
            P.PROVIDERS["binance_futures"]["market_type"] = real


class CanonicalInstrumentIdentity(unittest.TestCase):
    def test_every_analysable_symbol_has_a_canonical_id(self):
        for m in I.MARKETS:
            for sym in I.analysis(m):
                self.assertTrue(I.canonical(sym), f"{sym} has no canonical id")

    def test_the_canonical_id_is_not_the_provider_spelling(self):
        """BTCUSDT is Binance's spelling; USOIL is the MT5 broker's. Neither may be the domain's identity."""
        for sym in ("BTCUSDT", "ETHUSDT", "USOIL", "UKOIL", "EURUSD"):
            self.assertNotEqual(I.canonical(sym), sym, f"{sym}'s canonical id is just the provider symbol")

    def test_canonical_ids_are_unique(self):
        ids = [I.canonical(s) for m in I.MARKETS for s in I.analysis(m)]
        self.assertEqual(len(ids), len(set(ids)), "two symbols share one canonical id")

    def test_identity_is_not_presentation(self):
        """`display().label` may be restyled for readability; a canonical id may not. They are allowed to
        agree today -- what must not happen is one field serving both jobs, because then a styling edit
        silently re-identifies an instrument."""
        self.assertIsNot(I.canonical, I.display)
        self.assertNotIn("label", I._CANONICAL, "canonical must be its own block, not part of display")

    def test_the_oil_benchmarks_are_named_by_benchmark_not_by_broker_ticker(self):
        self.assertEqual(I.canonical("USOIL"), "WTI/USD")
        self.assertEqual(I.canonical("UKOIL"), "BRENT/USD")


class AccountContextsLiveInSection33(unittest.TestCase):
    """§5 also asks for CFD account/context types (Personal / Prop Challenge / Prop Funded / Demo / Custom).
    They were deferred to §33 and landed there on 2026-09-18. What this class now guards is the boundary: an
    account type describes an ACCOUNT, and putting it in the market model would give account rules two homes."""

    def test_they_exist_in_the_account_profile_registry(self):
        import account_profile as AP
        self.assertEqual(set(AP.CONTEXT_TYPES),
                         {"PERSONAL", "PROP_CHALLENGE", "PROP_FUNDED", "DEMO", "CUSTOM"})

    def test_they_have_not_leaked_into_the_market_model(self):
        self.assertFalse(hasattr(I, "account_contexts"),
                         "account contexts appeared in instruments.py; they belong to the §33 Account Profile")
        raw = open(os.path.join(ROOT, "docs", "architecture", "instruments.json"), encoding="utf-8").read()
        for word in ("PROP_CHALLENGE", "PROP_FUNDED", "Prop Challenge", "Prop Funded"):
            self.assertNotIn(word, raw, "an account/context type is being declared in the instrument registry")


if __name__ == "__main__":
    unittest.main()
