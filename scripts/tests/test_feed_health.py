"""CLAUDE.md §52 REALTIME DATA -- what a polling feed does instead of a socket, and how it goes wrong silently.

§52 is written for a WebSocket and this repo has none. Four of its ten requirements are about a connection
nobody opens; they are declared not-applicable **with a reason and with what would make them apply**, and the
loader refuses an exemption missing either — an exemption that outlives the transport justifying it is how a
requirement quietly disappears.

The sentence that survives any transport is *"do not trade from silently stale state"*, and the word is
**silently**. §20 catches everything wrong INSIDE one response. These tests are about the faults that only
exist BETWEEN polls, each of which returns a response §20 finds perfectly valid:

* a series that stopped advancing;
* bars missing since the previous poll;
* a series that went backwards;
* a closed bar that came back with different values.

**Two false positives shaped this module and both are pinned below.** Identical polls inside one bar are
normal, not a stall — the first version called all 32 feeds stalled when three ticks ran in a minute. And
`last_updated` advancing while bars stand still is normal *here*, because `fetch-binance-klines.sh` stamps it
with the fetch time — the second version called all 28 crypto feeds stalled for that reason. Running it is
what showed both.
"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import feed_health as FH
import quality as Q

REGISTRY = os.path.join(ROOT, "docs", "architecture", "feed-health.json")
RUNNER_SRC = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()


def bars(times, close=100.0):
    return [{"time": t, "open": close, "high": close + 1, "low": close - 1, "close": close} for t in times]


def series(n, *, start_hour=0, close=100.0):
    return bars([f"2026-09-18T{start_hour + i:02d}:00:00Z" for i in range(n)], close)


class TheRegistryIsTheSpec(unittest.TestCase):
    def test_all_ten_requirements_claude_md_52_names_are_declared(self):
        spec = open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8").read()
        body = spec.split("52. REALTIME DATA", 1)[1].split("The system must detect", 1)[0]
        want = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
        self.assertEqual([FH.spec_name(r) for r in FH.REQ_ORDER], want)

    def test_six_apply_to_this_transport_and_four_do_not(self):
        self.assertEqual(len(FH.APPLICABLE), 6)
        self.assertEqual(set(FH.NOT_APPLICABLE),
                         {"connection_lifecycle", "heartbeat", "reconnect", "exponential_backoff"})

    def test_every_exemption_says_why_and_what_would_end_it(self):
        # An exemption that outlives the transport justifying it is how a requirement disappears.
        for rid in FH.NOT_APPLICABLE:
            r = FH.requirement(rid)
            self.assertTrue(r["_why"].strip(), rid)
            self.assertTrue(r["becomes_applicable_when"].strip(), rid)

    def test_every_applicable_requirement_names_its_implementation(self):
        for rid in FH.APPLICABLE:
            self.assertTrue(FH.requirement(rid)["implemented_by"].strip(), rid)

    def test_an_exemption_without_a_reason_is_refused(self):
        data = json.load(open(REGISTRY, encoding="utf-8"))
        for r in data["requirements"]:
            if r["applies"] is False:
                r.pop("_why")
                break
        p = os.path.join(ROOT, "scripts", "tests", "__mutant-feed.json")
        try:
            json.dump(data, open(p, "w"))
            with self.assertRaises(FH.RegistryError) as cm:
                FH._load(p)
            self.assertIn("indistinguishable from 'not done'", str(cm.exception))
        finally:
            os.remove(p)

    def test_unknown_must_be_declared_not_healthy(self):
        # A restart must not launder a stalled feed.
        self.assertIn("NOT healthy", FH._DATA["states"][FH.UNKNOWN])


class TheFaultsThatOnlyExistBetweenPolls(unittest.TestCase):
    def setUp(self):
        self.p = os.path.join(tempfile.mkdtemp(), "fh.json")

    def _obs(self, candles, *, now, tf="1H", lu=None):
        return FH.observe("prov", "BTCUSDT", tf, candles, last_updated=lu, now=now, path=self.p)

    def test_the_first_observation_is_unknown_not_healthy(self):
        r = self._obs(series(5), now="2026-09-18T05:00:00Z")
        self.assertEqual(r["state"], FH.UNKNOWN)

    def test_an_advancing_feed_is_healthy(self):
        self._obs(series(5), now="2026-09-18T05:00:00Z")
        r = self._obs(series(6), now="2026-09-18T06:00:00Z")
        self.assertEqual(r["state"], FH.HEALTHY)

    def test_identical_polls_inside_one_bar_are_not_a_stall(self):
        # The first false positive: three ticks in a minute called every feed in the repo stalled.
        self._obs(series(5), now="2026-09-18T04:10:00Z")
        for minute in ("04:20:00", "04:30:00", "04:40:00"):
            r = self._obs(series(5), now=f"2026-09-18T{minute}Z")
            self.assertEqual(r["state"], FH.HEALTHY, minute)

    def test_last_updated_advancing_while_bars_stand_still_is_not_a_stall_here(self):
        # The second false positive: fetch-binance-klines.sh stamps last_updated with the FETCH time, so it
        # advances on every poll by design. Reading the field's name would not have shown this; running it did.
        self._obs(series(5), now="2026-09-18T04:10:00Z", lu="2026-09-18T04:10:00Z")
        r = self._obs(series(5), now="2026-09-18T04:20:00Z", lu="2026-09-18T04:20:00Z")
        self.assertEqual(r["state"], FH.HEALTHY)

    def test_a_feed_that_stops_advancing_for_several_bars_is_stalled(self):
        self._obs(series(5), now="2026-09-18T05:00:00Z")
        r = self._obs(series(5), now="2026-09-18T09:00:00Z")      # 4h past a 1H bar's close
        self.assertEqual(r["state"], FH.STALLED)
        self.assertIn("not advancing", r["findings"][0])

    def test_a_gap_since_the_previous_poll_is_detected(self):
        self._obs(series(3), now="2026-09-18T03:00:00Z")           # newest 02:00
        r = self._obs(bars(["2026-09-18T06:00:00Z", "2026-09-18T07:00:00Z"]), now="2026-09-18T07:30:00Z")
        self.assertEqual(r["state"], FH.GAPPED)
        self.assertIn("never seen", r["findings"][0])

    def test_a_feed_that_goes_backwards_is_regressed(self):
        self._obs(series(6), now="2026-09-18T06:00:00Z")
        r = self._obs(series(3), now="2026-09-18T07:00:00Z")
        self.assertEqual(r["state"], FH.REGRESSED)

    def test_a_revised_closed_bar_is_detected(self):
        # §8's provider correction, arriving live: the decision that read the old value was made on
        # information the provider has since withdrawn.
        first = series(5)
        self._obs(first, now="2026-09-18T05:00:00Z")
        revised = [dict(c) for c in first]
        revised[1]["close"] = 999.0
        revised.append({"time": "2026-09-18T05:00:00Z", "open": 100, "high": 101, "low": 99, "close": 100})
        r = self._obs(revised, now="2026-09-18T06:00:00Z")
        self.assertEqual(r["state"], FH.REVISED)

    def test_the_newest_bar_changing_is_not_a_revision(self):
        # The newest bar is the one still settling; only an ALREADY-CLOSED bar changing is a revision.
        # (Written the wrong way round first: appending a NEWER bar makes the changed one closed, and the
        # module correctly called that a revision.)
        first = series(5)
        self._obs(first, now="2026-09-18T05:00:00Z")
        moved = [dict(c) for c in first]
        moved[-1] = dict(moved[-1], close=123.0)
        r = self._obs(moved, now="2026-09-18T06:00:00Z")
        self.assertNotEqual(r["state"], FH.REVISED)

    def test_recovery_is_recorded_rather_than_erasing_the_incident(self):
        self._obs(series(5), now="2026-09-18T05:00:00Z")
        self._obs(series(5), now="2026-09-18T09:00:00Z")           # stalled
        r = self._obs(series(10), now="2026-09-18T10:00:00Z")
        self.assertEqual(r["state"], FH.HEALTHY)
        self.assertTrue(r["recovered"])
        self.assertGreaterEqual(r["incidents"], 1)


class FeedHealthFeedsTheSame20Gate(unittest.TestCase):
    """§52: 'Realtime data quality must feed into the same data-quality and required-analysis rules used by
    the Decision Engine.'"""

    def test_every_state_maps_onto_a_real_20_state(self):
        for st in (FH.HEALTHY, FH.STALLED, FH.GAPPED, FH.REGRESSED, FH.REVISED, FH.UNKNOWN):
            self.assertIn(FH.as_quality(st), Q.STATES, st)

    def test_a_stalled_feed_maps_to_stale_and_a_gapped_one_to_partial(self):
        self.assertEqual(FH.as_quality(FH.STALLED), "STALE")
        self.assertEqual(FH.as_quality(FH.GAPPED), "PARTIAL")

    def test_a_regressed_or_revised_feed_is_invalid(self):
        # A series that goes backwards is not a series; a withdrawn bar is information a decision may already
        # have used.
        self.assertEqual(FH.as_quality(FH.REGRESSED), "INVALID")
        self.assertEqual(FH.as_quality(FH.REVISED), "INVALID")

    def test_unknown_maps_to_unknown_not_to_fresh(self):
        self.assertEqual(FH.as_quality(FH.UNKNOWN), "UNKNOWN")

    def test_the_mapped_states_produce_the_blocking_outcomes_20_defines(self):
        for feed_state, expect_block in ((FH.STALLED, True), (FH.GAPPED, True), (FH.REGRESSED, True),
                                         (FH.REVISED, True), (FH.HEALTHY, False)):
            decision, _ = Q.gate({"candles": FH.as_quality(feed_state)}, required=("candles",))
            self.assertEqual(bool(decision), expect_block, feed_state)

    def test_there_is_no_second_gate_in_this_module(self):
        # A second, quieter gate would be a second place for an entry to be allowed. Checked on the CODE, not
        # on the prose: `as_quality` names §20's outcomes in a comment explaining what it maps onto.
        src = open(os.path.join(ROOT, "scripts", "feed_health.py"), encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
        for forbidden in ("raise RuntimeError", "BLOCK_ENTRY =", "def gate(", "def refuse("):
            self.assertNotIn(forbidden, code, forbidden)


class WiredIntoTheLivePath(unittest.TestCase):
    def test_the_runner_observes_every_live_fetch(self):
        self.assertIn("FH.observe(", RUNNER_SRC)

    def test_an_unhealthy_feed_reaches_the_20_gate_rather_than_a_new_one(self):
        self.assertIn("feed_state=FH.as_quality(obs)", RUNNER_SRC)
        self.assertIn("def _require_quality(sym, tf, series, allow=(\"FRESH\",), now=None, at=None, feed_state=None)",
                      RUNNER_SRC)

    def test_a_replay_is_not_observed(self):
        # A replay re-reads one stored file; poll-to-poll health is meaningless there and would mark every
        # research run stalled.
        self.assertIn("if at is None and out:", RUNNER_SRC)

    def test_an_observation_failure_never_fails_a_tick(self):
        self.assertIn("feed-health observation failed", RUNNER_SRC)

    def test_the_stricter_of_the_two_states_decides(self):
        self.assertIn("if feed_state and feed_state not in allow:", RUNNER_SRC)

    def test_the_real_repository_state_file_parses_if_it_exists(self):
        h = FH.health()
        self.assertIn("feeds", h)
        for key, rec in h["feeds"].items():
            self.assertIn(rec.get("state"), FH.STATES, key)


if __name__ == "__main__":
    unittest.main(verbosity=2)
