"""CLAUDE.md §35 -- Trading System, and the four-way dependency classification §62 calls non-negotiable.

Before 2026-09-18 the four names (`REQUIRED_FOR_DECISION`, `OPTIONAL_FOR_ANALYSIS`, `VISUALIZATION_ONLY`,
`RESEARCH_ONLY`) appeared in `CLAUDE.md` and in prose comments and NOWHERE in code or config. The dependency
model was binary: a dimension was engaged or it was skipped. §36's canonical ordering and §62's invariant were
both unstateable, and `scripts/snapshot.py` was typing `required_evidence` / `required_analytics` as
`unavailable(..., "§35")` for exactly that reason.

A registry existing does not satisfy §35, so these tests are built around four things it would be easy to
ship without:

1. **Required-ness cannot be inherited.** A dependency gates only a system that named it. The registry is
   MUTATED here to declare `baseline_role: REQUIRED_FOR_DECISION` and the loader must refuse, because a
   dependency that becomes required by default is a required input in nine systems nobody reviewed.
2. **Missing context never relaxes a role.** Every conditional dependency asked without its condition's input
   resolves REQUIRED_FOR_DECISION. "I was not told which setup" must never read as "not required" -- that is
   the silent downgrade §36 names.
3. **Only REQUIRED_FOR_DECISION may gate.** `assert_may_gate` raises on the other three roles, and the live
   order path routes every dependency-derived block through it. The runner's own source is parsed here so a
   new block site on an unclassified input cannot land unnoticed.
4. **The classification is wired to something.** A registry read by nothing is prose in a different file
   extension, so the §11 configuration snapshot and the runner's own report are exercised against it.
"""
import importlib.util
import json
import os
import re
import sys
import unittest

import fresh_calendar as FC  # noqa: E402  (a current, quiet copy of the real calendar)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import account_profile as AP
import automation as A
import methods as M
import trading_system as TS

from live_write_isolation import redirect as _redirect_writes

RUNNER_SRC = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()

_RESTORE_WRITES = None


def setUpModule():
    # Several classes below load strategy-runner.py (or backtest-methods.py, which shares its `bt`) fresh;
    # anything that reaches sr.tick() through it would otherwise append a real trace to data/live/latency/
    # (scripts/tests/live_write_isolation.py).
    global _RESTORE_WRITES
    _RESTORE_WRITES = _redirect_writes()


def tearDownModule():
    _RESTORE_WRITES()


def _raw():
    with open(TS.PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _with_dependency(dep_id, **fields):
    """A deep copy of the live registry with one dependency altered, for the REAL validator to reject.

    Keyed by an explicit (section, id) rather than a dotted path, because dependency ids contain dots
    themselves ('display.chart') and a dotted-path helper would silently address the wrong node."""
    data = _raw()
    data["dependencies"][dep_id] = dict(data["dependencies"][dep_id], **fields)
    return data


class RegistryShape(unittest.TestCase):
    def test_roles_are_claude_mds_four_names_in_its_order(self):
        self.assertEqual(tuple(_raw()["roles"]), TS.ROLES)
        self.assertEqual(TS.ROLES, ("REQUIRED_FOR_DECISION", "OPTIONAL_FOR_ANALYSIS",
                                    "VISUALIZATION_ONLY", "RESEARCH_ONLY"))

    def test_only_required_for_decision_is_the_gating_role(self):
        self.assertEqual(_raw()["gating_role"], TS.REQUIRED)
        self.assertNotIn(TS.REQUIRED, TS.NON_GATING)

    def test_every_dependency_declares_kind_producer_baseline_and_reason(self):
        for dep_id, dep in TS.DEPENDENCIES.items():
            for field in ("kind", "produced_by", "baseline_role", "why"):
                self.assertTrue(str(dep.get(field) or "").strip(), f"{dep_id} has no {field}")
            self.assertIn(dep["baseline_role"], TS.ROLES, dep_id)

    def test_every_repo_path_named_as_a_producer_exists(self):
        """A `produced_by` that names a file which is not there is a citation that cannot be checked."""
        pattern = re.compile(r"\b(?:scripts|docs|data|integrations)/[A-Za-z0-9_./-]+")
        for dep_id, dep in TS.DEPENDENCIES.items():
            text = dep["produced_by"]
            for m in pattern.finditer(text):
                token = m.group(0).rstrip(".,)/")
                # A template path (`data/live/anchors.<style>.json`) cannot be checked as a literal, so the
                # directory that holds it is checked instead -- still catching a producer pointed at a folder
                # that does not exist, which is the failure this test is for.
                tail = text[m.end():m.end() + 1]
                target = os.path.dirname(token) if tail in ("<", "*") else token
                self.assertTrue(os.path.exists(os.path.join(ROOT, target)),
                                f"{dep_id} produced_by names {target}, which does not exist")

    def test_a_conditional_dependency_names_a_predicate_that_is_implemented(self):
        for dep_id, dep in TS.DEPENDENCIES.items():
            if "only_when" in dep:
                self.assertIn(dep["only_when"], TS.PREDICATES, dep_id)
                self.assertIn(dep.get("else_role"), TS.NON_GATING, dep_id)


class RequirednessCannotBeInherited(unittest.TestCase):
    """The single rule that makes the gating set reviewable: a dependency gates only a system that named it."""

    def test_a_baseline_role_of_required_refuses_to_load(self):
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(_with_dependency("display.chart", baseline_role=TS.REQUIRED), TS.PATH)
        self.assertIn("baseline_role", str(cm.exception))
        self.assertIn("inheritance", str(cm.exception))

    def test_an_else_role_of_required_refuses_to_load(self):
        with self.assertRaises(TS.RegistryError):
            TS._validate(_with_dependency("candles.htf", else_role=TS.REQUIRED), TS.PATH)

    def test_an_unimplemented_predicate_refuses_to_load(self):
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(_with_dependency("candles.htf", only_when="setup.vibes"), TS.PATH)
        self.assertIn("setup.vibes", str(cm.exception))

    def test_a_dimension_predicate_with_no_dimension_refuses_to_load(self):
        bad = _with_dependency("methodology.ict")
        del bad["dependencies"]["methodology.ict"]["dimension"]
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(bad, TS.PATH)
        self.assertIn("dimension", str(cm.exception))

    def test_an_else_role_with_no_condition_refuses_to_load(self):
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(_with_dependency("display.chart", else_role=TS.OPTIONAL), TS.PATH)
        self.assertIn("only_when", str(cm.exception))

    def test_no_dependency_outside_a_profile_can_ever_resolve_required(self):
        """The §62 property, checked over every system and a spread of contexts rather than argued."""
        declared = set(TS.declared_required(TS.styles()[0]))
        outside = [d for d in TS.DEPENDENCIES if d not in declared]
        self.assertTrue(outside, "the profile requires everything; this test would prove nothing")
        contexts = [{}, {"engaged": ()}, {"engaged": ("wyckoff", "ict", "footprint", "heatmap")},
                    {"setup": {"htf": True, "method": "COMBINED-BOOK"}},
                    {"setup": {"htf": False, "method": "ICT"}}]
        for style in TS.styles():
            for dep in outside:
                for ctx in contexts:
                    self.assertNotEqual(TS.role_of(style, dep, **ctx), TS.REQUIRED,
                                        f"{style}/{dep} became required with {ctx}")


class SystemsMatchTheStyleRegistry(unittest.TestCase):
    def test_one_system_per_style_and_no_others(self):
        self.assertEqual(set(TS.SYSTEMS), set(A.STYLE.values()))

    def test_a_missing_system_refuses_to_load(self):
        data = _raw(); data["systems"].pop("cfd-day")
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(data, TS.PATH)
        self.assertIn("cfd-day", str(cm.exception))

    def test_a_system_for_a_style_that_does_not_exist_refuses_to_load(self):
        data = _raw(); data["systems"]["crypto-lunar"] = dict(data["systems"]["swing"])
        with self.assertRaises(TS.RegistryError) as cm:
            TS._validate(data, TS.PATH)
        self.assertIn("crypto-lunar", str(cm.exception))

    def test_every_system_has_a_version_a_profile_and_a_resolvable_account(self):
        for style in TS.styles():
            sysd = TS.get(style)
            self.assertRegex(sysd["version"], r"^v[1-9][0-9]*$")
            self.assertIn(sysd["dependency_profile"], TS.PROFILES)
            prof = TS.account_profile(style)                  # raises if the account does not exist
            self.assertEqual(AP.snapshot(prof)["venue"], sysd["account_profile"]["venue"])

    def test_a_system_pointing_at_a_nonexistent_account_refuses_to_load(self):
        data = _raw(); data["systems"]["swing"]["account_profile"] = {"venue": "kraken", "environment": "real"}
        with self.assertRaises(Exception):
            TS._validate(data, TS.PATH)

    def test_market_and_timeframe_are_derived_not_declared(self):
        """Nothing in the file says `swing` is crypto 4h -- automation.STYLE does, so the two cannot drift."""
        self.assertNotIn("market", _raw()["systems"]["swing"])
        self.assertEqual((TS.get("swing")["market"], TS.get("swing")["timeframe"]), ("crypto", "4h"))


class RoleResolution(unittest.TestCase):
    def test_every_system_dependency_pair_resolves_to_one_of_the_four(self):
        n = 0
        for style in TS.styles():
            for dep in TS.DEPENDENCIES:
                self.assertIn(TS.role_of(style, dep), TS.ROLES)
                n += 1
        self.assertEqual(n, len(TS.styles()) * len(TS.DEPENDENCIES))

    def test_missing_context_resolves_required_never_optional(self):
        """Rule 2. Asked with nothing, every conditional dependency is required."""
        for dep_id, dep in TS.DEPENDENCIES.items():
            if "only_when" not in dep or dep_id not in TS.declared_required("scalping"):
                continue
            self.assertEqual(TS.role_of("scalping", dep_id), TS.REQUIRED,
                             f"{dep_id} relaxed itself when the caller supplied no context")

    def test_htf_condition_follows_the_setup_row(self):
        on = {"htf": True, "method": "ICT"}
        off = {"htf": False, "method": "ICT"}
        for dep in ("candles.htf", "analytics.htf_bias"):
            self.assertEqual(TS.role_of("scalping", dep, setup=on), TS.REQUIRED)
            self.assertEqual(TS.role_of("scalping", dep, setup=off), TS.OPTIONAL)

    def test_mechanical_analytics_follow_the_runner_method_requires_table(self):
        ict = {"htf": False, "method": "ICT"}
        wy = {"htf": False, "method": "WYCKOFF-BOOK"}
        both = {"htf": False, "method": "COMBINED-BOOK"}
        self.assertEqual(TS.role_of("scalping", "analytics.ict_scan", setup=ict), TS.REQUIRED)
        self.assertEqual(TS.role_of("scalping", "analytics.wyckoff_rules", setup=ict), TS.OPTIONAL)
        self.assertEqual(TS.role_of("scalping", "analytics.wyckoff_rules", setup=wy), TS.REQUIRED)
        self.assertEqual(TS.role_of("scalping", "analytics.ict_scan", setup=wy), TS.OPTIONAL)
        for dep in ("analytics.ict_scan", "analytics.wyckoff_rules"):
            self.assertEqual(TS.role_of("scalping", dep, setup=both), TS.REQUIRED)

    def test_an_unknown_method_is_required_not_relaxed(self):
        self.assertEqual(TS.role_of("scalping", "analytics.ict_scan",
                                    setup={"htf": False, "method": "MOON-PHASE"}), TS.REQUIRED)

    def test_the_analytics_condition_is_the_registrys_requires_table(self):
        """Not a copy of it: the roles above must still hold if methods.json's requires[] is what decides."""
        for method, spec in M.RUNNER_METHODS.items():
            row = {"htf": False, "method": method}
            for dep_id, dep in TS.DEPENDENCIES.items():
                if dep.get("only_when") != "setup.method_requires":
                    continue
                expected = TS.REQUIRED if dep["dimension"] in spec["requires"] else TS.OPTIONAL
                self.assertEqual(TS.role_of("scalping", dep_id, setup=row), expected, f"{method}/{dep_id}")

    def test_a_dimension_with_no_source_on_this_market_can_never_gate_it(self):
        """cfd has no CoinGlass source, so footprint/heatmap are structurally unengageable there -- and the
        predicate must answer that WITHOUT being handed an engaged set, or a cfd system asked with no context
        would fail closed onto a dimension that can never arrive and never trade again. (forex was the same
        case, 2026-09-17..2026-09-27; its three fx-* systems are gone with the market -- instruments.json
        history.)"""
        for style in ("cfd-scalping", "cfd-day", "cfd-swing"):
            for dep in ("methodology.footprint", "methodology.heatmap"):
                self.assertEqual(TS.role_of(style, dep), TS.OPTIONAL, f"{style}/{dep}")
                self.assertEqual(TS.role_of(style, dep, engaged=("footprint", "heatmap")), TS.OPTIONAL)

    def test_engaged_dimensions_are_required_and_merely_analysed_ones_are_not(self):
        self.assertEqual(TS.role_of("scalping", "methodology.ict", engaged=("ict",)), TS.REQUIRED)
        self.assertEqual(TS.role_of("scalping", "methodology.wyckoff", engaged=("ict",)), TS.OPTIONAL)
        self.assertEqual(TS.role_of("scalping", "methodology.wyckoff", engaged=("wyckoff", "ict")), TS.REQUIRED)

    def test_required_never_contains_a_non_required_role(self):
        for style in TS.styles():
            for dep in TS.required(style, setup={"htf": False, "method": "ICT"}, engaged=("ict",)):
                self.assertEqual(TS.role_of(style, dep, setup={"htf": False, "method": "ICT"},
                                            engaged=("ict",)), TS.REQUIRED)

    def test_an_undeclared_dependency_raises_and_says_why(self):
        with self.assertRaises(TS.NotDeclared) as cm:
            TS.role_of("scalping", "analytics.moon_phase")
        self.assertIn("§35", str(cm.exception))


class OnlyRequiredMayGate(unittest.TestCase):
    def test_assert_may_gate_allows_a_required_dependency(self):
        self.assertEqual(TS.assert_may_gate("scalping", "event_risk.calendar"), TS.REQUIRED)

    def test_assert_may_gate_refuses_every_non_gating_role(self):
        for dep in ("display.chart", "display.expected_path", "candles.context",
                    "research.backtest_stability", "research.ranking", "research.journal_review",
                    "display.model_narrative"):
            with self.assertRaises(TS.NotGating, msg=dep) as cm:
                TS.assert_may_gate("scalping", dep)
            self.assertIn("§62", str(cm.exception))

    def test_assert_may_gate_refuses_a_conditionally_relaxed_dependency(self):
        """The case that matters: htf:false means the higher-timeframe read is NOT a gate for that setup, and
        a block site that fires anyway is blocking on an optional input."""
        with self.assertRaises(TS.NotGating):
            TS.assert_may_gate("scalping", "analytics.htf_bias", setup={"htf": False, "method": "ICT"})

    def test_there_is_no_runtime_reclassification(self):
        with self.assertRaises(TS.NotGating) as cm:
            TS.reclassify("scalping", "display.chart", TS.REQUIRED)
        self.assertIn("§36", str(cm.exception))


class QualityGating(unittest.TestCase):
    """§20 x §35: a failing REQUIRED input blocks; a failing non-required one does not."""

    def _states(self, style, **ctx):
        return {d: "FRESH" for d in TS.required(style, **ctx)}

    def test_all_fresh_required_inputs_do_not_gate(self):
        ctx = {"setup": {"htf": False, "method": "ICT"}, "engaged": ("ict",)}
        decision, reasons = TS.gate("scalping", self._states("scalping", **ctx), **ctx)
        self.assertIsNone(decision, reasons)

    def test_a_missing_required_input_blocks_entry(self):
        ctx = {"setup": {"htf": False, "method": "ICT"}, "engaged": ("ict",)}
        states = self._states("scalping", **ctx); states["event_risk.calendar"] = "MISSING"
        decision, reasons = TS.gate("scalping", states, **ctx)
        # MISSING -> NO_TRADE is quality.py's documented mapping ("nothing to wait for"); what §35 owns is
        # that the calendar is in the required set at all, so a missing one produces a decision instead of None.
        self.assertEqual(decision, "NO_TRADE")
        self.assertTrue(any("event_risk.calendar" in r for r in reasons))

    def test_a_required_input_nobody_reported_is_missing_not_absent(self):
        ctx = {"setup": {"htf": False, "method": "ICT"}, "engaged": ("ict",)}
        states = self._states("scalping", **ctx); del states["candles.entry"]
        decision, reasons = TS.gate("scalping", states, **ctx)
        self.assertEqual(decision, "NO_TRADE")
        self.assertTrue(any("candles.entry" in r and "MISSING" in r for r in reasons))

    def test_a_broken_optional_input_does_not_block(self):
        ctx = {"setup": {"htf": False, "method": "ICT"}, "engaged": ("ict",)}
        states = self._states("scalping", **ctx)
        states.update({"display.chart": "MISSING", "research.ranking": "INVALID",
                       "methodology.wyckoff": "STALE", "candles.context": "MISSING"})
        decision, _ = TS.gate("scalping", states, **ctx)
        self.assertIsNone(decision, "an optional / visualization / research input gated an entry -- §62")


class WiredIntoTheLivePath(unittest.TestCase):
    """A registry nothing reads is prose in a different file extension."""

    BLOCK_SITES = re.compile(r'blocked_on\(\s*"([^"]+)"')

    def test_the_runner_routes_its_dependency_blocks_through_the_classification(self):
        deps = set(self.BLOCK_SITES.findall(RUNNER_SRC))
        self.assertTrue(deps, "no blocked_on() call sites found in strategy-runner.py")
        for dep in deps:
            self.assertIn(dep, TS.DEPENDENCIES, f"strategy-runner.py blocks on undeclared {dep!r}")

    def test_the_runner_blocks_on_each_of_the_four_dependency_families_it_has(self):
        deps = set(self.BLOCK_SITES.findall(RUNNER_SRC))
        for expected in ("account.profile_rules", "event_risk.calendar", "venue.reconciliation",
                         "analytics.htf_bias", "risk.net_rr"):
            self.assertIn(expected, deps)

    def test_every_real_pilot_setup_row_resolves_to_a_trading_system(self):
        """Regression: pilot rows spell timeframes `1H`/`4H` and automation.STYLE spells them `1h`/`4h`, so
        the first wiring left three of six setups with no governing system."""
        rows = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")))["setups"]
        self.assertTrue(rows)
        for row in rows:
            sysd = TS.for_setup(row)
            self.assertEqual(sysd["market"], row["market"])
            self.assertEqual(sysd["horizon"], row["horizon"])

    def test_market_timeframe_lookup_folds_the_two_timeframe_spellings(self):
        self.assertEqual(TS.for_market_tf("crypto", "1H")["id"], TS.for_market_tf("crypto", "1h")["id"])
        with self.assertRaises(KeyError):
            TS.for_market_tf("crypto", "3m")

    def test_the_model_narrative_is_not_read_by_the_order_path(self):
        """It is classified OPTIONAL_FOR_ANALYSIS on the claim that the runner never opens it. Check it."""
        self.assertNotIn("narrative", RUNNER_SRC)
        self.assertNotIn("anchors", RUNNER_SRC)

    def test_the_configuration_snapshot_records_the_declared_dependencies(self):
        spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts",
                                                                         "backtest-methods.py"))
        bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
        import snapshot
        snap = snapshot.backtest_config_snapshot(bt, timeframes=["15m", "1H"], methods={"ICT"},
                                                 market="crypto")["fields"]
        self.assertEqual(snap["trading_system_version"]["systems"], {"15m": "scalping", "1H": "day"})
        self.assertIn("candles.entry", snap["required_evidence"]["per_timeframe"]["15m"])
        self.assertIn("analytics.ict_scan", snap["required_analytics"]["per_timeframe"]["15m"])
        # §38: what the system declares required and this engine never applies is RECORDED, not smoothed over.
        self.assertIn("event_risk.calendar", snap["required_evidence"]["declared_but_not_applied_by_this_engine"])

    def test_a_snapshot_with_no_market_says_so_instead_of_guessing_a_system(self):
        spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts",
                                                                         "backtest-methods.py"))
        bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
        import snapshot
        snap = snapshot.backtest_config_snapshot(bt, timeframes=["15m"], methods={"ICT"})["fields"]
        self.assertIn("unavailable", snap["required_evidence"])
        self.assertIn("§35", snap["required_evidence"]["owner"])
        self.assertIn("no market", snap["required_evidence"]["unavailable"])


class Composition(unittest.TestCase):
    """§35's checklist: Market + Instrument + Market Type + Session + Methodology + Setup + Entry + Exit +
    Risk + Account Profile + Custom Constraints + Event Risk + Required Data."""

    def test_describe_covers_every_part_of_the_composition(self):
        # The system is CHOSEN from the current selection, not named. Which systems have rows changes with
        # every re-rank, and naming one turns a selection change into a test failure that says nothing about
        # describe(). 2026-09-19 made that concrete: correcting the ICT fill assumption emptied 11 of 12
        # horizon cells, and "scalping" -- named here since this test was written -- stopped having rows.
        style = next((st for st in TS.styles() if TS.setups(st)), None)
        if style is None:
            self.skipTest("no trading system currently has a selected setup")
        d = TS.describe(style)
        for field in ("market", "instruments", "market_types", "session", "methodology", "setups",
                      "account_profile", "risk", "custom_constraints", "event_risk", "dependencies",
                      "version"):
            self.assertIn(field, d)
        self.assertTrue(d["setups"], f"{style} has pilot rows; describe() lost them")
        for s in d["setups"]:
            self.assertIn(s["entry"], {"market", "limit"})
            self.assertIn("mgmt", s["exit"])

    def test_composition_is_resolved_from_the_owning_registries_not_copied(self):
        import instruments as I
        d = TS.describe("cfd-scalping")
        # research-only fund-search symbols are not reported as analysable here (owner 2026-10-01)
        import instruments as _I
        self.assertEqual(d["instruments"]["analysis"], _I.live_analysis("cfd"))
        self.assertTrue(set(_I.research_only("cfd")).isdisjoint(d["instruments"]["analysis"]))
        self.assertEqual(d["instruments"]["analysis"], list(I.live_analysis("cfd")))
        self.assertEqual(d["instruments"]["execution"], list(I.execution("cfd")))
        self.assertEqual(d["market_types"], list(I.market_types("cfd")))
        raw = _raw()["systems"]["cfd-scalping"]
        self.assertNotIn("instruments", raw)
        self.assertNotIn("risk", raw)

    def test_a_system_with_no_setup_row_reports_no_execution_venue_rather_than_claiming_one(self):
        # Pick a system that genuinely has no selected setup right now rather than naming one: which
        # systems are covered changes with every re-rank (2026-09-19: prop-pass selection covers
        # crypto-scalping / cfd-scalping / cfd-swing and nothing else).
        empty = next((st for st in TS.styles() if not TS.setups(st)), None)
        if empty is None:
            self.skipTest("every trading system currently has a selected setup")
        self.assertEqual(TS.execution_venues(empty), ())
        # And the converse, also chosen rather than named: a system that DOES have a row names its venue.
        filled = next((st for st in TS.styles() if TS.setups(st)), None)
        if filled is None:
            self.skipTest("no trading system currently has a selected setup")
        self.assertTrue(TS.execution_venues(filled),
                        f"{filled} has setup rows but reports no execution venue")

    def test_the_snapshot_view_names_the_version_and_both_required_sets(self):
        snap = TS.snapshot("scalping", setup={"htf": True, "method": "COMBINED-BOOK"}, engaged=("ict",))
        self.assertEqual(snap["trading_system_version"], "v1")
        self.assertIn("candles.htf", snap["resolved_required"])
        self.assertIn("methodology.wyckoff", snap["declared_required"])
        self.assertNotIn("methodology.wyckoff", snap["resolved_required"])


if __name__ == "__main__":
    unittest.main()


class TheGateRunsOnTheRealOrderPath(unittest.TestCase):
    """The half that matters. A classification nothing consults is a table; these drive the runner's real
    `tick()` and prove (a) a blocked entry's reason travelled through the classification, and (b) the check
    FIRES -- by telling the registry that the event calendar is merely optional here and watching the same
    tick refuse to block on it. Harness shape borrowed from test_account_profile.AccountLimitsOnTheOrderPath,
    which drives the same function for §33."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts",
                                                                        "strategy-runner.py"))
        cls.sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.sr)

    def _tick(self, *, blackout="FOMC 14:00Z"):
        import datetime
        import tempfile
        sr = self.sr
        sig = {"time": "2026-09-18T00:00:00Z", "mss_time": "2026-09-18T00:00:00Z", "entry": 100.0,
               "stop": 99.0, "target": 130.0, "r_planned": 30.0, "vol_type": 1, "side": "long"}
        setup = {"id": "t", "market": "crypto", "horizon": "scalping", "symbols": ["BTCUSDT"], "tf": "15m",
                 "method": "ICT", "htf": False, "mgmt": "none", "execution": "futures"}
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]},
                           "cfd": {"enabled": False, "instruments": []}},
               "execution": {"environment": "demo"}}
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        state = {"started": "2026-01-01T00:00:00Z", "positions": {}, "pending": {}, "seen": [],
                 "day": today, "trades_today": {}, "errors": 0, "halted": None, "last_tick": None,
                 "equity_basis": "equity",
                 "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0}
                            for v in sr.VENUES}}
        tmps = []

        def tmp(obj):
            fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            json.dump(obj, fh); fh.close(); tmps.append(fh.name); return fh.name

        cfg_p, sel_p, state_p = tmp(cfg), tmp({"setups": [setup]}), tmp(state)
        keys = ("AUTOMATION_CONFIG", "SELECTION", "STATE", "STOP", "automation_gate", "fetch_candles",
                "setups", "htf_pass", "event_blackout", "log", "due", "allowed_methods", "place_limit",
                "place_market", "manage_position", "manage_pending", "min_notional")
        old = {k: getattr(sr, k) for k in keys}
        logs = []
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_p, sel_p, state_p
        sr.STOP = state_p + ".STOP"
        sr.automation_gate = lambda: None
        sr.fetch_candles = lambda *a, **k: [{"time": "2026-09-18T00:00:00Z", "open": 100.0, "high": 101.0,
                                             "low": 99.0, "close": 100.0, "volume": 1.0} for _ in range(400)]
        sr.setups = lambda *a, **k: [dict(sig)]
        sr.htf_pass = lambda *a, **k: True
        sr.event_blackout = lambda *a, **k: blackout
        sr.due = lambda *a, **k: True
        sr.allowed_methods = lambda *a, **k: ("ICT",)
        sr.place_limit = lambda *a, **k: None
        sr.place_market = lambda *a, **k: None
        sr.manage_position = lambda *a, **k: None
        sr.manage_pending = lambda *a, **k: ("waiting", None, None, None)
        # §36 step 12 now runs the sizing refusal inside the tick. Stubbed so the harness tests the
        # gate it means to test rather than whether the exchange answered a filters query.
        sr.min_notional = lambda *a, **k: 5.0
        sr.log = lambda kind, **kw: logs.append((kind, kw))
        old_load, sr.ER.load = sr.ER.load, FC.fresh_load    # the §36 step-3 precheck reads the calendar itself
        try:
            sr.tick(live=False, tick_time=sr.now(), ignore_gate=True)
        finally:
            sr.ER.load = old_load
            for k, v in old.items():
                setattr(sr, k, v)
            for p in tmps:
                os.unlink(p)
        return [kw for kind, kw in logs if kind == "signal"]

    def test_an_event_blackout_blocks_through_the_classification(self):
        rows = self._tick()
        self.assertTrue(rows, "the harness produced no signal row")
        self.assertFalse(rows[0]["ok"])
        self.assertTrue(any("blackout" in r for r in rows[0]["reasons"]), rows[0]["reasons"])

    def test_the_same_tick_refuses_to_block_once_that_dependency_is_not_a_gate(self):
        """The mutation. If `blocked_on` were decorative, downgrading the calendar's role would change
        nothing and the tick would block exactly as before. It must raise instead."""
        real = TS.role_of

        def downgraded(style, dep, **ctx):
            return TS.OPTIONAL if dep == "event_risk.calendar" else real(style, dep, **ctx)

        TS.role_of = downgraded
        try:
            with self.assertRaises(TS.NotGating) as cm:
                self._tick()
            self.assertIn("event_risk.calendar", str(cm.exception))
        finally:
            TS.role_of = real

    def test_a_clear_signal_still_passes_with_the_check_in_place(self):
        rows = self._tick(blackout=None)
        self.assertTrue(rows)
        self.assertTrue(rows[0]["ok"], rows[0]["reasons"])
