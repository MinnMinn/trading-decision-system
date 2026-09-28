"""CLAUDE.md §39 -- the twenty-three metrics, the sample size that must travel with them, and the single
universal score that must not exist.

§39 is a list plus two rules, and the two rules are where the failures live.

**"Always show sample size."** Not "print n somewhere on the page": a metric computed over three trades and
one computed over three thousand are different claims, and the first must not be presentable as the second.
So `min_n` is declared per metric in the registry and enforced in the computer, and a metric below its floor
returns a REASON, never a number.

**"Do not optimize against a single universal metric."** There is no `score()` in `performance.py`; there is
`refuse_universal_score()`, and the test below asserts the module has no other way to produce one.

The audit that preceded this file (SPEC-COMPLIANCE row 39) found seven of the twenty-three absent, four more
wrong in the same way -- `journal.stats()` folded `R <= 0` into `losses`, so a flat trade sat in the win-rate
denominator AND extended the losing streak -- and **zero tests over any of them**. The arithmetic below is
therefore checked against hand-computed values, not against the implementation's own output.
"""
import importlib.util
import json
import math
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import performance as P
import account_profile as AP

REGISTRY = os.path.join(ROOT, "docs", "architecture", "performance-metrics.json")
PERF_SRC = open(os.path.join(ROOT, "scripts", "performance.py"), encoding="utf-8").read()
JOURNAL_SRC = open(os.path.join(ROOT, "scripts", "journal.py"), encoding="utf-8").read()
BT_SRC = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()


def _spec_bullets():
    """§39's own list, read out of CLAUDE.md."""
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split("39. PERFORMANCE METRICS", 1)[1].split("Always show sample size", 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def T(r, **kw):
    """One trade record."""
    return dict(R=r, **kw)


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_every_bullet_in_claude_md_39_is_a_declared_metric(self):
        self.assertEqual([P.spec_name(m) for m in P.ORDER], _spec_bullets())

    def test_there_are_twenty_three(self):
        self.assertEqual(len(P.ORDER), 23)

    def test_every_metric_declares_a_minimum_sample_size(self):
        for mid in P.ORDER:
            self.assertIsInstance(P.METRICS[mid]["min_n"], int, mid)

    def test_the_risk_adjusted_and_probability_metrics_have_real_floors(self):
        # A Sharpe over 3 trades and a bootstrap over 5 are noise wearing a number's clothes.
        self.assertGreaterEqual(P.METRICS["sharpe"]["min_n"], 8)
        self.assertGreaterEqual(P.METRICS["sortino"]["min_n"], 8)
        for mid in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            # min_n is a COMPUTABILITY floor (a bootstrap must have something to resample), not a
            # confidence judgement -- the confidence band is `low_confidence_below` (user decision
            # 2026-09-19; see `_sample_size_floors` in the registry).
            self.assertGreaterEqual(P.METRICS[mid]["min_n"], 5, mid)
            self.assertGreaterEqual(P.METRICS[mid]["low_confidence_below"], 30, mid)

    def test_a_registry_metric_with_an_unknown_kind_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["metrics"][0]["kind"] = "vibes"
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-perf.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(P.RegistryError):
                P._load(p)
        finally:
            os.remove(p)

    def test_a_registry_metric_with_no_min_n_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["metrics"][0].pop("min_n")
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-perf2.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(P.RegistryError):
                P._load(p)
        finally:
            os.remove(p)


class SampleSizeAlwaysTravels(unittest.TestCase):
    def test_n_is_present_even_for_an_empty_population(self):
        self.assertEqual(P.metrics([])["n"], 0)

    def test_every_declared_metric_appears_in_the_result(self):
        # The computer raises rather than returning a partial record, so a registry entry cannot quietly
        # become a hole. Checked on both an empty and a populated call.
        for pop in ([], [T(1.0), T(-1.0), T(2.0)]):
            res = P.metrics(pop)
            for mid in P.ORDER:
                self.assertIn(mid, res, mid)

    def test_a_metric_below_its_floor_is_a_reason_not_a_number(self):
        res = P.metrics([T(1.0), T(-1.0), T(0.5)])
        self.assertTrue(P.is_unavailable(res["sharpe"]))
        self.assertIn("sample size 3", res["sharpe"]["unavailable"])

    def test_the_floor_is_read_from_the_registry_not_hardcoded(self):
        # Raise the declared floor and the metric must disappear from a population that previously had it.
        n = P.METRICS["consecutive_wins"]["min_n"]
        try:
            P.METRICS["consecutive_wins"]["min_n"] = 999
            self.assertTrue(P.is_unavailable(P.metrics([T(1.0)] * 10)["consecutive_wins"]))
        finally:
            P.METRICS["consecutive_wins"]["min_n"] = n

    def test_describe_leads_with_the_sample_size(self):
        self.assertTrue(P.describe(P.metrics([T(1.0), T(-1.0)])).startswith("n=2"))


class BreakevenIsItsOwnBucket(unittest.TestCase):
    """§39 lists breakeven beside wins and losses. The pre-2026-09-18 code had no such bucket."""

    POP = [T(2.0), T(-1.0), T(0.0), T(-1.0), T(3.0), T(0.01)]   # 2 wins, 2 losses, 2 breakeven

    def test_the_three_buckets_partition_the_population(self):
        res = P.metrics(self.POP)
        self.assertEqual((res["wins"], res["losses"], res["breakeven"]), (2, 2, 2))
        self.assertEqual(res["wins"] + res["losses"] + res["breakeven"], res["total_trades"])

    def test_a_flat_trade_is_in_the_win_rate_denominator_but_not_the_numerator(self):
        self.assertAlmostEqual(P.metrics(self.POP)["win_rate"], 2 / 6)

    def test_an_engine_label_of_breakeven_outranks_the_band(self):
        # backtest-methods' walk() knows it moved the stop to entry. A fee can push that trade's R slightly
        # negative; it is still a breakeven trade, not a loss.
        res = P.metrics([T(-0.12, outcome="breakeven"), T(1.0), T(-1.0)])
        self.assertEqual((res["wins"], res["losses"], res["breakeven"]), (1, 1, 1))

    def test_a_breakeven_trade_breaks_the_losing_streak_rather_than_extending_it(self):
        # This is the defect the audit named: the old code counted R<=0 as a loss, so a flat trade between two
        # losses reported a streak of 3 where the account saw two.
        res = P.metrics([T(-1.0), T(0.0), T(-1.0)])
        self.assertEqual(res["consecutive_losses"], 1)

    def test_a_breakeven_trade_breaks_the_winning_streak_too(self):
        res = P.metrics([T(1.0), T(0.0), T(1.0)])
        self.assertEqual(res["consecutive_wins"], 1)

    def test_streaks_are_measured_on_both_sides(self):
        # journal.py counted only the losing side.
        res = P.metrics([T(1.0), T(1.0), T(1.0), T(-1.0), T(-1.0)])
        self.assertEqual((res["consecutive_wins"], res["consecutive_losses"]), (3, 2))


class TheArithmeticIsCheckedByHand(unittest.TestCase):
    POP = [T(2.0), T(-1.0), T(-1.0), T(3.0)]      # sum 3.0 over 4 trades

    def test_expectancy_and_average_R(self):
        res = P.metrics(self.POP)
        self.assertAlmostEqual(res["expectancy"], 0.75)
        self.assertAlmostEqual(res["average_R"], 0.75)
        self.assertAlmostEqual(res["average_win_R"], 2.5)
        self.assertAlmostEqual(res["average_loss_R"], -1.0)

    def test_profit_factor(self):
        self.assertAlmostEqual(P.metrics(self.POP)["profit_factor"], 5.0 / 2.0)

    def test_profit_factor_with_no_loser_is_unavailable_not_infinite(self):
        v = P.metrics([T(1.0), T(2.0)])["profit_factor"]
        self.assertTrue(P.is_unavailable(v))
        self.assertIn("infinity", v["unavailable"])

    def test_sharpe_is_mean_over_stdev_of_the_per_trade_series(self):
        pop = [T(1.0), T(-1.0)] * 6                       # mean 0 -> Sharpe 0, dispersion non-zero
        self.assertAlmostEqual(P.metrics(pop)["sharpe"]["value"], 0.0)
        pop2 = [T(1.0)] * 8 + [T(-1.0)] * 4               # n=12, mean = 4/12
        res = P.metrics(pop2)
        rs = [1.0] * 8 + [-1.0] * 4
        mu = sum(rs) / len(rs)
        sd = (sum((r - mu) ** 2 for r in rs) / len(rs)) ** 0.5
        self.assertAlmostEqual(res["sharpe"]["value"], mu / sd)

    def test_sharpe_says_whether_it_is_annualised(self):
        pop = [T(1.0)] * 8 + [T(-1.0)] * 4
        self.assertEqual(P.metrics(pop)["sharpe"]["basis"], "per-trade")
        ann = P.metrics(pop, trades_per_year=100)["sharpe"]
        self.assertEqual(ann["basis"], "annualised")
        self.assertAlmostEqual(ann["value"], P.metrics(pop)["sharpe"]["value"] * math.sqrt(100))

    def test_sortino_uses_only_the_downside(self):
        rs = [1.0] * 8 + [-1.0] * 4
        res = P.metrics([T(r) for r in rs])
        mu = sum(rs) / len(rs)
        dd = (sum(min(0.0, r) ** 2 for r in rs) / len(rs)) ** 0.5
        self.assertAlmostEqual(res["sortino"]["value"], mu / dd)
        self.assertGreater(res["sortino"]["value"], res["sharpe"]["value"])   # upside is not punished

    def test_sortino_with_no_downside_is_unmeasured_not_infinite(self):
        v = P.metrics([T(1.0)] * 10)["sortino"]
        self.assertTrue(P.is_unavailable(v))
        self.assertIn("not infinite", v["unavailable"])

    def test_max_and_average_drawdown_over_a_known_curve(self):
        curve = [100, 110, 88, 110, 120, 60, 130]         # two episodes: 22/110 = 0.2, 60/120 = 0.5
        res = P.metrics([T(1.0)] * 6, equity=curve)
        self.assertAlmostEqual(res["max_drawdown"]["fraction"], 0.5)
        self.assertAlmostEqual(res["average_drawdown"]["fraction"], (0.2 + 0.5) / 2)
        self.assertEqual(res["average_drawdown"]["episodes"], 2)

    def test_an_unrecovered_drawdown_is_counted_and_flagged(self):
        # Dropping the open episode would flatter exactly the curve that ends underwater.
        res = P.metrics([T(1.0)] * 3, equity=[100, 120, 60])
        self.assertTrue(res["average_drawdown"]["includes_unrecovered"])
        self.assertAlmostEqual(res["max_drawdown"]["fraction"], 0.5)

    def test_time_in_drawdown_reports_both_the_share_and_the_longest_stretch(self):
        # A strategy underwater in short dips is not the one that spent an unbroken year there.
        res = P.metrics([T(1.0)] * 6, equity=[100, 90, 100, 90, 90, 100])
        self.assertAlmostEqual(res["time_in_drawdown"]["fraction_of_series"], 3 / 6)
        self.assertEqual(res["time_in_drawdown"]["longest_stretch"], 2)

    def test_recovery_factor_is_net_over_the_worst_hole(self):
        res = P.metrics([T(1.0)] * 4, equity=[100, 50, 100, 150])
        self.assertAlmostEqual(res["max_drawdown"]["fraction"], 0.5)
        self.assertAlmostEqual(res["recovery_factor"], 50 / (0.5 * 100))

    def test_time_to_target_shows_the_denominator_it_excluded(self):
        pop = [T(3.0, bars_held=10), T(3.0, bars_held=20), T(-1.0, bars_held=4)]
        v = P.metrics(pop)["time_to_target"]
        self.assertEqual(v["median_bars"], 15)
        self.assertEqual((v["n_reached_target"], v["n_did_not"]), (2, 1))


class Excursions(unittest.TestCase):
    """MFE/MAE were absent everywhere; the backtest engine now measures them in the one loop that sees the
    bars between entry and exit."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "bt_perf", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        self.bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.bt)

    def test_walk_records_the_excursion_of_a_losing_trade_that_first_went_up(self):
        # entry 100, stop 90 (R = 10), target 130. Bar 0 reaches 115 (+1.5R) then bar 1 stops out.
        H = [115, 100]; L = [100, 89]; C = [110, 89]
        self.bt.OPTS["mgmt"] = "none"
        w = self.bt.walk("long", 100, 90, 130, H, L, C, 0, 10)
        self.assertEqual(w["outcome"], "loss")
        self.assertAlmostEqual(w["mfe"], 1.5)
        self.assertAlmostEqual(w["mae"], -1.1)
        self.assertEqual(w["bars_held"], 2)

    def test_a_short_trade_measures_its_excursion_in_the_other_direction(self):
        # entry 100, stop 110 (R = 10), target 70. Price drops to 85 (+1.5R) then hits target.
        H = [101, 100]; L = [85, 69]; C = [90, 70]
        self.bt.OPTS["mgmt"] = "none"
        w = self.bt.walk("short", 100, 110, 70, H, L, C, 0, 10)
        self.assertEqual(w["outcome"], "win")
        self.assertAlmostEqual(w["mfe"], 3.1)
        self.assertAlmostEqual(w["mae"], -0.1)

    def test_the_excursion_fields_are_outcome_fields_the_pit_prober_allows_to_move(self):
        # §37 permits the future to determine an outcome. leakage.py must already know these are outcomes, or
        # adding them would make every PIT probe fail.
        import leakage
        self.assertIn("mfe", leakage.OUTCOME_FIELDS)
        self.assertIn("mae", leakage.OUTCOME_FIELDS)

    def test_the_metric_separates_winners_from_losers(self):
        pop = [T(3.0, mfe=3.2, mae=-0.9), T(-1.0, mfe=1.8, mae=-1.0)]
        res = P.metrics(pop)
        self.assertAlmostEqual(res["mfe"]["mean_on_losers"], 1.8)     # the loser that first went to +1.8R
        self.assertAlmostEqual(res["mae"]["mean_on_winners"], -0.9)   # the winner that first went to -0.9R

    def test_a_population_without_excursions_says_so(self):
        v = P.metrics([T(1.0), T(-1.0)])["mfe"]
        self.assertTrue(P.is_unavailable(v))
        self.assertIn("walk()", v["unavailable"])


class MoneyAndProbabilityNeedAnAccount(unittest.TestCase):
    def test_pnl_without_an_account_or_a_money_column_is_unavailable(self):
        v = P.metrics([T(1.0)])["pnl"]
        self.assertTrue(P.is_unavailable(v))

    def test_pnl_prefers_the_realised_money_the_trades_carry(self):
        res = P.metrics([T(1.0, pnl_usd=100.0), T(-1.0, pnl_usd=-50.0)])
        self.assertAlmostEqual(res["pnl"]["value"], 50.0)
        self.assertIn("realised", res["pnl"]["basis"])

    def test_the_three_probabilities_are_unavailable_without_an_account(self):
        res = P.metrics([T(1.0), T(-1.0)] * 30)
        for mid in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            self.assertTrue(P.is_unavailable(res[mid]), mid)
            self.assertIn("account", res[mid]["unavailable"], mid)

    def test_a_probability_below_the_sample_floor_is_refused(self):
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        res = P.metrics([T(1.0), T(-1.0)] * 2, account=acct)      # n = 4 < min_n 5: the resample is degenerate
        self.assertTrue(P.is_unavailable(res["risk_of_ruin"]))
        self.assertIn("every path is drawn from the same", res["risk_of_ruin"]["unavailable"])

    def test_ten_trades_are_computed_and_flagged_rather_than_refused(self):
        """The old floor of 30 refused this; it is now a wide number that says it is wide (2026-09-19)."""
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        res = P.metrics([T(1.0), T(-1.0)] * 5, account=acct)      # n = 10
        self.assertFalse(P.is_unavailable(res["risk_of_ruin"]))
        self.assertTrue(res["risk_of_ruin"]["low_confidence"])

    def test_a_probability_carries_its_method_seed_and_horizon(self):
        # A bare number would be a decoration: nobody could reproduce or argue with it (§46).
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        v = P.metrics([T(1.0), T(-1.0)] * 30, account=acct, iterations=200)["risk_of_ruin"]
        for k in ("method", "iterations", "seed", "horizon_trades", "risk_per_trade", "sample"):
            self.assertIn(k, v, k)
        self.assertIn("bootstrap", v["method"])

    def test_the_bootstrap_is_deterministic_for_a_given_seed(self):
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        pop = [T(2.0), T(-1.0), T(-1.0)] * 20
        a = P.metrics(pop, account=acct, iterations=300)["risk_of_ruin"]["value"]
        b = P.metrics(pop, account=acct, iterations=300)["risk_of_ruin"]["value"]
        self.assertEqual(a, b)

    def test_a_losing_system_ruins_more_often_than_a_winning_one(self):
        # The direction is the only thing a bootstrap has to get right to be worth reporting.
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        losing = P.metrics([T(-1.0)] * 40, account=acct, iterations=300, horizon=400)["risk_of_ruin"]["value"]
        winning = P.metrics([T(3.0)] * 40, account=acct, iterations=300, horizon=400)["risk_of_ruin"]["value"]
        self.assertGreater(losing, winning)

    def test_account_failure_is_at_least_as_likely_as_ruin(self):
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.05}}}
        res = P.metrics([T(2.0), T(-1.0), T(-1.0), T(-1.0)] * 15, account=acct, iterations=400, horizon=200)
        self.assertGreaterEqual(res["account_failure_probability"]["value"], res["risk_of_ruin"]["value"])

    def test_prop_pass_is_unavailable_for_an_account_with_no_profit_target(self):
        # A demo or personal account cannot be "passed" -- a property of the profile, not a gap in the metric.
        acct = {"rules": {"initial_balance": 10000, "max_total_drawdown": {"pct": 0.15}}}
        v = P.metrics([T(1.0), T(-1.0)] * 30, account=acct, iterations=200)["prop_pass_probability"]
        self.assertTrue(P.is_unavailable(v))
        self.assertIn("profit_target", v["unavailable"])

    def test_every_declared_profile_reaches_a_stated_reason_or_a_value_never_a_crash(self):
        # The two DEMO profiles are neither, and one declares no starting balance either -- each must produce
        # a REASON naming which it is. The two RESEARCH prop-challenge profiles (A2) DO declare a
        # profit_target on purpose, so for those the metric must actually COMPUTE rather than say unavailable.
        for pid in AP.PROFILES:
            prof = AP.get(pid)
            res = P.metrics([T(1.0), T(-1.0)] * 30, account=prof, iterations=100)
            v = res["prop_pass_probability"]
            if prof["rules"].get("profit_target") is not None:
                self.assertFalse(P.is_unavailable(v), pid)
                self.assertIn("value", v, pid)
            else:
                self.assertTrue(P.is_unavailable(v), pid)
                self.assertTrue(any(w in v["unavailable"] for w in ("profit_target", "starting balance")), pid)

    def test_a_declared_prop_target_makes_the_pass_probability_computable(self):
        acct = {"rules": {"initial_balance": 10000, "profit_target": {"pct": 0.08},
                          "max_total_drawdown": {"pct": 0.10}}}
        v = P.metrics([T(3.0), T(-1.0), T(-1.0)] * 20, account=acct, iterations=400, horizon=200)
        self.assertIn("value", v["prop_pass_probability"])
        self.assertGreaterEqual(v["prop_pass_probability"]["value"], 0.0)
        self.assertLessEqual(v["prop_pass_probability"]["value"], 1.0)

    def test_a_real_declared_profile_is_readable_end_to_end(self):
        prof = AP.get("pilot-binance-futures-testnet")
        res = P.metrics([T(1.0), T(-1.0)] * 30, account=prof, iterations=200)
        # This profile has no initial_balance (the testnet faucet tops it up), so the money metrics say so
        # rather than inventing a balance.
        self.assertTrue(P.is_unavailable(res["risk_of_ruin"]))
        self.assertIn("starting balance", res["risk_of_ruin"]["unavailable"])


class AccountTermsAcceptsBothInitialBalanceShapes(unittest.TestCase):
    """A2 (§0.2) -- the vocabulary says `initial_balance` is `{amount, currency}`; before this fix
    `_account_terms` accepted only a bare number, so every profile with a real initial_balance dict (the two
    new prop-challenge profiles) was reported as having no starting balance at all."""

    def test_a_dict_shaped_initial_balance_is_read(self):
        terms, why = P._account_terms({"rules": {"initial_balance": {"amount": 1e5, "currency": "USD"}}})
        self.assertIsNone(why)
        self.assertEqual(terms["balance"], 100000.0)

    def test_a_bare_number_still_works(self):
        terms, why = P._account_terms({"rules": {"initial_balance": 10000}})
        self.assertIsNone(why)
        self.assertEqual(terms["balance"], 10000.0)

    def test_a_dict_with_no_amount_is_refused_not_guessed(self):
        terms, why = P._account_terms({"rules": {"initial_balance": {"currency": "USD"}}})
        self.assertIsNone(terms)
        self.assertIsNotNone(why)

    def test_the_real_ftmo_profile_now_reads_its_balance(self):
        terms, why = P._account_terms(AP.get("ftmo-challenge-phase1"))
        self.assertIsNone(why)
        self.assertEqual(terms["balance"], 100000.0)


class MaxDailyLossDayBlockBootstrap(unittest.TestCase):
    """A2 -- `max_daily_loss` needs trades resampled as whole TRADING DAYS, not trade-by-trade, or the rule
    can never actually fire: an iid per-trade bootstrap can spread one bad day's -6% across several resampled
    'days' that each look fine on their own. `entry_time` is what groups a trade into its day; without it,
    max_daily_loss is dropped (not silently ignored) and the other failure conditions still compute."""

    def test_prop_pass_probability_is_not_unavailable_for_a_profile_with_max_daily_loss(self):
        prof = AP.get("ftmo-challenge-phase1")     # declares max_daily_loss AND profit_target
        trades = [T(2.0, entry_time=f"2026-01-{1 + (i % 20):02d}T00:00:00Z") for i in range(40)]
        res = P.metrics(trades, account=prof, iterations=100, horizon=10)
        self.assertFalse(P.is_unavailable(res["prop_pass_probability"]), res["prop_pass_probability"])
        self.assertIn("value", res["prop_pass_probability"])

    def test_a_synthetic_day_losing_six_percent_fails_under_max_daily_loss(self):
        prof = AP.get("ftmo-challenge-phase1")     # max_daily_loss 5 % of day_start_equity
        day = "2026-02-02"
        # One UTC day, 30 trades at -0.2R each: compounding at the 1 % platform risk ceiling loses ~5.8 % of
        # the day's starting equity -- past the account's 5 % floor. Because every trade lands on the SAME
        # day, `_day_blocks` produces exactly ONE block, so every bootstrap iteration resamples this same
        # losing day and the failure is deterministic.
        trades = [T(-0.2, entry_time=f"{day}T00:{i:02d}:00Z") for i in range(30)]
        res = P.metrics(trades, account=prof, iterations=50, horizon=1)
        self.assertFalse(P.is_unavailable(res["account_failure_probability"]), res["account_failure_probability"])
        self.assertEqual(res["account_failure_probability"]["value"], 1.0, res["account_failure_probability"])
        self.assertIn("max_daily_loss", res["account_failure_probability"]["conditions"])

    def test_without_entry_time_max_daily_loss_is_dropped_with_a_reason_not_silently_ignored(self):
        prof = AP.get("ftmo-challenge-phase1")
        trades = [T(2.0) for _ in range(40)]        # no entry_time on any trade
        res = P.metrics(trades, account=prof, iterations=50, horizon=10)
        self.assertFalse(P.is_unavailable(res["account_failure_probability"]))
        self.assertNotIn("max_daily_loss", res["account_failure_probability"]["conditions"])
        self.assertIn("max_total_drawdown", res["account_failure_probability"]["conditions"])
        self.assertIn("entry_time", str(res["account_failure_probability"]))


class BootstrapDaysMinProfitable(unittest.TestCase):
    """Fix round 2, item 3: direct unit tests for `_bootstrap_days(..., min_profitable=...)`, independent of
    the full `metrics()` pipeline. `min_profitable`'s counter gates the bootstrap's PASS event on a running
    count of days whose OWN return clears `profit_threshold_pct` -- see `_bootstrap_days`'s own docstring for
    the entry-day-vs-exit-day approximation this counts against (proven separately, below)."""

    def test_pass_requires_the_full_profitable_day_count_within_the_horizon(self):
        block = [0.02]   # a "day" (one resampled block) whose own return is 2%, always >= a 1% threshold
        kwargs = dict(risk=1.0, iterations=1, seed=1, ruin_level=0.0, failure={}, profit_target=0.01,
                     min_profitable={"count": 3, "profit_threshold_pct": 0.01})
        # Only 2 days fit in the horizon -- 3 profitable days can never accumulate -- no pass, even though the
        # cumulative profit_target (1%) is blown past on day 1 alone.
        _, _, passed_short = P._bootstrap_days([block], horizon_days=2, **kwargs)
        self.assertEqual(passed_short, 0.0)
        # Exactly 3 days fit -- the 3rd profitable day lands inside the horizon -- pass.
        _, _, passed_enough = P._bootstrap_days([block], horizon_days=3, **kwargs)
        self.assertEqual(passed_enough, 1.0)

    def test_a_day_below_the_threshold_never_counts_even_though_profit_target_compounds_past_it(self):
        block = [0.001]   # each day's OWN return (0.1%) is below the 1% profitable-day threshold
        _, _, passed = P._bootstrap_days(
            [block], risk=1.0, horizon_days=100, iterations=1, seed=1, ruin_level=0.0, failure={},
            profit_target=0.01, min_profitable={"count": 3, "profit_threshold_pct": 0.01})
        # (1.001)^100 ~= 1.105 -- the CUMULATIVE profit_target (1%) is reached well within 100 days by
        # compounding alone, but no single day ever clears the per-day threshold, so profitable_so_far stays
        # 0 forever and the gate must never let the pass event fire.
        self.assertEqual(passed, 0.0)

    def test_with_no_min_profitable_the_gate_is_a_no_op_matching_min_days_alone(self):
        """Regression: min_profitable=None must reproduce exactly the pre-addendum-§8.3 behaviour (min_days
        alone), proving this fix did not change FTMO's own reading."""
        block = [0.02]
        kwargs = dict(risk=1.0, iterations=1, seed=1, ruin_level=0.0, failure={}, profit_target=0.01)
        _, _, passed_with_min_days = P._bootstrap_days([block], horizon_days=3, min_days=3, **kwargs)
        self.assertEqual(passed_with_min_days, 1.0)
        _, _, passed_too_short = P._bootstrap_days([block], horizon_days=2, min_days=3, **kwargs)
        self.assertEqual(passed_too_short, 0.0)

    def test_min_days_and_min_profitable_together_require_both(self):
        """Not a real profile shape today (account_profile._validate_rules refuses declaring both), but
        _bootstrap_days itself makes no such assumption -- documented as the conservative combination."""
        profitable_block = [0.02]
        _, _, passed = P._bootstrap_days(
            [profitable_block], risk=1.0, horizon_days=5, iterations=1, seed=1, ruin_level=0.0, failure={},
            profit_target=0.01, min_days=10, min_profitable={"count": 2, "profit_threshold_pct": 0.01})
        # min_profitable's count (2) is satisfied by day 2, but min_days (10) is not satisfied within the
        # 5-day horizon -- BOTH conditions are required, so no pass.
        self.assertEqual(passed, 0.0)


class DayBlocksGroupsByEntryDayNotExitDay(unittest.TestCase):
    """Fix round 2, item 3: proves directly (not merely documented) the root cause of the entry-day
    approximation `_bootstrap_days`'s own docstring names -- `_day_blocks` groups by ENTRY day, so a trade
    that opens one day and closes the next is counted under its OPEN day, not its close day."""

    def test_a_trade_that_closes_the_next_day_is_grouped_under_its_entry_day(self):
        rows = [{"entry_time": "2026-01-01T23:00:00Z", "exit_time": "2026-01-02T01:00:00Z"}]
        blocks = P._day_blocks(rows, [5.0])
        self.assertEqual(blocks, [[5.0]])

    def test_it_merges_with_a_same_entry_day_trade_rather_than_its_own_exit_day(self):
        rows = [{"entry_time": "2026-01-01T23:00:00Z", "exit_time": "2026-01-02T01:00:00Z"},
               {"entry_time": "2026-01-01T10:00:00Z", "exit_time": "2026-01-01T12:00:00Z"}]
        blocks = P._day_blocks(rows, [5.0, 1.0])
        self.assertEqual(blocks, [[5.0, 1.0]],
                         "both trades share ENTRY day 2026-01-01 -> one block, even though the first trade's "
                         "own EXIT day is 2026-01-02")


class DayCountingApproximationIsDisclosedOnTheRecord(unittest.TestCase):
    """Fix round 2, item 3: metrics() stamps `day_counting_approximation` onto the probability results
    whenever min_profitable_days gates the bootstrap (The5ers), and NEVER for a fund whose day rule is plain
    min_trading_days (FTMO) -- proving the disclosure is conditioned on the right thing, not always-on."""

    def test_the5ers_carries_the_approximation_note(self):
        prof = AP.get("the5ers-high-stakes-step1")
        trades = [T(2.0, entry_time=f"2026-01-{1 + i:02d}T00:00:00Z", exit_time=f"2026-01-{1 + i:02d}T02:00:00Z")
                 for i in range(10)]
        res = P.metrics(trades, account=prof, iterations=50, horizon=10)
        self.assertFalse(P.is_unavailable(res["prop_pass_probability"]), res["prop_pass_probability"])
        note = res["prop_pass_probability"].get("day_counting_approximation")
        self.assertIsNotNone(note)
        self.assertIn("entry_day", note)
        self.assertIn("day_counts_for", note)

    def test_ftmo_never_carries_the_approximation_note(self):
        prof = AP.get("ftmo-challenge-phase1")
        trades = [T(2.0, entry_time=f"2026-01-{1 + i:02d}T00:00:00Z") for i in range(10)]
        res = P.metrics(trades, account=prof, iterations=50, horizon=10)
        self.assertFalse(P.is_unavailable(res["prop_pass_probability"]), res["prop_pass_probability"])
        self.assertNotIn("day_counting_approximation", res["prop_pass_probability"])


class NoUniversalScore(unittest.TestCase):
    def test_the_module_offers_no_score_function(self):
        self.assertFalse(hasattr(P, "score"))
        self.assertFalse(hasattr(P, "composite"))
        self.assertFalse(hasattr(P, "rank"))

    def test_asking_for_one_raises_and_says_what_to_do_instead(self):
        with self.assertRaises(P.UniversalScoreRefused) as cm:
            P.refuse_universal_score({"win_rate": 0.5})
        self.assertIn("lexicographic", str(cm.exception))

    def test_the_selection_consumer_is_not_a_score(self):
        # §39's second rule is about the consumer, so it is checked there too.
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        # ADR 0008: the pilot selection is no longer a ranking at all -- every system is judged alone against
        # absolute criteria, so there is no sort key and no blended score to become.
        self.assertIn("SC.evaluate(", src)
        self.assertNotIn(".sort(", src)


class WiredWhereTheNumbersAreProduced(unittest.TestCase):
    def test_the_backtest_summary_carries_the_full_set_beside_its_five_columns(self):
        self.assertIn("perf=_perf.metrics(", BT_SRC)
        self.assertIn("def summarize(taken, *, curve=None, account=None)", BT_SRC)

    def test_the_journal_carries_it_too_and_keeps_its_legacy_keys(self):
        self.assertIn('"perf": _perf.metrics(cl)', JOURNAL_SRC)
        for legacy in ('"closed":', '"wins":', '"losses":', '"win_rate":', '"worst_losing_streak":'):
            self.assertIn(legacy, JOURNAL_SRC, legacy)

    def test_the_journals_legacy_convention_is_documented_rather_than_silently_redefined(self):
        # §59: a figure quoted in an earlier review must keep meaning what it meant.
        self.assertIn("RESEARCH-SEMANTICS NOTE (§59)", JOURNAL_SRC)

    def test_the_stability_rows_carry_it_without_disturbing_the_keys_rank_setups_reads(self):
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("perf=perf", src)
        for k in ("ann=", "q_pos=", "y_pos=", "ruin=", "stab="):
            self.assertIn(k, src, k)

    def test_there_is_exactly_one_computer(self):
        # The defect this closes: two independent definitions of the same metric that agreed by accident.
        self.assertEqual(PERF_SRC.count("def metrics("), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class SmallSampleIsWideNotRefused(unittest.TestCase):
    """User decision 2026-09-19: below 30 trades the prop-pass question still has an answer -- a wide one.
    The metric is computed, flagged `low_confidence`, and carries the spread across bootstrap batches."""

    ACCT = {"rules": {"initial_balance": 100000, "max_total_drawdown": {"pct": 0.10},
                      "profit_target": {"pct": 0.10}}}

    def _trades(self, n, r=-0.4):
        return [{"r_multiple": r if i % 3 else 1.8, "entry_time": f"2026-09-{(i % 28) + 1:02d}T10:00:00Z"}
                for i in range(n)]

    def test_fourteen_trades_produce_a_number_with_a_spread(self):
        res = P.metrics(self._trades(14), account=self.ACCT)
        for mid in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            v = res[mid]
            self.assertNotIn("unavailable", v, f"{mid} was refused at n=14")
            self.assertIsInstance(v["value"], float)
            self.assertTrue(v["low_confidence"])
            self.assertEqual(v["sample"], 14)
            lo, hi = v["spread"][mid]
            self.assertLessEqual(lo, v["value"] + 1e-9); self.assertGreaterEqual(hi, v["value"] - 1e-9)

    def test_a_healthy_sample_carries_no_low_confidence_flag(self):
        res = P.metrics(self._trades(60), account=self.ACCT)
        self.assertNotIn("low_confidence", res["prop_pass_probability"])

    def test_four_trades_are_still_refused_because_the_resample_is_degenerate(self):
        res = P.metrics(self._trades(4), account=self.ACCT)
        self.assertIn("unavailable", res["risk_of_ruin"])
