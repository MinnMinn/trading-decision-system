"""scripts/research/personal_account.py on hand-built trades (no history, no outcome).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_personal_account
(docs/plans/2026-10-04-personal-account-backtest-design.md, conditions A1-A11)
"""
import datetime
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("personal_account", os.path.join(ROOT, "scripts", "research", "personal_account.py"))
PA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(PA)
UTC = datetime.timezone.utc
# gold-like: 0.01 lot = 1 oz at 4000, so a 100 bp stop costs $40 per minimum lot
GOLD = PA.Spec(contract=100.0, vmin=0.01, vstep=0.01, vmax=100.0, pref=4000.0)


def row(c="A", sym="XAU", day=1, h=10, m=0, bars=6, R=1.0, adv=None, stop_bp=100.0, cost_R=0.0):
    e = datetime.datetime(2025, 1, day, h, m, tzinfo=UTC)
    path = adv if adv is not None else [0.0] * bars
    return {"c": c, "symbol": sym, "entry": e, "exit": e + PA.BAR * (len(path) - 1), "R": R, "cost_R": cost_R,
            "stop_bp": stop_bp, "adv_path_R": path}


def days(*rows_per_day):
    return [(i, list(rs)) for i, rs in enumerate(rows_per_day)]


class Sizing(unittest.TestCase):
    def test_lots_round_down_and_never_exceed_r(self):
        acct = PA.Account(b0=10_000, r=0.01)
        lots, why = PA.lots_for(acct, GOLD, 10_000, 100.0)         # $100 / $4000 per lot = 0.025 -> 0.02
        self.assertEqual((lots, why), (0.02, None))

    def test_below_min_lot_skips_or_floors(self):
        self.assertEqual(PA.lots_for(PA.Account(b0=1_000, r=0.01), GOLD, 1_000, 100.0), (0.0, "min_lot"))
        self.assertEqual(PA.lots_for(PA.Account(b0=1_000, r=0.01, mode="floor"), GOLD, 1_000, 100.0), (0.01, None))

    def test_compounding_on_the_current_balance(self):
        acct = PA.Account(b0=100_000, r=0.01)
        m = PA.replay(days([row(R=1.0)], [row(day=2, R=1.0)]), acct, {"XAU": GOLD})
        # day 1: 0.25 lot x $4000 = $1000 -> 101,000; day 2: 0.25 lot ($1010 rounds down to 0.25) -> 102,000
        self.assertAlmostEqual(m["terminal_multiple"], 1.02, places=6)
        self.assertEqual(m["taken"], 2)


class FloorCap(unittest.TestCase):
    """Mode floor_cap (owner 2026-10-04): size at r; below the minimum lot, trade it only if its risk <= min_lot_cap."""
    ACCT = dict(r=0.01, mode="floor_cap", min_lot_cap=0.02)

    def test_min_lot_traded_up_to_the_cap_inclusive_else_skipped(self):
        acct = PA.Account(b0=5_000, **self.ACCT)                            # one min lot at 100 bp = $40
        self.assertEqual(PA.lots_for(acct, GOLD, 2_500, 100.0), (0.01, None))   # $40 <= 2 % of 2,500 = $50
        self.assertEqual(PA.lots_for(acct, GOLD, 2_000, 100.0), (0.01, None))   # $40 = 2 % of 2,000: inclusive
        self.assertEqual(PA.lots_for(acct, GOLD, 1_999, 100.0), (0.0, "min_lot_over_cap"))
        self.assertEqual(PA.lots_for(acct, GOLD, 1_500, 100.0), (0.0, "min_lot_over_cap"))

    def test_above_the_min_lot_it_sizes_exactly_like_skip(self):
        for bal, stop in ((10_000, 100.0), (100_000, 37.0), (7_777, 140.0)):
            self.assertEqual(PA.lots_for(PA.Account(**self.ACCT), GOLD, bal, stop),
                             PA.lots_for(PA.Account(r=0.01), GOLD, bal, stop))

    def test_cap_must_lie_between_r_and_five_percent(self):
        with self.assertRaises(ValueError):
            PA.Account(r=0.01, mode="floor_cap", min_lot_cap=0.005)
        with self.assertRaises(ValueError):
            PA.Account(r=0.01, mode="floor_cap", min_lot_cap=0.06)
        PA.Account(r=0.03)                                                   # the default cap binds floor_cap only

    def test_replay_counts_trades_above_r_and_the_risk_actually_taken(self):
        acct = PA.Account(b0=3_000, **self.ACCT)
        wide = row(day=1, stop_bp=100.0, R=0.0)                             # $40 min lot > $30 (1 %), <= $60 (2 %)
        wider = row(day=2, stop_bp=200.0, R=0.0)                            # $80 > $60: skipped
        m = PA.replay(days([wide], [wider]), acct, {"XAU": GOLD})
        self.assertEqual((m["taken"], m["taken_above_r"], m["skips"]), (1, 1, {"min_lot_over_cap": 1}))
        self.assertAlmostEqual(m["risk_taken_mean"], 40 / 3_000)
        self.assertAlmostEqual(m["effective_risk_mean"], 40 / 30)

    def test_stalled_counts_min_lot_over_cap_skips(self):
        acct = PA.Account(b0=1_000, stall_k=3, **self.ACCT)                 # $40 min lot > 2 % of 1,000 = $20
        m = PA.replay(days(*[[row(day=d)] for d in range(1, 6)]), acct, {"XAU": GOLD})
        self.assertEqual((m["stalled"], m["skips"], m["taken"]), (0, {"min_lot_over_cap": 5}, 0))

    def test_cap_equal_to_r_trades_like_skip_and_a_wide_cap_like_floor(self):
        seq = days([row(day=1, stop_bp=100.0, R=1.0)], [row(day=2, stop_bp=60.0, R=-1.0)], [row(day=3, stop_bp=180.0, R=2.0)])
        for b0 in (2_500, 4_000, 9_000):
            fc_r = PA.replay(seq, PA.Account(b0=b0, r=0.01, mode="floor_cap", min_lot_cap=0.01), {"XAU": GOLD})
            sk = PA.replay(seq, PA.Account(b0=b0, r=0.01), {"XAU": GOLD})
            fc_w = PA.replay(seq, PA.Account(b0=b0, r=0.01, mode="floor_cap", min_lot_cap=0.05), {"XAU": GOLD})
            fl = PA.replay(seq, PA.Account(b0=b0, r=0.01, mode="floor"), {"XAU": GOLD})
            self.assertEqual((fc_r["terminal_multiple"], fc_r["taken"]), (sk["terminal_multiple"], sk["taken"]))
            self.assertEqual(sum(fc_r["skips"].values()), sk["skips"].get("min_lot", 0))
            self.assertEqual((fc_w["terminal_multiple"], fc_w["taken"]), (fl["terminal_multiple"], fl["taken"]))

    def test_skip_and_floor_never_count_above_r_except_floor_on_the_min_lot(self):
        seq = days([row(day=1, stop_bp=100.0)])
        self.assertEqual(PA.replay(seq, PA.Account(b0=10_000), {"XAU": GOLD})["taken_above_r"], 0)    # 0.02 lot = $80 <= $100
        self.assertEqual(PA.replay(seq, PA.Account(b0=3_000, mode="floor"), {"XAU": GOLD})["taken_above_r"], 1)


class Grid(unittest.TestCase):
    def test_mode_labels_expand_floor_cap_per_cap_and_parse_back(self):
        grid = {"mode": ("skip", "floor_cap"), "cap": (0.02, 0.015)}
        self.assertEqual(PA.mode_labels(grid), ["skip", "floor_cap@0.02", "floor_cap@0.015"])
        a = PA.account_for(5_000.0, 0.01, "floor_cap@0.015")
        self.assertEqual((a.b0, a.r, a.mode, a.min_lot_cap), (5_000.0, 0.01, "floor_cap", 0.015))
        self.assertEqual(PA.account_for(5_000.0, 0.01, "floor"), PA.Account(b0=5_000.0, r=0.01, mode="floor"))

    def test_default_grid_cells_are_unchanged(self):
        self.assertEqual(PA.mode_labels(PA.GRID), ["skip", "floor"])
        self.assertEqual(len(list(PA.cells())), 144)

    def test_summary_pools_trades_above_r_and_risk_taken_over_paths(self):
        # (blown, stalled, max_dd, terminal, cagr, taken, risk_taken_mean, taken_above_r)
        v = [(False, False, 0.1, 1.2, 0.04, 10, 0.010, 0), (False, False, 0.3, 0.9, -0.02, 30, 0.014, 15)]
        s = PA.summarise_cell(v)
        self.assertAlmostEqual(s["taken_above_r_share"], 15 / 40)
        self.assertAlmostEqual(s["risk_taken_mean"], (10 * 0.010 + 30 * 0.014) / 40)
        self.assertAlmostEqual(s["p_dd_ge_25"], 0.5)

    def test_a_grid_the_run_would_fail_on_late_is_refused_up_front(self):
        self.assertIs(PA.check_grid(PA.GRID), PA.GRID)
        with self.assertRaisesRegex(ValueError, "0.5"):           # the ranking reads edge x 0.5 after the bootstrap
            PA.check_grid(dict(PA.GRID, edge=(1.0, 0.0)))
        with self.assertRaises(ValueError):                       # cap below r
            PA.check_grid(dict(PA.GRID, mode=("skip", "floor_cap"), r=(0.01,), cap=(0.005,)))
        with self.assertRaises(ValueError):
            PA.check_grid(dict(PA.GRID, mode=("skip", "half")))
        PA.check_grid(dict(PA.GRID, mode=("floor_cap",), r=(0.01,), cap=(0.02, 0.015)))

    def test_compare_results_reads_shared_entries_on_the_old_fields_only(self):
        old = {"bootstrap": {"a": {"x": 1.0}, "gone": {"x": 2.0}}, "historical": {"h": {"m": 3.0, "s": None}}}
        same = {"bootstrap": {"a": {"x": 1.0, "added": 9}}, "historical": {"h": {"m": 3.0, "s": None}, "new": {"m": 0}}}
        self.assertEqual(PA.compare_results(old, same), (2, []))
        moved = {"bootstrap": {"a": {"x": 1.0000001}}, "historical": {"h": {"m": 3.0}}}
        self.assertEqual(PA.compare_results(old, moved), (2, ["bootstrap|a", "historical|h"]))

    def test_code_version_names_the_commit_and_the_script_hash(self):
        v = PA.code_version()
        self.assertEqual(set(v), {"commit", "dirty_tracked", "script_sha256"})
        self.assertEqual(len(v["script_sha256"]), 64)


class Floor(unittest.TestCase):
    def test_drawdown_uses_the_floating_floor(self):
        m = PA.replay(days([row(adv=[0.0, -0.9, -0.5, 0.3], R=0.3)]), PA.Account(b0=100_000), {"XAU": GOLD})
        self.assertAlmostEqual(m["max_dd"], 0.009, places=6)                 # 0.9 R at 1 % = 0.9 %

    def test_overlapping_trades_add_their_bar_by_bar_floats_not_their_mae_sums(self):
        a = row(c="A", adv=[0.0, -1.0, 0.0, 0.0], R=0.0)
        b = row(c="B", adv=[0.0, 0.0, -1.0, 0.0], R=0.0)
        m = PA.replay(days([a, b]), PA.Account(b0=100_000), {"XAU": GOLD})
        self.assertAlmostEqual(m["max_dd"], 0.01, places=6)                  # never -2 % at one bar


class Ruin(unittest.TestCase):
    def test_blown_is_absorbing_and_later_signals_are_post_ruin(self):
        acct = PA.Account(b0=1_000, r=0.01, mode="floor", leverage=1000)
        crash = row(R=-40.0, adv=[0.0, -40.0])                              # a gap: 40 R on a min lot = -$1,600
        m = PA.replay(days([crash], [row(day=2)], [row(day=3)]), acct, {"XAU": GOLD})
        self.assertEqual(m["blown"], 0)
        self.assertEqual((m["taken"], m["post_ruin"]), (1, 2))

    def test_stalled_means_the_path_ends_unable_to_trade(self):
        acct = PA.Account(b0=1_000, r=0.01, stall_k=3)
        m = PA.replay(days(*[[row(day=d)] for d in range(1, 6)]), acct, {"XAU": GOLD})
        self.assertEqual((m["stalled"], m["skips"]["min_lot"], m["post_ruin"]), (0, 5, 0))   # from the first skip of the streak

    def test_a_run_of_wide_stops_that_narrows_again_is_not_stalled(self):
        acct = PA.Account(b0=10_000, r=0.01, stall_k=3)
        wide = [[row(day=d, stop_bp=500.0)] for d in range(1, 5)]           # $200 per min lot > $100: skipped
        m = PA.replay(days(*wide, [row(day=6, stop_bp=100.0)]), acct, {"XAU": GOLD})
        self.assertEqual((m["stalled"], m["taken"], m["longest_min_lot_skip_streak"]), (None, 1, 4))

    def test_stop_out_closes_everything_at_the_bar(self):
        acct = PA.Account(b0=10_000, r=0.01, mode="floor", leverage=1.0, stop_out=0.5)
        # 0.02 lot = $8,000 notional -> margin $8,000 at 1:1, $80 per R. -30 R: level 7,600 / 8,000 = 95 %; -80 R: 45 % -> out
        t = row(stop_bp=100.0, adv=[0.0, -30.0, -80.0, 0.0], R=0.0)
        m = PA.replay(days([t]), acct, {"XAU": GOLD})
        self.assertEqual(m["skips"].get("stop_out_events"), 1)
        self.assertAlmostEqual(m["terminal_multiple"], (10_000 - 80 * 80) / 10_000, places=6)


class Guards(unittest.TestCase):
    def test_netting_skips_a_second_same_symbol_position(self):
        a, b = row(c="A"), row(c="B", m=5)
        self.assertEqual(PA.replay(days([a, b]), PA.Account(b0=100_000, position_mode="netting"), {"XAU": GOLD})["skips"],
                         {"netting": 1})
        self.assertEqual(PA.replay(days([a, b]), PA.Account(b0=100_000), {"XAU": GOLD})["taken"], 2)

    def test_portfolio_cap(self):
        acct = PA.Account(b0=100_000, r=0.03, portfolio_cap=0.05)
        m = PA.replay(days([row(c="A"), row(c="B", m=5)]), acct, {"XAU": GOLD})
        self.assertEqual(m["skips"], {"portfolio_cap": 1})

    def test_margin_skip(self):
        acct = PA.Account(b0=10_000, r=0.01, leverage=1.0)                  # 0.02 lot needs $8,000; a second needs 8,000 more
        m = PA.replay(days([row(c="A"), row(c="B", m=5)]), acct, {"XAU": GOLD})
        self.assertEqual(m["skips"], {"margin": 1})

    def test_an_exit_at_the_entry_label_is_realised_after_the_entry_is_sized(self):
        win = row(c="A", bars=2, R=10.0)                                     # exits at 10:05
        nxt = row(c="B", m=5)                                                # enters at 10:05
        m = PA.replay(days([win, nxt]), PA.Account(b0=100_000), {"XAU": GOLD})
        self.assertEqual(m["effective_risk_mean"] < 1.01, True)
        # the second trade was sized on 100,000 (0.25 lot, +$1,000), not on 110,000 (0.27 lot, +$1,080)
        self.assertAlmostEqual(m["terminal_multiple"], 1.0 + 10 * 0.01 + 0.01, places=6)


class Haircut(unittest.TestCase):
    def test_the_haircut_mean_is_taken_on_the_sampled_span(self):
        rows = {("H7_XAUUSD_eod", 2.0): [dict(row(R=1.0), day="2010-01-04"), dict(row(R=0.2), day="2020-01-06")]}
        self.assertAlmostEqual(PA.haircut_shift(rows, "H7_XAU", 1.0)["H7_XAUUSD_eod"], 0.6)
        self.assertAlmostEqual(PA.haircut_shift(rows, "H7_XAU", 1.0, since="2018-02-26")["H7_XAUUSD_eod"], 0.2)


if __name__ == "__main__":
    unittest.main()
