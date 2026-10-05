#!/usr/bin/env python3
"""NEWS-FLAT (NF): be flat across HIGH-impact US releases -- a policy lever on fvg-book v4 (H7 + G9 XAUUSD, stop_k 1.4).
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-news-flat-preregistration-DRAFT.md [NF-P1].

    python3 scripts/research/news_flat.py manifest          # the code-sha256 lines and the calendar line for the seal
    python3 scripts/research/news_flat.py check-calendar    # load + point-in-time checks of the calendar; counts only
    python3 scripts/research/news_flat.py dry-run --out <json>
        # outcome-blind: planned entries in windows, planned-open across a release, UNKNOWN days (no exit walk, no R)
    python3 scripts/research/news_flat.py run --read exposed --out docs/audits/<date>-edge-nf-exposed.json
    python3 scripts/research/news_flat.py run --read forward --out docs/audits/<date>-edge-nf-forward.json

The three policies (fixed in NF-P1 §2; nothing else is run):
* P0 baseline: the v4 trade rows as scripts/research/book_sim.py gives them (the research replay has no calendar).
* P1 no new entry: a row whose entry time lies in a restricted window [T - 10 min, T + 10 min] (closed; the union over
  events) of a HIGH release T is dropped. This is the live executor's rule (scripts/fvg_demo.py blocks new entries through
  scripts/event_risk.py; CLAUDE.md §24).
* P2 flat across: P1, and every position still open at a window start is closed at the CLOSE of the bar that ends exactly
  at that start (book_sim's fill convention for a time exit; a data gap there makes the trade UNKNOWN). The flatten leg is
  priced at the p90 spread, the conservative reading; the book_sim pricing and the held trade's cost are reported as
  sensitivities. A flattened trade is not resumed; signals that enter after the window are taken as the detectors give them.

Point in time (CLAUDE.md §8, §27-§30): a window restricts a decision at time t only when the calendar row was available
(`available_time` <= t) and not withdrawn by then; windows use the scheduled time, never a later-known actual time;
overlapping or touching windows join. The exposed read sees the bars before EXPOSED_END only (pinned by digest) and one
calendar state; the forward read uses the calendar as COMMITTED at each decision (`AsOf`), re-prices both legs of dR with one
cost basis, and refuses on bytecode outside the repository. UNKNOWN is never LOW (§25, §32): a row without an impact loads as UNKNOWN and
restricts like HIGH; a release whose time or availability is UNKNOWN makes the trades around it UNKNOWN, and those trades
are removed from all three policies alike (counted), never treated as "no news". Coverage gaps are UNKNOWN the same way.

Each read runs once, from committed code whose sha256 the SEALED pre-registration lists, with the calendar history the
sealed text pins (scripts/research/prereg_guard.py; `require_calendar_history`). Synthetic tests only:
scripts/tests/test_news_flat.py."""
import argparse
import bisect
import collections
import contextlib
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
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
Refused = G.Refused

PREREG = "docs/plans/2026-10-04-news-flat-preregistration.md"
TAG = "[NF-P1]"
FAMILY = "nf"                                   # read outputs: docs/audits/<YYYY-MM-DD>-edge-nf-<read>.json
READS = ("exposed", "forward")
SCRIPT = "scripts/research/news_flat.py"
TESTS_FILE = "scripts/tests/test_news_flat.py"
CALENDAR = "data/calendar/us-high-impact-releases.json"
LEDGER = "docs/architecture/research-ledger.json"   # CLAUDE.md §43: the budget is registered before any read
LEDGER_KEY = "news_flat"
#: Every file whose content can change an NF read (traced: test_news_flat `test_code_lists_every_module_a_read_loads`).
CODE = (SCRIPT, TESTS_FILE, "scripts/research/prereg_guard.py", "scripts/tests/test_prereg_guard.py",
        "scripts/research/book_sim.py", "scripts/research/fvg_book_sim.py", "scripts/research/edge_census.py",
        "scripts/research/edge_f3.py", "scripts/research/edge_f4.py", "scripts/research/pass_policy.py",
        "scripts/research/fvg_forward.py", "scripts/broker_symbols.py", "scripts/real_costs.py", "scripts/history_store.py",
        "scripts/mt5_time.py", "scripts/providers.py", "scripts/instruments.py")
HISTORY_BEFORE = "2026-10-05"                   # the exposed read's calendar rows: release dates before this day (ET)
#: The exposed read sees the stored XAUUSD 5m bars BEFORE this instant and no later ones (the stored history ends
#: 2026-10-02T20:45:00Z): a re-export after the seal must not feed the descriptive read with forward days (CLAUDE.md §44), and
#: the digest of exactly these bars is pinned in the sealed text (`dataset_line`, `require_dataset`).
EXPOSED_END = "2026-10-03T00:00:00Z"
VC_TAG = "[VC-P1]"                              # the tag VC's read output must carry (prereg_guard.require_read_json)
#: VC-P1 (docs/plans/2026-10-04-vc-volatility-condition-preregistration-DRAFT.md) decides on XAU window B (before
#: 2008-12-10), unread for its volatility split. The exposed NF read reports R on release days of those years, so it runs
#: only after VC's xau-holdout read is committed (NF-P1 §3, §5). The coordinator sets False before sealing ONLY if VC is
#: withdrawn, and records that in NF-P1 §3; the code fingerprint pins the value.
AFTER_VC = True

COMPS = ("H7_XAUUSD_eod", "G9_XAUUSD_eod")      # fvg-book v4 (docs/audits/2026-10-04-a1-under-owner-tolerance.md §3)
SYMBOL = "XAUUSD"
STOP_K = 1.4
RISK = 0.01                                     # 1 % of the balance at the stop
PRE_MIN, POST_MIN = 10, 10                      # CLAUDE.md §24 defaults (event-calendar.json policy)
POLICIES = ("P0", "P1", "P2")
TYPES = ("NFP", "CPI", "FOMC_STATEMENT", "FOMC_PRESS_CONFERENCE")
IMPACTS = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
RESTRICTED = ("HIGH", "UNKNOWN")                # UNKNOWN is never silently LOW (CLAUDE.md §25)
STATUSES = ("released", "scheduled", "postponed", "cancelled", "unscheduled")
GAP_R = -1.05                                   # a stop exit below -1.05 R gapped through its stop (vol-schedule.md:39-45)
DAILY_LOSS = 0.05                               # FTMO daily loss limit (scripts/research/pass_policy.py:27)
SELECT_END = "2024-01-01"                       # pass_policy's selection / confirmation split
BAR = datetime.timedelta(minutes=5)
NY = zoneinfo.ZoneInfo("America/New_York")
UTC = datetime.timezone.utc
# Forward FAIR test (NF-P1 §4): fixed now, before any forward row exists.
FWD_MIN_AFFECTED = 50                           # due when >= 50 forward v4 trades are flattened by P2 ...
FWD_MAX_MONTHS = 36                             # ... or 36 months after the seal, whichever comes first
FWD_MIN_CLUSTERS = 20                           # fewer release days than this: INCONCLUSIVE (no decision)
#: P2 is CHEAP when its cost per flattened trade is credibly below this margin (NF-P1 §4, §6, §11). 0.10 R would certify a
#: truly free P2 only about 34-42 % of the time at 50 flattened trades; 0.20 R does so 67-81 % of the time and errs in about 10 %
#: of reads when the true cost equals the margin. The owner may set another value before the seal; the fingerprint pins it.
MARGIN_R = 0.20
Z_ONE_SIDED_90 = 1.2815515655446004


# ------------------------------------------------------------------------------------------------ time helpers
def utc(s):
    """ISO-8601 with an explicit zone -> aware UTC datetime; None stays None. A naive time is refused (§8)."""
    if s is None:
        return None
    d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise Refused(f"refused: timestamp {s!r} has no zone (CLAUDE.md §8 needs an explicit clock)")
    return d.astimezone(UTC)


def iso(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def et_to_utc(date_iso, hhmm):
    """New York wall time on `date_iso` -> UTC, with that date's own DST state (zoneinfo)."""
    d = datetime.date.fromisoformat(date_iso)
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=NY).astimezone(UTC)


def ny_date(t):
    return t.astimezone(NY).date()


# ------------------------------------------------------------------------------------------------ calendar
class Event:
    __slots__ = ("id", "type", "impact", "status", "date", "t", "avail", "withdrawn", "superseded_by", "row")

    def __init__(self, row, t, avail, withdrawn, impact):
        self.id, self.type, self.status = row["id"], row["type"], row["status"]
        self.date = datetime.date.fromisoformat(row["date_et"])
        self.t, self.avail, self.withdrawn, self.impact = t, avail, withdrawn, impact
        self.superseded_by = row.get("superseded_by")
        self.row = row

    def __repr__(self):
        return f"Event({self.id}, {self.status}, {self.t and iso(self.t)})"


class Calendar:
    def __init__(self, events, coverage, snapshot, sha256=None, path=None):
        self.events = sorted(events, key=lambda e: (e.date, e.t or datetime.datetime.max.replace(tzinfo=UTC), e.id))
        self.coverage = coverage                    # {type: (from date, through date)}
        self.snapshot, self.sha256, self.path = snapshot, sha256, path
        self._dates = [e.date for e in self.events]
        self.by_id = {e.id: e for e in self.events}

    def at(self, t):
        """The calendar as known at the instant `t`. A loaded calendar is one state: what was public when is carried by each
        row's `available_time` / `withdrawn_available_time` (the exposed read). `AsOf` returns the committed version."""
        return self

    @property
    def latest(self):
        return self

    def near(self, lo, hi):
        """Events whose New York date lies in [date(lo) - 1, date(hi) + 1] (a window or an UNKNOWN day can reach a
        trade only from those dates)."""
        a = bisect.bisect_left(self._dates, ny_date(lo) - datetime.timedelta(days=1))
        b = bisect.bisect_right(self._dates, ny_date(hi) + datetime.timedelta(days=1))
        return self.events[a:b]


def load_calendar(path=None, doc=None):
    """The sourced calendar, validated; refuses (never repairs) a malformed one (CLAUDE.md §32: an unusable calendar is
    not an empty one). Checks: schema; snapshot id; every row sourced (each cited source exists with url, sha256 and
    retrieval time, and carries a quote); unique ids; known type and status; impact in §25's four levels, a missing impact
    loading as UNKNOWN (never LOW); a KNOWN time consistent between New York wall time and UTC (the date's own DST); an
    UNKNOWN time with no UTC instant; availability not after a released row's own time; postponed rows name their
    replacement; coverage per type."""
    raw = None
    if doc is None:
        path = path or os.path.join(ROOT, CALENDAR)
        with open(path, "rb") as fh:
            raw = fh.read()
        doc = json.loads(raw.decode("utf-8"))
    if doc.get("schema") != "nf-calendar/1":
        raise Refused(f"refused: calendar schema {doc.get('schema')!r} is not 'nf-calendar/1'")
    snap = doc.get("snapshot") or {}
    if not snap.get("id"):
        raise Refused("refused: the calendar carries no snapshot id (CLAUDE.md §29)")
    sources = doc.get("sources") or {}
    for sid, s in sources.items():
        if not (s.get("url") and re.fullmatch(r"[0-9a-f]{64}", s.get("sha256") or "") and s.get("retrieved_utc")):
            raise Refused(f"refused: source {sid} lacks url / sha256 / retrieved_utc")
    cov = {}
    for typ in TYPES:
        c = (doc.get("coverage") or {}).get(typ)
        if not c:
            raise Refused(f"refused: the calendar declares no coverage for {typ}")
        cov[typ] = (datetime.date.fromisoformat(c["from"]), datetime.date.fromisoformat(c["through"]))
    events, seen = [], set()
    for row in doc.get("events") or []:
        eid = row.get("id")
        if not eid or eid in seen:
            raise Refused(f"refused: missing or duplicate event id {eid!r}")
        seen.add(eid)
        if row.get("type") not in TYPES:
            raise Refused(f"refused: {eid} has type {row.get('type')!r}")
        if row.get("status") not in STATUSES:
            raise Refused(f"refused: {eid} has status {row.get('status')!r}")
        impact = row.get("impact")
        impact = "UNKNOWN" if impact in (None, "") else str(impact).upper()
        if impact not in IMPACTS:
            raise Refused(f"refused: {eid} declares impact {impact!r}, not one of {IMPACTS} (CLAUDE.md §25)")
        srcs = row.get("sources") or []
        if not srcs:
            raise Refused(f"refused: {eid} cites no source (every row must be sourced)")
        for s in srcs:
            if s.get("source") not in sources or not s.get("quote"):
                raise Refused(f"refused: {eid} cites {s.get('source')!r} without a known source or a quote")
        datetime.date.fromisoformat(row["date_et"])
        if row.get("time_status") == "KNOWN":
            if not row.get("time_et") or not row.get("scheduled_event_time"):
                raise Refused(f"refused: {eid} is KNOWN but has no time")
            t = utc(row["scheduled_event_time"])
            if et_to_utc(row["date_et"], row["time_et"]) != t:
                raise Refused(f"refused: {eid}: {row['date_et']} {row['time_et']} New York is not {row['scheduled_event_time']} "
                              "(time-zone / DST error)")
        elif row.get("time_status") == "UNKNOWN":
            if row.get("scheduled_event_time") is not None:
                raise Refused(f"refused: {eid} has an UNKNOWN time but a UTC instant")
            t = None
        else:
            raise Refused(f"refused: {eid} has time_status {row.get('time_status')!r}")
        avail, wd = utc(row.get("available_time")), utc(row.get("withdrawn_available_time"))
        if row["status"] == "released" and avail is not None and t is not None and avail > t:
            raise Refused(f"refused: {eid} became available after its own release time (it was not scheduled)")
        if row["status"] == "postponed" and not row.get("superseded_by"):
            raise Refused(f"refused: postponed {eid} names no replacement")
        if row["status"] not in ("postponed", "cancelled") and wd is not None:
            raise Refused(f"refused: {eid} is {row['status']} but carries a withdrawal time")
        events.append(Event(row, t, avail, wd, impact))
    ids = {e.id for e in events}
    for e in events:
        if e.superseded_by and e.superseded_by not in ids:
            raise Refused(f"refused: {e.id} is superseded by an unknown row {e.superseded_by!r}")
    return Calendar(events, cov, snap, hashlib.sha256(raw).hexdigest() if raw is not None else None, path)


EMPTY = Calendar([], {typ: (datetime.date.max, datetime.date.min) for typ in TYPES}, {"id": "empty"})   # covers nothing


class AsOf:
    """The calendar as it was COMMITTED (CLAUDE.md §29): `at(t)` is the latest committed version whose commit time is <= t,
    and an empty calendar that covers nothing before the first commit (every trade then UNKNOWN). The forward read uses it, so
    a row added, edited or backdated after a decision cannot steer that decision, and a calendar not yet extended over a
    day makes that day UNKNOWN instead of silently 'no news'. Commit dates are as trustworthy as git's (the seal instant
    rests on the same assumption)."""

    def __init__(self, versions):
        self.versions = sorted(versions, key=lambda v: v[0])
        self._times = [v[0] for v in self.versions]

    def at(self, t):
        k = bisect.bisect_right(self._times, t) - 1
        return self.versions[k][1] if k >= 0 else EMPTY

    @property
    def latest(self):
        return self.versions[-1][1] if self.versions else EMPTY


def calendar_versions(root, rel=CALENDAR):
    """[(commit time UTC, Calendar)] of every commit on the current history that touched `rel`: the calendar as committed. A
    version that does not load is a refusal, never a skipped version (skipping would silently age the calendar)."""
    r = subprocess.run(["git", "-C", root, "log", "--format=%H %cI", "--", rel], capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise Refused(f"refused: cannot read the git history of {rel} ({r.stderr.strip()})")
    out = []
    for ln in reversed(r.stdout.splitlines()):             # oldest first, so commits of one second keep their order
        sha, _, ts = ln.partition(" ")
        show = subprocess.run(["git", "-C", root, "show", f"{sha}:{rel}"], capture_output=True, check=False)
        if show.returncode != 0:
            continue                                       # the commit deleted the file: no calendar from then
        out.append((utc(ts.strip()), load_calendar(doc=json.loads(show.stdout.decode("utf-8")))))
    for a, b in zip(out, out[1:]):
        if b[0] < a[0]:
            raise Refused(f"refused: the commit times of {rel} go backwards ({iso(a[0])} then {iso(b[0])}): the history was "
                          f"rewritten or committed with a skewed clock, so 'as committed' is not defined")
    return out


def expected(ev, t):
    """True when the calendar as known at decision time `t` says `ev` will happen: available by t and not withdrawn by t.
    Unscheduled actions are never expected (nobody could know them in advance)."""
    if ev.status == "unscheduled":
        return False
    if ev.withdrawn is not None and ev.withdrawn <= t:
        return False
    return ev.avail is not None and ev.avail <= t


def state_unknown(ev, t):
    """True when the row's state at `t` cannot be established: its time is UNKNOWN, or its availability is UNKNOWN and it
    is not withdrawn by t. Such a row makes nearby trades UNKNOWN (§32), never clear."""
    if ev.status == "unscheduled" or ev.impact not in RESTRICTED:
        return False
    if ev.withdrawn is not None and ev.withdrawn <= t:
        return False
    return ev.t is None or ev.avail is None


def restricts(ev):
    return ev.impact in RESTRICTED and ev.t is not None and ev.status != "unscheduled"


def window(ev, pre=PRE_MIN, post=POST_MIN):
    return ev.t - datetime.timedelta(minutes=pre), ev.t + datetime.timedelta(minutes=post)


def merge(spans):
    """Union of closed intervals [(a, b, ids)]: overlapping OR touching intervals join (`<=`, CLAUDE.md §30)."""
    out = []
    for a, b, ids in sorted(spans, key=lambda s: (s[0], s[1])):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b), out[-1][2] + list(ids))
        else:
            out.append((a, b, list(ids)))
    return out


def windows_at(cal, t, lo, hi, pre=PRE_MIN, post=POST_MIN):
    """Merged restricted windows that meet [lo, hi], built only from rows expected at decision time `t`."""
    spans = []
    for ev in cal.near(lo - datetime.timedelta(minutes=post), hi + datetime.timedelta(minutes=pre)):
        if not restricts(ev) or not expected(ev, t):
            continue
        a, b = window(ev, pre, post)
        if a <= hi and b >= lo:
            spans.append((a, b, [ev.id]))
    return merge(spans)


def in_windows(t, wins):
    """Closed membership, as the live gate (scripts/event_risk.py:258): start <= t <= end."""
    return any(a <= t <= b for a, b, _ in wins)


def covered(cal, lo, hi):
    """Every type's coverage contains the New York dates of [lo, hi]."""
    d0, d1 = ny_date(lo), ny_date(hi)
    return all(f <= d0 and d1 <= th for f, th in cal.coverage.values())


def unknown_reasons(cal, lo, hi, pre=PRE_MIN, post=POST_MIN):
    """Why a trade open over [lo, hi] (UTC) cannot be judged, or [] when it can: outside coverage, or near a row whose
    time or availability is UNKNOWN at the decision. A row with an UNKNOWN time is taken to occupy its whole New York date
    (the conservative reading: any instant that day), widened by the buffers."""
    out = []
    if not covered(cal, lo, hi):
        out.append("coverage")
    for ev in cal.near(lo, hi):
        if ev.t is None:
            day0 = datetime.datetime(ev.date.year, ev.date.month, ev.date.day, tzinfo=NY).astimezone(UTC)
            a, b = day0 - datetime.timedelta(minutes=pre), day0 + datetime.timedelta(days=1, minutes=post)
            decision = a
        else:
            a, b = window(ev, pre, post)
            decision = a
        if a <= hi and b >= lo and state_unknown(ev, max(lo, decision) if ev.t is not None else lo):
            out.append(ev.id)
    return out


# ------------------------------------------------------------------------------------------------ policies (pure)
def row_span(row):
    """[entry, end of the exit bar] of a book_sim row (exit_time is the exit bar's OPEN time, book_sim.py:75)."""
    return utc(row["entry_time"]), utc(row["exit_time"]) + BAR


def server_day_end(t, zone):
    """The UTC instant that ends the server day (the broker's `zone`, 00:00 to 24:00) containing the instant `t`. Known at the
    entry: the hold-to-end-of-day components never leave their server day (scripts/research/book_sim.py:53)."""
    d = t.astimezone(zone).date() + datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day, tzinfo=zone).astimezone(UTC)


def classify(row, cal, pre=PRE_MIN, post=POST_MIN, zone=None):
    """The policy facts of one trade row, from the calendar as known at each decision:
    {'unknown': [reasons], 'p1_drop': bool, 'flatten_at': UTC datetime or None, 'events': [ids]}.
    P1 drops a row whose entry lies in a window known at the entry. P2 also flattens a kept row at the first window start s
    known at s with entry < s and the position still open at s (its exit bar opens at or after s: the position's state at s
    is a fact known at s, so the realised exit may be used there).
    UNKNOWN (coverage, a row with an UNKNOWN time or availability) is judged on the PLANNED span, the entry to the end of
    its server day, which is known at the entry; never on the realised exit, so that a stop hit cannot decide which trades
    the news filter removes (CLAUDE.md §37). Without a `zone` (synthetic rows in tests) only the realised end exists.
    `cal` is a Calendar (one state, point in time by each row's available_time) or an AsOf (the committed versions): every
    decision looks at `cal.at(its own time)` -- the entry for P1 and UNKNOWN, the window start for P2."""
    entry, end = row_span(row)
    exit_open = utc(row["exit_time"])
    span_end = max(end, server_day_end(entry, zone)) if zone is not None else end
    cal_e = cal.at(entry)
    unk = unknown_reasons(cal_e, entry, span_end, pre, post)
    if unk:
        return {"unknown": unk, "p1_drop": False, "flatten_at": None, "events": []}
    wins = windows_at(cal_e, entry, entry, entry, pre, post)
    if in_windows(entry, wins):
        return {"unknown": [], "p1_drop": True, "flatten_at": None, "events": [i for w in wins for i in w[2]]}
    cands = {ev.id: ev for ev in cal_e.near(entry, end)}
    cands.update({ev.id: ev for ev in cal.at(exit_open).near(entry, end)})     # rows that reached the calendar meanwhile
    starts = []
    for id_, ev in cands.items():
        if ev.t is None:
            continue
        a, _ = window(ev, pre, post)
        if not (entry < a <= exit_open):
            continue
        ev_a = cal.at(a).by_id.get(id_)                                          # the row as known at its window start
        if ev_a is not None and ev_a.t == ev.t and restricts(ev_a) and expected(ev_a, a):
            starts.append((a, id_))
    if starts:
        s = min(starts)[0]
        return {"unknown": [], "p1_drop": False, "flatten_at": s, "events": sorted(i for a, i in starts if a == s)}
    return {"unknown": [], "p1_drop": False, "flatten_at": None, "events": []}


def flatten_row(row, cut_open_iso, cut_close, cost_px, n_bars, cost_med_px=None):
    """`row` closed at the CLOSE of the bar that opens at `cut_open_iso` (the same R and cost arithmetic as
    book_sim.trades: R = (side x (exit - entry) - cost) / stop distance, book_sim.py:59, :74-76). `cost_px` prices the flatten
    (the conservative leg, see `series_cutter`); `R_med` prices it as book_sim does (median spread at both legs) and
    `R_neutral` with the cost the held trade paid, the two sensitivities of NF-P1 §3. `n_bars` = bars from the entry bar to
    the cut bar inclusive (the adverse path is cut there). Pure: no market data is read here."""
    px, side = row["entry_px"], row["side"]
    dist = row["stop_bp"] / 1e4 * px
    adv = list(row.get("adv_path_R", []))[:n_bars]
    gross = side * (cut_close - px)
    cost_med_px = cost_px if cost_med_px is None else cost_med_px
    return dict(row, exit_time=cut_open_iso, exit="news_flat", R=(gross - cost_px) / dist, R_med=(gross - cost_med_px) / dist,
                R_neutral=gross / dist - row.get("cost_R", 0.0), cost_R=cost_px / dist, adv_path_R=adv,
                mae_R=min([0.0] + adv) - cost_px / dist)


def flatten_paper_row(row, cut_open_iso, cut_close, cost_px, cost_med_px=None, cost_held_px=None):
    """A forward paper-log row (scripts/research/fvg_forward.py:296-297) closed at the cut bar's close; `cost_px`,
    `cost_med_px` and `cost_held_px` are the three pricings of `flatten_row`."""
    px, side, dist = row["entry"], row["side"], row["stop_distance"]
    gross = side * (cut_close - px)
    cost_med_px = cost_px if cost_med_px is None else cost_med_px
    cost_held_px = cost_px if cost_held_px is None else cost_held_px
    return dict(row, exit_time=cut_open_iso, exit=cut_close, exit_reason="news_flat", R=(gross - cost_px) / dist,
                R_med=(gross - cost_med_px) / dist, R_neutral=(gross - cost_held_px) / dist,
                net_bp=(gross - cost_px) / px * 1e4)


def apply_policies(rows, cal, cut_fn, pre=PRE_MIN, post=POST_MIN, zone=None):
    """{policy: [rows]} plus the bookkeeping. `cut_fn(row, flatten_at)` -> the flattened row (it reads bars; tests pass a
    pure stand-in), or None when no bar ends at the flatten instant (a data gap: the price is not known, so the trade is
    UNKNOWN, CLAUDE.md §20, §32). UNKNOWN rows leave all three policies alike, so the comparison stays on identical rows
    (§49)."""
    out = {p: [] for p in POLICIES}
    book = {"unknown": [], "p1_dropped": [], "p2_flattened": []}
    for r in rows:
        c = classify(r, cal, pre, post, zone)
        key = {"component": r.get("component"), "entry_time": r["entry_time"], "side": r["side"]}
        if c["unknown"]:
            book["unknown"].append(dict(key, reasons=c["unknown"]))
            continue
        f = None
        if not c["p1_drop"] and c["flatten_at"] is not None:
            f = cut_fn(r, c["flatten_at"])
            if f is None:
                book["unknown"].append(dict(key, reasons=["no_bar_at_flatten_instant"]))
                continue
        out["P0"].append(r)
        if c["p1_drop"]:
            book["p1_dropped"].append(dict(key, events=c["events"], R_P0=r["R"]))
            continue
        out["P1"].append(r)
        if f is not None:
            out["P2"].append(f)
            book["p2_flattened"].append(dict(key, events=c["events"], flatten_at=iso(c["flatten_at"]), R_P1=r["R"], R_P2=f["R"],
                                             R_P2_med=f.get("R_med", f["R"]), R_P2_neutral=f.get("R_neutral", f["R"])))
        else:
            out["P2"].append(r)
    return out, book


# ------------------------------------------------------------------------------------------------ measurement (pure)
def _how(r):
    """Exit reason: book_sim rows carry it in `exit`; forward paper rows in `exit_reason` (their `exit` is the price)."""
    return r["exit_reason"] if "exit_reason" in r else r.get("exit")


def summary(rows):
    """Descriptive per-policy numbers (NF-P1 §3)."""
    if not rows:
        return {"n": 0}
    rs = [r["R"] for r in rows]
    n = len(rs)
    mu = sum(rs) / n
    sd = math.sqrt(sum((x - mu) ** 2 for x in rs) / (n - 1)) if n > 1 else None
    by_year = collections.defaultdict(list)
    for r in rows:
        by_year[r["entry_time"][:4]].append(r["R"])
    return {"n": n, "mean_R": mu, "sd_R": sd, "sum_R": sum(rs), "worst_R": min(rs),
            "worst_loss_pct_of_balance": -100.0 * RISK * min(rs),
            "gap_through_stops": sum(1 for r in rows if _how(r) == "stop" and r["R"] < GAP_R),
            "stop_share": sum(1 for r in rows if _how(r) == "stop") / n,
            "flattened": sum(1 for r in rows if _how(r) == "news_flat"),
            "by_year": {y: {"n": len(v), "mean_R": sum(v) / len(v), "sum_R": sum(v)} for y, v in sorted(by_year.items())}}


def daily_breach_days(rows, risk=RISK, limit=DAILY_LOSS):
    """Server days whose realised loss at a fixed `risk` reaches the FTMO daily limit, and the same with every trade at its
    worst excursion (mae_R) at once (the floating bound pass_policy uses)."""
    real, flo = collections.defaultdict(float), collections.defaultdict(float)
    for r in rows:
        real[r["server_day"]] += risk * r["R"]
        flo[r["server_day"]] += risk * r.get("mae_R", min(0.0, r["R"]))
    return {"realised": sum(1 for v in real.values() if v <= -limit), "floating_bound": sum(1 for v in flo.values() if v <= -limit)}


def paired_delta(book):
    """P2 - P1 on the flattened trades: mean, CR1 SE clustered by the release day of the flatten, one-sided 90 % bounds."""
    rows = book["p2_flattened"]
    if not rows:
        return {"n": 0}
    d = [r["R_P2"] - r["R_P1"] for r in rows]
    n = len(d)
    mu = sum(d) / n
    cl = collections.defaultdict(float)
    for r, x in zip(rows, d):
        cl[r["flatten_at"][:10]] += x - mu
    g = len(cl)
    se = math.sqrt(g / (g - 1) * sum(v * v for v in cl.values()) / n ** 2) if g > 1 else None
    out = {"n": n, "clusters": g, "mean_dR": mu, "se_cr1": se,
           # the same trades priced two other ways (NF-P1 §3): the median-spread flatten leg book_sim uses, and the held
           # trade's own cost; the decision reads `mean_dR` only
           "sensitivity": {"mean_dR_median_cost": sum(r.get("R_P2_med", r["R_P2"]) - r["R_P1"] for r in rows) / n,
                           "mean_dR_cost_neutral": sum(r.get("R_P2_neutral", r["R_P2"]) - r["R_P1"] for r in rows) / n}}
    if se is not None:
        out.update(lower_90=mu - Z_ONE_SIDED_90 * se, upper_90=mu + Z_ONE_SIDED_90 * se)
    return out


def forward_verdict(delta):
    """NF-P1 §4, fixed now: CHEAP (P2 becomes a CANDIDATE for the owner) when the one-sided 90 % lower bound of the
    per-trade cost is above -MARGIN_R; otherwise COSTLY when the upper bound is below 0, else INCONCLUSIVE. Fewer than
    FWD_MIN_CLUSTERS release days: INCONCLUSIVE."""
    if not delta.get("n") or delta.get("se_cr1") is None or delta["clusters"] < FWD_MIN_CLUSTERS:
        return "INCONCLUSIVE"
    if delta["lower_90"] > -MARGIN_R:
        return "CHEAP"
    if delta["upper_90"] < 0:
        return "COSTLY"
    return "INCONCLUSIVE"


def forward_due(n_flattened, seal_day, today):
    end = datetime.date(seal_day.year + FWD_MAX_MONTHS // 12, seal_day.month, min(seal_day.day, 28))
    return n_flattened >= FWD_MIN_AFFECTED or today >= end


# ------------------------------------------------------------------------------------------------ calendar pinning
CAL_LINE = re.compile(r"(?m)^calendar-history-sha256 ([0-9a-f]{64}) before (\d{4}-\d{2}-\d{2}) (\S+)[ \t]*$")


def calendar_history_digest(doc, before):
    """sha256 of the calendar rows dated before `before` (canonical JSON, sorted by id): the exposed read's input. Rows
    appended later (forward dates) do not change it; any edit of an earlier row does."""
    rows = sorted((e for e in doc["events"] if e["date_et"] < before), key=lambda e: e["id"])
    cited = sorted({s["source"] for e in rows for s in e.get("sources", [])})
    blob = json.dumps({"coverage": {k: {"from": v["from"]} for k, v in doc["coverage"].items()}, "events": rows,
                       "sources": {sid: doc["sources"].get(sid) for sid in cited}},
                      sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def calendar_line(path=None, before=HISTORY_BEFORE):
    with open(path or os.path.join(ROOT, CALENDAR), encoding="utf-8") as fh:
        doc = json.load(fh)
    return f"calendar-history-sha256 {calendar_history_digest(doc, before)} before {before} {CALENDAR}"


def require_calendar_history(text, path=None):
    """Refuse unless the sealed text pins exactly this calendar history (one line, as `calendar_line` prints it)."""
    lines = CAL_LINE.findall(text)
    if len(lines) != 1:
        raise Refused("refused: the sealed text must carry exactly one 'calendar-history-sha256' line")
    sha, before, rel = lines[0]
    if rel != CALENDAR:
        raise Refused(f"refused: the sealed calendar line names {rel}, not {CALENDAR}")
    with open(path or os.path.join(ROOT, rel), encoding="utf-8") as fh:
        doc = json.load(fh)
    got = calendar_history_digest(doc, before)
    if got != sha:
        raise Refused(f"refused: the calendar's rows before {before} changed since the seal ({got[:12]} != {sha[:12]})")
    return before


def require_vc_first(root):
    """Refuse the exposed read until VC's xau-holdout read output is committed in this tree with VC's tag and read name
    (prereg_guard.require_read_json: tracked, unchanged, `meta.tag` == VC_TAG, `meta.read` == 'xau-holdout')."""
    pat = G.read_name("vc", "xau-holdout")
    d = os.path.join(root, *G.READ_DIR.split("/"))
    found = sorted(f"{G.READ_DIR}/{f}" for f in (os.listdir(d) if os.path.isdir(d) else ()) if pat.match(f"{G.READ_DIR}/{f}"))
    if not found:
        raise Refused("refused: the exposed NF read runs only after VC's xau-holdout read is committed (NF-P1 §3: VC's "
                      "window B is unread for its split and NF reports R on release days of those years)")
    if len(found) > 1:
        raise Refused(f"refused: more than one VC xau-holdout output ({', '.join(found)}); each read runs once")
    G.require_read_json(root, found[0], "vc", "xau-holdout", VC_TAG)
    return found[0]


def require_no_pycache_prefix():
    """Bytecode written outside the repository would hide executed code from `require_covered` (as edge_vc does)."""
    if sys.pycache_prefix is not None:
        raise Refused(f"refused: sys.pycache_prefix is {sys.pycache_prefix!r} (PYTHONPYCACHEPREFIX / -X pycache_prefix): "
                      f"bytecode outside the repository would hide executed code from require_covered")


# ------------------------------------------------------------------------------------------------ exposed data pin
DATASET_LINE = re.compile(r"(?m)^dataset-sha256 ([0-9a-f]{64}) (\S+) before (\S+)[ \t]*$")


@contextlib.contextmanager
def capped(BS, end=EXPOSED_END):
    """book_sim's loader sees the stored bars before `end` only, whatever `end` the caller passes (book_sim.trades asks for
    everything, scripts/research/book_sim.py:34, :41). Restored on exit."""
    orig, cap = BS.EC.load, end
    BS.EC.load = lambda sym, end=None, _orig=orig, _cap=cap: _orig(sym, end=_cap)   # book_sim passes `end=` as a keyword
    try:
        yield
    finally:
        BS.EC.load = orig


def exposed_dataset_digest():
    """sha256 of the stored XAUUSD 5m bars before EXPOSED_END, in prereg_guard.candles_digest's canonical form: a function of
    exactly the bars the exposed read can see, so bars appended later change nothing and any edit of an earlier bar does."""
    import history_store as HS
    doc, _ = HS.read_doc(SYMBOL, "5m", root=_bs().EC.HIST_ROOT)
    if doc is None:
        raise Refused(f"refused: no stored {SYMBOL} 5m history")
    return G.candles_digest([b for b in doc["candles"] if b["time"] < EXPOSED_END])


def dataset_line():
    """The line the sealed text carries (the manifest prints it), as `require_dataset` reads it."""
    return f"dataset-sha256 {exposed_dataset_digest()} {SYMBOL}|5m before {EXPOSED_END}"


def require_dataset(text):
    """Refuse the exposed read unless the stored history it will load is byte-identical to the sealed text's dataset line."""
    lines = DATASET_LINE.findall(text)
    if len(lines) != 1:
        raise Refused("refused: the sealed text must carry exactly one 'dataset-sha256' line (`news_flat.py manifest`)")
    sha, key, before = lines[0]
    if key != f"{SYMBOL}|5m" or before != EXPOSED_END:
        raise Refused(f"refused: the sealed dataset line names {key} before {before}, the read uses {SYMBOL}|5m before {EXPOSED_END}")
    got = exposed_dataset_digest()
    if got != sha:
        raise Refused(f"refused: the stored {key} history before {before} changed since the seal ({got[:12]} != {sha[:12]}); "
                      f"a re-export that edits old bars needs a re-seal by amendment")
    return {"key": key, "before": before, "sha256": got}


# ------------------------------------------------------------------------------------------------ market glue (reads)
def _bs():
    return _load("book_sim", "scripts/research/book_sim.py")


def series_cutter(s, costs):
    """A cut_fn over a loaded edge_census Series: the last bar of the entry's server day that ENDS at or before the flatten
    instant, its close and the bar count; None unless that bar ends EXACTLY at the instant (a data gap, §20/§32). Pricing:
    the held trade's entry leg at the median spread, the flatten leg at the p90 spread (the minutes before a release are not
    the median hour: the conservative reading, NF-P1 §2), with the book_sim pricing and the held trade's cost as the two
    sensitivities of `flatten_row`."""
    idx = {t: j for j, t in enumerate(s.T)}

    def cut(row, flatten_at):
        e = idx[row["entry_time"]]
        j = cut_bar(s, e, flatten_at)
        if not exact_cut(s, j, flatten_at):
            return None
        px = row["entry_px"]
        cost_p90 = (0.5 * costs.leg_at(s.dt[e], "median") + 0.5 * costs.leg_at(s.dt[j], "p90")) * px
        return flatten_row(row, s.T[j], s.C[j], cost_p90, j - e + 1, costs.round_trip_at(s.dt[e], s.dt[j]) * px)
    return cut


def cut_bar(s, e, flatten_at):
    """Index of the last bar of entry bar e's server day that ENDS at or before `flatten_at` (5m bars; a data gap gives an
    earlier bar). The entry bar itself when no later bar qualifies (on the 5-minute grid the entry bar always ends by then)."""
    j = e
    while j + 1 < len(s.T) and s.sday[j + 1] == s.sday[e] and s.dt[j + 1] + BAR <= flatten_at:
        j += 1
    return j


def exact_cut(s, j, flatten_at):
    """The cut bar ends exactly at the flatten instant: its close is the price at that instant. Otherwise the bar is stale."""
    return s.dt[j] + BAR == flatten_at


def planned_entries(s, events, hold="eod"):
    """book_sim.trades' entry filter WITHOUT the exit walk (outcome-blind): rows of entry time, server day, side and the
    planned exit bar (the server day's last bar). Same skips as book_sim.py:48-57."""
    last = {}
    for d, rows in s.day_rows.items():
        for i in rows:
            last[i] = rows[-1]
    out = []
    for ev in events(s):
        e, side = ev["entry_i"], ev["side"]
        if e >= len(s.C):
            continue
        x = last[e] if hold == "eod" else e + hold - 1
        if x >= len(s.C) or s.sday[x] != s.sday[e]:
            continue
        if not s.sigma(ev["i"]):
            continue
        out.append({"entry_time": s.T[e], "exit_time": s.T[x], "server_day": str(s.sday[x]), "side": side})
    return out


def dry_counts(rows_by_comp, cal, zone=None, s=None):
    """Outcome-blind counts per component and year (and `pooled`, both components): planned trades, P1 entry blocks,
    planned-open across a window start (an upper bound on P2's flattened trades: a stop may close a trade first) with the
    number of release days those fall on (the forward statistic clusters on them), and UNKNOWN trades; blocks, flattens and
    UNKNOWN also by release type. With the series `s`, a planned flatten whose cut bar is missing (a data gap at the window
    start) counts as `no_bar_at_flatten_instant`, as the read would make it UNKNOWN. No exit walk and no R: only entry
    times, the planned exit, bar existence and the calendar."""
    kind = {e.id: e.type for e in cal.events}
    idx = {t: j for j, t in enumerate(s.T)} if s is not None else None
    out, pooled, pooled_days = {}, collections.defaultdict(collections.Counter), collections.defaultdict(set)
    for comp, rows in rows_by_comp.items():
        c, days = collections.defaultdict(collections.Counter), collections.defaultdict(set)
        for r in rows:
            y = r["entry_time"][:4]
            k = classify(r, cal, zone=zone)
            c[y]["planned"] += 1
            if k["unknown"]:
                c[y]["unknown"] += 1
                for t in sorted({kind.get(x, x) for x in k["unknown"]}):
                    c[y]["unknown:" + t] += 1
            elif k["p1_drop"]:
                c[y]["p1_entry_blocked"] += 1
                for t in sorted({kind[x] for x in k["events"]}):
                    c[y]["p1_entry_blocked:" + t] += 1
            elif k["flatten_at"] is not None:
                if s is not None and not exact_cut(s, cut_bar(s, idx[r["entry_time"]], k["flatten_at"]), k["flatten_at"]):
                    c[y]["no_bar_at_flatten_instant"] += 1
                    continue
                c[y]["planned_open_across_window"] += 1
                for t in sorted({kind[x] for x in k["events"]}):
                    c[y]["planned_open_across_window:" + t] += 1
                days[y].add(iso(k["flatten_at"])[:10])
        out[comp] = {y: dict(v, release_days_with_open_trade=len(days[y])) for y, v in sorted(c.items())}
        for y, v in c.items():
            pooled[y].update(v)
            pooled_days[y] |= days[y]
    out["pooled"] = {y: dict(v, release_days_with_open_trade=len(pooled_days[y])) for y, v in sorted(pooled.items())}
    return out


# ------------------------------------------------------------------------------------------------ CLI
def _rel(p):
    return os.path.relpath(os.path.abspath(p), ROOT).replace(os.sep, "/")


def _dump(res, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {path}")


def cmd_check_calendar(path=None):
    cal = load_calendar(path)
    c = collections.Counter((e.type, e.status, "time" if e.t else "time UNKNOWN") for e in cal.events)
    lead = [(e.t - e.avail).total_seconds() / 86400 for e in cal.events if e.t and e.avail and e.status == "released"]
    res = {"snapshot": cal.snapshot, "sha256": cal.sha256, "events": len(cal.events),
           "by_type_status": {"|".join(k): v for k, v in sorted(c.items())},
           "coverage": {k: [str(a), str(b)] for k, v in cal.coverage.items() for a, b in [v]},
           "time_unknown": [e.id for e in cal.events if e.t is None and e.status != "unscheduled"],
           "availability_unknown": [e.id for e in cal.events if e.avail is None and e.status in ("released", "scheduled")],
           "min_days_known_before_release": min(lead) if lead else None,
           "postponed_or_cancelled": [e.id for e in cal.events if e.status in ("postponed", "cancelled")]}
    print(json.dumps(res, indent=1))
    return res


def cmd_dry_run(out):
    for read in READS:
        if G.read_name(FAMILY, read).match(_rel(out)):
            raise Refused(f"refused: {out} is the {read} read's output name; a dry run there would block that read for good")
    G.refuse_overwrite(out)
    cal = load_calendar()
    BS = _bs()
    import real_costs as RC
    zone = RC.server_zone(BS.EC.PROVIDER)[1]
    s = BS.EC.load(SYMBOL, end=EXPOSED_END)
    rows = {c: planned_entries(s, BS.COMPONENTS[c][1], BS.COMPONENTS[c][2]) for c in COMPS}
    counts = dry_counts(rows, cal, zone, s)
    _dump({"meta": {"script": SCRIPT, "kind": "dry-run (outcome-blind counts; no exit walk, no R)", "calendar": CALENDAR,
                    "calendar_sha256": cal.sha256, "snapshot": cal.snapshot, "git_head": G.git_head(ROOT),
                    "exposed_end": EXPOSED_END, "dataset_line": dataset_line(),
                    "dataset": G.dataset_snapshot(os.path.join(ROOT, "data", "history", "ftmo"), [(SYMBOL, "5m")]),
                    "counts_sha256": hashlib.sha256(json.dumps(counts, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                    "code_sha256": {p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE}},
           "counts": counts}, out)


def exposed_result(cal, rows, s, costs, zone, PP):
    """The exposed read's whole report from injected inputs: `rows` = the v4 rows of book_sim tagged with their
    `component`, `s` = the edge_census Series they were built on, `costs` its cost table, `zone` the broker clock, `PP` =
    scripts/research/pass_policy.py. Nothing here reads a file."""
    pol, book = apply_policies(rows, cal, series_cutter(s, costs), zone=zone)
    sday = {t: str(d) for t, d in zip(s.T, s.sday)}
    for f in pol["P2"]:
        if f.get("exit") == "news_flat" and f["server_day"] != sday[f["exit_time"]]:
            raise Refused(f"refused: a flattened trade left its server day ({f['entry_time']})")
    ftmo = {}
    pp_pol = dict(book="v4", risk=RISK, throttle="dd3", day_stop=None, floating="mae")
    for p in POLICIES:
        by = {c: [r for r in pol[p] if r["component"] == c] for c in COMPS}
        comps = [c for c in COMPS if by[c]]
        trades = PP.prepare(by, comps) if comps else []
        ftmo[p] = {"selection": PP.evaluate_hist(trades, pp_pol, "2000-01-01", SELECT_END) if trades else {"n": 0},
                   "confirmation": PP.evaluate_hist(trades, pp_pol, SELECT_END, "2100-01-01") if trades else {"n": 0},
                   "daily_loss_breach_days": daily_breach_days(pol[p])}
    return {"policies": {p: summary(pol[p]) for p in POLICIES}, "ftmo": ftmo, "p2_vs_p1": paired_delta(book),
            "p1_vs_p0": {"dropped": len(book["p1_dropped"]), "sum_R_dropped": sum(r["R_P0"] for r in book["p1_dropped"])},
            "bookkeeping": book, "label": "POLICY-EXPOSED (descriptive; NF-P1 §3)"}


def cost_profile(EC, sym=SYMBOL):
    """The cost profile that prices the trades (edge_census.Costs, at read time) with the sha256 of the symbol's spec file
    under it and its price_ref provenance (as edge_vc.cost_profile; CLAUDE.md §46)."""
    import real_costs as RC
    p = RC.spec_path(EC.COST_PROFILE, sym)
    return {"name": EC.COST_PROFILE, "spec_sha256": G.file_sha256(p) if os.path.exists(p) else None,
            "price_ref_info": RC.price_ref_info(EC.COST_PROFILE, sym)}


def _exposed(cal):
    BS = _bs()
    PP = _load("pass_policy", "scripts/research/pass_policy.py")
    import real_costs as RC
    zone = RC.server_zone(BS.EC.PROVIDER)[1]
    with capped(BS):                                     # bars before EXPOSED_END only, for the rows and for the cut
        raw = {c: BS.trades(*BS.COMPONENTS[c], stop_k=STOP_K) for c in COMPS}
        s = BS.EC.load(SYMBOL, end=BS.END)
    rows = [dict(r, component=c) for c in COMPS for r in raw[c]]
    res = exposed_result(cal, rows, s, BS.EC.Costs(SYMBOL), zone, PP)
    res["cost_profile"] = cost_profile(BS.EC)
    return res, [(SYMBOL, "5m")]


def last_full_day(times, zone):
    """The last server day an export surely holds whole: the day before the server day of its last bar (as
    edge_cal.last_full_day). None without bars. The forward 'due' clock: a function of the data, never of the wall clock."""
    if not times:
        return None
    return utc(max(times)).astimezone(zone).date() - datetime.timedelta(days=1)


def forward_window(rows):
    """[first entry, end of the last exit bar] of the forward rows (UTC)."""
    return min(utc(r["entry_time"]) for r in rows), max(utc(r["exit_time"]) for r in rows) + BAR


def reprice_paper_row(row, s, idx, costs):
    """The paper row priced at read time with `costs`, from its own logged entry and exit prices: the held trade (P1) and the
    flattened one (P2) then share one cost basis. The log's own R was priced by fvg_forward.resolve_row with the cost table
    current at resolve time (none recorded), so it is kept only as `R_logged`."""
    e, x = idx[row["entry_time"]], idx[row["exit_time"]]
    gross = row["side"] * (row["exit"] - row["entry"])
    cost = costs.round_trip_at(s.dt[e], s.dt[x]) * row["entry"]
    return dict(row, R_logged=row["R"], R=(gross - cost) / row["stop_distance"], net_bp=(gross - cost) / row["entry"] * 1e4)


def forward_result(cal, rows, s, costs, zone, seal_day, data_end):
    """The forward read's whole report from injected inputs: `rows` = closed paper-log rows of the v4 components after the
    seal, `s` = the merged-bar Series, `costs` its cost table, `cal` an AsOf (the committed calendar versions) or, in tests,
    a Calendar, `data_end` = the last full server day the bars hold. Refused when the latest calendar does not cover the
    window or the read is not due (NF-P1 §4)."""
    if not rows:
        raise Refused("refused: no closed forward v4 rows after the seal")
    lo, hi = forward_window(rows)
    if not covered(cal.latest, lo, hi):
        raise Refused("refused: the calendar does not cover the forward window; append the new releases first")
    idx = {t: j for j, t in enumerate(s.T)}
    rows = [reprice_paper_row(r, s, idx, costs) for r in rows]

    def cut(row, flatten_at):
        e = idx[row["entry_time"]]
        j = cut_bar(s, e, flatten_at)
        if not exact_cut(s, j, flatten_at):
            return None
        px = row["entry"]
        cost_p90 = (0.5 * costs.leg_at(s.dt[e], "median") + 0.5 * costs.leg_at(s.dt[j], "p90")) * px
        return flatten_paper_row(row, s.T[j], s.C[j], cost_p90, costs.round_trip_at(s.dt[e], s.dt[j]) * px,
                                 costs.round_trip_at(s.dt[e], s.dt[idx[row["exit_time"]]]) * px)

    pol, book = apply_policies(rows, cal, cut, zone=zone)
    if not forward_due(len(book["p2_flattened"]), seal_day, data_end):
        raise Refused(f"refused: forward read not due ({len(book['p2_flattened'])} flattened trades < {FWD_MIN_AFFECTED}, "
                      f"data to {data_end} < {FWD_MAX_MONTHS} months after the seal {seal_day})")
    delta = paired_delta(book)
    return {"p2_vs_p1": delta, "verdict": forward_verdict(delta), "policies": {p: summary(pol[p]) for p in POLICIES},
            "bookkeeping": book, "label": "FAIR (forward, NF-P1 §4)", "data_end": str(data_end)}


def forward_snapshot(FF, merged):
    """The forward read's dataset snapshot (CLAUDE.md §10, §46): the paper log (untracked, appended by fvg_forward: the
    sha256 and row count of its bytes), the merged 5m bars the read used (canonical digest, count, first and last bar) and
    their sources (the stored history is in `meta.dataset`; the forward store and live bridge files here)."""
    def sha_or_none(path):
        return G.file_sha256(path) if os.path.exists(path) else None
    log = FF.LOG
    n = sum(1 for ln in open(log) if ln.strip()) if os.path.exists(log) else 0
    return {"paper_log": {"path": _rel(log), "sha256": sha_or_none(log), "rows": n},
            "candles": {"sha256": G.candles_digest(merged), "n": len(merged), "first": merged[0]["time"] if merged else None,
                        "last": merged[-1]["time"] if merged else None},
            "sources": {"forward_store_sha256": sha_or_none(FF._store_path(SYMBOL)),
                        "live_bridge_sha256": sha_or_none(FF.live_path(SYMBOL))}}


def _forward(cal, seal_day, zone):
    FF = _load("fvg_forward", "scripts/research/fvg_forward.py")
    rows = [r for r in FF._read_log() if r.get("component") in COMPS and r.get("status") == "closed"
            and abs(float(r.get("stop_k", 0)) - STOP_K) < 1e-9 and utc(r["entry_time"]).astimezone(zone).date() >= seal_day]
    if not rows:
        raise Refused("refused: no closed forward v4 rows after the seal")
    merged = FF.merged_candles(SYMBOL)
    s = FF.EC.Series(SYMBOL, merged, zone, end="9999-12-31T00:00:00Z", sigma_every_day=True)
    asof = AsOf(calendar_versions(ROOT))                 # the calendar as COMMITTED at each decision (CLAUDE.md §29)
    res = forward_result(asof, rows, s, FF.EC.Costs(SYMBOL), zone, seal_day, last_full_day([c["time"] for c in merged], zone))
    res["forward_snapshot"] = forward_snapshot(FF, merged)
    res["cost_profile"] = cost_profile(FF.EC)
    res["calendar_versions"] = len(asof.versions)
    return res, [(SYMBOL, "5m")]


def require_ledger(root):
    """The research ledger registers the budget before any read (NF-P1 §7, §12 step 5; CLAUDE.md §43-44): LEDGER is
    committed unchanged and its LEDGER_KEY entry names PREREG and TAG and carries the budget counts the code runs (the
    number of policies and of reads), so a count cannot change silently. Returns ({path, entry, sha256}, entry); the ledger
    is not code, so the manifest does not cover it."""
    G.require_committed(root, [LEDGER])
    path = os.path.join(root, LEDGER)
    with open(path, encoding="utf-8") as fh:
        entry = json.load(fh).get(LEDGER_KEY) or {}
    if entry.get("preregistration") != PREREG or entry.get("tag") != TAG:
        raise Refused(f"refused: {LEDGER} has no {LEDGER_KEY!r} entry naming {PREREG} and {TAG} (the seal commit adds it)")
    if entry.get("policies") != len(POLICIES) or entry.get("reads") != len(READS):
        raise Refused(f"refused: the ledger entry {LEDGER_KEY!r} records {entry.get('policies')} policies and "
                      f"{entry.get('reads')} reads, the code runs {len(POLICIES)} and {len(READS)}")
    return {"path": LEDGER, "entry": LEDGER_KEY, "sha256": G.file_sha256(path)}, entry


def cmd_run(read, out):
    G.refuse_overwrite(out)
    G.require_read_once(ROOT, _rel(out), FAMILY, read)
    text = G.require_sealed(ROOT, PREREG, TAG)
    G.require_committed(ROOT, CODE + (CALENDAR,))
    man = G.require_fingerprint(ROOT, text, CODE)
    before = require_calendar_history(text)
    ledger, _entry = require_ledger(ROOT)
    pins = {}
    if read == "exposed":
        pins["pinned_dataset"] = require_dataset(text)   # the bars the read will see are the sealed ones
        if AFTER_VC:
            pins["vc_read"] = require_vc_first(ROOT)
    require_no_pycache_prefix()
    G.trace_start(ROOT)                                  # before any data is loaded: everything the read executes is traced
    cal = load_calendar()
    window = {}
    if read == "exposed":
        res, pairs = _exposed(cal)
    else:
        import real_costs as RC
        zone = RC.server_zone("mt5_bridge_ftmo")[1]
        seal_day = G.first_forward_day(ROOT, PREREG, zone)
        window = {"seal_commit": G.seal_time(ROOT, PREREG).isoformat(), "first_forward_day": str(seal_day)}
        res, pairs = _forward(cal, seal_day, zone)
    res["meta"] = {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "read": read, **window,
                   "calendar": CALENDAR, "calendar_sha256": cal.sha256, "calendar_history_before": before,
                   "ledger": ledger, "snapshot": cal.snapshot, "git_head": G.git_head(ROOT), "pre_min": PRE_MIN,
                   "post_min": POST_MIN, "stop_k": STOP_K, "components": list(COMPS), "after_vc": AFTER_VC,
                   "margin_r": MARGIN_R, "exposed_end": EXPOSED_END, **pins,
                   "dataset": G.dataset_snapshot(os.path.join(ROOT, "data", "history", "ftmo"), pairs)}
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print the code-sha256, calendar-history and dataset lines the sealed text must carry")
    c = sub.add_parser("check-calendar")
    c.add_argument("--calendar")
    d = sub.add_parser("dry-run")
    d.add_argument("--out", required=True)
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE) + [calendar_line(), dataset_line()]))
    elif a.cmd == "check-calendar":
        cmd_check_calendar(a.calendar)
    elif a.cmd == "dry-run":
        cmd_dry_run(a.out)
    else:
        cmd_run(a.read, a.out)


if __name__ == "__main__":
    main()
