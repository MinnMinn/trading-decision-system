"""Wyckoff structure rules a narrative cannot violate -- the two that were missing.

Found 2026-09-19 from a reader's comment on the BTC Bias chart ("chart Wyckoff này vẽ có vẻ hơi kỳ"). The
chart drew SOS 2026-09-03, ST 2026-09-04 and UA 2026-09-09 beside an SC of 2026-09-10 whose Phase A began that
day: three events from an EARLIER range rendered as one sequence, so the picture read SOS → ST → UA → SC →
Spring. Wyckoff does not run that way round -- the SC opens the range the ST retests and the SOS leaves
(knowledge/wyckoff/advance.md §2.7.1-§2.7.4) -- and two of them sat above the declared AR, which an ST cannot
do, since it retests the SC area below the AR by construction.

The hole was precise: `phase_at()` returns None for an event outside every phase band, and the vocabulary rule
was written `if L and ...`, so those events were the only ones checked by NOTHING. They still reached the
chart. Nine of them were live in data/live/narrative/scalping.json when this was written.
"""
import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mod():
    spec = importlib.util.spec_from_file_location("check_narrative",
                                                  os.path.join(ROOT, "scripts", "check-narrative.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CN = _mod()

PHASES = [{"from": "2026-09-10T12:00:00Z", "to": "2026-09-10T16:00:00Z", "label": "Pha A — stopping action"},
          {"from": "2026-09-10T16:00:00Z", "to": "2026-09-10T20:00:00Z", "label": "Pha B — test"},
          {"from": "2026-09-10T20:00:00Z", "to": None, "label": "Pha C — spring"}]


def _check(wy):
    out = []
    CN.phase_grammar("BTCUSDT", wy, out.append)
    return out


class AnEventOutsideEveryPhaseBandIsRefused(unittest.TestCase):

    def test_the_foreign_event_from_the_reported_chart_is_caught(self):
        wy = {"phases": PHASES,
              "events": [{"time": "2026-09-10T12:00:00Z", "label": "SC 76,676 · KL 2.20x"},
                         {"time": "2026-09-10T20:00:00Z", "label": "Spring 76,464 · KL 0.53x"},
                         {"time": "2026-09-03T12:00:00Z", "label": "SOS 81,348 · KL 2.77x"}]}
        msgs = _check(wy)
        self.assertTrue(any("outside every phase band" in m and "SOS" in m for m in msgs), msgs)

    def test_it_names_where_the_structure_actually_begins(self):
        wy = {"phases": PHASES, "events": [{"time": "2026-09-03T12:00:00Z", "label": "ST 79,429 · KL 3.05x"}]}
        msgs = _check(wy)
        self.assertTrue(any("2026-09-10T12:00:00Z" in m for m in msgs),
                        "the refusal must say where the first phase begins, or it cannot be acted on")

    def test_an_event_inside_a_band_is_not_flagged_for_this(self):
        wy = {"phases": PHASES, "events": [{"time": "2026-09-10T13:00:00Z", "label": "SC 76,676 · KL 2.20x"}]}
        self.assertFalse([m for m in _check(wy) if "outside every phase band" in m])

    def test_an_event_in_the_open_last_phase_is_not_flagged(self):
        """Phase C has `to: None` -- it is still running, so a later event is inside it, not outside."""
        wy = {"phases": PHASES,
              "events": [{"time": "2026-09-10T12:00:00Z", "label": "SC 76,676 · KL 2.20x"},
                         {"time": "2026-09-19T08:00:00Z", "label": "Spring 76,464 · KL 0.53x"}]}
        self.assertFalse([m for m in _check(wy) if "outside every phase band" in m])

    def test_a_read_with_no_phases_at_all_is_left_alone(self):
        """No phases declared means no band to be outside of; that is a different (already-covered) case."""
        wy = {"phases": [], "events": [{"time": "2026-09-03T12:00:00Z", "label": "SOS 81,348 · KL 2.77x"}]}
        self.assertFalse([m for m in _check(wy) if "outside every phase band" in m])


class TheRangeAndThePhasesMustBeOneStructure(unittest.TestCase):

    def test_a_range_predating_its_own_stopping_action_is_refused(self):
        wy = {"phases": PHASES, "events": [{"time": "2026-09-10T12:00:00Z", "label": "SC 76,676 · KL 2.20x"}],
              "trading_range": {"from": "2026-09-01T00:00:00Z", "high": 77959.2, "low": 76676.07}}
        self.assertTrue(any("BEFORE Phase A" in m for m in _check(wy)))

    def test_a_range_stamped_slightly_after_phase_a_is_NOT_refused(self):
        """Ordinary bookkeeping: the range is not drawable until the AR completes the SC/AR pair. Flagging it
        would be noise, and noisy checks get ignored -- which is how the real defect survived."""
        wy = {"phases": PHASES, "events": [{"time": "2026-09-10T12:00:00Z", "label": "SC 76,676 · KL 2.20x"}],
              "trading_range": {"from": "2026-09-10T12:45:00Z", "high": 77959.2, "low": 76676.07}}
        self.assertFalse([m for m in _check(wy) if "BEFORE Phase" in m])


class TheCheckRunsOnTheContextReadToo(unittest.TestCase):
    """The reported chart was the BIAS tier, which is fed by `context.wyckoff` -- so the check has to reach it,
    not only the working-timeframe read."""

    def test_check_narrative_applies_phase_grammar_to_the_context_wyckoff(self):
        src = open(os.path.join(ROOT, "scripts", "check-narrative.py"), encoding="utf-8").read()
        self.assertIn('phase_grammar(sym + " (context)", cw, bad)', src)


if __name__ == "__main__":
    unittest.main()
