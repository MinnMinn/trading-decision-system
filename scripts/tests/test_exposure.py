"""The aggregate-exposure gate: the one place that can see 100 accounts betting on the same signal.

CLAUDE.md §34 names "existing exposure" as a risk input. scripts/risk_model.py open_risk() measures ONE book;
until 2026-09-19 nothing summed across books because only one live account per venue was allowed at all
(scripts/account_profile.py:123-132). docs/plans/2026-09-19-multi-account.md §1.2 is the argument for this
module: ten accounts each risking their own 1 % on the same setup is a single 10 % bet, and every per-account
check passes it.

Every test below drives the module against a temporary ledger, never data/live/exposure.json.
"""
import importlib.util
import json
import os
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _mod():
    spec = importlib.util.spec_from_file_location("exposure", os.path.join(ROOT, "scripts", "exposure.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def pos(qty, entry, stop):
    return {"qty": qty, "entry": entry, "stop": stop}


class Gate(unittest.TestCase):

    def setUp(self):
        self.EX = _mod()
        self.dir = tempfile.mkdtemp()
        self.EX.PATH = os.path.join(self.dir, "exposure.json")
        self.EX.LOCK = self.EX.PATH + ".lock"

    # ---------------------------------------------------------------- the ceiling itself

    def test_the_correlated_cap_has_one_authored_source_and_is_a_count(self):
        v = json.load(open(os.path.join(ROOT, "docs", "architecture", "risk-config.json"),
                           encoding="utf-8"))["max_correlated_accounts"]
        self.assertIsInstance(v, int)
        self.assertGreaterEqual(v, 1)

    def test_a_missing_correlated_cap_refuses_rather_than_falling_back(self):
        bad = os.path.join(self.dir, "no-cap.json")
        json.dump({"max_portfolio_risk_pct": 0.05}, open(bad, "w"))
        self.EX.CONFIG = bad
        with self.assertRaises(self.EX.ExposureRefused):
            self.EX._read_correlated_cap()

    def test_the_ceiling_has_one_authored_source_and_it_is_a_fraction(self):
        v = json.load(open(os.path.join(ROOT, "docs", "architecture", "risk-config.json"),
                           encoding="utf-8"))["max_portfolio_risk_pct"]
        self.assertIsInstance(v, float)
        self.assertGreater(v, 0)
        self.assertLessEqual(v, 1, "a `5` typed for '5 %' would authorise 500 % of total equity")

    def test_a_missing_ceiling_refuses_rather_than_falling_back(self):
        bad = os.path.join(self.dir, "no-ceiling.json")
        json.dump({"max_risk_pct": 0.01}, open(bad, "w"))
        self.EX.CONFIG = bad
        with self.assertRaises(self.EX.ExposureRefused):
            self.EX._read_ceiling()

    def test_a_percent_typed_as_a_whole_number_refuses(self):
        bad = os.path.join(self.dir, "five.json")
        json.dump({"max_portfolio_risk_pct": 5}, open(bad, "w"))
        self.EX.CONFIG = bad
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX._read_ceiling()
        self.assertIn("500", str(cm.exception))

    # ---------------------------------------------------------------- the claim that turned out to be false

    def test_a_fraction_of_summed_equity_is_invariant_in_the_number_of_accounts(self):
        """This is the arithmetic that falsified the module's first design, kept as a test so the wrong gate
        cannot be reintroduced. N accounts each risking 1 % of their OWN equity is 1 % of the total, for any N
        -- so max_portfolio_risk_pct cannot be the gate that makes multi-account safe."""
        for n in (1, 10, 100):
            self.setUp()
            for i in range(n):
                self.EX.report(f"acc-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
            self.assertAlmostEqual(self.EX.totals()["fraction"], 0.01, places=9,
                                   msg=f"the summed fraction moved with N={n}; it must not")

    # ---------------------------------------------------------------- correlation is the real gate

    def test_the_cap_binds_on_one_owners_accounts_holding_the_same_symbol_and_side(self):
        cap = self.EX._read_correlated_cap()
        for i in range(cap):
            self.EX.report(f"acc-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0,
                           owner="cust-1")
        self.EX.report("acc-next", {}, equity=10000.0, owner="cust-1")
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("acc-next", "BTCUSDT", "long", want_risk_usd=100.0)
        msg = str(cm.exception)
        self.assertIn("acc-next", msg)
        self.assertIn("cust-1", msg)
        self.assertIn("BTCUSDT", msg)
        self.assertIn("daily-loss limit", msg, "the refusal must say WHY correlation is the hazard")

    def test_another_customer_is_not_blocked_by_the_first_customers_positions(self):
        """The business is customers renting a methodology and handing over their own account (user,
        2026-09-19). Two customers who both chose the same methodology will hold the same position; refusing
        the second is not risk management, it is deciding that whoever's runner ticks first wins."""
        cap = self.EX._read_correlated_cap()
        for i in range(cap + 3):
            self.EX.report(f"a-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0,
                           owner="cust-1")
        self.EX.report("b-000", {}, equity=10000.0, owner="cust-2")
        g = self.EX.quota("b-000", "BTCUSDT", "long", want_risk_usd=10.0)
        self.assertEqual(g["correlated_holders"], 0, "cust-2 has no sibling holding it")
        self.assertEqual(g["house_holders"], cap + 3, "the house-wide count must still be reported")

    def test_an_account_with_no_declared_owner_is_its_own_pool(self):
        """The safe default for the concentration question: an unowned account cannot dilute anyone's cap,
        and we do not pretend to know whose it is."""
        cap = self.EX._read_correlated_cap()
        for i in range(cap + 1):
            self.EX.report(f"x-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        self.EX.report("x-new", {}, equity=10000.0)
        g = self.EX.quota("x-new", "BTCUSDT", "long", want_risk_usd=10.0)
        self.assertEqual(g["owner"], "x-new")
        self.assertEqual(g["correlated_holders"], 0)

    def test_the_other_side_of_the_same_symbol_is_not_the_same_crowd(self):
        cap = self.EX._read_correlated_cap()
        for i in range(cap):
            self.EX.report(f"acc-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0,
                           owner="cust-1")
        self.EX.report("acc-next", {}, equity=10000.0, owner="cust-1")
        g = self.EX.quota("acc-next", "BTCUSDT", "short", want_risk_usd=100.0)
        self.assertEqual(g["correlated_holders"], 0)

    def test_a_different_symbol_is_not_the_same_crowd(self):
        cap = self.EX._read_correlated_cap()
        for i in range(cap):
            self.EX.report(f"acc-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0,
                           owner="cust-1")
        self.EX.report("acc-next", {}, equity=10000.0, owner="cust-1")
        self.EX.quota("acc-next", "ETHUSDT", "long", want_risk_usd=100.0)

    def test_an_account_already_in_the_crowd_is_not_counted_against_itself(self):
        """Re-checking quota for a symbol this account already holds (a size increase, a re-entry after a
        partial) must not be refused by its own presence in the crowd."""
        cap = self.EX._read_correlated_cap()
        for i in range(cap):
            self.EX.report(f"acc-{i:03d}", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0,
                           owner="cust-1")
        g = self.EX.quota("acc-000", "BTCUSDT", "long", want_risk_usd=10.0)
        self.assertEqual(g["correlated_holders"], cap - 1)

    def test_the_side_is_inferred_from_the_stop_when_not_declared(self):
        self.EX.report("a", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)    # stop below = long
        self.EX.report("b", {"BTCUSDT": pos(1.0, 10000.0, 10100.0)}, equity=10000.0)    # stop above = short
        crowd = self.EX.totals()["crowd"]
        self.assertEqual(crowd.get("BTCUSDT|long"), ["a"])
        self.assertEqual(crowd.get("BTCUSDT|short"), ["b"])

    # ---------------------------------------------------------------- concentration, the secondary gate

    def test_concentration_still_binds_when_one_account_dwarfs_the_others(self):
        """What max_portfolio_risk_pct IS for: a lopsided estate, where the fraction does move."""
        self.EX.report("small", {}, equity=1000.0)
        big = {"ETHUSDT": pos(10.0, 2000.0, 1990.0)}     # 10 * 10 = $100 risk on $1,000 equity
        self.EX.report("big", big, equity=1000.0)
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("small", "SOLUSDT", "long", want_risk_usd=100.0)
        self.assertIn("ceiling", str(cm.exception))

    def test_headroom_is_granted_while_it_exists(self):
        self.EX.report("acc-000", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        g = self.EX.quota("acc-000", "ETHUSDT", "long", want_risk_usd=100.0)
        self.assertAlmostEqual(g["portfolio_risk_usd_after"], 200.0)
        self.assertAlmostEqual(g["fraction_after"], 0.02)
        self.assertGreater(g["headroom_usd"], 0)

    # ---------------------------------------------------------------- fail closed, every time

    def test_a_crashed_runners_positions_keep_counting(self):
        """A dead process's position is still on the exchange. The slice expires to STALE, never to zero."""
        self.EX.report("dead", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        later = time.time() + self.EX.STALE_AFTER_S + 1
        t = self.EX.totals(now_epoch=later)
        self.assertAlmostEqual(t["risk_usd"], 100.0, msg="a stale slice was treated as flat")
        self.assertEqual(t["stale"], ["dead"])

    def test_a_stale_sibling_blocks_everyone(self):
        """A healthy runner must not keep trading while a sibling's book is unaccounted for: that sibling's
        positions still count toward the estate and may have changed unseen."""
        self.EX.report("dead", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        # Age ONLY the dead slice, so the caller's own slice is fresh and the refusal must name the sibling.
        d = json.load(open(self.EX.PATH, encoding="utf-8"))
        d["accounts"]["dead"]["updated_epoch"] -= self.EX.STALE_AFTER_S + 1
        json.dump(d, open(self.EX.PATH, "w"))
        self.EX.report("live", {}, equity=10000.0)
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("live", "ETHUSDT", "long", want_risk_usd=10.0)
        msg = str(cm.exception)
        self.assertIn("dead", msg)
        self.assertIn("live", msg)

    def test_an_unmeasurable_position_blocks_rather_than_counting_as_zero(self):
        self.EX.report("acc-000", {"BTCUSDT": {"qty": 1.0, "entry": 10100.0}}, equity=10000.0)
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("acc-000", "BTCUSDT", "long", want_risk_usd=10.0)
        self.assertIn("could not be computed", str(cm.exception))

    def test_an_unreadable_ledger_refuses_rather_than_assuming_an_empty_book(self):
        open(self.EX.PATH, "w").write("{ not json")
        with self.assertRaises(self.EX.ExposureRefused):
            self.EX.totals()

    def test_no_equity_reported_means_no_denominator_and_no_quota(self):
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("acc-000", "BTCUSDT", "long", want_risk_usd=10.0)
        self.assertIn("denominator", str(cm.exception))

    # ---------------------------------------------------------------- mechanics

    def test_release_is_the_only_way_a_slice_disappears(self):
        self.EX.report("acc-000", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        self.assertEqual(self.EX.totals()["accounts"], 1)
        self.EX.release("acc-000")
        self.assertEqual(self.EX.totals()["accounts"], 0)

    def test_reporting_a_flat_book_zeroes_that_account_without_removing_it(self):
        self.EX.report("acc-000", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        self.EX.report("acc-000", {}, equity=10000.0)
        t = self.EX.totals()
        self.assertEqual(t["accounts"], 1)
        self.assertAlmostEqual(t["risk_usd"], 0.0)

    def test_the_ledger_is_written_atomically(self):
        """A concurrent reader must see one whole version or another, never a truncated file."""
        src = open(os.path.join(ROOT, "scripts", "exposure.py"), encoding="utf-8").read()
        self.assertIn("os.replace(tmp, PATH)", src)

    def test_a_negative_request_is_refused(self):
        self.EX.report("acc-000", {}, equity=10000.0)
        with self.assertRaises(self.EX.ExposureRefused):
            self.EX.quota("acc-000", "BTCUSDT", "long", want_risk_usd=-1.0)

    def test_a_stale_lock_is_broken_rather_than_wedging_every_account(self):
        open(self.EX.LOCK, "w").write("999999 0\n")
        os.utime(self.EX.LOCK, (0, 0))
        self.EX.report("acc-000", {}, equity=10000.0)      # must not raise
        self.assertEqual(self.EX.totals()["accounts"], 1)


if __name__ == "__main__":
    unittest.main()


class Capacity(unittest.TestCase):
    """The instrument's own limit, and the honest handling of not knowing it.

    docs/plans/2026-09-19-multi-account.md §0.3 item 4. N accounts sending the same order into one book move
    the price against themselves. Nothing here reads order-book depth, so the capacity cannot be measured --
    and CLAUDE.md §20 says an UNKNOWN must never silently become a benign value.
    """

    def setUp(self):
        self.EX = _mod()
        self.dir = tempfile.mkdtemp()
        self.EX.PATH = os.path.join(self.dir, "exposure.json")
        self.EX.LOCK = self.EX.PATH + ".lock"

    def test_the_shipped_registry_declares_no_capacity_and_that_is_the_honest_state(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import instruments as I
        self.assertIsInstance(I.CAPACITY, dict)
        blk = json.load(open(os.path.join(ROOT, "docs", "architecture", "instruments.json"),
                             encoding="utf-8"))["estate_capacity"]
        self.assertIn("_why_empty", blk, "an empty capacity table must say why it is empty")

    def test_notional_is_summed_per_symbol_across_accounts(self):
        self.EX.report("a", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        self.EX.report("b", {"BTCUSDT": pos(2.0, 10100.0, 10000.0)}, equity=10000.0)
        self.assertAlmostEqual(self.EX.totals()["notional"]["BTCUSDT"], 3 * 10100.0)

    def test_a_grant_always_reports_the_capacity_state(self):
        self.EX.report("a", {}, equity=10000.0)
        g = self.EX.quota("a", "BTCUSDT", "long", want_risk_usd=10.0, want_notional_usd=5000.0)
        self.assertEqual(g["capacity"], "UNDECLARED")
        self.assertAlmostEqual(g["symbol_notional_after"], 5000.0)

    def test_a_declared_capacity_is_a_hard_ceiling(self):
        self.EX._declared_capacity = lambda sym: 20000.0
        self.EX.report("a", {"BTCUSDT": pos(1.0, 10100.0, 10000.0)}, equity=10000.0)
        self.EX.report("b", {}, equity=10000.0)
        self.EX.quota("b", "BTCUSDT", "long", want_risk_usd=10.0, want_notional_usd=5000.0)   # 15.1k < 20k
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("b", "BTCUSDT", "long", want_risk_usd=10.0, want_notional_usd=50000.0)
        self.assertIn("trading against itself", str(cm.exception))

    def test_an_undeclared_capacity_refuses_once_the_estate_outgrows_the_threshold(self):
        """Below the threshold the estate is too small for capacity to bind; above it, trading on an
        unmeasured assumption is the silent unknown §20 forbids."""
        n = self.EX._read_capacity_threshold()
        for i in range(n):
            self.EX.report(f"a-{i:03d}", {"ETHUSDT": pos(1.0, 2000.0, 1990.0)}, equity=10000.0,
                           owner=f"cust-{i}")
        self.EX.report("late", {}, equity=10000.0, owner="cust-late")
        with self.assertRaises(self.EX.ExposureRefused) as cm:
            self.EX.quota("late", "ETHUSDT", "long", want_risk_usd=10.0, want_notional_usd=2000.0)
        msg = str(cm.exception)
        self.assertIn("declares no", msg)
        self.assertIn("nothing here measures depth", msg)

    def test_below_the_threshold_an_undeclared_capacity_only_reports(self):
        n = self.EX._read_capacity_threshold()
        for i in range(n - 1):
            self.EX.report(f"a-{i:03d}", {"ETHUSDT": pos(1.0, 2000.0, 1990.0)}, equity=10000.0,
                           owner=f"cust-{i}")
        self.EX.report("late", {}, equity=10000.0, owner="cust-late")
        g = self.EX.quota("late", "ETHUSDT", "long", want_risk_usd=10.0, want_notional_usd=2000.0)
        self.assertEqual(g["capacity"], "UNDECLARED")
        self.assertEqual(g["symbol_accounts"], n - 1)

    def test_a_capacity_of_zero_is_refused_rather_than_read_as_no_trading(self):
        """Zero would otherwise read as "this instrument may not be traded", which is a different statement
        from "we have not measured it" -- and the registry has a way to say the second: leave the key out."""
        I = self.EX._instruments()
        saved = dict(I.CAPACITY)
        try:
            I.CAPACITY.clear(); I.CAPACITY["BTCUSDT"] = 0
            with self.assertRaises(self.EX.ExposureRefused) as cm:
                self.EX._declared_capacity("BTCUSDT")
            self.assertIn("remove the key", str(cm.exception))
        finally:
            I.CAPACITY.clear(); I.CAPACITY.update(saved)

    def test_the_registry_is_imported_once_not_on_every_order(self):
        self.assertIs(self.EX._instruments(), self.EX._instruments())

    def test_the_threshold_has_one_authored_source(self):
        v = json.load(open(os.path.join(ROOT, "docs", "architecture", "risk-config.json"),
                           encoding="utf-8"))["capacity_required_above_accounts"]
        self.assertIsInstance(v, int)
        self.assertGreaterEqual(v, 1)
