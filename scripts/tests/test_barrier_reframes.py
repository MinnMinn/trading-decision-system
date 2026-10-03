"""scripts/research/barrier_reframes.py: the synthetic FTMO barrier model (no market data at all).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_barrier_reframes
"""
import importlib.util
import math
import os
import random
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("barrier_reframes",
                                              os.path.join(ROOT, "scripts", "research", "barrier_reframes.py"))
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class Barrier(unittest.TestCase):
    def test_day_low_never_above_the_open_or_the_close(self):
        rng = random.Random(1)
        for _ in range(2000):
            r, sd = rng.gauss(0, 0.01), 0.01
            low = B.day_low(r, sd, 1.0 - rng.random())
            self.assertLessEqual(low, min(0.0, r) + 1e-15)

    def test_a_sure_winner_passes_phase_one_on_the_fourth_day_not_earlier(self):
        rng = random.Random(2)
        out, n = B.phase(rng, mu=0.2, sd=1e-9, target=B.P1, days_left=50, policy="const")
        self.assertEqual((out, n), ("pass", B.MIN_DAYS))

    def test_a_minus_six_percent_day_fails_on_the_daily_limit(self):
        rng = random.Random(3)
        out, n = B.phase(rng, mu=-0.06, sd=1e-9, target=B.P1, days_left=50, policy="const")
        self.assertEqual((out, n), ("fail", 1))

    def test_dd3_scales_like_the_v2_throttle(self):
        self.assertEqual([B.scale("dd3", e, B.P1) for e in (0.0, -0.031, -0.061)], [1.0, 0.5, 0.25])
        self.assertEqual(B.scale("taper", 0.085, B.P1), 0.5)
        self.assertEqual(B.scale("const", -0.09, B.P1), 1.0)

    def test_forward_power_grows_with_n_and_shrinks_under_holm(self):
        for row in B.forward_power().values():
            self.assertLess(row["power_n100_alpha0.10"], row["power_n250_alpha0.10"])
            self.assertLess(row["power_n100_holm4_alpha0.025"], row["power_n100_alpha0.10"])
            n80 = row["n_for_80pct_power_alpha0.10"]
            snr = row["mean_R"] / row["sd_R"] * math.sqrt(n80)
            self.assertAlmostEqual(B.norm_sf(1.2816 - snr), 0.80, places=2)

    def test_zero_edge_cannot_be_safe_and_fast(self):
        c = B.cell(0.0, 0.30, "const", paths=300)
        self.assertGreater(c["fail_first"], 0.5)


if __name__ == "__main__":
    unittest.main()
