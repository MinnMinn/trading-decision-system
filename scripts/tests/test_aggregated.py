"""CLAUDE.md §23 -- an aggregate keeps its scope, and cannot be presented as one venue's figure.

§23 has two halves and they were in different states, which is why the compliance ledger's old "MISSING"
verdict was out of date by the time it was read:

**Preserving** was already done by the §7 provider work: `providers.json` declares `aggregation_scopes`, and
`coinglass` carries `multi_venue` / `["UNDECLARED"]` with a note explaining why naming an unverified venue set
would be the same error pointed the other way. One thing was genuinely missing -- `mock/coinglass/*.json`
carried **no `_source` marker**, so nothing could say which provider wrote them and §23's five fields could
not be attached to a figure even in principle. Marker added; `load()` does the join.

**Presenting** did not exist. §23's rule -- *"Never present aggregated information as if it came from one
venue"*, with its own worked example of "Aggregated OI across venues" becoming "OKX OI" -- lived as prose in a
registry note. `attribute()` is that rule with code attached.

The test that matters is `test_the_specs_own_example_is_refused`: it is §23's example, verbatim, against the
live registry.
"""
import glob
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import aggregated as A
import providers as P
import spec

OI = os.path.join(ROOT, "mock", "coinglass", "open-interest.BTCUSDT.json")
SINGLE = {"provider": "binance_public", "aggregation_scope": "single_venue",
          "underlying_venues": ["binance"], "timestamp": "2026-09-18T00:00:00Z",
          "source_identifier": "data/live/market-data/x.json"}


class TheFiveFieldsSurvive(unittest.TestCase):
    def test_a_loaded_aggregate_carries_every_field_section_23_lists(self):
        rec = A.load(OI)
        for f in A.REQUIRED_FIELDS:
            self.assertIn(f, rec)
        self.assertEqual(A.check(rec), [])

    def test_the_scope_comes_from_the_registry_not_the_file(self):
        """A fact about the PROVIDER, not about the bytes -- the same reasoning normalized.py gives for not
        copying fifteen provenance fields into a hundred data files."""
        with open(OI, encoding="utf-8") as fh:
            raw = json.load(fh)
        self.assertNotIn("aggregation_scope", raw)
        self.assertEqual(A.load(OI)["aggregation_scope"],
                         P.provider("coinglass")["aggregation_scope"])

    def test_a_file_that_cannot_name_its_provider_is_refused(self):
        """Defaulting to single_venue would be exactly the misattribution §23 forbids."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT) as fh:
            json.dump({"symbol": "BTCUSDT", "last_updated": "2026-09-18T00:00:00Z"}, fh)
            p = fh.name
        try:
            with self.assertRaises(ValueError) as cm:
                A.load(p)
            self.assertIn("_source", str(cm.exception))
        finally:
            os.unlink(p)

    def test_an_unclaimed_marker_is_refused_rather_than_learned(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT) as fh:
            json.dump({"_source": "some_vendor_v2", "last_updated": "2026-09-18T00:00:00Z"}, fh)
            p = fh.name
        try:
            with self.assertRaises(ValueError) as cm:
                A.load(p)
            self.assertIn("source_markers", str(cm.exception))
        finally:
            os.unlink(p)

    def test_every_coinglass_fixture_can_be_joined_to_the_registry(self):
        n = 0
        for f in sorted(glob.glob(os.path.join(ROOT, "mock", "coinglass", "*.json"))):
            rec = A.load(f)
            self.assertEqual(rec["provider"], "coinglass", f)
            self.assertEqual(A.check(rec), [], f)
            n += 1
        self.assertGreaterEqual(n, 5)


class AnAggregateIsNotOneVenuesFigure(unittest.TestCase):
    """§23: 'Never present aggregated information as if it came from one venue.'"""

    def test_the_specs_own_example_is_refused(self):
        """"Aggregated OI across venues" must not become "OKX OI" — §23, verbatim, against the live registry."""
        rec = A.load(OI)
        with self.assertRaises(ValueError) as cm:
            A.attribute(rec, "okx")
        self.assertIn("§23", str(cm.exception))
        self.assertIn("OKX OI", str(cm.exception))

    def test_no_venue_name_slips_through_on_an_aggregate(self):
        rec = A.load(OI)
        for venue in ("binance", "okx", "bybit", "aggregate"):
            with self.assertRaises(ValueError, msg=venue):
                A.attribute(rec, venue)

    def test_the_legitimate_case_still_works(self):
        """A single-venue provider's figure genuinely IS that venue's, and saying so is not a violation. A
        guard that made attribution impossible would be routed around."""
        self.assertEqual(A.attribute(SINGLE, "binance"), "binance")

    def test_a_single_venue_figure_cannot_be_given_the_wrong_venue_either(self):
        with self.assertRaises(ValueError) as cm:
            A.attribute(SINGLE, "okx")
        self.assertIn("actually came from", str(cm.exception))

    def test_the_honest_phrasing_says_aggregated_and_says_over_what(self):
        line = A.describe(A.load(OI), "open interest")
        self.assertIn("Aggregated", line)
        self.assertIn("across venues", line)
        self.assertIn("UNDECLARED", line, "a reader must not assume the venue set was checked")

    def test_a_single_venue_figure_is_described_by_its_venue(self):
        self.assertTrue(A.describe(SINGLE, "open interest").startswith("binance open interest"))


class TheRegistryIsHeldToItsOwnVocabulary(unittest.TestCase):
    """The scopes were declared by the §7 work and read by nothing, so a provider could carry a scope no one
    had defined and §23 would have had nothing to test against."""

    def test_every_provider_declares_a_known_scope(self):
        for pid in P.ALL:
            self.assertIn(P.provider(pid)["aggregation_scope"], P.AGGREGATION_SCOPES, pid)

    def test_a_provider_with_an_invented_scope_is_refused(self):
        self._reload_with(lambda d: d["providers"]["coinglass"].update(aggregation_scope="some_venues"),
                          expect="vocabulary is")

    def test_an_aggregate_naming_no_venues_at_all_is_refused(self):
        """An empty list reads as 'checked, none'. The honest value is ['UNDECLARED']."""
        self._reload_with(lambda d: d["providers"]["coinglass"].update(underlying_venues=[]),
                          expect="UNDECLARED")

    def _reload_with(self, mutate, expect):
        """Load providers.py against a mutated registry in a throwaway tree.

        Every directory a declared adapter can live in is copied, not just the two modules: providers.py also
        validates that every declared adapter exists on disk, and that check fires before this one -- so a
        partial tree tests the adapter guard instead of the scope guard, which is what the first version did.
        """
        import importlib.util
        import shutil
        import tempfile
        with open(os.path.join(ROOT, "docs", "architecture", "providers.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        mutate(data)
        with tempfile.TemporaryDirectory() as tmp:
            for d in ("scripts", "integrations"):
                if os.path.isdir(os.path.join(ROOT, d)):
                    shutil.copytree(os.path.join(ROOT, d), os.path.join(tmp, d),
                                    ignore=shutil.ignore_patterns("__pycache__", "tests"))
            os.makedirs(os.path.join(tmp, "docs", "architecture"))
            shutil.copy(os.path.join(ROOT, "docs", "architecture", "instruments.json"),
                        os.path.join(tmp, "docs", "architecture"))
            with open(os.path.join(tmp, "docs", "architecture", "providers.json"), "w") as fh:
                json.dump(data, fh)
            s = importlib.util.spec_from_file_location("prov_bad", os.path.join(tmp, "scripts", "providers.py"))
            with self.assertRaises(ValueError) as cm:
                s.loader.exec_module(importlib.util.module_from_spec(s))
        self.assertIn(expect, str(cm.exception))


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_23_lists_the_five_fields(self):
        body = spec.body(23)
        for f in ("aggregation scope", "underlying venues", "timestamp", "provider", "source identifier"):
            self.assertIn(f, body)

    def test_section_23_states_the_rule_and_its_example(self):
        body = spec.body(23)
        self.assertIn("Never present aggregated information as if it came from one venue", body)
        self.assertIn("Aggregated OI across venues", body)
        self.assertIn("OKX OI", body)


if __name__ == "__main__":
    unittest.main()
