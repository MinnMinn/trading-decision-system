import datetime, importlib.util, json, os, subprocess, sys, tempfile, threading, time, unittest

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
        """COMBINED (a Spring/Upthrust proxy + ICT confirmation, mirroring bt.scan's now-deleted COMBINED
        block) was removed 2026-09-19 along with the WYCKOFF proxy it depended on
        (docs/audits/2026-09-19-knowledge-fidelity.md finding 6); sr.setups() now only ever produces ICT
        setups (see its own docstring)."""
        c = synthetic()
        for method in ("ICT",):
            for side in ("long", "short"):
                for s in sr.setups(method, side, c, "30m"):
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
            r = bt.find_ict("long", i, i, H, L, C, 14, len(c), PH, PL, [x["open"] for x in c])
            if r:
                mss, edge, far = r
                self.assertTrue(any(H[k - 1] < L[k + 1] and L[k + 1] == edge for k in range(i + 1, mss)))

    def test_the_dead_ict_switches_are_gone_from_the_signature_and_from_opts(self):
        """Before 2026-09-19 this asserted that setups()'s now-deleted COMBINED branch saved and restored
        bt.OPTS['ict_disp']/['std_origin'] around its own call into bt.find_ict. COMBINED was removed with the
        WYCKOFF proxy it depended on (finding 6), after which the three switches were kept as call-site
        compatibility parameters that read nothing -- and then removed outright (finding 11), because all
        three name real deck rules that are enforced unconditionally elsewhere: R13 is `pd_ok` in
        scripts/ict-scan.py, the STDEV fib-0 anchor is fixed by Model11 p20, and displacement is what
        separates an MSS (R10) from a liquidity grab (R11). A switch that can turn a mandatory rule off is
        not a feature, and one that reads nothing at all is worse.
        """
        import inspect
        params = inspect.signature(sr.setups).parameters
        for dead in ("ict_disp", "ict_pd", "std_origin"):
            self.assertNotIn(dead, params, f"setups() still accepts {dead}")
            self.assertNotIn(dead, bt.OPTS, f"{dead} is back in bt.OPTS")
        sr.setups("ICT", "long", synthetic(), "30m")          # the surviving signature still runs


class ParityWithBacktest(unittest.TestCase):
    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, "data", "history", "ohlcv.SOLUSDT.30m.json")), "history not fetched")
    def test_replay_matches_backtest_first_setup(self):
        """`bars` must clear the window the method actually reads. It was 450 while the live ICT scanner reads
        576 bars on 15m, so replay fed the scanner a short window, live_rules.read_at refused it by design, the
        runner produced zero placements, and the check passed only because the backtest found nothing in the
        span either. The first backtest trade to land in a span surfaced it (2026-09-19)."""
        st = sr.load_setups()[0]
        rep = sr.replay([st["id"]], bars=900)
        self.assertTrue(rep, "replay produced no rows at all")
        for r in rep:
            self.assertNotIn("skipped", r, r)
            self.assertEqual(r["unmatched"], 0, r)

    def test_replay_actually_exercises_the_runner(self):
        """A parity check with zero runner placements on every symbol proves nothing; it is the shape the ICT
        window bug hid behind for as long as it did."""
        st = sr.load_setups()[0]
        rep = sr.replay([st["id"]], bars=900)
        self.assertTrue(any(r["runner_placements"] > 0 or r["backtest_trades"] > 0 for r in rep),
                        f"neither engine produced anything in the replay span: {rep}")


class TheBacktestSeesOnlyWhatTheRunnerSaw(unittest.TestCase):
    """bt.scan()'s Wyckoff branch reads the history window by window through bt.wyckoff_fires -- the runner's own
    read -- since 2026-09-19. Before that it detected over the whole series at once, and wyckoff_rules' CHoCH
    stage can complete a structure with a swing that forms AFTER its Phase D entry bar (XAGUSD 4H, entry
    2026-07-20T05:00Z: the structure exists on no causal prefix until five bars after that entry). The backtest
    took that entry; the runner could not have -- replay() reported it as the first Wyckoff parity mismatch.
    Measured cost of the fix, WYCKOFF-BOOK trades old -> causal: XAGUSD 4H 41 -> 31, XAUUSD 4H 50 -> 46,
    BTCUSDT 15m 115 -> 89, ETHUSDT 1H 41 -> 34; almost every spring-leg entry went (its reclaim/test bar is
    only identified later), the Phase D legs mostly stayed."""

    HIST = os.path.join(ROOT, "data", "history", "ohlcv.XAGUSD.4H.json")

    def setUp(self):
        bt.OPTS.update(htf=False, sides=("long", "short"), types=(1, 2, 3), entry="book")

    def test_one_window_for_both_engines(self):
        """The runner's WINDOW is bt's number, not a second literal that can drift from it."""
        self.assertEqual(sr.WINDOW, bt.WYCKOFF_WINDOW)
        self.assertIn("WINDOW = bt.WYCKOFF_WINDOW", open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read())

    @unittest.skipUnless(os.path.exists(HIST), "history not fetched")
    def test_every_backtest_wyckoff_trade_is_the_runners_read_at_its_own_entry_bar(self):
        """Parity by construction, checked on real bars: for each WYCKOFF-BOOK trade the backtest reports in the
        last 3000 bars, the runner's setups_wyckoff() on the WINDOW bars ending at that trade's entry bar fires
        the identical entry/stop/target."""
        c = json.load(open(self.HIST))["candles"]; idx = {b["time"]: i for i, b in enumerate(c)}
        sc = bt.scan("XAGUSD", "4H", only=("WYCKOFF-BOOK",))
        trades = [t for t in sc["trades"]["WYCKOFF-BOOK"] if t["entry_time"] >= c[-3000]["time"]]
        self.assertTrue(trades, "no WYCKOFF-BOOK trade in the last 3000 bars to check against")
        for t in trades:
            e = idx[t["entry_time"]]
            fires = sr.setups_wyckoff("WYCKOFF-BOOK", t["side"], c[e + 1 - sr.WINDOW:e + 1], "4H", sym="XAGUSD")
            hit = [f for f in fires if abs(f["entry"] - t["entry"]) < 1e-9 and abs(f["stop"] - t["stop"]) < 1e-9 and abs(f["target"] - t["target"]) < 1e-9]
            self.assertEqual(len(hit), 1, f"{t['event']} entered {t['entry_time']}: the runner's read at that bar gives {fires}")

    @unittest.skipUnless(os.path.exists(HIST), "history not fetched")
    def test_the_entry_that_needed_future_bars_is_gone(self):
        """The case that found it, pinned so a whole-series shortcut cannot creep back into scan(). The second
        half states the reason on the detector itself; if wyckoff_rules is ever made causal at the CHoCH stage
        that half will start failing, and then it should simply be deleted -- the first half is the invariant."""
        c = json.load(open(self.HIST))["candles"]
        sc = bt.scan("XAGUSD", "4H", only=("WYCKOFF-BOOK",))
        self.assertNotIn("2026-07-20T05:00:00Z", [t["entry_time"] for t in sc["trades"]["WYCKOFF-BOOK"]])
        e = [b["time"] for b in c].index("2026-07-20T05:00:00Z")
        def found(prefix):
            O = [x["open"] for x in prefix]; H = [x["high"] for x in prefix]; L = [x["low"] for x in prefix]; C = [x["close"] for x in prefix]; V = [x.get("volume", 0) for x in prefix]
            return any(r.get("bu") and r["bu"]["bar"] == e for r in sr.W.detect_distributions(O, H, L, C, V, volume_kind="tick"))
        self.assertFalse(found(c[:e + 1]), "the structure is visible on the causal prefix -- the detector changed; delete this half")
        self.assertTrue(found(c[:e + 6]), "the structure no longer appears five bars later either -- the detector changed; delete this half")


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

    # 6000, not 3000 (2026-09-19): after the fill fix ICT fires 6 times in the last 30 000 BTCUSDT 15m bars, the
    # nearest 2 919 and 5 036 bars from the end, and the live scanner needs its 576-bar window before either --
    # so 3000 bars held zero trades and the parity test proved agreement on nothing. 6000 holds two.
    WINDOW = 8000   # 2026-09-24: 6000 held no setup after the ICT-1 fix removed two false sweeps (docs/audits review, round 2)

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
        # old_sr's own ROOT-relative import loads bt fresh from disk -- i.e. the CURRENT backtest-methods.py,
        # not the febd2d6 blob -- so left alone it would carry today's OPTS schema and be missing bt.ict_target()
        # entirely (this task deleted it, 2026-09-13: no caller left). old_sr's febd2d6-era setups() ICT branch
        # calls bt.ict_target() directly, so it needs the ACTUAL febd2d6 backtest-methods.py, not today's --
        # rebind it to the old_bt already loaded above (the matching commit) rather than the disk version.
        old_sr.bt = old_bt
        old_runner_pending = sum(len(old_sr.setups("ICT", side, self.full, "15m")) for side in ("long", "short"))
        new_runner_pending = sum(len(sr.setups("ICT", side, self.full, "15m", sym="BTCUSDT")) for side in ("long", "short"))

        matched = 0
        with open("/tmp/task8-ict-agree.txt", "w") as f:
            f.write("BTCUSDT 15m, 3000-bar window\n")
            f.write(f"BEFORE (commit febd2d6, bt.scan --rules live vs legacy, the divergence "
                    f"IctParityIsKnownBroken pinned): live={before['live']} legacy={before['legacy']} "
                    f"(the legacy-vs-live evidence gate this task was "
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

    def test_ict_is_still_selectable_and_every_selected_method_is_runnable(self):
        """The reason parity matters: these are the setups that would trade if the locks were lifted. This used
        to assert that the selection CONTAINS an ICT setup -- a pin on a ranking outcome, and it went false for
        a measured reason, not a code one: after the 2026-09-19 fill fix ICT places 2-4 trades a year against
        the 1y window's 20-trade threshold (docs/audits/2026-09-19-knowledge-fidelity.md §8-§9). The invariant
        worth keeping is that ICT remains a RUNNABLE, selectable method, and that nothing the ranking selects
        is a method the runner cannot run."""
        self.assertIn("ICT", sr.mreg.runnable())
        setups = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-top20.json")))["setups"]
        for st in setups:
            self.assertIn(st.get("method"), sr.mreg.runnable(), st.get("id"))


class HtfGateFailsClosed(unittest.TestCase):
    """2026-09-13, Task 8 fix round 1: a setup that declares htf:true is asking for a higher-timeframe gate.
    Before this fix, tick() only blocked on an explicit `sig["htf_pass"] is False`; once htf_pass() started
    reading the live rules (this task), it can also return None for reasons that have NOTHING to do with the
    actual bias -- no candles fetched, htf_tf not in bt.P, or automation.SCAN_WINDOW has no entry for htf_tf
    (the 2H/30m gap) -- and every one of those sailed through as if the gate had opened. This is a fail-OPEN
    order gate; every other gate this task touched fails closed on missing data. These tests assert on the
    DECISION (was place_limit/place_market ever called), not on htf_pass's return value, per the coordinator's
    review."""

    # r_planned 3.0 (target 103 against a 1.0 stop), not the 2.0 this fixture carried until 2026-09-13: the
    # planned-R:R floor (rr_reason, MIN_RR = 3R) now also sits in the reasons[] block, and a signal that fails it
    # never reaches the order stage. These tests are about the HTF gate, so the fixture has to clear every OTHER
    # gate to isolate it. Entry/stop/target stay internally consistent with r_planned.
    # target 103.1, not 103.0, since 2026-09-18: the R:R floor is charged NET of fees (CLAUDE.md §34), and
    # 3.00R gross on a 1 % stop is 2.96R after the maker fee -- i.e. the old fixture planned exactly the floor
    # gross and therefore sat just under it net. Moved so this class keeps testing the HTF gate rather than
    # silently becoming a second test of the R:R gate.
    ONE_SIG = dict(time="2026-01-01T00:00:00Z", mss_time="2026-01-01T00:00:00Z", entry=100.0, stop=99.0,
                   target=103.1, bars_left=5, r_planned=3.1, vol_type=None)

    def _run(self, htf_pass_return):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"], "dimensions": {"wyckoff": True, "ict": True}},
                           "cfd": {"enabled": False, "instruments": []}},
               "execution": {"environment": "demo"}}
        selection = {"setups": [dict(id="test-ict-htf", market="crypto", symbols=["BTCUSDT"], tf="15m",
                                      method="ICT", htf=True, mgmt="be", execution="futures")]}
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
        sr.place_limit = lambda sym, st, sig, equity, risk_mult, live, **k: (placed.append((sym, sig)), None)[1]
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

    def test_no_selected_setup_can_have_an_unjudgeable_htf_tier(self):
        """The gate failing closed is only half the answer: a setup whose HTF tier is a timeframe live never
        scans would be refused on EVERY tick, forever -- correct, but useless, and invisible except as an
        absence.

        crypto-scalping-wyckoff-5m-border-c was exactly that (WYCKOFF, 5m, htf:true, HTF_OF["5m"] == "30m",
        which automation.SCAN_WINDOW has no entry for). The 2026-09-13 re-rank onto live-scannable timeframes
        removed it. This asserts the selection cannot reacquire one -- it is the invariant, not that one id."""
        setups = json.load(open(os.path.join(ROOT, "docs", "architecture", "pilot-top20.json")))["setups"]
        doomed = [s["id"] for s in setups
                  if s.get("htf") and sr.ict_scan_bars(sr.HTF_OF.get(s["tf"])) is None]
        self.assertEqual(doomed, [],
                         "these setups declare htf:true but their HTF tier is a timeframe live never scans, so "
                         "the gate would refuse them on every tick forever")


class PlanCarriesExpectations(unittest.TestCase):
    """CLAUDE.md §17/plan §0.6 (Task B2): step 11 builds one scripts/expectation.py record PER DIMENSION the
    setup's rule family requires, and the SAME records (not a re-derived copy) are what place_limit/
    place_market eventually persist onto the plan."""

    ONE_SIG = dict(time="2026-01-01T00:00:00Z", mss_time="2026-01-01T00:00:00Z", entry=100.0, stop=99.0,
                   target=103.1, bars_left=5, r_planned=3.1, vol_type=None)

    def _run(self):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"], "dimensions": {"wyckoff": True, "ict": True}},
                           "cfd": {"enabled": False, "instruments": []}},
               "execution": {"environment": "demo"}}
        # COMBINED (scan="ict", requires=["wyckoff","ict"]) was removed 2026-09-19 along with the WYCKOFF proxy
        # it depended on (docs/audits/2026-09-19-knowledge-fidelity.md finding 6). COMBINED-BOOK is its
        # surviving, book-faithful equivalent but is scan="wyckoff" -- so it routes through setups_wyckoff(),
        # not setups() -- hence both are mocked below (see `saved`/monkeypatch section).
        selection = {"setups": [dict(id="test-combined", market="crypto", symbols=["BTCUSDT"], tf="15m",
                                      method="COMBINED-BOOK", htf=False, mgmt="be", execution="futures")]}
        state = {}
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(selection, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()

        saved = dict(AUTOMATION_CONFIG=sr.AUTOMATION_CONFIG, SELECTION=sr.SELECTION, STATE=sr.STATE,
                     fetch_candles=sr.fetch_candles, log=sr.log, setups=sr.setups, setups_wyckoff=sr.setups_wyckoff,
                     htf_pass=sr.htf_pass, allowed_methods=sr.allowed_methods, load_setups=sr.load_setups,
                     place_limit=sr.place_limit, place_market=sr.place_market, event_blackout=sr.event_blackout,
                     from_signal=sr.EP.from_signal)
        placed_kwargs, spy_calls = [], []
        real_from_signal = sr.EP.from_signal

        def spy_from_signal(*a, **k):
            recs = real_from_signal(*a, **k)
            spy_calls.append(recs)
            return recs

        def fake_place_limit(sym, st, sig, equity, risk_mult, live, **kw):
            placed_kwargs.append(kw); return None

        candles80 = [dict(time=f"2026-01-01T{(m // 60) % 24:02d}:{m % 60:02d}:00Z", open=100, high=101, low=99, close=100, volume=1) for m in range(0, 80 * 15, 15)]
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
        sr.fetch_candles = lambda *a, **k: list(candles80)
        sr.log = lambda *a, **k: None
        sr.event_blackout = lambda *a, **k: None
        sr.setups = lambda method, side, c, tf, *a, **k: ([dict(self.ONE_SIG, side=side)] if side == "long" else [])
        # `sym` is passed by the caller since 2026-09-19: setups_wyckoff needs it to read the symbol's own
        # volume kind (traded vs MT5 tick count -- wyckoff_rules R0, WMT p131-133). A stub that omits it
        # raises TypeError inside the tick and the test sees "no signals" instead of the real reason.
        sr.setups_wyckoff = lambda method, side, c, tf, sym=None: ([dict(self.ONE_SIG, side=side)] if side == "long" else [])
        sr.htf_pass = lambda *a, **k: True
        # COMBINED-BOOK is runnable=false (docs/architecture/methods.json): load_setups() filters it out
        # (`if s.get("method") in METHODS`, METHODS = mreg.runnable()) before allowed_methods() is even asked,
        # and allowed_methods() would exclude it too -- both are step 1/3's own concern (tested elsewhere:
        # load_setups by TestLoadSetups, the preset gate by PresetFilter). This test is about step 11 (one
        # expectation record per dimension a TWO-dimension method requires), and COMBINED-BOOK is the only
        # surviving RUNNER_METHODS entry with requires=["wyckoff","ict"] (COMBINED and PARTIAL, the other two,
        # were removed 2026-09-19 -- docs/audits/2026-09-19-knowledge-fidelity.md finding 6); mocking both
        # gates open is what lets step 11 be exercised at all despite COMBINED-BOOK never reaching a real live
        # tick through either of them.
        sr.load_setups = lambda: [dict(selection["setups"][0])]
        sr.allowed_methods = lambda *a, **k: {"COMBINED-BOOK"}
        sr.place_limit = fake_place_limit
        sr.place_market = lambda *a, **k: None
        sr.EP.from_signal = spy_from_signal
        try:
            sr.tick(live=False, tick_time=sr.parse_t("2026-01-02T00:01:00Z"), ignore_gate=True)
        finally:
            for k, v in saved.items():
                if k == "from_signal":
                    sr.EP.from_signal = v
                else:
                    setattr(sr, k, v)
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
        return placed_kwargs, spy_calls

    def test_combined_setup_yields_one_record_per_dimension(self):
        _placed, spy_calls = self._run()
        self.assertEqual(len(spy_calls), 1, "expectation records must be computed exactly once per decision")
        methodologies = sorted(r["original"]["methodology"] for r in spy_calls[0])
        self.assertEqual(methodologies, ["ict", "wyckoff"])

    def test_the_plan_carries_the_same_record_ids_step_11_named(self):
        placed_kwargs, spy_calls = self._run()
        self.assertEqual(len(placed_kwargs), 1, "place_limit must have been called exactly once")
        got_ids = [r["id"] for r in placed_kwargs[0]["expectations"]]
        want_ids = [r["id"] for r in spy_calls[0]]
        self.assertEqual(got_ids, want_ids)


class Sizing(unittest.TestCase):
    def test_risk_never_above_the_ceiling_and_notional_capped(self):
        # Asserts against the ceiling constant, not a literal. This test read `0.01` until 2026-09-13, when the
        # user raised the per-trade ceiling to 3 % together with the 3R planned-R:R floor; a literal here means
        # the test has to be edited every time the policy moves, and an edit is a chance to weaken it by mistake.
        # The invariant being protected is "sizing never exceeds the configured ceiling", not any one number.
        self.assertLessEqual(sr.RISK_PCT, sr.RISK_CEILING)
        qty, risk = sr.size(10000, 100.0, 99.0, 1.0)
        self.assertAlmostEqual(risk, 10000 * sr.RISK_PCT)
        self.assertLessEqual(qty * 100.0, 10000 * sr.NOTIONAL_CAP_PCT * sr.futures_leverage() + 1e-9)
        qty2, _ = sr.size(10000, 100.0, 99.99, 1.0)
        self.assertAlmostEqual(qty2 * 100.0, 10000 * sr.NOTIONAL_CAP_PCT * sr.futures_leverage())

    def test_mt5_lots_from_contract_data(self):
        sr._MT5_SYMBOLS["XAUUSD"] = dict(tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_max=1.0, volume_step=0.01, digits=2)
        lots, risk, per_lot = sr.mt5_lots("XAUUSD", 10000, 2000.0, 1990.0, 1.0)      # 10 $ stop = 1000 ticks x 1 $ = 1000 $/lot
        self.assertAlmostEqual(risk, 10000 * sr.RISK_PCT)
        self.assertLessEqual(lots * per_lot, risk + 1e-9)
        # Step check via the QUOTIENT, not `lots % step`. Float modulo on a step this small returns the step
        # itself rather than 0 for most multiples: 0.3 % 0.01 == 0.00999999999999998, while 0.1 % 0.01 == 3.5e-18.
        # The old `lots % 0.01` assertion passed only because 1 % risk happened to land on 0.1 lots; raising the
        # ceiling to 3 % moved it to 0.3 and the test failed on a perfectly valid size (0.3 / 0.01 == 30.0).
        self.assertAlmostEqual(lots / 0.01, round(lots / 0.01), places=6)


class Gate(unittest.TestCase):
    def _gate_with(self, cfg):
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, tmp); tmp.close()
        old = sr.AUTOMATION_CONFIG; sr.AUTOMATION_CONFIG = tmp.name
        try:
            return sr.automation_gate()
        finally:
            sr.AUTOMATION_CONFIG = old; os.unlink(tmp.name)

    def base(self, **exe):
        return {"enabled": True, "layers": {"pilot": True}, "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}}, "execution": {"environment": "demo", **exe}}

    def test_refuses_real_environment(self):
        self.assertIn("REAL", self._gate_with(self.base(environment="real")) or "")

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
        # The script is copied to a temp dir, so its __file__-derived ROOT would point outside the repo -- pin
        # ROOT before overriding BRIDGE, otherwise it can no longer import scripts/instruments.py for the
        # allowlist it now derives instead of hard-coding.
        script = (open(os.path.join(ROOT, "scripts", "mt5-order-bridge.py")).read()
                  .replace('ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))', f'ROOT = {ROOT!r}')
                  # BRIDGE became a two-line assignment when the folder was made per-account
                  # (MT5_BRIDGE_SUBDIR, 2026-09-19); match the whole of it, and assert the match so this
                  # patch cannot silently stop applying and leave the test pointing at the real bridge.
                  )
        anchor = ('BRIDGE = os.path.join(ROOT, "data", "live", "mt5-bridge",\n'
                  '                      os.environ.get("MT5_BRIDGE_SUBDIR", "bridge"))')
        self.assertIn(anchor, script, "the connector's BRIDGE assignment moved; update this patch")
        script = script.replace(anchor, f'BRIDGE = {bridge!r}')
        sp = os.path.join(tmp, "bridge.py"); open(sp, "w").write(script)
        try:
            out = json.loads(subprocess.run(["python3", sp, "check"], capture_output=True, text=True, env=env).stdout); self.assertTrue(out["demo"]); self.assertIn("XAUUSD", out["symbols"])
            out = json.loads(subprocess.run(["python3", sp, "limit", "XAUUSD", "buy", "0.05", "2400.00", "2390.00", "2425.00", "t5-test"], capture_output=True, text=True, env=env).stdout)
            self.assertTrue(out["ok"]); self.assertEqual(out["ticket"], 4242)
            # Off-allowlist probe. Was EURUSD; that is about to become a real allowlisted symbol (2026-09-17
            # Forex decision), and this assertion is about the bridge's allowlist, never about currency pairs.
            r = subprocess.run(["python3", sp, "limit", "NOTAREALSYM", "buy", "0.05", "1", "0.9", "1.1"], capture_output=True, text=True, env=env); self.assertEqual(r.returncode, 2)
        finally:
            stop.set(); th.join(timeout=1)


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
        self.assertEqual(rc, 0); self.assertIn("--horizons", calls[0]); self.assertIn("1y", calls[0])
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
                "execution": {"environment": "demo"}}

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
        self.assertEqual(got, {"WYCKOFF-BOOK"})
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
        def recording_manage_pending(sym, pend, live, bars_elapsed, t=None):
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
               "execution": {"environment": "demo"}}
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
               "execution": {"environment": "demo"}}
        selection = {"setups": [dict(id="grandfather-test", market="crypto", symbols=["BTCUSDT"], tf="30m",
                                      method="ICT", htf=False, mgmt="be", execution="futures")]}
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
                                      method="ICT", htf=False, mgmt="be", execution="futures")]}
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
               "execution": {"environment": "demo"}}
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
                                             execution="futures", mgmt="be", leverage=sr.futures_leverage(), qty="1", price="100",
                                             stop="99", tp="103", order_id="1", client_id="c1", placed_at="2026-01-01T00:00:00Z",
                                             bars_waited=0, expires_bar_left=5, htf_pass=True,
                                             sweep_time=None, mss_time=None)},
                "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}

    _BALANCE_ROW = {"asset": "USDT", "balance": "10000.00", "crossUnPnl": "0.00", "availableBalance": "10000.00"}

    def _run_live_tick(self, state, order_json_fn):
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}, "cfd": {"enabled": True, "instruments": []}},
               "execution": {"environment": "demo"}}
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
        sr.manage_pending = lambda sym, pend, live, bars_elapsed, t=None: ("filled", 1.0, 100.0, None)
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


class SessionStepWiring(unittest.TestCase):
    """A4 -- decision-order.json step 4 emits tr.ok/tr.block from account_profile.entry_gate's own
    session_restrictions finding instead of unconditionally tr.skip()'ing the step. Full behavioural proof
    (a session_restrictions rule actually refusing/passing on a dry tick) lives in
    scripts/tests/test_account_profile.py::AccountLimitsOnTheOrderPath, which already owns the tick() harness
    and the account-profile fixtures this needs; this checks the wiring at the source."""

    def test_session_is_no_longer_unconditionally_skipped(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertNotIn('tr.skip("session"', src)
        self.assertIn('tr.block("session"', src)
        self.assertIn('tr.ok("session"', src)

    def test_the_session_finding_comes_from_entry_gate_not_a_second_reader(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn('f["rule"] == "session_restrictions"', src)


class Drill(unittest.TestCase):
    """docs/plans/2026-09-18-close-feature-gaps.md §0.11: the demo-only drill that proves signal -> order -> page."""

    def _candles(self, n=40, close=100.0):
        return [dict(time=f"2026-01-01T{(m // 60) % 24:02d}:{m % 60:02d}:00Z", open=close, high=close + 1, low=close - 1,
                     close=close, volume=1) for m in range(0, n * 15, 15)]

    def test_synthetic_signal_is_a_3r_market_entry_at_the_last_close(self):
        c = self._candles()
        for side in ("long", "short"):
            sig = sr.drill_signal(c, side)
            self.assertTrue(sig["entry_now"]); self.assertTrue(sig["drill"])
            self.assertEqual(sig["entry"], c[-1]["close"]); self.assertEqual(sig["time"], c[-1]["time"])
            risk = abs(sig["entry"] - sig["stop"]); reward = abs(sig["target"] - sig["entry"])
            self.assertAlmostEqual(reward / risk, sr.DRILL_RR, places=9)
            self.assertEqual(sig["r_planned"], sr.DRILL_RR)
            self.assertGreaterEqual(risk, sr.DRILL_MIN_STOP_PCT * sig["entry"])
            if side == "long":
                self.assertLess(sig["stop"], sig["entry"]); self.assertGreater(sig["target"], sig["entry"])
            else:
                self.assertGreater(sig["stop"], sig["entry"]); self.assertLess(sig["target"], sig["entry"])

    def test_too_few_bars_is_refused(self):
        with self.assertRaises(ValueError):
            sr.drill_signal(self._candles(n=10), "long")

    def test_client_id_of_a_drill_is_prefixed_so_the_venue_audit_can_find_it(self):
        sig = sr.drill_signal(self._candles(), "long")
        self.assertTrue(sr.client_id("s", "BTCUSDT", sig).startswith("drill-"))
        self.assertTrue(sr.client_id("s", "BTCUSDT", dict(sig, drill=False)).startswith("t5-"))

    def test_parse_drill(self):
        self.assertEqual(sr.parse_drill("crypto-x:BTCUSDT:long"), {"setup": "crypto-x", "symbol": "BTCUSDT", "side": "long"})
        for bad in ("", "a:b", "a:b:c:d", "a:b:sideways", "a::long"):
            with self.assertRaises(ValueError):
                sr.parse_drill(bad)

    def test_refusals_cover_every_condition_that_would_make_the_order_real_or_unasked(self):
        d = {"setup": "s1", "symbol": "BTCUSDT", "side": "long"}
        ok = dict(live=True, env_name="demo", config_env="demo", gate_reason=None, setups_known={"s1"}, symbols_enabled={"BTCUSDT"})
        self.assertIsNone(sr.drill_refusal(d, **ok))
        self.assertIn("--live", sr.drill_refusal(d, **dict(ok, live=False)))
        self.assertIn("real", sr.drill_refusal(d, **dict(ok, env_name="real")))
        self.assertIn("execution.environment", sr.drill_refusal(d, **dict(ok, config_env="real")))
        self.assertIn("gate", sr.drill_refusal(d, **dict(ok, gate_reason="pilot layer disabled")))
        self.assertIn("no selected setup", sr.drill_refusal(d, **dict(ok, setups_known={"other"})))
        self.assertIn("not an enabled", sr.drill_refusal(d, **dict(ok, symbols_enabled={"ETHUSDT"})))

    def test_a_drill_tick_evaluates_only_the_drill_and_the_plan_carries_the_flag(self):
        """The real detectors are silenced on a drill tick; the synthetic signal walks the same steps and the
        resulting plan says `drill: true` so the journal can keep it out of every rollup."""
        import tempfile
        placed = []
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump({"enabled": True, "execution": {"environment": "demo"}, "layers": {"pilot": True}, "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}}}, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"setups": [dict(id="s1", market="crypto", tf="15m", method="WYCKOFF-BOOK", htf=False, mgmt="none", execution="futures", symbols=["BTCUSDT"], rule_version="v1")]}, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); state_tmp.write("{}"); state_tmp.close()
        saved = {k: getattr(sr, k) for k in ("AUTOMATION_CONFIG", "SELECTION", "STATE", "STOP", "fetch_candles", "log", "event_blackout", "setups", "setups_wyckoff", "htf_pass", "place_limit", "place_market", "automation_gate", "allowed_methods", "load_state", "save_state")}
        try:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
            sr.STOP = state_tmp.name + ".no-such-stop-file"      # the real kill switch is present on this machine; the test must not read it
            candles = self._candles(n=120)
            sr.fetch_candles = lambda *a, **k: list(candles)
            sr.log = lambda *a, **k: None
            sr.event_blackout = lambda *a, **k: None
            sr.automation_gate = lambda: None
            sr.allowed_methods = lambda *a, **k: {"WYCKOFF-BOOK"}     # the preset filter is step 3's own concern (PresetFilter tests it)
            real_detector_calls = []
            sr.setups = lambda *a, **k: real_detector_calls.append(a) or [dict(time="2026-01-01T00:00:00Z", side="long", entry=1, stop=0.5, target=3, r_planned=4.0, vol_type=1, mss_time=None, bars_left=0)]
            sr.setups_wyckoff = sr.setups
            sr.htf_pass = lambda *a, **k: True
            def fake_place_market(sym, st, sig, equity, risk_mult, live, **kw):
                placed.append((sym, st["id"], sig)); return None
            sr.place_market = fake_place_market
            sr.place_limit = lambda *a, **k: placed.append(("limit",)) or None
            sr.tick(True, sr.parse_t("2026-01-02T00:00:00Z"), drill={"setup": "s1", "symbol": "BTCUSDT", "side": "long"})
        finally:
            for k, v in saved.items():
                setattr(sr, k, v)
        self.assertEqual(len(placed), 1, placed)
        sym, sid, sig = placed[0]
        self.assertEqual((sym, sid, sig["side"]), ("BTCUSDT", "s1", "long"))
        self.assertTrue(sig["drill"]); self.assertTrue(sig["entry_now"])
        plan = sr.plan_of(sym, {"id": sid, "tf": "15m", "method": "WYCKOFF-BOOK", "execution": "futures"}, sig, "1", sig["entry"], sig["stop"], sig["target"], 10.0)
        self.assertTrue(plan["drill"])
        plan_real = sr.plan_of(sym, {"id": sid, "tf": "15m", "method": "WYCKOFF-BOOK", "execution": "futures"}, dict(sig, drill=False), "1", sig["entry"], sig["stop"], sig["target"], 10.0)
        self.assertFalse(plan_real["drill"])


class TraderOverlayOnTheLivePath(unittest.TestCase):
    """plan §0.9: a trader's constraints can only TIGHTEN the live walk; without a trader nothing changes."""

    ONE = dict(time="2026-01-01T00:00:00Z", side="long", entry=100.0, stop=99.0, target=103.2, r_planned=3.2, vol_type=1,
               mss_time=None, bars_left=0, entry_now=True)

    def _run(self, *, trader, registry, method="ICT", tick_time="2026-01-02T00:00:00Z"):
        import tempfile
        placed, logs = [], []
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump({"enabled": True, "execution": {"environment": "demo", "trader": trader}, "layers": {"pilot": True}, "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}}}, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump({"setups": [dict(id="s1", market="crypto", tf="15m", method=method, htf=False, mgmt="none", execution="futures", symbols=["BTCUSDT"], rule_version="v1")]}, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); state_tmp.write("{}"); state_tmp.close()
        keys = ("AUTOMATION_CONFIG", "SELECTION", "STATE", "STOP", "fetch_candles", "log", "event_blackout", "setups", "setups_wyckoff", "htf_pass", "place_limit", "place_market", "automation_gate", "allowed_methods")
        saved = {k: getattr(sr, k) for k in keys}; saved_ft = sr.TC.for_trader
        try:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
            sr.STOP = state_tmp.name + ".no-such-stop-file"
            candles = [dict(time=f"2026-01-01T{(m // 60) % 24:02d}:{m % 60:02d}:00Z", open=100, high=101, low=99, close=100, volume=1) for m in range(0, 120 * 15, 15)]
            sr.fetch_candles = lambda *a, **k: list(candles)
            sr.log = lambda kind, venue="futures", **kw: logs.append((kind, kw))
            sr.event_blackout = lambda *a, **k: None
            sr.automation_gate = lambda: None
            sr.allowed_methods = lambda *a, **k: {"ICT", "WYCKOFF-BOOK"}
            sr.setups = lambda m, side, c, tf, *a, **k: ([dict(self.ONE)] if side == "long" else [])
            sr.setups_wyckoff = lambda m, side, c, tf, sym=None: ([dict(self.ONE)] if side == "long" else [])
            sr.htf_pass = lambda *a, **k: True
            sr.place_market = lambda sym, st, sig, equity, risk_mult, live, **kw: placed.append(sig) or None
            sr.place_limit = lambda sym, st, sig, equity, risk_mult, live, **kw: placed.append(sig) or None
            sr.TC.for_trader = lambda tid: registry
            sr.tick(True, sr.parse_t(tick_time))
        finally:
            for k, v in saved.items():
                setattr(sr, k, v)
            sr.TC.for_trader = saved_ft
        sigs = [kw for kind, kw in logs if kind == "signal"]
        return placed, sigs

    def test_no_trader_leaves_the_walk_unchanged(self):
        placed, sigs = self._run(trader=None, registry={})
        self.assertEqual(len(placed), 1, sigs)

    def test_a_trader_floor_refuses_what_the_platform_floor_admits(self):
        placed, sigs = self._run(trader="t", registry={"ict": [{"kind": "min_rr", "value": 3.5}]})
        self.assertEqual(placed, [])
        self.assertTrue(any("sàn riêng của trader" in r for sg in sigs for r in sg["reasons"]), sigs)

    def test_a_trader_floor_cannot_loosen_the_platform_floor(self):
        # a declared 2.0 would be refused at import by trader_constraints; here overlay() itself takes max()
        ov = sr.TC.overlay({"min_rr": sr.MIN_RR}, "t", "ict") if False else None
        self.assertIsNone(sr.rr_reason(dict(self.ONE), "futures", floor=1.0))       # floor below MIN_RR: ignored
        self.assertIsNotNone(sr.rr_reason(dict(self.ONE), "futures", floor=3.5))    # floor above: applied

    def test_a_trader_session_set_refuses_outside_it(self):
        placed, sigs = self._run(trader="t", registry={"wyckoff": [{"kind": "sessions", "value": ["london"]}]},
                                 method="WYCKOFF-BOOK", tick_time="2026-01-02T02:00:00Z")   # 02:00Z = Asia
        self.assertEqual(placed, [])
        self.assertTrue(any("trader t" in r and "phiên" in r for sg in sigs for r in sg["reasons"]), sigs)

    def test_overlay_merges_bool_flags_onto_the_setup_copy(self):
        saved = sr.TC.for_trader
        try:
            sr.TC.for_trader = lambda tid: {"ict": [{"kind": "htf", "value": True}]}
            ov = sr.trader_overlay({"method": "ICT", "htf": False}, "t")
            self.assertTrue(ov["htf"]); self.assertEqual(ov["min_rr"], sr.MIN_RR)
            self.assertEqual(sr.trader_overlay({"method": "ICT"}, None), {})
        finally:
            sr.TC.for_trader = saved


class MarketFillIsAVenueFact(unittest.TestCase):
    """docs/audits/2026-09-18-e2e-drill.md: the fill price comes from the venue, never from the plan."""

    def test_a_result_response_with_a_price_is_used_as_is(self):
        self.assertEqual(sr.market_fill("BTCUSDT", {"orderId": 1, "avgPrice": "79767.0", "executedQty": "0.0467"}, "0.0467"), (79767.0, 0.0467))

    def test_a_zero_avg_price_is_polled_from_order_status_not_taken_from_the_plan(self):
        calls = []
        saved = sr.order_json
        try:
            sr.order_json = lambda *a: calls.append(a) or {"avgPrice": "79767.0", "executedQty": "0.0467", "status": "FILLED"}
            got = sr.market_fill("BTCUSDT", {"orderId": 7, "avgPrice": "0", "executedQty": "0.0467"}, "0.0467", polls=2, sleep=0)
        finally:
            sr.order_json = saved
        self.assertEqual(got, (79767.0, 0.0467)); self.assertEqual(calls[0][:2], ("order-status", "BTCUSDT"))

    def test_an_unreadable_fill_raises_instead_of_guessing(self):
        saved = sr.order_json
        try:
            sr.order_json = lambda *a: {"avgPrice": "0", "executedQty": "0"}
            with self.assertRaises(RuntimeError):
                sr.market_fill("BTCUSDT", {"orderId": 7, "avgPrice": "0"}, "0.0467", polls=2, sleep=0)
        finally:
            sr.order_json = saved


class Mt5CloseReadsTheSettledProfit(unittest.TestCase):
    """docs/audits/2026-09-18-e2e-drill.md §4.3: the EA's close reply says profit 0; the settled deal is in position-status."""

    def test_profit_comes_from_position_status_after_the_close_settles(self):
        calls = []
        saved = sr.mt5_json
        try:
            def fake(cmd, *a):
                calls.append(cmd)
                if cmd == "close": return {"ok": True, "price": 4353.83, "profit": 0}
                return {"ok": True, "state": "closed", "price_close": 4353.83, "profit": -44.0}
            sr.mt5_json = fake
            self.assertEqual(sr.mt5_close(1, sleep=0), (4353.83, -44.0))
        finally:
            sr.mt5_json = saved
        self.assertEqual(calls[:2], ["close", "position-status"])

    def test_an_unsettled_close_reports_profit_unknown_not_zero(self):
        saved = sr.mt5_json
        try:
            sr.mt5_json = lambda cmd, *a: {"ok": True, "price": 4353.83, "profit": 0, "state": "open"}
            px, profit = sr.mt5_close(1, polls=2, sleep=0)
        finally:
            sr.mt5_json = saved
        self.assertEqual(px, 4353.83); self.assertIsNone(profit)


class PerAccountScope(unittest.TestCase):
    """One process, one customer account: its own state, logs, candle cache and kill switch.

    docs/plans/2026-09-19-multi-account.md §0.3 item 2. Before this, `STOP` was one file for every venue and
    every account, so one customer breaching a drawdown limit halted everybody, and `top20-state.json` was one
    file written with a bare `open(..., "w")`, so two processes would have silently overwritten each other's
    positions. Scoping the paths is what makes one process per account safe to run at all.
    """

    def setUp(self):
        self._saved = (sr.ACCOUNT, sr.PILOT_DIR, sr.STATE, sr.LOG, sr.MT5_LOG, sr.STOP, sr.CANDLES,
                       dict(sr.VENUE_LOG))
        self.account = next(pid for pid, p in sr.AP.PROFILES.items()
                            if p["environment"] not in sr.AP.UNROUTABLE_ENVIRONMENTS)

    def tearDown(self):
        (sr.ACCOUNT, sr.PILOT_DIR, sr.STATE, sr.LOG, sr.MT5_LOG, sr.STOP, sr.CANDLES, vl) = self._saved
        sr.VENUE_LOG = dict(vl)

    def test_binding_none_restores_the_houses_paths_exactly(self):
        """Every existing test and the running pilot depend on this being byte-identical."""
        before = sr.PILOT_DIR
        sr.bind_account(self.account)
        self.assertNotEqual(sr.PILOT_DIR, before)
        sr.bind_account(None)
        self.assertEqual(sr.PILOT_DIR, before)
        self.assertTrue(sr.PILOT_DIR.endswith("pilot-futures"))

    def test_every_path_a_customer_owns_moves_together(self):
        sr.bind_account(self.account)
        for path in (sr.STATE, sr.LOG, sr.MT5_LOG, sr.STOP):
            self.assertIn(os.path.join("accounts", self.account), path, path)
        self.assertEqual(sr.VENUE_LOG["mt5"], sr.MT5_LOG, "the venue log map must follow the rebind")

    def test_the_candle_cache_is_SHARED_and_does_not_move(self):
        """Candles are public market data: BTCUSDT 15m is the same bytes for every customer. Per-account
        copies would multiply the feed load by N -- 26 provider calls per tick becomes 26N against a rate
        limit that is per IP, not per key -- and would let two accounts disagree about the market whenever
        their fetches landed either side of a bar close. What is per-account is what a customer owns or can
        lose; the market is not that."""
        before = sr.CANDLES
        sr.bind_account(self.account)
        self.assertEqual(sr.CANDLES, before)
        self.assertNotIn("accounts", sr.CANDLES)

    def test_an_unknown_account_refuses_rather_than_inventing_a_directory(self):
        with self.assertRaises(SystemExit) as cm:
            sr.bind_account("no-such-account")
        self.assertIn("must not guess whose rules apply", str(cm.exception))

    def test_a_research_template_cannot_be_traded(self):
        research = [pid for pid, p in sr.AP.PROFILES.items()
                    if p["environment"] in sr.AP.UNROUTABLE_ENVIRONMENTS]
        if not research:
            self.skipTest("no research profile in the registry")
        with self.assertRaises(SystemExit) as cm:
            sr.bind_account(research[0])
        self.assertIn("unroutable", str(cm.exception))


class TheKillSwitchIsTwoTier(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = (sr.STOP, sr.GLOBAL_STOP)
        sr.STOP = os.path.join(self.dir, "STOP")
        sr.GLOBAL_STOP = os.path.join(self.dir, "GLOBAL-STOP")

    def tearDown(self):
        sr.STOP, sr.GLOBAL_STOP = self._saved

    def test_neither_file_means_not_halted(self):
        self.assertFalse(sr.halted())

    def test_this_accounts_own_stop_halts_it(self):
        open(sr.STOP, "w").close()
        self.assertTrue(sr.halted())

    def test_the_estate_wide_stop_halts_it_too(self):
        """One lever that stops everything, kept alongside one lever per customer."""
        open(sr.GLOBAL_STOP, "w").close()
        self.assertTrue(sr.halted())


class OrdersCarryTheirAccount(unittest.TestCase):
    """Attribution (plan §0.3 item 1): billing, and disputes."""

    def setUp(self):
        self._saved = sr.ACCOUNT

    def tearDown(self):
        sr.ACCOUNT = self._saved

    SIG = {"side": "long", "time": "2026-09-19T14:00:00Z"}

    def test_two_accounts_on_the_same_signal_get_different_client_ids(self):
        """Without the account in the digest both mint the SAME newClientOrderId, the venue rejects the
        second as a duplicate, and one customer silently loses the trade while the rejection looks like a
        venue fault."""
        sr.ACCOUNT = "acc-a"; a = sr.client_id("setup-1", "BTCUSDT", self.SIG)
        sr.ACCOUNT = "acc-b"; b = sr.client_id("setup-1", "BTCUSDT", self.SIG)
        self.assertNotEqual(a, b)

    def test_the_same_account_and_signal_is_still_stable(self):
        sr.ACCOUNT = "acc-a"
        self.assertEqual(sr.client_id("setup-1", "BTCUSDT", self.SIG),
                         sr.client_id("setup-1", "BTCUSDT", self.SIG))

    def test_the_drill_prefix_survives(self):
        sr.ACCOUNT = "acc-a"
        self.assertTrue(sr.client_id("s", "BTCUSDT", dict(self.SIG, drill=True)).startswith("drill-"))
        self.assertTrue(sr.client_id("s", "BTCUSDT", self.SIG).startswith("t5-"))

    def test_house_mode_ids_are_unchanged_in_shape(self):
        sr.ACCOUNT = None
        self.assertTrue(sr.client_id("s", "BTCUSDT", self.SIG).startswith("t5-"))
        self.assertEqual(len(sr.client_id("s", "BTCUSDT", self.SIG)), len("t5-") + 20)


class EveryOrderSaysWhoseItIsAndUnderWhatAgreement(unittest.TestCase):
    """Attribution, end to end (plan §0.3 item 1). A customer asking "which methodology took this trade, on
    which version, under which agreement" must be answerable from the record alone -- and the same record is
    the billing line."""

    def setUp(self):
        self._saved = (sr.ACCOUNT, list(sr.MD.MANDATES))

    def tearDown(self):
        sr.ACCOUNT, rows = self._saved
        sr.MD.MANDATES = rows

    ST = {"id": "cfd-scalping-ict-15m-phase1-a", "rule_version": "abc123", "tf": "15m", "method": "ICT",
          "execution": "mt5", "mgmt": "be"}
    SIG = {"side": "long", "time": "2026-09-19T14:00:00Z", "mss_time": "2026-09-19T13:45:00Z",
           "bars_left": 5, "htf_pass": True, "r_planned": 3.2}

    def _plan(self):
        return sr.plan_of("XAUUSD", self.ST, self.SIG, "0.1", "3300", "3290", "3330", 100.0)

    def test_the_plan_names_the_setup_and_its_version(self):
        p = self._plan()
        self.assertEqual(p["strategy"], self.ST["id"])
        self.assertEqual(p["setup_version"], "abc123")

    def test_the_plan_names_the_mandate_when_one_exists(self):
        sr.ACCOUNT = "acc-x"
        sr.MD.MANDATES = [{"id": "m-77", "account": "acc-x", "setup": self.ST["id"],
                           "setup_version": "abc123", "state": "ACTIVE", "started_at": "2020-01-01"}]
        self.assertEqual(self._plan()["mandate"], "m-77")

    def test_a_setup_this_account_has_no_mandate_for_records_none_rather_than_guessing(self):
        sr.ACCOUNT = "acc-x"
        sr.MD.MANDATES = [{"id": "m-77", "account": "acc-x", "setup": "some-other-setup",
                           "setup_version": "abc123", "state": "ACTIVE", "started_at": "2020-01-01"}]
        self.assertIsNone(self._plan()["mandate"])

    def test_house_mode_records_no_mandate_because_there_is_no_agreement(self):
        sr.ACCOUNT = None
        self.assertIsNone(self._plan()["mandate"])

    def test_a_paused_mandate_is_not_the_agreement_an_order_runs_under(self):
        sr.ACCOUNT = "acc-x"
        sr.MD.MANDATES = [{"id": "m-77", "account": "acc-x", "setup": self.ST["id"],
                           "setup_version": "abc123", "state": "PAUSED", "started_at": "2020-01-01"}]
        self.assertIsNone(self._plan()["mandate"])

    def test_an_unreadable_mandate_table_does_not_stop_an_order_decided_on_other_grounds(self):
        sr.ACCOUNT = "acc-x"
        saved = sr.MD.for_account
        try:
            sr.MD.for_account = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
            self.assertIsNone(self._plan()["mandate"])
        finally:
            sr.MD.for_account = saved


class TheSharedCandleCacheIsFetchedOncePerBar(unittest.TestCase):
    """The feed, not the CPU, is what caps how many accounts a machine can serve.

    Every account runs its own process, and each one used to shell out to the provider for all 18 crypto
    (symbol, timeframe) pairs on every tick -- 18N calls into a rate limit that is per IP, not per key. The
    cache is shared and the bytes are identical for everyone, so the first runner to tick after a bar close
    refreshes it and the rest read it. Measured on this repo: a tick fell from ~5.1 s wall / 1.25 s CPU to
    ~0.85 s wall / 0.81 s CPU once the fetch was skipped.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = sr.CANDLES
        sr.CANDLES = self.dir

    def tearDown(self):
        sr.CANDLES = self._saved

    @staticmethod
    def _t(epoch):
        return datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)

    def _write(self, sym, tf, last_epoch, n=600):
        step = sr.N.tf_seconds(tf)
        candles = [{"time": sr.iso(self._t(last_epoch - (n - 1 - i) * step)),
                    "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10} for i in range(n)]
        json.dump({"candles": candles}, open(os.path.join(self.dir, f"ohlcv.{sym}.{tf}.json"), "w"))

    def test_a_cache_holding_the_last_closed_bar_is_reused(self):
        step = sr.N.tf_seconds("15m")
        now_ = 1800000000 - (1800000000 % step) + 120          # 2 minutes into a forming bar
        self._write("BTCUSDT", "15m", now_ - (now_ % step) - step)
        self.assertTrue(sr._cache_has_last_closed("BTCUSDT", "15m", 576, self._t(now_)))

    def test_a_cache_one_bar_behind_is_refetched(self):
        step = sr.N.tf_seconds("15m")
        now_ = 1800000000 - (1800000000 % step) + 120
        self._write("BTCUSDT", "15m", now_ - (now_ % step) - 2 * step)
        self.assertFalse(sr._cache_has_last_closed("BTCUSDT", "15m", 576, self._t(now_)))

    def test_a_missing_or_unreadable_cache_refetches(self):
        self.assertFalse(sr._cache_has_last_closed("NOSUCH", "15m", 10))
        open(os.path.join(self.dir, "ohlcv.BAD.15m.json"), "w").write("{ not json")
        self.assertFalse(sr._cache_has_last_closed("BAD", "15m", 10))

    def test_too_few_bars_for_the_callers_window_refetches(self):
        step = sr.N.tf_seconds("15m")
        now_ = 1800000000 - (1800000000 % step) + 120
        self._write("BTCUSDT", "15m", now_ - (now_ % step) - step, n=100)
        self.assertFalse(sr._cache_has_last_closed("BTCUSDT", "15m", 576, self._t(now_)),
                         "a 100-bar cache must not satisfy a 576-bar window")

    def test_an_unknown_timeframe_refetches_rather_than_guessing(self):
        self.assertFalse(sr._cache_has_last_closed("BTCUSDT", "3W", 10))

    def test_the_cache_is_published_atomically(self):
        """Many readers, and until the reuse check lands everywhere, possibly several writers. `> file`
        truncates in place and a concurrent reader gets whatever bytes exist at that instant."""
        src = open(os.path.join(ROOT, "scripts", "fetch-binance-klines.sh"), encoding="utf-8").read()
        self.assertIn('mv -f "$OUT_FILE.tmp.$$" "$OUT_FILE"', src)
        self.assertNotIn("""  }' > "$OUT_FILE\"""", src)

    def test_the_quality_gate_still_runs_on_a_reused_cache(self):
        """A cache this check wrongly accepts must still be caught before it is traded on, not after."""
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        i = src.index("def _cache_has_last_closed")
        j = src.index("if market == \"crypto\":")
        block = src[j:j + 1200]
        self.assertIn("_require_quality", block, "the freshness gate must run whether or not the fetch ran")


class SeveralMt5TerminalsCanShareOneMachine(unittest.TestCase):
    r"""One machine is NOT limited to one CFD account.

    An MT5 terminal is logged into exactly one account, so N customers need N terminals -- but terminals in
    one installation share `Common\Files`, and this connector CONSUMES res-<id>.json (reads it, then deletes
    it). Two accounts pointed at one folder would race to eat each other's replies and one customer's fill
    could be reported to another. Each terminal therefore gets its own folder: the EA's InpBridgeDir input,
    and the matching MT5_BRIDGE_SUBDIR on the runner side.

    Measured on this machine 2026-09-19: a running terminal64.exe is ~142 MB RSS, so the limit is the number
    of terminals a host can run, not memory on a 36 GB box. MT5 runs on macOS through the vendor's own
    Wine-wrapped build (docs/architecture/mt5-bridge.md:27-31); only MetaQuotes' Python package is
    Windows-only, and this project deliberately does not use it (mt5-bridge.md:14).
    """

    def setUp(self):
        self._saved = sr.ACCOUNT

    def tearDown(self):
        sr.ACCOUNT = self._saved

    def test_house_mode_keeps_the_original_folder(self):
        sr.ACCOUNT = None
        self.assertEqual(sr.mt5_bridge_subdir(), "bridge")

    def test_each_account_gets_its_own_folder(self):
        sr.ACCOUNT = "acc-001"; a = sr.mt5_bridge_subdir()
        sr.ACCOUNT = "acc-002"; b = sr.mt5_bridge_subdir()
        self.assertNotEqual(a, b)
        self.assertIn("acc-001", a)

    def test_the_connector_reads_the_folder_from_the_environment(self):
        src = open(os.path.join(ROOT, "scripts", "mt5-order-bridge.py"), encoding="utf-8").read()
        self.assertIn('os.environ.get("MT5_BRIDGE_SUBDIR", "bridge")', src)

    def test_the_runner_passes_it_on_every_bridge_call(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        self.assertIn("MT5_BRIDGE_SUBDIR=mt5_bridge_subdir()", src)

    def test_the_ea_takes_it_as_an_input_and_says_it_is_compiled_in(self):
        src = open(os.path.join(ROOT, "integrations", "mt5", "OrderBridge.mq5"), encoding="utf-8").read()
        self.assertIn("input string InpBridgeDir", src)
        self.assertIn("COMPILED INPUT", src)
        self.assertIn("g_dir = (StringLen(InpBridgeDir) > 0)", src,
                      "the input must actually replace the hardcoded folder at OnInit")


class TheTerminalMustBeTheAccountWeThinkItIs(unittest.TestCase):
    """Defence in depth for multi-account MT5 (user question 2026-09-19: "can account ids fix the file mix-up?").

    The first half is isolation by construction -- each terminal gets its own command/response folder, so files
    cannot cross. This is the second half: it assumes that failed anyway (a symlink repointed, a terminal
    restarted on the wrong login, a folder name typed once and wrongly) and turns the consequence from
    "customer A's order placed on customer B's account" into a logged refusal.

    The asymmetry is the reason it is worth a round trip: isolation-only fails SILENTLY and in the worst
    direction. Identity-only is worse still -- it would let every terminal see every command and rely on a
    filter being correct in two places.
    """

    def setUp(self):
        self._saved = (sr.ACCOUNT, dict(sr._env), sr._MT5_IDENTITY_OK, sr.mt5_json)
        sr._MT5_IDENTITY_OK = None

    def tearDown(self):
        sr.ACCOUNT, env, sr._MT5_IDENTITY_OK, sr.mt5_json = self._saved
        sr._env.clear(); sr._env.update(env)

    def _terminal(self, login):
        sr.mt5_json = lambda *a, **k: {"login": login, "equity": 1000.0, "trade_mode": "demo"}

    def test_a_matching_login_passes(self):
        sr.ACCOUNT = "acc-001"; sr._env["MT5_ACCOUNT_LOGIN"] = "12345"
        self._terminal(12345)
        self.assertTrue(sr.mt5_assert_identity())

    def test_a_different_login_refuses_and_says_which_folder_is_wrong(self):
        sr.ACCOUNT = "acc-001"; sr._env["MT5_ACCOUNT_LOGIN"] = "12345"
        self._terminal(99999)
        with self.assertRaises(RuntimeError) as cm:
            sr.mt5_assert_identity()
        msg = str(cm.exception)
        self.assertIn("99999", msg)
        self.assertIn("12345", msg)
        self.assertIn("bridge-acc-001", msg, "the refusal must name the folder that reached the wrong terminal")

    def test_an_account_run_with_no_configured_login_refuses_rather_than_trusting_whoever_answers(self):
        sr.ACCOUNT = "acc-001"; sr._env.pop("MT5_ACCOUNT_LOGIN", None)
        self._terminal(12345)
        with self.assertRaises(RuntimeError) as cm:
            sr.mt5_assert_identity()
        self.assertIn("whoever happens to be logged in", str(cm.exception))

    def test_house_mode_without_a_login_is_unchanged(self):
        """The existing single-account pilot must not start refusing because a new check appeared."""
        sr.ACCOUNT = None; sr._env.pop("MT5_ACCOUNT_LOGIN", None)
        self._terminal(12345)
        self.assertTrue(sr.mt5_assert_identity())

    def test_it_is_checked_once_per_process_not_per_order(self):
        sr.ACCOUNT = "acc-001"; sr._env["MT5_ACCOUNT_LOGIN"] = "12345"
        calls = []
        sr.mt5_json = lambda *a, **k: (calls.append(a) or {"login": 12345, "trade_mode": "demo"})
        sr.mt5_assert_identity(); sr.mt5_assert_identity(); sr.mt5_assert_identity()
        self.assertEqual(len(calls), 1, "a terminal does not change account mid-run; this is the order path")

    def test_the_equity_read_goes_through_it(self):
        src = open(os.path.join(ROOT, "scripts", "strategy-runner.py"), encoding="utf-8").read()
        i = src.index("def mt5_equity()")
        self.assertIn("mt5_assert_identity()", src[i:i + 700])


# ==================================================================================================
# 2026-09-24 system audit, round 1 (docs/audits/2026-09-24-system-audit.md): live order safety and fees.
# ==================================================================================================


class DEC1_EventRiskCancelsARestingOrder(unittest.TestCase):
    """A RESTING order must not be allowed to keep working into an event-risk blackout that opened AFTER it
    was placed (CLAUDE.md §24/§31/§32). Before this fix, manage_pending() never consulted event risk at all."""

    def _pend(self, execution="futures", tf="15m"):
        return dict(execution=execution, order_id="o1", tf=tf, price="100", qty="1", stop="99", tp="103",
                    expires_bar_left=5, bars_waited=0)

    def test_cancel_succeeds_not_filled_returns_gone(self):
        """Code review fix round 1 (DEC-1a): the cancel-then-recheck must actually RE-QUERY order status
        (not just trust the cancel) -- order_json is wired to answer BOTH the cancel-order call and a
        subsequent order-status call, and the latter says NEW/unfilled."""
        old_blackout, old_sh, old_log, old_oj = sr.event_blackout, sr.sh, sr.log, sr.order_json
        sh_calls, oj_calls, logs = [], [], []
        sr.event_blackout = lambda t, sym: "HIGH event window active"
        sr.sh = lambda *a, **k: sh_calls.append((a, k)) or ""

        def order_json_fn(*a, **k):
            oj_calls.append(a)
            return {"status": "CANCELED", "executedQty": "0"}
        sr.order_json = order_json_fn
        sr.log = lambda *a, **k: logs.append((a, k))
        try:
            state, qty, px, pt = sr.manage_pending("BTCUSDT", self._pend(), live=True, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout, sr.sh, sr.log, sr.order_json = old_blackout, old_sh, old_log, old_oj
        self.assertEqual((state, qty, px, pt), ("gone", None, None, None))
        self.assertTrue(sh_calls, "the resting order must be cancelled the way the STOP kill switch cancels one")
        args, kwargs = sh_calls[0]
        self.assertEqual(args[1], "cancel-order")
        self.assertEqual(kwargs.get("check"), False)
        self.assertEqual(oj_calls, [("order-status", "BTCUSDT", "o1")],
                         "manage_pending must re-query order status AFTER the cancel, not assume it worked")
        self.assertEqual([a[0] for a, _ in logs], ["event_cancel_pending"])

    def test_filled_before_cancel_returns_filled_not_gone(self):
        """Code review fix round 1 (DEC-1b, BLOCKING): the venue may have matched the order in the instant
        before the cancel reached it. manage_pending() must report this as a FILL (so _tick()'s existing
        'state == filled' branch calls open_position(), which places the protective stop), never as 'gone' --
        'gone' makes _tick() delete the pending entry as if nothing happened, leaving a real, unprotected,
        untracked position on the exchange."""
        old_blackout, old_sh, old_log, old_oj = sr.event_blackout, sr.sh, sr.log, sr.order_json
        sr.event_blackout = lambda t, sym: "HIGH event window active"
        sr.sh = lambda *a, **k: ""
        sr.order_json = lambda *a, **k: {"status": "FILLED", "executedQty": "1", "avgPrice": "100.5"}
        sr.log = lambda *a, **k: None
        try:
            state, qty, px, pt = sr.manage_pending("BTCUSDT", self._pend(), live=True, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout, sr.sh, sr.log, sr.order_json = old_blackout, old_sh, old_log, old_oj
        self.assertEqual((state, qty, px, pt), ("filled", 1.0, 100.5, None))

    def test_partial_fill_before_cancel_protects_only_the_filled_quantity(self):
        """Code review fix round 1 (DEC-1c): a partial fill (executedQty > 0 but status not FILLED, e.g. the
        cancel raced a partial match) must still be reported as a fill for the EXECUTED quantity -- exactly
        the same shape the pre-existing expiry-cancel branch already uses for this case (line ~1645)."""
        old_blackout, old_sh, old_log, old_oj = sr.event_blackout, sr.sh, sr.log, sr.order_json
        sr.event_blackout = lambda t, sym: "HIGH event window active"
        sr.sh = lambda *a, **k: ""
        sr.order_json = lambda *a, **k: {"status": "CANCELED", "executedQty": "0.4", "avgPrice": "100.25"}
        sr.log = lambda *a, **k: None
        try:
            state, qty, px, pt = sr.manage_pending("BTCUSDT", self._pend(), live=True, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout, sr.sh, sr.log, sr.order_json = old_blackout, old_sh, old_log, old_oj
        self.assertEqual((state, qty, px, pt), ("filled", 0.4, 100.25, None))

    def test_a_full_tick_opens_a_protected_position_when_the_fill_races_the_cancel(self):
        """End-to-end (DEC-1b): a full sr.tick(live=True) with a resting pending order, an active blackout,
        and a venue that reports the order FILLED when re-checked after the cancel -- the position must land
        in state with its protective stop already placed, exactly like any other fill."""
        cfg = {"enabled": True, "layers": {"pilot": True},
               "markets": {"crypto": {"enabled": True, "instruments": ["BTCUSDT"]}, "cfd": {"enabled": True, "instruments": []}},
               "execution": {"environment": "demo"}}
        state = {"started": "2026-01-01T00:00:00Z", "positions": {}, "day": None, "trades_today": {}, "errors": 0,
                 "halted": None, "last_tick": None, "seen": [], "equity_basis": "equity",
                 "pending": {"BTCUSDT": dict(symbol="BTCUSDT", side="LONG", strategy="x", tf="15m", method="ICT",
                                             execution="futures", mgmt="be", leverage=3, qty="1", price="100",
                                             stop="99", tp="103", order_id="1", client_id="c1",
                                             placed_at="2026-01-01T00:00:00Z", bars_waited=0, expires_bar_left=5,
                                             htf_pass=True, sweep_time=None, mss_time=None)},
                 "venues": {v: {"equity_start": 10000.0, "closed": [], "consec_losses": 0} for v in sr.VENUES}}
        cfg_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(cfg, cfg_tmp); cfg_tmp.close()
        sel_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump({"setups": []}, sel_tmp); sel_tmp.close()
        state_tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(state, state_tmp); state_tmp.close()
        stop_path = state_tmp.name + ".STOP"; global_stop_path = state_tmp.name + ".GLOBAL_STOP"  # guaranteed absent

        old = dict(cfg=sr.AUTOMATION_CONFIG, sel=sr.SELECTION, state=sr.STATE, gate=sr.automation_gate,
                  order_json=sr.order_json, mt5_json=sr.mt5_json, fetch_candles=sr.fetch_candles, log=sr.log,
                  manage_position=sr.manage_position, event_blackout=sr.event_blackout, sh=sr.sh,
                  stop=sr.STOP, global_stop=sr.GLOBAL_STOP)
        sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = cfg_tmp.name, sel_tmp.name, state_tmp.name
        sr.STOP, sr.GLOBAL_STOP = stop_path, global_stop_path
        sr.automation_gate = lambda: None
        sr.event_blackout = lambda t, sym: "HIGH event window active"
        sr.sh = lambda *a, **k: ""
        _BALANCE_ROW = {"asset": "USDT", "balance": "10000.00", "crossUnPnl": "0.00", "availableBalance": "10000.00"}

        def order_json_fn(*a, **k):
            cmd = a[0] if a else None
            if cmd == "balance":
                return [_BALANCE_ROW]
            if cmd == "order-status":
                return {"status": "FILLED", "executedQty": "1", "avgPrice": "100.5"}
            if cmd == "stop-market":
                return {"orderId": 501}
            if cmd == "take-profit-market":
                return {"orderId": 502}
            if cmd in ("position-risk", "open-orders"):
                return []
            return {}
        sr.order_json = order_json_fn
        sr.mt5_json = lambda *a, **k: {}
        sr.fetch_candles = lambda *a, **k: []
        sr.log = lambda *a, **k: None
        sr.manage_position = lambda *a, **k: None
        try:
            sr.tick(live=True, tick_time=sr.now(), ignore_gate=False)
            out = json.load(open(state_tmp.name))
        finally:
            sr.AUTOMATION_CONFIG, sr.SELECTION, sr.STATE = old["cfg"], old["sel"], old["state"]
            sr.STOP, sr.GLOBAL_STOP = old["stop"], old["global_stop"]
            sr.automation_gate, sr.order_json, sr.mt5_json = old["gate"], old["order_json"], old["mt5_json"]
            sr.fetch_candles, sr.log, sr.manage_position = old["fetch_candles"], old["log"], old["manage_position"]
            sr.event_blackout, sr.sh = old["event_blackout"], old["sh"]
            os.unlink(cfg_tmp.name); os.unlink(sel_tmp.name); os.unlink(state_tmp.name)
            for p in (stop_path, global_stop_path):
                if os.path.exists(p):
                    os.unlink(p)
        self.assertNotIn("BTCUSDT", out["pending"], "the fill must clear the pending entry, not leave it stuck")
        self.assertIn("BTCUSDT", out["positions"], "a real fill discovered after the cancel must become a tracked position")
        self.assertEqual(out["positions"]["BTCUSDT"]["stop_order"], 501,
                         "the protective stop must have been placed -- this is the whole point of DEC-1b")

    def test_an_active_blackout_cancels_a_resting_mt5_order(self):
        old_blackout, old_mj, old_log = sr.event_blackout, sr.mt5_json, sr.log
        mj_calls, logs = [], []
        sr.event_blackout = lambda t, sym: "HIGH event window active"
        sr.mt5_json = lambda *a, **k: mj_calls.append(a) or {}
        sr.log = lambda *a, **k: logs.append((a, k))
        try:
            state, *_ = sr.manage_pending("XAUUSD", self._pend(execution="mt5"), live=True, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout, sr.mt5_json, sr.log = old_blackout, old_mj, old_log
        self.assertEqual(state, "gone")
        self.assertEqual(mj_calls[0][0], "cancel")
        self.assertEqual([a[0] for a, _ in logs], ["event_cancel_pending"])

    def test_no_blackout_falls_through_to_the_ordinary_fill_check(self):
        old_blackout, old_oj, old_log = sr.event_blackout, sr.order_json, sr.log
        sr.event_blackout = lambda t, sym: None
        sr.order_json = lambda *a, **k: {"status": "NEW", "executedQty": "0"}
        sr.log = lambda *a, **k: None
        try:
            state, *_ = sr.manage_pending("BTCUSDT", self._pend(), live=True, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout, sr.order_json, sr.log = old_blackout, old_oj, old_log
        self.assertEqual(state, "waiting")

    def test_a_dry_run_never_asks_event_risk(self):
        """--dry-run never touches a venue; manage_pending's existing `if not live` short-circuit must stay
        first, or a dry tick would start asking a live question."""
        old_blackout = sr.event_blackout
        asked = []
        sr.event_blackout = lambda t, sym: asked.append(sym) or None
        try:
            state, *_ = sr.manage_pending("BTCUSDT", self._pend(), live=False, bars_elapsed=1, t=sr.now())
        finally:
            sr.event_blackout = old_blackout
        self.assertEqual(state, "waiting")
        self.assertEqual(asked, [])


class DEC2_MT5RiskUsdIncludesContractSize(unittest.TestCase):
    """The MT5 position record's risk_usd must include the contract multiplier (tick_value/tick_size), or
    every recorded MT5 R-multiple is wrong by that factor (close_record divides pnl by risk_usd)."""

    def test_open_position_risk_usd_uses_the_contract_multiplier(self):
        sr._MT5_SYMBOLS["XAUUSD"] = dict(tick_size=0.01, tick_value=1.0, volume_min=0.01, volume_max=10.0,
                                         volume_step=0.01, digits=2)
        pend = dict(execution="mt5", side="LONG", strategy="x", tf="15m", method="WYCKOFF-BOOK", mgmt="be",
                    order_id="t1", client_id="c1", stop=4304.15, tp=4400.0, leverage=1, htf_pass=True,
                    sweep_time=None, mss_time=None, expectations=[])
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            pos = sr.open_position("XAUUSD", pend, filled_qty=1.0, avg_px=4354.27, live=False)
        finally:
            sr.log = old_log
        # r = |4354.27 - 4304.15| = 50.12 price units; value per price unit = tick_value/tick_size = 100 $/unit.
        expected = round(abs(4354.27 - 4304.15) * (1.0 / 0.01) * 1.0, 2)
        self.assertGreater(expected, 4000, "sanity: the contract-aware figure must be far larger than the "
                                          "price-distance-only 50.12 the audit found")
        self.assertAlmostEqual(pos["risk_usd"], expected, places=2)

    def test_futures_risk_usd_is_unaffected_price_distance_times_qty(self):
        pend = dict(execution="futures", side="LONG", strategy="x", tf="15m", method="ICT", mgmt="be",
                    order_id="t1", client_id="c1", stop=99.0, tp=110.0, leverage=3, htf_pass=True,
                    sweep_time=None, mss_time=None, expectations=[])
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            pos = sr.open_position("BTCUSDT", pend, filled_qty=2.0, avg_px=100.0, live=False)
        finally:
            sr.log = old_log
        self.assertAlmostEqual(pos["risk_usd"], round(1.0 * 2.0, 2))


class DEC3_PAR2_ExitFeeIsAlwaysTaker(unittest.TestCase):
    """The ICT net-R gate must price the exit at TAKER even for a maker (resting limit) entry -- every exit on
    this venue is a STOP_MARKET/TAKE_PROFIT_MARKET (or a market close for the time stop)."""

    def test_rr_reason_passes_exit_order_type_taker_for_a_resting_ict_limit(self):
        seen = {}
        old_net_r = sr.RM.net_r

        def spy(entry, stop, target, venue, order_type="taker", cfg=None, exit_order_type=None):
            seen["order_type"] = order_type; seen["exit_order_type"] = exit_order_type
            return old_net_r(entry, stop, target, venue, order_type, cfg=cfg, exit_order_type=exit_order_type)
        sr.RM.net_r = spy
        try:
            sig = dict(entry=100.0, stop=99.8, target=100.65, entry_now=False, r_planned=3.25)   # resting limit -> maker entry
            sr.rr_reason(sig, "futures")
        finally:
            sr.RM.net_r = old_net_r
        self.assertEqual(seen["order_type"], "maker")
        self.assertEqual(seen["exit_order_type"], "taker")

    def test_a_maker_priced_net_r_that_only_clears_the_floor_at_the_maker_exit_rate_now_fails(self):
        """DEC-3 evidence shape: a setup whose net R clears MIN_RR when BOTH sides are priced maker must now
        fail once the exit is correctly priced taker (real round-trip cost is higher)."""
        old_min_rr = sr.MIN_RR
        try:
            both_maker = sr.RM.net_r(100.0, 99.8, 100.65, "futures", "maker", exit_order_type="maker")
            sr.MIN_RR = round(both_maker["net_r"] - 0.001, 3)   # a floor the both-maker price would just clear
            sig = dict(entry=100.0, stop=99.8, target=100.65, entry_now=False, r_planned=3.25)
            why = sr.rr_reason(sig, "futures")
        finally:
            sr.MIN_RR = old_min_rr
        self.assertIsNotNone(why, "pricing the exit as maker would have passed this floor; taker must not")


class DEC4_SizingIncludesRoundTripFee(unittest.TestCase):
    """Position size must include the round-trip fee so the loss AT THE STOP does not exceed risk_usd."""

    def test_size_all_in_loss_does_not_exceed_risk_usd(self):
        qty, risk_usd = sr.size(10_000.0, 100.0, 99.8, 1.0, leverage=100, entry_order_type="maker")
        entry_fee = sr.RM.costs("futures", "maker")["fee_pct_per_side"]
        exit_fee = sr.RM.costs("futures", "taker")["fee_pct_per_side"]
        all_in_loss = qty * (abs(100.0 - 99.8) + 100.0 * entry_fee + 99.8 * exit_fee)
        self.assertLessEqual(all_in_loss, risk_usd + 1e-9)
        # distance-only sizing (the pre-fix arithmetic) would have overshot risk_usd once fees are paid:
        distance_only_qty = risk_usd / abs(100.0 - 99.8)
        self.assertLess(qty, distance_only_qty)

    def test_mt5_lots_all_in_loss_does_not_exceed_risk_usd(self):
        sr._MT5_SYMBOLS["XAUUSD"] = dict(tick_size=0.01, tick_value=1.0, volume_min=0.0, volume_max=100.0,
                                         volume_step=0.01, digits=2)
        lots, risk_usd, per_lot = sr.mt5_lots("XAUUSD", 10_000.0, 2000.0, 1990.0, 1.0)
        self.assertLessEqual(lots * per_lot, risk_usd + 1e-9)
        entry_fee = sr.RM.costs("mt5", "taker")["fee_pct_per_side"]
        exit_fee = entry_fee
        all_in_price_units = abs(2000.0 - 1990.0) + 2000.0 * entry_fee + 1990.0 * exit_fee
        self.assertAlmostEqual(per_lot, all_in_price_units * (1.0 / 0.01), places=6)


class DEC5_RevalidateFill(unittest.TestCase):
    """Nothing re-checked risk/R:R after a MARKET fill before this fix; a fill materially away from the
    planned entry must now be DISCLOSED (the position is already open, so this cannot be a refusal)."""

    def _pos(self, entry, stop=99.0, tp=110.0, risk_usd=100.0):
        return dict(entry=entry, stop=stop, tp=tp, execution="futures", risk_usd=risk_usd)

    def test_a_fill_far_from_the_planned_entry_discloses_a_risk_breach(self):
        logs = []
        old_log = sr.log; sr.log = lambda *a, **k: logs.append((a, k))
        try:
            # Planned risk 100 at |entry-stop|=1; actual fill moved the distance to 5 -> ~5x the planned risk.
            pos = self._pos(entry=104.0, stop=99.0, risk_usd=500.0)
            breaches = sr.revalidate_fill("BTCUSDT", pos, planned_risk_usd=100.0, entry_order_type="taker")
        finally:
            sr.log = old_log
        self.assertTrue(breaches)
        self.assertEqual([a[0] for a, _ in logs], ["fill_risk_breach"])

    def test_a_fill_close_to_the_planned_entry_discloses_nothing(self):
        old_log = sr.log; logs = []
        sr.log = lambda *a, **k: logs.append((a, k))
        try:
            pos = self._pos(entry=100.0, stop=99.0, tp=110.0, risk_usd=100.0)
            breaches = sr.revalidate_fill("BTCUSDT", pos, planned_risk_usd=100.0, entry_order_type="taker")
        finally:
            sr.log = old_log
        self.assertEqual(breaches, [])
        self.assertEqual(logs, [])

    def test_place_market_calls_revalidate_fill_after_a_futures_market_fill(self):
        calls = []
        old = dict(oj=sr.order_json, log=sr.log, mn=sr.min_notional, mf=sr.market_fill, rf=sr.revalidate_fill,
                  sh=sr.sh, ordr=sr.order)
        sr.order = lambda *a: "1"
        sr.min_notional = lambda sym: 0.0
        sr.sh = lambda *a, **k: ""
        sr.order_json = lambda *a, **k: {"orderId": "1"}
        sr.market_fill = lambda sym, o, qty_r, **k: (100.5, 1.0)
        sr.log = lambda *a, **k: None
        sr.revalidate_fill = lambda *a, **k: calls.append(a) or []
        try:
            sig = dict(side="long", entry=100.0, stop=99.0, target=103.0, time="t", mss_time="t", bars_left=0,
                      r_planned=3.0, htf_pass=True)
            st = dict(execution="futures", id="s1", tf="15m", method="WYCKOFF-BOOK", mgmt="be")
            sr.place_market("BTCUSDT", st, sig, 10_000.0, 1.0, live=True)
        finally:
            sr.order_json, sr.log, sr.min_notional, sr.market_fill, sr.revalidate_fill, sr.sh, sr.order = (
                old["oj"], old["log"], old["mn"], old["mf"], old["rf"], old["sh"], old["ordr"])
        self.assertTrue(calls, "place_market must re-validate risk/R:R against the actual fill")

    def test_a_generic_exception_from_revalidate_fill_does_not_lose_the_position(self):
        """Code review fix round 1 (DEC-5, BLOCKING): revalidate_fill() used to be called unguarded; any
        exception OTHER than RM.RiskRefused (a KeyError, a connector hiccup, anything unforeseen) propagated
        out of place_market() AFTER the entry and its protective stop were already placed on the exchange, so
        place_market() never reached `return pos` -- the caller in tick() never adds an already-protected,
        already-real position to s['positions']. place_market() must still return the position."""
        old = dict(oj=sr.order_json, log=sr.log, mn=sr.min_notional, mf=sr.market_fill, rf=sr.revalidate_fill,
                  sh=sr.sh, ordr=sr.order)
        logs = []
        sr.order = lambda *a: "1"
        sr.min_notional = lambda sym: 0.0
        sr.sh = lambda *a, **k: ""
        sr.order_json = lambda *a, **k: {"orderId": "1"}
        sr.market_fill = lambda sym, o, qty_r, **k: (100.5, 1.0)
        sr.log = lambda *a, **k: logs.append((a, k))

        def raising_revalidate(*a, **k):
            raise KeyError("some_unexpected_field")
        sr.revalidate_fill = raising_revalidate
        try:
            sig = dict(side="long", entry=100.0, stop=99.0, target=103.0, time="t", mss_time="t", bars_left=0,
                      r_planned=3.0, htf_pass=True)
            st = dict(execution="futures", id="s1", tf="15m", method="WYCKOFF-BOOK", mgmt="be")
            pos = sr.place_market("BTCUSDT", st, sig, 10_000.0, 1.0, live=True)
        finally:
            sr.order_json, sr.log, sr.min_notional, sr.market_fill, sr.revalidate_fill, sr.sh, sr.order = (
                old["oj"], old["log"], old["mn"], old["mf"], old["rf"], old["sh"], old["ordr"])
        self.assertIsNotNone(pos, "an already-protected position must never be lost because a disclosure step raised")
        self.assertAlmostEqual(pos["entry"], 100.5)
        self.assertEqual([a[0] for a, _ in logs if a[0] == "fill_revalidate_error"], ["fill_revalidate_error"])


class DEC6_UnresolvableAccountRuleBlocksEntriesNotHalt(unittest.TestCase):
    """A declared account-survival rule whose basis fact this runner cannot supply must block NEW ENTRIES
    (never HALT) -- CLAUDE.md §20 forbids treating that UNKNOWN as a pass."""

    def _profile(self, **rules_over):
        rules = {k: None for k in sr.AP.RULE_KEYS}
        rules.update(rules_over)
        return {"id": "test-prop", "rules": rules}

    def test_a_rule_whose_basis_the_runner_never_supplies_blocks_entries(self):
        prof = self._profile(max_daily_loss={"pct": 0.05, "basis": "day_start_equity", "action": "HALT"})
        facts = {"equity": 9000.0, "equity_start": 10000.0, "consec_losses": 0}   # no day_start_equity
        why = sr._account_survival_block(prof, facts)
        self.assertIsNotNone(why)
        self.assertIn("max_daily_loss", why)

    def test_a_fully_supplied_rule_that_has_not_breached_blocks_nothing(self):
        prof = self._profile(max_daily_loss={"pct": 0.05, "basis": "day_start_equity", "action": "HALT"})
        facts = {"equity": 9990.0, "equity_start": 10000.0, "consec_losses": 0, "day_start_equity": 10000.0}
        self.assertIsNone(sr._account_survival_block(prof, facts))

    def test_a_profile_with_no_rules_declared_blocks_nothing(self):
        prof = self._profile()
        self.assertIsNone(sr._account_survival_block(prof, {"equity": 100.0}))


class DEC7_UnknownImpactEventIsDisclosedNotSilentlyClear(unittest.TestCase):
    """CLAUDE.md §25: UNKNOWN must never be silently treated as LOW. `event_blackout` must not BLOCK on a
    non-strict UNKNOWN event (test_event_risk.py pins that `ER.windows(mode='NORMAL')` stays empty for
    UNKNOWN), but it must DISCLOSE one that the calendar's own strict_no_trade flag would gate in STRICT mode."""

    def _cal(self, when):
        return {
            "snapshot": {"id": "test-cal"},
            "policy": {"pre_minutes": 10, "post_minutes": 10,
                      "by_impact": {"HIGH": {"restricted": True}, "MEDIUM": {"restricted": False},
                                    "LOW": {"restricted": False},
                                    "UNKNOWN": {"restricted": False, "strict_no_trade": True}}},
            "relevance": {"global_keyword": "GLOBAL"},
            "events": [{"id": "e1", "name": "Unscheduled release", "impact": "UNKNOWN", "status": "released",
                       "currencies": ["GLOBAL"], "scheduled_event_time": when,
                       "available_time": "2026-01-01T00:00:00Z"}],
        }

    def test_an_unknown_event_in_window_is_disclosed_but_not_blocked(self):
        when = "2026-06-01T12:00:00Z"
        cal = self._cal(when)
        old_load, old_tighten, old_log = sr.ER.load, sr.AP.tighten_calendar, sr.log
        logs = []
        sr.ER.load = lambda **k: cal
        sr.AP.tighten_calendar = lambda prof, c: c
        sr.log = lambda *a, **k: logs.append((a, k))
        try:
            why = sr.event_blackout(sr.parse_t(when), "BTCUSDT")
        finally:
            sr.ER.load, sr.AP.tighten_calendar, sr.log = old_load, old_tighten, old_log
        self.assertIsNone(why, "a non-strict UNKNOWN event must not block -- disclosure only")
        self.assertEqual([a[0] for a, _ in logs], ["unknown_event_disclosed"])

    def test_outside_the_window_nothing_is_disclosed(self):
        cal = self._cal("2026-06-01T12:00:00Z")
        old_load, old_tighten, old_log = sr.ER.load, sr.AP.tighten_calendar, sr.log
        logs = []
        sr.ER.load = lambda **k: cal
        sr.AP.tighten_calendar = lambda prof, c: c
        sr.log = lambda *a, **k: logs.append((a, k))
        try:
            why = sr.event_blackout(sr.parse_t("2026-06-01T09:00:00Z"), "BTCUSDT")
        finally:
            sr.ER.load, sr.AP.tighten_calendar, sr.log = old_load, old_tighten, old_log
        self.assertIsNone(why)
        self.assertEqual(logs, [])


class DEC8_CloseRecordIsNetOfFeesForFutures(unittest.TestCase):
    """Futures exits (no venue P&L passed in) must record P&L/R NET of the round-trip fee, matching the
    backtest's own net_R = R - fee_R -- gross alone overstated live expectancy vs. the evidence it is
    compared against, and hid a fee-losing breakeven exit from consec_losses."""

    def test_a_futures_exit_with_no_venue_pnl_is_net_of_fees(self):
        pos = dict(side="LONG", strategy="x", tf="15m", execution="futures", htf_pass=True, be=False,
                  entry=100.0, opened_at="2026-01-01T00:00:00Z", risk_usd=1.0, method="WYCKOFF-BOOK")
        rec = sr.close_record("BTCUSDT", pos, px=100.0, via="BE", qty=1.0)   # gross P&L is exactly 0 (BE)
        self.assertEqual(rec["pnl_gross"], 0.0)
        self.assertLess(rec["pnl"], 0.0, "a breakeven exit still pays the round-trip fee and must show a loss")
        self.assertLess(rec["r"], 0.0)

    def test_an_mt5_exit_with_a_venue_pnl_is_unaffected(self):
        pos = dict(side="LONG", strategy="x", tf="15m", execution="mt5", htf_pass=True, be=False,
                  entry=100.0, opened_at="2026-01-01T00:00:00Z", risk_usd=100.0, method="WYCKOFF-BOOK")
        rec = sr.close_record("XAUUSD", pos, px=100.0, via="BE", qty=1.0, pnl=-5.0)
        self.assertEqual(rec["pnl"], -5.0)
        self.assertNotIn("pnl_gross", rec, "a venue-supplied pnl is already net; there is no gross figure to add")


class PAR1_BreakevenCountsTheFirstBarAfterEntry(unittest.TestCase):
    """Live breakeven must arm from the FIRST bar after the entry bar, strictly excluding the entry/fill bar
    itself -- matching the backtest's walk(start=entry_bar+1). Anchoring on wall-clock `opened_at` (the tick
    that noticed the fill, always later than the entry bar's own open) used to exclude that first bar forever."""

    def test_plus_one_r_on_the_first_bar_after_entry_arms_breakeven(self):
        pos = dict(side="LONG", strategy="x", tf="30m", method="ICT", execution="futures", mgmt="be", qty="1",
                  entry=100.0, stop=99.0, tp=103.0, stop_order=None, tp_order=None,
                  opened_at="2026-01-01T01:05:00Z",     # wall-clock: well AFTER the 00:30 entry bar's open
                  entry_bar_time="2026-01-01T00:30:00Z", bars=0, risk_usd=1.0, be=False, be_level=101.0,
                  htf_pass=True)
        # The bar strictly after the entry bar (01:00) touches +1R; under the old wall-clock anchor this bar
        # is EXCLUDED (01:00:00Z < opened_at's minute 01:05), so breakeven would never arm on it.
        candles = [dict(time="2026-01-01T01:00:00Z", high=101.2, low=100.1, close=100.9)]
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            rec = sr.manage_position("BTCUSDT", pos, candles, live=False, bars_elapsed=1)
        finally:
            sr.log = old_log
        self.assertIsNone(rec)
        self.assertTrue(pos["be"], "breakeven must arm on the first bar after entry, not the second")
        self.assertAlmostEqual(pos["stop"], 100.0)

    def test_the_entry_bar_itself_never_arms_breakeven(self):
        """The backtest never arms BE on the fill bar itself; the live filter must exclude it too."""
        pos = dict(side="LONG", strategy="x", tf="30m", method="ICT", execution="futures", mgmt="be", qty="1",
                  entry=100.0, stop=99.0, tp=103.0, stop_order=None, tp_order=None,
                  opened_at="2026-01-01T00:35:00Z", entry_bar_time="2026-01-01T00:30:00Z", bars=0,
                  risk_usd=1.0, be=False, be_level=101.0, htf_pass=True)
        candles = [dict(time="2026-01-01T00:30:00Z", high=101.2, low=99.9, close=100.9)]   # the entry bar itself
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            sr.manage_position("BTCUSDT", pos, candles, live=False, bars_elapsed=1)
        finally:
            sr.log = old_log
        self.assertFalse(pos["be"], "the entry/fill bar itself must never arm breakeven")

    def test_a_position_with_no_entry_bar_time_falls_back_to_the_old_wall_clock_anchor(self):
        """Positions already open under the pre-fix state file have no entry_bar_time on disk; guessing one
        would invent history. The pre-fix wall-clock anchor is the only safe fallback for them."""
        pos = dict(side="LONG", strategy="x", tf="30m", method="ICT", execution="futures", mgmt="be", qty="1",
                  entry=100.0, stop=99.0, tp=103.0, stop_order=None, tp_order=None,
                  opened_at="2026-01-01T00:00:00Z", bars=0, risk_usd=1.0, be=False, be_level=101.0, htf_pass=True)
        candles = [dict(time="2026-01-01T00:30:00Z", high=100.5, low=99.5, close=100.2),
                  dict(time="2026-01-01T01:00:00Z", high=101.2, low=100.1, close=100.9)]
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            rec = sr.manage_position("BTCUSDT", pos, candles, live=False, bars_elapsed=1)
        finally:
            sr.log = old_log
        self.assertIsNone(rec); self.assertTrue(pos["be"]); self.assertAlmostEqual(pos["stop"], 100.0)


class PAR1_EntryBarTimeIsRecorded(unittest.TestCase):
    def test_open_position_stores_the_entry_bar_time_when_given(self):
        pend = dict(execution="futures", side="LONG", strategy="x", tf="15m", method="WYCKOFF-BOOK", mgmt="be",
                    order_id="t1", client_id="c1", stop=99.0, tp=103.0, leverage=1, htf_pass=True,
                    sweep_time=None, mss_time=None, expectations=[])
        old_log = sr.log; sr.log = lambda *a, **k: None
        try:
            pos = sr.open_position("BTCUSDT", pend, 1.0, 100.0, live=False, entry_bar_time="2026-01-01T00:00:00Z")
        finally:
            sr.log = old_log
        self.assertEqual(pos["entry_bar_time"], "2026-01-01T00:00:00Z")

    def test_a_limit_fill_with_no_explicit_entry_bar_time_floors_now_to_the_tf_grid(self):
        pend = dict(execution="futures", side="LONG", strategy="x", tf="15m", method="ICT", mgmt="be",
                    order_id="t1", client_id="c1", stop=99.0, tp=103.0, leverage=1, htf_pass=True,
                    sweep_time=None, mss_time=None, expectations=[])
        old_log, old_now = sr.log, sr.now
        sr.log = lambda *a, **k: None
        sr.now = lambda: sr.parse_t("2026-01-01T00:07:23Z")
        try:
            pos = sr.open_position("BTCUSDT", pend, 1.0, 100.0, live=False)
        finally:
            sr.log, sr.now = old_log, old_now
        self.assertEqual(pos["entry_bar_time"], "2026-01-01T00:00:00Z")
