"""CLAUDE.md §41 -- eight outcome states, the two that must not be called failures, and the decision only a
human may make.

§41's three demands, and how each had been missed:

**Eight outcome states.** Five were *unrepresentable*. A trade file carries WIN / LOSS / BREAKEVEN; the runner
logged every block reason into `pilot-selection-log.jsonl` and **nothing ever read it back**, so "the filter saved us"
and "the filter cost us a winner" were the same silence.

**"NO TRADE and BLOCKED ENTRY must NOT automatically be classified as failures."** The word is *automatically*.
`is_failure` is three-valued here and the registry itself refuses an evaluation state that declares a
non-null default — the guard is in the loader, not in a convention.

**"AI must NEVER silently rewrite the production Trading System."** The word is *silently*. Enforced by making
the artifact mandatory, ordered, and unapprovable until the pipeline has been walked — plus a decision stage
that refuses any actor but a human. The tests below try to subvert each of those three separately.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import outcomes as O

REGISTRY = os.path.join(ROOT, "docs", "architecture", "outcomes.json")
SRC = open(os.path.join(ROOT, "scripts", "outcomes.py"), encoding="utf-8").read()


def _bullets(after, until):
    """Bullets between two markers INSIDE §41. Scoped to the section on purpose: 'Distinguish:' first appears
    in §27, and a repo-wide split would have quietly parsed the wrong list."""
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    section = spec.split("41. FAILURE LEARNING", 1)[1].split("42. EXPERIMENT INFRASTRUCTURE", 1)[0]
    body = section.split(after, 1)[1].split(until, 1)[0]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_eight_outcome_states_claude_md_41_names_are_declared(self):
        self.assertEqual([O.spec_name(s) for s in O.ORDER],
                         _bullets("Outcome states must include:", "NO TRADE and BLOCKED ENTRY"))

    def test_the_five_things_an_evaluation_state_may_reveal_are_declared(self):
        want = _bullets("They may reveal:", "Distinguish:")
        self.assertEqual([r["spec_name"] for r in O._DATA["reveals"]], want)

    def test_the_four_causal_categories_are_declared(self):
        want = _bullets("Distinguish:", "Unknown is a valid causal state")
        self.assertEqual([c["spec_name"] for c in O._DATA["causes"]], want)

    def test_the_five_things_ai_may_do_are_declared(self):
        self.assertEqual(list(O.AI_MAY), _bullets("AI may:", "AI must NEVER"))

    def test_the_pipeline_has_all_eleven_stages_in_order(self):
        self.assertEqual(len(O.PIPELINE), 11)
        self.assertEqual(O.STAGE_ORDER[0], "trading_outcomes")
        self.assertEqual(O.STAGE_ORDER[-1], "human_decision")

    def test_an_unimplemented_stage_must_say_why(self):
        # A stage nobody declared absent is a stage a proposal will quietly skip.
        for sid, why in O.ABSENT_STAGES.items():
            self.assertTrue(str(why or "").strip(), sid)

    def test_a_registry_that_calls_an_evaluation_state_a_failure_is_refused(self):
        # The guard is in the loader, not in a convention -- this is §41's most reversible rule.
        data = json.load(open(REGISTRY, encoding="utf-8"))
        for st in data["states"]:
            if st["id"] == "BLOCKED_ENTRY":
                st["is_failure"] = True
                break
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-outcomes.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(O.RegistryError) as cm:
                O._load(p)
            self.assertIn("must NOT automatically", str(cm.exception))
        finally:
            os.remove(p)

    def test_a_null_failure_flag_must_justify_itself(self):
        for sid in O.ORDER:
            if O.is_failure(sid) is None:
                self.assertTrue(O.STATES[sid].get("_is_failure_why", "").strip(), sid)


class EvaluationStatesAreNotFailures(unittest.TestCase):
    def test_no_trade_and_blocked_entry_are_neither_failures_nor_successes(self):
        for sid in ("NO_TRADE", "BLOCKED_ENTRY"):
            self.assertIsNone(O.is_failure(sid), sid)
            self.assertEqual(O.family(sid), O.EVALUATION)

    def test_a_loss_is_not_automatically_a_failure_either(self):
        # A loss inside the system's expectancy is the cost of the edge. What makes it a failure is a CAUSE.
        self.assertIsNone(O.is_failure("LOSS"))

    def test_the_faults_are_failures(self):
        for sid in ("EXECUTION_FAILURE", "DATA_FAILURE"):
            self.assertIs(O.is_failure(sid), True, sid)

    def test_the_distribution_separates_failures_from_needs_a_counterfactual(self):
        rows = [O.record("BLOCKED_ENTRY"), O.record("EXECUTION_FAILURE"), O.record("WIN")]
        d = O.distribution(rows)
        self.assertEqual(d["failures"], 1)
        self.assertEqual(d["needs_counterfactual"], 1)

    def test_the_distribution_reports_states_that_are_zero(self):
        # "No execution failure was recorded" and "execution failure cannot be recorded" look identical in a
        # dict that omits empty keys -- and the second was this repo's actual state until §41.
        d = O.distribution([O.record("WIN")])
        for sid in O.ORDER:
            self.assertIn(sid, d["counts"], sid)
        self.assertEqual(d["counts"]["EXECUTION_FAILURE"], 0)

    def test_reveals_only_applies_to_an_evaluation_state(self):
        O.record("BLOCKED_ENTRY", reveals=["beneficial_filtering"])          # fine
        with self.assertRaises(O.NotDeclared):
            O.record("WIN", reveals=["beneficial_filtering"])

    def test_an_invented_reveal_is_refused(self):
        with self.assertRaises(O.NotDeclared):
            O.record("NO_TRADE", reveals=["it_felt_wrong"])


class UnknownIsAValidCause(unittest.TestCase):
    def test_unknown_is_the_default(self):
        self.assertEqual(O.record("LOSS")["cause"], O.UNKNOWN)

    def test_unknown_is_accepted_explicitly(self):
        self.assertEqual(O.cause(O.UNKNOWN), O.UNKNOWN)

    def test_an_invented_cause_is_refused(self):
        with self.assertRaises(O.NotDeclared):
            O.record("LOSS", cause_id="bad_luck")

    def test_the_registry_says_not_to_force_a_category(self):
        self.assertIn("Do not force every outcome into a causal category",
                      O._DATA["_unknown_cause"])


class IngestReadsWhatTheLivePathAlreadyWrote(unittest.TestCase):
    """The §41 gap was not capture, it was that nothing read the capture back."""

    def test_a_blocked_signal_becomes_a_blocked_entry_naming_what_blocked_it(self):
        row = {"kind": "signal", "t": "2026-09-12T08:00:00Z", "symbol": "BTCUSDT", "strategy": "s1",
               "ok": False, "reasons": ["event_risk.calendar: lịch sự kiện không đọc được"]}
        rec = O._from_log_row(row, "test")
        self.assertEqual(rec["state"], "BLOCKED_ENTRY")
        self.assertEqual(rec["blocked_on"], "event_risk.calendar")
        self.assertIsNone(rec["is_failure"])

    def test_a_signal_with_no_reasons_is_a_no_trade_not_a_block(self):
        rec = O._from_log_row({"kind": "signal", "ok": False, "reasons": []}, "test")
        self.assertEqual(rec["state"], "NO_TRADE")

    def test_an_accepted_signal_is_not_an_outcome_here(self):
        # It becomes a trade; the journal carries its result. Counting it twice would double the population.
        self.assertIsNone(O._from_log_row({"kind": "signal", "ok": True, "reasons": []}, "test"))

    def test_a_venue_rejection_is_an_execution_failure(self):
        rec = O._from_log_row({"kind": "rejected", "note": "MT5 retcode 10016"}, "test")
        self.assertEqual(rec["state"], "EXECUTION_FAILURE")
        self.assertEqual(rec["cause"], "execution_failure")

    def test_a_venue_floor_skip_is_an_execution_failure_but_an_ordinary_skip_is_not(self):
        # The distinction matters: one is the venue refusing our size, the other is us declining to trade.
        floor = O._from_log_row({"kind": "skip", "why": "notional below exchange minimum 5.0"}, "test")
        self.assertEqual(floor["state"], "EXECUTION_FAILURE")
        other = O._from_log_row({"kind": "skip", "why": "htf filter"}, "test")
        self.assertEqual(other["state"], "NO_TRADE")

    def test_a_quality_error_is_a_data_failure(self):
        rec = O._from_log_row({"kind": "error", "msg": "BTCUSDT 1H quality PARTIAL"}, "test")
        self.assertEqual(rec["state"], "DATA_FAILURE")
        self.assertEqual(rec["cause"], "data_failure")

    def test_a_closed_trade_becomes_win_loss_or_breakeven_on_the_same_band_as_39(self):
        for r, want in ((2.0, "WIN"), (-1.0, "LOSS"), (0.0, "BREAKEVEN"), (0.01, "BREAKEVEN")):
            rec = O._from_trade({"status": "CLOSED", "r_multiple": r, "instrument": "BTCUSDT"}, "j")
            self.assertEqual(rec["state"], want, r)

    def test_an_open_or_planned_trade_is_not_an_outcome(self):
        self.assertIsNone(O._from_trade({"status": "PLANNED", "r_multiple": None}, "j"))

    def test_ingest_runs_over_the_real_repository(self):
        rows = O.ingest()
        self.assertIsInstance(rows, list)
        for r in rows:
            self.assertIn(r["state"], O.ORDER)
            self.assertIn(r["cause"], (O.UNKNOWN,) + O.CAUSES)

    def test_the_real_pilot_log_produces_evaluation_states_that_were_previously_invisible(self):
        # The point of §41 in this repo: these records existed as log lines and nothing could count them.
        rows = O.ingest()
        if not rows:
            self.skipTest("no pilot log in this checkout")
        self.assertTrue(any(r["family"] == O.EVALUATION for r in rows))


class TheCounterfactual(unittest.TestCase):
    def _candles(self, highs, lows):
        return [{"time": f"2026-09-12T{8 + i:02d}:00:00Z", "high": h, "low": l, "open": h, "close": l}
                for i, (h, l) in enumerate(zip(highs, lows))]

    def test_a_blocked_entry_that_would_have_won_becomes_a_missed_opportunity(self):
        rec = dict(O.record("BLOCKED_ENTRY", at="2026-09-12T08:00:00Z", symbol="BTCUSDT"),
                   plan={"entry": 100, "stop": 95, "target": 110})
        out = O.resolve([rec], {"BTCUSDT": self._candles([101, 111], [99, 105])})
        self.assertEqual(out[0]["state"], "MISSED_OPPORTUNITY")
        self.assertEqual(out[0]["resolves"], "BLOCKED_ENTRY")
        self.assertIn("missed_opportunities", out[0]["reveals"])

    def test_a_blocked_entry_that_would_have_lost_reveals_beneficial_filtering(self):
        rec = dict(O.record("BLOCKED_ENTRY", at="2026-09-12T08:00:00Z", symbol="BTCUSDT"),
                   plan={"entry": 100, "stop": 95, "target": 110})
        out = O.resolve([rec], {"BTCUSDT": self._candles([101, 102], [99, 94])})
        self.assertEqual(out[0]["state"], "BLOCKED_ENTRY")
        self.assertIn("beneficial_filtering", out[0]["reveals"])

    def test_an_unresolved_counterfactual_says_so_rather_than_defaulting(self):
        rec = dict(O.record("BLOCKED_ENTRY", at="2026-09-12T08:00:00Z", symbol="BTCUSDT"),
                   plan={"entry": 100, "stop": 95, "target": 110})
        out = O.resolve([rec], {"BTCUSDT": self._candles([101, 102], [99, 98])})
        self.assertIn("neither target nor stop", out[0]["resolution"])

    def test_the_horizon_travels_with_the_verdict(self):
        # "Would have won" is meaningless without "by when", and a long enough horizon makes almost anything
        # a missed opportunity.
        rec = dict(O.record("BLOCKED_ENTRY", at="2026-09-12T08:00:00Z", symbol="BTCUSDT"),
                   plan={"entry": 100, "stop": 95, "target": 110})
        out = O.resolve([rec], {"BTCUSDT": self._candles([101, 111], [99, 105])}, horizon=50)
        self.assertEqual(out[0]["horizon_bars"], 50)

    def test_a_realised_outcome_is_left_alone(self):
        rows = [O.record("WIN", r=2.0)]
        self.assertEqual(O.resolve(rows, {}), rows)


class Clustering(unittest.TestCase):
    def test_a_repeated_failure_clusters_and_a_single_one_does_not(self):
        rows = [O.record("BLOCKED_ENTRY", setup="s1", blocked_on="event_risk.calendar") for _ in range(4)]
        rows.append(O.record("BLOCKED_ENTRY", setup="s2", blocked_on="risk.position_size"))
        c = O.cluster(rows, min_size=3)
        self.assertEqual(len(c["clusters"]), 1)
        self.assertEqual(c["clusters"][0]["n"], 4)
        self.assertEqual(c["singletons"], 1)

    def test_the_threshold_is_stated_in_the_result(self):
        # What separates a pattern from an anecdote is the caller's choice, and the report must carry it.
        self.assertEqual(O.cluster([], min_size=7)["min_size"], 7)

    def test_wins_are_not_failure_patterns(self):
        rows = [O.record("WIN", setup="s1") for _ in range(5)]
        self.assertEqual(O.cluster(rows, min_size=2)["clusters"], [])


class OnlyAHumanDecides(unittest.TestCase):
    """§41: 'AI must NEVER silently rewrite the production Trading System.'"""

    def _walked(self):
        p = O.Proposal("widen the 15m ICT stop", hypothesis="MAE says the stop sits inside the noise",
                       author="learning-agent")
        for sid in O.IMPLEMENTED_STAGES:
            if sid not in ("hypothesis_generation", "human_decision"):
                p.stage(sid, evidence=f"docs/backtests/{sid}.md")
        return p

    def test_a_model_cannot_decide_its_own_proposal(self):
        p = self._walked()
        with self.assertRaises(O.HumanDecisionRequired) as cm:
            p.decide("APPROVED", actor="learning-agent")
        self.assertIn("never silently rewrite", str(cm.exception).lower())

    def test_no_actor_other_than_human_may_decide_even_to_reject(self):
        # Rejection is a decision too, and a model that can reject can also bury a finding.
        with self.assertRaises(O.HumanDecisionRequired):
            self._walked().decide("REJECTED", actor="claude")

    def test_no_proposal_can_be_approved_in_this_repo_today_and_the_refusal_says_why(self):
        # Not a defect: §44 (OOS exposure) and §45 (robustness) are unimplemented, and §41 puts both BEFORE
        # the human decision. The gap blocks adoption instead of being skipped, which is the whole point.
        with self.assertRaises(O.PipelineIncomplete) as cm:
            self._walked().decide("APPROVED", actor="human")
        self.assertIn("cannot yet perform", str(cm.exception))
        self.assertIn("oos_validation", str(cm.exception))

    def test_a_human_may_approve_once_a_real_oos_period_exists_and_every_stage_is_walked(self):
        # The same proposal with a genuinely untouched period carved out: approval then works. So the refusal
        # above is about the missing DATA, not about the human path being broken -- and carving a period out
        # is exactly what unblocks it.
        import research_ledger as RL
        RL.PERIODS["t-oos-approval"] = {"id": "t-oos-approval", "range": ["2026-01-01", "2026-06-30"],
                                        "state": RL.UNTOUCHED, "why": "carved out for this test"}
        try:
            p = self._walked()
            for sid in ("oos_validation", "robustness_sensitivity"):
                p.stage(sid, evidence="docs/backtests/oos.md")
            self.assertEqual(p.blocked_by(), {})
            rep = p.decide("APPROVED", actor="human", note="ok")
            self.assertEqual(rep["decision"], "APPROVED")
            self.assertEqual(rep["decided_by"], "human")
        finally:
            RL.PERIODS.pop("t-oos-approval", None)

    def test_approval_is_refused_while_a_stage_is_unwalked(self):
        p = O.Proposal("t", hypothesis="h", author="a")
        with self.assertRaises(O.PipelineIncomplete) as cm:
            p.decide("APPROVED", actor="human")
        self.assertIn("pipeline has not been walked", str(cm.exception))

    def test_a_stage_cannot_be_marked_complete_without_evidence(self):
        # A stage marked complete with nothing behind it is the pipeline being skipped politely.
        with self.assertRaises(ValueError):
            O.Proposal("t", hypothesis="h", author="a").stage("backtest", evidence="")

    def test_an_invented_stage_is_refused(self):
        with self.assertRaises(O.NotDeclared):
            O.Proposal("t", hypothesis="h", author="a").stage("vibes_check", evidence="x")

    def test_a_proposal_must_name_its_author(self):
        # §41 distinguishes what AI MAY do from what only a human may; an anonymous proposal erases that.
        with self.assertRaises(ValueError):
            O.Proposal("t", hypothesis="h", author="")

    def test_the_report_lists_what_is_missing_not_only_what_passed(self):
        rep = O.Proposal("t", hypothesis="h", author="a").report()
        self.assertTrue(rep["stages_missing"])
        self.assertTrue(rep["stages_not_possible_here"])

    def test_a_stage_this_repo_cannot_perform_blocks_approval_rather_than_being_skipped(self):
        # Since §45 landed, OOS validation is IMPLEMENTED (`scripts/validation.py oos()`) -- what still blocks
        # an approval is §44: no period in this repo is untouched, so there is nothing to validate ON. The
        # block therefore comes from the live ledger rather than from a registry note, which is what keeps it
        # from standing stale on the day a period is finally carved out.
        p = self._walked()
        self.assertIn("oos_validation", p.blocked_by())
        with self.assertRaises(O.PipelineIncomplete) as cm:
            p.decide("APPROVED", actor="human")
        self.assertIn("cannot yet perform", str(cm.exception))
        self.assertIn("§44", str(cm.exception))

    def test_a_human_may_still_reject_or_defer_through_the_gap(self):
        # The block is on ADOPTION. Rejecting a candidate needs no OOS run.
        for d in ("REJECTED", "DEFERRED"):
            p = O.Proposal("t", hypothesis="h", author="a")
            self.assertEqual(p.decide(d, actor="human")["decision"], d)


class NoSilentPathToProduction(unittest.TestCase):
    def test_this_module_cannot_write_the_trading_system_registry_or_the_pilot_selection(self):
        # The filenames appear in the docstring, saying there is deliberately no writer for them. What must
        # not exist is a WRITE -- json.dump, a "w" mode, a shutil copy.
        for forbidden in ("json.dump", "shutil", "os.replace", "os.rename"):
            self.assertNotIn(forbidden, SRC, forbidden)

    def test_the_only_writes_in_this_module_are_none(self):
        # Reads the repo, writes nothing. A learning module with a writer is one refactor away from applying
        # its own conclusions.
        self.assertNotIn('"w"', SRC)
        self.assertNotIn("'w'", SRC)

    def test_the_registry_states_the_prohibition_and_how_it_is_enforced(self):
        note = O._DATA["_ai_must_never"]
        self.assertIn("NEVER silently rewrite", note)
        self.assertIn("decide()", note)


if __name__ == "__main__":
    unittest.main(verbosity=2)
