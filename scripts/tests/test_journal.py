"""scripts/journal.py -- B2 (docs/plans/2026-09-18-close-feature-gaps.md §0.6): expectation records must
survive the round trip from the pilot log through trades/*.md frontmatter into trades/index.jsonl, unmodified.
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import expectation as X


def load(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def sample_expectations():
    r1 = X.create("structural_objective", "ict", "ict long entry 77000 -> 78000",
                  path=[X.leg("before_entry", 77000.0, "vùng vào lệnh"), X.leg("entry_area", 77000.0, "entry"),
                        X.leg("after_entry", 78000.0, "target_1")],
                  invalidation=X.invalidation("stop", 76500.0, owner="ict"), created_at="2026-09-17T18:00:00Z")
    r2 = X.create("trading_range_objective", "wyckoff", "wyckoff long entry 77000 -> 78000",
                  path=[X.leg("before_entry", 77000.0, "vùng vào lệnh"), X.leg("entry_area", 77000.0, "entry"),
                        X.leg("after_entry", 78000.0, "target_1")],
                  invalidation=X.invalidation("stop", 76500.0, owner="wyckoff"), created_at="2026-09-17T18:00:00Z")
    return [X.to_json(r1), X.to_json(r2)]


class FrontmatterRoundtrip(unittest.TestCase):
    """The minimal-YAML frontmatter (scripts/journal.py _scalar/_emit) must round-trip a list of JSON OBJECTS,
    not just a list of scalars -- expectation records nest a dict (`original`) inside a list."""

    def setUp(self):
        self.j = load("journal.py")

    def test_list_of_dicts_round_trips_exactly(self):
        exps = sample_expectations()
        dumped = self.j.dump_frontmatter({"id": "t1", "expectations": exps})
        fm, _ = self.j.parse_frontmatter(dumped)
        self.assertEqual(fm["expectations"], exps)

    def test_existing_flat_list_fields_are_unaffected(self):
        dumped = self.j.dump_frontmatter({"id": "t1", "dimensions_used": ["wyckoff", "ict"], "targets": [1.0, 2.5]})
        fm, _ = self.j.parse_frontmatter(dumped)
        self.assertEqual(fm["dimensions_used"], ["wyckoff", "ict"])
        self.assertEqual(fm["targets"], [1.0, 2.5])

    def test_empty_expectations_round_trips_to_empty_list(self):
        dumped = self.j.dump_frontmatter({"id": "t1", "expectations": []})
        fm, _ = self.j.parse_frontmatter(dumped)
        self.assertEqual(fm["expectations"], [])


class SyncPilotCarriesExpectations(unittest.TestCase):
    def setUp(self):
        self.j = load("journal.py")
        self.tmp = tempfile.mkdtemp()
        self.trades_dir = os.path.join(self.tmp, "trades")
        os.makedirs(self.trades_dir, exist_ok=True)
        self.j.TRADES = self.trades_dir
        self.j.INDEX = os.path.join(self.trades_dir, "index.jsonl")
        self.log_path = os.path.join(self.tmp, "top20-log.jsonl")
        self.j.PILOT["futures-top20"] = self.log_path

    def _write_log(self, exps):
        entry = {"kind": "entry", "symbol": "BTCUSDT", "opened_at": "2026-09-17T18:00:00Z", "side": "LONG",
                  "entry": 77000.0, "stop": 76500.0, "tp": 78000.0, "qty": "0.01", "entry_order": 1001,
                  "risk_usd": 10.0, "expectations": exps}
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def test_sync_pilot_writes_expectations_into_the_trade_file(self):
        exps = sample_expectations()
        self._write_log(exps)
        self.j.sync_pilot("futures-top20")
        trades = self.j.all_trades()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["expectations"], exps)

    def test_build_index_keeps_expectations(self):
        exps = sample_expectations()
        self._write_log(exps)
        self.j.sync_pilot("futures-top20")
        rows = self.j.build_index()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["expectations"], exps)
        # and the persisted index.jsonl itself, not just the in-memory rows
        with open(self.j.INDEX, encoding="utf-8") as f:
            persisted = [json.loads(l) for l in f if l.strip()]
        self.assertEqual(persisted[0]["expectations"], exps)

    def test_no_expectations_in_log_writes_an_empty_list(self):
        self._write_log([])
        self.j.sync_pilot("futures-top20")
        trades = self.j.all_trades()
        self.assertEqual(trades[0]["expectations"], [])


if __name__ == "__main__":
    unittest.main()


class DrillRowsAreNotEvidence(unittest.TestCase):
    """plan §0.11: a drill trade is a real order on fake money placed to prove the path; it never counts."""

    @classmethod
    def setUpClass(cls):
        global J
        J = load("journal.py")

    def test_closed_real_excludes_drill_rows(self):
        rows = [{"status": "CLOSED", "r_multiple": 2.0}, {"status": "CLOSED", "r_multiple": 2.0, "drill": True},
                {"status": "CLOSED", "r_multiple": 2.0, "rehearsal_mode": True}]
        self.assertEqual(len(J.closed_real(rows)), 1)

    def test_outcomes_ingest_skips_drill_rows_and_drill_signals(self):
        import outcomes as O
        self.assertIsNone(O._from_trade({"status": "CLOSED", "r_multiple": -1.0, "drill": True, "instrument": "BTCUSDT"}, "t"))
        self.assertIsNotNone(O._from_trade({"status": "CLOSED", "r_multiple": -1.0, "instrument": "BTCUSDT"}, "t"))
        self.assertIsNone(O._from_log_row({"kind": "signal", "ok": False, "reasons": ["x: y"], "drill": True, "t": "2026-01-01T00:00:00Z"}, "t"))
        self.assertIsNotNone(O._from_log_row({"kind": "signal", "ok": False, "reasons": ["x: y"], "t": "2026-01-01T00:00:00Z"}, "t"))
