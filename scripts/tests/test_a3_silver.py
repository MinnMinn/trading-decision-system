"""scripts/research/a3_silver.py on hand-built trades (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_a3_silver
(docs/plans/2026-10-04-a3-silver-preregistration.md)
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("a3_silver", os.path.join(ROOT, "scripts", "research", "a3_silver.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
UTC = datetime.timezone.utc


def daily(R, n, c, start=datetime.datetime(2020, 1, 6, tzinfo=UTC)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            e, x = d.replace(hour=10), d.replace(hour=12)
            out.append({"entry": e, "exit": x, "entry_day": e.date().isoformat(), "exit_day": x.date().isoformat(),
                        "R": R, "mae": min(0.0, R), "c": c})
        d += datetime.timedelta(days=1)
    return out


class Decision(unittest.TestCase):
    def test_every_condition(self):
        self.assertTrue(A.decide(0.1, -0.1, 0.0, 0.05, 1.1)["PROPOSED"])
        self.assertFalse(A.decide(-0.01, -0.1, 0.0, 0.05, 1.1)["PROPOSED"])
        self.assertFalse(A.decide(0.1, -0.1, 0.11, 0.05, 1.1)["PROPOSED"])
        self.assertFalse(A.decide(0.1, -0.1, 0.0, 0.11, 1.1)["PROPOSED"])
        self.assertFalse(A.decide(0.1, -0.1, 0.0, 0.05, 1.21)["PROPOSED"])
        self.assertTrue(A.decide(0.1, 0.2, 0.0, 0.05, 1.1)["variance_not_edge"])


class AlignedBootstrap(unittest.TestCase):
    def test_identical_books_give_identical_results(self):
        v = daily(0.5, 400, "X")
        out = A.bootstrap_books({"a": v, "b": [dict(t) for t in v]}, A.VS.pol("realised"), paths=30, seed=1)
        self.assertEqual(out["a"], out["b"])

    def test_a_losing_extra_component_lowers_the_value(self):
        good = daily(0.5, 400, "X")
        bad = good + daily(-0.3, 400, "Y")
        bad.sort(key=lambda t: (t["entry"], t["c"]))
        out = A.bootstrap_books({"v3": good, "v3+ag": bad}, A.VS.pol("realised"), paths=30, seed=1)
        self.assertLess(out["v3+ag"]["E_net_pct"], out["v3"]["E_net_pct"])


if __name__ == "__main__":
    unittest.main()
