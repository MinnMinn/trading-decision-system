"""scripts/import-ftmo-symbols.py -- the FTMO symbol-universe validator / registry-proposal generator
(docs/plans/2026-10-01-symbol-universe-design.md).

All data is a synthetic miniature written into temp dirs (no real history is read here, no network, no MT5).
The six-symbol fixture covers: a forex pair (complete), an index (complete, mapped through an existing
symbol-map entry), a crypto CFD (missing 1m), an energy (a long gap), a stock (unmapped class), and a plain
`US500` that collides with `US500.cash` on the canonical name.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_import_ftmo_symbols
"""
import contextlib
import datetime
import gzip
import importlib.util
import io
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


def _load():
    spec = importlib.util.spec_from_file_location("import_ftmo_symbols_mod",
                                                  os.path.join(ROOT, "scripts", "import-ftmo-symbols.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()

TFS = ("1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W")
STEP = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "4H": 14400, "1D": 86400, "1W": 604800}
T0 = datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def candles(tf, n=40, skip_after=None, skip_s=0, dup_at=None, back_at=None, bad_ohlc_at=None):
    out, t = [], T0
    for i in range(n):
        if skip_after is not None and i == skip_after:
            t += datetime.timedelta(seconds=skip_s)
        o = 100 + i * 0.1
        c = {"time": _iso(t), "open": o, "high": o + 0.5, "low": o - 0.5, "close": o + 0.1, "volume": 10}
        if bad_ohlc_at == i:
            c["high"] = o - 1.0           # high below low
        out.append(c)
        t += datetime.timedelta(seconds=STEP[tf])
    if dup_at is not None:
        out[dup_at]["time"] = out[dup_at - 1]["time"]
    if back_at is not None:
        out[back_at]["time"] = out[back_at - 3]["time"]
    return out


def write_series(root, sym, tf, cs, shape="file"):
    if shape == "file":
        with open(os.path.join(root, f"ohlcv.{sym}.{tf}.json"), "w", encoding="utf-8") as fh:
            json.dump({"symbol": sym, "timeframe": tf, "_source": "mt5_bridge_ftmo_history_utc", "candles": cs}, fh)
        return
    d = os.path.join(root, f"ohlcv.{sym}.{tf}")
    os.makedirs(d, exist_ok=True)
    years = sorted({c["time"][:4] for c in cs})
    for y in years:
        with gzip.open(os.path.join(d, f"{y}.json.gz"), "wt", encoding="utf-8") as fh:
            json.dump({"candles": [c for c in cs if c["time"][:4] == y]}, fh)
    with open(os.path.join(d, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"symbol": sym, "timeframe": tf, "_format": "split-gz-year-v1", "years": [int(y) for y in years],
                   "first": cs[0]["time"], "last": cs[-1]["time"], "_bars": len(cs)}, fh)


def write_spec(costs, raw, swap_mode=1, spread_bars=1000, currency_profit="USD", digits=2):
    with open(os.path.join(costs, f"symbolspec.{raw}.json"), "w", encoding="utf-8") as fh:
        json.dump({"symbol": raw, "_source": "mt5_symbol_spec", "digits": digits, "point": 10 ** -digits, "swap_mode": swap_mode,
                   "swap_long": -1.0, "swap_short": 0.5, "swap_rollover3days": 3, "currency_profit": currency_profit,
                   "commission": {"deals": 0, "lots": 0.0, "sum_account_ccy": 0.0, "status": "no_deals"},
                   "recorded_spread_m15": {"bars": spread_bars, "median_points": 10, "p90_points": 20,
                                           "by_utc_hour": [{"h": h, "n": 10, "median": 10, "p90": 20}
                                                           for h in range(24)]}}, fh)


def sym_entry(name, path, base, profit, digits=2, first=None, description=None):
    return {"name": name, "path": path, "description": description or name, "currency_base": base,
            "currency_profit": profit, "currency_margin": profit, "digits": digits, "point": 10 ** -digits,
            "contract_size": 1.0, "volume_min": 0.01, "volume_step": 0.01, "volume_max": 100.0,
            "trade_mode": 4, "trade_mode_name": "SYMBOL_TRADE_MODE_FULL", "calc_mode": 0, "swap_mode": 1,
            "swap_long": -1.0, "swap_short": 0.5, "spread_now_points": 12, "spread_float": True,
            "sessions_trade": [], "first_bar_server": first or {}, "server_first_date": "", "terminal_first_date": ""}


REGISTRY = {
    "_comment": "fixture", "_policy": "fixture",
    "market_types": {"_comment": "x", "CFD": {}},
    "canonical": {"_comment": "x", "BTCUSDT": "BTC/USDT", "XAUUSD": "XAU/USD", "US500": "US500/USD"},
    "markets": {"_comment": "x",
                "crypto": {"market_types": ["SPOT"], "data_dir": "market-data", "tick_volume": False,
                           "continuous": True, "default_enabled": True, "feed": "f"},
                "cfd": {"market_types": ["CFD"], "data_dir": "mt5-bridge", "tick_volume": True,
                        "continuous": False, "default_enabled": True, "feed": "f"}},
    "analysis": {"crypto": ["BTCUSDT"], "cfd": ["XAUUSD", "US500"]},
    "display": {"_comment": "x", "BTCUSDT": {"label": "BTC/USDT", "price_decimals": 0},
                "XAUUSD": {"id": "xau", "label": "XAU/USD", "asset_class": "metals"},
                "US500": {"id": "us500", "label": "S&P 500", "asset_class": "indices"}},
    "execution": {"crypto": ["BTCUSDT"], "cfd": ["XAUUSD", "US500"]},
    "backtested": {"_comment": "x", "crypto": ["BTCUSDT"], "cfd": ["XAUUSD"]},
    "history": [{"date": "2026-09-27", "change": "c", "reason": "r", "approved_by": "user"}],
    "estate_capacity": {"max_estate_notional_usd": {}},
}


class Fixture:
    """A temp workspace: history root, costs dir, registry + symbol-map + ExportSymbolList files, out dir."""

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="ifs-test-")
        self.hist = os.path.join(self.tmp, "hist"); os.makedirs(self.hist)
        self.costs = os.path.join(self.tmp, "costs"); os.makedirs(self.costs)
        self.out = os.path.join(self.tmp, "out")
        self.registry = os.path.join(self.tmp, "instruments.json")
        self.map = os.path.join(self.tmp, "symbol-map.json")
        self.list = os.path.join(self.tmp, "symbollist.json")
        with open(self.registry, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(REGISTRY, indent=2, ensure_ascii=False) + "\n")
        with open(self.map, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"_note": "n", "server": "FTMO-Demo",
                                 "map": {"XAUUSD": "XAUUSD", "US500.cash": "US500"}}, indent=2) + "\n")
        self.symbols = [
            sym_entry("EURUSD", "Forex\\EURUSD", "EUR", "USD", 5,
                      first={"1m": "2020-01-01T00:00:00", "5m": "2015-01-01T00:00:00"}),
            sym_entry("US500.cash", "Indices\\US500.cash", "USD", "USD"),
            sym_entry("BTCUSD", "Crypto\\BTCUSD", "BTC", "USD"),
            sym_entry("USOIL.cash", "Energies\\USOIL.cash", "USOIL", "USD"),
            sym_entry("AAPL", "Stocks\\US\\AAPL", "AAPL", "USD"),
            sym_entry("US500", "Indices\\US500", "USD", "USD"),     # collides with US500.cash on "US500"
        ]

    def write_list(self, symbols=None, server="FTMO-Demo"):
        with open(self.list, "w", encoding="utf-8") as fh:
            json.dump({"_source": "mt5_symbol_list", "_server": server, "_exported_at_utc": "2026.10.02 10:00:00",
                       "_server_utc_offset_sec_now": 10800, "symbols": symbols or self.symbols}, fh)

    def series(self, sym, tfs=TFS, shape="file", **kw):
        for tf in tfs:
            write_series(self.hist, sym, tf, candles(tf, **kw.get(tf, {})), shape=shape)

    def argv(self, *extra, with_list=True):
        a = ["--history-root", self.hist, "--costs-dir", self.costs, "--registry", self.registry,
             "--symbol-map", self.map, "--out", self.out]
        if with_list:
            a += ["--symbol-list", self.list]
        return a + list(extra)

    def run(self, *extra, with_list=True):
        buf, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
            rc = M.main(self.argv(*extra, with_list=with_list))
        return rc, buf.getvalue() + err.getvalue()

    def report(self):
        with open(os.path.join(self.out, "report.json"), encoding="utf-8") as fh:
            return json.load(fh)

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


def by_raw(report):
    return {s["raw"]: s for s in report["symbols"]}


def codes(sym, severity=None):
    return {i["code"] for i in sym["issues"] if severity is None or i["severity"] == severity}


class MiniUniverse(unittest.TestCase):
    """The six-symbol fixture, run end to end."""

    @classmethod
    def setUpClass(cls):
        f = cls.f = Fixture()
        f.write_list()
        f.series("EURUSD", shape="split")
        write_spec(f.costs, "EURUSD", digits=5)
        # US500.cash: complete, plain files
        f.series("US500")
        write_spec(f.costs, "US500.cash")
        # BTCUSD: no 1m (the decision timeframe the fund search needs most)
        f.series("BTCUSD", tfs=[t for t in TFS if t != "1m"])
        write_spec(f.costs, "BTCUSD")
        # USOIL: a 10-day hole inside the 15m series
        f.series("USOIL", **{"15m": dict(skip_after=20, skip_s=10 * 86400)})
        write_spec(f.costs, "USOIL.cash")
        cls.rc, cls.out = f.run()
        cls.rep = f.report()
        cls.s = by_raw(cls.rep)

    @classmethod
    def tearDownClass(cls):
        cls.f.close()

    def test_asset_class_derived_from_symbol_path(self):
        self.assertEqual(self.s["EURUSD"]["asset_class"], "fx")
        self.assertEqual(self.s["US500.cash"]["asset_class"], "indices")
        self.assertEqual(self.s["BTCUSD"]["asset_class"], "crypto")
        self.assertEqual(self.s["USOIL.cash"]["asset_class"], "energies")
        self.assertEqual(self.s["AAPL"]["asset_class"], "other")

    def test_unmapped_class_is_listed_clearly_and_excluded(self):
        un = self.rep["unmapped_classes"]
        self.assertEqual([u["path_head"] for u in un], ["Stocks"])
        self.assertEqual(un[0]["count"], 1)
        self.assertIn("AAPL", un[0]["symbols"])
        self.assertEqual(self.s["AAPL"]["status"], "excluded_unmapped_class")
        self.assertNotIn("AAPL", json.dumps(self.rep["proposals"]))

    def test_canonical_names_follow_the_existing_convention(self):
        self.assertEqual(self.s["EURUSD"]["canonical"], "EURUSD")
        self.assertEqual(self.s["EURUSD"]["mapping_source"], "identity")
        self.assertEqual(self.s["BTCUSD"]["canonical"], "BTCUSD")
        self.assertEqual(self.s["USOIL.cash"]["canonical"], "USOIL")
        self.assertEqual(self.s["USOIL.cash"]["mapping_source"], "strip_cash")

    def test_name_collision_fails_loud_and_blocks_both(self):
        self.assertEqual(self.rc, 1, self.out)
        for raw in ("US500.cash", "US500"):
            self.assertIn("name_collision", codes(self.s[raw], "ERROR"), raw)
        self.assertEqual(self.s["US500.cash"]["status"], "error")
        self.assertEqual(self.rep["collisions"][0]["canonical"], "US500")
        self.assertEqual(sorted(self.rep["collisions"][0]["raw_names"]), ["US500", "US500.cash"])
        prop = json.dumps(self.rep["proposals"])
        self.assertNotIn('"US500"', prop)       # neither colliding symbol is proposed

    def test_missing_1m_is_flagged_with_the_timeframe_named(self):
        b = self.s["BTCUSD"]
        self.assertEqual(b["timeframes_missing"], ["1m"])
        self.assertFalse(b["decision_ready"])
        self.assertIn("decision_timeframe_missing", codes(b, "ERROR"))
        self.assertEqual(b["status"], "history_incomplete")

    def test_gap_detected_and_reported_as_warning_not_error(self):
        o = self.s["USOIL.cash"]
        g = o["timeframes"]["15m"]["gaps"]
        self.assertEqual(g["long"], 1)
        self.assertGreaterEqual(g["max_seconds"], 10 * 86400)
        self.assertIn("long_gap", codes(o, "WARN"))
        self.assertNotIn("long_gap", codes(o, "ERROR"))
        self.assertEqual(o["timeframes"]["15m"]["integrity"], "VALID_WITH_GAPS")
        self.assertEqual(o["timeframes"]["5m"]["integrity"], "VALID")

    def test_complete_symbol_is_ready_and_split_shape_is_read(self):
        e = self.s["EURUSD"]
        self.assertEqual(e["status"], "ready", e["issues"])
        self.assertTrue(e["decision_ready"] and e["context_complete"])
        self.assertEqual(e["timeframes"]["1m"]["shape"], "split")
        self.assertEqual(e["timeframes"]["1m"]["bars"], 40)
        self.assertEqual(e["timeframes"]["1m"]["first"], "2024-01-01T00:00:00Z")
        self.assertEqual(e["timeframes"]["1m"]["last"], "2024-01-01T00:39:00Z")
        self.assertTrue(e["spec"]["present"])
        self.assertEqual(e["spec"]["swap_mode"], 1)

    def test_listed_first_bar_is_compared_to_what_was_exported(self):
        e = self.s["EURUSD"]
        self.assertIn("history_shallower_than_available", codes(e, "INFO"))

    def test_export_batches_list_raw_names_of_clean_symbols_only(self):
        txt = open(os.path.join(self.f.out, "export-batches.txt"), encoding="utf-8").read()
        self.assertIn("EURUSD", txt)
        self.assertIn("USOIL.cash", txt)
        self.assertIn("BTCUSD", txt)
        self.assertNotIn("AAPL", txt)                       # unmapped class
        self.assertNotIn("US500", txt.replace("US500.cash", ""))   # a colliding name is never exported
        self.f.run("--batch-size", "2")
        lines = [l for l in open(os.path.join(self.f.out, "export-batches.txt"), encoding="utf-8")
                 if l.startswith("batch-")]
        self.assertTrue(all(len(l.split(": ", 1)[1].strip().split(",")) <= 2 for l in lines))

    def test_outputs_land_outside_repo_and_are_complete(self):
        for name in ("report.md", "report.json", "registry.patch.json", "symbol-map.patch.json",
                     "registry.diff", "symbol-map.diff", "export-batches.txt"):
            self.assertTrue(os.path.exists(os.path.join(self.f.out, name)), name)
        md = open(os.path.join(self.f.out, "report.md"), encoding="utf-8").read()
        self.assertIn("Binance", md)            # the not-equivalent disclosure is part of every report
        self.assertIn("name_collision", md)


class ProposalShape(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        f = self.f
        f.write_list([sym_entry("EURUSD", "Forex\\EURUSD", "EUR", "USD", 5),
                      sym_entry("US100.cash", "Indices\\US100.cash", "USD", "USD"),
                      sym_entry("BTCUSD", "Crypto\\BTCUSD", "BTC", "USD"),
                      sym_entry("XAUUSD", "Metals\\XAUUSD", "XAU", "USD")])
        self.rc, self.out = f.run()
        self.rep = f.report()

    def tearDown(self):
        self.f.close()

    def _ops(self, name):
        with open(os.path.join(self.f.out, name), encoding="utf-8") as fh:
            return json.load(fh)

    def test_clean_run_exits_zero_before_any_history_exists(self):
        self.assertEqual(self.rc, 0, self.out)
        st = {s["raw"]: s["status"] for s in self.rep["symbols"]}
        self.assertEqual(st["EURUSD"], "listed_only")

    def test_us100_cash_maps_to_ustec(self):
        s = by_raw(self.rep)["US100.cash"]
        self.assertEqual(s["canonical"], "USTEC")
        self.assertEqual(s["mapping_source"], "alias")

    def test_registry_patch_adds_canonical_display_analysis_only(self):
        ops = self._ops("registry.patch.json")
        paths = [o["path"] for o in ops if o["op"] == "add"]
        self.assertIn("/canonical/EURUSD", paths)
        self.assertIn("/display/EURUSD", paths)
        self.assertIn("/analysis/cfd/-", paths)
        self.assertNotIn("/canonical/XAUUSD", paths)       # already in the registry -> never re-added
        for forbidden in ("/execution", "/backtested", "/estate_capacity"):
            self.assertFalse([p for p in paths if p.startswith(forbidden)], forbidden)
        disp = next(o["value"] for o in ops if o["path"] == "/display/EURUSD")
        self.assertEqual(disp["asset_class"], "fx")
        self.assertEqual(disp["price_decimals"], 5)
        canon = next(o["value"] for o in ops if o["path"] == "/canonical/EURUSD")
        self.assertEqual(canon, "EUR/USD")
        self.assertEqual(next(o["value"] for o in ops if o["path"] == "/canonical/USTEC"), "USTEC/USD")
        self.assertEqual(next(o["value"] for o in ops if o["path"] == "/display/BTCUSD")["asset_class"], "crypto")

    def test_symbol_map_patch_adds_only_new_raw_names(self):
        ops = self._ops("symbol-map.patch.json")
        added = {o["path"]: o["value"] for o in ops if o["op"] == "add"}
        self.assertEqual(added["/map/US100.cash"], "USTEC")
        self.assertEqual(added["/map/EURUSD"], "EURUSD")
        self.assertNotIn("/map/XAUUSD", added)

    def test_analysis_side_effects_are_disclosed_in_the_report_and_on_apply(self):
        md = open(os.path.join(self.f.out, "report.md"), encoding="utf-8").read()
        self.assertIn("Side effects of adding to analysis.cfd", md)
        self.assertIn("prop-search", md)
        self.assertTrue(self.rep["proposals"]["side_effects"])
        rc, out = self.f.run("--apply")
        self.assertIn("side effect:", out)

    def test_apply_is_off_by_default_and_leaves_files_untouched(self):
        before = open(self.f.registry, "rb").read(), open(self.f.map, "rb").read()
        self.f.run()
        self.assertEqual(before, (open(self.f.registry, "rb").read(), open(self.f.map, "rb").read()))

    def test_apply_writes_both_files_with_backup(self):
        before_reg = open(self.f.registry, "rb").read()
        rc, out = self.f.run("--apply")
        self.assertEqual(rc, 0, out)
        reg = json.load(open(self.f.registry, encoding="utf-8"))
        mp = json.load(open(self.f.map, encoding="utf-8"))
        for sym in ("EURUSD", "USTEC", "BTCUSD"):
            self.assertIn(sym, reg["canonical"]); self.assertIn(sym, reg["display"])
            self.assertIn(sym, reg["analysis"]["cfd"])
        self.assertEqual(reg["execution"], REGISTRY["execution"])        # never widened
        self.assertEqual(reg["backtested"], REGISTRY["backtested"])
        self.assertIn("FTMO symbol universe", reg["history"][0]["change"])
        self.assertEqual(len(reg["history"]), len(REGISTRY["history"]) + 1)
        self.assertEqual(mp["map"]["US100.cash"], "USTEC")
        self.assertEqual(mp["_note"], "n")                               # untouched fields preserved
        backups = os.listdir(os.path.join(self.f.out, "backup"))
        self.assertTrue(any(b.startswith("instruments.json") for b in backups), backups)
        bak = [b for b in backups if b.startswith("instruments.json")][0]
        self.assertEqual(open(os.path.join(self.f.out, "backup", bak), "rb").read(), before_reg)
        # idempotent: a second run proposes nothing new
        rc2, _ = self.f.run()
        self.assertEqual(rc2, 0)
        self.assertEqual([o for o in self._ops("registry.patch.json") if o["path"].startswith("/canonical")], [])

    def test_apply_refuses_while_any_error_exists(self):
        self.f.write_list([sym_entry("US500.cash", "Indices\\US500.cash", "USD", "USD"),
                           sym_entry("US500", "Indices\\US500", "USD", "USD")])
        before = open(self.f.registry, "rb").read()
        rc, out = self.f.run("--apply")
        self.assertEqual(rc, 1)
        self.assertEqual(before, open(self.f.registry, "rb").read())
        self.assertIn("refus", out.lower())

    def test_patched_registry_still_loads_in_the_real_instruments_loader(self):
        """Apply onto a copy of the REAL registry and import it with the real scripts/instruments.py, which
        raises on any structural violation (execution subset of analysis, unique canonical ids ...)."""
        tmp = tempfile.mkdtemp(prefix="ifs-real-")
        try:
            os.makedirs(os.path.join(tmp, "scripts")); os.makedirs(os.path.join(tmp, "docs", "architecture"))
            shutil.copy(os.path.join(ROOT, "scripts", "instruments.py"), os.path.join(tmp, "scripts"))
            real = os.path.join(ROOT, "docs", "architecture", "instruments.json")
            shutil.copy(real, os.path.join(tmp, "docs", "architecture", "instruments.json"))
            fx = Fixture()
            try:
                fx.write_list([sym_entry("EURUSD", "Forex\\EURUSD", "EUR", "USD", 5),
                               sym_entry("BTCUSD", "Crypto\\BTCUSD", "BTC", "USD"),
                               sym_entry("USOIL.cash", "Energies\\USOIL.cash", "USOIL", "USD")])
                argv = fx.argv("--apply") ; argv[argv.index("--registry") + 1] = os.path.join(tmp, "docs", "architecture", "instruments.json")
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(M.main(argv), 0)
            finally:
                fx.close()
            code = ("import sys; sys.path.insert(0, 'scripts'); import instruments as I; "
                    "assert 'EURUSD' in I.analysis('cfd'); assert 'BTCUSD' in I.analysis('cfd'); "
                    "assert I.display('BTCUSD')['asset_class']=='crypto'; "
                    "assert I.canonical('EURUSD')=='EUR/USD'; "
                    "assert 'EURUSD' not in I.execution('cfd'); assert 'EURUSD' not in I.backtested('cfd'); "
                    "assert I.market_of('USOIL')=='cfd'; print('ok')")
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), "ok", r.stdout + r.stderr)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class MappingRules(unittest.TestCase):
    def test_precedence_override_then_map_then_alias_then_strip(self):
        em = {"GER40.cash": "DE40"}
        self.assertEqual(M.derive_canonical("GER40.cash", em, {}), ("DE40", "existing_map"))
        self.assertEqual(M.derive_canonical("GER40.cash", {}, {}), ("DE40", "alias"))
        self.assertEqual(M.derive_canonical("US100.cash", {}, {}), ("USTEC", "alias"))
        self.assertEqual(M.derive_canonical("FRA40.cash", {}, {}), ("FRA40", "strip_cash"))
        self.assertEqual(M.derive_canonical("EURUSD", {}, {}), ("EURUSD", "identity"))
        self.assertEqual(M.derive_canonical("JP225.cash", {}, {"JP225.cash": "JPN225"}), ("JPN225", "override"))

    def test_bad_canonical_names_are_refused_not_sanitised(self):
        f = Fixture()
        try:
            f.write_list([sym_entry("EURUSD.r", "Forex\\EURUSD.r", "EUR", "USD", 5)])
            rc, out = f.run()
            self.assertEqual(rc, 1)
            s = by_raw(f.report())["EURUSD.r"]
            self.assertIn("bad_canonical_name", codes(s, "ERROR"))
            self.assertEqual(f.report()["proposals"]["registry_ops"], [])
        finally:
            f.close()

    def test_class_alias_flag_maps_a_non_default_path_head(self):
        f = Fixture()
        try:
            f.write_list([sym_entry("EURUSD", "Forex Majors\\EURUSD", "EUR", "USD", 5)])
            f.run()
            self.assertEqual(by_raw(f.report())["EURUSD"]["asset_class"], "other")
            f.run("--class-alias", "Forex Majors=fx")
            self.assertEqual(by_raw(f.report())["EURUSD"]["asset_class"], "fx")
        finally:
            f.close()

    def test_crypto_cfd_cannot_take_a_binance_registry_name(self):
        f = Fixture()
        try:
            f.write_list([sym_entry("BTCUSDT", "Crypto\\BTCUSDT", "BTC", "USDT")])
            rc, out = f.run()
            self.assertEqual(rc, 1, out)
            self.assertIn("registry_other_market", codes(by_raw(f.report())["BTCUSDT"], "ERROR"))
        finally:
            f.close()


class DataIntegrity(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        self.f.write_list([sym_entry("EURUSD", "Forex\\EURUSD", "EUR", "USD", 5)])
        write_spec(self.f.costs, "EURUSD", digits=5)

    def tearDown(self):
        self.f.close()

    def _run_with(self, tf, **kw):
        f = self.f
        f.series("EURUSD", **{tf: kw})
        rc, out = f.run()
        return rc, by_raw(f.report())["EURUSD"]

    def test_duplicate_timestamp_is_invalid(self):
        rc, s = self._run_with("5m", dup_at=7)
        self.assertEqual(rc, 1)
        self.assertEqual(s["timeframes"]["5m"]["integrity"], "INVALID")
        self.assertEqual(s["timeframes"]["5m"]["duplicates"], 1)
        self.assertIn("series_invalid", codes(s, "ERROR"))

    def test_non_monotone_is_invalid(self):
        rc, s = self._run_with("1m", back_at=9)
        self.assertEqual(rc, 1)
        self.assertGreaterEqual(s["timeframes"]["1m"]["non_monotone"], 1)
        self.assertEqual(s["timeframes"]["1m"]["integrity"], "INVALID")

    def test_broken_ohlc_is_invalid(self):
        rc, s = self._run_with("15m", bad_ohlc_at=3)
        self.assertEqual(rc, 1)
        self.assertEqual(s["timeframes"]["15m"]["integrity"], "INVALID")
        self.assertIn("high", s["timeframes"]["15m"]["fault"])

    def test_series_exactly_at_the_export_cap_is_flagged_as_probably_truncated(self):
        self.f.series("EURUSD")
        with mock.patch.object(M, "EXPORT_BAR_CAP", 40):       # the fixture's series hold exactly 40 bars
            rc, out = self.f.run()
        self.assertIn("bars_hit_export_cap", codes(by_raw(self.f.report())["EURUSD"], "WARN"))
        self.assertEqual(rc, 0)                                # a warning, not an error

    def test_clean_series_has_no_issue(self):
        self.f.series("EURUSD")
        rc, out = self.f.run()
        self.assertEqual(rc, 0, out)
        s = by_raw(self.f.report())["EURUSD"]
        self.assertEqual(s["status"], "ready")
        self.assertEqual([i for i in s["issues"] if i["severity"] in ("ERROR", "WARN")], [])

    def test_split_index_that_lies_about_its_bar_count_is_flagged(self):
        self.f.series("EURUSD", shape="split")
        p = os.path.join(self.f.hist, "ohlcv.EURUSD.1m", "index.json")
        idx = json.load(open(p)); idx["_bars"] = 999; json.dump(idx, open(p, "w"))
        rc, out = self.f.run()
        self.assertIn("index_mismatch", codes(by_raw(self.f.report())["EURUSD"], "WARN"))

    def test_spec_missing_and_unsupported_swap_mode_are_errors_when_history_exists(self):
        self.f.series("EURUSD")
        os.remove(os.path.join(self.f.costs, "symbolspec.EURUSD.json"))
        rc, _ = self.f.run()
        s = by_raw(self.f.report())["EURUSD"]
        self.assertEqual(rc, 1)
        self.assertIn("spec_missing", codes(s, "ERROR"))
        self.assertFalse(s["spec"]["present"])
        write_spec(self.f.costs, "EURUSD", swap_mode=2, digits=5)
        rc, _ = self.f.run()
        self.assertIn("spec_swap_mode_unsupported", codes(by_raw(self.f.report())["EURUSD"], "ERROR"))
        write_spec(self.f.costs, "EURUSD", spread_bars=0, digits=5)
        rc, _ = self.f.run()
        self.assertIn("spec_no_recorded_spread", codes(by_raw(self.f.report())["EURUSD"], "ERROR"))

    def test_require_history_turns_a_listed_only_symbol_into_an_error(self):
        f = self.f
        rc, _ = f.run()
        self.assertEqual(rc, 0)
        self.assertEqual(by_raw(f.report())["EURUSD"]["status"], "spec_only")
        rc, _ = f.run("--require-history")
        self.assertEqual(rc, 1)


class ListlessMode(unittest.TestCase):
    """No ExportSymbolList: the symbol set comes from symbol-map.json + the spec files, the class from the registry."""

    def test_existing_universe_reproduces_the_known_mapping(self):
        f = Fixture()
        try:
            with open(f.map, "w", encoding="utf-8") as fh:
                json.dump({"map": {"XAUUSD": "XAUUSD", "US500.cash": "US500"}}, fh)
            f.series("XAUUSD"); write_spec(f.costs, "XAUUSD")
            f.series("US500"); write_spec(f.costs, "US500.cash")
            rc, out = f.run(with_list=False)
            self.assertEqual(rc, 0, out)
            s = by_raw(f.report())
            self.assertEqual(s["US500.cash"]["canonical"], "US500")
            self.assertEqual(s["US500.cash"]["mapping_source"], "existing_map")
            self.assertEqual(s["US500.cash"]["asset_class"], "indices")     # from the registry's display
            self.assertEqual(s["XAUUSD"]["asset_class"], "metals")
            self.assertEqual({v["status"] for v in s.values()}, {"ready"})
            self.assertEqual(f.report()["proposals"]["registry_ops"], [])
            self.assertEqual(f.report()["proposals"]["symbol_map_ops"], [])
        finally:
            f.close()


class DefaultOutside(unittest.TestCase):
    def test_default_out_dir_is_outside_the_git_tree(self):
        d = M.default_out_dir()
        self.assertFalse(os.path.abspath(d).startswith(ROOT + os.sep), d)


if __name__ == "__main__":
    unittest.main()
