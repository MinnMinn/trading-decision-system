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

    def test_the_current_base_never_takes_a_trade_above_the_cap(self):
        acct = PA.Account(b0=3_000, **self.ACCT)
        m = PA.replay(days([row(day=1, stop_bp=140.0, R=0.0)], [row(day=2, stop_bp=100.0, R=0.0)]), acct, {"XAU": GOLD})
        self.assertEqual((m["taken"], m["taken_above_cap"]), (2, 0))                  # $56, $40 <= $60
        self.assertAlmostEqual(m["risk_taken_max"], 56 / 3_000)                       # the largest, not the last


class FloorCapFixed(unittest.TestCase):
    """Cap base "initial" (owner 2026-10-04: "Trần 2% tính theo cố định 100 USD"): the minimum lot may be traded when its
    risk <= min_lot_cap x b0, a FIXED amount (100 USD on 5,000), not a share of the current balance."""
    FIX = dict(b0=5_000, r=0.01, mode="floor_cap", min_lot_cap=0.02, min_lot_cap_base="initial")
    CUR = dict(b0=5_000, r=0.01, mode="floor_cap", min_lot_cap=0.02)

    def test_the_default_base_is_the_current_balance(self):
        self.assertEqual(PA.Account().min_lot_cap_base, "current")
        self.assertEqual(PA.Account(**self.CUR), PA.Account(min_lot_cap_base="current", **self.CUR))

    def test_after_a_drawdown_the_fixed_cap_trades_where_the_current_cap_skips(self):
        # balance 2,500: min lot at 200 bp = $80 > 2 % x 2,500 = $50 (current) but <= $100 (fixed)
        self.assertEqual(PA.lots_for(PA.Account(**self.CUR), GOLD, 2_500, 200.0), (0.0, "min_lot_over_cap"))
        self.assertEqual(PA.lots_for(PA.Account(**self.FIX), GOLD, 2_500, 200.0), (0.01, None))
        self.assertEqual(PA.lots_for(PA.Account(**self.FIX), GOLD, 1_000, 200.0), (0.01, None))      # 8 % of the balance

    def test_the_fixed_amount_is_inclusive(self):
        acct = PA.Account(**self.FIX)
        self.assertEqual(PA.lots_for(acct, GOLD, 2_500, 250.0), (0.01, None))       # $100 = 2 % x 5,000: inclusive
        self.assertEqual(PA.lots_for(acct, GOLD, 2_500, 250.5), (0.0, "min_lot_over_cap"))   # $100.20

    def test_the_fixed_amount_is_min_lot_cap_times_b0_for_any_b0(self):
        # b0 10,000 -> $200: balance 6,000, min lot at 500 bp = $200 trades (2 % of 6,000 = $120 would skip it), 501 bp skips
        big = PA.Account(**dict(self.FIX, b0=10_000))
        self.assertEqual(PA.lots_for(big, GOLD, 6_000, 500.0), (0.01, None))
        self.assertEqual(PA.lots_for(big, GOLD, 6_000, 501.0), (0.0, "min_lot_over_cap"))
        # b0 2,500 -> $50: min lot at 125 bp = $50 trades, 130 bp = $52 skips (a constant $100 would trade it)
        small = PA.Account(**dict(self.FIX, b0=2_500))
        self.assertEqual(PA.lots_for(small, GOLD, 2_500, 125.0), (0.01, None))
        self.assertEqual(PA.lots_for(small, GOLD, 2_500, 130.0), (0.0, "min_lot_over_cap"))

    def test_a_trade_exactly_at_two_percent_of_the_balance_is_not_counted_above_the_cap(self):
        # b0 5,000: a min lot at 250 bp risks $100 = exactly 2 % of 5,000 -> taken, not above the cap
        at = PA.replay(days([row(day=1, stop_bp=250.0, R=0.0)]), PA.Account(**self.FIX), {"XAU": GOLD})
        self.assertEqual((at["taken"], at["taken_above_cap"]), (1, 0))
        self.assertAlmostEqual(at["risk_taken_max"], 0.02)
        # after a $40 loss (balance 4,960) the same $100 is 2.016 % of the balance -> counted
        seq = days([row(day=1, R=-1.0)], [row(day=2, stop_bp=250.0, R=0.0)])
        after = PA.replay(seq, PA.Account(**self.FIX), {"XAU": GOLD})
        self.assertEqual((after["taken"], after["taken_above_cap"]), (2, 1))
        self.assertAlmostEqual(after["risk_taken_max"], 100 / 4_960)

    def test_above_b0_the_fixed_cap_is_tighter_than_the_current_cap(self):
        # balance 6,000: min lot at 275 bp = $110 > 1 % ($60), <= 2 % x 6,000 = $120 (current), > $100 (fixed)
        self.assertEqual(PA.lots_for(PA.Account(**self.CUR), GOLD, 6_000, 275.0), (0.01, None))
        self.assertEqual(PA.lots_for(PA.Account(**self.FIX), GOLD, 6_000, 275.0), (0.0, "min_lot_over_cap"))

    def test_from_cap_over_r_times_b0_up_the_fixed_cap_sizes_exactly_like_skip(self):
        # balance >= (2 % / 1 %) x 5,000 = 10,000: a min lot that 1 % cannot place risks > $100, so the fixed cap skips it
        skip = PA.Account(b0=5_000, r=0.01)
        for bal in (10_000, 12_000, 40_000):
            for stop in (100.0, 200.0, 250.0, 251.0, 300.0, 400.0, 900.0):
                want = PA.lots_for(skip, GOLD, bal, stop)
                want = (want[0], "min_lot_over_cap") if want[1] == "min_lot" else want
                self.assertEqual(PA.lots_for(PA.Account(**self.FIX), GOLD, bal, stop), want, (bal, stop))

    def test_the_cap_check_bounds_the_fixed_amount_between_r_and_five_percent_of_b0(self):
        with self.assertRaises(ValueError):
            PA.Account(**dict(self.FIX, min_lot_cap=0.005))
        with self.assertRaises(ValueError):
            PA.Account(**dict(self.FIX, min_lot_cap=0.06))
        with self.assertRaisesRegex(ValueError, "min_lot_cap_base"):
            PA.Account(min_lot_cap_base="start")
        PA.Account(**dict(self.FIX, min_lot_cap=0.05))

    def test_a_deep_drawdown_can_now_end_in_blown(self):
        # gaps of -20 R; 100 bp stop -> $40 per min lot. Current cap: trades at 5,000 / 4,200 / 3,400 / 2,600, then $40 > 2 % of
        # 1,800 and every later signal is skipped (STALLED, money left). Fixed cap: keeps trading the $40 lot at 1,800 / 1,000 /
        # 200; at 200 the bar at -20 R takes the floor below 0 -> stop-out -> balance -600 -> BLOWN.
        crash = [[row(day=d, R=-20.0, adv=[0.0, -20.0])] for d in range(1, 9)]
        cur = PA.replay(days(*crash), PA.Account(stall_k=3, **self.CUR), {"XAU": GOLD})
        fix = PA.replay(days(*crash), PA.Account(stall_k=3, **self.FIX), {"XAU": GOLD})
        self.assertEqual((cur["blown"], cur["stalled"], cur["taken"], cur["taken_above_cap"]), (None, 4, 4, 0))
        self.assertAlmostEqual(cur["terminal_multiple"], 1_800 / 5_000)
        self.assertEqual((fix["blown"], fix["stalled"], fix["taken"], fix["post_ruin"]), (6, None, 7, 1))
        self.assertEqual((fix["taken_above_cap"], fix["skips"]), (3, {"stop_out_events": 1}))
        self.assertEqual(fix["terminal_multiple"], 0.0)
        # A5 binds only a trade opened next to others: the lone $40 lot at a 200 balance risks 20 %, above the 5 % portfolio cap
        self.assertAlmostEqual(fix["risk_taken_max"], 40 / 200)
        self.assertGreater(fix["risk_taken_max"], PA.Account(**self.FIX).portfolio_cap)

    def test_after_a_drawdown_the_portfolio_cap_still_binds_a_second_open_trade(self):
        # down to 1,000 (as above), then two overlapping signals: the first $40 lot (4 %) opens alone; the second would put
        # $80 at risk > 5 % x 1,000 = $50 and is skipped
        crash = [[row(day=d, R=-20.0, adv=[0.0, -20.0])] for d in range(1, 6)]
        pair = [row(day=6, c="A", R=0.0), row(day=6, c="B", m=5, R=0.0)]
        m = PA.replay(days(*crash, pair), PA.Account(**self.FIX), {"XAU": GOLD})
        self.assertEqual((m["taken"], m["skips"], m["blown"]), (6, {"portfolio_cap": 1}, None))


class Grid(unittest.TestCase):
    def test_mode_labels_expand_floor_cap_per_cap_and_parse_back(self):
        grid = {"mode": ("skip", "floor_cap"), "cap": (0.02, 0.015)}
        self.assertEqual(PA.mode_labels(grid), ["skip", "floor_cap@0.02", "floor_cap@0.015"])
        a = PA.account_for(5_000.0, 0.01, "floor_cap@0.015")
        self.assertEqual((a.b0, a.r, a.mode, a.min_lot_cap), (5_000.0, 0.01, "floor_cap", 0.015))
        self.assertEqual(PA.account_for(5_000.0, 0.01, "floor"), PA.Account(b0=5_000.0, r=0.01, mode="floor"))

    def test_the_cap_base_gets_its_own_label_and_the_current_base_keeps_the_old_one(self):
        grid = {"mode": ("skip", "floor_cap"), "cap": (0.02,), "cap_base": ("current", "initial")}
        self.assertEqual(PA.mode_labels(grid), ["skip", "floor_cap@0.02", "floor_cap@0.02/initial"])
        self.assertEqual(PA.mode_labels({"mode": ("floor_cap",), "cap": (0.02,), "cap_base": ("initial",)}),
                         ["floor_cap@0.02/initial"])
        a = PA.account_for(5_000.0, 0.01, "floor_cap@0.02/initial")
        self.assertEqual((a.mode, a.min_lot_cap, a.min_lot_cap_base), ("floor_cap", 0.02, "initial"))
        self.assertEqual(PA.account_for(5_000.0, 0.01, "floor_cap@0.02").min_lot_cap_base, "current")
        with self.assertRaises(ValueError):
            PA.account_for(5_000.0, 0.01, "floor_cap@0.02/start")

    def test_check_grid_reads_the_cap_base(self):
        ok = dict(PA.GRID, mode=("floor_cap",), r=(0.01,), cap=(0.02,), cap_base=("initial",))
        self.assertIs(PA.check_grid(ok), ok)
        with self.assertRaises(ValueError):
            PA.check_grid(dict(ok, cap_base=("start",)))
        with self.assertRaises(ValueError):                       # the fixed amount below r x b0
            PA.check_grid(dict(ok, cap=(0.005,)))
        PA.check_grid(dict(PA.GRID, cap_base=("start",)))         # no floor_cap in the grid: the base is not read

    def test_summary_adds_the_cap_keys_only_for_the_ten_field_form(self):
        # (..., taken_above_r, taken_above_cap, risk_taken_max)
        v = [(False, False, 0.1, 1.2, 0.04, 10, 0.010, 0, 0, 0.012), (True, False, 0.9, 0.0, -1.0, 30, 0.03, 20, 5, 0.25)]
        s = PA.summarise_cell(v)
        self.assertAlmostEqual(s["taken_above_cap_share"], 5 / 40)
        self.assertAlmostEqual(s["p_any_above_cap"], 0.5)
        self.assertEqual((s["risk_taken_max"], s["risk_taken_max_p95"]), (0.25, 0.25))
        new = {"taken_above_cap_share", "p_any_above_cap", "risk_taken_max", "risk_taken_max_p95"}
        self.assertEqual(PA.summarise_cell([x[:8] for x in v]), {k: s[k] for k in s if k not in new})

    def test_risk_taken_max_p95_is_the_95th_percentile_of_the_per_path_maxima(self):
        # 21 paths with maxima 0.01 .. 0.21, plus one path without a trade (None, left out): sorted[int(0.95 x 21)] = 0.20
        v = [(False, False, 0.1, 1.0, 0.0, 1, 0.01, 0, 0, (i + 1) / 100) for i in range(21)]
        v.append((False, False, 0.0, 1.0, 0.0, 0, None, 0, 0, None))
        s = PA.summarise_cell(v)
        self.assertAlmostEqual(s["risk_taken_max_p95"], 0.20)
        self.assertAlmostEqual(s["risk_taken_max"], 0.21)

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
