"""Audit round 4c / ADR 0008 (owner decision 2026-09-26): the pilot's systems are enabled by ABSOLUTE per-horizon
criteria (docs/architecture/selection-criteria.json), on the in-sample window AND the held-out OOS window, and the
old count-named selection concept is gone from the repository.

Covered here:
  * every criterion's boundary (== threshold passes; one step beyond fails), per horizon, thresholds read from
    the file (never re-typed here)
  * a missing / null / non-numeric / non-finite input FAILS with reason "missing" (CLAUDE.md §20)
  * a criteria file with a key the gate cannot evaluate, or a horizon with no gate, is refused
  * IS-pass/OOS-fail and OOS-pass/IS-fail are both disabled
  * every passing row is enabled (no cap), and no row's decision depends on another row (no runner-up
    substitution)
  * a horizon with zero passing rows is empty and the report says so in words
  * the 10 % scalping target is reported and never gates
  * data-sufficiency preconditions can only disable
  * the OOS window is marked EXPOSED and the experiment budget is recorded
  * the runner trades nothing when the selection file is absent (no built-in default)
  * `/automation on` has exactly one selection path; any `setup ...` words are a usage error
  * the renamed files are what the code opens, and no tracked file contains the removed name
  * OLD behaviour pinned at 06a4eae (never HEAD): one winner per slot, and a pick enabled on OOS profitability
    alone even when it fails the owner's criteria
"""
import ast, datetime, importlib.util, json, math, os, subprocess, sys, tempfile, unittest
import unittest.mock as mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import selection_criteria as SC

PRE_ROUND4C = "06a4eae"   # round-4b head this round started from -- NOT "HEAD"


def load(name, modname):
    spec = importlib.util.spec_from_file_location(modname, os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


RS = load("rank-setups.py", "rank_setups_r4c")
CRIT = SC.load()
H = CRIT["horizons"]

CUT = "2026-03-11T00:00:00Z"
IS_SINCE = "2025-03-11"
LAST = "2026-09-11"


def blk(**kw):
    """One IS/OOS window block, passing every horizon's criteria by default."""
    b = dict(n=40, since=IS_SINCE, until=CUT[:10], m_mean_geo=6.0, m_losing=1, m_worst=-3.0, dd=5.0, q_worst=-1.0,
             ann=100.0, net_pnl=4000.0, expectancy_R=0.3, profit_factor=1.6, ruin=None, q_pos=75.0, final=14000.0,
             months=[dict(month="2025-03", ret_pct=1.0, partial=True), dict(month="2025-04", ret_pct=2.0)])
    b.update(kw)
    return b


def oos_blk(**kw):
    return blk(**dict(dict(n=20, since=CUT[:10], until=LAST), **kw))


def row(tf="15m", method="ICT", cfg="A", *, is_kw=None, oos_kw=None, file="data/history/stability/crypto-live.json",
        target="live", market="crypto"):
    return dict(tf=tf, cfg=cfg, method=method, first="2023-09-13", last=LAST, n=200, ann=5.0, market=market,
                target=target, file=file, research_validity="FLAGGED",
                oos6m=dict(cutoff=CUT, dataset_last_bar=LAST + "T05:45:00Z", split="entry_time",
                           in_sample=blk(**(is_kw or {})), oos=oos_blk(**(oos_kw or {}))))


def decisions(rows, market="crypto"):
    judged, _others, budget = RS.select_criteria(rows, market, CRIT)
    return {j["id"]: j for j in judged}, budget


# The window field and the "one step beyond" direction of every gating criterion, as the gate defines them.
STEP = 1e-6


class CriterionBoundaries(unittest.TestCase):
    def _beyond(self, key, thr):
        field, op, _ = SC.GATES[key]
        if key == "losing_months_max":
            return thr + 1                       # a count: the next integer is the first failing value
        return thr - STEP if op == SC.GE else thr + STEP

    def test_every_gate_of_every_horizon_passes_at_the_threshold_and_fails_just_beyond(self):
        seen = 0
        for hz, spec in H.items():
            for key, thr in spec.items():
                if key not in SC.GATES:
                    continue
                field = SC.GATES[key][0]
                at = SC.evaluate(blk(**{field: thr}), hz, CRIT)
                c = next(c for c in at["checks"] if c["criterion"] == key)
                self.assertTrue(c["passed"], f"{hz} {key}: value == threshold {thr} must pass")
                self.assertTrue(at["passed"], f"{hz}: {at['failed']}")
                out = SC.evaluate(blk(**{field: self._beyond(key, thr)}), hz, CRIT)
                c = next(c for c in out["checks"] if c["criterion"] == key)
                self.assertFalse(c["passed"], f"{hz} {key}: one step beyond {thr} must fail")
                self.assertFalse(out["passed"])
                seen += 1
        # 3 scalping + 4 day + 3 swing gates in the owner's file
        self.assertEqual(seen, 10)

    def test_the_file_carries_the_owner_values(self):
        """Read, not re-typed: this only pins that the file this gate reads is the ADR 0008 one."""
        self.assertEqual(H["scalping"]["mean_monthly_return_pct_min"], 5.0)
        self.assertEqual(H["day"]["max_drawdown_pct_max"], 10.0)
        self.assertEqual(H["swing"]["worst_quarter_pct_min"], -3.0)

    def test_each_horizon_gates_on_exactly_its_own_criteria(self):
        """Swing has no losing-months gate: 5 losing months cannot fail a swing system; it fails a day system."""
        b = blk(m_losing=5)
        self.assertTrue(SC.evaluate(b, "swing", CRIT)["passed"])
        self.assertFalse(SC.evaluate(b, "day", CRIT)["passed"])
        self.assertFalse(SC.evaluate(b, "scalping", CRIT)["passed"])


class MissingInputFails(unittest.TestCase):
    def test_absent_null_non_numeric_non_finite_and_bool_all_fail_as_missing(self):
        for bad in ("__absent__", None, "6.0", float("nan"), float("inf"), True):
            b = blk()
            if bad == "__absent__":
                b.pop("m_mean_geo")
            else:
                b["m_mean_geo"] = bad
            ev = SC.evaluate(b, "scalping", CRIT)
            c = next(c for c in ev["checks"] if c["criterion"] == "mean_monthly_return_pct_min")
            self.assertFalse(c["passed"], repr(bad))
            self.assertEqual(c["reason"], SC.MISSING, repr(bad))
            self.assertFalse(ev["passed"], repr(bad))

    def test_a_missing_window_block_fails_every_criterion(self):
        ev = SC.evaluate(None, "day", CRIT)
        self.assertFalse(ev["passed"])
        self.assertEqual({c["reason"] for c in ev["checks"]}, {SC.MISSING})
        self.assertEqual(len(ev["checks"]), 4)

    def test_an_unknown_horizon_fails_closed(self):
        ev = SC.evaluate(blk(), "seconds-scalping", CRIT)
        self.assertFalse(ev["passed"]); self.assertTrue(ev["failed"])

    def test_a_row_without_the_monthly_fields_is_disabled_not_enabled(self):
        r = row(oos_kw=dict(m_mean_geo=None, m_losing=None, m_worst=None))
        d, _ = decisions([r])
        j = next(iter(d.values()))
        self.assertEqual(j["decision"], RS.DISABLED)
        self.assertTrue(any("missing" in x for x in j["reasons"]), j["reasons"])


class CriteriaFileRefusals(unittest.TestCase):
    def _write(self, doc):
        fd, p = tempfile.mkstemp(suffix=".json", dir=os.environ.get("TMP")); os.close(fd)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        self.addCleanup(os.remove, p)
        return p

    def test_an_unknown_criterion_key_refuses_the_file(self):
        doc = json.loads(json.dumps(CRIT)); doc["horizons"]["day"]["sharpe_min"] = 1.0
        with self.assertRaises(SC.CriteriaError):
            SC.load(self._write(doc))

    def test_a_horizon_with_only_a_reported_target_is_refused(self):
        doc = json.loads(json.dumps(CRIT)); doc["horizons"]["scalping"] = {"monthly_return_pct_target": 10.0}
        with self.assertRaises(SC.CriteriaError):
            SC.load(self._write(doc))

    def test_a_non_numeric_threshold_is_refused(self):
        doc = json.loads(json.dumps(CRIT)); doc["horizons"]["swing"]["max_drawdown_pct_max"] = "8"
        with self.assertRaises(SC.CriteriaError):
            SC.load(self._write(doc))


class BothWindowsRequired(unittest.TestCase):
    def test_in_sample_pass_oos_fail_is_disabled(self):
        d, b = decisions([row(oos_kw=dict(m_mean_geo=1.0))])
        j = next(iter(d.values()))
        self.assertTrue(j["in_sample"]["passed"]); self.assertFalse(j["oos"]["passed"])
        self.assertEqual(j["decision"], RS.DISABLED)
        self.assertTrue(any(x.startswith("OOS ") for x in j["reasons"]))
        self.assertEqual(b["enabled"], 0)

    def test_oos_pass_in_sample_fail_is_disabled(self):
        d, b = decisions([row(is_kw=dict(m_worst=-9.0))])
        j = next(iter(d.values()))
        self.assertFalse(j["in_sample"]["passed"]); self.assertTrue(j["oos"]["passed"])
        self.assertEqual(j["decision"], RS.DISABLED)
        self.assertTrue(any(x.startswith("IS ") for x in j["reasons"]))

    def test_both_pass_is_enabled(self):
        d, b = decisions([row()])
        self.assertEqual(next(iter(d.values()))["decision"], RS.ENABLED)
        self.assertEqual(b["enabled"], 1)


class EveryPassingRowIsEnabled(unittest.TestCase):
    def test_no_cap_many_passing_rows_at_one_horizon_all_enabled(self):
        rows = [row("15m", m, cfg, file=f"data/history/stability/crypto-{t}.json", target=(t if m == "ICT" else "border"))
                for m in sorted(RS.RUNNABLE) for cfg in ("A", "B", "C") for t in ("live", "v1", "testnet")]
        d, b = decisions(rows)
        n_ict = 3 * 3                                          # ICT: 3 cfg x 3 files; WYCKOFF-BOOK dedups to 3 cfg
        self.assertEqual(sum(1 for j in d.values() if j["decision"] == RS.ENABLED), b["enabled"])
        self.assertEqual(b["enabled"], n_ict + 3 * (len(RS.RUNNABLE) - 1))
        self.assertEqual(b["by_horizon"]["scalping"]["enabled"], b["enabled"])

    def test_no_runner_up_substitution_decisions_are_independent(self):
        """Adding a failing (better-looking in-sample) row neither disables the passing one nor enables anything
        in its place; removing it changes nothing either."""
        good = row(cfg="B", is_kw=dict(m_mean_geo=5.5))
        star_fails_oos = row(cfg="A", is_kw=dict(m_mean_geo=40.0), oos_kw=dict(m_mean_geo=-2.0))
        alone, _ = decisions([good])
        both, b = decisions([star_fails_oos, good])
        self.assertEqual(alone["crypto-scalping-ict-15m-live-b"]["decision"], RS.ENABLED)
        self.assertEqual(both["crypto-scalping-ict-15m-live-b"]["decision"], RS.ENABLED)
        self.assertEqual(both["crypto-scalping-ict-15m-live-a"]["decision"], RS.DISABLED)
        self.assertEqual(b["enabled"], 1)
        only_star, b2 = decisions([star_fails_oos])
        self.assertEqual(b2["enabled"], 0, "a failed system must not be replaced by anything")

    def test_a_retired_timeframe_or_unrunnable_method_is_never_a_candidate(self):
        rows = [row("30m"), row("5m"), row("2H"), row("1D"), row("15m", "COMBINED-BOOK")]
        d, b = decisions(rows)
        self.assertEqual(d, {}); self.assertEqual(b["not_candidates"], 5); self.assertEqual(b["enabled"], 0)

    def test_conflicting_duplicate_ids_are_both_withheld(self):
        a = row("1H", "WYCKOFF-BOOK", "A", target="border", file="data/history/stability/crypto-live.json")
        b_ = row("1H", "WYCKOFF-BOOK", "A", target="border", file="data/history/stability/crypto-v1.json",
                 oos_kw=dict(m_mean_geo=9.0))
        d, bud = decisions([a, b_])
        j = d["crypto-day-wyckoff-book-1h-border-a"]
        self.assertEqual(j["decision"], RS.DISABLED)
        self.assertTrue(any("conflicting duplicate" in x for x in j["reasons"]))
        self.assertEqual(bud["enabled"], 0)


class TargetIsReportedNotGating(unittest.TestCase):
    def test_a_scalping_system_below_the_10pct_target_but_above_the_5pct_gate_is_enabled(self):
        self.assertEqual(H["scalping"]["monthly_return_pct_target"], 10.0)
        d, _ = decisions([row(is_kw=dict(m_mean_geo=6.0), oos_kw=dict(m_mean_geo=5.0))])
        j = next(iter(d.values()))
        self.assertEqual(j["decision"], RS.ENABLED)
        self.assertEqual([c["passed"] for c in j["in_sample"]["reported"]], [False])
        self.assertNotIn("monthly_return_pct_target", " ".join(j["reasons"]))
        self.assertNotIn("monthly_return_pct_target", {c["criterion"] for c in j["in_sample"]["checks"]})


class Preconditions(unittest.TestCase):
    def test_a_short_window_disables(self):
        d, _ = decisions([row(oos_kw=dict(since="2026-08-01"))])          # 41-day OOS window
        j = next(iter(d.values()))
        self.assertEqual(j["decision"], RS.DISABLED)
        self.assertTrue(any("window" in x and "< 90" in x for x in j["reasons"]), j["reasons"])

    def test_too_few_in_sample_trades_disables(self):
        d, _ = decisions([row(is_kw=dict(n=RS.IS_MIN_TRADES["scalping"] - 1))])
        self.assertEqual(next(iter(d.values()))["decision"], RS.DISABLED)
        d, _ = decisions([row(is_kw=dict(n=RS.IS_MIN_TRADES["scalping"]))])
        self.assertEqual(next(iter(d.values()))["decision"], RS.ENABLED)

    def test_unparseable_window_dates_fail_closed(self):
        d, _ = decisions([row(is_kw=dict(since="not-a-date"))])
        self.assertEqual(next(iter(d.values()))["decision"], RS.DISABLED)


class EndToEnd(unittest.TestCase):
    """Synthetic stability file -> selection JSON + report, through RS.run()."""

    def _run(self, rows, tmp, sel=None):
        for r in rows:
            for k in ("market", "target", "file", "research_validity"):
                r.pop(k, None)
        crypto = os.path.join(tmp, "crypto-live.json")
        with open(crypto, "w", encoding="utf-8") as fh:
            json.dump(dict(generated="2026-09-26", oos_holdout=dict(cutoff=CUT),
                           dataset_snapshot={"snapshot_id": "abc"}, rows=rows), fh)
        sel = sel or os.path.join(tmp, "sel.json"); out = os.path.join(tmp, "report.md")
        ns = type("A", (), dict(crypto=[crypto], cfd=[], select=sel, out=out, criteria=SC.PATH,
                                crypto_symbols="BTCUSDT", cfd_symbols="XAUUSD", require_stamped=False))()
        with mock.patch("builtins.print"):
            RS.REFUSED.clear(); RS.SOURCE_VALIDITY.clear()
            RS.run(ns, "2026-09-26")
        with open(sel, encoding="utf-8") as fh:
            d = json.load(fh)
        with open(out, encoding="utf-8") as fh:
            md = fh.read()
        return d, md, sel

    def test_zero_pass_horizon_is_empty_and_said_in_words(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("TMP"))
        rows = [row("15m", "ICT", "A", oos_kw=dict(m_mean_geo=0.5)),       # scalping: fails OOS
                row("1H", "ICT", "A"),                                        # day: passes
                row("4H", "WYCKOFF-BOOK", "B", is_kw=dict(dd=12.0))]          # swing: fails IS
        d, md, sel = self._run(rows, tmp)
        self.assertEqual(d["mode"], "criteria-oos6m")
        self.assertEqual([s["id"] for s in d["setups"]], ["crypto-day-ict-1h-live-a"])
        self.assertEqual({x["id"] for x in d["disabled"]},
                         {"crypto-scalping-ict-15m-live-a", "crypto-swing-wyckoff-book-4h-border-b"})
        for x in d["disabled"]:
            self.assertEqual(x["decision"], "DISABLED"); self.assertTrue(x["reasons"]); self.assertIn("rule_version", x)
        empty = {(h["market"], h["horizon"]) for h in d["horizons_without_system"]}
        self.assertEqual(empty, {("crypto", "scalping"), ("crypto", "swing"),
                                 ("cfd", "scalping"), ("cfd", "day"), ("cfd", "swing")})
        self.assertIn("crypto scalping: 0 systems enabled — this horizon trades nothing", md)
        self.assertIn("crypto swing: 0 systems enabled — this horizon trades nothing", md)
        # every candidate is listed with IS and OOS values against each threshold
        self.assertIn("IS mean_monthly_return_pct_min", md); self.assertIn("OOS max_drawdown_pct_max", md)
        self.assertIn("monthly_return_pct_target (IS / OOS, not gating)", md)
        self.assertIn("12.00 <= 8 ✗", md)
        # OOS exposure and experiment budget
        self.assertEqual(d["oos_holdout"]["crypto"]["status"], "EXPOSED")
        self.assertEqual(d["oos_holdout"]["crypto"]["cutoff"], CUT)
        self.assertEqual(d["experiment_budget"]["crypto"]["candidate_rows"], 3)
        self.assertEqual(d["experiment_budget"]["crypto"]["enabled"], 1)
        self.assertEqual(d["criteria"]["source"], "docs/architecture/selection-criteria.json")
        self.assertIn("EXPOSED", md)
        # a second run at the same cutoff counts a second use of the exposed window
        d2, _, _ = self._run([row("1H", "ICT", "A")], tmp, sel=sel)
        self.assertEqual(d2["oos_holdout"]["crypto"]["times_used_for_selection"], 2)

    def test_nothing_passes_nothing_is_enabled(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("TMP"))
        d, md, _ = self._run([row("15m", "ICT", "A", is_kw=dict(m_mean_geo=-1.0))], tmp)
        self.assertEqual(d["setups"], [])
        self.assertIn("none — the pilot trades nothing", md)

    def test_a_file_without_the_split_is_refused(self):
        r = row(); r.pop("oos6m")
        with self.assertRaises(SystemExit):
            RS.require_oos_blocks([r])

    def test_mixed_cutoffs_refused(self):
        a, b = row(), row(cfg="B"); b["oos6m"] = dict(b["oos6m"], cutoff="2026-03-18T00:00:00Z")
        with self.assertRaises(SystemExit):
            RS.market_cutoff([a, b], "crypto")


class OneSelectionPath(unittest.TestCase):
    def test_rank_setups_has_no_ranking_or_count_selection_left(self):
        for gone in ("rank", "solvent", "prop_key", "select_oos", "main_horizons", "main_window_1y", "fmt"):
            self.assertFalse(hasattr(RS, gone), f"rank-setups.py still defines {gone}()")
        src = open(os.path.join(ROOT, "scripts", "rank-setups.py"), encoding="utf-8").read()
        for flag in ('"--n"', '"--horizons"', '"--window"', '"--rank-by"', '"--account-rows"'):
            self.assertNotIn(flag, src)
        self.assertIn("SC.evaluate(", src)

    def test_automation_on_has_one_path_and_refuses_selection_words(self):
        au = load("automation.py", "au_r4c")
        cfg = json.loads(json.dumps(au.DEFAULTS))
        for words in (["setup", "top", "3"], ["setup", "horizons"], ["anything"]):
            rc, lines = au.apply_setup_spec(cfg, type("A", (), {"setup": words, "cmd": "on", "who": None, "reason": None})())
            self.assertEqual(rc, 1, words); self.assertIn("ADR 0008", lines[0])
        self.assertEqual(cfg["history"], [])
        calls = []
        def fake_run(args, **kw):
            calls.append(args); return type("R", (), {"returncode": 1, "stderr": "stubbed"})()
        with mock.patch.object(au.subprocess, "run", fake_run):
            rc, _ = au.apply_setup_spec(cfg, type("A", (), {"setup": [], "cmd": "on", "who": None, "reason": None})())
        self.assertEqual(rc, 2)
        self.assertTrue(calls[0][1].endswith("rank-setups.py"))
        for gone in ("--horizons", "--window", "--n", "1y", "oos6m"):
            self.assertNotIn(gone, calls[0])
        self.assertIn(os.path.join(ROOT, "docs", "architecture", "pilot-selection.json"), calls[0])


class RenamedFilesAreWhatTheCodeOpens(unittest.TestCase):
    def test_runner_journal_panel_outcomes_and_mandates_point_at_the_new_names(self):
        sr = load("strategy-runner.py", "sr_r4c")
        self.assertEqual(sr.SELECTION, os.path.join(ROOT, "docs", "architecture", "pilot-selection.json"))
        self.assertEqual(os.path.basename(sr.STATE), "pilot-selection-state.json")
        self.assertEqual(os.path.basename(sr.LOG), "pilot-selection-log.jsonl")
        self.assertEqual(os.path.basename(sr.MT5_LOG), "pilot-selection-mt5-log.jsonl")
        sr.bind_account(None)
        self.assertEqual(os.path.basename(sr.STATE), "pilot-selection-state.json")
        self.assertTrue(os.path.exists(sr.SELECTION))
        for p in (sr.STATE, sr.LOG, sr.MT5_LOG):
            self.assertTrue(os.path.exists(p), p)
        j = load("journal.py", "journal_r4c")
        self.assertEqual(os.path.basename(j.PILOT["futures-selection"]), "pilot-selection-log.jsonl")
        self.assertEqual(os.path.basename(j.PILOT["cfd-mt5"]), "pilot-selection-mt5-log.jsonl")
        mp = load("method-panel.py", "mp_r4c")
        self.assertEqual(os.path.basename(mp.PILOT_STATE_PATH), "pilot-selection-state.json")
        md = load("mandates.py", "md_r4c")
        self.assertEqual(md.SELECTION, sr.SELECTION)

    def test_the_runner_trades_nothing_without_a_selection_file(self):
        sr = load("strategy-runner.py", "sr_r4c_empty")
        sr.SELECTION = os.path.join(tempfile.mkdtemp(dir=os.environ.get("TMP")), "absent.json")
        self.assertEqual(sr.load_setups(), [])
        self.assertFalse(hasattr(sr, "DEFAULT_SETUPS"))


class TheRemovedNameIsGone(unittest.TestCase):
    """Owner decision 2026-09-26: no tracked file may contain the removed name -- code, docs, history or data.
    The pattern is assembled from parts so this file does not match itself."""
    PATTERN = "t" + "op[ _-]?" + "2" + "0"

    def test_no_tracked_file_contains_it(self):
        r = subprocess.run(["git", "grep", "-n", "-i", "-I", "-E", self.PATTERN], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 1, "git grep found the removed name:\n" + r.stdout[:3000])

    def test_no_tracked_file_is_named_with_it(self):
        import re
        names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.splitlines()
        hits = [n for n in names if re.search(self.PATTERN, n, re.I)]
        self.assertEqual(hits, [])


class OldBehaviourPinnedAt06a4eae(unittest.TestCase):
    """PRE_ROUND4C's `select_oos` enabled ONE winner per (horizon, method) slot, on OOS profitability alone. Its
    pure functions are extracted from `git show 06a4eae:scripts/rank-setups.py` and run in an isolated namespace
    (they reference no sibling module)."""

    def _old(self):
        src = subprocess.check_output(["git", "show", f"{PRE_ROUND4C}:scripts/rank-setups.py"], cwd=ROOT, text=True,
                                      encoding="utf-8")
        tree = ast.parse(src)
        fns = {"solvent", "rank", "_num", "_pass_estimate", "prop_key", "oos_verdict", "select_oos"}
        consts = {"MIN_WINDOW_DAYS", "HORIZONS", "OOS_MIN_TRADES"}
        body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in fns]
        body += [n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", None) in consts for t in n.targets)]
        body += [n for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple)
                 and "ENABLED" in [getattr(e, "id", None) for e in n.targets[0].elts]]
        ns = {"datetime": datetime, "RUNNABLE": RS.RUNNABLE, "CFD_TFS": RS.CFD_TFS}
        exec(compile(ast.Module(body=body, type_ignores=[]), f"{PRE_ROUND4C}:scripts/rank-setups.py", "exec"), ns)
        return ns

    def _old_row(self, cfg, *, q_pos, ann, m_mean_geo):
        r = row("15m", "ICT", cfg, oos_kw=dict(m_mean_geo=m_mean_geo))
        r["oos6m"]["in_sample"].update(q_pos=q_pos, ann=ann)
        return r

    def test_old_capped_the_slot_at_one_and_enabled_a_row_failing_the_criteria(self):
        old = self._old()
        # A: best in-sample, OOS profitable (+P&L, +expectancy) but mean monthly 0.5 % -- fails the 5 % gate.
        # B: second in-sample, passes every criterion on both windows.
        a = self._old_row("A", q_pos=100.0, ann=200.0, m_mean_geo=0.5)
        b = self._old_row("B", q_pos=50.0, ann=80.0, m_mean_geo=6.0)
        slots, _ = old["select_oos"]([a, b], "crypto")
        s = [x for x in slots if x["tf"] == "15m" and x["method"] == "ICT"][0]
        self.assertIs(s["pick"], a); self.assertEqual(s["status"], "ENABLED")      # old: A enabled, B never
        new, _ = decisions([a, b])
        self.assertEqual(new["crypto-scalping-ict-15m-live-a"]["decision"], RS.DISABLED)
        self.assertEqual(new["crypto-scalping-ict-15m-live-b"]["decision"], RS.ENABLED)


if __name__ == "__main__":
    unittest.main()
