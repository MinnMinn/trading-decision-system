#!/usr/bin/env python3
"""Evaluator of experiment IC, "can Claude trade ICT discretionarily with an edge?"
(docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md §4-§6; implementation note
docs/plans/2026-10-04-claude-ict-implementation.md). RESEARCH ONLY: no account, no order path.

    python3 scripts/research/claude_ict_eval.py evaluate        # once, after decisions.jsonl is committed and complete
    python3 scripts/research/claude_ict_eval.py feasibility     # arms M / T intents BEFORE the window, no outcome
    python3 scripts/research/claude_ict_eval.py calibrate       # test sizes under random directions, BEFORE the window

`evaluate` refuses unless the pre-registration, the manifest, every prompt, decisions.jsonl, the shared module and this
file are committed and unchanged, every manifest decision point has exactly one stored decision, the run's last event is
`stop / complete`, this file's committed blob is the one the run recorded at its start (the evaluator was frozen before
the first decision), every committed version of decisions.jsonl is a prefix of the final one and its shadow (when on this
machine) holds nothing else, every repository Python file it executes is committed, and the result file does not exist
and was never committed. It writes docs/experiments/claude-ict/evaluation.json once.

§4 simulator (identical for every arm; BID bars + the order's snapshot spread, ASK = BID + spread):
  * placement at the order's instant, against the first 5m bar at / after it: a pending order on the wrong side of the
    market (buy limit not below the ASK, sell limit not above the BID, buy stop not above the ASK, sell stop not below the
    BID) is REJECTED, as MT5 rejects it; a market order fills at that bar's open (ASK long / BID short) and is rejected
    when that price is already beyond its stop or target;
  * buy limit fills when ASK <= entry, sell limit when BID >= entry, at the entry (never improved); buy stop when
    ASK >= entry, sell stop when BID <= entry, at the first trade through (the open on a gap); no fill at / after the
    16:00 New York time exit of the bar's server day; an unfilled order expires at its valid_until (killzone end for C);
  * stop and target rest; a LONG exits at the BID, a SHORT at the ASK; stop and target in one bar = stop first; a bar
    opening beyond the stop exits at that open; on the bar a pending order fills inside of, the extreme price travelled
    to after the fill is known to follow it and the other extreme may come before or after it: resolved against the
    trade, the stop is checked on the whole bar and the target only on the extreme known to follow the fill;
  * time exit 16:00 New York of the fill's FTMO server day (close of the last bar before it), so flat before the
    17:00 New York rollover; R = net P&L / (|entry - stop| + spread), entry = a limit / stop order's price or a market
    order's fill; commission real_costs' recorded 0, no swap.
"""
import argparse
import bisect
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "research"))
import claude_ict_common as K  # noqa: E402

TD = datetime.timedelta
MIN_FILLED = 60                      # §6 minimum sample (filled trades of arm C)
ALPHA = 0.05                         # §6 one-sided
N_PERM = 2000                        # §5 R-control permutations
N_BOOT = 10000                       # §6 bootstrap of C's mean net R (95 % lower bound reported)
SAMPLE_N = 10                        # §6 seeded sample of decisions
SEEDS = {"permutation": "IC|R-control|shuffle|v1", "signflip": "IC|R-control|signflip|v1",
         "global": "IC|R-control|global-shuffle|v1", "killzone": "IC|R-control|killzone-shuffle|v1",
         "mirror": "IC|mirror-control|v1",
         "bootstrap": "IC|C-mean-R|bootstrap|v1", "sample": "IC|sample-10|v1"}
KEYS = ("decision", "order", "entry", "stop", "target", "valid_until", "htf_bias", "draw_on_liquidity", "pd_array",
        "invalidation", "reasoning")
DECISION_VALUES = ("NO_TRADE", "LONG", "SHORT")
ORDER_VALUES = ("limit", "stop", "market")
BIAS_VALUES = ("bullish", "bearish", "neutral")
MAX_REASONING_WORDS = 120
MIN_REWARD_RISK = 1.0
#: The mirror-order control (implementation note §4 item 21b) is a fourth PASS condition: amendment 1 of the
#: pre-registration (docs/plans/2026-10-05-claude-ict-amendment-1.md), decided 2026-10-05 BEFORE any decision, with the
#: reviewing session's agreement. The §6 primary test is unchanged and is reported with the mirror p-value either way.
MIRROR_CONTROL_GATES = True
# Arm M: the repo ICT engine (scripts/backtest-methods.py ict_setups_live) at the pilot's 15m settings --
# docs/architecture/pilot-selection.json cfd-scalping-ict-15m-range-a = scripts/stability-report.py CONFIGS["A"]
# (no management, no HTF filter), ict_target "range"; B and C manage the stop (breakeven) and are not fixed-exit orders.
M_TF, M_CONFIG, M_TARGET, M_METHODS = "15m", "A", "range", ("ict",)
M_LEAD_BARS = 576 + 288              # the 15m scan window (automation SCAN_WINDOW) + three days for the first-seen rule
# Arm T: the demo book (docs/architecture/trading-systems.json fvg-book), XAUUSD H7 + G9, report-only.
T_SYMBOL = "XAUUSD"
T_VERSIONS = {"v3": {"stop_k": 2.0, "tp_stop_multiple": 5, "close_before_rollover_minutes": 10},
              "v4": {"stop_k": 1.4, "tp_stop_multiple": 7, "close_before_rollover_minutes": 10}}


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rng_for(tag):
    """A seeded generator used through random() only (the one method whose sequence Python guarantees per seed)."""
    return random.Random(int.from_bytes(hashlib.sha256(tag.encode()).digest()[:8], "big"))


def shuffle(rng, xs):
    xs = list(xs)
    for i in range(len(xs) - 1, 0, -1):
        j = int(rng.random() * (i + 1))
        xs[i], xs[j] = xs[j], xs[i]
    return xs


# ------------------------------------------------------------------------------------------------ the answer
def _price(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0


def validate(obj):
    """(decision, None) for an answer object that meets pre-registration §3 exactly, else (None, reason). Exactly the
    eleven keys; NO_TRADE carries null order / entry / stop / target; LONG stop < entry < target, SHORT target < entry <
    stop; reward/risk >= 1.0; valid_until "killzone_end"; reasoning <= 120 words; no other key (so no confidence)."""
    if not isinstance(obj, dict):
        return None, "not_an_object"
    missing = [k for k in KEYS if k not in obj]
    if missing:
        return None, "missing_keys:" + ",".join(missing)
    extra = sorted(set(obj) - set(KEYS))
    if extra:
        return None, "extra_keys:" + ",".join(map(str, extra))
    d = obj["decision"]
    if d not in DECISION_VALUES:
        return None, "decision_value"
    if obj["valid_until"] != "killzone_end":
        return None, "valid_until"
    if obj["htf_bias"] not in BIAS_VALUES:
        return None, "htf_bias_value"
    for k in ("draw_on_liquidity", "pd_array", "invalidation", "reasoning"):
        if not isinstance(obj[k], str) or not obj[k].strip():
            return None, f"empty_{k}"
    if len(obj["reasoning"].split()) > MAX_REASONING_WORDS:
        return None, "reasoning_over_120_words"
    out = {k: obj[k] for k in KEYS}
    if d == "NO_TRADE":
        if any(obj[k] is not None for k in ("order", "entry", "stop", "target")):
            return None, "no_trade_with_order_fields"
        return out, None
    if obj["order"] not in ORDER_VALUES:
        return None, "order_value"
    e, s, t = obj["entry"], obj["stop"], obj["target"]
    if not all(_price(x) for x in (e, s, t)):
        return None, "price_not_a_positive_number"
    if d == "LONG" and not s < e < t:
        return None, "long_sides"
    if d == "SHORT" and not t < e < s:
        return None, "short_sides"
    if abs(t - e) / abs(e - s) < MIN_REWARD_RISK - 1e-9:
        return None, "reward_risk_below_1"
    return out, None


def judge(record):
    """(decision or None, error or None, how) for one stored final decision record."""
    if record.get("status") != "answered":
        return None, "technical_failure", None
    obj, how = K.extract_answer(record.get("answer"))
    if obj is None:
        return None, "unparseable:" + how, None
    dec, why = validate(obj)
    return dec, why, how


# ------------------------------------------------------------------------------------------------ §4 simulator
class Book:
    """One instrument's 5m BID bars (sorted labels + parsed times) the simulator walks."""

    def __init__(self, sym, candles):
        self.sym, self.c = sym, candles
        self.times = [b["time"] for b in candles]
        self.dt = [K.parse_z(t) for t in self.times]


def _exit(book, j, price, reason):
    return {"exit_i": j, "exit_time": book.times[j], "exit_price": price, "exit_reason": reason}


def exits(book, f, px, mode, side, stop, target, sp):
    """Walk a position filled on bar f at price px (mode: 'open' = filled at the bar's open, else 'rising' / 'falling' =
    the direction price travelled to reach the fill inside the bar) to its stop, target or time exit.

    The fill bar of a 'rising' / 'falling' fill: the extreme price travelled to (the high when rising) is known to come
    after the fill; the other extreme may come before or after it. That uncertainty is resolved against the trade, for C
    and for every control trade alike: the stop is checked on the whole bar, the target only on the extreme known to
    follow the fill. No trade gains from an assumption about the unseen order of the bar (implementation note §4 item 16)."""
    texit = K.time_exit(book.dt[f])[0]
    # a stop inside the spread at the fill (a LONG's BID, a SHORT's ASK already at or beyond it) is hit at once, at that
    # price -- never at the better stop price (MT5 triggers the stop on the next tick)
    if side > 0 and px - sp <= stop:
        return _exit(book, f, px - sp, "stop_inside_spread")
    if side < 0 and px + sp >= stop:
        return _exit(book, f, px + sp, "stop_inside_spread")
    n = len(book.c)
    j = f
    while True:
        if j >= n:
            b = book.c[j - 1]
            return _exit(book, j - 1, b["close"] if side > 0 else b["close"] + sp, "data_end")
        if j > f and book.dt[j] >= texit:
            b = book.c[j - 1]
            return _exit(book, j - 1, b["close"] if side > 0 else b["close"] + sp, "time")
        b = book.c[j]
        bo, bh, bl, bc = b["open"], b["high"], b["low"], b["close"]
        if side > 0:
            stop_hit, tgt_hit = bl <= stop, bh >= target
        else:
            stop_hit, tgt_hit = bh + sp >= stop, bl + sp <= target
        if j == f and mode != "open":
            tgt_hit = tgt_hit and (mode == "rising" if side > 0 else mode == "falling")
        gap_ok = j > f or mode == "open"
        if stop_hit:
            if side > 0:
                price = bo if gap_ok and bo <= stop else stop
            else:
                price = bo + sp if gap_ok and bo + sp >= stop else stop
            return _exit(book, j, price, "stop")
        if tgt_hit:
            return _exit(book, j, target, "target")
        if book.dt[j] + K.BAR >= texit:
            return _exit(book, j, bc if side > 0 else bc + sp, "time")
        j += 1


def simulate(book, order):
    """One order through the §4 rules (module docstring). `order`: side (+1 long / -1 short), kind (limit / stop /
    market), entry, stop, target, placed_at, valid_until (aware datetimes), spread (price units)."""
    sp, side, kind = order["spread"], order["side"], order["kind"]
    e, s, t = order["entry"], order["stop"], order["target"]
    p = bisect.bisect_left(book.times, K.iso_z(order["placed_at"]))
    if order.get("bar_at_placement") and (p >= len(book.c) or book.times[p] != K.iso_z(order["placed_at"])):
        return {"status": "rejected", "reason": "no_price_at_placement"}      # C: no market price at the killzone open
    if p >= len(book.c) or book.dt[p] >= order["valid_until"]:
        return {"status": "unfilled", "reason": "no_bar_before_expiry"}
    bid0 = book.c[p]["open"]
    ask0 = bid0 + sp
    if kind == "limit" and ((side > 0 and not e < ask0) or (side < 0 and not e > bid0)):
        return {"status": "rejected", "reason": "limit_on_wrong_side_of_market", "market_bid": bid0}
    if kind == "stop" and ((side > 0 and not e > ask0) or (side < 0 and not e < bid0)):
        return {"status": "rejected", "reason": "stop_on_wrong_side_of_market", "market_bid": bid0}
    fill = None
    if kind == "market":
        if K.no_fill_after(book.dt[p]):
            return {"status": "unfilled", "reason": "after_time_exit"}
        close_px = bid0 if side > 0 else ask0
        if (side > 0 and not s < close_px < t) or (side < 0 and not t < close_px < s):
            return {"status": "rejected", "reason": "stops_on_wrong_side_at_fill", "market_bid": bid0}
        fill = (p, ask0 if side > 0 else bid0, "open")
    else:
        j = p
        while j < len(book.c) and book.dt[j] < order["valid_until"]:
            if not K.no_fill_after(book.dt[j]):
                b = book.c[j]
                bo, bh, bl = b["open"], b["high"], b["low"]
                if kind == "limit" and side > 0 and bl + sp <= e:
                    fill = (j, e, "open" if bo + sp <= e else "falling")
                elif kind == "limit" and side < 0 and bh >= e:
                    fill = (j, e, "open" if bo >= e else "rising")
                elif kind == "stop" and side > 0 and bh + sp >= e:
                    fill = (j, bo + sp, "open") if bo + sp >= e else (j, e, "rising")
                elif kind == "stop" and side < 0 and bl <= e:
                    fill = (j, bo, "open") if bo <= e else (j, e, "falling")
                if fill:
                    break
            j += 1
        if fill is None:
            return {"status": "unfilled", "reason": "expired"}
    f, px, mode = fill
    ex = exits(book, f, px, mode, side, s, t, sp)
    pnl = side * (ex["exit_price"] - px)
    # R unit (pre-registration §4): |entry - stop| + spread, entry = the ORDER's price -- a limit or stop order's own
    # price (it fills there or worse), a market order's fill (its price is the market at placement; the answer's
    # `entry` field is only the model's estimate and would let an arbitrary number set the unit)
    risk = abs((px if kind == "market" else e) - s) + sp
    return dict({"status": "filled", "fill_i": f, "fill_time": book.times[f], "fill_price": px, "fill_mode": mode,
                 "pnl": pnl, "risk_unit": risk, "R": pnl / risk}, **ex)


def control_pair(book, trade, order):
    """(R same direction, R opposite direction) of the R-control for one of C's FILLED trades: an entry at the trade's
    own fill instant (the BID there, +spread for a LONG), in each direction, with the trade's own distances from its fill
    to its stop and to its target (its planned ones when a gap fill left either <= 0), the trade's own fill bar and
    path, and the trade's own R unit -- so the same-direction control IS the trade."""
    sp, side, f, mode = order["spread"], order["side"], trade["fill_i"], trade["fill_mode"]
    px = trade["fill_price"]
    bid_f = px - sp if side > 0 else px
    d_in, g_in = side * (px - order["stop"]), side * (order["target"] - px)
    if d_in <= 0 or g_in <= 0:
        d_in, g_in = abs(order["entry"] - order["stop"]), abs(order["target"] - order["entry"])
    out = {}
    for s in (side, -side):
        entry = bid_f + sp if s > 0 else bid_f
        ex = exits(book, f, entry, mode, s, entry - s * d_in, entry + s * g_in, sp)
        out[s] = s * (ex["exit_price"] - entry) / trade["risk_unit"]
    return out[side], out[-side]


def placement_bid(book, order):
    """The BID at the order's placement (the open of the first bar at / after it), or None."""
    p = bisect.bisect_left(book.times, K.iso_z(order["placed_at"]))
    return book.c[p]["open"] if p < len(book.c) else None


def mirror_order(order, bid0):
    """C's order on the other side, mirrored around the mid price at placement (BID bid0, ASK bid0 + spread): the same
    kind at the same distance from the market, the same stop and target distances (a market order: from its own fill).
    The mirror of a fade is a fade and of a breakout a breakout, so C's side is compared with the opposite side of the
    SAME order -- unlike the same-time control, whose opposite trade at a limit fill follows the move (note item 21b)."""
    sp, side = order["spread"], order["side"]
    if order["kind"] == "market":
        fill_c = bid0 + sp if side > 0 else bid0
        d_s, d_t = side * (fill_c - order["stop"]), side * (order["target"] - fill_c)
        e = bid0 if side > 0 else bid0 + sp                   # the mirror's own fill: a SHORT at the BID, a LONG at the ASK
    else:
        d_s, d_t = abs(order["entry"] - order["stop"]), abs(order["target"] - order["entry"])
        e = 2 * bid0 + sp - order["entry"]                    # (BID + ASK) - entry
    return dict(order, side=-side, entry=e, stop=e + side * d_s, target=e - side * d_t)


def mirror_test(units, n_perm=N_PERM, tag=SEEDS["mirror"], strata=None):
    """units: [(C's direction, C's R or None, the mirror's R or None)] for every order C placed (None = not filled). The
    statistic is the mean R per ORDER (0 when it did not fill); a permutation shuffles the direction labels (within
    `strata`); an order keeps C's outcome when its label equals C's direction and takes the mirror's otherwise.
    p = (1 + #{permuted >= observed}) / (n_perm + 1)."""
    n = len(units)
    if not n:
        return None
    dirs = [u[0] for u in units]
    obs = sum(u[1] or 0.0 for u in units) / n
    groups = collections.defaultdict(list)
    for i, k in enumerate(strata if strata is not None else [""] * n):
        groups[k].append(i)
    rng = rng_for(tag)
    ge, means = 0, []
    for _ in range(n_perm):
        labels = [0] * n
        for k in sorted(groups):
            idx = groups[k]
            for i, d in zip(idx, shuffle(rng, [dirs[i] for i in idx])):
                labels[i] = d
        m = sum((units[i][1] if labels[i] == dirs[i] else units[i][2]) or 0.0 for i in range(n)) / n
        means.append(m)
        ge += m >= obs - 1e-12
    return {"observed_mean_R_per_order": obs, "p_one_sided": (1 + ge) / (n_perm + 1), "n_orders": n,
            "n_permutations": n_perm, "seed_tag": tag, "control_mean_R_per_order": mean(means)}


# ------------------------------------------------------------------------------------------------ statistics
def mean(xs):
    return sum(xs) / len(xs) if xs else None


def permutation_test(r_c, dirs, r_same, r_opp, n_perm=N_PERM, tag=SEEDS["permutation"], signflip=False, strata=None):
    """One-sided p of mean(r_c) against the R-control (§5): permutation k shuffles the direction labels of C's filled
    trades WITHIN each stratum (`strata`: one key per trade, e.g. the instrument; None = one stratum), or flips a fair
    coin per trade with `signflip`; trade i then scores r_same[i] when its label equals C's own direction, r_opp[i]
    otherwise. p = (1 + #{control mean >= C mean}) / (n_perm + 1), ties counted against C."""
    n = len(r_c)
    obs = mean(r_c)
    rng = rng_for(tag)
    groups = collections.defaultdict(list)
    for i, k in enumerate(strata if strata is not None else [""] * n):
        groups[k].append(i)
    ge, means = 0, []
    for _ in range(n_perm):
        if signflip:
            labels = [1 if rng.random() < 0.5 else -1 for _ in range(n)]
        else:
            labels = [0] * n
            for k in sorted(groups):
                idx = groups[k]
                for i, d in zip(idx, shuffle(rng, [dirs[i] for i in idx])):
                    labels[i] = d
        m = sum(r_same[i] if labels[i] == dirs[i] else r_opp[i] for i in range(n)) / n
        means.append(m)
        ge += m >= obs - 1e-12
    means.sort()
    return {"observed_mean_R": obs, "p_one_sided": (1 + ge) / (n_perm + 1), "n_permutations": n_perm, "seed_tag": tag,
            "control_mean_R": mean(means), "control_p05": means[int(0.05 * n_perm)],
            "control_p95": means[int(math.ceil(0.95 * n_perm)) - 1],
            "strata": None if strata is None else dict(collections.Counter(strata))}


def bootstrap_ci(xs, n_boot=N_BOOT, tag=SEEDS["bootstrap"]):
    """Percentile bootstrap of the mean: (2.5 %, 97.5 %) of n_boot seeded resamples."""
    rng = rng_for(tag)
    n = len(xs)
    ms = sorted(sum(xs[int(rng.random() * n)] for _ in range(n)) / n for _ in range(n_boot))
    return ms[int(math.floor(0.025 * n_boot))], ms[int(math.ceil(0.975 * n_boot)) - 1]


def metrics(trades):
    """§6 metrics of filled trades: count, win rate, mean / median R, profit factor, max drawdown in R (cumulative R in
    exit order), total R, exits."""
    n = len(trades)
    if not n:
        return {"n": 0}
    rs = [t["R"] for t in trades]
    gains, losses = sum(r for r in rs if r > 0), -sum(r for r in rs if r < 0)
    cum = peak = mdd = 0.0
    for t in sorted(trades, key=lambda t: (t["exit_time"], t["fill_time"], t["id"])):
        cum += t["R"]
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return {"n": n, "mean_R": mean(rs), "median_R": statistics.median(rs), "sd_R": statistics.pstdev(rs),
            "win_rate": sum(1 for r in rs if r > 0) / n, "profit_factor": gains / losses if losses else None,
            "max_drawdown_R": mdd, "total_R": sum(rs),
            "exits": dict(collections.Counter(t["exit_reason"] for t in trades))}


def verdict(n_filled, p, mean_c, m_evaluable, mean_m, p_mirror=None):
    """Pre-registration §6, plus the reviewing session's arm-M rule: INSUFFICIENT below 60 filled trades; FAIL when the
    primary test does not pass; PASS only when it passes, C's mean net R > 0 and C beats M; "INCOMPLETE (C vs M not
    evaluable)" when M is not evaluable and every other PASS condition holds; NOT_PASS otherwise (the primary test
    passed but another PASS condition failed -- the pre-registration names no state for that case). With
    MIRROR_CONTROL_GATES the mirror-order test must pass too (a pre-registration amendment)."""
    if n_filled < MIN_FILLED:
        return "INSUFFICIENT"
    if not p < ALPHA:
        return "FAIL"
    if MIRROR_CONTROL_GATES and not (p_mirror is not None and p_mirror < ALPHA):
        return "NOT_PASS"
    beats = (mean_c > mean_m) if m_evaluable else "not evaluable"
    if mean_c > 0 and beats is True:
        return "PASS"
    if mean_c > 0 and beats == "not evaluable":
        return "INCOMPLETE (C vs M not evaluable)"
    return "NOT_PASS"


# ------------------------------------------------------------------------------------------------ arm C
def order_of(dec, point, spread):
    return {"side": 1 if dec["decision"] == "LONG" else -1, "kind": dec["order"], "entry": float(dec["entry"]),
            "stop": float(dec["stop"]), "target": float(dec["target"]), "placed_at": K.parse_z(point["kz_open_utc"]),
            "valid_until": K.parse_z(point["kz_end_utc"]), "spread": spread, "bar_at_placement": True}


def arm_c(points, final, books):
    rows = []
    for p in points:
        rec = final[p["id"]]
        dec, err, how = judge(rec)
        row = {"id": p["id"], "instrument": p["instrument"], "killzone": p["killzone"], "date_et": p["date_et"],
               "answer_form": how, "retry": bool(rec.get("retry")),
               "served_model_unverifiable": bool(rec.get("served_model_unverifiable"))}
        if dec is None:
            row["outcome"] = "technical_failure" if err == "technical_failure" else "invalid"
            row["error"] = err
        elif dec["decision"] == "NO_TRADE":
            row["outcome"] = "no_trade"
        else:
            book = books[p["instrument"]]
            order = order_of(dec, p, p["spread"]["spread"])
            sim = simulate(book, order)
            bid0 = placement_bid(book, order)
            msim = simulate(book, mirror_order(order, bid0)) if bid0 is not None else {"status": "rejected"}
            row.update(outcome=sim["status"], decision=dec["decision"], order=dec["order"], entry=order["entry"],
                       stop=order["stop"], target=order["target"], spread=order["spread"], _order=order,
                       mirror_outcome=msim["status"], mirror_R=msim.get("R"),
                       **{k: v for k, v in sim.items() if k != "status"})
        rows.append(row)
    return rows


def counts(rows):
    c = collections.Counter(r["outcome"] for r in rows)
    orders = sum(c[k] for k in ("filled", "unfilled", "rejected"))
    answered = len(rows) - c["technical_failure"]
    return {"decision_points": len(rows), "technical_failures": c["technical_failure"], "invalid_answers": c["invalid"],
            "valid_answers": answered - c["invalid"], "no_trade": c["no_trade"],
            "no_trade_rate_of_valid": c["no_trade"] / (answered - c["invalid"]) if answered - c["invalid"] else None,
            "no_trade_rate_incl_invalid_and_failures": (c["no_trade"] + c["invalid"] + c["technical_failure"]) / len(rows)
            if rows else None,
            "orders": orders, "rejected_at_placement": c["rejected"], "unfilled": c["unfilled"], "filled": c["filled"],
            "fill_rate": c["filled"] / orders if orders else None,
            "invalid_by_reason": dict(collections.Counter(r["error"] for r in rows if r["outcome"] == "invalid")),
            "rejected_by_reason": dict(collections.Counter(r["reason"] for r in rows if r["outcome"] == "rejected")),
            "answer_forms": dict(collections.Counter(r["answer_form"] for r in rows if r.get("answer_form"))),
            "retried_decisions": sum(1 for r in rows if r["retry"]),
            "served_model_unverifiable": sum(1 for r in rows if r["served_model_unverifiable"])}


# ------------------------------------------------------------------------------------------------ arm M
def _engine(hist_root=None):
    """backtest-methods.py on the FTMO-Demo history + the pilot's config-A overlay (stability-report.config_opts)."""
    os.environ["BT_HISTORY_ROOT"] = hist_root or K.HIST_ROOT
    bt = _load("bt_ic", "scripts/backtest-methods.py")
    sr = _load("stability_report_ic", "scripts/stability-report.py")
    overlay = sr.config_opts(sr.CONFIGS[M_CONFIG], M_TARGET)
    return bt, overlay


def m_scan(bt, overlay, sym, start, end, future_times=True):
    """(intents, skipped, probe) of the ICT engine on `sym` 15m (FTMO-Demo) for setups whose order is placed in
    [start, end): the engine's own per-bar read (live_rules.read_at -> _ict_candidate, first-seen dedupe), the order its
    _ict_trade would place (LIMIT at the FVG near edge, its stop and target, alive from the close of the detection bar
    to the close of bar mss + K, refused when the edge already traded by then), admitted by simulate()'s planned-risk
    rule and its planned R:R floor (bt.MIN_RR) net of the placement-hour spread. Detection reads bars[:i+1] at bar i;
    `probe` re-detects every intent on the series cut after its detection bar (implementation note §5)."""
    saved = bt.OPTS
    bt.OPTS = dict(bt._OPTS_BASE, **overlay)
    bt.series_start(sym, M_TF, K.iso_z(start), lead_bars=M_LEAD_BARS)
    try:
        bt.pit_cutoff(K.iso_z(end))
        c, _src = bt.load(sym, M_TF)
        if future_times:
            bt.pit_cutoff(None)
            c_all, _src = bt.load(sym, M_TF)
        else:
            c_all = c
        if [b["time"] for b in c_all[:len(c)]] != [b["time"] for b in c]:
            raise K.Refused(f"refused: {sym} {M_TF}: the cut series is not a prefix of the full one")
        Tm, H, L, C = ([b[k] for b in c] for k in ("time", "high", "low", "close"))
        HZ = bt.P[M_TF]["H"]
        x = bt._ict_ctx(sym, M_TF, c, Tm, HZ, H, L, C, M_METHODS)
        tick = K.RC.tick_size(K.COST_PROFILE, sym)
        seen, intents, skipped = set(), [], collections.Counter()
        for i in range(x.n):
            a = bt.lr.read_at(c, i, M_TF, M_METHODS, opts=x.fx_opts)
            if a is None:
                continue
            su = bt._ict_candidate(x, i, a)
            if su is None:
                continue
            key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
            if key in seen:
                continue
            seen.add(key)
            placed = K.parse_z(Tm[i]) + TD(minutes=15)
            if not start <= placed < end:
                skipped["placed_outside_span"] += 1
                continue
            mss_i = x.idx_of_time.get(su["mss"]["time"])
            if mss_i is None:
                skipped["mss_bar_unknown"] += 1
                continue
            if i > mss_i + x.K:
                skipped["expired_before_detectable"] += 1
                continue
            entry, stop, target = float(su["entry"]), float(su["stop"]), float(su["target"])
            fstart = bt.fvg_formed_start(su, x.idx_of_time) if bt.OPTS.get("fx_fvg_formed_start") else None
            if bt.fvg_fill(su["side"], mss_i, entry, su["entry_models"]["fill"], stop, H, L, x.K, i + 1,
                           start=fstart) is not None:
                skipped["already_triggered"] += 1
                continue
            if mss_i + x.K >= len(c_all):
                skipped["expiry_beyond_data"] += 1
                continue
            side = 1 if su["side"] == "long" else -1
            spread = K.spread_snapshot(sym, placed)["spread"]
            if not (side * (entry - stop) >= tick and side * (target - entry) > 0):
                skipped["planned_risk_refused"] += 1
                continue
            if (abs(target - entry) - spread) / abs(entry - stop) < bt.MIN_RR:
                skipped["below_min_rr_net"] += 1
                continue
            intents.append({"arm": "M", "id": f"{sym}|{su['side']}|{su['sweep']['time']}|{su['mss']['time']}",
                            "instrument": sym, "side": side, "kind": "limit", "entry": entry, "stop": stop,
                            "target": target, "placed_at": placed,
                            "valid_until": K.parse_z(c_all[mss_i + x.K]["time"]) + TD(minutes=15), "spread": spread,
                            "detected_bar": Tm[i], "_i": i, "_key": (su["side"], su["sweep"]["time"], su["mss"]["time"],
                                                                     entry, stop, target)})
        probe = m_probe(bt, sym, c, HZ, intents)
    finally:
        bt.OPTS = saved
        bt.pit_cutoff(None)
        bt.series_start(sym, M_TF, None)
    return intents, dict(skipped), probe


def m_probe(bt, sym, c, HZ, intents):
    """Leakage probe of the engine's path (reviewing session, 2026-10-04): every intent is re-detected on the series cut
    right after its detection bar -- the same setup (side, sweep, MSS, entry, stop, target) must appear at that bar and
    the edge must still be untouched. Detection only, no outcome."""
    failed = []
    for it in intents:
        i = it["_i"]
        cut = c[:i + 1]
        Tm, H, L, C = ([b[k] for b in cut] for k in ("time", "high", "low", "close"))
        x = bt._ict_ctx(sym, M_TF, cut, Tm, HZ, H, L, C, M_METHODS)
        a = bt.lr.read_at(cut, i, M_TF, M_METHODS, opts=x.fx_opts)
        su = bt._ict_candidate(x, i, a) if a is not None else None
        ok = su is not None and (su["side"], su["sweep"]["time"], su["mss"]["time"], float(su["entry"]),
                                 float(su["stop"]), float(su["target"])) == it["_key"]
        if ok:
            mss_i = x.idx_of_time.get(su["mss"]["time"])
            fstart = bt.fvg_formed_start(su, x.idx_of_time) if bt.OPTS.get("fx_fvg_formed_start") else None
            ok = mss_i is not None and bt.fvg_fill(su["side"], mss_i, float(su["entry"]), su["entry_models"]["fill"],
                                                   float(su["stop"]), H, L, x.K, i + 1, start=fstart) is None
        if not ok:
            failed.append(it["id"])
    return {"checked": len(intents), "failed": len(failed), "failed_ids": failed[:25], "passed": not failed}


# ------------------------------------------------------------------------------------------------ arm T
_T_MODULES = {}


def t_modules():
    """The research modules the demo book's detectors live in (loaded once)."""
    if not _T_MODULES:
        _T_MODULES.update(ec=_load("edge_census_ic", "scripts/research/edge_census.py"),
                          f3=_load("edge_f3_ic", "scripts/research/edge_f3.py"),
                          f4=_load("edge_f4_ic", "scripts/research/edge_f4.py"),
                          ff=_load("fvg_forward_ic", "scripts/research/fvg_forward.py"))
    return _T_MODULES


def t_scan(start, end, versions=T_VERSIONS, hist_root=None):
    """{version: (intents, skipped)} of the demo book's H7 + G9 on XAUUSD, placed in [start, end): the live executor's
    rule (scripts/fvg_demo.py _eod_breakout) replayed on the stored bars -- a MARKET order when the signal bar closes,
    reference = its close, stop k x sigma_5m x sqrt(5m bars to the rollover) x ref, target ref + side x tp_stop_multiple x
    stop distance, one trade per (component, server day, side), refused on stale volatility, a data hole in the last
    35 days, or a signal within close_before_rollover_minutes of the rollover. Its own time exit is replaced by §4's."""
    mods = t_modules()
    ec, f3, f4, ff = mods["ec"], mods["f3"], mods["f4"], mods["ff"]
    doc, _ = K.HS.read_doc(T_SYMBOL, "5m", root=hist_root or K.HIST_ROOT)
    s = ec.Series(T_SYMBOL, doc["candles"], K.server_zone(), end=K.iso_z(end), sigma_every_day=True)
    events = {"H7": f3.ev_breakout_trend(s), "G9": f4.ev_vol_breakout(s)}
    out = {}
    for ver, cfg in versions.items():
        intents, skipped = [], collections.Counter()
        for comp, evs in events.items():
            done = set()
            for ev in sorted(evs, key=lambda e: e["i"]):
                i, side = ev["i"], ev["side"]
                now = s.dt[i] + K.BAR
                if not start <= now < end:
                    continue
                key = (s.sday[i], side)          # the executor's done_keys: set on an order and on the rollover skip
                if key in done:
                    skipped["not_first_of_day"] += 1
                    continue
                sig = s.sigma(i)
                if not sig or not ff._vol_fresh(s, i):
                    skipped["volatility_stale"] += 1
                    continue
                k0 = max(0, bisect.bisect_left(s.T, K.iso_z(now - ff.HOLE_LOOKBACK)) - 1)   # incl. the pair across
                if ff.holes(s.T[k0:i + 1], since=now - ff.HOLE_LOOKBACK):
                    skipped["data_hole"] += 1
                    continue
                day_end = K.server_midnight(K.server_date(now) + TD(days=1))
                done.add(key)
                if now >= day_end - TD(minutes=cfg["close_before_rollover_minutes"]) or s.sday[i] != K.server_date(now):
                    skipped["too_close_to_rollover"] += 1
                    continue
                nb = max(1, int((day_end - now).total_seconds() // 300))
                ref = s.C[i]
                dist = cfg["stop_k"] * sig * math.sqrt(nb) * ref
                intents.append({"arm": "T", "id": f"{ver}|{comp}|{s.T[i]}|{side}", "instrument": T_SYMBOL, "side": side,
                                "kind": "market", "entry": ref, "stop": ref - side * dist,
                                "target": ref + side * cfg["tp_stop_multiple"] * dist, "placed_at": now,
                                "valid_until": K.time_exit(now)[0], "spread": K.spread_snapshot(T_SYMBOL, now)["spread"],
                                "component": comp, "signal_bar": s.T[i]})
        out[ver] = (sorted(intents, key=lambda x: x["placed_at"]), dict(skipped))
    return out


def run_orders(books, intents):
    trades, status = [], collections.Counter()
    for it in intents:
        sim = simulate(books[it["instrument"]], it)
        status[sim["status"] if sim["status"] == "filled" else f"{sim['status']}:{sim['reason']}"] += 1
        if sim["status"] == "filled":
            trades.append(dict({k: v for k, v in it.items() if not k.startswith("_")}, placed_at=K.iso_z(it["placed_at"]),
                               valid_until=K.iso_z(it["valid_until"]), **sim))
    return trades, dict(status)


# ------------------------------------------------------------------------------------------------ evaluate
class Ctx:
    def __init__(self, root=None, exp_dir=None, shadow_dir=None, hist_root=None):
        self.root = root or K.ROOT
        self.hist_root = hist_root or K.HIST_ROOT
        self.exp_dir = exp_dir or K.EXP_DIR
        self.shadow_dir = K.shadow_dir(shadow_dir)

    def path(self, rel):
        return os.path.join(self.root, rel)


def _read_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip():
                try:
                    rec = json.loads(line)
                except ValueError as e:
                    raise K.Refused(f"refused: {path}:{n} is not JSON ({e})")
                if not isinstance(rec, dict) or "record" not in rec:
                    raise K.Refused(f"refused: {path}:{n} is not a record")
                out.append(rec)
    return out


def preconditions(ctx):
    """Every refusal of `evaluate`, before any outcome is computed. Returns (manifest, manifest sha256, final records,
    run events, decisions sha256, log integrity)."""
    result_rel = os.path.join(ctx.exp_dir, "evaluation.json")
    if os.path.exists(ctx.path(result_rel)):
        raise K.Refused(f"refused: {result_rel} exists -- the evaluation runs once")
    if K.ever_committed(ctx.root, result_rel):
        raise K.Refused(f"refused: {result_rel} was committed before -- the evaluation runs once")
    man_rel, dec_rel = os.path.join(ctx.exp_dir, "manifest.json"), os.path.join(ctx.exp_dir, "decisions.jsonl")
    if not os.path.exists(ctx.path(dec_rel)):
        raise K.Refused(f"refused: no {dec_rel} -- nothing to evaluate")
    K.require_clean(ctx.root, [K.PREREG, man_rel, dec_rel, K.COMMON, K.EVALUATOR, K.TEMPLATE], "input")
    with open(ctx.path(man_rel), "rb") as fh:
        man_bytes = fh.read()
    man = json.loads(man_bytes)
    prompts = [os.path.join(ctx.exp_dir, "prompts", p["prompt_file"]) for p in man["decision_points"]]
    K.require_clean(ctx.root, prompts, "prompt file")
    if K.sha256_file(ctx.path(K.COMMON)) != man["code"][K.COMMON]:
        raise K.Refused(f"refused: {K.COMMON} changed since the build (manifest) -- the decision points and clock rules "
                        f"must be the ones the prompts were built with")
    recs = _read_jsonl(ctx.path(dec_rel))
    events = [r for r in recs if r["record"] == "run_event"]
    start = next((e for e in events if e["event"] == "start"), None)
    if start is None or not events or events[-1]["event"] != "stop" or events[-1].get("reason") != "complete":
        raise K.Refused("refused: the run has not ended with a `stop / complete` event")
    blob = K.git_blob(ctx.root, K.EVALUATOR)
    if start.get("evaluator_blob") != blob:
        raise K.Refused(f"refused: {K.EVALUATOR} is blob {blob} but the run started with {start.get('evaluator_blob')} "
                        f"-- the evaluator must be the one frozen before the first decision")
    man_sha = K.sha256_bytes(man_bytes)
    with open(ctx.path(dec_rel), "rb") as fh:
        dec_bytes = fh.read()
    commits = K.require_append_only(ctx.root, dec_rel, dec_bytes)
    others = K.shadows_with_records(ctx.shadow_dir, exclude_sha=man_sha)
    if others:
        raise K.Refused(f"refused: shadow log(s) of another build hold decisions on this machine: {others}")
    shadow = K.shadow_path(man_sha, ctx.shadow_dir)
    shadow_state = (K.compare_shadow(K.raw_lines(ctx.path(dec_rel)), K.raw_lines(shadow), shadow)
                    if os.path.exists(shadow) else "absent (not on this machine)")
    integrity = {"commits_of_decisions_log_checked": commits, "shadow": shadow_state, "shadow_path": shadow}
    final = {}
    for r in recs:
        if r["record"] == "decision":
            if r["decision_id"] in final:
                raise K.Refused(f"refused: decision {r['decision_id']} is stored twice")
            final[r["decision_id"]] = r
    ids = [p["id"] for p in man["decision_points"]]
    missing = [i for i in ids if i not in final]
    extra = sorted(set(final) - set(ids))
    if missing or extra:
        raise K.Refused(f"refused: decisions.jsonl is not complete: missing {missing[:3]} ({len(missing)}), unknown "
                        f"{extra[:3]} ({len(extra)})")
    by_id = {p["id"]: p for p in man["decision_points"]}
    for i, r in final.items():
        if r.get("status") == "answered" and K.sha256_bytes((r.get("answer") or "").encode("utf-8")) != r.get("answer_sha256"):
            raise K.Refused(f"refused: the stored answer of {i} does not match its answer_sha256 -- the log was edited")
        if r.get("prompt_sha256") != by_id[i]["prompt_sha256"] or r.get("manifest_sha256") != man_sha:
            raise K.Refused(f"refused: decision {i} was not made from the committed prompt / manifest")
        if K.sha256_file(ctx.path(os.path.join(ctx.exp_dir, "prompts", by_id[i]["prompt_file"]))) != r["prompt_sha256"]:
            raise K.Refused(f"refused: the prompt file of {i} does not match its decision record")
    return man, man_sha, final, events, K.sha256_bytes(dec_bytes), integrity


def sample_decisions(rows, final):
    valid = sorted(r["id"] for r in rows if r["outcome"] not in ("invalid", "technical_failure"))
    picked = sorted(shuffle(rng_for(SEEDS["sample"]), valid)[:SAMPLE_N])
    by = {r["id"]: r for r in rows}
    out = []
    for i in picked:
        dec, _err, _how = judge(final[i])
        r = by[i]
        out.append(dict(id=i, outcome=r["outcome"], R=r.get("R"), exit_reason=r.get("exit_reason"), **dec))
    return out


def group_metrics(rows, key):
    groups = collections.defaultdict(list)
    for r in rows:
        groups[r[key] if isinstance(key, str) else key(r)].append(r)
    out = {}
    for g, rs in sorted(groups.items()):
        filled = [r for r in rs if r["outcome"] == "filled"]
        out[g] = dict(counts(rs), **{"metrics": metrics(filled)})
    return out


ALWAYS_EXECUTED = (K.COMMON, K.EVALUATOR, "scripts/history_store.py", "scripts/real_costs.py", "scripts/mt5_time.py",
                   "scripts/research/prereg_guard.py")


def require_executed_clean(ctx, pg):
    """Every repository .py file this process has executed is committed and unchanged; returns their sorted list."""
    executed = sorted(pg.executed_code() | set(ALWAYS_EXECUTED))
    K.require_clean(ctx.root, executed, "executed code file")
    return executed


def require_frozen_inputs(ctx, man, start_head, pg, executed):
    """Refuses unless every code / configuration file the evaluation has executed or opened (the experiment's own files
    aside) is committed and is the SAME blob as at the run's start commit, the bars every arm reads are the ones `build`
    pinned, and the cost tables and build libraries are the manifest's (implementation note §4 item 31). Returns the
    dependency list. When a dependency changed after the start, evaluate from a worktree of the start commit (note §8)."""
    exp_prefix = ctx.exp_dir.rstrip("/") + "/"
    opened = [p for p in pg.opened_files(ctx.root) if not p.startswith(exp_prefix)]
    deps = sorted(set(executed) | set(opened))
    K.require_clean(ctx.root, deps, "dependency")
    drift = [p for p in deps if K.git_blob(ctx.root, p, start_head) is None
             or K.git_blob(ctx.root, p, start_head) != K.git_blob(ctx.root, p)]
    if drift:
        raise K.Refused(f"refused: {len(drift)} file(s) the evaluation depends on differ from the run's start commit "
                        f"{start_head[:12]}: {drift[:6]} -- evaluate from a worktree of that commit (implementation "
                        f"note §8)")
    window = (K.parse_z(man["window"]["start"]), K.parse_z(man["window"]["end_close_of_last_bar"]))
    pins = K.data_pins(window, ctx.hist_root)
    bad = sorted(k for k in set(pins) | set(man.get("data_pins") or {}) if pins.get(k) != (man.get("data_pins") or {}).get(k))
    if bad:
        raise K.Refused(f"refused: the stored bars of {bad} are not the ones the build pinned -- a re-export changed them")
    if K.RC.profile_snapshot(K.COST_PROFILE, list(K.INSTRUMENTS)) != man["cost"]["snapshot"]:
        raise K.Refused("refused: the cost tables differ from the ones the build recorded")
    libs = {rel: K.sha256_file(os.path.join(K.ROOT, rel)) for rel in man["build_libraries"]}
    if libs != man["build_libraries"]:
        raise K.Refused(f"refused: build libraries changed since the build: "
                        f"{sorted(k for k in libs if libs[k] != man['build_libraries'][k])}")
    return deps


def cmd_evaluate(ctx, out=print):
    pg = _load("prereg_guard_ic", "scripts/research/prereg_guard.py")
    pg.trace_start(ctx.root)
    man, man_sha, final, events, dec_sha, integrity = preconditions(ctx)
    start_head = next(e for e in events if e["event"] == "start")["git_head"]
    # every module the arms need is loaded and every input checked BEFORE any outcome is computed
    bt, overlay = _engine(ctx.hist_root)
    t_modules()
    require_frozen_inputs(ctx, man, start_head, pg, require_executed_clean(ctx, pg))
    start, end = K.parse_z(man["window"]["start"]), K.parse_z(man["window"]["end_close_of_last_bar"])
    points = man["decision_points"]
    books = {s: Book(s, K.load_bars(s, ctx.hist_root, since=start - TD(days=2), until=end + TD(days=1)))
             for s in K.INSTRUMENTS}
    # ---- C
    rows = arm_c(points, final, books)
    filled = [r for r in rows if r["outcome"] == "filled"]
    r_c = [r["R"] for r in filled]
    # ---- R (the control lives on C's filled trades)
    dirs, r_same, r_opp, mismatch = [], [], [], 0
    for r in filled:
        same, opp = control_pair(books[r["instrument"]], r, r["_order"])
        mismatch += abs(same - r["R"]) > 1e-9
        dirs.append(r["_order"]["side"])
        r_same.append(same)
        r_opp.append(opp)
    # a label equal to C's direction scores C's own trade (r_c), so the identity permutation IS C; r_same only checks
    # that the control construction reproduces C (it can differ after a gap fill beyond the stop or target). The
    # primary shuffle runs within each instrument (a per-instrument static direction cannot pass, note item 21).
    inst = [r["instrument"] for r in filled]
    perm = permutation_test(r_c, dirs, r_c, r_opp, strata=inst) if filled else None
    glob = permutation_test(r_c, dirs, r_c, r_opp, tag=SEEDS["global"]) if filled else None
    kzp = permutation_test(r_c, dirs, r_c, r_opp, tag=SEEDS["killzone"],
                           strata=[f"{r['instrument']}|{r['killzone']}" for r in filled]) if filled else None
    flip = permutation_test(r_c, dirs, r_c, r_opp, tag=SEEDS["signflip"], signflip=True) if filled else None
    placed = [r for r in rows if r["outcome"] in ("filled", "unfilled", "rejected")]
    mirror = mirror_test([(r["_order"]["side"], r.get("R"), r.get("mirror_R")) for r in placed],
                         strata=[r["instrument"] for r in placed])
    lb, ub = bootstrap_ci(r_c) if filled else (None, None)
    # ---- M
    m_trades, m_status, m_skipped, m_probe_res = [], {}, {}, {}
    for sym in K.INSTRUMENTS:
        intents, skipped, probe = m_scan(bt, overlay, sym, start, end)
        tr, st = run_orders(books, intents)
        m_trades += tr
        m_status[sym], m_skipped[sym], m_probe_res[sym] = st, skipped, probe
    m_probe_ok = all(p["passed"] for p in m_probe_res.values())
    m_metrics = metrics(m_trades)
    m_evaluable = m_probe_ok and m_metrics["n"] > 0
    # ---- T (report-only)
    t_out = {}
    for ver, (intents, skipped) in t_scan(start, end, hist_root=ctx.hist_root).items():
        tr, st = run_orders(books, intents)
        t_out[ver] = {"params": T_VERSIONS[ver], "orders": st, "skipped": skipped, "metrics": metrics(tr),
                      "by_component": {c: metrics([t for t in tr if t["component"] == c]) for c in ("H7", "G9")},
                      "trades": [{k: t[k] for k in ("id", "side", "entry", "stop", "target", "fill_time", "fill_price",
                                                    "exit_time", "exit_price", "exit_reason", "R")} for t in tr]}
    mean_c = mean(r_c)
    status = verdict(len(filled), perm["p_one_sided"] if perm else 1.0, mean_c if mean_c is not None else 0.0,
                     m_evaluable, m_metrics.get("mean_R"), p_mirror=mirror["p_one_sided"] if mirror else None)
    res = {
        "meta": {"experiment": K.EXPERIMENT, "preregistration": K.PREREG, "implementation_note": K.IMPL_NOTE,
                 "evaluated_at_utc": K.iso_z(K.utc_now()), "git_head": K.git_head(ctx.root),
                 "evaluator_blob": K.git_blob(ctx.root, K.EVALUATOR), "manifest_sha256": man_sha,
                 "decisions_sha256": dec_sha, "run_events": events, "log_integrity": integrity,
                 "dataset": {s: K.dataset_snapshot(s, ctx.hist_root) for s in K.INSTRUMENTS},
                 "parameters": {"min_filled": MIN_FILLED, "alpha": ALPHA, "n_permutations": N_PERM,
                                "n_bootstrap": N_BOOT, "seeds": SEEDS, "max_reasoning_words": MAX_REASONING_WORDS,
                                "min_reward_risk": MIN_REWARD_RISK, "cost_profile": K.COST_PROFILE,
                                "m": {"tf": M_TF, "config": M_CONFIG, "ict_target": M_TARGET, "methods": M_METHODS,
                                      "overlay": overlay, "min_rr": bt.MIN_RR,
                                      "resolve_methods_now": {s: bt.resolve_methods(s) for s in K.INSTRUMENTS}},
                                "t": T_VERSIONS}},
        "verdict": {"status": status, "n_filled_C": len(filled), "min_filled": MIN_FILLED,
                    "primary_test": dict(perm or {}, alpha=ALPHA, control="shuffle of C's direction labels over its "
                                         "filled trades within each instrument; same fill instant, stop distance, "
                                         "reward/risk and R unit", passed=bool(perm and perm["p_one_sided"] < ALPHA)),
                    "mirror_control": dict(mirror or {}, gates=MIRROR_CONTROL_GATES,
                                           passed=bool(mirror and mirror["p_one_sided"] < ALPHA)),
                    "mean_net_R_C": mean_c, "mean_net_R_C_positive": bool(mean_c is not None and mean_c > 0),
                    "bootstrap_95": {"lower": lb, "upper": ub, "n": N_BOOT, "seed_tag": SEEDS["bootstrap"]},
                    "c_beats_m": (mean_c is not None and m_metrics.get("mean_R") is not None and mean_c > m_metrics["mean_R"])
                    if m_evaluable else "not evaluable",
                    "m_leakage_probe": m_probe_res, "m_evaluable": m_evaluable,
                    "c_minus_t_mean_R": {v: (mean_c - t["metrics"]["mean_R"]) if mean_c is not None and t["metrics"]["n"]
                                         else None for v, t in t_out.items()},
                    "report_only": "T does not gate; the global / killzone / sign-flip controls are descriptive; the "
                                   "mirror-order control gates only with MIRROR_CONTROL_GATES"},
        "arms": {
            "C": {"counts": counts(rows), "metrics": metrics(filled),
                  "by_instrument": group_metrics(rows, "instrument"),
                  "by_killzone": group_metrics(rows, lambda r: f"{r['instrument']}|{r['killzone']}"),
                  "decisions": [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]},
            "R": {"shuffle_within_instrument": perm, "global_shuffle_descriptive": glob,
                  "within_killzone_shuffle_descriptive": kzp, "signflip_descriptive": flip,
                  "same_direction_differs_from_C": mismatch, "mirror_order": mirror},
            "M": {"metrics": m_metrics, "orders": m_status, "skipped": m_skipped, "leakage_probe": m_probe_res,
                  "by_instrument": {s: metrics([t for t in m_trades if t["instrument"] == s]) for s in K.INSTRUMENTS},
                  "trades": [{k: t[k] for k in ("id", "instrument", "side", "entry", "stop", "target", "placed_at",
                                                 "fill_time", "fill_price", "exit_time", "exit_reason", "R")}
                             for t in m_trades]},
            "T": t_out},
        "sample_10": sample_decisions(rows, final),
    }
    deps = require_frozen_inputs(ctx, man, start_head, pg, require_executed_clean(ctx, pg))   # again: lazy imports
    res["meta"]["frozen_inputs"] = {"start_commit": start_head, "dependencies": {p: K.git_blob(ctx.root, p) for p in deps},
                                    "data_pins": man["data_pins"]}
    res["meta"]["opened_files_sha256"] = pg.opened_files(ctx.root)
    result_path = ctx.path(os.path.join(ctx.exp_dir, "evaluation.json"))
    if os.path.exists(result_path):
        raise K.Refused(f"refused: {result_path} appeared during the evaluation")
    tmp = result_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, sort_keys=True, default=str)
        fh.write("\n")
    os.replace(tmp, result_path)
    out(f"verdict: {status}; C filled {len(filled)}, mean net R {mean_c}, p {perm and perm['p_one_sided']}; "
        f"M n {m_metrics['n']} mean {m_metrics.get('mean_R')} (probe {'passed' if m_probe_ok else 'FAILED'}); wrote {result_path}")
    return 0


def cmd_feasibility(start="2026-04-01T00:00:00Z", out=print):
    """Arms M and T on bars BEFORE the window only: intent counts, their structure and the M leakage probe. No order is
    simulated and no outcome is computed (house rule: no outcome on an uncommitted window)."""
    a, b = K.parse_z(start), K.parse_z(K.WINDOW_START)
    if not a < b:
        raise K.Refused("refused: feasibility reads bars before the window only")
    bt, overlay = _engine()
    for sym in K.INSTRUMENTS:
        intents, skipped, probe = m_scan(bt, overlay, sym, a, b, future_times=False)
        ok = all(it["kind"] == "limit" and all(math.isfinite(it[k]) for k in ("entry", "stop", "target")) and
                 it["side"] * (it["entry"] - it["stop"]) > 0 and it["side"] * (it["target"] - it["entry"]) > 0
                 for it in intents)
        out(f"M {sym}: {len(intents)} fixed-exit LIMIT intents in {start[:10]} .. {K.WINDOW_START[:10]}; structure ok: {ok}; "
            f"skipped {skipped}; probe {probe['checked'] - probe['failed']}/{probe['checked']} identical")
    for ver, (intents, skipped) in t_scan(a, b).items():
        ok = all(it["kind"] == "market" and it["side"] * (it["entry"] - it["stop"]) > 0 for it in intents)
        out(f"T {ver}: {len(intents)} MARKET intents (H7 {sum(1 for i in intents if i['component'] == 'H7')}, "
            f"G9 {sum(1 for i in intents if i['component'] == 'G9')}); structure ok: {ok}; skipped {skipped}")
    return 0


def cmd_calibrate(since="2026-03-02T00:00:00Z", until=K.WINDOW_START, reps=600, n_trades=80, n_orders=120, n_perm=300,
                  kinds=("market", "limit", "stop"), hist_root=None, out=print):
    """Size of the primary test and of the mirror-order test under RANDOM directions, on bars BEFORE the window (no outcome
    inside it): seeded random orders at real killzone opens -- stop 2-8x the median 5m range of the 48 bars before the
    open, reward/risk 1-2.5, a pending order 0.5-4x that range away from the market -- with BOTH sides simulated; each
    replicate flips a fair coin per order, calls the chosen side "C" and runs both tests (`n_trades` filled trades for
    the primary, `n_orders` orders for the mirror). A calibrated test rejects in about 5 % of the replicates; above that,
    a book without directional skill passes too often (implementation note §4 item 21b)."""
    a, b = K.parse_z(since), K.parse_z(until)
    if not a < b <= K.parse_z(K.WINDOW_START):
        raise K.Refused("refused: calibration reads bars before the window only")
    rng = rng_for("IC|calibrate|v1")
    results = {}
    for sym in K.INSTRUMENTS:
        bars = K.load_bars(sym, hist_root, since=a - TD(days=2), until=b)
        book = Book(sym, bars)
        opens, day = [], a.astimezone(K.ET).date()
        while day < b.astimezone(K.ET).date():
            if day.weekday() < 5:
                for kz, *_x in K.killzones(sym):
                    o, e = K.killzone_window(sym, kz, day)
                    if a <= o and e <= b:
                        opens.append((o, e))
            day += TD(days=1)
        for kind in kinds:
            slots = []
            for o, e in opens:
                i = bisect.bisect_left(book.times, K.iso_z(o))
                if i < 48 or i >= len(bars) or book.times[i] != K.iso_z(o):
                    continue
                med = statistics.median(bars[j]["high"] - bars[j]["low"] for j in range(i - 48, i))
                sp, bid0 = K.spread_snapshot(sym, o)["spread"], bars[i]["open"]
                for _ in range(10):
                    d = med * (2 + 6 * rng.random())
                    g, off = d * (1 + 1.5 * rng.random()), med * (0.5 + 3.5 * rng.random())
                    entry = {"market": bid0 + sp, "limit": bid0 + sp - off, "stop": bid0 + sp + off}[kind]
                    long_o = {"side": 1, "kind": kind, "entry": entry, "stop": entry - d, "target": entry + g,
                              "placed_at": o, "valid_until": e, "spread": sp, "bar_at_placement": True}
                    orders = {1: long_o, -1: mirror_order(long_o, bid0)}
                    sims = {sd: simulate(book, od) for sd, od in orders.items()}
                    opp = {sd: control_pair(book, sims[sd], orders[sd])[1] for sd in (1, -1)
                           if sims[sd]["status"] == "filled"}
                    slots.append((sims, opp))
            rej_p = rej_m = done = 0
            for rep in range(reps):
                picks = [(sl, 1 if rng.random() < 0.5 else -1) for sl in slots]
                trades = [(sl[0][sd]["R"], sd, sl[1][sd]) for sl, sd in picks if sl[0][sd]["status"] == "filled"]
                if len(trades) < n_trades or len(picks) < n_orders:
                    continue
                tr = shuffle(rng, trades)[:n_trades]
                pt = permutation_test([t[0] for t in tr], [t[1] for t in tr], [t[0] for t in tr], [t[2] for t in tr],
                                      n_perm=n_perm, tag=f"cal|{sym}|{kind}|{rep}")
                units = [(sd, sl[0][sd].get("R"), sl[0][-sd].get("R")) for sl, sd in shuffle(rng, picks)[:n_orders]]
                mt = mirror_test(units, n_perm=n_perm, tag=f"calm|{sym}|{kind}|{rep}")
                rej_p += pt["p_one_sided"] < ALPHA
                rej_m += mt["p_one_sided"] < ALPHA
                done += 1
            fill = sum(1 for sl in slots for sd in (1, -1) if sl[0][sd]["status"] == "filled") / max(1, 2 * len(slots))
            results[f"{sym}|{kind}"] = {"orders": len(slots), "fill_rate": fill, "replicates": done,
                                        "primary_size": rej_p / done if done else None,
                                        "mirror_size": rej_m / done if done else None}
            out(f"{sym:7s} {kind:6s} orders {len(slots):5d} fill {fill:.2f} replicates {done}: P(p<0.05) primary "
                f"{results[f'{sym}|{kind}']['primary_size']} mirror {results[f'{sym}|{kind}']['mirror_size']}")
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("evaluate")
    f = sub.add_parser("feasibility")
    f.add_argument("--start", default="2026-04-01T00:00:00Z")
    c = sub.add_parser("calibrate")
    c.add_argument("--reps", type=int, default=600)
    a = ap.parse_args(argv)
    if a.cmd == "evaluate":
        return cmd_evaluate(Ctx())
    if a.cmd == "calibrate":
        cmd_calibrate(reps=a.reps)
        return 0
    return cmd_feasibility(a.start)


if __name__ == "__main__":
    sys.exit(main())
