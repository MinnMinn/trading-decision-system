"""CLAUDE.md §15 -- the active trading selection is not a global analysis filter, all the way to the page.

The §15 work in `methods.dispatch_plan` established the DISTINCTION (`engaged` vs `analysed`). This file covers
the half that makes the distinction visible: the authoring brief asks for every live-sourced methodology, the
validator accepts exactly that set, and the page shows the analysed-but-not-traded lane -- marked as not
counting toward confluence, per §18 and §50.

The defect this closes, stated plainly: selecting the ICT preset stopped Wyckoff from being READ, not just from
being traded. The brief demanded only `m-ict`, `check-model-prose.py` rejected an `m-wyckoff` block if one was
written anyway, and the page footer said "Wyckoff: off in /automation" -- a claim about the system's own
configuration that the analysis scope had already made false.

The interesting boundary is what did NOT move. `bias_of` still reads the engaged set only; the ladder -- the
grid that produces the verdict -- still shows engaged lanes only. §15 widens ANALYSIS; §18 keeps CONFLUENCE
narrow. A test that let the wider set reach the bias would be testing the opposite of the spec.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import spec


def load(name, mod):
    s = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


HTF = load("htf_context.py", "htf_context")
SRC = lambda n: open(os.path.join(ROOT, "scripts", n), encoding="utf-8").read()


class TheScopeHasOneImplementation(unittest.TestCase):
    """`analysed_dimensions` is the single source; `dispatch_plan` must agree with it, or a decision record and
    a page can disagree about what was analysed."""

    def test_dispatch_plan_and_the_market_level_reader_agree(self):
        plan = M.dispatch_plan("BTCUSDT")
        analysed, skipped, scope = M.analysed_dimensions("crypto")
        self.assertEqual(plan["analysed"], analysed)
        self.assertEqual(plan["analysis_skipped"], skipped)
        self.assertEqual(plan["analysis_scope"], scope)

    def test_the_reason_a_dimension_is_not_analysed_is_preserved(self):
        """§6: an unavailable capability must expose the state AND the reason."""
        _, skipped, _ = M.analysed_dimensions("crypto")
        self.assertIn("footprint", skipped)
        self.assertIn("coinglass", skipped["footprint"])

    def test_a_missing_config_analyses_everything_rather_than_nothing(self):
        analysed, _, scope = M.analysed_dimensions("crypto", config_path="/nonexistent/automation.json")
        self.assertEqual(scope, M.DEFAULT_ANALYSIS_SCOPE)
        self.assertIn("wyckoff", analysed)


class TheAuthoringPathAsksForEveryAnalysedMethod(unittest.TestCase):
    def test_analysed_methods_is_a_superset_of_engaged_under_the_default_scope(self):
        for style in ("scalping", "cfd-scalping"):
            eng, ana = HTF.engaged_methods(style), HTF.analysed_methods(style)
            self.assertTrue(set(eng) <= set(ana),
                            f"{style}: a TRADED method is not being analysed -- {eng} vs {ana}")

    def test_the_live_configuration_analyses_a_method_it_does_not_trade(self):
        """The concrete case: the preset is ict (SOLO), and Wyckoff reads the same candle file."""
        self.assertEqual(HTF.engaged_methods("scalping"), ("ict",))
        self.assertIn("wyckoff", HTF.analysed_methods("scalping"))

    def test_the_brief_demands_the_analysed_set_not_the_engaged_one(self):
        src = SRC("local-eval-brief.py")
        self.assertIn("_analysed = _htf.analysed_methods(a.style)", src)
        self.assertIn('" + ".join(f"m-{m}" for m in _analysed', src,
                      "the required-blocks line still reads the engaged set")

    def test_the_validator_demands_the_same_set_as_the_brief(self):
        """If these two disagree the brief asks for a block the checker rejects, which is how a model gets
        stuck in a fix loop it cannot win."""
        self.assertIn("htf.analysed_methods(style)", SRC("check-model-prose.py"))

    def test_a_dimension_with_no_live_source_is_still_not_demanded(self):
        """What the 2026-09-13 audit got right is preserved: live-sourcing gates the demand, so nobody is
        asked to write footprint prose from a fixture (§6)."""
        self.assertNotIn("footprint", HTF.analysed_methods("scalping"))
        self.assertNotIn("heatmap", HTF.analysed_methods("scalping"))


class TheWiderReadNeverReachesTheDecision(unittest.TestCase):
    """§18: confluence counts only explicitly configured methodologies. §15 widens analysis, not eligibility."""

    def test_the_ladder_passes_engaged_to_the_bias_and_analysed_to_the_prose(self):
        src = SRC("htf_context.py")
        self.assertIn("load_tier(style, name, sym, methods=methods)", src,
                      "the bias must still be computed from the ENGAGED set")
        self.assertIn("reading=reading", src)

    def test_reading_defaults_to_methods_so_unplumbed_callers_are_unchanged(self):
        ctx = {"tf": "4h", "style": "swing", "pct": 0.5, "lo": 1.0, "hi": 2.0, "eq": 1.5, "last": 1.5,
               "bias": "long", "basis": [], "anchors": [], "wyckoff": None}
        self.assertEqual(HTF.brief_lines(ctx, str, ("ict",)),
                         HTF.brief_lines(ctx, str, ("ict",), reading=("ict",)))

    def test_the_bias_line_names_which_methods_it_rests_on(self):
        """Handing the model Wyckoff material above an ICT-only bias, unlabelled, invites it to argue the
        direction from a lane that cannot vote."""
        ctx = {"tf": "4h", "style": "swing", "pct": 0.5, "lo": 1.0, "hi": 2.0, "eq": 1.5, "last": 1.5,
               "bias": "long", "basis": [], "anchors": [], "wyckoff": None}
        line = [x for x in HTF.brief_lines(ctx, str, ("ict",), reading=("wyckoff", "ict")) if "BIAS" in x][0]
        self.assertIn("chỉ từ: ict", line)
        self.assertIn("wyckoff", line)
        self.assertIn("không vào bias", line)

    def test_an_engaged_only_read_does_not_grow_the_disclaimer(self):
        ctx = {"tf": "4h", "style": "swing", "pct": 0.5, "lo": 1.0, "hi": 2.0, "eq": 1.5, "last": 1.5,
               "bias": "long", "basis": [], "anchors": [], "wyckoff": None}
        line = [x for x in HTF.brief_lines(ctx, str, ("wyckoff", "ict")) if "BIAS" in x][0]
        self.assertNotIn("không vào bias", line)


class ADisengagedLaneKeepsItsVocabularyWhenItIsAnalysed(unittest.TestCase):
    """Anchors carry a method's NAME. Naming was tied to the engaged set, so an analysed-but-not-traded lane
    got its own levels back as bare prices -- and then the model was asked to write about them."""

    CTX = {"tf": "4h", "style": "swing", "pct": 0.5, "lo": 1.0, "hi": 2.0, "eq": 1.5, "last": 1.5,
           "bias": "long", "basis": [],
           "anchors": [{"method": "wyckoff", "short": "SC", "label": "SC", "price": 1.1,
                        "ref_vs": "above", "dist_pct": 1.0}],
           "wyckoff": {"updated": "x", "structure": "tích lũy", "phase": "C"}}

    def test_an_analysed_lane_anchor_keeps_its_name(self):
        out = "\n".join(HTF.brief_lines(self.CTX, str, ("ict",), reading=("wyckoff", "ict")))
        self.assertIn("Mốc SC", out)

    def test_a_lane_outside_the_analysis_scope_still_loses_its_name(self):
        out = "\n".join(HTF.brief_lines(self.CTX, str, ("ict",), reading=("ict",)))
        self.assertNotIn("Mốc SC", out)
        self.assertIn("không tên", out)

    def test_the_wyckoff_read_is_printed_when_wyckoff_is_analysed(self):
        out = "\n".join(HTF.brief_lines(self.CTX, str, ("ict",), reading=("wyckoff", "ict")))
        self.assertIn("Đọc Wyckoff", out)


class ThePageShowsTheAnalysisAndSaysItDoesNotCount(unittest.TestCase):
    def test_the_matrix_columns_follow_the_analysed_set(self):
        src = SRC("build-artifact.py")
        self.assertIn('dims.get(c, {}).get("analysed")', src)

    def test_the_ladder_columns_stay_engaged_only(self):
        """The ladder is the decision grid. §50: do not visually imply that all displayed analysis
        contributes to trading confluence."""
        src = SRC("build-artifact.py")
        ladder = src[src.index("def ladder("):]
        head = ladder[:ladder.index("def ", 10)] if "def " in ladder[10:] else ladder
        self.assertIn('dims.get(m, {}).get("engaged")', head)
        self.assertNotIn('dims.get(m, {}).get("analysed")', head.split("cols =")[1].split("\n")[0])

    def test_an_optional_lane_is_marked_in_the_header(self):
        src = SRC("build-artifact.py")
        self.assertIn("optional-lane", src)
        self.assertIn("matrix.head.optional", src)

    def test_no_lane_claims_to_be_off_when_the_analysis_scope_keeps_it_on(self):
        """The false claim this closes. Three states wore one sentence: not traded + read, not traded +
        nothing written yet, and genuinely out of scope."""
        src = SRC("build-artifact.py")
        self.assertIn("dims.reason.analysis_only", src)
        self.assertIn("dims.reason.analysis_pending", src)

    def test_both_new_reasons_exist_in_every_locale(self):
        with open(os.path.join(ROOT, "docs", "architecture", "i18n.json"), encoding="utf-8") as fh:
            msgs = json.load(fh)["messages"]
        for key in ("dims.reason.analysis_only", "dims.reason.analysis_pending", "matrix.head.optional"):
            self.assertIn(key, msgs)
            for loc in ("en", "vi"):
                self.assertTrue(msgs[key].get(loc), f"{key} has no {loc} text")


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_15_still_says_analysis_is_not_filtered_by_the_trading_selection(self):
        body = spec.body(15)
        self.assertIn("NOT a global analysis filter", body)
        self.assertIn("Displayed analysis != trading confluence", body)


if __name__ == "__main__":
    unittest.main()


class TheStatusChipSaysWhoSaidIt(unittest.TestCase):
    """CLAUDE.md §20 and §50, and the question that exposed both (user, 2026-09-19: "why are only BTC, ETH and
    SOL watching long -- are the others displaying correctly?").

    They were not. The chip read `l2.verdict or l1.verdict or "—"`, and l1's verdict is always absent because
    the scanner writes `stance`, never `verdict`. So the scanner's reading -- which exists for EVERY
    instrument -- was dropped and six of nine symbols showed an em-dash. An em-dash reads as "nothing is
    known"; the truth was "the scanner looked, the answer is WAIT, and no local read exists yet". §20 is
    explicit that a known state must not be shown as an unknown one, and the safe direction of that mistake is
    still the mistake.

    The source travels with the value because they are not the same authority: a model verdict is a
    judgement, a scanner stance is a fixed rule. One pill carrying both without saying which is exactly the
    confusion §50 warns about, so it is rendered beside the chip rather than hidden.
    """

    @classmethod
    def setUpClass(cls):
        cls.BA = _ba() if "_ba" in globals() else None

    def _mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("build_artifact",
                                                      os.path.join(ROOT, "scripts", "build-artifact.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_a_model_verdict_wins_and_is_attributed(self):
        BA = self._mod()
        v, src = BA.verdict_of({"stance": "CHỜ"}, {"verdict": "THEO DÕI LONG"})
        self.assertEqual(v, "THEO DÕI LONG")
        self.assertEqual(src, "status.src.model")

    def test_the_scanner_stance_is_shown_when_there_is_no_local_read(self):
        BA = self._mod()
        v, src = BA.verdict_of({"stance": "CHỜ"}, None)
        self.assertEqual(v, "CHỜ", "the scanner's reading must not be hidden behind an em-dash")
        self.assertEqual(src, "status.src.scanner")

    def test_only_a_genuinely_absent_reading_shows_the_dash(self):
        BA = self._mod()
        v, src = BA.verdict_of(None, None)
        self.assertEqual(v, "—")
        self.assertEqual(src, "status.src.none")

    def test_the_verdict_vocabulary_has_one_source(self):
        """The layer-2 verdict is scraped out of prose. It is held to the same four values the layer-3
        narrative is validated against, read from that schema -- not a second copy that can drift."""
        BA = self._mod()
        schema = json.load(open(os.path.join(ROOT, "docs", "architecture", "schemas", "narrative.schema.json"),
                                encoding="utf-8"))
        found = []

        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "verdict" and isinstance(v, dict) and isinstance(v.get("enum"), list):
                        found.append(tuple(v["enum"]))
                    walk(v)
            elif isinstance(o, list):
                for x in o:
                    walk(x)
        walk(schema)
        self.assertTrue(found)
        self.assertEqual(BA.VERDICT_VOCAB, found[0])

    def test_the_prose_checker_reads_the_same_vocabulary(self):
        src = open(os.path.join(ROOT, "scripts", "check-model-prose.py"), encoding="utf-8").read()
        self.assertIn("narrative.schema.json", src,
                      "check-model-prose kept its own copy of the verdict list; it must read the schema")

    def test_the_layer2_verdict_is_anchored_to_the_head_not_any_bold_text(self):
        """A bare `<strong>` match meant whichever bold phrase came first became the page's verdict, and
        chip() renders an unrecognised value verbatim rather than refusing it."""
        src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()
        self.assertIn('prelim-head">.*?<strong>', src)

    def test_a_value_outside_the_vocabulary_does_not_become_a_verdict(self):
        BA = self._mod()
        import tempfile
        d = tempfile.mkdtemp()
        pre = os.path.join(d, "data", "live", "prelim")
        os.makedirs(pre, exist_ok=True)
        p = os.path.join(pre, "s.X.model.html")
        open(p, "w", encoding="utf-8").write(
            '<div class="prelim-head">Đánh giá cục bộ (Sonnet) · dữ liệu tới 10:00 UTC · '
            '<strong>MUA NGAY</strong></div><div>x</div>')
        saved = BA.ROOT
        try:
            BA.ROOT = d
            out = BA.layer2("s", "X")
        finally:
            BA.ROOT = saved
        self.assertIsNotNone(out, "the fixture file was not where layer2 looks")
        self.assertIsNone(out["verdict"], "an unrecognised phrase must not be rendered as a verdict")
