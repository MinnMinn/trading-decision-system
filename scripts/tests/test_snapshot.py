"""CLAUDE.md §10 -- a research result must identify the data it was computed from.

Before this, `data/history/stability/crypto-live.json` carried exactly one top-level key above sixty rows of
metrics: `generated`, a date. No provider, no symbols, no timeframes, no input files, no code version. So
"re-run this and see whether it still holds" had no defined meaning, and the 3%-vs-1% risk-ceiling drift was
expensive to reason about afterwards precisely because no result said which ceiling produced it.

Two findings came out of building this, and both are pinned below:

  1. **The marker list was incomplete.** `by_source_marker` was built from a scan of `data/live/` and
     `mock/`, which found two markers. `data/history/` -- which every backtest reads -- carried two more.
     Snapshots of research data came back `provider: None` until the snapshot itself surfaced it.
  2. **The CFD backtests run on a different instrument than the CFD system trades.** The history is
     front-month futures from Yahoo (`GC=F`, `SI=F`, `CL=F`, `BZ=F`); the venue trades broker CFDs. The
     fetcher's docstring said so and required every report built on it to say so; nothing enforced that, the
     files are named `ohlcv.XAUUSD.*`, and the provider was undeclared. Now the snapshot reports
     `market_type: FUTURES` against a live `CFD`, and `research_data_mismatch()` makes it assertable.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import normalized as N
import providers as P
import snapshot


class CodeVersion(unittest.TestCase):
    def test_it_reports_a_sha_and_whether_the_tree_is_dirty(self):
        v = snapshot.code_version()
        for field in ("git_sha", "dirty", "modified_files"):
            self.assertIn(field, v)
        self.assertIsInstance(v["dirty"], bool)

    def test_a_dirty_tree_says_it_is_not_reproducible(self):
        """Asserted on the FLAG, not on cleanliness: this repo's tree is usually dirty mid-change, and a test
        demanding a clean tree would simply get disabled. What must hold is that dirtiness is disclosed."""
        v = snapshot.code_version()
        if v["dirty"]:
            self.assertIn("NOT reproducible", v["dirty_note"])
        else:
            self.assertNotIn("dirty_note", v)

    def test_an_unavailable_sha_is_none_not_invented(self):
        self.assertTrue(snapshot.code_version()["git_sha"] is None
                        or len(snapshot.code_version()["git_sha"]) == 40)


class SourceMarkers(unittest.TestCase):
    """Finding 1: the marker list was incomplete, and the history store was the half that was missed."""

    def test_every_marker_present_in_the_tree_resolves_to_a_provider(self):
        import glob
        unresolved = {}
        for path in glob.glob(os.path.join(ROOT, "data", "**", "*.json"), recursive=True):
            try:
                with open(path, encoding="utf-8") as fh:
                    d = json.load(fh)
            except (OSError, ValueError):
                continue
            if not isinstance(d, dict) or "candles" not in d:
                continue
            marker = d.get("_source")
            if marker and P.by_source_marker(marker) is None:
                unresolved.setdefault(marker, os.path.relpath(path, ROOT))
        self.assertEqual(unresolved, {}, (
            f"data files carry `_source` markers no provider declares: {unresolved}. Declare the provider in "
            f"docs/architecture/providers.json -- an unresolved marker means a snapshot of that data reports "
            f"provider: None, which is how the Yahoo futures history went unnoticed."))

    def test_one_provider_may_declare_several_markers(self):
        self.assertEqual(P.by_source_marker("binance_public_rest_live"), "binance_public")
        self.assertEqual(P.by_source_marker("binance_public_rest_history"), "binance_public")

    def test_a_marker_family_matches_by_prefix(self):
        for ticker in ("GC=F", "SI=F", "CL=F", "BZ=F"):
            self.assertEqual(P.by_source_marker(f"yahoo_finance_{ticker}_research_only"), "yahoo_finance")

    def test_an_unknown_marker_is_none_not_a_guess(self):
        self.assertIsNone(P.by_source_marker("some_new_vendor_v2"))


class ResearchOnlyIsItsOwnThing(unittest.TestCase):
    """Finding 2. `research_only` is neither staleness nor a mock, and collapsing it into either loses the
    fact that matters: a backtest on it is evidence about a different instrument."""

    def test_yahoo_is_connected_and_research_only(self):
        self.assertTrue(P.is_live("yahoo_finance"), "it is genuinely connected; this is not a staleness flag")
        self.assertTrue(P.is_research_only("yahoo_finance"))
        self.assertFalse(P.is_research_only("binance_public"))

    def test_it_is_not_an_execution_provider(self):
        self.assertNotIn("yahoo_finance", P.for_role("execution", "cfd"))

    def test_the_cfd_research_instrument_differs_from_the_traded_one(self):
        m = P.research_data_mismatch("cfd")
        self.assertIsNotNone(m, "the futures-vs-CFD mismatch stopped being reported")
        self.assertEqual(m["research_market_type"], ["FUTURES"])
        self.assertEqual(m["execution_market_type"], ["CFD"])
        self.assertTrue(m["differences"], "the provider must name HOW the instruments differ, not just that")

    def test_the_crypto_research_store_is_the_same_instrument_it_analyses(self):
        """Contrast case: crypto history is the same SPOT series as live, so no research mismatch. The
        SPOT-vs-PERPETUAL execution mismatch is a separate finding (§20.1) and a separate function."""
        self.assertIsNone(P.research_data_mismatch("crypto"))
        self.assertIsNotNone(P.data_execution_mismatch("crypto"))


class DatasetSnapshot(unittest.TestCase):
    def snap(self):
        return snapshot.dataset_snapshot([("BTCUSDT", "1D")], base=os.path.join(ROOT, "data", "history"))

    def test_it_carries_the_identity_fields_section_10_asks_for(self):
        try:
            s = self.snap()
        except FileNotFoundError:
            self.skipTest("no BTCUSDT 1D history on disk")
        for field in ("snapshot_format", "snapshot_id", "created_at", "code_version",
                      "preprocessing_version", "series"):
            self.assertIn(field, s)
        row = s["series"][0]
        for field in ("symbol", "canonical_symbol", "market", "market_type", "timeframe", "provider",
                      "source_venue", "aggregation_scope", "underlying_venues", "source_identifier",
                      "retrieval_state", "bars", "first_open", "last_open", "sha256"):
            self.assertIn(field, row)

    def test_the_data_version_is_a_content_hash_not_a_path(self):
        """§10 asks for a 'data version'. A path is not one: the fetcher overwrites in place, so a result
        citing a path cites a file that has since changed."""
        try:
            s = self.snap()
        except FileNotFoundError:
            self.skipTest("no history on disk")
        self.assertRegex(s["series"][0]["sha256"], r"^[0-9a-f]{64}$")

    def test_identical_inputs_share_a_snapshot_id(self):
        try:
            a, b = self.snap(), self.snap()
        except FileNotFoundError:
            self.skipTest("no history on disk")
        self.assertEqual(a["snapshot_id"], b["snapshot_id"])

    def test_different_inputs_do_not_share_an_id(self):
        base = os.path.join(ROOT, "data", "history")
        try:
            one = snapshot.dataset_snapshot([("BTCUSDT", "1D")], base=base)
            two = snapshot.dataset_snapshot([("BTCUSDT", "1D"), ("ETHUSDT", "1D")], base=base)
        except FileNotFoundError:
            self.skipTest("no history on disk")
        self.assertNotEqual(one["snapshot_id"], two["snapshot_id"])

    def test_the_provenance_is_not_recomputed_a_second_way(self):
        """The snapshot builds on normalized.load() rather than re-reading the file, so provider/venue/
        market_type/canonical_symbol have one implementation. A second answer to the same question is how the
        two drift."""
        try:
            s = self.snap()
        except FileNotFoundError:
            self.skipTest("no history on disk")
        direct = N.load("BTCUSDT", "1D", base=os.path.join(ROOT, "data", "history"))["provenance"]
        row = s["series"][0]
        self.assertEqual(row["provider"], direct["provider"])
        self.assertEqual(row["market_type"], direct["market_type"])
        self.assertEqual(row["canonical_symbol"], direct["canonical_symbol"])

    def test_preprocessing_version_is_recorded(self):
        """So a re-run can tell 'the data changed' from 'our reading of the data changed'."""
        try:
            s = self.snap()
        except FileNotFoundError:
            self.skipTest("no history on disk")
        self.assertEqual(s["preprocessing_version"], N.SNAPSHOT_INPUTS_VERSION)


class WiredIntoTheResearchRun(unittest.TestCase):
    def test_the_stability_report_writes_a_snapshot_beside_its_rows(self):
        """Additive on purpose: rank-setups.py reads `rows` and must keep working."""
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("dataset_snapshot", src)
        self.assertIn("rows=rows", src, "the rows key must survive for rank-setups.py")

    def test_a_snapshot_failure_is_recorded_not_swallowed(self):
        """A research run must not fail because a snapshot could not be taken -- and must never silently
        claim one either."""
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("snapshot_error", src)


if __name__ == "__main__":
    unittest.main()
