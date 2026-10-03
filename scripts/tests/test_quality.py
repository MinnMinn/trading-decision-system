"""CLAUDE.md §20 -- six data-quality states, computed, and what a failing REQUIRED input does.

§7 already produced a quality word per series (`normalized.QUALITY` = AVAILABLE / STALE / MOCK / UNAVAILABLE)
and said so in its own docstring: "PARTIAL / INVALID / UNKNOWN are §20's work and are not invented early."
This is that work. Three of §20's six states were unrepresentable, so:

  * a series with holes in it and a complete one produced the same word,
  * corrupt provider data (high below low, bars out of order, a repeated timestamp) read as AVAILABLE,
  * and there was no way to say "I cannot tell", so every uncertainty collapsed into a confident word.

§20's second half -- "critical required inputs that do not satisfy their configured quality requirement must
prevent unsafe decision-making", with WAIT / NO TRADE / BLOCK ENTRY / UNKNOWN / HUMAN CONFIRMATION -- existed
only as prose a model was asked to narrate. It is now computed, and wired into the one place a decision is
actually made from candles.

Every detector below is tested by BREAKING a real series, not by asserting over a hand-built happy path: a
guard that has never been seen to fail has not been seen to work.
"""
import copy
import datetime
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import normalized as N
import quality as Q
import spec

NOW = datetime.datetime(2026, 9, 18, 0, 5, tzinfo=datetime.timezone.utc)
LIVE = os.path.join(ROOT, "data", "live", "market-data", "ohlcv.BTCUSDT.15m.json")


def live():
    with open(LIVE, encoding="utf-8") as fh:
        return json.load(fh)


class TheSixStatesExist(unittest.TestCase):
    def test_the_vocabulary_is_the_specs_own(self):
        self.assertEqual(Q.STATES, ("FRESH", "STALE", "MISSING", "PARTIAL", "INVALID", "UNKNOWN"))

    def test_the_outcomes_are_the_specs_own(self):
        self.assertEqual(Q.DECISIONS, ("WAIT", "NO_TRADE", "BLOCK_ENTRY", "UNKNOWN", "HUMAN_CONFIRMATION"))

    def test_every_state_maps_to_an_outcome(self):
        for st in Q.STATES:
            self.assertIn(st, Q.DEFAULT_ACTION, f"{st} has no declared consequence")
        for st, act in Q.DEFAULT_ACTION.items():
            if act is not None:
                self.assertIn(act, Q.DECISIONS)

    def test_an_invented_state_is_refused(self):
        with self.assertRaises(ValueError):
            Q.usable("PROBABLY_FINE")


class TheLiveDataIsFresh(unittest.TestCase):
    """The baseline that makes every mutation below meaningful. A detector that fires on good data is not a
    detector, it is an outage."""

    def test_every_live_series_reads_fresh(self):
        import glob
        checked = 0
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "live", "*", "ohlcv.*.json"))):
            base = os.path.basename(f).split(".")
            sym, tf = base[1], base[2]
            with open(f, encoding="utf-8") as fh:
                state, why = Q.assess(json.load(fh), tf, symbol=sym, now=NOW)
            self.assertEqual(state, "FRESH", f"{sym} {tf}: {why}")
            checked += 1
        self.assertGreater(checked, 40, "the survey found almost no series -- it is not proving anything")

    def test_a_young_instruments_short_history_is_not_partial(self):
        """ASTERUSDT's 1W series holds 50 bars against a 240-bar window and is COMPLETE -- the coin is young.
        This is why PARTIAL is computed from continuity and not from a bar count."""
        p = os.path.join(ROOT, "data", "live", "market-data", "ohlcv.ASTERUSDT.1W.json")
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        self.assertLess(len(d["candles"]), 100, "precondition: this series is short")
        self.assertEqual(Q.assess(d, "1W", symbol="ASTERUSDT", now=NOW)[0], "FRESH")

    def test_a_cfd_series_weekend_gaps_are_not_partial(self):
        """XAUUSD 1D has 125 gaps and every one is a closure. Reporting those would gate a market on correct
        data, which is the §20 error in the other direction."""
        # The STORED broker history (tracked in the repo, present on every machine) rather than the machine-local live
        # bridge file, which exists only where MetaTrader runs -- cut at NOW so the series is as fresh as it was then.
        import history_store as HS
        doc, _shape = HS.read_doc("XAUUSD", "1D", root=os.path.join(ROOT, "data", "history", "ftmo"))
        self.assertIsNotNone(doc, "precondition: the stored FTMO XAUUSD 1D history is in the repo")
        stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
        d = dict(doc, candles=[c for c in doc["candles"] if c["time"] < stamp][-600:])
        self.assertGreater(sum(1 for a, b in zip(d["candles"], d["candles"][1:])
                               if b["time"][:10] > a["time"][:10] and
                               (datetime.date.fromisoformat(b["time"][:10]) - datetime.date.fromisoformat(a["time"][:10])).days > 1),
                           50, "precondition: the window contains many closures (weekends)")
        self.assertFalse(I.is_continuous("XAUUSD"), "precondition: the CFD tape closes")
        self.assertEqual(Q.assess(d, "1D", symbol="XAUUSD", now=NOW)[0], "FRESH")


class PartialIsReachable(unittest.TestCase):
    """The state that did not exist. Each case mutates the real BTCUSDT series."""

    def test_a_hole_in_a_continuous_series_is_partial(self):
        d = live()
        del d["candles"][300]
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "PARTIAL")
        self.assertIn("missing", why)

    def test_the_reason_names_where_the_hole_is(self):
        d = live()
        edge = d["candles"][300]["time"]
        del d["candles"][300]
        self.assertIn(d["candles"][299]["time"], Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[1])
        self.assertNotIn(edge, Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[1])

    def test_the_same_hole_in_a_non_continuous_market_is_not_claimed(self):
        """Not because it is fine -- because this module cannot tell, and §20 forbids the guess."""
        d = live()
        del d["candles"][300]
        self.assertEqual(Q.assess(d, "15m", continuous=False, now=NOW)[0], "FRESH")

    def test_a_short_fetch_is_partial_when_the_caller_knows_its_window(self):
        d = live()
        d["candles"] = d["candles"][-120:]
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", expected_bars=576, now=NOW)
        self.assertEqual(state, "PARTIAL")
        self.assertIn("120 of 576", why)

    def test_an_unclosed_last_bar_does_not_make_a_window_partial(self):
        d = live()
        d["candles"] = d["candles"][1:]
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", expected_bars=576, now=NOW)[0], "FRESH")


class InvalidIsReachable(unittest.TestCase):
    """Corrupt provider data. Every one of these read as AVAILABLE before."""

    def test_a_high_below_its_low(self):
        d = live()
        d["candles"][10]["high"], d["candles"][10]["low"] = d["candles"][10]["low"], d["candles"][10]["high"]
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "INVALID")

    def test_a_close_outside_the_bar(self):
        d = live()
        d["candles"][10]["close"] = float(d["candles"][10]["high"]) * 2
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "INVALID")
        self.assertIn("outside the high-low range", why)

    def test_bars_out_of_order(self):
        d = live()
        d["candles"][10], d["candles"][11] = d["candles"][11], d["candles"][10]
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "INVALID")

    def test_a_repeated_timestamp(self):
        d = live()
        d["candles"][11]["time"] = d["candles"][10]["time"]
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "INVALID")
        self.assertIn("repeats", why)

    def test_a_missing_ohlc_field(self):
        d = live()
        del d["candles"][10]["low"]
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "INVALID")

    def test_a_non_numeric_price(self):
        d = live()
        d["candles"][10]["open"] = "n/a"
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "INVALID")

    def test_a_series_that_is_not_a_series(self):
        self.assertEqual(Q.assess({"candles": "soon"}, "15m", now=NOW)[0], "INVALID")

    def test_invalid_outranks_partial(self):
        """A corrupt series should not be reported as merely incomplete -- the reader would go looking for
        the missing bars instead of for the broken one."""
        d = live()
        del d["candles"][300]
        d["candles"][10]["high"] = 0
        self.assertEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "INVALID")


class MissingAndUnknownAreReachable(unittest.TestCase):
    def test_no_file_at_all_is_missing(self):
        self.assertEqual(Q.assess(None, "15m")[0], "MISSING")

    def test_an_empty_series_is_missing_not_invalid(self):
        """Zero candles is an absent answer, not a malformed one. §20 keeps MISSING and INVALID apart because
        they lead to different responses."""
        self.assertEqual(Q.assess({"candles": []}, "15m")[0], "MISSING")

    def test_a_series_that_cannot_date_itself_is_unknown(self):
        d = live()
        del d["last_updated"]
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "UNKNOWN")
        self.assertIn("§20", why)

    def test_unknown_is_never_quietly_downgraded(self):
        """§9: 'Unknown is a valid state.' It must not read as FRESH just because the bars look fine."""
        d = live()
        d["last_updated"] = None
        self.assertNotEqual(Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)[0], "FRESH")


class StaleIsStillStale(unittest.TestCase):
    def test_an_old_write_is_stale(self):
        # `late` is derived from the SERIES' own last_updated, not from the module-level NOW. NOW is a fixed
        # wall-clock instant and the file under it is rewritten by the live scanner every few minutes, so
        # `NOW + 6h` drifts from "comfortably past the staleness threshold" to "not past it at all" purely
        # with the time of day the suite is run -- which is what it did on 2026-09-18 at 05:39Z, a failure
        # about the clock and not about staleness. Anchoring to the write makes the interval mean what the
        # test says it means.
        d = live()
        written = datetime.datetime.fromisoformat(str(d["last_updated"]).replace("Z", "+00:00"))
        late = written + datetime.timedelta(minutes=15 * (N.STALE_AFTER_BARS + 1))
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=late)
        self.assertEqual(state, "STALE")
        self.assertIn(str(N.STALE_AFTER_BARS), why)

    def test_the_threshold_is_the_one_normalized_already_owns(self):
        """A second staleness constant would drift from §7's on the first tuning."""
        src = open(os.path.join(ROOT, "scripts", "quality.py"), encoding="utf-8").read()
        self.assertIn("N.STALE_AFTER_BARS", src)
        self.assertNotIn("STALE_AFTER_BARS =", src)


class TheForbiddenConversions(unittest.TestCase):
    """§20: 'Never silently convert UNKNOWN -> LOW, MISSING -> EMPTY, STALE -> FRESH.'"""

    def test_spelling_any_of_them_raises(self):
        for a, b in (("UNKNOWN", "LOW"), ("MISSING", "EMPTY"), ("STALE", "FRESH")):
            with self.assertRaises(ValueError):
                Q.coerce(a, b)

    def test_the_refusal_quotes_the_rule_it_is_enforcing(self):
        try:
            Q.coerce("MISSING", "EMPTY")
        except ValueError as e:
            self.assertIn("§20", str(e))
            self.assertIn("allow-list", str(e), "the message should name the legitimate alternative")

    def test_a_mock_series_gets_no_quality_state_from_the_seven_word_translation(self):
        """MOCK is a PROVENANCE question (§7/§6), not a quality one. Mapping it to FRESH is how a fixture
        ends up satisfying a live requirement."""
        self.assertIsNone(Q.from_normalized("MOCK"))
        for word in ("AVAILABLE", "STALE", "UNAVAILABLE"):
            self.assertIn(Q.from_normalized(word), Q.STATES)

    def test_a_fresh_fixture_says_it_is_a_fixture(self):
        d = live()
        d["_mock"] = True
        state, why = Q.assess(d, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "FRESH", "a complete, freshly written fixture IS fresh data")
        self.assertIn("FIXTURE", why, "...but a reader of the state alone would never learn that")


class TheGate(unittest.TestCase):
    """§20's second half: a failing REQUIRED input prevents the unsafe decision."""

    def test_all_required_inputs_usable_gates_nothing(self):
        self.assertEqual(Q.gate({"ict": "FRESH"}, required=("ict",)), (None, []))

    def test_each_state_produces_its_declared_outcome(self):
        for state, expected in Q.DEFAULT_ACTION.items():
            if expected is None:
                continue
            self.assertEqual(Q.gate({"x": state}, required=("x",))[0], expected, state)

    def test_an_absent_input_is_missing_not_absent(self):
        """A required input nobody reported on is MISSING, not silently skipped."""
        self.assertEqual(Q.gate({}, required=("ict",))[0], "NO_TRADE")

    def test_an_optional_input_never_gates(self):
        """§62: only REQUIRED_FOR_DECISION may gate entry."""
        self.assertEqual(Q.gate({"ict": "FRESH", "wyckoff": "MISSING"}, required=("ict",)), (None, []))

    def test_the_most_restrictive_outcome_wins(self):
        """A run that would BLOCK_ENTRY must not merely WAIT because a second input was only late."""
        d, _ = Q.gate({"a": "PARTIAL", "b": "STALE"}, required=("a", "b"))
        self.assertEqual(d, "BLOCK_ENTRY")

    def test_every_failing_input_is_named_in_the_reasons(self):
        _, why = Q.gate({"a": "PARTIAL", "b": "STALE"}, required=("a", "b"))
        self.assertEqual(len(why), 2)
        self.assertTrue(any("'a'" in r for r in why) and any("'b'" in r for r in why))

    def test_a_configured_allowance_is_explicit_not_a_relabelling(self):
        """§20: requirements 'may differ by data type, methodology, setup, Trading System, timeframe, market
        type, account, mode'. A system that accepts STALE says so; it does not rename STALE to FRESH."""
        self.assertEqual(Q.gate({"x": "STALE"}, required=("x",), allow=("FRESH", "STALE")), (None, []))


class ContinuityIsARegistryFact(unittest.TestCase):
    def test_every_market_declares_whether_its_tape_closes(self):
        with open(os.path.join(ROOT, "docs", "architecture", "instruments.json"), encoding="utf-8") as fh:
            markets = json.load(fh)["markets"]
        for m in [k for k in markets if not k.startswith("_")]:
            self.assertIsInstance(markets[m].get("continuous"), bool, f"market {m} does not declare it")

    def test_the_registry_refuses_a_market_that_does_not(self):
        """Mutation test: instruments.py resolves its registry relative to its own location, so a throwaway
        tree with one key removed exercises the real loader without touching the repo's file."""
        import importlib.util
        import shutil
        import tempfile
        with open(os.path.join(ROOT, "docs", "architecture", "instruments.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        del data["markets"]["crypto"]["continuous"]
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "docs", "architecture"))
            shutil.copy(os.path.join(ROOT, "scripts", "instruments.py"), os.path.join(tmp, "scripts"))
            with open(os.path.join(tmp, "docs", "architecture", "instruments.json"), "w") as fh:
                json.dump(data, fh)
            s = importlib.util.spec_from_file_location(
                "inst_bad", os.path.join(tmp, "scripts", "instruments.py"))
            mod = importlib.util.module_from_spec(s)
            with self.assertRaises(ValueError) as cm:
                s.loader.exec_module(mod)
        self.assertIn("continuous", str(cm.exception))

    def test_the_required_key_check_names_it(self):
        src = open(os.path.join(ROOT, "scripts", "instruments.py"), encoding="utf-8").read()
        self.assertIn('"data_dir", "tick_volume", "continuous", "default_enabled"', src)

    def test_an_unknown_symbol_is_refused_rather_than_guessed(self):
        with self.assertRaises(KeyError):
            I.is_continuous("NOTASYMBOL")


class TheDecisionPathActuallyAsks(unittest.TestCase):
    """Code that exists but is never called is not a guard. This pins the wiring."""

    def setUp(self):
        import importlib.util
        s = importlib.util.spec_from_file_location(
            "strategy_runner", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        self.sr = importlib.util.module_from_spec(s)
        s.loader.exec_module(self.sr)

    def test_a_holed_live_series_stops_the_decision(self):
        d = live()
        del d["candles"][300]
        with self.assertRaises(RuntimeError) as cm:
            self.sr._require_quality("BTCUSDT", "15m", d, now=NOW)
        self.assertIn("PARTIAL", str(cm.exception))
        self.assertIn("BLOCK_ENTRY", str(cm.exception))

    def test_a_sound_live_series_does_not(self):
        self.sr._require_quality("BTCUSDT", "15m", live(), now=NOW)

    def test_a_replay_flags_rather_than_refuses(self):
        """§38 offers 'flagged OR invalidated'. Refusing would delete the finding along with the result."""
        d = live()
        del d["candles"][300]
        self.sr.QUALITY_FLAGS.clear()
        self.sr._REPLAY_QUALITY.clear()
        self.sr._require_quality("BTCUSDT", "15m", d, allow=("FRESH", "STALE", "UNKNOWN"),
                                 now=NOW, at="2026-01-01T00:00:00Z")
        self.assertEqual(len(self.sr.QUALITY_FLAGS), 1)
        self.assertEqual(self.sr.QUALITY_FLAGS[0]["state"], "PARTIAL")

    def test_the_backtest_loader_is_where_research_actually_reads(self):
        """`strategy-runner --replay` reaches its data through bt.scan -> bt.load, NOT through fetch_candles.
        A check placed only on the runner's replay branch would be code that never runs during a backtest --
        which is what a real replay emitting no flags revealed."""
        import importlib.util
        s = importlib.util.spec_from_file_location(
            "bt_q", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        bt = importlib.util.module_from_spec(s)
        s.loader.exec_module(bt)
        if not os.path.exists(os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.1H.json")):
            self.skipTest("the stored history is not in this checkout")
        bt.load("BTCUSDT", "1H")
        self.assertTrue(any(f["symbol"] == "BTCUSDT" and f["state"] == "PARTIAL" for f in bt.QUALITY_FLAGS),
                        "the backtest loader read a holed history and said nothing")

    def test_the_backtest_loader_does_not_flag_a_sound_series(self):
        import importlib.util
        s = importlib.util.spec_from_file_location(
            "bt_q2", os.path.join(ROOT, "scripts", "backtest-methods.py"))
        bt = importlib.util.module_from_spec(s)
        s.loader.exec_module(bt)
        p = os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.15m.json")
        if not os.path.exists(p):
            self.skipTest("the stored history is not in this checkout")
        bt.load("BTCUSDT", "15m")
        self.assertEqual(bt.QUALITY_FLAGS, [], "a sound archive was flagged -- STALE is not a fault here")

    def test_the_stored_history_really_does_carry_the_fault_this_found(self):
        """Not a hypothetical: BTCUSDT/ETHUSDT/SOLUSDT all miss 2023-03-24T13:00Z in their 1H history, one
        provider outage every backtest over that range has replayed as whole."""
        found = {}
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            p = os.path.join(ROOT, "data", "history", f"ohlcv.{sym}.1H.json")
            if not os.path.exists(p):
                self.skipTest(f"{p} is not in this checkout")
            with open(p, encoding="utf-8") as fh:
                found[sym] = Q.assess(json.load(fh), "1H", symbol=sym, now=NOW)
        for sym, (state, why) in found.items():
            self.assertEqual(state, "PARTIAL", f"{sym} no longer carries the hole: {why}")
            self.assertIn("2023-03-24", why)

    def test_the_replay_verdict_is_computed_once_per_series(self):
        d = live()
        del d["candles"][300]
        self.sr.QUALITY_FLAGS.clear()
        self.sr._REPLAY_QUALITY.clear()
        for _ in range(5):
            self.sr._require_quality("BTCUSDT", "15m", d, allow=("FRESH", "STALE", "UNKNOWN"),
                                     now=NOW, at="2026-01-01T00:00:00Z")
        self.assertEqual(len(self.sr.QUALITY_FLAGS), 1, "one fault was recorded once per tick")


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_20_names_these_six_states(self):
        body = spec.body(20)
        for word in ("FRESH", "STALE", "MISSING", "PARTIAL", "INVALID", "UNKNOWN"):
            self.assertIn(word, body)

    def test_section_20_names_these_five_outcomes(self):
        body = spec.body(20)
        for phrase in ("WAIT", "NO TRADE", "BLOCK ENTRY", "HUMAN CONFIRMATION"):
            self.assertIn(phrase, body)

    def test_section_20_forbids_the_three_conversions(self):
        body = spec.body(20)
        self.assertIn("Never silently convert", body)
        for pair in ("UNKNOWN", "LOW", "MISSING", "EMPTY", "STALE", "FRESH"):
            self.assertIn(pair, body)

    def test_section_20_says_requirements_may_differ_by_configuration(self):
        body = spec.body(20)
        for axis in ("data type", "methodology", "setup", "Trading System", "timeframe", "market type",
                     "account", "mode"):
            self.assertIn(axis, body)


if __name__ == "__main__":
    unittest.main()


class TheDocumentedCallPathWorks(unittest.TestCase):
    """`assess(normalized.load(...))` is what the module's own docstring tells a caller to write.

    It returned UNKNOWN for every live series, because `normalized.load()` lifts `last_updated` into
    `provenance.received_time` and leaves no copy at the top level -- so a required input gated on
    HUMAN_CONFIRMATION with perfectly fresh data behind it. Every earlier test fed the RAW dict from disk, so
    the suite was green while the documented path was broken. Found by running the real call.
    """

    def test_a_normalized_series_reads_fresh(self):
        s = N.load("BTCUSDT", "15m")
        state, why = Q.assess(s, "15m", symbol="BTCUSDT", now=NOW)
        self.assertEqual(state, "FRESH", why)

    def test_both_spellings_of_the_receive_time_agree(self):
        raw, norm = live(), N.load("BTCUSDT", "15m")
        self.assertEqual(Q.assess(raw, "15m", symbol="BTCUSDT", now=NOW)[0],
                         Q.assess(norm, "15m", symbol="BTCUSDT", now=NOW)[0])

    def test_a_series_with_neither_spelling_is_still_unknown(self):
        s = dict(N.load("BTCUSDT", "15m"))
        s["provenance"] = {k: v for k, v in s["provenance"].items() if k != "received_time"}
        self.assertEqual(Q.assess(s, "15m", symbol="BTCUSDT", now=NOW)[0], "UNKNOWN")

    def test_every_live_series_reads_fresh_through_the_loader_too(self):
        import glob
        n = 0
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "live", "*", "ohlcv.*.json"))):
            b = os.path.basename(f).split(".")
            sym, tf = b[1], b[2]
            state, why = Q.assess(N.load(sym, tf), tf, symbol=sym, now=NOW)
            self.assertEqual(state, "FRESH", f"{sym} {tf}: {why}")
            n += 1
        self.assertGreater(n, 40)
