#!/usr/bin/env python3
"""Point-in-time H7 / G9 on any 5m bar series and any server-day clock: a library, no CLI, no market-data I/O.

It writes ONE copy of the rule text of docs/plans/2026-10-04-edge-cx-ftmo-crypto-preregistration.md §1 ([CX-P1]) for the
drafts that apply it to data no test has read:
  docs/plans/2026-10-04-oil-trend-transfer-preregistration-DRAFT.md      (OIL: FTMO crude-oil CFDs)
  docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md (VC-X: FTMO crypto CFDs)
Callers pass candles ({"time": ISO "...Z", "open", "high", "low", "close"}) and a server zone. Nothing here reads an
outcome unless a caller asks for `outcome`, `stop_trade` or `placebo_table`.

Rules ([CX-P1] §1; MOM_DAYS and VB_K are F3's and F4's own constants, scripts/research/edge_f3.py:28,
scripts/research/edge_f4.py:35 -- never re-chosen):
* A server day QUALIFIES as history iff it has >= `min_bars` distinct on-grid 5m bars (second 0, minute % 5 == 0). The
  caller fixes `min_bars` before any read (crypto: 230 = 0.8 x 288; a 5-day market: 0.8 x its regular session's bars).
* Day D is ELIGIBLE iff its previous day qualifies and >= MOM_DAYS + 1 qualifying days precede D. "Previous day" is the
  calendar day D - 1 (`prev_rule="calendar"`, a 7-day market, [CX-P1]) or the latest earlier server day that has any bar
  (`prev_rule="trading"`, a 5-day market: Monday's previous day is Friday). D's own bar count is never consulted.
* MOM20 = last close of the previous qualifying day / last close of the 21st previous qualifying day - 1.
  sigma_5m = RMS of within-day 5m log returns over the previous VOL_DAYS qualifying days.
* H7: the first 5m close beyond the previous day's high (low) when MOM20 > 0 (< 0). G9: the first 5m close beyond
  open(D) +/- VB_K x the previous day's range, either side. Continuation.
* Entry at the next bar's OPEN; an event whose entry bar is not in D is dropped. Exit at the CLOSE of D's last bar (or D's
  last available bar; `exit_slot` is in every row so a reader can count short days). One event per (D, rule).
* Bars held nb = exit index - entry index + 1 (the census / book_sim convention, scripts/research/edge_census.py:395,
  scripts/research/book_sim.py:59)."""
import bisect
import collections
import datetime
import math
import statistics

MOM_DAYS = 20                     # == edge_f3.MOM_DAYS (asserted in scripts/tests/test_pit_trend.py)
VOL_DAYS = 20                     # == edge_census.VOL_DAYS
VB_K = 0.5                        # == edge_f4.VB_K
RULES = ("H7", "G9")
BAR = datetime.timedelta(minutes=5)
UTC = datetime.timezone.utc


def _parse(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00"))


class Bars:
    """One symbol's 5m bars in [start, end) (ISO strings, UTC), de-duplicated by time (the last copy wins), with server
    dates under `zone` (an aware tzinfo: the server clock)."""

    def __init__(self, sym, candles, zone, start=None, end=None):
        by_t = {}
        for b in candles:
            t = b["time"]
            if (start is None or t >= start) and (end is None or t < end):
                by_t[t] = b
        c = [by_t[t] for t in sorted(by_t)]
        self.sym, self.zone = sym, zone
        self.T = [b["time"] for b in c]
        self.O = [float(b["open"]) for b in c]
        self.H = [float(b["high"]) for b in c]
        self.L = [float(b["low"]) for b in c]
        self.C = [float(b["close"]) for b in c]
        self.dt = [_parse(t) for t in self.T]
        self.local = [d.astimezone(zone) for d in self.dt]
        self.sday = [d.date() for d in self.local]
        self.day_rows = collections.OrderedDict()
        for i, d in enumerate(self.sday):
            self.day_rows.setdefault(d, []).append(i)


def slot(b, i):
    """Server minutes from midnight of bar i's open."""
    t = b.local[i]
    return t.hour * 60 + t.minute


def on_grid(dt):
    return dt.second == 0 and dt.microsecond == 0 and dt.minute % 5 == 0


def qualifying(b, min_bars):
    """{server day: (high, low, last close, mean squared within-day 5m log return, distinct on-grid bars)} for every day
    with >= min_bars distinct on-grid bars."""
    out = {}
    for d, rows in b.day_rows.items():
        slots = {slot(b, j) for j in rows if on_grid(b.dt[j])}
        if len(slots) < min_bars:
            continue
        rs = [math.log(b.C[j] / b.C[j - 1]) for j in rows[1:] if b.C[j - 1] > 0 and b.C[j] > 0]
        out[d] = (max(b.H[j] for j in rows), min(b.L[j] for j in rows), b.C[rows[-1]],
                  sum(r * r for r in rs) / len(rs) if rs else 0.0, len(slots))
    return out


def context(b, min_bars, prev_rule="calendar"):
    """{eligible server day D: inputs known at D's first bar}. Only D's first bar's OPEN is read from D itself (G9's
    open(D)); D's bar count is never consulted."""
    if prev_rule not in ("calendar", "trading"):
        raise ValueError(f"prev_rule must be 'calendar' or 'trading', not {prev_rule!r}")
    info = qualifying(b, min_bars)
    q = sorted(info)
    days = list(b.day_rows)
    out = {}
    for n, d in enumerate(days):
        if prev_rule == "calendar":
            y = d - datetime.timedelta(days=1)
        else:
            y = days[n - 1] if n > 0 else None
        if y is None or y not in info:
            continue
        k = bisect.bisect_left(q, d)                   # qualifying days strictly before D; q[k-1] == y
        if k < MOM_DAYS + 1 or q[k - 1] != y:
            continue
        mom = info[q[k - 1]][2] / info[q[k - 1 - MOM_DAYS]][2] - 1.0
        sig = math.sqrt(sum(info[x][3] for x in q[k - VOL_DAYS:k]) / VOL_DAYS)
        hi, lo = info[y][0], info[y][1]
        out[d] = {"prev_day": y, "prev_high": hi, "prev_low": lo, "prev_range": hi - lo, "mom": mom,
                  "mom_sign": (mom > 0) - (mom < 0), "sigma": sig, "open": b.O[b.day_rows[d][0]],
                  "weekday": d.weekday()}
    return out


def _first(b, rule, d, c, test):
    """The day's event from its FIRST qualifying close; None when that close's next bar is not in D."""
    rows = b.day_rows[d]
    for i in rows:
        side = test(b.C[i])
        if side:
            e = i + 1
            if e >= len(b.C) or b.sday[e] != d:
                return None
            return {"rule": rule, "day": d, "i": i, "side": side, "entry_i": e, "slot": slot(b, e),
                    "weekday": c["weekday"], "mom_sign": c["mom_sign"]}
    return None


def ev_h7(b, ctx):
    out = []
    for d in b.day_rows:
        c = ctx.get(d)
        if c is None or not c["mom_sign"]:
            continue
        if c["mom_sign"] > 0:
            ev = _first(b, "H7", d, c, lambda x, h=c["prev_high"]: 1 if x > h else 0)
        else:
            ev = _first(b, "H7", d, c, lambda x, l=c["prev_low"]: -1 if x < l else 0)
        if ev:
            out.append(ev)
    return out


def ev_g9(b, ctx):
    out = []
    for d in b.day_rows:
        c = ctx.get(d)
        if c is None:
            continue
        hi, lo = c["open"] + VB_K * c["prev_range"], c["open"] - VB_K * c["prev_range"]
        ev = _first(b, "G9", d, c, lambda x, hi=hi, lo=lo: 1 if x > hi else (-1 if x < lo else 0))
        if ev:
            out.append(ev)
    return out


DETECTORS = {"H7": ev_h7, "G9": ev_g9}


def events(b, ctx):
    return {rule: DETECTORS[rule](b, ctx) for rule in RULES}


def exit_index(b, ev):
    return b.day_rows[ev["day"]][-1]


# ------------------------------------------------------------------------------------------------ outcomes (a read only)
def outcome(b, ev, ctx, cost=None):
    """The [CX-P1] §4 row of one event: r = side x (C[exit] / O[entry] - 1), scale = sigma x sqrt(nb). `cost(t_in, t_out,
    stat)` returns the round-trip cost as a fraction of price (None: cost 0, flagged)."""
    e, x = ev["entry_i"], exit_index(b, ev)
    c = ctx[ev["day"]]
    nb = x - e + 1
    r = ev["side"] * (b.C[x] / b.O[e] - 1.0)
    rt = cost(b.dt[e], b.dt[x], "median") if cost else 0.0
    rt90 = cost(b.dt[e], b.dt[x], "p90") if cost else 0.0
    return {"symbol": b.sym, "rule": ev["rule"], "date": ev["day"].isoformat(), "year": ev["day"].year,
            "side": ev["side"], "slot": ev["slot"], "weekday": ev["weekday"], "mom_sign": ev["mom_sign"],
            "r": r, "cost": rt, "cost90": rt90, "costed": cost is not None, "scale": c["sigma"] * math.sqrt(nb),
            "sigma": c["sigma"], "nb": nb, "exit_slot": slot(b, x), "entry_time": b.T[e], "exit_time": b.T[x]}


def stop_trade(b, ev, ctx, k, cost=None):
    """The book's trade mechanics (scripts/research/book_sim.py:38-82): protective stop k x sigma_5m x sqrt(nb) from the
    entry open, checked bar by bar from the entry bar (a bar opening beyond the stop fills at its open), else exit at the
    close of D's last bar. R_gross / R_net per unit of stop distance."""
    e, x = ev["entry_i"], exit_index(b, ev)
    c = ctx[ev["day"]]
    side, px = ev["side"], b.O[e]
    dist = k * c["sigma"] * math.sqrt(x - e + 1) * px
    stop = px - side * dist
    exit_px, how, j_exit = b.C[x], "time", x
    for j in range(e, x + 1):
        if (b.L[j] <= stop) if side > 0 else (b.H[j] >= stop):
            exit_px = (min(stop, b.O[j]) if side > 0 else max(stop, b.O[j])) if j > e else stop
            how, j_exit = "stop", j
            break
    rt = cost(b.dt[e], b.dt[j_exit], "median") if cost else 0.0
    gross = side * (exit_px - px)
    return {"symbol": b.sym, "rule": ev["rule"], "day": ev["day"].isoformat(), "side": side, "k": k,
            "R_gross": gross / dist, "R_net": (gross - rt * px) / dist, "cost_R": rt * px / dist,
            "stop_bp": dist / px * 1e4, "nb_planned": x - e + 1, "exit": how, "sigma": c["sigma"],
            "entry_time": b.T[e], "exit_time": b.T[j_exit]}


def placebo_table(b, ctx, days):
    """{(entry slot, weekday, MOM20 sign): mean C[D's last bar] / O[slot bar] - 1} over the eligible `days` ([CX-P1] §4;
    unsigned, signed by the trade's side later)."""
    acc = collections.defaultdict(lambda: [0.0, 0])
    for d in days:
        c = ctx.get(d)
        if c is None or d not in b.day_rows:
            continue
        rows = b.day_rows[d]
        last = rows[-1]
        for e in rows:
            a = acc[(slot(b, e), c["weekday"], c["mom_sign"])]
            a[0] += b.C[last] / b.O[e] - 1.0
            a[1] += 1
    return {k: v[0] / v[1] for k, v in acc.items() if v[1]}


def with_excess(rows, placebo):
    """Rows with `excess` = r - side x placebo; rows without a placebo cell are returned separately (counted)."""
    kept, missing = [], 0
    for r in rows:
        p = placebo.get((r["slot"], r["weekday"], r["mom_sign"]))
        if p is None:
            missing += 1
            continue
        kept.append(dict(r, excess=r["r"] - r["side"] * p))
    return kept, missing


# ------------------------------------------------------------------------------------------------ costs from a spec export
def server_stamp_to_utc(stamp, zone):
    """'2022.07.06 08:00' in server time -> aware UTC datetime."""
    d = datetime.datetime.strptime(stamp, "%Y.%m.%d %H:%M")
    return d.replace(tzinfo=zone).astimezone(UTC)


def price_ref(m15_candles, spec, zone):
    """Median M15 close over the spec's spread-recording window: the relative-spread scaling of
    scripts/real_costs.py:426 (price_ref), computed here from the candles the caller passes."""
    rec = spec.get("recorded_spread_m15") or {}
    a, z = rec.get("first_bar_server"), rec.get("last_bar_server")
    if not a or not z:
        raise ValueError(f"{spec.get('symbol')}: recorded_spread_m15 has no window")
    lo, hi = server_stamp_to_utc(a, zone), server_stamp_to_utc(z, zone)
    closes = [float(c["close"]) for c in m15_candles if lo <= _parse(c["time"]) <= hi]
    if not closes:
        raise ValueError(f"{spec.get('symbol')}: no M15 close inside the spread-recording window")
    return statistics.median(closes)


class SpecCost:
    """Round-trip cost as a fraction of price from an ExportSymbolSpec JSON: per leg half the recorded spread at the leg's
    table bucket ((server hour - export offset) mod 24, the scripts/real_costs.py:314 `table_hour` frame), scaled by
    `price_ref`, plus `c_sym` (commission per side, a fraction of notional). A bucket without data falls back to the
    overall statistic (scripts/real_costs.py:342), counted in `fallbacks`."""

    def __init__(self, spec, price_ref_value, c_sym, zone):
        off = spec.get("_server_utc_offset_sec_now")
        if not isinstance(off, int) or isinstance(off, bool) or abs(off - 3600 * round(off / 3600)) > 60:
            raise ValueError(f"{spec.get('symbol')}: export offset {off!r} is not a whole hour")
        if c_sym is None:
            raise ValueError(f"{spec.get('symbol')}: no commission c_sym (a symbol without c_sym cannot be screened in)")
        self.offset_h = round(off / 3600)
        self.point = float(spec["point"])
        self.ref = float(price_ref_value)
        self.c_sym = float(c_sym)
        self.zone = zone
        rec = spec.get("recorded_spread_m15") or {}
        self.by_h = {row["h"]: row for row in rec.get("by_utc_hour") or ()}
        self.overall = {s: rec.get(f"{s}_points") for s in ("median", "p90")}
        self.fallbacks = 0

    def bucket(self, t):
        return (t.astimezone(self.zone).hour - self.offset_h) % 24

    def spread_rel(self, bucket, stat="median"):
        row = self.by_h.get(bucket)
        if row is not None and row.get("n", 0) > 0 and row.get(stat) not in (None, -1):
            pts = row[stat]
        else:
            pts = self.overall.get(stat)
            if pts is None or pts < 0:
                raise ValueError(f"no recorded {stat} spread for bucket {bucket} and no fallback")
            self.fallbacks += 1
        return pts * self.point / self.ref

    def leg(self, t, stat="median"):
        return 0.5 * self.spread_rel(self.bucket(t), stat) + self.c_sym

    def __call__(self, t_in, t_out, stat="median"):
        return self.leg(t_in, stat) + self.leg(t_out, stat)


def session_bars(sessions_trade):
    """Regular weekday session length in 5m bars from a symbol-list `sessions_trade` (Mon-Fri windows must agree)."""
    lens = set()
    for row in sessions_trade:
        if row["dow"] not in (1, 2, 3, 4, 5):
            continue
        n = 0
        for a, z in row["windows"]:
            ha, ma = map(int, a.split(":"))
            hz, mz = map(int, z.split(":"))
            n += ((hz * 60 + mz) - (ha * 60 + ma)) // 5
        lens.add(n)
    if len(lens) != 1:
        raise ValueError(f"weekday sessions differ ({sorted(lens)}); min_bars needs one regular session")
    return lens.pop()
