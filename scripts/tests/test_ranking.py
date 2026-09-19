"""CLAUDE.md §48 SYSTEM RANKING + §49 NEWS A/B -- two sections, one rule.

    §48: "Do not create a universal 'best system' score."
    §49: "Do not assume the filter improves performance."

Both forbid a conclusion from being baked into the machinery that is supposed to reach it. §48's version is a
weighted blend whose weights ARE the objective while looking like arithmetic. §49's is an A/B that can only
come out one way because the arms were not actually identical.

So the tests below spend most of their weight on three refusals:

* a ranking may not be produced from a blend — every objective is lexicographic over named keys, the deciding
  key is reported per row, and the registry loader rejects an objective that looks like a weighted score;
* an unmeasurable row may not win by being unmeasured, and may not be quietly dropped either;
* an A/B whose arms differ in anything §49 says to hold identical RAISES rather than reporting with a caveat,
  because a caveat on a two-column table is not read.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ranking as R
import performance as P

REGISTRY = os.path.join(ROOT, "docs", "architecture", "ranking.json")
SRC = open(os.path.join(ROOT, "scripts", "ranking.py"), encoding="utf-8").read()


def _bullets(section, nxt, after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split(section, 1)[1].split(nxt, 1)[0].split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


def _row(rid, **kw):
    """A ranking row with every §48 exposure supplied unless a test removes one."""
    d = {"id": rid, "ranking_objective": "expectancy", "metrics": {"n": 100}, "sample_size": 100,
         "validation_state": {"verdict": "NOT_RUN"}, "test_period": "2023-2026",
         "assumptions": {"slippage": False}, "robustness_status": "SURVIVED"}
    d.update(kw)
    return d


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_seven_ranking_objectives_are_declared(self):
        self.assertEqual([R.OBJECTIVES[o]["spec_name"] for o in R.OBJECTIVE_ORDER],
                         _bullets("48. SYSTEM RANKING", "49. NEWS A/B", "Possible objectives:",
                                  "Do not create a universal"))

    def test_all_seven_always_expose_items_are_declared(self):
        self.assertEqual([R.EXPOSURE_NAMES[e] for e in R.EXPOSURES],
                         _bullets("48. SYSTEM RANKING", "49. NEWS A/B", "Always expose:", "==="))

    def test_all_nine_ab_comparison_dimensions_are_declared(self):
        self.assertEqual([c["spec_name"] for c in R._DATA["news_ab"]["compare"]],
                         _bullets("49. NEWS A/B", "50. UI / UX", "Compare:", "Use identical:"))

    def test_everything_49_says_to_hold_identical_is_declared(self):
        self.assertEqual([i["spec_name"] for i in R._DATA["news_ab"]["identical"]],
                         _bullets("49. NEWS A/B", "50. UI / UX", "Use identical:", "==="))

    def test_every_objective_pairs_each_key_with_a_direction(self):
        for oid in R.OBJECTIVE_ORDER:
            o = R.OBJECTIVES[oid]
            self.assertEqual(len(o["keys"]), len(o["direction"]), oid)

    def test_a_registry_objective_that_looks_like_a_weighted_blend_is_refused(self):
        # The one edit that would turn a lexicographic ranking back into a universal score.
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["ranking"]["objectives"][0]["weight"] = {"expectancy": 0.6, "max_drawdown": 0.4}
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-ranking.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(R.RegistryError) as cm:
                R._load(p)
            self.assertIn("universal best system score", str(cm.exception))
        finally:
            os.remove(p)

    def test_the_module_has_no_weighting_parameter(self):
        for forbidden in ("weight", "blend", "composite_score"):
            self.assertNotIn(f"{forbidden}=", SRC, forbidden)


class RankingIsLexicographicAndSaysWhatDecided(unittest.TestCase):
    def test_a_single_key_objective_orders_by_that_key(self):
        rows = [_row("a", expectancy=0.1), _row("b", expectancy=0.5), _row("c", expectancy=0.3)]
        res = R.rank(rows, objective_id="expectancy")
        self.assertEqual([x["row"]["id"] for x in res["ranked"]], ["b", "c", "a"])

    def test_the_deciding_key_is_reported_per_row(self):
        # "Why is this first" must have an answer that is not "the score".
        rows = [_row("a", max_drawdown=0.5, time_in_drawdown=0.1),
                _row("b", max_drawdown=0.5, time_in_drawdown=0.9)]
        res = R.rank(rows, objective_id="drawdown")
        self.assertEqual(res["ranked"][0]["row"]["id"], "a")
        self.assertEqual(res["ranked"][0]["decided_by"], "time_in_drawdown")

    def test_a_later_key_only_decides_when_the_earlier_ones_tie(self):
        rows = [_row("a", max_drawdown=0.2, time_in_drawdown=0.9),
                _row("b", max_drawdown=0.5, time_in_drawdown=0.1)]
        res = R.rank(rows, objective_id="drawdown")
        self.assertEqual(res["ranked"][0]["row"]["id"], "a")
        self.assertEqual(res["ranked"][0]["decided_by"], "max_drawdown")

    def test_the_result_names_the_objective_and_its_keys(self):
        # "Ranked by consistency" without the keys is a label, not a method.
        res = R.rank([_row("a")], objective_id="survival")
        self.assertEqual(res["objective_name"], "Survival")
        self.assertEqual(res["keys"][0], "not_ruined")

    def test_different_objectives_give_different_winners(self):
        # The whole reason §48 forbids one score: "best" depends on what you are asking.
        rows = [_row("hot", expectancy=1.0, max_drawdown=0.9, time_in_drawdown=0.8),
                _row("steady", expectancy=0.2, max_drawdown=0.1, time_in_drawdown=0.1)]
        self.assertEqual(R.rank(rows, objective_id="expectancy")["ranked"][0]["row"]["id"], "hot")
        self.assertEqual(R.rank(rows, objective_id="drawdown")["ranked"][0]["row"]["id"], "steady")

    def test_a_custom_objective_must_declare_its_keys(self):
        with self.assertRaises(R.NotDeclared):
            R.rank([_row("a")], objective_id="custom")
        res = R.rank([_row("a", foo=1.0), _row("b", foo=2.0)],
                     objective_id="custom", custom_keys=["foo"], custom_direction=["max"])
        self.assertEqual(res["ranked"][0]["row"]["id"], "b")

    def test_an_invented_objective_is_refused(self):
        with self.assertRaises(R.NotDeclared):
            R.rank([_row("a")], objective_id="vibes")


class AnUnmeasurableRowNeitherWinsNorDisappears(unittest.TestCase):
    def test_a_row_missing_the_sort_key_sorts_last(self):
        rows = [_row("measured", expectancy=0.1), _row("unmeasured")]
        res = R.rank(rows, objective_id="expectancy")
        self.assertEqual(res["ranked"][0]["row"]["id"], "measured")
        self.assertEqual(res["ranked"][1]["unmeasurable_keys"], ["expectancy"])

    def test_an_unavailable_metric_never_sorts_as_a_number(self):
        rows = [_row("real", expectancy=0.1),
                _row("unavailable", expectancy=P.unavailable("no account"))]
        res = R.rank(rows, objective_id="expectancy")
        self.assertEqual(res["ranked"][0]["row"]["id"], "real")

    def test_a_minimised_key_that_is_missing_still_sorts_last(self):
        # The subtle case: on a MIN key, a missing value must not read as "zero drawdown".
        rows = [_row("has_dd", max_drawdown=0.4, time_in_drawdown=0.2), _row("no_dd")]
        res = R.rank(rows, objective_id="drawdown")
        self.assertEqual(res["ranked"][0]["row"]["id"], "has_dd")

    def test_every_row_is_returned_none_are_filtered(self):
        rows = [_row("a", expectancy=0.1), _row("b")]
        self.assertEqual(len(R.rank(rows)["ranked"]), 2)

    def test_a_row_missing_an_exposure_is_ranked_and_marked(self):
        # Dropping it hides a system; ranking it silently hides that the comparison is uneven.
        bare = _row("bare", expectancy=0.9)
        del bare["robustness_status"]
        res = R.rank([_row("full", expectancy=0.1), bare])
        marked = [x for x in res["ranked"] if x["row"]["id"] == "bare"][0]
        self.assertEqual(marked["rank"], 1)
        self.assertIn("robustness status", marked["missing_exposure_names"])

    def test_a_fully_exposed_row_is_marked_with_nothing(self):
        res = R.rank([_row("full", expectancy=0.1)])
        self.assertEqual(res["ranked"][0]["missing_exposures"], [])

    def test_the_exposure_report_names_which_rows_lack_which(self):
        bare = _row("bare"); del bare["validation_state"]
        rep = R.exposure_report([_row("full"), bare])
        self.assertEqual(rep["validation_state"]["supplied"], 1)
        self.assertEqual(rep["validation_state"]["missing_from"], ["bare"])


class TheABRefusesRatherThanCaveats(unittest.TestCase):
    CTX = {"datasets": "ds1", "time_ranges": "2023-2026", "pit_state": "strict",
           "risk_assumptions": {"max_risk_pct": 0.01}, "execution_assumptions": {"fee": 0.0005},
           "account_profile": "pilot-mt5-demo"}

    def _arm(self, **kw):
        d = dict(self.CTX)
        d.update({"expectancy": 0.2, "drawdown": 0.3, "trade_count": 100, "opportunity_loss": 0.0,
                  "missed_opportunities": 0, "robustness": 1, "regime_behavior": 1,
                  "session_behavior": 1, "sample_size": 100})
        d.update(kw)
        return d

    def test_identical_arms_compare(self):
        out = R.ab(self._arm(expectancy=0.2), self._arm(expectancy=0.5))
        self.assertAlmostEqual(out["dimensions"]["expectancy"]["delta"], -0.3)

    def test_arms_that_differ_on_the_dataset_raise(self):
        with self.assertRaises(R.ArmsDiffer) as cm:
            R.ab(self._arm(), self._arm(datasets="ds2"))
        self.assertIn("datasets", str(cm.exception))

    def test_every_item_49_lists_is_enforced_individually(self):
        for k in R.AB_IDENTICAL:
            with self.assertRaises(R.ArmsDiffer, msg=k):
                R.ab(self._arm(), self._arm(**{k: "different"}))

    def test_the_refusal_names_which_item_differed(self):
        with self.assertRaises(R.ArmsDiffer) as cm:
            R.ab(self._arm(), self._arm(account_profile="other"))
        self.assertIn("account profile", str(cm.exception))

    def test_the_comparison_reaches_no_verdict(self):
        # §49: "Do not assume the filter improves performance." The comparison states; it does not conclude.
        out = R.ab(self._arm(expectancy=0.5), self._arm(expectancy=0.1))
        self.assertIsNone(out["_verdict"])
        self.assertIn("does not conclude", out["_note"])

    def test_the_filters_cost_is_reported_beside_its_benefit(self):
        # An A/B that reports only expectancy and drawdown can only ever flatter a filter.
        out = R.ab(self._arm(expectancy=0.5, opportunity_loss=-40.0, missed_opportunities=12),
                   self._arm(expectancy=0.3, opportunity_loss=0.0, missed_opportunities=0))
        self.assertEqual(out["dimensions"]["opportunity_loss"]["A_filter_on"], -40.0)
        self.assertEqual(out["dimensions"]["missed_opportunities"]["A_filter_on"], 12)

    def test_all_nine_dimensions_appear_even_when_one_cannot_be_compared(self):
        out = R.ab(self._arm(robustness=None), self._arm())
        for dim in R.AB_COMPARE:
            self.assertIn(dim, out["dimensions"], dim)
        self.assertIn("robustness", out["incomparable_dimensions"])

    def test_an_undeclared_context_item_is_reported_not_assumed_equal(self):
        a = self._arm(); b = self._arm()
        del a["pit_state"]; del b["pit_state"]
        out = R.ab(a, b)
        self.assertIn("pit_state", out["undeclared_context"])

    def test_the_held_identical_context_travels_in_the_result(self):
        out = R.ab(self._arm(), self._arm())
        self.assertEqual(out["held_identical"]["datasets"], "ds1")


class AgainstTheRepositorysOwnRankingConsumer(unittest.TestCase):
    def test_rank_setups_still_sorts_on_a_lexicographic_tuple(self):
        # §48 is enforced at the consumer too: the pilot selection must not become a blended score.
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertIn('key=lambda r: (r["ruin"] is None, r["q_pos"]', src)
        self.assertNotIn("weighted", src.lower())

    def test_the_consistency_objective_matches_what_that_consumer_sorts_on(self):
        # Named as one objective among seven rather than as the meaning of "best".
        self.assertEqual(R.OBJECTIVES["consistency"]["keys"],
                         ["positive_period_share", "worst_period"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
