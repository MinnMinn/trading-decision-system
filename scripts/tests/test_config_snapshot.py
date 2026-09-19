"""CLAUDE.md §11 -- a result must capture the configuration that produced it.

§11 lists sixteen configuration fields. None were recorded: every rule switch existed as a CLI flag or a
module-level dict, and the two most load-bearing numbers -- the risk ceiling and the planned-R:R floor -- are
read at import from *mutable* files. So a re-run after an edit measures a different system while the old
report still claims the old figures. That is documented history, not a hypothetical: the ceiling moved 3 % to
1 % on 2026-09-17 and every report produced before it was silently modelling a different account
(`scripts/backtest-methods.py:59`).

Three properties are under test, and the second and third are the ones that took work:

  1. **Completeness over the spec's own list.** Every §11 field gets an entry -- a value,
     `unavailable(reason, owner)`, or `not_applicable(reason)`. `config_snapshot()` REFUSES a partial record,
     because the whole value of the block is that a reader can trust an absence to mean something specific.
  2. **Captured by value, not by reference.** The snapshot holds the risk % and R:R floor as numbers, so
     editing risk-config.json afterwards cannot retroactively change what a recorded result says it measured.
  3. **The residual-state trap.** `bt.OPTS` is a module-level dict that `stability-report.py` mutates once
     per (timeframe, configuration) inside its loop. What is readable when the loop ends is the LAST
     configuration's state, not "the run's settings". Reporting it as the latter would be a snapshot that
     lies in the most plausible way available, so those fields carry `varied_per_config` and point at the
     matrix that actually applied. This was found by reading my own first output, not by a test.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import snapshot
import spec


def bt():
    s = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def sample(**over):
    module = over.pop("bt", None) or bt()
    kw = dict(timeframes=["1D"], methods=("ICT", "WYCKOFF-BOOK"),
              configs={"A": {"mgmt": "none", "htf": False, "fee": 0.0005},
                       "B": {"mgmt": "be", "htf": True, "fee": 0.0005}},
              fee_pct=None, ict_target="range", dataset_snapshot_id="deadbeef")
    kw.update(over)
    return snapshot.backtest_config_snapshot(module, **kw)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class CompleteOverTheSpecsList(unittest.TestCase):
    def test_the_declared_fields_are_exactly_the_ones_section_11_lists(self):
        listed = spec.bullet_list(spec.body(11))
        self.assertEqual(len(listed), 16, f"§11's field list changed shape: {listed}")
        self.assertEqual({f.replace(" ", "_").lower() for f in listed}, set(snapshot.CONFIG_FIELDS))

    def test_a_record_covers_every_field(self):
        self.assertEqual(set(sample()["fields"]), set(snapshot.CONFIG_FIELDS))

    def test_a_partial_record_refuses(self):
        """An absent key cannot be told apart from an empty value, so a partial record is not accepted."""
        with self.assertRaises(ValueError) as cm:
            snapshot.config_snapshot(fields={"methodology": "x"})
        self.assertIn("incomplete", str(cm.exception))

    def test_an_unknown_field_refuses(self):
        full = {k: None for k in snapshot.CONFIG_FIELDS}
        full["vibes"] = "good"
        with self.assertRaises(ValueError) as cm:
            snapshot.config_snapshot(fields=full)
        self.assertIn("vibes", str(cm.exception))


class GapsAreTypedNotOmitted(unittest.TestCase):
    def test_a_missing_artifact_says_unavailable_and_names_its_owner(self):
        f = sample()["fields"]
        for field, owner_hint in (("trading_system_version", "35"), ("required_evidence", "35"),
                                  ("required_analytics", "35")):
            self.assertIn("unavailable", f[field], f"{field} should be typed unavailable")
            self.assertIn(owner_hint, f[field]["owner"], f"{field} should name its owning section")

    def test_the_account_profile_is_now_captured_rather_than_typed_unavailable(self):
        """It was `unavailable(..., "§33")` until 2026-09-18, when the Account Profile object was built. A
        run record must say WHICH account rules were in force (§11): under a 15 % drawdown limit is not the
        same experiment as under 5 %."""
        import account_profile as AP
        f = sample()["fields"]["account_profile"]
        self.assertNotIn("unavailable", f)
        self.assertEqual(f["profile_id"], "pilot-binance-futures-testnet")
        self.assertEqual(f["registry_version"], AP.VERSION)
        for key in AP.RULE_KEYS:
            self.assertIn(key, f["rules"])

    def test_a_category_error_says_not_applicable_instead(self):
        """'We have no account profile' and 'a mechanical backtest has no methodology mode' are different
        statements; collapsing both to a missing key would lose which is a gap."""
        f = sample()["fields"]
        for field in ("methodology_mode", "session", "news_rules"):
            self.assertIn("not_applicable", f[field], f"{field} should be typed not_applicable")
            self.assertNotIn("unavailable", f[field])

    def test_the_news_entry_states_that_no_event_filtering_happened(self):
        """Not just 'no news rules' -- the consequence. A reader comparing this backtest to live behaviour
        needs to know the results contain no event-risk filtering at all."""
        self.assertIn("no event-risk filtering",
                      sample()["fields"]["news_rules"]["not_applicable"])


class CapturedByValue(unittest.TestCase):
    def test_the_risk_ceiling_and_rr_floor_are_numbers_not_paths(self):
        m = bt()
        risk = sample(bt=m)["fields"]["risk_model"]
        self.assertEqual(risk["risk_pct_of_equity"], m.RISK)
        self.assertEqual(risk["min_planned_rr"], m.MIN_RR)
        self.assertIsInstance(risk["risk_pct_of_equity"], float)
        self.assertIsInstance(risk["min_planned_rr"], float)

    def test_it_also_records_where_those_numbers_came_from(self):
        """The value answers 'what did this measure'; the source answers 'where would I change it'. Both."""
        risk = sample()["fields"]["risk_model"]
        self.assertIn("risk-config.json", risk["risk_source"])
        self.assertIn("analysis-params.json", risk["min_rr_source"])

    def test_a_later_config_edit_cannot_change_an_already_recorded_result(self):
        """The property that makes §11 worth having: a record HOLDS the number, it does not point at it.

        Demonstrated by capturing, then mutating the source, then re-reading the ORIGINAL record. A fresh
        capture is expected to see the new value -- that is not the risk. The risk is the old report silently
        re-describing itself, which is what happened when the ceiling moved 3% -> 1%."""
        m = bt()
        recorded = sample(bt=m)
        original = recorded["fields"]["risk_model"]["risk_pct_of_equity"]
        self.assertNotEqual(original, 0.99, "pick a sentinel the real config does not use")

        m.RISK = 0.99                                    # the config file is edited after the run
        self.assertEqual(recorded["fields"]["risk_model"]["risk_pct_of_equity"], original,
                         "the already-recorded result changed when its source did -- captured by reference")
        self.assertEqual(sample(bt=m)["fields"]["risk_model"]["risk_pct_of_equity"], 0.99,
                         "a FRESH capture should see the new value; only the old record must be immutable")

    def test_the_unmodelled_execution_costs_are_named(self):
        ex = sample()["fields"]["execution_assumptions"]
        self.assertIn("NOT MODELLED", ex["slippage"])
        self.assertIn("NOT MODELLED", ex["funding"])


class TheResidualStateTrap(unittest.TestCase):
    def test_opts_derived_fields_disclose_that_they_varied(self):
        f = sample()["fields"]
        for field in ("entry_rules", "exit_rules", "custom_constraints"):
            self.assertIn("varied_per_config", f[field], f"{field} must disclose per-config variation")
            self.assertIsNotNone(f[field]["varied_per_config"],
                                 f"{field} claims a single value across a multi-config run")
            self.assertIn("RESIDUAL", f[field]["varied_per_config"])

    def test_a_single_config_run_makes_no_such_disclaimer(self):
        """The disclaimer must be accurate, not decorative: one configuration means the captured state IS the
        run's state."""
        f = sample(configs={"A": {"mgmt": "none", "htf": False}})["fields"]
        self.assertIsNone(f["entry_rules"]["varied_per_config"])

    def test_the_configuration_matrix_itself_is_recorded(self):
        setup = sample()["fields"]["setup"]
        self.assertEqual(sorted(setup["configs"]), ["A", "B"])
        self.assertEqual(setup["timeframes"], ["1D"])

    def test_a_per_config_fee_is_not_reported_as_unknown(self):
        """`fee_pct_per_side: null` read as 'we do not know the fee' when in fact the fee is per
        configuration. Pointing at where it lives beats a null that looks like ignorance."""
        ex = sample()["fields"]["execution_assumptions"]
        self.assertIn("setup.configs", str(ex["fee_pct_per_side"]))


class LinkedToTheDatasetHalf(unittest.TestCase):
    def test_the_two_blocks_are_separate_and_linked(self):
        """§10 and §11 are separate because the same parameters over different candles, and the same candles
        under different parameters, are both 'a different experiment'."""
        c = sample()
        self.assertEqual(c["dataset_snapshot_id"], "deadbeef")
        self.assertNotIn("series", c, "the data half must not be duplicated into the config half")

    def test_provider_selection_points_at_the_dataset_snapshot(self):
        self.assertEqual(sample()["fields"]["provider_selection"]["see"], "dataset_snapshot_id")


class WiredIntoTheResearchRun(unittest.TestCase):
    def test_the_stability_report_emits_both_blocks(self):
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertIn("config_snapshot=cfg_snap", src)
        self.assertIn("dataset_snapshot=snap", src)
        self.assertIn("rows=rows", src, "rank-setups.py reads `rows` and must keep working")

    def test_a_config_snapshot_failure_is_recorded_not_swallowed(self):
        src = open(os.path.join(ROOT, "scripts", "stability-report.py"), encoding="utf-8").read()
        self.assertEqual(src.count("snapshot_error"), 2, "both snapshot halves must record their own failure")


if __name__ == "__main__":
    unittest.main()
