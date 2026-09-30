"""O1 (owner-approved 2026-09-30; docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md): the new OPTS key
`fx_admission_entry_cost`. simulate()'s min_rr admission used real_costs.cost_r(entry_time, exit_time), which
includes the EXIT-hour half-spread and the per-night swap, so whether a trade was admitted depended on when it
exited (a look-ahead against CLAUDE.md §8 / plan §37).

Default False = v1, byte-identical. True = admission uses ONLY costs knowable at the entry decision (entry-hour
spread on both legs, no swap, commission); the REPORTED net R keeps the real entry+exit costs.

No R / expectancy of any real evaluation is computed here: every trade is a hand-built dict.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import real_costs as RC  # noqa: E402

FTMO = "ftmo_demo_2026_09"
ENTRY, STOP = 2000.0, 1999.5          # 0.025% stop distance: the spread is a visible fraction of R
T_IN = "2024-01-10T14:00:00Z"         # entry hour 14 (median spread 15 pts)
EXIT_NEAR = "2024-01-10T15:00:00Z"    # same day, hour 15
EXIT_WIDE = "2024-01-10T22:00:00Z"    # hour 22 (median spread 21 pts) -- and the server-midnight rollover


def _bt():
    spec = importlib.util.spec_from_file_location("bt_o1", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cost(exit_time):
    return RC.cost_r(ENTRY, STOP, T_IN, exit_time, "XAUUSD", "long", FTMO)["total_R"]


class AdmissionEntryCost(unittest.TestCase):
    def setUp(self):
        self.bt = _bt()
        self.c_entry = RC.cost_r(ENTRY, STOP, T_IN, T_IN, "XAUUSD", "long", FTMO)["total_R"]
        self.c_near, self.c_wide = _cost(EXIT_NEAR), _cost(EXIT_WIDE)
        # the fixture only means something if the exit hour really costs more than the entry-only estimate
        self.assertLess(self.c_entry, self.c_wide)
        # R_planned sits strictly between the entry-only cost and the wide-exit cost (plus the floor)
        self.r_planned = self.bt.OPTS["min_rr"] + (self.c_entry + self.c_wide) / 2

    def tearDown(self):
        self.bt.reset_opts()

    def _trade(self, exit_time, r_planned=None):
        return {"symbol": "XAUUSD", "side": "long", "entry": ENTRY, "stop": STOP, "target": 2003.0,
                "entry_time": T_IN, "exit_time": exit_time, "R": 2.0,
                "R_planned": self.r_planned if r_planned is None else r_planned, "event": "e1"}

    def _sim(self, trade, on):
        self.bt.OPTS["fx_admission_entry_cost"] = on
        return self.bt.simulate([trade], 0.0, cost_profile=FTMO)

    def test_key_registered_default_false(self):
        self.assertIs(self.bt._OPTS_BASE["fx_admission_entry_cost"], False)
        self.assertIs(self.bt.OPTS["fx_admission_entry_cost"], False)

    def test_default_equals_v1_and_v1_refuses_the_wide_exit_trade(self):
        """OFF (explicit) is byte-equal to the key never having been set; v1 refuses the wide-exit trade."""
        for exit_time in (EXIT_NEAR, EXIT_WIDE):
            base = self.bt.simulate([self._trade(exit_time)], 0.0, cost_profile=FTMO)   # key untouched
            off = self._sim(self._trade(exit_time), False)
            self.assertEqual(repr(base), repr(off))
        _, _, taken = self._sim(self._trade(EXIT_WIDE), False)
        self.assertEqual(taken, [])                                    # refused because of the EXIT hour cost

    def test_on_admits_the_trade_v1_refuses(self):
        _, _, taken = self._sim(self._trade(EXIT_WIDE), True)
        self.assertEqual(len(taken), 1)

    def test_on_admission_is_independent_of_the_exit_time(self):
        """The look-ahead itself: only the exit time / exit-hour spread changes; admission must not."""
        for r_planned in (self.r_planned, self.bt.OPTS["min_rr"] + self.c_entry - 0.05):   # admitted / refused
            verdicts = {len(self._sim(self._trade(x, r_planned), True)[2]) for x in (EXIT_NEAR, EXIT_WIDE,
                                                                                 "2024-01-12T03:00:00Z")}
            self.assertEqual(len(verdicts), 1, r_planned)
        self.assertEqual(len(self._sim(self._trade(EXIT_WIDE, self.bt.OPTS["min_rr"] + self.c_entry - 0.05),
                                       True)[2]), 0)

    def test_reported_net_r_still_uses_the_real_exit_costs(self):
        (_, _, near), (_, _, wide) = (self._sim(self._trade(x), True) for x in (EXIT_NEAR, EXIT_WIDE))
        self.assertAlmostEqual(near[0]["net_R"], round(2.0 - self.c_near, 3), places=9)
        self.assertAlmostEqual(wide[0]["net_R"], round(2.0 - self.c_wide, 3), places=9)
        self.assertNotEqual(near[0]["net_R"], wide[0]["net_R"])

    def test_flat_fee_path_is_unaffected_by_the_key(self):
        t = dict(self._trade(EXIT_WIDE), symbol="BTCUSDT")
        self.bt.OPTS["fx_admission_entry_cost"] = False
        off = self.bt.simulate([t], 0.0005)
        self.bt.OPTS["fx_admission_entry_cost"] = True
        on = self.bt.simulate([t], 0.0005)
        self.assertEqual(repr(off), repr(on))


if __name__ == "__main__":
    unittest.main()
