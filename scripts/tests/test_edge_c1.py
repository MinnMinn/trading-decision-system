"""scripts/research/edge_c1.py (pre-registration docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md) on HAND-BUILT
series only: no real history, no outcome. Covers the Donchian state machine and its ratchet, the volatility weight, the 20 %
threshold, fill and funding timing (exact 00:05 fills, funding marks never from a later price), costs, the monthly re-split of
sleeve and benchmark, the stdlib OLS / Newey-West, the placebo mechanics (per-coin offsets of a joining coin), N2 caps, the labels,
point-in-time truncation (a truncated future never changes a past decision: Donchian, MA arms, held weights, the whole read JSON)
and the read protocol end to end on synthetic files (refusals: END mark, last settlement, holes, funding gaps, eligibility dates,
the registration guard).

Run from scripts/tests, ONE module per invocation:  PYTHONPATH=.. python3 -W ignore -m unittest test_edge_c1
"""
import array
import ast
import collections
import contextlib
import datetime
import gzip
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I  # noqa: E402

PATH = os.path.join(ROOT, "scripts", "research", "edge_c1.py")
spec = importlib.util.spec_from_file_location("edge_c1", PATH)
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
EC = F.EC
D = datetime.date
DAY = datetime.timedelta(days=1)


def days_from(start, n):
    return [start + k * DAY for k in range(n)]


def walk(seed=11, n=900, p=100.0):
    """A seeded random walk with alternating trend regimes, so every sub-model enters and exits.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    rng = random.Random(seed)
    out = []
    for k in range(n):
        drift = 0.004 if (k // 120) % 2 == 0 else -0.003
        p *= math.exp(drift + rng.gauss(0, 0.03))
        out.append(p)
    return out


def coin(sym, bars, settlements=(), dates=(), closes=()):
    """An in-memory Coin from {epoch: open} (close = open) and [(epoch, rate, source)].
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    T, O, C = array.array("q"), array.array("d"), array.array("d")
    for t in sorted(bars):
        T.append(t)
        O.append(bars[t])
        C.append(bars[t])
    return F.Coin(sym, list(dates), list(closes), T, O, C, list(settlements))


def signal_coin(sym, dates, closes):
    """A Coin with spot closes and one flat 00:05 bar per day (decisions never read 5m prices; the simulator needs them).
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    bars = {F.t_fill(d): 100.0 for d in [dates[0] + k * DAY for k in range((dates[-1] - dates[0]).days + 3)]}
    return coin(sym, bars, dates=dates, closes=closes)


def inputs(n, elig=True, target=0.0, changed=False, held0=0.0, P0=100.0, P1=None, Fd=0.0, risk=0.0):
    """Simulator inputs for one coin over n days from scalars or lists.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    as_list = lambda v: list(v) if isinstance(v, (list, tuple)) else [v] * n   # noqa: E731
    p0 = as_list(P0)
    return {"elig": as_list(elig), "target": as_list(target), "changed": as_list(changed), "held0": held0, "P0": p0,
            "P1": as_list(P1) if P1 is not None else p0[1:] + p0[-1:], "F": as_list(Fd), "risk": as_list(risk),
            "mask": [0] * n, "lev": [1.0] * n, "carried": False}


# ------------------------------------------------------------------------------------------------ signals
class Donchian(unittest.TestCase):
    """§3: entry on C_t == Up (today included), stop Mid for the next day, exit on C_t < the stop in force, ratchet.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""

    closes = [10, 11, 12, 15, 14, 13.6, 14.5, 14.2]

    def setUp(self):
        self.dates = days_from(D(2021, 1, 1), len(self.closes))
        self.sg = F.coin_signals(self.dates, self.closes, ns=(3,))

    def at(self, k):
        """The state decided from close k (fill day = dates[k] + 1).
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        return self.sg["days"].index(self.dates[k] + DAY)

    def test_fill_days_follow_the_close(self):
        self.assertEqual(self.sg["days"][0], self.dates[0] + DAY)
        self.assertEqual(self.sg["days"][-1], self.dates[-1] + DAY)

    def test_no_signal_while_the_window_is_incomplete(self):
        for k in (0, 1):                                       # C == max of what exists, but n = 3 closes do not exist yet
            self.assertEqual(self.sg["mask"][self.at(k)], 0)

    def test_entry_on_the_close_that_equals_up_with_the_mid_as_next_stop(self):
        j = self.at(2)
        self.assertEqual((self.sg["mask"][j], self.sg["ts"][j], self.sg["entered"][j]), (1, (11.0,), 1))

    def test_stop_ratchets_and_is_never_lowered(self):
        self.assertEqual([self.sg["ts"][self.at(k)][0] for k in (3, 4, 5, 6)], [13.0, 13.5, 14.3, 14.3])
        # k = 6: Mid = (14.5 + 13.6) / 2 = 14.05 < 14.3 -> the stop stays at 14.3

    def test_exit_uses_the_stop_in_force_not_todays_mid(self):
        j = self.at(7)                                          # C = 14.2 < 14.3 (in force); today's Mid is 14.05
        self.assertEqual((self.sg["mask"][j], self.sg["ts"][j], self.sg["exited"][j]), (0, (None,), 1))

    def test_a_missing_close_is_no_state_update(self):
        dates = self.dates[:4] + self.dates[5:]                 # day 4 missing
        closes = self.closes[:4] + self.closes[5:]
        sg = F.coin_signals(dates, closes, ns=(3,))
        j = sg["days"].index(self.dates[4] + DAY)               # decided at 00:00 after the missing day
        self.assertTrue(sg["stale"][j])
        self.assertEqual(sg["ts"][j], sg["ts"][j - 1])
        self.assertEqual(sg["mask"][j], sg["mask"][j - 1])


class Weights(unittest.TestCase):
    def test_sigma_is_the_sample_sd_of_the_last_90_log_returns_annualised(self):
        a = 0.01
        closes = [100.0]
        for k in range(200):
            closes.append(closes[-1] * math.exp(a if k % 2 == 0 else -a))
        sg = F.coin_signals(days_from(D(2020, 1, 1), len(closes)), closes, ns=(5,))
        want = a * math.sqrt(90 / 89) * math.sqrt(365)
        self.assertAlmostEqual(sg["sigma"][-1], want, places=12)
        self.assertIsNone(sg["sigma"][88])                      # 89 returns: no sigma yet

    def test_vol_target_and_cap(self):
        self.assertAlmostEqual(F.lev(0.5), 0.5)
        self.assertEqual(F.lev(0.10), 2.0)                       # 0.25 / 0.10 = 2.5 -> capped
        self.assertEqual(F.lev(0.0), 2.0)
        self.assertIsNone(F.lev(None))

    def test_eligibility_needs_360_prior_closes(self):
        closes = walk(n=400)
        dates = days_from(D(2017, 8, 17), len(closes))
        sg = F.coin_signals(dates, closes)
        first = next(d for d, e in zip(sg["days"], sg["eligible"]) if e)
        self.assertEqual(first, D(2018, 8, 12))                  # the pre-registration's BTC/ETH date
        self.assertEqual(F.eligible_from(dates), D(2018, 8, 12))
        sol = days_from(D(2020, 8, 11), 400)
        self.assertEqual(F.eligible_from(sol), D(2021, 8, 6))    # the pre-registration's SOL date

    def test_coin_target_is_the_mean_of_nine_weights(self):
        closes = walk(n=700)
        coins = {"XUSDT": signal_coin("XUSDT", days_from(D(2020, 1, 1), 700), closes)}
        _grid, arrs = F.build(coins, D(2021, 11, 30))
        A = arrs["XUSDT"]
        for j in range(len(A["elig"])):
            if A["lev"][j] is not None:
                self.assertAlmostEqual(A["target"][j], A["lev"][j] * bin(A["mask"][j]).count("1") / 9.0)


class Threshold(unittest.TestCase):
    def test_a_submodel_change_always_trades_to_target(self):
        self.assertEqual(F.decide(0.5, True, 0.49), (0.5, True))

    def test_volatility_only_drift_is_relative_to_the_target(self):
        self.assertEqual(F.decide(0.5, False, 0.5625), (0.5625, False))     # |0.0625| <= 0.1
        self.assertEqual(F.decide(0.5, False, 0.375), (0.5, True))           # |0.125| > 0.1
        self.assertEqual(F.decide(2.5, False, 2.0), (2.0, False))            # exactly 0.20 x target: no trade
        self.assertEqual(F.decide(0.0, False, 0.0), (0.0, False))


# ------------------------------------------------------------------------------------------------ fills, funding, costs
def t(d, h, m=0):
    return F.t_at(d, h, m)


class FillsAndFunding(unittest.TestCase):
    d0 = D(2019, 12, 1)

    def bars(self, days=4, drop=()):
        out = {}
        for k in range(days + 1):
            d = self.d0 + k * DAY
            for (h, m), px in (((0, 0), 100.0), ((0, 5), 101.0), ((8, 0), 102.0), ((16, 0), 103.0)):
                if (k, h, m) not in drop:
                    out[t(d, h, m)] = px
        return out

    def test_fill_is_the_0005_open_never_the_0000_bar(self):
        c = coin("X", self.bars())
        self.assertEqual(F.price_at(c, F.t_fill(self.d0)), (101.0, "exact"))

    def test_a_missing_0005_bar_is_never_filled_at_a_later_bar(self):
        b = self.bars(drop={(1, 0, 5)})
        b[t(self.d0 + DAY, 0, 10)] = 101.5
        with self.assertRaises(ValueError):
            F.price_at(coin("X", b), F.t_fill(self.d0 + DAY))
        with self.assertRaises(ValueError):                        # and never at a 00:00 bar days later
            F.day_prices(coin("X", self.bars(drop={(1, 0, 5)})), [self.d0 + DAY])

    def test_a_funding_mark_never_uses_a_later_price(self):
        d1 = self.d0 + DAY
        c = coin("X", self.bars(drop={(1, 8, 0)}))
        self.assertEqual(F.funding_mark(c, t(d1, 16)), (103.0, "exact"))
        self.assertEqual(F.funding_mark(c, t(d1, 8)), (101.0, "prior_close"))   # the 00:05 bar's close, not 16:00's open
        self.assertEqual(F.funding_mark(c, t(self.d0, 0) - 300), (None, "none"))
        px = F.day_prices(coin("X", self.bars(drop={(1, 8, 0)}), [(t(d1, 8), 0.001, "archive")]), [d1])
        self.assertAlmostEqual(px[d1][2], 0.001 * 101.0)
        self.assertEqual(dict(px[d1][6]), {"prior_close": 1})

    def test_settlements_belong_to_the_interval_and_the_proxy_stops_at_listing(self):
        d1, d2 = self.d0 + DAY, self.d0 + 2 * DAY
        sett = [(t(d1, 0), 0.001, "rest"), (t(d1, 8), 0.002, "rest"), (t(d2, 0), 0.003, "archive")]
        c = coin("X", self.bars(), sett)
        px = F.day_prices(c, [self.d0, d1])
        # day d0 = [00:05 d0, 00:05 d1): proxy 08:00 and 16:00 (before the first realized stamp), realized 00:00 d1
        self.assertAlmostEqual(px[self.d0][2], 0.0001 * 102 + 0.0001 * 103 + 0.001 * 100)
        self.assertEqual(dict(px[self.d0][5]), {"proxy": 2, "rest": 1})
        self.assertAlmostEqual(px[d1][2], 0.002 * 102 + 0.003 * 100)
        self.assertEqual((px[self.d0][0], px[self.d0][1]), (101.0, 101.0))

    def test_proxy_is_at_00_08_16_utc(self):
        c = coin("X", self.bars())                                  # no realized funding at all
        s = F.settlements_in(c, F.t_fill(self.d0), F.t_fill(self.d0 + DAY))
        self.assertEqual([(F._iso(x[0])[11:16], x[1], x[2]) for x in s],
                         [("08:00", 0.0001, "proxy"), ("16:00", 0.0001, "proxy"), ("00:00", 0.0001, "proxy")])

    def test_actual_settlement_times_are_used(self):
        d1 = self.d0 + DAY
        sett = [(t(self.d0, h), 0.0001, "archive") for h in (0, 4, 8, 12, 16, 20)] + [(t(d1, 0), 0.0001, "archive")]
        c = coin("X", self.bars(), sett)
        s = F.settlements_in(c, F.t_fill(self.d0), F.t_fill(d1))
        self.assertEqual([F._iso(x[0])[11:16] for x in s], ["04:00", "08:00", "12:00", "16:00", "20:00", "00:00"])

    def test_the_0000_settlement_is_paid_by_the_position_held_before_the_0005_fill(self):
        d1, d2 = self.d0 + DAY, self.d0 + 2 * DAY
        sett = [(t(self.d0, 0), 0.0, "archive"), (t(d1, 0), 0.001, "archive"), (t(d1, 8), 0.002, "archive"),
                (t(d2, 0), 0.003, "archive")]
        c = coin("X", self.bars(), sett)
        days = [self.d0, d1]
        px = F.day_prices(c, days)
        base = dict(P0=[px[d][0] for d in days], P1=[px[d][1] for d in days], Fd=[px[d][2] for d in days])
        # flat on d0, long 1x from the d1 fill: the 00:00 d1 stamp is NOT paid; the 00:00 d2 stamp IS
        sim = F.simulate(days, {"X": inputs(2, target=[0.0, 1.0], changed=[False, True], **base)}, 0.0)
        self.assertEqual(sim["funding"][0], 0.0)
        q = 1.0 / 101.0
        self.assertAlmostEqual(sim["funding"][1], q * (0.002 * 102 + 0.003 * 100))
        # long on d0, flat from the d1 fill: d0 pays its 08:00, 16:00 and the 00:00 d1 stamp; d1 pays nothing
        sim = F.simulate(days, {"X": inputs(2, target=[1.0, 0.0], changed=[True, True], **base)}, 0.0)
        self.assertAlmostEqual(sim["funding"][0], q * 0.001 * 100)
        self.assertEqual(sim["funding"][1], 0.0)

    def test_costs_are_taker_plus_slippage_per_side_on_traded_notional(self):
        days = days_from(D(2021, 3, 2), 3)
        inp = {"X": inputs(3, target=[1.0, 1.0, 0.0], changed=[True, False, True])}
        sim = F.simulate(days, inp, F.TAKER + F.SLIPPAGE)
        self.assertAlmostEqual(sim["r"][0], -0.0006)                  # buy 1x at 6 bp
        self.assertAlmostEqual(sim["r"][1], 0.0)
        self.assertAlmostEqual(sim["r"][2], -0.0006 / (1 - 0.0006))   # sell the 1.0 notional at 6 bp on equity 0.9994
        sim2 = F.simulate(days, inp, F.TAKER + 2 * F.SLIPPAGE)
        self.assertAlmostEqual(sim2["r"][0], -0.0007)

    def test_monthly_resplit_is_equal_capital_and_charged(self):
        days = [D(2021, 1, 30), D(2021, 1, 31), D(2021, 2, 1)]
        a = inputs(3, target=1.0, held0=1.0, P0=[100.0, 200.0, 200.0])
        b = inputs(3, target=1.0, held0=1.0, P0=100.0)
        sim = F.simulate(days, {"A": a, "B": b}, 0.0006)
        self.assertAlmostEqual(sim["r"][0], 0.5)                      # A doubled on half the capital, no fee (carried)
        self.assertAlmostEqual(sim["fees"][1], 0.0)                   # no re-split on the 31st
        # Feb 1: equity 1.5 re-split 0.75 / 0.75: A sells 0.25 of notional, B buys 0.25 -> fee 0.0006 x 0.5 on 1.5
        self.assertAlmostEqual(sim["fees"][2], 0.0006 * 0.5 / 1.5)

    def test_a_coin_joining_resplits_and_pays_its_entry(self):
        days = days_from(D(2021, 5, 26), 2)
        a = inputs(2, target=1.0, held0=1.0)
        c = inputs(2, elig=[False, True], target=1.0)
        sim = F.simulate(days, {"A": a, "C": c}, 0.0006)
        self.assertAlmostEqual(sim["fees"][0], 0.0)
        self.assertAlmostEqual(sim["fees"][1], 0.0006 * 1.0)          # A sells 0.5, C buys 0.5 of equity 1.0
        self.assertEqual(sim["coin"]["C"]["date"], [days[1]])

    def test_daily_return_and_benchmark_share_the_interval(self):
        days = days_from(D(2021, 3, 2), 2)
        a = inputs(2, target=[1.0, 1.0], changed=[True, False], P0=[100.0, 110.0], P1=[110.0, 99.0])
        b = inputs(2, target=[0.0, 0.0], P0=[50.0, 50.0], P1=[50.0, 60.0])
        sim = F.simulate(days, {"A": a, "B": b}, 0.0)
        self.assertAlmostEqual(sim["bench"][0], (0.10 + 0.0) / 2)
        # equal-capital sub-accounts drift like the sleeve's capital: A 0.55, B 0.50 entering day 2
        self.assertAlmostEqual(sim["bench"][1], (0.55 * -0.10 + 0.50 * 0.2) / 1.05)
        self.assertAlmostEqual(sim["r"][0], 0.5 * 0.10)              # A long on half, B flat
        self.assertAlmostEqual(sim["coin"]["A"]["r"][1], -0.10)

    def test_benchmark_resplits_on_the_sleeves_days(self):
        days = [D(2021, 1, 30), D(2021, 1, 31), D(2021, 2, 1)]
        a = inputs(3, P0=[100.0, 200.0, 200.0], P1=[200.0, 220.0, 220.0])
        b = inputs(3, P0=[100.0, 100.0, 100.0], P1=[100.0, 100.0, 130.0])
        sim = F.simulate(days, {"A": a, "B": b}, 0.0)
        self.assertAlmostEqual(sim["bench"][0], 0.5)
        self.assertAlmostEqual(sim["bench"][1], (1.0 * 0.1 + 0.5 * 0.0) / 1.5)      # drifted: A 1.0, B 0.5
        self.assertAlmostEqual(sim["bench"][2], (0.1 + 0.3) / 2)                    # Feb 1: re-split 0.8 / 0.8
        self.assertAlmostEqual(sim["bench_funded"][2], sim["bench"][2])              # no funding here


# ------------------------------------------------------------------------------------------------ statistics
def brute_hac(y, x, lags):
    """Independent (X'X)^-1 S (X'X)^-1 with explicit outer products, for the Newey-West check.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    n = len(y)
    X = [[1.0, v] for v in x]
    xtx = [[sum(X[t][i] * X[t][j] for t in range(n)) for j in range(2)] for i in range(2)]
    det = xtx[0][0] * xtx[1][1] - xtx[0][1] * xtx[1][0]
    inv = [[xtx[1][1] / det, -xtx[0][1] / det], [-xtx[1][0] / det, xtx[0][0] / det]]
    beta = [sum(inv[i][k] * sum(X[t][k] * y[t] for t in range(n)) for k in range(2)) for i in range(2)]
    u = [y[t] - beta[0] - beta[1] * x[t] for t in range(n)]
    S = [[0.0, 0.0], [0.0, 0.0]]
    for l in range(0, lags + 1):
        w = 1.0 if l == 0 else 1.0 - l / (lags + 1.0)
        for t in range(l, n):
            for i in range(2):
                for j in range(2):
                    v = u[t] * u[t - l] * X[t][i] * X[t - l][j]
                    S[i][j] += w * (v if l == 0 else v + u[t] * u[t - l] * X[t - l][i] * X[t][j])
    M = [[sum(inv[i][k] * S[k][m] for k in range(2)) for m in range(2)] for i in range(2)]
    V = [[sum(M[i][k] * inv[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
    return beta, V[0][0]


class Statistics(unittest.TestCase):
    def setUp(self):
        rng = random.Random(3)
        self.x = [rng.gauss(0, 0.03) for _ in range(300)]
        e, self.y = 0.0, []
        for v in self.x:
            e = 0.5 * e + rng.gauss(0, 0.01)                         # serially dependent errors
            self.y.append(0.0005 + 0.6 * v + e)

    def test_ols_matches_the_normal_equations(self):
        a, b, _u = F.ols(self.y, self.x)
        beta, _v = brute_hac(self.y, self.x, 0)
        self.assertAlmostEqual(a, beta[0], places=12)
        self.assertAlmostEqual(b, beta[1], places=12)

    def test_newey_west_matches_a_brute_force_sandwich(self):
        _a, _b, u = F.ols(self.y, self.x)
        for lags in (0, 3, 10):
            self.assertAlmostEqual(F.hac_v00(self.x, u, lags) / brute_hac(self.y, self.x, lags)[1], 1.0, places=10)

    def test_regress_reports_nw10_one_sided_and_cr1(self):
        r = F.regress(self.y, self.x)
        n = len(self.y)
        _a, _b, u = F.ols(self.y, self.x)
        self.assertAlmostEqual(r["se_nw"], math.sqrt(F.hac_v00(self.x, u, 10)))
        self.assertAlmostEqual(r["p_one_sided"], EC.t_sf(r["alpha"] / r["se_nw"], n - 2))
        self.assertAlmostEqual(r["se_cr1"] ** 2, F.hac_v00(self.x, u, 0) * n / (n - 2))
        self.assertAlmostEqual(r["alpha_annual"], r["alpha"] * 365)

    def test_month_contributions_sum_to_alpha_and_flag_regimes(self):
        dates = days_from(D(2021, 1, 1), len(self.y))
        r = F.regress(self.y, self.x)
        mc = F.month_contrib(dates, self.y, self.x, r["beta"])
        self.assertAlmostEqual(sum(mc.values()), r["alpha"], places=12)
        y = [v + (0.05 if d.month == 3 else 0.0) for v, d in zip(self.y, dates)]   # one huge month
        rr = F.regress(y, self.x)
        g = F.regime(dates, y, self.x, rr)
        self.assertTrue(g["regime_driven"])
        self.assertEqual(g["best3_months"][0], "2021-03")

    def test_regime_flag_fires_when_the_third_best_month_is_negative(self):
        """Two positive months and a negative third: every later month is <= the third, so alpha <= the top-3 sum and the
        top-3 share is >= 1 -- the flag cannot be missed by summing exactly 3 months.
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        dates, y = [], []
        for month, v in ((1, 0.004), (2, 0.003), (3, -0.001), (4, -0.002)):
            dates += days_from(D(2021, month, 1), 10)
            y += [v] * 10
        x = [0.0] * len(y)
        reg = {"alpha": sum(y) / len(y), "beta": 0.0}
        g = F.regime(dates, y, x, reg)
        self.assertTrue(g["regime_driven"])
        self.assertGreaterEqual(g["best3_share"], 1.0)
        self.assertEqual(g["best3_months"], ["2021-01", "2021-02", "2021-03"])

    def test_bh_family_is_t1_to_t4(self):
        self.assertEqual(F.PREREG_FAMILY_M, 4)
        self.assertEqual(len(F.symbols()) + 1, F.PREREG_FAMILY_M)


class Placebo(unittest.TestCase):
    def test_circular_shift(self):
        self.assertEqual(F.shift([1, 2, 3, 4, 5], 2), [4, 5, 1, 2, 3])
        self.assertEqual(F.shift([1, 2, 3], 3), [1, 2, 3])

    def test_offsets_are_seeded_and_inside_60_to_L_minus_60(self):
        n = 200
        days = days_from(D(2021, 1, 1), n)
        inp = {"X": inputs(n, target=0.5, changed=False, held0=0.5)}
        a = F.placebo(days, inp, 0.0006, draws=30)
        b = F.placebo(days, inp, 0.0006, draws=30)
        self.assertEqual(a["k"], b["k"])
        rng = random.Random(20261003)
        self.assertEqual(a["k"][:3], [rng.randint(60, n - 60) for _ in range(3)])
        self.assertTrue(all(60 <= k <= n - 60 for k in a["k"]))
        self.assertIsNone(F.placebo(days[:119], {"X": inputs(119)}, 0.0, draws=3))

    def test_weights_use_the_destination_days_sigma(self):
        n = 6
        x = inputs(n)
        x["carried"] = True
        masks, levs = [1, 3, 0, 511, 7, 1], [1.0, 2.0, 0.5, 1.5, 0.25, 1.25]
        out = F.placebo_inputs({"X": (list(range(n)), masks, levs)}, {"X": x}, {"X": 2})["X"]
        sh = F.shift(masks, 2)
        for m in range(n):
            self.assertAlmostEqual(out["target"][m], levs[m] * bin(sh[m]).count("1") / 9)
            self.assertEqual(out["changed"][m], sh[m] != sh[m - 1])
        self.assertAlmostEqual(out["held0"], levs[0] * bin(sh[-1]).count("1") / 9)

    def test_p_placebo(self):
        self.assertAlmostEqual(F.p_placebo(0.2, [0.1, 0.2, 0.3]), 3 / 4)
        self.assertAlmostEqual(F.p_placebo(1.0, [0.1] * 1000), 1 / 1001)
        self.assertAlmostEqual(F.p_placebo(0.2, [None, 0.1]), 2 / 3)            # an undefined draw counts against
        self.assertIsNone(F.p_placebo(0.2, None))

    def test_coin_shift_maps_a_joining_coin_into_its_own_range(self):
        L = 400
        for k in range(60, L - 60 + 1):
            self.assertEqual(F.coin_shift(k, L, L), k)
            kc = F.coin_shift(k, L, 200)
            self.assertTrue(60 <= kc <= 140, (k, kc))
            self.assertIsNone(F.coin_shift(k, L, 119))
        self.assertEqual(F.coin_shift(340, L, 200), 60 + 280 % 81)

    def test_a_joining_coin_never_gets_a_shift_below_60_or_its_observed_path(self):
        """A coin eligible on the last 200 of 400 window days: every draw shifts it by 60 <= k_c <= 140 (k mod 200 would put
        ~30 % of draws within 60 days and some on 0, the observed path).
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        n = 400
        rng = random.Random(4)
        days = days_from(D(2021, 1, 1), n)
        a = inputs(n, target=0.5, changed=False, held0=0.5)
        j = inputs(n, elig=[False] * 200 + [True] * 200, target=0.5)
        j["mask"] = [rng.randrange(512) for _ in range(n)]
        observed = [j["mask"][m] for m in range(200, n)]
        pl = F.placebo(days, {"A": a, "J": j}, 0.0006, draws=40)
        self.assertEqual(pl["k_coin"]["A"], pl["k"])
        for kc in pl["k_coin"]["J"]:
            self.assertTrue(60 <= kc <= 140, kc)
            self.assertNotEqual(F.shift(observed, kc), observed)
        short = inputs(n, elig=[False] * 300 + [True] * 100, target=0.5)
        pl = F.placebo(days, {"A": a, "S": short}, 0.0006, draws=5)
        self.assertIsNone(pl["coins"]["S"])                                      # L_c < 120: unshifted, no p_P
        self.assertEqual(pl["k_coin"]["S"], [None] * 5)


class OwnerSizing(unittest.TestCase):
    """§7 N2: 1 % open risk per coin at the stop, 3 % in total, on the target AND on the held weight.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""

    def test_a_coin_at_2pct_open_risk_is_halved(self):
        self.assertEqual(F._n2_scales(["X"], {"X": 0.02}, {"X": 1.0}), {"X": 0.5})
        self.assertEqual(F._n2_scales(["X"], {"X": 0.005}, {"X": 1.0}), {"X": 1.0})
        self.assertEqual(F._n2_scales(["X"], {"X": 0.0}, {"X": 1.0}), {"X": 1.0})

    def test_the_total_is_capped_at_3pct(self):
        sc = F._n2_scales(list("ABC"), dict.fromkeys("ABC", 0.015), dict.fromkeys("ABC", 1.0))
        for s in "ABC":
            self.assertAlmostEqual(sc[s], 2 / 3)                    # per coin 1 %, total exactly 3 %: no further scale
        sc = F._n2_scales(list("ABCD"), dict.fromkeys("ABCD", 0.01), dict.fromkeys("ABCD", 1.0))
        for s in "ABCD":
            self.assertAlmostEqual(sc[s], 0.75)                     # 4 x 1 % -> 3 %
        sc = F._n2_scales(["A", "B"], {"A": 0.02, "B": 0.02}, {"A": 0.5, "B": 0.5})   # risk x capital share
        self.assertEqual(sc, {"A": 1.0, "B": 1.0})

    def test_the_cap_forces_a_trade_inside_the_20pct_band(self):
        self.assertEqual(F.decide_all(["X"], {"X": 0.5}, {"X": False}, {"X": 0.55}),
                         {"X": (0.55, False)})                                 # the band alone keeps 0.55 vs target 0.5
        args = (["X"], {"X": 1.0}, {"X": False}, {"X": 0.55})
        self.assertEqual(F.decide(0.5, False, 0.55), (0.55, False))           # N2 scales 1.0 to 0.5: the band would keep it
        w, trade = F.decide_all(*args, {"X": 0.02}, {"X": 1.0})["X"]           # ... but 0.55 = 1.1 % open risk
        self.assertAlmostEqual(w, 0.5)
        self.assertTrue(trade)
        w, trade = F.decide_all(["X"], {"X": 1.0}, {"X": False}, {"X": 1.15}, {"X": 0.009}, {"X": 1.0})["X"]
        self.assertAlmostEqual(w, 1.15 * 0.01 / (0.009 * 1.15))               # scale 1, but held 1.15 = 1.035 % risk
        self.assertTrue(trade)
        w, trade = F.decide_all(["X"], {"X": 1.0}, {"X": False}, {"X": 0.45}, {"X": 0.02}, {"X": 1.0})["X"]
        self.assertEqual((w, trade), (0.45, False))                            # below the cap: the band holds

    def test_the_n2_simulation_trades_down_to_the_cap(self):
        days = days_from(D(2021, 3, 2), 2)
        inp = {"X": inputs(2, target=1.0, held0=0.55, risk=0.02)}
        sim = F.simulate(days, inp, 0.0006, n2=True)
        self.assertAlmostEqual(sim["coin"]["X"]["w"][0], 0.5)
        self.assertAlmostEqual(sim["fees"][0], 0.0006 * 0.05)              # carried 0.55 placed free, 0.05 sold
        self.assertAlmostEqual(sim["coin"]["X"]["w"][1], 0.5)              # inside the band of 0.5: held

    def test_exit_loss_over_planned_by_hand(self):
        none9 = (None,) * 9
        arrs = {"X": {"exited": [0, 0b11], "elig": [True, True], "P0": [100.0, 85.0],
                      "ts": [(90.0, 80.0) + (None,) * 7, none9]}}
        self.assertEqual(F.exit_ratios(arrs, ["X"], 0, 1), [(100 - 85) / (100 - 90), (100 - 85) / (100 - 80)])
        arrs["X"]["elig"][0] = False                                        # no planned distance without a prior fill
        self.assertEqual(F.exit_ratios(arrs, ["X"], 0, 1), [])


class Labels(unittest.TestCase):
    def h(self, p, alpha=0.001, pv=0.01, net=0.001):
        return {"pass": p, "alpha": alpha, "p_one_sided": pv, "net": net}

    def test_labels(self):
        L = F.label
        self.assertEqual(L({"discovery": self.h(True), "confirmation": self.h(True), "exposed": self.h(True)}), "VALIDATED")
        self.assertTrue(L({"discovery": self.h(True), "confirmation": self.h(True),
                           "exposed": self.h(False, pv=0.2)}).startswith("PROMISING"))
        self.assertEqual(L({"discovery": self.h(False, alpha=-0.001)}), "DEAD")
        self.assertEqual(L({"discovery": self.h(True), "confirmation": self.h(False, alpha=0.0)}), "DEAD")
        self.assertTrue(L({"discovery": self.h(True), "confirmation": self.h(True),
                           "exposed": self.h(False, pv=0.2, net=-0.001)}).startswith("INCONCLUSIVE"))
        self.assertIn("NOT validated", L({"discovery": self.h(True), "confirmation": self.h(True)}))

    def test_read_thresholds(self):
        reg = {"p_one_sided": 0.04}
        self.assertTrue(F.read_pass("discovery", reg, 0.001, None, 0.10, True))
        self.assertFalse(F.read_pass("discovery", reg, 0.001, None, 0.11, True))
        self.assertFalse(F.read_pass("discovery", reg, 0.001, None, 0.05, False))
        self.assertTrue(F.read_pass("confirmation", reg, 0.001, 0.0001, 0.05, False))
        self.assertFalse(F.read_pass("confirmation", reg, 0.001, -0.0001, 0.05, False))
        self.assertFalse(F.read_pass("confirmation", {"p_one_sided": 0.05}, 0.001, 0.001, 0.05, False))
        self.assertTrue(F.read_pass("exposed", {"p_one_sided": 0.09}, 0.001, None, None, False))
        self.assertFalse(F.read_pass("exposed", {"p_one_sided": 0.10}, 0.001, None, None, False))

    def test_server_day_mapping(self):
        self.assertEqual(F.server_day(D(2026, 10, 3)), D(2026, 10, 5))     # Saturday -> Monday
        self.assertEqual(F.server_day(D(2026, 10, 4)), D(2026, 10, 5))     # Sunday -> Monday
        self.assertEqual(F.server_day(D(2026, 10, 5)), D(2026, 10, 5))

    def test_read_windows_are_the_preregistered_ones(self):
        n = {r: (b - a).days + 1 for r, (a, b) in F.WINDOWS.items()}
        self.assertEqual(n, {"discovery": 1447, "confirmation": 965, "exposed": 560})
        self.assertEqual(F.WINDOWS["confirmation"][0] - F.WINDOWS["discovery"][1], DAY)
        self.assertEqual(F.WINDOWS["exposed"][0] - F.WINDOWS["confirmation"][1], DAY)

    def test_frozen_parameters(self):
        self.assertEqual(F.NS, (5, 10, 20, 30, 60, 90, 150, 250, 360))
        self.assertEqual((F.VOL_DAYS, F.VOL_TARGET, F.LEV_CAP, F.REBALANCE_REL), (90, 0.25, 2.0, 0.20))
        self.assertEqual((F.TAKER, F.SLIPPAGE, F.PROXY_RATE, F.NW_LAGS), (0.0005, 0.0001, 0.0001, 10))
        self.assertEqual((F.PLACEBO_DRAWS, F.PLACEBO_SEED, F.PLACEBO_MIN_SHIFT), (1000, 20261003, 60))


class Sources(unittest.TestCase):
    def test_symbols_come_from_instruments(self):
        self.assertEqual(F.symbols(), I.backtested("crypto"))

    def test_no_hardcoded_core_triple(self):
        src = open(PATH, encoding="utf-8").read()
        self.assertIsNone(re.search(r'BTCUSDT["\',\s]+ETHUSDT["\',\s]+SOLUSDT', src))

    def test_every_docstring_cites_the_preregistration(self):
        tree = ast.parse(open(PATH, encoding="utf-8").read())
        missing = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                   and ast.get_docstring(n) and F.PREREG not in ast.get_docstring(n)]
        self.assertEqual(missing, [])
        self.assertIn(F.PREREG, ast.get_docstring(tree))

    def test_n1_diagnostic_arms(self):
        closes = [1, 2, 3, 4, 5, 4, 3]
        ms = F.ma_signals(days_from(D(2021, 1, 1), len(closes)), closes, mas=(3,))
        # fill day k+1: C_k > mean(C_{k-2..k})
        self.assertEqual(ms[3], [0, 0, 1, 1, 1, 0, 0])


# ------------------------------------------------------------------------------------------------ point in time
class PointInTime(unittest.TestCase):
    """The generic leakage probe applied to C1 (pattern of test_detector_leakage_probe.py): truncating the future never changes
    a past decision -- the Donchian state, stops, sigma, eligibility, targets, change flags and the 20 % threshold path.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""

    def test_truncating_the_future_never_changes_a_past_decision(self):
        closes = walk(seed=5, n=900)
        dates = days_from(D(2019, 1, 1), len(closes))
        dates = dates[:400] + dates[401:]                      # one missing close, too
        closes = closes[:400] + closes[401:]
        full = F.coin_signals(dates, closes)
        keys = ("mask", "ts", "sigma", "eligible", "entered", "exited", "stale")
        for cut in (380, 520, 777, len(dates) - 1):
            part = F.coin_signals(dates[:cut], closes[:cut])
            m = len(part["days"])
            self.assertEqual(part["days"], full["days"][:m])
            for k in keys:
                self.assertEqual(part[k], full[k][:m], (cut, k))

    def test_truncating_the_future_never_changes_a_past_ma_arm(self):
        """N1 (ma_signals): S_L for fill days before the cut is identical with and without the later closes.
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        closes = walk(seed=7, n=600)
        dates = days_from(D(2019, 1, 1), len(closes))
        dates, closes = dates[:250] + dates[251:], closes[:250] + closes[251:]
        full = F.ma_signals(dates, closes)
        for cut in (40, 101, 333, len(dates) - 1):
            part = F.ma_signals(dates[:cut], closes[:cut])
            m = len(part["days"])
            self.assertEqual(part["days"], full["days"][:m])
            for L in F.N1_MAS:
                self.assertEqual(part[L], full[L][:m], (cut, L))

    def test_truncating_the_future_never_changes_the_held_weight_path(self):
        closes = walk(seed=9, n=900)
        dates = days_from(D(2019, 1, 1), len(closes))
        mk = lambda n: {"X": signal_coin("X", dates[:n], closes[:n])}   # noqa: E731
        g_full, a_full = F.build(mk(len(dates)), dates[-1] + DAY)
        for cut in (500, 640, 811):
            g, a = F.build(mk(cut), dates[cut - 1] + DAY)
            self.assertEqual(g, g_full[:len(g)])
            for key in ("elig", "target", "changed", "mask", "ts"):
                self.assertEqual(a["X"][key], a_full["X"][key][:len(g)], (cut, key))
            for j in range(1, len(g) + 1, 37):
                self.assertEqual(F.held_at(a, ["X"], j), F.held_at(a_full, ["X"], j))


# ------------------------------------------------------------------------------------------------ the read protocol, end to end
SYN = ("AAAUSDT", "BBBUSDT", "CCCUSDT")
SYN_WINDOWS = {"discovery": (D(2020, 12, 26), D(2021, 8, 31)), "confirmation": (D(2021, 9, 1), D(2022, 3, 31)),
               "exposed": (D(2022, 4, 1), D(2022, 12, 31))}
INTRADAY = ((0, 0), (0, 5), (4, 0), (8, 0), (12, 0), (16, 0), (20, 0))


def _write_split(root, sym, tf, candles):
    d = os.path.join(root, f"ohlcv.{sym}.{tf}")
    os.makedirs(d)
    by = collections.defaultdict(list)
    for c in candles:
        by[int(c["time"][:4])].append(c)
    with open(os.path.join(d, "index.json"), "w") as fh:
        json.dump({"symbol": sym, "timeframe": tf, "years": sorted(by)}, fh)
    for y, cs in by.items():
        with gzip.open(os.path.join(d, f"{y}.json.gz"), "wt") as fh:
            json.dump({"year": y, "candles": cs}, fh)


def _write_funding(root, name, rows):
    with gzip.open(os.path.join(root, name), "wt") as fh:
        json.dump({"rows": rows}, fh)


def _bar(tm, p):
    return {"time": F._iso(tm), "open": p, "high": p, "low": p, "close": p}


SYN_SPEC = {"AAAUSDT": (D(2020, 1, 1), 1, D(2021, 1, 1), True), "BBBUSDT": (D(2020, 1, 1), 2, D(2021, 1, 1), True),
            "CCCUSDT": (D(2020, 5, 1), 3, D(2020, 7, 1), False)}         # (first spot close, seed, first perp bar, spot 5m?)
SYN_ELIGIBLE = {"AAAUSDT": D(2020, 12, 26), "BBBUSDT": D(2020, 12, 26), "CCCUSDT": D(2021, 4, 26)}


def make_history(root, perturb_end=None, last=D(2023, 1, 1), drop_5m=(), drop_funding=(), drop_first_spot=None):
    """Synthetic spot 1d / spot 5m / perp 5m / funding files shaped like data/history/binance_* (hand-built, seeded), through
    `last` (one day past the exposed window, so its END mark and the 00:00 settlement after its last day exist).
    perturb_end = a read's END day: x1.7 on every 5m bar opening after its END mark (prices computed from the UNperturbed
    closes, so the END bar itself is unchanged), on every 1d close dated >= that day (the last day's close is never used by a
    window decision) and on every funding rate stamped at or after the END instant. drop_5m / drop_funding = {(sym, epoch)}
    removed; drop_first_spot = {sym: n} drops the first n spot closes.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    spot, um = os.path.join(root, "spot"), os.path.join(root, "um")
    os.makedirs(spot)
    os.makedirs(um)
    t_cut = F.t_fill(perturb_end + DAY) if perturb_end is not None else None
    for sym, (start, seed, perp0, has_spot5) in SYN_SPEC.items():
        dates = [start + k * DAY for k in range((last - start).days + 1)]
        closes = walk(seed=seed, n=len(dates), p=50.0 * seed)
        cl = dict(zip(dates, closes))
        shown = [(d, cl[d] * (1.7 if perturb_end is not None and d >= perturb_end else 1.0)) for d in dates]
        shown = shown[(drop_first_spot or {}).get(sym, 0):]
        _write_split(spot, sym, "1d", [_bar(F.t_at(d), c) for d, c in shown])

        def px(tm):
            d = datetime.datetime.fromtimestamp(tm, datetime.timezone.utc).date()
            a, b = cl.get(d - DAY, cl[dates[0]]), cl.get(d, cl[dates[-1]])
            v = a * (b / a) ** ((tm - F.t_at(d)) / 86400.0)
            return v * (1.7 if t_cut is not None and tm > t_cut else 1.0)
        bars5 = [F.t_at(d, h, m) for d in dates for h, m in INTRADAY if (sym, F.t_at(d, h, m)) not in drop_5m]
        if has_spot5:
            _write_split(spot, sym, "5m", [_bar(tm, px(tm)) for tm in bars5 if tm < F.t_at(perp0)])
        _write_split(um, sym, "5m", [_bar(tm, px(tm)) for tm in bars5 if tm >= F.t_at(perp0)])

        def rate(tm, r):
            return r * (1.7 if t_cut is not None and tm >= t_cut else 1.0)
        arch = []
        for d in dates:
            if d < perp0:
                continue
            hours = (0, 4, 8, 12, 16, 20) if (sym == "CCCUSDT" and d.year == 2022 and d.month == 1) else (0, 8, 16)
            for h in hours:
                tm = F.t_at(d, h)
                if (sym, tm) not in drop_funding:
                    arch.append({"time": F._iso(tm), "interval_hours": 24 // len(hours),
                                 "rate": rate(tm, 0.0001 if (d.toordinal() + h) % 3 else -0.00005)})
        _write_funding(um, f"funding.{sym}.json.gz", arch)
        rest = []
        if sym == "AAAUSDT":
            d = D(2020, 10, 1)
            while d < perp0:
                rest += [{"time": F._iso(F.t_at(d, h)), "rate": 0.0002} for h in (0, 8, 16)]
                d += DAY
        _write_funding(um, f"funding_rest.{sym}.json.gz", rest)
    return spot, um


def _json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class ReadProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="edge_c1_test_")
        cls.saved = {k: getattr(F, k) for k in ("SPOT_ROOT", "UM_ROOT", "symbols", "WINDOWS", "N1_SYMBOLS", "_book_daily",
                                                "ELIGIBLE_FROM", "_git", "_prereg_text", "PLACEBO_DRAWS")}
        cls.roots = make_history(os.path.join(cls.tmp, "a"))
        F.SPOT_ROOT, F.UM_ROOT = cls.roots
        F.symbols = lambda: list(SYN)
        F.WINDOWS = SYN_WINDOWS
        F.N1_SYMBOLS = ("AAAUSDT", "BBBUSDT")
        F.ELIGIBLE_FROM = dict(SYN_ELIGIBLE)
        F._book_daily = lambda: ({"2021-03-01": 0.5, "2021-03-02": -1.0}, pearson)
        cls.out = {r: os.path.join(cls.tmp, f"{r}.json") for r in F.READS}
        with contextlib.redirect_stdout(io.StringIO()):
            cls.res = {"discovery": F.run("discovery", cls.out["discovery"], draws=25, require_clean=False)}
            cls.res["confirmation"] = F.run("confirmation", cls.out["confirmation"], cls.out["discovery"], draws=25,
                                            require_clean=False)
            cls.res["exposed"] = F.run("exposed", cls.out["exposed"], cls.out["confirmation"], draws=25,
                                       require_clean=False)

    def setUp(self):
        self._quiet = contextlib.redirect_stdout(io.StringIO())
        self._quiet.__enter__()

    def tearDown(self):
        self._quiet.__exit__(None, None, None)
        for k in ("SPOT_ROOT", "UM_ROOT"):
            setattr(F, k, self.roots[0] if k == "SPOT_ROOT" else self.roots[1])
        for k in ("WINDOWS", "ELIGIBLE_FROM", "_git", "_prereg_text", "PLACEBO_DRAWS"):
            setattr(F, k, {"WINDOWS": SYN_WINDOWS, "ELIGIBLE_FROM": dict(SYN_ELIGIBLE)}.get(k, self.saved[k]))

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.saved.items():
            setattr(F, k, v)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def refused(self, name, read, after=None, **history):
        """The SystemExit message of `read` on a synthetic history built with `history` (asserting it IS refused).
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        F.SPOT_ROOT, F.UM_ROOT = make_history(os.path.join(self.tmp, name), **history)
        with self.assertRaises(SystemExit) as cm:
            F.run(read, os.path.join(self.tmp, f"{name}.json"), after, draws=3, require_clean=False)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, f"{name}.json")))
        return str(cm.exception)

    def test_outcome_rows_are_the_reads_own_window_only(self):
        for r, res in self.res.items():
            a, b = SYN_WINDOWS[r]
            got = [row["date"] for row in res["daily"]]
            self.assertEqual(got[0], str(a), r)
            self.assertEqual(got[-1], str(b), r)
            self.assertEqual(len(got), (b - a).days + 1)
            self.assertFalse(res["meta"]["pre_window_pnl_computed"])

    def test_every_fill_and_mark_is_an_exact_0005_bar(self):
        for r, res in self.res.items():
            self.assertEqual(set(res["meta"]["fill_price_lookups"]), {"exact"}, r)
            self.assertEqual(set(res["meta"]["end_mark_lookups"]), {"exact"}, r)
            self.assertEqual(set(res["meta"]["funding_mark_lookups"]), {"exact"}, r)

    def test_family_bh_placebo_and_diagnostics_are_reported(self):
        res = self.res["discovery"]
        self.assertEqual([t["id"] for t in res["tests"]], ["T1", "T2", "T3", "T4"])
        self.assertEqual(res["bh"]["m"], 4)
        L = res["meta"]["window_days"]
        self.assertTrue(all(60 <= k <= L - 60 for k in res["placebo"]["k"]))
        self.assertEqual(res["placebo"]["k_coin"]["AAAUSDT"], res["placebo"]["k"])
        L_c = (SYN_WINDOWS["discovery"][1] - SYN_ELIGIBLE["CCCUSDT"]).days + 1
        self.assertTrue(all(60 <= k <= L_c - 60 for k in res["placebo"]["k_coin"]["CCCUSDT"]))
        self.assertEqual(set(res["placebo"]["coin_alpha"]), set(SYN))
        self.assertEqual(len(res["placebo"]["coin_alpha"]["CCCUSDT"]), 25)
        self.assertEqual(set(res["diagnostics"]), {"N1", "N2", "N3", "N4", "N5", "N6"})
        self.assertEqual(set(res["diagnostics"]["N1"]), {"MA5", "MA10", "MA20", "MA50", "MA100", "mean"})
        self.assertIn("AAAUSDT+BBBUSDT", res["diagnostics"]["N1"]["mean"])
        self.assertEqual(res["tests"][3]["first_day"], str(SYN_ELIGIBLE["CCCUSDT"]))   # CCC joins at its 360th close + 1
        self.assertEqual(res["meta"]["data_truncated_at"], "2021-09-01T00:05:00Z")
        self.assertEqual(res["meta"]["resolved_ambiguities"], list(F.RESOLVED_AMBIGUITIES))
        self.assertFalse(res["meta"]["guarded"])
        self.assertTrue(all(res["meta"]["snapshot"]["series"][s]["perp_5m"]["sha256"] for s in SYN))

    def test_proxy_rest_and_archive_funding_all_appear(self):
        self.assertEqual(set(self.res["discovery"]["meta"]["funding_settlements_by_source"]), {"rest", "proxy", "archive"})

    def test_history_chains_and_the_label_is_final_after_exposed(self):
        hist = self.res["exposed"]["history"]
        self.assertEqual(set(hist), set(F.READS))
        self.assertTrue(any(self.res["exposed"]["label"].startswith(x) for x in
                            ("VALIDATED", "PROMISING", "DEAD", "INCONCLUSIVE")))
        self.assertTrue(self.res["discovery"]["label"].startswith(("PENDING", "DEAD")))

    def test_later_reads_refuse_without_the_previous_json(self):
        with self.assertRaises(SystemExit):
            F.run("confirmation", os.path.join(self.tmp, "x.json"), require_clean=False)
        with self.assertRaises(SystemExit):
            F.run("exposed", os.path.join(self.tmp, "x.json"), self.out["discovery"], require_clean=False)
        with self.assertRaises(SystemExit):
            F.run("discovery", os.path.join(self.tmp, "x.json"), self.out["discovery"], require_clean=False)

    def test_a_read_refuses_when_the_data_do_not_reach_its_end(self):
        F.WINDOWS = dict(SYN_WINDOWS, exposed=(D(2022, 4, 1), D(2023, 1, 31)))
        with self.assertRaises(SystemExit) as cm:
            F.run("exposed", os.path.join(self.tmp, "x.json"), self.out["confirmation"], draws=3, require_clean=False)
        self.assertIn("not ready", str(cm.exception))

    def test_a_read_refuses_without_its_end_mark(self):
        msg = self.refused("no_end_bar", "exposed", self.out["confirmation"],
                           drop_5m={("AAAUSDT", F.t_fill(D(2023, 1, 1)))})
        self.assertIn("not ready", msg)
        self.assertIn("AAAUSDT: no 5m bar opens at 00:05 UTC on 1 required day(s)", msg)

    def test_a_read_refuses_when_the_data_end_on_its_last_day(self):
        msg = self.refused("ends_last_day", "exposed", self.out["confirmation"], last=D(2022, 12, 31))
        self.assertIn("not ready", msg)
        self.assertIn("2023-01-01T00:05:00Z", msg)

    def test_a_read_refuses_without_the_settlement_after_its_last_day(self):
        msg = self.refused("no_end_funding", "exposed", self.out["confirmation"],
                           drop_funding={("BBBUSDT", F.t_at(D(2023, 1, 1)))})
        self.assertIn("not ready", msg)
        self.assertIn("BBBUSDT: realized funding ends 2022-12-31T16:00:00Z", msg)

    def test_a_read_refuses_a_missing_0005_bar_inside_its_window(self):
        msg = self.refused("hole", "discovery", drop_5m={("CCCUSDT", F.t_fill(D(2021, 6, 10)))})
        self.assertIn("not ready", msg)
        self.assertIn("2021-06-10T00:05:00Z (next bar 2021-06-10T04:00:00Z)", msg)

    def test_a_read_refuses_a_funding_gap_inside_its_window(self):
        msg = self.refused("fgap", "discovery", drop_funding={("AAAUSDT", F.t_at(D(2021, 3, 10), 8))})
        self.assertIn("not ready", msg)
        self.assertIn("2021-03-10T00:00:00Z -> 2021-03-10T16:00:00Z", msg)

    def test_a_read_refuses_an_eligibility_date_other_than_the_preregistered_one(self):
        msg = self.refused("late_spot", "discovery", drop_first_spot={"AAAUSDT": 10})
        self.assertIn("AAAUSDT: eligible from 2021-01-05", msg)
        F.ELIGIBLE_FROM = dict(SYN_ELIGIBLE, AAAUSDT=D(2021, 1, 5), BBBUSDT=D(2021, 1, 5))
        msg = self.refused("late_spot_both", "discovery", drop_first_spot={"AAAUSDT": 10, "BBBUSDT": 10})
        self.assertIn("after the window's first day 2020-12-26", msg)          # never a silently shorter window

    def test_data_after_the_read_end_never_change_the_read(self):
        """Point-in-time for the whole read: perturb every 5m bar after the discovery END, every spot close from its last day
        on and every funding rate from the END; the read JSON is identical except meta.after and the file inventory.
        (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
        F.SPOT_ROOT, F.UM_ROOT = make_history(os.path.join(self.tmp, "b"), perturb_end=SYN_WINDOWS["discovery"][1])
        out = os.path.join(self.tmp, "disc_b.json")
        F.run("discovery", out, draws=25, require_clean=False)
        base, other = _json(self.out["discovery"]), _json(out)
        self.assertNotEqual(base["meta"]["snapshot"], other["meta"]["snapshot"])     # the files DID change after END
        for res in (base, other):
            res["meta"].pop("after")
            res["meta"].pop("snapshot")
        self.assertEqual(other, base)

    def test_dry_run_is_outcome_blind_and_reports_missing_files(self):
        out = os.path.join(self.tmp, "dry.json")
        shutil.move(os.path.join(F.UM_ROOT, "funding_rest.CCCUSDT.json.gz"), os.path.join(self.tmp, "moved.gz"))
        try:
            res = F.dry_run(out)
        finally:
            shutil.move(os.path.join(self.tmp, "moved.gz"), os.path.join(F.UM_ROOT, "funding_rest.CCCUSDT.json.gz"))
        self.assertTrue(any("funding_rest" in m for m in res["symbols"]["CCCUSDT"]["missing"]))
        self.assertTrue(any("spot 5m" in m for m in res["symbols"]["CCCUSDT"]["missing"]))
        w = res["reads"]["discovery"]["AAAUSDT"]
        self.assertTrue(w["ready"])
        self.assertEqual(set(w["submodel_entries"]), {str(n) for n in F.NS})
        text = json.dumps(dict(res, meta={k: v for k, v in res["meta"].items() if k != "snapshot"}))   # paths: tmp names
        for word in ("alpha", "\"r\"", "pnl", "excess", "net_mean", "sigma"):
            self.assertNotIn(word, text)
        x = res["reads"]["exposed"]["AAAUSDT"]
        self.assertTrue(x["ready"])
        self.assertTrue(x["end_mark"]["exact_bar"])
        self.assertTrue(x["last_day_settlements"]["has_0000_after_last_day"])

    def test_dry_run_flags_a_missing_end_mark_and_a_late_fill(self):
        F.SPOT_ROOT, F.UM_ROOT = make_history(os.path.join(self.tmp, "dry_b"), last=D(2022, 12, 31),
                                              drop_5m={("CCCUSDT", F.t_fill(D(2021, 6, 10)))})
        res = F.dry_run(os.path.join(self.tmp, "dry_b.json"))
        x = res["reads"]["exposed"]["AAAUSDT"]
        self.assertFalse(x["ready"])
        self.assertFalse(x["end_mark"]["exact_bar"])
        self.assertFalse(x["last_day_settlements"]["has_0000_after_last_day"])
        c = res["reads"]["discovery"]["CCCUSDT"]
        self.assertFalse(c["ready"])
        self.assertEqual(c["fill_bars"], {"exact_0005_bar": c["eligible_days"] - 1, "later_bar": 1})

    def test_the_guard_refuses_uncommitted_code_a_missing_addendum_and_a_short_placebo(self):
        out = os.path.join(self.tmp, "g.json")
        F._git = lambda *a: (1, "") if a[0] == "ls-files" else (0, "")
        with self.assertRaises(SystemExit) as cm:
            F.run("discovery", out)
        self.assertIn("not tracked", str(cm.exception))
        F._git = lambda *a: (0, "?? x\n") if a[0] == "status" else (0, "")
        with self.assertRaises(SystemExit) as cm:
            F.run("discovery", out)
        self.assertIn("uncommitted changes", str(cm.exception))
        F._git = lambda *a: (0, "abc123\n") if a[0] == "rev-parse" else (0, "")
        F._prereg_text = lambda: "no addendum here"
        with self.assertRaises(SystemExit) as cm:
            F.run("discovery", out)
        self.assertIn(F.PREREG_AMENDMENT, str(cm.exception))
        with self.assertRaises(SystemExit) as cm:
            F.run("discovery", out, draws=25)
        self.assertIn("placebo draws", str(cm.exception))
        F._prereg_text = lambda: "... " + F.PREREG_AMENDMENT + " ..."
        with self.assertRaises(SystemExit) as cm:                          # an --after written without the guard
            F.run("confirmation", out, self.out["discovery"])
        self.assertIn("refusing", str(cm.exception))
        self.assertFalse(os.path.exists(out))

    def test_a_guarded_read_records_code_and_data_identity(self):
        F._git = lambda *a: (0, "abc123\n") if a[0] == "rev-parse" else (0, "")
        F._prereg_text = lambda: F.PREREG_AMENDMENT
        F.PLACEBO_DRAWS = 5
        res = F.run("discovery", os.path.join(self.tmp, "guarded.json"))
        m = res["meta"]
        self.assertTrue(m["guarded"])
        self.assertEqual(m["git_head"], "abc123")
        self.assertEqual(sorted(m["committed_sha256"]), sorted(F.GUARDED))
        self.assertEqual(m["params"]["placebo_draws"], 5)
        snap = m["snapshot"]["series"]
        self.assertIsNone(snap["CCCUSDT"]["spot_5m"])
        self.assertEqual(len(snap["AAAUSDT"]["funding"]["sha256"]), 64)


def pearson(a, b):
    """Stand-in for book_sim.corr (same contract: union of days, a missing day is 0) -- the FTMO book is never loaded here.
    (docs/plans/2026-10-03-edge-c1-crypto-trend-preregistration.md)"""
    days = sorted(set(a) | set(b))
    if len(days) < 3:
        return None
    x, y = [a.get(d, 0.0) for d in days], [b.get(d, 0.0) for d in days]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sx = sum((u - mx) ** 2 for u in x) ** 0.5
    sy = sum((v - my) ** 2 for v in y) ** 0.5
    return sum((u - mx) * (v - my) for u, v in zip(x, y)) / (sx * sy) if sx and sy else None


if __name__ == "__main__":
    unittest.main()
