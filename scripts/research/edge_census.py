#!/usr/bin/env python3
"""Edge census (docs/plans/2026-10-02-edge-census-preregistration.md): do simple, low-parameter market primitives carry a
forward-return signal on the FTMO CFDs, net of the broker's real spread, on DEVELOPMENT data only (< 2024-03-01)?

    python3 scripts/research/edge_census.py run    --out docs/audits/2026-10-02-edge-census.json
    python3 scripts/research/edge_census.py report --json docs/audits/2026-10-02-edge-census.json --out docs/audits/2026-10-02-edge-census.md

Design (every choice is pre-registered; nothing here is tuned on outcomes):
* Data: FTMO-Demo 5m bid bars (data/history/ftmo), the analysis-allowlist CFDs only (docs/architecture/instruments.json),
  bars strictly before DEV_CUTOFF. Only DENSE server days (>= 80 % of the symbol's median bars per day) are used.
* Split per symbol: DISCOVERY = the first 60 % of its dense days, CONFIRMATION = the last 40 % (dates only).
* An event is detected on CLOSED bars only (signal bar i); the trade enters at bar i+1 OPEN (or, for E5, at the limit price
  on the touch bar) and exits at the CLOSE h bars after entry. Events whose exit would fall on another server day (the
  broker's rollover) are skipped and counted. One event per (symbol, server day, event, side): the first.
* Outcome per event: signed forward return s*r (s = +1 long / -1 short in the hypothesis' direction), in bp and in
  volatility units z = s*r / (sigma_5m * sqrt(h)), sigma_5m = RMS of 5m log returns over the previous 20 dense days (PIT).
* Placebo: the mean s*r of the SAME symbol, SAME server minute-of-day, SAME h, SAME direction over every dense day of the
  same period. excess = s*r - placebo. This removes intraday seasonality.
* Cost: one full relative spread per round trip (half at the entry UTC hour, half at the exit hour), from the broker's
  recorded spread (`real_costs.spread_price`) divided by its price_ref (the `ftmo_demo_2026_09_relspread` scaling).
  p90 spread for the stress line.
* Statistics: CR1 cluster-robust standard error by UTC date (cross-symbol same-day dependence), Student-t with G-1 df.

Read-only on repo data. Nothing here touches the fund-search, the live path or any account."""
import argparse
import bisect
import collections
import datetime
import json
import math
import os
import statistics
import sys
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

DEV_CUTOFF = "2024-03-01T00:00:00Z"
HIST_ROOT = os.path.join(ROOT, "data", "history", "ftmo")
COST_PROFILE = "ftmo_demo_2026_09_relspread"
PROVIDER = "mt5_bridge_ftmo"
METALS = ("XAUUSD", "XAGUSD")
INDICES = ("US500", "US30", "USTEC", "DE40", "FRA40", "AUS200")
GROUPS = {"metals": METALS, "indices": INDICES}
HORIZONS = (6, 12, 24)                 # bars of 5m: 30 / 60 / 120 minutes
DENSE_SHARE = 0.80
DISCOVERY_SHARE = 0.60
VOL_DAYS = 20
FDR_Q = 0.10
CONFIRM_P = 0.05
MIN_SYMBOL_EVENTS = 20
ASIA_UTC = (0, 7)                      # Asia range: 00:00-07:00 UTC
EU_US_UTC = (7, 16)                    # sweep / break window after Asia
DISPLACEMENT_BODY = 0.6                # E5/E9 thresholds: fixed here, never tuned
DISPLACEMENT_RANGE_X = 1.5
BIG_BAR_RANGE_X = 3.0
BIG_BAR_BODY = 0.7
FVG_TOUCH_BARS = 24
OPEN_LOCAL = {"US500": ("America/New_York", 9, 30), "US30": ("America/New_York", 9, 30),
              "USTEC": ("America/New_York", 9, 30), "DE40": ("Europe/Berlin", 9, 0),
              "FRA40": ("Europe/Paris", 9, 0), "AUS200": ("Australia/Sydney", 10, 0)}
CLOSE_LOCAL = {"US500": (16, 0), "US30": (16, 0), "USTEC": (16, 0), "DE40": (17, 30), "FRA40": (17, 30),
               "AUS200": (16, 0)}
ORB_BARS = 3                           # 15-minute opening range
ORB_DEADLINE_MIN = 150                 # first break within 2.5 h of the open

EVENTS = {
    "E1_prev_day_sweep_reclaim": "bar trades beyond the previous server day's high (low) and CLOSES back inside; "
                                 "direction: reversal (short after a high sweep, long after a low sweep)",
    "E2_prev_day_acceptance": "first bar of the day to CLOSE beyond the previous day's high (low); direction: continuation",
    "E3_asia_sweep_reclaim": "07-16 UTC bar trades beyond the 00-07 UTC range high (low) and closes back inside; reversal",
    "E4_asia_breakout": "07-16 UTC first bar to close beyond the 00-07 UTC range; continuation",
    "E5_fvg_retrace": "3-bar FVG whose middle bar is a displacement (body >= 0.6 range, range >= 1.5 x 20-bar median); "
                      "first retrace to the gap's near edge within 24 bars, filled at that edge; continuation",
    "E6_opening_range_breakout": "indices: first bar to close beyond the 15-min cash-open range within 2.5 h; continuation",
    "E7_intraday_momentum": "indices: sign of the return from the previous cash close to 30 min after the open; trade it "
                            "from 30 min before the close to the close (Gao, Han, Li, Zhou 2018)",
    "E9_big_bar": "bar range >= 3 x 48-bar median and body >= 0.7 range; continuation from the next open",
}
#: (event, group, horizons) -- THE family. E6 and E7 exist for indices only; E7 has its own fixed horizon (30 min).
FAMILY = ([(e, g, h) for e in ("E1_prev_day_sweep_reclaim", "E2_prev_day_acceptance", "E3_asia_sweep_reclaim",
                               "E4_asia_breakout", "E5_fvg_retrace", "E9_big_bar")
           for g in GROUPS for h in HORIZONS]
          + [("E6_opening_range_breakout", "indices", h) for h in HORIZONS]
          + [("E7_intraday_momentum", "indices", 6)])


# ------------------------------------------------------------------------------------------------ data
class Series:
    """One symbol's dense development 5m bars with their server date and UTC/local helpers."""

    def __init__(self, sym, candles, zone):
        cut = DEV_CUTOFF
        c = [b for b in candles if b["time"] < cut]
        self.sym = sym
        self.T = [b["time"] for b in c]
        self.O = [b["open"] for b in c]
        self.H = [b["high"] for b in c]
        self.L = [b["low"] for b in c]
        self.C = [b["close"] for b in c]
        self.dt = [datetime.datetime.fromisoformat(t.replace("Z", "+00:00")) for t in self.T]
        self.sday = [d.astimezone(zone).date() for d in self.dt]
        per_day = collections.Counter(self.sday)
        full = [v for v in per_day.values() if v >= 50]
        med = statistics.median(full) if full else 0
        self.dense_days = sorted(d for d, v in per_day.items() if v >= DENSE_SHARE * med)
        dset = set(self.dense_days)
        # PIT: whether a day is dense needs the WHOLE day, so a detector may only use the PREVIOUS server day's density
        # (known at the day's start). `dense` (same day) is for periods, placebo and volatility history, never for a decision.
        self.dense = [d in dset for d in self.sday]
        days = sorted(per_day)
        prev = {d: (days[k - 1] in dset) for k, d in enumerate(days) if k > 0}
        self.prev_dense = [prev.get(d, False) for d in self.sday]
        k = int(len(self.dense_days) * DISCOVERY_SHARE)
        self.split_day = self.dense_days[k] if self.dense_days else datetime.date.max   # first confirmation day
        # day index ranges
        self.day_rows = collections.OrderedDict()
        for i, d in enumerate(self.sday):
            self.day_rows.setdefault(d, []).append(i)
        self._vol = self._vol_by_day()

    def period(self, i):
        return "discovery" if self.sday[i] < self.split_day else "confirmation"

    def _vol_by_day(self):
        """sigma_5m for each dense day = RMS of 5m log returns over the previous VOL_DAYS dense days (PIT: prior days only)."""
        ms = {}
        for d, rows in self.day_rows.items():
            rs = [math.log(self.C[j] / self.C[j - 1]) for j in rows if j > 0 and self.sday[j - 1] == d
                  and self.C[j - 1] > 0 and self.C[j] > 0]
            if rs:
                ms[d] = sum(r * r for r in rs) / len(rs)
        out, hist = {}, []
        for d in self.dense_days:
            if len(hist) >= VOL_DAYS:
                out[d] = math.sqrt(sum(hist[-VOL_DAYS:]) / VOL_DAYS)
            if d in ms:
                hist.append(ms[d])
        return out

    def sigma(self, i):
        return self._vol.get(self.sday[i])


def load(sym):
    import history_store as HS
    import real_costs as RC
    doc, _ = HS.read_doc(sym, "5m", root=HIST_ROOT)
    if doc is None:
        raise SystemExit(f"no 5m history for {sym} under {HIST_ROOT}")
    return Series(sym, doc["candles"], RC.server_zone(PROVIDER)[1])


# ------------------------------------------------------------------------------------------------ events
def _first_per_day(events):
    """Keep the first event per (server day, side)."""
    seen, out = set(), []
    for ev in events:
        k = (ev["day"], ev["side"])
        if k not in seen:
            seen.add(k)
            out.append(ev)
    return out


def _ev(s, i, side, entry_i=None, entry_px=None, fixed_exit=None):
    """An event signalled at the CLOSE of bar i. Entry at bar i+1's OPEN unless `entry_i`/`entry_px` say otherwise."""
    return {"i": i, "day": s.sday[i], "side": side, "entry_i": i + 1 if entry_i is None else entry_i,
            "entry_px": entry_px, "fixed_exit": fixed_exit}


def prev_day_levels(s):
    """{server day: (prev dense day's high, low)} -- the previous DENSE server day's range, known at the day's start."""
    out, prev = {}, None
    for d, rows in s.day_rows.items():
        if prev is not None:
            out[d] = prev
        if s.dense[rows[0]]:
            prev = (max(s.H[j] for j in rows), min(s.L[j] for j in rows))
    return out


def ev_prev_day(s, kind):
    lv = prev_day_levels(s)
    out = []
    for d, rows in s.day_rows.items():
        if d not in lv or not s.prev_dense[rows[0]]:
            continue
        ph, pl = lv[d]
        for i in rows:
            if kind == "sweep":
                if s.H[i] > ph and s.C[i] < ph:
                    out.append(_ev(s, i, -1))
                if s.L[i] < pl and s.C[i] > pl:
                    out.append(_ev(s, i, +1))
            else:
                if s.C[i] > ph:
                    out.append(_ev(s, i, +1))
                if s.C[i] < pl:
                    out.append(_ev(s, i, -1))
    return _first_per_day(out)


def ev_asia(s, kind):
    out = []
    by_utc_day = collections.OrderedDict()
    for i, t in enumerate(s.dt):
        by_utc_day.setdefault(t.date(), []).append(i)
    for _, rows in by_utc_day.items():
        if not s.prev_dense[rows[0]]:
            continue
        asia = [j for j in rows if ASIA_UTC[0] <= s.dt[j].hour < ASIA_UTC[1]]
        if len(asia) < 0.8 * (ASIA_UTC[1] - ASIA_UTC[0]) * 12:
            continue
        ah, al = max(s.H[j] for j in asia), min(s.L[j] for j in asia)
        for i in rows:
            if not (EU_US_UTC[0] <= s.dt[i].hour < EU_US_UTC[1]):
                continue
            if kind == "sweep":
                if s.H[i] > ah and s.C[i] < ah:
                    out.append(_ev(s, i, -1))
                if s.L[i] < al and s.C[i] > al:
                    out.append(_ev(s, i, +1))
            else:
                if s.C[i] > ah:
                    out.append(_ev(s, i, +1))
                if s.C[i] < al:
                    out.append(_ev(s, i, -1))
    return _first_per_day(out)


def _median_range(s, i, n):
    lo = max(0, i - n)
    rs = [s.H[j] - s.L[j] for j in range(lo, i)]
    return statistics.median(rs) if rs else None


def ev_fvg(s):
    """Displacement FVG at middle bar m (gap known at the close of m+1); the limit rests from bar m+2; first touch of the
    near edge within FVG_TOUCH_BARS fills AT the edge; the event's entry bar is the touch bar."""
    out = []
    n = len(s.C)
    for m in range(1, n - 2):
        if not s.prev_dense[m] or s.sday[m + 1] != s.sday[m]:
            continue
        rng = s.H[m] - s.L[m]
        if rng <= 0 or abs(s.C[m] - s.O[m]) < DISPLACEMENT_BODY * rng:
            continue
        med = _median_range(s, m, 20)
        if not med or rng < DISPLACEMENT_RANGE_X * med:
            continue
        if s.L[m + 1] > s.H[m - 1] and s.C[m] > s.O[m]:
            side, edge = +1, s.L[m + 1]
        elif s.H[m + 1] < s.L[m - 1] and s.C[m] < s.O[m]:
            side, edge = -1, s.H[m + 1]
        else:
            continue
        for j in range(m + 2, min(n, m + 2 + FVG_TOUCH_BARS)):
            if s.sday[j] != s.sday[m]:
                break
            if (side > 0 and s.L[j] <= edge) or (side < 0 and s.H[j] >= edge):
                o = s.O[j]                              # a bar opening beyond the edge fills at its open (no price improvement)
                px = min(edge, o) if side > 0 else max(edge, o)
                out.append(_ev(s, m + 1, side, entry_i=j, entry_px=px))
                break
    return _first_per_day(out)


def ev_big_bar(s):
    out = []
    for i in range(48, len(s.C) - 1):
        if not s.prev_dense[i]:
            continue
        rng = s.H[i] - s.L[i]
        if rng <= 0 or abs(s.C[i] - s.O[i]) < BIG_BAR_BODY * rng:
            continue
        med = _median_range(s, i, 48)
        if med and rng >= BIG_BAR_RANGE_X * med:
            out.append(_ev(s, i, +1 if s.C[i] > s.O[i] else -1))
    return _first_per_day(out)


def _local_index(s, zone):
    """{local date: [(local minutes from midnight, i), ...]} for the cash-session events."""
    z = zoneinfo.ZoneInfo(zone)
    out = collections.OrderedDict()
    for i, t in enumerate(s.dt):
        lt = t.astimezone(z)
        out.setdefault(lt.date(), []).append((lt.hour * 60 + lt.minute, i))
    return out


def ev_orb(s):
    zone, oh, om = OPEN_LOCAL[s.sym]
    open_min = oh * 60 + om
    out = []
    for _, rows in _local_index(s, zone).items():
        rng = [i for m, i in rows if open_min <= m < open_min + 5 * ORB_BARS]
        if len(rng) < ORB_BARS or not s.prev_dense[rng[0]]:
            continue
        hi, lo = max(s.H[i] for i in rng), min(s.L[i] for i in rng)
        for m, i in rows:
            if open_min + 5 * ORB_BARS <= m < open_min + ORB_DEADLINE_MIN:
                if s.C[i] > hi:
                    out.append(_ev(s, i, +1)); break
                if s.C[i] < lo:
                    out.append(_ev(s, i, -1)); break
    return out


def ev_intraday_momentum(s):
    """Previous cash close -> open + 30 min sets the sign; enter at the bar that OPENS 30 min before the close, exit at the
    close of the last bar before the close (6 bars)."""
    zone, oh, om = OPEN_LOCAL[s.sym]
    ch, cm = CLOSE_LOCAL[s.sym]
    open_min, close_min = oh * 60 + om, ch * 60 + cm
    out, prev_close = [], None
    for _, rows in _local_index(s, zone).items():
        by_min = {m: i for m, i in rows}
        last = by_min.get(close_min - 5)
        i30 = by_min.get(open_min + 25)                  # bar closing at open + 30 min
        ent = by_min.get(close_min - 30)
        if prev_close is not None and i30 is not None and ent is not None and last is not None and s.prev_dense[i30]:
            r1 = s.C[i30] / prev_close - 1.0
            if r1 != 0:
                ev = _ev(s, ent - 1, +1 if r1 > 0 else -1, entry_i=ent, fixed_exit=last)
                out.append(ev)
        if last is not None:
            prev_close = s.C[last]
    return out


DETECTORS = {
    "E1_prev_day_sweep_reclaim": lambda s: ev_prev_day(s, "sweep"),
    "E2_prev_day_acceptance": lambda s: ev_prev_day(s, "accept"),
    "E3_asia_sweep_reclaim": lambda s: ev_asia(s, "sweep"),
    "E4_asia_breakout": lambda s: ev_asia(s, "break"),
    "E5_fvg_retrace": ev_fvg,
    "E6_opening_range_breakout": ev_orb,
    "E7_intraday_momentum": ev_intraday_momentum,
    "E9_big_bar": ev_big_bar,
}


# ------------------------------------------------------------------------------------------------ outcomes
class Costs:
    def __init__(self, sym):
        import real_costs as RC
        self.ref = RC.price_ref(COST_PROFILE, sym)
        self.med = {h: RC.spread_price(COST_PROFILE, sym, h, "median")[0] / self.ref for h in range(24)}
        self.p90 = {h: RC.spread_price(COST_PROFILE, sym, h, "p90")[0] / self.ref for h in range(24)}

    def round_trip(self, h_in, h_out, stat="median"):
        t = self.med if stat == "median" else self.p90
        return 0.5 * t[h_in] + 0.5 * t[h_out]


def outcome(s, ev, h, costs):
    """The event's trade over h bars, or (None, reason)."""
    e = ev["entry_i"]
    x = ev["fixed_exit"] if ev["fixed_exit"] is not None else e + h - 1
    if e >= len(s.C) or x >= len(s.C) or x < e:
        return None, "end_of_data"
    if s.sday[x] != s.sday[e]:
        return None, "crosses_rollover"
    sig = s.sigma(ev["i"])
    if not sig:
        return None, "no_vol_history"
    px_in = ev["entry_px"] if ev["entry_px"] is not None else s.O[e]
    r = ev["side"] * (s.C[x] / px_in - 1.0)
    nb = x - e + 1
    cost = costs.round_trip(s.dt[e].hour, s.dt[x].hour)
    cost90 = costs.round_trip(s.dt[e].hour, s.dt[x].hour, "p90")
    return {"symbol": s.sym, "date": s.dt[ev["i"]].date().isoformat(), "period": s.period(ev["i"]), "side": ev["side"],
            "tod": (s.dt[e].hour * 60 + s.dt[e].minute), "nb": nb, "r": r, "cost": cost, "cost90": cost90,
            "scale": sig * math.sqrt(nb), "entry_i": e, "exit_i": x}, None


def placebo_table(s, nb_set):
    """{(period, tod, nb): mean forward return C[x]/O[e]-1 over every dense day} -- unsigned; signed later by side."""
    acc = collections.defaultdict(lambda: [0.0, 0])
    for e in range(len(s.C)):
        if not s.dense[e]:
            continue
        tod = s.dt[e].hour * 60 + s.dt[e].minute
        per = s.period(e)
        for nb in nb_set:
            x = e + nb - 1
            if x < len(s.C) and s.sday[x] == s.sday[e]:
                a = acc[(per, tod, nb)]
                a[0] += s.C[x] / s.O[e] - 1.0
                a[1] += 1
    return {k: v[0] / v[1] for k, v in acc.items() if v[1]}


# ------------------------------------------------------------------------------------------------ statistics
def cr1(values, clusters):
    """(mean, se, df) with CR1 cluster-robust SE by `clusters`; se None when fewer than 2 clusters."""
    n = len(values)
    if n == 0:
        return None, None, 0
    mu = sum(values) / n
    g = collections.defaultdict(float)
    for v, c in zip(values, clusters):
        g[c] += v - mu
    G = len(g)
    if G < 2:
        return mu, None, G - 1
    se = math.sqrt(G / (G - 1) * sum(x * x for x in g.values())) / n
    return mu, se, G - 1


def t_sf(t, df):
    """P(T > t) for Student-t (regularized incomplete beta via continued fraction; no scipy)."""
    if df <= 0:
        return float("nan")
    x = df / (df + t * t)
    p = 0.5 * _betainc(df / 2.0, 0.5, x)
    return p if t > 0 else 1.0 - p


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(math.log(x) * a + math.log(1 - x) * b + lbeta)
    if x < (a + 1) / (a + b + 2):
        return front * _cf(a, b, x) / a
    return 1.0 - math.exp(math.log(1 - x) * b + math.log(x) * a + lbeta) * _cf(b, a, 1 - x) / b


def _cf(a, b, x, it=300, eps=1e-14):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, it):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e-300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = 1.0 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1.0 + aa / c if abs(c) > 1e-300 else 1e-300
        dl = d * c
        h *= dl
        if abs(dl - 1.0) < eps:
            break
    return h


def bh(pvals, q):
    """Benjamini-Hochberg: the set of indices rejected at FDR q."""
    order = sorted(range(len(pvals)), key=lambda k: pvals[k])
    m, kmax = len(pvals), 0
    for rank, k in enumerate(order, 1):
        if pvals[k] <= q * rank / m:
            kmax = rank
    return set(order[:kmax])


def summarise(rows, direction=+1):
    """Statistics of a list of outcome rows, in `direction` (+1 = the hypothesis' own sign, -1 = reversed)."""
    if not rows:
        return {"n": 0}
    ex = [direction * r["excess"] / r["scale"] for r in rows]
    gross_bp = [direction * r["r"] * 1e4 for r in rows]
    net_bp = [(direction * r["r"] - r["cost"]) * 1e4 for r in rows]
    net90_bp = [(direction * r["r"] - r["cost90"]) * 1e4 for r in rows]
    net_z = [(direction * r["r"] - r["cost"]) / r["scale"] for r in rows]
    cl = [r["date"] for r in rows]
    mu, se, df = cr1(ex, cl)
    t = mu / se if se else None
    p2 = 2 * min(t_sf(t, df), 1 - t_sf(t, df)) if t is not None else 1.0
    p1 = t_sf(t, df) if t is not None else 1.0
    mz, sez, dfz = cr1(net_z, cl)
    tz = mz / sez if sez else None
    return {"n": len(rows), "days": len(set(cl)), "excess_z": mu, "t_excess": t, "p_two_sided": p2, "p_one_sided": p1,
            "gross_bp": sum(gross_bp) / len(rows), "net_bp": sum(net_bp) / len(rows),
            "net_bp_p90": sum(net90_bp) / len(rows), "cost_bp": sum(r["cost"] for r in rows) / len(rows) * 1e4,
            "net_z": mz, "t_net": tz, "p_net_one_sided": t_sf(tz, dfz) if tz is not None else 1.0,
            "win_rate_net": sum(1 for v in net_bp if v > 0) / len(rows)}


# ------------------------------------------------------------------------------------------------ run
def run(out_path, symbols=None):
    syms = symbols or (METALS + INDICES)
    rows = collections.defaultdict(list)          # (event, group, h) -> rows
    skipped = collections.Counter()
    meta_sym = {}
    for sym in syms:
        s = load(sym)
        costs = Costs(sym)
        grp = "metals" if sym in METALS else "indices"
        nbs = set(HORIZONS) | {6}
        events = {e: DETECTORS[e](s) for e in DETECTORS
                  if any(f[0] == e and f[1] == grp for f in FAMILY)}
        # placebo needs the exact nb of fixed-exit events too
        fixed_nb = set()
        for e, evs in events.items():
            for ev in evs:
                if ev["fixed_exit"] is not None:
                    fixed_nb.add(ev["fixed_exit"] - ev["entry_i"] + 1)
        plc = placebo_table(s, nbs | fixed_nb)
        for (e, g, h) in FAMILY:
            if g != grp:
                continue
            for ev in events.get(e, []):
                o, why = outcome(s, ev, h, costs)
                if o is None:
                    skipped[(e, g, h, why)] += 1
                    continue
                base = plc.get((o["period"], o["tod"], o["nb"]))
                if base is None:
                    skipped[(e, g, h, "no_placebo")] += 1
                    continue
                o["excess"] = o["r"] - o["side"] * base
                rows[(e, g, h)].append(o)
        meta_sym[sym] = {"dense_days": len(s.dense_days), "first_dense_day": str(s.dense_days[0]),
                         "split_day": str(s.split_day), "last_dense_day": str(s.dense_days[-1]),
                         "bars": len(s.C), "price_ref": costs.ref,
                         "median_round_trip_cost_bp": statistics.median(
                             0.5 * (costs.med[a] + costs.med[a]) for a in range(24)) * 1e4}
        print(f"{sym}: {len(s.C)} bars, dense days {len(s.dense_days)}, split {s.split_day}", flush=True)
    out = {"meta": {"script": "scripts/research/edge_census.py", "dev_cutoff": DEV_CUTOFF, "cost_profile": COST_PROFILE,
                    "family_size": len(FAMILY), "fdr_q": FDR_Q, "confirm_p": CONFIRM_P, "symbols": meta_sym,
                    "events": EVENTS},
           "skipped": {"|".join(map(str, k)): v for k, v in skipped.items()},
           "tests": []}
    disc_p = []
    for key in FAMILY:
        rs = rows.get(key, [])
        disc = [r for r in rs if r["period"] == "discovery"]
        conf = [r for r in rs if r["period"] == "confirmation"]
        sd = summarise(disc)
        direction = 1 if (sd.get("excess_z") or 0) >= 0 else -1
        per_sym = {}
        for sym in GROUPS[key[1]]:
            sr = [r for r in disc if r["symbol"] == sym]
            if len(sr) >= MIN_SYMBOL_EVENTS:
                per_sym[sym] = summarise(sr, direction)
        test = {"event": key[0], "group": key[1], "h_bars": key[2], "direction": direction,
                "discovery": summarise(disc, direction), "discovery_raw_sign": sd,
                "discovery_by_symbol": per_sym, "confirmation": summarise(conf, direction)}
        out["tests"].append(test)
        disc_p.append(sd.get("p_two_sided", 1.0) if sd.get("n") else 1.0)
    rej = bh(disc_p, FDR_Q)
    for k, test in enumerate(out["tests"]):
        d, c, ps = test["discovery"], test["confirmation"], test["discovery_by_symbol"]
        need = math.ceil(2 * len(ps) / 3) if ps else 1
        agree = sum(1 for v in ps.values() if (v.get("excess_z") or 0) > 0)
        cand = (k in rej and d.get("n", 0) > 0 and d["net_bp"] > 0 and len(ps) >= 1 and agree >= need)
        conf_ok = (cand and c.get("n", 0) > 0 and c["p_one_sided"] < CONFIRM_P and c["net_bp"] > 0
                   and c["net_bp_p90"] > 0)
        test["verdict"] = {"bh_rejected": k in rej, "symbols_agree": f"{agree}/{len(ps)} (need {need})",
                           "candidate": bool(cand), "confirmed": bool(conf_ok)}
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(f"wrote {out_path}: {sum(t['verdict']['candidate'] for t in out['tests'])} candidates, "
          f"{sum(t['verdict']['confirmed'] for t in out['tests'])} confirmed of {len(FAMILY)} tests")
    return out


def report(json_path, out_path):
    d = json.load(open(json_path))
    L = ["| event | group | h | dir | disc n | disc excess z | disc p (2s) | BH | disc net bp | cost bp | symbols | conf n | "
         "conf excess z | conf p (1s) | conf net bp | conf net bp p90 | verdict |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda v, p=3: "n/a" if v is None else f"{v:.{p}f}"
    for t in d["tests"]:
        a, c, v = t["discovery"], t["confirmation"], t["verdict"]
        verdict = "CONFIRMED" if v["confirmed"] else ("candidate, not confirmed" if v["candidate"] else "-")
        L.append(f"| {t['event']} | {t['group']} | {t['h_bars']} | {'+' if t['direction'] > 0 else '-'} | {a.get('n', 0)} | "
                 f"{f(a.get('excess_z'))} | {f(a.get('p_two_sided'), 4)} | {'yes' if v['bh_rejected'] else 'no'} | "
                 f"{f(a.get('net_bp'), 2)} | {f(a.get('cost_bp'), 2)} | {v['symbols_agree']} | {c.get('n', 0)} | "
                 f"{f(c.get('excess_z'))} | {f(c.get('p_one_sided'), 4)} | {f(c.get('net_bp'), 2)} | "
                 f"{f(c.get('net_bp_p90'), 2)} | {verdict} |")
    open(out_path, "w").write("\n".join(L) + "\n")
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--symbols", help="comma list (tests / smoke only; the census is all eight)")
    q = sub.add_parser("report")
    q.add_argument("--json", required=True)
    q.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.out, a.symbols.split(",") if a.symbols else None)
    else:
        report(a.json, a.out)


if __name__ == "__main__":
    main()
