"""FTMO-Demo history import (owner decision 2026-09-28/29, docs/audits/2026-09-29-ftmo-server-timezone.md):
a SECOND MT5 provider/server whose zone is a named CONVENTION (US DST dates, EET-sized offset) rather than a
real IANA zone, a SECOND history root (data/history/ftmo) the engine can read without changing its default
behaviour, and a symbol-map translation the default (mt5_bridge) provider never needed.

What this file defends, one test class per claim:
  * the split-gz-year format `backtest-methods.load()` reads is IDENTICAL to what the single-file/in-memory
    path would have produced for the same input -- ImportMT5History's own `convert()` is the reference.
  * the default history root's behaviour is untouched -- a real on-disk MetaQuotes-Demo file reads the same
    with this code as it would have before HISTORY_ROOT existed.
  * a symbol map translates the export's own symbol into the canonical one BEFORE the allowlist check.
  * the FTMO zone convention refuses exactly like the original IANA-only path always has, on the same two
    questions (no declaration at all; an unimplemented/incomplete declaration) -- a convention is not a
    second way to guess.
  * `UsDatesFixedOffsetZone` transitions on the US calendar (not the EU one already proven for mt5_bridge),
    and both DST edge cases (gap, ambiguous) are caught the same way the EU-zone path already is.
"""
import datetime
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import providers as P    # noqa: E402
import scan_cache as SC  # noqa: E402


def _load(name, relpath, env=None):
    """importlib load of a dashed-filename module, optionally with an env var set for the duration of the
    exec (backtest-methods.HISTORY_ROOT is read once, at import time)."""
    old = {}
    try:
        if env:
            for k, v in env.items():
                old[k] = os.environ.get(k)
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
        spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", relpath))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def IM():
    return _load("imp_mt5_ftmo", "import-mt5-history.py")


import mt5_time as MT  # noqa: E402


RAW_EXPORT_HEADER = """{{
  "symbol": "{sym}",
  "timeframe": "{tf}",
  "_source": "mt5_bridge_history",
  "_time_basis": "BROKER SERVER TIME, NOT UTC",
  "_server": "{server}",
  "_server_utc_offset_sec_now": 10800,
  "_exported_at_utc": "2026-09-18T03:47:17Z",
  "_bars": {n},
  "_volume_caveat": "tick_volume, not real traded volume",
  "candles": [
"""


def write_raw_export(path, candles, sym="XAUUSD", tf="1H", server="MetaQuotes-Demo"):
    """A file in ExportHistory.mq5's exact on-disk shape -- what `_stream_candles()`/`_header_only()` parse,
    and what `read_export()` parses via plain `json.load()`. Both paths must see the same file."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(RAW_EXPORT_HEADER.format(sym=sym, tf=tf, server=server, n=len(candles)))
        for i, c in enumerate(candles):
            row = json.dumps(c)
            fh.write(f"    {row}" + (",\n" if i < len(candles) - 1 else "\n"))
        fh.write("  ]\n}\n")


def bar(t, o=100.0, h=101.0, lo=99.0, c=100.5, v=1.0):
    return {"time": t, "open": o, "high": h, "low": lo, "close": c, "volume": v}


class SplitRoundTrip(unittest.TestCase):
    """The gz-year-split reader must reproduce EXACTLY what the in-memory path produces for the same input."""

    def setUp(self):
        self.M = IM()
        self.tmp = tempfile.mkdtemp(prefix="ftmo-hist-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _candles_crossing_a_utc_year(self):
        # Europe/Helsinki (mt5_bridge, the default provider) is +02:00 in December: these server-local hours
        # convert to 2019-12-31T21:00Z .. 2020-01-01T01:00Z -- one bar in each of two UTC calendar years.
        times = ["2019-12-31T23:00:00", "2020-01-01T00:00:00", "2020-01-01T01:00:00",
                 "2020-01-01T02:00:00", "2020-01-01T03:00:00"]
        return [bar(t, o=100 + i, h=101 + i, lo=99 + i, c=100.5 + i, v=float(i)) for i, t in enumerate(times)]

    def test_split_reader_matches_in_memory_convert(self):
        M = self.M
        name, zone = MT.server_zone()  # default provider, unchanged
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = self._candles_crossing_a_utc_year()
        write_raw_export(raw_path, candles)

        raw, sym, tf = M.read_export(raw_path)
        expected = M.convert(raw, sym, tf, name, zone)

        dest_root = os.path.join(self.tmp, "out")
        first, last, n, years, last_row = M.stream_write_split(raw_path, sym, tf, name, zone, dest_root,
                                                       "mt5_bridge", header=raw)
        self.assertEqual(sorted(years), [2019, 2020])
        self.assertEqual(n, len(expected))

        split_dir = os.path.join(dest_root, f"ohlcv.{sym}.{tf}")
        self.assertTrue(os.path.isdir(split_dir))
        self.assertTrue(os.path.exists(os.path.join(split_dir, "index.json")))
        self.assertTrue(os.path.exists(os.path.join(split_dir, "2019.json.gz")))
        self.assertTrue(os.path.exists(os.path.join(split_dir, "2020.json.gz")))

        bt = _load("bt_ftmo_split", "backtest-methods.py", env={"BT_HISTORY_ROOT": dest_root})
        got, source = bt.load(sym, tf)
        self.assertEqual(got, expected, "split-gz read must equal the in-memory convert() output exactly")
        self.assertIn(sym, source)

    def test_split_threshold_zero_forces_every_series_through_plan(self):
        """Owner fix-round-1 (2026-09-29): a public-repo dest root (data/history/ftmo) must not carry ANY
        plain, uncompressed multi-MB JSON -- `--split-threshold-bytes 0` makes `plan()` treat every file as
        'large' regardless of size, so even a tiny export never takes the in-memory `raw` path."""
        M = self.M
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        write_raw_export(raw_path, self._candles_crossing_a_utc_year())
        rows = M.plan(src_dir=self.tmp, split_threshold=0)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("error", rows[0])
        self.assertNotIn("raw", rows[0], "threshold=0 must route even a tiny file through the split path")
        self.assertIn("header", rows[0])

    def test_split_threshold_zero_small_series_reads_back_identical_via_bt_load(self):
        """The exact claim owner fix-round-1 asked for: a SMALL series, written split+gz because
        split_threshold=0 forced it, reads back through `backtest-methods.load()` byte-identical to what the
        in-memory `convert()` path would have produced for the same input."""
        M = self.M
        name, zone = MT.server_zone()
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = self._candles_crossing_a_utc_year()
        write_raw_export(raw_path, candles)

        raw, sym, tf = M.read_export(raw_path)
        expected = M.convert(raw, sym, tf, name, zone)

        rows = M.plan(src_dir=self.tmp, split_threshold=0)
        self.assertNotIn("raw", rows[0])
        dest_root = os.path.join(self.tmp, "out_threshold0")
        first, last, n, years, last_row = M.stream_write_split(
            rows[0]["path"], sym, tf, name, zone, dest_root, "mt5_bridge", header=rows[0]["header"])
        self.assertEqual(n, len(expected))

        split_dir = os.path.join(dest_root, f"ohlcv.{sym}.{tf}")
        self.assertTrue(os.path.isdir(split_dir))
        self.assertFalse(os.path.exists(split_dir + ".json"),
                          "no plain single-file copy should exist alongside the split dir")

        bt = _load("bt_ftmo_threshold0", "backtest-methods.py", env={"BT_HISTORY_ROOT": dest_root})
        got, source = bt.load(sym, tf)
        self.assertEqual(got, expected,
                          "a SMALL series written split+gz (threshold=0) must read back identical")

    def test_a_stale_plain_single_file_is_removed_once_superseded_by_a_split_write(self):
        """Re-importing an FTMO series that was PREVIOUSLY written as a plain `ohlcv.<sym>.<tf>.json` (an
        earlier run, before split_threshold=0 was chosen for this dest root) must not leave that stale copy
        next to the new split dir -- backtest-methods.load() checks the plain-file path FIRST, so a leftover
        stale file would silently shadow the new, correct split data forever."""
        M = self.M
        name, zone = MT.server_zone()
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = self._candles_crossing_a_utc_year()
        write_raw_export(raw_path, candles)
        raw, sym, tf = M.read_export(raw_path)

        dest_root = os.path.join(self.tmp, "out_stale")
        os.makedirs(dest_root, exist_ok=True)
        stale_path = os.path.join(dest_root, f"ohlcv.{sym}.{tf}.json")
        # Simulate a PRIOR plain-file write with different (old, now-wrong) content.
        with open(stale_path, "w", encoding="utf-8") as fh:
            json.dump({"symbol": sym, "timeframe": tf, "candles": [bar("2000-01-01T00:00:00Z")],
                       "_source": "mt5_bridge_history_utc", "last_updated": "2000-01-01T00:00:00Z"}, fh)

        M.stream_write_split(raw_path, sym, tf, name, zone, dest_root, "mt5_bridge", header=raw)
        self.assertFalse(os.path.exists(stale_path), "the stale plain-file copy must be removed")
        self.assertTrue(os.path.isdir(os.path.join(dest_root, f"ohlcv.{sym}.{tf}")))

        bt = _load("bt_ftmo_stale", "backtest-methods.py", env={"BT_HISTORY_ROOT": dest_root})
        got, source = bt.load(sym, tf)
        self.assertEqual(len(got), 5, "load() must serve the NEW split data, not the stale plain-file copy")

    def test_split_dir_atomically_replaces_a_prior_one(self):
        """A second import over the same (symbol, tf) must never leave a reader looking at half-old,
        half-new parts."""
        M = self.M
        name, zone = MT.server_zone()
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        write_raw_export(raw_path, self._candles_crossing_a_utc_year())
        raw, sym, tf = M.read_export(raw_path)
        dest_root = os.path.join(self.tmp, "out2")
        M.stream_write_split(raw_path, sym, tf, name, zone, dest_root, "mt5_bridge", header=raw)
        first, last, n, years, last_row = M.stream_write_split(raw_path, sym, tf, name, zone, dest_root,
                                                       "mt5_bridge", header=raw)
        self.assertEqual(n, 5)
        split_dir = os.path.join(dest_root, f"ohlcv.{sym}.{tf}")
        self.assertEqual(sorted(os.listdir(split_dir)),
                         ["2019.json.gz", "2020.json.gz", "index.json"])


class StrictlyIncreasingAcrossPartBoundaries(unittest.TestCase):
    """Code review MINOR fix (2026-09-29): `history_store._read_split()` must fail loud on a time regression
    at the SEAM between two gz-year parts, not just within one part (each part was already validated
    internally at write time by `stream_write_split()`'s own per-bar check; nothing had checked the seam)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftmo-strict-order-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _write_split_dir(self, years_and_times):
        """A hand-built split dir: `years_and_times` is {year: [iso times]}, written directly (bypassing
        `stream_write_split()`) so a corrupt/hand-edited seam can be constructed on purpose."""
        d = os.path.join(self.tmp, "ohlcv.XAUUSD.1H")
        os.makedirs(d, exist_ok=True)
        years = sorted(years_and_times)
        for y in years:
            import gzip
            candles = [{"time": t, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
                      for t in years_and_times[y]]
            with gzip.open(os.path.join(d, f"{y}.json.gz"), "wt", encoding="utf-8") as fh:
                json.dump({"year": y, "candles": candles}, fh)
        with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as fh:
            json.dump({"symbol": "XAUUSD", "timeframe": "1H", "years": years, "_source": "mt5_bridge_history_utc",
                      "last_updated": "2026-01-01T00:00:00Z"}, fh)
        return d

    def test_a_time_regression_at_the_seam_raises(self):
        HS = _load("hs_strict_bad", "history_store.py")
        d = self._write_split_dir({
            2019: ["2019-12-31T22:00:00Z", "2019-12-31T23:00:00Z"],
            2020: ["2019-12-31T20:00:00Z", "2020-01-01T01:00:00Z"],   # first bar goes BACKWARDS vs 2019's last
        })
        with self.assertRaises(ValueError) as cm:
            HS._read_split(d)
        self.assertIn("not after the previous bar", str(cm.exception))

    def test_a_correctly_ordered_seam_reads_fine(self):
        HS = _load("hs_strict_ok", "history_store.py")
        d = self._write_split_dir({
            2019: ["2019-12-31T22:00:00Z", "2019-12-31T23:00:00Z"],
            2020: ["2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z"],
        })
        doc = HS._read_split(d)
        self.assertEqual(len(doc["candles"]), 4)
        self.assertEqual(doc["candles"][-1]["time"], "2020-01-01T01:00:00Z")


class ReplacedProviderNoticeOnSplitPath(unittest.TestCase):
    """MINOR fix (2026-09-29): the small-file write path has always reported '[replaces <prior provider>]'
    when a re-import supersedes a DIFFERENT provider's series (CLAUDE.md §59: research semantics changed).
    The split-gz write path (added 2026-09-28) did not -- `stream_write_split()` silently overwrote a prior
    series of any provider with no notice at all."""

    def setUp(self):
        self.M = IM()
        self.tmp = tempfile.mkdtemp(prefix="ftmo-replaced-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_prior_marker_any_reads_a_plain_file_predecessor(self):
        M = self.M
        dest_root = os.path.join(self.tmp, "out")
        os.makedirs(dest_root, exist_ok=True)
        with open(os.path.join(dest_root, "ohlcv.XAUUSD.1H.json"), "w", encoding="utf-8") as fh:
            json.dump({"symbol": "XAUUSD", "timeframe": "1H", "candles": [],
                      "_source": "mt5_bridge_history_utc"}, fh)
        self.assertEqual(M._prior_marker_any(dest_root, "XAUUSD", "1H"), "mt5_bridge_history_utc")

    def test_prior_marker_any_reads_a_split_dir_predecessor(self):
        M = self.M
        name, zone = MT.server_zone()
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = [bar(f"2026-01-15T{h:02d}:00:00") for h in range(3)]
        write_raw_export(raw_path, candles)
        raw, sym, tf = M.read_export(raw_path)
        dest_root = os.path.join(self.tmp, "out2")
        M.stream_write_split(raw_path, sym, tf, name, zone, dest_root, "mt5_bridge", header=raw)
        self.assertEqual(M._prior_marker_any(dest_root, sym, tf), "mt5_bridge_history_utc")

    def test_prior_marker_any_is_none_when_nothing_exists(self):
        M = self.M
        dest_root = os.path.join(self.tmp, "empty")
        os.makedirs(dest_root, exist_ok=True)
        self.assertIsNone(M._prior_marker_any(dest_root, "XAUUSD", "1H"))

    def test_a_different_providers_split_series_is_detected_as_replaced(self):
        """The scenario the notice exists for: FTMO's importer run supersedes a MetaQuotes-Demo split series
        (synthetic here -- MetaQuotes-Demo series are never actually split in production, but the marker
        comparison this test pins does not care which shape the PRIOR series was written in)."""
        M = self.M
        name, zone = MT.server_zone()
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = [bar(f"2026-01-15T{h:02d}:00:00") for h in range(3)]
        write_raw_export(raw_path, candles)
        raw, sym, tf = M.read_export(raw_path)
        dest_root = os.path.join(self.tmp, "out3")
        # a prior split write, as if from a DIFFERENT provider
        M.stream_write_split(raw_path, sym, tf, name, zone, dest_root, "mt5_bridge", header=raw)
        prior = M._prior_marker_any(dest_root, sym, tf)
        out_marker_for_ftmo = M._out_marker("mt5_bridge_ftmo")
        self.assertEqual(prior, "mt5_bridge_history_utc")
        self.assertNotEqual(prior, out_marker_for_ftmo,
                            "a re-import under a DIFFERENT provider must be detected as a replacement")


class HeaderOnlyParsing(unittest.TestCase):
    """`_header_only()`/`plan()`'s large-file branch must see the SAME header `read_export()` would have,
    without reading the candles. Caught a real bug: ExportHistory.mq5 writes a leading `{` on its own line
    (`FileWriteString(h, "{\\n")`), and including that line in the header reconstruction produced `"{" + "{"`
    -- two opening braces -- which is invalid JSON. `write_raw_export()` reproduces that leading-brace line
    exactly, which is what exposed it."""

    def setUp(self):
        self.M = IM()
        self.tmp = tempfile.mkdtemp(prefix="ftmo-header-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_header_only_matches_a_full_read_export(self):
        M = self.M
        path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        candles = [bar(f"2026-01-15T{h:02d}:00:00") for h in range(3)]
        write_raw_export(path, candles, sym="XAUUSD", tf="1H", server="MetaQuotes-Demo")

        header, size = M._header_only(path)
        raw, sym, tf = M.read_export(path)
        self.assertEqual(header["symbol"], raw["symbol"])
        self.assertEqual(header["_server"], raw["_server"])
        self.assertEqual(header["_source"], raw["_source"])
        self.assertEqual(size, os.path.getsize(path))

    def test_plan_treats_a_file_above_the_threshold_as_large_without_reading_candles(self):
        M = self.M
        path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        write_raw_export(path, [bar("2026-01-15T12:00:00")], sym="XAUUSD", tf="1H", server="MetaQuotes-Demo")
        real_threshold = M.SPLIT_RAW_THRESHOLD_BYTES
        try:
            M.SPLIT_RAW_THRESHOLD_BYTES = 1   # force the large-file branch on this tiny fixture
            rows = M.plan(src_dir=self.tmp)
        finally:
            M.SPLIT_RAW_THRESHOLD_BYTES = real_threshold
        self.assertEqual(len(rows), 1)
        self.assertNotIn("error", rows[0])
        self.assertNotIn("raw", rows[0], "a large-file row must not carry the full in-memory `raw` dict")
        self.assertEqual(rows[0]["symbol"], "XAUUSD")


class DefaultRootUnchanged(unittest.TestCase):
    """HISTORY_ROOT unset must behave exactly like the hardcoded `data/history` path did before it existed."""

    def test_history_root_defaults_to_data_history(self):
        bt = _load("bt_ftmo_default", "backtest-methods.py", env={"BT_HISTORY_ROOT": None})
        self.assertEqual(os.path.normpath(bt.HISTORY_ROOT),
                          os.path.normpath(os.path.join(ROOT, "data", "history")))

    def test_a_real_metaquotes_demo_file_loads_identically(self):
        real = os.path.join(ROOT, "data", "history", "ohlcv.XAUUSD.15m.json")
        if not os.path.exists(real):
            self.skipTest("data/history/ohlcv.XAUUSD.15m.json not present in this checkout")
        with open(real, encoding="utf-8") as fh:
            direct = json.load(fh)

        bt = _load("bt_ftmo_default2", "backtest-methods.py", env={"BT_HISTORY_ROOT": None})
        got, source = bt.load("XAUUSD", "15m")
        self.assertEqual(got, direct["candles"])
        self.assertIn("XAUUSD", source)

    def test_missing_series_is_still_none_none(self):
        bt = _load("bt_ftmo_default3", "backtest-methods.py", env={"BT_HISTORY_ROOT": None})
        got, source = bt.load("NOSUCHSYMBOL", "15m")
        self.assertIsNone(got)
        self.assertIsNone(source)


class SymbolMapApplied(unittest.TestCase):
    def setUp(self):
        self.M = IM()
        self.tmp = tempfile.mkdtemp(prefix="ftmo-symmap-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_raw_symbol_translates_to_canonical_before_the_allowlist_check(self):
        M = self.M
        raw_path = os.path.join(self.tmp, "history.US500.cash.1H.json")
        write_raw_export(raw_path, [bar("2026-01-15T12:00:00")], sym="US500.cash", tf="1H",
                          server="FTMO-Demo")
        symbol_map = {"US500.cash": "US500"}
        raw, sym, tf = M.read_export(raw_path, provider="mt5_bridge_ftmo", symbol_map=symbol_map)
        self.assertEqual(sym, "US500")
        name, zone = MT.server_zone("mt5_bridge_ftmo")
        candles = M.convert(raw, sym, tf, name, zone)
        doc = M.series(raw, sym, tf, candles, name, out_marker=M._out_marker("mt5_bridge_ftmo"))
        self.assertEqual(doc["symbol"], "US500")
        self.assertEqual(doc["_source"], "mt5_bridge_ftmo_history_utc")

    def test_an_untranslated_raw_symbol_is_used_as_is(self):
        """XAUUSD/XAGUSD map to themselves in data/history/costs/ftmo/symbol-map.json -- identity is a valid
        entry, not merely the fallback for a symbol missing from the map."""
        M = self.M
        raw_path = os.path.join(self.tmp, "history.XAUUSD.1H.json")
        write_raw_export(raw_path, [bar("2026-01-15T12:00:00")], sym="XAUUSD", tf="1H", server="FTMO-Demo")
        raw, sym, tf = M.read_export(raw_path, provider="mt5_bridge_ftmo", symbol_map={"XAUUSD": "XAUUSD"})
        self.assertEqual(sym, "XAUUSD")

    def test_the_real_symbol_map_file_loads_and_matches_its_own_shape(self):
        M = self.M
        path = os.path.join(ROOT, "data", "history", "costs", "ftmo", "symbol-map.json")
        m = M.load_symbol_map(path)
        self.assertEqual(m["US500.cash"], "US500")
        self.assertEqual(m["XAUUSD"], "XAUUSD")


class ZoneConventionRefusals(unittest.TestCase):
    """The FTMO convention path refuses on the same two questions the IANA-only path always has: no
    declaration, and an incomplete/unimplemented one. A convention is not a second way to guess."""

    def test_ftmo_provider_resolves_today(self):
        name, zone = MT.server_zone("mt5_bridge_ftmo")
        self.assertIn("us_dst_dates_fixed_offset", name)

    def test_an_unimplemented_convention_name_refuses(self):
        real = P.PROVIDERS["mt5_bridge_ftmo"]["server_timezone_convention"]
        try:
            P.PROVIDERS["mt5_bridge_ftmo"]["server_timezone_convention"] = "made_up_convention"
            with self.assertRaises(MT.Refused) as cm:
                MT.server_zone("mt5_bridge_ftmo")
            self.assertIn("made_up_convention", str(cm.exception))
        finally:
            P.PROVIDERS["mt5_bridge_ftmo"]["server_timezone_convention"] = real

    def test_a_convention_with_no_offset_magnitude_refuses(self):
        real = P.PROVIDERS["mt5_bridge_ftmo"].pop("server_utc_offset_standard_sec")
        try:
            with self.assertRaises(MT.Refused) as cm:
                MT.server_zone("mt5_bridge_ftmo")
            self.assertIn("server_utc_offset_standard_sec", str(cm.exception))
        finally:
            P.PROVIDERS["mt5_bridge_ftmo"]["server_utc_offset_standard_sec"] = real

    def test_a_file_from_the_other_server_refuses(self):
        with self.assertRaises(MT.Refused) as cm:
            MT.check_server("MetaQuotes-Demo", "test", provider="mt5_bridge_ftmo")
        self.assertIn("MetaQuotes-Demo", str(cm.exception))


class UsDatesZoneBehavior(unittest.TestCase):
    """`UsDatesFixedOffsetZone`: transitions on the US calendar, not the EU one -- the opposite of
    mt5_bridge's Europe/Helsinki -- and both DST edge cases refuse/resolve the same way that zone's do."""

    def setUp(self):
        self.name, self.zone = MT.server_zone("mt5_bridge_ftmo")

    def _utc(self, stamp):
        return MT.to_utc(stamp, self.zone, self.name, "test").isoformat()

    def test_winter_is_plus_two(self):
        self.assertEqual(self._utc("2026-01-15T12:00:00"), "2026-01-15T10:00:00+00:00")

    def test_summer_is_plus_three(self):
        self.assertEqual(self._utc("2026-07-15T12:00:00"), "2026-07-15T09:00:00+00:00")

    def test_no_shift_in_the_eu_gap_week_unlike_mt5_bridge(self):
        """2026-03-09 is AFTER the US 2nd-Sunday-March transition but BEFORE the EU last-Sunday-March one --
        exactly the week docs/architecture/mt5-history-export.md found MetaQuotes-Demo dips to +02:00 in.
        FTMO-Demo must NOT dip: this is the whole finding in docs/audits/2026-09-29-ftmo-server-timezone.md."""
        self.assertEqual(self._utc("2026-03-09T12:00:00"), "2026-03-09T09:00:00+00:00")   # already +03:00

    def test_no_shift_in_the_other_gap_week_either(self):
        # 2026-10-31 is AFTER the EU last-Sunday-October transition but BEFORE the US 1st-Sunday-November one.
        self.assertEqual(self._utc("2026-10-31T12:00:00"), "2026-10-31T09:00:00+00:00")   # still +03:00

    def test_a_nonexistent_local_time_refuses(self):
        # US 2nd Sunday March 2026 = 2026-03-08; the local clock jumps 09:00 -> 10:00 that day.
        with self.assertRaises(MT.Refused) as cm:
            self._utc("2026-03-08T09:30:00")
        self.assertIn("does not exist", str(cm.exception))

    def test_an_ambiguous_local_time_refuses(self):
        # US 1st Sunday Nov 2026 = 2026-11-01; the local hour 08:00-09:00 repeats.
        with self.assertRaises(MT.Refused) as cm:
            self._utc("2026-11-01T08:30:00")
        self.assertIn("twice", str(cm.exception))

    def test_ordered_resolution_of_the_ambiguous_hour_matches_fold_convention(self):
        first, amb1 = MT.to_utc_ordered("2026-11-01T08:30:00", self.zone, self.name, "t1", None)
        second, amb2 = MT.to_utc_ordered("2026-11-01T08:30:00", self.zone, self.name, "t2", first)
        self.assertTrue(amb1 and amb2)
        self.assertLess(first, second)

    def test_a_timestamp_that_already_claims_utc_refuses(self):
        with self.assertRaises(MT.Refused):
            self._utc("2026-01-15T12:00:00Z")


class ScanCacheDigestsSplitFiles(unittest.TestCase):
    """A split-gz history directory's key must change when a PART inside it changes, not just when the
    directory itself is touched -- scripts/scan_cache.py's whole correctness rests on this."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ftmo-digest-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.hist = os.path.join(self.tmp, "hist")
        os.makedirs(self.hist)
        self.series_dir = os.path.join(self.hist, "ohlcv.XAUUSD.1m")
        os.makedirs(self.series_dir)
        with open(os.path.join(self.series_dir, "index.json"), "w", encoding="utf-8") as fh:
            fh.write('{"years": [2020]}')
        import gzip
        with gzip.open(os.path.join(self.series_dir, "2020.json.gz"), "wt", encoding="utf-8") as fh:
            fh.write('{"candles": []}')

    def test_editing_a_part_changes_the_digest(self):
        before = SC.data_digest(ROOT, "XAUUSD", history_root=self.hist)
        import gzip
        with gzip.open(os.path.join(self.series_dir, "2020.json.gz"), "wt", encoding="utf-8") as fh:
            fh.write('{"candles": [{"time": "2020-01-01T00:00:00Z"}]}')
        after = SC.data_digest(ROOT, "XAUUSD", history_root=self.hist)
        self.assertNotEqual(before, after)

    def test_default_history_root_is_unaffected(self):
        """`history_root=None` must reproduce the pre-existing default-root digest exactly."""
        default_a = SC.data_digest(ROOT, "XAUUSD")
        default_b = SC.data_digest(ROOT, "XAUUSD", history_root=None)
        self.assertEqual(default_a, default_b)


if __name__ == "__main__":
    unittest.main()
