"""CLAUDE.md §33 in the research path: a personal account and a prop account do not lose the same way.

The account-rule engine was complete and tested (`scripts/tests/test_account_profile.py` drives every limit),
and the backtest never called it. `simulate()` had exactly one loss condition -- `RUIN_FRAC`, equity at 10 % of
the start -- which is the PERSONAL notion of "blown", applied to every account including prop ones. So:

* every §39 money metric (`pnl`, `risk_of_ruin`, `account_failure_probability`, `prop_pass_probability`) came
  back `unavailable: no account profile supplied` in every real run, and
* a setup that a prop firm would have cut at a 10 % drawdown was ranked as if it had kept trading to the end.

The demonstration that matters is `test_the_same_setup_can_win_personally_and_fail_a_prop_account`: the same
sixty trades on the same data finish at +48 % under the personal rule and are dead on trade ten under a 10 %
peak-drawdown rule. Ranking both against "blown" alone cannot tell those apart, which is the whole reason the
distinction was asked for.

No prop profile is ROUTABLE. This began as "no prop profile is SHIPPED" (§57: configuration for an account
nobody holds is speculative), and the user's 2026-09-18 decision changed it: two firms' rule sets now ship as
RESEARCH templates, so a Trading System can be backtested against real fail conditions before anybody opens a
challenge. What §57 was protecting is kept exactly, and by the loader rather than by absence -- both templates
declare an environment in `unroutable_environments`, so they are loadable by id for a backtest and can never
be resolved by an order path (`account_profile.for_venue` refuses outright). `--account-file` remains how you
evaluate against your own firm's numbers without claiming they describe an account here.
"""
import datetime
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP  # noqa: E402
import performance as P       # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bt = _load("bt", "backtest-methods.py")
SR = _load("stability_report", "stability-report.py")


def prop(pct=0.10, basis="peak_equity", target=0.08):
    """A prop-shaped rule set built HERE, in a test, never shipped as configuration."""
    p = {"id": "eval-prop", "what": "test template", "context_type": "PROP_CHALLENGE", "venue": "mt5",
         "environment": "backtest", "rules": {k: None for k in AP.RULE_KEYS}}
    p["rules"].update({"initial_balance": 10000.0, "max_positions": {"mode": "full_book"},
                       "consistency_rules": [], "custom_failure_conditions": [],
                       "max_total_drawdown": {"pct": pct, "basis": basis, "action": "HALT"}})
    if target is not None:
        p["rules"]["profit_target"] = {"pct": target}
    return p


def run(n_losses=12, n=60):
    d = datetime.date(2025, 1, 2)
    out = []
    for i in range(n):
        t = (d + datetime.timedelta(days=i)).isoformat()
        out.append(dict(entry_time=t + "T10:00:00Z", exit_time=t + "T15:00:00Z", symbol="XAUUSD", side="long",
                        entry=100.0, stop=99.0, R=(-1.0 if i < n_losses else 1.2), R_planned=9.0))
    return out


class TheSameSetupIsTwoDifferentAnswers(unittest.TestCase):
    def test_the_same_setup_can_win_personally_and_fail_a_prop_account(self):
        trades = run()
        eq_personal, _, taken_personal = bt.simulate(trades, 0.0005)
        self.assertIsNone(bt.SIM_LAST["failed_by"])
        self.assertGreater(eq_personal, bt.START)              # +48 % on this data
        self.assertEqual(len(taken_personal), len(trades))

        eq_prop, _, taken_prop = bt.simulate(trades, 0.0005, account=prop())
        self.assertLess(eq_prop, bt.START)
        self.assertLess(len(taken_prop), len(taken_personal))  # the run ended early
        self.assertIn("drawdown", bt.SIM_LAST["failed_by"])

    def test_the_run_records_which_rule_ended_it_and_whose_account(self):
        bt.simulate(run(), 0.0005, account=prop())
        self.assertIn("peak_equity", bt.SIM_LAST["failed_by"])
        self.assertEqual(bt.SIM_LAST["account"], "eval-prop")

    def test_a_tighter_drawdown_kills_it_sooner(self):
        _, _, loose = bt.simulate(run(), 0.0005, account=prop(pct=0.10))
        _, _, tight = bt.simulate(run(), 0.0005, account=prop(pct=0.05))
        self.assertLess(len(tight), len(loose))

    def test_without_a_profile_the_only_loss_condition_is_a_blown_balance(self):
        # 40 straight losses at 1 % each cannot reach 10 % of the start, so nothing stops it.
        _, _, taken = bt.simulate(run(n_losses=40, n=40), 0.0005)
        self.assertEqual(len(taken), 40)
        self.assertIsNone(bt.SIM_LAST["ruin"])

    def test_a_real_dollar_profile_is_not_halted_by_a_scale_mismatch_on_trade_one(self):
        """Found 2026-09-18 running the A3 CLI evidence command against ftmo-challenge-phase1: every method
        failed by 'drawdown' with ZERO trades taken, on every run, regardless of R. Root cause: the engine's
        own equity is tracked at a fixed notional START ($10,000, a readability constant -- see START's own
        comment); `max_total_drawdown`'s basis 'initial_balance' is read by account_profile._basis_value as
        the PROFILE's OWN declared dollar figure ($100,000 for FTMO/The5ers). Comparing the $10,000-scaled
        equity against a $90,000 floor (90 % of $100,000) fails unconditionally on the very first trade. Fixed
        fractional % returns are scale-invariant, so the fix rescales the equity/peak/day-start facts onto the
        profile's own declared balance rather than changing what the numbers MEAN."""
        wins = [dict(entry_time=f"2025-01-0{1 + i}T10:00:00Z", exit_time=f"2025-01-0{1 + i}T15:00:00Z",
                     symbol="XAUUSD", side="long", entry=100.0, stop=99.0, R=1.0, R_planned=9.0) for i in range(5)]
        _, _, taken = bt.simulate(wins, 0.0001, account=AP.get("ftmo-challenge-phase1"))
        self.assertEqual(len(taken), 5, bt.SIM_LAST["failed_by"])
        self.assertIsNone(bt.SIM_LAST["failed_by"])

    def test_the_rescale_still_catches_a_real_drawdown_breach(self):
        """The fix must not just stop halting -- it must halt at the SAME PERCENTAGE the profile declares,
        just measured against the profile's own $100,000 rather than the engine's $10,000."""
        losses = [dict(entry_time=f"2025-02-{1 + i:02d}T10:00:00Z", exit_time=f"2025-02-{1 + i:02d}T15:00:00Z",
                       symbol="XAUUSD", side="long", entry=100.0, stop=95.0, R=-1.0, R_planned=9.0) for i in range(25)]
        _, _, taken = bt.simulate(losses, 0.0001, account=AP.get("ftmo-challenge-phase1"))
        self.assertLess(len(taken), 25, "a 5 % stop repeated 25 times must breach a 10 % max_total_drawdown")
        self.assertIn("drawdown", bt.SIM_LAST["failed_by"])

    def test_the_rules_are_not_reimplemented_here(self):
        # §33's reader stays the one reader; this engine walks the curve and asks it.
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        self.assertIn("_AP.halt_check(", src)
        body = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
        for reimplementation in ("max_total_drawdown", "trailing_drawdown", "profit_target"):
            self.assertNotIn(f'"{reimplementation}"', body, f"{reimplementation} is being re-decided here")


class TheMoneyMetricsComeAlive(unittest.TestCase):
    def test_without_an_account_they_are_unavailable_by_name(self):
        m = P.metrics([{"net_R": 1.0} for _ in range(40)])
        for k in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability", "pnl"):
            self.assertIn("unavailable", m[k], k)

    def test_with_an_account_and_enough_sample_they_compute(self):
        trades = [{"net_R": (1.5 if i % 3 else -1.0)} for i in range(45)]
        eq = [10000.0]
        for t in trades:
            eq.append(eq[-1] * (1 + 0.01 * t["net_R"]))
        m = P.metrics(trades, equity=eq, account=prop())
        for k in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            self.assertIsInstance(m[k].get("value"), float, k)
            self.assertEqual(m[k]["sample"], 45)

    def test_failure_is_a_strictly_wider_event_than_ruin(self):
        # §33: a prop account fails long before the balance is gone, so failure >= ruin always.
        trades = [{"net_R": (1.2 if i % 3 else -1.0)} for i in range(45)]
        eq = [10000.0]
        for t in trades:
            eq.append(eq[-1] * (1 + 0.01 * t["net_R"]))
        m = P.metrics(trades, equity=eq, account=prop())
        self.assertGreaterEqual(m["account_failure_probability"]["value"], m["risk_of_ruin"]["value"])

    def test_an_account_with_no_profit_target_cannot_be_passed_and_says_so(self):
        """The personal/prop distinction, in one metric: a personal account has no challenge to complete, so
        `prop_pass_probability` is unavailable as a PROPERTY OF THE PROFILE -- not as a gap in the metric."""
        trades = [{"net_R": (1.5 if i % 3 else -1.0)} for i in range(45)]
        eq = [10000.0]
        for t in trades:
            eq.append(eq[-1] * (1 + 0.01 * t["net_R"]))
        m = P.metrics(trades, equity=eq, account=prop(target=None))
        self.assertIn("no profit_target", m["prop_pass_probability"]["unavailable"])
        # ...while the failure probability, which every account has, still computes.
        self.assertIsInstance(m["account_failure_probability"]["value"], float)

    def test_a_small_sample_is_computed_and_flagged_not_refused(self):
        """Until 2026-09-19 a 17-trade population was refused outright by a floor of 30. The user asked for
        that floor to go: a prop account's question ("would this have passed?") has an answer at n=17, and a
        wide number that SAYS it is wide beats a refusal. Below min_n (5) it is still refused -- there the
        resample is degenerate."""
        m = P.metrics([{"net_R": 1.0} for _ in range(17)], account=prop())
        self.assertNotIn("unavailable", m["risk_of_ruin"])
        self.assertTrue(m["risk_of_ruin"]["low_confidence"])
        self.assertIn("spread", m["risk_of_ruin"])
        deg = P.metrics([{"net_R": 1.0} for _ in range(4)], account=prop())
        self.assertIn("unavailable", deg["risk_of_ruin"])


class NoPropAccountIsRoutable(unittest.TestCase):
    """A prop account nobody holds must never be reachable by an order path.

    Until 2026-09-18 this was enforced by absence -- no prop profile shipped at all (§57). The user asked for
    prop fail conditions in the backtest, so two firms' rule sets now ship as RESEARCH templates and the
    guarantee moved from "there is nothing to route to" to "the loader refuses to route to it". The second is
    the stronger statement, and unlike absence it survives somebody adding a third template.
    """

    def test_the_registry_says_why_prop_profiles_ship_at_all(self):
        d = json.load(open(os.path.join(ROOT, "docs", "architecture", "account-profiles.json"),
                           encoding="utf-8"))
        self.assertIn("_prop_profiles_why", d)
        self.assertIn("research", d["_prop_profiles_why"].lower())

    def test_every_shipped_prop_profile_is_research_only(self):
        prop = [p for p, v in AP.PROFILES.items()
                if v["context_type"] in ("PROP_CHALLENGE", "PROP_FUNDED")]
        self.assertTrue(prop, "no prop profile ships; this test would prove nothing")
        for pid in prop:
            with self.subTest(profile=pid):
                self.assertIn(AP.PROFILES[pid]["environment"], AP.UNROUTABLE_ENVIRONMENTS)

    def test_no_order_path_can_resolve_a_prop_profile(self):
        """The guarantee itself, driven through the lookup an order path actually calls."""
        for pid, prof in AP.PROFILES.items():
            if prof["context_type"] not in ("PROP_CHALLENGE", "PROP_FUNDED"):
                continue
            for env in AP._TE.ENV_NAMES:          # every environment execution can be switched to
                with self.subTest(profile=pid, environment=env):
                    try:
                        got = AP.for_venue(prof["venue"], env)
                    except ValueError:
                        continue                   # refused: the account is unreachable, which is the point
                    self.assertNotEqual(got["id"], pid)

    def test_a_prop_template_is_still_loadable_by_id_for_a_backtest(self):
        """Unreachable by execution must not mean unusable by research -- that was the whole request."""
        prop = [p for p, v in AP.PROFILES.items()
                if v["context_type"] in ("PROP_CHALLENGE", "PROP_FUNDED")]
        for pid in prop:
            with self.subTest(profile=pid):
                prof = AP.get(pid)
                self.assertEqual(prof["id"], pid)
                self.assertIsNotNone(AP.rule(prof, "max_total_drawdown"))

    def test_the_context_types_exist_so_a_real_one_can_be_declared(self):
        for t in ("PERSONAL", "PROP_CHALLENGE", "PROP_FUNDED"):
            self.assertIn(t, AP.CONTEXT_TYPES)

    def test_the_stability_report_can_evaluate_against_a_profile_it_does_not_own(self):
        import argparse
        names = {a.dest for a in SR.main.__globals__["argparse"].ArgumentParser()._actions} if False else None
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn('"--account-file"', src)
        self.assertIn("account=account", src)



class HaltIsTwoDifferentFacts(unittest.TestCase):
    """The distinction that decides whether an `--account` run means anything.

    §33's `action: HALT` covers both "the account is gone" (a prop drawdown breach: terminal) and "stop until a
    human resumes" (`pilot-mt5-demo`'s five-consecutive-losses circuit breaker). A research run ends on either,
    which is right for the first and wrong for the second -- over years of history the breaker kills every row
    in its first losing streak and the table then measures how long until five losses, not the setup.

    Recorded rather than silently resolved: no account is applied by DEFAULT, so the choice is always a
    deliberate one, and the docstring on `_account_stop` says which kind is which.
    """

    def test_the_pilots_own_breaker_would_end_a_research_run_at_five_losses(self):
        d = datetime.date(2025, 1, 2)
        losses = []
        for i in range(30):
            t = (d + datetime.timedelta(days=i)).isoformat()
            losses.append(dict(entry_time=t + "T10:00:00Z", exit_time=t + "T15:00:00Z", symbol="XAUUSD", side="long",
                               entry=100.0, stop=99.0, R=-1.0, R_planned=9.0))
        _, _, taken = bt.simulate(losses, 0.0005, account=AP.get("pilot-mt5-demo"))
        self.assertEqual(len(taken), 5)
        self.assertIn("consecutive losses", bt.SIM_LAST["failed_by"])

    def test_which_is_why_no_account_is_applied_by_default(self):
        import inspect
        sig = inspect.signature(bt.simulate)
        self.assertIsNone(sig.parameters["account"].default)
        doc = bt._account_stop.__doc__
        self.assertIn("circuit-breaker", doc)
        self.assertIn("terminal", doc)

    def test_the_facts_a_backtest_cannot_produce_are_named_not_omitted(self):
        # An omitted fact makes the rule needing it silently inapplicable -- an account limit disappearing
        # without anyone deciding to remove it.
        self.assertIn("consec_errors", bt.UNAPPLICABLE_ACCOUNT_FACTS)
        bt.simulate([], 0.0005, account=prop())
        self.assertEqual(bt.SIM_LAST["rules_not_applicable"], ["consec_errors"])

    def test_the_facts_it_can_produce_are_all_supplied(self):
        # Everything account_state() reads, except the declared-inapplicable one.
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        for fact in ("realised_today", "consec_losses", "profit_by_day", "profit_by_symbol",
                     "peak_equity", "day_start_equity"):
            self.assertIn(f'"{fact}"', src, fact)


if __name__ == "__main__":
    unittest.main(verbosity=2)
