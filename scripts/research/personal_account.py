#!/usr/bin/env python3
"""Personal-account replay: a trade sequence on the owner's OWN account -- no prop rules, compounding, the minimum lot, margin,
stop-out, an exact floating floor, and ruin that ends the account (docs/plans/2026-10-04-personal-account-backtest-design.md,
v2: conditions A1-A11). DESCRIPTIVE research; never routes an order.

    python3 scripts/research/personal_account.py run --out docs/audits/<date>-personal-account.json --cache <rows.pkl>
        [--r 0.01 --b0 5000 100000 --mode skip floor_cap --cap 0.02 0.015 --cap-base current initial]
                                                                                (grid overrides; default GRID)
    python3 scripts/research/personal_account.py check --against <earlier.json> --cache <rows.pkl> [--new <later.json>]

Scope: INTRADAY rows from `book_sim.trades` (flat before the server rollover, so no swap and no weekend gap). Every money
figure uses ONE reference price per symbol (the last stored daily close at the run, A3): R and the stop width in bp come from
the row, the lot size and the minimum lot from today's price -- otherwise a 2004 gold price would make the minimum lot vanish."""
import argparse
import bisect
import collections
import concurrent.futures
import dataclasses
import datetime
import hashlib
import importlib.util
import json
import math
import os
import pickle
import random
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SCRIPT = "scripts/research/personal_account.py"
DESIGN = "docs/plans/2026-10-04-personal-account-backtest-design.md"
BAR = datetime.timedelta(minutes=5)
WEEKDAYS_PER_YEAR = 261
SKIP_REASONS = ("min_lot", "min_lot_over_cap", "netting", "portfolio_cap", "margin")
MODES = ("skip", "floor", "floor_cap")
CAP_BASES = ("current", "initial")    # floor_cap: min_lot_cap x the CURRENT balance, or x b0 (a fixed money amount)
ABOVE_R_TOL = 1e-6                     # relative: a trade risks "above r" only beyond float rounding


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def code_version():
    """CLAUDE.md §46: the commit, the tracked files under scripts/ with uncommitted changes (empty = the run used the
    committed code), and this script's own sha256 (identifies the code even when dirty). None fields when git cannot run."""
    def git(*args):
        try:
            p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=60)
            return p.stdout if p.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain", "--untracked-files=no", "--", "scripts")
    with open(os.path.join(ROOT, SCRIPT), "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    return {"commit": head.strip() if head else None,
            "dirty_tracked": [ln[3:] for ln in dirty.splitlines()] if dirty is not None else None, "script_sha256": sha}


@dataclasses.dataclass(frozen=True)
class Account:
    """A1-A11 inputs. Defaults are NAMED assumptions (design §1, §6), not owner facts."""
    b0: float = 5_000.0                # A1, USD (owner 2026-10-04: "5.000 USD")
    r: float = 0.01                    # A2, risk at the stop, fraction of the CURRENT balance
    mode: str = "skip"                 # A3: "skip" = never above r; "floor" = volume_min whatever its risk (sensitivity);
                                       #     "floor_cap" = volume_min only if its risk <= min_lot_cap (owner 2026-10-04, design §7.4)
    min_lot_cap: float = 0.02          # A3, floor_cap only: ceiling on the minimum lot's risk, a fraction of the cap's base
    min_lot_cap_base: str = "current"  # A3, floor_cap only: "current" = min_lot_cap x the CURRENT balance (as first run);
                                       #     "initial" = min_lot_cap x b0, a FIXED money amount (owner 2026-10-04: "Trần 2% tính
                                       #     theo cố định 100 USD", design §7.4). Not a share of the balance after a drawdown.
    leverage: float = 30.0             # A4 (ASSUMED until the owner's broker spec exists)
    margin_rate: float = 1.0           # A4 (ASSUMED)
    portfolio_cap: float = 0.05        # A5 = risk-config.json max_portfolio_risk_pct
    stop_out: float = 0.50             # A7, margin level
    commission_per_lot: float = 0.0    # A8, USD per lot per round turn
    position_mode: str = "hedging"     # A11: "hedging" | "netting"
    stall_k: int = 20                  # A9: a path that ENDS with >= stall_k consecutive min-lot skips is STALLED (not absorbing)
    pain: float = 0.50                 # A10: reported drawdown line

    def __post_init__(self):
        if self.mode not in MODES or self.position_mode not in ("hedging", "netting"):
            raise ValueError(f"bad mode {self.mode!r} / {self.position_mode!r}")
        if self.min_lot_cap_base not in CAP_BASES:
            raise ValueError(f"bad min_lot_cap_base {self.min_lot_cap_base!r}: one of {CAP_BASES}")
        if not 0 < self.r <= 0.05 or self.b0 <= 0 or self.leverage <= 0:
            raise ValueError("r must be in (0, 5 %], b0 and leverage positive")
        # base "current": the cap is a share of the balance at every trade. Base "initial": the check bounds the FIXED amount
        # min_lot_cap x b0 between r x b0 and 5 % x b0, i.e. at the START it neither undercuts r nor exceeds the portfolio
        # cap (A5); after a drawdown the same amount is a larger share of the balance, by design.
        if self.mode == "floor_cap" and not self.r <= self.min_lot_cap <= 0.05:
            raise ValueError(f"floor_cap needs r <= min_lot_cap <= 5 % (of the {self.min_lot_cap_base} base)")


@dataclasses.dataclass(frozen=True)
class Spec:
    contract: float
    vmin: float
    vstep: float
    vmax: float
    pref: float                        # reference price (A3)


def lots_for(acct, spec, balance, stop_bp):
    """(lots, reason): A3 sizing at the reference price; reason None when tradable."""
    risk_per_lot = stop_bp / 1e4 * spec.pref * spec.contract
    raw = acct.r * balance / risk_per_lot
    lots = min(math.floor(raw / spec.vstep + 1e-9) * spec.vstep, spec.vmax)
    if lots + 1e-12 < spec.vmin:
        if acct.mode == "skip":
            return 0.0, "min_lot"
        base = balance if acct.min_lot_cap_base == "current" else acct.b0
        if acct.mode == "floor_cap" and spec.vmin * risk_per_lot > acct.min_lot_cap * base * (1 + 1e-9):
            return 0.0, "min_lot_over_cap"
        lots = spec.vmin
    return round(lots, 8), None


def _adv_at(o, tick):
    k = int((tick - o["entry"]) / BAR)
    path = o["adv_path_R"]
    return path[min(max(k, 0), len(path) - 1)]


def replay(days, acct, specs, edge_shift=None, keep_curve=False):
    """One account over `days` = [(day_key, [rows])] in path order. rows: dicts with c, symbol, entry, exit (aware
    datetimes, same server day), R, cost_R, stop_bp, adv_path_R. edge_shift: {component: R subtracted} (the haircut).
    Returns the path's metrics. BLOWN is absorbing: nothing trades after it (A9). STALLED is measured after the fact: the
    path ENDS with >= stall_k consecutive signals too small for the minimum lot (`min_lot`, or `min_lot_over_cap` in mode
    floor_cap), i.e. the account never traded again (a temporary run of wide stops that later narrows is not STALLED; the
    money is still there either way). `taken_above_r` counts trades whose risk at the stop exceeded r x the balance (only
    the minimum lot in floor / floor_cap); `risk_taken_mean` is the mean risk actually taken, as a fraction of the balance.
    `taken_above_cap` counts trades whose risk exceeded min_lot_cap x the balance at entry (the CURRENT-balance cap): 0 by
    construction in floor_cap with base "current"; with base "initial" it counts what the fixed amount allowed beyond it
    (only below b0). `risk_taken_max` is the largest risk taken, as a fraction of the balance at entry. A5 (portfolio cap)
    binds only a trade opened next to others, so a lone minimum lot can exceed it after a deep drawdown."""
    shift = edge_shift or {}
    bal, peak, max_dd = acct.b0, acct.b0, 0.0
    skips = collections.Counter()
    taken, post_ruin, consec_skip, above_r, above_cap, risk_max = 0, 0, 0, 0, 0, None
    eff_risk = []
    blown = stalled = None
    streak_start, max_streak = None, 0
    curve = []
    min_margin = min(sp.vmin * sp.contract * sp.pref * acct.margin_rate / acct.leverage for sp in specs.values())
    under, longest_under = 0, 0
    for di, (dkey, rows) in enumerate(days):
        if blown is not None:
            post_ruin += len(rows)
            if keep_curve:
                curve.append(bal)
            continue
        rows = sorted(rows, key=lambda t: (t["entry"], t["c"]))
        ticks = sorted({t["entry"] + BAR * k for t in rows for k in range(len(t["adv_path_R"]))})
        by_entry = collections.defaultdict(list)
        for t in rows:
            by_entry[t["entry"]].append(t)
        open_ = []
        for tick in ticks:
            # A11: an exit is realised before an entry only if exit < entry (strict)
            for o in [o for o in open_ if o["exit"] < tick]:
                bal += o["money"] * (o["R"] - shift.get(o["c"], 0.0)) - acct.commission_per_lot * o["lots"]
                open_.remove(o)
            for t in by_entry.get(tick, ()):
                if blown is not None:
                    post_ruin += 1
                    continue
                sp = specs[t["symbol"]]
                lots, why = lots_for(acct, sp, bal, t["stop_bp"])
                if why:
                    skips[why] += 1
                    if consec_skip == 0:
                        streak_start = dkey
                    consec_skip += 1
                    max_streak = max(max_streak, consec_skip)
                    continue
                consec_skip = 0
                if acct.position_mode == "netting" and any(o["symbol"] == t["symbol"] for o in open_):
                    skips["netting"] += 1
                    continue
                money = lots * t["stop_bp"] / 1e4 * sp.pref * sp.contract
                open_risk = sum(o["money"] for o in open_)
                if open_ and open_risk + money > acct.portfolio_cap * bal:
                    skips["portfolio_cap"] += 1
                    continue
                margin = lots * sp.contract * sp.pref * acct.margin_rate / acct.leverage
                used = sum(o["margin"] for o in open_)
                floor_now = bal + sum(o["money"] * (_adv_at(o, tick) - o["cost_R"]) for o in open_)
                if used + margin > floor_now:
                    skips["margin"] += 1
                    continue
                open_.append(dict(t, lots=lots, money=money, margin=margin))
                taken += 1
                eff_risk.append(money / (acct.r * bal))
                above_r += money > acct.r * bal * (1 + ABOVE_R_TOL)
                above_cap += money > acct.min_lot_cap * bal * (1 + ABOVE_R_TOL)
                risk_max = money / bal if risk_max is None else max(risk_max, money / bal)
            if open_:
                floor_now = bal + sum(o["money"] * (_adv_at(o, tick) - o["cost_R"]) for o in open_)
                max_dd = max(max_dd, 1.0 - floor_now / peak)
                used = sum(o["margin"] for o in open_)
                if floor_now <= 0 or floor_now / used <= acct.stop_out:            # A7 stop-out at this bar
                    for o in open_:
                        bal += o["money"] * (_adv_at(o, tick) - o["cost_R"]) - acct.commission_per_lot * o["lots"]
                    open_ = []
                    skips["stop_out_events"] += 1
        for o in open_:                                   # the day's last bar has passed: realise what is left
            bal += o["money"] * (o["R"] - shift.get(o["c"], 0.0)) - acct.commission_per_lot * o["lots"]
        peak = max(peak, bal)
        max_dd = max(max_dd, 1.0 - bal / peak)
        if blown is None and (bal <= 0 or bal < min_margin):
            blown = dkey
        under = under + 1 if bal < peak else 0
        longest_under = max(longest_under, under)
        if keep_curve:
            curve.append(bal)
    if blown is None and consec_skip >= acct.stall_k:
        stalled = streak_start
    years = max(len(days), 1) / WEEKDAYS_PER_YEAR
    term = max(bal, 0.0) / acct.b0
    cagr = term ** (1 / years) - 1 if term > 0 else -1.0
    out = {"terminal_multiple": term, "cagr": cagr, "max_dd": min(max_dd, 1.0), "calmar": (cagr / max_dd) if max_dd > 0 else None,
           "longest_under_water_days": longest_under, "blown": blown, "stalled": stalled, "taken": taken,
           "longest_min_lot_skip_streak": max_streak,
           "post_ruin": post_ruin, "skips": dict(skips),
           "effective_risk_mean": statistics.mean(eff_risk) if eff_risk else None,
           "taken_above_r": above_r, "risk_taken_mean": statistics.mean(eff_risk) * acct.r if eff_risk else None,
           "taken_above_cap": above_cap, "risk_taken_max": risk_max}
    if keep_curve:
        out["curve"] = curve
    return out


# ---------------------------------------------------------------------------------------------------------------- data
BOOKS = {"H7_XAU": ["H7_XAUUSD_eod"], "G9_XAU": ["G9_XAUUSD_eod"], "G9_XAG": ["G9_XAGUSD_eod"],
         "v3": ["H7_XAUUSD_eod", "G9_XAUUSD_eod"], "v4": ["H7_XAUUSD_eod", "G9_XAUUSD_eod"],
         "v4+ag": ["H7_XAUUSD_eod", "G9_XAUUSD_eod", "G9_XAGUSD_eod"]}
STOP_K = {"H7_XAU": 2.0, "G9_XAU": 2.0, "G9_XAG": 2.0, "v3": 2.0, "v4": 1.4, "v4+ag": 1.4}
#: v4+ag: silver at stop 2.0 (A3 measured it there; silver at 1.4 was never studied)
STOP_K_OVERRIDE = {("v4+ag", "G9_XAGUSD_eod"): 2.0}
LABEL = {"H7_XAU": "COMPONENT-VALIDATED", "G9_XAU": "COMPONENT-VALIDATED", "G9_XAG": "COMPONENT-VALIDATED",
         "v3": "POLICY-EXPOSED", "v4": "POLICY-EXPOSED", "v4+ag": "UNTESTED"}


def _pref(sym):
    """(close, time) of the last stored FTMO daily bar (history_store, the repo's one history reader)."""
    import history_store as HS
    doc, _path = HS.read_doc(sym, "1D", os.path.join(ROOT, "data", "history", "ftmo"))
    c = doc["candles"][-1]
    return c["close"], c["time"]


def specs_for(symbols, profile="ftmo_demo_2026_09_relspread"):
    import real_costs as RC
    out, prov = {}, {}
    for s in symbols:
        d = RC.spec(profile, s)
        p, at = _pref(s)
        out[s] = Spec(float(d["contract_size"]), float(d["volume_min"]), float(d["volume_step"]), float(d["volume_max"]), p)
        prov[s] = {"pref": p, "pref_time": at, "contract": d["contract_size"], "volume_min": d["volume_min"],
                   "volume_step": d["volume_step"], "volume_max": d["volume_max"]}
    return out, prov


def build_rows(cache=None):
    """{(component, stop_k): [rows with parsed times and server-day keys]} -- book_sim.trades, cached to a pickle."""
    if cache and os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    BS = _load("book_sim", "scripts/research/book_sim.py")
    need = {(c, STOP_K_OVERRIDE.get((b, c), STOP_K[b])) for b, cs in BOOKS.items() for c in cs}
    out = {}
    for c, k in sorted(need):
        rows = []
        for t in BS.trades(*BS.COMPONENTS[c], stop_k=k):
            e = datetime.datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00"))
            x = datetime.datetime.fromisoformat(t["exit_time"].replace("Z", "+00:00"))
            rows.append({"c": c, "symbol": t["symbol"], "entry": e, "exit": x, "day": t["server_day"], "R": t["R"],
                         "cost_R": t["cost_R"], "stop_bp": t["stop_bp"], "adv_path_R": t["adv_path_R"]})
        out[(c, k)] = rows
    if cache:
        pickle.dump(out, open(cache, "wb"))
    return out


def book_days(rows_by_ck, book):
    """{server_day (date): [rows]} for a book."""
    by = collections.defaultdict(list)
    for c in BOOKS[book]:
        k = STOP_K_OVERRIDE.get((book, c), STOP_K[book])
        for t in rows_by_ck[(c, k)]:
            by[datetime.date.fromisoformat(t["day"])].append(t)
    return by


def haircut_shift(rows_by_ck, book, haircut, since=None):
    """{component: haircut x its mean R} (as pass_policy.prepare: every component's mean R cut by that share). The mean is
    taken over the SAME span the bootstrap samples (`since` on): with the full-history mean, "edge x 0" on the 2018+ days
    was in fact a negative edge (G9 gold's 2018+ mean R is lower than its 2004+ mean)."""
    out = {}
    for c in BOOKS[book]:
        k = STOP_K_OVERRIDE.get((book, c), STOP_K[book])
        out[c] = haircut * statistics.mean(t["R"] for t in rows_by_ck[(c, k)] if since is None or t["day"] >= str(since))
    return out


# ---------------------------------------------------------------------------------------------------------------- runs
#: "cap" and "cap_base" are read only when "floor_cap" is in "mode": one mode label per cap and base, "floor_cap@0.02" (base
#: "current", the label of the first cap run) or "floor_cap@0.02/initial" (the fixed amount). The CLI overrides any key.
GRID = {"r": (0.005, 0.01), "b0": (5_000.0, 100_000.0), "mode": ("skip", "floor"), "cap": (0.02,), "cap_base": ("current",),
        "edge": (1.0, 0.5, 0.0)}
PATHS, HORIZON_DAYS, SEED = 1000, 5 * WEEKDAYS_PER_YEAR, 20261004
POST_DISCOVERY_FROM = datetime.date(2018, 2, 26)        # the latest discovery/confirmation split of the components (XAG)
SURVIVE_BLOWN, SURVIVE_PAIN, BEATS_SHARE = 0.01, 0.05, 0.80


def _weekdays(lo, hi):
    d, out = lo, []
    while d <= hi:
        if d.weekday() < 5:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out


def common_span(rows_by_ck):
    firsts = [min(datetime.date.fromisoformat(t["day"]) for t in v) for v in rows_by_ck.values()]
    lasts = [max(datetime.date.fromisoformat(t["day"]) for t in v) for v in rows_by_ck.values()]
    return max(firsts), min(lasts)


def check_grid(grid):
    """ValueError before any work if `run` would fail late: the ranking reads edge x 0.5 (design §4) after the bootstrap,
    and every floor_cap account needs r <= cap <= 5 % and a known cap base."""
    if 0.5 not in grid["edge"]:
        raise ValueError(f"edge grid {tuple(grid['edge'])} lacks 0.5: the ranking (design §4) reads edge x 0.5")
    if set(grid["mode"]) - set(MODES):
        raise ValueError(f"unknown mode in {tuple(grid['mode'])}")
    if "floor_cap" in grid["mode"]:
        for r in grid["r"]:
            for cap in grid["cap"]:
                for base in grid.get("cap_base", ("current",)):
                    Account(r=r, mode="floor_cap", min_lot_cap=cap, min_lot_cap_base=base)
    return grid


def mode_labels(grid=None):
    """The grid's sizing modes as labels; floor_cap expands to one label per cap and base: "floor_cap@0.02" (base
    "current", unchanged from the first cap run) and "floor_cap@0.02/initial" (the fixed amount cap x b0)."""
    grid = grid or GRID
    caps = [f"floor_cap@{c}" + ("" if b == "current" else f"/{b}")
            for c in grid["cap"] for b in grid.get("cap_base", ("current",))]
    return [lab for m in grid["mode"] for lab in (caps if m == "floor_cap" else [m])]


def account_for(b0, r, label):
    mode, _, cap = label.partition("@")
    cap, _, base = cap.partition("/")
    return Account(b0=b0, r=r, mode=mode, **({"min_lot_cap": float(cap)} if cap else {}),
                   **({"min_lot_cap_base": base} if base else {}))


def cells(grid=None):
    grid = grid or GRID
    for book in BOOKS:
        for r in grid["r"]:
            for b0 in grid["b0"]:
                for mode in mode_labels(grid):
                    for edge in grid["edge"]:
                        yield (book, r, b0, mode, edge)


_W = {}


def _init(cache, lo, hi, grid=None):
    grid = grid or GRID
    rows = build_rows(cache)
    syms = sorted({t["symbol"] for v in rows.values() for t in v})
    specs, _ = specs_for(syms)
    _W.update(rows=rows, specs=specs, days={b: book_days(rows, b) for b in BOOKS}, grid=grid,
              shift={(b, e): haircut_shift(rows, b, 1.0 - e, since=lo) for b in BOOKS for e in grid["edge"]},
              weekdays=_weekdays(lo, hi))


def _paths(seeds):
    VS = _load("vol_schedule", "scripts/research/vol_schedule.py")
    out = collections.defaultdict(list)
    for sd in seeds:
        src = VS.sample_days(_W["weekdays"], random.Random(sd), HORIZON_DAYS)
        for cell in cells(_W["grid"]):
            book, r, b0, mode, edge = cell
            by = _W["days"][book]
            sp = {s: _W["specs"][s] for s in {t["symbol"] for v in by.values() for t in v}}
            days = [(i, by.get(d, [])) for i, d in enumerate(src)]
            m = replay(days, account_for(b0, r, mode), sp, _W["shift"][(book, edge)])
            out[cell].append((m["blown"] is not None, m["stalled"] is not None, m["max_dd"], m["terminal_multiple"], m["cagr"],
                              m["taken"], m["risk_taken_mean"], m["taken_above_r"], m["taken_above_cap"], m["risk_taken_max"]))
    return dict(out)


def bootstrap(cache, lo, hi, paths=PATHS, jobs=10, grid=None):
    seeds = [SEED + i for i in range(paths)]
    chunks = [seeds[i::jobs] for i in range(jobs)]
    acc = collections.defaultdict(list)
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs, initializer=_init, initargs=(cache, lo, hi, grid)) as ex:
        for part in ex.map(_paths, chunks):
            for cell, v in part.items():
                acc[cell].extend(v)
    # restore seed order so every cell's i-th entry is the same sampled path (paired comparisons)
    order = [s for ch in chunks for s in ch]
    rank = {s: i for i, s in enumerate(order)}
    perm = sorted(range(len(order)), key=lambda i: order[i])
    return {cell: [v[i] for i in perm] for cell, v in acc.items()}, rank


def summarise_cell(v, pain=0.5):
    """v: per path (blown, stalled, max_dd, terminal, cagr, taken, risk_taken_mean, taken_above_r[, taken_above_cap,
    risk_taken_max]). The trade shares are pooled over every trade of every path. The four cap keys (added with the cap
    base; extra keys only) need the 10-field form: the share of trades above the current-balance cap, the share of paths
    with at least one, and the largest risk taken (max over paths, and the p95 of the per-path maxima)."""
    q = lambda xs, p: sorted(xs)[min(len(xs) - 1, int(p * len(xs)))]
    term = [x[3] for x in v]
    n = sum(x[5] for x in v)
    out = {"p_blown": statistics.mean(x[0] for x in v), "p_stalled": statistics.mean(x[1] for x in v),
           "p_dd_ge_25": statistics.mean(x[2] >= 0.25 for x in v), "p_dd_ge_pain": statistics.mean(x[2] >= pain for x in v),
           "terminal_p5": q(term, 0.05), "terminal_p50": q(term, 0.5), "terminal_p95": q(term, 0.95),
           "median_cagr": statistics.median(x[4] for x in v), "p95_max_dd": q([x[2] for x in v], 0.95),
           "trades_taken": n, "taken_above_r_share": sum(x[7] for x in v) / n if n else None,
           "risk_taken_mean": sum(x[5] * x[6] for x in v if x[5]) / n if n else None}
    if v and all(len(x) >= 10 for x in v):
        mx = [x[9] for x in v if x[9] is not None]
        out.update({"taken_above_cap_share": sum(x[8] for x in v) / n if n else None,
                    "p_any_above_cap": statistics.mean(x[8] > 0 for x in v),
                    "risk_taken_max": max(mx) if mx else None, "risk_taken_max_p95": q(mx, 0.95) if mx else None})
    return out


def rank_within_label(boot, b0, mode, grid=None):
    """Design §4: survivors at edge x 0.5, best r per setup, then paired growth comparisons within each label."""
    best = {}
    for book in BOOKS:
        ok = []
        for r in (grid or GRID)["r"]:
            s = summarise_cell(boot[(book, r, b0, mode, 0.5)])
            if s["p_blown"] <= SURVIVE_BLOWN and s["p_dd_ge_pain"] <= SURVIVE_PAIN:
                ok.append((s["median_cagr"], r))
        if ok:
            best[book] = max(ok)[1]
    out = {}
    for label in sorted(set(LABEL.values())):
        members = [b for b in BOOKS if LABEL[b] == label and b in best]
        wins = {}
        for a in members:
            for b in members:
                if a != b:
                    ca = [x[4] for x in boot[(a, best[a], b0, mode, 0.5)]]
                    cb = [x[4] for x in boot[(b, best[b], b0, mode, 0.5)]]
                    wins[(a, b)] = statistics.mean(x > y for x, y in zip(ca, cb))
        order = sorted(members, key=lambda a: (-sum(wins.get((a, b), 0) >= BEATS_SHARE for b in members),
                                               summarise_cell(boot[(a, best[a], b0, mode, 0.5)])["p95_max_dd"]))
        out[label] = {"order": order, "best_r": {b: best[b] for b in members},
                      "paired_win_share": {f"{a} > {b}": w for (a, b), w in wins.items()},
                      "not_surviving": [b for b in BOOKS if LABEL[b] == label and b not in best]}
    return out


def run(out_path, cache, paths=PATHS, jobs=10, grid=None):
    grid = check_grid(grid or GRID)
    code = code_version()
    rows = build_rows(cache)
    lo, hi = common_span(rows)
    syms = sorted({t["symbol"] for v in rows.values() for t in v})
    specs, prov = specs_for(syms)
    res = {"meta": {"script": SCRIPT, "design": DESIGN, "status": "DESCRIPTIVE (labels in design §2)", "code": code,
                    "common_span": [str(lo), str(hi)],
                    "bootstrap": {"paths": paths, "horizon_weekdays": HORIZON_DAYS, "from": str(POST_DISCOVERY_FROM), "to": str(hi),
                                  "block": "vol_schedule.BOOT_BLOCK", "seed": SEED},
                    "account_defaults": dataclasses.asdict(Account()), "grid": grid, "mode_labels": mode_labels(grid),
                    "specs": prov, "labels": LABEL,
                    "stop_k": STOP_K, "stop_k_override": {f"{a}|{b}": v for (a, b), v in STOP_K_OVERRIDE.items()},
                    "cells": len(list(cells(grid)))},
           "historical": {}, "bootstrap": {}, "ranking": {}, "min_lot": {}}
    for book in BOOKS:
        by = book_days(rows, book)
        sp = {s: specs[s] for s in {t["symbol"] for v in by.values() for t in v}}
        for span_name, a in (("common_span", lo), ("post_discovery", POST_DISCOVERY_FROM)):
            days = [(d, by.get(d, [])) for d in _weekdays(a, hi)]
            for r in grid["r"]:
                for b0 in grid["b0"]:
                    for mode in mode_labels(grid):
                        m = replay(days, account_for(b0, r, mode), sp)
                        m["blown"], m["stalled"] = (str(m["blown"]) if m["blown"] else None), (str(m["stalled"]) if m["stalled"] else None)
                        res["historical"][f"{book}|{span_name}|r={r}|b0={int(b0)}|{mode}"] = m
        # B* per component at the median stop since 2024 (design §0)
        for c in BOOKS[book]:
            k = STOP_K_OVERRIDE.get((book, c), STOP_K[book])
            recent = [t["stop_bp"] for t in rows[(c, k)] if t["day"] >= "2024-01-01"]
            s = specs[rows[(c, k)][0]["symbol"]]
            one = statistics.median(recent) / 1e4 * s.pref * s.contract * s.vmin
            res["min_lot"][f"{c}|stop_k={k}"] = {"median_stop_bp_since_2024": statistics.median(recent),
                                                 "min_lot_loss_usd": one, "b_star_r1pct": one / 0.01, "b_star_r05pct": one / 0.005}
    boot, _ = bootstrap(cache, POST_DISCOVERY_FROM, hi, paths, jobs, grid)
    for cell, v in boot.items():
        res["bootstrap"]["|".join(map(str, cell))] = summarise_cell(v)
    for b0 in grid["b0"]:
        for mode in mode_labels(grid):
            res["ranking"][f"b0={int(b0)}|{mode}"] = rank_within_label(boot, b0, mode, grid)
    with open(out_path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(json.dumps(res["ranking"], indent=1)[:3000])
    print(f"wrote {out_path}")


def compare_results(old, new):
    """(compared, differing) over the bootstrap and historical keys two result files share. Each entry is compared on the
    OLD entry's fields only (a newer run may add keys, never change them). Exact equality: same code, same numbers."""
    n, bad = 0, []
    for part in ("bootstrap", "historical"):
        for key, want in old.get(part, {}).items():
            got = new.get(part, {}).get(key)
            if got is None:
                continue
            n += 1
            if any(f not in got or got[f] != v for f, v in want.items()):          # a dropped field differs too
                bad.append(f"{part}|{key}")
    return n, bad


def replay_historical(old, cache):
    """Replays every historical entry of an earlier result file with the CURRENT code: (compared, differing). Refuses when
    the data snapshot differs (common span or specs), since the numbers could then not match for another reason."""
    rows = build_rows(cache)
    lo, hi = common_span(rows)
    specs, prov = specs_for(sorted({t["symbol"] for v in rows.values() for t in v}))
    if [str(lo), str(hi)] != old["meta"]["common_span"] or json.loads(json.dumps(prov, default=str)) != old["meta"]["specs"]:
        raise ValueError("different data snapshot (common span or specs): not comparable")
    n, bad = 0, []
    for key, want in old["historical"].items():
        book, span, r, b0, mode = key.split("|")
        by = book_days(rows, book)
        sp = {s: specs[s] for s in {t["symbol"] for v in by.values() for t in v}}
        days = [(d, by.get(d, [])) for d in _weekdays(lo if span == "common_span" else POST_DISCOVERY_FROM, hi)]
        m = replay(days, account_for(float(b0[len("b0="):]), float(r[len("r="):]), mode), sp)
        m["blown"], m["stalled"] = (str(m["blown"]) if m["blown"] else None), (str(m["stalled"]) if m["stalled"] else None)
        n += 1
        if json.loads(json.dumps({f: m.get(f) for f in want}, default=str)) != want:
            bad.append(f"historical|{key}")
    return n, bad


def check(against, cache, new=None):
    """The reproducibility check of docs/audits/2026-10-04-personal-account.md §5: (1) the current code replays every
    historical entry of `against` exactly; (2) with `new`, every entry both files share is equal. Exit 1 on any difference."""
    old = json.load(open(against))
    n, bad = replay_historical(old, cache)
    print(f"replay of {against} historical entries with the current code: compared {n}, differing {len(bad)}")
    if new:
        n2, bad2 = compare_results(old, json.load(open(new)))
        print(f"{new} vs {against}, shared entries: compared {n2}, differing {len(bad2)}")
        bad += bad2
    for b in bad[:20]:
        print("DIFF", b)
    return 1 if bad else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--cache", required=True, help="pickle of the book_sim rows (built once)")
    r.add_argument("--paths", type=int, default=PATHS)
    r.add_argument("--jobs", type=int, default=10)
    for key, typ, choices in (("r", float, None), ("b0", float, None), ("mode", str, MODES), ("cap", float, None),
                              ("cap_base", str, CAP_BASES), ("edge", float, None)):
        r.add_argument("--" + key.replace("_", "-"), dest=key, type=typ, nargs="+", choices=choices,
                       help=f"grid override (default {GRID[key]})")
    c = sub.add_parser("check", help="replay an earlier result's historical entries; optionally compare two result files")
    c.add_argument("--against", required=True, help="an earlier result JSON")
    c.add_argument("--cache", required=True)
    c.add_argument("--new", help="a later result JSON: its entries shared with --against must be equal")
    a = ap.parse_args()
    if a.cmd == "check":
        sys.exit(check(a.against, a.cache, a.new))
    grid = {k: tuple(getattr(a, k)) if getattr(a, k) else v for k, v in GRID.items()}
    try:
        check_grid(grid)
    except ValueError as e:
        ap.error(str(e))
    run(a.out, a.cache, a.paths, a.jobs, grid)


if __name__ == "__main__":
    main()
