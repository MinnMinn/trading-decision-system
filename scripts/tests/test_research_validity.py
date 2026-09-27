"""CLAUDE.md §38 -- a research run is flagged or invalidated, and an invalid one cannot pass for a result.

§38 is two sentences and the tests split along them.

**"A research run must be flagged or invalidated when there is evidence of: <ten kinds>."** The ten are
parsed back out of CLAUDE.md here, so the registry cannot quietly cover nine of them, and each of the ten has
to arrive at a verdict from evidence this repo actually produces -- §20's quality flags, §37's probe, §11's
configuration snapshot, the engine's own declared execution assumptions.

**"Never silently produce a trustworthy-looking performance result from invalid research."** That is a claim
about what a reader SEES, so the tests below check the artifacts: the backtest report carries its verdict
above the performance tables, the stability JSON carries it beside the rows, and `rank-setups.py` -- whose
output is what the pilot places orders from -- refuses a source §38 invalidated. The three ways this could be
subverted are each given a test of their own: downgrading a condition, clearing one without evidence, and
letting an unassessed run read as a clean one.
"""
import copy
import io
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import research_validity as RV

REGISTRY = os.path.join(ROOT, "docs", "architecture", "research-validity.json")
RANK_SRC = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
BT_SRC = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
STAB_SRC = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()


def _spec_bullets():
    """§38's own list, read out of CLAUDE.md. The registry is checked against this, not against memory."""
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split("38. BACKTEST INVALIDATION", 1)[1]
    body = body.split("A research run must be flagged or invalidated when there is evidence of:", 1)[1]
    body = body.split("Never silently", 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_every_bullet_in_claude_md_38_is_a_declared_condition(self):
        self.assertEqual([RV.spec_bullet(c) for c in RV.ORDER], _spec_bullets())

    def test_an_eleventh_bullet_would_fail_rather_than_go_unclassified(self):
        # The guard is the equality above; this states the consequence explicitly so a future editor who adds
        # a bullet to CLAUDE.md sees why a test broke.
        self.assertEqual(len(RV.ORDER), 10)
        self.assertNotIn("survivorship bias", _spec_bullets())   # §9's list, not §38's -- they are different

    def test_every_disposition_is_one_of_the_two_words_38_uses(self):
        for cid in RV.ORDER:
            self.assertIn(RV.disposition_of(cid), ("FLAGS", "INVALIDATES"), cid)

    def test_every_condition_gives_a_reason_for_its_disposition(self):
        for cid in RV.ORDER:
            self.assertTrue(len(RV.CONDITIONS[cid]["why"]) > 60, cid)

    def test_a_condition_with_no_detector_must_say_why(self):
        for cid in RV.ORDER:
            c = RV.CONDITIONS[cid]
            if c["detector"] is None:
                self.assertTrue(c.get("_detector_why", "").strip(), cid)

    def test_the_look_ahead_family_invalidates_and_the_measurement_family_flags(self):
        # The registry's own test: an unbounded, flattering error invalidates; a run that measured a real but
        # different system flags. Pinned here because drifting either way is silent.
        self.assertEqual(set(RV.invalidating()),
                         {"look_ahead", "leakage", "invalid_timestamps", "future_calendar_state",
                          "future_methodology_state", "oos_contamination"})

    def test_a_registry_with_an_invented_disposition_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        data["conditions"][0]["disposition"] = "NOTED"
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-validity.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(RV.RegistryError):
                RV._load(p)
        finally:
            os.remove(p)

    def test_a_detectorless_condition_that_does_not_explain_itself_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        for c in data["conditions"]:
            if c["detector"] is None:
                c.pop("_detector_why")
                break
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-validity2.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(RV.RegistryError):
                RV._load(p)
        finally:
            os.remove(p)


class TheVerdict(unittest.TestCase):
    def _full(self, a):
        """Account for every condition so the verdict is about findings, not about blind spots."""
        for cid in RV.ORDER:
            if not a.findings(cid) and cid not in a._cleared and cid not in a._na:
                a.checked(cid, "test harness: accounted for")
        return a

    def test_nothing_checked_is_unverified_not_valid(self):
        self.assertEqual(RV.Assessment("empty").verdict(), RV.UNVERIFIED)

    def test_all_ten_accounted_for_and_clean_is_valid(self):
        self.assertEqual(self._full(RV.Assessment("clean")).verdict(), RV.VALID)

    def test_one_flags_condition_makes_the_run_flagged(self):
        a = RV.Assessment("x"); a.finding("unavailable_historical_data", "a hole")
        self.assertEqual(self._full(a).verdict(), RV.FLAGGED)

    def test_one_invalidating_condition_makes_the_run_invalid(self):
        a = RV.Assessment("x"); a.finding("look_ahead", "a decision moved")
        self.assertEqual(self._full(a).verdict(), RV.INVALID)

    def test_an_invalidating_condition_outranks_any_number_of_flags(self):
        a = RV.Assessment("x")
        for i in range(5):
            a.finding("unavailable_historical_data", f"hole {i}")
        a.finding("oos_contamination", "the holdout was used to pick this")
        self.assertEqual(self._full(a).verdict(), RV.INVALID)

    def test_an_unchecked_condition_is_named_in_the_stamp_even_when_something_fired(self):
        a = RV.Assessment("x"); a.finding("unavailable_historical_data", "a hole")
        s = a.stamp()
        self.assertEqual(s["verdict"], RV.FLAGGED)
        self.assertIn("oos_contamination", s["unchecked"])

    def test_unverified_is_documented_as_not_one_of_38s_two_words(self):
        note = json.load(open(REGISTRY, encoding="utf-8"))["verdicts"]["UNVERIFIED"]
        self.assertIn("NOT one of", note)


class EscalationOnly(unittest.TestCase):
    """The direction that loses information is closed."""

    def test_a_caller_may_escalate_a_flag_to_an_invalidation(self):
        a = RV.Assessment("x")
        a.finding("corrupted_provider_data", "every bar in 2024 has high < low",
                  disposition=RV.INVALIDATES)
        self.assertEqual(a.verdict(), RV.INVALID)
        self.assertTrue(a.findings("corrupted_provider_data")[0]["escalated"])

    def test_a_caller_may_not_soften_an_invalidation_to_a_flag(self):
        a = RV.Assessment("x")
        with self.assertRaises(RV.Downgrade):
            a.finding("look_ahead", "only a little", disposition=RV.FLAGS)

    def test_the_refusal_quotes_the_registrys_reason(self):
        a = RV.Assessment("x")
        with self.assertRaises(RV.Downgrade) as cm:
            a.finding("oos_contamination", "just a bit", disposition=RV.FLAGS)
        self.assertIn("§44", str(cm.exception))

    def test_an_undeclared_condition_cannot_be_recorded(self):
        with self.assertRaises(RV.NotDeclared):
            RV.Assessment("x").finding("vibes", "felt wrong")

    def test_a_finding_needs_a_detail_and_a_clear_needs_evidence(self):
        a = RV.Assessment("x")
        with self.assertRaises(ValueError):
            a.finding("look_ahead", "")
        with self.assertRaises(ValueError):
            a.checked("look_ahead", "")

    def test_a_condition_cannot_be_both_found_and_clear(self):
        a = RV.Assessment("x"); a.finding("look_ahead", "moved")
        with self.assertRaises(ValueError):
            a.checked("look_ahead", "ran the probe")

    def test_a_later_finding_overrides_an_earlier_clear(self):
        a = RV.Assessment("x")
        a.checked("unavailable_historical_data", "assessed, no holes")
        a.finding("unavailable_historical_data", "a hole after all")
        self.assertEqual(a.verdict(), RV.FLAGGED)
        self.assertNotIn("unavailable_historical_data", a.stamp()["checked"])


class EvidenceThisRepoActuallyProduces(unittest.TestCase):
    def test_a_timestamp_fault_invalidates_but_another_structural_fault_only_flags(self):
        # Both arrive from quality.assess() as the single state INVALID. Without the split the harsher
        # condition would never fire and the registry's distinction would be decoration.
        a = RV.Assessment("x")
        a.from_quality_flags([{"symbol": "BTCUSDT", "tf": "1H", "state": "INVALID",
                               "reason": "candle 7 repeats timestamp 2024-01-01T00:00:00Z"}])
        self.assertEqual([f["condition"] for f in a.findings()], ["invalid_timestamps"])
        self.assertEqual(a.verdict(), RV.INVALID)

        b = RV.Assessment("y")
        b.from_quality_flags([{"symbol": "BTCUSDT", "tf": "1H", "state": "INVALID",
                               "reason": "candle 7 at 2024-01-01T00:00:00Z: high 3 is below low 9"}])
        self.assertEqual([f["condition"] for f in b.findings()], ["corrupted_provider_data"])
        self.assertEqual(b.verdict(), RV.FLAGGED)

    def test_a_hole_in_the_history_flags_as_unavailable_historical_data(self):
        a = RV.Assessment("x")
        a.from_quality_flags([{"symbol": "BTCUSDT", "tf": "1H", "state": "PARTIAL",
                               "reason": "1 bar(s) missing between ... and ..."}])
        self.assertEqual([f["condition"] for f in a.findings()], ["unavailable_historical_data"])

    def test_the_real_1h_history_defect_reaches_a_38_verdict(self):
        # §20 found that BTCUSDT/ETHUSDT/SOLUSDT 1H history all miss 2023-03-24T13:00Z. That finding lived in
        # a stderr line; this is the test that it now becomes a verdict on any run that loads those bars.
        import quality
        p = os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.1H.json")
        if not os.path.exists(p):
            self.skipTest("BTCUSDT 1H history not present")
        state, why = quality.assess(json.load(open(p)), "1H", symbol="BTCUSDT")
        self.assertEqual(state, "PARTIAL", why)
        a = RV.Assessment("run over 1H")
        a.from_quality_flags([{"symbol": "BTCUSDT", "tf": "1H", "state": state, "reason": why}])
        self.assertEqual(a.verdict(), RV.FLAGGED)

    def test_a_non_fault_quality_state_is_refused_as_evidence(self):
        with self.assertRaises(ValueError):
            RV.Assessment("x").from_quality_flags([{"symbol": "B", "tf": "1H", "state": "FRESH",
                                                    "reason": "fine"}])

    def test_no_quality_flags_clears_all_three_data_conditions(self):
        a = RV.Assessment("x").from_quality_flags([])
        for cid in ("unavailable_historical_data", "corrupted_provider_data", "invalid_timestamps"):
            self.assertIn(cid, a.stamp()["checked"], cid)

    def test_a_leakage_probe_violation_invalidates_and_a_clean_probe_clears(self):
        bad = {"ok": False, "checked": 3, "modes": ["scale"],
               "violations": [{"mode": "scale", "key": "t1", "field": "entry", "before": 1, "after": 2}]}
        self.assertEqual(RV.Assessment("x").from_leakage(bad).verdict(), RV.INVALID)
        good = {"ok": True, "checked": 214, "modes": ["scale", "freeze", "invert"], "violations": []}
        self.assertIn("look_ahead", RV.Assessment("y").from_leakage(good).stamp()["checked"])

    def test_the_configuration_snapshots_unapplied_required_dependencies_become_a_finding(self):
        snap = {"fields": {"required_evidence": {
            "declared_but_not_applied_by_this_engine": ["event_risk.calendar", "venue.reconciliation"]}}}
        a = RV.Assessment("x").from_config_snapshot(snap)
        self.assertEqual([f["condition"] for f in a.findings()], ["incomplete_required_inputs"])
        self.assertIn("event_risk.calendar", a.findings()[0]["detail"])

    def test_a_snapshot_that_cannot_say_is_a_finding_not_a_pass(self):
        # A run whose configuration snapshot failed knows LESS than one whose snapshot said "nothing missing".
        a = RV.Assessment("x").from_config_snapshot({"snapshot_error": "boom"})
        self.assertEqual([f["condition"] for f in a.findings()], ["incomplete_required_inputs"])

    def test_unmodelled_execution_costs_flag_and_a_fully_modelled_engine_clears(self):
        a = RV.Assessment("x").from_execution_assumptions({"fee": "both sides", "slippage": False})
        self.assertEqual([f["condition"] for f in a.findings()], ["unrealistic_execution_assumptions"])
        self.assertIn("slippage", a.findings()[0]["detail"])
        b = RV.Assessment("y").from_execution_assumptions({"fee": "both sides", "slippage": "1 tick"})
        self.assertIn("unrealistic_execution_assumptions", b.stamp()["checked"])


class TheBacktestEngineReachesAVerdict(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "bt_rv", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        self.bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.bt)

    def test_the_engine_declares_what_it_does_and_does_not_model(self):
        ea = self.bt.EXECUTION_ASSUMPTIONS
        self.assertIs(ea["slippage"], False)
        self.assertIs(ea["min_notional"], False)     # SPEC-COMPLIANCE row 37's open item, now a §38 finding
        self.assertTrue(ea["taker_fee_both_sides"])

    def test_the_caveats_section_is_generated_from_that_dict_not_typed(self):
        # The two used to be independent and the prose was already one item short.
        self.assertIn("EXECUTION_ASSUMPTIONS.items()", BT_SRC)

    def test_a_default_run_is_flagged_for_its_unmodelled_execution(self):
        a = self.bt.assess_run()
        self.assertEqual(a.verdict(), RV.FLAGGED)
        self.assertIn("unrealistic_execution_assumptions", [f["condition"] for f in a.findings()])

    def test_the_hindsight_entry_rule_invalidates_the_run_that_used_it(self):
        # `--combined-entry hindsight` picks between two fill prices using a LATER bar. It is kept for
        # comparison against the causal rules, and before §38 a report produced with it looked exactly like a
        # report produced without it.
        self.bt.OPTS["combined_entry"] = "hindsight"
        try:
            a = self.bt.assess_run()
            self.assertEqual(a.verdict(), RV.INVALID)
            self.assertIn("look_ahead", [f["condition"] for f in a.findings()])
        finally:
            self.bt.OPTS["combined_entry"] = "limit"

    def test_a_causal_entry_rule_clears_look_ahead_and_says_what_proved_it(self):
        a = self.bt.assess_run()
        self.assertIn("leakage.py", a.stamp()["checked"]["look_ahead"])

    def test_the_engine_declares_the_calendar_inapplicable_rather_than_clean(self):
        # It reads no calendar at all; the omission belongs to incomplete_required_inputs, and calling it
        # "checked and clean" would be a claim nobody made.
        self.assertIn("future_calendar_state", self.bt.assess_run().stamp()["not_applicable"])


class TheVerdictTravelsWithTheNumbers(unittest.TestCase):
    """§38's second sentence is about what a reader sees, so these check the artifacts."""

    def test_the_backtest_report_puts_the_verdict_above_the_performance_tables(self):
        self.assertIn("_VERDICT_SLOT", BT_SRC)
        head = BT_SRC.index("_VERDICT_SLOT, \"\"]")
        tables = BT_SRC.index("| Phương pháp | Lệnh | Thắng |")
        self.assertLess(head, tables)

    def test_the_backtest_json_carries_the_block(self):
        self.assertIn("research_validity=block", BT_SRC)

    def test_the_stability_json_carries_the_block_beside_its_rows(self):
        self.assertIn("research_validity=validity.stamp()", STAB_SRC)

    def test_rank_setups_reads_the_verdict_at_the_one_place_all_modes_load_rows(self):
        self.assertIn("def load_rows(paths, market, *, require_stamped=False)", RANK_SRC)
        self.assertEqual(RANK_SRC.count("load_rows(sorted(paths), market, require_stamped=a.require_stamped)"), 1)   # ADR 0008: one selection path (was 3 modes)

    def test_the_selection_file_carries_the_validity_of_every_source_it_used(self):
        self.assertEqual(RANK_SRC.count('selection["research_validity"] = validity_note()'), 1)   # ADR 0008: one selection path (was 3 modes)


class AnInvalidRunCannotBeSelectedFrom(unittest.TestCase):
    """The end §38 exists for: `pilot-selection.json` is what the runner places orders from."""

    def _stability_file(self, tmpdir, verdict, name="crypto-std25.json"):
        os.makedirs(tmpdir, exist_ok=True)
        p = os.path.join(tmpdir, name)
        doc = {"generated": "2026-09-18", "rows": [
            {"tf": "4H", "cfg": "A", "method": "ICT", "first": "2023-01-01", "last": "2026-01-01",
             "n": 200, "ann": 30.0, "dd": 10.0, "final": 20000.0, "ruin": None, "q_pos": 70.0,
             "q_worst": -5.0, "q_med": 3.0, "q_mean": 4.0, "q_sd": 2.0, "stab": 2.0, "y_pos": 3, "y_n": 3,
             "years": [["2023", 10.0], ["2024", 10.0], ["2025", 10.0]], "quarters": [3.0] * 12,
             "w1y": {"n": 60, "ann": 20.0, "dd": 5.0, "final": 12000.0, "ruin": None, "q_pos": 75.0,
                     "q_worst": -2.0, "q_med": 2.0, "q_mean": 3.0, "q_sd": 1.0, "stab": 2.0,
                     "y_pos": 1, "y_n": 1, "since": "2025-01-01"}}]}
        if verdict is not None:
            doc["research_validity"] = {"verdict": verdict, "findings": [
                {"condition": "look_ahead", "spec_bullet": "look-ahead", "disposition": "INVALIDATES",
                 "escalated": False, "detail": "a decision moved when the future moved", "source": "test"}
            ] if verdict == RV.INVALID else [], "checked": {}, "not_applicable": {}, "unchecked": []}
        json.dump(doc, open(p, "w"))
        return p

    def _load(self, path, require_stamped=False):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rs_rv", os.path.join(ROOT, "scripts", "rank-setups.py"))
        rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
        err = io.StringIO(); real = rs._sys.stderr; rs._sys.stderr = err
        try:
            rows = rs.load_rows([path], "crypto", require_stamped=require_stamped)
        finally:
            rs._sys.stderr = real
        return rs, rows, err.getvalue()

    def setUp(self):
        self.tmp = os.path.join(ROOT, "scripts", "tests", "__tmp_stability")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rows_from_an_invalid_run_never_reach_the_ranking(self):
        rs, rows, err = self._load(self._stability_file(self.tmp, RV.INVALID))
        self.assertEqual(rows, [])
        self.assertIn("§38 REFUSED", err)
        self.assertEqual(rs.validity_note()["refused"][0]["reason"].count("INVALID"), 1)

    def test_rows_from_a_flagged_run_are_used_and_carry_the_flag(self):
        rs, rows, _ = self._load(self._stability_file(self.tmp, RV.FLAGGED))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["research_validity"], RV.FLAGGED)
        self.assertEqual(rs.validity_note()["worst"], RV.FLAGGED)

    def test_an_unstamped_file_is_used_but_never_silently(self):
        rs, rows, err = self._load(self._stability_file(self.tmp, None))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["research_validity"], rs.UNSTAMPED)
        self.assertIn("§38 WARNING", err)
        self.assertIn("UNSTAMPED", rs.validity_markdown())

    def test_require_stamped_refuses_it_outright(self):
        rs, rows, err = self._load(self._stability_file(self.tmp, None), require_stamped=True)
        self.assertEqual(rows, [])
        self.assertIn("§38 REFUSED", err)

    def test_unstamped_outranks_flagged_when_reporting_the_worst_source(self):
        # A flagged run was assessed and its defects are named; an unstamped one is entirely unknown.
        self.assertEqual(RV.worst([RV.FLAGGED, "UNSTAMPED"], extra={"UNSTAMPED": 3}), "UNSTAMPED")

    def test_worst_refuses_a_label_it_does_not_know_rather_than_skipping_it(self):
        with self.assertRaises(ValueError):
            RV.worst([RV.VALID, "PROBABLY FINE"])


class SilenceIsNotAPass(unittest.TestCase):
    def test_reading_an_unstamped_artifact_raises(self):
        with self.assertRaises(RV.Unstamped):
            RV.read({"rows": []}, where="x.json")

    def test_a_verdict_the_registry_does_not_know_is_not_accepted_as_one(self):
        with self.assertRaises(RV.Unstamped):
            RV.read({"research_validity": {"verdict": "FINE"}}, where="x.json")

    def test_require_refuses_a_verdict_outside_the_allow_list_and_says_why(self):
        block = {"verdict": RV.INVALID, "findings": [
            {"condition": "look_ahead", "detail": "a decision moved"}], "unchecked": []}
        with self.assertRaises(RV.InvalidResearch) as cm:
            RV.require(block, where="x.json")
        self.assertIn("look_ahead", str(cm.exception))

    def test_the_module_refuses_to_be_the_place_a_verdict_is_invented(self):
        # There is no setter and no "override" path: a verdict is a function of the findings.
        self.assertFalse(hasattr(RV.Assessment, "set_verdict"))
        self.assertFalse(re.search(r"def\s+override", open(
            os.path.join(ROOT, "scripts", "research_validity.py"), encoding="utf-8").read()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
