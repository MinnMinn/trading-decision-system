"""The planned-R:R floor and the per-trade risk ceiling.

User decision 2026-09-13: every entry must plan at least 3R, and the per-trade risk ceiling rises from 1 % to 3 %.

Why these two belong in one test file: they are one decision. Measured over the last year on the nine crypto
instruments (215 ICT 15m setups, fee 0.05 %/side), the R:R floor is what makes the higher risk survivable --
without it 5 % risk drew the account down 63 % and 3 % drew it down 44 %. 5 % was rejected outright because the
live EQUITY_HALT_FRAC guard (-15 % from start) would have fired on 2025-10-12 and halted the pilot permanently,
which the backtest does not model; 3 % never trips it. Evidence: docs/backtests/2026-09-13-rr-floor-and-risk.md.

The floor has ONE source -- docs/architecture/analysis-params.json project_defined.ict.min_rr -- so a future change
is one edit. These tests exist because before today that value was read only to print an advisory note
(ict-scan.py:359) while every decision path hardcoded min_rr=0.0, so 38 % of the setups the system took planned
less than 2R and the worst planned 0.00R.
"""
import importlib.util, json, os, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARAMS = os.path.join(ROOT, "docs", "architecture", "analysis-params.json")


def _load(fname, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class MinRRSource(unittest.TestCase):
    def test_params_file_carries_the_floor(self):
        v = json.load(open(PARAMS, encoding="utf-8"))["project_defined"]["ict"]["min_rr"]["value"]
        self.assertEqual(v, 3.0, "the R:R floor lives in analysis-params.json and nowhere else")

    def test_basis_records_that_this_is_a_user_override_of_the_sourced_2R(self):
        """knowledge/06 §3.1 rule 23 says 2R. 3R is stricter than the source, so the basis must say whose call it
        is -- otherwise a later reader 'corrects' it back to 2.0 to match the citation."""
        basis = json.load(open(PARAMS, encoding="utf-8"))["project_defined"]["ict"]["min_rr"]["_basis"]
        self.assertIn("2R", basis)
        low = basis.lower()
        self.assertTrue("user decision" in low or "quyết định" in low or "override" in low, basis)


class BacktestReadsTheFloor(unittest.TestCase):
    def setUp(self):
        self.bt = _load("backtest-methods.py", "bt")

    def test_opts_default_is_the_params_value_not_zero(self):
        self.assertEqual(self.bt.OPTS["min_rr"], 3.0)

    def test_cli_default_is_the_params_value_too(self):
        """OPTS defaulting correctly is not enough: main() overwrites min_rr from argparse on every run, so a
        --min-rr default of 0.0 would silently switch the filter back off for every command-line backtest."""
        import argparse, contextlib, io
        p = argparse.ArgumentParser()
        # re-read the flag's default straight out of the source: main() builds its parser inline
        src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()
        i = src.index('"--min-rr"')
        line = src[i:src.index("\n", i)]
        self.assertNotIn("default=0.0", line, f"--min-rr still defaults to 0.0: {line}")
        self.assertIn("MIN_RR", line, f"--min-rr must default to the params value: {line}")

    def test_account_risk_matches_the_live_ceiling(self):
        """simulate() sizes at bt.RISK. If it drifts below the runner's ceiling the backtest understates the
        drawdown the pilot would actually take; if above, it overstates the return. Same number or the report is
        measuring a different account than the one that trades."""
        runner = _load("strategy-runner.py", "sr")
        self.assertEqual(self.bt.RISK, runner.RISK_CEILING)


class RiskCeiling(unittest.TestCase):
    def setUp(self):
        self.sr = _load("strategy-runner.py", "sr")

    def test_ceiling_is_three_percent(self):
        self.assertEqual(self.sr.RISK_CEILING, 0.03)

    def test_risk_pct_is_still_clamped_to_the_ceiling(self):
        """Raising the ceiling must not remove the clamp -- a typo in config/env (0.3 for 3 %) would otherwise
        size every trade at 30 % of equity."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("min(RISK_CEILING", src)
        self.assertLessEqual(self.sr.RISK_PCT, self.sr.RISK_CEILING)

    def test_there_is_exactly_one_ceiling(self):
        """The cap lives in TWO layers -- trading_env.load_env() clamps the file value, then strategy-runner
        clamps again. Defence in depth is right, but two COPIES of the number are not: on 2026-09-13 the runner's
        copy was raised to 0.03 and trading_env's was left at 0.01, so config/env's 0.03 was silently cut back to
        1 % and the runner reported a 3 % ceiling it could never actually reach. One number, read by both."""
        import importlib
        te = importlib.import_module("trading_env")
        self.assertEqual(self.sr.RISK_CEILING, te.MAX_RISK_PCT)

    def test_a_three_percent_env_value_survives_the_clamp(self):
        """The end-to-end assertion the first version of this file was missing: `RISK_PCT <= RISK_CEILING` passes
        trivially when RISK_PCT is 0.01 and the ceiling is 0.03. Assert that the ceiling is actually REACHABLE."""
        import importlib
        te = importlib.import_module("trading_env")
        clamped = min(0.03, te.MAX_RISK_PCT)
        self.assertEqual(clamped, 0.03, "a config/env value of 0.03 is still being cut below 3 %")

    def test_equity_halt_is_untouched(self):
        """The -15 % halt is what makes 3 % survivable (it is why 5 % was rejected). Raising the risk without it
        is a different, unapproved decision."""
        self.assertEqual(self.sr.EQUITY_HALT_FRAC, 0.85)


class LiveGate(unittest.TestCase):
    def setUp(self):
        self.sr = _load("strategy-runner.py", "sr")

    def test_passes_a_signal_at_or_above_the_floor(self):
        self.assertIsNone(self.sr.rr_reason({"r_planned": 3.0}))
        self.assertIsNone(self.sr.rr_reason({"r_planned": 7.4}))

    def test_refuses_a_signal_below_the_floor(self):
        for rr in (0.0, 1.9, 2.99):
            self.assertIsNotNone(self.sr.rr_reason({"r_planned": rr}), f"{rr}R should be refused")

    def test_fails_closed_on_an_uncomputable_rr(self):
        """An R:R that could not be computed is not permission to trade -- same rule as the htf gate. NaN is the
        one that bites: `nan < 3.0` is False, so a plain comparison would OPEN the gate."""
        for bad in ({}, {"r_planned": None}, {"r_planned": "3"}, {"r_planned": float("nan")}):
            self.assertIsNotNone(self.sr.rr_reason(bad), f"{bad} should be refused")

    def test_the_gate_is_wired_into_the_signal_block(self):
        """A correct rr_reason() that nothing calls blocks nothing."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("rr_reason(sig)", src)

    def test_no_decision_path_pins_the_floor_to_zero(self):
        """Every script whose output a live order eventually depends on must measure the population the live gate
        actually takes. stability-report feeds rank-setups, which writes pilot-top5.json; ict-flags-1y --apply
        writes ict_disp/ict_pd/std_origin INTO pilot-top5.json directly (and rank-setups carries those keys over
        on rewrite), so it is a decision path too -- it was missed on the first pass of this change.

        A script that genuinely wants the unfiltered population may still pass --min-rr 0 on the command line;
        what is banned is pinning it in code where nobody sees it.

        Matched against OPTS mutations only, not the whole file: these scripts discuss `min_rr=0.0` in prose
        (docstrings, comments) precisely because it was the bug, and banning the string outright would make
        documenting the fix impossible.
        """
        import re
        pinned = re.compile(r"OPTS(?:\.update\(|\[).*min_rr\s*=\s*0(?:\.0+)?\b")
        for fname in ("stability-report.py", "ict-flags-1y.py", "strategy-runner.py", "backtest-methods.py"):
            for i, line in enumerate(open(os.path.join(ROOT, "scripts", fname), encoding="utf-8"), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(pinned.search(line), f"{fname}:{i} pins the R:R floor to zero: {line.strip()}")


class OneFloorReaderForBothOrderPaths(unittest.TestCase):
    """Security review 2026-09-13 (F1, HIGH): the first pass gave the legacy engine (deleted 2026-09-13) a strict
    validating reader while backtest-methods.py -- and therefore strategy-runner.py, which does
    `MIN_RR = bt.MIN_RR` -- kept `_ICT.get("min_rr", {}).get("value", 2.0)`. The two live order paths then had
    OPPOSITE fail modes on one config key: drop or rename project_defined.ict.min_rr and the legacy engine
    refused every entry while the runner silently reverted to a 2R floor and kept sizing at RISK_CEILING = 3 %
    -- exactly the 3 %/2R pair this project's own evidence rejected. One reader, one validation, read by every
    path. The legacy engine is gone now (one-system collapse, 2026-09-13); this class keeps proving there is
    exactly one reader for the remaining path.
    """

    def setUp(self):
        import importlib
        self.te = importlib.import_module("trading_env")
        self.bt = _load("backtest-methods.py", "bt3")
        self.sr = _load("strategy-runner.py", "sr2")

    def test_every_path_reports_the_same_floor(self):
        v = json.load(open(PARAMS, encoding="utf-8"))["project_defined"]["ict"]["min_rr"]["value"]
        for name, got in (("trading_env", self.te.min_rr()), ("backtest", self.bt.MIN_RR),
                          ("strategy-runner", self.sr.MIN_RR)):
            self.assertEqual(got, v, f"{name} disagrees with analysis-params.json")

    def test_no_path_keeps_a_two_r_fallback(self):
        """`.get("value", 2.0)` is the exact shape of the bug: a silent revert to the superseded floor."""
        import re
        bad = re.compile(r'min_rr.*\.get\(\s*"value"\s*,\s*[0-9]')
        for fname in ("backtest-methods.py", "strategy-runner.py", "trading_env.py", "ict-scan.py"):
            for i, line in enumerate(open(os.path.join(ROOT, "scripts", fname), encoding="utf-8"), 1):
                if line.lstrip().startswith("#"):
                    continue
                self.assertIsNone(bad.search(line), f"{fname}:{i} falls back to a literal floor: {line.strip()}")

    def test_the_reader_refuses_every_invalid_value(self):
        import tempfile
        for value in (None, 0, -3, "3", True, float("nan")):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
                json.dump({"project_defined": {"ict": {"min_rr": {"value": value}}}}, fh)
            self.assertIsNone(self.te.min_rr(fh.name), f"value {value!r} must not be accepted as a floor")
            os.unlink(fh.name)

    def test_the_reader_refuses_a_missing_key_and_a_missing_file(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump({"project_defined": {"ict": {}}}, fh)
        self.assertIsNone(self.te.min_rr(fh.name))
        os.unlink(fh.name)
        self.assertIsNone(self.te.min_rr(os.path.join(ROOT, "no", "such", "params.json")))

    def test_the_runner_gate_fails_closed_on_an_unreadable_floor(self):
        """demo-pilot got this branch on the first pass; the runner did not, and the runner is the path that
        actually runs under the current top5 profile."""
        saved = self.sr.MIN_RR
        try:
            self.sr.MIN_RR = None
            self.assertIsNotNone(self.sr.rr_reason({"r_planned": 99.0}))
        finally:
            self.sr.MIN_RR = saved


class BacktestReportHonesty(unittest.TestCase):
    """The report is the artifact a human reads to make the risk decision. Three ways it misreported itself."""

    def setUp(self):
        self.bt = _load("backtest-methods.py", "bt2")
        self.src = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()

    def test_the_report_does_not_claim_a_risk_it_does_not_use(self):
        """The title was the fixed string "rủi ro 1%/lệnh" while RISK = 0.03, so every equity figure in the
        report was a 3 % curve labelled 1 %."""
        self.assertNotIn("rủi ro 1%/lệnh", self.src)
        self.assertNotIn("1% risk per trade", self.src)

    def test_no_stale_risk_literal_survives_anywhere_in_the_file(self):
        """Security review 2026-09-13 (F5): the first pass banned only the title and the module-docstring
        phrasing, so a THIRD copy survived at simulate()'s docstring ("Chronological 1%-risk compounding
        account") -- in the very function a reviewer opens to audit the risk decision. The floor/ceiling numbers
        belong in RISK, never restated in prose."""
        for phrase in ("1%-risk", "1% risk", "rủi ro 1 %", "0.5% per half"):
            self.assertNotIn(phrase, self.src, f"stale risk literal in prose: {phrase!r}")

    def test_period_keys_are_the_union_across_methods_not_one_method_s(self):
        """The year/quarter/month tables took their row labels from res["WYCKOFF"]. WYCKOFF ruins in 2023 on this
        data, so its period list stops there -- and 2024 and 2025 vanished from the table for EVERY method,
        including the one that was actually profitable."""
        res = {"WYCKOFF": {"years": [("2023", -90.1)]},
               "ICT": {"years": [("2023", 42.7), ("2024", 109.1), ("2025", 60.3), ("2026", 103.7)]}}
        self.assertEqual(self.bt.period_keys(res, "years"), ["2023", "2024", "2025", "2026"])

    def test_the_caveats_render_the_account_size(self):
        """The line was a plain string, not an f-string, so the report printed the literal `${START:,.0f}`.

        Asserted on the quote PREFIX, not on the text: `"- Tài khoản ... ${START` is a substring of the fixed
        version too (the `"` belongs to `f"`), so a text search cannot tell the two apart -- the first version
        of this test passed against the bug it was meant to catch."""
        hits = [ln.strip() for ln in self.src.splitlines() if "Tài khoản bắt đầu ${START" in ln]
        self.assertEqual(len(hits), 1, "expected exactly one caveats line mentioning START")
        self.assertTrue(hits[0].startswith('f"'), f"caveats line is not an f-string: {hits[0][:60]}")


if __name__ == "__main__":
    unittest.main()
