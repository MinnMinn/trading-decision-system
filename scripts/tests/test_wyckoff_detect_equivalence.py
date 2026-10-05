"""Randomized differential test: the CURRENT wyckoff_rules.detect_accumulations / detect_distributions vs a FROZEN copy
of the module as of 85bbc08 (fixtures/wyckoff_rules_frozen_85bbc08.py). Guards the byte-identical speed changes to the
`prior` loop and the bisect'ed `st`/`after` reads: output (repr), exceptions and STATS counters must be equal."""
import copy
import importlib.util
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import wyckoff_rules as NEW  # noqa: E402


def _load_frozen():
    spec = importlib.util.spec_from_file_location("wyckoff_rules_frozen_85bbc08",
                                                  os.path.join(HERE, "fixtures", "wyckoff_rules_frozen_85bbc08.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def gen(rnd, kind, n):
    O, H, L, C, V = [], [], [], [], []
    p = 100.0
    for i in range(n):
        if kind == "flat":
            o = c = h = l = p
        elif kind == "stair":
            p += -0.5 if (i // 7) % 2 == 0 else 0.3
            o = p; c = p + rnd.choice([-.1, .1]); h = max(o, c) + rnd.choice([0, .2]); l = min(o, c) - rnd.choice([0, .2])
        elif kind == "intpx":
            p = max(p + rnd.choice([-2, -1, 0, 1]), 1)
            o = p; c = p + rnd.choice([-1, 0, 1]); h = max(o, c) + rnd.choice([0, 1]); l = min(o, c) - rnd.choice([0, 1])
        elif kind == "down":
            p = max(p + rnd.gauss(-0.15, 1) + (2.5 * rnd.random() if rnd.random() < .15 else 0), 1)
            o = p; c = p + rnd.gauss(0, .6); h = max(o, c) + abs(rnd.gauss(0, .5)); l = min(o, c) - abs(rnd.gauss(0, .5))
        else:
            p = max(p + rnd.gauss(0, 1), 1)
            o = p; c = p + rnd.gauss(0, .6); h = max(o, c) + abs(rnd.gauss(0, .5)); l = min(o, c) - abs(rnd.gauss(0, .5))
        if rnd.random() < 0.02 and kind != "flat":
            h = l = c = o                                   # ~2 % zero-range bars
        O.append(o); H.append(h); L.append(l); C.append(c)
        V.append(rnd.choice([0, 1, 5, 10, 100]) if kind in ("flat", "intpx") else abs(rnd.gauss(100, 40)))
    return O, H, L, C, V


def _call(mod, fn, args, P, vk, side):
    try:
        if fn == "acc":
            return repr(mod.detect_accumulations(*args, P=P, volume_kind=vk, side=side)), None
        return repr(mod.detect_distributions(*args, P=P, volume_kind=vk)), None
    except Exception as e:  # compared, not swallowed
        return None, repr(e)


class DetectEquivalence(unittest.TestCase):
    def test_random_series_match_frozen(self):
        old = _load_frozen()
        rnd = random.Random(20261001)
        kinds = ["flat", "stair", "intpx", "down", "noisy"]
        total = nonempty = 0
        for _ in range(int(os.environ.get("WY_EQUIV_ITERS", "450"))):
            kind = rnd.choice(kinds)
            n = rnd.choice([0, 1, 2, 5, 8, 12, 20, 40, 80, 150, 300, 600])
            args = gen(rnd, kind, n)
            for fn, side in (("acc", "long"), ("acc", "short"), ("dist", None)):
                for nd in (0, 1, 2, 3):
                    for pv in (1, 2, 3):
                        Pn, Po = copy.deepcopy(NEW.PARAMS), copy.deepcopy(old.PARAMS)
                        # The frozen copy predates W8 (default ON since owner 2026-10-05): compare with W8 off so this
                        # stays a speed-refactor equivalence; W8 itself is pinned by test_wyckoff_chart_fidelity.
                        Pn["fx_w8_choch_in_box"] = False
                        for P in (Pn, Po):
                            P["downtrend_swings"] = nd; P["pivot"] = pv
                        if rnd.random() < .5:
                            flags = dict(fx_w1_tr_low_st=rnd.random() < .5, fx_w2_st_below_sc=rnd.random() < .5)
                            Pn.update(flags); Po.update(flags)
                        vk = rnd.choice(["traded", "tick"])
                        a = _call(NEW, fn, args, Pn, vk, side)
                        b = _call(old, fn, args, Po, vk, side)
                        total += 1
                        if a[0] not in (None, "[]"):
                            nonempty += 1
                        self.assertEqual(a, b, f"{kind} n={n} {fn} {side} nd={nd} pivot={pv}")
        self.assertEqual(NEW.STATS, old.STATS)
        self.assertGreater(nonempty, 300, f"vacuous: only {nonempty}/{total} non-empty outputs")


if __name__ == "__main__":
    unittest.main()
