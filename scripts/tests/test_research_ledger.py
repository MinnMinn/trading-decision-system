"""CLAUDE.md §43 EXPERIMENT BUDGET + §44 OOS EXPOSURE -- what was tried, and what trying it did to the data.

Two sections over one structure, and two failure modes that look like success:

**§43: "Do not hide the number of experiments performed."** A counter that is zero because nothing was
recorded reads exactly like a counter that is zero because nothing was tried. Two real searches predate the
§42 store — seven ICT target-model variants over one dataset, and 120 candidate rows narrowed to 6 with
nothing recorded about the 114 — and folding them into a total would make an unrecorded search
indistinguishable from a recorded one. They are reported as `unrecorded` and the tests below require that.

**§44: "Do not label it as pristine validation anymore."** The transition is one-way. A state machine that can
go back is a label that can be restored by whoever needs it to be, so `unexpose()` exists only to raise.

The honest current state, which the tests pin so it cannot drift silently: **no period can validate anything.**
Every span of history this repo holds was read by the runs that produced the live selection.
"""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import research_ledger as RL
import experiment as X

REGISTRY = os.path.join(ROOT, "docs", "architecture", "research-ledger.json")


def _bullets(section_title, next_title, after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    section = spec.split(section_title, 1)[1].split(next_title, 1)[0]
    body = section.split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_seven_43_counters_are_declared(self):
        want = _bullets("43. EXPERIMENT BUDGET", "44. OOS EXPOSURE",
                        "Record where applicable:", "Do not hide the number")
        self.assertEqual([RL.counter_name(c) for c in RL.COUNTERS], want)

    def test_all_four_things_43_says_to_account_for_are_declared(self):
        want = _bullets("43. EXPERIMENT BUDGET", "44. OOS EXPOSURE", "Account for:", "===")
        self.assertEqual([a["spec_name"] for a in RL._DATA["budget"]["account_for"]], want)

    def test_all_four_44_data_states_are_declared(self):
        want = _bullets("44. OOS EXPOSURE", "45. VALIDATION",
                        "the system can distinguish:", "Do not continue treating")
        self.assertEqual([s["spec_name"] for s in RL._DATA["oos"]["states"]], want)

    def test_all_five_exposure_triggers_are_declared(self):
        want = _bullets("44. OOS EXPOSURE", "45. VALIDATION",
                        "Once OOS data has materially influenced:", "that OOS period is exposed")
        self.assertEqual([t["spec_name"] for t in RL._DATA["oos"]["exposure_triggers"]], want)

    def test_every_declared_counter_has_a_computation(self):
        # A declared counter nobody computes is a number silently reported as zero.
        counts = RL.budget()["counts"]
        for cid in RL.COUNTERS:
            self.assertIn(cid, counts, cid)

    def test_a_registry_with_an_invented_data_state_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["oos"]["states"].append({"id": "probably_fine", "spec_name": "probably fine", "means": "..."})
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-ledger.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(RL.RegistryError):
                RL._load(p)
        finally:
            os.remove(p)

    def test_a_period_labelled_untouched_that_admits_it_was_read_is_refused(self):
        # The contradiction §44 exists to prevent, caught by the loader rather than by a reader's attention.
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["oos"]["periods"][0]["state"] = "oos_untouched"
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-ledger2.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(RL.RegistryError) as cm:
                RL._load(p)
            self.assertIn("untouched validation data", str(cm.exception))
        finally:
            os.remove(p)

    def test_every_period_says_why_it_is_in_the_state_it_is_in(self):
        for pid in RL.PERIODS:
            self.assertTrue(RL.period(pid)["why"].strip(), pid)


class TheBudgetIsComputedNotRemembered(unittest.TestCase):
    def _rec(self, **over):
        r = X.Record(hypothesis=over.pop("hypothesis", "h"), motivation="m",
                     parent_trading_system_version="v1",
                     candidate_version=over.pop("candidate_version", "v1.1"),
                     experiment_id=over.pop("experiment_id", None))
        base = {"failure_pattern": "fp", "dataset_snapshot": {"snapshot_id": "ds1"},
                "configuration_snapshot": {}, "account_configuration": {}, "risk_configuration": {},
                "news_configuration": {}, "session_configuration": {}, "parameters": {"x": 1},
                "random_seed": 1, "test_periods": {"in_sample": "a", "oos": "b"},
                "validation_method": "oos", "metrics": {"n": 1}, "robustness_results": X.unavailable("n/a"),
                "system_version": "v1"}
        base.update(over)
        for k, v in base.items():
            r.set(k, v)
        return r.seal()

    def test_counts_are_derived_from_the_store(self):
        recs = [self._rec(experiment_id="a"), self._rec(experiment_id="b", hypothesis="h2",
                                                        candidate_version="v1.2")]
        b = RL.budget(recs)
        self.assertEqual(b["experiments_recorded"], 2)
        self.assertEqual(b["counts"]["hypothesis_count"], 2)
        self.assertEqual(b["counts"]["candidate_count"], 2)

    def test_two_experiments_on_one_hypothesis_are_one_hypothesis_and_two_candidates(self):
        recs = [self._rec(experiment_id="a", candidate_version="v1.1"),
                self._rec(experiment_id="b", candidate_version="v1.2")]
        b = RL.budget(recs)
        self.assertEqual(b["counts"]["hypothesis_count"], 1)
        self.assertEqual(b["counts"]["candidate_count"], 2)

    def test_dataset_reuse_counts_reads_of_the_same_snapshot(self):
        recs = [self._rec(experiment_id="a"), self._rec(experiment_id="b"),
                self._rec(experiment_id="c", dataset_snapshot={"snapshot_id": "ds2"})]
        self.assertEqual(RL.budget(recs)["counts"]["dataset_reuse"], {"ds1": 2, "ds2": 1})

    def test_oos_reuse_counts_only_the_periods_declared_out_of_sample(self):
        recs = [self._rec(experiment_id="a"), self._rec(experiment_id="b")]
        self.assertEqual(RL.budget(recs)["counts"]["oos_reuse"], {"b": 2})

    def test_a_swept_parameter_is_counted_as_a_search_not_as_one_candidate(self):
        # A sweep of twenty values is twenty tests wearing one hypothesis.
        one = self._rec(experiment_id="a", parameters={"min_rr": {"from": 2.0, "to": 3.0}})
        sweep = self._rec(experiment_id="b", parameters={"min_rr": {"sweep": [2.0, 2.5, 3.0, 3.5]}})
        listed = self._rec(experiment_id="c", parameters={"targets": ["std2", "std25", "std4"]})
        self.assertEqual(RL.budget([one])["counts"]["parameter_searches"], 0)
        self.assertEqual(RL.budget([sweep, listed])["counts"]["parameter_searches"], 2)

    def test_rejected_candidates_are_counted_because_they_still_consumed_a_test(self):
        r = self._rec(experiment_id="a")
        rejected = self._rec(experiment_id="b", decision={"decision": "REJECTED", "by": "human"})
        self.assertEqual(RL.budget([r, rejected])["counts"]["rejected_candidates"], 1)

    def test_an_empty_store_reports_zero_and_does_not_pretend_otherwise(self):
        b = RL.budget([])
        self.assertEqual(b["experiments_recorded"], 0)
        self.assertEqual(b["counts"]["hypothesis_count"], 0)


class UnrecordedIsNotZero(unittest.TestCase):
    def test_the_two_known_unrecorded_searches_are_reported(self):
        b = RL.budget([])
        self.assertEqual(len(b["unrecorded"]), 2)
        kinds = {u["bias"] for u in b["unrecorded"]}
        self.assertEqual(kinds, {"data_snooping", "candidate_selection_bias"})

    def test_they_are_not_folded_into_the_counts(self):
        # An unrecorded search added to a total is indistinguishable from a recorded one.
        b = RL.budget([])
        self.assertEqual(b["counts"]["parameter_searches"], 0)
        self.assertIn("NOT added to", b["_note"])

    def test_each_unrecorded_item_names_a_declared_bias_and_says_why_it_is_unrecorded(self):
        for u in RL.budget([])["unrecorded"]:
            self.assertIn(u["bias"], RL.BIASES, u["what"])
            self.assertTrue(u["why_unrecorded"].strip())

    def test_all_four_biases_are_explained_in_the_output(self):
        self.assertEqual(set(RL.budget([])["account_for"]), set(RL.BIASES))


class ExposureIsOneWay(unittest.TestCase):
    def setUp(self):
        self.saved = copy.deepcopy(RL.PERIODS)
        RL.PERIODS["test-oos"] = {"id": "test-oos", "range": ["2026-01-01", "2026-06-30"],
                                  "state": RL.UNTOUCHED, "why": "carved out for this test"}

    def tearDown(self):
        RL.PERIODS.clear(); RL.PERIODS.update(self.saved)

    def test_an_untouched_period_can_validate(self):
        self.assertEqual(RL.assert_untouched("test-oos"), RL.UNTOUCHED)

    def test_exposure_moves_it_and_records_the_trigger(self):
        RL.expose("test-oos", trigger="candidate_selection", experiment_id="e1")
        self.assertEqual(RL.state_of("test-oos"), RL.EXPOSED)
        self.assertEqual(RL.PERIODS["test-oos"]["exposures"][0]["trigger"], "candidate_selection")

    def test_an_exposed_period_can_no_longer_validate(self):
        RL.expose("test-oos", trigger="parameter_selection")
        with self.assertRaises(RL.NotValidationData) as cm:
            RL.assert_untouched("test-oos")
        self.assertIn("§44", str(cm.exception))

    def test_unexposing_always_raises_and_says_what_to_do_instead(self):
        RL.expose("test-oos", trigger="setup_selection")
        with self.assertRaises(RL.ExposureIsOneWay) as cm:
            RL.unexpose("test-oos")
        self.assertIn("Carve out a NEW period", str(cm.exception))

    def test_exposing_twice_is_idempotent_rather_than_an_error(self):
        RL.expose("test-oos", trigger="hypothesis_refinement")
        self.assertEqual(RL.expose("test-oos", trigger="methodology_changes"), RL.EXPOSED)

    def test_an_invented_trigger_is_refused(self):
        with self.assertRaises(RL.NotDeclared):
            RL.expose("test-oos", trigger="had_a_look")

    def test_development_data_cannot_become_exposed_because_it_was_never_validation(self):
        # Not a swallowed error: a caller that expected to be validating here believed something false.
        with self.assertRaises(RL.NotValidationData):
            RL.expose("crypto-history-2023-2026", trigger="candidate_selection")

    def test_a_final_holdout_is_treated_as_validation_capacity(self):
        RL.PERIODS["test-holdout"] = {"id": "test-holdout", "range": ["2026-07-01", "2026-12-31"],
                                      "state": RL.HOLDOUT, "why": "reserved"}
        self.assertEqual(RL.assert_untouched("test-holdout"), RL.HOLDOUT)


class TheHonestCurrentState(unittest.TestCase):
    def test_every_declared_period_is_development_data(self):
        # Pinned so it cannot drift silently: if a period is later carved out, this test is where the claim
        # in the registry's note has to be updated with it.
        for pid in RL.PERIODS:
            self.assertEqual(RL.state_of(pid), RL.DEVELOPMENT, pid)

    def test_no_period_can_currently_validate_anything_and_the_output_says_so(self):
        p = RL.periods()
        self.assertFalse(p["validation_available"])
        self.assertIn("CARVED OUT", p["_note"])

    def test_the_registry_states_that_carving_one_out_is_a_59_decision(self):
        self.assertIn("§59", RL._DATA["oos"]["_no_untouched_period_exists"])

    def test_assert_untouched_refuses_every_period_this_repo_has(self):
        for pid in RL.PERIODS:
            with self.assertRaises(RL.NotValidationData, msg=pid):
                RL.assert_untouched(pid)

    def test_describe_leads_with_the_recorded_count_and_names_the_unrecorded(self):
        out = RL.describe()
        self.assertIn("experiment(s) recorded", out)
        self.assertIn("UNRECORDED", out)
        self.assertIn("NO period can currently validate", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
