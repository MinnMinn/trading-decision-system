#!/usr/bin/env python3
"""Shared definitions of experiment IC, "can Claude trade ICT discretionarily with an edge?"
(docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md; implementation note
docs/plans/2026-10-04-claude-ict-implementation.md). RESEARCH ONLY: nothing here places an order or reads an account.

Imported by BOTH the prompt harness (scripts/research/claude_ict_harness.py) and the evaluator
(scripts/research/claude_ict_eval.py). Neither of those imports the other. What lives here is what both must agree on,
and none of it reads a market outcome:

* the window, the instruments and their killzones (knowledge/ict/core-a.md §2.1, `1. Killzones p3`), in New York time
  with DST through zoneinfo, and the decision-point enumeration -- it reads bar OPEN TIMES only (CLAUDE.md §21);
* the FTMO-Demo server clock, always through real_costs.server_zone -> mt5_time (+2/+3 on US DST dates,
  docs/audits/2026-09-29-ftmo-server-timezone.md), never a fixed offset: the trading day, the 4H alignment, the
  rollover;
* the §4 time exit (16:00 New York of the position's server day; the rollover is that day's server midnight);
* the spread snapshot (scripts/real_costs.py, profile ftmo_demo_2026_09, the table bucket of the killzone-open hour);
* the 5m history loader, the answer-JSON extraction, and the git / sha256 guards.
"""
import bisect
import datetime
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import history_store as HS  # noqa: E402 -- THE history reader (single-file / split-gz shapes)
import real_costs as RC  # noqa: E402 -- THE cost tables and the FTMO server clock

UTC = datetime.timezone.utc
ET = ZoneInfo("America/New_York")
BAR = datetime.timedelta(minutes=5)

EXPERIMENT = "IC"
PREREG = "docs/plans/2026-10-04-claude-ict-discretionary-preregistration.md"
IMPL_NOTE = "docs/plans/2026-10-04-claude-ict-implementation.md"
EXP_DIR = "docs/experiments/claude-ict"
TEMPLATE = EXP_DIR + "/prompt-template.md"
MANIFEST = EXP_DIR + "/manifest.json"
PROMPTS_DIR = EXP_DIR + "/prompts"
SYSTEM_PROMPT_NAME = "system.txt"
DECISIONS = EXP_DIR + "/decisions.jsonl"
RESULT = EXP_DIR + "/evaluation.json"
COMMON = "scripts/research/claude_ict_common.py"
HARNESS = "scripts/research/claude_ict_harness.py"
EVALUATOR = "scripts/research/claude_ict_eval.py"
#: The knowledge base the system prompt embeds, verbatim, in this order (pre-registration §1: knowledge/ict/*.md,
#: knowledge/integrated/method.md, the ict-skill). `kb_glob_matches()` refuses a build if knowledge/ict/ gains a file.
KB_FILES = ("knowledge/ict/core-a.md", "knowledge/ict/core-b.md", "knowledge/ict/mentorship-2024.md",
            "knowledge/ict/models.md", "knowledge/integrated/method.md", ".claude/skills/ict-skill/SKILL.md")
#: Repository code and configuration a `build` executes or reads besides this module and the harness (recorded with
#: their sha256 in the manifest, CLAUDE.md §46).
BUILD_LIBS = ("scripts/history_store.py", "scripts/real_costs.py", "scripts/mt5_time.py",
              "docs/architecture/providers.json")

#: Pre-registration §2: 2026-07-01 00:00 UTC -> 2026-10-02 20:45 UTC (the open label of the last 5m bar).
WINDOW_START = "2026-07-01T00:00:00Z"
WINDOW_LAST_BAR = "2026-10-02T20:45:00Z"
INSTRUMENTS = ("XAUUSD", "US500")
KILLZONE_SET = {"XAUUSD": "forex", "US500": "indices"}
#: knowledge/ict/core-a.md §2.1: (id, label, open (h, m), end (h, m)) in New York time, the sets the pre-registration
#: §3 names (XAUUSD: forex London + New York AM; US500: indices London + New York AM + New York PM).
KILLZONES = {
    "forex": (("london", "London", (2, 0), (5, 0)), ("ny_am", "New York AM", (7, 0), (10, 0))),
    "indices": (("london", "London", (2, 0), (5, 0)), ("ny_am", "New York AM", (8, 30), (11, 0)),
                ("ny_pm", "New York PM", (13, 30), (16, 0))),
}
ASIA_ET = ((20, 0), (0, 0))          # the Asia killzone of both sets: 20:00 -> 00:00 New York
TIME_EXIT_ET = (16, 0)               # pre-registration §4
PROVIDER = "mt5_bridge_ftmo"         # docs/architecture/providers.json id of the FTMO-Demo server clock
HIST_ROOT = os.path.join(ROOT, "data", "history", "ftmo")
COST_PROFILE = "ftmo_demo_2026_09"   # the FTMO spread table as exported (absolute price units)
SPREAD_STAT = "median"
MODEL_ID = "claude-opus-5-5"
#: Thinking depth of every decision (amendment 1, 2026-10-05): pinned, because the CLI default is version-dependent and
#: its result does not record it.
EFFORT = "high"
INSTRUMENT_NOTE = {"XAUUSD": "spot XAU/USD CFD (FTMO-Demo symbol XAUUSD)",
                   "US500": "S&P 500 index CFD (FTMO-Demo symbol US500.cash)"}
SYSTEM_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"   # a line the CLI would split the system prompt at
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$")


class Refused(SystemExit):
    """A guard that must stop the command, with the reason a person needs (same discipline as prereg_guard.Refused)."""


# ------------------------------------------------------------------------------------------------ time
def parse_z(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def iso_z(dt):
    """UTC ISO-8601 with seconds and a 'Z', the format of every stored bar label (so labels compare as strings)."""
    if dt.tzinfo is None:
        raise ValueError(f"naive datetime {dt!r}: refusing to guess its zone")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def short_z(dt):
    """'2026-07-01T06:00Z' -- the minute-precision UTC label used inside prompts."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def server_zone():
    """The FTMO-Demo server clock as a tzinfo (real_costs.server_zone -> mt5_time; refuses rather than defaulting)."""
    return RC.server_zone(PROVIDER)[1]


def server_date(t):
    return t.astimezone(server_zone()).date()


def server_midnight(day):
    """UTC instant of 00:00 server time on server date `day` (the broker's daily rollover, 17:00 New York)."""
    return datetime.datetime.combine(day, datetime.time(0), tzinfo=server_zone()).astimezone(UTC)


def et_instant(day, hm):
    """UTC instant of New York wall time `hm` = (hour, minute) on calendar date `day`. Refuses a wall time that does
    not exist (spring forward) or exists twice (fall back) instead of picking one (CLAUDE.md §21)."""
    h, m = hm
    local = datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=ET)
    if local.replace(fold=1).utcoffset() != local.utcoffset():
        raise ValueError(f"{day} {h:02d}:{m:02d} New York is ambiguous (DST fall back)")
    utc = local.astimezone(UTC)
    back = utc.astimezone(ET)
    if (back.date(), back.hour, back.minute) != (day, h, m):
        raise ValueError(f"{day} {h:02d}:{m:02d} New York does not exist (DST spring forward)")
    return utc


def et_label(t):
    """'2026-06-30 17:00' New York wall time of instant t."""
    return t.astimezone(ET).strftime("%Y-%m-%d %H:%M")


def et_offset_label(t):
    """'-4' / '-5': New York's UTC offset at instant t, in whole hours (refuses anything else)."""
    off = t.astimezone(ET).utcoffset().total_seconds() / 3600
    if off != int(off):
        raise ValueError(f"New York offset {off} h is not whole")
    return f"{int(off):+d}"


def time_exit(t):
    """(time exit, rollover) of a position open at instant t (pre-registration §4): 16:00 New York on the FTMO server
    day that contains t, and that day's end (the server midnight = 17:00 New York). Refuses unless the time exit lies
    inside the server day, before its rollover, so no position can be held into the rollover or overnight."""
    d = server_date(t)
    start, rollover = server_midnight(d), server_midnight(d + datetime.timedelta(days=1))
    exit_ = et_instant(d, TIME_EXIT_ET)
    if not start < exit_ < rollover:
        raise ValueError(f"16:00 New York {exit_} is not inside server day {d} ({start} .. {rollover})")
    return exit_, rollover


def no_fill_after(t):
    """True when a new fill at instant t is not allowed: at/after the §4 time exit of t's server day (the 16:00-17:00
    New York hour) -- a position opened then would have to be closed before it exists."""
    return t >= time_exit(t)[0]


# ------------------------------------------------------------------------------------------------ decision points
def killzones(sym):
    return KILLZONES[KILLZONE_SET[sym]]


def killzone_window(sym, kz_id, day):
    for k, _label, a, b in killzones(sym):
        if k == kz_id:
            return et_instant(day, a), et_instant(day, b)
    raise KeyError(f"{sym} has no killzone {kz_id!r}")


def window_bounds(start=WINDOW_START, last_bar=WINDOW_LAST_BAR):
    """(start, end) instants of the window: end = the CLOSE of its last 5m bar."""
    return parse_z(start), parse_z(last_bar) + BAR


def point_id(sym, kz_id, day):
    return f"{day.isoformat()}|{sym}|{kz_id}"


def prompt_name(pid):
    return pid.replace("|", "_") + ".txt"


def decision_points(times_by_sym, start=None, end=None, instruments=INSTRUMENTS):
    """(points, skipped). One decision point per (instrument, killzone, New York weekday) whose killzone lies inside
    [start, end]; a killzone that holds no 5m bar is skipped and counted (pre-registration §3). OUTCOME-BLIND: reads
    the sorted bar OPEN-TIME labels in `times_by_sym` only, never a price. A trading day is a Monday-Friday New York
    calendar date; the killzones of one date all fall in the FTMO server day of that date (asserted)."""
    if start is None or end is None:
        s0, e0 = window_bounds()
        start, end = start or s0, end or e0
    points, skipped = [], []
    day = start.astimezone(ET).date()
    last = end.astimezone(ET).date()
    while day <= last:
        if day.weekday() < 5:
            for sym in instruments:
                times = times_by_sym[sym]
                for kz_id, label, a, b in killzones(sym):
                    o, e = et_instant(day, a), et_instant(day, b)
                    if o < start or e > end:
                        continue
                    if server_date(o) != day:
                        raise ValueError(f"{sym} {kz_id} {day}: killzone open {o} is not in server day {day}")
                    lo = bisect.bisect_left(times, iso_z(o))
                    hi = bisect.bisect_left(times, iso_z(e))
                    pid = point_id(sym, kz_id, day)
                    row = {"id": pid, "instrument": sym, "killzone": kz_id, "killzone_label": label,
                           "date_et": day.isoformat(), "kz_open_utc": iso_z(o), "kz_end_utc": iso_z(e)}
                    if hi <= lo:
                        skipped.append(dict(row, reason="no_data_in_killzone"))
                        continue
                    row["time_exit_utc"] = iso_z(time_exit(o)[0])
                    points.append(row)
        day += datetime.timedelta(days=1)
    points.sort(key=lambda p: (p["kz_open_utc"], p["instrument"]))
    return points, skipped


# ------------------------------------------------------------------------------------------------ history
def _check_bar(sym, b):
    t = b.get("time")
    if not isinstance(t, str) or not TIME_RE.match(t):
        raise Refused(f"refused: {sym} bar time {t!r} is not a 'YYYY-MM-DDTHH:MM:00Z' label")
    o, h, l, c = (b.get(k) for k in ("open", "high", "low", "close"))
    for v in (o, h, l, c):
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0:
            raise Refused(f"refused: {sym} bar {t} has a non-finite / non-positive price ({o}, {h}, {l}, {c}) -- INVALID data")
    if not (l <= min(o, c) and h >= max(o, c)):
        raise Refused(f"refused: {sym} bar {t} is not a valid OHLC bar ({o}, {h}, {l}, {c}) -- INVALID data")


def load_bars(sym, hist_root=None, since=None, until=None, validate=True):
    """5m BID bars of `sym` from `hist_root` (default data/history/ftmo), as [{"time","open","high","low","close"}],
    strictly increasing in time. For a split-gz series only the yearly parts overlapping [since, until) are read; the
    result is cut to [since, until) when given. Refuses missing, unordered or invalid bars (CLAUDE.md §20)."""
    root = hist_root or HIST_ROOT
    path, shape = HS.resolve(sym, "5m", root=root)
    if shape is None:
        raise Refused(f"refused: no 5m history for {sym} under {root}")
    if shape == "file":
        raw = HS.read_at(path, shape)["candles"]
    else:
        with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
            years = sorted(json.load(fh).get("years") or ())
        y0 = since.year if since is not None else None
        y1 = until.year if until is not None else None
        raw = []
        for y in years:
            if (y0 is not None and int(y) < y0) or (y1 is not None and int(y) > y1):
                continue
            with gzip.open(os.path.join(path, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
                raw.extend(json.load(fh)["candles"])
    lo = iso_z(since) if since is not None else None
    hi = iso_z(until) if until is not None else None
    out, prev = [], None
    for b in raw:
        t = b.get("time")
        if (lo is not None and t < lo) or (hi is not None and t >= hi):
            continue
        if validate:
            _check_bar(sym, b)
        if prev is not None and t <= prev:
            raise Refused(f"refused: {sym} bar {t} is not after {prev} -- the series must be strictly increasing")
        prev = t
        out.append({"time": t, "open": float(b["open"]), "high": float(b["high"]), "low": float(b["low"]),
                    "close": float(b["close"])})
    return out


#: The stored bars every arm reads, pinned by `build` (manifest `data_pins`) and re-checked by `evaluate` (implementation
#: note §4 item 31): (timeframe, days before the window start, None = from the first bar) -- the 5m series from its first
#: bar (the prompts, C's fills, the H7 / G9 detectors of arm T read years of it), the 15m series from 35 days before the
#: window (the ICT engine of arm M). A re-export that changes any of these bars refuses the evaluation; bars appended
#: after the window do not.
DATA_PIN_TFS = (("5m", None), ("15m", 35))


def bars_digest(sym, tf, since, until, hist_root=None):
    """{n, first, last, sha256} of the stored bars of `sym` / `tf` whose open label is in [since, until) (since None = from
    the first bar), one canonical [time, open, high, low, close] line per bar (prereg_guard.candles_digest's form)."""
    doc, _ = HS.read_doc(sym, tf, root=hist_root or HIST_ROOT)
    if doc is None:
        raise Refused(f"refused: no {tf} history for {sym} under {hist_root or HIST_ROOT}")
    lo, hi = (iso_z(since) if since is not None else None), iso_z(until)
    h, n, first, last = hashlib.sha256(), 0, None, None
    for b in doc["candles"]:
        t = b["time"]
        if (lo is not None and t < lo) or t >= hi:
            continue
        h.update(json.dumps([t, b["open"], b["high"], b["low"], b["close"]], separators=(",", ":")).encode("utf-8"))
        h.update(b"\n")
        n += 1
        first = first or t
        last = t
    return {"n": n, "first": first, "last": last, "sha256": h.hexdigest()}


def data_pins(window, hist_root=None, instruments=INSTRUMENTS):
    start, end = window
    out = {}
    for sym in instruments:
        for tf, days in DATA_PIN_TFS:
            since = None if days is None else start - datetime.timedelta(days=days)
            out[f"{sym}|{tf}"] = dict(bars_digest(sym, tf, since, end, hist_root),
                                      since=iso_z(since) if since is not None else None, until=iso_z(end))
    return out


def dataset_snapshot(sym, hist_root=None):
    """CLAUDE.md §10: the identity of every byte behind the 5m series (history_store.digest / part_digests)."""
    root = hist_root or HIST_ROOT
    return {"symbol": sym, "timeframe": "5m", "root": os.path.relpath(root, ROOT).replace(os.sep, "/"),
            "sha256": HS.digest(sym, "5m", root=root), "parts": HS.part_digests(sym, "5m", root=root)}


# ------------------------------------------------------------------------------------------------ costs
def spread_snapshot(sym, at):
    """The spread the prompt shows and the simulator charges for an order placed at instant `at` (pre-registration
    §3, §4): the FTMO-Demo median spread of the table bucket of `at`'s server hour (real_costs.table_hour,
    HOUR_FRAME "server_table"), in price units, rounded to the instrument's digits. Commission: real_costs'
    own (0 with the recorded state, never guessed)."""
    bucket = RC.table_hour(COST_PROFILE, sym, at)
    price, note = RC.spread_price(COST_PROFILE, sym, bucket, SPREAD_STAT)
    digits = int(RC.spec(COST_PROFILE, sym)["digits"])
    commission, state = RC.commission_r(COST_PROFILE, sym)
    return {"spread": round(price, digits), "digits": digits, "table_bucket": bucket, "note": note,
            "profile": COST_PROFILE, "stat": SPREAD_STAT, "hour_frame": RC.HOUR_FRAME,
            "commission": commission, "commission_state": state}


# ------------------------------------------------------------------------------------------------ answer JSON
class _DuplicateKey(ValueError):
    pass


def _strict_loads(text):
    """json.loads that refuses duplicate keys and NaN / Infinity (strict JSON)."""
    def pairs(items):
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise _DuplicateKey("duplicate key")
        return dict(items)

    def constant(name):
        raise ValueError(f"non-finite number {name}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def _top_level_objects(text):
    """Every top-level '{...}' span of `text`, braces matched outside JSON strings."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"' and depth > 0:
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                out.append(text[start:i + 1])
    return out


FENCE = re.compile(r"```[A-Za-z0-9_-]*[ \t]*\n(.*?)```", re.S)


def extract_answer(text):
    """(object, how) for the one JSON object in a model answer, or (None, why). `how`: 'whole' (the answer is the
    object), 'fenced' (inside a code fence) or 'embedded' (prose around it). Refuses an answer with no object, with more
    than one DIFFERENT object carrying "decision", or whose object has a duplicate key or a non-finite number. Shared by
    the harness (no object = a technical failure, retried once) and the evaluator (the schema check)."""
    if not isinstance(text, str) or not text.strip():
        return None, "empty_answer"
    s = text.strip()
    try:
        v = _strict_loads(s)
        return (v, "whole") if isinstance(v, dict) else (None, "not_an_object")
    except _DuplicateKey:
        return None, "duplicate_key"
    except ValueError:
        pass
    cands = [("fenced", m.group(1).strip()) for m in FENCE.finditer(s)]
    cands += [("embedded", span) for span in _top_level_objects(s)]
    found, dup = {}, False
    for how, c in cands:
        try:
            v = _strict_loads(c)
        except _DuplicateKey:
            dup = True
            continue
        except ValueError:
            continue
        if isinstance(v, dict) and "decision" in v:
            found.setdefault(json.dumps(v, sort_keys=True), (v, how))
    if len(found) == 1:
        return next(iter(found.values()))
    if len(found) > 1:
        return None, "several_objects"
    return None, "duplicate_key" if dup else "no_json_object"


# ------------------------------------------------------------------------------------------------ hashes / git
def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, check=False)


def require_clean(root, paths, what="file"):
    """Every path exists, is tracked by git, and has no staged or unstaged change -- batched (one ls-files, one
    status call), so a few hundred prompt files cost two subprocesses."""
    paths = sorted(set(paths))
    missing = [p for p in paths if not os.path.isfile(os.path.join(root, p))]
    if missing:
        raise Refused(f"refused: {len(missing)} {what}(s) missing, e.g. {missing[:3]}")
    r = git(root, "ls-files", "-z", "--", *paths)
    if r.returncode != 0:
        raise Refused(f"refused: git ls-files failed in {root}: {r.stderr.strip()}")
    tracked = {p for p in r.stdout.split("\0") if p}
    untracked = [p for p in paths if p not in tracked]
    if untracked:
        raise Refused(f"refused: {len(untracked)} {what}(s) not committed, e.g. {untracked[:3]} -- commit before this step")
    st = git(root, "status", "--porcelain", "-z", "--", *paths)
    if st.returncode != 0:
        raise Refused(f"refused: git status failed in {root}: {st.stderr.strip()}")
    dirty = [e[3:] for e in st.stdout.split("\0") if e.strip()]
    if dirty:
        raise Refused(f"refused: {len(dirty)} {what}(s) changed since the last commit, e.g. {dirty[:3]}")


def git_blob(root, path, rev="HEAD"):
    """The blob id of `path` at `rev` (git reads it; the caller never opens the file), or None."""
    r = git(root, "rev-parse", f"{rev}:{path}")
    return r.stdout.strip() if r.returncode == 0 else None


def git_head(root):
    r = git(root, "rev-parse", "HEAD")
    return r.stdout.strip() if r.returncode == 0 else None


def ever_committed(root, path):
    """True when `path` was committed on any branch at any time (deleted files included). A repository without any
    commit has committed nothing."""
    if git(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0 and not git(root, "branch", "-a").stdout.strip():
        return False
    r = git(root, "log", "--all", "--format=%H", "--", path)
    if r.returncode != 0:
        raise Refused(f"refused: cannot read the git history of {path}: {r.stderr.strip()}")
    return bool(r.stdout.strip())


def utc_now():
    return datetime.datetime.now(UTC)


# ------------------------------------------------------------------------------------------------ the decision log
#: An append-only copy of every decisions.jsonl record OUTSIDE the repository (IC_SHADOW_DIR overrides it), keyed by the
#: manifest: deleting or truncating the uncommitted log on this machine cannot go unnoticed (implementation note §4 item 29).
SHADOW_DIR = os.path.join(os.path.expanduser("~"), ".local", "state", "trading-decision-system", "claude-ict")


def shadow_dir(override=None):
    return override or os.environ.get("IC_SHADOW_DIR") or SHADOW_DIR


def shadow_path(manifest_sha, override=None):
    return os.path.join(shadow_dir(override), f"decisions-{manifest_sha[:16]}.jsonl")


def raw_lines(path):
    """The non-empty lines of a file as bytes (newline stripped); [] when the file does not exist."""
    if not os.path.exists(path):
        return []
    with open(path, "rb") as fh:
        return [ln.rstrip(b"\n") for ln in fh if ln.strip()]


def shadows_with_records(override=None, exclude_sha=None):
    """Shadow logs of this experiment that hold at least one record, except the one of manifest `exclude_sha`."""
    d = shadow_dir(override)
    if not os.path.isdir(d):
        return []
    skip = f"decisions-{exclude_sha[:16]}.jsonl" if exclude_sha else None
    return [os.path.join(d, f) for f in sorted(os.listdir(d))
            if f.startswith("decisions-") and f.endswith(".jsonl") and f != skip and raw_lines(os.path.join(d, f))]


def compare_shadow(repo_lines, shadow_lines, where):
    """'equal', or 'repo_ahead' (the shadow missed the last lines: a crash between the two writes). Refuses when the
    repository log lost records the shadow holds, or when the two differ."""
    for i in range(min(len(repo_lines), len(shadow_lines))):
        if repo_lines[i] != shadow_lines[i]:
            raise Refused(f"refused: decisions.jsonl and its shadow {where} differ at record {i + 1}")
    if len(shadow_lines) > len(repo_lines):
        raise Refused(f"refused: decisions.jsonl lost {len(shadow_lines) - len(repo_lines)} record(s) that its shadow "
                      f"{where} holds -- restore them from the shadow; a removed decision is never asked again")
    return "equal" if len(repo_lines) == len(shadow_lines) else "repo_ahead"


def require_append_only(root, rel, current_bytes):
    """Every committed version of `rel` (any branch, any time) is a byte prefix of `current_bytes`: no committed record
    was ever changed or removed. Returns the number of commits checked."""
    if git(root, "rev-parse", "--verify", "-q", "HEAD").returncode != 0 and not git(root, "branch", "-a").stdout.strip():
        return 0
    r = git(root, "log", "--all", "--format=%H", "--", rel)
    if r.returncode != 0:
        raise Refused(f"refused: cannot read the git history of {rel}: {r.stderr.strip()}")
    shas = [x for x in r.stdout.split() if x]
    for sha in shas:
        p = subprocess.run(["git", "-C", root, "show", f"{sha}:{rel}"], capture_output=True, check=False)
        if p.returncode != 0:
            raise Refused(f"refused: commit {sha[:12]} touched {rel} but does not hold it (deleted?) -- the decision log "
                          f"may only grow")
        if not current_bytes.startswith(p.stdout):
            raise Refused(f"refused: the version of {rel} committed in {sha[:12]} is not a prefix of the current file -- "
                          f"committed records were changed or removed")
    return len(shas)


def kb_glob_matches(root=ROOT):
    """(ok, found): the knowledge/ict/*.md files on disk are exactly the ones KB_FILES embeds (a new ICT file must be
    a decision, not something the prompt silently gains or misses)."""
    d = os.path.join(root, "knowledge", "ict")
    found = sorted(f"knowledge/ict/{f}" for f in os.listdir(d) if f.endswith(".md"))
    return found == sorted(p for p in KB_FILES if p.startswith("knowledge/ict/")), found
