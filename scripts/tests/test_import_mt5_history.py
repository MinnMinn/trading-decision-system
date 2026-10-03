"""scripts/import-mt5-history.py -- broker CFD history, server time -> UTC (CLAUDE.md §23.1, §7, §20).

The thing being defended here is one hour. `ExportOHLCV.mq5` converts with `TimeCurrent() - TimeGMT()`, the
offset *now*, which is right for a 600-bar live window and wrong for years of history: an EET broker is UTC+2
in winter and UTC+3 in summer. An import that applies one offset to everything produces a file that looks
perfect, passes every shape check, and is an hour wrong for half the year -- which is worse than the Yahoo
futures proxy it replaces, because that one is labelled and this one would not be.

So most of these tests are about REFUSALS. A converter that cannot say "I don't know which zone this is" will
eventually convert something with the wrong one.
"""
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import providers as P  # noqa: E402


def _load():
    spec = importlib.util.spec_from_file_location(
        "imp_mt5", os.path.join(ROOT, "scripts", "import-mt5-history.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


M = _load()


def export(candles, symbol="XAUUSD", timeframe="1H", **over):
    doc = {"symbol": symbol, "timeframe": timeframe, "_source": "mt5_bridge_history",
           "_server": P.provider("mt5_bridge").get("server"), "_server_utc_offset_sec_now": 10800,
           "_exported_at_utc": "2026-09-18T03:47:17Z", "_bars": len(candles), "candles": candles}
    doc.update(over)
    return doc


def bar(t, o=100.0, h=101.0, lo=99.0, c=100.5, v=1.0):
    return {"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}


class ZoneIsAReadFact(unittest.TestCase):
    def test_the_zone_comes_from_the_provider_registry(self):
        name, zone = M._zone()
        self.assertEqual(name, P.provider("mt5_bridge")["server_timezone"])
        self.assertIn("/", name)

    def test_there_is_no_timezone_flag_to_guess_with(self):
        """A `--timezone` option with a default IS a guess wearing a flag. The zone has one source, so the
        argument parser must not offer a second one."""
        src = open(os.path.join(ROOT, "scripts", "import-mt5-history.py"), encoding="utf-8").read()
        for flag in ("--timezone", "--tz", "--zone", "--offset"):
            self.assertNotIn(f'add_argument("{flag}"', src, f"{flag} would let a caller override the registry")

    def test_a_missing_zone_refuses(self):
        real = P.PROVIDERS["mt5_bridge"].pop("server_timezone")
        try:
            with self.assertRaises(M.Refused) as cm:
                M._zone()
            self.assertIn("server_timezone", str(cm.exception))
        finally:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = real

    def test_an_abbreviation_refuses_because_it_has_no_daylight_saving(self):
        """`ZoneInfo('EET')` LOADS, and means a permanent +02:00. Taking it would be an hour wrong all summer."""
        real = P.PROVIDERS["mt5_bridge"]["server_timezone"]
        try:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = "EET"
            with self.assertRaises(M.Refused) as cm:
                M._zone()
            self.assertIn("Region/City", str(cm.exception))
        finally:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = real


class TheHour(unittest.TestCase):
    """The conversion itself, at the two offsets and across the transition between them."""

    def setUp(self):
        self.name, self.zone = M._zone()

    def _utc(self, stamp):
        return M._to_utc(stamp, self.zone, self.name, "test").isoformat().replace("+00:00", "Z")

    def test_winter_is_plus_two(self):
        self.assertEqual(self._utc("2026-01-15T12:00:00"), "2026-01-15T10:00:00Z")

    def test_summer_is_plus_three(self):
        self.assertEqual(self._utc("2026-07-15T12:00:00"), "2026-07-15T09:00:00Z")

    def test_the_same_local_hour_is_a_different_utc_hour_either_side_of_the_transition(self):
        """This is the whole point. A single fixed offset makes these two equal, and they are not."""
        before = self._utc("2026-03-28T12:00:00")
        after = self._utc("2026-03-30T12:00:00")
        self.assertEqual(before, "2026-03-28T10:00:00Z")
        self.assertEqual(after, "2026-03-30T09:00:00Z")
        self.assertNotEqual(before[11:], after[11:])

    def test_a_september_bar_uses_summer_time_not_the_exports_current_offset(self):
        """The export records `_server_utc_offset_sec_now`; this converter must never reach for it."""
        src = open(os.path.join(ROOT, "scripts", "import-mt5-history.py"), encoding="utf-8").read()
        self.assertNotIn("_server_utc_offset_sec_now\"]", src, "the current offset must not drive conversion")
        self.assertEqual(self._utc("2026-09-18T09:00:00"), "2026-09-18T06:00:00Z")

    def test_a_nonexistent_local_time_refuses(self):
        with self.assertRaises(M.Refused) as cm:
            self._utc("2026-03-29T03:30:00")
        self.assertIn("does not exist", str(cm.exception))

    def test_an_ambiguous_local_time_refuses_rather_than_picking_a_branch(self):
        with self.assertRaises(M.Refused) as cm:
            self._utc("2026-10-25T03:30:00")
        self.assertIn("twice", str(cm.exception))

    def test_a_timestamp_that_already_claims_utc_refuses(self):
        for stamp in ("2026-01-15T12:00:00Z", "2026-01-15T12:00:00+02:00"):
            with self.subTest(stamp=stamp), self.assertRaises(M.Refused) as cm:
                self._utc(stamp)
            self.assertIn("already claims", str(cm.exception))


class Provenance(unittest.TestCase):
    def setUp(self):
        self.name, self.zone = M._zone()

    def test_a_file_from_another_server_refuses(self):
        raw = export([bar("2026-01-15T12:00:00")], _server="SomeOtherBroker-Live")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh); path = fh.name
        try:
            with self.assertRaises(M.Refused) as cm:
                M.read_export(path)
            self.assertIn("SomeOtherBroker-Live", str(cm.exception))
        finally:
            os.unlink(path)

    def test_a_file_from_the_LIVE_exporter_refuses(self):
        """`mt5_bridge_live` bars were already converted with the current offset. Converting them again
        would apply the zone twice; they are a different artifact and are not importable here."""
        raw = export([bar("2026-01-15T12:00:00Z")], _source="mt5_bridge_live")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh); path = fh.name
        try:
            with self.assertRaises(M.Refused) as cm:
                M.read_export(path)
            self.assertIn("mt5_bridge_history", str(cm.exception))
        finally:
            os.unlink(path)

    def test_a_symbol_off_the_allowlist_refuses(self):
        raw = export([bar("2026-01-15T12:00:00")], symbol="TSLA")
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh); path = fh.name
        try:
            with self.assertRaises(M.Refused):
                M.read_export(path)
        finally:
            os.unlink(path)

    def test_the_written_series_carries_a_marker_a_provider_declares(self):
        """An unresolvable marker means a dataset snapshot of this data reports `provider: None` -- which is
        exactly how the Yahoo futures history went unnoticed (test_snapshot.SourceMarkers)."""
        raw = export([bar("2026-01-15T12:00:00")])
        doc = M.series(raw, "XAUUSD", "1H", M.convert(raw, "XAUUSD", "1H", self.name, self.zone), self.name)
        self.assertEqual(P.by_source_marker(doc["_source"]), "mt5_bridge")

    def test_the_written_series_names_the_zone_and_where_it_came_from(self):
        raw = export([bar("2026-01-15T12:00:00")])
        doc = M.series(raw, "XAUUSD", "1H", M.convert(raw, "XAUUSD", "1H", self.name, self.zone), self.name)
        self.assertEqual(doc["_server_timezone"], self.name)
        self.assertIn("providers.json", doc["_server_timezone_source"])
        self.assertIn("tick_volume", doc["_volume_caveat"])

    def test_the_output_shape_matches_every_other_history_file(self):
        raw = export([bar("2026-01-15T12:00:00")])
        doc = M.series(raw, "XAUUSD", "1H", M.convert(raw, "XAUUSD", "1H", self.name, self.zone), self.name)
        for key in ("symbol", "timeframe", "last_updated", "_source", "candles"):
            self.assertIn(key, doc)
        self.assertEqual(set(doc["candles"][0]), {"time", "open", "high", "low", "close", "volume"})
        self.assertTrue(doc["candles"][0]["time"].endswith("Z"))


class BrokenInputRefuses(unittest.TestCase):
    def setUp(self):
        self.name, self.zone = M._zone()

    def _convert(self, candles):
        raw = export(candles)
        return M.convert(raw, "XAUUSD", "1H", self.name, self.zone)

    def test_out_of_order_bars_refuse(self):
        with self.assertRaises(M.Refused) as cm:
            self._convert([bar("2026-01-15T12:00:00"), bar("2026-01-15T11:00:00")])
        self.assertIn("not after", str(cm.exception))

    def test_a_duplicate_timestamp_refuses(self):
        with self.assertRaises(M.Refused):
            self._convert([bar("2026-01-15T12:00:00"), bar("2026-01-15T12:00:00")])

    def test_an_impossible_ohlc_bar_refuses(self):
        with self.assertRaises(M.Refused) as cm:
            self._convert([bar("2026-01-15T12:00:00", o=100, h=99, lo=101, c=100)])
        self.assertIn("valid OHLC", str(cm.exception))

    def test_a_null_price_refuses(self):
        with self.assertRaises(M.Refused):
            self._convert([bar("2026-01-15T12:00:00", c=None)])

    def test_an_empty_export_refuses(self):
        with self.assertRaises(M.Refused):
            self._convert([])


class RealExportsOnDisk(unittest.TestCase):
    """Whatever is actually in data/live/mt5-bridge/ must convert, or the importer is not usable."""

    def test_every_export_present_converts_and_passes_section_20(self):
        rows = [r for r in M.plan() if not r.get("error")]
        if not rows:
            self.skipTest("no history.*.json exports on disk")
        name, zone = M._zone()
        for row in rows:
            with self.subTest(file=os.path.basename(row["path"])):
                candles = M.convert(row["raw"], row["symbol"], row["timeframe"], name, zone)
                doc = M.series(row["raw"], row["symbol"], row["timeframe"], candles, name)
                state, why = M.assess(row["symbol"], row["timeframe"], doc)
                self.assertIn(state, ("FRESH", "STALE"), f"{row['symbol']} {row['timeframe']}: {state} -- {why}")

    def test_a_converted_series_starts_and_ends_in_utc(self):
        rows = [r for r in M.plan() if not r.get("error")]
        if not rows:
            self.skipTest("no history.*.json exports on disk")
        name, zone = M._zone()
        candles = M.convert(rows[0]["raw"], rows[0]["symbol"], rows[0]["timeframe"], name, zone)
        for c in (candles[0], candles[-1]):
            t = datetime.datetime.fromisoformat(c["time"].replace("Z", "+00:00"))
            self.assertEqual(t.tzinfo, datetime.timezone.utc)


class ShrinkGuard(unittest.TestCase):
    """A truncated export must never silently delete stored history (2026-10-03: a 1m export covering 2012-2017 replaced
    the stored 2012-2026 series)."""

    def test_shrinks(self):
        prior = ("2012-01-02T00:00:00Z", "2026-09-28T17:00:00Z")
        self.assertIsNone(M.shrinks(None, "2020-01-01T00:00:00Z", "2020-02-01T00:00:00Z"))
        self.assertIsNone(M.shrinks(prior, "2012-01-02T00:00:00Z", "2026-10-02T20:45:00Z"))     # append-only: fine
        self.assertIn("EARLIER", M.shrinks(prior, "2012-01-02T00:00:00Z", "2017-03-01T00:00:00Z"))
        self.assertIn("LATER", M.shrinks(prior, "2018-01-02T00:00:00Z", "2026-10-02T20:45:00Z"))

    def test_existing_span_reads_split_and_file(self):
        import gzip
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "ohlcv.XAUUSD.5m"))
        json.dump({"_format": "split-gz-year-v1", "years": [2020], "first": "2020-01-01T00:00:00Z",
                   "last": "2020-12-31T23:55:00Z"}, open(os.path.join(d, "ohlcv.XAUUSD.5m", "index.json"), "w"))
        with gzip.open(os.path.join(d, "ohlcv.XAUUSD.5m", "2020.json.gz"), "wt") as fh:
            json.dump({"year": 2020, "candles": []}, fh)
        self.assertEqual(M.existing_span(d, "XAUUSD", "5m"), ("2020-01-01T00:00:00Z", "2020-12-31T23:55:00Z"))
        json.dump({"candles": [{"time": "2021-01-01T00:00:00Z"}, {"time": "2021-02-01T00:00:00Z"}]},
                  open(os.path.join(d, "ohlcv.XAUUSD.1H.json"), "w"))
        self.assertEqual(M.existing_span(d, "XAUUSD", "1H"), ("2021-01-01T00:00:00Z", "2021-02-01T00:00:00Z"))
        self.assertIsNone(M.existing_span(d, "XAUUSD", "4H"))


if __name__ == "__main__":
    unittest.main()
