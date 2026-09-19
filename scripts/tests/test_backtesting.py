"""CLAUDE.md §37 -- the backtest is event-driven, point-in-time correct, and the same system as live.

§37 makes two demands and this file answers each with evidence rather than with a reading of the code.

**"Only information available at the historical decision time may affect the entry decision."** A code
review cannot establish that; an experiment can. `scripts/leakage.py` replaces every bar strictly after a
cut with something wildly different -- same length, same timestamps, different prices -- and re-runs the
engine. Every decision whose entry happened at or before the cut must come back byte-identical; only the
outcome fields (`outcome`, `R`, `exit`, `exit_time`) may move, which is exactly what §37 permits. Three
mutation modes run, because one can agree with the original by accident. The probe is itself put through a
mutation test here: a deliberately leaky scan must be CAUGHT, or a passing probe means nothing.

**"The backtest must execute the same logical Trading System and Decision Engine semantics used by live
decisions wherever practical."** Since §36 that is measurable: `decision-order.json` declares, per canonical
step, where it lives on the backtest path or why it is absent, and the tests below check that column against
what the §11 configuration snapshot independently reports as not applied.

Writing that column found a real divergence. The live R:R gate has measured R **net of fees** since §34;
`simulate()` was still filtering on **gross** `R_planned` and charging the fee afterwards, so the backtest
was taking trades the live runner refuses -- 392 of 8,071 admitted trades (5 %) across BTC/ETH/SOL 15m. That
is fixed, and it is a research-semantics change: results produced before 2026-09-18 are not comparable.
"""
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import decision_order as DO
import leakage

BT_SRC = open(os.path.join(ROOT, "scripts", "backtest-methods.py"), encoding="utf-8").read()

# The fields §37 forbids the future to influence. Everything a trade record carries that is NOT here is an
# outcome, and the future is explicitly allowed to decide those.
DECISION_FIELDS = ("symbol", "tf", "side", "time", "event", "support", "resistance", "vol_type", "vol_ratio",
                   "entry", "entry_time", "stop", "target", "R_planned", "via", "leg", "size", "path")


def _bt():
    spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _key(rec):
    return (rec.get("event"), rec.get("leg"), rec.get("entry_time"), rec.get("size"))


class TheProbeCatchesLeakage(unittest.TestCase):
    """A passing look-ahead probe proves nothing unless the probe can fail. These make it fail on purpose."""

    def _series(self, n=200, start=100.0):
        out = []
        for i in range(n):
            px = start + (i % 17) - 8
            out.append({"time": f"2026-01-{1 + i // 96:02d}T{(i % 96) // 4:02d}:{15 * (i % 4):02d}:00Z",
                        "open": px, "high": px + 1, "low": px - 1, "close": px, "volume": 10.0 + (i % 5)})
        return out

    def test_a_causal_engine_passes(self):
        s = self._series()

        def honest(candles):
            # Decides at bar 50 using bar 50 only. Entry at 50; the outcome looks forward, which is allowed.
            return [{"event": "e", "leg": None, "size": 1.0, "entry_time": candles[50]["time"],
                     "entry": candles[50]["close"], "stop": candles[50]["low"], "target": candles[50]["high"],
                     "outcome": "win" if candles[-1]["close"] > candles[50]["close"] else "loss"}]

        rep = leakage.probe(honest, s, 100, key=_key, decision_fields=("entry", "stop", "target"))
        self.assertTrue(rep["ok"], leakage.describe(rep))
        self.assertEqual(rep["checked"], 1)

    def test_an_entry_that_peeks_at_the_future_is_caught(self):
        s = self._series()

        def leaky(candles):
            # The classic leak: the "entry" is the best price in the whole series, including bars that had
            # not happened when the decision was made.
            best = max(c["close"] for c in candles)
            return [{"event": "e", "leg": None, "size": 1.0, "entry_time": candles[50]["time"],
                     "entry": best, "stop": candles[50]["low"], "target": candles[50]["high"]}]

        rep = leakage.probe(leaky, s, 100, key=_key, decision_fields=("entry", "stop", "target"))
        self.assertFalse(rep["ok"])
        self.assertTrue(any(v["field"] == "entry" for v in rep["violations"]), rep["violations"])
        self.assertIn("LOOK-AHEAD", leakage.describe(rep))

    def test_a_decision_that_only_exists_because_of_the_future_is_caught(self):
        s = self._series()

        def leaky(candles):
            # Existence depends on a bar after the cut: "only take it if price later exceeded the cut close".
            # The `freeze` mutation flattens the future onto that exact level, so the condition flips.
            level = candles[100]["close"]
            if not any(c["high"] > level for c in candles[101:]):
                return []
            return [{"event": "e", "leg": None, "size": 1.0, "entry_time": candles[50]["time"],
                     "entry": candles[50]["close"]}]

        rep = leakage.probe(leaky, s, 100, key=_key, decision_fields=("entry",))
        self.assertFalse(rep["ok"])
        self.assertTrue(any(v["field"] == "__present__" for v in rep["violations"]))

    def test_the_mutation_preserves_shape_and_only_touches_the_future(self):
        s = self._series()
        for mode in leakage.MODES:
            m = leakage.mutate_future(s, 100, mode)
            self.assertEqual(len(m), len(s), mode)
            self.assertEqual([c["time"] for c in m], [c["time"] for c in s], mode)
            self.assertEqual(s[:101], m[:101], f"{mode} changed a bar at or before the cut")
            self.assertNotEqual(s[101:], m[101:], f"{mode} left the future unchanged -- it would prove nothing")
            for c in m:                          # a mutated bar must still be a valid bar (§20)
                self.assertLessEqual(c["low"], min(c["open"], c["close"]), mode)
                self.assertGreaterEqual(c["high"], max(c["open"], c["close"]), mode)

    def test_an_unknown_mutation_mode_is_refused(self):
        with self.assertRaises(ValueError):
            leakage.mutate_future(self._series(), 10, "vibes")


class TheRealEngineIsPointInTime(unittest.TestCase):
    """The probe, run on `scripts/backtest-methods.py` over REAL history.

    One method per test so a failure names the rule family that leaked. Each asserts `checked > 0` first: a
    probe that examined no decisions passes vacuously, which is the way this kind of test rots.
    """

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()
        cls.series, _src = cls.bt.load("BTCUSDT", "15m")
        if not cls.series:
            raise unittest.SkipTest("no BTCUSDT 15m history on this machine")

    def _run_for(self, method):
        bt = self.bt

        def run(candles):
            real = bt.load
            bt.load = lambda s, t, _c=candles: (_c, "injected")
            try:
                sc = bt.scan("BTCUSDT", "15m", only=(method,))
                return list(sc["trades"][method]) if sc else []
            finally:
                bt.load = real
        return run

    def _probe(self, method, bars, min_checked=1):
        series = self.series[-bars:]
        cut = int(len(series) * 0.7)
        rep = leakage.probe(self._run_for(method), series, cut, key=_key,
                            decision_fields=DECISION_FIELDS)
        self.assertGreaterEqual(rep["checked"], min_checked,
                                f"{method}: the probe examined {rep['checked']} decisions -- a probe with "
                                f"nothing to check cannot fail, so this window is too small to be evidence")
        self.assertTrue(rep["ok"], leakage.describe(rep))
        return rep

    def test_wyckoff_entries_do_not_read_the_future_with_htf_enabled(self):
        """A1 (2026-09-18): OPTS['htf'] defaults to False, so a probe with htf off never exercises
        htf_position/htf_allows -- exactly the config stability-report.py's 'C' preset runs (htf=True), and the
        one the one-bar look-ahead leak escaped in. Retargeted at WYCKOFF-BOOK (2026-09-19,
        docs/audits/2026-09-19-knowledge-fidelity.md finding 6): the WYCKOFF mechanical proxy this probe used
        to run against was removed, and htf_position/htf_allows is the SAME shared code the surviving
        WYCKOFF-BOOK/COMBINED-BOOK block calls (backtest-methods.py scan()), so the regression coverage
        carries over unchanged."""
        self.bt.OPTS["htf"] = True
        try:
            self._probe("WYCKOFF-BOOK", 20000, min_checked=1)
        finally:
            self.bt.OPTS["htf"] = False

    def test_wyckoff_book_entries_do_not_read_the_future(self):
        self._probe("WYCKOFF-BOOK", 20000, min_checked=1)

    def test_combined_book_entries_do_not_read_the_future(self):
        self._probe("COMBINED-BOOK", 20000, min_checked=1)

    def test_the_pivot_helper_is_causal_by_construction(self):
        """`last_pivot` is the one place a 3-bar pivot could leak: a pivot at i is only confirmed at i+3."""
        piv = [10, 20, 30, 40]
        for upto in range(0, 60):
            got = self.bt.last_pivot(piv, upto)
            if got is not None:
                self.assertLessEqual(got + 3, upto - 1,
                                     f"pivot {got} was admitted at bar {upto} but needs bar {got + 3}")
        self.assertIsNone(self.bt.last_pivot(piv, 13), "a pivot at 10 needs bar 13; it is not knowable AT 13")
        self.assertEqual(self.bt.last_pivot(piv, 14), 10)


class HTFFilterUsesOnlyClosedBars(unittest.TestCase):
    """A1 -- htf_position must key each row on the HTF bar's CLOSE time (normalized.available_time), so
    htf_allows only ever sees a bar that has actually finished forming. Before the 2026-09-18 fix it keyed on
    the bar's OPEN time, so a still-forming HTF bar's close (baked into `pct`) leaked into any LTF decision
    made during that hour -- one bar early, every time (CLAUDE.md §8)."""

    def test_htf_allows_never_uses_a_still_forming_bar(self):
        import datetime as _dt
        bt = _bt()
        base = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
        Rh = bt.P["1H"]["R"]
        c = []
        for i in range(Rh + 2):
            t = base + _dt.timedelta(hours=i)
            close = 100.0
            if i == Rh:        # the last CLOSED 1H bar at decision time: pct 0.5 -- blocks "long"
                close = 100.0
            elif i == Rh + 1:  # still forming at decision time: pct 0.1 -- would wrongly ALLOW "long" if leaked
                close = 92.0
            c.append({"time": t.isoformat().replace("+00:00", "Z"), "open": 100.0, "high": 110.0, "low": 90.0,
                      "close": close, "volume": 1.0})
        real_load = bt.load
        bt.load = lambda sym, tf, _c=c: (_c, "synthetic") if tf == "1H" else real_load(sym, tf)
        try:
            htf = bt.htf_position("SYM", "15m")  # HTF_OF["15m"] == "1H"
        finally:
            bt.load = real_load
        # 30 minutes into the still-forming last 1H bar (opened at Rh+1, closes one hour later)
        t_decision = (base + _dt.timedelta(hours=Rh + 1, minutes=30)).isoformat().replace("+00:00", "Z")
        self.assertFalse(bt.htf_allows(htf, t_decision, "long"),
                         "htf_allows used the still-forming HTF bar's close (pct 0.1) instead of the last "
                         "CLOSED bar (pct 0.5) -- a one-bar look-ahead leak")


class TheSameSystemAsLive(unittest.TestCase):
    """§37's second demand, made measurable by §36's registry."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()

    def test_the_registry_declares_a_backtest_column_for_every_step(self):
        for s in DO.STEPS:
            self.assertIn("backtest", s)
            if s["backtest"] is None:
                self.assertTrue(str(s.get("_backtest_why") or "").strip(),
                                f"step {s['id']} absent on the backtest path with no reason")

    def test_the_engine_now_reads_a_calendar_when_one_is_supplied(self):
        """A4 (2026-09-18): steps 3, 4 and 14 are IMPLEMENTED on the backtest path -- simulate()'s
        admission-time refusal, gated on --calendar/--sessions being supplied at all. Steps 3/4/14 are no
        longer in `unimplemented("backtest")`; the capability exists on the path even for a run that passes
        neither flag (that run simply has nothing to refuse against -- a per-run fact, not a per-path one)."""
        self.assertIn("event_risk", BT_SRC)
        self.assertEqual(set(DO.unimplemented("backtest")) & {"event_precheck", "session", "event_final"}, set())

    def test_the_declared_absences_match_what_the_snapshot_reports(self):
        """Cross-registry agreement: §36's registry and §11's snapshot must not disagree about what the
        engine does. Both are hand-written; this is the test that keeps them one statement."""
        import snapshot
        # No --calendar/--sessions/--account for THIS run: event_risk.calendar is correctly still reported
        # not-applied for a run that supplied none, even though the capability exists on the path (A4).
        fields = snapshot.backtest_config_snapshot(self.bt, timeframes=["15m"], methods={"ICT"},
                                                   market="crypto")["fields"]
        not_applied = set(fields["required_evidence"]["declared_but_not_applied_by_this_engine"])
        absent = set(DO.unimplemented("backtest"))
        self.assertIn("event_risk.calendar", not_applied)
        self.assertEqual({"event_precheck", "event_final"} & absent, set())
        # The account's ENTRY gates are not applied, and step 5 says so while still citing simulate() for the
        # survival half -- so `account.profile_rules` is in the snapshot's not-applied list but step 5 is NOT
        # in the absent list. That asymmetry is deliberate and is asserted rather than left to be noticed.
        self.assertIn("account.profile_rules", not_applied)
        self.assertNotIn("account_constraints", absent)
        self.assertIn("SURVIVAL half", DO.step("account_constraints")["backtest"])

    def test_live_and_backtest_share_the_rule_modules(self):
        """Parity does not rest on two implementations agreeing; it rests on there being one."""
        runner = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        for module in ("live_rules", "wyckoff_rules"):
            self.assertIn(module, BT_SRC, f"the backtest does not use {module}")
            self.assertIn(module, runner, f"the live runner does not use {module}")

    def test_the_rr_floor_is_the_same_gate_on_both_paths(self):
        """The divergence found on 2026-09-18: live measured R net of fees (§34), the backtest gross."""
        self.assertIn("t.get(\"R_planned\", 99) - fee_R < OPTS[\"min_rr\"]", BT_SRC,
                      "simulate() must apply the R:R floor to R NET of fees, as the live path does")
        i_fee = BT_SRC.index("fee_R = 2 * fee_pct / dist")
        i_floor = BT_SRC.index("- fee_R < OPTS[\"min_rr\"]")
        self.assertLess(i_fee, i_floor, "the fee must be computed before the floor is applied")

    def test_the_floor_actually_refuses_a_trade_the_live_path_would_refuse(self):
        """Driven, not read: a trade whose gross R clears the floor but whose net R does not must be dropped."""
        bt = self.bt
        floor = bt.OPTS["min_rr"]
        dist_pct = 0.002                       # a 0.2 % stop: fee cost in R is 2*fee/dist = 0.5R at 5 bps
        entry = 100.0
        stop = entry * (1 - dist_pct)
        gross = floor + 0.2                    # clears the gross floor by 0.2R, loses 0.5R to fees
        trade = dict(symbol="BTCUSDT", event="e", side="long", entry=entry, stop=stop,
                     target=entry + gross * (entry - stop), entry_time="2026-01-01T00:00:00Z",
                     exit_time="2026-01-01T01:00:00Z", R=gross, R_planned=gross, outcome="win")
        _eq, _curve, taken = bt.simulate([dict(trade)], 0.0005)
        self.assertEqual(taken, [], "a trade below the NET floor was still taken")
        _eq, _curve, taken_cheap = bt.simulate([dict(trade)], 0.00001)
        self.assertEqual(len(taken_cheap), 1, "the same trade must be taken when the fee is negligible")

    def test_the_semantics_change_is_recorded_where_a_reader_will_find_it(self):
        """§59: a change to historical research semantics that is not announced is a silent one."""
        self.assertIn("RESEARCH-SEMANTICS CHANGE", BT_SRC)
        design = open(os.path.join(ROOT, "docs", "architecture", "SYSTEM-DESIGN.md"), encoding="utf-8").read()
        self.assertIn("§45", design)
        compliance = open(os.path.join(ROOT, "docs", "architecture", "SPEC-COMPLIANCE.md"),
                          encoding="utf-8").read()
        self.assertIn("not comparable", compliance)


class TheFutureMayOnlyDecideTheOutcome(unittest.TestCase):
    """§37's explicit allowance, checked as an allowance rather than assumed."""

    @classmethod
    def setUpClass(cls):
        cls.bt = _bt()

    def test_walk_reads_only_bars_after_the_entry(self):
        bt = self.bt
        H = [10.0] * 50; L = [9.0] * 50; C = [9.5] * 50
        H[30] = 99.0                            # a target-sized spike AFTER the entry
        r = bt.walk("long", 9.5, 8.5, 12.0, H, L, C, 20, 40)   # stop below the series low, so only the
        self.assertEqual(r["outcome"], "win")                  # target can resolve it
        H2 = list(H); H2[30] = 10.0             # remove the spike -> the same entry now times out
        r2 = bt.walk("long", 9.5, 8.5, 12.0, H2, L, C, 20, 40)
        self.assertNotEqual(r2["outcome"], "win")
        self.assertEqual(r["R_planned"], r2["R_planned"], "the PLAN may not move with the future")

    def test_a_spike_before_the_entry_is_not_read_at_all(self):
        bt = self.bt
        H = [10.0] * 50; L = [9.0] * 50; C = [9.5] * 50
        base = bt.walk("long", 9.5, 8.5, 12.0, H, L, C, 20, 40)
        H[5] = 99.0                             # far in the past relative to the entry bar
        self.assertEqual(bt.walk("long", 9.5, 8.5, 12.0, H, L, C, 20, 40), base)



class OneInstrumentTwoProviders(unittest.TestCase):
    """CLAUDE.md §6 and §23, arriving in the research path on 2026-09-18.

    The MT5 CFD import replaced XAUUSD 15m/1H/4H/1D and left 2H/30m/5m on the Yahoo futures proxy, because the
    broker export has no 2H. Every one of those series is individually valid, correctly labelled, and §20
    FRESH -- and a stability table spanning them compares a CFD against a futures contract and prints one
    number. That is the quiet form of the fault §6 forbids loudly on the order path.

    The run is FLAGGED rather than refused, on purpose: refusing would delete the finding along with the
    result, and §38 exists so a research defect can be reported instead of hidden in an exception.
    """

    def _fresh(self):
        import importlib
        spec = importlib.util.spec_from_file_location("bt2", os.path.join(ROOT, "scripts",
                                                                          "backtest-methods.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m

    def test_one_source_per_instrument_is_not_a_mix(self):
        m = self._fresh()
        m.PROVIDERS_SEEN.update({"BTCUSDT": {"1H": "binance", "4H": "binance"}})
        self.assertEqual(m.provider_mix(), {})

    def test_two_sources_for_one_instrument_is_reported(self):
        m = self._fresh()
        m.PROVIDERS_SEEN.update({"XAUUSD": {"1H": "mt5_bridge_history_utc",
                                            "2H": "yahoo_finance_GC=F_research_only"}})
        self.assertIn("XAUUSD", m.provider_mix())

    def test_a_mixed_run_is_flagged_and_names_both_providers(self):
        m = self._fresh()
        m.PROVIDERS_SEEN.update({"XAUUSD": {"1H": "mt5_bridge_history_utc",
                                            "2H": "yahoo_finance_GC=F_research_only"}})
        a = m.assess_run()
        self.assertEqual(a.verdict(), "FLAGGED")
        detail = " ".join(f.get("detail", "") for f in a.stamp().get("findings", []))
        self.assertIn("mt5_bridge_history_utc", detail)
        self.assertIn("yahoo_finance_GC=F_research_only", detail)
        self.assertIn("MORE THAN ONE provider", detail)

    def test_an_undeclared_source_still_counts_as_a_source(self):
        # A series with no `_source` is not "the same provider as everything else" -- it is unknown, and an
        # unknown beside a known one is still two different answers.
        m = self._fresh()
        m.PROVIDERS_SEEN.update({"XAGUSD": {"1H": "mt5_bridge_history_utc", "2H": "UNDECLARED"}})
        self.assertIn("XAGUSD", m.provider_mix())


if __name__ == "__main__":
    unittest.main()
