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


def _load_git_revision(ref, name):
    """Loads scripts/`name` as it existed at git ref `ref`, with __file__ pinned to the file's CURRENT path so
    ROOT-relative reads inside the module resolve against the real repo. Used to derive a "before" expectation
    from a prior revision's ACTUAL behaviour, not from reading today's source or re-typing the legacy algorithm
    by hand (mirrors scripts/tests/test_live_rules.py's load_git_revision)."""
    real_path = os.path.join(ROOT, "scripts", name)
    src = subprocess.check_output(["git", "show", f"{ref}:scripts/{name}"], cwd=ROOT, text=True)
    mod_name = f"{name.replace('-', '_').replace('.py', '')}_{ref}"
    spec = importlib.util.spec_from_loader(mod_name, loader=None, origin=real_path)
    m = importlib.util.module_from_spec(spec)
    m.__file__ = real_path
    exec(compile(src, real_path, "exec"), m.__dict__)
    return m


class IctParityAchieved(unittest.TestCase):
    """Task 8 (2026-09-13) migrated strategy-runner.setups()'s ICT path off the legacy bt.all_pivots/bt.find_ict/
    bt.ict_target proxies and onto scripts/live_rules.py -- the SAME read_at/setup_candidate/bias_allows/
    fvg_fill chain bt.ict_setups_live uses for bt.scan()'s ICT branch -- so the runner and the backtest now ask
    the live scanner the SAME question about the SAME bars. This replaces IctParityIsKnownBroken (see git
    history at commit febd2d6), which pinned the PRE-migration divergence and predicted its own class would
    need rewriting once the migration landed -- this is that rewrite; it must stay green from here on, not just
    once."""

    WINDOW = 3000

    def setUp(self):
        self.full = json.load(open(os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.15m.json")))["candles"][-self.WINDOW:]

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.15m.json")), "history not fetched")
    def test_runner_and_backtest_compute_the_same_entry_stop_target_for_every_ict_trade(self):
        """For every trade bt.scan's ICT branch records, calling the SAME live_rules.read_at() / setup_candidate()
        the runner's ict_live_setups() calls, at the trade's own bar, reproduces the exact entry/stop/target --
        proof the runner and the backtest ask the live scanner the same question, not two different ones that
        happen to agree by coincidence. Also logs the legacy (pre-Task-8) runner's own ICT setup count on this
        same window, loaded from git so the "before" number is the legacy algorithm's ACTUAL behaviour, not a
        restated claim."""
        saved_load = bt.load
        bt.load = lambda sym, tf: (self.full, "test")
        try:
            res = bt.scan("BTCUSDT", "15m", only=("ICT",))
        finally:
            bt.load = saved_load
        trades = res["trades"]["ICT"]
        self.assertGreater(len(trades), 0, "no ICT trades in this window -- cannot prove agreement on nothing")
        Tm = [x["time"] for x in self.full]
        idx_of_time = {tt: j for j, tt in enumerate(Tm)}
        methods = bt.resolve_methods("BTCUSDT")

        # BEFORE: reproduce IctParityIsKnownBroken's own comparison (commit febd2d6, which still has
        # OPTS["rules"]/the legacy pure-ICT branch this task deletes) -- bt.scan's live vs legacy ICT trade
        # counts on this exact window, i.e. the actual divergence that test class pinned, not a restated claim.
        old_bt = _load_git_revision("febd2d6", "backtest-methods.py")
        old_bt.load = lambda sym, tf: (self.full, "test")
        before = {}
        for rules in ("live", "legacy"):
            old_bt.OPTS["rules"] = rules
            before[rules] = len(old_bt.scan("BTCUSDT", "15m", only=("ICT",))["trades"].get("ICT", []))
        # Also the OLD runner's OWN ICT setups() (the legacy bt.all_pivots/bt.find_ict proxy this task migrates
        # off of) on the SAME window, for the "still working as of the last closed bar" category the NEW
        # runner's setups() also reports in AFTER below.
        old_sr = _load_git_revision("febd2d6", "strategy-runner.py")
        old_runner_pending = sum(len(old_sr.setups("ICT", side, self.full, "15m")) for side in ("long", "short"))
        new_runner_pending = sum(len(sr.setups("ICT", side, self.full, "15m", sym="BTCUSDT")) for side in ("long", "short"))

        matched = 0
        with open("/tmp/task8-ict-agree.txt", "w") as f:
            f.write("BTCUSDT 15m, 3000-bar window\n")
            f.write(f"BEFORE (commit febd2d6, bt.scan --rules live vs legacy, the divergence "
                    f"IctParityIsKnownBroken pinned): live={before['live']} legacy={before['legacy']} "
                    f"(the docs/backtests/2026-09-13-live-rules-vs-legacy.md evidence gate this task was "
                    f"conditioned on)\n")
            f.write(f"BEFORE (commit febd2d6, OLD runner setups(), legacy bt.all_pivots/bt.find_ict proxy): "
                    f"still-working-at-window-end setups = {old_runner_pending}\n")
            f.write(f"AFTER  (this commit, live_rules-based both sides): backtest bt.scan ICT trades = "
                    f"{len(trades)}; NEW runner still-working-at-window-end setups = {new_runner_pending}\n")
            f.write("(a backtest trade is a COMPLETED fill; a runner setup is a STILL-WORKING, not-yet-filled "
                    "limit -- the two counts are different categories by design, see ict_live_setups' docstring, "
                    "so the real agreement check below is entry/stop/target equality on the shared detection "
                    "call the runner and the backtest both now make, not a raw count match.)\n")
            for t in trades:
                i = idx_of_time[t["time"]]
                a = bt.lr.read_at(self.full, i, "15m", methods)
                su = bt.lr.ict_scan.setup_candidate(a, bt.lr.window(self.full, i, "15m"), bt.lr.setup_lookback("15m"))
                ok = (su is not None and su.get("complete") and su.get("pd_ok")
                      and abs(su["entry"] - t["entry"]) < 1e-9 and abs(su["stop"] - t["stop"]) < 1e-9
                      and abs(su["target"] - t["target"]) < 1e-9)
                matched += ok
                f.write(f"  {t['side']} {t['time']} entry={t['entry']} stop={t['stop']} target={t['target']} "
                        f"-- runner's own setup_candidate call agrees: {ok}\n")
                self.assertTrue(ok, f"runner's setup_candidate call disagrees with the backtest trade at {t['time']}: {su}")
            f.write(f"matched: {matched}/{len(trades)}\n")

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "history", "ohlcv.BTCUSDT.15m.json")), "history not fetched")
    def test_runner_setups_never_resignals_an_already_filled_or_expired_ict_setup(self):
        """Once a setup's LIMIT has filled or its K-bar expiry has passed, the runner must not offer it again as
        a NEW order: every signal setups("ICT", ...) still returns must be unexpired (bars_left >= 0)."""
        for side in ("long", "short"):
            for sig in sr.setups("ICT", side, self.full, "15m", sym="BTCUSDT"):
                self.assertGreaterEqual(sig["bars_left"], 0)

    def test_pilot_selection_still_contains_ict_setups(self):
        """The reason parity matters: these are the setups that would trade if the locks were lifted."""
        setups = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-top5.json")))["setups"]
        self.assertTrue([s for s in setups if s.get("method") == "ICT"])


class HtfGateFailsClosed(unittest.TestCase):
    """2026-09-13, Task 8 fix round 1: a setup that declares htf:true is asking for a higher-timeframe gate.
    Before this fix, tick() only blocked on an explicit `sig["htf_pass"] is False`; once htf_pass() started
    reading the live rules (this task), it can also return None for reasons that have NOTHING to do with the
    actual bias -- no candles fetched, htf_tf not in bt.P, or automation.SCAN_WINDOW has no entry for htf_tf
    (the 2H/30m gap) -- and every one of those sailed through as if the gate had opened. This is a fail-OPEN
    order gate; every other gate this task touched fails closed on missing data. These tests assert on the
    DECISION (was place_limit/place_market ever called), not on htf_pass's return value, per the coordinator's
    review."""

    ONE_SIG = dict(time="2026-01-01T00:00:00Z", mss_time="2026-01-01T00:00:00Z", entry=100.0, stop=99.0,
                   target=102.0, bars_left=5, r_planned=2.0, vol_type=None)

    def _run(self, htf_pass_return):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"], "dimensions": {"wyckoff": True, "ict": True}},
                           "cfd": {"enabled": False, "instruments": []}},
               "execution": {"environment": "demo", "pilot_profile": "top5"}}
        selection = {"setups": [dict(id="test-ict-htf", market="crypto", symbols=["BTCUSDT"], tf="15m",
                                      method="ICT", ict_target="range", htf=True, mgmt="be", execution="futures")]}
        state = {}
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(selection, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()

        saved = dict(AUTOMATION_CONFIG=sr.AUTOMATION_CONFIG, SELECTION=sr.SELECTION, STATE=sr.STATE,
                     fetch_candles=sr.fetch_candles, log=sr.log, setups=sr.setups, htf_pass=sr.htf_pass,
                     place_limit=sr.place_limit, place_market=sr.place_market, event_blackout=sr.event_blackout)
        placed = []
        candles80 = [dict(time=f"2026-01-01T{(m // 60) % 24:02d}:{m % 60:02d}:00Z", open=100, high=101, low=99, close=100, volume=1) for m in range(0, 80 * 15, 15)]
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
        sr.fetch_candles = lambda *a, **k: list(candles80)
        sr.log = lambda *a, **k: None
        sr.event_blackout = lambda *a, **k: None
        sr.setups = lambda method, side, c, tf, *a, **k: ([dict(self.ONE_SIG, side=side)] if side == "long" else [])
        sr.htf_pass = lambda *a, **k: htf_pass_return
        sr.place_limit = lambda sym, st, sig, equity, risk_mult, live: (placed.append((sym, sig)), None)[1]
        sr.place_market = lambda *a, **k: (placed.append(("market",)), None)[1]
        try:
            sr.tick(live=False, tick_time=sr.parse_t("2026-01-02T00:01:00Z"), ignore_gate=True)
        finally:
            for k, v in saved.items():
                setattr(sr, k, v)
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
        return placed

    def test_htf_pass_none_must_not_place_an_order(self):
        """The regression: htf_pass() unable to judge (None) used to sail through as permission."""
        self.assertEqual(self._run(None), [], "htf_pass()=None must refuse a setup that declared htf:true")

    def test_htf_pass_false_must_not_place_an_order(self):
        """The pre-existing, always-worked case: an explicit refusal still blocks."""
        self.assertEqual(self._run(False), [])

    def test_htf_pass_true_still_places_an_order(self):
        """The fix must not just block everything: an explicit agreement still permits."""
        placed = self._run(True)
        self.assertEqual(len(placed), 1, "htf_pass()=True must still let a setup that declared htf:true place")

    def test_before_after_decision_for_the_real_pilot_setup_hitting_this_gap(self):
        """crypto-scalping-wyckoff-5m-border-c (WYCKOFF, 5m, htf:true) is the setup concern 2 named:
        HTF_OF["5m"] == "30m", which automation.SCAN_WINDOW has no entry for, so its htf_pass is structurally
        None on every tick, forever (not a transient data gap). Writes the OLD vs NEW block decision for it."""
        setups = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-top5.json")))["setups"]
        st = next(s for s in setups if s["id"] == "crypto-scalping-wyckoff-5m-border-c")
        self.assertTrue(st.get("htf"))
        htf_tf = sr.HTF_OF[st["tf"]]
        self.assertIsNone(sr.ict_scan_bars(htf_tf), f"expected {htf_tf} to be the unscannable gap this test documents")
        htf_pass_value = None   # what htf_pass() returns for this setup, every tick, per the assertion above
        old_blocks = bool(st.get("htf")) and htf_pass_value is False       # pre-fix condition (:1108 before this commit)
        new_blocks = bool(st.get("htf")) and htf_pass_value is not True    # post-fix condition
        with open("/tmp/task8-failclosed.txt", "w") as f:
            f.write(f"setup: {st['id']} (method={st['method']} tf={st['tf']} htf={st.get('htf')})\n")
            f.write(f"HTF_OF[{st['tf']!r}] = {htf_tf!r} -- automation.SCAN_WINDOW has no entry for it, so "
                    f"htf_pass() returns None every tick, forever\n")
            f.write(f"sig['htf_pass'] = {htf_pass_value!r}\n")
            f.write(f"BEFORE (tick() blocked on `is False`):    blocks_new_entry = {old_blocks}  "
                    f"-- fail-OPEN: the gate never refused this setup\n")
            f.write(f"AFTER  (tick() blocks on `is not True`):  blocks_new_entry = {new_blocks}  "
                    f"-- fail-CLOSED: the gate refuses until it can actually judge\n")
        self.assertFalse(old_blocks, "sanity check: reproduces the fail-open bug under the OLD condition")
        self.assertTrue(new_blocks, "the NEW condition must refuse this setup until the SCAN_WINDOW gap is fixed")


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


class PresetFilter(unittest.TestCase):
    """The preset filters NEW signals only. An open position taken under a previous preset must still be
    managed -- spec §2.2, the sharpest bug the design review caught."""

    def cfg_with(self, dims, instruments=("BTCUSDT",)):
        return {"enabled": True, "layers": {"pilot": True},
                "markets": {"crypto": {"enabled": True, "instruments": list(instruments), "dimensions": dims},
                            "cfd": {"enabled": False, "instruments": [], "dimensions": {"wyckoff": True, "ict": True}}},
                "execution": {"environment": "demo", "pilot_profile": "top5"}}

    def _with_config(self, cfg, fn):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        old = sr.AUTOMATION_CONFIG; sr.AUTOMATION_CONFIG = tmp.name
        try:
            return fn()
        finally:
            sr.AUTOMATION_CONFIG = old; os.unlink(tmp.name)

    def test_load_setups_is_never_preset_filtered(self):
        """Filtering there would narrow replay parity, --list and the loop period. Spec §4.3."""
        cfg = self.cfg_with({"wyckoff": False, "ict": False, "footprint": False, "heatmap": False})
        n = self._with_config(cfg, lambda: len(sr.load_setups()))
        self.assertGreater(n, 0, "load_setups() must return the selection regardless of preset")

    def test_allowed_methods_reflects_the_preset(self):
        wy = self.cfg_with({"wyckoff": True, "ict": False, "footprint": False, "heatmap": False})
        got = self._with_config(wy, lambda: sr.allowed_methods("crypto"))
        self.assertEqual(got, {"WYCKOFF", "WYCKOFF-BOOK"})
        none = self.cfg_with({"wyckoff": False, "ict": False, "footprint": False, "heatmap": False})
        self.assertEqual(self._with_config(none, lambda: sr.allowed_methods("crypto")), set())

    def test_tick_still_manages_an_open_position_when_the_preset_blocks_every_method(self):
        """The regression that matters: no early return before step 1/2."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        head = src[src.index("def tick("):src.index("    # 1. positions")]
        self.assertNotIn("no runnable setup", head,
                         "the empty-setups early return still precedes position management")

    def test_step_three_filters_by_allowed_methods(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        body = src[src.index("    # 3. signals"):]
        self.assertIn("allowed_methods", body.split("def ")[0])

    def test_unticked_instrument_with_an_open_position_still_gets_candles(self):
        """Instrument narrowing grandfathers too: the need set adds every symbol holding a position or a
        pending order WITHOUT consulting enabled_symbols. Lock that in."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        head = src[src.index("    need = set()"):src.index("    # 1. positions")]
        self.assertIn('s["positions"].items()', head)
        self.assertIn('s["pending"].items()', head)

    def test_enabled_symbols_narrows_but_never_widens(self):
        cfg = self.cfg_with({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False},
                            instruments=("BTCUSDT",))
        got = self._with_config(cfg, lambda: sr.enabled_symbols("crypto"))
        self.assertEqual(got, ["BTCUSDT"])
        empty = self.cfg_with({"wyckoff": True, "ict": True, "footprint": False, "heatmap": False},
                              instruments=())
        self.assertEqual(self._with_config(empty, lambda: sr.enabled_symbols("crypto")), [])


class ScanDispatchFromRegistry(unittest.TestCase):
    def test_no_hard_coded_method_tuple_picks_the_scanner(self):
        """Adding a runner method must be a registry entry plus a scan function, not another if/elif arm."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn('st["method"] in ("ICT", "COMBINED")', src)
        self.assertNotIn('in ("WYCKOFF", "WYCKOFF-BOOK")', src)
        self.assertIn("scan_of", src)


class GrandfatherBehavioral(unittest.TestCase):
    """Requirement 3 of the task 8 prompt: real behavioural tests, not only source-text assertions. Two
    DISTINCT regressions, covered separately so neither can hide behind the other:

    - §2.2 (the empty-selection early return): `test_tick_manages_open_state_with_an_empty_selection` uses
      setups_cfg == [] -- the ONLY condition the old `if not setups_cfg: ... return` ever fired on -- with both
      an open position and a resting pending order in state, and asserts manage_position AND manage_pending are
      both still reached. This is the discriminating test: restoring the old early return must fail it.
    - §4.3 (the preset filter grandfathers correctly): `test_tick_still_manages_an_open_position_when_the_preset_
      blocks_the_only_setup` uses a NON-empty setups_cfg that allowed_methods() blocks, and asserts
      manage_position is still reached. This does NOT exercise the old early return (setups_cfg is truthy, so
      `if not setups_cfg` never fires here) -- it exercises the NEW step-3 filter added by this task instead.
    """

    def _run_dry_tick(self, cfg, selection, state):
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(selection, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()

        old_cfg, old_sel, old_state = sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE
        old_fetch, old_log, old_manage_pos, old_manage_pend = sr.fetch_candles, sr.log, sr.manage_position, sr.manage_pending
        calls = {"position": [], "pending": []}
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
        sr.fetch_candles = lambda *a, **k: []
        sr.log = lambda *a, **k: None

        def recording_manage_position(sym, pos, candles, live, bars_elapsed):
            calls["position"].append(sym); return None
        def recording_manage_pending(sym, pend, live, bars_elapsed):
            calls["pending"].append(sym); return "waiting", None, None, None
        sr.manage_position = recording_manage_position
        sr.manage_pending = recording_manage_pending
        try:
            sr.tick(live=False, tick_time=sr.now(), ignore_gate=True)
        finally:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = old_cfg, old_sel, old_state
            sr.fetch_candles, sr.log, sr.manage_position, sr.manage_pending = old_fetch, old_log, old_manage_pos, old_manage_pend
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
        return calls

    def test_tick_manages_open_state_with_an_empty_selection(self):
        """The regression this task exists to prevent (spec §2.2). setups_cfg is [] -- the exact condition the
        removed `if not setups_cfg: ... return` fired on. An open position AND a resting pending limit must
        both still be managed. Verified to fail against the old early-return code (see task report)."""
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT", "ETHUSDT"],
                                       "dimensions": {"wyckoff": True, "ict": True, "footprint": False, "heatmap": False}},
                           "cfd": {"enabled": False, "instruments": [], "dimensions": {"wyckoff": True, "ict": True}}},
               "execution": {"environment": "demo", "pilot_profile": "top5"}}
        selection = {"setups": []}
        state = {"started": "2026-01-01T00:00:00Z", "day": None, "trades_today": {}, "errors": 0,
                 "halted": None, "last_tick": None, "seen": [],
                 "positions": {"BTCUSDT": dict(side="LONG", strategy="empty-sel-test", tf="30m", method="ICT",
                                                execution="futures", mgmt="be", qty="1", entry=100.0, stop=99.0,
                                                tp=103.0, stop_order=None, tp_order=None, opened_at="2026-01-01T00:00:00Z",
                                                bars=0, risk_usd=1.0, be=False, be_level=101.0, htf_pass=True,
                                                sweep_time=None, mss_time=None)},
                 "pending": {"ETHUSDT": dict(symbol="ETHUSDT", side="LONG", strategy="empty-sel-test", tf="30m",
                                              method="ICT", execution="futures", qty="1", price="100", stop="99",
                                              tp="103", order_id="1", client_id="c1", placed_at="2026-01-01T00:00:00Z",
                                              bars_waited=0, expires_bar_left=5, htf_pass=True)},
                 "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}
        calls = self._run_dry_tick(cfg, selection, state)
        self.assertEqual(calls["position"], ["BTCUSDT"],
                         "manage_position must be reached with an empty setups_cfg -- a naked resting limit or "
                         "an unmanaged open position is exactly the failure mode this task must not reintroduce")
        self.assertEqual(calls["pending"], ["ETHUSDT"],
                         "manage_pending must be reached with an empty setups_cfg -- a resting futures limit "
                         "carries no stop until open_position() sees it fill")

    def test_tick_still_manages_an_open_position_when_the_preset_blocks_the_only_setup(self):
        """§4.3 only: the NEW step-3 preset filter must not touch steps 1/2. setups_cfg is non-empty here (one
        ICT setup) so the OLD `if not setups_cfg` early return is never reached by this scenario -- it is NOT a
        test of §2.2's early return (see class docstring); it is a test of the filter added at step 3."""
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"],
                                       "dimensions": {"wyckoff": False, "ict": False, "footprint": False, "heatmap": False}},
                           "cfd": {"enabled": False, "instruments": [], "dimensions": {"wyckoff": True, "ict": True}}},
               "execution": {"environment": "demo", "pilot_profile": "top5"}}
        selection = {"setups": [dict(id="grandfather-test", market="crypto", symbols=["BTCUSDT"], tf="30m",
                                      method="ICT", ict_target="range", htf=False, mgmt="be", execution="futures")]}
        state = {"started": "2026-01-01T00:00:00Z", "pending": {}, "day": None, "trades_today": {}, "errors": 0,
                 "halted": None, "last_tick": None, "seen": [],
                 "positions": {"BTCUSDT": dict(side="LONG", strategy="grandfather-test", tf="30m", method="ICT",
                                                execution="futures", mgmt="be", qty="1", entry=100.0, stop=99.0,
                                                tp=103.0, stop_order=None, tp_order=None, opened_at="2026-01-01T00:00:00Z",
                                                bars=0, risk_usd=1.0, be=False, be_level=101.0, htf_pass=True,
                                                sweep_time=None, mss_time=None)},
                 "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}
        self.assertEqual(sr.allowed_methods("crypto", {"wyckoff": False, "ict": False, "footprint": False, "heatmap": False}),
                         set(), "preset must block every method for this to be a real test of the step-3 filter")
        calls = self._run_dry_tick(cfg, selection, state)
        self.assertEqual(calls["position"], ["BTCUSDT"],
                         "manage_position must still be reached for the open position even though the preset "
                         "blocks the setup's only method -- the step-3 filter must never affect steps 1/2")


class ConfigReadFailureFallback(unittest.TestCase):
    """tick()'s per-tick dims cache must share allowed_methods()'s own fail-OPEN fallback (documented there as
    "unconfigured = behave exactly as before this switch existed"). A prior version of the fix set the per-tick
    cache to {} on a read failure, which is NOT equivalent to "no config": runner_methods({}) is the EMPTY set
    because every runner method requires at least one dimension, so a corrupt/unreadable config silently
    blocked every method (fail CLOSED) instead of falling back to "no preset switch" (fail OPEN). Not reachable
    on the live path -- automation_gate() already refuses a tick on a missing/unreadable config -- but the two
    fallbacks must still agree."""

    def test_corrupt_automation_config_does_not_block_every_method_in_tick(self):
        bad_cfg = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); bad_cfg.write("{not valid json"); bad_cfg.close()
        selection = {"setups": [dict(id="corrupt-cfg-test", market="crypto", symbols=["BTCUSDT"], tf="30m",
                                      method="ICT", ict_target="range", htf=False, mgmt="be", execution="futures")]}
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(selection, sel_tmp); sel_tmp.close()
        state = {"started": "2026-01-01T00:00:00Z", "pending": {}, "positions": {}, "day": None, "trades_today": {},
                 "errors": 0, "halted": None, "last_tick": None, "seen": [],
                 "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()

        old_cfg, old_sel, old_state = sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE
        old_fetch, old_log = sr.fetch_candles, sr.log
        logs = []
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = bad_cfg.name, sel_tmp.name, state_tmp.name
        sr.fetch_candles = lambda *a, **k: []
        sr.log = lambda kind, **kw: logs.append((kind, kw))
        try:
            sr.tick(live=False, tick_time=sr.now(), ignore_gate=True)
        finally:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = old_cfg, old_sel, old_state
            sr.fetch_candles, sr.log = old_fetch, old_log
            os.unlink(bad_cfg.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)

        filtered = [kw for kind, kw in logs if kind == "preset_filtered"]
        self.assertEqual(filtered, [], "a corrupt/unreadable AUTOMATION_CONFIG must fail OPEN inside tick() too "
                         "(no preset filtering applied), matching allowed_methods()'s own documented fallback "
                         "-- not fail CLOSED (every method blocked)")


class EquityHalt(unittest.TestCase):
    """2026-09-13 incident: EQUITY_HALT_FRAC compared availableBalance (free margin) to equity_start and
    halted the pilot on its first resting order -- margin reserved for a pending limit isn't a loss. The
    fix reads usdt_equity() (balance + crossUnPnl) for the halt instead, while usdt_free() (unchanged) keeps
    feeding position sizing. These tests hit tick(live=True) with order_json/mt5_json/automation_gate/
    fetch_candles/manage_position/manage_pending all mocked -- no network call is made and the --live CLI
    path is never invoked."""

    def _run_live_tick(self, state, balance_row):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}, "cfd": {"enabled": True, "instruments": []}},
               "execution": {"environment": "demo", "pilot_profile": "top5"}}
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump({"setups": []}, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()
        stop_path = state_tmp.name + ".STOP"   # a path guaranteed not to exist yet

        old = dict(cfg=sr.AUTOMATION_CONFIG, sel=sr.SELECTION, state=sr.STATE, stop=sr.STOP, gate=sr.automation_gate,
                   order_json=sr.order_json, mt5_json=sr.mt5_json, fetch_candles=sr.fetch_candles, log=sr.log,
                   manage_position=sr.manage_position, manage_pending=sr.manage_pending)
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE, sr.STOP = cfg_tmp.name, sel_tmp.name, state_tmp.name, stop_path
        sr.automation_gate = lambda: None
        sr.order_json = lambda *a, **k: ([balance_row] if a and a[0] == "balance" else [])
        sr.mt5_json = lambda *a, **k: {}
        sr.fetch_candles = lambda *a, **k: []
        sr.log = lambda *a, **k: None
        sr.manage_position = lambda *a, **k: None
        sr.manage_pending = lambda *a, **k: ("waiting", None, None, None)
        try:
            sr.tick(live=True, tick_time=sr.now(), ignore_gate=False)
            out = json.load(open(state_tmp.name)); stop_written = os.path.exists(stop_path)
            return out, stop_written
        finally:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE, sr.STOP = old["cfg"], old["sel"], old["state"], old["stop"]
            sr.automation_gate, sr.order_json, sr.mt5_json = old["gate"], old["order_json"], old["mt5_json"]
            sr.fetch_candles, sr.log = old["fetch_candles"], old["log"]
            sr.manage_position, sr.manage_pending = old["manage_position"], old["manage_pending"]
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
            if os.path.exists(stop_path):
                os.unlink(stop_path)

    def _state(self, equity_start):
        """One resting futures pending order so venues_used == {"futures"} without needing a live setup."""
        return {"started": "2026-01-01T00:00:00Z", "positions": {}, "day": None, "trades_today": {}, "errors": 0,
                "halted": None, "last_tick": None, "seen": [], "equity_basis": "equity",
                "pending": {"BTCUSDT": dict(symbol="BTCUSDT", side="LONG", strategy="x", tf="30m", method="ICT",
                                             execution="futures", qty="1", price="100", stop="99", tp="103",
                                             order_id="1", client_id="c1", placed_at="2026-01-01T00:00:00Z",
                                             bars_waited=0, expires_bar_left=5, htf_pass=True)},
                "venues": {v: {"equity_start": equity_start, "closed": [], "consec_losses": 0} for v in sr.VENUES}}

    def test_reserved_margin_for_a_resting_order_does_not_halt(self):
        """Exact reconstruction of the 2026-09-12 incident: wallet balance 4999.00, zero unrealised P&L,
        availableBalance 3750.48 (margin reserved for the BTCUSDT resting limit, qty 0.0485 @ 77289.7 / 3x
        leverage = 1249.52 reserved), equity_start 5000.00. Old code compared 3750.48 to 85% of 5000 = 4250
        and halted. Fixed code compares equity (4999.00) to the same threshold and must not halt."""
        balance_row = {"asset": "USDT", "balance": "4999.00", "crossUnPnl": "0.00", "availableBalance": "3750.48"}
        out, stop_written = self._run_live_tick(self._state(5000.0), balance_row)
        self.assertIsNone(out["halted"], out["halted"])
        self.assertFalse(stop_written, "no STOP file may be written for this scenario")
        self.assertAlmostEqual(out["venues"]["futures"]["equity_start"], 5000.0)

    def test_genuine_drawdown_still_halts(self):
        """The guard must still work: wallet balance itself down past EQUITY_HALT_FRAC halts, STOP written."""
        balance_row = {"asset": "USDT", "balance": "4000.00", "crossUnPnl": "0.00", "availableBalance": "4000.00"}
        out, stop_written = self._run_live_tick(self._state(5000.0), balance_row)
        self.assertIsNotNone(out["halted"])
        self.assertIn("futures", out["halted"]["why"])
        self.assertTrue(stop_written)

    def test_open_position_unrealised_loss_halts_even_though_free_margin_looks_fine(self):
        """balance 5000, crossUnPnl -900 -> equity 4100 <= 4250 halts. availableBalance (4995) stays high
        because little margin is committed -- the old free-margin reading would have missed this real
        drawdown entirely. This is the guard becoming MORE correct, not looser: EQUITY_HALT_FRAC (0.85) is
        unchanged, only the quantity it is compared against changed."""
        balance_row = {"asset": "USDT", "balance": "5000.00", "crossUnPnl": "-900.00", "availableBalance": "4995.00"}
        out, _ = self._run_live_tick(self._state(5000.0), balance_row)
        self.assertIsNotNone(out["halted"])
        self.assertIn("4100.00", out["halted"]["why"])


class EquityReadings(unittest.TestCase):
    """Direct unit tests of the balance-reading split (point 1 of the fix): usdt_free() (free margin, feeds
    sizing) and usdt_equity() (true equity, feeds the halt) must read different fields, from the same
    underlying usdt_balance() fetch."""

    def _with_balance_row(self, row, fn):
        old = sr.order_json
        sr.order_json = lambda *a, **k: ([row] if a and a[0] == "balance" else [])
        try:
            return fn()
        finally:
            sr.order_json = old

    def test_usdt_free_returns_available_balance_unchanged(self):
        row = {"asset": "USDT", "balance": "4999.00", "crossUnPnl": "0.00", "availableBalance": "3750.48"}
        self.assertAlmostEqual(self._with_balance_row(row, sr.usdt_free), 3750.48)

    def test_usdt_equity_returns_balance_plus_cross_unpnl(self):
        row = {"asset": "USDT", "balance": "4999.00", "crossUnPnl": "0.00", "availableBalance": "3750.48"}
        self.assertAlmostEqual(self._with_balance_row(row, sr.usdt_equity), 4999.00)

    def test_usdt_equity_reflects_floating_pnl_that_free_margin_hides(self):
        row = {"asset": "USDT", "balance": "5000.00", "crossUnPnl": "-900.00", "availableBalance": "4995.00"}
        self.assertAlmostEqual(self._with_balance_row(row, sr.usdt_equity), 4100.00)
        self.assertAlmostEqual(self._with_balance_row(row, sr.usdt_free), 4995.00)

    def test_usdt_balance_free_and_equity_agree_with_the_named_wrappers(self):
        row = {"asset": "USDT", "balance": "4999.00", "crossUnPnl": "0.00", "availableBalance": "3750.48"}
        bal = self._with_balance_row(row, sr.usdt_balance)
        self.assertAlmostEqual(bal["free"], self._with_balance_row(row, sr.usdt_free))
        self.assertAlmostEqual(bal["equity"], self._with_balance_row(row, sr.usdt_equity))


class SizingUsesFreeMarginNotEquity(unittest.TestCase):
    """Call-site split (point 1): place_market()/place_limit() -- position sizing / order placement -- must
    keep receiving the free-margin-based reading (sizing_equity), never the equity reading used by the
    halt guard. A structural check on tick()'s source, matching this suite's existing convention (see
    ScanDispatchFromRegistry, PresetFilter) for wiring invariants that don't have a deterministic signal to
    trigger behaviourally."""

    def test_place_calls_use_sizing_equity_not_equity(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        body = src[src.index("def tick("):]
        self.assertIn("place_market(sym, st, sig, sizing_equity.get(venue, 10000.0)", body)
        self.assertIn("place_limit(sym, st, sig, sizing_equity.get(venue, 10000.0)", body)
        self.assertNotIn("place_market(sym, st, sig, equity.get(venue, 10000.0)", body)
        self.assertNotIn("place_limit(sym, st, sig, equity.get(venue, 10000.0)", body)

    def test_futures_sizing_equity_is_free_margin_not_true_equity(self):
        """End-to-end within tick(): sizing_equity["futures"] must equal usdt_free()'s reading (availableBalance),
        not usdt_equity()'s, even though the halt-check `equity` dict differs from it in the same tick."""
        old_order_json = sr.order_json
        row = {"asset": "USDT", "balance": "4999.00", "crossUnPnl": "0.00", "availableBalance": "3750.48"}
        sr.order_json = lambda *a, **k: ([row] if a and a[0] == "balance" else [])
        try:
            bal = sr.usdt_balance()
        finally:
            sr.order_json = old_order_json
        self.assertNotAlmostEqual(bal["free"], bal["equity"])
        self.assertAlmostEqual(bal["free"], 3750.48)
        self.assertAlmostEqual(bal["equity"], 4999.00)


class ProtectiveOrderFailure(unittest.TestCase):
    """2026-09-13 incident: a filled BTCUSDT limit's stop-market placement raised (Binance testnet -4120), and
    open_position() propagated the exception AFTER the entry had already filled on the exchange -- leaving a
    naked leveraged position while state still showed it under `pending` (positions: {}). Fix: placing the
    protective stop is part of opening a position, not a step after it (task spec, Change 2). On a stop-market
    failure, open_position() now emergency-closes the just-filled entry (MARKET reduceOnly) before any failure
    can surface; only if that emergency close ALSO fails does the runner halt hard with a STOP file naming the
    symbol and quantity -- the one case where a naked position may exist. These tests hit tick(live=True) with
    order_json/automation_gate/fetch_candles/manage_pending mocked, matching the EquityHalt suite's pattern --
    no network call is made and the --live CLI path is never invoked."""

    def _state_with_pending(self):
        return {"started": "2026-01-01T00:00:00Z", "positions": {}, "day": None, "trades_today": {}, "errors": 0,
                "halted": None, "last_tick": None, "seen": [], "equity_basis": "equity",
                "pending": {"BTCUSDT": dict(symbol="BTCUSDT", side="LONG", strategy="x", tf="30m", method="ICT",
                                             execution="futures", mgmt="be", leverage=sr.LEVERAGE, qty="1", price="100",
                                             stop="99", tp="103", order_id="1", client_id="c1", placed_at="2026-01-01T00:00:00Z",
                                             bars_waited=0, expires_bar_left=5, htf_pass=True,
                                             sweep_time=None, mss_time=None)},
                "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}

    _BALANCE_ROW = {"asset": "USDT", "balance": "10000.00", "crossUnPnl": "0.00", "availableBalance": "10000.00"}

    def _run_live_tick(self, state, order_json_fn):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}, "cfd": {"enabled": True, "instruments": []}},
               "execution": {"environment": "demo", "pilot_profile": "top5"}}
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump({"setups": []}, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()
        stop_path = state_tmp.name + ".STOP"

        old = dict(cfg=sr.AUTOMATION_CONFIG, sel=sr.SELECTION, state=sr.STATE, stop=sr.STOP, gate=sr.automation_gate,
                   order_json=sr.order_json, mt5_json=sr.mt5_json, fetch_candles=sr.fetch_candles, log=sr.log,
                   manage_position=sr.manage_position, manage_pending=sr.manage_pending)
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE, sr.STOP = cfg_tmp.name, sel_tmp.name, state_tmp.name, stop_path
        sr.automation_gate = lambda: None
        logs = []
        sr.order_json = order_json_fn
        sr.mt5_json = lambda *a, **k: {}
        sr.fetch_candles = lambda *a, **k: []
        sr.log = lambda kind, **kw: logs.append((kind, kw))
        sr.manage_position = lambda *a, **k: None
        sr.manage_pending = lambda sym, pend, live, bars_elapsed: ("filled", 1.0, 100.0, None)
        try:
            sr.tick(live=True, tick_time=sr.now(), ignore_gate=False)
            out = json.load(open(state_tmp.name)); stop_written = os.path.exists(stop_path)
            stop_content = open(stop_path).read() if stop_written else ""
            return out, stop_written, stop_content, logs
        finally:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE, sr.STOP = old["cfg"], old["sel"], old["state"], old["stop"]
            sr.automation_gate, sr.order_json, sr.mt5_json = old["gate"], old["order_json"], old["mt5_json"]
            sr.fetch_candles, sr.log = old["fetch_candles"], old["log"]
            sr.manage_position, sr.manage_pending = old["manage_position"], old["manage_pending"]
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
            if os.path.exists(stop_path):
                os.unlink(stop_path)

    def test_stop_placement_fails_but_emergency_close_succeeds(self):
        """entry fills, stop placement raises -> position is closed, state has no positions and no pending
        entry for BTCUSDT, and the failure is logged."""
        def order_json_fn(*a, **k):
            cmd = a[0] if a else None
            if cmd == "balance":
                return [self._BALANCE_ROW]
            if cmd == "stop-market":
                raise RuntimeError("binance-futures-testnet-order.sh stop-market BTCUSDT failed: "
                                   '{"code":-4120,"msg":"Order type not supported for this endpoint. '
                                   'Please use the Algo Order API endpoints instead."}')
            if cmd == "close-position":
                return {"orderId": 999, "status": "FILLED", "executedQty": "1", "avgPrice": "100.0"}
            if cmd in ("position-risk", "open-orders"):
                return []
            return {}
        out, stop_written, _stop_content, logs = self._run_live_tick(self._state_with_pending(), order_json_fn)
        self.assertNotIn("BTCUSDT", out["positions"], "no phantom positions entry after a safely-unwound failure")
        self.assertNotIn("BTCUSDT", out["pending"], "no stale pending entry -- the exact 2026-09-13 bug")
        self.assertIsNone(out["halted"])
        self.assertFalse(stop_written, "emergency close succeeded -- no hard halt needed")
        kinds = [kind for kind, kw in logs]
        self.assertIn("protection_failed_closed", kinds, "the failure and the closing action must both be logged")
        failure_log = next(kw for kind, kw in logs if kind == "protection_failed_closed")
        self.assertEqual(failure_log.get("symbol"), "BTCUSDT")

    def test_take_profit_failure_alone_does_not_unwind_the_position(self):
        """entry fills, stop succeeds, take-profit raises -> the stop already bounds the loss; a missing
        take-profit only forgoes an exit target, so the position is NOT closed. Asserted per this task's
        take-profit decision (see open_position() docstring/comment)."""
        def order_json_fn(*a, **k):
            cmd = a[0] if a else None
            if cmd == "balance":
                return [self._BALANCE_ROW]
            if cmd == "stop-market":
                return {"orderId": 555, "status": "NEW"}
            if cmd == "take-profit-market":
                raise RuntimeError("binance-futures-testnet-order.sh take-profit-market BTCUSDT failed: timeout")
            if cmd in ("position-risk", "open-orders"):
                return []
            return {}
        out, stop_written, _stop_content, logs = self._run_live_tick(self._state_with_pending(), order_json_fn)
        self.assertIn("BTCUSDT", out["positions"], "stop succeeded -- the position must remain open")
        self.assertNotIn("BTCUSDT", out["pending"])
        self.assertEqual(out["positions"]["BTCUSDT"]["stop_order"], 555)
        self.assertFalse(out["positions"]["BTCUSDT"].get("tp_order"))
        self.assertIsNone(out["halted"])
        self.assertFalse(stop_written)
        kinds = [kind for kind, kw in logs]
        self.assertIn("tp_placement_failed", kinds)

    def test_stop_placement_fails_and_emergency_close_also_fails_halts_hard(self):
        """entry fills, stop raises, emergency close also raises -> halts, STOP file written, reason names
        the symbol and quantity. The one case where a naked position may exist; must never be silent."""
        def order_json_fn(*a, **k):
            cmd = a[0] if a else None
            if cmd == "balance":
                return [self._BALANCE_ROW]
            if cmd == "stop-market":
                raise RuntimeError("stop-market BTCUSDT failed: -4120 Order type not supported")
            if cmd == "close-position":
                raise RuntimeError("close-position BTCUSDT failed: curl: (28) Connection timed out")
            if cmd in ("position-risk", "open-orders"):
                return []
            return {}
        out, stop_written, stop_content, logs = self._run_live_tick(self._state_with_pending(), order_json_fn)
        self.assertIsNotNone(out["halted"])
        self.assertIn("BTCUSDT", out["halted"]["why"])
        self.assertIn("1.0", out["halted"]["why"], "the halt reason must name the quantity")
        self.assertTrue(stop_written)
        self.assertIn("BTCUSDT", stop_content)

    def test_happy_path_unaffected(self):
        """entry fills, stop and take-profit both succeed -> unchanged behaviour."""
        def order_json_fn(*a, **k):
            cmd = a[0] if a else None
            if cmd == "balance":
                return [self._BALANCE_ROW]
            if cmd == "stop-market":
                return {"orderId": 555, "status": "NEW"}
            if cmd == "take-profit-market":
                return {"orderId": 556, "status": "NEW"}
            if cmd in ("position-risk", "open-orders"):
                return []
            return {}
        out, stop_written, _stop_content, logs = self._run_live_tick(self._state_with_pending(), order_json_fn)
        self.assertIn("BTCUSDT", out["positions"])
        self.assertNotIn("BTCUSDT", out["pending"])
        self.assertEqual(out["positions"]["BTCUSDT"]["stop_order"], 555)
        self.assertEqual(out["positions"]["BTCUSDT"]["tp_order"], 556)
        self.assertIsNone(out["halted"])
        self.assertFalse(stop_written)
        kinds = [kind for kind, kw in logs]
        self.assertNotIn("protection_failed_closed", kinds)
        self.assertNotIn("tp_placement_failed", kinds)


class ConnectorRequestShape(unittest.TestCase):
    """Connector-level tests with no network call: pins the exact request scripts/binance-futures-testnet-order.sh
    sends for the protective-order subcommands, and the response aliasing that keeps strategy-runner.py's
    classic-order vocabulary working.

    HISTORY. On 2026-09-13 every conditional order type (STOP_MARKET / STOP / TAKE_PROFIT_MARKET /
    TRAILING_STOP_MARKET) began failing at POST /fapi/v1/order with -4120 "Order type not supported for this
    endpoint. Please use the Algo Order API endpoints instead.", across all 12 parameter combinations tried
    (closePosition vs reduceOnly+quantity, workingType, priceProtect, positionSide, newOrderRespType, query vs
    form body). MARKET/LIMIT were unaffected.

    RESOLUTION (verified live against testnet 2026-09-13). Conditional orders moved to the futures Algo Order
    API: POST /fapi/v1/algoOrder with algoType=CONDITIONAL and the order type in `type`. The trigger level is
    named triggerPrice, NOT stopPrice -- that rename is the single parameter change; side, closePosition,
    workingType and priceProtect are unchanged, as is -2021 "Order would immediately trigger".

    Two consequences this class also guards, because they are silent-failure shaped:
      * conditional orders are NOT returned by /fapi/v1/openOrders (only /fapi/v1/openAlgoOrders), and
      * DELETE /fapi/v1/allOpenOrders does NOT cancel them.
    Left unhandled, the first makes reconciliation believe a protected position is unprotected, and the second
    leaves a live stop resting after its position is gone."""

    ORDER_SH = os.path.join(ROOT, "scripts", "binance-futures-testnet-order.sh")

    ALGO_NEW = ('{"algoId":1000000203021052,"clientAlgoId":"abc","algoType":"CONDITIONAL",'
                '"orderType":"STOP_MARKET","symbol":"BTCUSDT","side":"SELL","algoStatus":"NEW",'
                '"quantity":"0.0000","triggerPrice":"74000.00","closePosition":true,"priceProtect":true,'
                '"workingType":"MARK_PRICE","actualOrderId":"","triggerTime":0}')

    def _fake_curl_env(self, tmp, bodies=None):
        """A fake `curl` on PATH ahead of the real one: records its argv (the connector's exact request) to
        curl.log and returns a canned body chosen by the request URL, so the connector script runs unmodified
        with no network access. Also fakes the -K/stdin-config path the connector uses to pass the API key."""
        bodies = dict(bodies or {})
        # exit code for the classic (non-algo) branch; 1 reproduces curl --fail-with-body on the real API's
        # 400 -2013 "Order does not exist.", which is what makes the connector fall back to the algo namespace.
        default_code = bodies.pop("default_code", 0)
        bodies.setdefault("default", '{"orderId": 1, "status": "NEW"}')
        bodies.setdefault("algo", self.ALGO_NEW)
        bodies.setdefault("algo_open", "[]")
        bodies.setdefault("reg_open", "[]")
        bodies.setdefault("all_open", '{"code":200,"msg":"ok"}')
        paths = {}
        for k, v in bodies.items():
            fp = os.path.join(tmp, "body_%s.json" % k)
            with open(fp, "w") as f:
                f.write(v)
            paths[k] = fp
        curl_log = os.path.join(tmp, "curl.log")
        fake_curl = os.path.join(tmp, "curl")
        script = (
            "#!/usr/bin/env bash\n"
            "cat >/dev/null\n"                      # drain the -K - header config from stdin
            f'printf %s\\\\n "$*" >> "{curl_log}"\n'
            'url="${!#}"\n'
            "case \"$url\" in\n"
            f'  *openAlgoOrders*) cat "{paths["algo_open"]}" ;;\n'
            f'  *allOpenOrders*)  cat "{paths["all_open"]}" ;;\n'
            f'  *openOrders*)     cat "{paths["reg_open"]}" ;;\n'
            f'  *algoOrder*)      cat "{paths["algo"]}" ;;\n'
            f'  *)                cat "{paths["default"]}"; exit {default_code} ;;\n'
            "esac\n"
        )
        with open(fake_curl, "w") as f:
            f.write(script)
        os.chmod(fake_curl, 0o755)
        env = dict(os.environ, PATH=tmp + os.pathsep + os.environ.get("PATH", ""))
        return env, curl_log

    def _urls(self, curl_log):
        lines = [l for l in open(curl_log).read().splitlines() if l.strip()]
        self.assertTrue(lines, "curl was never invoked")
        return [l.split(" ")[-1] for l in lines]   # `curl ... -K - -X POST <url>` -- url is the last token

    def _run(self, args, bodies=None):
        tmp = tempfile.mkdtemp()
        env, curl_log = self._fake_curl_env(tmp, bodies)
        r = subprocess.run(["bash", self.ORDER_SH] + args, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r, self._urls(curl_log)

    def test_stop_market_uses_algo_order_endpoint(self):
        """The -4120 fix: POST /fapi/v1/algoOrder, algoType=CONDITIONAL, trigger level as triggerPrice."""
        _, urls = self._run(["stop-market", "BTCUSDT", "SELL", "75000.0"])
        url = urls[-1]
        self.assertIn("/fapi/v1/algoOrder?", url)
        self.assertIn("algoType=CONDITIONAL", url)
        self.assertIn("symbol=BTCUSDT", url)
        self.assertIn("side=SELL", url)
        self.assertIn("type=STOP_MARKET", url)
        self.assertIn("triggerPrice=75000.0", url)
        self.assertIn("closePosition=true", url)
        self.assertIn("workingType=MARK_PRICE", url)
        self.assertIn("priceProtect=TRUE", url)
        # the two things that produced -4120 / -1102 must not come back
        self.assertNotIn("/fapi/v1/order?", url)
        self.assertNotIn("stopPrice=", url)

    def test_take_profit_market_uses_algo_order_endpoint(self):
        _, urls = self._run(["take-profit-market", "BTCUSDT", "SELL", "90000.0"])
        url = urls[-1]
        self.assertIn("/fapi/v1/algoOrder?", url)
        self.assertIn("algoType=CONDITIONAL", url)
        self.assertIn("type=TAKE_PROFIT_MARKET", url)
        self.assertIn("triggerPrice=90000.0", url)
        self.assertIn("closePosition=true", url)
        self.assertIn("workingType=MARK_PRICE", url)
        self.assertIn("priceProtect=TRUE", url)
        self.assertNotIn("/fapi/v1/order?", url)
        self.assertNotIn("stopPrice=", url)

    def test_algo_response_is_aliased_to_classic_order_shape(self):
        """strategy-runner.py reads .orderId/.status/.stopPrice off the placement response; the Algo API
        returns algoId/algoStatus/triggerPrice instead, so the connector must alias them."""
        r, _ = self._run(["stop-market", "BTCUSDT", "SELL", "74000.0"])
        d = json.loads(r.stdout)
        self.assertEqual(d["orderId"], 1000000203021052)      # <- algoId
        self.assertEqual(d["algoId"], 1000000203021052)       # original field preserved
        self.assertEqual(d["status"], "NEW")                  # <- algoStatus
        self.assertEqual(d["type"], "STOP_MARKET")            # <- orderType
        self.assertEqual(d["stopPrice"], "74000.00")          # <- triggerPrice

    def test_triggered_algo_order_reports_filled(self):
        """A conditional order that fired reads algoStatus=FINISHED with actualQty/actualPrice. The runner
        only closes a position when it sees status==FILLED, so FINISHED must map to FILLED."""
        body = ('{"algoId":42,"orderType":"STOP_MARKET","symbol":"BTCUSDT","side":"SELL",'
                '"algoStatus":"FINISHED","actualOrderId":"28582102498","actualQty":"0.0007",'
                '"actualPrice":"77110.200000","triggerPrice":"77125.00","quantity":"0.0007"}')
        r, _ = self._run(["order-status", "BTCUSDT", "42"],
                         bodies={"algo": body, "default": '{"code":-2013,"msg":"Order does not exist."}',
                                 "default_code": 1})
        d = json.loads(r.stdout)
        self.assertEqual(d["status"], "FILLED")
        self.assertEqual(d["executedQty"], "0.0007")
        self.assertEqual(d["avgPrice"], "77110.200000")

    def test_finished_with_no_fill_is_not_reported_as_filled(self):
        """FINISHED but nothing executed (the position was already gone) is not a close -- reporting FILLED
        would book a phantom exit at price 0."""
        body = ('{"algoId":43,"orderType":"STOP_MARKET","symbol":"BTCUSDT","algoStatus":"FINISHED",'
                '"actualQty":"0","actualPrice":"0","triggerPrice":"77125.00"}')
        r, _ = self._run(["order-status", "BTCUSDT", "43"],
                         bodies={"algo": body, "default": '{"code":-2013,"msg":"Order does not exist."}',
                                 "default_code": 1})
        self.assertEqual(json.loads(r.stdout)["status"], "EXPIRED")

    def test_open_orders_merges_conditional_orders(self):
        """Conditional orders are absent from /fapi/v1/openOrders. If the connector did not merge
        /fapi/v1/openAlgoOrders, reconciliation would see a protected position as unprotected."""
        r, urls = self._run(["open-orders"], bodies={"reg_open": "[]", "algo_open": "[%s]" % self.ALGO_NEW})
        self.assertTrue(any("openAlgoOrders" in u for u in urls), "openAlgoOrders was never queried")
        rows = json.loads(r.stdout)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["orderId"], 1000000203021052)
        self.assertEqual(rows[0]["status"], "NEW")
        self.assertEqual(rows[0]["symbol"], "BTCUSDT")

    def test_cancel_all_also_cancels_conditional_orders(self):
        """DELETE /fapi/v1/allOpenOrders leaves conditional orders resting, so cancel-all must delete each
        algoId explicitly -- otherwise a stop outlives the position it was protecting."""
        _, urls = self._run(["cancel-all", "BTCUSDT"], bodies={"algo_open": "[%s]" % self.ALGO_NEW})
        self.assertTrue(any("/fapi/v1/allOpenOrders?" in u for u in urls), urls)
        self.assertTrue(any("/fapi/v1/algoOpenOrders?" in u and "symbol=BTCUSDT" in u for u in urls),
                        "cancel-all did not cancel the resting conditional orders: %s" % urls)

    def test_cancel_order_tries_classic_endpoint_before_algo(self):
        """A conditional order that has already TRIGGERED leaves the algo namespace and becomes an ordinary
        order -- cancelling it via the algo path returns -2011 Unknown order. So the classic endpoint must be
        tried FIRST and the algo path used only as the fallback. Getting this backwards is what produced the
        widely-reported orphaned-stop bug (freqtrade #12681). Here the classic call succeeds, so the algo
        endpoint must never be reached."""
        _, urls = self._run(["cancel-order", "BTCUSDT", "28582102498"])
        self.assertIn("/fapi/v1/order?", urls[-1])
        self.assertIn("orderId=28582102498", urls[-1])
        self.assertFalse(any("algoOrder" in u for u in urls),
                         "algo cancel path was used for an order the classic endpoint accepted: %s" % urls)

    def test_cancel_order_falls_back_to_algo_when_classic_rejects(self):
        """A still-resting conditional order is unknown to the classic endpoint (-2013), so cancel-order must
        fall back to DELETE /fapi/v1/algoOrder with the id as algoId."""
        _, urls = self._run(["cancel-order", "BTCUSDT", "1000000203021052"],
                            bodies={"default": '{"code":-2013,"msg":"Order does not exist."}',
                                    "default_code": 1, "algo": '{"algoId":1000000203021052,"code":"200"}'})
        self.assertIn("/fapi/v1/algoOrder?", urls[-1])
        self.assertIn("algoId=1000000203021052", urls[-1])


class EquityStartMigration(unittest.TestCase):
    """Point 3 of the fix: equity_start persisted before this fix was captured under the OLD (free-margin)
    reading and is not comparable to the NEW (equity) reading. load_state() must detect a state file with no
    "equity_basis" marker (or a stale one) and re-baseline -- reset equity_start to None so the next LIVE
    tick recaptures it from the corrected reading -- exactly once, not on every load."""

    def _with_state_file(self, content, fn):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(content, tmp); tmp.close()
        old = sr.STATE; sr.STATE = tmp.name
        try:
            return fn()
        finally:
            sr.STATE = old; os.unlink(tmp.name)

    def test_legacy_state_without_equity_basis_is_rebaselined(self):
        legacy = {"started": "2026-09-11T10:55:04Z", "pending": {}, "positions": {}, "seen": [], "day": None,
                  "trades_today": {}, "errors": 0, "halted": None, "last_tick": None,
                  "venues": {"futures": {"equity_start": 5000.0, "closed": [], "consec_losses": 0},
                             "mt5": {"equity_start": 99999.5, "closed": [], "consec_losses": 0}}}
        s = self._with_state_file(legacy, sr.load_state)
        self.assertIsNone(s["venues"]["futures"]["equity_start"], "stale free-margin-basis baseline must be cleared")
        self.assertIsNone(s["venues"]["mt5"]["equity_start"])
        self.assertEqual(s["equity_basis"], sr.EQUITY_BASIS)

    def test_already_migrated_state_is_left_alone(self):
        migrated = {"started": "2026-09-11T10:55:04Z", "pending": {}, "positions": {}, "seen": [], "day": None,
                    "trades_today": {}, "errors": 0, "halted": None, "last_tick": None, "equity_basis": sr.EQUITY_BASIS,
                    "venues": {"futures": {"equity_start": 4999.0, "closed": [], "consec_losses": 0},
                               "mt5": {"equity_start": 99999.5, "closed": [], "consec_losses": 0}}}
        s = self._with_state_file(migrated, sr.load_state)
        self.assertAlmostEqual(s["venues"]["futures"]["equity_start"], 4999.0, "an already-migrated baseline must not be reset again")
        self.assertAlmostEqual(s["venues"]["mt5"]["equity_start"], 99999.5)
