"""Who gets a shared signal first, and whether that answer survives being asked again months later.

docs/plans/2026-09-19-multi-account.md §0.3 item 3. One setup serves many customer accounts; when it fires
they all want the same instrument on the same side at the same moment. The order was previously "whichever
runner process ticked first", which is biased the same way every time and cannot be reconstructed afterwards.
"""
import collections
import importlib.util
import json
import os
import statistics
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mod():
    spec = importlib.util.spec_from_file_location("dispatch_order",
                                                  os.path.join(ROOT, "scripts", "dispatch_order.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


DO = _mod()
ACCOUNTS = [f"acc-{i:03d}" for i in range(12)]


def sid(n):
    """A DISTINCT signal per n. The first draft wrapped the day at 28, so the fairness tests drew from 28
    signals however many iterations they ran -- and 28 draws over 12 accounts is noise, not a distribution."""
    day = (n % 28) + 1
    return DO.signal_id("cfd-scalping-ict-15m", "XAUUSD", "long",
                        f"2026-{(n // 28) % 12 + 1:02d}-{day:02d}T{(n // 336) % 24:02d}:00:00Z")


class TheOrderIsReproducible(unittest.TestCase):
    """The property that makes it an answer to a dispute rather than an apology."""

    def test_the_same_signal_always_gives_the_same_order(self):
        self.assertEqual(DO.order(sid(1), ACCOUNTS), DO.order(sid(1), list(reversed(ACCOUNTS))))

    def test_a_rank_can_be_recomputed_from_the_signal_alone(self):
        want = DO.rank(sid(3), "acc-005", ACCOUNTS)["rank"]
        self.assertEqual(DO.rank(sid(3), "acc-005", ACCOUNTS)["rank"], want)

    def test_the_order_is_a_permutation_of_exactly_the_eligible_set(self):
        self.assertEqual(sorted(DO.order(sid(2), ACCOUNTS)), sorted(ACCOUNTS))

    def test_different_signals_give_different_orders(self):
        seen = {tuple(DO.order(sid(n), ACCOUNTS)) for n in range(20)}
        self.assertGreater(len(seen), 1, "every signal produced the same queue; the id is not reaching the hash")


class NoAccountIsStructurallyAdvantaged(unittest.TestCase):
    """The whole reason not to leave it to process scheduling."""

    def test_first_place_is_shared_roughly_evenly(self):
        firsts = collections.Counter(DO.order(sid(n), ACCOUNTS)[0] for n in range(6000))
        self.assertEqual(len(firsts), len(ACCOUNTS), "some account was never first in 6000 signals")
        expected = 6000 / len(ACCOUNTS)
        for acc, n in firsts.items():
            self.assertLess(abs(n - expected) / expected, 0.25,
                            f"{acc} was first {n} times, expected about {expected:.0f}")

    def test_mean_rank_is_near_the_middle_for_everyone(self):
        ranks = collections.defaultdict(list)
        for n in range(3000):
            for i, acc in enumerate(DO.order(sid(n), ACCOUNTS)):
                ranks[acc].append(i)
        middle = (len(ACCOUNTS) - 1) / 2
        for acc, rs in ranks.items():
            self.assertLess(abs(statistics.mean(rs) - middle), 0.5,
                            f"{acc} averages rank {statistics.mean(rs):.2f}, not {middle}")

    def test_account_id_alone_does_not_decide_the_order(self):
        """An order that is just sorted(ids) would pass the reproducibility tests and fail the fairness ones,
        so this pins the difference directly."""
        self.assertNotEqual(DO.order(sid(7), ACCOUNTS), sorted(ACCOUNTS))


class TheCostIsDeclaredNotCompiledIn(unittest.TestCase):
    def test_the_stagger_has_one_authored_source(self):
        d = json.load(open(os.path.join(ROOT, "docs", "architecture", "execution-safety.json"),
                           encoding="utf-8"))["dispatch"]
        self.assertIsInstance(d["stagger_ms"], (int, float))
        self.assertGreaterEqual(d["stagger_ms"], 0)

    def test_the_worst_wait_is_bounded_however_many_accounts_there_are(self):
        """A fixed stagger does not survive growth: 100 accounts x 200 ms is 19.8 s for the last one, which
        is a different product rather than a fairer one. The gap shrinks so the DEADLINE holds."""
        budget = DO.max_total_delay_ms() / 1000.0
        for n in (2, 12, 25, 100, 500):
            gap = DO.effective_stagger_ms(n)
            self.assertLessEqual((n - 1) * gap / 1000.0, budget + 1e-9, f"n={n} exceeds the total budget")

    def test_below_the_binding_point_the_declared_stagger_is_used_exactly(self):
        n = int(DO.max_total_delay_ms() // DO.stagger_ms())          # the largest n the budget still fits
        self.assertAlmostEqual(DO.effective_stagger_ms(n), DO.stagger_ms())

    def test_above_it_the_gap_shrinks_rather_than_the_deadline_slipping(self):
        n = int(DO.max_total_delay_ms() // DO.stagger_ms()) + 10
        self.assertLess(DO.effective_stagger_ms(n), DO.stagger_ms())
        self.assertAlmostEqual((n - 1) * DO.effective_stagger_ms(n), DO.max_total_delay_ms())

    def test_a_single_account_waits_for_nobody(self):
        self.assertEqual(DO.effective_stagger_ms(1), 0.0)

    def test_rank_reports_the_worst_wait_so_the_cost_is_visible_at_the_call_site(self):
        r = DO.rank(sid(5), ACCOUNTS[0], ACCOUNTS)
        self.assertIn("worst_delay_s", r)
        self.assertIn("gap_ms", r)

    def test_delay_grows_with_rank(self):
        seq = DO.order(sid(11), ACCOUNTS)
        delays = [DO.rank(sid(11), a, ACCOUNTS)["delay_s"] for a in seq]
        self.assertEqual(delays, sorted(delays))
        self.assertEqual(delays[0], 0.0, "the first account must not wait")

    def test_the_module_never_sleeps(self):
        """It returns a delay for the caller to honour. A module that sleeps cannot be tested for what it
        decides, and would put a sleep on the order path where nobody can see it."""
        src = open(os.path.join(ROOT, "scripts", "dispatch_order.py"), encoding="utf-8").read()
        self.assertNotIn("time.sleep", src)

    def test_a_missing_dispatch_block_refuses_rather_than_defaulting(self):
        import tempfile
        bad = os.path.join(tempfile.mkdtemp(), "no-dispatch.json")
        json.dump({"requirements": []}, open(bad, "w"))
        m = _mod(); m.CONFIG = bad
        with self.assertRaises(m.DispatchError):
            m.stagger_ms()


class BadInputRefuses(unittest.TestCase):
    def test_an_empty_signal_id_is_refused(self):
        with self.assertRaises(DO.DispatchError):
            DO.order("", ACCOUNTS)

    def test_duplicate_accounts_are_refused(self):
        with self.assertRaises(DO.DispatchError):
            DO.order(sid(1), ACCOUNTS + [ACCOUNTS[0]])

    def test_ranking_an_account_outside_the_set_is_refused(self):
        with self.assertRaises(DO.DispatchError):
            DO.rank(sid(1), "stranger", ACCOUNTS)

    def test_signal_id_requires_every_field(self):
        for args in (("", "X", "long", "t"), ("s", "", "long", "t"), ("s", "X", "", "t"), ("s", "X", "long", "")):
            with self.subTest(args=args), self.assertRaises(DO.DispatchError):
                DO.signal_id(*args)

    def test_the_signal_id_is_the_same_four_fields_the_runner_dedupes_on(self):
        """Keyed on one signal, not on a tick -- otherwise the queue reshuffles every 15 seconds while the
        limit is still working."""
        self.assertEqual(DO.signal_id("s", "X", "long", "t"), "s|X|long|t")


if __name__ == "__main__":
    unittest.main()
