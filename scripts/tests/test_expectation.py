"""CLAUDE.md §17 -- methodology-specific expectations, and the immutability that makes §41 possible.

What was there before: `trade-file.schema.json`'s `targets`, `{"type": "array", "items": {"type": "number"}}`.
Three bare numbers, carrying none of the eight things §17 says an expectation must preserve, and no lifecycle
at all -- a repo-wide grep for POTENTIAL/EXPECTED/CONFIRMED/REACHED/INVALIDATED found only an unrelated trade
`status`, an i18n label, and Wyckoff prose.

The tests that matter here are the refusals, because every one of them is a way the type could quietly become
something else:

  * a status change that edits the thesis          -> §41 can no longer compare a thesis to its outcome
  * an expectation carrying `direction`            -> §17's "NOT automatic signals", violated in one field
  * ICT borrowing a Wyckoff kind                   -> the two methodologies' expectations stop being independent
  * a "path" of one target price                   -> §17's "Do not reduce expectations to target prices"
  * a merged cross-methodology path                -> §17 forbids the result, so no function returns it
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import expectation as X
import methods as M
import spec


def ict(**kw):
    kw.setdefault("path", [X.leg("after_entry", 77_083, "target_1"), X.leg("after_entry", 77_728, "target_2")])
    kw.setdefault("invalidation", X.invalidation("close below", 76_464, owner="wyckoff"))
    return X.create("liquidity_objective", "ict", "draw on BSL 77,728", **kw)


class TheOriginalIsImmutable(unittest.TestCase):
    """§17: 'Original expectations are immutable… The actual path must never rewrite the original.'"""

    def test_a_status_change_returns_a_new_record_and_keeps_the_same_original(self):
        e = ict()
        e2 = X.advance(e, "EXPECTED")
        self.assertIsNot(e2, e)
        self.assertIs(e2["original"], e["original"], "advance() rebuilt the original instead of carrying it")

    def test_the_original_cannot_be_edited_at_all(self):
        e = ict()
        with self.assertRaises(TypeError):
            e["original"]["statement"] = "rewritten after the fact"
        with self.assertRaises(TypeError):
            del e["original"]["expected_path"]

    def test_the_whole_lifecycle_leaves_the_thesis_untouched(self):
        e = ict()
        before = dict(e["original"])
        r = X.advance(X.advance(e, "EXPECTED"), "REACHED")
        self.assertEqual(dict(r["original"]), before)
        self.assertEqual([(h["from"], h["to"]) for h in r["history"]],
                         [("POTENTIAL", "EXPECTED"), ("EXPECTED", "REACHED")])

    def test_comparing_against_the_actual_path_writes_nothing_back(self):
        e = X.advance(ict(), "EXPECTED")
        before = dict(e["original"]), e["status"], e["history"]
        X.actual_vs_expected(e, [{"level": 76_500, "time": "t"}, {"level": 77_800, "time": "t"}])
        self.assertEqual((dict(e["original"]), e["status"], e["history"]), before)


class TheLifecycle(unittest.TestCase):
    def test_every_state_the_spec_names_exists(self):
        for s in ("POTENTIAL", "EXPECTED", "CONFIRMED", "REACHED", "INVALIDATED", "CANCELLED", "UNKNOWN"):
            self.assertIn(s, X.STATES)

    def test_an_expectation_is_born_potential(self):
        """A record that could be born CONFIRMED would let a caller skip the evidence that confirms it."""
        self.assertEqual(ict()["status"], "POTENTIAL")

    def test_an_outcome_is_final(self):
        for terminal in X.TERMINAL:
            r = X.advance(ict(), terminal)
            with self.assertRaises(ValueError) as cm:
                X.advance(r, "EXPECTED")
            self.assertIn("terminal", str(cm.exception))

    def test_unknown_is_a_state_you_can_come_back_from(self):
        """§9: 'Unknown is a valid state.' It is an absence of knowledge, not an outcome, so it resolves."""
        u = X.advance(ict(), "UNKNOWN")
        self.assertTrue(X.is_open(u))
        self.assertEqual(X.advance(u, "CONFIRMED")["status"], "CONFIRMED")

    def test_every_transition_target_is_a_real_state(self):
        for src, dests in X.TRANSITIONS.items():
            self.assertIn(src, X.STATES)
            for d in dests:
                self.assertIn(d, X.STATES)

    def test_a_status_change_records_when_and_why(self):
        r = X.advance(ict(), "REACHED", at="2026-09-17T20:00:00Z", because="traded 77,728")
        self.assertEqual(r["history"][-1]["at"], "2026-09-17T20:00:00Z")
        self.assertEqual(r["history"][-1]["because"], "traded 77,728")


class MethodologiesStayIndependent(unittest.TestCase):
    """§17: 'Multiple methodologies must maintain independent expectations. Do not merge their expected
    paths merely because they appear on the same chart.'"""

    def test_each_kind_belongs_to_exactly_one_methodology(self):
        seen = {}
        for dim in M.ALL_DIMENSIONS:
            for k in X.kinds(dim):
                self.assertNotIn(k, seen, f"{k!r} is claimed by both {seen.get(k)} and {dim}")
                seen[k] = dim
        self.assertTrue(seen, "no expectation kinds are declared at all")

    def test_borrowing_another_methodologys_kind_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            X.create("liquidity_objective", "wyckoff", "x", path=[X.leg("after_entry", 1, "t")],
                     invalidation=X.invalidation("r", 1, owner="wyckoff"))
        self.assertIn("belongs to 'ict'", str(cm.exception))

    def test_paths_are_returned_grouped_never_merged(self):
        a = ict()
        b = X.create("cause_effect_objective", "wyckoff", "TR objective",
                     path=[X.leg("after_entry", 78_000, "co")],
                     invalidation=X.invalidation("close below", 76_464, owner="wyckoff"))
        grouped = X.paths_by_methodology([a, b])
        self.assertEqual(sorted(grouped), ["ict", "wyckoff"])
        self.assertEqual(len(grouped["ict"]), 1)
        self.assertEqual(len(grouped["wyckoff"]), 1)

    def test_no_function_here_concatenates_two_methodologies_paths(self):
        """The shape a function returns is what its callers will do, so the merged shape does not exist."""
        src = open(os.path.join(ROOT, "scripts", "expectation.py"), encoding="utf-8").read()
        self.assertIn("never merged across them", src)

    def test_the_kinds_come_from_the_registry_not_this_module(self):
        src = open(os.path.join(ROOT, "scripts", "expectation.py"), encoding="utf-8").read()
        self.assertIn("M.DIMENSIONS[methodology]", src)
        with open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
        self.assertIn("expectation_kinds", reg["dimensions"]["ict"])


class AnExpectationIsNotASignal(unittest.TestCase):
    """§17: 'Expectations are NOT automatic signals.' Same failure as §12's, one rung up the ladder."""

    def test_decision_shaped_fields_are_refused(self):
        for field in ("direction", "side", "signal", "entry", "position_size", "risk_pct"):
            with self.assertRaises(ValueError, msg=f"{field} was accepted") as cm:
                ict(**{field: "long"})
            self.assertIn("NOT automatic signals", str(cm.exception))

    def test_an_analytical_extra_field_is_still_allowed(self):
        """The guard must refuse decisions, not annotations -- otherwise callers route around it."""
        e = ict(confidence_note="displacement was weak")
        self.assertEqual(e["original"]["confidence_note"], "displacement was weak")


class TheEightRequiredFields(unittest.TestCase):
    def test_the_spec_names_all_eight_and_every_record_carries_them(self):
        e = ict(series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z")
        for f in ("methodology", "source_evidence", "created_at", "available_time",
                  "status", "expected_path", "invalidation", "provenance"):
            self.assertIn(f, e["original"], f"§17 requires {f}")

    def test_a_record_missing_one_is_refused_rather_than_written_with_a_hole(self):
        with self.assertRaises(ValueError) as cm:
            X._seal({"methodology": "ict"})
        self.assertIn("missing required field", str(cm.exception))

    def test_available_time_follows_the_bar_not_the_wall_clock(self):
        """§7/§8: a 15m bar opening 18:00 is knowable at 18:15, so an expectation drawn from it is too."""
        e = ict(series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z")
        self.assertEqual(e["original"]["available_time"], "2026-09-17T18:15:00Z")

    def test_creation_time_and_available_time_are_different_facts(self):
        e = ict(series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z",
                created_at="2026-09-17T19:30:00Z")
        self.assertNotEqual(e["original"]["created_at"], e["original"]["available_time"])

    def test_expectations_pass_through_the_pit_gate(self):
        """§8 lists 'expectations' among the things point-in-time integrity applies to."""
        e = ict(series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z")
        self.assertTrue(X.admissible([e], decision_time="2026-09-17T18:30:00Z")["ok"])
        early = X.admissible([e], decision_time="2026-09-17T18:05:00Z")
        self.assertFalse(early["ok"])
        self.assertIn("look-ahead", early["refused"][0]["reason"])


class APathIsNotATargetPrice(unittest.TestCase):
    """§17: 'Expectation is broader than targetPrice' and 'Do not reduce expectations to target prices.'"""

    def test_an_expectation_with_no_path_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            X.create("liquidity_objective", "ict", "x", path=[],
                     invalidation=X.invalidation("r", 1, owner="ict"))
        self.assertIn("target prices", str(cm.exception))

    def test_a_leg_carries_its_phase(self):
        """§17's model has three phases: before entry, entry area, after entry."""
        self.assertEqual(sorted(X.PHASES), ["after_entry", "before_entry", "entry_area"])
        self.assertEqual(X.leg("entry_area", 76_500, "zone")["phase"], "entry_area")

    def test_an_unknown_phase_is_refused(self):
        with self.assertRaises(ValueError):
            X.leg("during_entry", 1, "t")

    def test_the_invalidation_owner_must_be_a_methodology_that_can_own_one(self):
        """A lane that cannot define a structural level cannot own the condition that ends an expectation."""
        with self.assertRaises(ValueError):
            X.invalidation("close below", 1, owner="footprint")


class ComparingTheActualPath(unittest.TestCase):
    def test_a_fully_traded_path_reads_reached(self):
        e = ict()
        cmp = X.actual_vs_expected(e, [{"level": 76_500, "time": "t"}, {"level": 77_800, "time": "t"}])
        self.assertTrue(cmp["reached"])
        self.assertTrue(all(l["met"] for l in cmp["legs"]))

    def test_a_partly_traded_path_says_which_leg(self):
        e = ict()
        cmp = X.actual_vs_expected(e, [{"level": 76_500, "time": "t"}, {"level": 77_100, "time": "t"}])
        self.assertEqual([l["met"] for l in cmp["legs"]], [True, False])
        self.assertFalse(cmp["reached"])

    def test_an_empty_actual_path_is_unknown_not_false(self):
        """No data is not evidence of failure -- forcing it to False is how a thesis gets blamed for a gap."""
        cmp = X.actual_vs_expected(ict(), [])
        self.assertIsNone(cmp["reached"])

    def test_a_downward_path_is_measured_downward(self):
        e = X.create("structural_objective", "ict", "down to SSL",
                     path=[X.leg("after_entry", 76_000, "t1")],
                     invalidation=X.invalidation("close above", 77_500, owner="ict"))
        self.assertTrue(X.actual_vs_expected(e, [{"level": 76_400, "time": "t"},
                                                 {"level": 75_900, "time": "t"}])["reached"])


class ItSurvivesBeingWrittenDown(unittest.TestCase):
    """A record that cannot reach disk is a record the trade file cannot carry -- and the workaround a
    caller would reach for (making `original` a plain dict) deletes the immutability outright."""

    def test_a_record_round_trips_through_json(self):
        r = X.advance(ict(series=("BTCUSDT", "15m"), event_time="2026-09-17T18:00:00Z"), "REACHED")
        back = X.from_json(json.loads(json.dumps(X.to_json(r))))
        self.assertEqual(back["id"], r["id"])
        self.assertEqual(back["status"], "REACHED")
        self.assertEqual(dict(back["original"]), dict(r["original"]))

    def test_a_record_read_back_from_disk_is_still_immutable(self):
        r = X.advance(ict(), "EXPECTED")
        back = X.from_json(json.loads(json.dumps(X.to_json(r))))
        with self.assertRaises(TypeError):
            back["original"]["statement"] = "rewritten after a restart"

    def test_the_lifecycle_continues_after_a_round_trip(self):
        back = X.from_json(json.loads(json.dumps(X.to_json(X.advance(ict(), "EXPECTED")))))
        self.assertEqual(X.advance(back, "REACHED")["status"], "REACHED")

    def test_the_trade_schema_accepts_the_written_shape(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            sch = json.load(fh)["properties"]["expectations"]["items"]
        blob = X.to_json(X.advance(ict(series=("BTCUSDT", "15m"),
                                       event_time="2026-09-17T18:00:00Z"), "REACHED"))
        for field in sch["required"]:
            self.assertIn(field, blob)
        for field in sch["properties"]["original"]["required"]:
            self.assertIn(field, blob["original"], f"schema requires original.{field}")
        self.assertRegex(blob["id"], r"^[0-9a-f]{12}$")
        self.assertIn(blob["status"], sch["properties"]["status"]["enum"])

    def test_the_legacy_targets_field_is_kept_and_labelled(self):
        """Deleting it would silently strip closed trades of what they recorded."""
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            props = json.load(fh)["properties"]
        self.assertIn("targets", props)
        self.assertIn("LEGACY", props["targets"]["description"])


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_every_state_in_the_spec_body_is_implemented(self):
        body = spec.body(17)
        for s in X.STATES:
            self.assertIn(s, body, f"{s} is not a state §17 names")

    def test_the_spec_still_forbids_reducing_expectations_to_targets(self):
        self.assertIn("Do not reduce expectations to target prices", spec.body(17))

    def test_the_spec_still_requires_immutability(self):
        body = spec.body(17)
        self.assertIn("Original expectations are immutable", body)
        self.assertIn("must never rewrite the original expectation", body)


if __name__ == "__main__":
    unittest.main()
