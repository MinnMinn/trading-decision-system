"""The statistics of the fund search -- docs/plans/2026-09-28-methodology-improvement-plan.md §1.4, restated as
PURE functions (no I/O, no engine, no clock) so every rule is unit-testable on synthetic trades and can never
be quietly loosened by the orchestrator (scripts/fund-search.py) that calls them.

Every threshold below is a named constant with its source. "Tighten later" is allowed; loosening is not
(plan §6 item 2): a change to any constant here is a research-integrity event, not a tuning knob.

A TRADE is a dict with at least `entry_time`, `exit_time` (ISO-8601 `...Z`), `net_R` (net of REAL costs), and
`symbol`. Optional: `adx14` (ADX(14) known BEFORE the entry, for the regime split), `volume_kind`.

WHAT IS COMPUTED, in the order the plan states it (§1.4):

1. NESTED rolling-origin walk-forward (`make_folds`, `nested_walk_forward`). Inside each fold the V values are
   chosen on TRAINING trades only (`train_window`: entered at the data start, and EXITED strictly before the
   test fold starts -- a purge, so a trade still open when the test fold begins cannot leak its outcome into
   selection). The chosen values are then scored on that fold's own TEST trades. The lower bound is taken on
   the POOLED test trades of all folds and nothing else.
2. A test fold with fewer than MIN_FOLD_TRADES trades makes the cell verdict "insufficient".
3. The lower bound is one-sided at confidence 1 - FAMILY_ALPHA/N (`n_adjusted_confidence`), N counting EVERY
   comparison that could be put forward (`n_per_method` x cells; the grid is read, never typed here).
4. Stability: net expectancy > 0 on >= ceil(2m/3) of the m symbols, and no single trade above MAX_TRADE_SHARE
   of total net R.
5. Frequency: longest trade-to-trade gap on the pooled account <= MAX_GAP_DAYS in >= MIN_FOLD_SHARE_OK of folds.
6. §45 checks: ADX(14) median regime split, +/- one grid step perturbation, prop_pass_probability.
7. Everything is reported per symbol (and per `volume_kind` when trades carry one).

INTERPRETATION CHOICES the plan leaves open (each stated where it is used, and returned to the owner):
  * the bound is a one-sided Student-t bound on the mean (`lower_bound`), not a bootstrap: at a tail of
    0.10/205 a percentile bootstrap needs tens of thousands of resamples to resolve its own quantile;
  * TEST_FOLD_DAYS / MIN_TRAIN_DAYS / MIN_TEST_FOLDS / MIN_TRAIN_TRADES (fold geometry and a training floor);
  * the frequency gap includes the fold's edges (stricter than gaps between trades only);
  * the regime split requires BOTH halves > 0 (stricter than "same sign");
  * a symbol with development data but no test trades counts as NOT positive (never dropped).
"""
import bisect
import datetime
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

#: `verdict_from`'s rule, stated so it can be pre-registered and recorded in the ledger declaration (I4).
VERDICT_PRECEDENCE = ("insufficient (any test fold < MIN_FOLD_TRADES, or fewer than MIN_TEST_FOLDS folds) "
                      "overrides everything; otherwise pass only if EVERY check is ok, else fail")

#: The regime split's pre-registered definition (fix round 1, S6): stated in the report and the draft.
REGIME_SPLIT_DEFINITION = ("ADX(14) (Wilder) of the last bar that opened strictly before the entry; split at the "
                           "MEDIAN of the pooled TEST trades' ADX values (<= median = low half, > median = high "
                           "half); BOTH halves must have positive mean net R")


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
    """Plan §1.4: one-sided confidence 1 - 0.10/N. N is EVERY comparison that could be put forward."""
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
           "value": None, "mean": None, "sd": None, "t": None}
    if n < 2:
        return out
    m = sum(net_rs) / n
    sd = math.sqrt(sum((r - m) ** 2 for r in net_rs) / (n - 1))
    t = t_quantile(confidence, n - 1)
    out.update(mean=m, sd=sd, t=t, value=m - t * sd / math.sqrt(n))
    return out


def _block_bound(trades, confidence, key_fn):
    """Cluster-robust (CR1) one-sided bound on the mean net R (fix round 1, C1). Trades sharing a block are
    dependent (same-day correlated entries, regime persistence), so the iid standard error understates the
    truth. With blocks g of sums S_g = sum_{i in g}(r_i - mean): se = sqrt(G/(G-1) * sum_g S_g^2) / n, bound =
    mean - t_{confidence, G-1} * se. G < 2 blocks -> no bound (value None), never a guess."""
    n = len(trades)
    out = {"blocks": None, "value": None, "se": None, "t": None}
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
    out.update(se=se, t=tq, value=m - tq * se)
    return out


def _date_key(t):
    return ts(t["entry_time"]).date()


def _window_key(t):
    return int(ts(t["entry_time"]).timestamp() // (BLOCK_DAYS * 86400))


def robust_lower_bound(trades, confidence):
    """bound = min(iid Student-t bound, block bound by UTC entry date, block bound by 30-day window), all at the
    same confidence (fix round 1, C1). The min can only LOWER the bound relative to the iid one -- it never
    loosens. Any component that cannot be computed makes the bound None (fail closed)."""
    rs = [t["net_R"] for t in trades]
    iid = lower_bound(rs, confidence)
    by_date = _block_bound(trades, confidence, _date_key)
    by_window = _block_bound(trades, confidence, _window_key)
    comps = [iid["value"], by_date["value"], by_window["value"]]
    value = None if any(c is None for c in comps) else min(comps)
    return {"n": len(rs), "confidence": confidence, "value": value, "mean": iid["mean"],
            "method": ("min(iid one-sided Student-t bound, cluster-robust CR1 bound by UTC entry date, "
                       f"cluster-robust CR1 bound by {BLOCK_DAYS}-day window)"),
            "iid": iid["value"], "block_date": by_date["value"], "block_30d": by_window["value"],
            "blocks_date": by_date["blocks"], "blocks_30d": by_window["blocks"]}


# --------------------------------------------------------------------------------------------- the grid
class GridError(ValueError):
    """The V grid file is not in the declared shape."""


class Grid:
    """docs/architecture/v-grid-<method>.json: {"method":..., "items":[{"id","key","existing_opts_key",
    "values":[baseline,...],"joint_group","source","implemented"}]}. Items sharing a `joint_group` form ONE
    factor whose candidate set is the cartesian product of their value lists (plan §3: B-EXIT = 3 x 4 x 2 = 24)."""

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


def load_grid(path):
    with open(path, encoding="utf-8") as fh:
        return Grid(json.load(fh))


def n_per_method(grid):
    """Plan §3: N per cell = 1 baseline + the non-baseline values + 1 combined candidate (ICT 41, Wyckoff 16)."""
    return 1 + sum(len(g["candidates"]) for g in grid.groups) + 1


def value_axis(values):
    """The ordered 'grid steps' of one item: numeric values ascending; anything else in listed order."""
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return sorted(set(values))
    return list(values)


def neighbours(values, current):
    """[(-1|+1, value)] one grid step either side of `current` on the item's axis (missing edge omitted)."""
    axis = value_axis(values)
    if current not in axis:
        raise GridError(f"value {current!r} is not on the axis {axis!r}")
    i = axis.index(current)
    out = []
    if i > 0:
        out.append((-1, axis[i - 1]))
    if i < len(axis) - 1:
        out.append((+1, axis[i + 1]))
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


def train_window(trades, fold):
    """Training trades of a fold: entered at/after the data start AND exited strictly BEFORE the test fold starts
    (purge). A trade the test fold could still change is not evidence the training side may use."""
    a, b = ts(fold["train_start"]), ts(fold["test_start"])
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


def nested_walk_forward(grid, trades_for, folds):
    """For each fold: choose on the training window, score the chosen values on that fold's OWN test window.
    Returns [{"fold", "chosen", "changed", "train_scores", "test_trades"}]. `trades_for(full_values)` may be a
    CountingSource; the selection step sees only `train_window` output."""
    out = []
    for fold in folds:
        chosen, scores = select_values(grid, lambda v, f=fold: train_window(trades_for(grid.full(v)), f))
        base = grid.baseline()
        out.append({"fold": fold, "chosen": chosen,
                    "changed": sorted(i for i in chosen if chosen[i] != base[i]),
                    "train_scores": scores,
                    "test_trades": test_window(trades_for(chosen), fold)})
    return out


def pooled_test_trades(fold_results):
    return [t for fr in fold_results for t in fr["test_trades"]]


def perturbation_trade_sets(grid, trades_for, fold_results):
    """Plan §1.4 §45: every chosen V value moved +/- one grid step. Each (item, direction) yields the POOLED
    test trades when, in every fold, that one item is moved from the value the fold chose. An item at its axis
    edge has no neighbour that side (nothing to move). Returns [{"item","direction","value_by_fold","trades"}]."""
    sets = {}
    for fr in fold_results:
        for item_id, cur in fr["chosen"].items():
            for direction, new in neighbours(grid.by_id[item_id]["values"], cur):
                moved = dict(fr["chosen"])
                moved[item_id] = new
                s = sets.setdefault((item_id, direction), {"item": item_id, "direction": direction,
                                                           "trades": [], "folds": 0})
                s["trades"].extend(test_window(trades_for(moved), fr["fold"]))
                s["folds"] += 1
    return [sets[k] for k in sorted(sets)]


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


def check_regime_split(trades):
    """ADX(14) median split of the pooled test trades: BOTH halves must have positive net expectancy. A trade
    without an ADX value cannot be split and fails the check (never dropped from it)."""
    if not trades:
        return {"ok": False, "reason": "no trades"}
    if any(t.get("adx14") is None for t in trades):
        return {"ok": False, "reason": "a trade has no ADX(14) value at entry (warm-up); the split is not computable"}
    xs = sorted(t["adx14"] for t in trades)
    n = len(xs)
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0
    low = [t["net_R"] for t in trades if t["adx14"] <= med]
    high = [t["net_R"] for t in trades if t["adx14"] > med]
    lm, hm = mean(low), mean(high)
    return {"ok": bool(low) and bool(high) and lm > 0 and hm > 0, "median_adx14": med,
            "low": {"n": len(low), "mean_R": lm}, "high": {"n": len(high), "mean_R": hm}}


def check_perturbation(perturbations, confidence):
    rows = []
    for p in perturbations:
        lb = robust_lower_bound(p["trades"], confidence)
        rows.append({"item": p["item"], "direction": p["direction"], "n": lb["n"], "lower_bound": lb["value"],
                     "ok": lb["value"] is not None and lb["value"] > 0})
    return {"ok": bool(rows) and all(r["ok"] for r in rows), "n_perturbations": len(rows), "rows": rows}


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
    stored boolean."""
    if not checks["folds_sufficient"]["ok"]:
        return INSUFFICIENT
    return PASS if all(c["ok"] for c in checks.values()) else FAIL


def evaluate_cell(fold_results, perturbations, symbols, n_comparisons, prop_by_fund, runs=None):
    """Every §1.4 rule over one (method, cell). The lower bound uses the POOLED TEST trades only; the checks
    are ALL computed (never short-circuited) so a failing candidate reports every reason."""
    conf = n_adjusted_confidence(n_comparisons)
    pooled = pooled_test_trades(fold_results)
    checks = {
        "folds_sufficient": check_fold_sufficiency(fold_results),
        "lower_bound_positive": check_lower_bound(pooled, conf),
        "stability": check_stability(pooled, symbols),
        "frequency": check_frequency(fold_results),
        "regime_split": check_regime_split(pooled),
        "perturbation": check_perturbation(perturbations, conf),
        "prop_pass_probability": check_prop_pass(prop_by_fund),
    }
    verdict = verdict_from(checks)
    return {"verdict": verdict, "n_comparisons": n_comparisons, "confidence": conf,
            "failed_checks": [k for k, c in checks.items() if not c["ok"]],
            "pooled": {"n_trades": len(pooled), "mean_R": mean([t["net_R"] for t in pooled])},
            "per_symbol": per_symbol(pooled, symbols),
            "by_volume_kind": split_by_volume_kind(pooled, conf),
            "chosen_value_stability": chosen_value_stability(fold_results),
            "verdict_precedence": VERDICT_PRECEDENCE,
            "folds": [{"test_start": fr["fold"]["test_start"], "test_end": fr["fold"]["test_end"],
                       "n_test_trades": len(fr["test_trades"]), "chosen": fr["chosen"], "changed": fr["changed"]}
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
    """(open-time list, ADX list) for a candle series -- the lookup `adx_before` reads."""
    vals = adx14([c["high"] for c in candles], [c["low"] for c in candles], [c["close"] for c in candles])
    return [ts(c["time"]) for c in candles], vals


def adx_before(index, entry_iso):
    """ADX(14) of the last bar that OPENED strictly before `entry_iso` -- a fully closed bar under either bar
    labelling convention, so the value was knowable at the decision (CLAUDE.md §8). None during warm-up."""
    times, vals = index
    i = bisect.bisect_left(times, ts(entry_iso)) - 1
    return vals[i] if i >= 0 else None
