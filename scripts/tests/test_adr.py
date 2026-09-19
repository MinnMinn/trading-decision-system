"""CLAUDE.md §53 -- the Architecture Decision Log, and the sentence most decision logs drop.

§53 asks for eight fields per decision. Every ADR format asks for roughly those, and most repositories that
adopt one end up with records whose `alternatives` field says "none considered" — which is the field that
turns a log into a decision record rather than an announcement.

The sentence that is usually dropped is the last one:

    "When an alternative has been rejected, do not repeatedly reopen it unless new evidence appears."

That is not satisfiable by a document. It needs an INDEX of every rejected alternative and something that can
be asked "has this been rejected before?" — otherwise the answer is available only by reading every decision,
which is the same as not being available. So the tests below weigh `rejected_alternatives()` and
`check_reopening()` most heavily, and require reopening to carry its evidence rather than a flag.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import adr

DIR = os.path.join(ROOT, "docs", "adr")


def _adr(**over):
    fm = {"title": "T", "date": "2026-09-18", "status": "ACCEPTED",
          "context": "c", "problem": "p", "decision": "d", "chosen_approach": "ca",
          "reason": "r", "consequences": "cons"}
    lists = {"alternatives": ["alt one", "alt two"], "rejected_alternatives": ["a rejected thing"]}
    fm.update({k: v for k, v in over.items() if k not in lists})
    lists.update({k: v for k, v in over.items() if k in lists})
    lines = ["---"]
    for k, v in fm.items():
        lines.append(f"{k}: {v}")
    for k, v in lists.items():
        lines.append(f"{k}:")
        for item in v:
            lines.append(f"  - {item}")
    lines += ["---", "", "body"]
    return "\n".join(lines) + "\n"


class TheFieldsAreTheSpecs(unittest.TestCase):
    def test_all_eight_fields_claude_md_53_names_are_required(self):
        spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
        body = spec.split("53. ADR", 1)[1].split("When an alternative has been rejected", 1)[0]
        want = [ln[2:].strip().replace(" ", "_") for ln in body.splitlines() if ln.startswith("- ")]
        self.assertEqual(list(adr.FIELDS), want)

    def test_every_field_is_individually_load_bearing(self):
        d = tempfile.mkdtemp()
        try:
            for f in adr.FIELDS:
                p = os.path.join(d, "0001-x.md")
                over = {f: ([] if f in adr.LIST_FIELDS else "")}
                open(p, "w", encoding="utf-8").write(_adr(**over))
                with self.assertRaises(adr.MalformedADR, msg=f):
                    adr.read(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_decision_with_no_alternatives_considered_is_refused(self):
        # A decision with no alternatives was not a decision, it was a default.
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "0001-x.md")
            open(p, "w", encoding="utf-8").write(_adr(alternatives=[]))
            with self.assertRaises(adr.MalformedADR) as cm:
                adr.read(p)
            self.assertIn("was not a decision", str(cm.exception))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_the_error_says_why_rejected_alternatives_matters(self):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "0001-x.md")
            open(p, "w", encoding="utf-8").write(_adr(rejected_alternatives=[]))
            with self.assertRaises(adr.MalformedADR) as cm:
                adr.read(p)
            self.assertIn("re-proposed and re-rejected", str(cm.exception))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_a_bad_status_or_date_is_refused(self):
        d = tempfile.mkdtemp()
        try:
            for over in ({"status": "MAYBE"}, {"date": "September 2026"}):
                p = os.path.join(d, "0001-x.md")
                open(p, "w", encoding="utf-8").write(_adr(**over))
                with self.assertRaises(adr.MalformedADR, msg=str(over)):
                    adr.read(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TheRealLog(unittest.TestCase):
    def test_every_adr_in_the_repository_is_complete(self):
        recs = adr.all_records()
        self.assertGreaterEqual(len(recs), 11)
        for r in recs:
            for f in adr.FIELDS:
                self.assertTrue(r[f], f"{r['id']}.{f}")

    def test_the_log_is_chronological_newest_first(self):
        recs = adr.all_records()
        keys = [(r["date"], r["id"]) for r in recs]
        self.assertEqual(keys, sorted(keys, reverse=True))

    def test_ids_are_unique(self):
        ids = [r["id"] for r in adr.all_records()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_adr_points_at_the_design_rather_than_restating_it(self):
        # rules/single-source-of-truth: a restatement is a second copy that goes stale.
        pointed = [r for r in adr.all_records() if "SYSTEM-DESIGN.md" in r["chosen_approach"]]
        self.assertGreaterEqual(len(pointed), 8)

    def test_the_generated_index_lists_every_decision_and_every_rejection(self):
        idx = adr.index()
        for r in adr.all_records():
            self.assertIn(r["title"], idx, r["id"])
        for r in adr.rejected_alternatives():
            self.assertIn(r["alternative"][:40], idx)

    def test_the_committed_index_is_the_generated_one(self):
        # Generated, never hand-maintained -- a hand-edited index is a second source.
        p = os.path.join(DIR, "README.md")
        if not os.path.exists(p):
            self.skipTest("index not built")
        self.assertEqual(open(p, encoding="utf-8").read(), adr.index())


class TheSentenceMostLogsDrop(unittest.TestCase):
    """§53: 'When an alternative has been rejected, do not repeatedly reopen it unless new evidence appears.'"""

    def test_every_rejected_alternative_is_indexed_with_the_adr_that_rejected_it(self):
        rej = adr.rejected_alternatives()
        self.assertGreaterEqual(len(rej), 20)
        for r in rej:
            self.assertTrue(r["alternative"].strip())
            self.assertTrue(r["adr"].strip())
            self.assertTrue(r["date"].strip())

    def test_reproposing_a_rejected_alternative_raises_and_names_the_adr(self):
        with self.assertRaises(adr.AlreadyRejected) as cm:
            adr.check_reopening("let's use a weighted composite score with documented weights")
        msg = str(cm.exception)
        self.assertIn("already rejected by ADR", msg)
        self.assertIn("§53", msg)

    def test_the_refusal_names_what_would_allow_the_reopening(self):
        with self.assertRaises(adr.AlreadyRejected) as cm:
            adr.check_reopening("store constants in the module that needs them")
        self.assertIn("new_evidence", str(cm.exception))

    def test_reopening_is_permitted_with_evidence_and_the_evidence_is_recorded(self):
        # §53 permits reopening -- it forbids reopening REPEATEDLY without new evidence. The mechanism takes
        # the evidence itself rather than a boolean, because a flag lets anyone re-litigate by passing True.
        out = adr.check_reopening("weighted composite score with documented weights",
                                  new_evidence="a 2027 study measuring reviewer behaviour on weighted scores")
        self.assertTrue(out["reopening_permitted"])
        self.assertIn("2027", out["new_evidence"])
        self.assertTrue(out["already_rejected"])

    def test_an_unrelated_proposal_passes(self):
        out = adr.check_reopening("add a Kalman filter to the volatility estimate")
        self.assertEqual(out["already_rejected"], [])

    def test_the_check_is_not_satisfied_by_a_boolean(self):
        import inspect
        sig = inspect.signature(adr.check_reopening)
        self.assertIn("new_evidence", sig.parameters)
        self.assertIsNone(sig.parameters["new_evidence"].default)

    def test_the_index_carries_the_rule_it_serves(self):
        self.assertIn("do not repeatedly reopen", adr.index())


class TheLogCoversWhatWasActuallyDecided(unittest.TestCase):
    """An ADR log seeded with nothing is a format, not a record."""

    def test_the_load_bearing_decisions_of_this_work_are_in_the_log(self):
        titles = " ".join(r["title"].lower() for r in adr.all_records())
        for topic in ("registry", "inherited", "ordering", "point-in-time", "universal score",
                      "three-valued", "immutable", "one-way", "did not run", "not-applicable"):
            self.assertIn(topic, titles, topic)

    def test_describe_reports_the_size_of_the_log(self):
        out = adr.describe()
        self.assertIn("decision(s)", out)
        self.assertIn("rejected alternative(s)", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
