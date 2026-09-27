"""CLAUDE.md §13 -- multiple methodologies, no invented rules, and Methodology != Setup != Trading System.

§13 is the section this repo was already closest to satisfying, which makes it the one most worth pinning
rather than rebuilding. Three requirements, and all three have real enforcement already:

  * **"The architecture must allow multiple methodologies"** -- `docs/architecture/methods.json` is a registry
    of four, each with its own agent, skill, knowledge sources and chart lane. Nothing hard-codes the set.
  * **"Do not invent methodology rules that are not supported by the methodology specification"** -- two
    mechanisms. `scripts/method_purity.py` refuses a block that borrows another methodology's vocabulary
    (an ICT sentence may not say "trading range"; a Wyckoff one may not say "sweep"), and
    `scripts/tests/test_doc_citations.py` requires every `knowledge/` citation to resolve to a real file.
  * **"Methodology != Setup != Trading System"** -- two-thirds real. Methodology and Setup are separate
    artifacts. Trading System has none, and a setup row is doing its job (SYSTEM-DESIGN.md §17.1).

These tests exist so the first two cannot regress quietly, and so the third stays visibly two-thirds rather
than being assumed closed.
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import methods as M
import spec


class MultipleMethodologiesAreSupported(unittest.TestCase):
    def test_the_registry_holds_more_than_one_and_nothing_hard_codes_the_set(self):
        self.assertGreaterEqual(len(M.ALL_DIMENSIONS), 2)
        self.assertEqual(set(M.ALL_DIMENSIONS), set(M.DIMENSIONS),
                         "the dimension list must come from the registry, not a constant")

    def test_each_methodology_has_its_own_agent_skill_and_lane(self):
        """Separate reasoning role, separate procedure, separate chart lane -- the shape that lets a
        methodology be analysed without being merged into another's read."""
        agents, skills, lanes = set(), set(), set()
        for d, v in M.DIMENSIONS.items():
            for field in ("agent", "skill", "lane"):
                self.assertTrue(v.get(field), f"dimension {d} has no {field}")
            skills.add(v["skill"]); lanes.add(v["lane"]); agents.add(v["agent"])
        self.assertEqual(len(skills), len(M.ALL_DIMENSIONS), "two dimensions share one skill")
        self.assertEqual(len(lanes), len(M.ALL_DIMENSIONS), "two dimensions share one chart lane")
        # Agents may legitimately be shared: structure-agent runs both Wyckoff and ICT, which is why the
        # Wyckoff/ICT de-duplication rule exists at all (SYSTEM-DESIGN.md §6.1).
        self.assertLessEqual(len(agents), len(M.ALL_DIMENSIONS))

    @unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
    def test_every_methodology_the_spec_names_is_in_the_registry(self):
        """§13 carries TWO bullet lists -- the methodologies, and what a methodology may produce
        (observations, structure, context, invalidation, expectations, setup candidates). Only the first is a
        registry claim; reading the section's bullets as one list asked the registry for a dimension called
        `observations`."""
        body = spec.body(13)
        listed = [b.lower() for b in spec.bullet_list(body[:body.index("The architecture must allow")])]
        self.assertEqual(len(listed), 4, f"§13's methodology list changed shape: {listed}")
        for name in listed:
            self.assertIn(name, M.ALL_DIMENSIONS,
                          f"CLAUDE.md §13 names the {name} methodology; the registry has "
                          f"{list(M.ALL_DIMENSIONS)}")

    @unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
    def test_what_a_methodology_may_produce_is_a_separate_list(self):
        """The second list is §17's territory (expectations) and §14's (setup candidates). Recorded here so
        the two lists stay distinguished -- conflating them is what broke this test's first version."""
        body = spec.body(13)
        produces = [b.lower() for b in spec.bullet_list(body[body.index("A methodology may produce"):])]
        self.assertIn("expectations", produces)
        self.assertIn("setup candidates", produces)
        for item in produces:
            self.assertNotIn(item, M.ALL_DIMENSIONS,
                             f"{item!r} is an OUTPUT of a methodology, not a methodology")


class NoInventedRules(unittest.TestCase):
    def test_every_methodology_declares_where_its_theory_comes_from(self):
        """A dimension with no source could have its rules written from memory, which is the failure §13's
        'not supported by the methodology specification' names."""
        design = open(os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md"), encoding="utf-8").read()
        table = design[design.index("| Skill | Owns | Reads |"):]
        table = table[:table.index("\n\n")]
        for d in M.ALL_DIMENSIONS:
            skill = M.DIMENSIONS[d]["skill"]
            name = skill.replace("-skill", "").capitalize()
            self.assertIn(name.lower(), table.lower(),
                          f"dimension {d}'s skill {skill} has no row in the §4 skills table")

    def test_the_one_methodology_with_no_ingested_source_says_so(self):
        """Heatmap's rules come from the master prompt only -- a declared gap (SYSTEM-DESIGN.md §12 item 1).
        Being honest about it is the requirement; pretending otherwise would be the violation."""
        note = M.DIMENSIONS["heatmap"].get("note", "")
        self.assertIn("No ingested knowledge", note,
                      "the heatmap dimension must keep stating that it has no ingested source doc")

    def test_vocabulary_purity_is_enforced_by_code_not_by_request(self):
        """Exercised, not just imported: the checker must actually catch a cross-methodology term. The real
        API is `violations(text, method)` over `RULES`/`METHODS` -- checked rather than guessed."""
        import importlib.util
        s = importlib.util.spec_from_file_location("mp", os.path.join(ROOT, "scripts", "method_purity.py"))
        mp = importlib.util.module_from_spec(s); s.loader.exec_module(mp)
        self.assertTrue(set(M.ALL_DIMENSIONS) & set(mp.METHODS), "no methodology is covered by the purity gate")
        # An ICT block reaching for a Wyckoff term is the exact failure the gate exists for.
        self.assertTrue(mp.violations("price returned to the trading range after the SOS", "ict"),
                        "the purity gate did not flag Wyckoff vocabulary inside an ICT block")
        self.assertFalse(mp.violations("price closed past the swing with displacement", "ict"),
                         "the purity gate flagged ordinary ICT wording")

    def test_the_ict_corpus_carries_no_volume_and_the_registry_says_so(self):
        """The load-bearing fact behind the Wyckoff/ICT independence rule: volume is the only orthogonal axis
        between them, so an ICT block claiming volume would be an invented rule (SYSTEM-DESIGN.md §6.1)."""
        self.assertIn("no volume", M.DIMENSIONS["ict"].get("note", "").lower())


class MethodologyIsNotSetupIsNotTradingSystem(unittest.TestCase):
    def test_methodology_and_setup_live_in_different_artifacts(self):
        self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "architecture", "methods.json")))
        self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")))

    def test_a_runner_method_is_not_the_same_thing_as_a_dimension_of_the_same_name(self):
        """`WYCKOFF-BOOK` the mechanical rule family and `wyckoff` the Confluence dimension are homonyms in
        spirit, and the registry says so in `_runner_note`. Collapsing them would let a mechanical rule set
        claim a discretionary read's credit. (The `WYCKOFF` mechanical proxy this test used to name was
        removed 2026-09-19 -- docs/audits/2026-09-19-knowledge-fidelity.md finding 6; WYCKOFF-BOOK is now the
        only mechanical Wyckoff runner method.)"""
        registry = json.load(open(os.path.join(ROOT, "docs", "architecture", "methods.json"), encoding="utf-8"))
        self.assertIn("Homonyms", registry["_runner_note"])
        self.assertIn("WYCKOFF-BOOK", M.RUNNER_METHODS)
        self.assertIn("wyckoff", M.DIMENSIONS)
        self.assertNotEqual(M.RUNNER_METHODS["WYCKOFF-BOOK"], M.DIMENSIONS["wyckoff"])

    def test_methodology_setup_and_trading_system_are_three_separate_artifacts(self):
        """The missing third arrived on 2026-09-18 (§35). This test was previously the failing-forward guard
        asserting the layer map still said NO ARTIFACT; it is now the positive statement it was waiting to
        become -- three layers, three files, and a Trading System that is not a methodology and not a setup."""
        import trading_system as TS
        design = open(os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md"), encoding="utf-8").read()
        self.assertNotIn("| Trading System | — | **NO ARTIFACT.**", design)
        self.assertIn("docs/architecture/trading-systems.json", design)
        # Three distinct vocabularies: a dimension is not a runner method and neither is a Trading System.
        self.assertTrue(set(TS.styles()).isdisjoint(M.DIMENSIONS))
        self.assertTrue(set(TS.styles()).isdisjoint(M.RUNNER_METHODS))
        # And the system points AT a setup rather than containing one: the pilot row is still its own record.
        for row in TS.setups("scalping"):
            self.assertIn("method", row)
            self.assertNotIn(row["id"], TS.SYSTEMS)


if __name__ == "__main__":
    unittest.main()
