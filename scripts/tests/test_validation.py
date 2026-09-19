"""CLAUDE.md §45 -- twelve ways to break a candidate, eleven things to check, and the posture that decides
what silence means.

§45's operative sentence is not the list:

    "Actively attempt to disprove candidates. Do not only search for evidence that a candidate works."

That is a claim about the DEFAULT, and a validation suite's default is visible in exactly one place: what it
does with a check that did not run. If `NOT_RUN` counts as a pass, a candidate can survive by being untested —
which is the shape every validation suite fails in. So the tests below put more weight on that than on the
arithmetic: a candidate that ran no checks at all must not come back SURVIVED, and neither must one where a
single check was skipped.

The arithmetic is checked against hand-computed values, and each method is additionally exercised against a
deliberately fragile synthetic system to prove it can actually break something. A test that only ever sees a
robust candidate proves nothing about a validator.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import validation as V
import research_ledger as RL

REGISTRY = os.path.join(ROOT, "docs", "architecture", "validation.json")


def _bullets(after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    section = spec.split("45. VALIDATION", 1)[1].split("46. REPRODUCIBILITY", 1)[0]
    body = section.split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def T(r, **kw):
    return dict(R=r, **kw)


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_twelve_validation_methods_are_declared(self):
        self.assertEqual([V.METHODS[m]["spec_name"] for m in V.METHOD_ORDER],
                         _bullets("Support:", "Actively attempt to disprove"))

    def test_all_eleven_checks_are_declared(self):
        self.assertEqual([V.CHECKS[c]["spec_name"] for c in V.CHECK_ORDER], _bullets("Check:", "==="))

    def test_the_not_run_verdict_must_declare_that_it_is_not_a_pass(self):
        # This is §45's posture expressed as a registry invariant, and the loader enforces it.
        self.assertIn("NOT a pass", V._DATA["verdicts"][V.NOT_RUN])

    def test_a_registry_that_softens_not_run_into_a_pass_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["verdicts"][V.NOT_RUN] = "the check did not run; treated as fine"
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-validation.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(V.RegistryError) as cm:
                V._load(p)
            self.assertIn("passes by being untested", str(cm.exception))
        finally:
            os.remove(p)

    def test_no_threshold_is_hardcoded_in_the_registry(self):
        # §45 says what to check, not where to draw a line; a line here would be a project parameter
        # masquerading as a rule. Checked per entry rather than over the whole blob, because the note
        # EXPLAINING the policy naturally contains the word.
        self.assertIn("No threshold in this file", V._DATA["_thresholds_are_the_callers"])
        for row in V._DATA["methods"] + V._DATA["checks"]:
            for k, v in row.items():
                self.assertNotIsInstance(v, (int, float), f"{row['id']}.{k} looks like a threshold")
            self.assertNotIn("threshold", row, row["id"])


class ThePostureIsRefutation(unittest.TestCase):
    def test_a_candidate_with_no_checks_is_not_survived(self):
        # The failure every validation suite has: passing by being untested.
        res = V.disprove(checks={})
        self.assertEqual(res["verdict"], V.NOT_RUN)
        self.assertEqual(len(res["not_run"]), len(V.CHECK_ORDER))

    def test_one_skipped_check_prevents_a_survived_verdict(self):
        checks = {c: V._verdict(True, "fine") for c in V.CHECK_ORDER}
        del checks[V.CHECK_ORDER[3]]
        self.assertEqual(V.disprove(checks=checks)["verdict"], V.NOT_RUN)

    def test_one_refuted_check_refutes_the_candidate(self):
        checks = {c: V._verdict(True, "fine") for c in V.CHECK_ORDER}
        checks["consistency"] = V._verdict(False, "two trades carry it")
        res = V.disprove(checks=checks)
        self.assertEqual(res["verdict"], V.REFUTED)
        self.assertEqual(res["refuted_by"], ["consistency"])

    def test_refuted_outranks_not_run(self):
        checks = {c: V._verdict(True, "fine") for c in V.CHECK_ORDER}
        checks["consistency"] = V._verdict(False, "broken")
        checks["sample_size"] = V.not_run("skipped")
        self.assertEqual(V.disprove(checks=checks)["verdict"], V.REFUTED)

    def test_only_a_fully_checked_unbroken_candidate_survives(self):
        checks = {c: V._verdict(True, "fine") for c in V.CHECK_ORDER}
        self.assertEqual(V.disprove(checks=checks)["verdict"], V.SURVIVED)

    def test_every_declared_check_appears_in_the_output_even_when_absent(self):
        # A missing check must be visible as NOT_RUN, not absent from the report.
        out = V.disprove(checks={})["checks"]
        for cid in V.CHECK_ORDER:
            self.assertIn(cid, out, cid)

    def test_the_output_states_the_posture(self):
        self.assertIn("NOT_RUN is not a pass", V.disprove(checks={})["_posture"])


class TheMethodsCanActuallyBreakSomething(unittest.TestCase):
    """A validator that only ever sees a robust candidate proves nothing."""

    def test_walk_forward_separates_a_spread_edge_from_a_concentrated_one(self):
        spread = [T(1.0 if i % 2 else -0.5, entry_time=f"2026-01-{i % 28 + 1:02d}") for i in range(40)]
        concentrated = ([T(-0.2, entry_time=f"2026-01-{i % 28 + 1:02d}") for i in range(30)] +
                        [T(5.0, entry_time=f"2026-02-{i % 28 + 1:02d}") for i in range(10)])
        self.assertGreater(V.walk_forward(spread)["positive_folds"],
                           V.walk_forward(concentrated)["positive_folds"])

    def test_walk_forward_refuses_a_population_too_small_to_fold(self):
        r = V.walk_forward([T(1.0, entry_time="2026-01-01")] * 3, folds=5)
        self.assertEqual(r["verdict"], V.NOT_RUN)

    def test_parameter_sensitivity_exposes_a_result_that_lives_at_one_setting(self):
        def fragile(cfg):
            return [T(1.0)] * 20 if cfg.get("min_rr") == 3.0 else [T(-1.0)] * 20
        r = V.parameter_sensitivity(fragile, parameter="min_rr", values=[2.0, 2.5, 3.0, 3.5],
                                    baseline_value=3.0)
        self.assertEqual(r["positive_settings"], 1)
        self.assertEqual(r["settings_tried"], 4)

    def test_parameter_sensitivity_passes_a_result_that_survives_its_neighbourhood(self):
        r = V.parameter_sensitivity(lambda cfg: [T(1.0)] * 20, parameter="min_rr",
                                    values=[2.0, 3.0, 4.0])
        self.assertEqual(r["positive_settings"], 3)

    def test_partition_finds_an_edge_carried_by_one_group(self):
        trades = ([T(3.0, symbol="BTCUSDT") for _ in range(10)] +
                  [T(-1.0, symbol="ETHUSDT") for _ in range(10)] +
                  [T(-1.0, symbol="SOLUSDT") for _ in range(10)])
        p = V.partition(trades, lambda t: t["symbol"], name="instrument")
        self.assertEqual(p["n_groups"], 3)
        self.assertEqual(p["positive"], ["BTCUSDT"])

    def test_one_partition_implementation_serves_the_four_questions(self):
        # §45 lists them separately because they are four questions; the arithmetic is one.
        trades = [T(1.0, k="a"), T(-1.0, k="b")]
        for name in ("regime", "instrument", "session", "time_period"):
            p = V.partition(trades, lambda t: t["k"], name=name)
            self.assertEqual(p["method"], f"{name}_variation")

    def test_monte_carlo_reports_the_drawdown_distribution_over_orderings(self):
        rs = [3.0, -1.0, -1.0, -1.0] * 10
        r = V.monte_carlo([T(x) for x in rs], iterations=300, seed=1)
        self.assertEqual(r["n"], 40)
        self.assertAlmostEqual(r["observed_sum_R"], sum(rs))
        # The worst ordering must be at least as bad as the median one.
        self.assertGreaterEqual(r["max_drawdown_R_worst"], r["max_drawdown_R_p50"])

    def test_monte_carlo_is_deterministic_for_a_seed(self):
        rs = [T(x) for x in ([2.0, -1.0] * 15)]
        a = V.monte_carlo(rs, iterations=200, seed=7)
        b = V.monte_carlo(rs, iterations=200, seed=7)
        self.assertEqual(a["max_drawdown_R_p95"], b["max_drawdown_R_p95"])

    def test_monte_carlo_refuses_a_population_too_small_to_resample(self):
        self.assertEqual(V.monte_carlo([T(1.0)] * 5)["verdict"], V.NOT_RUN)

    def test_perturbation_exposes_a_result_that_needs_an_exact_fill(self):
        def exact(j):
            return [T(1.0)] * 20 if j.get("entry_offset_pct", 0) == 0 else [T(-1.0)] * 20
        r = V.perturbation(exact, jitters=[{"entry_offset_pct": 0}, {"entry_offset_pct": 0.001},
                                           {"entry_offset_pct": -0.001}], baseline=[T(1.0)] * 20)
        self.assertEqual(r["positive_under_jitter"], 1)
        self.assertEqual(r["jitters_tried"], 3)

    def test_stress_names_which_hostile_scenarios_were_survived(self):
        def engine(cfg):
            return [T(1.0 - cfg["fee_pct"] * 100)] * 20
        r = V.stress(engine, scenarios={"double_fee": {"fee_pct": 0.001},
                                        "brutal_fee": {"fee_pct": 0.02}})
        self.assertEqual(r["survived"], ["double_fee"])
        self.assertEqual(r["scenarios_tried"], 2)

    def test_robustness_refuses_to_call_three_passes_and_one_failure_robust(self):
        good = V.parameter_sensitivity(lambda c: [T(1.0)] * 20, parameter="p", values=[1, 2])
        bad = V.stress(lambda c: [T(-1.0)] * 20, scenarios={"s": {}})
        self.assertEqual(V.robustness(good, bad)["verdict"], V.REFUTED)
        self.assertEqual(V.robustness(good)["verdict"], V.SURVIVED)

    def test_robustness_reports_not_run_when_a_component_could_not_run(self):
        good = V.parameter_sensitivity(lambda c: [T(1.0)] * 20, parameter="p", values=[1, 2])
        skipped = V.monte_carlo([T(1.0)] * 3)
        self.assertEqual(V.robustness(good, skipped)["verdict"], V.NOT_RUN)


class TheChecks(unittest.TestCase):
    def test_sample_size_uses_the_threshold_it_was_given_and_records_it(self):
        r = V.check_sample_size([T(1.0)] * 20, minimum=30)
        self.assertEqual(r["verdict"], V.REFUTED)
        self.assertEqual(r["threshold"], 30)
        self.assertEqual(V.check_sample_size([T(1.0)] * 20, minimum=10)["verdict"], V.SURVIVED)

    def test_consistency_catches_an_edge_carried_by_a_handful_of_trades(self):
        carried = [T(-0.1)] * 99 + [T(50.0)]
        self.assertEqual(V.check_consistency(carried)["verdict"], V.REFUTED)
        spread = [T(0.3)] * 100
        self.assertEqual(V.check_consistency(spread)["verdict"], V.SURVIVED)

    def test_consistency_does_not_run_on_a_losing_population(self):
        # There is no positive total to attribute, and inventing a verdict would be worse than saying so.
        self.assertEqual(V.check_consistency([T(-1.0)] * 20)["verdict"], V.NOT_RUN)

    def test_partition_dependency_refutes_an_edge_carried_by_one_group(self):
        trades = ([T(3.0, s="a")] * 10 + [T(-1.0, s="b")] * 10 + [T(-1.0, s="c")] * 10)
        p = V.partition(trades, lambda t: t["s"], name="instrument")
        self.assertEqual(V.check_partition_dependency(p)["verdict"], V.REFUTED)

    def test_partition_dependency_survives_a_broad_edge(self):
        trades = [T(1.0, s=x) for x in "abcd" for _ in range(5)]
        p = V.partition(trades, lambda t: t["s"], name="instrument")
        self.assertEqual(V.check_partition_dependency(p)["verdict"], V.SURVIVED)

    def test_execution_assumptions_requires_every_scenario_not_most(self):
        r = V.stress(lambda c: [T(1.0 if c.get("ok") else -1.0)] * 20,
                     scenarios={"a": {"ok": True}, "b": {"ok": False}})
        self.assertEqual(V.check_execution_assumptions(r)["verdict"], V.REFUTED)

    def test_data_quality_reads_the_38_verdict(self):
        self.assertEqual(V.check_data_quality({"verdict": "FLAGGED"})["verdict"], V.SURVIVED)
        self.assertEqual(V.check_data_quality({"verdict": "INVALID"})["verdict"], V.REFUTED)
        self.assertEqual(V.check_data_quality(None)["verdict"], V.NOT_RUN)

    def test_selection_bias_and_multiple_testing_refuse_while_the_denominator_is_incomplete(self):
        # The repo's real state: two searches predate the experiment store, so the denominator is unknown and
        # a correction computed from the recorded part would understate it.
        b = RL.budget([])
        for fn in (V.check_selection_bias, V.check_multiple_testing):
            r = fn(b)
            self.assertEqual(r["verdict"], V.NOT_RUN, fn.__name__)
            self.assertIn("unrecorded" if fn is V.check_multiple_testing else "predate", r["why"])

    def test_survivorship_reports_rather_than_passing(self):
        # No threshold makes this pass; it is a property of the instrument set (§9).
        r = V.check_survivorship()
        self.assertEqual(r["verdict"], V.NOT_RUN)
        self.assertIn("structural", r["why"])


class OOSIsGatedBy44(unittest.TestCase):
    def test_oos_refuses_to_measure_development_data_and_call_it_validation(self):
        called = []
        r = V.oos(lambda cfg: called.append(cfg) or [T(1.0)] * 50, "crypto-history-2023-2026")
        self.assertEqual(r["verdict"], V.NOT_RUN)
        self.assertEqual(called, [], "the evaluator must not even be invoked on development data")

    def test_oos_refuses_an_undeclared_period(self):
        self.assertEqual(V.oos(lambda cfg: [], "some-period")["verdict"], V.NOT_RUN)

    def test_oos_runs_once_a_period_is_genuinely_untouched(self):
        RL.PERIODS["t-oos"] = {"id": "t-oos", "range": ["2026-01-01", "2026-06-30"],
                               "state": RL.UNTOUCHED, "why": "carved out for this test"}
        try:
            r = V.oos(lambda cfg: [T(1.0)] * 50, "t-oos")
            self.assertEqual(r["n"], 50)
            self.assertAlmostEqual(r["expectancy"], 1.0)
        finally:
            RL.PERIODS.pop("t-oos", None)


class InSampleIsLabelledAsNotValidation(unittest.TestCase):
    def test_in_sample_says_it_is_the_baseline(self):
        r = V.in_sample([T(1.0)] * 10)
        self.assertIn("not evidence", r["_note"])
        self.assertEqual(r["n"], 10)


class AgainstTheRealEngine(unittest.TestCase):
    """The methods must work on the repository's own trades, not only on synthetic ones."""

    def test_partition_and_walk_forward_run_over_a_real_backtest_population(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bt_val", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
        scan = bt.scan("BTCUSDT", "4H")
        if not scan:
            self.skipTest("no BTCUSDT 4H history fixture")
        trades = scan["trades"]["ICT"] + scan["trades"]["COMBINED-BOOK"]
        if len(trades) < 12:
            self.skipTest(f"only {len(trades)} trades in the fixture")
        p = V.partition(trades, lambda t: t["side"], name="regime")
        self.assertGreaterEqual(p["n_groups"], 1)
        wf = V.walk_forward(trades, folds=3)
        self.assertEqual(wf.get("folds", 3), 3)
        self.assertIn("results", wf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
