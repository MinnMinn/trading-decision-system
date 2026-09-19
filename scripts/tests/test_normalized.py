"""CLAUDE.md §7 -- the normalized data layer and its provenance.

§7 lists fifteen fields a data record must preserve. Nine were absent before this module. They are DERIVED
here rather than written into every file, and the reasoning is worth keeping: `provider`, `source_venue`,
`market_type`, `canonical_symbol`, `aggregation_scope` and `underlying_venues` are facts about the REGISTRY,
not about a particular file of candles. Copying them into 131 data files would make 131 copies of something
docs/architecture/providers.json already owns.

The load-bearing function is `available_time()`. A bar with open time T on timeframe D is knowable at T+D and
not before -- reading its close at its open time is the commonest look-ahead there is. The live engine already
enforced exactly this, as an inline expression inside `drop_forming()`; the rule now has one definition, and
one of these tests pins the equivalence timeframe by timeframe so the unification cannot have changed
behaviour in the path that decides which bars a live setup may see.

The timeframe-duration table is the other thing under test. FOUR copies exist in this repo
(build-artifact.py, automation.py, event-ledger.py, strategy-runner.py). available_time() reads the one
automation.py owns; a drift test makes the other three safe rather than merely tolerated, because a wrong
duration here does not look like a bug -- it looks like a slightly different backtest.
"""
import datetime
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I
import normalized as N
import providers as P

UTC = datetime.timezone.utc


def runner():
    spec = importlib.util.spec_from_file_location("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def series(rows, **header):
    base = {"symbol": "BTCUSDT", "timeframe": "15m", "last_updated": "2026-09-17T18:00:00Z",
            "_source": "binance_public_rest_live", "candles": rows}
    base.update(header)
    return base


def bar(t, close=100.0):
    return {"time": t, "open": close, "high": close, "low": close, "close": close, "volume": 1.0}


class AvailableTime(unittest.TestCase):
    def test_a_bar_is_knowable_one_period_after_its_open(self):
        self.assertEqual(N.available_time(bar("2026-09-17T18:00:00Z"), "15m"),
                         datetime.datetime(2026, 9, 17, 18, 15, tzinfo=UTC))
        self.assertEqual(N.available_time(bar("2026-09-17T18:00:00Z"), "4H"),
                         datetime.datetime(2026, 9, 17, 22, 0, tzinfo=UTC))

    def test_an_unknown_timeframe_refuses(self):
        with self.assertRaises(ValueError):
            N.available_time(bar("2026-09-17T18:00:00Z"), "7m")

    def test_it_matches_the_inline_rule_the_live_engine_used(self):
        """The equivalence that makes the unification safe. The old expression is written out here ON PURPOSE:
        the assertion IS 'the rule did not change'."""
        sr = runner()
        for tf, secs in sr.TF_SEC.items():
            for opened in ("2026-09-17T00:00:00Z", "2026-03-29T01:00:00Z", "2026-12-31T23:00:00Z"):
                old = sr.parse_t(opened) + datetime.timedelta(seconds=secs)
                self.assertEqual(N.available_time(bar(opened), tf), old, f"{tf} @ {opened}")

    def test_drop_forming_still_drops_exactly_the_forming_bar(self):
        sr = runner()
        rows = [bar("2026-09-17T17:30:00Z"), bar("2026-09-17T17:45:00Z"), bar("2026-09-17T18:00:00Z")]
        # 18:05 -- the 18:00 bar has not closed yet
        kept = sr.drop_forming(list(rows), "15m", datetime.datetime(2026, 9, 17, 18, 5, tzinfo=UTC))
        self.assertEqual([r["time"] for r in kept], [rows[0]["time"], rows[1]["time"]])
        # exactly 18:15 -- the bar has just closed and is knowable, so it stays
        kept = sr.drop_forming(list(rows), "15m", datetime.datetime(2026, 9, 17, 18, 15, tzinfo=UTC))
        self.assertEqual(len(kept), 3, "a bar is available AT its close time, not one tick after")


class TimeframeTableHasOneSource(unittest.TestCase):
    """Four copies exist. This makes the duplication visible and safe instead of silently divergent."""

    def copies(self):
        out = {}
        spec = importlib.util.spec_from_file_location("ba", os.path.join(ROOT, "scripts", "build-artifact.py"))
        ba = importlib.util.module_from_spec(spec); spec.loader.exec_module(ba)
        out["build-artifact.py TF_MIN"] = {k: v * 60 for k, v in ba.TF_MIN.items()}
        spec = importlib.util.spec_from_file_location("el", os.path.join(ROOT, "scripts", "event-ledger.py"))
        el = importlib.util.module_from_spec(spec); spec.loader.exec_module(el)
        out["event-ledger.py TF_SEC"] = dict(el.TF_SEC)
        out["strategy-runner.py TF_SEC"] = dict(runner().TF_SEC)
        return out

    def test_every_copy_agrees_with_the_one_available_time_reads(self):
        bad = []
        for name, table in self.copies().items():
            for tf, secs in table.items():
                if tf in N.TF_MINUTES and N.TF_MINUTES[tf] * 60 != secs:
                    bad.append(f"{name}: {tf} = {secs}s but automation.TF_MINUTES says {N.TF_MINUTES[tf]*60}s")
        self.assertEqual(bad, [], "timeframe duration tables have drifted:\n  " + "\n  ".join(bad))


class Provenance(unittest.TestCase):
    def test_all_fifteen_fields_are_present(self):
        p = N.provenance(series([bar("2026-09-17T18:00:00Z")]), "BTCUSDT", "15m", "/tmp/x.json")
        for field in ("provider", "source_venue", "source_identifier", "aggregation_scope",
                      "underlying_venues", "symbol", "canonical_symbol", "market", "market_type",
                      "timeframe", "event_time", "available_time", "received_time", "data_scope",
                      "freshness_seconds", "quality"):
            self.assertIn(field, p)

    def test_provenance_is_joined_from_the_registries(self):
        p = N.provenance(series([bar("2026-09-17T18:00:00Z")]), "BTCUSDT", "15m", "/tmp/x.json")
        self.assertEqual(p["provider"], "binance_public")
        self.assertEqual(p["source_venue"], "binance")
        self.assertEqual(p["canonical_symbol"], "BTC/USDT")
        self.assertEqual(p["aggregation_scope"], "single_venue")
        self.assertEqual(p["underlying_venues"], ["binance"])

    def test_the_three_times_are_kept_distinct(self):
        """§7 keeps eventTime, availableTime and receivedTime separate because they answer different
        questions. Collapsing them is what makes a look-ahead invisible."""
        p = N.provenance(series([bar("2026-09-17T18:00:00Z")]), "BTCUSDT", "15m", "/tmp/x.json")
        self.assertEqual(p["event_time"], "2026-09-17T18:00:00Z")      # the bar's own open
        self.assertEqual(p["available_time"], "2026-09-17T18:15:00Z")  # when it became knowable
        self.assertEqual(p["received_time"], "2026-09-17T18:00:00Z")   # when we fetched it
        self.assertNotEqual(p["event_time"], p["available_time"])

    def test_a_mock_series_can_never_read_as_live(self):
        """SYSTEM-DESIGN.md §3's mock-integrity rule: MOCK outranks freshness however recent the file is."""
        raw = series([bar("2026-09-17T18:00:00Z")], _mock=True, last_updated="2026-09-17T18:00:00Z")
        p = N.provenance(raw, "BTCUSDT", "15m", "/tmp/x.json",
                         now=datetime.datetime(2026, 9, 17, 18, 1, tzinfo=UTC))
        self.assertEqual(p["quality"], "MOCK")

    def test_an_empty_series_is_unavailable_not_fresh(self):
        p = N.provenance(series([]), "BTCUSDT", "15m", "/tmp/x.json")
        self.assertEqual(p["quality"], "UNAVAILABLE")
        self.assertEqual(p["data_scope"]["bars"], 0)

    def test_an_old_series_is_stale(self):
        raw = series([bar("2026-09-17T18:00:00Z")], last_updated="2026-09-17T18:00:00Z")
        p = N.provenance(raw, "BTCUSDT", "15m", "/tmp/x.json",
                         now=datetime.datetime(2026, 9, 17, 19, 30, tzinfo=UTC))
        self.assertEqual(p["quality"], "STALE")

    def test_quality_uses_only_the_states_that_exist_today(self):
        """PARTIAL / INVALID / UNKNOWN are CLAUDE.md §20's work. Inventing them here would let a state exist
        that no schema accepts and no consumer understands."""
        self.assertEqual(set(N.QUALITY), {"AVAILABLE", "STALE", "MOCK", "UNAVAILABLE"})


class RealSeriesOnDisk(unittest.TestCase):
    def test_the_live_btc_series_carries_full_provenance(self):
        try:
            s = N.load("BTCUSDT", "15m")
        except FileNotFoundError:
            self.skipTest("no live BTCUSDT 15m series on disk")
        p = s["provenance"]
        self.assertEqual(p["provider"], "binance_public")
        self.assertEqual(p["market_type"], "SPOT")
        self.assertEqual(p["canonical_symbol"], "BTC/USDT")
        self.assertGreater(p["data_scope"]["bars"], 0)


class DataAndExecutionMarketTypes(unittest.TestCase):
    """The finding §7's provenance made visible: what we analyse is not what we trade."""

    def test_crypto_analyses_spot_and_executes_perpetual(self):
        m = P.data_execution_mismatch("crypto")
        self.assertIsNotNone(m, "the spot/perpetual mismatch stopped being reported")
        self.assertEqual(m["data_market_type"], ["SPOT"])
        self.assertEqual(m["execution_market_type"], ["PERPETUAL"])

    def test_the_cfd_markets_analyse_and_execute_the_same_thing(self):
        for market in ("cfd", "forex"):
            self.assertIsNone(P.data_execution_mismatch(market),
                              f"{market} unexpectedly reports a data/execution market-type mismatch")


if __name__ == "__main__":
    unittest.main()


class SnapToGrid(unittest.TestCase):
    """docs/audits/2026-09-18-e2e-drill.md §4.4: exporter clock jitter is not a market fact."""

    def test_one_second_either_side_snaps_and_on_grid_is_unchanged(self):
        self.assertEqual(N.snap_to_grid("2026-09-18T09:00:01Z", "1H"), "2026-09-18T09:00:00Z")
        self.assertEqual(N.snap_to_grid("2026-09-18T08:59:59Z", "1H"), "2026-09-18T09:00:00Z")
        self.assertEqual(N.snap_to_grid("2026-09-14T14:44:59Z", "15m"), "2026-09-14T14:45:00Z")
        self.assertEqual(N.snap_to_grid("2026-09-18T09:00:00Z", "1H"), "2026-09-18T09:00:00Z")

    def test_a_bar_genuinely_off_the_grid_is_left_alone(self):
        self.assertEqual(N.snap_to_grid("2026-09-11T07:37:29Z", "30m"), "2026-09-11T07:37:29Z")
        self.assertEqual(N.snap_to_grid("2026-09-18T09:00:03Z", "1H"), "2026-09-18T09:00:03Z")

    def test_series_is_copied_not_mutated(self):
        src = [{"time": "2026-09-18T09:00:01Z", "close": 1}]
        out = N.snap_series(src, "1H")
        self.assertEqual(out[0]["time"], "2026-09-18T09:00:00Z"); self.assertEqual(src[0]["time"], "2026-09-18T09:00:01Z")
