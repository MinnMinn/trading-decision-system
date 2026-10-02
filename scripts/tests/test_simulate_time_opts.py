"""C1 (red-team 2026-10-02): the harness must run `bt.simulate()` under the FIXED fund OPTS.

`BtEngine.trades_for` hands the candidate overlay to `bt.scan(opts=...)`, but `simulate()` reads the MODULE-GLOBAL
`OPTS` (the v1 baseline outside a scan), so the harness used to simulate with the v1 exit-hour min_rr admission although
the pre-registration says O1 is ON. These tests go through `BtEngine.trades_for` and `BtEngine.prop_pass` themselves
(stubbed `bt.scan`, REAL `simulate`) with a hand-built trade whose admission verdict DIFFERS between v1 (exit-hour cost)
and O1 (entry-hour cost). No real history is evaluated; no R / expectancy is computed.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_simulate_time_opts
"""
import importlib.util
import inspect
import os
import re
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import fund_stats as FS      # noqa: E402
import real_costs as RC      # noqa: E402

REAL_ARCH = os.path.join(ROOT, "docs", "architecture")
ENTRY, STOP = 2000.0, 1999.8            # a 0.2 stop distance: the spread is a visible fraction of R
T_IN = "2024-01-10T14:00:00Z"           # entry hour 14 (median spread 15 pts)
T_OUT = "2024-01-10T20:00:00Z"          # exit hour 20 (17 pts), same server day (no rollover crossing)


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search_c1", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fs = _fs()
        grids, _ = cls.fs.load_grids(REAL_ARCH)
        cls.grid = grids["ict"].runnable()

    def setUp(self):
        self.bt = self.fs._load_bt()
        self.profile = self.fs.COST_PROFILE
        self.c_entry = RC.cost_r(ENTRY, STOP, T_IN, T_IN, "XAUUSD", "long", self.profile)["total_R"]
        self.c_exit = RC.cost_r(ENTRY, STOP, T_IN, T_OUT, "XAUUSD", "long", self.profile)["total_R"]
        self.assertLess(self.c_entry, self.c_exit)       # the fixture means something only if the exit hour costs more
        self.min_rr = self.bt._OPTS_BASE["min_rr"]
        # strictly between "entry-only admission floor" and "exit-hour admission floor"
        self.r_planned = self.min_rr + (self.c_entry + self.c_exit) / 2
        self.trade = {"symbol": "XAUUSD", "tf": "15m", "side": "long", "entry": ENTRY, "stop": STOP, "target": 2003.0,
                      "entry_time": T_IN, "exit_time": T_OUT, "outcome": "win", "R": 2.0, "R_planned": self.r_planned,
                      "event": "XAUUSD-long-ict-s1-m1"}
        self.scan_calls = []

    def _engine(self, trades):
        eng = object.__new__(self.fs.BtEngine)
        eng.grid, eng.method, eng.tf, eng.symbols, eng.bt = self.grid, "ICT", "15m", ["XAUUSD"], self.bt
        eng._raw, eng._done, eng._admission, eng._edge, eng._part = {}, {}, {}, {}, {}
        eng._adx = {"XAUUSD": FS.adx_index([])}
        eng._d1, eng._d1_series = {"XAUUSD": None}, {"XAUUSD": None}      # no D1 series: no regime value (fails closed)
        eng._last = {"XAUUSD": "2100-01-01T00:00:00Z"}
        eng._dev_start_ts = None
        eng.workers = 1

        def scan(sym, tf, only=None, opts=None):
            self.scan_calls.append(opts)
            return {"trades": {"ICT": [dict(t) for t in trades]}}
        self.bt.scan = scan
        return eng


class HarnessRunsSimulateUnderO1(_Base):
    def test_control_v1_global_opts_refuse_the_trade_o1_admits_it(self):
        """What the OLD harness did: simulate() under the process-global OPTS (v1) refuses this trade."""
        self.assertIs(self.bt.OPTS["fx_admission_entry_cost"], False)
        _, _, taken = self.bt.simulate([dict(self.trade)], 0.0, cost_profile=self.profile)
        self.assertEqual(taken, [])
        sim = dict(self.bt._OPTS_BASE, **self.fs.fixed_opts())
        old, self.bt.OPTS = self.bt.OPTS, sim
        try:
            _, _, taken = self.bt.simulate([dict(self.trade)], 0.0, cost_profile=self.profile)
        finally:
            self.bt.OPTS = old
        self.assertEqual(len(taken), 1)

    def test_trades_for_admits_the_o1_trade_and_restores_opts(self):
        eng = self._engine([self.trade])
        before = self.bt.OPTS
        taken = eng.trades_for(self.grid.baseline())
        self.assertEqual([t["event"] for t in taken], [self.trade["event"]])   # v1 admission would have returned []
        self.assertIs(self.bt.OPTS, before)                                     # restored (same object)
        self.assertIs(before["fx_admission_entry_cost"], False)
        self.assertIs(self.scan_calls[0]["fx_admission_entry_cost"], True)      # the scan overlay still carries O1

    def test_o1_refuses_a_trade_below_the_entry_cost_floor_whatever_the_exit_hour(self):
        t = dict(self.trade, R_planned=self.min_rr + self.c_entry - 0.05)
        eng = self._engine([t])
        self.assertEqual(eng.trades_for(self.grid.baseline()), [])

    def test_admission_rows_use_the_same_entry_hour_cost_as_simulate(self):
        eng = self._engine([self.trade])
        eng.trades_for(self.grid.baseline())
        rows = eng._admission[self.fs.FS.CountingSource._key(self.grid.baseline())]
        self.assertAlmostEqual(rows[0]["fee_R"], self.c_entry, places=12)
        st = eng.admission_stats(self.grid.baseline())
        self.assertEqual((st["candidates"], st["refused_min_rr"]), (1, 0))      # v1's exit-hour cost would say refused

    def test_opts_restored_when_simulate_raises(self):
        eng = self._engine([self.trade])
        before = self.bt.OPTS
        with mock.patch.object(self.bt, "simulate", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                eng.trades_for(self.grid.baseline())
        self.assertIs(self.bt.OPTS, before)

    def test_prop_pass_simulates_under_the_fixed_set(self):
        eng = self._engine([self.trade])
        seen = []
        real = self.bt.simulate

        def spy(*a, **k):
            seen.append({x: self.bt.OPTS[x] for x in self.fs.SIMULATE_TIME_OPTS})
            out = real(*a, **k)
            seen[-1]["n_taken"] = len(out[2])
            return out
        with mock.patch.object(self.bt, "simulate", side_effect=spy):
            eng.prop_pass([dict(self.trade)])
        self.assertEqual(len(seen), 1)
        self.assertIs(seen[0]["fx_admission_entry_cost"], True)
        self.assertEqual(seen[0]["min_rr"], self.min_rr)
        self.assertEqual(seen[0]["fx_b_exit"], self.bt._OPTS_BASE["fx_b_exit"])
        self.assertEqual(seen[0]["n_taken"], 1)                                  # the O1 trade was admitted
        self.assertIs(self.bt.OPTS["fx_admission_entry_cost"], False)           # and OPTS is back to the baseline


class DeclaredFixedSet(_Base):
    def test_declared_set_equals_what_simulate_and_its_callees_read(self):
        """Fails loudly if a new OPTS key is ever read at simulate time (a V key would make simulate() fold-dependent)."""
        fns = [self.bt.simulate, self.bt.planned_risk_refusal, self.bt._risk_scale, self.bt._account_stop,
               self.bt._venue_for_symbol]
        keys = set()
        for fn in fns:
            src = inspect.getsource(fn)
            src = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
            src = re.sub(r'"""[\s\S]*?"""', "", src)             # docstrings describe keys, they do not read them
            keys |= set(re.findall(r'OPTS\[\s*["\'](\w+)["\']\s*\]', src))
            keys |= set(re.findall(r'OPTS\.get\(\s*["\'](\w+)["\']', src))
        self.assertEqual(keys, set(self.fs.SIMULATE_TIME_OPTS))
        self.assertNotIn("mgmt", keys)                              # read by walk() (scan time), not by simulate()
        self.assertIn("mgmt", inspect.getsource(self.bt.walk))

    def test_the_fixed_context_is_the_declared_one(self):
        sim = self.fs.simulate_time_opts(self.bt, self.fs.fixed_opts())
        self.assertIs(sim["fx_admission_entry_cost"], True)
        self.assertEqual(sim["min_rr"], self.bt._OPTS_BASE["min_rr"])
        self.assertEqual(sim["fx_b_exit"].split("|")[2], "floor")

    def test_a_v_key_that_becomes_simulate_time_is_refused(self):
        fs = self.fs
        with self.assertRaises(fs.GridRefused):
            fs.simulate_time_opts(self.bt, dict(fs.fixed_opts(), min_rr=1.0))
        with self.assertRaises(fs.GridRefused):
            fs.simulate_time_opts(self.bt, dict(fs.fixed_opts(), fx_admission_entry_cost=False))
        with self.assertRaises(fs.GridRefused):
            fs.simulate_time_opts(self.bt, dict(fs.fixed_opts(), fx_b_exit="-2.0|H|no_floor"))
        fs.simulate_time_opts(self.bt, dict(fs.fixed_opts(), fx_b_exit="-2.0|H|floor"))      # a declared B-EXIT value is fine

    def test_every_declared_b_exit_value_has_the_floor_token(self):
        for g in (self.grid,):
            for it in g.items:
                if it["key"] == "fx_b_exit":
                    self.assertTrue(all(v.split("|")[2] == "floor" for v in it["values"]), it["values"])

    def test_a_baseline_without_o1_in_the_fixed_set_is_refused(self):
        fs = self.fs
        with mock.patch.object(fs, "fixed_opts", return_value={"flat_before_rollover": True,
                                                                "rollover_provider": "mt5_bridge_ftmo"}):
            with self.assertRaises(fs.GridRefused):
                fs.simulate_time_opts(self.bt, None)


if __name__ == "__main__":
    unittest.main()
