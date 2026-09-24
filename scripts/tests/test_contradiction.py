"""CLAUDE.md §19 -- contradictions stay explicit, and the tolerance for them belongs to the configuration.

Most of §19 was already real, and these tests verify it rather than claim credit for it:
`htf_context.bias_of` returns **neutral** when two engaged methods disagree and keeps BOTH readings in the
basis (`bias.contradiction_two` plus each lane's own reason), which is precisely §19's "Do not silently
resolve contradictions" and "must remain explainable in the decision record".

One gap was real. §19: *"The active Trading System determines contradiction tolerance … acceptable
disagreement, blocking behaviour."* The only such rule in the repo lived inside STRICT's own registry note --
"also requires zero unresolved high-impact contradictions, **enforced in the DecisionAgent procedure, not
this table**" -- i.e. prose addressed to a model, with nothing checking it, and no statement at all for the
other three modes. `max_unresolved_high_impact` now declares it per mode and `confluence.tolerance()` reads it.

**SOLO = 0 is a deliberate tightening of the live configuration**, on the same reasoning that raised SOLO's
threshold to 85: one engaged dimension has no second lane to weigh an unresolved HIGH-impact contradiction
against, so there is nothing for tolerance to be tolerant of.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import confluence as C
import methods as M
import spec


def htf():
    s = importlib.util.spec_from_file_location("htf_context", os.path.join(ROOT, "scripts", "htf_context.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


ACC = {"structure": "tích lũy", "phase": "C", "trading_range": {"low": 1, "high": 2}}
# ICT-5 (docs/audits/2026-09-24-system-audit.md): htf_context.ict_bias reads `last_displaced_mss`, not the raw
# `last_mss` (which may be an undisplaced grab) -- kept on both here since this fixture represents a genuine,
# displaced MSS, not a grab (see scripts/tests/test_audit_round2_ict.py for the grab-vs-real-MSS distinction).
BEAR_MSS = {"last_mss": {"type": "bear", "level": 100}, "last_displaced_mss": {"type": "bear", "level": 100},
            "prev_candle": {}}


class DisagreementIsRaisedNotResolved(unittest.TestCase):
    """§19: 'Do not silently resolve contradictions.'"""

    def test_two_engaged_methods_disagreeing_returns_neutral(self):
        bias, _ = htf().bias_of(ACC, BEAR_MSS, methods=("wyckoff", "ict"))
        self.assertEqual(bias, "neutral", "one lane silently won the disagreement")

    def test_both_readings_survive_into_the_basis(self):
        """§19: 'Contradiction must remain explainable in the decision record.' A neutral with no reasons
        would be a resolution wearing a neutral's clothes."""
        _, basis = htf().bias_of(ACC, BEAR_MSS, methods=("wyckoff", "ict"))
        keys = [p[1] for p in basis]
        self.assertIn("bias.contradiction_two", keys)
        self.assertTrue(any("wy" in k for k in keys), f"the Wyckoff reading was dropped: {keys}")
        self.assertTrue(any("ict" in k for k in keys), f"the ICT reading was dropped: {keys}")

    def test_a_silent_lane_is_not_a_dissenting_one(self):
        """A method returning 'unknown' has no data; the other stands alone. Only a real reading dissents."""
        h = htf()
        bias, _ = h.bias_of(ACC, {"last_mss": None, "prev_candle": {}}, methods=("wyckoff", "ict"))
        self.assertEqual(bias, "long", "a silent ICT was treated as disagreement")


class ToleranceBelongsToTheConfiguration(unittest.TestCase):
    """§19: 'The active Trading System determines contradiction tolerance … blocking behaviour.'"""

    def test_every_mode_declares_a_tolerance(self):
        for mode in M.MODES:
            self.assertIsInstance(C.tolerance(mode), int, f"mode {mode} declares no contradiction tolerance")

    def test_strict_and_solo_tolerate_none(self):
        self.assertEqual(C.tolerance("STRICT"), 0)
        self.assertEqual(C.tolerance("SOLO"), 0)

    def test_a_record_that_trades_through_its_own_limit_is_refused(self):
        rec = {"dimensions": {"ict": {"eligible": True, "points": 22}}, "engaged_count": 1,
               "methodology_mode": "STRICT", "unresolved_high_impact_contradictions": 1}
        problems = [p for p in C.check(rec, instrument="BTCUSDT") if "contradiction" in p]
        self.assertTrue(problems)
        self.assertIn("tolerates at most 0", problems[0])

    def test_a_mode_that_allows_one_is_not_blocked_by_one(self):
        rec = {"dimensions": {"ict": {"eligible": True, "points": 22}}, "engaged_count": 1,
               "methodology_mode": "NORMAL", "unresolved_high_impact_contradictions": 1}
        self.assertEqual([p for p in C.check(rec, instrument="BTCUSDT") if "contradiction" in p], [])

    def test_the_live_configuration_now_tolerates_none(self):
        """Recorded because it is a real behaviour change, not an implementation detail."""
        self.assertEqual(C.tolerance(M.dispatch_plan("BTCUSDT")["mode"]), 0)

    def test_the_tolerance_is_read_from_the_registry_not_the_code(self):
        with open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8") as fh:
            modes = json.load(fh)["modes"]
        for mode in modes:
            self.assertIn("max_unresolved_high_impact", modes[mode])
        self.assertIn("M.MODES.get(mode)",
                      open(os.path.join(ROOT, "scripts", "confluence.py"), encoding="utf-8").read())


class TheAsymmetryWithScoringIsDeliberate(unittest.TestCase):
    """A lane may not add points it is not configured to add (§18), but disagreement it can see is still
    information. Suppressing that would be the silent resolution §19 forbids -- so the anti-cherry-picking
    rule stays, and this test exists so a later tidy-up does not "align" the two and lose it."""

    def test_contradictions_are_collected_from_every_available_dimension(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas",
                               "confluence-score.schema.json"), encoding="utf-8") as fh:
            desc = json.load(fh)["properties"]["contradictions"]["description"]
        self.assertIn("EVERY dimension whose data source is AVAILABLE", desc)
        self.assertIn("not only the engaged/counted dimensions", desc)

    def test_the_asymmetry_is_written_down_where_someone_would_remove_it(self):
        src = open(os.path.join(ROOT, "scripts", "confluence.py"), encoding="utf-8").read()
        self.assertIn("asymmetry with §18 and it is not an oversight", src)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_19_still_asks_for_all_of_this(self):
        body = spec.body(19)
        self.assertIn("Do not silently resolve contradictions", body)
        self.assertIn("contradiction tolerance", body)
        self.assertIn("blocking behavior", body)
        self.assertIn("explainable in the decision record", body)


if __name__ == "__main__":
    unittest.main()
