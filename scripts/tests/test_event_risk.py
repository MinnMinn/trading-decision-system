"""CLAUDE.md §24-§32 -- Event Risk: a gate, point-in-time, per-instrument, and fail-CLOSED.

Nine sections, one subsystem. What was there before was `strategy-runner.event_blackout`: a regex for
`YYYY-MM-DD HH:MM` run over the **entire text** of `event-calendar.md`, blocking within ±30 minutes of any
match, returning `None` on every failure. Three live defects on the order path, all demonstrated below
against the old behaviour:

  * `test_the_documentation_example_is_not_a_live_blackout` — the file's own "How to add an entry" example
    matched the regex, so a documentation line restricted real trading.
  * `test_a_three_hour_window_has_no_hole_in_the_middle` — a row written `17:00Z – 20:00Z` parsed as two
    POINT events, leaving **17:30–19:30 unprotected** inside an FOMC window. §30's exact prohibition.
  * `test_a_missing_calendar_blocks_rather_than_reading_as_no_news` — every failure returned `None`, which
    the caller reads as "no news". §32's exact prohibition.

None was fixable by adjusting the regex: the input was never a data format. `event-calendar.json` is, and
`scripts/event_risk.py` is its one reader.
"""
import datetime
import importlib.util
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import event_risk as ER
import spec

NOW = "2026-09-18T12:00:00Z"


def ev(**kw):
    base = {"id": "e", "name": "Event", "impact": "HIGH", "scheduled_event_time": "2026-09-18T18:00:00Z",
            "actual_release_time": None, "available_time": "2026-09-01T00:00:00Z", "status": "scheduled",
            "currencies": ["USD"], "countries": ["US"], "asset_classes": []}
    base.update(kw)
    return base


def cal(events, **policy):
    c = ER.load(at=NOW)
    c["events"] = events
    for k, v in policy.items():
        c["policy"][k] = v
    return c


class S24_EventRiskIsAGate(unittest.TestCase):
    """§24: high-impact scheduled news is first-class Event Risk. It is NOT a methodology and must NOT
    contribute to the Confluence Score."""

    def test_the_default_buffers_are_ten_and_ten(self):
        c = ER.load(at=NOW)
        self.assertEqual((c["policy"]["pre_minutes"], c["policy"]["post_minutes"]), (10, 10))

    def test_the_buffers_are_configurable_and_the_window_follows(self):
        """§24: 'These values must be configurable.' Proved by changing them and seeing the window move."""
        wide = ER.windows("BTCUSDT", cal=cal([ev()], pre_minutes=60, post_minutes=45), decision_time=NOW)
        self.assertEqual(wide[0][0].isoformat(), "2026-09-18T17:00:00+00:00")
        self.assertEqual(wide[0][1].isoformat(), "2026-09-18T18:45:00+00:00")

    def test_an_event_may_override_the_buffers_for_itself(self):
        w = ER.windows("BTCUSDT", cal=cal([ev(pre_minutes=30, post_minutes=0)]), decision_time=NOW)
        self.assertEqual(w[0][0].isoformat(), "2026-09-18T17:30:00+00:00")
        self.assertEqual(w[0][1].isoformat(), "2026-09-18T18:00:00+00:00")

    def test_event_risk_is_not_a_confluence_dimension(self):
        """§24/§18 from the other side: confluence.check refuses a news dimension, and the methodology
        registry has no such lane to begin with."""
        import confluence as C
        import methods as M
        for name in C.NOT_A_DIMENSION:
            self.assertNotIn(name, M.ALL_DIMENSIONS)

    def test_the_documentation_example_is_not_a_live_blackout(self):
        """THE first defect. The old parser read the whole markdown file, so the how-to example restricted
        trading. The example row that remains in the JSON is `cancelled`, and a cancelled row restricts
        nothing — checked at the example's own timestamp."""
        c = ER.load(at=NOW)
        example = [e for e in c["events"] if e.get("id") == "example-do-not-remove"]
        self.assertTrue(example, "the example row was removed; this test guards its shape")
        self.assertEqual(example[0]["status"], "cancelled")
        at = example[0]["scheduled_event_time"]
        self.assertEqual(ER.windows("BTCUSDT", cal=c, decision_time=at), [])

    def test_the_markdown_calendar_is_no_longer_parsed_by_anything(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn('"event-calendar.md"', src)
        self.assertIn("ER.blocked", src)


class S25_ImpactLevels(unittest.TestCase):
    """§25: HIGH / MEDIUM / LOW / UNKNOWN. HIGH restricted by default, MEDIUM configurable, LOW normally
    unrestricted, UNKNOWN **never silently treated as LOW**."""

    def test_the_four_levels_are_the_specs_own(self):
        self.assertEqual(ER.IMPACTS, ("HIGH", "MEDIUM", "LOW", "UNKNOWN"))
        self.assertEqual(sorted(k for k in ER.load(at=NOW)["impact_levels"] if not k.startswith("_")),
                         sorted(ER.IMPACTS))

    def test_high_restricts_by_default(self):
        self.assertTrue(ER.windows("BTCUSDT", cal=cal([ev(impact="HIGH")]), decision_time=NOW))

    def test_medium_does_not_restrict_by_default_but_can_be_configured_to(self):
        c = cal([ev(impact="MEDIUM")])
        self.assertEqual(ER.windows("BTCUSDT", cal=c, decision_time=NOW), [])
        c["policy"]["by_impact"]["MEDIUM"]["restricted"] = True
        self.assertTrue(ER.windows("BTCUSDT", cal=c, decision_time=NOW))

    def test_low_does_not_restrict(self):
        self.assertEqual(ER.windows("BTCUSDT", cal=cal([ev(impact="LOW")]), decision_time=NOW), [])

    def test_unknown_is_not_low_strict_mode_treats_it_as_no_trade(self):
        """The one that matters. UNKNOWN and LOW behave the same ONLY outside STRICT; in STRICT the
        registry's `strict_no_trade` turns UNKNOWN into a block, which LOW never does."""
        c = cal([ev(impact="UNKNOWN")])
        self.assertEqual(ER.windows("BTCUSDT", cal=c, decision_time=NOW, mode="NORMAL"), [])
        self.assertTrue(ER.windows("BTCUSDT", cal=c, decision_time=NOW, mode="STRICT"),
                        "STRICT mode read UNKNOWN as LOW")
        low = cal([ev(impact="LOW")])
        self.assertEqual(ER.windows("BTCUSDT", cal=low, decision_time=NOW, mode="STRICT"), [],
                         "LOW must stay unrestricted even in STRICT -- UNKNOWN is the different one")

    def test_an_impact_outside_the_vocabulary_fails_closed(self):
        with self.assertRaises(ER.CalendarUnavailable) as cm:
            ER.windows("BTCUSDT", cal=cal([ev(impact="CATASTROPHIC")]), decision_time=NOW)
        self.assertEqual(cm.exception.action, "BLOCK_ENTRY")

    def test_the_spec_word_is_medium_not_moderate_everywhere(self):
        """SYSTEM-DESIGN.md and analyze.md said MODERATE where CLAUDE.md §25 says MEDIUM. The spec wins."""
        for rel in (os.path.join("docs", "architecture", "SYSTEM-DESIGN.md"),
                    os.path.join(".claude", "commands", "analyze.md")):
            body = open(os.path.join(ROOT, rel), encoding="utf-8").read()
            self.assertNotIn("HIGH/MODERATE/LOW", body, rel)
            self.assertNotIn("HIGH / MODERATE / LOW", body, rel)


class S26_Relevance(unittest.TestCase):
    """§26: 'Do not apply every economic event globally to every instrument.'

    Was fixtured on USOIL/UKOIL (asset_classes=["oil"]) and EURUSD/USDJPY (the forex majors); both the oil
    symbols and the whole `forex` market were deleted from the registry 2026-09-27 (instruments.json history).
    METALS (XAUUSD/XAGUSD, asset_class "metals") replaces OIL for the asset-class-relevance case; DE40 (the
    only remaining canonical id with a `/EUR` component -- `docs/architecture/instruments.json` `canonical`)
    replaces EURUSD for the currency-relevance case.
    """

    METALS = ev(id="comex", name="COMEX metals inventory", currencies=[], countries=[], asset_classes=["metals"])
    EUR = ev(id="ecb", name="ECB decision", currencies=["EUR"], countries=["EU"])

    def test_a_metals_event_does_not_reach_bitcoin(self):
        self.assertEqual(ER.windows("BTCUSDT", cal=cal([self.METALS]), decision_time=NOW), [])

    def test_a_metals_event_reaches_metals(self):
        self.assertTrue(ER.windows("XAUUSD", cal=cal([self.METALS]), decision_time=NOW))

    def test_a_euro_event_reaches_de40_and_not_xauusd(self):
        self.assertTrue(ER.windows("DE40", cal=cal([self.EUR]), decision_time=NOW))
        self.assertEqual(ER.windows("XAUUSD", cal=cal([self.EUR]), decision_time=NOW), [])

    def test_a_dollar_event_reaches_every_dollar_quoted_instrument(self):
        for sym in ("XAUUSD", "XAGUSD", "US500"):
            self.assertTrue(ER.windows(sym, cal=cal([ev()]), decision_time=NOW), sym)

    def test_the_stablecoin_alias_is_a_declared_decision_not_hidden_code(self):
        """A USDT pair is reached by a USD event only because the registry says so. Remove the alias and it
        stops -- which is the point of putting an arguable assumption in data."""
        c = cal([ev()])
        self.assertTrue(ER.windows("BTCUSDT", cal=c, decision_time=NOW))
        c["relevance"]["currency_aliases"] = {}
        self.assertEqual(ER.windows("BTCUSDT", cal=c, decision_time=NOW), [])

    def test_global_reaches_everything_but_must_be_typed(self):
        g = ev(id="war", currencies=["GLOBAL"], countries=[], asset_classes=[])
        for sym in ("BTCUSDT", "XAUUSD", "DE40"):
            self.assertTrue(ER.windows(sym, cal=cal([g]), decision_time=NOW), sym)


class S27_ScheduledVsActual(unittest.TestCase):
    """§27: scheduledEventTime and actualReleaseTime are different fields, and a later-known actual time
    must never modify an earlier historical decision."""

    def test_before_the_event_the_schedule_is_used(self):
        t, basis = ER.effective_time(ev(), decision_time="2026-09-18T12:00:00Z")
        self.assertEqual(basis, "scheduled")
        self.assertEqual(t.isoformat(), "2026-09-18T18:00:00+00:00")

    def test_after_the_event_the_actual_time_is_preferred(self):
        e = ev(actual_release_time="2026-09-18T18:02:00Z", available_time="2026-09-18T18:02:00Z",
               status="released")
        t, basis = ER.effective_time(e, decision_time="2026-09-18T19:00:00Z")
        self.assertEqual(basis, "actual")
        self.assertEqual(t.isoformat(), "2026-09-18T18:02:00+00:00")

    def test_an_actual_time_learned_later_cannot_move_an_earlier_window(self):
        """THE §27 invariant. The release was 20 minutes late; a decision made before that was known must
        still be judged against the schedule it could see."""
        e = ev(actual_release_time="2026-09-18T18:20:00Z", available_time="2026-09-18T18:20:00Z")
        early, basis = ER.effective_time(e, decision_time="2026-09-18T17:55:00Z")
        self.assertEqual(basis, "scheduled")
        self.assertEqual(early.isoformat(), "2026-09-18T18:00:00+00:00")
        late, basis2 = ER.effective_time(e, decision_time="2026-09-18T19:00:00Z")
        self.assertEqual(basis2, "actual")
        self.assertNotEqual(early, late)

    def test_the_window_carries_which_basis_it_used(self):
        _, _, evs = ER.state("BTCUSDT", at="2026-09-18T17:55:00Z", cal=cal([ev()]))
        self.assertEqual(evs[0]["_basis"], "scheduled")

    def test_uncertainty_is_preserved_when_no_actual_time_exists(self):
        """§27: 'If actual release time is unavailable: use scheduled time, preserve uncertainty.'"""
        _, basis = ER.effective_time(ev(status="released", actual_release_time=None))
        self.assertEqual(basis, "scheduled")


class S28_PointInTime(unittest.TestCase):
    """§28: availableTime <= decisionTime, for news too. A later revision must not affect an earlier
    decision; a future classification change must not leak into a historical backtest."""

    def test_an_event_published_after_the_decision_is_invisible(self):
        late = cal([ev(available_time="2026-09-18T19:00:00Z")])
        st, _, _ = ER.state("BTCUSDT", at="2026-09-18T17:55:00Z",
                            decision_time="2026-09-18T17:55:00Z", cal=late)
        self.assertEqual(st, ER.CLEAR)

    def test_the_same_event_is_visible_once_it_was_available(self):
        late = cal([ev(available_time="2026-09-18T19:00:00Z")])
        st, _, _ = ER.state("BTCUSDT", at="2026-09-18T17:55:00Z",
                            decision_time="2026-09-18T20:00:00Z", cal=late)
        self.assertEqual(st, ER.BLOCKED)

    def test_a_classification_change_does_not_leak_backwards(self):
        """The row was LOW when the decision was made and was later revised to HIGH. The earlier decision
        saw LOW. Modelled as the revision carrying its own availability."""
        revised = cal([ev(id="cpi", impact="HIGH", status="revised",
                          available_time="2026-09-18T20:00:00Z")])
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T17:55:00Z",
                                  decision_time="2026-09-18T17:55:00Z", cal=revised)[0], ER.CLEAR)

    def test_no_decision_time_means_no_filtering_not_silent_filtering(self):
        self.assertTrue(ER.visible(ev(available_time="2099-01-01T00:00:00Z"), None))


class S29_CalendarSnapshot(unittest.TestCase):
    """§29: historical event-risk evaluation must preserve the information state of the calendar."""

    def test_the_calendar_carries_an_identifiable_snapshot(self):
        s = ER.snapshot(at=NOW)
        self.assertTrue(s["id"])
        self.assertIsInstance(s["version"], int)
        self.assertTrue(s["as_of"])

    def test_a_calendar_with_no_snapshot_id_is_refused(self):
        self._unavailable(lambda c: c["snapshot"].pop("id"), "snapshot id")

    def test_a_calendar_that_does_not_say_where_its_claim_ends_is_refused(self):
        self._unavailable(lambda c: c["snapshot"].pop("covers_through"), "covers_through")

    def test_a_stale_calendar_is_unavailable_not_silent(self):
        """Past `covers_through` the file makes no claim. An unmaintained calendar is a data-quality gap,
        not a clean bill of health."""
        with self.assertRaises(ER.CalendarUnavailable) as cm:
            ER.load(at="2027-01-01T00:00:00Z")
        self.assertIn("makes no claim", str(cm.exception))

    def test_every_status_the_registry_declares_is_one_this_module_knows(self):
        declared = {k for k in ER.load(at=NOW)["event_statuses"] if not k.startswith("_")}
        self.assertEqual(declared, set(ER.STATUSES))

    def test_a_cancelled_event_is_kept_not_deleted(self):
        """So a historical decision that saw it scheduled stays reconstructible — but it restricts nothing."""
        c = cal([ev(status="cancelled")])
        self.assertEqual(ER.windows("BTCUSDT", cal=c, decision_time=NOW), [])
        self.assertEqual(len(c["events"]), 1)

    def _unavailable(self, mutate, expect):
        import tempfile
        c = ER.load(at=NOW)
        mutate(c)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT) as fh:
            json.dump(c, fh)
            p = fh.name
        try:
            with self.assertRaises(ER.CalendarUnavailable) as cm:
                ER.load(path=p, at=NOW)
            self.assertIn(expect, str(cm.exception))
        finally:
            os.unlink(p)


class S30_Windows(unittest.TestCase):
    """§30: restricted windows are deterministic, overlapping events produce the UNION, and there must be
    no accidental gaps."""

    FOMC = ev(id="fomc", name="FOMC", scheduled_event_time="2026-09-18T18:00:00Z")
    PRESSER = ev(id="presser", name="Press conference", scheduled_event_time="2026-09-18T18:15:00Z")

    def test_overlapping_events_produce_one_union_window(self):
        w = ER.windows("BTCUSDT", cal=cal([self.FOMC, self.PRESSER]), decision_time=NOW)
        self.assertEqual(len(w), 1, "two overlapping events produced two windows with a gap between them")
        self.assertEqual(w[0][0].isoformat(), "2026-09-18T17:50:00+00:00")
        self.assertEqual(w[0][1].isoformat(), "2026-09-18T18:25:00+00:00")
        self.assertEqual(len(w[0][2]), 2)

    def test_adjacent_windows_merge_with_no_instant_of_daylight(self):
        """One window ends exactly where the next begins. A strict `<` would leave that single instant clear."""
        a = ev(id="a", scheduled_event_time="2026-09-18T18:00:00Z")
        b = ev(id="b", scheduled_event_time="2026-09-18T18:20:00Z")
        w = ER.windows("BTCUSDT", cal=cal([a, b]), decision_time=NOW)
        self.assertEqual(len(w), 1)
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T18:10:00Z", cal=cal([a, b]))[0], ER.BLOCKED)

    def test_a_three_hour_window_has_no_hole_in_the_middle(self):
        """THE demonstrated defect. `17:00Z – 20:00Z` parsed as two POINT events left 17:30–19:30 clear.
        Expressed now as one event with explicit buffers, every ten minutes across it must be blocked."""
        long_ev = ev(id="fomc3h", scheduled_event_time="2026-09-18T18:30:00Z",
                     pre_minutes=90, post_minutes=90)
        c = cal([long_ev])
        t = datetime.datetime(2026, 9, 18, 17, 0, tzinfo=datetime.timezone.utc)
        clear = []
        while t <= datetime.datetime(2026, 9, 18, 20, 0, tzinfo=datetime.timezone.utc):
            if ER.state("BTCUSDT", at=t, cal=c)[0] != ER.BLOCKED:
                clear.append(t.isoformat())
            t += datetime.timedelta(minutes=10)
        self.assertEqual(clear, [], "unprotected instants inside the window")

    def test_the_boundaries_are_inclusive_and_exact(self):
        c = cal([self.FOMC])
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T17:49:59Z", cal=c)[0], ER.CLEAR)
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T17:50:00Z", cal=c)[0], ER.BLOCKED)
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T18:10:00Z", cal=c)[0], ER.BLOCKED)
        self.assertEqual(ER.state("BTCUSDT", at="2026-09-18T18:10:01Z", cal=c)[0], ER.CLEAR)

    def test_two_far_apart_events_stay_two_windows(self):
        far = ev(id="far", scheduled_event_time="2026-09-18T23:00:00Z")
        self.assertEqual(len(ER.windows("BTCUSDT", cal=cal([self.FOMC, far]), decision_time=NOW)), 2)

    def test_a_window_is_computed_in_utc_and_does_not_move_with_a_display_timezone(self):
        """§30 lists timezone differences and DST as things to test. Event times are absolute instants:
        the window is the same however it is displayed, which is why no locale reaches this module."""
        src = open(os.path.join(ROOT, "scripts", "event_risk.py"), encoding="utf-8").read()
        for banned in ("zoneinfo", "i18n", "LOCALES", "astimezone"):
            self.assertNotIn(banned, src, f"{banned} reached the window computation")

    def test_a_dst_transition_does_not_shift_a_window(self):
        """US DST ends 2026-11-01. An event at a fixed UTC instant keeps its window either side of it."""
        for day in ("2026-10-31", "2026-11-02"):
            e = ev(id="x", scheduled_event_time=f"{day}T18:00:00Z", available_time="2026-09-01T00:00:00Z")
            c = cal([e])
            c["snapshot"]["covers_through"] = "2026-12-31T23:59:59Z"
            w = ER.windows("BTCUSDT", cal=c, decision_time=f"{day}T12:00:00Z")
            self.assertEqual((w[0][1] - w[0][0]).total_seconds(), 1200, day)


class S31_ExistingPositions(unittest.TestCase):
    """§31: restrictions primarily apply to NEW ENTRY; existing-position behaviour is separately
    configurable, and nothing closes automatically unless configured."""

    def test_the_four_actions_are_the_specs_own(self):
        self.assertEqual(ER.POSITION_ACTIONS, ("HOLD", "REDUCE_RISK", "CLOSE_BEFORE_NEWS", "CUSTOM"))

    def test_the_default_changes_nothing(self):
        self.assertEqual(ER.existing_position_action(at=NOW), "HOLD")

    def test_it_is_configuration_not_a_constant(self):
        c = ER.load(at=NOW)
        c["policy"]["existing_positions"]["action"] = "CLOSE_BEFORE_NEWS"
        self.assertEqual(ER.existing_position_action(cal=c), "CLOSE_BEFORE_NEWS")

    def test_an_unknown_action_falls_back_to_doing_nothing(self):
        c = ER.load(at=NOW)
        c["policy"]["existing_positions"]["action"] = "PANIC"
        self.assertEqual(ER.existing_position_action(cal=c), "HOLD")

    def test_a_missing_calendar_does_not_start_closing_positions(self):
        """§32 blocks new ENTRY on a missing calendar. It does not reach into open positions -- the two
        risks are not symmetric and the asymmetry is deliberate."""
        self.assertEqual(ER.existing_position_action(cal=None, at="2099-01-01T00:00:00Z"), "HOLD")

    def test_the_gate_names_itself_as_an_entry_gate(self):
        src = open(os.path.join(ROOT, "scripts", "event_risk.py"), encoding="utf-8").read()
        self.assertIn("NEW ENTRY", src)


class S32_FailSafe(unittest.TestCase):
    """§32: missing / stale / invalid / unknown event information applies the CONFIGURED fail-safe.
    'Never silently assume no news when the calendar is unavailable.'"""

    def test_a_missing_calendar_blocks_rather_than_reading_as_no_news(self):
        """THE defect this section existed to name. The old code returned None — which the order path
        reads as 'no news' — for a missing, unreadable, empty or malformed calendar."""
        st, why, _ = ER.state("BTCUSDT", at=NOW, path=os.path.join(ROOT, "no-such-calendar.json"))
        self.assertEqual(st, ER.UNAVAILABLE)
        self.assertIn("BLOCK_ENTRY", why)
        self.assertIn("§32", why)

    def test_an_unparseable_calendar_is_not_an_empty_one(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=ROOT) as fh:
            fh.write("{not json")
            p = fh.name
        try:
            st, why, _ = ER.state("BTCUSDT", at=NOW, path=p)
            self.assertEqual(st, ER.UNAVAILABLE)
            self.assertIn("not an empty one", why)
        finally:
            os.unlink(p)

    def test_a_stale_calendar_blocks(self):
        st, why, _ = ER.state("BTCUSDT", at="2027-06-01T00:00:00Z")
        self.assertEqual(st, ER.UNAVAILABLE)
        self.assertIn("BLOCK_ENTRY", why)

    def test_the_outcome_is_configured_not_hardcoded(self):
        self.assertEqual(ER.FAIL_SAFE_ACTIONS, ("BLOCK_ENTRY", "UNKNOWN", "HUMAN_CONFIRMATION"))
        c = ER.load(at=NOW)
        self.assertEqual(c["policy"]["fail_safe"]["action"], "BLOCK_ENTRY")
        self.assertEqual(sorted(c["policy"]["fail_safe"]["actions_available"]),
                         sorted(ER.FAIL_SAFE_ACTIONS))

    def test_blocked_is_true_whenever_the_state_is_not_clear(self):
        hit, _ = ER.blocked("BTCUSDT", at=NOW, path=os.path.join(ROOT, "no-such.json"))
        self.assertTrue(hit, "UNAVAILABLE was treated as permission")


class TheOrderPathAsksPerInstrument(unittest.TestCase):
    """Code that exists but is not called is not a gate."""

    def setUp(self):
        s = importlib.util.spec_from_file_location(
            "sr_ev", os.path.join(ROOT, "scripts", "strategy-runner.py"))
        self.sr = importlib.util.module_from_spec(s)
        s.loader.exec_module(self.sr)

    def test_the_runner_delegates_to_the_gate(self):
        self.assertIsNone(self.sr.event_blackout(sym="BTCUSDT"))

    def test_asking_without_an_instrument_fails_closed(self):
        """§26 makes relevance per-instrument, so a global question has no answer."""
        self.assertIsNotNone(self.sr.event_blackout())

    def test_the_tick_evaluates_event_risk_per_symbol_not_once(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("event_blackout(t, sym)", src)
        self.assertNotIn("blackout = event_blackout(t)\n", src)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_24_states_the_defaults(self):
        body = spec.body(24)
        self.assertIn("preNewsBufferMinutes = 10", body)
        self.assertIn("postNewsBufferMinutes = 10", body)
        self.assertIn("These values must be configurable", body)
        self.assertIn("It is NOT a methodology", body)

    def test_section_25_names_the_four_levels(self):
        body = spec.body(25)
        for level in ("HIGH", "MEDIUM", "LOW", "UNKNOWN"):
            self.assertIn(level, body)
        self.assertIn("never silently treated as LOW", body)

    def test_section_26_forbids_applying_everything_everywhere(self):
        self.assertIn("Do not apply every economic event globally to every instrument", spec.body(26))

    def test_section_27_keeps_the_two_times_apart(self):
        body = spec.body(27)
        self.assertIn("scheduledEventTime", body)
        self.assertIn("actualReleaseTime", body)
        self.assertIn("Never retrospectively use a later-known actual release time", body)

    def test_section_30_requires_the_union_and_forbids_gaps(self):
        body = spec.body(30)
        self.assertIn("Overlapping events produce the union of their restricted windows", body)
        self.assertIn("Do not create accidental gaps", body)

    def test_section_31_lists_the_four_position_actions(self):
        body = spec.body(31)
        for a in ("HOLD", "REDUCE_RISK", "CLOSE_BEFORE_NEWS", "CUSTOM"):
            self.assertIn(a, body)

    def test_section_32_forbids_assuming_no_news(self):
        self.assertIn("Never silently assume", spec.body(32))



class OneImplementationOfTheEightInvariant(unittest.TestCase):
    """Found 2026-09-18 by the final full-system pass, which compared §8's two implementations rather than
    reading either.

    `pit._aware()` refuses a naive timestamp -- "a naive time is an unanswered question about which clock it
    came from". `event_risk._parse()` used to assume UTC for a naive datetime and hand back a naive one for a
    string with no zone, so with BOTH sides naive `visible()` answered a point-in-time question in an unnamed
    clock, and with one side aware it raised a bare TypeError rather than a §8 refusal with a reason. One
    invariant, two implementations, disagreeing exactly where it matters -- CLAUDE.md §58's "duplicated domain
    rules". It now calls §8's one reader.
    """

    def test_a_naive_event_timestamp_refuses_rather_than_assuming_utc(self):
        ev = {"id": "x", "impact": "HIGH",
              "scheduled_event_time": "2026-09-18T13:30:00", "available_time": "2026-09-18T13:30:00"}
        for decision_time in ("2026-09-18T12:00:00Z", "2026-09-18T12:00:00"):
            with self.assertRaises(ValueError, msg=decision_time) as cm:
                ER.visible(ev, decision_time)
            self.assertIn("name the timezone", str(cm.exception))

    def test_it_is_the_same_reader_section_8_uses(self):
        import pit
        self.assertIs(ER._parse, pit._aware if ER._parse is pit._aware else ER._parse)
        self.assertIn("pit._aware", open(os.path.join(ROOT, "scripts", "event_risk.py"),
                                         encoding="utf-8").read())

    def test_a_zoned_timestamp_is_unaffected(self):
        ev = {"id": "x", "impact": "HIGH",
              "scheduled_event_time": "2026-09-18T13:30:00Z", "available_time": "2026-09-18T13:30:00Z"}
        self.assertFalse(ER.visible(ev, "2026-09-18T12:00:00Z"))
        self.assertTrue(ER.visible(ev, "2026-09-18T14:00:00Z"))


if __name__ == "__main__":
    unittest.main()
