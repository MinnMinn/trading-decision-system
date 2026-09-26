"""CLAUDE.md §14 -- setup logic must be versioned, so a closed trade names the rules it was taken under.

§14 asks for four properties: explicit, independently testable, versioned, explainable. Three held. Versioned
did not, and the failure is specific: a setup's `id` encodes its parameters
(`crypto-scalping-combined-15m-border-b`) but not a version, `scripts/rank-setups.py` rewrites
`docs/architecture/pilot-selection.json` in place, and `trade-file.schema.json` records `strategy` as that id. So a
rule change produces the SAME id with DIFFERENT behaviour, and every past trade filed under it silently
re-points at rules it was never taken under.

A **content** version rather than a hand-bumped integer, because the two fail in opposite directions: a
digest changes exactly when behaviour changes; a counter is remembered when someone is thinking about
versioning and skipped when they are thinking about the rule.

The interesting tests here are the exclusions. `RISK`, `START` and `RUIN_FRAC` are deliberately NOT in the
version: halving risk does not change which bars qualify, and folding it in would churn every setup's version
whenever the ceiling moved -- which is how a version field trains people to ignore it. Risk IS
version-significant for a Trading System (§47), a different object that does not exist yet (§35).
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import setup_version as SV

ROW = {"id": "crypto-scalping-ict-15m-border-a", "market": "crypto", "tf": "15m", "method": "ICT",
       "htf": True, "mgmt": "be", "execution": "futures", "rank": 1,
       "symbols": ["BTCUSDT"], "fee_assumed": 0.0005, "backtest": {"n": 120, "ann_pct": 9.1}}
GLOBALS = {"min_rr": 3.0, "stop_buffer_pct": 0.0005,
           "displacement": {"body_min_ratio": 0.6, "range_min_median_ratio": 1.2},
           "volume": {"low_max_ratio": 0.7, "high_min_ratio": 1.5, "spike_min_ratio": 2.5},
           "per_timeframe": {"R": 48, "K": 16, "T": 16, "H": 96, "sob": 6}}


def v(row=None, **gover):
    g = dict(GLOBALS); g.update(gover)
    return SV.rule_version(row or ROW, g)


def rank_setups():
    s = importlib.util.spec_from_file_location("rs", os.path.join(ROOT, "scripts", "rank-setups.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
    return m


class TheVersionTracksBehaviour(unittest.TestCase):
    def test_it_is_stable_for_identical_inputs(self):
        self.assertEqual(v(), v())
        self.assertRegex(v(), r"^[0-9a-f]{12}$")

    def test_every_rule_field_changes_it(self):
        for field, other in (("market", "cfd"), ("tf", "1H"), ("method", "WYCKOFF-BOOK"),
                             ("htf", False), ("mgmt", "none"), ("execution", "mt5")):
            self.assertNotEqual(v(dict(ROW, **{field: other})), v(),
                                f"changing the {field} rule did not change the version")

    def test_every_deck_faithful_switch_changes_it(self):
        """Whatever is declared in FLAG_FIELDS must be part of the version. The set is EMPTY since 2026-09-19:
        ict_disp / ict_pd / std_origin were removed because none of the three could change an ICT setup
        (docs/audits/2026-09-19-knowledge-fidelity.md finding 11), so the loop below has nothing to iterate --
        which is why the removal is asserted explicitly rather than left to pass vacuously."""
        for dead in ("ict_disp", "ict_pd", "std_origin"):
            self.assertNotIn(dead, SV.FLAG_FIELDS,
                             f"{dead} is back in FLAG_FIELDS; it reads nothing on any ICT path")
        for flag in SV.FLAG_FIELDS:
            self.assertNotEqual(v(dict(ROW, **{flag: True})), v(),
                                f"setting {flag} did not change the version")

    def test_the_entry_filter_changes_it(self):
        """`min_rr` decides which setups qualify -- 38 % of a year's setups planned under 2R before the floor
        was raised -- so it is part of what the setup IS."""
        self.assertNotEqual(v(min_rr=2.0), v())

    def test_detection_parameters_change_it(self):
        self.assertNotEqual(v(displacement={"body_min_ratio": 0.9, "range_min_median_ratio": 1.2}), v())
        self.assertNotEqual(v(per_timeframe={"R": 48, "K": 99, "T": 16, "H": 96, "sob": 6}), v())


class TheVersionIgnoresWhatIsNotBehaviour(unittest.TestCase):
    def test_selection_metadata_does_not_change_it(self):
        """`rank` and `backtest` describe how a setup SCORED, not what it detects. If they moved the version,
        re-running the ranking on new data would invalidate every past trade's attribution."""
        self.assertEqual(v(dict(ROW, rank=9)), v())
        self.assertEqual(v(dict(ROW, backtest={"n": 5, "ann_pct": -40.0})), v())
        self.assertEqual(v(dict(ROW, negative_backtest=True)), v())

    def test_the_id_itself_does_not_change_it(self):
        """The id is a NAME. Including it would make the version move when a label moved and sit still when a
        rule moved -- backwards on both counts."""
        self.assertEqual(v(dict(ROW, id="something-else-entirely")), v())

    def test_the_symbol_list_does_not_change_it(self):
        self.assertEqual(v(dict(ROW, symbols=["ETHUSDT", "SOLUSDT"])), v())

    def test_risk_and_account_are_not_part_of_a_setup(self):
        """The deliberate exclusion. A Setup is 'a specific market condition that can qualify for entry'
        (§14); sizing is not part of that. Passing them is refused outright so the boundary cannot be blurred
        by a caller adding them later."""
        with self.assertRaises(ValueError) as cm:
            SV.rule_version(ROW, dict(GLOBALS, risk_pct=0.01))
        self.assertIn("risk_pct", str(cm.exception))


class TheInputsAreInspectable(unittest.TestCase):
    def test_rule_inputs_shows_exactly_what_was_hashed(self):
        """So a surprising version change can be explained rather than guessed at."""
        inp = SV.rule_inputs(ROW, GLOBALS)
        self.assertEqual(set(inp), {"setup", "global"})
        self.assertEqual(set(inp["setup"]), set(SV.RULE_FIELDS))
        self.assertNotIn("rank", inp["setup"])
        self.assertNotIn("backtest", inp["setup"])


class QualifiedIdentity(unittest.TestCase):
    def test_a_trade_records_name_and_version(self):
        self.assertEqual(SV.qualified_id(dict(ROW, rule_version="abc123abc123")),
                         "crypto-scalping-ict-15m-border-a@abc123abc123")

    def test_an_unversioned_setup_degrades_to_its_bare_name(self):
        self.assertEqual(SV.qualified_id(ROW), ROW["id"])

    def test_split_round_trips_and_tolerates_legacy_ids(self):
        self.assertEqual(SV.split_qualified("a-b@0123456789ab"), ("a-b", "0123456789ab"))
        self.assertEqual(SV.split_qualified("a-b"), ("a-b", None))


class WiredIntoTheWritePath(unittest.TestCase):
    def test_every_selection_write_path_stamps_versions(self):
        """`finalize()` exists so a fourth write path cannot forget: carry the switches, THEN version --
        in that order, since a carried switch changes the rules."""
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        self.assertEqual(src.count("selection = finalize(selection, a.select)"), 1)   # ADR 0008: one write path (was 3 modes)
        self.assertEqual(src.count("carry_flags(selection, a.select)"), 0,
                         "a write path still calls carry_flags directly and would ship unversioned setups")

    def test_stamp_runs_after_flags_are_carried(self):
        rs = rank_setups()
        i_carry = rs.__dict__ and open(os.path.join(ROOT, "scripts", "rank-setups.py"),
                                       encoding="utf-8").read().index("return SV.stamp(carry_flags(")
        self.assertGreater(i_carry, 0, "finalize must wrap carry_flags inside SV.stamp, not the reverse")

    def test_stamping_a_selection_adds_a_version_to_every_setup(self):
        rs = rank_setups()
        sel = {"setups": [dict(ROW), dict(ROW, id="other", mgmt="none")]}
        SV.stamp(sel, rs._global_rule_params)
        versions = [st["rule_version"] for st in sel["setups"]]
        self.assertTrue(all(len(x) == 12 for x in versions))
        self.assertNotEqual(versions[0], versions[1], "two different rule sets share a version")

    def test_the_runner_puts_the_version_on_the_plan(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn('setup_version=st.get("rule_version")', src)

    def test_the_journal_carries_it_onto_the_trade_file(self):
        src = open(os.path.join(ROOT, "scripts", "journal.py"), encoding="utf-8").read()
        self.assertIn('"setup_version": e["setup_version"]', src)

    def test_the_trade_schema_accepts_it(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            schema = json.load(fh)
        field = schema["properties"]["setup_version"]
        self.assertEqual(field["pattern"], "^[0-9a-f]{12}$")
        self.assertIn("null", field["type"], "legacy trades have no version and must still validate")


if __name__ == "__main__":
    unittest.main()
