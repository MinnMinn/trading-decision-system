"""CLAUDE.md §46 REPRODUCIBILITY + §47 SYSTEM VERSIONING -- one question asked of a result and of the system
that produced it.

**§46's teeth are in its last sentence**, and it is a sentence about comparison, not about records:

    "A result without reproducibility metadata must not be treated as equivalent to a fully reproducible
     experiment."

The harm never happens in the record. It happens when a partial result and a complete one appear as two rows
of the same table, where a reader treats them as equivalent whatever the footnote says. So the tests below
weigh `compare()` and `assert_comparable()` more heavily than the grading arithmetic, and they check the
three ways a capture list gets ticked off without capturing anything: a `None`, an empty container, and an
`unavailable()` marker.

**§47's teeth are in "rejected candidates must remain traceable".** A version counter hands v1.3 to a new
candidate the moment the old v1.3 is rejected and forgotten. `next_candidate()` reads the experiment store
instead, so a number that has been worn stays worn — and the test for that files a rejected candidate and
requires the next number to skip it.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import versioning as VER
import experiment as X

REGISTRY = os.path.join(ROOT, "docs", "architecture", "versioning.json")


def _bullets(section, nxt, after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split(section, 1)[1].split(nxt, 1)[0].split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def _complete(**over):
    """An artifact carrying all nine §46 items."""
    d = {"code_version": {"commit": "abc", "dirty": False}, "trading_system_version": "v1",
         "dataset_snapshot": {"snapshot_id": "ds1"}, "configuration_snapshot": {"fields": {}},
         "provider_state": {"providers": {"binance_public": {}}}, "random_seed": 1,
         "parameters": {"min_rr": 3.0}, "test_periods": {"in_sample": "2024"},
         "validation_state": {"verdict": "NOT_RUN"}}
    d.update(over)
    return d


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_nine_reproducibility_items_are_declared(self):
        self.assertEqual([VER.spec_name(i) for i in VER.ITEM_ORDER],
                         _bullets("46. REPRODUCIBILITY", "47. SYSTEM VERSIONING", "Capture:",
                                  "A result without"))

    def test_all_thirteen_version_significant_change_kinds_are_declared(self):
        self.assertEqual([VER.spec_name(k) for k in VER.KIND_ORDER],
                         _bullets("47. SYSTEM VERSIONING", "48. SYSTEM RANKING", "Examples:",
                                  "Failure Learning must use"))

    def test_every_item_says_what_captures_it(self):
        # An item with no capturer is an item nobody will notice is missing.
        for iid in VER.ITEM_ORDER:
            self.assertTrue(VER.ITEMS[iid]["captured_by"].strip(), iid)

    def test_a_registry_without_a_version_grammar_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["versioning"]["grammar"].pop("candidate")
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-versioning.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(VER.RegistryError):
                VER._load(p)
        finally:
            os.remove(p)

    def test_the_registry_explains_why_the_two_sections_share_a_file(self):
        self.assertIn("version cannot mean two things", VER._DATA["_why_one_file"])


class GradingAResult(unittest.TestCase):
    def test_a_complete_artifact_is_reproducible(self):
        self.assertEqual(VER.grade(_complete())["grade"], VER.REPRODUCIBLE)

    def test_a_bare_artifact_is_not_reproducible(self):
        g = VER.grade({"expectancy": 0.3})
        self.assertEqual(g["grade"], VER.NOT_REPRODUCIBLE)
        self.assertEqual(len(g["missing"]), len(VER.ITEM_ORDER))

    def test_a_partly_captured_artifact_is_partial_and_names_what_is_missing(self):
        d = _complete(); del d["provider_state"]; del d["random_seed"]
        g = VER.grade(d)
        self.assertEqual(g["grade"], VER.PARTIAL)
        self.assertEqual(set(g["missing"]), {"provider_state", "random_seed"})
        self.assertIn("provider state", g["missing_names"])

    def test_the_three_ways_a_capture_is_ticked_off_without_capturing_anything(self):
        # None, an empty container, and an unavailable() marker.
        for bad in (None, {}, {"unavailable": "could not read"}, {"snapshot_error": "boom"}):
            d = _complete(dataset_snapshot=bad)
            self.assertIn("dataset_snapshot", VER.grade(d)["missing"], repr(bad))

    def test_a_null_seed_is_a_gap_not_an_exemption(self):
        # It was defensible while nothing stochastic ran; §39's bootstrap and §45's Monte Carlo ended that.
        self.assertIn("random_seed", VER.grade(_complete(random_seed=None))["missing"])

    def test_missing_items_are_named_not_counted(self):
        # "7 of 9 captured" tells a reader nothing about whether they can re-run it.
        g = VER.grade(_complete(code_version=None))
        self.assertEqual(g["missing_names"], ["code version"])


class TheRuleIsAboutComparison(unittest.TestCase):
    def test_comparing_a_reproducible_result_with_a_partial_one_raises(self):
        weak = _complete(); del weak["provider_state"]
        with self.assertRaises(VER.NotEquivalent) as cm:
            VER.assert_comparable(_complete(), weak)
        self.assertIn("§46", str(cm.exception))
        self.assertIn("provider state", str(cm.exception))

    def test_two_results_of_the_same_grade_are_comparable(self):
        self.assertEqual(VER.assert_comparable(_complete(), _complete()), VER.REPRODUCIBLE)

    def test_two_equally_partial_results_are_comparable_with_each_other(self):
        a = _complete(); del a["provider_state"]
        b = _complete(); del b["random_seed"]
        self.assertEqual(VER.assert_comparable(a, b), VER.PARTIAL)

    def test_compare_carries_both_grades_inside_the_result(self):
        # Inside, not beside: a caller that wants to render only the numbers has to delete them on purpose.
        weak = _complete(); del weak["provider_state"]
        c = VER.compare(_complete(expectancy=0.4), dict(weak, expectancy=0.9), metric="expectancy")
        self.assertIn("a_reproducibility", c)
        self.assertIn("b_reproducibility", c)
        self.assertFalse(c["comparable"])
        self.assertIn("NOT EQUIVALENT", c["_warning"])

    def test_a_comparable_pair_carries_no_warning(self):
        c = VER.compare(_complete(expectancy=0.4), _complete(expectancy=0.9), metric="expectancy")
        self.assertTrue(c["comparable"])
        self.assertIsNone(c["_warning"])

    def test_the_warning_names_what_the_weaker_result_is_missing(self):
        weak = _complete(); del weak["test_periods"]
        c = VER.compare(_complete(), weak, metric="expectancy")
        self.assertIn("test periods", c["_warning"])


class ProviderStateIsCapturedByNothingElse(unittest.TestCase):
    def test_it_reads_the_real_provider_registry(self):
        ps = VER.provider_state()
        self.assertIn("providers", ps)
        self.assertGreaterEqual(len(ps["providers"]), 4)

    def test_each_provider_carries_its_role_status_and_capabilities(self):
        for pid, rec in VER.provider_state()["providers"].items():
            for k in ("roles", "status", "capabilities"):
                self.assertIn(k, rec, f"{pid}.{k}")

    def test_a_capture_failure_is_recorded_rather_than_omitted(self):
        # An omitted item grades as missing, which is right -- but the reason must survive.
        self.assertTrue(VER.is_significant("provider_dependency"))


class TheVersionGrammar(unittest.TestCase):
    def test_released_versions(self):
        for v in ("v1", "v2", "v17"):
            self.assertTrue(VER.is_released(v), v)
            self.assertEqual(VER.parse(v), (v, None))

    def test_candidate_versions_carry_their_parent_in_their_name(self):
        self.assertEqual(VER.parse("v1.3"), ("v1", 3))
        self.assertEqual(VER.parent_of("v2.11"), "v2")

    def test_there_is_no_third_form(self):
        # §47 forbids a separate incompatible version system, and a grammar that accepts
        # "v2-experimental" is how one starts.
        for bad in ("v0", "1", "v1.0", "v1.2.3", "v2-experimental", "candidate-7", "", None):
            with self.assertRaises(VER.BadVersion, msg=repr(bad)):
                VER.parse(bad)

    def test_an_approved_candidate_becomes_the_next_released_version(self):
        # §47's own example: v1 -> candidate v1.x -> approved v2.
        self.assertEqual(VER.approved_successor("v1.4"), "v2")
        self.assertEqual(VER.approved_successor("v9.1"), "v10")

    def test_a_released_version_has_no_successor_of_that_kind(self):
        with self.assertRaises(VER.BadVersion):
            VER.approved_successor("v1")


class EveryListedChangeIsSignificant(unittest.TestCase):
    def test_all_thirteen_are_significant(self):
        for kid in VER.KIND_ORDER:
            self.assertTrue(VER.is_significant(kid), kid)

    def test_there_is_no_way_to_declare_a_listed_kind_insignificant(self):
        # The direction in which a version silently stops tracking the system.
        import inspect
        sig = inspect.signature(VER.is_significant)
        self.assertNotIn("insignificant", sig.parameters)
        self.assertNotIn("force", sig.parameters)

    def test_an_unlisted_kind_raises_unless_the_caller_declares_it_significant(self):
        # §47's list is examples -- a floor, not a ceiling.
        with self.assertRaises(VER.NotDeclared):
            VER.is_significant("logging change")
        self.assertTrue(VER.is_significant("logging change", also_significant=True))

    def test_no_kind_at_all_is_not_significant(self):
        self.assertFalse(VER.is_significant(None))


class RejectedCandidatesStayTraceable(unittest.TestCase):
    """§47: 'Rejected candidates must remain traceable.'"""

    def _rec(self, candidate, decision="PENDING"):
        r = X.Record(hypothesis=f"h-{candidate}", motivation="m",
                     parent_trading_system_version="v1", candidate_version=candidate,
                     experiment_id=f"e-{candidate}")
        for k in X.ORDER:
            if k not in r._v:
                r.set(k, X.unavailable("test record"))
        r._v["decision"] = {"decision": decision, "by": "human"}
        return r.seal()

    def test_the_next_candidate_number_comes_from_the_store_not_a_counter(self):
        recs = [self._rec("v1.1"), self._rec("v1.2")]
        self.assertEqual(VER.next_candidate("v1", records=recs), "v1.3")

    def test_a_rejected_candidates_number_stays_spent(self):
        # A counter would hand v1.2 to a new candidate the moment the old one was rejected and forgotten.
        recs = [self._rec("v1.1"), self._rec("v1.2", decision="REJECTED")]
        self.assertEqual(VER.next_candidate("v1", records=recs), "v1.3")

    def test_gaps_are_filled_only_where_nothing_ever_wore_the_number(self):
        recs = [self._rec("v1.2")]
        self.assertEqual(VER.next_candidate("v1", records=recs), "v1.1")

    def test_candidates_of_another_parent_do_not_consume_numbers(self):
        recs = [self._rec("v2.1"), self._rec("v2.2")]
        self.assertEqual(VER.next_candidate("v1", records=recs), "v1.1")

    def test_a_candidate_cannot_have_a_candidate_as_its_parent(self):
        with self.assertRaises(VER.BadVersion):
            VER.next_candidate("v1.2", records=[])

    def test_an_empty_store_starts_at_one(self):
        self.assertEqual(VER.next_candidate("v1", records=[]), "v1.1")


class AgainstTheRealRepository(unittest.TestCase):
    def test_the_live_trading_system_versions_parse_under_47s_grammar(self):
        # §47 forbids a separate incompatible version system; the registry must already obey it.
        import trading_system as TS
        for sid in TS.SYSTEMS:
            v = TS.get(sid)["version"]
            self.assertTrue(VER.is_released(v) or VER.is_candidate(v), f"{sid}: {v!r}")

    def test_a_real_42_record_grades_against_46s_list(self):
        rec = X.Record(hypothesis="h", motivation="m", parent_trading_system_version="v1",
                       candidate_version="v1.1")
        for k in X.ORDER:
            if k not in rec._v:
                rec.set(k, X.unavailable("smoke record"))
        g = VER.grade(dict(rec.seal()))
        # An all-unavailable record must NOT grade as reproducible: unavailable is not captured.
        self.assertNotEqual(g["grade"], VER.REPRODUCIBLE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
