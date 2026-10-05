#!/usr/bin/env python3
"""WY-F1, the Wyckoff forward stage. It collects one cell of the sealed re-test, W-C-long-15m: the Phase-C Spring /
Shakeout long (docs/plans/2026-10-04-wyckoff-retest-preregistration.md §3.2). That cell read INCONCLUSIVE, +0.25R, n 63,
p 0.18 (docs/audits/2026-10-04-wyckoff-retest.md:20). Here it is collected on FTMO 15m bars of 10 symbols that close
AFTER the WY-F1 seal, logged as each signal bar closes, and read at two pre-registered looks.
Pre-registration: docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md ("WY-F1 §n" below).

What it measures (WY-F1 §1, §5): that cell on the Wyckoff engine AS THE SEALED RE-TEST'S R0 / R1 READ IT -- the files
`r0_drift` pins (edge_wyckoff, wyckoff_rules, backtest-methods, ...), run from the sealed extract. A later change to that
engine (for example to scripts/wyckoff_rules.py's semantics) never enters WY-F1 and does not apply to it: WY-F1's verdict
is a statement about the old detector only. A forward test of a changed engine is a SEPARATE registration, never a
re-seal of WY-F1.

    python3 scripts/research/wyckoff_forward.py spawn                                   # scripts/forward_cycle.py runs it
    python3 scripts/research/wyckoff_forward.py cycle [--only accumulate|scan|resolve]   # what `spawn` starts, detached
    python3 scripts/research/wyckoff_forward.py status [--json]                         # counts only, never an R
    python3 scripts/research/wyckoff_forward.py anchor                                  # chain heads -> anchors.jsonl
    python3 scripts/research/wyckoff_forward.py read --look 1 --out docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look1.json
    python3 scripts/research/wyckoff_forward.py read --look 2 --out docs/experiments/wyckoff-forward-wc15/wyckoff-forward-look2.json
    python3 scripts/research/wyckoff_forward.py fingerprint --out docs/experiments/wyckoff-forward-wc15/fingerprint.json

`read --look 2` runs only after look 1's record is committed and did not pass (a look-1 PASS ends the study).

How it stays point in time and tamper-evident without freezing the repository:
- Pinned code (WY-F1 §5). `cycle` and `read` never run the working tree. They run this file from a read-only extract of
  the commit that ADDS the sealed pre-registration (`git archive` into data/live/forward/wyckoff-wc15/code/<sha>/), in a
  fresh process (-E -s -B). Every other file of the repository may change. The extract is checked against the
  fingerprint: the files the forward steps execute, load and open, traced on a synthetic canary before sealing. Every
  record carries it. `fingerprint` also builds that extract from HEAD and runs the canary in it alone (extract_check),
  so a file the extract would lack fails before sealing. A run that touches the live tree outside its extract (other
  than the bar inputs and its own output directories) writes nothing.
- Bars (§4). One append-only, hash-chained 15m store per symbol. It is fed by the bridge's 15m file and the FTMO history
  export. Closed bars only. Times are snapped to the 15-minute grid (the v1.02 bridge stamps them +-1 s). A source appends
  only when it holds the store's last bars and is ALIGNED with the store (`plan_append`): most of the store's last day
  that it holds carries the same prices. A bar it shows at another price is a REVISION: the store keeps the bar as first
  stored (decisions and resolves stay point in time), the new bars are appended, and a chained revision record (old and
  new prices) goes to the log; every look reports them. A gap, a hole or a shifted clock (most bars differ) appends
  nothing and says why. A missing or unusable live file is STALLED, never an empty market: nothing is appended from it
  and the symbol is listed as stalled (CLAUDE.md §20: MISSING is not EMPTY). A store that does not advance while its live
  file exists, or a stale live file, is NOT ADVANCING (`status`, the cycle summary), with the reason and the store's last
  bar. A history export bridges a hole or a stalled feed; the events it uncovers are logged late and disclosed.
- Torn writes (§4). A chain line ends with a newline. A worker killed during `commit` can leave an UNTERMINATED last
  line, which was never part of the chain: the read and `anchor` refuse it, nothing is appended after it, and the next
  cycle drops it -- only it, never a terminated line, never under a live writer's lock -- after logging the bytes in
  repairs.jsonl. `status` names it; the read reports every drop. `anchor` never appends after an unterminated line,
  and a committed anchors.jsonl line that is not an anchor record refuses the read.
- Events (§2, §4). edge_wyckoff.window_fire, unmodified, on each new window, with edge_wyckoff.detect_series'
  de-duplication on (side, SC, AR), keyed by bar time. An event is logged once its signal bar has closed after the seal,
  with its decision fields, the hash of its 300-bar window and the store's chain hash at the signal bar.
- Resolve (§6): the event's own walk, once its exit is known. It also LOGS, never tests: MFE and MAE in R, bars to MFE,
  the planned R:R, the entry-hour spread and the ICT HTF gate flag at the signal (backtest-methods.htf_bias_gate, as
  the ablation's A3 arm applies it), all from bars the resolve already uses. They never reach `status` or a cycle
  summary. No command prints an outcome before a look.
- Read (§7, §8): two looks, at LOOK_MONTHS after the seal. Every look needs a FTMO history export of ALL 10 symbols
  taken after its cutoff + 96 bars, absorbed by a cycle (`export_problems`): a symbol complete through the cutoff is read
  (events the export uncovered are late-logged and disclosed); otherwise the look waits, and from GRACE_MONTHS after the
  cutoff, if at least DROP_MIN_COMPLETE symbols are complete, the rest are dropped whole. Lan-DeMets O'Brien-Fleming-
  type alpha spending, one-sided ALPHA in total, the boundaries from the looks' ACTUAL event counts (`look1_boundary`,
  `look2_boundary`). PASS iff net excess > 0 and the look's boundary is crossed; NOT PASSED only at look 2. A look 1
  that does not cross writes a BLINDED record (`blind`: no estimate, no resolve count, only the sha256 of its statistic)
  and look 2 recomputes and verifies it. Each look runs in a FRESH extract, checks the extract's fingerprint against the
  seal commit's, and the anchors against git history. It replays every window and checks the replay against the log. It
  runs the truncation probe and checks the bars against the export both ways, replaying the detector on the export
  (`export_replay`). Only then, after a chained look-attempt record in the log (a look runs ONCE, even if its file is
  lost), does it compute an outcome: the export's walks, then the sealed re-test's §5 (edge_wyckoff.score / summarise).
- Never due (§7): if look 2 is still not due NEVER_DUE_MONTHS after the seal, WY-F1 closes with no verdict. That close
  is PROCEDURAL: the coordinator records it (`status` shows the date); the code does not refuse a later look.
- Interpreter (§5): the fingerprint pins the Python it was made with, by a stable versioned path (python3.14 outside
  Homebrew's Cellar, no patch release in it); every worker runs under it. A patch upgrade keeps collecting; another
  minor version refuses every cycle, recorded as a failure. The read's canary refuses any numeric change.
- Numbers (§5): Python's math module takes erfc, exp, log, lgamma, sin and asin from the OS library, which a macOS update
  may move by an ulp; pinning Python does not pin it. So rows, counts and labels -- the detector, the walk, the placebo
  and the cost use no OS math function -- are hashed exactly, and a derived float (a p, a bound, a boundary, rho) enters
  a hash or a comparison rounded to SIG_DIGITS significant digits (`sig10`); one within TIE_REL of a rounding midpoint
  verifies under either rounding (`tie_variants`). Look 1's boundary is re-checked with math.isclose.
- Time zone (§5): server days, slots and cost hours use America/New_York's DST instants from the OS time-zone database.
  The fingerprint records the instants 2025-2030 as computed at the seal (`tz_pin`); every cycle and look refuses when
  this system computes others.
- Off the live path (§12): `spawn` starts `cycle` in its own session and returns at once, so research never delays the
  next cycle's demo ticks (CLAUDE.md §40). The previous cycle's failure is reported in the cycle log.

PAPER ONLY: it places no order, reads no account and touches no live configuration."""
import argparse
import base64
import bisect
import calendar
import collections
import contextlib
import datetime
import gzip
import hashlib
import importlib.util
import inspect
import io
import itertools
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

try:
    import fcntl                # the chain files' writer lock (`_flock`); POSIX only
except ImportError:             # Windows: no writer lock. WY-F1 runs on the sealed Mac (WY-F1 §5).
    fcntl = None

#: The CODE root: the working tree, or a sealed extract (data/live/forward/wyckoff-wc15/code/<sha>/). Data paths are
#: always resolved against an explicit data root (the live repository), never against this one.
CODE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.join(CODE_ROOT, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(CODE_ROOT, "scripts"))      # broker_symbols, history_store: this code root's
UTC = datetime.timezone.utc

# ------------------------------------------------------------------------------------------------ the registered design
STUDY = "WY-F1"
PREREG_DRAFT = "docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration-DRAFT.md"
PREREG = "docs/plans/2026-10-04-wyckoff-forward-wc15-preregistration.md"     # the SEALED file; its adding commit = the seal
SCRIPT = "scripts/research/wyckoff_forward.py"
EW_PATH = "scripts/research/edge_wyckoff.py"
R0 = "docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json"                # the sealed re-test's dense table (§4)
REC_DIR = "docs/experiments/wyckoff-forward-wc15"
FINGERPRINT = REC_DIR + "/fingerprint.json"
ANCHORS = REC_DIR + "/anchors.jsonl"
#: One record per look (WY-F1 §7). Look 1's is BLINDED unless it crosses (then it is the verdict); look 2's is final.
LOOK_OUT = {1: REC_DIR + "/wyckoff-forward-look1.json", 2: REC_DIR + "/wyckoff-forward-look2.json"}
RUNTIME = "data/live/forward/wyckoff-wc15"            # per machine, gitignored (.gitignore: data/live/forward/)
#: Under RUNTIME: one hash-chained record per dropped UNTERMINATED last line (WY-F1 §4, `drop_torn`).
REPAIRS = "repairs.jsonl"
REPAIR_KEEP = 1 << 16       # a repair record keeps up to this many of the dropped bytes (base64); their sha256 covers all
LIVE_DIR = "data/live/mt5-bridge"
HIST_DIR = "data/history/ftmo"

CELL, TF, MINUTES, LEG, SIDE = "W-C-long-15m", "15m", 15, "W-C", "long"
#: The sealed re-test's tradeable symbols (edge_wyckoff.TRADEABLE) that have a 15m dense start in its R0 record.
#: FRA40 has none (R0 dense table), so R1 never read it at 15m and neither does WY-F1.
RT_SYMBOLS = ("XAUUSD", "XAGUSD", "US500", "US30", "USTEC", "DE40", "AUS200")
#: Added 2026-10-04 (lead decision; WY-X1 draft §12.2 (a)): the three cheap research-only indices of the re-test's
#: replication set (edge_wyckoff.REPLICATION) with an R0 15m dense start. Only their bars AFTER the seal are scored, so
#: the re-test's R2 window (before 2024-03-01) stays unread. The platinum-group metals stay out (spread about 0.9R).
ADDED_SYMBOLS = ("US2000", "UK100", "JP225")
SYMBOLS = RT_SYMBOLS + ADDED_SYMBOLS
#: The read rule (WY-F1 §7), fixed before any forward bar: two looks, LOOK_MONTHS after the seal (look 2 final);
#: Lan-DeMets O'Brien-Fleming-type alpha spending, ALPHA one-sided in total. PASS iff net excess > 0 and the look's
#: boundary is crossed; NOT PASSED only at look 2.
LOOK_MONTHS = (12, 36)
ALPHA = 0.10
#: Look 1's information fraction is t1 = n1 / (n1 + N_REST_PLAN): its read events over those plus the events the
#: planning rate PLAN_RATE (a year, WY-F1 §9) expects between the looks. Outcome-blind, fixed now. Look 2 is the final
#: look (t = 1) and spends exactly what look 1 left, with the looks' correlation from their actual counts.
PLAN_RATE = 14
N_REST_PLAN = PLAN_RATE * (LOOK_MONTHS[1] - LOOK_MONTHS[0]) // 12
#: §7: look 2 still not due this long after the seal -> WY-F1 closes with no verdict (the coordinator records it).
NEVER_DUE_MONTHS = 48
#: The resolve's LOG-ONLY fields (WY-F1 §6): never tested in WY-F1, never in `status` or a cycle summary.
LOG_ONLY_KEYS = ("planned_rr", "spread_r_entry", "mfe_r", "mae_r", "bars_to_mfe", "htf_gate", "htf_gate_error")
#: The ICT HTF gate as the ablation's A3 arm applies it (scripts/research/wyckoff_ablation.py ARMS["A3"]: the engine's
#: scan with htf=True): backtest-methods.htf_bias_gate on the next rung (1H for 15m), with the bias methods its scan
#: resolves for the seven re-test symbols (backtest-methods.resolve_methods: automation.market_of -> "cfd", and
#: htf_context.engaged_methods_for_market("cfd") -> ("ict",) on 2026-10-04). Pinned here, so the forward path never
#: reads the live automation config; a test checks the pin against that config while WY-F1 is unsealed. The three added
#: symbols have no live market (automation.market_of gives None); they get the same pinned methods as the other seven.
HTF_METHODS = ("ict",)
WARMUP_DAYS = 90            # store bars before the seal: >= 60 dense-rule days + one 300-bar window + the dedup context
SNAP_TOL_S = 60             # a source time more than this off the 15-minute grid refuses the source
OVERLAP_BARS = 4            # a source appends only if it holds the times of the store's last bars (up to this many)
#: §4 alignment (decision 2026-10-04, lead): of the store's last ALIGN_BARS bars (one day) that a source holds, at least
#: ALIGN_MIN and at least half must carry the same prices; the others are REVISIONS (logged, the store keeps its bars).
#: A shifted clock or another series disagrees on nearly every bar and appends nothing.
ALIGN_BARS, ALIGN_MIN = 96, 4
PRICE_DP = 8                # price comparison precision (sources print 2-5 decimals)
#: §4 NOT ADVANCING (decision 2026-10-04, lead): a live file whose newest closed bar is older than this before the cycle
#: (or `status`) is stale -- the EA may have stopped. A weekend is about 49 hours; a long holiday can show here.
STALE_LIVE_HOURS = 72
HIST_COVER_MIN, HIST_AGREE_MIN = 0.95, 0.99   # §8: the read's check of the forward bars against a later history export
#: §8: the most of the export's bars inside the checked window that the store may lack (MISSING is not EMPTY, CLAUDE.md
#: §20). Inside a sampled event's span (its window to the end of its longest walk) a difference is tolerated only when
#: it changes no decision field and no walk (`export_replay`, `export_walks`); every difference is reported.
HIST_MISSING_MAX = 0.01
#: §7 fallback, per look (decisions 2026-10-04: option A; lead: the minimum below): once any symbol is complete through
#: GRACE_MONTHS after a look's cutoff and at least DROP_MIN_COMPLETE of the 10 are complete through the cutoff, a symbol
#: still not complete through it -- after the look's export of all 10 symbols (`export_problems`) -- is dropped WHOLE
#: from that look (every event of it, before any outcome is computed). Fewer complete: the look waits. None = no
#: fallback (the look stays not due; §7 closes the study NEVER_DUE_MONTHS after the seal, by procedure).
GRACE_MONTHS = 3
DROP_MIN_COMPLETE = 5
#: §5 numbers (decision 2026-10-04, lead): a derived float enters a hash, a commitment or a comparison rounded to
#: SIG_DIGITS significant digits (`sig10`); a float within TIE_REL (relative) of a rounding midpoint verifies under either
#: rounding (`tie_variants`, at most TIE_CAP such floats in one body). Look 2 re-checks look 1's boundary within
#: BOUNDARY_REL_TOL (math.isclose).
SIG_DIGITS = 10
TIE_REL = 1e-12
TIE_CAP = 12
BOUNDARY_REL_TOL = 1e-9
#: §5 time zone (decision 2026-10-04, lead): the DST instants the fingerprint pins and every cycle and look recomputes.
TZ_PIN_ZONE = "America/New_York"
TZ_PIN_YEARS = (2025, 2030)
#: The cycle worker's cap. `spawn` runs it detached from scripts/forward_cycle.py, so it no longer delays a tick; the cap
#: stops a hung worker from holding the lock.
WORKER_TIMEOUT_S = 120
LOCK_STALE_S = 900
SPAWN_LOG_MAX = 1 << 20     # spawn.log is rotated to spawn.log.1 above this size
#: What the sealed extract holds (WY-F1 §5): the code, the configs and cost tables it reads, the sealed history of the
#: symbols (the warm-up and real_costs' price_ref), the R0 record, the fingerprint and the sealed pre-registration --
#: and the two MT5 adapter files docs/architecture/providers.json names, because providers._validate (scripts/
#: providers.py:63) refuses the whole registry when a named adapter does not EXIST (only stat()ed, never opened, so the
#: trace cannot see it). `extract_check` proves before sealing that nothing else is missing.
SNAPSHOT_ROOTS = ("scripts", "docs/architecture", "data/history/costs", HIST_DIR, R0, FINGERPRINT, PREREG,
                  "integrations/mt5/ExportOHLCV.mq5", "integrations/mt5/ExportHistory.mq5")
#: What a run may open under the DATA root outside its code root (WY-F1 §5): the live bridge files, a later history
#: export, its own runtime directory (not another extract) and its record directory, and the sealed pre-registration.
DATA_INPUTS = (LIVE_DIR + "/", HIST_DIR + "/", RUNTIME + "/", REC_DIR + "/")
LATE_LOG_S = 86400          # §8: an event logged more than a day after its signal close is reported as late-logged
#: The fields an event is decided on. The replay, the truncation probe and the log must agree on every one.
DECISION_KEYS = ("id", "symbol", "tf", "cell", "leg", "side", "type", "sc_time", "ar_time", "s_time", "r_time", "t_time",
                 "signal_time", "signal_close", "store_index", "tr_lo", "tr_hi", "ceiling", "spring_low", "stop", "target",
                 "phase_b_tests", "sloped", "path", "prev_dense", "atr", "window_first", "window_sha256",
                 "chain_at_signal")
#: The decision fields without the store's provenance (its line index, the window's first bar time and hash, the chain
#: hash): what the detector decided. The export replay must give these for every event (`export_replay`).
DECISION_VALUE_KEYS = tuple(k for k in DECISION_KEYS
                            if k not in ("store_index", "window_first", "window_sha256", "chain_at_signal"))
GENESIS = hashlib.sha256(STUDY.encode()).hexdigest()


# ------------------------------------------------------------------------------------------------ small helpers
def _utc(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(UTC)


def _iso(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _now():
    return _iso(datetime.datetime.now(UTC))


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def add_months(d, n):
    """`d` plus n calendar months, the day clipped to the month's last day (2028-02-29 + 12 -> 2029-02-28).
    [WY-F1 §7]"""
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def _rt(data_root, *parts):
    return os.path.join(data_root, RUNTIME, *parts)


# ------------------------------------------------------------------------------------------------ numbers (WY-F1 §5)
def sig10(x):
    """`x` rounded to SIG_DIGITS (10) significant digits: Python's own float formatting ('%.9e', correctly rounded,
    round-half-even on the exact binary value; CPython's dtoa, never the OS library), parsed back. The same double gives
    the same result on every platform. None, bools, ints and non-finite values pass through. It is how a DERIVED float
    -- one that went through an OS math function -- enters a hash, a commitment or a comparison. [WY-F1 §5]"""
    if isinstance(x, float) and math.isfinite(x):
        return float(f"{x:.{SIG_DIGITS - 1}e}")
    return x


def _json(obj):
    """`obj` as plain JSON values (tuples -> lists, other types -> str), as a record holds it."""
    return json.loads(json.dumps(obj, default=str))


def rounded(obj):
    """`obj` (JSON values) with every float rounded by `sig10`. [WY-F1 §5]"""
    if isinstance(obj, dict):
        return {k: rounded(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rounded(v) for v in obj]
    return sig10(obj)


def _tie_pair(x):
    """The two 10-digit roundings of a float that lies within TIE_REL of the midpoint between them (a last-ulp
    difference in the OS math library could have given either), else None. About 1 float in 130 is such a float.
    [WY-F1 §5]"""
    if not isinstance(x, float) or not math.isfinite(x) or x == 0.0:
        return None
    a, b = sig10(x * (1.0 - TIE_REL)), sig10(x * (1.0 + TIE_REL))
    return (a, b) if a != b else None


def tie_variants(obj, cap=TIE_CAP):
    """Every `rounded(obj)` that a last-ulp difference in its floats could have produced: one, unless some float lies
    within TIE_REL of a rounding midpoint (`_tie_pair`); then each such float takes either rounding (2^k variants).
    A drift of up to TIE_REL (about 4,500 ulps) can never change a rounding the variants do not cover. Refuses more than
    `cap` such floats (expected: about 0.25 in a look's summary, about 1 in the canary's derived part). [WY-F1 §5]"""
    obj = _json(obj)
    ties = []

    def walk(x, path):
        if isinstance(x, dict):
            for k in sorted(x):
                walk(x[k], path + (k,))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path + (i,))
        else:
            p = _tie_pair(x)
            if p:
                ties.append((path, p))
    walk(obj, ())
    if len(ties) > cap:
        raise SystemExit(f"refusing: {len(ties)} derived floats lie within {TIE_REL} of a 10-digit rounding midpoint "
                         f"(at most {cap}) [WY-F1 §5]")
    base = rounded(obj)
    out = []
    for pick in itertools.product((0, 1), repeat=len(ties)):
        v = json.loads(json.dumps(base))
        for (path, pair), j in zip(ties, pick):
            node = v
            for key in path[:-1]:
                node = node[key]
            node[path[-1]] = pair[j]
        out.append(v)
    return out


def split_sha256(exact, derived):
    """sha256 of a body whose `exact` part (rows, counts, labels, bar records) is hashed as it is and whose `derived`
    part (summaries, boundaries) is rounded by `sig10`: the digest a fingerprint or a look commits to. [WY-F1 §5]"""
    return hashlib.sha256(_canon({"exact": _json(exact), "derived": rounded(_json(derived))}).encode()).hexdigest()


def split_digests(exact, derived):
    """Every digest `split_sha256(exact, derived)` could have had under a last-ulp difference in a derived float
    (`tie_variants`): a committed digest verifies iff it is one of them. The exact part never varies. [WY-F1 §5]"""
    ex = _json(exact)
    return {hashlib.sha256(_canon({"exact": ex, "derived": v}).encode()).hexdigest() for v in tie_variants(derived)}


_EW = {}


def ew():
    """scripts/research/edge_wyckoff.py of THIS code root, loaded once and unmodified, with its engine
    (backtest-methods) loaded too, so a trace's import phase holds every import. [WY-F1 §2, §5]"""
    if "m" not in _EW:
        sys.path.insert(0, os.path.join(CODE_ROOT, "scripts"))
        spec = importlib.util.spec_from_file_location("edge_wyckoff_wyf1", os.path.join(CODE_ROOT, EW_PATH))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.engine()
        _EW["m"] = m
    return _EW["m"]


def det_ctx():
    """(cfg, P, sob): DET-PO exactly as the sealed re-test registered it -- edge_wyckoff.BASE_CFG, det_params(BASE_CFG)
    and the engine's sob for 15m. Nothing is restated here. [WY-F1 §2]"""
    E = ew()
    cfg = dict(E.BASE_CFG)
    return cfg, E.det_params(cfg), E.engine().P[TF]["sob"]


def horizon():
    """The time cap H in bars: the engine's P['15m']['H'] times BASE_CFG's cap_mult (96). [WY-F1 §6]"""
    E = ew()
    return E.engine().P[TF]["H"] * E.BASE_CFG["cap_mult"]


_DENSE = {}


def r0_dense():
    """The sealed re-test's R0 dense table, read from this code root (the sealed extract holds the committed file).
    [WY-F1 §2]"""
    if "d" not in _DENSE:
        _DENSE["d"] = _read_json(os.path.join(CODE_ROOT, R0))["dense"]
    return _DENSE["d"]


# ------------------------------------------------------------------------------------------------ hash chains
def _link(prev, rec):
    return hashlib.sha256((prev + "|" + _canon(rec)).encode()).hexdigest()


def link_all(prev, recs):
    """The chain hashes the records would get if appended after `prev`. [WY-F1 §4]"""
    out = []
    for r in recs:
        prev = _link(prev, r)
        out.append(prev)
    return out


def _torn(path):
    """(offset, bytes) of the file's UNTERMINATED last line -- every byte after its last newline -- or None when the
    file is missing, empty or ends with a newline. A chain line ends with a newline (`append_chain` writes whole lines),
    so these bytes are a write that never completed (a worker killed during `commit`): never part of the chain.
    [WY-F1 §4]"""
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        end = fh.seek(0, os.SEEK_END)
        if end == 0:
            return None
        fh.seek(end - 1)
        if fh.read(1) == b"\n":
            return None
        pos, buf = end, b""
        while pos > 0:
            step = min(65536, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
            cut = buf.rfind(b"\n")
            if cut >= 0:
                return pos + cut + 1, buf[cut + 1:]
        return 0, buf


def read_chain(path, torn=None):
    """(records, chain hashes) of an append-only JSONL file whose every line carries `ch` = sha256(previous ch | the
    record). An edited, removed, inserted or reordered line refuses, and so does any TERMINATED line that is not JSON:
    a terminated line is never dropped. An UNTERMINATED last line (`_torn`) was never part of the chain. It refuses
    here too, unless `torn` (a dict) is passed: then its (offset, bytes) go to torn[path] and the records before it are
    returned -- the cycle plans its drop (`cycle_core`, `drop_torn`). [WY-F1 §4]"""
    recs, heads, head = [], [], GENESIS
    if not os.path.exists(path):
        return recs, heads
    tail, off = None, 0
    with open(path, "rb") as fh:
        for n, line in enumerate(fh, 1):
            if not line.endswith(b"\n"):                 # only the last line can lack its newline
                tail = (off, line)
                break
            off += len(line)
            try:
                d = json.loads(line)
            except ValueError:
                d = None
            if not isinstance(d, dict):
                raise SystemExit(f"refusing: {path} line {n} is not a JSON record, and it is terminated, so it is never "
                                 f"dropped; the chain cannot be verified [WY-F1 §4]")
            ch = d.pop("ch", None)
            if ch != _link(head, d):
                raise SystemExit(f"refusing: {path} line {n} breaks the hash chain (a line was edited, removed, "
                                 f"inserted or reordered) [WY-F1 §4]")
            head = ch
            recs.append(d)
            heads.append(ch)
    if tail is not None:
        if torn is None:
            raise SystemExit(f"refusing: {path} ends with an unterminated line (a write that never completed, never "
                             f"part of the chain); the next `cycle` drops it and logs the drop in {RUNTIME}/{REPAIRS} "
                             f"[WY-F1 §4]")
        torn[path] = tail
    return recs, heads


def _flock(fh, block=False):
    """An exclusive advisory lock on an open chain file: True when held. It is released when the file is closed or its
    process dies, so a writer killed during `commit` holds nothing while a live one (a stale worker lock, a woken
    laptop) still does -- its line is never cut, nor appended to. No lock without fcntl (Windows). [WY-F1 §4]"""
    if fcntl is None:
        return True
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | (0 if block else fcntl.LOCK_NB))
    except BlockingIOError:
        return False
    return True


def _tail_head(path):
    """The last line's `ch` (GENESIS for a missing or empty file), read from the file's end. Refuses on an unterminated
    last line: nothing is appended after one (the torn bytes would join the new line into a terminated, broken one).
    [WY-F1 §4]"""
    if _torn(path) is not None:
        raise SystemExit(f"refusing: {path} ends with an unterminated line; nothing appended (the next `cycle` drops it) "
                         f"[WY-F1 §4]")
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return GENESIS
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        pos, buf = fh.tell(), b""
        while pos > 0 and buf.count(b"\n") < 2:
            step = min(65536, pos)
            pos -= step
            fh.seek(pos)
            buf = fh.read(step) + buf
    last = [x for x in buf.splitlines() if x.strip()][-1]
    return json.loads(last).get("ch")


def append_chain(path, recs, expect_head):
    """Append `recs` as whole lines, holding the file's lock from the check that it still ends at `expect_head` (no
    other writer since it was read, and no unterminated last line) to the fsync. [WY-F1 §4]"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines, head = [], expect_head
    for r in recs:
        head = _link(head, r)
        lines.append(_canon(dict(r, ch=head)) + "\n")
    with open(path, "ab") as fh:
        if not _flock(fh):
            raise SystemExit(f"refusing: another writer holds {path}; nothing appended [WY-F1 §4]")
        if _tail_head(path) != expect_head:
            raise SystemExit(f"refusing: {path} changed while this cycle ran; nothing appended")
        fh.write("".join(lines).encode())
        fh.flush()
        os.fsync(fh.fileno())
    return head


def _complete_record(data, head):
    """Do the dropped bytes hold a whole record on `head` (a write that lost only its newline)? Reported, not used."""
    try:
        d = json.loads(data)
        return isinstance(d, dict) and d.pop("ch", None) == _link(head, d)
    except ValueError:
        return False


def repair_plan(data_root, path, tail, kept, seal, fp_digest, now):
    """The planned drop of one chain file's UNTERMINATED last line (`read_chain` with `torn`) and its repairs.jsonl
    record: the file, the offset, the records and head that remain, the dropped bytes (base64, up to REPAIR_KEEP) and
    their sha256. Nothing is written here. [WY-F1 §4]"""
    off, data = tail
    n, head = kept
    rec = {"kind": "repair", "study": STUDY, "file": os.path.relpath(path, _rt(data_root)).replace(os.sep, "/"),
           "offset": off, "kept_records": n, "kept_head": head, "dropped_bytes": len(data),
           "dropped_sha256": hashlib.sha256(data).hexdigest(),
           "dropped_b64": base64.b64encode(data[:REPAIR_KEEP]).decode(), "dropped_b64_complete": len(data) <= REPAIR_KEEP,
           "complete_record": _complete_record(data, head), "seal": seal["sha"], "fingerprint": fp_digest,
           "python": platform.python_version(), "repaired_at": now}
    return {"path": path, "offset": off, "bytes": data, "record": rec}


def drop_torn(rep_path, rep_head, plans):
    """Drop each planned UNTERMINATED last line, and nothing else (WY-F1 §4). First every file is locked (`_flock`: a
    live writer refuses the whole step) and its bytes from the offset must be exactly the planned ones, with no newline
    -- a terminated line is never dropped, and a file that changed since the plan refuses. Then repairs.jsonl's own
    torn tail is cut (a repair record that never completed: the drop it described was not done and is planned again),
    every record is appended to repairs.jsonl and fsynced, and only then are the other files cut. Killed in between, the
    next cycle logs the same drop again. One cut can go unlogged: killed after repairs.jsonl's own tail is cut and
    before the records are appended, that cut has no record. Those bytes were an incomplete repair record, and the drops
    it described were not done: the next cycle plans and logs them. [WY-F1 §4]"""
    held = []
    try:
        for p in plans:
            fh = open(p["path"], "r+b")
            held.append(fh)
            if not _flock(fh):
                raise SystemExit(f"refusing: a writer still holds {p['path']}; its unterminated last line is not "
                                 f"dropped [WY-F1 §4]")
            fh.seek(p["offset"])
            rest = fh.read()
            if rest != p["bytes"] or b"\n" in rest:
                raise SystemExit(f"refusing: {p['path']} changed while this cycle ran; nothing dropped [WY-F1 §4]")

        def cut(fh, off):
            fh.truncate(off)
            fh.flush()
            os.fsync(fh.fileno())
        for fh, p in zip(held, plans):
            if p["path"] == rep_path:
                cut(fh, p["offset"])
                fh.close()                               # its lock goes before append_chain takes it
        append_chain(rep_path, [p["record"] for p in plans], rep_head)
        for fh, p in zip(held, plans):
            if p["path"] != rep_path:
                cut(fh, p["offset"])
    finally:
        for fh in held:
            fh.close()


def commit(writes):
    """Perform a cycle's planned writes: ("repair", repairs.jsonl, its head, plans), ("chain", path, records, expected
    head) or ("json", path, object). [WY-F1 §4]"""
    for w in writes:
        if w[0] == "repair":
            drop_torn(w[1], w[2], w[3])
        elif w[0] == "chain":
            append_chain(w[1], w[2], w[3])
        else:
            _write_json(w[1], w[2])


# ------------------------------------------------------------------------------------------------ bars (WY-F1 §4)
PRICE_KEYS = ("o", "h", "l", "c")


def snap(t, minutes=MINUTES, tol=SNAP_TOL_S):
    """The bar-open label on the `minutes` grid nearest to ISO `t`, or None when `t` is more than `tol` seconds off it.
    The live bridge v1.02 converts with a measured offset (10799 s), so its times read "...:00:01Z". [WY-F1 §4]"""
    s = _utc(t).timestamp()
    step = minutes * 60
    g = round(s / step) * step
    if abs(s - g) > tol:
        return None
    return _iso(datetime.datetime.fromtimestamp(g, UTC))


def norm(c):
    """A source candle as a store bar {t, o, h, l, c, v} with its time snapped; None when unreadable or off-grid.
    [WY-F1 §4]"""
    t = c.get("time")
    if not isinstance(t, str) or not t.endswith("Z"):
        return None
    try:
        ts = snap(t)
        o, h, lo, cl = (float(c[k]) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return None
    if ts is None or any(x != x or x in (float("inf"), float("-inf")) for x in (o, h, lo, cl)):
        return None
    v = c.get("volume")
    return {"t": ts, "o": o, "h": h, "l": lo, "c": cl, "v": v if isinstance(v, (int, float)) else None}


def clean(candles, label):
    """(bars sorted by time, None) or ([], why): a source with ANY unreadable or off-grid bar, or two bars on one
    label, is not used at all -- its time basis cannot be trusted. [WY-F1 §4]"""
    out, bad, dup = {}, 0, 0
    for c in candles:
        b = norm(c)
        if b is None:
            bad += 1
            continue
        if b["t"] in out:
            dup += 1
        out[b["t"]] = b
    if bad or dup:
        return [], f"{label}: {bad} bar(s) unreadable or off the 15-minute grid, {dup} duplicate label(s); not used"
    return [out[t] for t in sorted(out)], None


def same(a, b):
    return all(round(a[k], PRICE_DP) == round(b[k], PRICE_DP) for k in PRICE_KEYS)


def live_source(data_root, sym):
    """(closed bars, note) from the bridge's 15m file, in the broker's spelling (broker_symbols, e.g. DE40 ->
    GER40.cash). The file's FINAL bar is dropped: ExportOHLCV copies from shift 0, so it may still be forming.
    A missing, unreadable or unusable file, or one with no closed bar, gives (None, "...STALLED...") -- never an empty
    bar list: the feed is MISSING, not an empty market (CLAUDE.md §20). Nothing is appended from it and the store does
    not advance, so no look counts the symbol complete (`due`). [WY-F1 §4, §7]"""
    import broker_symbols as BS
    p = os.path.join(data_root, LIVE_DIR, f"ohlcv.{BS.to_broker(sym)}.{TF}.json")
    if not os.path.exists(p):
        return None, (f"{sym}: STALLED, no live 15m file ({os.path.relpath(p, data_root)}); attach ExportOHLCV to "
                      f"it")
    try:
        doc = _read_json(p)
    except ValueError:
        return None, f"{sym}: STALLED, live 15m file unreadable"
    bars, note = clean(doc.get("candles") or [], f"{sym} live")
    if note:
        return None, f"{sym}: STALLED, {note}"
    if len(bars) < 2:
        return None, f"{sym}: STALLED, the live 15m file holds no closed bar"
    return bars[:-1], None


def history_source(root, sym, since=None):
    """(closed bars, note) from the FTMO 15m history export under `root`/data/history/ftmo (history_store's file or split
    shape). A split series reads only the year parts from `since`'s year on. The final bar is dropped (an export taken
    while the market is open ends on a forming bar). [WY-F1 §4]"""
    import history_store as HS
    path, shape = HS.resolve(sym, TF, root=os.path.join(root, HIST_DIR))
    if shape is None:
        return [], f"{sym}: no 15m history under {os.path.join(root, HIST_DIR)}"
    if shape == "file":
        candles = HS.read_at(path, shape)["candles"]
    else:
        idx = _read_json(os.path.join(path, "index.json"))
        y0 = int(since[:4]) if since else None
        candles = []
        for y in sorted(idx.get("years") or (), key=int):
            if y0 is None or int(y) >= y0:
                with gzip.open(os.path.join(path, f"{y}.json.gz"), "rt", encoding="utf-8") as fh:
                    candles.extend(json.load(fh)["candles"])
    bars, note = clean(candles, f"{sym} history")
    return bars[:-1], note


def history_meta(root, sym, since=None):
    """The provenance of what `history_source(root, sym, since)` reads: the export's `_exported_at_utc` and the sha256 of
    every file it opens (relative to `root`). [WY-F1 §8]"""
    import history_store as HS
    path, shape = HS.resolve(sym, TF, root=os.path.join(root, HIST_DIR))
    if shape is None:
        return {"exported_at_utc": None, "files": {}}
    if shape == "file":
        files = [path]
        head = HS.read_at(path, shape)
    else:
        head = _read_json(os.path.join(path, "index.json"))
        y0 = int(since[:4]) if since else None
        files = [os.path.join(path, "index.json")] + [os.path.join(path, f"{y}.json.gz")
                                                      for y in sorted(head.get("years") or (), key=int)
                                                      if y0 is None or int(y) >= y0]
    return {"exported_at_utc": head.get("_exported_at_utc"),
            "files": {os.path.relpath(f, root).replace(os.sep, "/"): _sha256(f) for f in files}}


def plan_init(source, seal_instant, at, warmup_days=WARMUP_DAYS):
    """The first bars of an empty store: the SEALED history's closed bars from `warmup_days` before the seal on.
    [WY-F1 §4]"""
    lo = _iso(_utc(seal_instant) - datetime.timedelta(days=warmup_days))
    return [dict(b, src="history", at=at) for b in source if b["t"] >= lo]


def plan_append(store, source, src, at):
    """(bars to append, why-not or None, revisions) from one source: its closed bars after the store's last bar, but only
    when the source holds the store's last bar and the times of its last OVERLAP_BARS bars (those inside the source's
    span), and is ALIGNED: it agrees on every bar it holds of the store's last ALIGN_BARS, or, where some differ, on at
    least ALIGN_MIN of them and on at least as many as differ. A bar it holds at another price is a REVISION, returned
    as (store bar, source bar): the store keeps
    its bar as first stored (point in time), the new bars are appended, and the caller logs the revision -- so a bar the
    broker revised after it was stored never stops a store (the old rule appended nothing until the bar left the
    overlap, which no later source let happen). A source that is behind appends nothing silently. A hole, a gap, or a
    shifted clock or another series (the v1.02 bridge after a DST change: nearly every bar differs) appends nothing and
    says why. [WY-F1 §4]"""
    if not store or not source or source[-1]["t"] <= store[-1]["t"]:
        return [], None, []
    last = store[-1]["t"]
    by_t = {b["t"]: b for b in source}
    if last not in by_t:
        if source[0]["t"] > last:
            return [], f"hole: the store ends {last}, the {src} source starts {source[0]['t']} (re-export the history)", []
        return [], f"the {src} source lacks the store's last bar {last}", []
    gap = [b["t"] for b in store[-OVERLAP_BARS:] if b["t"] >= source[0]["t"] and b["t"] not in by_t]
    if gap:
        return [], f"the {src} source lacks the store's bar {gap[0]} (a gap or a shifted clock)", []
    held = [b for b in store[-ALIGN_BARS:] if b["t"] in by_t]
    bad = [b for b in held if not same(b, by_t[b["t"]])]
    if bad and (len(held) - len(bad) < ALIGN_MIN or len(bad) > len(held) - len(bad)):
        return [], (f"the {src} source disagrees with the store on {len(bad)} of the {len(held)} bars it holds of the "
                    f"store's last day, first {bad[0]['t']} (a shifted clock or another series; revisions need at "
                    f"least {ALIGN_MIN} agreeing bars and at most as many differing ones)"), []
    return [dict(b, src=src, at=at) for b in source if b["t"] > last], None, [(b, by_t[b["t"]]) for b in bad]


def _stale(live, now):
    """Why the live file is stale -- its newest closed bar closed more than STALE_LIVE_HOURS before `now` -- or None.
    [WY-F1 §4]"""
    try:
        t_now = _utc(now)
    except (AttributeError, TypeError, ValueError):     # not a time (a test's stand-in stamp): nothing to judge
        return None
    if not live:
        return None
    age = (t_now - _utc(live[-1]["t"]) - datetime.timedelta(minutes=MINUTES)).total_seconds() / 3600.0
    if age <= STALE_LIVE_HOURS:
        return None
    return (f"the live 15m file is stale: its newest closed bar {live[-1]['t']} closed {age:.0f} h before {now} (the EA "
            f"may have stopped; a weekend or holiday can show here)")


def history_ahead(root, sym, last_t):
    """Can the history export under `root` hold a bar after `last_t`? A split series says so in its small index.json
    (`last`), read before any year part is parsed; a one-file series is read anyway (False only when it is missing).
    [WY-F1 §4]"""
    import history_store as HS
    path, shape = HS.resolve(sym, TF, root=os.path.join(root, HIST_DIR))
    if shape is None:
        return False
    if shape == "file":
        return True
    try:
        last = _read_json(os.path.join(path, "index.json")).get("last")
    except (OSError, ValueError):
        return True
    return not isinstance(last, str) or last > last_t


def accumulate_symbol(sym, store, data_root, init_root, seal, at, now=None):
    """What one cycle adds to a store: {"add": bars, "notes": [...], "stalled": bool, "revisions": [(store bar, source
    bar, src)], "not_advancing": why or None, "last": the store's last bar after the cycle}. An empty store starts from
    the sealed history (`init_root`, the extract); then the live file appends; and the history export under `data_root`
    is read whenever the live file gave no new bar (a hole after downtime, a shifted clock, a stale or stopped feed, a
    missing file): it bridges the bars the live file does not bring, and the live file is then tried again.
    - `stalled`: the live file is missing or unusable (`live_source`); a history export may still bridge bars.
    - `not_advancing` (the live file exists): the store took no bar from any source (the bars an empty store starts
      from do not count) although the live file holds bars after its last one (plan_append's reason), or the live file
      is stale (`_stale`, against `now`, default `at`) -- each with the store's last bar. [WY-F1 §4]"""
    now = now or at
    notes, add, cur, revs = [], [], list(store), []
    if not cur:
        src, note = history_source(init_root, sym, since=_iso(_utc(seal["instant"])
                                                               - datetime.timedelta(days=WARMUP_DAYS)))
        cur = plan_init(src, seal["instant"], at)
        add += cur
        if not cur:
            return {"add": [], "notes": [note or f"{sym}: no sealed history to start the store from"], "stalled": True,
                    "revisions": [], "not_advancing": None, "last": None}
    n_init = len(add)                       # the bars the store starts from are not an advance
    live, lnote = live_source(data_root, sym)
    new, why, rv = plan_append(cur, live, "live", at)
    revs += [(a, b, "live") for a, b in rv]
    if new:
        cur, add = cur + new, add + new
        return {"add": add, "notes": notes, "stalled": False, "revisions": revs, "last": cur[-1]["t"],
                "not_advancing": None}
    if history_ahead(data_root, sym, cur[-1]["t"]):
        hist, hnote = history_source(data_root, sym, since=cur[max(0, len(cur) - ALIGN_BARS)]["t"])
    else:
        hist, hnote = [], None
    hnew, hwhy, hrv = plan_append(cur, hist, "history", at)
    revs += [(a, b, "history") for a, b in hrv]
    cur, add = cur + hnew, add + hnew
    new2, why2, rv2 = plan_append(cur, live, "live", at)
    revs += [(a, b, "live") for a, b in rv2]
    cur, add = cur + new2, add + new2
    for msg in (lnote, why if not hnew else None, hnote if not hnew else None, hwhy, why2 if hnew else None):
        if msg:
            notes.append(msg if msg.startswith(sym) else f"{sym}: {msg}")
    stuck = None
    if live is not None and len(add) == n_init:
        stuck = why if live[-1]["t"] > cur[-1]["t"] else _stale(live, now)
    return {"add": add, "notes": notes, "stalled": live is None, "revisions": revs, "last": cur[-1]["t"],
            "not_advancing": f"{stuck}; the store's last bar is {cur[-1]['t']}" if stuck else None}


def revision_record(sym, old, new, src, seal, fp_digest, now):
    """The chained log record of one revised bar (WY-F1 §4): the bar as the store holds it (first stored: what every
    decision and resolve uses) and as the source now shows it, the fields that differ, the source and when it was seen.
    [WY-F1 §4]"""
    def px(b):
        return {k: b.get(k) for k in PRICE_KEYS + ("v",)}
    return {"kind": "revision", "study": STUDY, "symbol": sym, "t": old["t"], "src": src, "store": px(old),
            "source": px(new), "fields": [k for k in PRICE_KEYS if round(old[k], PRICE_DP) != round(new[k], PRICE_DP)],
            "seal": seal["sha"], "fingerprint": fp_digest, "python": platform.python_version(), "seen_at": now}


def series_of(sym, bars, dense=None):
    """edge_wyckoff.Series over store bars, cut at the sealed R0 dense start (every store bar is after it). Its index
    is the store's line index, so it is asserted equal. [WY-F1 §2]"""
    E = ew()
    dense = dense or r0_dense()
    candles = [{"time": b["t"], "open": b["o"], "high": b["h"], "low": b["l"], "close": b["c"], "volume": b.get("v")}
               for b in bars]
    start = datetime.date.fromisoformat(dense[f"{sym}|{TF}"]["start"])
    S = E.Series(sym, TF, candles, E.series_zone("ftmo"), start, venue="ftmo", volume="raw")
    if len(S) != len(bars):
        raise SystemExit(f"refusing: {sym} store bars precede its R0 dense start {start}; the store index would move")
    return S


# ------------------------------------------------------------------------------------------------ events (WY-F1 §2, §4)
def event_id(sym, sc_time, ar_time):
    return f"{sym}|{TF}|{sc_time}|{ar_time}"


def window_sha256(bars, a, k):
    """sha256 over the decision window's bars a..k (time and the four prices, repr): the detector's inputs.
    [WY-F1 §4]"""
    h = hashlib.sha256()
    for b in bars[a:k + 1]:
        h.update(f"{b['t']}|{b['o']!r}|{b['h']!r}|{b['l']!r}|{b['c']!r}\n".encode())
    return h.hexdigest()


def fire(S, k_lo, k_hi, emit_from, ctx, pidx):
    """W-C (Phase-C long) events of the windows k_lo..k_hi-1, de-duplicated over those windows as
    edge_wyckoff.detect_series does it: per leg, on (side, SC, AR), here as bar TIMES. Only events at windows >=
    `emit_from` are returned. Starting `window - 1` windows before `emit_from` rebuilds the de-duplication exactly: a
    structure's SC lies inside every window that sees it, so an earlier firing is at most window - 1 windows back.
    [WY-F1 §2, §4]"""
    E = ew()
    cfg, P, sob = ctx
    seen, out = set(), []
    for k in range(max(k_lo, cfg["window"] - 1), k_hi):
        for ev in E.window_fire(S, k, cfg, P, sob, pidx)[0]:
            if ev["leg"] != LEG:
                continue
            key = (ev["side"], S.T[ev["sc"]], S.T[ev["ar"]])
            if key in seen:
                continue
            seen.add(key)
            if k >= emit_from:
                out.append(ev)
    return out


def decision(S, ev, bars, heads, window):
    """The DECISION_KEYS record of one event, everything known at the close of its signal bar k. [WY-F1 §4]"""
    k = ev["k"]
    a = k - window + 1

    def t(i):
        return S.T[i] if i is not None else None
    return {"id": event_id(S.sym, S.T[ev["sc"]], S.T[ev["ar"]]), "symbol": S.sym, "tf": TF, "cell": CELL,
            "leg": ev["leg"], "side": ev["side"], "type": ev["type"], "sc_time": t(ev["sc"]), "ar_time": t(ev["ar"]),
            "s_time": t(ev["s"]), "r_time": t(ev["r"]), "t_time": t(ev["t"]), "signal_time": S.T[k],
            "signal_close": _iso(S.avail[k]), "store_index": k, "tr_lo": ev["tr_lo"], "tr_hi": ev["tr_hi"],
            "ceiling": ev["ceiling"], "spring_low": ev["spring_low"], "stop": ev["stop"], "target": ev["target"],
            "phase_b_tests": ev["phase_b_tests"], "sloped": ev["sloped"], "path": ev["path"],
            "prev_dense": bool(S.prev_dense[k]), "atr": S.atr[k], "window_first": S.T[a],
            "window_sha256": window_sha256(bars, a, k), "chain_at_signal": heads[k]}


def stamp(dec, seal, fp_digest, now):
    return dict(dec, kind="event", study=STUDY, seal=seal["sha"], fingerprint=fp_digest,
                python=platform.python_version(), logged_at=now)


def scan_symbol(S, bars, heads, through, seal, ctx, logged):
    """(new event decisions, last bar time scanned): the windows not scanned yet (after `through`, the scan cache;
    from the first bar closing at or after the seal without it), with window - 1 earlier windows as de-duplication
    context. An event is new when its signal bar closed at or after the seal and its id is not in `logged`; a lost
    cache only costs a re-scan. [WY-F1 §3, §4]"""
    E = ew()
    if not len(S):
        return [], through
    cfg, P, _sob = ctx
    seal_dt = _utc(seal["instant"])
    k0 = bisect.bisect_left(S.avail, seal_dt)
    if through is not None:
        k0 = max(k0, bisect.bisect_right(S.T, through))
    if k0 >= len(S):
        return [], S.T[-1]
    pidx = E.W.pivot_index(S.H, S.L, P["pivot"])
    out = []
    for ev in fire(S, k0 - (cfg["window"] - 1), len(S), k0, ctx, pidx):
        if S.avail[ev["k"]] < seal_dt:
            continue
        dec = decision(S, ev, bars, heads, cfg["window"])
        if dec["id"] not in logged:
            out.append(dec)
            logged.add(dec["id"])
    return out, S.T[-1]


def htf_candles(S, k, minutes):
    """The next-rung candles known at the CLOSE of store bar k, from the store's own bars 0..k (S.src): grouped by their
    UTC bucket of `minutes` -- first open, max high, min low, last close, summed tick volume (None when a bar lacks
    one). That is how MT5 builds its own 1H bar from the hour's ticks, and FTMO's server offset is whole hours, so the
    UTC hour is the server hour. The bucket that bar k does not complete is left out. Nothing after bar k is read.
    [WY-F1 §6]"""
    step = minutes * 60
    out, cur, key = [], None, None
    for c in S.src[:k + 1]:
        g = int(_utc(c["time"]).timestamp()) // step
        if g != key:
            if cur is not None:
                out.append(cur)
            key = g
            cur = {"time": _iso(datetime.datetime.fromtimestamp(g * step, UTC)), "open": c["open"], "high": c["high"],
                   "low": c["low"], "close": c["close"], "volume": c.get("volume")}
        else:
            cur.update(high=max(cur["high"], c["high"]), low=min(cur["low"], c["low"]), close=c["close"],
                       volume=(cur["volume"] + c["volume"]) if cur["volume"] is not None
                       and c.get("volume") is not None else None)
    if cur is not None and S.avail[k].timestamp() >= (key + 1) * step:
        out.append(cur)
    return out


def htf_gate(S, k):
    """(flag, error) -- the ICT HTF gate at the signal, as the ablation's A3 arm applies it: backtest-methods
    htf_bias_gate(sym, 15m, long, decision time = the signal bar's CLOSE, HTF_METHODS), under the engine's base OPTS
    with htf on, its history load answered by `htf_candles` (the store's own bars up to the signal; no file is read).
    flag: True agrees, False refused, None unable to judge (htf_bias_gate's own three values). LOG ONLY: an exception
    is logged as (None, its repr), never raised, so this field cannot stop collection. [WY-F1 §6]"""
    bt = ew().engine()
    h = bt.HTF_OF.get(TF)
    candles = htf_candles(S, k, bt._N.tf_seconds(h) // 60) if h else []
    real_load, saved = bt.load, bt.OPTS

    def load(sym, tf):
        if sym == S.sym and tf == h:
            return list(candles), None
        raise SystemExit(f"refusing: the HTF gate asked for {sym} {tf}; WY-F1 serves only {S.sym} {h} from its store")
    try:
        bt.load, bt.OPTS = load, dict(bt._OPTS_BASE, htf=True)
        return bt.htf_bias_gate(S.sym, TF, SIDE, _iso(S.avail[k]), HTF_METHODS), None
    except Exception as exc:  # noqa: BLE001 -- a log-only field never stops collection; the error is logged instead
        return None, repr(exc)[:300]
    finally:
        bt.load, bt.OPTS = real_load, saved


def trade_path(S, e, x, entry, stop):
    """MFE and MAE in R, and bars to MFE, of a long filled at the open of bar e and exited on bar x: the highs and lows
    of bars e..x -- the walk's own bars -- over the planned risk entry - stop. bars_to_mfe counts from the entry bar (0)
    to the first bar at the highest high. [WY-F1 §6]"""
    risk = entry - stop
    hs, ls = S.H[e:x + 1], S.L[e:x + 1]
    top = max(hs)
    return {"mfe_r": (top - entry) / risk, "mae_r": (entry - min(ls)) / risk, "bars_to_mfe": hs.index(top)}


def entry_spread(S, e, entry, stop):
    """The round-trip spread priced at the ENTRY hour, no night held, in R of the planned stop (median and p90):
    real_costs.cost_r with the entry time as both ends, the sealed re-test's cost profile -- a cost known at the entry,
    the WY-X1 draft's X0 convention. A refused price is logged as {"error": why}. [WY-F1 §6]"""
    E = ew()
    try:
        return {st: E.RC.cost_r(entry, stop, S.T[e], S.T[e], S.sym, SIDE, E.COST_PROFILE, st)["spread_R"]
                for st in ("median", "p90")}
    except E.RC.CostRefused as exc:
        return {"error": str(exc)[:200]}


def resolve_record(S, rec, seal, fp_digest, now):
    """The event's own trade (sealed re-test §3.2), once it is known, or None: entry at the open of k+1; skipped when
    that open is at or beyond the stop or the target, or ATR20 is missing; else edge_wyckoff.walk_from under
    walk_opts (fx_gap_fill on, mgmt none). Recorded once the stop or the target is hit, or after H bars. Gross R only:
    the placebo and the cost need the whole read window and are the read's. Every record also carries the LOG-ONLY
    fields (LOG_ONLY_KEYS, None where they do not apply): the ICT HTF gate flag at the signal (`htf_gate`) and, for a
    walked trade, the planned R:R at the entry open, the entry-hour spread (`entry_spread`), MFE / MAE in R and bars to
    MFE (`trade_path`) -- all from bars this resolve already reads. Never tested in WY-F1. [WY-F1 §6]"""
    E = ew()
    bt = E.engine()
    k = rec["store_index"]
    e = k + 1
    if S.T[k] != rec["signal_time"]:
        raise SystemExit(f"refusing: {rec['id']}'s signal bar is no longer store line {k}")
    if e >= len(S):
        return None
    entry = S.O[e]
    base = {"kind": "resolve", "study": STUDY, "id": rec["id"], "symbol": rec["symbol"], "entry_time": S.T[e],
            "entry": entry, "seal": seal["sha"], "fingerprint": fp_digest, "python": platform.python_version(),
            "resolved_at": now}

    def done(**kw):
        flag, err = htf_gate(S, k)
        out = dict(base, **dict.fromkeys(LOG_ONLY_KEYS))
        out.update(kw)
        out.update(htf_gate=flag, htf_gate_error=err)
        return out
    if not E.placeable(SIDE, entry, rec["stop"], rec["target"]):
        return done(placeable=False, skip="entry_beyond_stop_or_target")
    if not (S.atr[k] or 0) > 0:
        return done(placeable=True, skip="no_atr")
    HZ = horizon()
    with E.walk_opts(bt):
        w = E.walk_from(bt, SIDE, entry, rec["stop"], rec["target"], S, e, HZ)
    if w is None:
        return done(placeable=True, skip="no_risk")
    if w["outcome"] not in ("win", "loss") and e + HZ > len(S):
        return None
    return done(placeable=True, skip=None, exit_time=S.T[w["exit"]], outcome=w["outcome"], R=w["R"],
                bars_held=w["bars_held"], planned_rr=(rec["target"] - entry) / (entry - rec["stop"]),
                spread_r_entry=entry_spread(S, e, entry, rec["stop"]),
                **trade_path(S, e, w["exit"], entry, rec["stop"]))


# ------------------------------------------------------------------------------------------------ one cycle (in memory)
def cycle_core(data_root, seal, fp_digest, now, only=None, init_root=None, symbols=SYMBOLS):
    """One forward cycle, computed in memory: repair (a chain's UNTERMINATED last line, left by a worker killed during
    `commit`, is planned for `drop_torn`), accumulate (closed 15m bars into each store; a revised bar is logged once per
    new price as a `revision` record, `revision_record`), scan (new windows into the log), resolve (logged events whose
    exit is now known). Returns {"writes": [...], "summary": {...}}; nothing is written here (the worker writes after
    its trace check). The summary lists stalled and NOT ADVANCING symbols with the reason; it never counts resolves: a
    resolve a few bars after its entry is a stop or a target, and the summary goes to the cycle log and
    last_cycle.json. [WY-F1 §4, §6]"""
    init_root = init_root or CODE_ROOT
    torn, kept = {}, {}

    def chain(path):
        recs, hs = read_chain(path, torn)
        kept[path] = (len(recs), hs[-1] if hs else GENESIS)
        return recs, hs
    log_path = _rt(data_root, "log.jsonl")
    log, log_heads = chain(log_path)
    logged = {r["id"] for r in log if r["kind"] == "event"}
    resolved = {r["id"] for r in log if r["kind"] == "resolve"}
    seen = {(r["symbol"], r["t"], _canon(r["source"])) for r in log if r["kind"] == "revision"}
    cache_path = _rt(data_root, "scan.json")
    cache = _read_json(cache_path, {}) or {}
    ctx = det_ctx() if only in (None, "scan") else None
    writes, new_log, notes = [], [], []
    summary = {"study": STUDY, "seal": seal["sha"][:12], "added_bars": {}, "new_events": 0, "stalled": [],
               "not_advancing": {}, "revisions": 0}
    for sym in symbols:
        bpath = _rt(data_root, "bars", f"{sym}.{TF}.jsonl")
        bars, heads = chain(bpath)
        if only in (None, "accumulate"):
            acc = accumulate_symbol(sym, bars, data_root, init_root, seal, now)
            add = acc["add"]
            notes += acc["notes"]
            if acc["stalled"]:
                summary["stalled"].append(sym)
            if acc["not_advancing"]:
                summary["not_advancing"][sym] = acc["not_advancing"]
            for old, new, src in acc["revisions"]:
                rec = revision_record(sym, old, new, src, seal, fp_digest, now)
                key = (sym, rec["t"], _canon(rec["source"]))
                if key not in seen:
                    seen.add(key)
                    new_log.append(rec)
                    summary["revisions"] += 1
            if add:
                writes.append(("chain", bpath, add, heads[-1] if heads else GENESIS))
                heads = heads + link_all(heads[-1] if heads else GENESIS, add)
                bars = bars + add
            summary["added_bars"][sym] = len(add)
        if not bars or only == "accumulate":
            continue
        S = series_of(sym, bars)
        if only in (None, "scan"):
            decs, through = scan_symbol(S, bars, heads, cache.get(sym), seal, ctx, logged)
            new_log += [stamp(d, seal, fp_digest, now) for d in decs]
            summary["new_events"] += len(decs)
            if through is not None:
                cache[sym] = through
        if only in (None, "resolve"):
            for rec in [r for r in log + new_log if r["kind"] == "event" and r["symbol"] == sym]:
                if rec["id"] in resolved:
                    continue
                rr = resolve_record(S, rec, seal, fp_digest, now)
                if rr is not None:
                    new_log.append(rr)
                    resolved.add(rec["id"])
    if new_log:
        writes.append(("chain", log_path, new_log, log_heads[-1] if log_heads else GENESIS))
    if only in (None, "scan"):
        writes.append(("json", cache_path, cache))
    rep_path = _rt(data_root, REPAIRS)
    chain(rep_path)
    if torn:                                    # first: every later append expects the chains without their torn tails
        plans = [repair_plan(data_root, p, torn[p], kept[p], seal, fp_digest, now) for p in sorted(torn)]
        writes.insert(0, ("repair", rep_path, kept[rep_path][1], plans))
        summary["repaired"] = [p["record"]["file"] for p in plans]
    summary["notes"] = notes
    return {"writes": writes, "summary": summary}


# ------------------------------------------------------------------------------------------------ two looks (WY-F1 §7)
def norm_cdf(x):
    """Phi(x), the standard normal CDF, in its erfc form (accurate in both tails). [WY-F1 §7]"""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_ppf(p):
    """Phi^-1(p) for 0 < p < 1, by bisection on norm_cdf to double precision. [WY-F1 §7]"""
    if not 0.0 < p < 1.0:
        raise ValueError(f"norm_ppf needs 0 < p < 1, got {p!r}")
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if norm_cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _gauss_legendre(n):
    """(nodes, weights) of n-point Gauss-Legendre on [-1, 1]: Newton's method on the Legendre recurrence, computed here
    so no table of constants can be mistyped. [WY-F1 §7]"""
    def legendre(x):
        p0, p1 = 1.0, x
        for j in range(2, n + 1):
            p0, p1 = p1, ((2 * j - 1) * x * p1 - (j - 1) * p0) / j
        return p1, n * (x * p1 - p0) / (x * x - 1.0)
    xs, ws = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p, dp = legendre(x)
            x, step = x - p / dp, p / dp
            if abs(step) < 1e-16:
                break
        _p, dp = legendre(x)
        xs.append(x)
        ws.append(2.0 / ((1.0 - x * x) * dp * dp))
    return tuple(xs), tuple(ws)


_GL20 = _gauss_legendre(20)


def bvn_lower(a, b, r):
    """P(Z1 <= a, Z2 <= b) for a standard bivariate normal with correlation r. [WY-F1 §7]
    - |r| < 0.925: Phi(a) Phi(b) + 1/(2 pi) * integral over th from 0 to asin(r) of
      exp(-(a^2 + b^2 - 2ab sin th) / (2 cos^2 th)), by 20-point Gauss-Legendre (the low-correlation branch of Drezner and
      Wesolowsky 1990 / Genz 2004);
    - |r| >= 0.925: integral over x up to a of phi(x) Phi((b - r x) / sqrt(1 - r^2)), composite 20-point Gauss-Legendre
      on panels no wider than sqrt(1 - r^2) (so the step in Phi is resolved);
    - r = 1 or -1 and infinite limits: closed forms."""
    if a == -math.inf or b == -math.inf:
        return 0.0
    if a == math.inf:
        return norm_cdf(b)
    if b == math.inf:
        return norm_cdf(a)
    r = max(-1.0, min(1.0, r))
    if r == 1.0:
        return norm_cdf(min(a, b))
    if r == -1.0:
        return max(0.0, norm_cdf(a) + norm_cdf(b) - 1.0)
    xs, ws = _GL20
    if abs(r) < 0.925:
        half = math.asin(r) / 2.0
        hs, ab = (a * a + b * b) / 2.0, a * b
        tot = 0.0
        for x, w in zip(xs, ws):
            sn = math.sin(half * (1.0 + x))
            tot += w * math.exp((sn * ab - hs) / (1.0 - sn * sn))
        return max(0.0, min(1.0, norm_cdf(a) * norm_cdf(b) + tot * half / (2.0 * math.pi)))
    s = math.sqrt((1.0 - r) * (1.0 + r))
    lo = -10.0
    if a <= lo:
        return 0.0
    m = max(1, int(math.ceil((a - lo) / min(0.25, s))))
    h = (a - lo) / m
    tot = 0.0
    for j in range(m):
        x0 = lo + j * h
        for x, w in zip(xs, ws):
            u = x0 + h * (x + 1.0) / 2.0
            tot += w * math.exp(-0.5 * u * u) * norm_cdf((b - r * u) / s)
    return max(0.0, min(1.0, tot * h / 2.0 / math.sqrt(2.0 * math.pi)))


def obf_spend(t, alpha=ALPHA):
    """Lan-DeMets O'Brien-Fleming-type alpha spending at information fraction t, one-sided level `alpha`:
    alpha(t) = 2 (1 - Phi(z_{1 - alpha/2} / sqrt(t))); 0 at t <= 0, alpha at t >= 1 (Lan and DeMets 1983, Biometrika
    70:659-663). [WY-F1 §7]"""
    if t <= 0:
        return 0.0
    if t >= 1:
        return alpha
    return 2.0 * norm_cdf(norm_ppf(alpha / 2.0) / math.sqrt(t))


def look1_boundary(n1, n_rest=N_REST_PLAN, alpha=ALPHA):
    """Look 1's boundary, from its ACTUAL read events n1 (outcome-blind): information fraction t1 = n1 / (n1 + n_rest),
    alpha spent a1 = obf_spend(t1), z boundary z1 = Phi^-1(1 - a1) (None when a1 = 0: no pass is possible), nominal
    one-sided p threshold a1. [WY-F1 §7]"""
    t = n1 / (n1 + n_rest) if n1 > 0 else 0.0
    a1 = obf_spend(t, alpha)
    return {"look": 1, "n": n1, "n_rest_plan": n_rest, "t": t, "alpha_spent": a1,
            "z": -norm_ppf(a1) if a1 > 0 else None, "p_threshold": a1}


def look2_boundary(b1, n2, n12, alpha=ALPHA):
    """Look 2's (final) boundary c2, from look 1's boundary `b1` and the ACTUAL counts: n2 events read at look 2, n12 of
    them also read at look 1. Under the null the look statistics (Z1, Z2) are standard bivariate normal with correlation
    rho = n12 / sqrt(n1 n2) (sqrt(n1 / n2) when look 1's sample lies inside look 2's), so c2 solves
    P0(Z1 < z1, Z2 < c2) = 1 - alpha: the false-pass probability over both looks is exactly `alpha` for any event rate,
    whatever look 1 spent. Nominal one-sided p threshold 1 - Phi(c2). [WY-F1 §7]"""
    n1, a1, z1 = b1["n"], b1["alpha_spent"], b1["z"]
    rho = min(1.0, max(0.0, n12 / math.sqrt(n1 * n2))) if n1 > 0 and n2 > 0 else 0.0
    if z1 is None:
        c2 = -norm_ppf(alpha)
    else:
        lo, hi = -12.0, 12.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            if bvn_lower(z1, mid, rho) < 1.0 - alpha:
                lo = mid
            else:
                hi = mid
        c2 = 0.5 * (lo + hi)
    return {"look": 2, "n1": n1, "n2": n2, "n12": n12, "rho": rho, "alpha_spent": alpha - a1, "z": c2,
            "p_threshold": norm_cdf(-c2)}


def crossed(summary, boundary):
    """The look's pass test: events read, mean net excess > 0 on the primary cost line, and its one-sided p (CR1 by ISO
    week, Student-t with G - 1 df) below the boundary's nominal threshold -- both compared rounded to 10 significant
    digits (`sig10`), so an ulp of the OS math library never decides it. [WY-F1 §5, §7]"""
    return (bool(summary.get("n")) and sig10(summary["net_excess"]) > 0
            and sig10(summary["p_one_sided"]) < sig10(boundary["p_threshold"]))


def statistic_sha256(stat):
    """The commitment to a look's statistic: `split_sha256` of its scored rows and counts, exactly (no row value goes
    through an OS math function), and its summary, its derived floats (p, bounds) rounded to 10 significant digits. A
    blinded look 1 publishes only this; look 2 recomputes the look-1 statistic and must reproduce it
    (`statistic_verifies`). [WY-F1 §5, §7]"""
    return split_sha256({"rows": stat["rows"]}, {"summary": stat["summary"]})


def statistic_verifies(stat, sha):
    """Does the recomputed statistic reproduce the committed `sha`, allowing a derived float that lies within TIE_REL of
    a rounding midpoint either rounding (`split_digests`)? One changed row value never does. [WY-F1 §5, §7]"""
    return sha in split_digests({"rows": stat["rows"]}, {"summary": stat["summary"]})


def boundary_matches(recomputed, committed):
    """Look 1's committed boundary against the one its recomputed count gives: the count exactly, every float within
    BOUNDARY_REL_TOL (math.isclose), z both None when no event was read. [WY-F1 §5, §7]"""
    if not committed or recomputed["n"] != committed.get("n"):
        return False
    for k in ("t", "alpha_spent", "z", "p_threshold"):
        a, b = recomputed.get(k), committed.get(k)
        if a is None or b is None:
            if a is not b:
                return False
        elif not math.isclose(a, b, rel_tol=BOUNDARY_REL_TOL, abs_tol=0.0):
            return False
    return True


# ------------------------------------------------------------------------------------------------ the read (WY-F1 §7-§8)
def complete_through(S, HZ):
    """The close of the last bar that has HZ bars after it in the store: every event or placebo entry up to there has
    its whole walk. None when the store is shorter (or missing). [WY-F1 §7]"""
    if S is None:
        return None
    j = len(S) - 1 - HZ
    return S.avail[j] if j >= 0 else None


def look_plan(seal_instant, months=LOOK_MONTHS, grace_months=GRACE_MONTHS):
    """[(cutoff, grace end)] of each look: the seal instant + LOOK_MONTHS calendar months, and that + GRACE_MONTHS
    (None without the fallback). Fixed by the seal alone. [WY-F1 §7]"""
    s = _utc(seal_instant)
    return [(add_months(s, m), add_months(s, m + grace_months) if grace_months is not None else None) for m in months]


def due(series, seal_instant, HZ, look=1, plan=None, min_complete=DROP_MIN_COMPLETE):
    """OUTCOME-BLIND: is look `look` due, and where does its window end? Its cutoff is fixed (`look_plan`). Every symbol
    must be complete through it (HZ bars after it, so every walk is whole). The fallback (T-drop), per look: when not
    every symbol is complete but some symbol is complete through the look's grace end AND at least `min_complete`
    symbols (5 of the 10) are complete through the cutoff, every symbol not complete through the cutoff is dropped
    WHOLE from this look (`dropped`); with fewer complete the look waits. Completeness is the store's own bars: a
    symbol without a store, or whose store stopped advancing, is never complete -- a missing feed is never read as an
    empty market. A look first takes a history export of all 10 symbols into the stores (`export_problems`), so a
    stalled or holed store is filled before this is asked. It reads data times only, never a wall clock or an outcome.
    [WY-F1 §7]"""
    plan = plan or look_plan(seal_instant)
    t_cut, g_cut = plan[look - 1]
    ends = {sym: complete_through(S, HZ) for sym, S in series.items()}
    common = min(ends.values()) if ends and all(v is not None for v in ends.values()) else None
    complete = sorted(s for s, v in ends.items() if v is not None and v >= t_cut)
    out = {"look": look, "t_cutoff": _iso(t_cut), "grace_cutoff": _iso(g_cut) if g_cut else None,
           "common_complete_through": _iso(common) if common else None,
           "complete_through": {s: (_iso(v) if v else None) for s, v in ends.items()}, "dropped": [],
           "complete_at_cutoff": len(complete), "min_complete": min_complete}
    if common is not None and common >= t_cut:
        return dict(out, cutoff=_iso(t_cut), rule=f"T{look}: look {look}, cutoff {_iso(t_cut)}")
    reached = [v for v in ends.values() if v is not None]
    if g_cut is not None and reached and max(reached) >= g_cut and len(complete) >= min_complete:
        drop = sorted(s for s in ends if s not in complete)
        return dict(out, cutoff=_iso(t_cut), dropped=drop,
                    rule=f"T{look}-drop: look {look}, cutoff {_iso(t_cut)}; {len(complete)} of {len(ends)} symbols "
                         f"complete through it at the grace end {_iso(g_cut)}, dropped whole: {', '.join(drop)}")
    return dict(out, cutoff=None, rule=None)


def member(S, ev, lo_dt, hi_dt):
    """In the read's sample: signal bar closed at or after the seal, entry bar exists and closes by the cutoff, and the
    server day before the signal bar was dense. [WY-F1 §3, §7]"""
    k, e = ev["k"], ev["k"] + 1
    return e < len(S) and S.prev_dense[k] and S.avail[k] >= lo_dt and S.avail[e] <= hi_dt


def probe(sym, bars, heads, decs, ctx, fire_fn=None):
    """The point-in-time truncation probe: each event is re-detected on the store CUT at its signal bar, with the
    window's own pivots, and every DECISION_KEYS field (prev_dense and ATR20 included) must be identical. A probe that
    checked nothing is not a pass. [WY-F1 §8]"""
    E = ew()
    cfg, P, sob = ctx
    fire_fn = fire_fn or E.window_fire
    checked, bad, first = 0, 0, None
    for dec in decs:
        k = dec["store_index"]
        checked += 1
        try:
            cut = series_of(sym, bars[:k + 1])
            got = [decision(cut, x, bars[:k + 1], heads[:k + 1], cfg["window"])
                   for x in fire_fn(cut, k, cfg, P, sob, None)[0] if x["leg"] == LEG]
            got = [g for g in got if g["id"] == dec["id"]]
            ok = len(got) == 1 and _canon(got[0]) == _canon({f: dec[f] for f in DECISION_KEYS})
            why = None if ok else {"event": dec["id"], "re_detected": got}
        except Exception as exc:  # noqa: BLE001 -- a read past the cut is exactly what the probe looks for
            ok, why = False, {"event": dec["id"], "error": repr(exc)}
        if not ok:
            bad += 1
            first = first or json.loads(json.dumps(why, default=str))
    return {"checked": checked, "violations": bad, "ok": checked > 0 and bad == 0, "first_violation": first}


def load_export(root, sym, since):
    """(closed bars, note, provenance) of the FTMO 15m history export under `root`, from `since`'s year on
    (`history_source`, `history_meta`). [WY-F1 §8]"""
    bars, note = history_source(root, sym, since=since)
    return bars, note, history_meta(root, sym, since=since)


def history_check(sym, bars, S, seal_dt, cutoff_dt, HZ, hist_root, spans=(), revised=(), export=None):
    """The forward bars against a LATER FTMO history export, BOTH ways, bar by bar (OUTCOME-BLIND). The window is the
    store bars from the first one closing at or after the seal to HZ bars after the cutoff bar. It reports:
    - coverage, the share of the window's store bars the export holds, and agreement, the share of those at the same
      prices;
    - missing, the export's bars inside the window's time span that the store lacks (a hole the live file skipped would
      otherwise pass with coverage 1.0);
    - spans_end, whether the export reaches the window's last bar (an export taken too early checks nothing after it);
    - `differences`: EVERY bar where the two differ, in the window or in a sampled event's span (`spans`: (event id,
      first index, last index) store ranges, each event's 300-bar window to HZ bars after its entry, its longest walk):
      the bar time, the kind (price, store_lacks, export_lacks), the fields, the spans it lies in, and whether a logged
      revision of that bar explains it (`revised`: bar times). No price is reported. A difference inside a span is not
      refused here: `export_replay` (decisions) and `export_walks` (trades) decide whether it changed anything;
    - the export's _exported_at_utc and the sha256 of every file read. `export` is a preloaded `load_export`.
    [WY-F1 §8]"""
    lo = bisect.bisect_left(S.avail, seal_dt)
    j = bisect.bisect_right(S.avail, cutoff_dt) - 1
    win = bars[lo:min(len(bars), j + HZ + 1)]
    out = {"bars": len(win), "covered": 0, "agree": 0, "coverage": 0.0, "agreement": 0.0, "first_mismatch": None,
           "export_bars_in_window": 0, "missing": 0, "missing_share": 0.0, "first_missing": None,
           "window_last": win[-1]["t"] if win else None, "export_last": None, "spans_end": False,
           "spans_checked": len(spans), "differences": [], "span_differences": 0, "revised_differences": 0,
           "export": None, "note": None}
    if not win:
        return out
    if export is None:
        export = load_export(hist_root, sym, min([win[0]["t"]] + [bars[a]["t"] for _i, a, _b in spans]))
    hist, note, meta = export
    htimes = [b["t"] for b in hist]
    hmap = {b["t"]: b for b in hist}
    stimes = [b["t"] for b in bars]
    smap = {b["t"]: b for b in bars}
    cov = [b for b in win if b["t"] in hmap]
    agr = [b for b in cov if same(b, hmap[b["t"]])]
    mis = next((b["t"] for b in cov if not same(b, hmap[b["t"]])), None)

    def export_in(t0, t1):
        return hist[bisect.bisect_left(htimes, t0):bisect.bisect_right(htimes, t1)]
    h_in = export_in(win[0]["t"], win[-1]["t"])
    gone = [b["t"] for b in h_in if b["t"] not in smap]
    times = set()
    for t0, t1 in [(win[0]["t"], win[-1]["t"])] + [(bars[a]["t"], bars[b]["t"]) for _i, a, b in spans]:
        times.update(stimes[bisect.bisect_left(stimes, t0):bisect.bisect_right(stimes, t1)])
        times.update(x["t"] for x in export_in(t0, t1))
    revised = set(revised)
    diffs = []
    for t in sorted(times):
        sb, xb = smap.get(t), hmap.get(t)
        if sb is not None and xb is not None:
            if same(sb, xb):
                continue
            d = {"t": t, "kind": "price",
                 "fields": [k for k in PRICE_KEYS if round(sb[k], PRICE_DP) != round(xb[k], PRICE_DP)]}
        else:
            d = {"t": t, "kind": "export_lacks" if xb is None else "store_lacks"}
        d["spans"] = [i for i, a, b in spans if bars[a]["t"] <= t <= bars[b]["t"]]
        d["revised"] = t in revised
        diffs.append(d)
    return dict(out, covered=len(cov), agree=len(agr), coverage=len(cov) / len(win),
                agreement=len(agr) / len(cov) if cov else 0.0, first_mismatch=mis,
                export_bars_in_window=len(h_in), missing=len(gone),
                missing_share=len(gone) / len(h_in) if h_in else 0.0, first_missing=gone[0] if gone else None,
                export_last=htimes[-1] if htimes else None, spans_end=bool(htimes) and htimes[-1] >= win[-1]["t"],
                differences=diffs, span_differences=sum(1 for d in diffs if d["spans"]),
                revised_differences=sum(1 for d in diffs if d["revised"]), export=meta, note=note)


def export_replay(sym, bars, export_bars, seal_dt, cutoff_dt, end_t, ctx, logged):
    """OUTCOME-BLIND (detection only; WY-F1 §8 item 4, decision 2026-10-04): the detector replayed on the EXPORT's bars
    over the store's own span (its first bar to `end_t`, the checked window's last bar), as the look replays the store,
    against `logged` (event id -> decision, the log's = the store replay's) for the events whose signal bar closes in
    [seal, cutoff]: the same ids, and for each the same DECISION_VALUE_KEYS. A doctored bar that suppresses or creates
    an event, or a difference that changes a decision (a pivot, the trading range, ATR20, the previous day's density),
    fails here; a harmless one passes. Returns (report, the export's Series for `export_walks`). [WY-F1 §8]"""
    E = ew()
    cfg, P, _sob = ctx
    xb = [b for b in export_bars if bars[0]["t"] <= b["t"] <= end_t] if bars and end_t else []
    want = {i: {k: d[k] for k in DECISION_VALUE_KEYS} for i, d in logged.items()
            if d["symbol"] == sym and seal_dt <= _utc(d["signal_close"]) <= cutoff_dt}
    if not xb:
        return {"events": 0, "logged": len(want), "only_in_export": [], "only_in_log": sorted(want), "changed": [],
                "ok": not want}, None
    Sx = series_of(sym, xb)
    got = {}
    for ev in fire(Sx, 0, len(Sx), 0, ctx, E.W.pivot_index(Sx.H, Sx.L, P["pivot"])):
        if seal_dt <= Sx.avail[ev["k"]] <= cutoff_dt:
            d = decision(Sx, ev, xb, [None] * len(xb), cfg["window"])
            got[d["id"]] = {k: d[k] for k in DECISION_VALUE_KEYS}
    only_x, only_l = sorted(set(got) - set(want)), sorted(set(want) - set(got))
    changed = sorted(i for i in set(got) & set(want) if _canon(got[i]) != _canon(want[i]))
    return {"events": len(got), "logged": len(want), "only_in_export": only_x, "only_in_log": only_l,
            "changed": changed, "ok": not (only_x or only_l or changed)}, Sx


def trade_key(bt, S, e, dec, HZ):
    """One event's trade on series S from entry bar e, as `resolve_record` and the sealed score take it: a skip, or
    (outcome, R, exit time, entry). [WY-F1 §6, §8]"""
    E = ew()
    if e is None or e >= len(S):
        return ("no_entry_bar",)
    entry = S.O[e]
    if not E.placeable(SIDE, entry, dec["stop"], dec["target"]):
        return ("entry_beyond_stop_or_target", entry)
    w = E.walk_from(bt, SIDE, entry, dec["stop"], dec["target"], S, e, HZ)
    if w is None:
        return ("no_risk", entry)
    return (w["outcome"], w["R"], S.T[w["exit"]], entry)


def export_walks(S, Sx, sample, HZ):
    """OUTCOME (after the look's attempt record; WY-F1 §8 item 4): each sampled event's trade walked on the export's
    bars must equal the store's -- the same skip, or the same outcome, R, exit time and entry. Counts only, never an R:
    a difference refuses the look (INVALID), so a written record always holds `differ` 0. [WY-F1 §8]"""
    E = ew()
    bt = E.engine()
    idx = {t: i for i, t in enumerate(Sx.T)} if Sx is not None else {}
    bad = []
    with E.walk_opts(bt):
        for _sym, ev, d in sample:
            e = ev["k"] + 1
            mine = trade_key(bt, S, e, d, HZ)
            theirs = trade_key(bt, Sx, idx.get(S.T[e]) if e < len(S) else None, d, HZ) if Sx is not None \
                else ("no_export",)
            if mine != theirs:
                bad.append(d["id"])
    return {"compared": len(sample), "differ": len(bad), "first": bad[0] if bad else None}


def export_problems(hist_root, stores, symbols, t_req):
    """OUTCOME-BLIND (WY-F1 §7, §8; decision 2026-10-04, lead): every look needs a FTMO 15m history export of ALL the
    symbols -- read or dropped -- taken (`_exported_at_utc`) at or after `t_req`, the close of the last bar any read
    symbol's window needs (its cutoff bar + HZ bars), usable, and taken INTO the stores: a store the export would still
    extend (`plan_append`) refuses the look until one `cycle` has run. So a stalled or holed symbol is filled and read
    when the broker has its bars, and no symbol can be left out by not exporting it. Returns ({sym: provenance},
    [problems]). [WY-F1 §7]"""
    meta, out = {}, []
    for sym in symbols:
        m = history_meta(hist_root, sym)
        meta[sym] = {"exported_at_utc": m["exported_at_utc"], "files": m["files"]}
        at = m["exported_at_utc"]
        if not m["files"]:
            out.append(f"{sym}: no 15m history export under {os.path.join(hist_root, HIST_DIR)}")
            continue
        try:
            late_enough = bool(at) and _utc(at) >= t_req
        except (AttributeError, TypeError, ValueError):
            late_enough = False
        if not late_enough:
            out.append(f"{sym}: its export was taken at {at}, not at or after {_iso(t_req)}")
            continue
        bars = stores.get(sym, ([], []))[0]
        hist, note = history_source(hist_root, sym, since=bars[max(0, len(bars) - ALIGN_BARS)]["t"] if bars else None)
        if note and not hist:
            out.append(f"{sym}: the export is unusable ({note})")
            continue
        new = plan_append(bars, hist, "history", "")[0] if bars else []
        if new:
            out.append(f"{sym}: the export still extends its store by {len(new)} bar(s) after {bars[-1]['t']} -- run "
                       f"one `cycle` first")
    return meta, out


def history_problem(h):
    """Why one symbol's history check fails, or None (OUTCOME-BLIND). [WY-F1 §8 item 4]"""
    if not h["bars"]:
        return None
    if not h["spans_end"]:
        return (f"the export ends {h['export_last']}, before the checked window's last bar {h['window_last']} (taken "
                f"too early)")
    if h["coverage"] < HIST_COVER_MIN or h["agreement"] < HIST_AGREE_MIN:
        return f"coverage {h['coverage']:.3f}, agreement {h['agreement']:.3f} (first mismatch {h['first_mismatch']})"
    if h["missing_share"] > HIST_MISSING_MAX:
        return (f"the store lacks {h['missing']} of the export's {h['export_bars_in_window']} bars in the window "
                f"(first {h['first_missing']})")
    rep = h.get("replay")
    if rep is not None and not rep["ok"]:
        return (f"the detector replayed on the export does not give the logged events (only in the export "
                f"{rep['only_in_export'][:3]}, only in the log {rep['only_in_log'][:3]}, decision changed "
                f"{rep['changed'][:3]}): a bar difference suppressed, created or changed an event")
    return None


def _stores(data_root, symbols):
    """(bars, heads) per symbol; a symbol without a store has none (it is not complete through any cutoff)."""
    return {sym: read_chain(_rt(data_root, "bars", f"{sym}.{TF}.jsonl")) for sym in symbols}


def _anchor_problem(a):
    """Why one parsed anchors.jsonl line is not an anchor record (`cmd_anchor`'s shape: an `at` time, and the log's and
    each store's chain length `n` and `head`), or None. [WY-F1 §8]"""
    if not isinstance(a, dict) or not isinstance(a.get("at"), str):
        return "not a JSON object with an `at` time"
    bars = a.get("bars", {})
    if not isinstance(bars, dict):
        return "`bars` is not an object"
    for name, v in [("log", a.get("log"))] + sorted(bars.items()):
        if not (isinstance(v, dict) and isinstance(v.get("n"), int) and v["n"] >= 0
                and (v.get("head") is None or isinstance(v["head"], str))):
            return f"no chain length and head for `{name}`"
    return None


def anchor_lines(data, where):
    """The anchor records in one anchors.jsonl text (bytes). A line that is not an anchor record refuses, naming `where`
    it is. A torn or glued line is never read as a pin. A committed one stays in git history, so `cmd_anchor` never
    writes one. [WY-F1 §4, §8]"""
    out = []
    for n, line in enumerate(data.split(b"\n"), 1):
        if not line.strip():
            continue
        try:
            a = json.loads(line)
        except ValueError:
            a = None
        why = _anchor_problem(a)
        if why:
            raise SystemExit(f"refusing: {ANCHORS} line {n} ({where}) is not an anchor record: {why} [WY-F1 §8]")
        out.append(a)
    return out


def committed_anchors(data_root):
    """Every anchor line ever committed to ANCHORS, on any branch, each with the earliest commit holding it: a later
    commit that drops or edits a line does not drop its pin. Refuses unless the working file is HEAD's -- an
    uncommitted anchor pins nothing, and a working-tree edit must not stand in for the committed lines. A committed
    line that is not an anchor record refuses too, naming its commit (`anchor_lines`): git keeps it, so it is evidence,
    like a terminated chain line that does not verify. [WY-F1 §4, §8]"""
    path = os.path.join(data_root, ANCHORS)
    rc, out = _git(data_root, "rev-parse", "-q", "--verify", f"HEAD:{ANCHORS}")
    head_blob = out.decode().strip() if rc == 0 else None
    if os.path.exists(path) and (head_blob is None or git_blob_id(path) != head_blob):
        raise SystemExit(f"refusing: {ANCHORS} differs from its committed version; commit it first [WY-F1 §8]")
    rc, out = _git(data_root, "log", "--all", "--format=%H %cI", "--", ANCHORS)
    if rc != 0:
        raise SystemExit(f"refusing: git cannot list the history of {ANCHORS} [WY-F1 §8]")
    seen = {}
    for row in reversed([x for x in out.decode().splitlines() if x.strip()]):          # oldest commit first
        sha, ci = row.split()
        rc, blob = _git(data_root, "show", f"{sha}:{ANCHORS}")
        if rc != 0:
            continue                                                                    # a commit that deleted it
        for a in anchor_lines(blob, f"commit {sha[:12]}"):
            seen.setdefault(_canon(a), dict(a, commit=sha, committed=_iso(datetime.datetime.fromisoformat(ci))))
    return list(seen.values())


def verify_anchors(anchors, log_heads, stores):
    """Every anchor must sit on the chains: the log's and each store's hash at the anchored length equal the anchored
    head. `anchors` comes from git (`committed_anchors`), never from the working file. [WY-F1 §8]"""
    for a in anchors:
        pairs = [("log", a["log"], log_heads)] + [(s, v, stores[s][1]) for s, v in a.get("bars", {}).items()
                                                  if s in stores]
        for name, v, heads in pairs:
            if v["n"] and (len(heads) < v["n"] or heads[v["n"] - 1] != v["head"]):
                raise SystemExit(f"refusing: anchor {a['at']} does not sit on the {name} chain (history rewritten "
                                 f"after it was anchored) [WY-F1 §8]")
    return {"verified": len(anchors), "last_committed": max((a.get("committed") or "" for a in anchors), default=None)
            or None, "log_records_anchored": max((a["log"]["n"] for a in anchors), default=0)}


def _sample(replay, series, kept, seal_dt, cut_dt):
    """One look's sample: the replayed events of the kept symbols that are `member`s of (seal, cutoff), in signal order.
    [WY-F1 §7]"""
    return sorted(((sym, ev, d) for sym, ev, d in replay.values()
                   if sym in kept and member(series[sym], ev, seal_dt, cut_dt)),
                  key=lambda x: (x[2]["signal_time"], x[2]["id"]))


def measure(series, sample, cutoff, seal, pricer, score_fn):
    """The sealed re-test's §5 on one look's sample (edge_wyckoff.score: the walk, the ATR-multiple placebo from the
    window (seal, cutoff), real cost; summarise: CR1 by ISO week, Student-t). Rows carry the event id and its symbol
    set ("rt": the re-test's seven, "added": the three added 2026-10-04). [WY-F1 §7]"""
    E = ew()
    bt = E.engine()
    HZ = horizon()
    rows, skipped = [], collections.Counter()
    with E.walk_opts(bt):
        for sym, ev, d in sample:
            r, why = score_fn(bt, series[sym], ev, HZ, pricer, seal["instant"], cutoff)
            if r is None:
                skipped[why] += 1
                continue
            rows.append(dict(r, id=d["id"], set="added" if sym in ADDED_SYMBOLS else "rt"))
    lines = E.FTMO_LINES
    return {"rows": rows, "skipped": dict(skipped), "summary": E.summarise(rows, lines),
            "groups": E.by(rows, "group", lines), "per_symbol": E.by(rows, "symbol", lines),
            "by_type": E.by(rows, "type", lines), "by_set": E.by(rows, "set", lines)}


def _resolve_mismatch(rows, resolves):
    """The scored rows whose logged resolve (gross R, outcome, exit) differs, or is missing. [WY-F1 §8 item 5]"""
    out = []
    for r in rows:
        rv = resolves.get(r["id"])
        if rv is None or rv.get("skip") is not None or rv.get("R") != r["R"] or rv.get("outcome") != r["outcome"] \
                or rv.get("exit_time") != r["exit_time"]:
            out.append(r["id"])
    return out


RESOLVE_STAMPS = ("seal", "fingerprint", "python", "resolved_at")


def log_only_check(series, replay, resolves, seal, fp_digest):
    """REPORTED, never decisive (WY-F1 §6, §8): every logged resolve, recomputed by this sealed code from the stored bars,
    must equal its record field for field (the stamps aside) -- the log-only fields included, so a later study that
    pre-registers on them knows they are reproducible. A mismatch is reported (count and first id), not refused: those
    fields never enter WY-F1's test, and the decisive ones are refused above (`_resolve_mismatch`). [WY-F1 §6]"""
    def strip(x):
        return {k: v for k, v in (x or {}).items() if k not in RESOLVE_STAMPS}
    bad, n = [], 0
    for i in sorted(resolves):
        if i not in replay:
            continue
        sym, _ev, d = replay[i]
        again = resolve_record(series[sym], d, seal, fp_digest, "")
        n += 1
        if again is None or strip(json.loads(json.dumps(again))) != strip(resolves[i]):
            bad.append(i)
    return {"checked": n, "mismatches": len(bad), "first": bad[0] if bad else None,
            "note": "the logged resolves recomputed from the stored bars, log-only fields included; reported, not a "
                    "WY-F1 check"}


#: What a blinded look 1 keeps of its verdict (WY-F1 §7): the decision facts, never an estimate or a p.
BLIND_VERDICT_KEYS = ("look", "label", "pass", "final", "crossed", "n", "t", "alpha_spent", "z_boundary", "p_threshold")
#: What a BLINDED look-1 record keeps (WY-F1 §7; decision 2026-10-04, lead): an ALLOWLIST, so nothing from which an
#: estimate or the resolve count could be derived leaves the worker. Never kept: the statistic; `log_only_check` (it
#: counts the resolves); the log's record count (records - events = resolves); the anchors' log length and the repair
#: list (a dropped line's offset and kept records count the log's lines). `blind` keeps their safe fields only.
BLIND_KEEP = ("look", "cutoff", "sample", "replay", "probe", "history_check", "symbols_read", "symbols_dropped",
              "anchors", "skipped", "boundary", "verdict", "statistic_sha256", "log_lag_seconds", "late_logged",
              "events_with_post_seal_history_bars", "stores", "log", "repairs", "revisions", "exports",
              "export_required_at", "attempt", "attempts", "meta")


def blind(res):
    """Look 1 that did not cross: its record with NO outcome -- no statistic, no estimate, no p, nothing that counts the
    resolves -- only what the look was decided on (outcome-blind; `BLIND_KEEP`) and `statistic_sha256`, the commitment
    look 2 must reproduce. [WY-F1 §7]"""
    out = {k: res[k] for k in BLIND_KEEP if k in res}
    out["verdict"] = {k: res["verdict"][k] for k in BLIND_VERDICT_KEYS if k in res["verdict"]}
    if "log" in res:
        out["log"] = {"head": res["log"].get("head")}
    if "anchors" in res:
        out["anchors"] = {k: res["anchors"].get(k) for k in ("verified", "last_committed", "note")}
    if "repairs" in res:
        out["repairs"] = {k: res["repairs"].get(k) for k in ("records", "files", "note")}
    out["blinded"] = ("look 1 did not cross its boundary: its estimate stays sealed (statistic_sha256) until look 2 "
                      "recomputes, verifies and discloses it")
    return out


def read_core(data_root, seal, fp_digest, look=1, plan=None, prior=None, cost_r=None, symbols=SYMBOLS,
              hist_root=None, price_ref=None, score_fn=None, anchors=(), attempt=None):
    """One look's computation, without its guards (`worker_read` adds them: the committed `anchors`; for look 2, look 1's
    committed record as `prior`; `attempt`, the hook that appends the chained look-attempt record). In order, refusing
    at the first failure:
    OUTCOME-BLIND -- the chains and stamps; the anchors; the full replay of every window against the log; the look's due
    rule (an early look refuses here); the export of ALL the symbols, taken after the window and absorbed by a cycle
    (`export_problems`); the truncation probe; the bars against the export both ways and the detector replayed on the
    export (`history_check`, `export_replay`); the price_ref check. Then `attempt(info)`: from here on the look is
    spent, even if it refuses.
    OUTCOME -- each sampled trade walked on the export (`export_walks`); the sealed §5 measurement; the logged resolves.
    A symbol the look drops (T-drop) leaves its sample whole. Look 1: the boundary from its actual count
    (`look1_boundary`); PASS (final) if crossed, else CONTINUE (`worker_read` writes it `blind`). Look 2: look 1's
    statistic is recomputed on look 1's cutoff and symbols and must reproduce its committed sha256 (`statistic_verifies`)
    and boundary (`boundary_matches`), and must not cross it (look 1 said CONTINUE); look 2's boundary from look 1's
    COMMITTED one and the actual counts (`look2_boundary`); PASS or NOT PASSED. A chain with an unterminated last line
    refuses (a `cycle` drops it first). Reported: the repairs, the revisions and the look attempts in the log, the
    exports, the late-logged events. [WY-F1 §4, §5, §7, §8]"""
    E = ew()
    HZ = horizon()
    ctx = det_ctx()
    cfg = ctx[0]
    seal_dt = _utc(seal["instant"])
    hist_root = hist_root or data_root
    if look not in (1, 2):
        raise SystemExit(f"refusing: WY-F1 has looks 1 and 2, not {look!r} [WY-F1 §7]")
    if look == 2 and not (prior and prior.get("look") == 1 and prior.get("statistic_sha256")
                          and (prior.get("cutoff") or {}).get("cutoff") and prior.get("symbols_read") is not None
                          and prior.get("boundary")):
        raise SystemExit("refusing: look 2 needs look 1's record (its cutoff, symbols, boundary and statistic "
                         "commitment) [WY-F1 §7]")
    log, log_heads = read_chain(_rt(data_root, "log.jsonl"))
    stray = [r.get("id") or r.get("kind") for r in log
             if r.get("seal") != seal["sha"] or r.get("fingerprint") != fp_digest]
    if stray:
        raise SystemExit(f"refusing: {len(stray)} log record(s) were written under another seal or code fingerprint, "
                         f"first {stray[0]} [WY-F1 §5]")
    repairs, _rh = read_chain(_rt(data_root, REPAIRS))
    stores = _stores(data_root, symbols)
    anchored = verify_anchors(anchors, log_heads, stores)
    logged = {r["id"]: r for r in log if r["kind"] == "event"}
    resolves = {r["id"]: r for r in log if r["kind"] == "resolve"}
    revisions = [r for r in log if r["kind"] == "revision"]
    attempts = [r for r in log if r["kind"] == "look_attempt"]
    series, replay = {}, {}
    for sym in symbols:
        bars, heads = stores[sym]
        if not bars:
            series[sym] = None
            continue
        S = series[sym] = series_of(sym, bars)
        pidx = E.W.pivot_index(S.H, S.L, ctx[1]["pivot"])
        for ev in fire(S, 0, len(S), 0, ctx, pidx):
            if S.avail[ev["k"]] >= seal_dt:
                d = decision(S, ev, bars, heads, cfg["window"])
                replay[d["id"]] = (sym, ev, d)
    missing = sorted(set(replay) - set(logged))
    extra = sorted(set(logged) - set(replay))
    changed = sorted(i for i in set(replay) & set(logged)
                     if _canon(replay[i][2]) != _canon({f: logged[i][f] for f in DECISION_KEYS}))
    if missing or extra or changed:
        raise SystemExit(f"refusing: the replay does not match the log (not logged {len(missing)}, not re-detected "
                         f"{len(extra)}, changed {len(changed)}; first {(missing + extra + changed)[0]}) [WY-F1 §8]")
    rule = due(series, seal["instant"], HZ, look, plan)
    if rule["cutoff"] is None:
        raise SystemExit(f"refusing: look {look} is not due -- every symbol must be complete through its cutoff "
                         f"{rule['t_cutoff']} (common complete time {rule['common_complete_through']}); a symbol is "
                         f"dropped only once another is complete through {rule['grace_cutoff']} and at least "
                         f"{rule['min_complete']} are complete through the cutoff ({rule['complete_at_cutoff']} now) "
                         f"[WY-F1 §7]")
    kept = [s for s in symbols if s not in rule["dropped"]]
    cut_dt = _utc(rule["cutoff"])
    sample = _sample(replay, series, kept, seal_dt, cut_dt)
    t_req = max(series[s].avail[min(len(series[s]) - 1, bisect.bisect_right(series[s].avail, cut_dt) - 1 + HZ)]
                for s in kept)
    exports, eprob = export_problems(hist_root, stores, symbols, t_req)
    if eprob:
        raise SystemExit(f"refusing: look {look} needs a FTMO 15m history export of all {len(symbols)} symbols taken at "
                         f"or after {_iso(t_req)} and taken into the stores by one `cycle` -- {len(eprob)} problem(s), "
                         f"first {eprob[0]} [WY-F1 §7, §8]")
    probes = {}
    for sym in kept:
        bars, heads = stores[sym]
        probes[sym] = probe(sym, bars, heads, [d for s, _ev, d in sample if s == sym], ctx)
    pr = {"checked": sum(p["checked"] for p in probes.values()), "violations": sum(p["violations"] for p in
                                                                                    probes.values())}
    if pr["violations"] or (sample and not pr["checked"]):
        raise SystemExit(f"refusing: the truncation probe found {pr['violations']} violation(s) [WY-F1 §8]")
    rev_t = collections.defaultdict(set)
    for r in revisions:
        rev_t[r["symbol"]].add(r["t"])
    hist, xseries, span_t = {}, {}, set()
    for sym in kept:
        bars = stores[sym][0]
        spans = [(d["id"], ev["k"] - cfg["window"] + 1, min(len(bars) - 1, ev["k"] + 1 + HZ))
                 for s, ev, d in sample if s == sym]
        span_t.update((sym, bars[i]["t"]) for _id, a, b in spans for i in range(a, b + 1))
        export = load_export(hist_root, sym, bars[0]["t"])
        h = history_check(sym, bars, series[sym], seal_dt, cut_dt, HZ, hist_root, spans, rev_t[sym], export)
        rep, xseries[sym] = export_replay(sym, bars, export[0], seal_dt, cut_dt, h["window_last"], ctx,
                                          {i: d for i, (s_, _ev, d) in replay.items() if s_ == sym})
        hist[sym] = dict(h, replay=rep)
    weak = {s: history_problem(h) for s, h in hist.items() if history_problem(h)}
    if weak:
        s0 = next(iter(weak))
        raise SystemExit(f"refusing: the forward bars of {', '.join(weak)} cannot be verified against the history export "
                         f"({s0}: {weak[s0]}) [WY-F1 §8]")
    if price_ref is not None:
        cur = {s: _price_ref(s) for s in symbols}
        if cur != price_ref:
            raise SystemExit("refusing: real_costs.price_ref differs from the fingerprint's [WY-F1 §5]")
    att = attempt({"look": look, "cutoff": rule["cutoff"], "rule": rule["rule"], "symbols_read": kept,
                   "symbols_dropped": rule["dropped"], "export_required_at": _iso(t_req),
                   "exports": {s: m["exported_at_utc"] for s, m in exports.items()}}) if attempt else None
    # ---- OUTCOMES from here on: the look is spent (its attempt record is in the log) ----
    for sym in kept:
        hist[sym]["walks"] = export_walks(series[sym], xseries[sym], [x for x in sample if x[0] == sym], HZ)
    moved = sorted(s for s, h in hist.items() if h["walks"]["differ"])
    if moved:
        raise SystemExit(f"refusing: a sampled trade walked on the history export differs from the store's ({moved[0]}: "
                         f"{hist[moved[0]]['walks']['differ']} trade(s)) -- INVALID [WY-F1 §8]")
    pricer = E.Pricer("ftmo", cost_r=cost_r)
    score_fn = score_fn or E.score
    stat = measure(series, sample, rule["cutoff"], seal, pricer, score_fn)
    mism = _resolve_mismatch(stat["rows"], resolves)
    if mism:
        raise SystemExit(f"refusing: {len(mism)} scored event(s) disagree with their logged resolve record, first "
                         f"{mism[0]} [WY-F1 §8]")
    rows, s = stat["rows"], stat["summary"]
    out = {}
    if look == 1:
        b = look1_boundary(s.get("n", 0))
        x = crossed(s, b)
        verdict = {"look": 1, "label": "PASS" if x else "CONTINUE", "pass": x, "final": x, "crossed": x, "n": b["n"],
                   "t": b["t"], "alpha_spent": b["alpha_spent"], "z_boundary": b["z"], "p_threshold": b["p_threshold"],
                   "alpha_total": ALPHA, "net_excess": s.get("net_excess"), "p_one_sided": s.get("p_one_sided"),
                   "upper_95": s.get("upper_95")}
    else:
        cut1 = prior["cutoff"]["cutoff"]
        stat1 = measure(series, _sample(replay, series, prior["symbols_read"], seal_dt, _utc(cut1)), cut1, seal,
                        pricer, score_fn)
        mism = _resolve_mismatch(stat1["rows"], resolves)
        if mism:
            raise SystemExit(f"refusing: {len(mism)} look-1 event(s) disagree with their logged resolve record, first "
                             f"{mism[0]} [WY-F1 §8]")
        if not statistic_verifies(stat1, prior["statistic_sha256"]):
            raise SystemExit("refusing: look 1's statistic, recomputed on its cutoff and symbols, does not reproduce "
                             "its committed sha256 -- INVALID [WY-F1 §7, §8]")
        raw1, b1 = look1_boundary(stat1["summary"].get("n", 0)), prior["boundary"]
        if not boundary_matches(raw1, b1):
            raise SystemExit("refusing: look 1's boundary does not follow from its recomputed count [WY-F1 §7]")
        if crossed(stat1["summary"], b1):
            raise SystemExit("refusing: look 1's recomputed statistic crosses its committed boundary, but look 1 said "
                             "CONTINUE -- INVALID [WY-F1 §7]")
        ids1, ids2 = {r["id"] for r in stat1["rows"]}, {r["id"] for r in rows}
        b = look2_boundary(b1, s.get("n", 0), len(ids1 & ids2))
        x = crossed(s, b)
        n = s.get("n", 0)
        verdict = {"look": 2, "label": "PASS" if x else "NOT PASSED", "pass": x, "final": True, "crossed": x, "n": n,
                   "alpha_spent": b["alpha_spent"], "alpha_spent_look1": b1["alpha_spent"], "alpha_total": ALPHA,
                   "rho": b["rho"], "z_boundary": b["z"], "p_threshold": b["p_threshold"],
                   "net_excess": s.get("net_excess"), "p_one_sided": s.get("p_one_sided"), "upper_95": s.get("upper_95"),
                   "against_the_book": bool(n) and sig10(s["net_excess"]) < 0 and sig10(s["p_two_sided"]) < E.AGAINST_P,
                   "below_delta": bool(n) and s["upper_95"] is not None and sig10(s["upper_95"]) < E.DELTA,
                   "delta": E.DELTA}
        out["look1"] = {"cutoff": prior["cutoff"], "symbols_read": prior["symbols_read"], "boundary": b1,
                        "boundary_recomputed": raw1, "crossed": False, "statistic_sha256": prior["statistic_sha256"],
                        "commitment": "reproduced: the recomputed look-1 statistic has the committed sha256 (its derived "
                                      "floats rounded to 10 significant digits)",
                        "statistic": stat1}
    lags = sorted((_utc(logged[r["id"]]["logged_at"]) - _utc(logged[r["id"]]["signal_close"])).total_seconds()
                  for r in rows)
    late = sorted(r["id"] for r in rows if (_utc(logged[r["id"]]["logged_at"])
                                            - _utc(logged[r["id"]]["signal_close"])).total_seconds() > LATE_LOG_S)
    hist_sourced = sum(1 for sym, ev, d in sample
                       if any(b_.get("src") != "live" for b_ in stores[sym][0][ev["k"] - cfg["window"] + 1:ev["k"] + 2]
                              if b_["t"] >= seal["instant"]))
    out.update({
        "look": look, "cutoff": rule, "sample": len(sample), "replay": {"events": len(replay), "logged": len(logged)},
        "probe": dict(pr, per_symbol=probes), "history_check": hist, "symbols_read": kept,
        "symbols_dropped": rule["dropped"],
        "anchors": dict(anchored, note=None if anchored["verified"] else
                        "no committed anchor: the log's timing (logged_at, the lag) is unanchored"),
        "skipped": stat["skipped"], "boundary": b, "verdict": verdict, "statistic": stat,
        "statistic_sha256": statistic_sha256(stat),
        "log_only_check": log_only_check(series, replay, resolves, seal, fp_digest),
        "log_lag_seconds": {"median": lags[len(lags) // 2] if lags else None, "max": lags[-1] if lags else None},
        "late_logged": {"threshold_seconds": LATE_LOG_S, "events": len(late), "ids": late},
        "events_with_post_seal_history_bars": hist_sourced,
        "stores": {sym: ({"bars": len(b_), "head": h[-1], "first": b_[0]["t"], "last": b_[-1]["t"],
                          "src": dict(collections.Counter(x_.get("src") for x_ in b_))} if b_ else {"bars": 0})
                   for sym, (b_, h) in stores.items()},
        "exports": exports, "export_required_at": _iso(t_req),
        "revisions": {"records": len(revisions), "per_symbol": dict(collections.Counter(r["symbol"] for r in revisions)),
                      "list": [{"symbol": r["symbol"], "t": r["t"], "src": r["src"], "fields": r["fields"],
                                "seen_at": r["seen_at"], "in_a_sampled_span": (r["symbol"], r["t"]) in span_t}
                               for r in revisions],
                      "note": "bars a source showed at another price after the store took them; every decision and "
                              "resolve uses the bar as first stored (point in time)"},
        "attempt": att, "attempts": [{"look": a["look"], "at": a["at"]} for a in attempts],
        "log": {"records": len(log), "head": log_heads[-1] if log_heads else GENESIS},
        "repairs": {"records": len(repairs), "files": dict(collections.Counter(r.get("file") for r in repairs)),
                    "list": [{k: r.get(k) for k in ("file", "offset", "kept_records", "dropped_bytes",
                                                    "dropped_sha256", "complete_record", "repaired_at", "seal",
                                                    "fingerprint")} for r in repairs],
                    "note": "each dropped an UNTERMINATED last line, a write that never completed and was never "
                            "part of a chain (repairs.jsonl holds the bytes); disclosed, not a check"}})
    return out


def _price_ref(sym):
    info = ew().RC.price_ref_info(ew().COST_PROFILE, sym)
    return {k: info[k] for k in ("price_ref", "n_bars", "closes_sha256", "window_utc")}


# ------------------------------------------------------------------------------------------------ fingerprint (WY-F1 §5)
_MON = getattr(sys, "monitoring", None)
_TRACE = {"active": None, "tool": None, "hook": False}


def _on_start(code, _offset):
    t = _TRACE["active"]
    if t is not None:
        t.saw(code)
    return _MON.DISABLE


def _audit(event, args):
    try:
        t = _TRACE["active"]
        if t is not None and event == "open" and args and isinstance(args[0], (str, bytes)):
            p = os.fsdecode(args[0])
            if os.path.isabs(p):                 # relative names are dir_fd opens (shutil.rmtree), not inputs
                t.opened.add(os.path.normpath(p))
    except Exception:  # noqa: BLE001 -- an audit hook must never break the open it observes
        pass


class Tracer:
    """What one process executes, loads and opens under a code root: module code objects (loaded), function code
    objects by phase ("import" until `run_phase`, then "run"), and files opened (audit hook). sys.monitoring PY_START
    reports each code object once per phase (DISABLE, then restart_events at the phase switch); sys.setprofile where
    sys.monitoring is missing. scripts/tests is never part of the forward path and is ignored. [WY-F1 §5]"""

    def __init__(self, root=CODE_ROOT):
        self.root = os.path.abspath(root) + os.sep
        self.phase = "import"
        self.exec = {"import": set(), "run": set()}
        self.modules, self.opened = set(), set()

    def _rel(self, path):
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    def saw(self, code):
        f = code.co_filename
        if not f.startswith(self.root):
            return
        rel = self._rel(f)
        if rel.startswith("scripts/tests/"):
            return
        if code.co_name == "<module>":
            self.modules.add(rel)
        elif code.co_flags & inspect.CO_NEWLOCALS:
            self.exec[self.phase].add(rel)

    def _prof(self, frame, event, _arg):
        if event == "call":
            self.saw(frame.f_code)

    def start(self):
        if not _TRACE["hook"]:
            sys.addaudithook(_audit)
            _TRACE["hook"] = True
        _TRACE["active"] = self
        if _MON is not None:
            if _TRACE["tool"] is None:
                for i in (_MON.PROFILER_ID, 3, 4):
                    if _MON.get_tool(i) is None:
                        _MON.use_tool_id(i, "wyckoff_forward")
                        _TRACE["tool"] = i
                        break
            if _TRACE["tool"] is None:
                raise SystemExit("refusing: no free sys.monitoring tool id for the code trace")
            _MON.register_callback(_TRACE["tool"], _MON.events.PY_START, _on_start)
            _MON.set_events(_TRACE["tool"], _MON.events.PY_START)
            _MON.restart_events()
        else:
            sys.setprofile(self._prof)
        return self

    def run_phase(self):
        self.phase = "run"
        if _MON is not None:
            _MON.restart_events()
        return self

    def stop(self):
        if _MON is not None and _TRACE["tool"] is not None:
            _MON.set_events(_TRACE["tool"], 0)
        else:
            sys.setprofile(None)
        _TRACE["active"] = None
        return self

    def touched(self):
        """(executed in the run phase, other code loaded, data opened): relative paths under the root. Opened data
        excludes Python files and caches and the runtime / live / record directories (inputs and outputs, hashed
        separately). [WY-F1 §5]"""
        skip = (RUNTIME + "/", LIVE_DIR + "/", REC_DIR + "/")
        run = set(self.exec["run"])
        code = (self.modules | self.exec["import"]) - run
        data = set()
        for p in self.opened:
            if not p.startswith(self.root):
                continue
            rel = self._rel(p)
            if rel.endswith((".py", ".pyc")) or "__pycache__" in rel or rel.startswith(skip):
                continue
            data.add(rel)
        return run, code, data


def _hashes(root, paths):
    return {p: (_sha256(os.path.join(root, p)) if os.path.isfile(os.path.join(root, p)) else None)
            for p in sorted(paths)}


def fp_digest(fp):
    """The fingerprint's identity, stamped on every record: sha256 over its file hashes, canary digest and time-zone
    pin. [WY-F1 §5]"""
    return hashlib.sha256(_canon({k: fp.get(k) for k in ("exec", "load", "data", "canary_sha256", "tz")}).encode()
                          ).hexdigest()


def _transitions(zone, years):
    """The UTC offset changes of `zone` from the start of years[0] to the end of years[1]: [{"utc": instant, "before":
    seconds, "after": seconds}], each instant to the second (a daily scan, then bisection; DST changes are months
    apart). [WY-F1 §5]"""
    def off(s):
        return int(datetime.datetime.fromtimestamp(s, UTC).astimezone(zone).utcoffset().total_seconds())
    s = int(datetime.datetime(years[0], 1, 1, tzinfo=UTC).timestamp())
    end = int(datetime.datetime(years[1] + 1, 1, 1, tzinfo=UTC).timestamp())
    out, cur = [], off(s)
    while s < end:
        n = min(s + 86400, end)
        o = off(n)
        if o != cur:
            lo, hi = s, n
            while hi - lo > 1:
                mid = (lo + hi) // 2
                lo, hi = (mid, hi) if off(mid) == cur else (lo, mid)
            out.append({"utc": _iso(datetime.datetime.fromtimestamp(hi, UTC)), "before": cur, "after": o})
            cur = o
        s = n
    return out


def tz_pin(years=TZ_PIN_YEARS):
    """The time-zone BEHAVIOUR this process computes, as the fingerprint pins it (WY-F1 §5; decision 2026-10-04, lead):
    America/New_York's DST instants in `years` (zoneinfo, from the OS time-zone database -- no tzdata package is in the
    extract) and the FTMO server zone's offset changes built on them (edge_wyckoff.series_zone("ftmo"): the zone of
    every server day, placebo slot and cost hour). Behaviour, not file bytes: a database update that leaves these
    instants alone changes nothing. [WY-F1 §5]"""
    import zoneinfo
    return {"years": list(years), TZ_PIN_ZONE: _transitions(zoneinfo.ZoneInfo(TZ_PIN_ZONE), years),
            "ftmo_server": _transitions(ew().series_zone("ftmo"), years)}


def require_tz(fp):
    """Inside a worker: this system computes the fingerprint's time-zone instants (`tz_pin`). Otherwise every cycle and
    look refuses -- server days, slots and cost hours would no longer be the sealed ones. [WY-F1 §5]"""
    pin = (fp or {}).get("tz")
    if not pin or not pin.get("years"):
        raise SystemExit("refusing: the fingerprint pins no time-zone behaviour (tz) [WY-F1 §5]")
    now = tz_pin(tuple(pin["years"]))
    for key in (TZ_PIN_ZONE, "ftmo_server"):
        if now.get(key) != pin.get(key):
            a, b = pin.get(key) or [], now.get(key) or []
            first = next((f"sealed {x} / now {y}" for x, y in itertools.zip_longest(a, b) if x != y), "")
            raise SystemExit(f"refusing: this system's time zone {key} computes other DST instants than the sealed "
                             f"fingerprint ({first}); server days, slots and cost hours would change [WY-F1 §5]")


def sealed_history_files(root=CODE_ROOT):
    """Every file of the symbols' 15m history under `root` (the warm-up and price_ref inputs), relative. [WY-F1 §5]"""
    out = []
    base = os.path.join(root, HIST_DIR)
    for sym in SYMBOLS:
        f = os.path.join(base, f"ohlcv.{sym}.{TF}.json")
        if os.path.isfile(f):
            out.append(f"{HIST_DIR}/ohlcv.{sym}.{TF}.json")
        d = os.path.join(base, f"ohlcv.{sym}.{TF}")
        if os.path.isdir(d):
            out += [f"{HIST_DIR}/ohlcv.{sym}.{TF}/{n}" for n in sorted(os.listdir(d))]
    return out


def verify_fingerprint(root=CODE_ROOT):
    """(fingerprint, digest): every file the fingerprint names has, under `root`, the sha256 it recorded. Refuses
    otherwise -- the extract (or the tree) is not the sealed code. [WY-F1 §5]"""
    fp = _read_json(os.path.join(root, FINGERPRINT))
    if not fp:
        raise SystemExit(f"refusing: {FINGERPRINT} is missing under {root}; WY-F1 has no sealed code fingerprint")
    bad = []
    for sect in ("exec", "load", "data"):
        for p, h in fp[sect].items():
            f = os.path.join(root, p)
            if not os.path.isfile(f) or _sha256(f) != h:
                bad.append(p)
    if bad:
        raise SystemExit(f"refusing: {len(bad)} fingerprinted file(s) differ from the sealed ones, first {bad[0]} "
                         f"[WY-F1 §5]")
    return fp, fp_digest(fp)


def require_committed_fingerprint(data_root, seal, root=CODE_ROOT):
    """The extract's fingerprint must be, byte for byte, the one the SEAL COMMIT holds (git is the trust root): an
    extract rebuilt with another fingerprint that matches its own files is refused. [WY-F1 §5]"""
    rc, blob = _git(data_root, "cat-file", "blob", f"{seal['sha']}:{FINGERPRINT}")
    with open(os.path.join(root, FINGERPRINT), "rb") as fh:
        mine = fh.read()
    if rc != 0 or blob != mine:
        raise SystemExit(f"refusing: the extract's {FINGERPRINT} is not the seal commit's [WY-F1 §5]")


def pinned_interpreter(fp):
    """The interpreter the fingerprint was made with: {"command", "realpath", "version", "minor"}. [WY-F1 §5]"""
    return fp.get("interpreter") or {}


def _minor(version):
    """"3.14" of "3.14.5". [WY-F1 §5]"""
    return ".".join(str(version).split(".")[:2])


def _command_version(cmd, timeout=30):
    """The Python version `cmd` runs (platform.python_version()), or None when it does not run. [WY-F1 §5]"""
    try:
        p = subprocess.run([cmd, "-c", "import platform; print(platform.python_version())"], capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return (p.stdout.strip() or None) if p.returncode == 0 else None


def stable_interpreter(command, version, minor):
    """Why `command` is NOT a stable, versioned interpreter to pin, or None. Pinned, a command must keep working through a
    patch upgrade (3.14.5 -> 3.14.6) and never turn into another minor version:
    - it is an absolute path;
    - it is named python<minor> (python3.14): `python3` follows whichever minor the package manager makes the default;
    - no part of it names a patch release (3.14.5) and none is Homebrew's Cellar: a patch upgrade deletes or re-points
      those (/opt/homebrew/Cellar/python@3.14/3.14.5/..., pyenv's versions/3.14.5/...).
    Homebrew's /opt/homebrew/opt/python@3.14/bin/python3.14 passes: brew keeps that link on 3.14 across patch upgrades.
    [WY-F1 §5]"""
    if not os.path.isabs(command):
        return f"{command} is not an absolute path"
    parts = command.replace("\\", "/").split("/")
    name = parts[-1][:-4] if parts[-1].lower().endswith(".exe") else parts[-1]
    if name != f"python{minor}":
        return (f"{command} is not named python{minor}: a name without the minor version (python3) follows the "
                f"package manager's default")
    m = re.search(r"(?<![\d.])\d+\.\d+\.\d+", command)
    if m:
        return f"{command} names the patch release {m.group(0)}: a patch upgrade deletes or re-points it"
    if "Cellar" in parts:
        return f"{command} lies in Homebrew's Cellar, which a patch upgrade deletes"
    return None


def interpreter_pin(require_stable=True):
    """The interpreter this process runs, as the fingerprint pins it: {"command" (sys.executable), "realpath", "version",
    "minor"}. With `require_stable` (the sealing fingerprint), the command must be stable and versioned
    (`stable_interpreter`) and must run this very Python, so every worker runs what the canary was traced with.
    [WY-F1 §5, §12 step 5]"""
    pin = {"command": sys.executable, "realpath": os.path.realpath(sys.executable),
           "version": platform.python_version(), "minor": "%d.%d" % sys.version_info[:2]}
    if require_stable:
        why = stable_interpreter(pin["command"], pin["version"], pin["minor"])
        if why:
            raise SystemExit(f"refusing to pin the interpreter: {why}. Run `fingerprint` with a stable versioned path, "
                             f"e.g. /opt/homebrew/opt/python@{pin['minor']}/bin/python{pin['minor']} [WY-F1 §5, §12]")
        now = _command_version(pin["command"])
        if now != pin["version"]:
            raise SystemExit(f"refusing to pin the interpreter: {pin['command']} runs Python {now}, this process runs "
                             f"{pin['version']} [WY-F1 §5]")
    return pin


def require_interpreter(fp):
    """Inside a worker: this process runs the fingerprint's Python minor version. A patch upgrade keeps collecting (the
    read's canary still refuses any numeric change); a minor change refuses every cycle, which the launcher records as
    a failure (`cmd_cycle`, `cmd_spawn`, `status`). [WY-F1 §5]"""
    pin = pinned_interpreter(fp)
    want = pin.get("minor")
    have = "%d.%d" % sys.version_info[:2]
    if want != have:
        raise SystemExit(f"refusing: this worker runs Python {have} ({platform.python_version()}), the fingerprint pins "
                         f"{want} ({pin.get('version')} at {pin.get('command')}); a patch upgrade keeps collecting, a "
                         f"minor change never does: reinstall Python {want} there [WY-F1 §5]")


def _interpreter(code_root):
    """The command the launcher runs a worker with: the fingerprint's pinned interpreter, never another Python.
    [WY-F1 §5]"""
    try:
        fp = _read_json(os.path.join(code_root, FINGERPRINT))
    except ValueError:
        raise SystemExit(f"refusing: {FINGERPRINT} in {code_root} is not readable JSON [WY-F1 §5]")
    pin = pinned_interpreter(fp or {})
    cmd = pin.get("command")
    if not cmd:
        raise SystemExit(f"refusing: {FINGERPRINT} pins no interpreter [WY-F1 §5]")
    if not os.path.exists(cmd):
        raise SystemExit(f"refusing: the pinned interpreter {cmd} (Python {pin.get('version')}) is missing; reinstall "
                         f"Python {pin.get('minor')} there -- WY-F1 never runs under another Python [WY-F1 §5]")
    return cmd


_R0_CODE = {}


def r0_code(root=CODE_ROOT):
    """(R0 meta code_sha256, R0 git_head) from this root's sealed re-test record. [WY-F1 §5]"""
    if "m" not in _R0_CODE:
        meta = _read_json(os.path.join(root, R0))["meta"]
        _R0_CODE["m"] = (meta["code_sha256"], meta["git_head"])
    return _R0_CODE["m"]


def r0_drift(root, paths):
    """The fingerprinted inputs that are NOT what the sealed re-test's R1 ran: a path R0's `code_sha256` names must have
    that sha256; any other (cost tables, broker_symbols, ...) must be the blob of R0's `git_head`. This file, the R0
    record and the 15m history (re-exported before sealing, WY-F1 §12) are exempt. Returns "path: why" lines.
    [WY-F1 §5, §7 "RT §5, unchanged"]"""
    code, head = r0_code(root)
    out = []
    for p in sorted(paths):
        if p in (SCRIPT, R0) or p.startswith(HIST_DIR + "/"):
            continue
        f = os.path.join(root, p)
        if p in code:
            if not os.path.isfile(f) or _sha256(f) != code[p]:
                out.append(f"{p}: differs from R0's code_sha256")
            continue
        rc, blob = _git(root, "rev-parse", "-q", "--verify", f"{head}:{p}")
        if rc != 0:
            out.append(f"{p}: not in R0's git_head {head[:12]} (or git cannot say)")
        elif not os.path.isfile(f) or git_blob_id(f) != blob.decode().strip():
            out.append(f"{p}: differs from R0's git_head {head[:12]}")
    return out


def check_touched(tr, fp):
    """After a traced run, before anything is written: every code file it executed or loaded and every data file it
    opened is one the fingerprint names (so its hash was verified). Returns the run-phase files executed outside the
    narrow `exec` set (verified, reported). [WY-F1 §5]"""
    run, code, data = tr.touched()
    named = set(fp["exec"]) | set(fp["load"]) | set(fp["data"])
    outside = sorted((run | code | data) - named)
    if outside:
        raise SystemExit(f"refusing: this run used {len(outside)} file(s) the sealed fingerprint does not name, first "
                         f"{outside[0]}; nothing was written [WY-F1 §5]")
    return sorted(run - set(fp["exec"]))


def check_outside(tr, data_root):
    """After a traced run, before anything is written: under the DATA root but outside this code root, the run opened
    only DATA_INPUTS (no other extract) and the sealed pre-registration, and no loaded module came from there (an
    inherited PYTHONPATH pointing at the live tree would run unsealed code the trace cannot see). [WY-F1 §5]"""
    droot = os.path.abspath(data_root) + os.sep
    bad = []

    def rel(p):
        return os.path.relpath(p, droot).replace(os.sep, "/")
    for p in sorted(tr.opened):
        if p.startswith(droot) and not p.startswith(tr.root):
            r = rel(p)
            if r != PREREG and (not r.startswith(DATA_INPUTS) or r.startswith(RUNTIME + "/code/")):
                bad.append(f"opened {r}")
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if isinstance(f, str):
            f = os.path.abspath(f)
            if f.startswith(droot) and not f.startswith(tr.root):
                bad.append(f"imported {rel(f)}")
    if bad:
        raise SystemExit(f"refusing: this run used {len(bad)} file(s) of the live tree outside the sealed extract, "
                         f"first {bad[0]}; nothing was written [WY-F1 §5]")


# ------------------------------------------------------------------------------------------------ canary (WY-F1 §5)
def _leg(a, b, n, vol=10.0):
    return [(a + (b - a) * i / n, max(a + (b - a) * i / n, a + (b - a) * (i + 1) / n) + 0.05,
             min(a + (b - a) * i / n, a + (b - a) * (i + 1) / n) - 0.05, a + (b - a) * (i + 1) / n, vol)
            for i in range(n)]


def _rising(n, a=100.0, b=104.0):
    out, p = [], a
    for i in range(n):
        q = a + (b - a) * (i + 1) / n + (0.3 if i % 2 else -0.3)
        out.append((p, max(p, q) + 0.1, min(p, q) - 0.1, q, 10.0))
        p = q
    return out


def canary_bars(i):
    """One synthetic 15m series: a rising zigzag (never a downtrend) of 2000 bars, one accumulation with a Spring that
    reclaims on its own bar (the shape of scripts/tests/test_edge_wyckoff.py scenario("spring")), its Phase D, a rising
    tail. Prices scaled by the symbol's index so the series differ. The 2000-bar prefix gives the HTF gate its FULL live
    1H window at every canary signal (about 520 hours; live_rules.read_at needs 480, automation.SCAN_WINDOW["1H"]), so
    the canary -- and with it the fingerprint and `extract_check` -- runs the gate's whole bias path. [WY-F1 §5, §6]"""
    b = _leg(104, 102, 5) + _leg(102, 99, 5) + _leg(99, 101, 5) + _leg(101, 97, 5) + _leg(97, 100, 5)
    b += _leg(100, 90, 5) + _leg(90, 96, 5) + _leg(96, 80, 5) + _leg(80, 110, 6) + _leg(110, 85, 6) + _leg(85, 108, 6)
    b += _leg(108, 88, 6) + _leg(88, 106, 6) + _leg(106, 90, 6) + _leg(90, 100, 6) + _leg(100, 92, 6)
    b += _leg(92, 82, 4) + [(82, 82.5, 78, 81, 20.0)] + _leg(81, 86, 3, vol=5.0) + _leg(86, 108, 6)
    b += [(108, 114, 107.5, 113.5, 30.0), (113.5, 114.5, 112, 114, 10.0), (114, 114.2, 111, 111.5, 5.0),
          (111.5, 115, 113.2, 114.8, 10.0)] + _leg(114.8, 118, 5)
    bars = _rising(CANARY_PREFIX) + b + _rising(400, 118, 122)
    off = 1.0 + 0.01 * i
    return [(o * off, h * off, lo * off, c * off, v) for (o, h, lo, c, v) in bars]


CANARY_PREFIX = 2000
CANARY_START, CANARY_SEAL_BAR, CANARY_HIST_END, CANARY_LIVE_FROM = "2026-06-01T00:00:00Z", 2050, 2300, 2200
#: The canary's two look cutoffs: the CLOSE of these store bars (a synthetic plan inside the canary's ~26 days; the
#: registered plan is `look_plan`, LOOK_MONTHS after the seal). Both need HZ stored bars after them, and the history
#: export (to bar CANARY_HIST_END - 2, taken at bar CANARY_HIST_END) must reach HZ bars after each, for the read's
#: history check and export rule.
CANARY_LOOK_BARS = (2100, 2200)


def canary_plan(seal=None):
    """The canary's look plan, in `look_plan`'s shape: [(cutoff, grace end None)] at the close of CANARY_LOOK_BARS.
    [WY-F1 §5]"""
    t0 = _utc(CANARY_START)
    return [(t0 + datetime.timedelta(minutes=MINUTES * (j + 1)), None) for j in CANARY_LOOK_BARS]


def canary_data(tmp):
    """Writes the canary's data root under `tmp`: per symbol a history export (file shape) ending at bar
    CANARY_HIST_END, `_exported_at_utc` that bar's open, and a live 15m file from bar CANARY_LIVE_FROM with the
    bridge's +1 s stamps. Returns the seal. [WY-F1 §5]"""
    import broker_symbols as BS
    t0 = _utc(CANARY_START)

    def t(j, jitter=0):
        return _iso(t0 + datetime.timedelta(minutes=MINUTES * j, seconds=jitter))
    for i, sym in enumerate(SYMBOLS):
        bars = canary_bars(i)
        cs = [{"time": t(j), "open": o, "high": h, "low": lo, "close": c, "volume": v}
              for j, (o, h, lo, c, v) in enumerate(bars)]
        _write_json(os.path.join(tmp, HIST_DIR, f"ohlcv.{sym}.{TF}.json"),
                    {"symbol": sym, "timeframe": TF, "_exported_at_utc": t(CANARY_HIST_END),
                     "candles": cs[:CANARY_HIST_END]})
        live = [dict(c, time=t(j, j % 2)) for j, c in enumerate(cs) if j >= CANARY_LIVE_FROM]
        _write_json(os.path.join(tmp, LIVE_DIR, f"ohlcv.{BS.to_broker(sym)}.{TF}.json"),
                    {"symbol": BS.to_broker(sym), "timeframe": TF, "candles": live})
    return {"sha": "canary", "instant": t(CANARY_SEAL_BAR)}


def canary_numerics():
    """The derived numbers the canary's own ten events cannot exercise (they share one ISO week, so CR1 has one cluster
    and no Student-t tail is computed): a FIXED statistic of 24 rows over 12 weeks through the registered summary
    (edge_wyckoff.summarise: CR1, `t_sf`, the 95 % bound) and both looks' boundaries at the planning counts. Pure
    arithmetic in, OS math functions inside: its digest part is rounded (`sig10`). [WY-F1 §5]"""
    E = ew()
    rows = []
    for i in range(24):
        r = ((i * 7) % 13 - 5) / 4.0
        plc = ((i * 5) % 7 - 3) / 10.0
        rows.append({"week": f"2027-W{10 + i // 2:02d}", "R": r, "placebo": plc, "excess": r - plc,
                     "cost": {"median_swap": 0.03, "median_noswap": 0.02, "p90_swap": 0.05, "p90_noswap": 0.04}})
    b1 = look1_boundary(PLAN_RATE)
    return {"summary": E.summarise(rows, E.FTMO_LINES), "look1": b1,
            "look2": look2_boundary(b1, PLAN_RATE + N_REST_PLAN, PLAN_RATE)}


def canary(tmp, cost_r=None):
    """Every forward step on synthetic bars, with the real detector, walk, HTF gate and cost: init, live append, scan,
    resolve (the log-only fields included), then the read core at both looks of `canary_plan` -- look 2 with look 1's
    result as its prior, so the export rule, the export replay and walks, the commitment check and both boundaries run.
    Returns (digest, {look: read result}, body). The body's EXACT part -- the log's records, each look's rows and label
    -- is hashed as it is; its DERIVED part -- each look's summary and boundary -- rounded to 10 significant digits
    (`split_sha256`); a look checks the sealed digest with `split_digests`, so a last-ulp change of the OS math library
    passes and any real numeric change refuses. Deterministic: wall clock fields are fixed, and the records' `python`
    stamp is left out, so a routine Python patch upgrade does not lock a look out. [WY-F1 §5]"""
    seal = canary_data(tmp)
    now = "2026-07-01T00:00:00Z"
    res = cycle_core(tmp, seal, "canary", now, init_root=tmp)
    commit(res["writes"])
    plan = canary_plan(seal)
    looks = {1: read_core(tmp, seal, "canary", look=1, plan=plan, cost_r=cost_r)}
    looks[2] = read_core(tmp, seal, "canary", look=2, plan=plan, prior=looks[1], cost_r=cost_r)
    log, _ = read_chain(_rt(tmp, "log.jsonl"))
    keep = ("id", "R", "outcome", "exit_time", "excess", "placebo", "n_placebo", "cost", "net_excess")
    body = {"exact": {"log": [{k: v for k, v in r.items() if k != "python"} for r in log],
                      "looks": {str(n): {"rows": [{k: r.get(k) for k in keep} for r in out["statistic"]["rows"]],
                                         "label": out["verdict"]["label"], "sample": out["sample"]}
                                for n, out in looks.items()}},
            "derived": {"looks": {str(n): {"summary": out["statistic"]["summary"], "boundary": out["boundary"]}
                                  for n, out in looks.items()},
                        "numerics": canary_numerics()}}
    body = _json(body)
    return split_sha256(body["exact"], body["derived"]), looks, body


def canary_verifies(fp, body):
    """Does a re-run canary `body` reproduce the fingerprint's sealed `canary_sha256` (`split_digests`)? [WY-F1 §5]"""
    return fp.get("canary_sha256") in split_digests(body["exact"], body["derived"])


# ------------------------------------------------------------------------------------------------ git, seal, extract
def _git(root, *args, timeout=120):
    try:
        p = subprocess.run(["git", "-C", root, *args], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None, b""


def seal_info(data_root=CODE_ROOT):
    """{"sha", "instant", "date"} of the commit that ADDED the sealed pre-registration, by its committer date (a rebase
    or cherry-pick keeps the author date, not this one); None when no commit adds it (not sealed). [WY-F1 §3]"""
    rc, out = _git(data_root, "log", "--diff-filter=A", "--format=%H %cI", "--", PREREG)
    lines = [x for x in out.decode().splitlines() if x.strip()] if rc == 0 else []
    if not lines:
        return None
    sha, ci = lines[-1].split()
    t = datetime.datetime.fromisoformat(ci)
    return {"sha": sha, "instant": _iso(t), "date": t.astimezone(UTC).date().isoformat()}


def _wanted(name):
    if name == HIST_DIR or name.startswith(HIST_DIR + "/"):
        return any(name == f"{HIST_DIR}/ohlcv.{s}.{TF}.json" or name.startswith(f"{HIST_DIR}/ohlcv.{s}.{TF}/")
                   for s in SYMBOLS)
    return any(name == r or name.startswith(r + "/") for r in SNAPSHOT_ROOTS)


def _extract(data_root, rev, dest, need_fingerprint=True):
    """`git archive` of `rev` (SNAPSHOT_ROOTS only) unpacked at `dest`; returns the file count. core.autocrlf is
    forced off: the extract holds the committed bytes, the ones the fingerprint hashed, on any checkout. [WY-F1 §5]"""
    rc, out = _git(data_root, "ls-tree", "-r", "-z", "--name-only", rev, "--", *SNAPSHOT_ROOTS)
    names = [n for n in out.decode().split("\0") if n and _wanted(n)] if rc == 0 else []
    if not names:
        raise SystemExit(f"refusing: cannot list commit {rev} (is git available?)")
    if need_fingerprint and FINGERPRINT not in names:
        raise SystemExit(f"refusing: the sealed commit {rev} has no {FINGERPRINT}")
    rc, tar = _git(data_root, "-c", "core.autocrlf=false", "archive", "--format=tar", rev, "--", *names, timeout=600)
    if rc != 0:
        raise SystemExit(f"refusing: git archive of {rev} failed")
    shutil.rmtree(dest, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(tar)) as tf:
        try:
            tf.extractall(dest, filter="data")
        except TypeError:
            tf.extractall(dest)
    return len(names)


def materialize(data_root, sha, fresh=False):
    """The read-only extract of commit `sha` (SNAPSHOT_ROOTS only) at data/live/forward/wyckoff-wc15/code/<sha>/,
    made once and reused; a half-made one is replaced. `fresh` (the read): rebuilt from git every time, at
    code/<sha>.read/, so no file a cycle could have touched since is used. [WY-F1 §5]"""
    dest = _rt(data_root, "code", sha + (".read" if fresh else ""))
    if not fresh and os.path.isfile(os.path.join(dest, ".complete")):
        return dest
    tmp = f"{dest}.tmp.{os.getpid()}"
    n = _extract(data_root, sha, tmp)
    _write_json(os.path.join(tmp, ".complete"), {"sha": sha, "files": n, "at": _now()})
    shutil.rmtree(dest, ignore_errors=True)
    os.replace(tmp, dest)
    return dest


def _worker_cmd(code_root, what, data_root, seal, *extra):
    """The fingerprint's pinned interpreter on the extract's own copy of this file: -E (no PYTHONPATH from the
    scheduler's environment), -s (no user site), -B (nothing written into the extract). [WY-F1 §5]"""
    return [_interpreter(code_root), "-B", "-E", "-s", os.path.join(code_root, SCRIPT), "_worker", what, "--data-root",
            os.path.abspath(data_root), "--seal-sha", seal["sha"], "--seal-instant", seal["instant"], *extra]


def extract_check(fp, root=CODE_ROOT, rev="HEAD", timeout=900):
    """BEFORE sealing: build the extract `materialize` will build, from `rev`, put the new fingerprint in it, and run
    the canary there BY ITSELF -- a fresh process, the fingerprint verified, the trace checks -- to the fingerprint's
    digest. A file the forward path needs but the extract would lack fails here, not at the first cycle after the
    seal. Returns the extract's file count. [WY-F1 §5, §12]"""
    with tempfile.TemporaryDirectory() as tmp:
        dest = os.path.join(tmp, "code")
        n = _extract(root, rev, dest, need_fingerprint=False)
        _write_json(os.path.join(dest, FINGERPRINT), fp)
        p = subprocess.run(_worker_cmd(dest, "canary", tmp, {"sha": "extract-check", "instant": _now()}),
                           capture_output=True, text=True, timeout=timeout)
        got = (p.stdout.strip().splitlines() or [""])[-1]
        if p.returncode != 0:
            raise SystemExit(f"refusing: the extract of {rev} cannot run the forward path by itself: "
                             + (p.stderr or p.stdout).strip()[-700:])
        if got != fp["canary_sha256"]:
            raise SystemExit(f"refusing: the canary in the extract of {rev} gives {got[:16]}, the working tree "
                             f"{fp['canary_sha256'][:16]}")
    return n


class Busy(SystemExit):
    """Another WY-F1 process holds the lock: a skip, not a failure."""


@contextlib.contextmanager
def _lock(data_root, name="worker.lock"):
    d = _rt(data_root)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) > LOCK_STALE_S:
        os.remove(p)
    try:
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Busy(f"WY-F1: another process holds {name}; skipped")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(p)


def _require_seal(data_root, seal, fp=None):
    """The seal passed in is the commit that adds the sealed file. With the fingerprint: that commit has ONE parent, the
    commit the fingerprint was taken at (`git_head`), and it adds exactly the sealed file and the fingerprint -- so the
    sealed code is the fingerprinted code and nothing rode in with the seal. [WY-F1 §3, §12]"""
    cur = seal_info(data_root)
    if cur is None or cur["sha"] != seal["sha"] or cur["instant"] != seal["instant"]:
        raise SystemExit(f"refusing: the seal passed in ({seal['sha'][:12]}) is not the commit that adds {PREREG}")
    if fp is None:
        return
    rc, out = _git(data_root, "rev-list", "--parents", "-n", "1", seal["sha"])
    parents = out.decode().split()[1:] if rc == 0 else None
    if parents != [fp.get("git_head")]:
        raise SystemExit(f"refusing: the seal commit's parent(s) {parents} are not the fingerprinted commit "
                         f"{fp.get('git_head')}; the seal is ONE commit on top of it [WY-F1 §12]")
    rc, out = _git(data_root, "diff-tree", "-r", "--no-commit-id", "--name-status", seal["sha"])
    got = sorted(tuple(x.split("\t", 1)) for x in out.decode().splitlines() if x.strip()) if rc == 0 else None
    if got != sorted([("A", FINGERPRINT), ("A", PREREG)]):
        raise SystemExit(f"refusing: the seal commit must add exactly {PREREG} and {FINGERPRINT}, got {got} "
                         f"[WY-F1 §12]")


def prereg_record(data_root, seal):
    """The sealed pre-registration as the read cites it: the sha256 of its text AT THE SEAL (git), of its committed text
    now, and every later commit that changed it (errata, disclosed). [WY-F1 §7]"""
    rc, blob = _git(data_root, "show", f"{seal['sha']}:{PREREG}")
    if rc != 0:
        raise SystemExit(f"refusing: git cannot show {PREREG} at the seal")
    rc2, now = _git(data_root, "show", f"HEAD:{PREREG}")
    rc3, later = _git(data_root, "log", "--format=%H", f"{seal['sha']}..HEAD", "--", PREREG)
    return {"sealed_sha256": hashlib.sha256(blob).hexdigest(),
            "head_sha256": hashlib.sha256(now).hexdigest() if rc2 == 0 else None,
            "changed_after_seal": [x for x in later.decode().split() if x] if rc3 == 0 else None}


# ------------------------------------------------------------------------------------------------ workers (sealed code)
def worker_cycle(data_root, seal, only=None):
    """In the sealed extract: trace, verify the fingerprint, the pinned Python and the time-zone instants, run one cycle
    in memory, check what it touched, then write. Prints a one-line JSON summary for scripts/forward_cycle.py's log
    (stalled and NOT ADVANCING symbols with their reasons). [WY-F1 §4, §5]"""
    tr = Tracer(CODE_ROOT).start()
    fp, digest = verify_fingerprint(CODE_ROOT)
    require_interpreter(fp)
    ew()
    tr.run_phase()
    require_tz(fp)
    with _lock(data_root):
        _require_seal(data_root, seal, fp)
        require_committed_fingerprint(data_root, seal)
        res = cycle_core(data_root, seal, digest, _now(), only=only)
        tr.stop()
        extra = check_touched(tr, fp)
        check_outside(tr, data_root)
        commit(res["writes"])
    s = res["summary"]
    s["notes"] = s["notes"][:3] + ([f"+{len(s['notes']) - 3} more"] if len(s["notes"]) > 3 else [])
    s["not_advancing"] = {k: v[:160] for k, v in s.get("not_advancing", {}).items()}     # `status` has them whole
    if extra:
        s["outside_exec"] = extra
    print(json.dumps(s, separators=(",", ":")))
    return s


def committed_record(data_root, rel):
    """A committed JSON record of the data root, read from git HEAD (never the working file, which must equal it):
    None when HEAD has none. [WY-F1 §7]"""
    rc, blob = _git(data_root, "show", f"HEAD:{rel}")
    if rc != 0:
        return None
    path = os.path.join(data_root, rel)
    rc, oid = _git(data_root, "rev-parse", "-q", "--verify", f"HEAD:{rel}")
    if not os.path.isfile(path) or git_blob_id(path) != oid.decode().strip():
        raise SystemExit(f"refusing: {rel} differs from its committed version [WY-F1 §7]")
    return json.loads(blob)


def require_prior(prior, seal, digest):
    """Look 2 runs on look 1's COMMITTED record only (`committed_record`), made under this seal and this fingerprint,
    and only when look 1 did not pass: a look-1 PASS is the verdict and ends WY-F1. [WY-F1 §7]"""
    if not prior:
        raise SystemExit(f"refusing: look 2 needs look 1's committed record {LOOK_OUT[1]} [WY-F1 §7]")
    meta, v = prior.get("meta") or {}, prior.get("verdict") or {}
    if prior.get("look") != 1 or meta.get("study") != STUDY:
        raise SystemExit(f"refusing: {LOOK_OUT[1]} is not WY-F1's look-1 record [WY-F1 §7]")
    if (meta.get("seal") or {}).get("sha") != seal["sha"] or meta.get("fingerprint_digest") != digest:
        raise SystemExit(f"refusing: {LOOK_OUT[1]} was made under another seal or code fingerprint [WY-F1 §5, §7]")
    if v.get("pass") or v.get("label") != "CONTINUE":
        raise SystemExit(f"refusing: look 1 is {v.get('label')!r}, not CONTINUE: a look-1 PASS ends WY-F1, there is no "
                         f"look 2 [WY-F1 §7]")
    return prior


def look_attempts(log, look=None):
    """The chained look-attempt records in the log: all of them, or those of `look` and later. [WY-F1 §7]"""
    return [r for r in log if r.get("kind") == "look_attempt" and (look is None or r.get("look", 0) >= look)]


def _attempted(a):
    return SystemExit(f"refusing: look {a.get('look')} was already attempted at {a.get('at')} (a chained look-attempt "
                      f"record in {RUNTIME}/log.jsonl): each look runs ONCE, even when its output file is gone "
                      f"[WY-F1 §7]")


def require_no_attempt(data_root, look):
    """Refuses when the log holds an attempt of this look or a later one (`look_attempts`). [WY-F1 §7]"""
    prev = look_attempts(read_chain(_rt(data_root, "log.jsonl"))[0], look)
    if prev:
        raise _attempted(prev[0])


def append_attempt(data_root, seal, fp_digest, look, rel, info, now):
    """The chained look-attempt record (WY-F1 §7; decision 2026-10-04, lead), appended to the log after every
    outcome-blind check passed and BEFORE any outcome is computed: what the look was decided on (`info`: cutoff, rule,
    symbols read and dropped, the exports' times), the output path, the seal, the fingerprint and the time. From then on
    the look is spent: a second attempt refuses (`require_no_attempt`), even if the first one's output file is deleted
    or it refused after computing an outcome. Returns the record with its chain hash. [WY-F1 §7]"""
    lp = _rt(data_root, "log.jsonl")
    log, heads = read_chain(lp)
    prev = look_attempts(log, look)
    if prev:
        raise _attempted(prev[0])
    rec = dict(info, kind="look_attempt", study=STUDY, look=look, out=rel, seal=seal["sha"], fingerprint=fp_digest,
               python=platform.python_version(), at=now)
    return dict(rec, ch=append_chain(lp, [rec], heads[-1] if heads else GENESIS))


def worker_read(data_root, seal, out, look=1):
    """In a FRESH extract of the seal (`cmd_read`): one look, ONCE, under every guard -- the sealed pre-registration
    committed and clean in the data root, its adding commit the seal, one commit on the fingerprinted one; the
    fingerprint the seal commit's, every file verified, the pinned Python, the time-zone instants, the canary re-run to
    its sealed digest (`canary_verifies`); the hour frame; the look's canonical --out path with no git history and no
    attempt of it (or a later look) in the log; for look 2, look 1's committed record (`require_prior`); the anchors from
    git -- then `read_core`, whose `attempt` hook re-checks the trace and appends the chained look-attempt record before
    the first outcome (`append_attempt`); the trace check again before writing. A look 1 that does not cross is written
    BLINDED (`blind`): no estimate and no resolve count leaves the worker, on disk or on screen. [WY-F1 §5, §7, §8]"""
    tr = Tracer(CODE_ROOT).start()
    fp, digest = verify_fingerprint(CODE_ROOT)
    require_interpreter(fp)
    E = ew()
    tr.run_phase()
    require_tz(fp)
    if look not in LOOK_OUT:
        raise SystemExit(f"refusing: WY-F1 has looks {sorted(LOOK_OUT)}, not {look!r} [WY-F1 §7]")
    rel = LOOK_OUT[look]
    want = os.path.join(data_root, rel)
    if os.path.abspath(out) != want:
        raise SystemExit(f"refusing: look {look} writes {rel} (got {out})")
    for later in [n for n in LOOK_OUT if n >= look]:
        p = LOOK_OUT[later]
        if os.path.exists(os.path.join(data_root, p)):
            raise SystemExit(f"{p} exists: each look is read ONCE [WY-F1 §7]")
        rc, log = _git(data_root, "log", "--all", "--format=%H", "--", p)
        if rc != 0 or log.strip():
            raise SystemExit(f"refusing: {p} has git history (or git cannot say) -- that look was already run")
    rc, st = _git(data_root, "status", "--porcelain", "--", PREREG)
    if rc != 0 or st.strip():
        raise SystemExit(f"refusing: {PREREG} has uncommitted changes")
    _require_seal(data_root, seal, fp)
    require_committed_fingerprint(data_root, seal)
    require_no_attempt(data_root, look)
    prior = require_prior(committed_record(data_root, LOOK_OUT[1]), seal, digest) if look == 2 else None
    prereg = prereg_record(data_root, seal)
    anchors = committed_anchors(data_root)
    E._require_hour_frame()
    with tempfile.TemporaryDirectory() as tmp:
        _cdig, _looks, body = canary(tmp)
    if not canary_verifies(fp, body):
        raise SystemExit("refusing: the canary no longer reproduces its sealed digest (Python or a sealed input "
                         "changed) [WY-F1 §5]")

    def attempt(info):
        check_touched(tr, fp)                   # what ran so far is fingerprinted: else refuse BEFORE the attempt
        check_outside(tr, data_root)
        return append_attempt(data_root, seal, digest, look, rel, info, _now())
    with _lock(data_root):
        res = read_core(data_root, seal, digest, look=look, prior=prior, price_ref=fp.get("price_ref"),
                        anchors=anchors, attempt=attempt)
        tr.stop()
        extra = check_touched(tr, fp)
        check_outside(tr, data_root)
        res["meta"] = {"study": STUDY, "cell": CELL, "script": SCRIPT, "preregistration": PREREG,
                       "preregistration_sha256": prereg["sealed_sha256"], "preregistration_git": prereg,
                       "seal": seal, "fingerprint": FINGERPRINT, "fingerprint_digest": digest,
                       "python": platform.python_version(), "interpreter": sys.executable, "read_at": _now(),
                       "look": look, "look_months": list(LOOK_MONTHS), "alpha": ALPHA,
                       "spending": "Lan-DeMets O'Brien-Fleming-type, alpha(t) = 2 (1 - Phi(z_{1-alpha/2} / sqrt(t)))",
                       "plan_rate": PLAN_RATE, "n_rest_plan": N_REST_PLAN, "grace_months": GRACE_MONTHS,
                       "drop_min_complete": DROP_MIN_COMPLETE, "never_due_months": NEVER_DUE_MONTHS,
                       "never_due": "procedural: the coordinator closes WY-F1 then; the code does not refuse a later look",
                       "numbers": {"sig_digits": SIG_DIGITS, "tie_rel": TIE_REL, "boundary_rel_tol": BOUNDARY_REL_TOL},
                       "tz": fp.get("tz", {}).get("years"), "outside_exec": extra,
                       "measurement": "sealed re-test §5: edge_wyckoff.score / summarise, FTMO cost lines"}
        rec = look_record(res)
        E._dump(rec, want)
    print(look_line(res) + f"\nwrote {want}")
    return rec


def look_record(res):
    """What a look writes (WY-F1 §7): a look 1 that did not cross, BLINDED (`blind`: no estimate, no p, no row); else
    the whole result, its scored rows moved to `rows` ({"W-C-long-15m@look<n>": rows}, one row per line in the file;
    look 2 adds look 1's, now disclosed). `statistic_sha256` was taken before the move, on the rows inside the
    statistic, so look 2's check reads the same bytes either way. [WY-F1 §7]"""
    look, v = res["look"], res["verdict"]
    if look == 1 and not v["crossed"]:
        return blind(res)
    rec = dict(res)
    rec["statistic"] = {k: x for k, x in res["statistic"].items() if k != "rows"}
    rec["rows"] = {f"{CELL}@look{look}": res["statistic"]["rows"]}
    if look == 2:
        l1 = dict(res["look1"])
        l1["statistic"] = {k: x for k, x in l1["statistic"].items() if k != "rows"}
        rec["look1"] = l1
        rec["rows"][f"{CELL}@look1"] = res["look1"]["statistic"]["rows"]
    return rec


def look_line(res):
    """The console line of a look: the decision facts, and the estimate only when the look is not blinded.
    [WY-F1 §7]"""
    look, v, b = res["look"], res["verdict"], res["boundary"]
    line = (f"WY-F1 {CELL} look {look}: {v['label']} (n {v['n']}, alpha spent {b['alpha_spent']:.5f}, nominal one-sided "
            f"p threshold {b['p_threshold']:.5f}; cutoff {res['cutoff']['cutoff']}, {res['cutoff']['rule']})")
    if look == 1 and not v["crossed"]:
        return line + f"\n  BLINDED: no estimate is shown or written; statistic_sha256 {res['statistic_sha256']}"
    return line + f"\n  net excess {v['net_excess']}, one-sided p {v['p_one_sided']}"


def worker_canary(data_root):
    """In an extract (`extract_check`, before sealing): the fingerprint, the pinned Python and the time-zone instants
    verified, the canary run under the trace and both trace checks; prints its digest. Synthetic bars only.
    [WY-F1 §5]"""
    tr = Tracer(CODE_ROOT).start()
    fp, _digest = verify_fingerprint(CODE_ROOT)
    require_interpreter(fp)
    ew()
    tr.run_phase()
    require_tz(fp)
    with tempfile.TemporaryDirectory() as tmp:
        cdig, _looks, _body = canary(tmp)
    tr.stop()
    check_touched(tr, fp)
    check_outside(tr, data_root)
    print(cdig)
    return cdig


# ------------------------------------------------------------------------------------------------ launcher commands
BUSY_RC = 75                # a worker that found the lock held exits with this (EX_TEMPFAIL): a skip, not a failure


def cmd_cycle(only=None, data_root=CODE_ROOT, timeout=WORKER_TIMEOUT_S):
    """One collection cycle (what `spawn` starts): nothing before the seal; after it, the worker in the sealed extract,
    in a fresh process under the pinned interpreter. Records the outcome in last_cycle.json and returns the worker's
    one-line summary. A checkout that lacks the seal while the stores exist is a FAILURE (collection would pause
    silently); another cycle still running is a skip. [WY-F1 §5, §12]"""
    last = _rt(data_root, "last_cycle.json")
    s = seal_info(data_root)
    if s is None:
        if os.path.isdir(_rt(data_root, "bars")) or os.path.exists(_rt(data_root, "log.jsonl")):
            err = (f"the stores exist but the checked-out branch has no commit adding {PREREG}: collection is PAUSED "
                   f"(check out the branch that holds the seal)")
            _write_json(last, {"at": _now(), "ok": False, "error": err})
            raise SystemExit(f"{STUDY}: {err}")
        return f"{STUDY} is not sealed ({PREREG} is not committed): nothing collected"
    try:
        with _lock(data_root, "launcher.lock"):
            try:
                code = materialize(data_root, s["sha"])
                p = subprocess.run(_worker_cmd(code, "cycle", data_root, s, *(["--only", only] if only else [])),
                                   capture_output=True, text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                err = (f"worker timed out after {timeout} s and was killed; lines it had appended whole stay, an "
                       f"unterminated last line is dropped by the next cycle ({REPAIRS})")
                _write_json(last, {"at": _now(), "ok": False, "error": err})
                raise SystemExit(f"{STUDY} {err}")
            except SystemExit as exc:
                _write_json(last, {"at": _now(), "ok": False, "error": str(exc)[-700:]})
                raise
    except Busy as exc:
        return f"{STUDY}: skipped ({exc})"
    if p.returncode == BUSY_RC:
        return f"{STUDY}: skipped (the worker lock is held)"
    if p.returncode != 0:
        err = (p.stderr or p.stdout).strip()[-700:]
        _write_json(last, {"at": _now(), "ok": False, "error": err})
        raise SystemExit(f"{STUDY} worker failed ({p.returncode}): " + err)
    line = (p.stdout.strip().splitlines() or [""])[-1]
    _write_json(last, {"at": _now(), "ok": True, "summary": line})
    return line


def cmd_spawn(data_root=CODE_ROOT, popen=subprocess.Popen):
    """What scripts/forward_cycle.py calls, AFTER the demo ticks: start `cycle` in a DETACHED process and return at once,
    so WY-F1 adds no time to the forward cycle and never delays the next cycle's ticks (CLAUDE.md §40; the cycle log
    shows launchd starting the next cycle about 300 s after the previous one ends). The child gets its own session
    (POSIX setsid; DETACHED_PROCESS on Windows), so launchd's end-of-job kill of the job's process group does not reach
    it; its output goes to spawn.log. If the PREVIOUS cycle failed, this raises after spawning, so the cycle log
    shows an EXIT line. [WY-F1 §12]"""
    os.makedirs(_rt(data_root), exist_ok=True)
    logp = _rt(data_root, "spawn.log")
    if os.path.exists(logp) and os.path.getsize(logp) > SPAWN_LOG_MAX:
        os.replace(logp, logp + ".1")
    cmd = [sys.executable, "-B", os.path.join(CODE_ROOT, SCRIPT), "cycle", "--background", "--data-root",
           os.path.abspath(data_root)]
    kw = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "cwd": os.path.abspath(data_root),
          "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    with open(logp, "a", encoding="utf-8") as fh:
        child = popen(cmd, stdout=fh, **kw)
    prev = None
    with contextlib.suppress(ValueError):
        prev = _read_json(_rt(data_root, "last_cycle.json"))
    if prev and not prev.get("ok"):
        raise SystemExit(f"{STUDY}: spawned pid {child.pid}; the previous cycle FAILED at {prev.get('at')}: "
                         f"{str(prev.get('error'))[:300]}")
    return f"{STUDY}: spawned pid {child.pid}"


def cmd_read(out, look, data_root=CODE_ROOT):
    """One look, in a FRESH extract of the seal (rebuilt from git, never the cycles' cached one), in a fresh process
    under the pinned interpreter. [WY-F1 §5, §7]"""
    s = seal_info(data_root)
    if s is None:
        raise SystemExit(f"refusing: {STUDY} is not sealed; nothing can be read")
    if look not in LOOK_OUT:
        raise SystemExit(f"refusing: WY-F1 has looks {sorted(LOOK_OUT)}, not {look!r} [WY-F1 §7]")
    code = materialize(data_root, s["sha"], fresh=True)
    return subprocess.run(_worker_cmd(code, "read", data_root, s, "--look", str(look),
                                      "--out", os.path.abspath(out))).returncode


class _Closes:
    """Only what `due` reads of a store: its bars' closes."""

    def __init__(self, bars):
        self.avail = [_utc(b["t"]) + datetime.timedelta(minutes=MINUTES) for b in bars]

    def __len__(self):
        return len(self.avail)


def status(data_root=CODE_ROOT, now=None):
    """Counts only, and none that times an exit -- never an R, an outcome, a mean, a resolve count or a log-only field
    (WY-F1 §6: a resolve a few bars after its entry is a stop or a target). Per symbol: the store, the live file (a
    missing or unusable one is STALLED, never an empty market), NOT ADVANCING (`accumulate_symbol`: the live file exists
    but the store takes no bar from it, or it is stale -- with the reason and the store's last bar), the bars the next
    cycle would add, the complete-through time, the revisions logged, the events, those kept (dense previous day),
    entered, and past their longest walk (entry + H bars stored), with `unresolved_past_walk` (0 when healthy). Each
    look's state from `due` itself; the counted events (entered, placeable at the entry open, dense previous day, ATR20
    known) by the common complete time, as the read counts; the never-due close (procedural); which look records exist
    and which looks were attempted. The pinned interpreter, the committed anchors, the last cycle, the repairs logged and
    pending (file names only: a torn line's bytes can hold an R), the working tree's drift from the sealed executed
    files. `now` (default: the wall clock) judges a stale live file. [WY-F1 §4, §6, §7, §12]"""
    E = ew()
    s = seal_info(data_root)
    HZ = horizon()
    now = now or _now()
    torn = {}
    log, log_heads = read_chain(_rt(data_root, "log.jsonl"), torn)
    ev = {r["id"]: r for r in log if r["kind"] == "event"}
    rs = {r["id"] for r in log if r["kind"] == "resolve"}
    revs = collections.Counter(r["symbol"] for r in log if r["kind"] == "revision")
    out = {"study": STUDY, "cell": CELL, "sealed": s, "symbols": {}, "log": {"events": len(ev),
           "head": log_heads[-1] if log_heads else None}}
    series, closes = {}, []
    for sym in SYMBOLS:
        bars, heads = read_chain(_rt(data_root, "bars", f"{sym}.{TF}.jsonl"), torn)
        series[sym] = _Closes(bars) if bars else None
        ct = complete_through(series[sym], HZ)
        mine = [r for r in ev.values() if r["symbol"] == sym]
        entered = [r for r in mine if r["store_index"] + 1 < len(bars)]
        past = [r for r in mine if r["store_index"] + 1 + HZ <= len(bars)]
        for r in entered:
            e = r["store_index"] + 1
            if r["prev_dense"] and (r["atr"] or 0) > 0 and E.placeable(SIDE, bars[e]["o"], r["stop"], r["target"]):
                closes.append(series[sym].avail[e])
        live, note = live_source(data_root, sym)
        acc = accumulate_symbol(sym, bars, data_root, CODE_ROOT, s, now, now) if bars else None
        out["symbols"][sym] = {"bars": len(bars), "last": bars[-1]["t"] if bars else None,
                               "src": dict(collections.Counter(b.get("src") for b in bars)),
                               "complete_through": _iso(ct) if ct else None, "stalled": live is None,
                               "live_last_closed": live[-1]["t"] if live else None, "live_note": note,
                               "not_advancing": acc["not_advancing"] if acc else None,
                               "next_cycle_adds": len(acc["add"]) if acc else None, "revisions": revs.get(sym, 0),
                               "events": len(mine), "kept": sum(1 for r in mine if r["prev_dense"]),
                               "entered": len(entered), "past_walk": len(past),
                               "unresolved_past_walk": sum(1 for r in past if r["id"] not in rs),
                               "head": heads[-1] if heads else None}
    out["stalled"] = [sym for sym, v in out["symbols"].items() if v["stalled"]]
    out["not_advancing"] = {sym: v["not_advancing"] for sym, v in out["symbols"].items() if v["not_advancing"]}
    out["revisions"] = sum(revs.values())
    if s:
        plan = look_plan(s["instant"])
        looks = {str(n): due(series, s["instant"], HZ, n, plan) for n in (1, 2)}
        common = [complete_through(S, HZ) for S in series.values()]
        common = min(common) if common and all(c is not None for c in common) else None
        recs = {str(n): os.path.exists(os.path.join(data_root, p)) for n, p in LOOK_OUT.items()}
        tried = {str(a["look"]): a["at"] for a in look_attempts(log)}
        nxt = next((n for n in ("1", "2") if not recs[n]), None)
        out["rule"] = {"looks": {n: dict(r, due=r["cutoff"] is not None) for n, r in looks.items()},
                       "records": recs, "attempted": tried, "next_look": nxt,
                       "read_due": nxt is not None and nxt not in tried and looks[nxt]["cutoff"] is not None,
                       "spent_without_record": [n for n in tried if not recs.get(n)],
                       "counted_events": sum(1 for c in closes if common is not None and c <= common),
                       "common_complete_through": _iso(common) if common else None,
                       "never_due_close": _iso(add_months(_utc(s["instant"]), NEVER_DUE_MONTHS))}
    else:
        out["rule"] = {"read_due": False, "note": "not sealed"}
    out["last_cycle"] = _read_json(_rt(data_root, "last_cycle.json"))
    rep, _rh = read_chain(_rt(data_root, REPAIRS), torn)
    out["repairs"] = {"logged": len(rep),
                      "last": {"at": rep[-1].get("repaired_at"), "file": rep[-1].get("file")} if rep else None,
                      "pending": sorted(os.path.relpath(p, _rt(data_root)).replace(os.sep, "/") for p in torn)}
    try:
        anc = committed_anchors(data_root) if s else []
        out["anchors"] = {"committed": len(anc), "last_committed": max((a["committed"] for a in anc), default=None)}
    except SystemExit as exc:
        out["anchors"] = {"error": str(exc)}
    fp = _read_json(os.path.join(data_root, FINGERPRINT))
    if fp:
        out["fingerprint_digest"] = fp_digest(fp)
        out["working_tree_drift"] = sorted(p for p, h in fp["exec"].items()
                                           if not os.path.isfile(os.path.join(data_root, p))
                                           or _sha256(os.path.join(data_root, p)) != h)
        pin = pinned_interpreter(fp)
        cur = _command_version(pin["command"]) if pin.get("command") and os.path.exists(pin["command"]) else None
        out["interpreter"] = dict(pin, now=cur, ok=bool(cur) and _minor(cur) == pin.get("minor"))
    return out


def _print_status(st):
    s = st["sealed"]
    print(f"{STUDY} {CELL}: " + (f"sealed {s['sha'][:12]} at {s['instant']}" if s else "NOT sealed (no collection)"))
    for sym, v in st["symbols"].items():
        print(f"  {sym:7s} bars {v['bars']:6d} last {v['last']} complete-through {v['complete_through']} | events "
              f"{v['events']} (kept {v['kept']}, entered {v['entered']}, past walk {v['past_walk']}"
              + (f", UNRESOLVED past walk {v['unresolved_past_walk']}" if v["unresolved_past_walk"] else "") + ")"
              + (f" | revisions {v['revisions']}" if v.get("revisions") else "")
              + (f" | {v['live_note']}" if v["live_note"] else ""))
    if st.get("stalled"):
        print(f"  STALLED (no usable live 15m file; nothing appended, never read as an empty market): "
              f"{', '.join(st['stalled'])}")
    for sym, why in (st.get("not_advancing") or {}).items():
        print(f"  NOT ADVANCING {sym}: {why}")
    r = st["rule"]
    if s:
        print(f"  counted events {r['counted_events']} by the common complete time {r['common_complete_through']}; "
              f"never-due close {r['never_due_close']} (procedural: the coordinator closes WY-F1 then)")
        for n, lk in r["looks"].items():
            print(f"  look {n}: cutoff {lk['t_cutoff']} (first export all 10 symbols after it + 96 bars and run one "
                  f"cycle; a symbol still incomplete is dropped once another is complete through {lk['grace_cutoff']} "
                  f"and at least {lk['min_complete']} are complete); due {lk['due']}"
                  + (f" -- {lk['rule']}" if lk["due"] else "")
                  + (f"; ATTEMPTED {r['attempted'][n]}" if n in r.get("attempted", {}) else "")
                  + ("; record written" if r["records"].get(n) else ""))
        for n in r.get("spent_without_record") or []:
            print(f"  ** look {n} was attempted without a record on disk: it never runs again (WY-F1 §7) **")
    lc = st.get("last_cycle")
    if lc:
        print(f"  last cycle {lc['at']}: " + ("ok" if lc["ok"] else f"FAILED -- {lc.get('error', '')[:300]}"))
    rp = st.get("repairs") or {}
    if rp.get("logged") or rp.get("pending"):
        last = rp.get("last") or {}
        print(f"  repairs: {rp.get('logged', 0)} unterminated last line(s) dropped and logged"
              + (f" (last {last.get('at')} in {last.get('file')})" if last else "")
              + (f"; pending, dropped by the next cycle: {', '.join(rp['pending'])}" if rp.get("pending") else ""))
    if st.get("revisions"):
        print(f"  revisions: {st['revisions']} bar(s) a source showed at another price after the store took them "
              f"(the store keeps them as first stored; each look lists them)")
    a = st.get("anchors") or {}
    if s:
        print("  anchors: " + (a["error"] if "error" in a else f"{a['committed']} committed, last {a['last_committed']}"))
    ip = st.get("interpreter")
    if ip:
        print(f"  interpreter: {ip.get('command')} pinned {ip.get('version')}, now {ip.get('now')}"
              + ("" if ip["ok"] else "  ** NOT the pinned minor version or missing: cycles will refuse **"))
    if st.get("working_tree_drift"):
        print("  working tree differs from the sealed executed files (the forward stage keeps the sealed ones): "
              + ", ".join(st["working_tree_drift"]))


def cmd_anchor(data_root=CODE_ROOT):
    """Append the chains' current lengths and heads to docs/experiments/wyckoff-forward-wc15/anchors.jsonl. Committed,
    each line pins the history before it; the read checks every one. Under the file's lock, the file must end with a
    newline and hold anchor records only (`anchor_lines`): a new line never joins a torn one, and a committed line that
    is not a record refuses every read. The line is fsynced. Commit the file only after this printed the line.
    [WY-F1 §4, §8, §12]"""
    log, lh = read_chain(_rt(data_root, "log.jsonl"))
    line = {"at": _now(), "study": STUDY, "log": {"n": len(log), "head": lh[-1] if lh else None}, "bars": {}}
    for sym in SYMBOLS:
        bars, heads = read_chain(_rt(data_root, "bars", f"{sym}.{TF}.jsonl"))
        line["bars"][sym] = {"n": len(bars), "head": heads[-1] if heads else None, "last": bars[-1]["t"] if bars
                             else None}
    p = os.path.join(data_root, ANCHORS)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "ab") as fh:
        if not _flock(fh):
            raise SystemExit(f"refusing: another writer holds {ANCHORS}; nothing appended [WY-F1 §8]")
        if _torn(p) is not None:
            raise SystemExit(f"refusing: {ANCHORS} ends with an unterminated line (a write that never completed); "
                             f"nothing appended. Remove that partial line, or end it with a newline if it is a whole "
                             f"record, then anchor again [WY-F1 §4, §8]")
        with open(p, "rb") as cur:
            anchor_lines(cur.read(), "the working file")
        fh.write((_canon(line) + "\n").encode())
        fh.flush()
        os.fsync(fh.fileno())
    return line


def git_blob_id(path):
    """git's object id of a file's bytes as they are (sha1 of "blob <size>\\0" + bytes): no filter, no eol conversion."""
    with open(path, "rb") as fh:
        data = fh.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _require_clean(root, paths, rev="HEAD"):
    """Every path is committed at `rev` and its bytes on disk ARE the committed blob -- so the extract of a later
    commit that keeps them holds the hashed bytes. Stricter than `git status`: a checkout with core.autocrlf on shows
    clean while its bytes differ from the blob (docs/plans/2026-09-20-windows-migration.md §5). [WY-F1 §5]"""
    rc, out = _git(root, "ls-tree", "-r", "-z", rev, "--", *sorted(paths))
    if rc != 0:
        raise SystemExit(f"refusing: cannot list {rev} (is git available?)")
    blob = {}
    for ent in out.decode().split("\0"):
        if "\t" in ent:
            meta, name = ent.split("\t", 1)
            blob[name] = meta.split()[2]
    bad = []
    for p in sorted(paths):
        if p not in blob:
            bad.append(f"{p}: not committed at {rev}")
        elif git_blob_id(os.path.join(root, p)) != blob[p]:
            bad.append(f"{p}: bytes differ from {rev} (uncommitted change, or core.autocrlf)")
    if bad:
        raise SystemExit("refusing: the fingerprint is taken on committed files only: " + "; ".join(bad[:6]))


def cmd_fingerprint(out, require_clean=True, cost_r=None):
    """BEFORE sealing, from the working tree: trace the canary through every forward step and record what it executes
    (run phase: `exec`, the narrow set), what else it loads (`load`), what it opens (`data`, plus every file of the
    symbols' sealed 15m history), real_costs' price_ref per symbol, the canary's digest (`canary`: exact part hashed as
    it is, derived floats rounded), the time-zone instants (`tz_pin`) and the interpreter (pinned: every worker runs
    it). Refuses unless every recorded file is inside SNAPSHOT_ROOTS and is what the sealed re-test's R1 ran
    (`r0_drift`), and, with `require_clean` (the sealing run), tracked and clean, and the interpreter stable and
    versioned (`interpreter_pin`, checked first). Run it with that path: /opt/homebrew/opt/python@3.14/bin/python3.14.
    [WY-F1 §5, §12 step 5]"""
    import zoneinfo
    if os.path.exists(out):
        raise SystemExit(f"{out} exists; refusing to overwrite a fingerprint")
    if require_clean and os.path.abspath(out) != os.path.join(CODE_ROOT, FINGERPRINT):
        raise SystemExit(f"refusing: the fingerprint is written to {FINGERPRINT}")
    pin = interpreter_pin(require_stable=require_clean)
    tr = Tracer(CODE_ROOT).start()
    ew()
    tr.run_phase()
    with tempfile.TemporaryDirectory() as tmp:
        digest, looks, body = canary(tmp, cost_r=cost_r)
    tz = tz_pin()
    pref = {s: _price_ref(s) for s in SYMBOLS} if cost_r is None else None
    tr.stop()
    gates = collections.Counter(str(r.get("htf_gate")) for r in body["exact"]["log"] if r.get("kind") == "resolve")
    run, code, data = tr.touched()
    data |= set(sealed_history_files(CODE_ROOT)) | {R0}         # inputs a warm process may have cached
    files = run | code | data
    outside = sorted(f for f in files if not _wanted(f))
    if outside:
        raise SystemExit(f"refusing: {outside[0]} is used but lies outside SNAPSHOT_ROOTS (the extract would miss it)")
    drift = r0_drift(CODE_ROOT, files)
    if drift:
        raise SystemExit(f"refusing: {len(drift)} fingerprinted input(s) are not what the sealed re-test ran, first "
                         f"{drift[0]} -- the read would not be 'RT §5, unchanged' [WY-F1 §5, §7]")
    if require_clean:
        _require_clean(CODE_ROOT, files)
    rc, head = _git(CODE_ROOT, "rev-parse", "HEAD")
    fp = {"study": STUDY, "created": _now(), "git_head": head.decode().strip() if rc == 0 else None,
          "python": platform.python_version(), "interpreter": pin,
          "exec": _hashes(CODE_ROOT, run), "load": _hashes(CODE_ROOT, code),
          "data": _hashes(CODE_ROOT, data), "price_ref": pref, "canary_sha256": digest, "tz": tz,
          "tz_source": {"tzpath": list(zoneinfo.TZPATH), "note": "disclosed, not checked: the pin is the behaviour"},
          "canary": {"events": looks[1]["replay"]["events"],
                     "rows": {str(n): x["statistic"]["summary"].get("n", 0) for n, x in looks.items()},
                     "htf_gate": dict(gates)},
          "r0_pinned": sorted(f for f in files if f not in (SCRIPT, R0) and not f.startswith(HIST_DIR + "/")),
          "snapshot_roots": list(SNAPSHOT_ROOTS)}
    fp["digest"] = fp_digest(fp)
    if require_clean:
        fp["extract_check"] = {"rev": head.decode().strip() if rc == 0 else None,
                               "files": extract_check(fp, CODE_ROOT, "HEAD"), "canary_sha256": digest}
    _write_json(out, fp)
    print(f"fingerprint: {len(fp['exec'])} executed, {len(fp['load'])} loaded, {len(fp['data'])} data files; canary "
          f"{fp['canary']['events']} events; digest {fp['digest'][:16]}; wrote {out}")
    return fp


# ------------------------------------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spawn")
    c = sub.add_parser("cycle")
    c.add_argument("--only", choices=("accumulate", "scan", "resolve"))
    c.add_argument("--data-root", default=CODE_ROOT)
    c.add_argument("--background", action="store_true")      # started by `spawn`: lower CPU priority
    st = sub.add_parser("status")
    st.add_argument("--json", action="store_true")
    sub.add_parser("anchor")
    r = sub.add_parser("read")
    r.add_argument("--look", type=int, required=True, choices=sorted(LOOK_OUT))
    r.add_argument("--out", required=True)
    f = sub.add_parser("fingerprint")
    f.add_argument("--out", required=True)
    w = sub.add_parser("_worker")                      # internal: runs inside the sealed extract
    w.add_argument("what", choices=("cycle", "read", "canary"))
    w.add_argument("--data-root", required=True)
    w.add_argument("--seal-sha", required=True)
    w.add_argument("--seal-instant", required=True)
    w.add_argument("--only", choices=("accumulate", "scan", "resolve"))
    w.add_argument("--look", type=int, choices=sorted(LOOK_OUT))
    w.add_argument("--out")
    a = ap.parse_args(argv)
    if a.cmd == "spawn":
        print(cmd_spawn())
    elif a.cmd == "cycle":
        if a.background and hasattr(os, "nice"):
            with contextlib.suppress(OSError):
                os.nice(10)
        print(f"{_now()} " + cmd_cycle(a.only, data_root=a.data_root), flush=True)
    elif a.cmd == "status":
        s = status()
        print(json.dumps(s, indent=1)) if a.json else _print_status(s)
    elif a.cmd == "anchor":
        print(json.dumps(cmd_anchor()))
    elif a.cmd == "read":
        return cmd_read(a.out, a.look)
    elif a.cmd == "fingerprint":
        cmd_fingerprint(a.out)
    else:
        seal = {"sha": a.seal_sha, "instant": a.seal_instant}
        try:
            if a.what == "cycle":
                worker_cycle(a.data_root, seal, a.only)
            elif a.what == "canary":
                worker_canary(a.data_root)
            else:
                worker_read(a.data_root, seal, a.out, a.look)
        except Busy as exc:
            print(exc, file=sys.stderr)
            return BUSY_RC
    return 0


if __name__ == "__main__":
    sys.exit(main())
