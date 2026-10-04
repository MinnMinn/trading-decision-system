#!/usr/bin/env python3
"""Family CAL: scheduled-calendar premia on the US index CFDs (US500, US30, USTEC) -- the pre-FOMC drift and the
pre-holiday effect -- against a calendar null.
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-cal-us-index-calendar-preregistration-DRAFT.md [CAL-P1].

    python3 scripts/research/edge_cal.py manifest                                   # the code-sha256 lines for the seal
    python3 scripts/research/edge_cal.py dry-run --fomc <calendar json> --out <json>  # outcome-blind: event / overlap COUNTS
    python3 scripts/research/edge_cal.py run --read forward --fomc <json> --out docs/audits/<date>-edge-cal-forward.json
        # window: from the server day after the seal commit (git) to the last full server day all three series hold
    python3 scripts/research/edge_cal.py run --read history --fomc <json> --out docs/audits/<date>-edge-cal-history.json
        # ONLY under an owner override

FORWARD ONLY by default. Both classes were judged before this family: pre-holiday is B6 "history CONTAMINATED (G7 / H2
read): forward only" (docs/plans/2026-10-03-candidates.md:44) and "no source, MDE about 32 bp"
(docs/plans/2026-10-03-crypto-cfd-design.md:263); pre-FOMC "decayed after 2015. Forward-only at most" (same file :248).
The history read exists only for an explicit, recorded owner override of B6 (CAL-P1 §0): the coordinator sets
HISTORICAL_READ = True before sealing, and the code fingerprint pins it. Even then it never computes a row on a day whose
return an earlier family read: G7's turn-of-month days (`edge_f4.tom_days` on each series, scripts/research/edge_f4.py:157)
and M1's discovery return days (week 4, the falsification placebo and the reversal; scripts/research/edge_m1.py:654-701).
Those days are skipped and counted, and they are not in the calendar null either.

Each read ONCE (one output name per read; a second run is refused even to another path, prereg_guard.require_read_once),
from committed code whose sha256 the SEALED pre-registration lists (scripts/research/prereg_guard.py). Without a FOMC
calendar file T1 is "not run (data)" and enters BH with p = 1. The forward read takes no date from the command line: it
starts on the server day after the seal commit's (`prereg_guard.first_forward_day`) and ends on the last full server day
that all three series hold (`last_full_day`), so neither an early seal date nor an end past the data can be typed in.

Events (long only; the server day D = 17:00 New York on D - 1 -> 17:00 New York on D, FTMO-Demo clock):
* T1 PRE-FOMC: D = a SCHEDULED FOMC announcement date (the calendar file, sourced from federalreserve.gov, carries each
  date's release time in New York time). Entry at the OPEN of server day D's first bar; exit at the CLOSE of the 5m bar
  that OPENS 10 minutes before the release (it closes 5 minutes before; flat before the statement).
* T2 PRE-HOLIDAY: D = the last NYSE business day before a regular NYSE holiday (scripts/research/edge_m1.py:219
  `nyse_holidays`; the two special closures of edge_m1.py:180 are not holidays here). Entry at the OPEN of D's first bar;
  exit at the CLOSE of the bar opening 12:50 New York (closes 12:55: before any 13:00 early close).
* Eligibility: D's previous server day is dense (edge_census.Series.prev_dense) and D has a sigma (sigma_every_day: the
  previous 20 dense days); the exit bar exists in D. No swap (one server day).
* Calendar null: excess = r - the mean r of the SAME window over every other NYSE business day of the same symbol, calendar
  year and WEEKDAY (and, forward, from the first forward day on) that is neither an event day nor an excluded read day; at
  least MIN_NULL_DAYS such days, else the event is skipped and counted (`thin_null`). Weekday-matched because the events
  are not spread over the week: more than half of the pre-holiday days are Fridays (45 of 83, 2017-12-28 -> 2026-09-25;
  four of the ten regular holidays are Mondays), and FOMC statements come mid-week. The all-weekday null of the same year
  is report-only (`excess_all_days`). Pooled over the three symbols; CR1 by the NYSE date; edge_census.summarise.
* Gate: BH (m = 2, q = 0.10) on the one-sided p of the excess, AND mean net > 0 -> CANDIDATE (discovery grade even when
  forward: ~17 events a year)."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
import sys
import zoneinfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


G = _load("prereg_guard", "scripts/research/prereg_guard.py")
M1 = _load("edge_m1", "scripts/research/edge_m1.py")
F4 = _load("edge_f4", "scripts/research/edge_f4.py")
EC = M1.EC

PREREG = "docs/plans/2026-10-04-cal-us-index-calendar-preregistration.md"
TAG = "[CAL-P1]"
FAMILY = "cal"                                  # read outputs: docs/audits/<YYYY-MM-DD>-edge-cal-<read>.json
SCRIPT = "scripts/research/edge_cal.py"
TESTS_FILE = "scripts/tests/test_edge_cal.py"
#: Every file whose content can change a CAL read (traced: scripts/tests/test_edge_cal.py
#: `test_code_lists_every_module_a_read_loads`). The sealed text lists each one's sha256.
CODE = (SCRIPT, TESTS_FILE, "scripts/tests/test_prereg_guard.py", "scripts/research/prereg_guard.py",
        "scripts/research/edge_m1.py", "scripts/research/edge_census.py", "scripts/research/edge_f3.py",
        "scripts/research/edge_f4.py", "scripts/real_costs.py", "scripts/history_store.py", "scripts/mt5_time.py",
        "scripts/providers.py", "scripts/instruments.py")
#: B6 (docs/plans/2026-10-03-candidates.md:44): forward only. True ONLY by a recorded owner override (CAL-P1 §0), set before
#: sealing; the code fingerprint pins the value.
HISTORICAL_READ = False
READS = ("forward", "history")
SYMBOLS = ("US500", "US30", "USTEC")
NY = zoneinfo.ZoneInfo("America/New_York")
END_DAY = datetime.date(2026, 9, 25)            # history read: the last full week of the export
PRE_HOLIDAY_EXIT = (12, 50)                     # bar OPEN, New York; it closes 12:55
FOMC_EXIT_LEAD_MIN = 10                         # bar opens release - 10 min, closes release - 5 min
FDR_Q = 0.10
TESTS = (("T1", "pre_fomc"), ("T2", "pre_holiday"))
M1_READ = "discovery"                           # the only M1 read that ran (docs/audits/2026-10-04-edge-m1-discovery.json)
FWD_MIN_EVENT_DAYS = 40                         # forward read due: >= 40 event dates in EACH run test ...
FWD_MAX_YEARS = 5                               # ... or 5 years after the seal, whichever comes first
MIN_NULL_DAYS = 8                               # a calendar-null cell (symbol, year, weekday) needs >= 8 days with a window


# ------------------------------------------------------------------------------------------------ calendars
def load_fomc(path):
    """{date: (hour, minute) New York} of SCHEDULED announcements; cancelled / unscheduled entries are dropped.
    Schema: {"_source": [...], "_retrieved_utc": "...", "events": [{"date", "release_et": "HH:MM", "scheduled": bool,
    "cancelled": bool (optional)}]}."""
    doc = json.load(open(path))
    if not doc.get("_source") or not doc.get("_retrieved_utc"):
        raise G.Refused(f"refused: {path} lacks _source / _retrieved_utc (the calendar must be sourced)")
    out = {}
    for e in doc["events"]:
        d = datetime.date.fromisoformat(e["date"])
        if d in out:
            raise G.Refused(f"refused: duplicate FOMC date {d}")
        if not e.get("scheduled") or e.get("cancelled"):
            continue
        h, m = map(int, e["release_et"].split(":"))
        out[d] = (h, m)
    return out


def pre_holidays(cal, y0, y1):
    """{NYSE day: holiday name} -- the last NYSE business day before each regular NYSE holiday in years y0..y1."""
    out = {}
    for y in range(y0, y1 + 1):
        for h, name in M1.nyse_holidays(y).items():
            if h in M1.SPECIAL_CLOSURES:
                continue
            out[cal.prev(h)] = name
    return out


def m1_read_days(cal):
    """NYSE days whose US return M1's discovery read computed: the return day of each week-4 day, of each falsification
    placebo day it kept (return day before T-4), and of the first-business-day reversal (scripts/research/edge_m1.py:654,
    :669, :682, :696; read in edge_m1.py's discovery run over EPISODES["discovery"])."""
    out = set()
    a, b = M1.EPISODES[M1_READ]
    for ep in M1.month_range(a, b):
        y, m = M1._ym(ep)
        w4 = cal.week4(y, m)
        for t in w4:
            out.add(M1.return_day(cal, t, "US"))
        for t in M1.placebo_days(cal, y, m):
            rd = M1.return_day(cal, t, "US")
            if rd < w4[0]:
                out.add(rd)
        out.add(M1.return_day(cal, cal.next(w4[-1]), "US"))
    return out


def read_days(s, cal):
    """{day: reason} of the days an earlier family read on this series: G7 turn of month (edge_f4.tom_days on the series
    itself, the days G7 traded) and M1's discovery return days."""
    out = {d: "g7_turn_of_month" for d in F4.tom_days(s)}
    for d in m1_read_days(cal):
        out.setdefault(d, "m1_discovery")
    return out


def exit_clock(kind, release=None):
    if kind == "pre_holiday":
        return PRE_HOLIDAY_EXIT
    t = datetime.datetime(2000, 1, 1, release[0], release[1]) - datetime.timedelta(minutes=FOMC_EXIT_LEAD_MIN)
    return t.hour, t.minute


# ------------------------------------------------------------------------------------------------ windows on a series
def day_window(s, d, clock):
    """(entry index, exit index) for server day d: its first bar, and the bar opening at `clock` New York on date d; None
    when the previous server day is not dense, there is no sigma, or no such exit bar exists."""
    rows = s.day_rows.get(d)
    if not rows or not s.prev_dense[rows[0]] or not s.sigma(rows[0]):
        return None
    e = rows[0]
    for j in rows:
        t = s.dt[j].astimezone(NY)
        if t.date() == d and (t.hour, t.minute) == clock:
            return (e, j) if j >= e else None
    return None


def window_return(s, w):
    e, x = w
    return s.C[x] / s.O[e] - 1.0


def placebo(s, cal, clock, year, exclude, start_day=None, end_day=END_DAY, weekday=None):
    """The calendar null: mean window return over the NYSE days of `year` (and of `weekday`, Monday = 0, unless None) in
    [start_day, end_day] not in `exclude`; None when fewer than MIN_NULL_DAYS such days have a window."""
    acc, n = 0.0, 0
    for d in cal.days:
        if d.year != year or d in exclude or d > end_day or (start_day and d < start_day):
            continue
        if weekday is not None and d.weekday() != weekday:
            continue
        w = day_window(s, d, clock)
        if w is None:
            continue
        acc += window_return(s, w)
        n += 1
    return acc / n if n >= MIN_NULL_DAYS else None


def event_rows(s, cal, events, kind, exclude, costs, end_day=END_DAY, start_day=None, drop=None):
    """Rows for `events` ({date: release or None}) in EC.summarise's shape; skips counted by reason. `drop` ({day: reason}):
    read days -- skipped BEFORE any price of the day is touched, and kept out of the null."""
    drop = drop or {}
    rows, skipped = [], collections.Counter()
    cache = {}
    first = s.dense_days[0] if s.dense_days else None
    null_exclude = set(exclude) | set(drop)
    for d, rel in sorted(events.items()):
        if first is None or d < first or d > end_day or (start_day and d < start_day) or not cal.in_range(d) \
                or not cal.is_open(d):
            skipped["outside_span"] += 1
            continue
        if d in drop:
            skipped[f"read_day:{drop[d]}"] += 1
            continue
        clock = exit_clock(kind, rel)
        w = day_window(s, d, clock)
        if w is None:
            skipped["no_window"] += 1
            continue
        for key in ((clock, d.year, d.weekday()), (clock, d.year, None)):
            if key not in cache:
                cache[key] = placebo(s, cal, clock, d.year, null_exclude, start_day, end_day, weekday=key[2])
        base, base_all = cache[(clock, d.year, d.weekday())], cache[(clock, d.year, None)]
        if base is None:
            skipped["thin_null"] += 1
            continue
        e, x = w
        r = window_return(s, w)
        nb = x - e + 1
        rows.append({"symbol": s.sym, "kind": kind, "date": d.isoformat(), "year": d.year, "weekday": d.weekday(),
                     "side": 1, "r": r, "excess": r - base,
                     "excess_all_days": None if base_all is None else r - base_all,          # report-only
                     "scale": s.sigma(e) * math.sqrt(nb), "nb": nb,
                     "cost": costs.round_trip_at(s.dt[e], s.dt[x]) if costs else 0.0,
                     "cost90": costs.round_trip_at(s.dt[e], s.dt[x], "p90") if costs else 0.0,
                     "entry_time": s.T[e], "exit_time": s.T[x]})
    return rows, skipped


def verdicts(tests):
    ids = [t for t, _ in TESTS]
    p = [tests[t].get("p_one_sided", 1.0) if tests[t].get("n") else 1.0 for t in ids]
    rej = EC.bh(p, FDR_Q)
    return {t: {"bh_rejected": k in rej,
                "candidate": bool(k in rej and tests[t].get("n") and tests[t]["net_bp"] > 0)} for k, t in enumerate(ids)}


def forward_due(event_dates, seal, today):
    """event_dates: {kind: set of NYSE event dates in [seal, today]} for the tests that run."""
    return all(len(v) >= FWD_MIN_EVENT_DAYS for v in event_dates.values()) or \
        today >= datetime.date(seal.year + FWD_MAX_YEARS, seal.month, min(seal.day, 28))


def by(rows, key):
    out = collections.defaultdict(list)
    for r in rows:
        out[str(r[key])].append(r)
    return {k: EC.summarise(v) for k, v in sorted(out.items())}


def last_full_day(candles, zone):
    """The last server day an export surely holds whole: the day before the server day of its last bar (an export can stop
    mid-session). None without bars."""
    if not candles:
        return None
    t = max(c["time"] for c in candles)
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(zone).date() - datetime.timedelta(days=1)


# ------------------------------------------------------------------------------------------------ CLI
def _zone():
    import real_costs as RC
    return RC.server_zone(EC.PROVIDER)[1]


_DOCS = {}


def _candles(sym):
    """The stored FTMO 5m bars of `sym` (read once per process)."""
    if sym not in _DOCS:
        import history_store as HS
        doc, _ = HS.read_doc(sym, "5m", root=EC.HIST_ROOT)
        if doc is None:
            raise G.Refused(f"refused: no FTMO 5m history for {sym}")
        _DOCS[sym] = doc["candles"]
    return _DOCS[sym]


def _series(sym, end_day):
    zone = _zone()
    n = end_day + datetime.timedelta(days=1)
    end_iso = datetime.datetime(n.year, n.month, n.day, tzinfo=zone).astimezone(
        datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")        # the end of server day end_day: nothing later is loaded
    return EC.Series(sym, _candles(sym), zone, end=end_iso, sigma_every_day=True)


def _dump(res, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {path}")


def _rel(p):
    return os.path.relpath(os.path.abspath(p), ROOT).replace(os.sep, "/")


def dry_counts(s, cal, events):
    """Outcome-blind, one series: its first dense day (US500 / USTEC start 2021-09, US30 2019-02: the history read's event
    dates before 2021-09 come from US30 alone), and per kind the eligible events (a window exists), how many fall on read
    days by reason, and the eligible events per weekday (Monday = 0; the null is weekday-matched)."""
    drop = read_days(s, cal)
    out = {"first_dense_day": str(s.dense_days[0]) if s.dense_days else None}
    for kind, ev in events.items():
        c = collections.Counter()
        for d, rel in ev.items():
            if d > END_DAY or not cal.in_range(d) or not cal.is_open(d) or day_window(s, d, exit_clock(kind, rel)) is None:
                continue
            c["eligible"] += 1
            c[f"weekday:{d.weekday()}"] += 1
            if d in drop:
                c[f"read_day:{drop[d]}"] += 1
            else:
                c["primary_if_history"] += 1
        out[kind] = dict(c)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print the code-sha256 lines the sealed text must carry")
    d = sub.add_parser("dry-run")
    d.add_argument("--fomc", help="the sourced FOMC calendar JSON (absent: T1 not run)")
    d.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--fomc")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE)))
        return
    G.refuse_overwrite(a.out)
    cal = M1.NyseCalendar()
    fomc = load_fomc(a.fomc) if a.fomc else {}
    if a.cmd == "dry-run":
        ph = pre_holidays(cal, 2017, END_DAY.year)
        events = {"pre_fomc": fomc, "pre_holiday": {x: None for x in ph}}
        per = {sym: dry_counts(_series(sym, END_DAY), cal, events) for sym in SYMBOLS}
        m1 = m1_read_days(cal)
        _dump({"meta": {"script": SCRIPT, "kind": "dry-run (counts only)", "fomc": a.fomc, "end_day": str(END_DAY),
                        "git_head": G.git_head(ROOT), "historical_read": HISTORICAL_READ,
                        "code_sha256": {p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE}},
               "eligible_events": per,
               "calendar_only": {"fomc_dates": len(fomc), "pre_holiday_dates": len(ph),
                                 "fomc_on_m1_read_days": sum(1 for x in fomc if x in m1),
                                 "pre_holiday_on_m1_read_days": sum(1 for x in ph if x in m1)}}, a.out)
        return
    if a.read == "history" and not HISTORICAL_READ:
        raise G.Refused("refused: CAL is forward-only (B6, docs/plans/2026-10-03-candidates.md:44); the history read needs a "
                        "recorded owner override and HISTORICAL_READ = True at the seal (CAL-P1 §0)")
    G.require_read_once(ROOT, _rel(a.out), FAMILY, a.read)
    text = G.require_sealed(ROOT, PREREG, TAG)
    G.require_committed(ROOT, CODE + ((_rel(a.fomc),) if a.fomc else ()))
    man = G.require_fingerprint(ROOT, text, CODE)
    G.trace_start(ROOT)                                 # before any data is loaded: everything the read executes is traced
    window = {}
    if a.read == "forward":
        zone = _zone()
        seal = G.seal_time(ROOT, PREREG)                # git: the commit that added the sealed text; never typed
        start = G.first_forward_day(ROOT, PREREG, zone)
        data_end = {sym: last_full_day(_candles(sym), zone) for sym in SYMBOLS}
        if any(v is None for v in data_end.values()):
            raise G.Refused(f"refused: an index series has no 5m bars ({data_end})")
        end = min(data_end.values())                    # every event day of the read has bars in all three series
        ph = pre_holidays(cal, start.year, end.year)
        fwd_dates = {"pre_holiday": {x for x in ph if start <= x <= end}}
        if fomc:
            fwd_dates["pre_fomc"] = {x for x in fomc if start <= x <= end}
        if not forward_due(fwd_dates, start - datetime.timedelta(days=1), end):
            raise G.Refused(f"refused: forward read not due ({ {k: len(v) for k, v in fwd_dates.items()} } event dates "
                            f"from {start} to {end}, < {FWD_MIN_EVENT_DAYS} each, < {FWD_MAX_YEARS} years)")
        window = {"seal_commit": seal.isoformat(), "first_forward_day": str(start),
                  "data_end_by_symbol": {k: str(v) for k, v in data_end.items()}}
    else:
        start, end = None, END_DAY
        ph = pre_holidays(cal, 2017, END_DAY.year)
    events = {"pre_fomc": fomc, "pre_holiday": {x: None for x in ph}}
    exclude = set(fomc) | set(ph)
    rows = {kind: [] for _, kind in TESTS}
    skipped = {}
    for sym in SYMBOLS:
        s = _series(sym, end)
        costs = EC.Costs(sym)
        drop = read_days(s, cal) if a.read == "history" else {}
        for _, kind in TESTS:
            got, sk = event_rows(s, cal, events[kind], kind, exclude, costs, end_day=end, start_day=start, drop=drop)
            rows[kind] += got
            skipped[f"{sym}|{kind}"] = dict(sk)
    tests = {t: (EC.summarise(rows[kind]) if (kind != "pre_fomc" or fomc) else {"n": 0, "not_run": "no FOMC calendar"})
             for t, kind in TESTS}
    res = {"meta": {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "read": a.read, "start": str(start),
                    "end_day": str(end), **window,
                    "fomc": a.fomc, "git_head": G.git_head(ROOT), "cost_profile": EC.COST_PROFILE,
                    "historical_read": HISTORICAL_READ,
                    "dataset": G.dataset_snapshot(EC.HIST_ROOT, [(x, "5m") for x in SYMBOLS]),
                    "fomc_sha256": G.file_sha256(a.fomc) if a.fomc else None},
           "tests": tests, "verdicts": verdicts(tests), "skipped": skipped,
           "report_only": {kind: {"by_symbol": by(rows[kind], "symbol"), "by_year": by(rows[kind], "year"),
                                  "by_weekday": by(rows[kind], "weekday"),
                                  "all_weekday_null": EC.summarise([dict(r, excess=r["excess_all_days"]) for r in rows[kind]
                                                                    if r["excess_all_days"] is not None])}
                           for _, kind in TESTS},
           "rows": rows}
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, a.out)


if __name__ == "__main__":
    main()
