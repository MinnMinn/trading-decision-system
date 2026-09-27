"""CLAUDE.md §36 -- the canonical decision ordering, made executable.

§36 opens with "The Decision Engine must preserve canonical decision ordering" and then lists seventeen
steps. Before 2026-09-18 this repo had two orderings and neither was that one: twelve prose steps in
`.claude/commands/analyze.md`, and whatever sequence `tick()` happened to run. Writing the canonical order
down found two real defects on the live path, and both are pinned here as named regressions:

* **Step 3 did not exist.** §36 asks for an Event Risk PRECHECK ("an early safety and data-availability
  check") that is distinct from step 14's per-instrument window check. The runner had only step 14, so a
  calendar that could not be read was discovered once per signal, inside the order loop.
* **Step 12 ran at step 17.** The two calculations that can refuse to size an order (`min_notional` on
  futures, the `volume_min` floor on MT5) lived inside `place_limit()`/`place_market()`. A signal that could
  not be sized was therefore declared ELIGIBLE at step 16 and then quietly did nothing.

The other thing these tests exist to stop is a step being silently skipped. A `Trace` refuses an
out-of-order record, refuses a block at a step that may not block, and refuses a block on a dependency §35
does not classify REQUIRED_FOR_DECISION.
"""
import importlib.util
import json
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import decision_order as DO
import trading_system as TS

from live_write_isolation import redirect as _redirect_writes

RUNNER_SRC = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
CLAUDE_MD = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()

_RESTORE_WRITES = None


def setUpModule():
    # The one setUpClass below loads strategy-runner.py fresh; anything that reaches sr.tick() through it
    # would otherwise append a real trace to data/live/latency/ (scripts/tests/live_write_isolation.py).
    global _RESTORE_WRITES
    _RESTORE_WRITES = _redirect_writes()


def tearDownModule():
    _RESTORE_WRITES()


def _raw():
    with open(DO.PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _spec_steps():
    """CLAUDE.md §36's own numbered list, parsed out of the spec rather than retyped."""
    body = CLAUDE_MD.split("36. DECISION ENGINE", 1)[1].split("37. BACKTESTING", 1)[0]
    found = {}
    for line in body.splitlines():
        m = re.match(r"^(\d{1,2})\.\s+(.*\S)\s*$", line.strip())
        if m and 1 <= int(m.group(1)) <= 17:
            found.setdefault(int(m.group(1)), m.group(2))
    return found


class TheRegistryIsTheSpecsOwnList(unittest.TestCase):
    def test_seventeen_steps_numbered_one_to_seventeen(self):
        self.assertEqual([s["n"] for s in DO.STEPS], list(range(1, 18)))
        self.assertEqual(len(set(DO.ORDER)), 17)

    def test_every_step_name_is_claude_mds_own_wording(self):
        """The drift test. If §36's list is edited, this fails rather than the registry quietly disagreeing."""
        spec = _spec_steps()
        self.assertEqual(len(spec), 17, f"parsed {len(spec)} steps out of CLAUDE.md §36, expected 17")
        for s in DO.STEPS:
            self.assertEqual(s["name"], spec[s["n"]], f"step {s['n']} wording drifted from CLAUDE.md §36")

    def test_every_dependency_is_classified_by_section_35(self):
        for s in DO.STEPS:
            for dep in s.get("dependencies") or ():
                self.assertIn(dep, TS.DEPENDENCIES, f"step {s['id']} consults unclassified {dep!r}")

    def test_every_step_says_where_it_lives_or_why_it_does_not(self):
        for s in DO.STEPS:
            for path in DO.PATHS:
                self.assertIn(path, s)
                if s[path] is None:
                    self.assertTrue(str(s.get(f"_{path}_why") or "").strip(),
                                    f"step {s['id']} is absent on {path} and does not say why")

    def test_execution_is_the_only_step_that_may_not_block(self):
        may_not = [s["id"] for s in DO.STEPS if not s["may_block"]]
        self.assertEqual(may_not, ["execution_instruction"])

    # --- mutations: the loader must refuse a registry that would make the order meaningless
    def test_a_renumbered_step_refuses_to_load(self):
        data = _raw(); data["steps"][4]["n"] = 99
        with self.assertRaises(DO.RegistryError) as cm:
            DO._validate(data, DO.PATH)
        self.assertIn("numbering", str(cm.exception))

    def test_a_reordered_step_list_refuses_to_load(self):
        data = _raw(); data["steps"][2], data["steps"][3] = data["steps"][3], data["steps"][2]
        with self.assertRaises(DO.RegistryError):
            DO._validate(data, DO.PATH)

    def test_an_unclassified_dependency_refuses_to_load(self):
        data = _raw(); data["steps"][0]["dependencies"] = ["analytics.moon_phase"]
        with self.assertRaises(DO.RegistryError) as cm:
            DO._validate(data, DO.PATH)
        self.assertIn("§35", str(cm.exception))

    def test_an_unexplained_absence_refuses_to_load(self):
        data = _raw()
        for s in data["steps"]:
            if s["live"] is None:
                del s["_live_why"]
                break
        with self.assertRaises(DO.RegistryError) as cm:
            DO._validate(data, DO.PATH)
        self.assertIn("precheck", str(cm.exception))


class TheTraceEnforcesTheOrder(unittest.TestCase):
    def _trace(self):
        return DO.Trace("scalping", setup={"htf": False, "method": "ICT"}, instrument="BTCUSDT")

    def test_a_canonical_walk_records_and_decides_nothing(self):
        tr = self._trace()
        for sid in DO.ORDER:
            tr.ok(sid)
        self.assertIsNone(tr.decision())
        self.assertTrue(tr.verify())
        self.assertEqual(len(tr.rows), 17)

    def test_going_backwards_raises_and_cites_the_rule(self):
        tr = self._trace()
        tr.ok("event_final")
        with self.assertRaises(DO.OrderViolation) as cm:
            tr.ok("entry_condition")
        self.assertIn("§36", str(cm.exception))
        self.assertIn("may not be reordered", str(cm.exception))

    def test_repeating_a_step_raises(self):
        tr = self._trace()
        tr.ok("data_quality")
        with self.assertRaises(DO.OrderViolation):
            tr.ok("data_quality")

    def test_skipping_forward_is_allowed(self):
        tr = self._trace()
        tr.ok("market_instrument")
        tr.ok("eligibility")
        self.assertEqual(tr.reached(), ("market_instrument", "eligibility"))

    def test_a_skip_must_carry_a_reason(self):
        tr = self._trace()
        with self.assertRaises(ValueError):
            tr.skip("session", "")
        tr.skip("session", "no session gate on this path")
        self.assertEqual(tr.rows[-1]["outcome"], DO.SKIPPED)
        self.assertIsNone(tr.decision(), "a skip is not a decision")

    def test_the_execution_step_may_not_block(self):
        tr = self._trace()
        with self.assertRaises(DO.OrderViolation) as cm:
            tr.block("execution_instruction", "venue said no")
        self.assertIn("may_block=false", str(cm.exception))

    def test_blocking_on_a_visualization_only_input_is_refused(self):
        """Step 11 exists, but `display.expected_path` is VISUALIZATION_ONLY in every system (§35)."""
        tr = self._trace()
        with self.assertRaises(TS.NotGating):
            tr.block("expectation", "no expected path drawn", dep="display.expected_path")

    def test_blocking_on_a_dependency_with_no_trading_system_is_refused(self):
        tr = DO.Trace(None)
        with self.assertRaises(DO.OrderViolation) as cm:
            tr.block("event_final", "blackout", dep="event_risk.calendar")
        self.assertIn("§62", str(cm.exception))

    def test_the_decision_is_the_first_block_in_canonical_order(self):
        tr = self._trace()
        tr.block("event_precheck", "calendar unreadable", outcome="BLOCK_ENTRY", dep="event_risk.calendar")
        tr.block("risk_validation", "R/R too low", outcome="NO_TRADE", dep="risk.net_rr")
        self.assertEqual(tr.decision(), "BLOCK_ENTRY")
        self.assertEqual(len(tr.blocked()), 2)
        self.assertEqual(tr.reasons(), ["calendar unreadable", "R/R too low"])

    def test_an_order_after_a_block_fails_verify(self):
        tr = self._trace()
        tr.block("risk_validation", "R/R too low", dep="risk.net_rr")
        tr.ok("execution_instruction")
        with self.assertRaises(DO.OrderViolation) as cm:
            tr.verify()
        self.assertIn("§62", str(cm.exception))

    def test_an_unknown_outcome_is_refused(self):
        tr = self._trace()
        with self.assertRaises(ValueError):
            tr.record("data_quality", "PROBABLY_FINE")

    def test_the_log_form_is_compact_and_ordered(self):
        tr = self._trace()
        tr.ok("market_instrument"); tr.block("event_final", "x", dep="event_risk.calendar")
        self.assertEqual(tr.as_log(), "1:market_instrument > 14:event_final=BLOCK_ENTRY")


class TheLivePathWalksIt(unittest.TestCase):
    """Parsed from the runner's own source: a step cannot be dropped from the order path unnoticed."""

    CALLS = re.compile(r'\btr\.(ok|block|skip)\(\s*"([a-z_]+)"')

    def _recorded(self):
        return [(kind, sid) for kind, sid in self.CALLS.findall(RUNNER_SRC)]

    def test_every_recorded_step_is_a_canonical_step(self):
        rec = self._recorded()
        self.assertTrue(rec, "strategy-runner.py records no decision steps")
        for _kind, sid in rec:
            self.assertIn(sid, DO.ORDER, f"runner records non-canonical step {sid!r}")

    def test_the_source_records_them_in_canonical_order(self):
        ns = [DO.position(sid) for _kind, sid in self._recorded()]
        self.assertEqual(ns, sorted(ns), f"the runner's trace calls appear out of §36 order: {ns}")

    def test_every_step_the_registry_calls_live_is_recorded(self):
        recorded = {sid for _kind, sid in self._recorded()}
        for sid in DO.implemented("live"):
            self.assertIn(sid, recorded,
                          f"decision-order.json says {sid!r} is implemented live, but the runner never "
                          f"records it -- one of the two is wrong")

    def test_steps_declared_absent_are_recorded_as_skips_not_as_passes(self):
        kinds = {}
        for kind, sid in self._recorded():
            kinds.setdefault(sid, set()).add(kind)
        for sid in DO.unimplemented("live"):
            if sid in kinds:
                self.assertEqual(kinds[sid], {"skip"},
                                 f"{sid!r} is declared unimplemented on the live path but the runner records "
                                 f"it as {sorted(kinds[sid])} -- a step that does not run must not report OK")


class TheTwoDefectsThisFound(unittest.TestCase):
    """Driven through the runner's real `tick()`. Harness shape shared with test_account_profile."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts",
                                                                        "strategy-runner.py"))
        cls.sr = importlib.util.module_from_spec(spec); spec.loader.exec_module(cls.sr)

    def _tick(self, *, blackout=None, calendar_fails=False, min_notional=5.0):
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
        old_load = sr.ER.load
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
        sr.min_notional = (lambda *a, **k: min_notional) if not isinstance(min_notional, Exception) else None
        if isinstance(min_notional, Exception):
            def _raise(*_a, **_k):
                raise min_notional
            sr.min_notional = _raise
        if calendar_fails:
            def _fail(*_a, **_k):
                raise sr.ER.CalendarUnavailable("calendar file is unreadable", "BLOCK_ENTRY")
            sr.ER.load = _fail
        sr.log = lambda kind, **kw: logs.append((kind, kw))
        try:
            sr.tick(live=False, tick_time=sr.now(), ignore_gate=True)
        finally:
            for k, v in old.items():
                setattr(sr, k, v)
            sr.ER.load = old_load
            for p in tmps:
                os.unlink(p)
        return logs

    def _signal(self, logs):
        rows = [kw for kind, kw in logs if kind == "signal"]
        self.assertTrue(rows, "the harness produced no signal row")
        return rows[0]

    # --- defect 1: §36 step 3 did not exist on the live path
    def test_a_readable_calendar_records_the_precheck_as_a_step(self):
        row = self._signal(self._tick())
        self.assertIn("3:event_precheck", row["decision_trace"])
        self.assertTrue(row["ok"], row["reasons"])

    def test_an_unreadable_calendar_blocks_at_step_3_not_at_step_14(self):
        logs = self._tick(calendar_fails=True)
        pre = [kw for kind, kw in logs if kind == "event_precheck"]
        self.assertTrue(pre, "no per-tick event precheck was logged")
        self.assertEqual(pre[0]["action"], "BLOCK_ENTRY")
        row = self._signal(logs)
        self.assertFalse(row["ok"])
        self.assertIn("3:event_precheck=BLOCK_ENTRY", row["decision_trace"])
        self.assertTrue(any("lịch sự kiện" in r for r in row["reasons"]), row["reasons"])

    def test_the_precheck_and_the_final_check_are_different_questions(self):
        """A readable calendar that nonetheless blocks THIS instrument blocks at 14, not at 3."""
        row = self._signal(self._tick(blackout="FOMC 14:00Z"))
        self.assertIn("3:event_precheck", row["decision_trace"])
        self.assertNotIn("3:event_precheck=", row["decision_trace"])   # step 3 passed
        self.assertIn("14:event_final=BLOCK_ENTRY", row["decision_trace"])

    # --- defect 2: §36 step 12 ran at step 17
    def test_a_size_that_cannot_be_computed_blocks_at_step_12(self):
        import risk_model as RM
        logs = self._tick(min_notional=RM.RiskRefused("MIN_NOTIONAL unknown and will not be guessed"))
        row = self._signal(logs)
        self.assertFalse(row["ok"])
        self.assertIn("12:risk_calculation=BLOCK_ENTRY", row["decision_trace"])
        self.assertTrue(any("kích thước lệnh" in r for r in row["reasons"]), row["reasons"])

    def test_a_notional_below_the_venue_minimum_blocks_before_eligibility(self):
        logs = self._tick(min_notional=10 ** 9)
        row = self._signal(logs)
        self.assertFalse(row["ok"])
        trace = row["decision_trace"]
        self.assertLess(trace.index("12:risk_calculation="), trace.index("16:eligibility"),
                        "the sizing refusal must be recorded before final eligibility, not after it")

    # --- the walk itself
    def test_the_live_trace_is_a_canonical_walk(self):
        trace = self._signal(self._tick())["decision_trace"]
        ns = [int(tok.split(":", 1)[0]) for tok in trace.split(" > ")]
        self.assertEqual(ns, sorted(ns), trace)
        self.assertEqual(len(ns), len(set(ns)), "a step was recorded twice")

    def test_a_clean_signal_reaches_the_execution_step(self):
        self.assertIn("17:execution_instruction", self._signal(self._tick())["decision_trace"])

    def test_a_blocked_signal_never_reaches_the_execution_step(self):
        self.assertNotIn("17:execution_instruction",
                         self._signal(self._tick(blackout="FOMC"))["decision_trace"])


if __name__ == "__main__":
    unittest.main()
