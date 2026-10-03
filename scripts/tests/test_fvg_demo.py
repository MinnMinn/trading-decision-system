"""scripts/fvg_demo.py with a FAKE bridge and hand-built bars: the safety gates and the order lifecycle. No terminal, no account.

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_fvg_demo
"""
import datetime
import importlib.util
import json
import os
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
spec = importlib.util.spec_from_file_location("fvg_demo", os.path.join(ROOT, "scripts", "fvg_demo.py"))
FD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(FD)
EC = FD.EC
UTC = datetime.timezone.utc
CFG = {"enabled": True, "risk_pct": 0.01, "components": {"XAUUSD": 24}, "bridge_subdir": "x", "max_bar_age_minutes": 15,
       "close_before_rollover_minutes": 10, "tp_stop_multiple": 5}


class FakeBridge:
    def __init__(self, demo=True):
        self.demo, self.calls, self.orders, self.n = demo, [], {}, 100

    def __call__(self, *a):
        self.calls.append(a)
        cmd = a[0]
        if cmd == "check":
            return {"demo": self.demo}
        if cmd == "account":
            return {"balance": getattr(self, "balance", 100000)}
        if cmd == "symbol":
            return {"tick_value": 1.0, "tick_size": 0.01, "volume_step": 0.01, "volume_min": 0.01, "volume_max": 50,
                    "digits": 2}
        if cmd == "limit":
            self.n += 1
            self.orders[self.n] = {"state": "pending", "price": float(a[4])}
            return {"ok": True, "ticket": self.n}
        if cmd == "order-status":
            return dict(self.orders[int(a[1])])
        if cmd == "cancel":
            self.orders[int(a[1])]["state"] = "canceled"
            return {"ok": True}
        if cmd == "position-status":
            return {"state": "open"}
        if cmd == "market":
            return {"ok": True, "ticket": 555, "price": 0.0 + float(a[4]) * 0 + 1.0}
        if cmd == "close":
            return {"ok": True, "price": 1.0}
        raise AssertionError(a)


def series_with_fresh_gap():
    """21 dense flat days, then a displacement FVG whose third bar is the last closed bar."""
    t0 = datetime.datetime(2026, 9, 1, tzinfo=UTC)
    bars, k = [], 0
    for d in range(22):
        for b in range(288 if d < 21 else 40):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            px = 2000.0 + (0.3 if b % 2 else -0.3)
            bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
    last = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00"))
    for j, (o, h, l, c) in enumerate([(2000.0, 2000.4, 1999.6, 2000.2), (2000.2, 2006.0, 2000.2, 2005.8),
                                      (2005.8, 2007.0, 2002.0, 2006.5)]):
        t = last + datetime.timedelta(minutes=5 * (j + 1))
        bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": o, "high": h, "low": l, "close": c})
    s = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    now = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=6)
    return s, now


class Gates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.paths = dict(state_path=os.path.join(self.tmp, "s.json"), log_path=os.path.join(self.tmp, "l.jsonl"))
        self.s, self.now = series_with_fresh_gap()
        p = mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: self.s)
        p.start(); self.addCleanup(p.stop)
        z = mock.patch.object(FD.FF, "_zone", lambda: UTC)
        z.start(); self.addCleanup(z.stop)

    def test_disabled_does_nothing(self):
        b = FakeBridge()
        self.assertEqual(FD.tick(self.now, b, dict(CFG, enabled=False), **self.paths, event_blocked=lambda s, t: (False, "")), "disabled")
        self.assertEqual(b.calls, [])

    def test_non_demo_account_is_refused_before_anything(self):
        b = FakeBridge(demo=False)
        self.assertEqual(FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, "")), "refused")
        self.assertEqual([c[0] for c in b.calls], ["check"])

    def test_places_one_limit_with_its_stop_then_never_twice(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        lim = [c for c in b.calls if c[0] == "limit"]
        self.assertEqual(len(lim), 1)
        _, sym, side, lots, px, sl, tp, _cmt = lim[0]
        self.assertEqual((sym, side, px), ("XAUUSD", "buy", "2002.00"))      # the gap's near edge = third bar's low
        self.assertLess(float(sl), float(px))
        self.assertGreater(float(tp), float(px))
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertEqual(len([c for c in b.calls if c[0] == "limit"]), 1)

    def test_event_risk_blocks_a_new_entry(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (True, "NFP window"))
        self.assertFalse([c for c in b.calls if c[0] == "limit"])

    def test_stale_bars_block_a_new_entry(self):
        b = FakeBridge()
        FD.tick(self.now + datetime.timedelta(hours=2), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertFalse([c for c in b.calls if c[0] == "limit"])

    def test_risk_is_clamped_to_the_ceiling(self):
        sysv = dict(FD.R.system_of(FD.R.assignment("asg-0002")))
        sysv["risk"] = dict(sysv["risk"], risk_pct=0.05)
        self.assertLessEqual(FD.config_for(sysv, FD.R.account("ftmo-demo-01"))["risk_pct"], 0.01)

    def test_fill_then_time_exit(self):
        b = FakeBridge()
        FD.tick(self.now, b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        tk = max(b.orders)
        b.orders[tk] = {"state": "filled", "price": 2002.0, "position_ticket": 777}
        FD.tick(self.now + datetime.timedelta(minutes=5), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        st = json.load(open(self.paths["state_path"]))
        self.assertEqual(len(st["open"]), 1)
        FD.tick(self.now + datetime.timedelta(hours=3), b, CFG, **self.paths, event_blocked=lambda s, t: (False, ""))
        self.assertIn(("close", 777), b.calls)
        self.assertEqual(json.load(open(self.paths["state_path"]))["open"], [])


def series_with_h7_breakout():
    """22 dense rising days, then a partial day whose last closed bar closes above the previous day's high."""
    t0 = datetime.datetime(2026, 8, 3, tzinfo=UTC)
    bars = []
    for d in range(23):
        base = 2000.0 + 5.0 * min(d, 21)          # the partial last day opens inside the previous day's range
        for b in range(288 if d < 22 else 30):
            t = t0 + datetime.timedelta(days=d, minutes=5 * b)
            px = base + (0.3 if b % 2 else -0.3)
            bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": px, "high": px + 0.5, "low": px - 0.5, "close": px})
    prev_high = 2000.0 + 5.0 * 21 + 0.8
    t = datetime.datetime.fromisoformat(bars[-1]["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=5)
    bars.append({"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "open": prev_high - 1, "high": prev_high + 3, "low": prev_high - 1,
                 "close": prev_high + 2})
    s = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    return s, t + datetime.timedelta(minutes=6)


class H7(unittest.TestCase):
    def test_market_entry_on_the_breakout_bar_once(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        cfg = dict(CFG, components={}, h7_symbols=["XAUUSD"])
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: s), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            b = FakeBridge()
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual(len(mk), 1)
        self.assertEqual(mk[0][1:3], ("XAUUSD", "buy"))
        self.assertLess(float(mk[0][4]), s.C[-1])          # the stop is below the entry reference


class DataGate(unittest.TestCase):
    def test_a_hole_in_the_decision_window_blocks_new_entries(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        keep = [i for i, t in enumerate(s.T) if not ("2026-08-19" <= t[:10] <= "2026-08-20")]   # a Wed-Thu hole
        bars = [{"time": s.T[i], "open": s.O[i], "high": s.H[i], "low": s.L[i], "close": s.C[i]} for i in keep]
        holed = EC.Series("XAUUSD", bars, UTC, end="9999-12-31T00:00:00Z", sigma_every_day=True)
        cfg = dict(CFG, components={"XAUUSD": 24}, h7_symbols=["XAUUSD"])
        b = FakeBridge()
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: holed), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        self.assertFalse([c for c in b.calls if c[0] in ("market", "limit")])
        rows = [json.loads(l) for l in open(paths["log_path"])]
        self.assertTrue(any("data hole" in r.get("reason", "") for r in rows))


class Isolation(unittest.TestCase):
    def test_a_symbol_the_ea_does_not_know_never_blocks_the_others(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()

        class Partial(FakeBridge):
            def __call__(self, *a):
                if a[0] == "symbol" and a[1] == "US500":
                    self.calls.append(a)
                    return {"ok": False, "comment": "symbol US500.cash not in the EA's symbols.json"}
                return super().__call__(*a)

        def boom(sym, now, live_dir=None):
            if sym == "AUS200":
                raise RuntimeError("corrupt bridge file")
            return s
        cfg = dict(CFG, components={"AUS200": 48}, h7_symbols=["US500", "XAUUSD"])
        b = Partial()
        with mock.patch.object(FD, "closed_series", boom), mock.patch.object(FD.FF, "_zone", lambda: UTC):
            self.assertEqual(FD.tick(now, b, cfg, **paths, event_blocked=lambda x, t: (False, "")), "ok")
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual([c[1] for c in mk], ["XAUUSD"])                  # US500 skipped, AUS200 errored, XAUUSD still traded
        kinds = [json.loads(l)["kind"] for l in open(paths["log_path"])]
        self.assertIn("error", kinds)
        self.assertIn("skip", kinds)
        self.assertTrue(os.path.exists(paths["state_path"]))              # the state is still written


class V2(unittest.TestCase):
    """Trading System v2: G9 gold market entries and the dd3 drawdown throttle."""

    def _run(self, cfg, now_shift=datetime.timedelta(0), balances=(100000,)):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        b = FakeBridge()
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: s), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            for bal in balances:
                b.balance = bal
                FD.tick(now + now_shift, b, cfg, **paths, event_blocked=lambda x, t: (False, ""))
        return b, s, paths

    def test_g9_places_one_market_order_on_the_live_last_bar(self):
        cfg = dict(CFG, components={}, h7_symbols=[], g9_symbols=["XAUUSD"])
        b, s, _ = self._run(cfg, balances=(100000, 100000))
        mk = [c for c in b.calls if c[0] == "market"]
        self.assertEqual(len(mk), 1)
        self.assertEqual((mk[0][1], mk[0][2], mk[0][-1]), ("XAUUSD", "buy", "g9-XAUUSD"))

    def test_g9_signal_ignored_in_the_research_series(self):
        s, _ = series_with_h7_breakout()
        research = EC.Series("XAUUSD", [{"time": t, "open": o, "high": h, "low": l, "close": c}
                                        for t, o, h, l, c in zip(s.T, s.O, s.H, s.L, s.C)], UTC, end="9999-12-31T00:00:00Z")
        self.assertFalse([e for e in FD.FF._f4().ev_vol_breakout(research) if e["i"] == len(research.T) - 1])
        self.assertTrue([e for e in FD.FF._f4().ev_vol_breakout(s) if e["i"] == len(s.T) - 1])

    def test_no_entry_inside_the_pre_rollover_window(self):
        cfg = dict(CFG, components={}, h7_symbols=["XAUUSD"], close_before_rollover_minutes=24 * 60)
        b, _s, paths = self._run(cfg)
        self.assertFalse([c for c in b.calls if c[0] == "market"])

    def test_throttle_steps_and_never_raises_risk(self):
        cfg = dict(CFG, throttle={"kind": "dd3", "initial_balance": 100000})
        self.assertEqual(FD.throttle_mult(cfg, 99000, 100000), 1.0)
        self.assertEqual(FD.throttle_mult(cfg, 96000, 100000), 0.5)
        self.assertEqual(FD.throttle_mult(cfg, 93000, 100000), 0.25)
        self.assertEqual(FD.throttle_mult(cfg, 50000, None), 0.25)          # unknown reference: most conservative
        self.assertEqual(FD.throttle_mult(dict(CFG), 50000, 100000), 1.0)   # no throttle configured
        st = {}
        self.assertEqual(FD.sizing(cfg, st, 120000), (0.01, 100000))        # sized on the INITIAL balance, never above 1 %
        self.assertEqual(FD.sizing(cfg, st, 95000), (0.005, 100000))
        st2 = {}
        cfg2 = dict(CFG, throttle={"kind": "dd3", "initial_balance": None})
        FD.sizing(cfg2, st2, 80000)
        self.assertEqual(st2["initial_balance"], 80000)                     # first balance seen becomes the reference
        self.assertEqual(FD.sizing(cfg2, st2, 75000)[0], 0.0025)

    def test_throttled_lots_are_smaller(self):
        info = {"tick_value": 1.0, "tick_size": 0.01, "volume_step": 0.01, "volume_max": 50}
        full = FD.lots_for(info, 100000, 0.01, 2000.0, 1990.0)
        half = FD.lots_for(info, 100000, 0.005, 2000.0, 1990.0)
        self.assertAlmostEqual(half, full / 2, places=6)


class Registry(unittest.TestCase):
    """ADR 0010: the executor's configuration comes from the account's live assignment, never from a side file."""

    LEGACY_V2 = {"enabled": True, "risk_pct": 0.01, "components": {"XAUUSD": 24, "US500": 48}, "h7_symbols": ["XAUUSD"],
                 "g9_symbols": ["XAUUSD"], "throttle": {"kind": "dd3", "initial_balance": None}, "bridge_subdir": "bridge",
                 "max_bar_age_minutes": 15, "close_before_rollover_minutes": 10, "tp_stop_multiple": 5}

    def test_fvg_book_v2_on_the_demo_account_equals_the_retired_side_file(self):
        """Equivalence: the registry reproduces docs/architecture/fvg-demo.json v2 exactly, so the migration changes
        where the configuration lives and nothing the executor does."""
        cfg = FD.config_for(FD.R.system_of(FD.R.assignment("asg-0002")), FD.R.account("ftmo-demo-01"),
                            FD.R.assignment("asg-0002"))
        self.assertEqual({k: cfg[k] for k in self.LEGACY_V2}, self.LEGACY_V2)
        self.assertEqual((cfg["trading_system"], cfg["assignment"], cfg["account"]), ("fvg-book@v2", "asg-0002", "ftmo-demo-01"))

    def test_v1_had_no_g9_and_no_throttle(self):
        cfg = FD.config_for(FD.R.system_of(FD.R.assignment("asg-0001")), FD.R.account("ftmo-demo-01"))
        self.assertEqual((cfg["g9_symbols"], cfg["throttle"]["kind"]), ([], "none"))

    def test_resolve_follows_the_assignment_live_at_the_instant(self):
        acc = "ftmo-demo-01"
        with mock.patch.object(FD, "GLOBAL_STOP", "/nonexistent"), \
                mock.patch.object(FD, "account_paths", lambda a: {"stop_path": "/nonexistent", "state_path": "", "log_path": ""}):
            v1, why1 = FD.resolve(acc, datetime.datetime(2026, 10, 2, 12, tzinfo=UTC))
            v2, why2 = FD.resolve(acc, datetime.datetime(2026, 10, 3, 12, tzinfo=UTC))
            none, why0 = FD.resolve(acc, datetime.datetime(2026, 9, 1, tzinfo=UTC))
        self.assertEqual((v1["trading_system"], v2["trading_system"]), ("fvg-book@v1", "fvg-book@v2"))
        self.assertTrue(v1["enabled"] and v2["enabled"])
        self.assertIsNone(none)
        self.assertEqual(why0, "no assignment")

    def test_a_stop_file_disables_new_entries_only(self):
        tmp = tempfile.mkdtemp()
        stop = os.path.join(tmp, "STOP")
        open(stop, "w").close()
        with mock.patch.object(FD, "account_paths", lambda a: {"stop_path": stop, "state_path": "", "log_path": ""}):
            cfg, why = FD.resolve("ftmo-demo-01", datetime.datetime(2026, 10, 3, 12, tzinfo=UTC))
        self.assertFalse(cfg["enabled"])
        self.assertEqual(why, "STOP file present")

    def test_executor_accounts_are_the_mt5_registry_accounts(self):
        self.assertEqual(FD.executor_accounts(), ["ftmo-demo-01"])


def _two_assignments(policy):
    """Registry rows: asg-a (v1) replaced by asg-b (v2) at 2026-10-03 with `policy`."""
    return [
        {"id": "asg-a", "account": "ftmo-demo-01", "trading_system": "fvg-book", "version": "v1",
         "effective_from": "2026-10-01T00:00:00Z", "ended_at": "2026-10-03T00:00:00Z", "open_position_policy": "DRAIN"},
        {"id": "asg-b", "account": "ftmo-demo-01", "trading_system": "fvg-book", "version": "v2",
         "effective_from": "2026-10-03T00:00:00Z", "ended_at": None, "open_position_policy": policy}]


class Switch(unittest.TestCase):
    """DRAIN keeps a drained position's own exit; CLOSE closes it at the next tick; new entries carry the new assignment."""

    def _state(self, tmp):
        st = {"pending": [{"key": "k1", "symbol": "XAUUSD", "h": 24, "side": 1, "ticket": 11, "edge": 2000.0, "stop": 1990.0,
                           "lots": 0.1, "gap_time": "2026-10-02T10:00:00Z", "placed_at": "2026-10-02T10:01:00Z",
                           "expires_at": "2026-10-09T00:00:00Z", "assignment": "asg-a"}],
              "open": [{"key": "k2", "symbol": "XAUUSD", "side": 1, "position_ticket": 22, "exit_due": "2026-10-09T00:00:00Z",
                        "assignment": "asg-a"}],
              "done_keys": [], "placed_gaps": []}
        p = os.path.join(tmp, "s.json")
        json.dump(st, open(p, "w"))
        return p

    def _bridge(self):
        b = FakeBridge()
        b.orders[11] = {"state": "pending"}
        return b

    def _tick(self, policy):
        tmp = tempfile.mkdtemp()
        sp, lp = self._state(tmp), os.path.join(tmp, "l.jsonl")
        now = datetime.datetime(2026, 10, 3, 12, tzinfo=UTC)
        with mock.patch.object(FD.R, "ASSIGNMENTS", _two_assignments(policy)):
            cfg = dict(CFG, enabled=False, close_assignments=sorted(FD._closing_assignments("ftmo-demo-01", now)))
        b = self._bridge()
        out = FD.tick(now, b, cfg, state_path=sp, log_path=lp, event_blocked=lambda s, t: (False, ""))
        return out, b, json.load(open(sp))

    def test_drain_keeps_the_old_positions_and_their_exits(self):
        out, b, st = self._tick("DRAIN")
        self.assertEqual(out, "manage-only")
        self.assertNotIn(("close", 22), b.calls)
        self.assertNotIn(("cancel", 11), b.calls)
        self.assertEqual([p["key"] for p in st["open"]], ["k2"])

    def test_close_closes_and_cancels_what_the_replaced_assignment_placed(self):
        out, b, st = self._tick("CLOSE")
        self.assertIn(("close", 22), b.calls)
        self.assertIn(("cancel", 11), b.calls)
        self.assertEqual((st["open"], st["pending"]), ([], []))

    def test_new_entries_carry_the_live_assignment(self):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        s, now = series_with_h7_breakout()
        cfg = dict(CFG, components={}, h7_symbols=["XAUUSD"], assignment="asg-b", trading_system="fvg-book@v2",
                   account="ftmo-demo-01")
        with mock.patch.object(FD, "closed_series", lambda sym, now, live_dir=None: s), \
                mock.patch.object(FD.FF, "_zone", lambda: UTC):
            FD.tick(now, FakeBridge(), cfg, **paths, event_blocked=lambda x, t: (False, ""))
        pos = json.load(open(paths["state_path"]))["open"][0]
        self.assertEqual((pos["assignment"], pos["trading_system"], pos["account"]), ("asg-b", "fvg-book@v2", "ftmo-demo-01"))


class TerminalIdentity(unittest.TestCase):
    def _run(self, login, env):
        tmp = tempfile.mkdtemp()
        paths = dict(state_path=os.path.join(tmp, "s.json"), log_path=os.path.join(tmp, "l.jsonl"))
        b = FakeBridge()
        real = b.__call__
        b.__class__ = type("B", (FakeBridge,), {"__call__": lambda self, *a: {"balance": 1, "login": login}
                                                 if a[0] == "account" else real(*a)})
        with mock.patch.dict(os.environ, env, clear=False):
            out = FD.tick(datetime.datetime(2026, 10, 5, 9, tzinfo=UTC), b, dict(CFG, components={}, login_ref="MT5_LOGIN_T"),
                          **paths, event_blocked=lambda s, t: (False, ""))
        return out

    def test_a_terminal_on_another_login_is_refused(self):
        self.assertEqual(self._run(111, {"MT5_LOGIN_T": "222"}), "refused")

    def test_an_unset_login_ref_is_refused(self):
        os.environ.pop("MT5_LOGIN_T", None)
        self.assertEqual(self._run(111, {}), "refused")

    def test_the_right_login_passes(self):
        self.assertEqual(self._run(222, {"MT5_LOGIN_T": "222"}), "ok")


class Migration(unittest.TestCase):
    def test_the_single_account_state_moves_once_into_the_legacy_channel_account(self):
        tmp = tempfile.mkdtemp()
        legacy_state, legacy_log = os.path.join(tmp, "fvg-demo-state.json"), os.path.join(tmp, "fvg-demo.jsonl")
        json.dump({"pending": [], "open": [{"key": "k", "filled_seen_at": "2026-10-02T12:00:00Z"}], "done_keys": ["d"],
                   "placed_gaps": [], "initial_balance": 100000}, open(legacy_state, "w"))
        open(legacy_log, "w").write(json.dumps({"kind": "filled"}) + "\n")
        sp, lp = os.path.join(tmp, "acc", "state.json"), os.path.join(tmp, "acc", "events.jsonl")
        with mock.patch.object(FD, "LEGACY_STATE", legacy_state), mock.patch.object(FD, "LEGACY_LOG", legacy_log):
            os.makedirs(os.path.dirname(sp))
            self.assertTrue(FD.migrate_legacy("ftmo-demo-01", sp, lp))
            self.assertFalse(FD.migrate_legacy("ftmo-demo-01", sp, lp))          # once
        st = json.load(open(sp))
        self.assertEqual(st["initial_balance"], 100000)                          # the throttle reference survives
        self.assertEqual(st["open"][0]["assignment"], "asg-0001")                # live when it was filled (v1 day)
        kinds = [json.loads(l)["kind"] for l in open(lp)]
        self.assertEqual(kinds, ["filled", "migrated"])
        self.assertFalse(os.path.exists(legacy_state))


if __name__ == "__main__":
    unittest.main()
