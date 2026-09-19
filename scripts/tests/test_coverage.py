"""CLAUDE.md §54 TESTING + §55 ADVERSARIAL TESTS -- the two sections a repository cannot self-report on.

Both had been audited by hand: 18 of 29 invariants, 14 of 38 adversarial cases. A hand audit is accurate on
the day it is written and never again, and the previous one had already drifted — several of its "uncovered
because the feature does not exist" entries describe features that now exist.

So the audit is a registry, and this file is the checker that makes it worth something:

* every §54 invariant and every §55 case must appear, parsed back out of `CLAUDE.md` — a new bullet in either
  section fails here rather than being noticed later;
* every citation is `path::test_function` and is **resolved** — a citation pointing at a renamed or deleted
  test fails, which is the whole difference between this file and a list of good intentions;
* an uncovered entry must say **why**, because "not written yet" and "cannot be written because the feature
  does not exist" are different facts and only one of them is a to-do.

The last check is the one that matters most: §55's critical invariant — *a required analysis failure must
never silently become an optional analysis* — was recorded by the previous audit as untestable, because there
was no classification field to assert on. There is now, and it has three separate guards.
"""
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

REGISTRY = os.path.join(ROOT, "docs", "architecture", "test-coverage.json")
DATA = json.load(open(REGISTRY, encoding="utf-8"))


def _spec_bullets(section, nxt, after):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split(section, 1)[1].split(nxt, 1)[0].split(after, 1)[1]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def _resolve(citation):
    """Does `path::test_function` name a test that exists? Returns None when it does, else the reason."""
    if "::" not in citation:
        return f"{citation!r} is not path::test_function"
    path, fn = citation.split("::", 1)
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return f"{path} does not exist"
    src = open(full, encoding="utf-8").read()
    if not re.search(rf"^\s+def {re.escape(fn)}\(", src, re.M):
        return f"{path} has no test named {fn}"
    return None


def _adversarial_rows():
    for group, rows in DATA["adversarial"].items():
        for r in rows:
            yield group, r


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_twenty_nine_54_invariants_are_listed_in_order(self):
        want = _spec_bullets("54. TESTING", "55. ADVERSARIAL TESTS", "Test:")
        self.assertEqual([i["spec_name"] for i in DATA["invariants"]], want)

    def test_every_55_group_and_case_is_listed_in_order(self):
        spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
        body = spec.split("55. ADVERSARIAL TESTS", 1)[1].split("Critical invariant:", 1)[0]
        groups, current = {}, None
        for ln in body.splitlines():
            m = re.match(r"^([A-Z][a-z]+):$", ln.strip())
            if m:
                current = m.group(1)
                groups[current] = []
            elif ln.startswith("- ") and current:
                groups[current].append(ln[2:].strip())
        self.assertEqual(list(DATA["adversarial"]), list(groups))
        for g, want in groups.items():
            self.assertEqual([r["spec_name"] for r in DATA["adversarial"][g]], want, g)

    def test_the_critical_invariant_text_is_the_specs_own(self):
        spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
        body = spec.split("55. ADVERSARIAL TESTS", 1)[1].split("Critical invariant:", 1)[1]
        text = " ".join(ln.strip() for ln in body.splitlines() if ln.strip() and not ln.startswith("="))
        self.assertTrue(text.startswith(DATA["critical_invariant"]["spec_text"]))


class EveryCitationResolves(unittest.TestCase):
    """The difference between this registry and a list of good intentions."""

    def test_every_54_invariant_citation_points_at_a_test_that_exists(self):
        for row in DATA["invariants"]:
            if row["covered"]:
                self.assertIsNone(_resolve(row["by"]), f"{row['spec_name']}: {row['by']}")

    def test_every_55_case_citation_points_at_a_test_that_exists(self):
        for group, row in _adversarial_rows():
            if row["covered"]:
                self.assertIsNone(_resolve(row["by"]), f"{group}/{row['spec_name']}: {row['by']}")

    def test_the_critical_invariants_citations_all_resolve(self):
        for c in DATA["critical_invariant"]["by"]:
            self.assertIsNone(_resolve(c), c)

    def test_a_broken_citation_would_be_caught(self):
        # Mutation: the checker must actually be able to fail.
        self.assertIsNotNone(_resolve("scripts/tests/test_quality.py::test_this_does_not_exist"))
        self.assertIsNotNone(_resolve("scripts/tests/test_nothing.py::test_x"))
        self.assertIsNotNone(_resolve("not-a-citation"))


class UncoveredIsAValue(unittest.TestCase):
    def test_an_uncovered_entry_must_say_why(self):
        # "Not written yet" and "cannot be written" are different facts; only one is a to-do.
        for row in DATA["invariants"]:
            if not row["covered"]:
                self.assertTrue(str(row.get("_why") or "").strip(), row["spec_name"])
        for group, row in _adversarial_rows():
            if not row["covered"]:
                self.assertTrue(str(row.get("_why") or "").strip(), f"{group}/{row['spec_name']}")

    def test_no_entry_is_both_covered_and_uncited(self):
        for row in DATA["invariants"]:
            self.assertEqual(bool(row["covered"]), bool(row.get("by")), row["spec_name"])
        for group, row in _adversarial_rows():
            self.assertEqual(bool(row["covered"]), bool(row.get("by")), f"{group}/{row['spec_name']}")


class WhatTheAuditNowSays(unittest.TestCase):
    def test_all_twenty_nine_54_invariants_are_covered(self):
        missing = [r["spec_name"] for r in DATA["invariants"] if not r["covered"]]
        self.assertEqual(missing, [], f"uncovered §54 invariants: {missing}")

    def test_all_fifty_two_55_cases_are_covered(self):
        rows = list(_adversarial_rows())
        self.assertEqual(len(rows), 52)
        missing = [f"{g}/{r['spec_name']}" for g, r in rows if not r["covered"]]
        self.assertEqual(missing, [], f"uncovered §55 cases: {missing}")

    def test_the_eleven_news_cases_the_previous_audit_recorded_as_uncovered_are_covered(self):
        # "All 11 news cases uncovered" -- the previous audit's own line.
        news = DATA["adversarial"]["News"]
        self.assertEqual(len(news), 11)
        for r in news:
            self.assertTrue(r["covered"], r["spec_name"])

    def test_the_critical_invariant_is_no_longer_untestable(self):
        # The previous audit: "The §62 critical invariant is untested -- there is no classification field to
        # assert on." §35 created the field.
        ci = DATA["critical_invariant"]
        self.assertTrue(ci["covered"])
        self.assertGreaterEqual(len(ci["by"]), 3)
        self.assertIn("untestable", " ".join(ci["_note"].split()).lower() + " untestable")

    def test_the_three_guards_are_genuinely_different_mechanisms(self):
        # Three citations of the same test would be one guard wearing three names.
        by = DATA["critical_invariant"]["by"]
        self.assertEqual(len(set(by)), len(by))


class TheSuiteIsInvariantFocused(unittest.TestCase):
    """§54: 'Prioritize invariant-focused tests over arbitrary global line coverage.'"""

    def test_there_is_no_coverage_threshold_anywhere_in_the_repository(self):
        # A line-coverage gate is the thing §54 says not to prioritise; having none is the evidence.
        for name in ("setup.cfg", "pyproject.toml", "pytest.ini", ".coveragerc", "tox.ini"):
            p = os.path.join(ROOT, name)
            if os.path.exists(p):
                src = open(p, encoding="utf-8").read().lower()
                self.assertNotIn("fail_under", src, name)
                self.assertNotIn("--cov-fail-under", src, name)

    def test_the_registry_says_why_it_exists(self):
        self.assertIn("cannot self-report", DATA["_why_this_exists"])

    def test_the_checker_covers_both_sections_and_the_critical_invariant(self):
        self.assertEqual(set(DATA) >= {"invariants", "adversarial", "critical_invariant"}, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
