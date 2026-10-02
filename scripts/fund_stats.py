"""The statistics of the fund search -- docs/plans/2026-09-28-methodology-improvement-plan.md §1.4, restated as
PURE functions (no I/O, no engine, no clock) so every rule is unit-testable on synthetic trades and can never
be quietly loosened by the orchestrator (scripts/fund-search.py) that calls them.

Every threshold below is a named constant with its source. "Tighten later" is allowed; loosening is not
(plan §6 item 2): a change to any constant here is a research-integrity event, not a tuning knob.

A TRADE is a dict with at least `entry_time`, `exit_time` (ISO-8601 `...Z`), `net_R` (net of REAL costs), and
`symbol`. Optional: `adx14_d1` (the D1 ADX(14) of the last COMPLETED D1 bar at the entry, for the regime split),
`adx14` (the decision-timeframe ADX, reporting only), `volume_kind`.

WHAT IS COMPUTED, in the order the plan states it (§1.4):

1. NESTED rolling-origin walk-forward (`make_folds`, `nested_walk_forward`). Inside each fold the V values are
   chosen on TRAINING trades only (`train_window`: entered at the data start, and EXITED strictly before the
   test fold starts -- a purge, so a trade still open when the test fold begins cannot leak its outcome into
   selection). The chosen values are then scored on that fold's own TEST trades. The lower bound is taken on
   the POOLED test trades of all folds and nothing else.
2. A test fold with fewer than MIN_FOLD_TRADES trades makes the cell verdict "insufficient".
3. The primary bound is the MIN of five one-sided bounds (iid t, CR1 by date / 30-day / quarter / half-year) at the
   FLOOR confidence 1 - FAMILY_ALPHA/F (`n_adjusted_confidence(F)`), F = the number of CANDIDATE procedures (3 cells x
   2 methods = 6; family A, pre-registration 0.2): grid values are NOT hypotheses of the family (the nesting handles
   value selection). A candidate's p = the MAX of the five one-sided p-values; Holm's step-down over the F candidates
   (`holm_stepdown`) is applied at REPORT time (fund-search.py `report`).
4. Stability: net expectancy > 0 on >= ceil(2m/3) of the m symbols, and no single trade above MAX_TRADE_SHARE
   of total net R.
5. Frequency: longest trade-to-trade gap on the pooled account <= MAX_GAP_DAYS in >= MIN_FOLD_SHARE_OK of folds.
6. §45 checks: D1 ADX(14) median regime split, ORDINAL one-component-at-a-time perturbation (`PERTURBATION_AXES`),
   prop_pass_probability (plain and with R shifted down by mean - bound), the stress gate (p90 spread + commission
   margin on the same admitted trades).
7. Everything is reported per symbol (and per `volume_kind` when trades carry one).

INTERPRETATION CHOICES the plan leaves open (each stated where it is used, and returned to the owner):
  * the bound is a one-sided Student-t bound on the mean (`lower_bound`), not a bootstrap: at a tail of
    0.10/6 a percentile bootstrap still needs thousands of resamples to resolve its own quantile;
  * TEST_FOLD_DAYS / MIN_TRAIN_DAYS / MIN_TEST_FOLDS / MIN_TRAIN_TRADES (fold geometry and a training floor);
  * the frequency gap includes the fold's edges (stricter than gaps between trades only);
  * the regime split requires BOTH halves > 0 (stricter than "same sign") and each half >= 25 % of the pooled trades;
  * a symbol with development data but no test trades counts as NOT positive (never dropped).
"""
import bisect
import datetime
import fractions
import itertools
import json
import math

# ---------------------------------------------------------------------------------------------- constants
DEV_CUTOFF = "2024-03-01T00:00:00Z"   # plan §1.1 / §1.4: development = all history before this (exclusive)
FAMILY_ALPHA = 0.10                   # plan §1.4: "one-sided confidence 1 - 0.10/N"
MIN_FOLD_TRADES = 30                  # plan §1.4: "each walk-forward test fold needs at least 30 trades"
MIN_TRAIN_TRADES = 30                 # interpretation: same floor for a value to be ELIGIBLE on a training fold
MAX_TRADE_SHARE = 0.25                # plan §1.4: "no single trade contributes more than 25 % of total net R"
STABILITY_FRACTION = (2, 3)           # plan §1.4: ceil(2m/3)
MAX_GAP_DAYS = 30                     # plan §1.4 / preregistration §8.3
MIN_FOLD_SHARE_OK = 0.90              # plan §1.4: ">= 90 % of folds"
PASS_PROB_MIN = 0.70                  # plan §1.4 / preregistration §2.1
ADX_PERIOD = 14                       # plan §1.4: ADX(14)
TEST_FOLD_DAYS = 365                  # interpretation: one calendar-year test fold
MIN_TRAIN_DAYS = 730                  # interpretation: the first training window is at least two years
MIN_TEST_FOLDS = 2                    # interpretation: fewer than two folds is not a walk-forward

BLOCK_DAYS = 30                       # fix round 1 (C1): the second block clustering is a 30-day window

INSUFFICIENT, PASS, FAIL = "insufficient", "pass", "fail"

#: The checks a verdict needs; `verdict_from` FAILS CLOSED when a stored record lacks one (a record sealed under an older
#: code must not read as a PASS because a newer gate is simply absent).
REQUIRED_CHECKS = ("folds_sufficient", "lower_bound_positive", "stability", "frequency", "regime_split",
                   "perturbation", "prop_pass_probability", "prop_pass_shifted", "stress", "min_trading_days")

#: `verdict_from`'s rule, stated so it can be pre-registered and recorded in the ledger declaration (I4).
VERDICT_PRECEDENCE = ("insufficient (any test fold < MIN_FOLD_TRADES, or fewer than MIN_TEST_FOLDS folds) "
                      "overrides everything; otherwise pass only if EVERY check is ok (primary bound > 0 at the floor "
                      "confidence 1 - 0.10/6, stability, frequency, D1-ADX regime split, ordinal perturbation, "
                      "prop pass, prop pass with R shifted down by mean - bound, stress gate, minimum trading days), else fail. Holm's "
                      "step-down over the six candidates is applied at report time and never turns a failing "
                      "candidate into a pass")

#: Family A (pre-registration 0.2 / A2), stated so the declaration pins it.
FAMILY_DEFINITION = ("the multiple-testing family is the CANDIDATE PROCEDURES (cells x methods = 6): grid values are not "
                     "hypotheses (the nested walk-forward handles value selection); per-candidate primary bound = MIN of "
                     "five one-sided bounds (iid t, CR1 by UTC date / 30-day window / calendar quarter / half-year), i.e. "
                     "candidate p = MAX of the five one-sided p-values; floor confidence 1 - FAMILY_ALPHA/6 for every "
                     "candidate; Holm step-down at FWER FAMILY_ALPHA over the six candidates at report time (a "
                     "candidate with the k-th smallest p is rejected iff p_(k) <= FAMILY_ALPHA/(6-k+1) and every "
                     "smaller p was rejected; NOT RUN and insufficient candidates enter with p = 1); the verdict "
                     "rests on the floor test, so a candidate that fails the floor is never a PASS")

#: The regime split's pre-registered definition (pre-registration 0.7, replaced 2026-10-02): stated in the report and the draft.
REGIME_SPLIT_DEFINITION = ("D1 ADX(14) (Wilder) of the last D1 bar whose CLOSE is at or before the entry time (close = "
                           "max(open label + 24 h, next D1 open label); the entry day's forming bar is never read), from "
                           "the symbol's own stored D1 series, point-in-time; split at the MEDIAN of the pooled TEST "
                           "trades' values (<= median = low half, > median = high half); EACH half must hold at least 25 % of the "
                           "pooled test trades (ties on one symbol-day ADX can leave a tiny half: 'regime halves "
                           "unbalanced' fails the check); BOTH halves must have positive mean net R; a trade with no "
                           "value fails the check")

#: Pre-registration A5 (REPLACED 2026-10-02): ordinal components only, one at a time, the other components at the fold's
#: chosen values; the neighbour must have pooled mean net R > 0 AND a primary bound > 0 at the floor confidence.
PERTURBATION_DEFINITION = ("ORDINAL components only (PERTURBATION_AXES), ONE component at a time, the other components at "
                           "the fold's chosen values; each (component, direction) neighbour pools the test trades of the "
                           "moved value sets (an edge has no neighbour on that side; a fold whose chosen value is not on "
                           "the component's order, e.g. the v1-typed W4a baseline, is not perturbed and is reported); a "
                           "neighbour passes iff its pooled mean net R > 0 AND its primary bound > 0 at the floor "
                           "confidence; every neighbour must pass; categorical items are flipped and REPORTED, never gated")

#: Pre-registration A8 (added 2026-10-02): the two extra conjunctive conditions of a PASS.
STRESS_SPREAD_STAT = "p90"                      # real_costs spread_stat of the stress gate (both legs, price-scaled)
STRESS_COMMISSION_FRACTION = 0.00003            # 0.003 % of notional per round turn: a STRESS MARGIN, NOT an estimate
STRESS_DEFINITION = ("pooled mean net R must stay > 0 on the SAME admitted trades re-priced with the p90 spread "
                     "(price-scaled, relative-spread profile) on both legs and a commission stress margin of 0.003 % of "
                     "notional per round turn charged as 0.00003 * entry / |entry - stop| in R (a stress margin, NOT an "
                     "estimate of FTMO's commission); admission is NOT re-run under stress; the stressed bound is reported, "
                     "the gate is on the mean only")
PROP_SHIFT_DEFINITION = ("prop_pass_probability must ALSO be >= 0.70 for every fund with every pooled test trade's net R "
                         "shifted DOWN by (pooled mean - primary bound at the floor confidence); the admitted trade list, "
                         "sizing and horizon are unchanged; the unshifted requirement stays")
MIN_TRADING_DAYS_DEFINITION = (
    "for EVERY fund of the prop gate whose account profile declares `min_trading_days` (FTMO Challenge Phase 1: 4, read from "
    "docs/architecture/account-profiles.json at evaluation time; the profile records the figure as flagged for verification: "
    "2024+ sources report 4, older sources 10), EVERY test fold must contain at least that many DISTINCT UTC calendar days "
    "on which a pooled test trade was INITIATED (entry day, the reading account_profile.objectives uses); a fund without the "
    "field (The5ers High Stakes Step 1: min_profitable_days instead) is not checked; an unreadable or malformed profile "
    "fails the check (fail closed). A fold is 365 days while the challenge horizon is 120 resampled active days, so this is "
    "a NECESSARY-condition proxy for the objective, not a replay of the challenge. Owner decision 2026-10-02: a tightening, "
    "harmless in practice because every fold needs >= MIN_FOLD_TRADES trades")
MDE_POWER = 0.80                                # section C item 1: the power of the minimum detectable edge


# ------------------------------------------------------------------------------------------------ time
def ts(iso):
    """ISO-8601 (`...Z` or offset) -> aware UTC datetime. Naive input is refused, never assumed UTC."""
    d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError(f"naive timestamp {iso!r}: refusing to assume UTC")
    return d.astimezone(datetime.timezone.utc)


def iso(dt):
    return dt.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------------------- Student-t lower bound
def _betacf(a, b, x):
    """Continued fraction for the incomplete beta (modified Lentz; Numerical Recipes `betacf`)."""
    fpmin, eps = 1e-300, 3e-16
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > fpmin else fpmin)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > fpmin else fpmin)
        c = 1.0 + aa / c
        c = c if abs(c) > fpmin else fpmin
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betai(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_upper_tail(t, df):
    """P(T > t) for Student's t with `df` degrees of freedom, t >= 0 -- computed as a tail (not 1 - cdf), so a
    tail of 5e-4 (N = 205) keeps full precision."""
    x = df / (df + t * t)
    return 0.5 * _betai(df / 2.0, 0.5, x)


def t_quantile(confidence, df):
    """The t with P(T <= t) = `confidence` (one-sided, confidence in (0.5, 1))."""
    if not 0.5 < confidence < 1.0:
        raise ValueError(f"confidence {confidence!r} must be in (0.5, 1)")
    if df < 1:
        raise ValueError("df must be >= 1")
    alpha = 1.0 - confidence
    hi = 1.0
    while t_upper_tail(hi, df) > alpha:
        hi *= 2.0
        if hi > 1e12:
            break
    lo = 0.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_upper_tail(mid, df) > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def n_adjusted_confidence(n_comparisons):
    """One-sided confidence 1 - FAMILY_ALPHA/N. Since family A (pre-registration 0.2, 2026-10-02) N is the number of CANDIDATE
    PROCEDURES (cells x methods = 6), giving the floor confidence 1 - 0.10/6 = 0.98333 of every candidate; before it, N counted
    every grid value as well (ICT 87, Wyckoff 48). The function itself is unchanged."""
    if not isinstance(n_comparisons, int) or n_comparisons < 1:
        raise ValueError(f"N must be a positive integer, got {n_comparisons!r}")
    return 1.0 - FAMILY_ALPHA / n_comparisons


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def lower_bound(net_rs, confidence):
    """One-sided lower confidence bound of the mean net R: mean - t_{confidence, n-1} * s / sqrt(n).

    Returns a dict (value None when n < 2 -- a bound of one number does not exist; never a guessed number).
    INTERPRETATION: Student-t, sample sd. A zero-variance sample returns its mean. R multiples are skewed, so the
    t bound is backed by the single-trade cap (MAX_TRADE_SHARE) and the perturbation check, not trusted alone.
    """
    n = len(net_rs)
    out = {"n": n, "confidence": confidence, "method": "one-sided Student-t bound on the mean net R",
           "value": None, "mean": None, "sd": None, "t": None, "se": None, "df": None}
    if n < 2:
        return out
    m = sum(net_rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in net_rs) / (n - 1))
    t = t_quantile(confidence, n - 1)
    out.update(mean=m, sd=sd, t=t, se=sd / math.sqrt(n), df=n - 1, value=m - t * sd / math.sqrt(n))
    return out


def _block_bound(trades, confidence, key_fn):
    """Cluster-robust (CR1) one-sided bound on the mean net R (fix round 1, C1). Trades sharing a block are
    dependent (same-day correlated entries, regime persistence), so the iid standard error understates the
    truth. With blocks g of sums S_g = sum_{i in g}(r_i - mean): se = sqrt(G/(G-1) * sum_g S_g^2) / n, bound =
    mean - t_{confidence, G-1} * se. G < 2 blocks -> no bound (value None), never a guess."""
    n = len(trades)
    out = {"blocks": None, "value": None, "se": None, "t": None, "df": None}
    if n < 2:
        return out
    m = sum(t["net_R"] for t in trades) / n
    sums = {}
    for t in trades:
        k = key_fn(t)
        sums[k] = sums.get(k, 0.0) + (t["net_R"] - m)
    g = len(sums)
    out["blocks"] = g
    if g < 2:
        return out
    se = math.sqrt(g / (g - 1.0) * sum(v * v for v in sums.values())) / n
    tq = t_quantile(confidence, g - 1)
    out.update(se=se, t=tq, df=g - 1, value=m - tq * se)
    return out


def _date_key(t):
    return ts(t["entry_time"]).date()


def _window_key(t):
    return int(ts(t["entry_time"]).timestamp() // (BLOCK_DAYS * 86400))


def _quarter_key(t):
    d = ts(t["entry_time"])
    return (d.year, (d.month - 1) // 3)


def _half_key(t):
    d = ts(t["entry_time"])
    return (d.year, (d.month - 1) // 6)


#: The five components of the PRIMARY bound, in the order the record lists them (pre-registration A2).
PRIMARY_COMPONENTS = ("iid", "date", "30d", "quarter", "half")


def one_sided_p(mean_, se, df):
    """One-sided p of H0 'mean <= 0' for a statistic t = mean / se on `df` degrees of freedom: P(T_df >= t). None when the
    statistic is not computable (fail closed: the caller treats None as p = 1). A zero standard error is a degenerate
    sample: p = 0 for a positive mean, 1 otherwise -- the same outcome as the bound mean - t * 0 > 0."""
    if mean_ is None or se is None or df is None:
        return None
    if se == 0:
        return 0.0 if mean_ > 0 else 1.0
    t = mean_ / se
    return t_upper_tail(t, df) if t >= 0 else 1.0 - t_upper_tail(-t, df)


def robust_lower_bound(trades, confidence):
    """bound = min(iid Student-t bound, block bounds by UTC entry date, 30-day window, calendar quarter and
    half-year), all at the same confidence (fix rounds 1-2, C1). The min can only LOWER the bound relative to the iid one -- it never
    loosens. Any component that cannot be computed makes the bound None (fail closed).

    Family A (2026-10-02): the SAME five statistics also give the candidate's p-values (`p_values`, one-sided, each on its
    own df); `p_robust` = the MAX of the five (None when any is not computable). bound > 0 at confidence c  <=>  p_robust < 1 - c.
    `components` carries mean / se / df / blocks per component, so the report can derive the minimum detectable edge and the
    upper bound without recomputing anything."""
    rs = [t["net_R"] for t in trades]
    iid = lower_bound(rs, confidence)
    by_date = _block_bound(trades, confidence, _date_key)
    by_window = _block_bound(trades, confidence, _window_key)
    by_quarter = _block_bound(trades, confidence, _quarter_key)
    by_half = _block_bound(trades, confidence, _half_key)
    parts = dict(zip(PRIMARY_COMPONENTS, (iid, by_date, by_window, by_quarter, by_half)))
    comps = [iid["value"], by_date["value"], by_window["value"], by_quarter["value"], by_half["value"]]
    value = None if any(c is None for c in comps) else min(comps)
    m = iid["mean"]
    pvals = {k: one_sided_p(m, v.get("se"), v.get("df")) for k, v in parts.items()}
    p_robust = None if any(v is None for v in pvals.values()) else max(pvals.values())
    components = {k: {"value": v["value"], "se": v.get("se"), "df": v.get("df"),
                      "blocks": v.get("blocks", v.get("n"))} for k, v in parts.items()}
    return {"n": len(rs), "confidence": confidence, "value": value, "mean": m,
            "method": ("min(iid one-sided Student-t bound, cluster-robust CR1 bound by UTC entry date, "
                       f"cluster-robust CR1 bound by {BLOCK_DAYS}-day window, by calendar quarter, by half-year)"),
            "iid": iid["value"], "block_date": by_date["value"], "block_30d": by_window["value"],
            "block_quarter": by_quarter["value"], "block_half": by_half["value"],
            "blocks_date": by_date["blocks"], "blocks_30d": by_window["blocks"],
            "blocks_quarter": by_quarter["blocks"], "blocks_half": by_half["blocks"],
            "components": components, "p_values": pvals, "p_robust": p_robust}


def edge_interval(mean_, se, df, confidence, power=MDE_POWER):
    """Section C items 1-2 for ONE bound's block structure: the one-sided lower and upper bounds (mean -/+ t_crit * se, t_crit
    at `confidence` on `df`) and the minimum detectable edge (t_crit + t_{power,df}) * se -- the true mean R per trade at which
    that bound would clear 0 with probability `power`. None when the bound's se / df do not exist."""
    if mean_ is None or se is None or df is None or df < 1:
        return None
    tc, tp = t_quantile(confidence, df), t_quantile(power, df)
    return {"se": se, "df": df, "t_crit": tc, "t_power": tp, "lower": mean_ - tc * se, "upper": mean_ + tc * se,
            "mde": (tc + tp) * se, "power": power, "confidence": confidence}


def primary_summary(trades, confidence):
    """The per-candidate PRIMARY record of family A: the five bounds, the five p-values, `p_robust` (their max), the
    floor-confidence verdict, and the edge intervals of the BINDING half-year CR1 bound (and of the numerically smallest
    bound when that is another one)."""
    lb = robust_lower_bound(trades, confidence)
    comps = lb["components"]
    smallest = None
    if lb["value"] is not None:
        smallest = min(PRIMARY_COMPONENTS, key=lambda k: comps[k]["value"])
    half = edge_interval(lb["mean"], comps["half"]["se"], comps["half"]["df"], confidence)
    other = None
    if smallest is not None and smallest != "half":
        other = edge_interval(lb["mean"], comps[smallest]["se"], comps[smallest]["df"], confidence)
    return {"confidence": confidence, "n": lb["n"], "mean": lb["mean"], "primary_bound": lb["value"],
            "floor_ok": lb["value"] is not None and lb["value"] > 0,
            "components": comps, "p_values": lb["p_values"], "p_robust": lb["p_robust"],
            "numerically_smallest": smallest, "binding_half_year": half,
            "smallest_bound_interval": ({"component": smallest, **other} if other else None),
            "definition": FAMILY_DEFINITION}


def holm_stepdown(p_by_id, family_size=None, alpha=FAMILY_ALPHA):
    """Holm's step-down at FWER `alpha` over a family of `family_size` hypotheses (default: the entries given). `p_by_id` maps a
    candidate id to its p (None = not computable / NOT RUN / insufficient -> p = 1, never rejected, but it STILL counts in the
    family). Sorted ascending (ties by id), the k-th smallest is rejected iff p_(k) <= alpha / (family_size - k + 1) and every
    smaller p was rejected; the first failure stops the procedure. Fewer entries than `family_size` means the missing ones
    are implicit p = 1 members (they rank last and are never rejected).

    Returns [{"id","p","rank","threshold","reject"}] in rank order. NOTE (stated in the report as well): rank 1's threshold
    equals the FLOOR (alpha / family_size), and every later rank's threshold is looser, so Holm can reject a candidate that
    FAILS the floor when an earlier candidate was rejected. This harness does NOT let that make a PASS (the verdict rests on the
    floor test, `VERDICT_PRECEDENCE`); a floor PASS is always Holm-rejected, because its p is below every threshold."""
    m = family_size if family_size is not None else len(p_by_id)
    if len(p_by_id) > m:
        raise ValueError(f"{len(p_by_id)} candidates given for a family of {m}")
    rows = sorted(((1.0 if p is None else float(p), cid) for cid, p in p_by_id.items()))
    out, alive = [], True
    for k, (p, cid) in enumerate(rows, start=1):
        thr = alpha / (m - k + 1)
        rej = alive and p <= thr
        alive = rej
        out.append({"id": cid, "p": None if p_by_id[cid] is None else p, "rank": k, "threshold": thr, "reject": rej})
    return out


# --------------------------------------------------------------------------------------------- the grid
class GridError(ValueError):
    """The V grid file is not in the declared shape."""


class Grid:
    """docs/architecture/v-grid-<method>.json: {"method":..., "items":[{"id","key","existing_opts_key",
    "values":[baseline,...],"joint_group","source","implemented"}]}. Items sharing a `joint_group` form ONE
    factor whose candidate set is the cartesian product of their value lists (the ICT grid's B-EXIT is ONE factor of 12 value
    sets: target x time stop, the `no_floor` sets removed 2026-09-30; see v-grid-ict.json `n_formula`)."""

    def __init__(self, data):
        if not isinstance(data, dict) or not data.get("method") or not isinstance(data.get("items"), list) \
                or not data["items"]:
            raise GridError("grid needs a `method` and a non-empty `items` list")
        self.method = str(data["method"])
        self.items = []
        seen = set()
        for it in data["items"]:
            for k in ("id", "key", "values"):
                if k not in it:
                    raise GridError(f"grid item {it!r} has no {k!r}")
            if it["id"] in seen:
                raise GridError(f"duplicate grid item id {it['id']!r}")
            seen.add(it["id"])
            if not isinstance(it["values"], list) or len(it["values"]) < 2:
                raise GridError(f"grid item {it['id']!r}: `values` must list the baseline and >= 1 other value")
            self.items.append(it)
        self.by_id = {it["id"]: it for it in self.items}
        self.groups = self._groups()

    def _groups(self):
        order, members = [], {}
        for it in self.items:
            g = it.get("joint_group") or it["id"]
            if g not in members:
                members[g] = []
                order.append(g)
            members[g].append(it)
        out = []
        for g in order:
            its = members[g]
            ids = [i["id"] for i in its]
            cands = [dict(zip(ids, combo)) for combo in itertools.product(*[i["values"] for i in its])]
            base = {i["id"]: i["values"][0] for i in its}
            non_base = [c for c in cands if c != base]
            out.append({"group": g, "ids": ids, "baseline": base, "candidates": non_base})
        return out

    def baseline(self):
        return {it["id"]: it["values"][0] for it in self.items}

    def full(self, partial):
        v = self.baseline()
        v.update(partial)
        return v

    def opts_key(self, item_id):
        it = self.by_id[item_id]
        return it.get("existing_opts_key") or it["key"]

    def overlay(self, values_by_id):
        """{OPTS key: value} for a full assignment."""
        return {self.opts_key(i): v for i, v in values_by_id.items()}

    @property
    def unimplemented(self):
        return [it["id"] for it in self.items if it.get("implemented") is False]

    def runnable(self):
        """The grid the engine can actually evaluate: every item minus the declared-but-unimplemented ones. N is
        ALWAYS computed on the FULL grid (n_per_method(self)), so leaving an item out of selection can only make
        the multiple-testing level stricter, never looser."""
        if not self.unimplemented:
            return self
        data = {"method": self.method, "items": [dict(it) for it in self.items if it.get("implemented") is not False]}
        return Grid(data)


def load_grid(path):
    with open(path, encoding="utf-8") as fh:
        return Grid(json.load(fh))


def n_per_method(grid):
    """Plan §3: N per cell = 1 baseline + the non-baseline values + 1 combined candidate (ICT 29, Wyckoff 16: the `n_formula` of each grid file)."""
    return 1 + sum(len(g["candidates"]) for g in grid.groups) + 1


#: Pre-registration A5 (REPLACED 2026-10-02): the ORDINAL components of the grids and their orders, lowest to highest. This
#: constant is the ONLY definition of "one step"; it is pinned through `evaluation_config.perturbation_axes` (a changed order
#: is drift). A grid item NOT listed here is CATEGORICAL: flipped and reported, never gated. `part` is the position of the
#: component inside a composite value ("-2.0|H|floor" splits on "|"; a Wyckoff window pair is a list); None = the whole value.
#: ICT: B-BUF stop buffer 0 < 0.1 ATR < 0.25 ATR; B-EX entry model iofed < ce < fill; B-EXIT target -2.0 < -2.25 < -2.5 and,
#: separately, time stop H < 1.5H < 2H < none; B-LB lookback 8 < 12 < 16 and, separately, expiry K < 2K. Wyckoff: W6 300 < 600;
#: W-TW test window 8 < 12 < 20 and, separately, Phase-B swings 2 < 3; W4a only between the explicit counts 3 and 4 (the
#: v1-typed baseline 2 is not an ordinal step: a fold that chose it is NOT perturbed on W4a, and the report lists those folds).
PERTURBATION_AXES = {
    "B-BUF": [{"component": "stop_buffer", "part": None, "order": ["0", "0.1atr", "0.25atr"]}],
    "B-EX": [{"component": "entry_model", "part": None, "order": ["iofed", "ce", "fill"]}],
    "B-EXIT": [{"component": "target", "part": 0, "order": ["-2.0", "-2.25", "-2.5"]},
               {"component": "time_stop", "part": 1, "order": ["H", "1.5H", "2H", "none"]}],
    "B-LB": [{"component": "lookback", "part": 0, "order": ["8", "12", "16"]},
             {"component": "expiry", "part": 1, "order": ["K", "2K"]}],
    "W6": [{"component": "structure_window", "part": None, "order": [300, 600]}],
    "W-TW": [{"component": "test_window", "part": 0, "order": [8, 12, 20]},
             {"component": "phase_b_swings", "part": 1, "order": [2, 3]}],
    "W4a": [{"component": "linger_closes", "part": None, "order": [3, 4]}],
}


def _split_value(value, part):
    if part is None:
        return value
    if isinstance(value, str):
        return value.split("|")[part]
    return list(value)[part]


def _with_part(value, part, new):
    if part is None:
        return new
    if isinstance(value, str):
        bits = value.split("|")
        bits[part] = str(new)
        return "|".join(bits)
    out = list(value)
    out[part] = new
    return out


def component_neighbours(grid, item_id, comp, current):
    """[(-1|+1, new item value)] -- the value the item takes when ONLY `comp` moves one step on its order, the other components
    staying as in `current`. A side with no neighbour (an edge) is omitted; a `current` whose component is not on the order
    (the v1-typed W4a baseline) has none. The moved value must be one the grid declares: a grid and an axis table that disagree
    fail loud (GridError), never skip silently."""
    order = list(comp["order"])
    cur = _split_value(current, comp["part"])
    if cur not in order:
        return []
    i = order.index(cur)
    out = []
    for direction, j in ((-1, i - 1), (+1, i + 1)):
        if 0 <= j < len(order):
            new = _with_part(current, comp["part"], order[j])
            if new not in grid.by_id[item_id]["values"]:
                raise GridError(f"axis {item_id}.{comp['component']}: the neighbour {new!r} of {current!r} is not a value the "
                                f"grid declares")
            out.append((direction, new))
    return out


# ------------------------------------------------------------------------------ walk-forward geometry
def make_folds(data_start_iso, cutoff_iso=DEV_CUTOFF, test_days=TEST_FOLD_DAYS, min_train_days=MIN_TRAIN_DAYS):
    """Rolling-origin folds ending exactly at the development cutoff, going back in `test_days` steps while the
    training span in front of the fold is >= `min_train_days`. Determined by DATES only -- never by results."""
    start, end = ts(data_start_iso), ts(cutoff_iso)
    step = datetime.timedelta(days=test_days)
    k = int(((end - start) - datetime.timedelta(days=min_train_days)) // step)
    folds = []
    for i in range(max(k, 0)):
        t_end = end - step * (k - 1 - i)
        folds.append({"index": i, "train_start": iso(start), "test_start": iso(t_end - step), "test_end": iso(t_end)})
    return folds


TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "2H": 120, "4H": 240, "1D": 1440}


def bar_delta(tf):
    """One bar of `tf` as a timedelta (fail loud on an unknown timeframe: a purge margin is never guessed)."""
    if tf not in TF_MINUTES:
        raise ValueError(f"unknown timeframe {tf!r}; known: {sorted(TF_MINUTES)}")
    return datetime.timedelta(minutes=TF_MINUTES[tf])


def train_window(trades, fold, margin=datetime.timedelta(0), embargo=datetime.timedelta(0)):
    """Training trades of a fold: entered at/after the data start AND with exit label strictly BEFORE
    `test_start - margin` (purge) AND strictly before `test_start - embargo` (O2, owner-approved 2026-09-30).
    Exit times are bar OPEN labels, so the caller passes one bar of the cell's timeframe as `margin` (fix round
    2): a trade whose last bar closes at/after the test start is not evidence the training side may use.
    `embargo` (a timedelta, computed by the caller from the engine's own P table -- this module stays pure) is
    2 x H bars of the cell's timeframe: 2H is the LARGEST FINITE time stop in the declared V grid, so no
    training trade whose time stop could reach into the test fold is used. LIMIT: a "none" time stop (held until
    the end of history) cannot be embargoed by any finite window; it is covered only by this same 2H. Both
    conditions must hold, i.e. the stricter of the two applies; the default (0) adds nothing to the purge."""
    a, b = ts(fold["train_start"]), ts(fold["test_start"]) - max(margin, embargo)
    return [t for t in trades if ts(t["entry_time"]) >= a and ts(t["exit_time"]) < b]


def test_window(trades, fold):
    a, b = ts(fold["test_start"]), ts(fold["test_end"])
    return [t for t in trades if a <= ts(t["entry_time"]) < b]


class CountingSource:
    """Memoises `trades_for(values)` and COUNTS every distinct evaluation -- plan §1.5: 'every run counted'."""

    def __init__(self, trades_for):
        self._f = trades_for
        self._cache = {}
        self._values = {}

    @staticmethod
    def _key(values):
        return json.dumps(values, sort_keys=True, default=repr)

    def __call__(self, values):
        k = self._key(values)
        if k not in self._cache:
            self._cache[k] = self._f(dict(values))
            self._values[k] = dict(values)
        return self._cache[k]

    def evaluated(self):
        """[(key, values)] of every distinct V assignment scored, in first-use order."""
        return list(self._values.items())

    @property
    def runs(self):
        return len(self._cache)


def _score(trades):
    return (len(trades), mean([t["net_R"] for t in trades]))


def select_values(grid, train_trades_for):
    """Choose V values on ONE fold's TRAINING trades only. `train_trades_for(values)` returns training trades and
    is the ONLY data this function can see. One factor at a time against the baseline (plan §3); a value is
    chosen only if it is ELIGIBLE (>= MIN_TRAIN_TRADES) and its training expectancy STRICTLY beats the
    baseline's; ties keep the baseline. Returns (chosen full assignment, scores list)."""
    base = grid.baseline()
    b_n, b_mean = _score(train_trades_for(base))
    base_score = b_mean if b_mean is not None else -math.inf
    chosen = dict(base)
    scores = [{"factor": "baseline", "values": base, "n_train": b_n, "mean_R": b_mean}]
    for g in grid.groups:
        best, best_score = None, base_score
        for cand in g["candidates"]:
            n, m = _score(train_trades_for(grid.full(cand)))
            scores.append({"factor": g["group"], "values": cand, "n_train": n, "mean_R": m})
            if n >= MIN_TRAIN_TRADES and m is not None and m > best_score:
                best, best_score = cand, m
        if best is not None:
            chosen.update(best)
    return chosen, scores


def nested_walk_forward(grid, trades_for, folds, purge_margin, embargo=datetime.timedelta(0)):
    """For each fold: choose on the training window, score the chosen values on that fold's OWN test window.
    Returns [{"fold", "chosen", "changed", "train_scores", "test_trades"}]. `trades_for(full_values)` may be a
    CountingSource; the selection step sees only `train_window` output."""
    out = []
    for fold in folds:
        chosen, scores = select_values(grid, lambda v, f=fold: train_window(trades_for(grid.full(v)), f, purge_margin, embargo))
        base = grid.baseline()
        out.append({"fold": fold, "chosen": chosen,
                    "changed": sorted(i for i in chosen if chosen[i] != base[i]),
                    "train_scores": scores,
                    "test_trades": test_window(trades_for(chosen), fold)})
    return out


def pooled_test_trades(fold_results):
    return [t for fr in fold_results for t in fr["test_trades"]]


def perturbation_trade_sets(grid, trades_for, fold_results, axes=None):
    """Pre-registration A5: for every ORDINAL component and each direction, in every fold, move the value the fold chose one
    step along its order (the other components -- and every other item -- stay at the fold's chosen values) and pool the
    TEST trades of the moved value sets. An edge has no neighbour that side; a fold whose chosen value is not on the order
    contributes nothing (listed by `perturbation_skips`). Returns [{"item","component","direction","kind","trades","folds"}]."""
    axes = PERTURBATION_AXES if axes is None else axes
    sets = {}
    for fr in fold_results:
        for item_id, cur in fr["chosen"].items():
            for comp in axes.get(item_id, ()):
                for direction, new in component_neighbours(grid, item_id, comp, cur):
                    moved = dict(fr["chosen"])
                    moved[item_id] = new
                    s = sets.setdefault((item_id, comp["component"], direction),
                                        {"item": item_id, "component": comp["component"], "direction": direction,
                                         "kind": "ordinal", "trades": [], "folds": 0})
                    s["trades"].extend(test_window(trades_for(moved), fr["fold"]))
                    s["folds"] += 1
    return [sets[k] for k in sorted(sets)]


def perturbation_skips(grid, fold_results, axes=None):
    """Folds whose chosen value of an ordinal component is not on that component's order (W4a: the v1-typed baseline), so
    nothing was perturbed there. Reported, never silently dropped."""
    axes = PERTURBATION_AXES if axes is None else axes
    out = []
    for fr in fold_results:
        for item_id, cur in fr["chosen"].items():
            for comp in axes.get(item_id, ()):
                if _split_value(cur, comp["part"]) not in list(comp["order"]):
                    out.append({"item": item_id, "component": comp["component"], "test_start": fr["fold"]["test_start"],
                                "chosen": cur, "reason": "the chosen value is not on the component's ordinal order"})
    return out


def categorical_flip_sets(grid, trades_for, fold_results, axes=None):
    """The REPORT-ONLY flips of every categorical item (a grid item not in `axes`): in every fold, the item's chosen value A is
    replaced by each other declared value B, everything else as chosen; the pooled test trades are grouped by (item, A -> B).
    Never gated. Returns [{"item","from","to","kind","trades","folds"}]."""
    axes = PERTURBATION_AXES if axes is None else axes
    sets = {}
    for fr in fold_results:
        for item_id, cur in fr["chosen"].items():
            if item_id in axes:
                continue
            for other in grid.by_id[item_id]["values"]:
                if other == cur:
                    continue
                moved = dict(fr["chosen"])
                moved[item_id] = other
                key = (item_id, json.dumps(cur, default=repr), json.dumps(other, default=repr))
                s = sets.setdefault(key, {"item": item_id, "from": cur, "to": other, "kind": "categorical",
                                          "trades": [], "folds": 0})
                s["trades"].extend(test_window(trades_for(moved), fr["fold"]))
                s["folds"] += 1
    return [sets[k] for k in sorted(sets)]


def component_stability(grid, fold_results, axes=None):
    """Section C item 5: per ORDINAL component of the perturbation orders, the component value each fold chose and how many
    times it changed between consecutive folds (an item's composite value hides which component moved)."""
    axes = PERTURBATION_AXES if axes is None else axes
    out = {}
    for item_id, comps in axes.items():
        if item_id not in grid.by_id:
            continue
        for comp in comps:
            vals = [_split_value(fr["chosen"][item_id], comp["part"]) for fr in fold_results if item_id in fr["chosen"]]
            out[f"{item_id}.{comp['component']}"] = {
                "values_by_fold": vals, "changes": sum(1 for a, b in zip(vals, vals[1:]) if a != b),
                "transitions": max(len(vals) - 1, 0)}
    return out


# ------------------------------------------------------------------------------------------- the checks
def check_fold_sufficiency(fold_results):
    per = [{"test_start": fr["fold"]["test_start"], "test_end": fr["fold"]["test_end"],
            "n_trades": len(fr["test_trades"]), "ok": len(fr["test_trades"]) >= MIN_FOLD_TRADES}
           for fr in fold_results]
    ok = len(per) >= MIN_TEST_FOLDS and all(p["ok"] for p in per)
    return {"ok": ok, "folds": per, "n_folds": len(per), "min_folds": MIN_TEST_FOLDS,
            "min_trades_per_fold": MIN_FOLD_TRADES}


def check_lower_bound(trades, confidence):
    lb = robust_lower_bound(trades, confidence)
    return {"ok": lb["value"] is not None and lb["value"] > 0, "bound": lb}


def per_symbol(trades, symbols):
    """Per-symbol pooled-test expectancy over EVERY symbol in `symbols` -- one with no trades is listed with
    n=0, never omitted."""
    out = {}
    for s in symbols:
        rs = [t["net_R"] for t in trades if t["symbol"] == s]
        out[s] = {"n": len(rs), "mean_R": mean(rs), "sum_R": sum(rs)}
    return out


def check_stability(trades, symbols):
    m = len(symbols)
    ps = per_symbol(trades, symbols)
    need = math.ceil(m * STABILITY_FRACTION[0] / STABILITY_FRACTION[1])
    positive = sum(1 for v in ps.values() if v["mean_R"] is not None and v["mean_R"] > 0)
    total = sum(t["net_R"] for t in trades)
    biggest = max((t["net_R"] for t in trades), default=None)
    share = (biggest / total) if (biggest is not None and total > 0) else None
    return {"symbols_ok": m > 0 and positive >= need, "positive_symbols": positive, "required_symbols": need,
            "m_symbols": m, "per_symbol": ps,
            "share_ok": share is not None and share <= MAX_TRADE_SHARE, "largest_trade_share": share,
            "max_trade_share": MAX_TRADE_SHARE, "total_net_R": total,
            "ok": m > 0 and positive >= need and share is not None and share <= MAX_TRADE_SHARE}


def max_gap_days(trades, window_start_iso, window_end_iso):
    """Longest run of calendar days without a trade ENTRY inside [start, end), edges included."""
    a, b = ts(window_start_iso).date(), ts(window_end_iso).date()
    days = sorted({ts(t["entry_time"]).date() for t in trades})
    if not days:
        return (b - a).days
    gaps = [(days[0] - a).days] + [(y - x).days for x, y in zip(days, days[1:])] + [(b - days[-1]).days]
    return max(gaps)


def check_frequency(fold_results):
    per = []
    for fr in fold_results:
        g = max_gap_days(fr["test_trades"], fr["fold"]["test_start"], fr["fold"]["test_end"])
        per.append({"test_start": fr["fold"]["test_start"], "max_gap_days": g, "ok": g <= MAX_GAP_DAYS})
    share = (sum(1 for p in per if p["ok"]) / len(per)) if per else 0.0
    return {"ok": bool(per) and share >= MIN_FOLD_SHARE_OK, "share_ok_folds": share,
            "required_share": MIN_FOLD_SHARE_OK, "max_gap_days": MAX_GAP_DAYS, "folds": per}


REGIME_MIN_HALF_SHARE = 0.25   # each regime half must hold >= this share of the pooled test trades (tightened 2026-10-02)
REGIME_KEY = "adx14_d1"   # the trade field the regime split reads: the D1 ADX(14) of the last COMPLETED D1 bar (pre-reg 0.7)


def _share_fraction(x):
    """A share as an exact (numerator, denominator) pair, so the 25 % boundary is decided in integers."""
    f = fractions.Fraction(str(x))
    return f.numerator, f.denominator


def check_regime_split(trades):
    """D1 ADX(14) median split of the pooled test trades (`REGIME_SPLIT_DEFINITION`): EACH half must hold at least
    REGIME_MIN_HALF_SHARE (25 %) of the pooled trades (else "regime halves unbalanced") and BOTH halves must have positive net
    expectancy. A trade without a D1 ADX value (no completed D1 bar yet, warm-up, no D1 series) cannot be split and fails
    the check (never dropped from it). The decision-timeframe ADX (`adx14`) plays no part in the verdict."""
    if not trades:
        return {"ok": False, "reason": "no trades"}
    if any(t.get(REGIME_KEY) is None for t in trades):
        return {"ok": False, "reason": "a trade has no D1 ADX(14) value at entry (no completed D1 bar / warm-up); "
                                       "the split is not computable"}
    xs = sorted(t[REGIME_KEY] for t in trades)
    n = len(xs)
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0
    low = [t["net_R"] for t in trades if t[REGIME_KEY] <= med]
    high = [t["net_R"] for t in trades if t[REGIME_KEY] > med]
    lm, hm = mean(low), mean(high)
    # Many trades share one symbol-day D1 ADX, so ties at the median can leave a half tiny ([10, 20, 20, 20, 50]: low 4, high
    # 1). Each half must hold >= REGIME_MIN_HALF_SHARE of the pooled trades (integer arithmetic, no float boundary).
    share_n, share_d = _share_fraction(REGIME_MIN_HALF_SHARE)
    balanced = bool(low) and bool(high) and share_d * min(len(low), len(high)) >= share_n * n
    out = {"ok": balanced and lm > 0 and hm > 0, "median_adx14_d1": med,
           "low": {"n": len(low), "mean_R": lm}, "high": {"n": len(high), "mean_R": hm},
           "min_half_share": REGIME_MIN_HALF_SHARE,
           "smaller_half_share": (min(len(low), len(high)) / n)}
    if not balanced:
        out["reason"] = (f"regime halves unbalanced: low n={len(low)}, high n={len(high)} of {n} pooled test trades; each half "
                         f"must hold at least {REGIME_MIN_HALF_SHARE:.0%} (ties at the median D1 ADX)")
    return out


def check_perturbation(perturbations, confidence, skips=None):
    """Pre-registration A5: every ORDINAL (component, direction) neighbour must have pooled mean net R > 0 AND a primary
    bound > 0 at `confidence` (the floor). `skips` (folds a component could not be perturbed in) are carried for the report."""
    rows = []
    for p in perturbations:
        lb = robust_lower_bound(p["trades"], confidence)
        m = lb["mean"]
        rows.append({"item": p["item"], "component": p.get("component"), "direction": p["direction"],
                     "folds": p.get("folds"), "n": lb["n"], "mean_R": m, "lower_bound": lb["value"],
                     "ok": m is not None and m > 0 and lb["value"] is not None and lb["value"] > 0})
    return {"ok": bool(rows) and all(r["ok"] for r in rows), "n_perturbations": len(rows), "rows": rows,
            "definition": PERTURBATION_DEFINITION, "confidence": confidence, "skipped_folds": list(skips or [])}


def categorical_report(flips, confidence):
    """The categorical flips as report rows (A -> B: pooled mean net R and bound). NEVER gated."""
    rows = []
    for f in flips:
        lb = robust_lower_bound(f["trades"], confidence)
        rows.append({"item": f["item"], "from": f["from"], "to": f["to"], "folds": f["folds"], "n": lb["n"],
                     "mean_R": lb["mean"], "lower_bound": lb["value"]})
    return rows


# ------------------------------------------------------------------------- stress gate and the shifted prop pass
def stress_commission_r(entry, stop):
    """The commission stress margin in R: 0.00003 of notional per round turn -> 0.00003 * entry / |entry - stop|. A stress
    margin, NOT an estimate (the FTMO commission is UNKNOWN). NOT COMPUTABLE (no valid stop distance, a non-finite or
    non-positive price) returns None, never a raise: the stress gate treats a trade whose margin is None as a FAIL (fail
    closed; the zero-risk refusal at admission keeps this unreachable on real data, the guard stays)."""
    try:
        entry, stop = float(entry), float(stop)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(entry) and math.isfinite(stop)) or entry <= 0 or entry == stop:
        return None
    return STRESS_COMMISSION_FRACTION * entry / abs(entry - stop)


def stressed_net_r(gross_r, stress_cost_r, entry, stop):
    """Net R of one admitted trade under stress: gross R - the real round-turn cost re-priced at the p90 spread (both legs,
    swap unchanged; `stress_cost_r` = real_costs.cost_r(..., spread_stat='p90')['total_R']) - the commission margin.
    None when the commission margin is not computable (see `stress_commission_r`)."""
    margin = stress_commission_r(entry, stop)
    if margin is None:
        return None
    return gross_r - stress_cost_r - margin


def check_stress(stressed_trades, confidence):
    """Stress gate (pre-registration A8a): the pooled mean net R of the SAME admitted trades, re-priced under stress, must be
    > 0. The stressed primary bound is REPORTED, never gated. `stressed_trades` None = the engine offered no stress pricing:
    fail closed."""
    if stressed_trades is None:
        return {"ok": False, "reason": "no stress pricing was computed (fail closed)", "definition": STRESS_DEFINITION}
    if not stressed_trades:
        return {"ok": False, "reason": "no trades", "definition": STRESS_DEFINITION}
    if any(t.get("net_R") is None for t in stressed_trades):
        return {"ok": False, "reason": "the stress re-pricing is not computable for at least one admitted trade (no valid "
                                       "stop distance; fail closed)", "definition": STRESS_DEFINITION}
    lb = robust_lower_bound(stressed_trades, confidence)
    m = lb["mean"]
    return {"ok": m is not None and m > 0, "n": len(stressed_trades), "mean_R_stressed": m,
            "stressed_primary_bound": lb["value"], "confidence": confidence,
            "spread_stat": STRESS_SPREAD_STAT, "commission_fraction": STRESS_COMMISSION_FRACTION,
            "definition": STRESS_DEFINITION}


def prop_shift_r(primary):
    """The shift of the shifted prop pass (A8b): pooled mean - primary bound at the floor confidence, in R (>= 0 because the
    primary bound is at most the iid bound, which is below the mean). None when the bound is not computable."""
    if primary is None or primary.get("value") is None or primary.get("mean") is None:
        return None
    return primary["mean"] - primary["value"]


def _prop_row(v):
    """One fund's prop_pass_probability as an explicit status (fix round 1, I6): `unavailable` (with a reason) is
    a DIFFERENT state from a numeric `below_threshold`; both block a PASS. A `low_confidence` estimate (performance
    .py: a small sample makes it WIDE) must ALSO clear the threshold at the MINIMUM of its bootstrap spread --
    stricter only."""
    if isinstance(v, dict):
        value, reason = v.get("value"), v.get("reason")
        low, smin = bool(v.get("low_confidence")), v.get("spread_min")
    else:
        value, reason, low, smin = v, None, False, None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return {"value": None, "status": "unavailable", "ok": False,
                "reason": reason or "prop_pass_probability was not computed or is unavailable"}
    row = {"value": value, "low_confidence": low, "spread_min": smin}
    if value < PASS_PROB_MIN:
        return dict(row, status="below_threshold", ok=False)
    if low and not (isinstance(smin, (int, float)) and smin >= PASS_PROB_MIN):
        return dict(row, status="low_confidence_spread_below_threshold", ok=False)
    return dict(row, status="ok", ok=True)


def check_prop_pass(prop_by_fund):
    """prop_pass_probability >= PASS_PROB_MIN on EVERY fund (see `_prop_row` for the status vocabulary)."""
    rows = {f: _prop_row(v) for f, v in (prop_by_fund or {}).items()}
    return {"ok": bool(rows) and all(r["ok"] for r in rows.values()), "threshold": PASS_PROB_MIN, "funds": rows}


def chosen_value_stability(fold_results):
    """Fix round 1, I3: per item, the value each fold chose and how many times it changed between consecutive
    folds. A PASS certifies a SELECTION PROCEDURE; a procedure whose choice flips every fold is not a
    configuration, and this is where that shows."""
    items = sorted({i for fr in fold_results for i in fr["chosen"]})
    out = {}
    for i in items:
        vals = [fr["chosen"].get(i) for fr in fold_results]
        changes = sum(1 for a, b in zip(vals, vals[1:]) if a != b)
        out[i] = {"values_by_fold": vals, "changes": changes, "transitions": max(len(vals) - 1, 0)}
    return out


def fold_arithmetic(n_folds):
    """Fix round 1, I5: the frequency rule's arithmetic for a cell with `n_folds` folds -- how many folds must
    keep every gap <= MAX_GAP_DAYS, and how many may fail."""
    need = math.ceil(round(n_folds * MIN_FOLD_SHARE_OK, 9)) if n_folds else 0
    return {"n_folds": n_folds, "folds_required_within_gap": need,
            "folds_allowed_to_fail": max(n_folds - need, 0), "max_gap_days": MAX_GAP_DAYS,
            "required_share": MIN_FOLD_SHARE_OK}


def split_by_volume_kind(trades, confidence):
    """Wyckoff results split by `volume_kind` (plan §6 item 4). Informational: it never rescues a failing cell."""
    kinds = sorted({t.get("volume_kind") for t in trades if t.get("volume_kind") is not None})
    if not kinds:
        return None
    out = {}
    for k in kinds:
        sub = [t for t in trades if t.get("volume_kind") == k]
        rs = [t["net_R"] for t in sub]
        out[k] = {"n": len(rs), "mean_R": mean(rs), "lower_bound": robust_lower_bound(sub, confidence)["value"]}
    out["_limitation"] = ("tick volume is a count of price changes at the broker, NOT real traded volume "
                          "(plan §6 item 4); results on it are labelled a limitation, never real volume")
    return out


def verdict_from(checks):
    """The ONE place a verdict is derived, so `report` re-derives it from stored checks instead of trusting a
    stored boolean. A record with no `folds_sufficient` check is treated as NOT sufficient (fail closed, never a KeyError and
    never a PASS)."""
    fs = checks.get("folds_sufficient")
    if not isinstance(fs, dict) or not fs.get("ok"):
        return INSUFFICIENT
    if any(k not in checks for k in REQUIRED_CHECKS):
        return FAIL
    return PASS if all(c["ok"] for c in checks.values()) else FAIL


def check_prop_pass_shifted(prop_by_fund, shift_r):
    """A8b: prop_pass_probability >= PASS_PROB_MIN for every fund with R shifted down by `shift_r` (mean - primary bound at
    the floor confidence). A shift that cannot be computed (no bound) fails closed."""
    if shift_r is None:
        return {"ok": False, "reason": "the primary bound is not computable, so the shift (mean - bound) is undefined "
                                       "(fail closed)", "shift_R": None, "definition": PROP_SHIFT_DEFINITION,
                "threshold": PASS_PROB_MIN, "funds": {}}
    out = check_prop_pass(prop_by_fund)
    out.update(shift_R=shift_r, definition=PROP_SHIFT_DEFINITION)
    return out


def check_min_trading_days(fold_results, required_by_fund):
    """Minimum trading days (owner 2026-10-02): per test fold, the number of distinct UTC ENTRY days among that fold's test
    trades must be >= the largest `min_trading_days` any prop-gate fund declares (`required_by_fund` = {fund: int | None},
    None = the fund declares none and is not checked). `required_by_fund` None / empty / malformed (an unreadable profile) and
    a trade whose entry time cannot be read FAIL CLOSED; so does an empty fold list (nothing proves the days)."""
    base = {"definition": MIN_TRADING_DAYS_DEFINITION}
    if not isinstance(required_by_fund, dict) or not required_by_fund:
        return dict(base, ok=False, reason="the funds' min_trading_days are unreadable (fail closed)", funds={}, folds=[])
    funds = {}
    for f, d in required_by_fund.items():
        if d is not None and (not isinstance(d, int) or isinstance(d, bool) or d < 1):
            return dict(base, ok=False, funds={}, folds=[],
                        reason=f"profile {f!r} min_trading_days is {d!r}: malformed (fail closed)")
        funds[f] = {"required": d, "checked": d is not None}
    need = max((d for d in required_by_fund.values() if d is not None), default=None)
    folds = []
    for fr in fold_results:
        a, b = ts(fr["fold"]["test_start"]), ts(fr["fold"]["test_end"])
        try:
            days = {ts(t["entry_time"]).date() for t in fr["test_trades"] if a <= ts(t["entry_time"]) < b}
        except (KeyError, TypeError, ValueError):
            return dict(base, ok=False, funds=funds, folds=folds, required=need,
                        reason="a test trade's entry time is unreadable (fail closed)")
        folds.append({"test_start": fr["fold"]["test_start"], "entry_days": len(days),
                      "ok": need is None or len(days) >= need})
    for f, row in funds.items():
        row["ok"] = (not row["checked"]) or bool(folds and all(x["entry_days"] >= row["required"] for x in folds))
    fewest = min((x["entry_days"] for x in folds), default=None)
    ok = bool(folds) and all(x["ok"] for x in folds) and all(r["ok"] for r in funds.values())
    return dict(base, ok=ok, funds=funds, folds=folds, required=need, fewest_entry_days=fewest,
                margin=None if need is None or fewest is None else fewest - need)


def _margin(check, measure, measured, threshold, unit, higher_is_better=True):
    if measured is None or threshold is None:
        m = None
    else:
        m = (measured - threshold) if higher_is_better else (threshold - measured)
    return {"check": check, "measure": measure, "measured": measured, "threshold": threshold, "margin": m, "unit": unit,
            "ok": m is not None and m >= 0}


def check_margins(checks):
    """Section C item 3: every check's measured value, its threshold and the distance to it IN THE CHECK'S OWN UNIT (negative
    margin = failing by that much). `ok` of a row is its own measure; a check can have several rows. A measure that cannot be
    computed has margin None and counts as failing."""
    rows = []
    fs = checks.get("folds_sufficient") or {}
    if fs.get("folds") is not None:
        rows.append(_margin("folds_sufficient", "smallest test fold (trades)",
                            min((f["n_trades"] for f in fs["folds"]), default=None), MIN_FOLD_TRADES, "trades"))
        rows.append(_margin("folds_sufficient", "test folds", fs.get("n_folds"), fs.get("min_folds"), "folds"))
    lb = (checks.get("lower_bound_positive") or {}).get("bound") or {}
    rows.append(_margin("lower_bound_positive", "primary bound at the floor confidence", lb.get("value"), 0.0, "R"))
    st = checks.get("stability") or {}
    if st:
        rows.append(_margin("stability", "symbols with positive mean net R", st.get("positive_symbols"),
                            st.get("required_symbols"), "symbols"))
        rows.append(_margin("stability", "largest single trade share of total net R", st.get("largest_trade_share"),
                            st.get("max_trade_share"), "share of total", higher_is_better=False))
    fq = checks.get("frequency") or {}
    if fq:
        rows.append(_margin("frequency", "share of folds with every entry gap <= 30 d", fq.get("share_ok_folds"),
                            fq.get("required_share"), "share of folds"))
    rg = checks.get("regime_split") or {}
    if rg:
        lo, hi = (rg.get("low") or {}).get("mean_R"), (rg.get("high") or {}).get("mean_R")
        rows.append(_margin("regime_split", "smaller of the two D1-ADX half means",
                            None if lo is None or hi is None else min(lo, hi), 0.0, "R"))
        if rg.get("smaller_half_share") is not None:
            rows.append(_margin("regime_split", "smaller half's share of the pooled test trades",
                                rg["smaller_half_share"], rg.get("min_half_share", REGIME_MIN_HALF_SHARE), "share of trades"))
    pt = checks.get("perturbation") or {}
    if pt:
        vals = [v for r in pt.get("rows", []) for v in (r.get("mean_R"), r.get("lower_bound"))]
        rows.append(_margin("perturbation", "worst neighbour (smaller of its mean and its bound)",
                            None if not vals or any(v is None for v in vals) else min(vals), 0.0, "R"))
    sr = checks.get("stress") or {}
    if sr:
        rows.append(_margin("stress", "pooled mean net R under p90 spread + commission margin",
                            sr.get("mean_R_stressed"), 0.0, "R"))
    md = checks.get("min_trading_days") or {}
    if md:
        rows.append(_margin("min_trading_days", "fewest distinct UTC entry days in any test fold",
                            md.get("fewest_entry_days"), md.get("required"), "days"))
    for name in ("prop_pass_probability", "prop_pass_shifted"):
        pp = checks.get(name) or {}
        if pp:
            vs = [r.get("value") for r in (pp.get("funds") or {}).values()]
            rows.append(_margin(name, "lowest prop_pass_probability over the funds",
                                None if not vs or any(v is None for v in vs) else min(vs), PASS_PROB_MIN, "probability"))
    return rows


def evaluate_cell(fold_results, perturbations, symbols, family_size, prop_by_fund, runs=None, *, stress=None,
                  prop_shifted=None, shift_r=None, categorical=None, skips=None, grid=None, axes=None,
                  min_days_required=None):
    """Every rule over one (method, cell). The primary bound uses the POOLED TEST trades only, at the FLOOR confidence
    1 - FAMILY_ALPHA/`family_size` (family A: the number of candidate procedures, not of grid values); the checks are ALL
    computed (never short-circuited) so a failing candidate reports every reason.

    `stress` = the pooled test trades re-priced under stress (None -> the gate fails closed); `prop_shifted` = the per-fund
    prop pass with R shifted down by `shift_r`; `categorical` = `categorical_flip_sets` (reported, never gated); `skips` =
    `perturbation_skips`; `grid`/`axes` (optional) add the per-component stability of the chosen values."""
    conf = n_adjusted_confidence(family_size)
    pooled = pooled_test_trades(fold_results)
    primary = primary_summary(pooled, conf)
    checks = {
        "folds_sufficient": check_fold_sufficiency(fold_results),
        "lower_bound_positive": check_lower_bound(pooled, conf),
        "stability": check_stability(pooled, symbols),
        "frequency": check_frequency(fold_results),
        "regime_split": check_regime_split(pooled),
        "perturbation": check_perturbation(perturbations, conf, skips),
        "prop_pass_probability": check_prop_pass(prop_by_fund),
        "prop_pass_shifted": check_prop_pass_shifted(prop_shifted, shift_r),
        "stress": check_stress(stress, conf),
        "min_trading_days": check_min_trading_days(fold_results, min_days_required),
    }
    verdict = verdict_from(checks)
    return {"verdict": verdict, "family_size": family_size, "confidence": conf, "primary": primary,
            "failed_checks": [k for k, c in checks.items() if not c["ok"]],
            "pooled": {"n_trades": len(pooled), "mean_R": mean([t["net_R"] for t in pooled])},
            "per_symbol": per_symbol(pooled, symbols),
            "by_volume_kind": split_by_volume_kind(pooled, conf),
            "chosen_value_stability": chosen_value_stability(fold_results),
            "component_stability": component_stability(grid, fold_results, axes) if grid is not None else None,
            "categorical_flips": categorical_report(categorical or [], conf),
            "verdict_precedence": VERDICT_PRECEDENCE, "margins": check_margins(checks),
            "folds": [{"test_start": fr["fold"]["test_start"], "test_end": fr["fold"]["test_end"],
                       "n_test_trades": len(fr["test_trades"]), "chosen": fr["chosen"], "changed": fr["changed"],
                       "mean_net_R": mean([t["net_R"] for t in fr["test_trades"]])}
                      for fr in fold_results],
            "checks": checks, "runs_evaluated": runs}


# ------------------------------------------------------------------------------------------------- ADX
def adx14(highs, lows, closes, period=ADX_PERIOD):
    """Wilder's ADX; list parallel to the inputs, None during warm-up (first value at index 2*period-1)."""
    n = len(closes)
    out = [None] * n
    if n < 2 * period:
        return out
    tr, pdm, ndm = [0.0] * n, [0.0] * n, [0.0] * n
    for i in range(1, n):
        up, dn = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        ndm[i] = dn if (dn > up and dn > 0) else 0.0
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    s_tr, s_p, s_n = sum(tr[1:period + 1]), sum(pdm[1:period + 1]), sum(ndm[1:period + 1])
    dx = []

    def _dx():
        if s_tr <= 0:
            return 0.0
        pdi, ndi = 100.0 * s_p / s_tr, 100.0 * s_n / s_tr
        return 0.0 if pdi + ndi == 0 else 100.0 * abs(pdi - ndi) / (pdi + ndi)

    dx.append(_dx())
    for i in range(period + 1, n):
        s_tr = s_tr - s_tr / period + tr[i]
        s_p = s_p - s_p / period + pdm[i]
        s_n = s_n - s_n / period + ndm[i]
        dx.append(_dx())
        if len(dx) == period:
            out[i] = sum(dx) / period
        elif len(dx) > period:
            out[i] = (out[i - 1] * (period - 1) + dx[-1]) / period
    return out


def adx_index(candles):
    """(open-time list, ADX list) for a candle series -- the lookup `adx_before` reads. REPORTING ONLY since 2026-10-02: the
    regime verdict reads the D1 ADX (`d1_adx_index`), never this decision-timeframe value."""
    vals = adx14([c["high"] for c in candles], [c["low"] for c in candles], [c["close"] for c in candles])
    return [ts(c["time"]) for c in candles], vals


def adx_before(index, entry_iso):
    """ADX(14) of the last bar that OPENED strictly before `entry_iso` -- a fully closed bar under either bar
    labelling convention for the decision timeframe, so the value was knowable at the decision (CLAUDE.md §8). None during
    warm-up. REPORTING ONLY (trade field `adx14`); NOT valid for a D1 series, whose last-opened bar is still forming."""
    times, vals = index
    i = bisect.bisect_left(times, ts(entry_iso)) - 1
    return vals[i] if i >= 0 else None


# ---------------------------------------------------------------------------- D1 ADX for the regime split (pre-reg 0.7)
D1_BAR = datetime.timedelta(days=1)


def d1_adx_index(candles):
    """([close time of each D1 bar], [ADX(14) of each D1 bar]) for a D1 series whose `time` is the bar's OPEN label (UTC, the
    repo's convention: the broker's server midnight converted to UTC, so 21:00Z or 22:00Z on the previous calendar day).
    The FTMO server clock follows the `us_dst_dates_fixed_offset` convention declared in docs/architecture/providers.json
    (`mt5_bridge_ftmo`: +02:00 standard / +03:00 on US DST dates; implemented by scripts/mt5_time.py `UsDatesFixedOffsetZone`,
    which `real_costs` and `history_store` use for the conversion). All 27,013 D1 labels of the 9 cell symbols were verified
    to sit at the server midnight under that convention (the 2026-10-02 review's check; the labels are not read from any
    other clock). The CLOSE of a bar = max(open label + 24 h, the next bar's open label): never earlier than the true
    close (a 25 h DST day closes at the next open, a 23 h day is read one hour late, a weekend or holiday gap only matters at
    hours the market is shut). Wilder's ADX of bar i uses bars <= i only, so the value is point-in-time."""
    vals = adx14([c["high"] for c in candles], [c["low"] for c in candles], [c["close"] for c in candles])
    opens = [ts(c["time"]) for c in candles]
    closes = [max(o + D1_BAR, opens[i + 1]) if i + 1 < len(opens) else o + D1_BAR for i, o in enumerate(opens)]
    return closes, vals


def d1_adx_at(index, entry_iso):
    """The D1 ADX(14) of the last D1 bar whose CLOSE is at or before `entry_iso`; the entry day's own forming bar is never
    read. None while no bar has closed yet or during the ADX warm-up."""
    closes, vals = index
    i = bisect.bisect_right(closes, ts(entry_iso)) - 1
    return vals[i] if i >= 0 else None
