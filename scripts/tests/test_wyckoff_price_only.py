"""wyckoff_rules PARAMS["price_only"]: the Wyckoff re-test's price-only detector DET-PO
(docs/plans/2026-10-04-wyckoff-retest-preregistration-DRAFT.md §3.1, §10 item 1). Synthetic and hand-built bars only;
nothing under data/ is read.

  1. DefaultIsV1. The key exists and is False. An explicit False gives the same output as a missing key. With the key
     off, the module reproduces the frozen 85bbc08 copy (fixtures/wyckoff_rules_frozen_85bbc08.py) with every fx/V key
     randomized, including fx_w3, fx_w5 and fx_w4a, which test_wyckoff_detect_equivalence.py does not toggle. That
     test (default PARAMS, which now carry price_only=False) is the other half of the byte-identity proof.
  2. EachVolumeGate. Two hand-built structures: a Spring path with a Test, an SOS and a BU, and an LPS[C] path with an
     SOS and a BU. For each of the six guarded clauses there is a volume series that breaks ONLY that clause. Key off:
     the event that clause gates moves or disappears, so the clause is live on this fixture. Key on: the record equals
     the key-on record on the book volume outside VOLUME_FIELDS. The same is checked through detect_distributions on
     the price-mirrored bars.
  3. VolumeInvariance. Random synthetic series with the key on: every record field outside VOLUME_FIELDS is unchanged
     under a random permutation of V, its reversal, rescaling by 1e-6 / 0.37 / 1e6, all-zero V and constant V. The fx
     keys of perturbation P1 (fx_w1/w2/w3) are randomized. Non-vacuous: the test asserts minimum counts of records
     that reach the Test, the SOS, the BU and the LPS[C] BU, and asserts that with the key OFF the same transformations
     do change some records.

VOLUME_FIELDS (vol_ratio, vol_type, rec_ratio, vpoc/vah/val/lvn, abandon) are recorded-only R7/R10 outputs that still
read V; §3.1 keeps them computed and says the price-only family reads none of them."""
import importlib.util
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import wyckoff_rules as W  # noqa: E402
from test_wyckoff_detect_equivalence import gen as equivalence_gen  # noqa: E402  (the frozen-diff corpus, one source)


def _load_frozen():
    spec = importlib.util.spec_from_file_location("wyckoff_rules_frozen_85bbc08_po",
                                                  os.path.join(HERE, "fixtures", "wyckoff_rules_frozen_85bbc08.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def leg(start, end, n, vol=10.0):
    """n bars ramping linearly start -> end, small wick each side (helper shape of test_wyckoff_fidelity.py)."""
    out = []
    for i in range(n):
        t = (i + 1) / n
        c = start + (end - start) * t
        o = start + (end - start) * (i / n)
        out.append((o, max(o, c) + 0.05, min(o, c) - 0.05, c, vol))
    return out


def base():
    """Downtrend -> SC (79.95, bar 40) -> AR (110.05, bar 46) -> ST (bar 52) -> three CHoBEV up-swings, the third on
    extra volume (CHoCH at bar 70) -> three Phase-B swings ending at 92 (test_wyckoff_fidelity.base_accumulation)."""
    b = []
    b += leg(104, 102, 5) + leg(102, 99, 5) + leg(99, 101, 5) + leg(101, 97, 5)
    b += leg(97, 100, 5) + leg(100, 90, 5) + leg(90, 96, 5) + leg(96, 80, 5)
    b += leg(80, 110, 6) + leg(110, 85, 6) + leg(85, 108, 6) + leg(108, 88, 6) + leg(88, 106, 6, vol=14.0)
    b += leg(106, 90, 6) + leg(90, 100, 6) + leg(100, 92, 6)
    return b


def phase_d(b):
    """SOS bar (wide spread, volume 30), its commitment close, a pullback into the BU zone on lower volume (5), and a BU
    up-close above the ceiling whose low sits above the zone, then a drift up."""
    return b + [(108, 114, 107.5, 113.5, 30.0), (113.5, 114.5, 112, 114, 10.0), (114, 114.2, 111, 111.5, 5.0),
                (111.5, 115, 113.2, 114.8, 10.0)] + leg(114.8, 118, 5)


def spring_bars():
    """Spring at bar 92 (low 78 under the SC, same-bar reclaim), Test at 93 (volume 5 < the Spring's 20), SOS at 102,
    BU at 105 (pullback bar 104)."""
    b = base() + leg(92, 82, 4) + [(82, 82.5, 78, 81, 20.0)] + leg(81, 86, 3, vol=5.0) + leg(86, 108, 6)
    return phase_d(b)


def lpsc_bars():
    """No Spring: Phase B breaks out directly. LPS[C] SOS at bar 94, pullback at 96, BU at 97."""
    return phase_d(base() + leg(92, 108, 6))


def cols(bars):
    return ([b[0] for b in bars], [b[1] for b in bars], [b[2] for b in bars], [b[3] for b in bars],
            [b[4] for b in bars])


def mirror(bars, k=300.0):
    """Price-inverted twin (o,h,l,c -> k-o, k-l, k-h, k-c; volume unchanged): an accumulation here is a distribution
    there (WA p101), the inversion detect_distributions applies internally."""
    return [(k - o, k - l, k - h, k - c, v) for (o, h, l, c, v) in bars]


def strip(recs):
    """Records without VOLUME_FIELDS: everything the price-only family may read."""
    return [{k: v for k, v in r.items() if k not in W.VOLUME_FIELDS} for r in recs]


def run(fn, O, H, L, C, V, P, side="long"):
    """(records, None) or (None, repr(exception)): exceptions are compared, not swallowed."""
    try:
        if fn == "acc":
            return W.detect_accumulations(O, H, L, C, V, P=P, side=side), None
        return W.detect_distributions(O, H, L, C, V, P=P), None
    except Exception as e:  # noqa: BLE001
        return None, repr(e)


ON = dict(W.PARAMS, price_only=True)
OFF = dict(W.PARAMS)


class DefaultIsV1(unittest.TestCase):

    def test_key_exists_and_defaults_false(self):
        self.assertIn("price_only", W.PARAMS)
        self.assertIs(W.PARAMS["price_only"], False)

    def test_volume_fields_are_record_keys(self):
        O, H, L, C, V = cols(spring_bars())
        rec = W.detect_accumulations(O, H, L, C, V, P=OFF)[0]
        self.assertTrue(set(W.VOLUME_FIELDS) <= set(rec), set(W.VOLUME_FIELDS) - set(rec))

    def test_explicit_false_equals_absent_on_hand_built(self):
        absent = {k: v for k, v in W.PARAMS.items() if k != "price_only"}
        for bars in (spring_bars(), lpsc_bars()):
            O, H, L, C, V = cols(bars)
            self.assertEqual(repr(W.detect_accumulations(O, H, L, C, V, P=absent)),
                             repr(W.detect_accumulations(O, H, L, C, V, P=OFF)))

    def test_key_off_matches_frozen_85bbc08_with_every_fx_key(self):
        old = _load_frozen()
        rnd = random.Random(20261004)
        W.STATS.clear(); old.STATS.clear()
        nonempty = total = 0
        for _ in range(250):
            kind = rnd.choice(["flat", "stair", "intpx", "down", "noisy"])
            args = equivalence_gen(rnd, kind, rnd.choice([0, 5, 40, 150, 300, 600]))
            flags = dict(fx_w1_tr_low_st=rnd.random() < .5, fx_w2_st_below_sc=rnd.random() < .5,
                         fx_w3_mSOW_spring=rnd.random() < .5, fx_w5_vp_abandon=rnd.random() < .5,
                         fx_w4a_linger_closes=rnd.choice([None, 2, 3, 4]), pivot=rnd.choice([1, 2, 3]),
                         downtrend_swings=rnd.choice([0, 1, 2]))
            for fn, side in (("acc", "long"), ("acc", "short"), ("dist", None)):
                vk = rnd.choice(["traded", "tick"])
                Pnew = dict(W.PARAMS, **flags)                  # price_only=False, explicit
                Pold = dict(old.PARAMS, **flags)                # no price_only key at all
                try:
                    a = repr(W.detect_accumulations(*args, P=Pnew, volume_kind=vk, side=side) if fn == "acc"
                             else W.detect_distributions(*args, P=Pnew, volume_kind=vk))
                except Exception as e:  # noqa: BLE001
                    a = "EXC " + repr(e)
                try:
                    b = repr(old.detect_accumulations(*args, P=Pold, volume_kind=vk, side=side) if fn == "acc"
                             else old.detect_distributions(*args, P=Pold, volume_kind=vk))
                except Exception as e:  # noqa: BLE001
                    b = "EXC " + repr(e)
                total += 1
                nonempty += a not in ("[]",) and not a.startswith("EXC")
                self.assertEqual(a, b, f"{kind} {fn} {side} {flags}")
        self.assertEqual(W.STATS, old.STATS)
        self.assertGreater(nonempty, 150, f"vacuous: only {nonempty}/{total} non-empty outputs")


class EachVolumeGate(unittest.TestCase):
    """For each guarded clause, a volume series that breaks only that clause on a hand-built structure."""

    # (name, fixture, bars whose volume is overwritten, new volume, the field the clause gates, its book value)
    CASES = (
        ("R1 CHoBEV effort", spring_bars, range(40, 71), 1.0, "choch", 70),       # post-SC up-swings on tiny volume
        ("R8 Test", spring_bars, (92,), 1.0, "test", 93),                          # no bar is quieter than the Spring
        ("R11 SOS effort", spring_bars, (102,), 1.0, "sos_bar", 102),              # breakout bar below its average
        ("R11 BU pullback", spring_bars, (104,), 50.0, "bu", 105),                 # pullback louder than the SOS
        ("R11 LPS[C] SOS effort", lpsc_bars, (94,), 1.0, "sos_bar", 94),
        ("R11 LPS[C] BU pullback", lpsc_bars, (96,), 50.0, "bu", 97),
    )

    @staticmethod
    def _event(rec, field):
        """The gated event's bar (`bu` is a dict whose `low` is price-mapped by the mirror; its `bar` is not)."""
        return (rec["bu"] or {}).get("bar") if field == "bu" else rec[field]

    def _check(self, fn):
        for name, fixture, idx, vol, field, book in self.CASES:
            with self.subTest(clause=name, fn=fn):
                b = fixture() if fn == "acc" else mirror(fixture())
                O, H, L, C, V = cols(b)
                Vbad = list(V)
                for i in idx:
                    Vbad[i] = vol
                book_off, _ = run(fn, O, H, L, C, V, OFF)
                bad_off, _ = run(fn, O, H, L, C, Vbad, OFF)
                book_on, _ = run(fn, O, H, L, C, V, ON)
                bad_on, _ = run(fn, O, H, L, C, Vbad, ON)
                self.assertEqual(len(book_off), 1)
                self.assertEqual(self._event(book_off[0], field), book, "fixture: book volume passes every gate")
                self.assertNotEqual(strip(bad_off), strip(book_off), "key off: this clause must bite")
                if bad_off:
                    self.assertNotEqual(self._event(bad_off[0], field), book)
                self.assertEqual(strip(bad_on), strip(book_on), "key on: volume must not move any event")
                self.assertEqual(strip(book_on), strip(book_off), "book volume: on and off agree on structure")

    def test_accumulation(self):
        self._check("acc")

    def test_distribution_mirror(self):
        self._check("dist")


class VolumeInvariance(unittest.TestCase):

    @staticmethod
    def series(rnd, n):
        """A random walk with occasional up-jumps (reactions for the CHoBEV test) and widely varying volume."""
        O, H, L, C, V = [], [], [], [], []
        p = 100.0
        drift = rnd.choice([-0.15, -0.05, 0.0])
        for _ in range(n):
            p = max(p + rnd.gauss(drift, 1) + (2.5 * rnd.random() if rnd.random() < .15 else 0), 1)
            o = p; c = p + rnd.gauss(0, .6); h = max(o, c) + abs(rnd.gauss(0, .5)); l = min(o, c) - abs(rnd.gauss(0, .5))
            O.append(o); H.append(h); L.append(l); C.append(c); V.append(abs(rnd.gauss(100, 60)))
        return O, H, L, C, V

    def test_records_ignore_any_permutation_or_rescaling_of_volume(self):
        rnd = random.Random(20261004)
        cov = dict(rec=0, test=0, sos=0, bu=0, lpsc_bu=0, off_changed=0)
        corpus = [self.series(rnd, rnd.choice([150, 300, 600])) for _ in range(300)]
        corpus += [cols(b) for b in (spring_bars(), lpsc_bars(), mirror(spring_bars()), mirror(lpsc_bars()))]
        for O, H, L, C, V in corpus:
            n = len(V)
            perm = list(V); rnd.shuffle(perm)
            variants = (perm, V[::-1], [v * 1e-6 for v in V], [v * 0.37 for v in V], [v * 1e6 for v in V],
                        [0.0] * n, [1.0] * n)
            for fn, side in (("acc", "long"), ("acc", "short"), ("dist", None)):
                fx = dict(fx_w1_tr_low_st=rnd.random() < .3, fx_w2_st_below_sc=rnd.random() < .3,
                          fx_w3_mSOW_spring=rnd.random() < .3)
                on, off = dict(ON, **fx), dict(OFF, **fx)
                ref, err = run(fn, O, H, L, C, V, on, side)
                ref_off, _ = run(fn, O, H, L, C, V, off, side)
                for r in ref or ():
                    cov["rec"] += 1
                    if r["path"] == "spring":
                        cov["test"] += r["test"] is not None
                        cov["sos"] += r["sos"] is not None
                        cov["bu"] += r["bu"] is not None
                    else:
                        cov["lpsc_bu"] += r["bu"] is not None
                for Vx in variants:
                    got, gerr = run(fn, O, H, L, C, Vx, on, side)
                    self.assertEqual(gerr, err)
                    self.assertEqual(strip(got or []), strip(ref or []), f"{fn} {side} {fx} n={n}")
                    got_off, _ = run(fn, O, H, L, C, Vx, off, side)
                    cov["off_changed"] += strip(got_off or []) != strip(ref_off or [])
        # Non-vacuous: every gated event is reached with the key on, and the same transformations DO move records
        # with the key off (so invariance here is a property of price_only, not of the corpus).
        self.assertGreater(cov["rec"], 300, cov)
        self.assertGreater(cov["test"], 30, cov)
        self.assertGreater(cov["sos"], 5, cov)
        self.assertGreater(cov["bu"], 5, cov)
        self.assertGreater(cov["lpsc_bu"], 30, cov)
        self.assertGreater(cov["off_changed"], 100, cov)


if __name__ == "__main__":
    unittest.main()
