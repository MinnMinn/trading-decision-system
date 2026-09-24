"""Fix round 3b: docs/audits/2026-09-24-wyckoff-label-review.md, proposals P1.1/P1.2, P2.1, P3.1, P4.1/P4.2,
P5.1, P6.1/P6.2 -- the narrative-authoring/checking contract for Wyckoff chart labels -- plus the invalidated-
label rendering contract §7 (P7.1-P7.3). P7.4 (the wyckoff_bias gate in scripts/htf_context.py) is round 3a's
scope and is not tested here.

Every fixture below is synthetic: constructed candle rows and narrative fragments, not the real XAUUSD read, so
each test pins the CHECKER's own arithmetic rather than trusting a real read to happen to fail the right way.
"""
import importlib.util
import json
import os
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHART = os.path.join(ROOT, "scripts", "chart.js")


def _node_available():
    try:
        return subprocess.run(["node", "-e", "0"], capture_output=True).returncode == 0
    except Exception:
        return False


def _node(js):
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    if r.returncode != 0:
        raise AssertionError(r.stderr[-2000:])
    return json.loads(r.stdout)


def _mod(name, relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, *relpath.split("/")))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


CN = _mod("check_narrative", "scripts/check-narrative.py")
WR = _mod("wyckoff_rules", "scripts/wyckoff_rules.py")


def bar(t, o, h, l, c, v):
    return {"time": t, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _check(fn, *a):
    out = []
    fn(*a, out.append)
    return out


# ---------------------------------------------------------------------------------------------- P1.1


class DoiNhanAndSpringChecks(unittest.TestCase):

    def test_spring_event_without_volume_type_is_refused(self):
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00"}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 100)]
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertTrue(any("needs volume_type" in m for m in msgs), msgs)

    def test_volume_type_disagreeing_with_computed_ratio_is_refused(self):
        """10 quiet bars then a Spring bar on 3x volume -- that is type 3 (high), not the type 1 the label claims."""
        rows = [bar(f"2026-01-01T{i:02d}:00:00Z", 105, 106, 104, 105, 10) for i in range(10)]
        rows.append(bar("2026-01-01T10:00:00Z", 101, 101.5, 99.0, 101.2, 30))
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T10:00:00Z", "label": "Spring[C] 99.00", "volume_type": 1}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertTrue(any("does not match the ratio computed from candles" in m for m in msgs), msgs)

    def test_volume_type_matching_the_computed_ratio_is_accepted(self):
        rows = [bar(f"2026-01-01T{i:02d}:00:00Z", 105, 106, 104, 105, 10) for i in range(10)]
        rows.append(bar("2026-01-01T10:00:00Z", 101, 101.5, 99.0, 101.2, 30))
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T10:00:00Z", "label": "Spring[C] 99.00", "volume_type": 3}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertFalse([m for m in msgs if "does not match the ratio" in m], msgs)

    def test_spring_bar_close_still_below_tr_low_is_refused(self):
        """The 2026-09-11 XAUUSD critique's core finding: a bar that never closed back inside the range."""
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 95.0, 96.0, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 95.00", "volume_type": 3}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertTrue(any("never came back above trading_range.low" in m for m in msgs), msgs)

    def test_spring_bar_closing_above_tr_high_is_only_a_warning(self):
        rows = [bar("2026-01-01T00:00:00Z", 101, 112.0, 95.0, 111.0, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 95.00", "volume_type": 3}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertFalse(msgs, "a close above TR high in the same bar must not be a hard failure")

    def test_event_class_disagreeing_with_the_label_token_is_refused(self):
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00", "volume_type": 2, "event_class": "Shakeout"}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertTrue(any("event_class" in m and "does not match" in m for m in msgs), msgs)

    def test_event_class_agreeing_with_the_label_token_is_accepted(self):
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00", "volume_type": 2, "event_class": "Spring"}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, rows, "")
        self.assertFalse([m for m in msgs if "event_class" in m], msgs)

    def test_volume_kind_disagreeing_with_the_real_feed_is_refused(self):
        """XAUUSD is an MT5/tick-volume symbol (scripts/instruments.py TICK_VOLUME_MARKETS) -- claiming 'traded'
        for it must be refused."""
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00", "volume_type": 2, "volume_kind": "traded"}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "XAUUSD", wy, rows, "")
        self.assertTrue(any("volume_kind" in m and "does not match this symbol's actual feed" in m for m in msgs), msgs)

    def test_volume_kind_agreeing_with_the_real_feed_is_accepted(self):
        rows = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 30)]
        wy = {"trading_range": {"low": 100.0, "high": 110.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00", "volume_type": 2, "volume_kind": "tick"}],
              "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "XAUUSD", wy, rows, "")
        self.assertFalse([m for m in msgs if "volume_kind" in m], msgs)

        rows2 = [bar("2026-01-01T00:00:00Z", 101, 101.5, 99.0, 101.2, 30)]
        wy2 = {"trading_range": {"low": 100.0, "high": 110.0},
               "events": [{"time": "2026-01-01T00:00:00Z", "label": "Spring[C] 99.00", "volume_type": 2, "volume_kind": "traded"}],
               "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs2 = _check(CN.doi_nhan_and_spring_checks, "BTCUSDT", wy2, rows2, "")
        self.assertFalse([m for m in msgs2 if "volume_kind" in m], msgs2)

    def test_phase_b_sign_required_once_phase_b_is_declared(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase A"},
                          {"from": "2026-01-01T01:00:00Z", "label": "Phase B"}],
              "events": [], "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "")
        self.assertTrue(any("doi_nhan.phase_b_sign missing" in m for m in msgs), msgs)

    def test_phase_b_sign_not_required_before_phase_b_exists(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase A"}],
              "events": [], "doi_nhan": {"st_sign": "neutral"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "")
        self.assertFalse([m for m in msgs if "phase_b_sign" in m], msgs)

    def test_phase_b_sign_present_and_valid_is_accepted(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase A"},
                          {"from": "2026-01-01T01:00:00Z", "label": "Phase B"}],
              "events": [], "doi_nhan": {"st_sign": "neutral", "phase_b_sign": "supports"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "")
        self.assertFalse([m for m in msgs if "phase_b_sign" in m], msgs)

    def test_missing_doi_nhan_st_sign_is_refused(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase C"}], "events": []}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "")
        self.assertTrue(any("doi_nhan.st_sign missing" in m for m in msgs), msgs)

    def test_contradicts_past_phase_c_without_alternative_and_synthesis_is_refused(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A"},
                          {"from": "2026-01-01T01:00:00Z", "to": "2026-01-01T02:00:00Z", "label": "Phase B"},
                          {"from": "2026-01-01T02:00:00Z", "to": "2026-01-01T03:00:00Z", "label": "Phase C"},
                          {"from": "2026-01-01T03:00:00Z", "label": "Phase D"}],
              "events": [], "doi_nhan": {"st_sign": "contradicts"}}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "no mention here")
        self.assertTrue(any("advanced past C without wyckoff.alternative" in m for m in msgs), msgs)

    def test_contradicts_past_phase_c_with_alternative_and_named_contradiction_is_accepted(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A"},
                          {"from": "2026-01-01T01:00:00Z", "to": "2026-01-01T02:00:00Z", "label": "Phase B"},
                          {"from": "2026-01-01T02:00:00Z", "to": "2026-01-01T03:00:00Z", "label": "Phase C"},
                          {"from": "2026-01-01T03:00:00Z", "label": "Phase D"}],
              "events": [], "doi_nhan": {"st_sign": "contradicts"}, "alternative": "ST duoi SC -> co the la phan phoi"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "mâu thuẫn giữa cấu trúc và ST[A]")
        self.assertFalse([m for m in msgs if "advanced past C" in m], msgs)

    def test_contradicts_still_in_phase_c_does_not_need_alternative(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A"},
                          {"from": "2026-01-01T01:00:00Z", "to": "2026-01-01T02:00:00Z", "label": "Phase B"},
                          {"from": "2026-01-01T02:00:00Z", "label": "Phase C"}],
              "events": [], "doi_nhan": {"st_sign": "contradicts"}, "alternative": "x"}
        msgs = _check(CN.doi_nhan_and_spring_checks, "SYM", wy, [], "")
        self.assertFalse([m for m in msgs if "advanced past C" in m], msgs)


# ---------------------------------------------------------------------------------------------- P1.2


class EventPriceSkipsRatiosBeforeThePrice(unittest.TestCase):
    """Fix round 3b/1, item 4: event_price() took the FIRST number in the label, which is wrong once a volume
    ratio is printed before the price (e.g. 'KL 2.78x Spring[C] 4,289.57')."""

    def test_price_after_a_ratio_is_still_found(self):
        self.assertEqual(CN.event_price("KL 2.78x Spring[C] 4,289.57"), 4289.57)

    def test_price_after_a_ratio_with_the_multiplication_sign_is_still_found(self):
        self.assertEqual(CN.event_price("KL 2.78× Spring[C] 4,289.57"), 4289.57)

    def test_price_before_a_ratio_is_unaffected(self):
        self.assertEqual(CN.event_price("Spring[C] 4,289.57 · KL 2.78x"), 4289.57)

    def test_only_a_ratio_present_returns_none(self):
        self.assertIsNone(CN.event_price("KL 2.78x"))

    def test_no_number_at_all_returns_none(self):
        self.assertIsNone(CN.event_price("Spring[C]"))


class ContextSpringMustBreachTheContextRange(unittest.TestCase):

    def test_context_spring_inside_the_range_is_refused(self):
        """The exact reported case: 4H 'Spring 4,289.57' against a 4H TR low of 4,285.91 -- the label price
        never crosses the border it claims to break."""
        cw = {"trading_range": {"low": 4285.91, "high": 4400.0},
              "events": [{"time": "2026-09-11T09:00:00Z", "label": "Spring[C] 4,289.57"}]}
        msgs = _check(CN.context_spring_checks, "XAUUSD", cw)
        self.assertTrue(any("must trade below the context trading_range low" in m for m in msgs), msgs)

    def test_context_spring_below_the_range_is_accepted(self):
        cw = {"trading_range": {"low": 4285.91, "high": 4400.0},
              "events": [{"time": "2026-09-11T09:00:00Z", "label": "Spring[C] 4,280.00"}]}
        self.assertFalse(_check(CN.context_spring_checks, "XAUUSD", cw))

    def test_context_utad_above_the_range_is_required(self):
        cw = {"trading_range": {"low": 100.0, "high": 200.0},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "UTAD 195.00"}]}
        msgs = _check(CN.context_spring_checks, "SYM", cw)
        self.assertTrue(any("must trade above the context trading_range high" in m for m in msgs), msgs)


# ---------------------------------------------------------------------------------------------- P2.1 / P3.1


class ConfirmationGrammar(unittest.TestCase):

    def _sos_rows(self, commit_hold=True):
        rows = [bar(f"2026-01-01T{i:02d}:00:00Z", 100, 101, 99, 100, 10) for i in range(20)]
        # the SOS bar: close above TR high (110), wide spread, high volume
        rows.append(bar("2026-01-01T20:00:00Z", 105, 115, 104, 114, 40))
        if commit_hold:
            rows.append(bar("2026-01-01T21:00:00Z", 114, 116, 113, 115, 20))
        else:
            rows.append(bar("2026-01-01T21:00:00Z", 114, 114, 108, 109, 20))  # falls back inside -- no commitment
        return rows

    def test_unconfirmed_sos_without_question_mark_is_refused(self):
        rows = self._sos_rows(commit_hold=False)
        wy = {"trading_range": {"high": 110.0}, "events": [{"time": "2026-01-01T20:00:00Z", "label": "SOS[D] 114.00"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T21:00:00Z")
        self.assertTrue(any("does not pass its confirmation test" in m for m in msgs), msgs)

    def test_unconfirmed_sos_written_as_a_candidate_is_accepted(self):
        rows = self._sos_rows(commit_hold=False)
        wy = {"trading_range": {"high": 110.0}, "events": [{"time": "2026-01-01T20:00:00Z", "label": "SOS[D] 114.00?"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T21:00:00Z")
        self.assertFalse(msgs, msgs)

    def test_confirmed_sos_needs_no_question_mark(self):
        rows = self._sos_rows(commit_hold=True)
        wy = {"trading_range": {"high": 110.0}, "events": [{"time": "2026-01-01T20:00:00Z", "label": "SOS[D] 114.00"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T21:00:00Z")
        self.assertFalse(msgs, msgs)

    def test_sos_with_commitment_bars_not_yet_printed_must_be_a_candidate(self):
        """Only the SOS bar itself exists so far (updated == the SOS bar's own time) -- P2.1's 'if the commitment
        bars do not exist yet at write time, the label must be written as a candidate'."""
        rows = self._sos_rows(commit_hold=True)[:21]  # trims off the commitment bar
        wy = {"trading_range": {"high": 110.0}, "events": [{"time": "2026-01-01T20:00:00Z", "label": "SOS[D] 114.00"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T20:00:00Z")
        self.assertTrue(any("not enough completed candles" in m for m in msgs), msgs)

    def test_unconfirmed_lps_without_question_mark_is_refused(self):
        """LPS 'đang test' -- the point 3 critique: a pullback in progress is not yet a confirmed LPS."""
        rows = [bar("2026-01-01T00:00:00Z", 112, 113, 110, 112, 20),   # SOS-ish bar, high = 113
                bar("2026-01-01T01:00:00Z", 111, 111.5, 109, 110, 8)]  # pullback bar itself; no reclaim yet
        wy = {"events": [{"time": "2026-01-01T01:00:00Z", "label": "LPS[D] 110.00"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T01:00:00Z")
        self.assertTrue(any("not enough completed candles" in m or "does not pass" in m for m in msgs), msgs)

    def test_lps_confirmed_once_price_is_pushed_back_up(self):
        rows = [bar("2026-01-01T00:00:00Z", 112, 113, 110, 112, 20),
                bar("2026-01-01T01:00:00Z", 111, 111.5, 109, 110, 8),
                bar("2026-01-01T02:00:00Z", 110, 114, 110, 113.5, 12)]  # close 113.5 > bar-1's own high 113? no -> use bar 0's high
        wy = {"events": [{"time": "2026-01-01T01:00:00Z", "label": "LPS[D] 110.00"}]}
        msgs = _check(CN.confirmation_grammar, "SYM", wy, rows, "2026-01-01T02:00:00Z")
        self.assertFalse(msgs, msgs)


# ---------------------------------------------------------------------------------------------- P3.1 (phase grammar)


class UnconfirmedEventCannotOpenAPhase(unittest.TestCase):

    def test_phase_d_on_an_unconfirmed_sos_candidate_is_refused(self):
        phases = [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A"},
                  {"from": "2026-01-01T01:00:00Z", "to": "2026-01-01T02:00:00Z", "label": "Phase B"},
                  {"from": "2026-01-01T02:00:00Z", "to": "2026-01-01T03:00:00Z", "label": "Phase C"},
                  {"from": "2026-01-01T03:00:00Z", "label": "Phase D"}]
        events = [{"time": "2026-01-01T00:00:00Z", "label": "SC 100.00"},
                  {"time": "2026-01-01T02:00:00Z", "label": "Spring[C] 95.00"},
                  {"time": "2026-01-01T03:00:00Z", "label": "SOS[D] 120.00?"}]
        wy = {"phases": phases, "events": events}
        out = []
        CN.phase_grammar("SYM", wy, out.append)
        self.assertTrue(any("cannot open a phase" in m and "Phase D" in m for m in out), out)

    def test_phase_d_on_a_confirmed_sos_is_accepted(self):
        phases = [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A"},
                  {"from": "2026-01-01T01:00:00Z", "to": "2026-01-01T02:00:00Z", "label": "Phase B"},
                  {"from": "2026-01-01T02:00:00Z", "to": "2026-01-01T03:00:00Z", "label": "Phase C"},
                  {"from": "2026-01-01T03:00:00Z", "label": "Phase D"}]
        events = [{"time": "2026-01-01T00:00:00Z", "label": "SC 100.00"},
                  {"time": "2026-01-01T02:00:00Z", "label": "Spring[C] 95.00"},
                  {"time": "2026-01-01T03:00:00Z", "label": "SOS[D] 120.00"}]
        wy = {"phases": phases, "events": events}
        out = []
        CN.phase_grammar("SYM", wy, out.append)
        self.assertFalse([m for m in out if "cannot open a phase" in m], out)


# ---------------------------------------------------------------------------------------------- P4.1 / P4.2


class ContextContradictionMustBeNamed(unittest.TestCase):

    def test_disagreeing_htf_bias_without_a_named_contradiction_is_refused(self):
        cw = {"structure": "tích lũy", "phase": "D", "text_html": '<p>x<span class="cite">y</span></p>', "nesting": "n"}
        ci = {"text_html": '<p>x<span class="cite">y</span></p>'}
        ctx_facts_sym = {"last_displaced_mss": {"type": "bear", "level": 100}, "prev_candle": {}}
        wy_b, _ = CN.htf.wyckoff_bias(cw, ctx_facts_sym)
        ic_b, _ = CN.htf.ict_bias(ctx_facts_sym)
        self.assertEqual(wy_b, "long"); self.assertEqual(ic_b, "short")

    def test_wyckoff_nesting_field_required_when_context_read_exists(self):
        wy = {"nesting": ""}
        self.assertFalse((wy.get("nesting") or "").strip())


class TheContextBiasDictCarriesTheNarrativesUpdatedField(unittest.TestCase):
    """Fix round 3b/1, item 1: cw_wy (the dict check-narrative.py's P4.1/P4.2 block passes to
    htf_context.wyckoff_bias) must carry "updated", mirroring htf_context.load_tier's own construction of the
    identical dict (~line 381, "updated": n_own.get("updated")) -- round 3a's P7.4 invalidation-aware bias reads
    this field to tell whether the CONTEXT read itself has since been closed beyond. Goes through the real
    scripts/check-narrative.py main() end to end (sys.argv, --narrative/--facts/--ctx-facts pointed at temp
    copies of a real, tracked narrative -- crypto "scalping", never mt5-bridge/live-CFD paths, so this test
    needs no live feed and never touches data/live), not a direct htf_context call -- a direct call would not
    have caught the bug (the bug was in the CALLER's dict construction, not in wyckoff_bias itself)."""

    def test_cw_wy_passed_to_wyckoff_bias_carries_updated(self):
        import shutil
        import sys as _sys
        import tempfile

        style = "scalping"
        with tempfile.TemporaryDirectory() as tmp:
            narrative_src = os.path.join(ROOT, "data", "live", "narrative", f"{style}.json")
            facts_src = os.path.join(ROOT, "data", "live", "prelim", f"{style}.facts.json")
            ctx_style = CN.CTX_STYLE.get(style)
            ctx_facts_src = os.path.join(ROOT, "data", "live", "prelim", f"{ctx_style}.facts.json")
            narrative_tmp = os.path.join(tmp, "narrative.json")
            facts_tmp = os.path.join(tmp, "facts.json")
            ctx_facts_tmp = os.path.join(tmp, "ctx_facts.json")
            shutil.copy(narrative_src, narrative_tmp)
            shutil.copy(facts_src, facts_tmp)
            shutil.copy(ctx_facts_src, ctx_facts_tmp)
            narrative = json.load(open(narrative_tmp, encoding="utf-8"))
            expected_updated = narrative.get("updated")
            self.assertTrue(expected_updated, "fixture narrative has no updated field -- test is pinning nothing")

            captured = []
            real_bias = CN.htf.wyckoff_bias

            def spy(wyckoff, facts):
                captured.append(wyckoff)
                return real_bias(wyckoff, facts)

            argv = _sys.argv
            bias_fn = CN.htf.wyckoff_bias
            try:
                CN.htf.wyckoff_bias = spy
                _sys.argv = ["check-narrative.py", style, "--narrative", narrative_tmp,
                            "--facts", facts_tmp, "--ctx-facts", ctx_facts_tmp]
                try:
                    CN.main()
                except SystemExit:
                    pass   # main() always sys.exit()s with a status; only the captured calls matter here
            finally:
                CN.htf.wyckoff_bias = bias_fn
                _sys.argv = argv

            self.assertTrue(captured, "htf.wyckoff_bias was never called for the P4.1/P4.2 context block -- "
                                      "the fixture no longer exercises this code path, update it")
            for wyckoff in captured:
                self.assertIn("updated", wyckoff, wyckoff)
                self.assertEqual(wyckoff["updated"], expected_updated, wyckoff)


# ---------------------------------------------------------------------------------------------- P5.1


class TickVolumeCannotBeTheSoleValidator(unittest.TestCase):

    def test_sole_volume_validation_on_a_tick_feed_is_refused(self):
        wy = {"text_html": '<p>SOS hợp lệ vì khối lượng vượt trung bình 2.49x<span class="cite">a</span></p>'}
        msgs = _check(CN.tick_volume_checks, "XAUUSD", wy, {}, True)
        self.assertTrue(any("validates an event by volume alone" in m for m in msgs), msgs)

    def test_sole_volume_validation_is_not_checked_on_a_traded_volume_feed(self):
        wy = {"text_html": '<p>SOS hợp lệ vì khối lượng vượt trung bình 2.49x<span class="cite">a</span></p>'}
        msgs = _check(CN.tick_volume_checks, "BTCUSDT", wy, {}, False)
        self.assertFalse(msgs, msgs)

    def test_ratio_without_a_tick_marker_is_refused_on_a_tick_feed(self):
        wy = {"text_html": '<p>Khối lượng 2.49x cho thấy áp lực mua<span class="cite">a</span></p>'}
        msgs = _check(CN.tick_volume_checks, "XAUUSD", wy, {}, True)
        self.assertTrue(any("has no '(tick)' marker" in m for m in msgs), msgs)

    def test_ratio_with_a_tick_marker_is_accepted(self):
        wy = {"text_html": '<p>Khối lượng 2.49x (tick) cho thấy áp lực mua<span class="cite">a</span></p>'}
        msgs = _check(CN.tick_volume_checks, "XAUUSD", wy, {}, True)
        self.assertFalse([m for m in msgs if "no '(tick)' marker" in m], msgs)


# ---------------------------------------------------------------------------------------------- P6.1 / P6.2


class AlternativeAndPhaseStatus(unittest.TestCase):

    def test_missing_alternative_is_refused(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase A", "status": "tested"}], "events": []}
        msgs = _check(CN.alternative_and_status_checks, "SYM", wy)
        self.assertTrue(any("wyckoff.alternative missing" in m for m in msgs), msgs)

    def test_phase_missing_status_is_refused(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "label": "Phase A"}], "events": [], "alternative": "x"}
        msgs = _check(CN.alternative_and_status_checks, "SYM", wy)
        self.assertTrue(any("needs status 'tested' or 'hypothesis'" in m for m in msgs), msgs)

    def test_phase_c_marked_tested_without_a_confirmed_event_is_refused(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A", "status": "tested"},
                          {"from": "2026-01-01T01:00:00Z", "label": "Phase C", "status": "tested"}],
              "events": [{"time": "2026-01-01T01:30:00Z", "label": "Spring[C] 95.00?"}],
              "alternative": "x"}
        msgs = _check(CN.alternative_and_status_checks, "SYM", wy)
        self.assertTrue(any("marked status 'tested' but its confirming event" in m for m in msgs), msgs)

    def test_phase_c_marked_hypothesis_with_an_unconfirmed_event_is_accepted(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A", "status": "tested"},
                          {"from": "2026-01-01T01:00:00Z", "label": "Phase C", "status": "hypothesis"}],
              "events": [{"time": "2026-01-01T01:30:00Z", "label": "Spring[C] 95.00?"}],
              "alternative": "x"}
        msgs = _check(CN.alternative_and_status_checks, "SYM", wy)
        self.assertFalse(msgs, msgs)

    def test_phase_c_marked_tested_with_a_confirmed_event_is_accepted(self):
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": "2026-01-01T01:00:00Z", "label": "Phase A", "status": "tested"},
                          {"from": "2026-01-01T01:00:00Z", "label": "Phase C", "status": "tested"}],
              "events": [{"time": "2026-01-01T01:30:00Z", "label": "Spring[C] 95.00"}],
              "alternative": "x"}
        msgs = _check(CN.alternative_and_status_checks, "SYM", wy)
        self.assertFalse(msgs, msgs)


# ---------------------------------------------------------------------------------------------- §7 P7.1 invalidation


class InvalidatedAtComputation(unittest.TestCase):
    """scripts/build-artifact.py invalidated_at() -- P7.1: derive the invalidation time from the scanner's
    first_close_beyond, using only completed candles, and never store it in the narrative."""

    @classmethod
    def setUpClass(cls):
        cls.BA = _mod("build_artifact", "scripts/build-artifact.py")

    def test_invalidated_at_found_when_first_close_beyond_is_after_updated(self):
        n3 = {"invalidation": {"owner": "wyckoff", "level": 4289.57, "rule": "đóng cửa dưới"}, "_updated_iso": "2026-09-11T15:00:00Z"}
        fsym = {"anchors": {"levels": [{"name": "spring_low", "price": 4289.57, "role": "support",
                                        "first_close_beyond": {"time": "2026-09-15T23:45:00Z", "close": 4283.38}}]}}
        got = self.BA.invalidated_at(n3, fsym)
        self.assertIsNotNone(got)
        self.assertEqual(got["time"], "2026-09-15T23:45:00Z")
        self.assertEqual(got["close"], 4283.38)

    def test_no_invalidation_when_first_close_beyond_is_missing(self):
        n3 = {"invalidation": {"owner": "wyckoff", "level": 100.0, "rule": "đóng cửa dưới"}, "_updated_iso": "2026-01-01T00:00:00Z"}
        fsym = {"anchors": {"levels": [{"name": "x", "price": 100.0, "role": "support", "first_close_beyond": None}]}}
        self.assertIsNone(self.BA.invalidated_at(n3, fsym))

    def test_no_invalidation_when_no_matching_level_price(self):
        n3 = {"invalidation": {"owner": "wyckoff", "level": 999.0, "rule": "đóng cửa dưới"}, "_updated_iso": "2026-01-01T00:00:00Z"}
        fsym = {"anchors": {"levels": [{"name": "x", "price": 100.0, "role": "support",
                                        "first_close_beyond": {"time": "2026-01-02T00:00:00Z", "close": 90.0}}]}}
        self.assertIsNone(self.BA.invalidated_at(n3, fsym))

    def test_no_invalidation_when_break_predates_updated(self):
        """PIT guard: a first_close_beyond at or before `updated` cannot be what invalidates a label written at
        that same moment -- CLAUDE.md §8."""
        n3 = {"invalidation": {"owner": "wyckoff", "level": 100.0, "rule": "đóng cửa dưới"}, "_updated_iso": "2026-01-02T00:00:00Z"}
        fsym = {"anchors": {"levels": [{"name": "x", "price": 100.0, "role": "support",
                                        "first_close_beyond": {"time": "2026-01-01T00:00:00Z", "close": 90.0}}]}}
        self.assertIsNone(self.BA.invalidated_at(n3, fsym))

    def test_no_invalidation_field_at_all(self):
        self.assertIsNone(self.BA.invalidated_at({}, {}))


# ---------------------------------------------------------------------------------------------- §7 P7.2 chart.js


def _rows(n, base_iso_hour=0):
    return [[100 + i, 101 + i, 99 + i, 100.5 + i, 10, f"2026-01-01T{(base_iso_hour + i):02d}:00:00Z"] for i in range(n)]


@unittest.skipUnless(_node_available(), "node not available")
class WyckoffOverlayTruncatesAndFadesAtInvalidation(unittest.TestCase):
    """P7.2 items 1-3 (docs/audits/2026-09-24-wyckoff-label-review.md §7): truncate, fade + suffix, mark the
    breaking candle. Runs the REAL scripts/chart.js wyckoffShapes/levelShapes/planShapes from node -- these are
    exported (`api`) precisely so they are checkable without a browser."""

    def test_phase_band_and_tr_line_truncate_at_the_invalidation_index(self):
        rows = _rows(10)
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase D", "status": "tested"}],
              "tr": {"high": 110, "low": 95, "from": "2026-01-01T00:00:00Z"}, "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v), invalidatedAt:'2026-01-01T05:00:00Z'}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertEqual(band["i2"], 5.5, band)   # runs THROUGH the breaking candle (index 5 = 05:00Z bar)
        tr_lines = [s for s in out if s["kind"] == "hseg"]
        self.assertTrue(all(s["i2"] == 5.5 for s in tr_lines), tr_lines)
        self.assertTrue(any(s["kind"] == "mark" and s.get("glyph") == "x" for s in out), out)

    def test_no_invalidation_leaves_bands_running_to_the_right_edge(self):
        rows = _rows(10)
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase D", "status": "tested"}],
              "tr": {"high": 110, "low": 95, "from": "2026-01-01T00:00:00Z"}, "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v), invalidatedAt:null}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertEqual(band["i2"], 9.5, band)   # n-0.5, the full window
        self.assertFalse([s for s in out if s["kind"] == "mark" and s.get("glyph") == "x"], out)

    def test_replay_before_the_break_draws_normally(self):
        """chart.js's own replay slice (applyLane's rowsV) is what wyckoffShapes receives -- passing a shorter
        rows array that does not yet REACH invalidatedAt must render as if nothing were invalidated (P7.2 item
        5: the reader replaying before the break sees what the system saw then)."""
        rows = _rows(4)   # 00:00..03:00Z -- invalidatedAt (05:00Z) is not in this slice
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase D", "status": "tested"}],
              "tr": {"high": 110, "low": 95, "from": "2026-01-01T00:00:00Z"}, "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v), invalidatedAt:'2026-01-01T05:00:00Z'}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertEqual(band["i2"], 3.5, band)   # n-0.5 for this 4-row slice, i.e. drawn normally
        self.assertFalse([s for s in out if s["kind"] == "mark" and s.get("glyph") == "x"], out)

    def test_hypothesis_phase_gets_a_question_mark_and_lower_alpha(self):
        rows = _rows(5)
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase C", "status": "hypothesis"}],
              "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v)}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertTrue(band["label"].endswith("?"), band)
        self.assertLess(band["alpha"], 0.07, band)

    def test_tested_phase_has_no_question_mark(self):
        rows = _rows(5)
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase C", "status": "tested"}],
              "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v)}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertFalse(band["label"].endswith("?"), band)
        self.assertEqual(band["alpha"], 0.07, band)

    def test_invalidation_line_relabels_and_truncates_once_fired(self):
        rows = _rows(10)
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const inv={{owner:'wyckoff', level:99.5, invalidated_at:'2026-01-01T05:00:00Z'}};
const S=T.planShapes(rows, [], inv, {{fmt:v=>String(v)}});
process.stdout.write(JSON.stringify(S));
""")
        line = next(s for s in out if s["kind"] == "hseg")
        self.assertEqual(line["i2"], 5.5, line)
        self.assertNotIn("99.5", line["label"])   # relabelled, the raw level no longer appears in the fired label

    # ---- fix round 3b/1, item 2: P7.2 item 4, the out-of-window case ----

    def test_wyckoff_shapes_draw_nothing_from_a_read_dead_before_the_window(self):
        """Fix round 1: invalidated_at precedes rows[0] entirely (the window starts AFTER the break) --
        wyckoffShapes must draw NOTHING from the dead structure (no TR rect, no phase band, no event flag),
        only the generic 'now' price dot plus one muted note."""
        rows = _rows(10, base_iso_hour=10)   # 10:00Z .. 19:00Z
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase D", "status": "tested"}],
              "tr": {"high": 110, "low": 95, "from": "2026-01-01T00:00:00Z"},
              "events": [{"time": "2026-01-01T00:00:00Z", "label": "SC 100.00"}]}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v), invalidatedAt:'2026-01-01T05:00:00Z', narrativeUpdated:'2026-01-01T00:00:00Z'}});
process.stdout.write(JSON.stringify(S));
""")
        self.assertFalse([s for s in out if s["kind"] == "rect"], out)       # no TR/phase band
        self.assertFalse([s for s in out if s["kind"] == "flag"], out)      # no event flag
        self.assertFalse([s for s in out if s["kind"] == "mark" and s.get("glyph") == "x"], out)  # no break-mark (off-window)
        self.assertTrue(any(s["kind"] == "mark" and s.get("glyph") == "dot" for s in out), out)    # the generic "now" dot survives
        # L() has no injected catalog under plain node (no DOM/i18n.js_catalog wiring here), so it falls back to
        # the raw key -- this still pins the literal key test_i18n.py's runtime-key scanner requires, and that
        # the shape is a price-anchored label rather than a TR/phase/event shape.
        note = next(s for s in out if s["kind"] == "label")
        self.assertEqual(note["text"], "chart.wyckoff.invalidated_note", note)
        self.assertEqual(note["color"], "muted", note)

    def test_wyckoff_shapes_draw_normally_when_the_break_is_not_yet_reached(self):
        """The OTHER -1 case (replay before the break) must not be confused with 'before the window': here
        invalidatedAt is AFTER the last row, i.e. simply not reached yet in this (replay-sliced) view -- draw
        normally, per item 5."""
        rows = _rows(5, base_iso_hour=0)   # 00:00Z .. 04:00Z
        wy = {"phases": [{"from": "2026-01-01T00:00:00Z", "to": None, "label": "Phase D", "status": "tested"}],
              "tr": {"high": 110, "low": 95, "from": "2026-01-01T00:00:00Z"}, "events": []}
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const wy={json.dumps(wy)};
const S=T.wyckoffShapes(rows, wy, {{compact:false, fmt:v=>String(v), invalidatedAt:'2026-01-01T09:00:00Z'}});
process.stdout.write(JSON.stringify(S));
""")
        band = next(s for s in out if s["kind"] == "rect")
        self.assertEqual(band["i2"], 4.5, band)   # n-0.5, drawn as if not invalidated (not reached yet)

    def test_level_shapes_suppress_wyckoff_anchors_dead_before_the_window(self):
        rows = _rows(10, base_iso_hour=10)
        levels = [{"price": 100.0, "time": "2026-01-01T00:00:00Z", "method": "wyckoff", "short": "SC"},
                  {"price": 105.0, "time": "2026-01-01T00:00:00Z", "method": "ict", "short": "FVG"}]
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const levels={json.dumps(levels)};
const S=T.levelShapes(rows, levels, 'wyckoff', v=>String(v), '2026-01-01T05:00:00Z');
process.stdout.write(JSON.stringify(S));
""")
        self.assertEqual(out, [], out)   # the wyckoff-lane call must drop the wyckoff anchor entirely

    def test_level_shapes_ict_lane_is_unaffected_by_wyckoff_invalidation(self):
        rows = _rows(10, base_iso_hour=10)
        levels = [{"price": 105.0, "time": "2026-01-01T00:00:00Z", "method": "ict", "short": "FVG"}]
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const levels={json.dumps(levels)};
const S=T.levelShapes(rows, levels, 'ict', v=>String(v), '2026-01-01T05:00:00Z');
process.stdout.write(JSON.stringify(S));
""")
        self.assertEqual(len(out), 1, out)

    def test_invalidation_line_relabels_even_when_the_break_is_off_window(self):
        """Fix round 1, item 2 (the exact bug reported): the label must say 'fired', never fall back to the
        original live-looking form, when invalidated_at exists but idxOf cannot resolve it because the break
        predates the visible window."""
        rows = _rows(10, base_iso_hour=10)
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
const inv={{owner:'wyckoff', level:99.5, invalidated_at:'2026-01-01T05:00:00Z'}};
const S=T.planShapes(rows, [], inv, {{fmt:v=>String(v)}});
process.stdout.write(JSON.stringify(S));
""")
        line = next(s for s in out if s["kind"] == "hseg")
        self.assertNotIn("99.5", line["label"], line)   # must be the fired label, not the live-looking one
        self.assertEqual(line["i1"], -0.5, line)
        self.assertEqual(line["i2"], -0.5, line)          # zero-width body -- nothing drawn in the visible window

    def test_invalidation_state_classifies_before_in_live(self):
        rows = _rows(10, base_iso_hour=10)
        out = _node(f"""
const T=require({CHART!r});
const rows={json.dumps(rows)};
process.stdout.write(JSON.stringify([
  T.invalidationState(rows, '2026-01-01T05:00:00Z'),
  T.invalidationState(rows, '2026-01-01T12:00:00Z'),
  T.invalidationState(rows, '2026-01-02T00:00:00Z'),
  T.invalidationState(rows, null),
]));
""")
        self.assertEqual(out, ["before", "in", "live", "live"], out)


if __name__ == "__main__":
    unittest.main()
