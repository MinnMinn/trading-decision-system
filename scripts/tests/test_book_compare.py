"""scripts/research/book_sim.py compare helpers on hand-built trades (no history).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_book_compare
"""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("book_sim", os.path.join(ROOT, "scripts", "research", "book_sim.py"))
BS = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BS)


class Compare(unittest.TestCase):
    def test_daily_r_sums_per_server_day(self):
        tr = [{"server_day": "2024-01-02", "R": 1.0}, {"server_day": "2024-01-02", "R": -0.5}, {"server_day": "2024-01-03", "R": 2}]
        self.assertEqual(dict(BS.daily_r(tr)), {"2024-01-02": 0.5, "2024-01-03": 2})

    def test_corr_fills_missing_days_with_zero(self):
        a = {"d1": 1.0, "d2": -1.0, "d3": 1.0}
        self.assertAlmostEqual(BS.corr(a, dict(a)), 1.0)
        self.assertAlmostEqual(BS.corr(a, {k: -v for k, v in a.items()}), -1.0)
        self.assertIsNone(BS.corr({"d1": 1.0}, {"d2": 1.0}))
        self.assertAlmostEqual(BS.corr({"d1": 1.0, "d2": 0.0, "d3": 0.0}, {"d4": 1.0, "d5": 0.0}), -0.25)

    def test_baseline_file_names_registered_components(self):
        base = json.load(open(BS.BASELINE_PATH))
        self.assertTrue(set(base["components"]) <= set(BS.COMPONENTS))
        self.assertLessEqual(base["risk_pct"], 0.01)


if __name__ == "__main__":
    unittest.main()
