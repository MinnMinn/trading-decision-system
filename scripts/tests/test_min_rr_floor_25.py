"""Owner decisions 2026-09-30: (1) the planned R:R floor at entry is 2.5 for BOTH methods, backtest and live, NET of
fees; (2) the ICT V-grid B-EXIT value `no_floor` is no longer declared by the grid, and the fund-search declaration
pins the effective floor so a change is refused as drift. Hand-built trades only: no real-data evaluation.
"""
import importlib.util
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import real_costs as RC  # noqa: E402
import trading_env  # noqa: E402

FTMO = "ftmo_demo_2026_09"
EPS = 1e-9


def _load(fname, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FloorValue(unittest.TestCase):
    def test_reader_returns_2_5(self):
        self.assertEqual(trading_env.min_rr(), 2.5)

    def test_backtest_and_live_share_the_same_reader_value(self):
        bt = _load("backtest-methods.py", "bt_mrr25")
        self.assertEqual(bt.MIN_RR, 2.5)
        self.assertEqual(bt.OPTS["min_rr"], 2.5)
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("MIN_RR = bt.MIN_RR", src)      # live floor == the backtest's == trading_env.min_rr()


class SimulateAdmission(unittest.TestCase):
    """simulate() refuses a trade whose R_planned is 2.4 NET of fees and admits 2.5 net, for both methods."""

    EVENTS = {"ICT": "BTCUSDT-long-ict-2024-01-10T10:00:00Z-2024-01-10T12:00:00Z",
              "WYCKOFF-BOOK": "BTCUSDT-long-book-2024-01-10T10:00:00Z"}

    def setUp(self):
        self.bt = _load("backtest-methods.py", "bt_mrr25_sim")

    def tearDown(self):
        self.bt.reset_opts()

    @staticmethod
    def _trade(event, r_planned, symbol="BTCUSDT", entry=100.0, stop=99.0, t_in="2024-01-10T14:00:00Z",
               t_out="2024-01-10T15:00:00Z"):
        return {"symbol": symbol, "side": "long", "entry": entry, "stop": stop, "target": entry + 3 * (entry - stop),
                "entry_time": t_in, "exit_time": t_out, "R": 2.0, "R_planned": r_planned, "event": event}

    def test_flat_fee_path_both_methods(self):
        fee_pct = 0.0005
        fee_R = 2 * fee_pct / (1.0 / 100.0)
        for method, ev in self.EVENTS.items():
            with self.subTest(method=method):
                refused = self.bt.simulate([self._trade(ev, 2.4 + fee_R)], fee_pct)[2]
                admitted = self.bt.simulate([self._trade(ev, 2.5 + fee_R + EPS)], fee_pct)[2]
                self.assertEqual(refused, [], "2.4R net must be refused")
                self.assertEqual(len(admitted), 1, "2.5R net must be admitted")

    def test_gross_2_5_is_refused_once_fees_are_charged(self):
        """The floor is net: a GROSS 2.5 plan does not clear it (the 2026-09-18 convention, unchanged)."""
        for ev in self.EVENTS.values():
            self.assertEqual(self.bt.simulate([self._trade(ev, 2.5)], 0.0005)[2], [])

    def test_real_cost_path_both_methods(self):
        entry, stop = 2000.0, 1999.5
        t_in, t_out = "2024-01-10T14:00:00Z", "2024-01-10T15:00:00Z"
        c_full = RC.cost_r(entry, stop, t_in, t_out, "XAUUSD", "long", FTMO)["total_R"]
        c_entry = RC.cost_r(entry, stop, t_in, t_in, "XAUUSD", "long", FTMO)["total_R"]
        for method, ev in self.EVENTS.items():
            for entry_cost, adm in ((False, c_full), (True, c_entry)):
                with self.subTest(method=method, admission_entry_cost=entry_cost):
                    self.bt.OPTS["fx_admission_entry_cost"] = entry_cost

                    def mk(rp):
                        return self._trade(ev.replace("BTCUSDT", "XAUUSD"), rp, "XAUUSD", entry, stop, t_in, t_out)
                    self.assertEqual(self.bt.simulate([mk(2.4 + adm)], 0.0, cost_profile=FTMO)[2], [])
                    self.assertEqual(len(self.bt.simulate([mk(2.5 + adm + EPS)], 0.0, cost_profile=FTMO)[2]), 1)

    def test_a_2_0_net_trade_the_old_floor_admitted_is_now_refused(self):
        fee_R = 2 * 0.0005 / 0.01
        for ev in self.EVENTS.values():
            self.assertEqual(self.bt.simulate([self._trade(ev, 2.0 + fee_R + EPS)], 0.0005)[2], [])


class GridNoLongerDeclaresNoFloor(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json"), encoding="utf-8") as fh:
            self.grid = json.load(fh)
        self.exit = [i for i in self.grid["items"] if i["id"] == "B-EXIT"][0]

    def test_no_floor_value_is_gone_and_counts_are_recomputed(self):
        self.assertFalse(any("no_floor" in v for v in self.exit["values"]))
        self.assertNotIn("no_floor", self.exit["components"]["floor"])
        self.assertEqual(len(self.exit["values"]), 12)          # 3 targets x 4 time stops x 1 floor token
        non_baseline = sum(len(i["values"]) - 1 for i in self.grid["items"])
        self.assertEqual(non_baseline, 27)
        self.assertEqual(1 + non_baseline + 1, 29)
        self.assertEqual(self.grid["n"], 29)

    def test_engine_still_accepts_the_token_but_the_grid_refuses_it(self):
        scan = _load("ict-scan.py", "ict_mrr25")
        self.assertIn("-2.0|H|no_floor", scan.V_ICT["fx_b_exit"])     # engine code path kept
        fs = _load("fund-search.py", "fs_mrr25")
        g = fs.FS.load_grid(os.path.join(ROOT, "docs", "architecture", "v-grid-ict.json"))
        with self.assertRaises(fs.GridRefused):
            fs.build_overlay(g, {"B-EXIT": "-2.0|H|no_floor"})


class DeclarationPinsMinRR(unittest.TestCase):
    def setUp(self):
        self.fs = _load("fund-search.py", "fs_mrr25_decl")

    def _cfg(self):
        plan = {"embargo": {"h_multiple": 2}, "grids": {}, "cells": [], "cells_file": {"sha256": "0" * 64, "warmup_days": 14},
                "cost_profile": self.fs.COST_PROFILE, "cost_profile_pin": {}}
        return self.fs.evaluation_config(plan), plan

    def test_evaluation_config_carries_the_effective_floor(self):
        cfg, _ = self._cfg()
        self.assertEqual(cfg["min_rr"], 2.5)

    def test_changing_min_rr_is_drift(self):
        cfg, plan = self._cfg()
        decl = {"code": self.fs.code_fingerprint(), "evaluation_config": cfg}
        self.assertEqual([d for d in self.fs.detect_drift(decl, plan) if "min_rr" in d], [])
        with mock.patch.object(self.fs._TE, "min_rr", return_value=2.0):
            drift = self.fs.detect_drift(decl, plan)
            self.assertTrue(any(d.startswith("evaluation_config.min_rr") for d in drift), drift)
            with self.assertRaises(SystemExit):
                self.fs.check_drift(decl, plan, allow_drift=False)


if __name__ == "__main__":
    unittest.main()
