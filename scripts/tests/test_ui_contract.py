"""CLAUDE.md §50 UI / UX -- the section that is satisfied only if the value reaches the screen.

Every other section can be satisfied by a module that computes the right thing. §50 cannot: a field can be
computed correctly, carried with its provenance intact, gated on correctly, and never be rendered -- and
nothing else in this repository would notice. The previous audit was a 22-row hand check that found six fields
missing, and a hand check is right on the day it is written and never again.

So the field list is `docs/architecture/ui-fields.json`, every field names a marker, and **these tests build
the real pages and look for it**. A field cannot be marked exposed by editing the registry; only by rendering.

The two checks that carry the most weight:

* `EveryPageRendersWhatItOwes` builds all three pages -- both chart styles, the control panel, the journal --
  and asserts zero missing markers. This is slow and it is the point.
* `TheValuesAreReadNotTyped` asserts the values are the registries' own. A page that says PERPETUAL because
  someone typed PERPETUAL is not exposing the market type, it is asserting it, and it goes on asserting it
  after the venue changes.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ui_contract as UI            # noqa: E402
import providers as P               # noqa: E402
import instruments as I             # noqa: E402
import account_profile as AP        # noqa: E402
import trading_env                  # noqa: E402
import trading_system as TS         # noqa: E402

REGISTRY = os.path.join(ROOT, "docs", "architecture", "ui-fields.json")


def _mod(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _spec_block(after, until):
    spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
    body = spec.split("50. UI / UX", 1)[1].split(until, 1)[0].split(after, 1)[1]
    return [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_twenty_two_fields_50_names_are_listed_in_order(self):
        want = _spec_block("The UI must clearly expose:", "Trading Control Center must distinguish")
        self.assertEqual(UI.spec_names(), want)

    def test_all_four_core_ui_areas_are_listed_in_order(self):
        want = _spec_block("Core UI areas:", "The UI must clearly expose:")
        self.assertEqual(list(UI.AREAS), want)

    def test_an_area_with_no_page_says_why(self):
        # "System Lab" has no page in this repository (System Performance & Ranking gained one 2026-09-18,
        # scripts/system-ranking.py). That is a fact worth recording -- and it must be recorded, not merely true.
        for name in UI.AREAS:
            a = UI.area(name)
            if not a["served_by"]:
                self.assertTrue(a["_why"].strip(), name)

    def test_every_field_names_the_reader_that_supplies_it(self):
        for fid in UI.FIELDS:
            self.assertTrue(str(UI.field(fid)["source"]).strip(), fid)


class TheLoaderRefusesWhatWouldInvert50(unittest.TestCase):
    def _mutate(self, fn):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        fn(data)
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-ui.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(UI.RegistryError) as cm:
                UI._load(p)
            return str(cm.exception)
        finally:
            os.remove(p)

    def test_required_and_optional_may_not_render_identically(self):
        # §50: "Required analysis should be visually distinguishable from optional analysis." Rendering them
        # the same implies every displayed lane counts toward the trade -- the confusion §18 and §62 exist to
        # prevent. This is the one edit that would invert the section's meaning while looking like a tidy-up.
        def same_class(d):
            klass = None
            for f in d["fields"]:
                if f.get("distinguishable_by"):
                    klass = klass or f["distinguishable_by"]
                    f["distinguishable_by"] = klass
        msg = self._mutate(same_class)
        self.assertIn("visually distinguishable", msg)
        self.assertIn("§62", msg)

    def test_an_unsurfaced_field_with_no_reason_is_refused(self):
        def drop(d):
            d["fields"][0]["pages"] = []
            d["fields"][0].pop("_why", None)
        self.assertIn("indistinguishable from an oversight", self._mutate(drop))

    def test_two_fields_may_not_claim_one_marker(self):
        def dup(d):
            d["fields"][1]["marker"] = d["fields"][0]["marker"]
        self.assertIn("cannot prove two fields", self._mutate(dup))

    def test_a_field_may_not_claim_a_page_nobody_builds(self):
        def ghost(d):
            d["fields"][0]["pages"] = ["mobile"]
        self.assertIn("no builder produces", self._mutate(ghost))


class EveryPageRendersWhatItOwes(unittest.TestCase):
    """The check that makes the registry worth more than the prose it replaced."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        b = _mod("build-artifact.py")
        cls.html = {}
        for style in ("scalping", "cfd-scalping"):
            out = os.path.join(cls.tmp, f"{style}.html")
            b.build(style, out)
            cls.html[style] = open(out, encoding="utf-8").read()
        panel = _mod("method-panel.py")
        cls.html["panel"] = panel.render(panel.facts()["config"])
        jr = _mod("journal.py")
        out = os.path.join(cls.tmp, "journal.html")
        jr.render(jr.build_index(), out)
        cls.html["journal"] = open(out, encoding="utf-8").read()
        sr = _mod("system-ranking.py")
        cls.html["ranking"] = sr.render(sr.rows())

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_crypto_chart_page_renders_all_twenty_two(self):
        r = UI.audit(self.html["scalping"], "chart")
        self.assertEqual(r["missing"], [], f"missing on the crypto chart page: {r['missing']}")

    def test_the_cfd_chart_page_renders_all_twenty_two(self):
        r = UI.audit(self.html["cfd-scalping"], "chart")
        self.assertEqual(r["missing"], [], f"missing on the cfd chart page: {r['missing']}")

    def test_the_control_panel_renders_what_it_owes(self):
        r = UI.audit(self.html["panel"], "panel")
        self.assertEqual(r["missing"], [])

    def test_the_journal_renders_what_it_owes(self):
        if not self.html["journal"]:
            self.skipTest("journal not rendered in this environment")
        r = UI.audit(self.html["journal"], "journal")
        self.assertEqual(r["missing"], [])

    def test_the_ranking_page_audits_clean(self):
        # The ranking page's six ranking-* markers live outside the 22-field §50 registry (they are
        # scripts/ranking.py's own always_expose list, CLAUDE.md §48) -- UI.expected("ranking") is
        # therefore empty and this asserts the audit finds nothing MISSING, not that markers are present.
        # scripts/tests/test_system_ranking.py is the test that pins the six ranking-* markers themselves.
        r = UI.audit(self.html["ranking"], "ranking")
        self.assertEqual(r["missing"], [])

    def test_a_missing_marker_would_be_caught(self):
        # Mutation: the checker must actually be able to fail. Strip one attribute and it must be reported.
        broken = self.html["scalping"].replace(UI.attr("event-risk"), "", 1)
        self.assertIn("event-risk", UI.audit(broken, "chart")["missing"])

    def test_no_page_says_confidence_percent(self):
        # §50: "Use Confluence Score, not Confidence %. Avoid fake precision."
        for name, html in self.html.items():
            if not html:
                continue
            for word in UI.FORBIDDEN_WORDS:
                self.assertNotIn(word, html, f"{name} says {word!r}")

    def test_required_and_optional_are_rendered_with_different_classes(self):
        # The registry refuses equal `distinguishable_by`; this asserts the page actually uses both.
        html = self.html["scalping"]
        klasses = {UI.field("required_analysis")["distinguishable_by"],
                   UI.field("optional_analysis")["distinguishable_by"]}
        self.assertEqual(len(klasses), 2)
        for k in klasses:
            self.assertIn(k, html, k)


class TheValuesAreReadNotTyped(unittest.TestCase):
    """A page that says PERPETUAL because someone typed PERPETUAL is asserting, not exposing."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        b = _mod("build-artifact.py")
        out = os.path.join(cls.tmp, "scalping.html")
        b.build("scalping", out)
        cls.html = open(out, encoding="utf-8").read()
        cls.src = open(os.path.join(ROOT, "scripts", "build-artifact.py"), encoding="utf-8").read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _cell(self, marker):
        m = re.search(rf'{UI.ATTR}="{marker}"[^>]*>(.*?)</div>', self.html, re.S)
        return re.sub(r"<[^>]+>", " ", m.group(1)) if m else ""

    def test_the_execution_venue_shown_is_the_registrys_unattended_provider(self):
        pid = [p for p in P.for_role("execution", "crypto") if P.PROVIDERS[p]["unattended"]]
        self.assertEqual(len(pid), 1)
        self.assertIn(pid[0], self._cell("execution-venue"))

    def test_the_data_provider_shown_is_the_registrys_market_data_provider(self):
        self.assertIn(P.for_role("market_data", "crypto")[0], self._cell("data-provider"))

    def test_the_source_venue_shown_is_the_registrys_venue(self):
        self.assertIn(P.venue_of(P.for_role("market_data", "crypto")[0]), self._cell("source-venue"))

    def test_both_market_types_are_shown_because_they_differ(self):
        # §20.1 on record: the crypto page reads SPOT candles while the pilot trades a PERPETUAL. Collapsing
        # the two into one word would hide a divergence this repository has deliberately written down.
        cell = self._cell("market-type")
        self.assertIn(P.data_market_type(P.for_role("market_data", "crypto")[0]), cell)
        self.assertIn(P.market_type_of("binance_futures"), cell)

    def test_the_account_profile_shown_is_the_one_an_order_would_obey(self):
        venue = P.unattended_venue_for("crypto")
        self.assertIn(AP.for_venue(venue, "demo")["id"], self._cell("account-profile"))

    def test_the_risk_ceiling_shown_is_the_one_source(self):
        self.assertIn(f"{trading_env.MAX_RISK_PCT * 100:g}%", self._cell("risk"))

    def test_the_required_lanes_shown_are_the_classifications_own(self):
        # The same call the order path makes, so the page cannot show one split while the runner uses another.
        cls = TS.classification("scalping", engaged=["ict"])
        req = {d.split(".", 1)[1] for d, r in cls.items()
               if r == TS.REQUIRED and d.startswith("methodology.")}
        cell = self._cell("required-analysis").lower()
        for lane in req:
            self.assertIn(lane, cell, lane)

    def test_the_builder_does_not_hard_code_a_venue_or_a_market_type(self):
        # The values above must come from the registries; a literal in the template would survive a registry
        # change and keep printing the old answer. (Comments are excluded -- they explain, they do not render.)
        code = "\n".join(ln for ln in self.src.splitlines() if not ln.strip().startswith("#"))
        body = code.split("def context_strip", 1)[1].split("\ndef lane_buttons", 1)[0]
        for literal in ('"PERPETUAL"', '"binance_futures"', '"mt5_bridge"', '"pilot-mt5-demo"'):
            self.assertNotIn(literal, body, literal)

    def test_the_point_in_time_values_carry_an_as_of(self):
        # A published page is a snapshot. An event-risk claim with no as-of is a claim about NOW made by a file
        # written hours ago -- §20's "never silently convert STALE to FRESH", happening on a screen.
        m = re.search(rf'{UI.ATTR}="event-risk".*?</div>\s*<div class="ctx-d">(.*?)</div>', self.html, re.S)
        self.assertIsNotNone(m)
        self.assertIn("as of", re.sub(r"<[^>]+>", " ", m.group(1)))


class TheRepositorysOwnState(unittest.TestCase):
    def test_describe_names_every_page_and_area(self):
        out = UI.describe()
        for p in UI.PAGES:
            self.assertIn(p, out)
        for a in UI.AREAS:
            self.assertIn(a, out)

    def test_the_chart_page_owes_every_field_because_it_is_the_decision_surface(self):
        self.assertEqual(len(UI.expected("chart")), len(UI.FIELDS))

    def test_the_registry_says_why_it_exists(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        self.assertIn("never reach the screen", data["_why_this_exists"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
