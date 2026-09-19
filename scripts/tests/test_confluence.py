"""CLAUDE.md §18 -- Confluence Score counts only what the active system trades.

§18 has two halves and they were in different states.

The NAMING half was already right: the repo says Confluence Score everywhere, never "Confidence %", and the
one `confidence` field is a pre-trade human 1-5 recorded before the outcome is known. Those tests are here so
a future edit cannot quietly reintroduce a fake probability.

The COUNTING half was broken, and §15 is what broke it. `eligible` was defined -- identically in
`confluence-score.schema.json`, `SYSTEM-DESIGN.md` §6 and `.claude/commands/analyze.md` step 6 -- as "data
AVAILABLE and actually analyzed". No mention of the preset. That was *accidentally* safe only while an
untraded lane was also an unanalysed one. After §15 (analysis_scope `available`) Wyckoff is live-sourced,
analysed and written up every tick under preset `ict` -- so the old definition marks it eligible, and an
untraded methodology enters both sides of the ratio that decides trades.

The test that matters is `test_an_analysed_but_untraded_lane_cannot_score`: it is the live configuration,
and it fails against the old definition.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import confluence as C
import methods as M
import spec

SCHEMA = os.path.join(ROOT, "docs", "architecture", "schemas", "confluence-score.schema.json")


def rec(dims, **kw):
    out = {"dimensions": dims}
    out.update(kw)
    return out


class OnlyConfiguredMethodologiesCount(unittest.TestCase):
    def test_an_analysed_but_untraded_lane_cannot_score(self):
        """THE defect. With preset `ict`, Wyckoff is analysed (§15) but not traded, so it must score 0."""
        plan = M.dispatch_plan("BTCUSDT")
        self.assertIn("wyckoff", plan["analysed"], "precondition: §15 analyses Wyckoff")
        self.assertNotIn("wyckoff", plan["engaged"], "precondition: the preset does not trade it")
        problems = C.check(rec({"ict": {"eligible": True, "points": 20},
                                "wyckoff": {"eligible": True, "points": 18}}, engaged_count=2),
                           instrument="BTCUSDT")
        self.assertTrue(problems)
        self.assertIn("analysed but NOT traded", problems[0])

    def test_the_same_record_without_the_untraded_lane_is_clean(self):
        self.assertEqual(C.check(rec({"ict": {"eligible": True, "points": 20},
                                      "wyckoff": {"eligible": False, "points": 0}}, engaged_count=1),
                                 instrument="BTCUSDT"), [])

    def test_a_backtest_may_pass_its_own_historical_engaged_set(self):
        """A historical run must be scored against the configuration it ran under, not today's."""
        self.assertEqual(C.check(rec({"wyckoff": {"eligible": True, "points": 18}}, engaged_count=1),
                                 engaged=["wyckoff"]), [])

    def test_resolving_eligibility_needs_both_questions(self):
        """Either question alone admits a lane the other excludes."""
        self.assertEqual(C.eligible_dimensions("BTCUSDT", {"ict", "wyckoff"}), ["ict"])   # preset excludes
        self.assertEqual(C.eligible_dimensions("BTCUSDT", {"wyckoff"}), [])              # data excludes


class EventRiskIsNotAMethodology(unittest.TestCase):
    """§18: 'Do not count ... news/event risk' as methodology confluence. §24: it is Event Risk, not a lane."""

    def test_a_news_dimension_is_refused(self):
        for name in ("news", "event_risk", "calendar"):
            problems = C.check(rec({"ict": {"eligible": True, "points": 20},
                                    name: {"eligible": True, "points": 5}}, engaged_count=2),
                               instrument="BTCUSDT")
            self.assertTrue(any("not methodology confluence" in p for p in problems), name)

    def test_the_registry_has_no_news_dimension_to_begin_with(self):
        for name in C.NOT_A_DIMENSION:
            self.assertNotIn(name, M.ALL_DIMENSIONS)


class TheArithmeticMustAgreeWithItself(unittest.TestCase):
    def test_the_denominator_must_match_what_was_counted(self):
        problems = C.check(rec({"ict": {"eligible": True, "points": 20}}, engaged_count=3),
                           instrument="BTCUSDT")
        self.assertTrue(any("denominator" in p for p in problems))

    def test_an_ineligible_lane_carrying_points_is_refused(self):
        """0 points and eligible=false are the same claim; a scored-but-ineligible lane invites a reader
        to count it."""
        problems = C.check(rec({"ict": {"eligible": True, "points": 20},
                                "wyckoff": {"eligible": False, "points": 18}}, engaged_count=1),
                           instrument="BTCUSDT")
        self.assertTrue(any("carries 18 points" in p for p in problems))


class NoFakeProbability(unittest.TestCase):
    """§18: 'Do NOT use Confidence % as a fake probability representation.'"""

    def test_the_score_declares_itself_not_a_probability(self):
        with open(SCHEMA, encoding="utf-8") as fh:
            sch = json.load(fh)
        self.assertIn("not a win-probability estimate", sch["description"])

    def test_no_confidence_pct_field_exists_anywhere_in_the_score(self):
        with open(SCHEMA, encoding="utf-8") as fh:
            props = json.load(fh)["properties"]
        for bad in ("confidence", "confidence_pct", "probability", "win_rate", "win_probability"):
            self.assertNotIn(bad, props)

    def test_the_trade_files_confidence_is_a_human_pre_trade_field(self):
        """It exists, and it is deliberately not a probability: 1-5, recorded before the outcome."""
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            f = json.load(fh)["properties"]["confidence"]
        self.assertIn("before the outcome is known", f["description"])
        self.assertNotIn("%", f["description"])


class TheDefinitionIsFixedEverywhereItWasWritten(unittest.TestCase):
    """It was stated in three places in the same words; fixing one would leave two readers wrong."""

    def test_the_schema_names_the_preset_as_the_first_condition(self):
        with open(SCHEMA, encoding="utf-8") as fh:
            desc = json.load(fh)["definitions"]["dimensionScore"]["properties"]["eligible"]["description"]
        self.assertIn("preset", desc)
        self.assertIn("§18", desc)

    def test_the_design_doc_names_it(self):
        with open(os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("the active preset engages it (§18", body)

    def test_the_analyze_command_names_it(self):
        with open(os.path.join(ROOT, ".claude", "commands", "analyze.md"), encoding="utf-8") as fh:
            body = fh.read()
        self.assertIn("engaged by the active preset", body)
        self.assertIn("analysed but not traded", body)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_18_still_says_what_this_enforces(self):
        body = spec.body(18)
        self.assertIn("Confluence Score", body)
        self.assertIn("Confidence %", body)
        self.assertIn("unrelated methodology analysis", body)
        self.assertIn("news/event risk", body)


if __name__ == "__main__":
    unittest.main()
