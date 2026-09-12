import importlib.util, json, os, subprocess, sys, tempfile, threading, time, unittest

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


sr = load("sr", os.path.join(ROOT, "scripts", "strategy-runner.py"))
bt = sr.bt


def synthetic(n=400, seed=7):
    import random
    rnd = random.Random(seed); px = 100.0; out = []
    for i in range(n):
        o = px; drift = rnd.uniform(-1, 1); c = o + drift; h = max(o, c) + rnd.uniform(0, 0.6); l = min(o, c) - rnd.uniform(0, 0.6)
        out.append(dict(time=f"2026-01-{1 + i // 48:02d}T{(i % 48) // 2:02d}:{(i % 2) * 30:02d}:00Z", open=o, high=h, low=l, close=c, volume=100 + rnd.uniform(0, 50)))
        px = c
    return out


class SetupsAreCausal(unittest.TestCase):
    def test_setup_fields_and_validity(self):
        c = synthetic()
        for method in ("ICT", "COMBINED"):
            for target in ("range", "std25"):
                for side in ("long", "short"):
                    for s in sr.setups(method, side, c, "30m", target):
                        n = len(c); K = bt.P["30m"]["K"]
                        self.assertGreaterEqual(s["mss_bar"], n - 1 - K)
                        self.assertGreater(s["r_planned"], 0)
                        if side == "long":
                            self.assertLess(s["stop"], s["entry"]); self.assertGreater(s["target"], s["entry"])
                        else:
                            self.assertGreater(s["stop"], s["entry"]); self.assertLess(s["target"], s["entry"])
                        for j in range(s["mss_bar"] + 1, n):
                            self.assertTrue(c[j]["low"] > s["entry"] if side == "long" else c[j]["high"] < s["entry"])

    def test_fvg_complete_by_mss_close(self):
        c = synthetic(); H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
        PH = bt.all_pivots(H, "high"); PL = bt.all_pivots(L, "low")
        for i in range(60, len(c) - 20):
            r = bt.find_ict("long", i, i, H, L, C, 14, len(c), PH, PL)
            if r:
                mss, edge, far = r
                self.assertTrue(any(H[k - 1] < L[k + 1] and L[k + 1] == edge for k in range(i + 1, mss)))

    def test_ict_target_restored_after_setups(self):
        before = bt.OPTS["ict_target"]; sr.setups("ICT", "long", synthetic(), "30m", "std4"); self.assertEqual(bt.OPTS["ict_target"], before)


class ParityWithBacktest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "history", "ohlcv.SOLUSDT.30m.json")), "history not fetched")
    def test_replay_matches_backtest_first_setup(self):
        st = sr.load_setups()[0]
        rep = sr.replay([st["id"]], bars=450)
        for r in rep:
            self.assertEqual(r["unmatched"], 0, r)


class Sizing(unittest.TestCase):
    def test_risk_never_above_one_percent_and_notional_capped(self):
        self.assertLessEqual(sr.RISK_PCT, 0.01)
        qty, risk = sr.size(10000, 100.0, 99.0, 1.0)
        self.assertAlmostEqual(risk, 10000 * sr.RISK_PCT)
        self.assertLessEqual(qty * 100.0, 10000 * sr.NOTIONAL_CAP_PCT * sr.LEVERAGE + 1e-9)
        qty2, _ = sr.size(10000, 100.0, 99.99, 1.0)
        self.assertAlmostEqual(qty2 * 100.0, 10000 * sr.NOTIONAL_CAP_PCT * sr.LEVERAGE)

    def test_mt5_lots_from_contract_data(self):
        sr._MT5_SYMBOLS["XAUUSD"] = dict(tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_max=1.0, volume_step=0.01, digits=2)
        lots, risk, per_lot = sr.mt5_lots("XAUUSD", 10000, 2000.0, 1990.0, 1.0)      # 10 $ stop = 1000 ticks x 1 $ = 1000 $/lot
        self.assertAlmostEqual(risk, 10000 * sr.RISK_PCT)
        self.assertLessEqual(lots * per_lot, risk + 1e-9)
        self.assertAlmostEqual(lots % 0.01, 0, places=6)


class Gate(unittest.TestCase):
    def _gate_with(self, cfg):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        old = sr.AUTOMATION_CONFIG; sr.AUTOMATION_CONFIG = tmp.name
        try:
            return sr.automation_gate()
        finally:
            sr.AUTOMATION_CONFIG = old; os.unlink(tmp.name)

    def base(self, **exe):
        return {"enabled": True, "layers": {"pilot": True}, "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}}, "execution": {"environment": "demo", "pilot_profile": "top5", **exe}}

    def test_refuses_real_environment(self):
        self.assertIn("REAL", self._gate_with(self.base(environment="real")) or "")

    def test_refuses_wrong_profile(self):
        self.assertIn("profile", self._gate_with(self.base(pilot_profile="legacy")) or "")

    def test_refuses_master_off(self):
        cfg = self.base(); cfg["enabled"] = False
        self.assertIn("OFF", self._gate_with(cfg) or "")


class Breakeven(unittest.TestCase):
    def test_dry_run_moves_stop_to_entry_once_plus_one_r_printed(self):
        pos = dict(side="LONG", strategy="x", tf="30m", method="ICT", execution="futures", mgmt="be", qty="1", entry=100.0, stop=99.0, tp=103.0, stop_order=None, tp_order=None,
                   opened_at="2026-01-01T00:00:00Z", bars=0, risk_usd=1.0, be=False, be_level=101.0, htf_pass=True)
        candles = [dict(time="2026-01-01T00:30:00Z", high=100.5, low=99.5, close=100.2), dict(time="2026-01-01T01:00:00Z", high=101.2, low=100.1, close=100.9)]
        old = sr.log; sr.log = lambda *a, **k: None
        try:
            rec = sr.manage_position("BTCUSDT", pos, candles, live=False, bars_elapsed=1)
        finally:
            sr.log = old
        self.assertIsNone(rec); self.assertTrue(pos["be"]); self.assertAlmostEqual(pos["stop"], 100.0)


class Due(unittest.TestCase):
    def test_timeframe_due_on_close_ticks(self):
        import datetime as dt
        t = lambda h, m: dt.datetime(2026, 1, 1, h, m, tzinfo=dt.timezone.utc)
        self.assertTrue(sr.due("30m", t(9, 31))); self.assertTrue(sr.due("1H", t(9, 1))); self.assertFalse(sr.due("1H", t(9, 31)))
        self.assertTrue(sr.due("2H", t(10, 1))); self.assertFalse(sr.due("2H", t(9, 1))); self.assertTrue(sr.due("4H", t(8, 1))); self.assertTrue(sr.due("1D", t(0, 1))); self.assertFalse(sr.due("1D", t(4, 1)))


class Mt5BridgeProtocol(unittest.TestCase):
    """scripts/mt5-order-bridge.py against a fake EA that answers command files the way OrderBridge.mq5 does."""
    def test_roundtrip_with_fake_ea(self):
        tmp = tempfile.mkdtemp(); bridge = os.path.join(tmp, "mt5-bridge", "bridge"); os.makedirs(bridge)
        stop = threading.Event()

        def fake_ea():
            while not stop.is_set():
                for f in os.listdir(bridge):
                    if f.startswith("cmd-") and f.endswith(".json"):
                        cmd = json.load(open(os.path.join(bridge, f)))
                        if cmd["action"] == "ping":
                            res = {"id": cmd["id"], "ok": True, "trade_mode": "demo"}
                        elif cmd["action"] == "symbol":
                            json.dump({"XAUUSD": {"tick_size": 0.01, "tick_value": 1.0, "volume_min": 0.01, "volume_max": 1.0, "volume_step": 0.01, "digits": 2}}, open(os.path.join(bridge, "symbols.json"), "w"))
                            res = {"id": cmd["id"], "ok": True}
                        elif cmd["action"] == "limit":
                            self.assertEqual(cmd["symbol"], "XAUUSD"); res = {"id": cmd["id"], "ok": True, "retcode": 10008, "ticket": 4242}
                        else:
                            res = {"id": cmd["id"], "ok": False, "comment": "unknown"}
                        json.dump(res, open(os.path.join(bridge, f"res-{cmd['id']}.json"), "w")); os.remove(os.path.join(bridge, f))
                time.sleep(0.05)
        th = threading.Thread(target=fake_ea, daemon=True); th.start()
        env = dict(os.environ, MT5_BRIDGE_TIMEOUT="5")
        script = open(os.path.join(ROOT, "scripts", "mt5-order-bridge.py")).read().replace('BRIDGE = os.path.join(ROOT, "data", "live", "mt5-bridge", "bridge")', f'BRIDGE = {bridge!r}')
        sp = os.path.join(tmp, "bridge.py"); open(sp, "w").write(script)
        try:
            out = json.loads(subprocess.run(["python3", sp, "check"], capture_output=True, text=True, env=env).stdout); self.assertTrue(out["demo"]); self.assertIn("XAUUSD", out["symbols"])
            out = json.loads(subprocess.run(["python3", sp, "limit", "XAUUSD", "buy", "0.05", "2400.00", "2390.00", "2425.00", "t5-test"], capture_output=True, text=True, env=env).stdout)
            self.assertTrue(out["ok"]); self.assertEqual(out["ticket"], 4242)
            r = subprocess.run(["python3", sp, "limit", "EURUSD", "buy", "0.05", "1", "0.9", "1.1"], capture_output=True, text=True, env=env); self.assertEqual(r.returncode, 2)
        finally:
            stop.set(); th.join(timeout=1)


class AutomationProfile(unittest.TestCase):
    def test_profiles_declared(self):
        au = load("au", os.path.join(ROOT, "scripts", "automation.py"))
        self.assertEqual(au.PILOT_PROFILES, ["legacy", "top5"]); self.assertEqual(au.DEFAULTS["execution"]["pilot_profile"], "top5")


if __name__ == "__main__":
    unittest.main()


class Aggregation(unittest.TestCase):
    def test_15m_to_30m_and_due_for_fast_timeframes(self):
        import datetime as dt
        c = [dict(time=f"2026-01-01T00:{m:02d}:00Z", open=1, high=2 + m, low=0.5, close=1.5, volume=1) for m in (0, 15, 30, 45)]
        agg = sr.aggregate_minutes(c, 30)
        self.assertEqual([x["time"] for x in agg], ["2026-01-01T00:00:00Z", "2026-01-01T00:30:00Z"]); self.assertEqual(agg[0]["high"], 17); self.assertEqual(agg[1]["volume"], 2)
        t = dt.datetime(2026, 1, 1, 9, 36, tzinfo=dt.timezone.utc)
        self.assertTrue(sr.due("5m", t)); self.assertTrue(sr.due("15m", t)); self.assertFalse(sr.due("1H", t))


class SetupSpec(unittest.TestCase):
    def test_bad_spec_is_usage_error_without_side_effects(self):
        au = load("au", os.path.join(ROOT, "scripts", "automation.py"))
        cfg = json.loads(json.dumps(au.DEFAULTS)); ns = type("A", (), {"setup": ["setup", "top", "99"], "who": None, "reason": None, "cmd": "on"})()
        rc, lines = au.apply_setup_spec(cfg, ns)
        self.assertEqual(rc, 1); self.assertEqual(cfg["history"], [])

    def test_plain_on_selects_per_horizon(self):
        """No spec = `setup horizons` (user decision 2026-09-11): rank-setups is called with --horizons --window 1y; a `top N` spec in force is kept."""
        from unittest import mock
        au = load("au", os.path.join(ROOT, "scripts", "automation.py"))
        cfg = json.loads(json.dumps(au.DEFAULTS)); calls = []
        def fake_run(args, **kw):
            calls.append(args); return type("R", (), {"returncode": 0, "stderr": ""})()
        with mock.patch.object(au.subprocess, "run", fake_run):
            rc, lines = au.apply_setup_spec(cfg, type("A", (), {"setup": [], "cmd": "on", "who": None, "reason": None})())
        self.assertEqual(rc, 0); self.assertIn("--horizons", calls[0]); self.assertIn("1y", calls[0]); self.assertEqual(cfg["execution"]["pilot_profile"], "top5")
        cfg["execution"]["setup_spec"] = "top 3 (1y)"; calls.clear()
        with mock.patch.object(au.subprocess, "run", fake_run):
            rc, lines = au.apply_setup_spec(cfg, type("A", (), {"setup": [], "cmd": "on", "who": None, "reason": None})())
        self.assertEqual(calls, []); self.assertEqual(rc, 0)
