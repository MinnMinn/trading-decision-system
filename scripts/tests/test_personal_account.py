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
