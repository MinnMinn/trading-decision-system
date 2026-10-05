"""A3t: scripts/build-pit-page.py draws a chart page as of a development decision time T -- nothing after T,
structure objects from the prefix only, development data only."""
import datetime, importlib.util, json, os, re, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(ROOT, "scripts", "build-pit-page.py")
POISON = 987654.5


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""), os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def synth(n, t0, step_min=15, base=1900.0):
    t = datetime.datetime.fromisoformat(t0.replace("Z", "+00:00")); out = []; p = base
    for i in range(n):
        o = p; c = o + ((i * 37) % 11 - 5) * 0.6; h = max(o, c) + (i * 13) % 7 * 0.2; l = min(o, c) - (i * 17) % 5 * 0.2
        out.append(dict(time=t.strftime("%Y-%m-%dT%H:%M:%SZ"), open=round(o, 2), high=round(h, 2), low=round(l, 2),
                        close=round(c, 2), volume=1 + (i * 7) % 13))
        p = c; t += datetime.timedelta(minutes=step_min)
    return out


def write_hist(root, sym, tf, candles):
    with open(os.path.join(root, f"ohlcv.{sym}.{tf}.json"), "w", encoding="utf-8") as f:
        json.dump({"symbol": sym, "timeframe": tf, "candles": candles}, f)


def init_data(page):
    i = page.index("TChart.init(") + len("TChart.init(")
    data, _ = json.JSONDecoder().raw_decode(page[i:])
    return data


T_ISO = "2023-06-15T14:00:00Z"


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls.tmp, "hist"); os.makedirs(cls.root)
        past = synth(700, "2023-06-01T00:00:00Z")                        # ends ~2023-06-08 -> extend to straddle T
        past = synth(1500, "2023-06-01T00:00:00Z")                       # 15m x 1500 = 15.6 days: straddles T
        future_poison = dict(time="2023-06-15T14:15:00Z", open=POISON, high=POISON, low=POISON, close=POISON, volume=1)
        cls.all = [c for c in past if c["time"] <= "2023-06-15T14:00:00Z"] + [future_poison] + \
                  [c for c in past if c["time"] > "2023-06-15T14:15:00Z"]
        cls.all.sort(key=lambda c: c["time"])
        write_hist(cls.root, "XAUUSD", "15m", cls.all)
        write_hist(cls.root, "XAGUSD", "15m", synth(50, "2024-03-05T00:00:00Z"))          # symbol wholly beyond dev
        cls.mod = load("build-pit-page.py")
        cls.out = os.path.join(cls.tmp, "p.html")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_cli(self, *args, env_root=None):
        env = dict(os.environ, BT_HISTORY_ROOT=env_root or self.root)
        return subprocess.run([sys.executable, "-W", "ignore", SCRIPT, *args], capture_output=True, text=True, env=env, cwd=self.tmp)


class NoFuture(Fixture):
    def test_poisoned_future_bar_absent_and_last_bar_is_knowable(self):
        r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", T_ISO, "--out", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = open(self.out, encoding="utf-8").read()
        self.assertNotIn(str(POISON), page)
        rows = init_data(page)["pit"]["tiers"][0]["rows"]
        t = datetime.datetime.fromisoformat(T_ISO.replace("Z", "+00:00"))
        self.assertTrue(rows)
        for r_ in rows:
            opened = datetime.datetime.fromisoformat(r_[5].replace("Z", "+00:00"))
            self.assertLessEqual(opened + datetime.timedelta(minutes=15), t)      # available_time <= T
        self.assertEqual(rows[-1][5], "2023-06-15T13:45:00Z")                     # the 14:00 bar is still forming at T

    def test_no_future_structure(self):
        b = load("build-pit-page.py")
        rows = b.pit_rows("XAUUSD", "15m", T_ISO, root=self.root)
        page = b.render("XAUUSD", "15m", T_ISO, "ICT", rows)
        for s in init_data(page)["pit"]["tiers"][0]["ict"]["structures"]:
            if s.get("available_at"):
                self.assertLessEqual(s["available_at"], T_ISO)


class DevOnly(Fixture):
    def test_refuses_at_or_after_cutoff(self):
        cutoff = self.mod.dev_cutoff()
        for at in (cutoff, "2024-03-02T00:00:00Z", "2025-01-01T00:00:00Z"):
            r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", at, "--out", self.out + ".x")
            self.assertNotEqual(r.returncode, 0, at)
            self.assertIn("REFUSED", r.stderr); self.assertIn("DEVELOPMENT", r.stderr)
            self.assertFalse(os.path.exists(self.out + ".x"))

    def test_cutoff_is_the_shared_constant(self):
        self.assertEqual(self.mod.dev_cutoff(), load("diagnose-methods.py").DEV_CUTOFF)
        self.assertNotIn("2024-03", open(SCRIPT, encoding="utf-8").read().split('"""', 2)[2])   # not restated in code

    def test_refuses_symbol_entirely_beyond_dev(self):
        r = self.run_cli("--symbol", "XAGUSD", "--tf", "15m", "--at", "2024-02-28T00:00:00Z", "--out", self.out + ".y")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no bar available", r.stderr)
        self.assertFalse(os.path.exists(self.out + ".y"))

    def test_refuses_naive_or_garbage_time(self):
        for at in ("2023-06-15T14:00:00", "yesterday"):
            r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", at, "--out", self.out + ".z")
            self.assertNotEqual(r.returncode, 0, at)

    def test_cutoff_boundary_and_offset_forms(self):
        """Review round 1: a date-only time is a clean REFUSED (no traceback); a +07:00 form mapping to the cutoff is
        refused; the last second before the cutoff is accepted by the time check."""
        for at in ("2024-03-01Z", "2024-03-01T07:00:00+07:00", "2024-03-01T00:00:00.000Z", "20240301T000000Z"):
            r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", at, "--out", self.out + ".b")
            self.assertNotEqual(r.returncode, 0, at)
            self.assertNotIn("Traceback", r.stderr, at)
            self.assertFalse(os.path.exists(self.out + ".b"), at)
        self.mod.check_at("2024-02-29T23:59:59Z")          # does not raise

    def test_unknown_timeframe_is_a_clean_refusal(self):
        r = self.run_cli("--symbol", "XAUUSD", "--tf", "7m", "--at", T_ISO, "--out", self.out + ".u")
        self.assertNotEqual(r.returncode, 0); self.assertNotIn("Traceback", r.stderr)

    def test_missing_history_refused(self):
        r = self.run_cli("--symbol", "XAUUSD", "--tf", "1H", "--at", T_ISO, "--out", self.out + ".w")
        self.assertNotEqual(r.returncode, 0); self.assertIn("no history", r.stderr)


class Structures(Fixture):
    def test_ict_structures_equal_direct_prefix_call(self):
        m = self.mod
        rows = m.pit_rows("XAUUSD", "15m", T_ISO, root=self.root)
        b = load("build-artifact.py")
        env = b.structures.ict_structures(rows, 4, "15m", methods=("ict",), opts=b.CHART_ICT_OPTS)   # the chart reading (1-bar swings)
        direct = {"structures": env["structures"], "dealing_range": env["dealing_range"], "bias": env["bias"]}
        _, data = m.entry_data(rows, "XAUUSD", "15m", "ICT")
        self.assertEqual(json.dumps(data["tiers"][0]["ict"], sort_keys=True), json.dumps(direct, sort_keys=True))
        # and the prefix equals a hand-truncation of the raw file at T (independent of pit.py)
        raw = [c for c in self.all if datetime.datetime.fromisoformat(c["time"].replace("Z", "+00:00")) + datetime.timedelta(minutes=15)
               <= datetime.datetime(2023, 6, 15, 14, tzinfo=datetime.timezone.utc)]
        self.assertEqual(rows, raw[-len(rows):])

    def test_wyckoff_lane_builds_and_matches_direct(self):
        m = self.mod
        rows = m.pit_rows("XAUUSD", "15m", T_ISO, root=self.root)
        b, data = m.entry_data(rows, "XAUUSD", "15m", "WYCKOFF-BOOK")
        self.assertEqual(json.dumps(data["tiers"][0]["wy"], sort_keys=True),
                         json.dumps(b.wy_json_engine(rows, "15m", "XAUUSD", "2"), sort_keys=True))
        self.assertEqual(data["analysed"], ["wyckoff"])


class NoOutcomes(Fixture):
    def test_no_plans_or_outcome_markers(self):
        r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", T_ISO, "--out", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        page = open(self.out, encoding="utf-8").read()
        d = init_data(page)["pit"]
        self.assertEqual(d["plans"], []); self.assertIsNone(d["invalidation"]); self.assertIsNone(d["updated"])
        blob = json.dumps(d).lower()
        for w in ("outcome", "pnl", "profit", "stopped", "target hit", "tp_hit", "sl_hit", "realized", "result"):
            self.assertNotIn(w, blob, w)
        # visible chrome (outside the inlined scripts) has no trade/verdict text either
        chrome = re.sub(r"<(script|style)>.*?</\1>", "", page, flags=re.S).lower()
        for w in ("outcome", "pnl", "profit", "stopped out", "verdict"):
            self.assertNotIn(w, chrome, w)


class Fixture5(Fixture):
    def test_builds_from_temp_root_and_respects_env(self):
        r = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", T_ISO, "--out", self.out, "--method", "WYCKOFF-BOOK")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("PIT PAGE OK", r.stdout)
        empty = os.path.join(self.tmp, "empty"); os.makedirs(empty)
        r2 = self.run_cli("--symbol", "XAUUSD", "--tf", "15m", "--at", T_ISO, "--out", self.out + ".e", env_root=empty)
        self.assertNotEqual(r2.returncode, 0)


if __name__ == "__main__":
    unittest.main()
