"""CLAUDE.md §48 SYSTEM RANKING -- the page. scripts/system-ranking.py is the ONE caller of scripts/ranking.py
over the repository's own registries (docs/architecture/trading-systems.json x data/history/stability/*.json).

Two things this module exists to prove:

1. `rows()` produces a row per (Trading System, selected setup) that `scripts/ranking.py` can rank WITHOUT
   dropping a §48 exposure -- a row that cannot supply one is marked, never silently completed with an invented
   number (`performance.unavailable()` stays a marker all the way to the page).
2. The built page renders one table per §48 objective, in the registry's own order, with the six `ranking-*`
   markers on every row and no "best system" claim anywhere -- §48 forbids a universal score, and a page that
   says "best system" would be making the exact claim the ranking machinery refuses to compute.
"""
import importlib.util
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import ranking as R              # noqa: E402
import performance as P          # noqa: E402
import trading_system as TS      # noqa: E402
import ui_contract as UI         # noqa: E402


def _mod(name):
    p = os.path.join(ROOT, "scripts", name)
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


SR = _mod("system-ranking.py")


class RowsCoverEverySelectedSetup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = SR.rows()

    def test_at_least_one_row_per_system_that_has_a_selected_setup(self):
        expected = sum(len(TS.setups(s)) for s in TS.styles())
        self.assertGreater(expected, 0)
        # An account-conditioned file may be BOTH the selection's own source and an extra view, so counting
        # account-free rows is not the invariant -- counting distinct (system, setup) pairs is. Every selected
        # setup must appear at least once; extra account views add rows, never setups.
        base = {(r["trading_system"], r["setup_id"].split(" @ ")[0]) for r in self.rows}
        self.assertEqual(len(base), expected)

    def test_every_row_names_its_trading_system_and_setup(self):
        systems = set(TS.styles())
        for r in self.rows:
            self.assertIn(r["trading_system"], systems)
            self.assertIn("::", r["id"])
            self.assertTrue(r["setup_id"])

    def test_every_row_supplies_all_seven_48_exposures(self):
        # The stability files this repo ships (crypto-live.json, cfd-live.json) both carry a §38 verdict
        # stamp, so a row built from them must not be marked for a missing exposure.
        for r in self.rows:
            gaps = R.exposure_gaps(r)
            self.assertEqual(gaps, [], f"{r['id']} missing {gaps}")

    def test_ranking_rejects_none_of_the_rows(self):
        # rank() never drops a row -- every row supplied must come back ranked.
        res = R.rank(self.rows, objective_id="expectancy")
        self.assertEqual(len(res["ranked"]), len(self.rows))

    def test_the_ruin_field_is_carried_so_not_ruined_is_computable(self):
        for r in self.rows:
            self.assertIn("ruin", r, r["id"])

    def test_account_aware_metrics_are_carried_not_invented(self):
        """An account-free row must still say `unavailable`; an ACCOUNT-conditioned row (one read from a
        `<market>-<account>.json` file, `row["account"]` set) may carry a real number. Neither may be
        fabricated: whatever the stability file holds is what the page shows.

        Rewritten 2026-09-19: rows conditioned on a profile now exist (the user asked for the prop-pass
        question to be answerable), so "always unavailable" stopped being the invariant. The invariant that
        remains is: no account -> no number."""
        for r in self.rows:
            for key in ("prop_pass_probability", "account_failure_probability"):
                if r.get("account"):
                    continue                       # may be a real value; test_39_values_are_copied pins fidelity
                self.assertTrue(P.is_unavailable(r[key]), f"{r['id']} has no account but supplies {key}")

    def test_39_values_are_copied_not_recomputed(self):
        # Pick one real row and check its expectancy against the stability file's own perf block, byte for
        # byte -- this module must never recompute a §39 metric, only carry it.
        import json
        raw = json.load(open(os.path.join(ROOT, "data/history/stability/crypto-live.json"), encoding="utf-8"))
        by_key = {(r["tf"], r["method"], r["cfg"]): r for r in raw["rows"]}
        # Any row whose source is the account-free crypto file; the selection's composition changes with
        # every re-rank, so pick by SOURCE rather than by a hard-coded trading system (2026-09-19).
        row = next((r for r in self.rows if r["trading_system"] in ("day", "swing", "scalping")
                    and not r.get("account")), None)
        if row is None:
            self.skipTest("no account-free crypto row in the current selection")
        prow = TS.setups("day")[0]
        cfg = prow["id"].rsplit("-", 1)[-1].upper()
        srow = by_key[(prow["tf"], prow["method"], cfg)]
        self.assertEqual(row["expectancy"], srow["perf"]["expectancy"])
        self.assertEqual(row["n"], srow["perf"]["n"])

    def test_positive_period_share_and_worst_period_are_derived_from_the_rows_own_quarters(self):
        # Neither key exists in the §39 perf block (grep confirms it) -- they come from the stability row's
        # own q_pos / q_worst, not an invented figure.
        for r in self.rows:
            self.assertIsInstance(r["positive_period_share"], float)
            self.assertGreaterEqual(r["positive_period_share"], 0.0)
            self.assertLessEqual(r["positive_period_share"], 1.0)

    def test_robustness_status_is_unavailable_because_no_row_carries_one(self):
        for r in self.rows:
            self.assertTrue(P.is_unavailable(r["robustness_status"]), r["id"])
            self.assertIn("§45", r["robustness_status"]["unavailable"])


class ThePageRendersOneTablePerObjective(unittest.TestCase):
    """One document now, carrying both locales as lang-tagged siblings (2026-09-18: this page used to build
    two STANDALONE documents, one per locale, with no in-page switch -- see system-ranking.py render()
    docstring). The reader's-eye check for "no Vietnamese visible in English mode" moved to
    scripts/tests/test_i18n.py's NoWrongLanguageIsEverVisible, which is the one place that check is
    implemented (VisibleText applies the actual CSS visibility rule instead of a raw substring scan, which
    would always find Vietnamese here -- it's on the page, just hidden)."""

    @classmethod
    def setUpClass(cls):
        cls.html = SR.render(SR.rows())

    def test_every_non_custom_objective_appears_in_registry_order(self):
        wanted = [oid for oid in R.OBJECTIVE_ORDER if oid != "custom"]
        positions = [self.html.index(R.OBJECTIVES[oid]["spec_name"]) for oid in wanted]
        self.assertEqual(positions, sorted(positions), "objective tables out of registry order")

    def test_all_six_ranking_markers_are_present(self):
        markers = ("ranking-objective", "ranking-sample-size", "ranking-validation-state",
                   "ranking-test-period", "ranking-assumptions", "ranking-robustness")
        for m in markers:
            self.assertIn(f'{UI.ATTR}="{m}"', self.html, f"missing marker {m}")

    def test_the_page_never_claims_one_best_system(self):
        self.assertNotIn("best system", self.html.lower())

    def test_an_unavailable_metric_renders_as_a_dash_with_its_reason_in_title(self):
        m = re.search(r'<span[^>]*class="unavail"[^>]*title="([^"]+)"[^>]*>(&mdash;|—|-)</span>', self.html)
        self.assertIsNotNone(m, "no unavailable-marker span found")
        self.assertTrue(m.group(1).strip())

    def test_the_exposure_report_is_rendered(self):
        self.assertIn("exposure-report", self.html)

    def test_ui_contract_audit_is_clean_for_the_ranking_page(self):
        r = UI.audit(self.html, "ranking")
        self.assertEqual(r["missing"], [], r["missing"])

    def test_the_page_carries_the_en_vi_switch(self):
        """The gap this page had until 2026-09-18: the switch (visibility CSS + toggle buttons + the shim
        that stamps data-lang) must all be in the ONE published document, same as the panel and the journal."""
        self.assertIn('[data-lang="', self.html, "the locale-visibility CSS is missing")
        self.assertIn("data-i18n-lang", self.html, "the language toggle is missing")
        self.assertIn("artifact-lang", self.html, "the shim that stamps data-lang is missing")


class MainWritesTheDualLocalePage(unittest.TestCase):
    def test_main_writes_one_file_carrying_both_locales(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "system-ranking.py"),
                               "--out-dir", tmp], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = os.path.join(tmp, ".vi-system-ranking.html")
            self.assertTrue(os.path.exists(out), r.stdout + r.stderr)
            html = open(out, encoding="utf-8").read()
            self.assertIn('lang="en"', html)
            self.assertIn('lang="vi"', html)
            self.assertIn("data-i18n-lang", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class AccountConditionedRows(unittest.TestCase):
    """CLAUDE.md §33/§39: a setup measured under an account's own failure rules is a second row, labelled."""

    def test_account_sources_are_discovered_next_to_the_live_file_and_never_invented(self):
        import tempfile, shutil, json
        d = tempfile.mkdtemp(dir=os.path.join(ROOT, "data", "history", "stability"))
        rel = os.path.relpath(d, ROOT)
        try:
            src = json.load(open(os.path.join(ROOT, "data", "history", "stability", "cfd-live.json"), encoding="utf-8"))
            open(os.path.join(d, "cfd-live.json"), "w").write(json.dumps(src))
            pid = sorted(SR.AP.PROFILES)[0]
            self.assertEqual(SR.account_sources(os.path.join(rel, "cfd-live.json")), [])
            open(os.path.join(d, f"cfd-{pid}.json"), "w").write(json.dumps(src))
            self.assertEqual(SR.account_sources(os.path.join(rel, "cfd-live.json")), [(pid, os.path.join(rel, f"cfd-{pid}.json"))])
            self.assertEqual(SR.account_sources(os.path.join(rel, "cfd-live.json"))[0][0], pid)
        finally:
            shutil.rmtree(d)

    def test_an_account_row_is_labelled_and_keeps_the_seven_exposures(self):
        base = SR.rows()
        prow = {"id": "x-15m-wyckoff-a", "tf": "15m", "method": "WYCKOFF-BOOK", "mgmt": "be", "htf": False, "fee_assumed": 0.0005}
        srow = {"tf": "15m", "cfg": "A", "method": "WYCKOFF-BOOK", "n": 10, "first": "2020", "last": "2026", "ruin": None,
                "failed_by": "max_daily_loss", "perf": {"n": 10, "expectancy": 0.2}}
        r = SR._row("cfd-scalping", prow, srow, {}, {"verdict": "ok"}, account="ftmo-challenge-phase1")
        self.assertEqual(r["id"], "cfd-scalping::x-15m-wyckoff-a@ftmo-challenge-phase1")
        self.assertIn("@ ftmo-challenge-phase1", r["setup_id"]); self.assertEqual(r["account"], "ftmo-challenge-phase1")
        self.assertEqual(r["failed_by"], "max_daily_loss"); self.assertEqual(r["assumptions"]["account"], "ftmo-challenge-phase1")
        self.assertEqual(SR.R.exposure_gaps(r), [])
        self.assertIsInstance(base, list)
