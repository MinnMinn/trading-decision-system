"""CLAUDE.md §16 -- methodology modes are explicit configuration, and every consumer knows the same set.

§16's two requirements were in opposite states. The mode-lock — "do not silently change methodology behaviour
based on provider availability" — was already real code and well tested (`methods.mode_of()` is a pure
function of the selected preset, and a dimension going unavailable at runtime can lower `engaged_count` but
never change the mode). What was broken was simpler and worse:

**SOLO was added to the registry on 2026-09-12 and never reached either schema.** `methods.json` declared four
modes; `trade-file.schema.json` and `confluence-score.schema.json` enumerated three. The live preset `ict`
resolves to SOLO — so a conformant `/analyze` record or trade file for the CURRENT configuration was
schema-invalid, and nothing noticed because nothing generated the pair. That is a §59 failure (a registry
change not traced to its consumers) wearing a §16 hat.

The fix is the repo's own idiom rather than a hand-edit: `sync-methods.py` already generates two derived enums
from the registry, and now generates this one too, with `--check` failing the build on drift.

The same change surfaced two false claims in `journal.py`, both hard-coded literals: every pilot trade filed
itself as `methodology_mode: "NORMAL"` (while the configuration was SOLO) and
`dimensions_used: ["wyckoff", "ict"]` (while an ICT-only setup uses one dimension).
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

MODE_SCHEMAS = ("trade-file.schema.json", "confluence-score.schema.json")


def schema(name):
    with open(os.path.join(ROOT, "docs", "architecture", "schemas", name), encoding="utf-8") as fh:
        return json.load(fh)


def journal():
    s = importlib.util.spec_from_file_location("j", os.path.join(ROOT, "scripts", "journal.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


class EveryConsumerKnowsTheSameModes(unittest.TestCase):
    def test_both_schemas_accept_every_registry_mode(self):
        """The defect, stated directly: SOLO existed in the registry and in neither schema for six days."""
        for name in MODE_SCHEMAS:
            enum = schema(name)["properties"]["methodology_mode"]["enum"]
            self.assertEqual(sorted(enum), sorted(M.MODES),
                             f"{name} methodology_mode.enum does not match the registry")

    def test_the_live_configuration_resolves_to_a_mode_both_schemas_accept(self):
        """The property that actually bit: it is not enough for the enums to match the registry in the
        abstract -- the mode the CURRENT config produces must be recordable."""
        live = M.dispatch_plan("BTCUSDT")["mode"]
        for name in MODE_SCHEMAS:
            self.assertIn(live, schema(name)["properties"]["methodology_mode"]["enum"],
                          f"the live preset resolves to {live}, which {name} would reject")

    def test_the_enums_are_generated_not_hand_kept(self):
        """A hand-kept copy is what drifted. `sync-methods.py --check` must fail on drift, and the test suite
        runs it (scripts/tests/test_methods_sync.py)."""
        src = open(os.path.join(ROOT, "scripts", "sync-methods.py"), encoding="utf-8").read()
        self.assertIn("MODE_SCHEMAS", src)
        self.assertIn("methodology_mode.enum", src, "the drift message must name the field")

    def test_sync_reports_no_drift_right_now(self):
        import subprocess
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-methods.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, f"sync-methods --check reports drift:\n{out.stdout}")


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class ModesAreExplicitConfiguration(unittest.TestCase):
    def test_the_three_spec_modes_all_exist(self):
        """§16 names NORMAL / ENHANCED / STRICT. SOLO is this project's own addition (user decision
        2026-09-12) and is allowed to exist beyond the spec's list -- the spec says modes 'such as'."""
        for mode in ("NORMAL", "ENHANCED", "STRICT"):
            self.assertIn(mode, M.MODES)

    def test_each_mode_declares_a_minimum_and_a_threshold(self):
        for name, m in M.MODES.items():
            self.assertIsInstance(m.get("minimum"), int, f"mode {name} has no integer minimum")
            self.assertIsInstance(m.get("threshold"), (int, float), f"mode {name} has no threshold")

    def test_a_mode_is_a_function_of_the_preset_never_of_runtime_availability(self):
        """§16: 'Do not silently change methodology behaviour based on provider availability.' A
        multi-dimension preset that loses a dimension at runtime keeps its mode and fails on count instead."""
        self.assertEqual(M.mode_of("wyckoff+footprint"), "NORMAL")
        self.assertEqual(M.mode_of("ict"), "SOLO")
        self.assertEqual(M.mode_of("custom"), M.DEFAULT_MODE)
        self.assertEqual(M.mode_of("UNREADABLE"), M.DEFAULT_MODE)

    def test_solo_is_reachable_only_from_a_single_dimension_preset(self):
        for p in M.PRESETS:
            if p["mode"] == "SOLO":
                self.assertEqual(len(p["dimensions"]), 1, f"preset {p['id']} claims SOLO with >1 dimension")


class TheJournalNoLongerAssertsAModeItDidNotRun(unittest.TestCase):
    def setUp(self):
        self.j = journal()

    def test_the_mode_comes_from_the_configuration_not_a_literal(self):
        mode, _ = self.j._pilot_mode_and_dims("BTCUSDT", "ICT")
        self.assertEqual(mode, M.dispatch_plan("BTCUSDT")["mode"])

    def test_the_dimensions_come_from_the_rule_family_requires(self):
        """An ICT-only setup used to file itself as having used Wyckoff too."""
        self.assertEqual(self.j._pilot_mode_and_dims("BTCUSDT", "ICT")[1], ["ict"])
        self.assertEqual(self.j._pilot_mode_and_dims("BTCUSDT", "COMBINED-BOOK")[1], ["wyckoff", "ict"])
        self.assertEqual(self.j._pilot_mode_and_dims("XAUUSD", "WYCKOFF-BOOK")[1], ["wyckoff"])

    def test_an_unknown_method_yields_none_rather_than_a_guess(self):
        self.assertIsNone(self.j._pilot_mode_and_dims("BTCUSDT", "NO-SUCH-METHOD")[1])
        self.assertIsNone(self.j._pilot_mode_and_dims("BTCUSDT", None)[1])

    def test_an_unknown_symbol_does_not_break_the_ingest(self):
        """A journal ingest must not fail because a symbol is off the allowlist -- but it must not invent a
        mode either, so the answer is None and the caller omits it."""
        mode, dims = self.j._pilot_mode_and_dims("NOTASYMBOL", "ICT")
        self.assertIsNone(mode)
        self.assertEqual(dims, ["ict"])

    def test_no_hard_coded_mode_literal_remains_in_the_ingest_path(self):
        src = open(os.path.join(ROOT, "scripts", "journal.py"), encoding="utf-8").read()
        self.assertNotIn('"methodology_mode": "NORMAL"', src)
        self.assertNotIn('"dimensions_used": ["wyckoff", "ict"],', src)


if __name__ == "__main__":
    unittest.main()
