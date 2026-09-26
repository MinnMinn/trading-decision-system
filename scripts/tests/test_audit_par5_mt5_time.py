"""Audit PAR-5 (docs/audits/2026-09-24-system-audit.md, ADR 0006): MT5 live bars in UTC per bar, and a
freshness stamp that is the last real quote.

Up to EA v1.02 (commit c86c8e4) ExportOHLCV.mq5 stamped EVERY bar with today's rounded server offset, so a bar
on the other side of a DST change was an hour off the history the backtest reads, and `last_updated` was the PC
clock, so a frozen quote stream still looked fresh. v1.03 exports raw server time; scripts/mt5_time.py converts
it with the zone providers.json declares -- the same code the history importer uses.

Every test here writes only to a temp folder. data/live/ is never touched.
"""
import datetime
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mt5_time as MT  # noqa: E402
import providers as P  # noqa: E402

UTC = datetime.timezone.utc
PIN = "c86c8e4"        # the last commit with the v1.02 live scheme; regression pins read it, never HEAD


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


IMP = _load("imp_mt5_par5", "scripts/import-mt5-history.py")
SERVER = P.provider("mt5_bridge").get("server")
ZNAME, ZONE = MT.server_zone()

# Two REAL XAUUSD D1 bars (OHLC copied from the MT5 export and data/history/ohlcv.XAUUSD.1D.json), one each side
# of the 2024-10-27 EU fall-back. Server midnight is 21:00Z in summer (UTC+3) and 22:00Z in winter (UTC+2).
REAL_PAIR = [
    {"time_server": "2024-10-25T00:00:00", "open": 2735.83, "high": 2747.55, "low": 2717.02, "close": 2747.39,
     "volume": 84877},
    {"time_server": "2024-10-28T00:00:00", "open": 2732.7, "high": 2745.92, "low": 2724.72, "close": 2742.24,
     "volume": 87422},
]
REAL_PAIR_UTC = ["2024-10-24T21:00:00Z", "2024-10-27T22:00:00Z"]


def live_raw(candles, symbol="XAUUSD", timeframe="1D", **over):
    doc = {"symbol": symbol, "timeframe": timeframe, "_source": "mt5_bridge_live", "_time_basis": "server",
           "_server": SERVER, "_ea_version": "1.03", "last_quote_server": candles[-1]["time_server"] if candles
           else None, "_exported_at_utc": "2030-01-01T00:00:00Z",
           "_volume_caveat": "tick_volume, not real traded volume", "candles": candles}
    doc.update(over)
    return doc


def bar(ts, o=100.0, h=101.0, lo=99.0, c=100.5, v=10):
    return {"time_server": ts, "open": o, "high": h, "low": lo, "close": c, "volume": v}


def m15(start_local, n):
    t = datetime.datetime.fromisoformat(start_local)
    return [bar((t + datetime.timedelta(minutes=15 * i)).isoformat()) for i in range(n)]


def git_show(path):
    try:
        r = subprocess.run(["git", "-C", ROOT, "show", f"{PIN}:{path}"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


class TempBridge(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="par5-")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def put(self, name, doc, mtime=None, text=None):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text if text is not None else json.dumps(doc))
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as fh:
            return json.load(fh)


# ------------------------------------------------------------------------------------------- the hour itself --

class SameBarSameStamp(unittest.TestCase):
    """The acceptance test the audit asked for: the live path and the history path agree on every bar."""

    def test_real_xauusd_d1_pair_across_dst_gets_the_same_utc_from_live_and_history(self):
        live = MT.convert_live(live_raw(REAL_PAIR), ZNAME, ZONE)
        hist_raw = {"symbol": "XAUUSD", "timeframe": "1D", "_source": "mt5_bridge_history", "_server": SERVER,
                    "candles": [dict(c, time=c["time_server"]) for c in REAL_PAIR]}
        hist = IMP.convert(hist_raw, "XAUUSD", "1D", ZNAME, ZONE)
        self.assertEqual([c["time"] for c in live["candles"]], REAL_PAIR_UTC)
        self.assertEqual([c["time"] for c in live["candles"]], [c["time"] for c in hist])

    def test_and_it_matches_the_committed_research_history_at_the_pinned_commit(self):
        src = git_show("data/history/ohlcv.XAUUSD.1D.json")
        if src is None:
            self.skipTest(f"git show {PIN} unavailable")
        by_ohlc = {(c["open"], c["close"]): c["time"] for c in json.loads(src)["candles"]}
        live = MT.convert_live(live_raw(REAL_PAIR), ZNAME, ZONE)
        for c in live["candles"]:
            self.assertEqual(by_ohlc[(c["open"], c["close"])], c["time"])

    def test_summer_bar_is_plus_three_and_winter_bar_is_plus_two(self):
        doc = MT.convert_live(live_raw([bar("2026-01-15T12:00:00"), bar("2026-07-15T12:00:00")],
                                       timeframe="1H"), ZNAME, ZONE)
        self.assertEqual([c["time"] for c in doc["candles"]], ["2026-01-15T10:00:00Z", "2026-07-15T09:00:00Z"])

    def test_the_importer_and_the_live_converter_share_one_implementation(self):
        """rules/single-source-of-truth: two copies of the zone lookup would drift."""
        self.assertIs(IMP._zone, MT.server_zone)
        self.assertIs(IMP._to_utc, MT.to_utc)
        self.assertIs(IMP.Refused, MT.Refused)


class DstTransitions(unittest.TestCase):
    def test_fall_back_hour_duplicated_is_resolved_by_order(self):
        # 2026-10-25: local 04:00 EEST -> 03:00 EET, so 03:00-03:59 local happens twice.
        stamps = ["02:45", "03:00", "03:15", "03:30", "03:45", "03:00", "03:15", "03:30", "03:45", "04:00"]
        bars = [bar(f"2026-10-25T{s}:00") for s in stamps]
        doc = MT.convert_live(live_raw(bars, timeframe="15m"), ZNAME, ZONE)
        got = [c["time"][11:16] for c in doc["candles"]]
        self.assertEqual(got, ["23:45", "00:00", "00:15", "00:30", "00:45", "01:00", "01:15", "01:30", "01:45",
                               "02:00"])
        self.assertEqual(doc["_dst_ambiguous_resolved"], 8)
        self.assertEqual(doc["candles"][0]["time"][:10], "2026-10-24")

    def test_a_lone_ambiguous_bar_takes_the_earlier_instant(self):
        doc = MT.convert_live(live_raw([bar("2026-10-25T02:00:00"), bar("2026-10-25T03:00:00")],
                                       timeframe="1H"), ZNAME, ZONE)
        self.assertEqual(doc["candles"][1]["time"], "2026-10-25T00:00:00Z")

    def test_the_resolution_is_deterministic(self):
        bars = [bar(f"2026-10-25T{s}:00") for s in ("03:00", "03:30", "03:00", "03:30")]
        a = MT.convert_live(live_raw(bars, timeframe="15m"), ZNAME, ZONE)
        b = MT.convert_live(live_raw(bars, timeframe="15m"), ZNAME, ZONE)
        self.assertEqual(a, b)

    def test_spring_forward_gap_refuses_on_the_live_path(self):
        with self.assertRaises(MT.Refused) as cm:
            MT.convert_live(live_raw([bar("2026-03-29T02:45:00"), bar("2026-03-29T03:30:00")],
                                     timeframe="15m"), ZNAME, ZONE)
        self.assertIn("does not exist", str(cm.exception))

    def test_bars_either_side_of_the_spring_gap_are_contiguous_in_utc(self):
        doc = MT.convert_live(live_raw([bar("2026-03-29T02:45:00"), bar("2026-03-29T04:00:00")],
                                       timeframe="15m"), ZNAME, ZONE)
        self.assertEqual([c["time"] for c in doc["candles"]], ["2026-03-29T00:45:00Z", "2026-03-29T01:00:00Z"])

    def test_the_history_importer_keeps_its_strict_refusal(self):
        with self.assertRaises(MT.Refused):
            IMP._to_utc("2026-10-25T03:30:00", ZONE, ZNAME, "t")


# ------------------------------------------------------------------------------------------------- staleness --

class FrozenQuoteReadsStale(TempBridge):
    """§52: the runner's own MT5 rule (now - last_updated > 2*TF + 900 s) must fire when quotes stop."""

    def _runner(self):
        sr = _load("sr_par5", "scripts/strategy-runner.py")
        return sr

    def _write_15m(self, last_quote, beat):
        bars = m15("2026-09-25T13:00:00", 44)          # server EEST, last bar 23:45 local = 20:45Z
        self.put("ohlcv.XAUUSD.15m.server.json",
                 live_raw(bars, timeframe="15m", last_quote_server=last_quote, _exported_at_utc=beat))

    def test_frozen_last_quote_fires_the_runner_staleness_rule(self):
        sr = self._runner()
        # Saturday noon UTC: the EA timer still runs (heartbeat fresh), the last tick was Friday's close.
        self._write_15m("2026-09-25T23:59:58", "2026-09-26T11:59:30Z")
        t = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
        with mock.patch.object(sr, "MT5_DIR", self.dir):
            with self.assertRaises(RuntimeError) as cm:
                sr.fetch_candles("XAUUSD", "15m", "cfd", t)
        self.assertIn("stale", str(cm.exception))
        self.assertEqual(self.read("ohlcv.XAUUSD.15m.json")["last_updated"], "2026-09-25T20:59:58Z")

    def test_a_live_quote_does_not_fire_it(self):
        sr = self._runner()
        self._write_15m("2026-09-25T23:49:50", "2026-09-25T20:49:55Z")
        t = datetime.datetime(2026, 9, 25, 20, 50, tzinfo=UTC)
        stub = lambda *a, **k: {"state": sr.FH.HEALTHY, "recovered": False, "findings": []}  # noqa: E731
        with mock.patch.object(sr, "MT5_DIR", self.dir), mock.patch.object(sr.FH, "observe", stub):
            out = sr.fetch_candles("XAUUSD", "15m", "cfd", t)
        self.assertTrue(out)
        self.assertEqual(out[-1]["time"], "2026-09-25T20:30:00Z")   # the forming 20:45 bar is dropped

    def test_the_v102_scheme_could_not_fire_on_the_same_weekend(self):
        """Pinned: c86c8e4 wrote last_updated = IsoTime(TimeCurrent()) ~= TimeGMT(), the heartbeat."""
        src = git_show("integrations/mt5/ExportOHLCV.mq5")
        if src is None:
            self.skipTest(f"git show {PIN} unavailable")
        self.assertIn('"last_updated\\": \\"" + IsoTime(TimeCurrent())', src)
        heartbeat = datetime.datetime(2026, 9, 26, 11, 59, 30, tzinfo=UTC)
        t = datetime.datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
        self.assertLessEqual((t - heartbeat).total_seconds(), 2 * 900 + 900)   # rule silent under v1.02

    def test_missing_last_quote_refuses_rather_than_writing_an_undated_file(self):
        self.put("ohlcv.XAUUSD.15m.server.json", live_raw(m15("2026-09-25T13:00:00", 4), timeframe="15m",
                                                           last_quote_server=None))
        r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "refused")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "ohlcv.XAUUSD.15m.json")))

    def test_a_quote_from_the_future_refuses(self):
        self.put("ohlcv.XAUUSD.15m.server.json", live_raw(m15("2026-09-25T13:00:00", 4), timeframe="15m",
                                                           last_quote_server="2026-09-25T16:00:00",
                                                           _exported_at_utc="2026-09-25T12:00:00Z"))
        r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "refused")
        self.assertIn("future", r[0]["why"])


# -------------------------------------------------------------------------------------------------- refusals --

class NoZoneNoConversion(TempBridge):
    def setUp(self):
        super().setUp()
        self.legacy = {"symbol": "XAUUSD", "timeframe": "1D", "candles": [], "last_updated": "2020-01-01T00:00:00Z"}
        self.put("ohlcv.XAUUSD.1D.json", self.legacy, mtime=1_000_000)
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)

    def _untouched(self):
        self.assertEqual(self.read("ohlcv.XAUUSD.1D.json"), self.legacy)

    def test_missing_zone_refuses_and_leaves_the_json(self):
        real = P.PROVIDERS["mt5_bridge"].pop("server_timezone")
        try:
            r = MT.sync_live(self.dir)
        finally:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = real
        self.assertEqual(r[0]["status"], "refused")
        self.assertIn("server_timezone", r[0]["why"])
        self._untouched()

    def test_an_abbreviation_zone_refuses(self):
        real = P.PROVIDERS["mt5_bridge"]["server_timezone"]
        try:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = "EET"
            r = MT.sync_live(self.dir)
        finally:
            P.PROVIDERS["mt5_bridge"]["server_timezone"] = real
        self.assertEqual(r[0]["status"], "refused")
        self._untouched()

    def test_a_different_server_refuses(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR, _server="OtherBroker-Live"), mtime=2_000_000)
        r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "refused")
        self.assertIn("OtherBroker-Live", r[0]["why"])
        self._untouched()

    def test_a_file_that_does_not_declare_server_time_refuses(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR, _time_basis=None), mtime=2_000_000)
        self.assertEqual(MT.sync_live(self.dir)[0]["status"], "refused")
        self._untouched()

    def test_a_stamp_that_already_claims_utc_refuses(self):
        bad = [dict(REAL_PAIR[0], time_server="2024-10-25T00:00:00Z")]
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(bad), mtime=2_000_000)
        self.assertEqual(MT.sync_live(self.dir)[0]["status"], "refused")
        self._untouched()

    def test_the_cli_exits_nonzero_on_a_refusal(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR, _server="OtherBroker-Live"), mtime=2_000_000)
        with mock.patch("sys.stderr"), mock.patch("sys.stdout"):
            self.assertEqual(MT.main(["sync", "--dir", self.dir]), 2)


# ------------------------------------------------------------------------------------------------- transition --

class LegacyAndPrecedence(TempBridge):
    def test_a_legacy_utc_only_file_is_left_exactly_as_it_is(self):
        p = self.put("ohlcv.XAUUSD.15m.json", {"symbol": "XAUUSD", "candles": [{"time": "2026-09-25T10:00:00Z"}]},
                     mtime=1_500_000)
        before = open(p, "rb").read()
        self.assertEqual(MT.sync_live(self.dir), [])
        self.assertEqual(open(p, "rb").read(), before)
        self.assertEqual(os.path.getmtime(p), 1_500_000)

    def test_a_newer_server_file_wins(self):
        self.put("ohlcv.XAUUSD.1D.json", {"legacy": True}, mtime=1_000_000)
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)
        r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "converted")
        self.assertEqual([c["time"] for c in self.read("ohlcv.XAUUSD.1D.json")["candles"]], REAL_PAIR_UTC)

    def test_a_newer_legacy_file_wins_and_is_not_touched(self):
        p = self.put("ohlcv.XAUUSD.1D.json", {"legacy": True}, mtime=3_000_000)
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)
        self.assertEqual(MT.sync_live(self.dir)[0]["status"], "up_to_date")
        self.assertEqual(self.read("ohlcv.XAUUSD.1D.json"), {"legacy": True})
        self.assertEqual(os.path.getmtime(p), 3_000_000)

    def test_converting_twice_is_a_no_op(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)
        self.assertEqual(MT.sync_live(self.dir)[0]["status"], "converted")
        self.assertEqual(MT.sync_live(self.dir)[0]["status"], "up_to_date")

    def test_symbol_and_timeframe_filters(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)
        self.put("ohlcv.XAGUSD.1D.server.json", live_raw(REAL_PAIR, symbol="XAGUSD"), mtime=2_000_000)
        r = MT.sync_live(self.dir, symbols={"XAGUSD"}, timeframes={"1D"})
        self.assertEqual([x["file"] for x in r], ["ohlcv.XAGUSD.1D.server.json"])

    def test_output_keeps_the_reader_contract_and_names_its_provenance(self):
        self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)
        MT.sync_live(self.dir)
        d = self.read("ohlcv.XAUUSD.1D.json")
        self.assertEqual(d["_source"], "mt5_bridge_live")
        self.assertEqual(P.by_source_marker(d["_source"]), "mt5_bridge")
        self.assertEqual(d["_server"], SERVER)
        self.assertEqual(d["_server_timezone"], ZNAME)
        self.assertEqual(d["_time_basis_converted_from"], "server")
        self.assertEqual(set(d["candles"][0]), {"time", "open", "high", "low", "close", "volume"})
        self.assertTrue(all(c["time"].endswith("Z") for c in d["candles"]))


class AtomicWrite(TempBridge):
    def setUp(self):
        super().setUp()
        self.old = {"old": True}
        self.put("ohlcv.XAUUSD.1D.json", self.old, mtime=1_000_000)
        self.src = self.put("ohlcv.XAUUSD.1D.server.json", live_raw(REAL_PAIR), mtime=2_000_000)

    def test_a_failed_replace_leaves_the_old_file_whole_and_no_temp_behind(self):
        with mock.patch.object(MT.os, "replace", side_effect=PermissionError("held open")), \
                mock.patch.object(MT.time, "sleep"):
            r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "busy")
        self.assertEqual(self.read("ohlcv.XAUUSD.1D.json"), self.old)
        self.assertEqual(sorted(os.listdir(self.dir)), ["ohlcv.XAUUSD.1D.json", "ohlcv.XAUUSD.1D.server.json"])

    def test_the_write_goes_through_a_temp_file_and_os_replace(self):
        seen = []
        real = os.replace

        def spy(a, b):
            seen.append((os.path.basename(a), os.path.basename(b), json.load(open(a, encoding="utf-8"))["symbol"]))
            return real(a, b)
        with mock.patch.object(MT.os, "replace", side_effect=spy):
            MT.sync_live(self.dir)
        self.assertEqual(len(seen), 1)
        self.assertTrue(seen[0][0].startswith("ohlcv.XAUUSD.1D.json.tmp"))
        self.assertEqual(seen[0][1:], ("ohlcv.XAUUSD.1D.json", "XAUUSD"))   # the temp was complete JSON
        self.assertEqual(sorted(os.listdir(self.dir)), ["ohlcv.XAUUSD.1D.json", "ohlcv.XAUUSD.1D.server.json"])

    def test_output_mtime_is_the_source_mtime(self):
        MT.sync_live(self.dir)
        self.assertEqual(os.path.getmtime(os.path.join(self.dir, "ohlcv.XAUUSD.1D.json")), 2_000_000)

    def test_a_half_written_server_file_is_skipped_not_converted(self):
        self.put("ohlcv.XAUUSD.1D.server.json", None, mtime=2_500_000,
                 text=json.dumps(live_raw(REAL_PAIR))[:120])
        r = MT.sync_live(self.dir)
        self.assertEqual(r[0]["status"], "unreadable")
        self.assertEqual(self.read("ohlcv.XAUUSD.1D.json"), self.old)


# ------------------------------------------------------------------------------------------ the pinned error --

class PinnedV102Error(unittest.TestCase):
    """What c86c8e4's EA did, reproduced from its own source, on the real bar pair: one hour wrong in winter."""

    def test_c86c8e4_applied_one_current_offset_to_every_bar(self):
        src = git_show("integrations/mt5/ExportOHLCV.mq5")
        if src is None:
            self.skipTest(f"git show {PIN} unavailable")
        self.assertIn('#property version   "1.02"', src)
        self.assertIn("datetime offset = (datetime)ServerUtcOffset();", src)
        self.assertIn("datetime t = serverTime - offset;", src)
        self.assertIn("long raw = (long)(TimeCurrent() - TimeGMT());", src)

        def v102_iso(server_stamp, offset_now=10800):     # the measured September offset (providers.json)
            t = datetime.datetime.fromisoformat(server_stamp) - datetime.timedelta(seconds=offset_now)
            return t.strftime("%Y-%m-%dT%H:%M:%SZ")
        old = [v102_iso(c["time_server"]) for c in REAL_PAIR]
        self.assertEqual(old, ["2024-10-24T21:00:00Z", "2024-10-27T21:00:00Z"])
        new = [c["time"] for c in MT.convert_live(live_raw(REAL_PAIR), ZNAME, ZONE)["candles"]]
        self.assertEqual(old[0], new[0])                                   # summer bar: right by luck of season
        err = (datetime.datetime.fromisoformat(new[1].replace("Z", "+00:00"))
               - datetime.datetime.fromisoformat(old[1].replace("Z", "+00:00")))
        self.assertEqual(err, datetime.timedelta(hours=1))                 # winter bar: an hour early

    def test_head_ea_exports_raw_server_time_and_the_last_quote(self):
        src = open(os.path.join(ROOT, "integrations", "mt5", "ExportOHLCV.mq5"), encoding="utf-8").read()
        self.assertIn('#property version   "1.03"', src)
        for token in ("time_server", "last_quote_server", "SymbolInfoTick", "ACCOUNT_SERVER", "_time_basis",
                      ".server.json", "FileMove"):
            self.assertIn(token, src)
        self.assertNotIn("ServerUtcOffset", src)
        self.assertNotIn('"last_updated', src)          # freshness is Python's, from the last quote

    def test_every_reader_entry_point_converts_first(self):
        runner = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("MT5T.sync_live(MT5_DIR", runner)
        self.assertLess(runner.index("MT5T.sync_live(MT5_DIR"), runner.index('raise RuntimeError(f"no MT5 export'))
        loop = open(os.path.join(ROOT, "scripts", "scan-loop.sh"), encoding="utf-8").read()
        self.assertLess(loop.index("scripts/mt5_time.py sync"), loop.index('if [ -s "data/live/mt5-bridge/ohlcv.'))


if __name__ == "__main__":
    unittest.main()
