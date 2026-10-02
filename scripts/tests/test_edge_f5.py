"""scripts/research/edge_f5.py family definition (no real history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_f5
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("edge_f5", os.path.join(ROOT, "scripts", "research", "edge_f5.py"))
F5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F5)


class Family(unittest.TestCase):
    def test_size_and_holds(self):
        self.assertEqual(len(F5.FAMILY), 3 * 9)
        self.assertEqual(F5.hold_of("E5", "XPTUSD"), 24)
        self.assertEqual(F5.hold_of("E5", "JP225"), 48)
        self.assertEqual({F5.hold_of(r, "HK50") for r in ("H7", "G9")}, {"eod"})

    def test_only_research_only_symbols_never_read_by_an_edge_family(self):
        read = set(F5.F4.SYMBOLS) | set(F5.F3.SYMBOLS) | set(F5.EC.METALS) | set(F5.EC.INDICES)
        self.assertFalse(set(F5.SYMBOLS) & read)
        import instruments
        self.assertTrue(set(F5.SYMBOLS) <= set(instruments.research_only()))

    def test_rules_are_the_survivors_detectors(self):
        self.assertIs(F5.DETECTORS["G9"], F5.F4.ev_vol_breakout)
        self.assertIs(F5.DETECTORS["H7"], F5.F3.ev_breakout_trend)
        self.assertIs(F5.DETECTORS["E5"], F5.EC.ev_fvg)


if __name__ == "__main__":
    unittest.main()
