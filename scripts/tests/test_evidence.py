"""CLAUDE.md §12 -- Evidence as a record type, and evidence is not a signal.

The scanner already computes everything §12 calls evidence: `last_mss`, `nearest_fvg`, `unswept_pools`,
`events_recent`, `eq` in `data/live/prelim/<style>.facts.json`. They are flat fields on a symbol -- a number
or a string -- with no source, event time, availability, quality or methodology scope of their own. The file
header says when the scan RAN; an observation cannot say what it came from or whether it was knowable at a
given decision time.

The consequence, which is why this is not bookkeeping: **nothing could answer "what evidence did this decision
use?"** A trade file records a score and a setup name; the facts file is overwritten by the next scan. A
post-trade review (§41) cannot reconstruct the inputs, and §8's gate had nothing per-observation to gate.

Two things here earned their tests the hard way, and both are recorded as properties:

  * **The adapter's field names were guesses at first** and emitted `latest MSS ? past 76862.85`. The shapes
    (`last_mss.type`, `nearest_fvg.type`, `unswept_pools[].kind`/`.level`) are read from a real facts file.
    `pct` is also a FRACTION, not a percentage -- the first version printed "0.2678%" for 26.8%.
  * **The first version anchored evidence on `last_time`, which is the FORMING candle**, and the §8 gate then
    refused every record it produced. That was the gate being right. ict-scan.py:232 states verdicts use the
    last completed candle `c[-2]`; evidence now anchors there too.
"""
import datetime
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import evidence as E
import normalized as N
import pit
import spec

UTC = datetime.timezone.utc
FACTS = os.path.join(ROOT, "data", "live", "prelim", "scalping.facts.json")


def facts():
    with open(FACTS, encoding="utf-8") as fh:
        return json.load(fh)


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class DrivenByTheSpec(unittest.TestCase):
    def test_the_evidence_kinds_match_the_spec_examples(self):
        listed = spec.bullet_list(spec.body(12))
        kinds = [k.replace("/", "_").replace(" ", "_") for k in listed[:10]]
        self.assertEqual(set(kinds), set(E.EVIDENCE_KINDS),
                         f"§12's example list and EVIDENCE_KINDS differ: {set(kinds) ^ set(E.EVIDENCE_KINDS)}")

    def test_the_required_fields_match_the_spec(self):
        body = spec.body(12)
        required = spec.bullet_list(spec.after(body, "Evidence must preserve:"))[:6]
        # §12 writes them in mixed style -- `eventTime`, `availableTime`, `methodology scope` -- so normalise
        # camelCase and spaces the same way the module's snake_case field names do.
        want = {f.replace("Time", "_time").replace(" ", "_").lower() for f in required}
        self.assertEqual(want, set(E.REQUIRED_FIELDS),
                         f"§12's required-field list and REQUIRED_FIELDS differ: {want ^ set(E.REQUIRED_FIELDS)}")

    def test_the_six_level_ladder_matches_the_spec(self):
        listed = spec.bullet_list(spec.after(spec.body(12), "The system must distinguish:"))
        self.assertEqual([l.replace(" ", "_") for l in listed], [name for name, _ in E.LADDER])

    def test_every_ladder_level_names_the_artifact_that_holds_it(self):
        """The distinction is §12's requirement; naming the holder is what makes it inspectable."""
        for name, holder in E.LADDER:
            self.assertTrue(len(holder) > 30, f"ladder level {name} has no real holder description")


class EvidenceIsNotASignal(unittest.TestCase):
    """§12 states this twice. The failure it guards is the easy one: a record that also carries a direction
    has become a decision, and every consumer downstream will read it as one."""

    def test_a_direction_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            E.observation("market_structure", "ict", "MSS up", available_time="2026-09-17T18:00:00Z",
                          direction="long")
        self.assertIn("not automatically a signal", str(cm.exception))

    def test_every_forbidden_field_is_refused(self):
        for field in E.FORBIDDEN_FIELDS:
            with self.assertRaises(ValueError, msg=f"{field} was accepted onto an evidence record"):
                E.observation("liquidity", "ict", "pool", available_time="2026-09-17T18:00:00Z",
                              **{field: "x"})

    def test_the_refusal_points_at_the_right_ladder_rung(self):
        with self.assertRaises(ValueError) as cm:
            E.observation("volume", "wyckoff", "high", available_time="2026-09-17T18:00:00Z", verdict="TRADE")
        self.assertIn("model.html", str(cm.exception), "the refusal should name where interpretation lives")

    def test_a_plain_observation_is_accepted(self):
        rec = E.observation("volume", "wyckoff", "volume 2.1x the 20-bar mean",
                            available_time="2026-09-17T18:00:00Z")
        self.assertEqual(rec["ladder_level"], "evidence")
        self.assertNotIn("direction", rec)


class RequiredFieldsAreReal(unittest.TestCase):
    def test_an_observation_with_no_availability_refuses(self):
        """Defaulting to 'now' would make every record trivially admissible, which is worse than refusing."""
        with self.assertRaises(ValueError) as cm:
            E.observation("liquidity", "ict", "a pool")
        self.assertIn("available_time", str(cm.exception))

    def test_an_unknown_kind_refuses(self):
        with self.assertRaises(ValueError):
            E.observation("astrology", "ict", "mercury", available_time="2026-09-17T18:00:00Z")

    def test_provenance_and_quality_derive_from_the_series_not_from_the_caller(self):
        try:
            rec = E.observation("market_structure", "ict", "MSS up", series=("BTCUSDT", "15m"),
                                event_time="2026-09-17T18:00:00Z")
        except FileNotFoundError:
            self.skipTest("no live BTCUSDT 15m series on disk")
        direct = N.load("BTCUSDT", "15m")["provenance"]
        self.assertEqual(rec["quality"], direct["quality"])
        self.assertEqual(rec["provenance"]["provider"], direct["provider"])
        self.assertEqual(rec["source"], direct["source_identifier"])

    def test_available_time_is_one_period_after_the_event(self):
        """§7's rule, reused rather than restated: an observation off a bar is knowable when that bar closes."""
        try:
            rec = E.observation("volume", "wyckoff", "spike", series=("BTCUSDT", "15m"),
                                event_time="2026-09-17T18:00:00Z")
        except FileNotFoundError:
            self.skipTest("no live series on disk")
        self.assertEqual(rec["event_time"], "2026-09-17T18:00:00Z")
        self.assertEqual(rec["available_time"], "2026-09-17T18:15:00Z")


class GatedByTheSameGateAsCandles(unittest.TestCase):
    def test_future_evidence_is_refused(self):
        rec = E.observation("news_event_state", "none", "CPI release",
                            available_time="2026-09-17T19:00:00Z")
        r = E.admissible([rec], decision_time=datetime.datetime(2026, 9, 17, 18, tzinfo=UTC))
        self.assertFalse(r["ok"])
        self.assertIn("look-ahead", r["refused"][0]["reason"])

    def test_past_evidence_is_admitted(self):
        rec = E.observation("liquidity", "ict", "swept BSL",
                            available_time="2026-09-17T17:00:00Z")
        r = E.admissible([rec], decision_time=datetime.datetime(2026, 9, 17, 18, tzinfo=UTC))
        self.assertTrue(r["ok"])

    def test_evidence_maps_onto_the_declared_pit_kinds(self):
        for kind in E.EVIDENCE_KINDS:
            rec = E.observation(kind, "x", "y", available_time="2026-09-17T17:00:00Z")
            mapped = E.as_pit_inputs([rec])[0]["kind"]
            self.assertIn(mapped, pit.INPUT_KINDS, f"{kind} maps to an undeclared PIT kind {mapped}")


class AdapterOverRealScannerOutput(unittest.TestCase):
    """The type is exercised on the scanner's actual output, so it is a reader rather than decoration."""

    def setUp(self):
        if not os.path.exists(FACTS):
            self.skipTest("no scanner facts on disk")
        self.recs = E.from_facts(facts(), "BTCUSDT", "15m")

    def test_it_produces_records_from_real_facts(self):
        self.assertGreater(len(self.recs), 0)
        for r in self.recs:
            for field in E.REQUIRED_FIELDS:
                self.assertIn(field, r)

    def test_no_statement_contains_an_unresolved_placeholder(self):
        """The first version guessed field names and emitted 'latest MSS ? past 76862.85'. A '?' where a value
        belongs is the visible symptom of a schema assumed rather than read."""
        for r in self.recs:
            self.assertNotIn("?", r["statement"],
                             f"unresolved field in {r['kind']}: {r['statement']!r} -- a guessed key name")

    def test_records_are_anchored_on_the_completed_candle_not_the_forming_one(self):
        """`last_time` in the facts is the FORMING bar, reported separately on purpose (ict-scan.py:232 --
        verdicts use `c[-2]`). Anchoring there made the §8 gate refuse every record, correctly."""
        forming = facts()["symbols"]["BTCUSDT"]["last_time"]
        for r in self.recs:
            self.assertLess(r["event_time"], forming,
                            "evidence is anchored on the forming candle; it must use the completed one")

    def test_every_record_is_admissible_at_the_scan_time(self):
        """The end-to-end property: evidence the scanner could legitimately have produced passes the gate at
        the moment the scan ran."""
        scanned = facts()["scanned_at"]
        r = E.admissible(self.recs, decision_time=scanned)
        self.assertTrue(r["ok"], f"refused: {[x['reason'] for x in r['refused']]}")

    def test_the_percentage_is_not_reported_as_a_fraction(self):
        """`pct` is 0.2678 in the facts file; the first version printed '0.2678%' for 26.8%."""
        vol = [r for r in self.recs if r["kind"] == "volatility"]
        if not vol:
            self.skipTest("no volatility record in this facts file")
        self.assertNotIn("0.2", vol[0]["statement"].split("%")[0][-4:],
                         f"percentage looks like a raw fraction: {vol[0]['statement']!r}")


if __name__ == "__main__":
    unittest.main()


class EveryEventShapeIsHandled(unittest.TestCase):
    """The scanner emits four event shapes and the adapter read one of them.

    `scripts/ict-scan.py` emits a LEVEL event (`sweep`, `erl_*`, `mss_*`), a ZONE event (`fvg_*`, which carries
    lo/hi and no `level` at all), a MULTIPLE event (`volume`), and whatever a later rule adds. The adapter read
    `ev.get("level", "?")` for all of them and called every one "swept" — so an FVG came out as
    `recent: swept fvg_bull ?`: a placeholder where a number belongs, and a verb wrong twice over.

    It sat unnoticed because the live scan had no FVG in its recent window for days. It surfaced the moment one
    did, which is why these cases are now constructed rather than waited for.
    """

    @staticmethod
    def _facts(events):
        return {"scanned_at": "2026-09-18T01:00:00Z",
                "symbols": {"BTCUSDT": {"tf": "15m", "last_time": "2026-09-18T01:00:00Z",
                                        "events_recent": events}}}

    def _statements(self, events):
        import evidence as E
        return [r["statement"] for r in E.from_facts(self._facts(events), "BTCUSDT", "15m")]

    def test_a_zone_event_reports_its_range_not_a_placeholder(self):
        s = self._statements([{"kind": "fvg_bull", "lo": 1.0, "hi": 2.0, "time": "2026-09-18T00:45:00Z"}])
        self.assertTrue(any("1.0-2.0" in x for x in s), s)
        self.assertFalse(any("?" in x for x in s), s)

    def test_a_zone_event_is_not_called_swept(self):
        s = self._statements([{"kind": "fvg_bull", "lo": 1.0, "hi": 2.0, "time": "2026-09-18T00:45:00Z"}])
        self.assertFalse(any("swept" in x for x in s), s)
        self.assertTrue(any("formed" in x for x in s), s)

    def test_a_volume_event_reports_its_multiple(self):
        s = self._statements([{"kind": "volume", "mult": 2.4, "dir": "up", "time": "2026-09-18T00:45:00Z"}])
        self.assertTrue(any("2.4x average" in x for x in s), s)

    def test_only_a_sweep_is_called_swept(self):
        s = self._statements([{"kind": "sweep", "pool": "BSL", "level": 10.0, "time": "2026-09-18T00:45:00Z"},
                              {"kind": "mss_bull", "level": 11.0, "time": "2026-09-18T00:45:00Z"}])
        self.assertTrue(any("swept at 10.0" in x for x in s), s)
        self.assertTrue(any("mss_bull printed at 11.0" in x for x in s), s)

    def test_an_unrecognised_shape_is_skipped_rather_than_guessed(self):
        """A record that says nothing is honest; one that says `?` is a fabricated observation §12 would carry
        into a decision."""
        s = self._statements([{"kind": "something_new", "whatever": 3, "time": "2026-09-18T00:45:00Z"}])
        self.assertEqual([x for x in s if "something_new" in x], [])
        self.assertFalse(any("?" in x for x in s), s)
