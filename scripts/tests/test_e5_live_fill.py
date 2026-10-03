"""scripts/research/e5_live_fill.py fill rules on hand-built bars (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_e5_live_fill
"""
import datetime
import importlib.util
import os
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("e5_live_fill", os.path.join(ROOT, "scripts", "research", "e5_live_fill.py"))
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
UTC = datetime.timezone.utc
REL = 0.0001                     # 1 bp relative spread at every hour


class Costs:
    med = {h: REL for h in range(24)}

    def round_trip(self, h_in, h_out, stat="median"):
        return REL


def bars(lows, edge=100.0):
    """Bars m-1, m, m+1 (indices 0..2) then the retrace bars; only L/O/C matter to the fill rules."""
    t0 = datetime.datetime(2024, 1, 3, 10, 0, tzinfo=UTC)
    n = 3 + len(lows)
    L = [99.0, 99.5, edge] + list(lows)
    O = [99.2, 99.6, edge + 0.5] + [edge + 0.3] * len(lows)
    C = [99.4, 100.4, edge + 0.6] + [edge + 0.2] * len(lows)
    H = [x + 1.0 for x in C]
    dt = [t0 + datetime.timedelta(minutes=5 * i) for i in range(n)]
    return types.SimpleNamespace(L=L, O=O, C=C, H=H, dt=dt, T=[d.strftime("%Y-%m-%dT%H:%M:%SZ") for d in dt],
                                 sday=[d.date() for d in dt])


class Fill(unittest.TestCase):
    def test_a_bid_touch_fills_research_but_not_the_live_buy_limit(self):
        s = bars([100.0, 100.05])                           # bid touches the edge exactly; the ask never gets there
        self.assertEqual(F.fill(s, Costs(), 1, +1, 100.0, "research", 1.0)[:1], (3,))
        self.assertIsNone(F.fill(s, Costs(), 1, +1, 100.0, "live", 1.0))
        self.assertEqual(F.fill(s, Costs(), 1, +1, 100.0, "plus_spread", 1.0)[0], 3)

    def test_a_deep_retrace_fills_live_at_the_edge_as_an_ask_price(self):
        s = bars([99.95])                                   # bid 5 bp below the edge: ask = 99.96 <= 100
        j, px, mode = F.fill(s, Costs(), 1, +1, 100.0, "live", 1.0)
        self.assertEqual((j, px, mode), (3, 100.0, "paid"))
        j, px, mode = F.fill(s, Costs(), 1, +1, 100.0, "research", 1.0)
        self.assertEqual((px, mode), (100.0, "spread"))

    def test_plus_spread_pays_the_edge_plus_the_placement_spread(self):
        s = bars([99.999])
        j, px, mode = F.fill(s, Costs(), 1, +1, 100.0, "plus_spread", 1.0)
        self.assertAlmostEqual(px, 100.0 + REL * 100.0)
        self.assertEqual(mode, "paid")

    def test_wider_spread_removes_live_fills(self):
        s = bars([99.985])                                  # 1.5 bp below the edge
        self.assertIsNotNone(F.fill(s, Costs(), 1, +1, 100.0, "live", 1.0))
        self.assertIsNone(F.fill(s, Costs(), 1, +1, 100.0, "live", 2.0))

    def test_shorts_use_the_research_rule_in_every_variant(self):
        s = bars([99.0])
        s.H = [101.0, 101.0, 101.0, 100.0]                  # a bear gap's near edge 100 touched by the bid high
        for rule in F.RULES:
            self.assertEqual(F.fill(s, Costs(), 1, -1, 100.0, rule, 1.0)[2], "spread")

    def test_paid_entries_carry_no_extra_spread(self):
        s = bars([99.95, 99.97, 99.98, 99.99])
        o = F.outcome(s, Costs(), 3, 100.0, +1, 2, 0.01, "paid", 1.0)
        self.assertAlmostEqual(o["net_bp"], (s.C[4] - 100.0) / 100.0 * 1e4)
        o2 = F.outcome(s, Costs(), 3, 100.0, +1, 2, 0.01, "spread", 1.0)
        self.assertAlmostEqual(o["net_bp"] - o2["net_bp"], REL * 1e4)


if __name__ == "__main__":
    unittest.main()
