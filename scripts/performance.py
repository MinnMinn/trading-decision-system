"""CLAUDE.md §39 -- THE computer for docs/architecture/performance-metrics.json.

§39 lists twenty-three metrics and adds two rules that are easy to read past:

    "Always show sample size."
    "Do not optimize against a single universal metric."

Before this module the repo computed sixteen of the twenty-three, in two places that agreed by accident
(`journal.stats()` and `stability-report.metrics()`), and had no test over any of them. Seven were absent
outright and four more were wrong in the same way: `journal.stats()` folded every `R <= 0` into `losses`, so a
flat trade sat in the win-rate denominator AND extended the losing streak -- exactly the trade that management
produces when it moves a stop to entry.

    import performance as P

    res = P.metrics(trades, equity=curve, account=AP.get("pilot-mt5-demo"))
    res["n"]                  -> sample size, always present
    res["win_rate"]           -> 0.34
    res["sortino"]            -> {"unavailable": "...", "owner": "§39"} when it cannot be computed
    res["risk_of_ruin"]       -> {"value": 0.07, "method": "bootstrap", "iterations": ..., "seed": ...}

Four properties this module exists to hold:

1. **Sample size is not optional.** `n` is written at the top level by the constructor, and a metric whose
   population is below its declared `min_n` comes back `unavailable()` rather than as a number a reader has to
   know to distrust. Three trades do not have a Sharpe ratio.
2. **Unavailable is a value.** Profit factor with no losing trade, Sortino with no downside, P&L with no
   account: each returns a reason, never `None`, never infinity, never a large placeholder. A placeholder
   sorts, and sorting is how a placeholder becomes a decision.
3. **Breakeven is its own bucket**, because §39 lists it beside wins and losses. It stays in the win-rate
   denominator (it happened) and breaks both streaks (it is neither).
4. **No universal score.** There is no `score()`. There is `refuse_universal_score()`, whose body raises, and
   the docstring explains what to do instead.

A probability here always carries its method, its assumptions and its seed. `risk_of_ruin: 0.07` on its own is
a decoration; this module will not produce one.
"""
import json
import math
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

PATH = os.path.join(ROOT, "docs", "architecture", "performance-metrics.json")

#: Default half-width of the breakeven band, in R. A trade that exits within 0.05R of entry is flat: the
#: difference is fees and a tick, not an outcome. Callers whose engine LABELS breakeven (backtest-methods'
#: `walk()` does, once management has moved the stop) do not depend on this number.
BREAKEVEN_BAND = 0.05

#: Bootstrap settings for the three probability metrics. Declared, not hidden: a probability whose iteration
#: count and seed are unknown is not reproducible (§46), and these travel into every result.
BOOTSTRAP_ITERATIONS = 2000
BOOTSTRAP_SEED = 20260918


class RegistryError(ValueError):
    """The §39 registry itself is wrong -- raised at import."""


class NotDeclared(KeyError):
    """Something asked for a metric CLAUDE.md §39 does not list."""


class UniversalScoreRefused(RuntimeError):
    """A caller tried to collapse §39's metrics into one number."""


def _load(path=None):
    path = path or PATH
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = data.get("metrics")
    if not isinstance(rows, list) or not rows:
        raise RegistryError(f"{path}: `metrics` must be a non-empty list")
    kinds = set(data.get("kinds") or ())
    seen = set()
    for m in rows:
        for field in ("id", "spec_name", "kind", "definition", "implemented_by"):
            if not str(m.get(field) or "").strip():
                raise RegistryError(f"{path}: metric {m.get('id')!r} has no {field!r}")
        if m["id"] in seen:
            raise RegistryError(f"{path}: duplicate metric id {m['id']!r}")
        seen.add(m["id"])
        if m["kind"] not in kinds:
            raise RegistryError(f"{path}: metric {m['id']!r} has kind {m['kind']!r}, which is not one of "
                                f"{sorted(kinds)}")
        if not isinstance(m.get("min_n"), int) or m["min_n"] < 0:
            raise RegistryError(f"{path}: metric {m['id']!r} must declare an integer `min_n` -- the sample "
                                f"size below which it is not computed. §39: 'Always show sample size.'")
        if not isinstance(m.get("needs"), list) or not m["needs"]:
            raise RegistryError(f"{path}: metric {m['id']!r} must say what inputs it `needs`")
    return data, {m["id"]: m for m in rows}, tuple(m["id"] for m in rows)


_DATA, METRICS, ORDER = _load()


def metric(mid):
    m = METRICS.get(mid)
    if m is None:
        raise NotDeclared(f"no §39 metric {mid!r}; the twenty-three are {list(ORDER)}")
    return m


def spec_name(mid):
    return metric(mid)["spec_name"]


def unavailable(reason, owner="§39"):
    """The value of a metric that could not be computed. A dict, never None: `None` reads as zero in a
    template and sorts as a number in a ranking, and both of those have happened."""
    return {"unavailable": reason, "owner": owner}


def is_unavailable(v):
    return isinstance(v, dict) and "unavailable" in v


def refuse_universal_score(*_a, **_kw):
    """CLAUDE.md §39: 'Do not optimize against a single universal metric.'

    There is deliberately no implementation. A ranking that must choose between two systems belongs in the
    caller and must be LEXICOGRAPHIC over named metrics in a declared order -- `scripts/rank-setups.py` sorts
    on (not blown up, share of positive quarters, share of positive years, worst quarter, stability), so a
    reader can see which criterion decided and a change of objective is a change of that tuple. A weighted
    composite hides both.
    """
    raise UniversalScoreRefused(
        "CLAUDE.md §39 forbids a single universal metric. Rank lexicographically over named metrics, and "
        "expose the objective (§48: 'Always expose ranking objective, metrics, sample size, validation "
        "state, test period, assumptions, robustness status').")


# ---- input normalisation


def _r(t):
    """The R multiple of one trade record, from whichever of the repo's two field names it carries."""
    for k in ("net_R", "R", "r_multiple"):
        v = t.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return None


def _bucket(t, band):
    """'win' / 'loss' / 'breakeven' for one trade. An engine's own label wins over the band: `walk()` knows
    it moved the stop to entry, and that is a breakeven trade even when the fee makes R slightly negative."""
    if str(t.get("outcome") or "").lower() == "breakeven":
        return "breakeven"
    r = _r(t)
    if r is None:
        return None
    if abs(r) <= band:
        return "breakeven"
    return "win" if r > 0 else "loss"


def _curve_from_R(rs):
    """Cumulative R as an equity-like series, for a population with no account attached."""
    out, cum = [], 0.0
    for r in rs:
        cum += r
        out.append(cum)
    return out


def _drawdowns(series, *, start_peak=None):
    """Every drawdown episode in a series, as (depth_fraction, length, recovered).

    An episode still open at the end is returned with `recovered=False` rather than dropped: dropping it
    flatters exactly the curve that ends underwater, which is the one a reader needs to see.
    """
    if not series:
        return []
    peak = series[0] if start_peak is None else start_peak
    eps, cur_depth, cur_len, in_dd = [], 0.0, 0, False
    for v in series:
        if v >= peak:
            if in_dd:
                eps.append((cur_depth, cur_len, True))
                in_dd, cur_depth, cur_len = False, 0.0, 0
            peak = v
            continue
        in_dd = True
        cur_len += 1
        depth = (peak - v) / abs(peak) if peak else 0.0
        cur_depth = max(cur_depth, depth)
    if in_dd:
        eps.append((cur_depth, cur_len, False))
    return eps


# ---- the account-dependent half


def _account_terms(account):
    """(initial_balance, risk_fraction, ruin_fraction, failure_rules) or a reason it cannot be read.

    Deliberately strict. §39's money metrics are about a specific account, and inventing a balance to make a
    number appear is how a research report ends up describing an account nobody has.

    `initial_balance` is read as EITHER shape the registry vocabulary allows (docs/architecture/
    account-profiles.json `_rule_vocabulary`): `{amount, currency}` (the documented shape; every real profile
    now uses it -- the two prop-challenge profiles, §0.1) or a bare number (kept for callers that build a
    minimal `{"rules": {"initial_balance": N}}` fixture, e.g. this module's own tests). A dict missing
    `amount` is refused with a reason, never guessed at.
    """
    if account is None:
        return None, "no account profile supplied; R is account-free but money, ruin and failure are not (§33)"
    rules = (account or {}).get("rules") or {}
    bal = rules.get("initial_balance")
    if isinstance(bal, dict):
        bal = bal.get("amount")
    if not isinstance(bal, (int, float)) or isinstance(bal, bool) or bal <= 0:
        why = rules.get("_initial_balance_why") or "the profile declares no initial_balance"
        return None, f"this account has no starting balance to measure against: {why}"
    return {"balance": float(bal), "rules": rules}, None


def _failure_thresholds(terms):
    """The equity levels this account fails at, as fractions of the starting balance (§33).

    `max_daily_loss` and `min_trading_days` are carried here too (A2, docs/plans/2026-09-18-
    close-feature-gaps.md §0.1): `max_daily_loss` as a raw pct (compared against the DAY's starting equity,
    not the account's), `min_trading_days` as an integer day count the bootstrap must not report a pass
    before. Neither is a per-trade equity floor like the other two, so `_bootstrap`/`_bootstrap_days` read
    them under their own names rather than the generic floor check the other keys share.
    """
    rules = terms["rules"]
    out = {}
    mtd = rules.get("max_total_drawdown")
    if isinstance(mtd, dict) and isinstance(mtd.get("pct"), (int, float)):
        out["max_total_drawdown"] = 1.0 - float(mtd["pct"])
    td = rules.get("trailing_drawdown")
    if isinstance(td, dict) and isinstance(td.get("pct"), (int, float)):
        out["trailing_drawdown"] = float(td["pct"])
    mdl = rules.get("max_daily_loss")
    if isinstance(mdl, dict) and isinstance(mdl.get("pct"), (int, float)):
        out["max_daily_loss"] = float(mdl["pct"])
    days = rules.get("min_trading_days")
    if isinstance(days, int) and not isinstance(days, bool) and days > 0:
        out["min_trading_days"] = days
    return out


def _day_blocks(rows, rs):
    """Group (row, R) pairs into per-UTC-day blocks, in the order each day is first seen, keyed by the
    `YYYY-MM-DD` prefix of `entry_time`. Returns None the moment any row lacks a usable `entry_time`: a
    day-loss rule needs EVERY trade's day known, or the missing ones would silently vanish from the
    resampled population rather than being reported as the reason `max_daily_loss` was dropped."""
    order = []
    buckets = {}
    for t, r in zip(rows, rs):
        et = t.get("entry_time")
        key = et[:10] if isinstance(et, str) and len(et) >= 10 else None
        if key is None:
            return None
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(r)
    return [buckets[k] for k in order]


def _bootstrap(rs, *, risk, horizon, iterations, seed, ruin_level, failure, profit_target):
    """One pass of the bootstrap that answers all three probability metrics at once.

    Resamples the OBSERVED per-trade R distribution with replacement -- no distributional assumption, which is
    the point: a 3R-target system's outcomes are not the two-valued bet the closed-form gambler's-ruin formula
    is derived for, so that formula would answer a question about a different strategy.

    The three events are tracked by WHEN they first happen, not by short-circuiting on the first one. A first
    version stopped the path at the account's failure threshold, which made `risk_of_ruin` structurally zero
    for every account whose drawdown rule is tighter than the ruin level -- i.e. every account -- and a metric
    that is zero by construction is worse than an absent one. Ruin is still absorbing (nothing recovers from
    10 % of the starting balance); a failure is not, because §33's failure conditions describe the account's
    rules being breached, and the equity curve continues regardless of whether a rule says to stop.
    """
    rng = random.Random(seed)
    ruined = failed = passed = 0
    for _ in range(iterations):
        eq, peak = 1.0, 1.0
        t_ruin = t_fail = t_target = None
        for i in range(horizon):
            eq *= (1.0 + risk * rng.choice(rs))
            peak = max(peak, eq)
            if t_fail is None:
                if "max_total_drawdown" in failure and eq <= failure["max_total_drawdown"]:
                    t_fail = i
                elif "trailing_drawdown" in failure and eq <= peak * (1.0 - failure["trailing_drawdown"]):
                    t_fail = i
            if t_target is None and profit_target is not None and eq >= 1.0 + profit_target:
                t_target = i
            if eq <= ruin_level:
                t_ruin = i
                break
        ruined += t_ruin is not None
        failed += (t_fail is not None) or (t_ruin is not None)   # ruin is a failure; the converse is not true
        passed += (t_target is not None
                   and (t_fail is None or t_target < t_fail)
                   and (t_ruin is None or t_target < t_ruin))
    return ruined / iterations, failed / iterations, passed / iterations


def _bootstrap_days(blocks, *, risk, horizon_days, iterations, seed, ruin_level, failure, profit_target,
                    min_days=None):
    """Day-block twin of `_bootstrap`, for accounts that declare `max_daily_loss`.

    A daily-loss rule is a statement about trades taken TOGETHER on one day; independently resampling
    individual trades destroys that correlation by construction (a day that actually lost 6 % could be split
    across two resampled 'days' that each look fine on their own, and the rule would never fire). This
    resamples whole per-day blocks (`_day_blocks`) instead, applying each day's trades in their original order
    and compounding equity trade-by-trade within the day.

    `max_daily_loss` is checked against the equity AT THE START of the simulated day (its own basis,
    `day_start_equity`); `max_total_drawdown` / `trailing_drawdown` / the profit target are checked once per
    day, at the day's close -- a day-granularity reading of the same rules `_bootstrap` checks per trade,
    which is the coarsest this can be without re-deriving intra-day equity paths the input does not carry.
    `min_days` (the account's `min_trading_days`, an OBJECTIVE per §33, not a gate) delays the earliest day
    `prop_pass_probability`'s PASS event may fire, so reaching the target on day 1 of a 4-minimum-day account
    is not reported as having passed on day 1.
    """
    rng = random.Random(seed)
    ruined = failed = passed = 0
    for _ in range(iterations):
        eq, peak = 1.0, 1.0
        t_ruin = t_fail = t_target = None
        for d in range(horizon_days):
            day_start = eq
            for r in rng.choice(blocks):
                eq *= (1.0 + risk * r)
            peak = max(peak, eq)
            if t_fail is None:
                if "max_daily_loss" in failure and eq <= day_start * (1.0 - failure["max_daily_loss"]):
                    t_fail = d
                elif "max_total_drawdown" in failure and eq <= failure["max_total_drawdown"]:
                    t_fail = d
                elif "trailing_drawdown" in failure and eq <= peak * (1.0 - failure["trailing_drawdown"]):
                    t_fail = d
            if (t_target is None and profit_target is not None and eq >= 1.0 + profit_target
                    and (min_days is None or d + 1 >= min_days)):
                t_target = d
            if eq <= ruin_level:
                t_ruin = d
                break
        ruined += t_ruin is not None
        failed += (t_fail is not None) or (t_ruin is not None)
        passed += (t_target is not None
                   and (t_fail is None or t_target < t_fail)
                   and (t_ruin is None or t_target < t_ruin))
    return ruined / iterations, failed / iterations, passed / iterations


# ---- the computation


def metrics(trades, *, equity=None, account=None, breakeven_band=BREAKEVEN_BAND, bars_per_year=None,
            iterations=BOOTSTRAP_ITERATIONS, seed=BOOTSTRAP_SEED, horizon=None, trades_per_year=None):
    """Every metric CLAUDE.md §39 names, for one population of closed trades.

    `trades`          -- records carrying an R multiple (`net_R` / `R` / `r_multiple`); optionally `outcome`,
                         `mfe`, `mae`, `bars_held`, `pnl_usd`.
    `equity`          -- the account curve as a list of values or (label, value) pairs. Omitted: a cumulative-R
                         curve is used, and the account-relative metrics say they are in R.
    `account`         -- a profile from scripts/account_profile.py. Without one, P&L / ruin / failure / pass
                         are unavailable BY NAME rather than assumed.
    `trades_per_year` -- enables an annualised Sharpe/Sortino. Without it they are reported per-trade AND
                         labelled per-trade, because the two differ by an order of magnitude.

    Every key in the returned dict is a metric id from the registry, plus `n` and `_assumptions`.
    """
    band = float(breakeven_band)
    rows = [t for t in (trades or []) if _r(t) is not None]
    rs = [_r(t) for t in rows]
    n = len(rs)
    buckets = [_bucket(t, band) for t in rows]
    wins = [r for r, b in zip(rs, buckets) if b == "win"]
    losses = [r for r, b in zip(rs, buckets) if b == "loss"]
    bes = [r for r, b in zip(rs, buckets) if b == "breakeven"]

    out = {"n": n, "_source": "docs/architecture/performance-metrics.json (CLAUDE.md §39)",
           "_assumptions": {"breakeven_band_R": band,
                            "risk_free_rate": 0.0,
                            "annualised": bool(trades_per_year),
                            "bootstrap": {"iterations": iterations, "seed": seed}}}

    def gate(mid, value):
        """Apply the metric's declared min_n. §39's 'always show sample size' with teeth: below the floor the
        answer is a reason, not a number."""
        need = metric(mid)["min_n"]
        if n < need:
            return unavailable(f"sample size {n} is below the {need} this metric needs to mean anything")
        return value

    # --- counts and the ratios over them
    out["total_trades"] = n
    out["wins"] = len(wins)
    out["losses"] = len(losses)
    out["breakeven"] = len(bes)
    out["win_rate"] = gate("win_rate", (len(wins) / n) if n else None)
    out["expectancy"] = gate("expectancy", (sum(rs) / n) if n else None)
    out["average_R"] = gate("average_R", (sum(rs) / n) if n else None)
    out["average_win_R"] = (sum(wins) / len(wins)) if wins else unavailable("no winning trade")
    out["average_loss_R"] = (sum(losses) / len(losses)) if losses else unavailable("no losing trade")
    out["total_R"] = sum(rs)
    gross_loss = abs(sum(losses))
    out["profit_factor"] = gate("profit_factor",
                                (sum(wins) / gross_loss) if gross_loss > 0 else
                                unavailable("no losing trade, so the ratio has no denominator -- reported as "
                                            "unavailable rather than as infinity, which would sort"))

    # --- streaks. A breakeven trade breaks BOTH runs: it is neither a win nor a loss (§39 lists it apart).
    best = {"win": 0, "loss": 0}
    cur = {"win": 0, "loss": 0}
    for b in buckets:
        for k in ("win", "loss"):
            cur[k] = cur[k] + 1 if b == k else 0
            best[k] = max(best[k], cur[k])
    out["consecutive_wins"] = gate("consecutive_wins", best["win"])
    out["consecutive_losses"] = gate("consecutive_losses", best["loss"])

    # --- excursions
    for mid, field, sign in (("mfe", "mfe", 1), ("mae", "mae", -1)):
        vals = [(t.get(field), b) for t, b in zip(rows, buckets) if isinstance(t.get(field), (int, float))]
        if not vals:
            out[mid] = unavailable(
                "no trade in this population records an intra-trade extreme; the backtest engine writes "
                "`mfe`/`mae` (scripts/backtest-methods.py walk()), the live journal does not yet")
            continue
        allv = [v for v, _ in vals]
        w = [v for v, b in vals if b == "win"]
        l = [v for v, b in vals if b == "loss"]
        out[mid] = gate(mid, {"mean": sum(allv) / len(allv), "n": len(allv),
                              "mean_on_winners": (sum(w) / len(w)) if w else None,
                              "mean_on_losers": (sum(l) / len(l)) if l else None})

    # --- the curve half
    curve = [v[1] if isinstance(v, (list, tuple)) else v for v in (equity or [])]
    in_R = not curve
    if in_R:
        curve = _curve_from_R(rs)
        # A pure-R curve starts at 0 and can cross it, so depth-as-a-fraction-of-peak is meaningless there.
        # Shift onto a notional 1.0 base so a drawdown is still a proportion of the equity that preceded it.
        curve = [1.0 + c for c in curve]
    eps = _drawdowns(curve, start_peak=curve[0] if curve else None)
    max_dd = max((d for d, _, _ in eps), default=0.0)
    out["max_drawdown"] = gate("max_drawdown", {"fraction": max_dd, "in": "R-equity" if in_R else "account"})
    out["average_drawdown"] = gate("average_drawdown", (
        {"fraction": sum(d for d, _, _ in eps) / len(eps), "episodes": len(eps),
         "includes_unrecovered": any(not rec for _, _, rec in eps)}
        if eps else {"fraction": 0.0, "episodes": 0, "includes_unrecovered": False}))
    under = sum(l for _, l, _ in eps)
    out["time_in_drawdown"] = gate("time_in_drawdown", {
        "fraction_of_series": (under / len(curve)) if curve else 0.0,
        "longest_stretch": max((l for _, l, _ in eps), default=0),
        "unit": "trades" if in_R else "curve points"})
    net = curve[-1] - curve[0] if curve else 0.0
    out["recovery_factor"] = gate("recovery_factor", (
        (net / (max_dd * curve[0])) if (max_dd > 0 and curve and curve[0]) else
        unavailable("no drawdown occurred, so there is nothing to have recovered from")))

    # --- risk-adjusted
    # Sharpe and Sortino are computed INDEPENDENTLY: they fail for different reasons and a shared guard loses
    # the one that matters. A population of nothing but winners has dispersion (Sharpe is fine) and no
    # downside at all (Sortino is unmeasured, not infinite).
    scale = math.sqrt(trades_per_year) if trades_per_year else 1.0
    basis = "annualised" if trades_per_year else "per-trade"
    if n < metric("sharpe")["min_n"]:
        floor_why = f"sample size {n} is below the {metric('sharpe')['min_n']} this metric needs to mean anything"
        out["sharpe"] = out["sortino"] = unavailable(floor_why)
    else:
        mu = sum(rs) / n
        sd = statistics.pstdev(rs)
        out["sharpe"] = ({"value": mu / sd * scale, "basis": basis, "risk_free_rate": 0.0} if sd > 0 else
                         unavailable("every trade returned the same R, so there is no dispersion to divide by"))
        dd = math.sqrt(sum(min(0.0, r) ** 2 for r in rs) / n)
        out["sortino"] = ({"value": mu / dd * scale, "basis": basis, "target_return": 0.0} if dd > 0 else
                          unavailable("no trade finished below the target return, so downside deviation is "
                                      "zero -- the ratio is unmeasured, not infinite"))

    # --- time to target
    held = [(t.get("bars_held"), b) for t, b in zip(rows, buckets)
            if isinstance(t.get("bars_held"), (int, float))]
    winners = [v for v, b in held if b == "win"]
    out["time_to_target"] = gate("time_to_target", (
        {"median_bars": statistics.median(winners), "mean_bars": sum(winners) / len(winners),
         "n_reached_target": len(winners), "n_did_not": n - len(winners),
         "_note": "averaged over the trades that REACHED target; the count that did not is beside it, because "
                  "a mean over survivors alone is a survivorship claim"}
        if winners else unavailable("no trade in this population reached its target, or none records "
                                    "`bars_held`")))

    # --- money and the three probabilities
    terms, why = _account_terms(account)
    # `pnl_usd` is the journal's field name (§41 trade records); `pnl` is the backtest engine's. One lookup
    # over both, because a metric that silently misses the money column of half the repo is worse than absent.
    realised = [t.get("pnl_usd", t.get("pnl")) for t in rows
                if isinstance(t.get("pnl_usd", t.get("pnl")), (int, float))]
    if realised:
        out["pnl"] = {"value": sum(realised), "n_with_pnl": len(realised), "basis": "realised, from the trades"}
    elif terms:
        risk = _risk_fraction(account)
        eq = terms["balance"]
        for r in rs:
            eq *= (1.0 + risk * r)
        out["pnl"] = {"value": eq - terms["balance"], "basis": f"modelled: compounding at {risk:.4g} of "
                                                               f"equity per trade from {terms['balance']:g}"}
    else:
        out["pnl"] = unavailable(why or "no account and no per-trade P&L")

    prob_floor = metric("risk_of_ruin")["min_n"]
    if not terms:
        for mid in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            out[mid] = unavailable(why)
    elif n < prob_floor:
        # Below min_n the resample is degenerate (n=4 means every path is drawn from four numbers), so this
        # stays a refusal. The old floor of 30 was NOT that -- it was a confidence judgement wearing a
        # computability floor's clothes, and it hid the one answer a prop account is asked for. See
        # `low_confidence_below` in the registry and `_batch_spread` below (user decision 2026-09-19).
        for mid in ("risk_of_ruin", "account_failure_probability", "prop_pass_probability"):
            out[mid] = unavailable(f"sample size {n} is below the {prob_floor} a bootstrap needs to resample "
                                   f"at all -- with {n} outcomes every path is drawn from the same {n} numbers")
    else:
        rules = terms["rules"]
        fail = _failure_thresholds(terms)
        min_days = fail.pop("min_trading_days", None)   # an objective's delay, not a failure threshold (§33)
        pt = rules.get("profit_target")
        pt = float(pt["pct"]) if isinstance(pt, dict) and isinstance(pt.get("pct"), (int, float)) else None
        ruin_level = 0.10          # the repo's own ruin convention (backtest-methods.RUIN_FRAC)
        risk = _risk_fraction(account)

        # max_daily_loss needs its trades grouped by their OWN day (_day_blocks); everything else keeps the
        # per-trade bootstrap. Missing entry_time drops max_daily_loss rather than silently skipping it.
        blocks = _day_blocks(rows, rs) if "max_daily_loss" in fail else None
        dropped_note = None
        if "max_daily_loss" in fail and blocks is None:
            fail = {k: v for k, v in fail.items() if k != "max_daily_loss"}
            dropped_note = "max_daily_loss excluded: no entry_time on trades"

        if blocks is not None:
            hz = int(horizon or max(5, len(blocks)))
            ruin, failed, passed = _bootstrap_days(blocks, risk=risk, horizon_days=hz, iterations=iterations,
                                                   seed=seed, ruin_level=ruin_level, failure=fail,
                                                   profit_target=pt, min_days=min_days)
            common = {"method": "day-block bootstrap: resamples whole UTC trading days with replacement, "
                                 "preserving within-day correlation for max_daily_loss (CLAUDE.md §33/§39)",
                      "iterations": iterations, "seed": seed, "horizon_trades": hz, "horizon_unit": "days",
                      "risk_per_trade": risk, "sample": n}
        else:
            hz = int(horizon or max(100, n))
            ruin, failed, passed = _bootstrap(rs, risk=risk, horizon=hz, iterations=iterations, seed=seed,
                                              ruin_level=ruin_level, failure=fail, profit_target=pt)
            common = {"method": "bootstrap over the observed per-trade R distribution, resampled with replacement",
                      "iterations": iterations, "seed": seed, "horizon_trades": hz, "horizon_unit": "trades",
                      "risk_per_trade": risk, "sample": n}
        if dropped_note:
            common["_dropped"] = dropped_note
        # How wide is this estimate? Re-run the same bootstrap under a handful of different seeds and report
        # the span. A small sample does not make the probability meaningless -- it makes it WIDE, and a span
        # the reader can see is the honest form of that (§39 'always show sample size', no fake precision).
        soft = metric("risk_of_ruin").get("low_confidence_below")
        if isinstance(soft, int) and n < soft:
            def _batch(seed_i):
                # NESTED bootstrap. The outer draw resamples the OBSERVED TRADES with replacement; the inner
                # one walks paths from that pseudo-sample. Varying only the RNG seed (the first version of
                # this, 2026-09-19) measured Monte-Carlo noise, which is tiny at these iteration counts -- it
                # reported a spread of 3 points for a 14-trade population and so said "wide" while showing
                # something narrow. Sampling uncertainty is the thing a small n actually causes, and only the
                # outer draw can see it.
                rng = random.Random(seed + 1000 + seed_i)
                it = max(200, iterations // 5)
                if blocks is not None:
                    pseudo = [blocks[rng.randrange(len(blocks))] for _ in range(len(blocks))]
                    return _bootstrap_days(pseudo, risk=risk, horizon_days=hz, iterations=it,
                                           seed=seed + 1 + seed_i, ruin_level=ruin_level, failure=fail,
                                           profit_target=pt, min_days=min_days)
                pseudo = [rs[rng.randrange(len(rs))] for _ in range(len(rs))]
                return _bootstrap(pseudo, risk=risk, horizon=hz, iterations=it,
                                  seed=seed + 1 + seed_i, ruin_level=ruin_level, failure=fail, profit_target=pt)
            batches = [_batch(i) for i in range(9)]
            common["low_confidence"] = True
            common["low_confidence_why"] = (
                f"sample size {n} is below {soft}: the estimate is computed and usable, but it is WIDE -- "
                f"`spread` is the min-max across 9 NESTED bootstrap batches, each of which first resamples "
                f"the {n} observed trades with replacement, so it measures how much the answer depends on "
                f"which {n} trades happened to occur")
            common["spread"] = {k: [round(min(b[i] for b in batches), 4), round(max(b[i] for b in batches), 4)]
                                for i, k in enumerate(("risk_of_ruin", "account_failure_probability",
                                                       "prop_pass_probability"))}
        out["risk_of_ruin"] = dict(common, value=ruin, threshold=f"equity <= {ruin_level:.0%} of start")
        out["account_failure_probability"] = (
            dict(common, value=failed, conditions=sorted(fail) or ["ruin only"],
                 _note="a strictly wider event than ruin: any declared failure condition counts (§33)")
            if fail else unavailable(
                "this account profile declares no failure condition beyond ruin, so there is no distinct "
                "failure event to estimate (§33: account rules are configurable and this one has none)"))
        out["prop_pass_probability"] = (
            dict(common, value=passed, profit_target=pt)
            if pt is not None else unavailable(
                "this account declares no profit_target, so it cannot be passed -- a personal or demo account "
                "has no challenge to complete. A property of the profile, not a gap in the metric (§33)."))

    missing = [m for m in ORDER if m not in out]
    if missing:                       # a registry entry with no computation would be a silent hole
        raise RegistryError(f"performance.metrics() computed nothing for {missing}; every metric declared in "
                            f"docs/architecture/performance-metrics.json must produce a value or an "
                            f"unavailable() reason")
    return out


def _risk_fraction(account):
    """Per-trade risk as a fraction of equity, from the ONE source (§34) via the account profile."""
    try:
        import account_profile as AP
        return float(AP.effective_risk_pct(account))
    except Exception:
        import trading_env
        return float(trading_env.MAX_RISK_PCT)


def describe(res):
    """A one-line summary that always leads with the sample size (§39)."""
    parts = [f"n={res['n']}"]
    for mid in ("win_rate", "expectancy", "profit_factor", "max_drawdown"):
        v = res.get(mid)
        if is_unavailable(v):
            continue
        if isinstance(v, dict):
            v = v.get("fraction", v.get("value"))
        parts.append(f"{spec_name(mid)} {v:.2f}" if isinstance(v, float) else f"{spec_name(mid)} {v}")
    un = [m for m in ORDER if is_unavailable(res.get(m))]
    line = " · ".join(parts)
    if un:
        line += f" · unavailable: {', '.join(un)}"
    return line


if __name__ == "__main__":
    print(f"CLAUDE.md §39 -- {len(ORDER)} metrics\n")
    for mid in ORDER:
        m = METRICS[mid]
        print(f"{mid:<30} {m['kind']:<12} min_n={m['min_n']:<4} needs={','.join(m['needs'])}")
