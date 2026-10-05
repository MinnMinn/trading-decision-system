"""ICT objects re-derived from the candles they came from (code-review I5, fix round 1 for c8772fa).

The ICT detector lives in exactly one place now -- scripts/ict-scan.py `analyze()` (ADR 0009) -- and the chart draws
what `scripts/structures.py` wraps from it. When chart.js's own detector was removed, its node checker
(`scripts/tests/ict-invariants.js`, deleted in c8772fa; recoverable with `git show 3d52fae:scripts/tests/ict-invariants.js`)
went with it, and five of its checks had no replacement. They are ported here, against REAL stored history
(data/history/ohlcv.*.json) at several window ends, and each is re-derived from the candles, not from the
detector's own intermediate values:

  1. pct / eq: `eq` is the midpoint of the range, `pct` is the last close's position inside lo..hi.
  2. dealing range: nearest UNSWEPT (and not closed-through) BSL above / SSL below the last close, the window
     extreme only as the declared fallback, and `dr_source` says which (knowledge/ict/core-a.md 2.18-2.19).
  3. pool state: `swept` / `closed_through` re-derived by a fresh forward scan of the candles from the pool's last
     constituent swing (a wick through the level with a close back = swept; a body close beyond it = closed
     through, R6 -- and whichever comes first ends the scan).
  4. FVG: every FVG is the real three-candle gap at its own index, with its bounds taken from the outer candles,
     and its mitigation bar re-derived (knowledge/ict/core-a.md 2.21).
  5. MSS: a BODY close beyond the swing it names, that swing is a real confirmed pivot before the break, and the
     manipulation leg is ordered origin <= extreme <= MSS bar (2.17; core-b 2.2).

OTE and STDEV levels are not ported: no ICT code path produces them any more (`ictFromStructures` returns
`ote:null, std:null`), so there is no object left to check.

A check that could pass vacuously is a check that pins nothing, so each test also asserts it actually saw objects.
"""
import importlib.util
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HIST = os.path.join(ROOT, "data", "history")


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").replace(".py", ""),
                                                   os.path.join(ROOT, "scripts", name))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ict_scan = _load("ict-scan.py")

# (symbol, timeframe, bars) -- crypto + index CFD, three timeframes; window ENDS differ so the last close sits in
# different places relative to the pools (the dealing-range branches: pools / mixed / window).
SERIES = [("BTCUSDT", "15m", 576), ("BTCUSDT", "1H", 480), ("BTCUSDT", "4H", 360),
          ("ETHUSDT", "1H", 480), ("AUS200", "4H", 360), ("DE40", "1H", 480), ("ONDOUSDT", "4H", 360)]
TAILS = (0, 61, 173, 331)


def windows():
    for sym, tf, bars in SERIES:
        path = os.path.join(HIST, f"ohlcv.{sym}.{tf}.json")
        if not os.path.exists(path):
            continue
        full = json.load(open(path, encoding="utf-8"))["candles"]
        for tail in TAILS:
            end = len(full) - tail
            if end - bars < 0:
                continue
            c = full[end - bars:end]
            yield f"{sym} {tf} -{tail}", c, ict_scan.analyze(c, 20, tf, methods=("ict",))


class IctInvariantsReDerivedFromCandles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.W = list(windows())

    def test_there_is_real_history_to_check(self):
        self.assertGreaterEqual(len(self.W), 8, "data/history is missing: every check below would pass vacuously")

    def test_1_pct_and_eq_come_from_the_candles(self):
        seen = 0
        for tag, c, a in self.W:
            self.assertAlmostEqual(a["eq"], (a["lo"] + a["hi"]) / 2, places=9, msg=f"{tag}: eq is not the midpoint")
            last = c[-1]["close"]
            self.assertEqual(a["last"], last, tag)
            if a["hi"] > a["lo"]:
                self.assertAlmostEqual(a["pct"], (last - a["lo"]) / (a["hi"] - a["lo"]), places=9,
                                       msg=f"{tag}: pct is not the last close inside lo..hi")
                seen += 1
            else:
                self.assertEqual(a["pct"], 0.5, tag)   # the declared degenerate case, never a divide by zero
            # the window fallback extremes are the candles' own extremes
            self.assertEqual(a["window_hi"], max(x["high"] for x in c), tag)
            self.assertEqual(a["window_lo"], min(x["low"] for x in c), tag)
        self.assertGreater(seen, 0)

    def _check_dealing_range(self, tag, c, a):
        last = c[-1]["close"]
        live = [p for p in a["pools"] if p["swept"] < 0 and p["state"] != "closed_through"]
        above = [p["level"] for p in live if p["kind"] == "BSL" and p["level"] > last]
        below = [p["level"] for p in live if p["kind"] == "SSL" and p["level"] < last]
        self.assertEqual(a["hi"], min(above) if above else a["window_hi"], f"{tag}: range high is not the nearest unswept buyside above")
        self.assertEqual(a["lo"], max(below) if below else a["window_lo"], f"{tag}: range low is not the nearest unswept sellside below")
        want = "pools" if (above and below) else ("mixed" if (above or below) else "window")
        self.assertEqual(a["dr_source"], want, f"{tag}: dr_source")
        # the pool KIND matters: a BSL below the close, or an SSL above it, is never a range edge
        self.assertTrue(all(x > last for x in above) and all(x < last for x in below), tag)
        return a["dr_source"]

    def test_2_dealing_range_is_the_nearest_unswept_pool_and_says_where_it_came_from(self):
        sources = {self._check_dealing_range(tag, c, a) for tag, c, a in self.W}
        self.assertIn("pools", sources, "no real window exercised the pools branch")

    def test_2b_the_window_extreme_fallback_is_declared_as_such(self):
        """Real history only reaches the `pools` branch, so the two fallbacks are pinned on constructed candles:
        a monotonic rise has no swing at all (dr_source `window`); a V has a swing LOW but no swing high above the
        close (dr_source `mixed`: one edge from a pool, the other from the window extreme)."""
        def candles(closes):
            out = []
            for k, cl in enumerate(closes):
                op = closes[k - 1] if k else cl
                out.append({"time": f"2026-01-{1 + k // 24:02d}T{k % 24:02d}:00:00Z", "open": op,
                            "high": max(op, cl) + 0.1, "low": min(op, cl) - 0.1, "close": cl, "volume": 1})
            return out
        rising = candles([100 + k for k in range(60)])
        rising[0]["low"] -= 1.0   # bars 0/1 had EQUAL lows, which a 1-bar pivot (default since 2026-10-05) reads as a swing low
        v = candles([200 - k for k in range(30)] + [170 + 2 * k for k in range(1, 61)])
        got = {}
        for name, c in (("rising", rising), ("v", v)):
            got[name] = self._check_dealing_range(name, c, ict_scan.analyze(c, 20, "1H", methods=("ict",)))
        self.assertEqual(got, {"rising": "window", "v": "mixed"})

    def test_3_pool_state_is_rederived_from_the_candles(self):
        seen = {"intact": 0, "swept": 0, "closed_through": 0}
        for tag, c, a in self.W:
            H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
            n = len(c)
            for p in a["pools"]:
                self.assertIsNotNone(p.get("to"), f"{tag}: pool has no forming bar")
                swept, state, closed_at = -1, "intact", None
                for j in range(p["to"] + 1, n):
                    if (p["kind"] == "BSL" and C[j] > p["level"]) or (p["kind"] == "SSL" and C[j] < p["level"]):
                        state, closed_at = "closed_through", j
                        break
                    if (p["kind"] == "BSL" and H[j] > p["level"] and C[j] < p["level"]) or \
                       (p["kind"] == "SSL" and L[j] < p["level"] and C[j] > p["level"]):
                        swept, state = j, "swept"
                        break
                self.assertEqual((p["state"], p["swept"], p["closed_at"]), (state, swept, closed_at),
                                 f"{tag}: {p['kind']} {p['level']} disagrees with the candles")
                # the level itself is a real extreme of the swing it names
                if p["type"] == "old":
                    self.assertEqual(p["level"], H[p["from"]] if p["kind"] == "BSL" else L[p["from"]],
                                     f"{tag}: an old pool's level is not its swing's own extreme")
                seen[state] += 1
        for k, v in seen.items():
            self.assertGreater(v, 0, f"no {k} pool in any window: that state is unpinned")

    def test_4_every_fvg_is_the_three_candle_gap_at_its_own_index(self):
        seen = mitigated = 0
        for tag, c, a in self.W:
            H = [x["high"] for x in c]; L = [x["low"] for x in c]
            n = len(c)
            for f in a["fvgs_all"]:
                i = f["i"]
                self.assertTrue(1 <= i < n - 1, f"{tag}: FVG index {i} is not an interior bar")
                if f["type"] == "bull":
                    self.assertLess(H[i - 1], L[i + 1], tag)
                    self.assertEqual((f["lo"], f["hi"]), (H[i - 1], L[i + 1]), f"{tag}: bull FVG bounds are not the outer candles'")
                    end = next((j for j in range(i + 2, n) if L[j] <= f["hi"]), None)
                else:
                    self.assertGreater(L[i - 1], H[i + 1], tag)
                    self.assertEqual((f["lo"], f["hi"]), (H[i + 1], L[i - 1]), f"{tag}: bear FVG bounds are not the outer candles'")
                    end = next((j for j in range(i + 2, n) if H[j] >= f["lo"]), None)
                self.assertEqual(f["mitigated"], end is not None, f"{tag}: mitigated flag")
                self.assertEqual(f["end"], end if end is not None else n - 1, f"{tag}: FVG end bar")
                self.assertAlmostEqual(f["ce"], (f["lo"] + f["hi"]) / 2, places=9)
                seen += 1
                mitigated += bool(f["mitigated"])
        self.assertGreater(seen, 0)
        self.assertGreater(mitigated, 0, "no mitigated FVG in any window: mitigation re-derivation is unpinned")

    def test_5_every_mss_is_a_body_close_beyond_a_real_swing_with_ordered_legs(self):
        seen = 0
        for tag, c, a in self.W:
            H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
            times = {x["time"]: k for k, x in enumerate(c)}
            highs, lows = set(a["pivots_high"]), set(a["pivots_low"])
            for m in a["mss_all"]:
                i, bull = m["i"], m["type"] == "bull"
                self.assertTrue(0 <= i < len(c), tag)
                self.assertTrue(C[i] > m["level"] if bull else C[i] < m["level"], f"{tag}: MSS is not a BODY close beyond its swing")
                # the swing it names is a confirmed pivot that formed BEFORE the break
                swing = [k for k in (highs if bull else lows) if k < i and (H[k] if bull else L[k]) == m["level"]]
                self.assertTrue(swing, f"{tag}: MSS level {m['level']} is not a pivot {'high' if bull else 'low'} before bar {i}")
                # manipulation leg: origin <= extreme <= MSS bar
                e = times[m["ext_time"]]
                self.assertLessEqual(e, i, f"{tag}: MSS extreme is after the break")
                self.assertEqual(m["ext"], L[e] if bull else H[e], f"{tag}: MSS extreme price is not the candle's own")
                origins = [k for k in range(0, e + 1) if (H[k] if bull else L[k]) == m["origin"]]
                self.assertTrue(origins, f"{tag}: MSS origin {m['origin']} is not a candle extreme at or before the leg extreme")
                self.assertLessEqual(min(origins), e)
                seen += 1
        self.assertGreater(seen, 0, "no MSS in any window")


if __name__ == "__main__":
    unittest.main()
