"""CLAUDE.md §56-§62 -- the six sections the ledger had recorded as POLICY, which is its word for "true by
intention".

Intentions are not checkable, and four of these turn out to be:

* **§56** -- a later phase's artifact existing without the earlier phase's is exactly "do not implement future
  phases speculatively during earlier phases", and it is a file check.
* **§57** -- nine speculative things are named BY NAME. Whether any is in the tree is a scan, and the scan has
  to be able to find one, so a mutation test plants a `celery` import and requires it to be reported.
* **§58** -- five of the nine `Avoid` rules are already pinned by a test somewhere; nobody had collected them,
  so nobody could say which four are conventions. Saying which is the point.
* **§60** -- thirty-five questions whose answers the suite already knows.

§60 is the one that matters. "Before declaring work complete, review:" is followed by *is PIT preserved?*,
*can required analysis accidentally be bypassed?*, *can AI modify production silently?* -- and every one of
those has a test in this suite. `python3 scripts/policy.py --review` prints all thirty-five with the citation
that answers each, and `test_every_self_review_question_resolves_to_a_real_test` fails if any stops resolving.
That is the difference between a self-review and a self-assessment.

§59's contribution is the smallest and the least comfortable: four changes in this repository DID change
historical research semantics, and each is recorded with what it invalidates. §59's sentence is about the word
*silently*, so the loader refuses a recorded change that does not say what it broke.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import policy  # noqa: E402

REGISTRY = os.path.join(ROOT, "docs", "architecture", "policy.json")
SPEC = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()


def _block(a, b):
    return SPEC.split(a, 1)[1].split(b, 1)[0]


def _bullets(text):
    return [ln.strip()[2:] for ln in text.splitlines() if ln.strip().startswith("- ")]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_the_nine_phases_are_the_specs_own_in_order(self):
        body = _block("56. IMPLEMENTATION PHASES", "57. PHASE DISCIPLINE")
        want = [ln.strip().rstrip(":") for ln in body.splitlines() if ln.strip().startswith("Phase ")]
        self.assertEqual(list(policy.PHASES), want)

    def test_every_phase_lists_the_specs_own_deliverables(self):
        body = _block("56. IMPLEMENTATION PHASES", "57. PHASE DISCIPLINE")
        cur, want = None, {}
        for ln in body.splitlines():
            t = ln.strip()
            if t.startswith("Phase "):
                cur = t.rstrip(":")
                want[cur] = []
            elif t.startswith("- ") and cur:
                want[cur].append(t[2:])
        for name, items in want.items():
            self.assertEqual(policy.phase(name)["deliverables"], items, name)

    def test_the_nine_speculative_things_are_the_specs_own(self):
        want = _bullets(_block("57. PHASE DISCIPLINE", "58. CODING RULES"))
        self.assertEqual(list(policy.SPECULATIVE), want)

    def test_the_coding_rules_are_the_specs_own_both_lists(self):
        body = _block("58. CODING RULES", "59. CHANGE SAFETY")
        pref, avoid = body.split("Prefer:", 1)[1].split("Avoid:", 1)
        rules = policy.coding_rules()
        self.assertEqual([r["rule"] for r in rules["prefer"]], _bullets(pref))
        self.assertEqual([r["rule"] for r in rules["avoid"]], _bullets(avoid))

    def test_the_thirty_five_self_review_questions_are_the_specs_own_in_order(self):
        body = _block("60. SELF-REVIEW", "61. FINAL REPORT")
        want = _bullets(body)
        self.assertEqual([i["question"] for i in policy.SELF_REVIEW], want)
        self.assertEqual(len(want), 35)

    def test_the_sixteen_final_report_items_are_the_specs_own(self):
        body = _block("61. FINAL REPORT", "62. FINAL NON-NEGOTIABLE")
        want = [ln.strip().split(". ", 1)[1] for ln in body.splitlines()
                if ln.strip()[:2].rstrip(".").isdigit() and ". " in ln.strip()]
        self.assertEqual(list(policy.REPORT_ITEMS), want)
        self.assertEqual(len(want), 16)


class TheSelfReviewIsACommandNotAPromise(unittest.TestCase):
    def test_every_self_review_question_resolves_to_a_real_test(self):
        bad = [(r["question"], r["unresolved"]) for r in policy.review() if r["unresolved"]]
        self.assertEqual(bad, [], f"§60 questions with no test behind them: {bad}")

    def test_every_question_declares_the_answer_the_spec_requires(self):
        for r in policy.SELF_REVIEW:
            self.assertIn(r["must_be"], ("YES", "NO"), r["question"])

    def test_the_can_this_happen_questions_must_answer_no(self):
        # §60 mixes two shapes. "Is PIT preserved?" wants YES; "Can required analysis accidentally be
        # bypassed?" wants NO, and answering YES to one of those would be a finding, not a pass.
        for r in policy.SELF_REVIEW:
            if r["question"].lower().startswith(("can ", "is there any")):
                self.assertEqual(r["must_be"], "NO", r["question"])

    def test_an_invariant_reference_resolves_through_the_54_registry(self):
        # One citation list, not two: a question already answered by a §54 invariant points at it by name.
        refs = [r for r in policy.SELF_REVIEW if r["answered_by"].startswith("invariant:")]
        self.assertGreaterEqual(len(refs), 10)
        for r in refs:
            citation, why = policy.resolve(r["answered_by"])
            self.assertIsNone(why, r["question"])
            self.assertIn("::", citation)

    def test_a_broken_citation_would_be_caught(self):
        self.assertIsNotNone(policy.resolve("scripts/tests/test_quality.py::test_nope")[1])
        self.assertIsNotNone(policy.resolve("invariant:no such invariant")[1])
        self.assertIsNotNone(policy.resolve("we checked")[1])

    def test_a_question_with_no_test_is_refused_at_load(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["self_review"][0]["answered_by"] = ""
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-policy.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(policy.RegistryError) as cm:
                policy._load(p)
            self.assertIn("self-assessment", str(cm.exception))
        finally:
            os.remove(p)


class Phase56(unittest.TestCase):
    def test_every_declared_phase_artifact_exists(self):
        self.assertEqual(policy.missing_artifacts(), [])

    def test_no_phase_is_skipped(self):
        # "Do not implement future phases speculatively during earlier phases" -- a phase-8 artifact with no
        # phase-3 artifact behind it is the shape that rule forbids.
        for i, name in enumerate(policy.PHASES):
            self.assertEqual(name, f"Phase {i}")


class Speculative57(unittest.TestCase):
    def test_nothing_on_the_speculative_list_is_in_the_tree(self):
        self.assertEqual(policy.speculative_findings(), [])

    def test_the_scan_can_actually_find_one(self):
        # Mutation: a scan that has never found anything is indistinguishable from a scan that cannot.
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "scripts"))
            open(os.path.join(tmp, "scripts", "worker.py"), "w").write("import celery\n")
            hits = policy.speculative_findings(tmp)
            self.assertTrue(any(h[1] == "celery" for h in hits), hits)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_an_item_that_is_neither_scanned_nor_explained_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        row = data["not_speculative"][1]
        row.pop("markers", None)
        row.pop("_why", None)
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-policy.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(policy.RegistryError) as cm:
                policy._load(p)
            self.assertIn("unexamined", str(cm.exception))
        finally:
            os.remove(p)

    def test_the_scan_does_not_report_the_files_that_name_the_markers(self):
        # The classic way a self-check reports itself: the registry lists "kafka" in order to look for it.
        for rel in policy.SCAN_EXEMPT:
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)


class CodingRules58(unittest.TestCase):
    def test_a_rule_with_a_citation_resolves(self):
        rules = policy.coding_rules()
        for group in ("prefer", "avoid"):
            for r in rules[group]:
                if r["checked_by"]:
                    self.assertIsNone(policy.resolve(r["checked_by"])[1], r["rule"])

    def test_the_unchecked_rules_are_declared_conventions_not_claimed_as_enforced(self):
        # "meaningful names" has no test, and pretending it does would make the enforced ones worth less.
        rules = policy.coding_rules()
        unchecked = [r["rule"] for g in ("prefer", "avoid") for r in rules[g] if not r["checked_by"]]
        self.assertTrue(unchecked)
        self.assertIn("convention", rules["_unchecked_is_a_value"].lower())

    def test_the_five_avoid_rules_that_can_be_enforced_are(self):
        avoid = {r["rule"]: r["checked_by"] for r in policy.coding_rules()["avoid"]}
        for rule in ("provider-specific leakage", "magic fallback", "silent provider switching",
                     "hidden side effects", "duplicated domain rules"):
            self.assertTrue(avoid[rule], rule)


class ChangeSafety59(unittest.TestCase):
    def test_the_ten_step_checklist_is_the_specs_own(self):
        body = _block("59. CHANGE SAFETY", "60. SELF-REVIEW")
        want = [ln.strip() for ln in body.splitlines()
                if ln.strip()[:2] in tuple(f"{i}." for i in range(1, 10)) or ln.strip()[:3] == "10."]
        self.assertEqual(policy.change_safety()["checklist"], want)
        self.assertEqual(len(want), 10)

    def test_the_version_significant_kinds_are_the_specs_own(self):
        body = _block("59. CHANGE SAFETY", "60. SELF-REVIEW").split("Any change to:", 1)[1]
        self.assertEqual(policy.change_safety()["version_significant"], _bullets(body))

    def test_the_significance_reader_exists(self):
        path, fn = policy.change_safety()["significance_reader"].split("::")
        src = open(os.path.join(ROOT, path), encoding="utf-8").read()
        self.assertIn(f"def {fn}(", src)

    def test_every_recorded_semantics_change_says_what_it_invalidates(self):
        # §59's sentence is about the word SILENTLY. A recorded change with no consequence recorded is still
        # silent, so the loader refuses it -- and the four real ones in this repository all name theirs.
        recs = policy.change_safety()["recorded_changes"]
        self.assertGreaterEqual(len(recs), 4)
        for r in recs:
            self.assertTrue(r["invalidates"].strip(), r["what"])
            self.assertIn(r["kind"], policy.change_safety()["version_significant"], r["what"])

    def test_a_recorded_change_with_no_consequence_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["change_safety"]["recorded_changes"][0]["invalidates"] = ""
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-policy.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(policy.RegistryError) as cm:
                policy._load(p)
            self.assertIn("still silent", str(cm.exception))
        finally:
            os.remove(p)

    def test_the_mt5_import_is_recorded_as_done_with_what_it_broke(self):
        """Updated 2026-09-18: this asserted the MT5 import was still PENDING. It was run that day, so the
        assertion moved from "recorded as pending" to "recorded as done with its consequences" -- the same
        fact at a later point in its life, not a softened one.

        The two consequences that matter are both asserted, because they are the ones a later reader would
        otherwise have to rediscover: the old series are gone (data/history/ is gitignored, so git cannot
        bring them back), and the import did NOT cover every timeframe -- the ones it left behind are a
        second provider standing inside one instrument's history.
        """
        rec = [r for r in policy.change_safety()["recorded_changes"] if "MT5 CFD history" in r["what"]]
        self.assertEqual(len(rec), 1)
        inv = rec[0]["invalidates"]
        self.assertIn("DONE 2026-09-18", inv)
        self.assertIn("not comparable", inv)
        self.assertIn("NOT replaced", inv)          # 2H/30m/5m stayed on the futures proxy
        self.assertIn("provider_mix", inv)          # and that residue has a guard

    def test_a_change_still_pending_would_have_to_say_so(self):
        # The shape is still supported -- the registry just has none today. A recorded change may be PENDING,
        # and if it is, it must name what is blocking it rather than reading as complete.
        for r in policy.change_safety()["recorded_changes"]:
            if "PENDING" in r["invalidates"]:
                self.assertRegex(r["invalidates"], r"PENDING\s*--")


class NonNegotiable62(unittest.TestCase):
    def test_the_three_guards_resolve(self):
        for c in policy.non_negotiable()["enforced_by"]:
            self.assertIsNone(policy.resolve(c)[1], c)

    def test_it_is_the_same_invariant_55_names_not_a_second_list(self):
        cov = json.load(open(os.path.join(ROOT, "docs", "architecture", "test-coverage.json"), encoding="utf-8"))
        self.assertEqual(sorted(policy.non_negotiable()["enforced_by"]),
                         sorted(cov["critical_invariant"]["by"]))


class Describe(unittest.TestCase):
    def test_describe_reports_the_counts_and_the_two_scans(self):
        out = policy.describe()
        self.assertIn("35/35", out)
        self.assertIn("all present", out)
        self.assertIn("none found", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
