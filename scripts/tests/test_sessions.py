"""CLAUDE.md §21 -- sessions as a configurable, reproducible, overlap-aware domain concept.

§21 asks for six properties: Asia / London / New York windows, **overlaps**, **custom sessions**,
timezone-aware, DST-aware, historically reproducible, configurable. Four were already true and the conversion
was genuinely DST-correct. Two were not:

  * **Configurable.** The same windows were written out in six places -- `session-model.md` §2, the if/elif
    chain in `journal.session_of`, `chart.js const SESSIONS`, `chart.js const KZ_WEIGHT`, the `session` enum in
    `trade-file.schema.json`, and `session-model.md` §3 -- with no generator and no drift test. "Configurable"
    is not a property a markdown table has.
  * **Overlaps.** An if/elif chain resolves an overlap by branch order, which is a rule nobody declared. The
    current four windows do not overlap, so this is a guard installed before it is needed rather than after a
    window moves.

The test that matters most is `test_the_new_model_labels_two_years_exactly_as_the_old_one_did`: 70,176
instants across both DST transitions, zero differences. A refactor of a labelling rule that cannot show that
is a re-specification wearing a refactor's clothes.
"""
import datetime
import importlib.util
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import sessions as S
import spec

REGISTRY = os.path.join(ROOT, "docs", "architecture", "sessions.json")


def load_registry():
    with open(REGISTRY, encoding="utf-8") as fh:
        return json.load(fh)


class TheWindowsAreWhatTheyWere(unittest.TestCase):
    """A registry that changed the answer would be a new session model, not a single-sourced old one."""

    def test_the_new_model_labels_two_years_exactly_as_the_old_one_did(self):
        def old(iso):
            import zoneinfo
            t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if t.weekday() >= 5:
                return "off"
            def lh(tz):
                lt = t.astimezone(zoneinfo.ZoneInfo(tz))
                return lt.hour + lt.minute / 60
            ny = lh("America/New_York")
            if 2 <= ny < 5:          # v3 (owner 2026-10-05): the decks' London killzone; v2 was 08-11 Europe/London
                return "london"
            if 8.5 <= ny < 11:
                return "ny_am"
            if 13.5 <= ny < 16:
                return "ny_pm"
            if 20 <= ny < 24:
                return "asia"
            return "off"

        t = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        end = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        diffs, n = [], 0
        while t < end:
            iso = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            n += 1
            if old(iso) != S.primary(iso):
                diffs.append((iso, old(iso), S.primary(iso)))
            t += datetime.timedelta(minutes=15)
        self.assertGreater(n, 70000, "the sweep did not actually cover two years")
        self.assertEqual(diffs[:5], [], f"{len(diffs)} labels changed")

    def test_the_journal_now_delegates_rather_than_carrying_its_own_copy(self):
        src = open(os.path.join(ROOT, "scripts", "journal.py"), encoding="utf-8").read()
        self.assertIn("_sessions.primary(iso)", src)
        for gone in ("Europe/London", "America/New_York"):
            self.assertNotIn(gone, src, f"journal.py still carries a hand-written zone ({gone})")


class ItIsDstAware(unittest.TestCase):
    """§21: 'timezone-aware, DST-aware'. A fixed UTC hour is right in summer only."""

    def test_the_ny_window_moves_with_us_daylight_saving(self):
        # 13:30Z is inside NY AM in January (08:30 EST) and after it in July (09:30 EDT is inside too, but
        # 12:30Z is inside only in summer).
        self.assertEqual(S.primary("2026-01-15T13:30:00Z"), "ny_am")
        self.assertEqual(S.primary("2026-01-15T12:30:00Z"), "off")
        self.assertEqual(S.primary("2026-07-15T12:30:00Z"), "ny_am")

    def test_the_london_killzone_follows_the_new_york_clock(self):
        """v3: 02:00-05:00 America/New_York (the decks' killzone), so it moves with US, not UK, daylight saving."""
        self.assertEqual(S.primary("2026-01-15T07:30:00Z"), "london")   # 02:30 EST
        self.assertEqual(S.primary("2026-01-15T06:30:00Z"), "off")      # 01:30 EST, before the window opens
        self.assertEqual(S.primary("2026-07-15T06:30:00Z"), "london")   # 02:30 EDT
        self.assertEqual(S.primary("2026-07-15T09:30:00Z"), "off")      # 05:30 EDT, after it closes
        # 2026-03-09..03-27: the US is on EDT, the UK still on GMT -- the window follows New York (06:00Z start).
        self.assertEqual(S.primary("2026-03-16T06:30:00Z"), "london")   # 02:30 EDT = 06:30 GMT

    def test_the_spring_forward_day_has_no_gap_and_no_double_count(self):
        """US DST starts 2026-03-08. Walk the whole day a minute at a time: every instant gets exactly one
        primary label and the NY AM window is 150 minutes long, as on any other weekday."""
        day = datetime.datetime(2026, 3, 9, tzinfo=datetime.timezone.utc)   # the Monday after
        minutes = sum(1 for i in range(1440)
                      if S.primary(day + datetime.timedelta(minutes=i)) == "ny_am")
        self.assertEqual(minutes, 150)

    def test_the_fall_back_day_does_not_duplicate_the_window(self):
        """US DST ends 2026-11-01; the Monday after must still see exactly one 150-minute NY AM."""
        day = datetime.datetime(2026, 11, 2, tzinfo=datetime.timezone.utc)
        minutes = sum(1 for i in range(1440)
                      if S.primary(day + datetime.timedelta(minutes=i)) == "ny_am")
        self.assertEqual(minutes, 150)

    def test_a_fixed_offset_would_have_been_wrong(self):
        """The whole reason the reference clock is exchange-local: the same UTC hour is in different windows
        in different seasons."""
        self.assertNotEqual(S.primary("2026-01-15T12:30:00Z"), S.primary("2026-07-15T12:30:00Z"))


class OverlapsAreDeclaredNotAccidental(unittest.TestCase):
    """§21 names overlaps as first-class."""

    def test_active_returns_every_matching_window(self):
        self.assertEqual(S.active("2026-01-15T13:30:00Z"), ("ny_am",))
        self.assertEqual(S.active("2026-01-17T13:30:00Z"), ())   # Saturday

    def test_primary_is_the_first_active_window_in_declared_precedence(self):
        for iso in ("2026-01-15T09:00:00Z", "2026-01-15T14:00:00Z", "2026-01-16T01:30:00Z"):
            a = S.active(iso)
            self.assertEqual(S.primary(iso), a[0] if a else "off")

    def test_precedence_is_unique_so_an_overlap_cannot_be_a_coin_toss(self):
        prec = [w["precedence"] for k, w in load_registry()["sessions"].items() if not k.startswith("_")]
        self.assertEqual(len(prec), len(set(prec)))

    def test_an_overlapping_window_resolves_by_precedence_and_keeps_both(self):
        """Proved on a throwaway registry rather than asserted about the current one, which has no overlap."""
        import tempfile
        data = load_registry()
        data["sessions"]["late_london"] = {"zone": "America/New_York", "display": "LDN2", "start": 4.0,
                                           "end": 6.0, "precedence": 0, "what": "test overlap"}
        for cls, m in data["weights"].items():
            if isinstance(m, dict) and not cls.endswith("_why"):
                m["late_london"] = "none"
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "docs", "architecture"))
            import shutil
            shutil.copy(os.path.join(ROOT, "scripts", "sessions.py"), os.path.join(tmp, "scripts"))
            with open(os.path.join(tmp, "docs", "architecture", "sessions.json"), "w") as fh:
                json.dump(data, fh)
            s = importlib.util.spec_from_file_location("sess_ov", os.path.join(tmp, "scripts", "sessions.py"))
            mod = importlib.util.module_from_spec(s)
            s.loader.exec_module(mod)
            at = "2026-01-15T09:30:00Z"                       # 04:30 New York: inside both windows
            self.assertEqual(set(mod.active(at)), {"london", "late_london"}, "an overlap was swallowed")
            self.assertEqual(mod.primary(at), "late_london", "precedence 0 did not win")


class TheRegistryRefusesNonsense(unittest.TestCase):
    """Mutation tests. A model that loads but is wrong mislabels trades and raises nowhere."""

    def _load_with(self, mutate):
        import shutil
        import tempfile
        data = load_registry()
        mutate(data)
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "scripts"))
            os.makedirs(os.path.join(tmp, "docs", "architecture"))
            shutil.copy(os.path.join(ROOT, "scripts", "sessions.py"), os.path.join(tmp, "scripts"))
            with open(os.path.join(tmp, "docs", "architecture", "sessions.json"), "w") as fh:
                json.dump(data, fh)
            s = importlib.util.spec_from_file_location("sess_bad", os.path.join(tmp, "scripts", "sessions.py"))
            s.loader.exec_module(importlib.util.module_from_spec(s))

    def test_a_nonexistent_timezone_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self._load_with(lambda d: d["sessions"]["london"].update(zone="Europe/Atlantis"))
        self.assertIn("IANA", str(cm.exception))

    def test_a_legacy_abbreviation_zone_is_refused(self):
        """`ZoneInfo('EST')` LOADS -- tzdata ships the abbreviation aliases -- and means a permanent -05:00
        with no daylight saving. That is the exact trap session-model.md §1 exists to avoid: the ICT decks
        label their windows 'EST' year-round. Found by this test failing to raise."""
        with self.assertRaises(ValueError) as cm:
            self._load_with(lambda d: d["sessions"]["ny_am"].update(zone="EST"))
        self.assertIn("FIXED offsets", str(cm.exception))

    def test_a_real_no_dst_region_city_zone_is_still_allowed(self):
        """The rule must not reject a legitimate custom session: Asia/Tokyo has no DST either."""
        self._load_with(lambda d: d["sessions"]["asia"].update(zone="Asia/Tokyo"))

    def test_a_zero_width_window_is_refused(self):
        with self.assertRaises(ValueError):
            self._load_with(lambda d: d["sessions"]["london"].update(start=8.0, end=8.0))

    def test_a_duplicate_precedence_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self._load_with(lambda d: d["sessions"]["ny_am"].update(precedence=1))
        self.assertIn("precedence", str(cm.exception))

    def test_an_hour_outside_the_day_is_refused(self):
        with self.assertRaises(ValueError):
            self._load_with(lambda d: d["sessions"]["asia"].update(end=25.0))

    def test_a_weight_map_that_forgets_a_window_is_refused(self):
        with self.assertRaises(ValueError) as cm:
            self._load_with(lambda d: d["weights"]["metals"].pop("ny_pm"))
        self.assertIn("says nothing about", str(cm.exception))

    def test_a_weight_for_a_window_that_does_not_exist_is_refused(self):
        with self.assertRaises(ValueError):
            self._load_with(lambda d: d["weights"]["metals"].update(tokyo="full"))


class TheDerivedCopiesCannotDrift(unittest.TestCase):
    def test_the_sync_script_reports_no_drift(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "sync-sessions.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_the_trade_schema_enum_is_the_registrys(self):
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            field = json.load(fh)["properties"]["session"]
        self.assertEqual(field["enum"], list(S.ORDER) + [S.OFF])

    def test_the_schema_no_longer_claims_the_label_is_derived_in_utc(self):
        """It never was, after the 2026-09-10 decision to use exchange-local clocks. The description said so
        for eight days."""
        with open(os.path.join(ROOT, "docs", "architecture", "schemas", "trade-file.schema.json"),
                  encoding="utf-8") as fh:
            desc = json.load(fh)["properties"]["session"]["description"]
        self.assertIn("EXCHANGE-LOCAL", desc)
        self.assertIn("DST-aware", desc)

    def test_the_chart_has_no_hand_kept_window_table(self):
        src = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        for line, want in (("const SESSIONS = ", 0), ("const KZ_WEIGHT = ", 1)):
            self.assertEqual(src.count(line), 1, f"{line} appears more than once")
        self.assertIn("const SESSIONS = " + json_like(S.js_sessions()), src)

    def test_the_page_and_the_scorer_agree_about_an_unknown_asset_class(self):
        """chart.js used to fall back to crypto's weights, which would shade an unconsidered instrument as if
        it had earned reduced credit the scorer never awards."""
        src = open(os.path.join(ROOT, "scripts", "chart.js"), encoding="utf-8").read()
        self.assertIn("KZ_WEIGHT.default", src)
        self.assertNotIn("||KZ_WEIGHT.crypto", src)
        self.assertEqual(S.weight_class("something_new", "london"), "none")


def json_like(windows):
    return "[" + ",".join("{key:'%s',name:'%s',tz:'%s',a:%s,b:%s}"
                          % (w["key"], w["name"], w["tz"], f"{w['a']:g}", f"{w['b']:g}")
                          for w in windows) + "];"


class WeightsAndPointsStaySeparate(unittest.TestCase):
    def test_the_registry_holds_classes_and_not_points(self):
        blob = open(REGISTRY, encoding="utf-8").read()
        self.assertNotIn('"full": 7', blob)
        self.assertIn("timing.weight_by_class", blob, "the registry should say where the points live")

    def test_the_points_are_still_where_they_were(self):
        with open(os.path.join(ROOT, "docs", "architecture", "analysis-params.json"), encoding="utf-8") as fh:
            w = json.load(fh)["timing"]["weight_by_class"]
        self.assertEqual(w, {"full": 7, "reduced": 3, "none": 0})

    def test_this_module_awards_no_points(self):
        src = open(os.path.join(ROOT, "scripts", "sessions.py"), encoding="utf-8").read()
        self.assertNotIn("weight_by_class", src.split('"""', 2)[-1],
                         "sessions.py should return a class and stop, not reach for the points")


class TheWeekendGate(unittest.TestCase):
    def test_no_session_on_a_saturday_even_for_crypto(self):
        self.assertEqual(S.primary("2026-01-17T14:00:00Z"), "off")
        self.assertTrue(S.gated("2026-01-17T14:00:00Z"))

    def test_the_gate_is_configuration_not_a_hardcoded_weekday(self):
        self.assertEqual(load_registry()["gates"]["weekend"]["days"], [5, 6])


class ItIsReproducible(unittest.TestCase):
    """§21: 'historically reproducible'. The conversion always was; what was missing was a way to say WHICH
    model produced a label."""

    def test_the_model_carries_a_version(self):
        self.assertIsInstance(S.VERSION, int)
        self.assertEqual(S.VERSION, load_registry()["version"])

    def test_the_stated_conversion_names_the_date_and_the_model(self):
        line = S.describe("2026-01-15T13:45:00Z", "metals")
        self.assertIn("ny_am", line)
        self.assertIn("13:30-16:00Z", line)
        self.assertIn("weight full", line)
        self.assertIn(f"v{S.VERSION}", line)
        self.assertIn("Project assumption", line)

    def test_the_same_line_in_summer_states_a_different_utc_span(self):
        self.assertIn("12:30-15:00Z", S.describe("2026-07-15T12:45:00Z", "metals"))


@unittest.skipUnless(spec.available(), "CLAUDE.md is not present in this checkout")
class TheSpecsOwnWords(unittest.TestCase):
    def test_section_21_asks_for_all_of_this(self):
        body = spec.body(21)
        for word in ("Asia", "London", "New York", "overlaps", "custom sessions",
                     "timezone-aware", "DST-aware", "historically reproducible", "configurable"):
            self.assertIn(word, body)

    def test_section_21_forbids_the_hardcoding_that_was_there(self):
        self.assertIn("Do not hardcode assumptions that break during timezone or DST transitions",
                      spec.body(21))


if __name__ == "__main__":
    unittest.main()
