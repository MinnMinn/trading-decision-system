#!/usr/bin/env python3
"""WY-X1: a pre-registered HISTORICAL replication, discovery grade, of the sealed Wyckoff re-test's W-C-long-15m cell (the
Phase-C Spring / Shakeout long, docs/plans/2026-10-04-wyckoff-retest-preregistration.md §3.2), UNCHANGED, on FTMO symbols
that no committed read has ever scored for it. Discovery grade, not confirmation: the pool's bars are UNREAD-FOR-H, "valid
as discovery" (docs/plans/2026-10-04-research-directions.md §0); only forward or FRESH bars confirm. Pre-registration
(DRAFT until sealed): docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md ("WY-X1 §n" below).

    python3 scripts/research/wyckoff_wcx.py manifest                 # the code-sha256 lines the sealed text must carry
    python3 scripts/research/wyckoff_wcx.py counts --out <X0 json>   # OUTCOME-BLIND: events, symbol-years, overlap, power
    python3 scripts/research/wyckoff_wcx.py read --counts docs/experiments/wyckoff-wcx/wyckoff-wcx-X0.json \
        --out docs/experiments/wyckoff-wcx/wyckoff-wcx-X1.json        # ONCE, only after the seal (prereg_guard)
    python3 scripts/research/wyckoff_wcx.py report --counts <X0 json> [--read <X1 json>] --out <md>

What is reused, never copied or modified (WY-X1 §4, §5): the detector DET-PO and every measurement function of
scripts/research/edge_wyckoff.py (EW below), imported from the file as committed: `BASE_CFG`, `det_params`,
`detect_series`, `kept`, `placeable`, `score`, `walk_opts`, `summarise`, `probe`, `dense_table`, `Pricer`. W-C-long reads
no higher timeframe (RT §3.2: its event, stop and target are the 15m structure's own), so none is built here.

`counts` reads no outcome: no walk, no exit, no exit-dependent cost, no R. It reads each event's entry OPEN (the fill
price, known at the entry) to apply RT §3.2's placeability skip and the planned R:R, exactly as the re-test's R0 did (EW
`count_series`), and prices the spread at the ENTRY hour (a cost known at the entry). `read` refuses BEFORE any market data
is loaded unless the SEALED text exists, is committed, carries [WY-X1], "Status: SEALED" and a code manifest matching the
files (scripts/research/prereg_guard.py), the ledger registers the study, the code and cost trees are clean, the counts
record is committed and pinned by its sha256 in the sealed text, every R0-pinned file (EW CODE without its tests) is
byte-identical to what the re-test's R1 ran (R0 `meta.code_sha256`), and the cost tables and EXTRA_CODE are the R0
commit's blobs. It then refuses on a bar or a price reference that differs from the counts record's. It runs once and
never overwrites.

Read-only on repository data. PAPER research: it places no order and reads no account."""
import argparse
import collections
import datetime
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


EW = _load("edge_wyckoff", "scripts/research/edge_wyckoff.py")      # the sealed re-test's code, unmodified
G = _load("prereg_guard", "scripts/research/prereg_guard.py")
EC = EW.EC
RC = EW.RC
UTC = datetime.timezone.utc

# ------------------------------------------------------------------------------------------------ the registered design
STUDY, TAG = "WY-X1", "[WY-X1]"
PREREG_DRAFT = "docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md"
PREREG = "docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration.md"     # the SEALED name: `read` refuses without it
SCRIPT = "scripts/research/wyckoff_wcx.py"
TESTS_FILE = "scripts/tests/test_wyckoff_wcx.py"
GUARD = "scripts/research/prereg_guard.py"
R0_PATH = "docs/experiments/wyckoff-retest-r0/edge-wyckoff-R0.json"           # the re-test's outcome-blind counts
R1_PATH = "docs/experiments/wyckoff-retest-2026-10-04/edge-wyckoff-R1.json"   # committed; only signal times are read
REC_DIR = "docs/experiments/wyckoff-wcx"
X0_OUT = REC_DIR + "/wyckoff-wcx-X0.json"
X1_OUT = REC_DIR + "/wyckoff-wcx-X1.json"
#: WY-X1 §10, §11 step 6: the read refuses unless the ledger (committed, clean) holds this entry naming PREREG.
LEDGER = "docs/architecture/research-ledger.json"
LEDGER_KEY = "wyckoff_wcx_replication"
#: As EW `_require_clean_trees` (EW.CLEAN_TREES): no edited, staged or untracked file under the code, config and cost trees.
CLEAN_TREES = tuple(EW.CLEAN_TREES)
#: WY-X1 §11 step 5: the sealed text pins the counts record by content, one line exactly as `x0_line` prints it.
X0_LINE = re.compile(r"(?m)^x0-sha256 ([0-9a-f]{64}) (\S+)[ \t]*$")
#: EW's CODE minus test files: what an EW measurement executes or opens (the scripts and configs the re-test froze). Its
#: tests run nothing in a read; one of them was edited after every re-test read (docs/audits/2026-10-04-wyckoff-retest.md,
#: test-file note), as the WY-F1 fingerprint also leaves tests out.
R0_PINNED = tuple(p for p in EW.CODE if not p.startswith("scripts/tests/"))
#: Files the read executes that EW CODE does not list: scripts/htf_context.py loads method_purity.py by file location at
#: import (htf_context.py:48), outside sys.modules, so neither EW `_loaded_code` nor a trace started after the import sees
#: it (test `test_a_traced_read_path_executes_only_code_files`). Pinned like WY-F1's (WY-F1 §5): the sealed manifest, and
#: the blob of R0's `meta.git_head` (`blob_drift`).
EXTRA_CODE = ("scripts/method_purity.py",)
#: Every file whose content can change a WY-X1 read: this script, its tests, the guard, R0_PINNED and EXTRA_CODE. A read
#: refuses if one of them differs from the sealed manifest, if an R0_PINNED file differs from what R0 recorded, and if an
#: EXTRA_CODE file differs from its blob at R0's commit.
CODE = (SCRIPT, TESTS_FILE, GUARD) + R0_PINNED + EXTRA_CODE

CELL, TF, LEG, SIDE = "W-C-long-15m", "15m", "W-C", "long"
CFG = dict(EW.BASE_CFG)                       # DET-PO exactly as RT §3.1 (no perturbation)
#: WY-X1 §3: the replication pool. RT §4's replication symbols (EW.REPLICATION) that have a 15m dense start under RT §4's
#: rule (R0 `dense`). Fixed by the exposure grading and the outcome-blind counts, never by an outcome.
POOL = ("XPTUSD", "XPDUSD", "US2000", "UK100", "JP225")
#: Counted for the owner's decision only (WY-X1 §3, §13): EU50 / HK50 have no 15m dense start under RT §4 (a session cut in
#: 2025-01 fails the share), N25 / SPN35 were excluded by RT §4 on data quality. None joins the pool without an owner
#: decision recorded BEFORE sealing.
OPTIONAL = ("EU50", "HK50", "N25", "SPN35")
#: The re-test's tradeable symbols: EXPOSED for W-C-long before 2024-03-01 (R1 read it) and PARTLY EXPOSED after (the
#: engine's Wyckoff legs were read there; RT §4 R3 = veto only). Counted for rates, the R0 cross-check and the overlap
#: disclosure only; never in the pool.
EXPOSED = tuple(EW.TRADEABLE)
#: RT §4's R2 clusters (EW.REPLICATION), with the two optional European indices placed in EU if the owner adds them.
#: Reported only (WY-X1 §6): at about 10 events a cluster, "every evaluable cluster positive" has little power.
CLUSTER_OF = dict({s: c for c, syms in EW.REPLICATION.items() for s in syms}, N25="EU", SPN35="EU")
#: WY-X1 §6 breadth gate = RT §6.2 item 3 (EW.r1_verdicts): metals and indices each >= EW.BREADTH_MIN events, each with a
#: mean > 0 on the decision line.
GROUP_OF = {s: ("metals" if c == "metals" else "indices") for s, c in CLUSTER_OF.items()}
#: WY-X1 §3: the read's window is every dense bar of the series (from its RT §4 dense start) up to WINDOW_END; the series
#: is cut there, as RT cut R1 / R2 at their end (EW run_w: until = hi). A fixed instant, not "the end of the data", so a
#: later history re-export cannot change the sample. Saturday 00:00 UTC: after every symbol's Friday close.
WINDOW_END = "2026-09-26T00:00:00Z"
WINDOW = (None, WINDOW_END)
DEV_CUTOFF = EW.DEV_CUTOFF                    # reporting split only (pre / post 2024-03-01)
#: WY-X1 §6: one pre-registered hypothesis (the unchanged cell); Holm over the registered list (m = 1 today).
HYPOTHESES = (CELL,)
ALPHA = 0.10                                  # one-sided (WY-X1 §6; owner decision §13 item 3: 0.10 or 0.05)
AGAINST_P = EW.AGAINST_P
DELTA = EW.DELTA
LINES = EW.FTMO_LINES
PRIMARY = LINES[0]                            # median spread, today's swap (RT §6.1)
#: RT §5's placebo excess BEFORE cost ("excess = R_event - mean(R_placebo), both gross"), carried as a zero-cost line so
#: EW.summarise computes it exactly as it computes the four net lines.
GROSS = "gross"
#: WY-X1 §6 (owner decision §13 item 2): the decision statistic. "gross" = the placebo excess (does the Spring / Shakeout
#: predict the move?), registered, because the PGMs' spread (X0: about 0.9R a trade on XPTUSD / XPDUSD, against R1's
#: realised 0.09R) would decide a net test before any effect could. "net" = RT's H-WC statistic (median spread, today's
#: swap, and net > 0 on all four cost lines). Either way all five lines are reported.
DECISION = "gross"
#: WY-X1 §7 planning SDs of the excess per event on THIS pool (mean planned R:R 4.23 in X0): 2.2R (WY-F1 §9's upper value;
#: RT §8's rule sqrt(mean planned R:R) gives 2.06R here) and 2.8R (that rule times R1's measured ratio: SD 2.09R at a mean
#: planned R:R of 2.39, 1.35 x sqrt(2.39)). RT §8's 1.4R belongs to a planned R:R near 1.9, not to this pool.
SD_PLAN = (2.2, 2.8)
EFFECTS = (0.25, 0.35, 0.50)                  # 0.35 = R1's own mean gross excess (R1 tests["W-C-long-15m"])
PROBE_N = EW.PROBE_N
CORR_FROM = "2021-09-01T00:00:00Z"            # the indices' common dense 15m era (R0): daily-return correlation window
CORR_PAIRS = {"XPTUSD": ("XAUUSD", "XAGUSD", "XPDUSD"), "XPDUSD": ("XAUUSD", "XAGUSD"),
              "US2000": ("US500", "US30", "USTEC"), "UK100": ("DE40", "FRA40", "EU50"), "JP225": ("AUS200", "US500"),
              "EU50": ("DE40", "FRA40"), "HK50": ("AUS200", "JP225"), "N25": ("DE40", "EU50"), "SPN35": ("DE40", "EU50")}
OUTCOME_KEYS = ("R", "exit", "exit_time", "outcome", "excess", "net_excess", "cost", "placebo", "mfe", "mae")
#: Informational only (WY-X1 §3, §13 item 4): EU50, HK50 and FRA40 lost their RT §4 15m dense start because FTMO cut
#: their sessions in 2025-01 (92 -> 56 / 64 bars a day; R0 `dense[...].months`), so every later month fails 0.8 x the
#: 2023 median. The same rule with the LAST complete calendar year as the reference (EW.dense_start(..., ref_year=2025))
#: is counted beside it. It is not the registered rule; adopting it is an owner decision before sealing.
ALT_REF_YEAR = 2025
ALT_SYMBOLS = ("EU50", "HK50", "FRA40")
#: WY-X1 §13 item 4 (owner, before sealing): symbols that JOIN the pool with the ALT_REF_YEAR dense start. () = RT §4's
#: rule only (registered default); ("EU50", "HK50") = option B. FRA40 can never join (EXPOSED symbol).
ALT_POOL = ()


def pool_symbols():
    """The registered pool: POOL, then ALT_POOL (WY-X1 §3, §13 item 4)."""
    return tuple(POOL) + tuple(ALT_POOL)


# ------------------------------------------------------------------------------------------------ small helpers
def _utc(t):
    return datetime.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(UTC)


def _sha256(path):
    return G.file_sha256(path)


def _rel(path, root=ROOT):
    return os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace(os.sep, "/")


def _git(*args):
    try:
        p = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, timeout=60)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return None, b""


def _dump(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=str)
        fh.write("\n")


def window_digest(candles, end=WINDOW_END, tf=TF):
    """sha256 over (time, open, high, low, close) of every bar whose CLOSE is at or before `end`: the read's data pin. It is
    taken on a Series' bars (`S.src`: from the RT §4 dense start), in X0 and again in the read. A later export that only
    APPENDS bars keeps it; a revised bar inside the window changes it.
    [WY-X1 §3: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    lim = _utc(end)
    bar = datetime.timedelta(minutes={"15m": 15, "1H": 60, "1D": 1440}[tf])
    h, n = hashlib.sha256(), 0
    for c in candles:
        if _utc(c["time"]) + bar > lim:
            break
        h.update(f"{c['time']}|{c['open']!r}|{c['high']!r}|{c['low']!r}|{c['close']!r}\n".encode())
        n += 1
    return {"sha256": h.hexdigest(), "bars": n, "end": end}


# ------------------------------------------------------------------------------------------------ detection (counts only)
def detect(S):
    """DET-PO events of one 15m series (EW.detect_series, unmodified; no higher timeframe: W-C-long reads none).
    [WY-X1 §4: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return EW.detect_series(S, CFG, EW.det_params(CFG), EW.engine().P[TF]["sob"], None)


def event_facts(S, ev, cost_r=None):
    """The OUTCOME-BLIND facts of one W-C-long event: its signal time, ISO week, server day and type; whether the server
    day before its signal was dense; its entry time; whether its entry open lies strictly between the stop and the target
    (RT §3.2 skip) and the planned R:R there. Reads the entry OPEN (the fill price), nothing after it. With `cost_r`
    (real_costs.cost_r), also the spread round trip priced at the ENTRY hour with no night held, in R of the planned stop
    (`spread_r_entry`, median and p90): a cost known at the entry (real_costs.mean_spread_r's convention: "a COST figure,
    not a result"), never the trade's own exit-dependent cost.
    [WY-X1 §2, §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    k, e = ev["k"], ev["e"]
    f = {"symbol": S.sym, "signal_time": S.T[k], "week": EW.week_of(S.dt[k]), "server_day": S.sday[k].isoformat(),
         "type": ev["type"], "prev_dense": bool(S.prev_dense[k]), "entry_time": S.T[e] if e < len(S) else None,
         "placeable": None, "planned_rr": None}
    if e < len(S):
        entry = S.O[e]
        ok = EW.placeable(SIDE, entry, ev["stop"], ev["target"])
        f["placeable"] = bool(ok)
        if ok:
            f["planned_rr"] = (ev["target"] - entry) / (entry - ev["stop"])
            if cost_r is not None:
                f["spread_r_entry"] = {st: cost_r(entry, ev["stop"], S.T[e], S.T[e], S.sym, SIDE, EW.COST_PROFILE,
                                                  st)["spread_R"] for st in ("median", "p90")}
    return f


def in_window(S, ev, lo, hi):
    """The event's ENTRY bar lies in (lo, hi) (EW.Series.in_window: open >= lo, close <= hi) -- RT's read membership.
    [WY-X1 §3: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return ev["e"] < len(S) and S.in_window(ev["e"], lo, hi)


def tally(facts):
    """{signals, kept, placeable, skips, by_type, by_year} over the events of one window (RT R0's counting rule).
    [WY-X1 §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    out = {"signals": len(facts), "kept": 0, "placeable": 0, "skips": collections.Counter(),
           "by_type": collections.Counter(), "by_year": collections.Counter()}
    for f in facts:
        if not f["prev_dense"]:
            out["skips"]["previous_server_day_not_dense"] += 1
            continue
        out["kept"] += 1
        if not f["placeable"]:
            out["skips"]["entry_beyond_stop_or_target"] += 1
            continue
        out["placeable"] += 1
        out["by_type"][f["type"]] += 1
        out["by_year"][f["entry_time"][:4]] += 1
    return {k: (dict(v) if isinstance(v, collections.Counter) else v) for k, v in out.items()}


def years_between(start_date, last_time, end=WINDOW_END):
    """Calendar years from a dense start (date) to min(last bar, end): the symbol-years a rate divides by."""
    if start_date is None or last_time is None:
        return 0.0
    a = datetime.datetime.combine(datetime.date.fromisoformat(start_date), datetime.time(), UTC)
    b = min(_utc(last_time), _utc(end))
    return max(0.0, (b - a).total_seconds() / (365.25 * 86400))


def count_symbol(sym, loader, dense, exposed=False, cost_r=None):
    """One symbol: the series cut nowhere (as R0), DET-PO events, and the outcome-blind tallies of the WY-X1 window and of
    the re-test's own windows (R1 / R2 before 2024-03-01, R3 after) for the R0 cross-check; the event facts kept for the
    overlap and the probe. Returns (summary, facts in the WY-X1 window, the raw W-C events in it).
    [WY-X1 §2, §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    S = EW.make_series(sym, TF, loader, dense, CFG, "ftmo")
    ent = dense.get(f"{sym}|{TF}") or {}
    if S is None:
        return {"symbol": sym, "dense_start": ent.get("start"), "bars": 0, "why": "no dense start or no bars",
                "window": tally([]), "years": 0.0}, [], []
    evs = [ev for ev in detect(S)[LEG] if ev["side"] == SIDE]
    rows = {}
    for name, (lo, hi) in (("window", WINDOW), ("pre", (None, DEV_CUTOFF)), ("post", (DEV_CUTOFF, WINDOW_END)),
                           ("rt_post", (DEV_CUTOFF, None))):
        rows[name] = [(ev, event_facts(S, ev, cost_r if name == "window" else None)) for ev in evs
                      if in_window(S, ev, lo, hi)]
    yrs = years_between(ent.get("start"), S.T[-1])
    yrs_pre = years_between(ent.get("start"), min(S.T[-1], DEV_CUTOFF), DEV_CUTOFF)
    out = {"symbol": sym, "group": "exposed" if exposed else CLUSTER_OF.get(sym), "dense_start": ent.get("start"),
           "bars": len(S), "first": S.T[0], "last": S.T[-1], "years": yrs, "years_pre": yrs_pre,
           "years_post": max(0.0, yrs - yrs_pre),
           "window": tally([f for _e, f in rows["window"]]), "pre": tally([f for _e, f in rows["pre"]]),
           "post": tally([f for _e, f in rows["post"]]), "rt_post": tally([f for _e, f in rows["rt_post"]]),
           "data": window_digest(S.src)}
    n = out["window"]["placeable"]
    out["rate_per_year"] = n / yrs if yrs else None
    out["rate_per_year_post"] = out["post"]["placeable"] / out["years_post"] if out["years_post"] else None
    ok = [f for _e, f in rows["window"] if f["prev_dense"] and f["placeable"]]
    out["planned_rr"] = EW._rr_quantiles([f["planned_rr"] for f in ok])
    out["spread_r_entry"] = {st: EW._rr_quantiles([f["spread_r_entry"][st] for f in ok if f.get("spread_r_entry")])
                             for st in ("median", "p90")}
    win = [f for _e, f in rows["window"]]
    wevs = [ev for ev, _f in rows["window"]]
    return out, win, wevs


# ------------------------------------------------------------------------------------------------ disclosure helpers
def exposed_times(r1_rows, tradeable_post_facts, zone):
    """(weeks, server days) holding a W-C-long-15m event on an EXPOSED symbol: R1's committed rows (signal times only) and
    the tradeable symbols' counted events from 2024-03-01 (no outcome read).
    [WY-X1 §2 "information overlap": docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    weeks, days = set(), set()
    for t in [r["signal_time"] for r in r1_rows] + [f["signal_time"] for f in tradeable_post_facts]:
        d = _utc(t)
        weeks.add(EW.week_of(d))
        days.add(d.astimezone(zone).date().isoformat())
    return weeks, days


def overlap(facts, weeks, days):
    """Of the placeable, kept events: how many share an ISO week / a server day with an exposed-symbol event.
    [WY-X1 §2: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    ev = [f for f in facts if f["prev_dense"] and f["placeable"]]
    w = sum(1 for f in ev if f["week"] in weeks)
    d = sum(1 for f in ev if f["server_day"] in days)
    return {"n": len(ev), "same_week": w, "same_server_day": d, "share_same_week": w / len(ev) if ev else None,
            "share_same_server_day": d / len(ev) if ev else None}


def daily_corr(loader, a, b, frm=CORR_FROM, end=WINDOW_END, min_days=30):
    """Pearson correlation of daily close-to-close log returns of two FTMO symbols over their common 1D bars in [frm, end)
    (a market statistic, not a trade outcome: it says nothing about a Spring's result). None without enough common days.
    [WY-X1 §2 "partial information overlap": docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    def closes(sym):
        c, _ = loader(sym, "1D")
        return {x["time"]: x["close"] for x in c if frm <= x["time"] < end}
    ca, cb = closes(a), closes(b)
    common = sorted(set(ca) & set(cb))
    ra, rb = [], []
    for t0, t1 in zip(common, common[1:]):
        if min(ca[t0], ca[t1], cb[t0], cb[t1]) > 0:
            ra.append(math.log(ca[t1] / ca[t0]))
            rb.append(math.log(cb[t1] / cb[t0]))
    if len(ra) < min_days:
        return {"n_days": len(ra), "corr": None}
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    sa = math.sqrt(sum((x - ma) ** 2 for x in ra))
    sb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    return {"n_days": len(ra), "corr": cov / (sa * sb) if sa and sb else None}


# ------------------------------------------------------------------------------------------------ power (no outcome)
def mde_t(n, sd, alpha, power=0.80, df=None):
    """Minimum detectable mean (R) at `power`, one-sided `alpha`, Student-t with df (default n - 1): (t_{1-a} + t_{power}) x
    SD / sqrt(n) -- WY-F1 §9's formula. None when df < 1.
    [WY-X1 §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    df = n - 1 if df is None else df
    if n <= 1 or df < 1:
        return None
    return (EW.t_quantile(1 - alpha, df) + EW.t_quantile(power, df)) * sd / math.sqrt(n)


def power_t(n, sd, effect, alpha, df=None):
    """P(one-sided t-test rejects) if the true mean is `effect`: P(T_df > t_{1-a} - effect sqrt(n) / SD) (shifted central t,
    WY-F1 §9's approximation). [WY-X1 §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    df = n - 1 if df is None else df
    if n <= 1 or df < 1:
        return None
    return EC.t_sf(EW.t_quantile(1 - alpha, df) - effect * math.sqrt(n) / sd, df)


def design_effect(facts):
    """n_eff = n^2 / sum over ISO weeks of n_w^2: the effective count if events of one week were fully correlated (a
    conservative bound; CR1 by week is what the read uses). [WY-X1 §7]"""
    w = collections.Counter(f["week"] for f in facts)
    s = sum(v * v for v in w.values())
    n = sum(w.values())
    return {"n": n, "weeks": len(w), "n_eff_week_bound": (n * n / s) if s else 0.0}


def power_table(n, weeks, n_eff=None, alphas=(0.05, 0.10)):
    """{alpha: {sd: {mde, power at each EFFECTS}}} for the pool's n (df = weeks - 1, the CR1 df), and the same at the
    conservative n_eff. [WY-X1 §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    out = {}
    for label, nn in (("n", n), ("n_eff_week_bound", n_eff)):
        if not nn:
            continue
        df = max(1, min(weeks, int(round(nn))) - 1)
        out[label] = {str(a): {str(sd): {"mde_80": mde_t(nn, sd, a, df=df),
                                         **{f"power_at_{e:+.2f}": power_t(nn, sd, e, a, df=df) for e in EFFECTS}}
                               for sd in SD_PLAN} for a in alphas}
        out[label]["n"] = nn
        out[label]["df"] = df
    return out


def pass_power(n_metals, n_indices, sd, effect, alpha, sims=20000, seed=20261004, effect_indices=None):
    """Approximate P(significant) and P(REPLICATED) when the true mean on the decision line is `effect` (metals; the
    indices' is `effect_indices`, default the same): group means drawn N(effect_g, SD^2 / n_g), the pooled mean against
    the t_{1-alpha, n-1} bound at a known SD, and the breadth gate (both groups >= EW.BREADTH_MIN events and > 0). The net
    design's extra gate (all four cost lines > 0) is not modelled. Fixed seed.
    [WY-X1 §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    n = n_metals + n_indices
    if min(n_metals, n_indices) < 1 or n < 3:
        return {"significant": None, "replicated": None}
    ei = effect if effect_indices is None else effect_indices
    rnd = random.Random(seed)
    tc = EW.t_quantile(1 - alpha, n - 1)
    meet = min(n_metals, n_indices) >= EW.BREADTH_MIN
    sig = rep = 0
    for _ in range(sims):
        mm = rnd.gauss(effect, sd / math.sqrt(n_metals))
        mi = rnd.gauss(ei, sd / math.sqrt(n_indices))
        s = (n_metals * mm + n_indices * mi) / n / (sd / math.sqrt(n)) > tc
        sig += s
        rep += s and meet and mm > 0 and mi > 0
    return {"significant": sig / sims, "replicated": rep / sims}


def _mean_or_zero(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _phi(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p):
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def bvn_cdf(a, b, rho, steps=4000):
    """P(Z1 <= a, Z2 <= b) for a standard bivariate normal with correlation rho (Simpson on the conditional form)."""
    lo = -9.0
    if a <= lo:
        return 0.0
    s = math.sqrt(1.0 - rho * rho)
    h = (a - lo) / steps
    tot = 0.0
    for i in range(steps + 1):
        x = lo + i * h
        f = math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi) * _phi((b - rho * x) / s)
        tot += f * (1 if i in (0, steps) else (4 if i % 2 else 2))
    return tot * h / 3.0


def obf_spend(t, alpha):
    """Lan-DeMets O'Brien-Fleming-type spending, one-sided level alpha: alpha(t) = 2 (1 - Phi(z_{1-alpha/2} / sqrt(t))).
    [WY-X1 §12 (proposal for WY-F1): docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return 2.0 * (1.0 - _phi(_phi_inv(1.0 - alpha / 2.0) / math.sqrt(t)))


def two_look(t1, alpha):
    """(c1, c2, alpha spent at look 1): z boundaries of a two-look one-sided design at information fraction t1 (look 2 at
    t = 1), OBF-type spending, P0(Z1 >= c1 or Z2 >= c2) = alpha with corr(Z1, Z2) = sqrt(t1).
    [WY-X1 §12: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    a1 = obf_spend(t1, alpha)
    c1 = _phi_inv(1.0 - a1)
    rho = math.sqrt(t1)
    lo, hi = -5.0, 8.0
    for _ in range(100):                                   # P0(Z1 < c1, Z2 < c2) = 1 - alpha
        mid = 0.5 * (lo + hi)
        if bvn_cdf(c1, mid, rho) < 1.0 - alpha:
            lo = mid
        else:
            hi = mid
    return c1, 0.5 * (lo + hi), a1


def two_look_power(n1, n2, sd, effect, c1, c2):
    """P(Z1 >= c1 or Z2 >= c2) when the true mean is `effect` (z statistics with drift effect sqrt(n_k) / SD).
    [WY-X1 §12: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    m1, m2 = effect * math.sqrt(n1) / sd, effect * math.sqrt(n2) / sd
    rho = math.sqrt(n1 / n2)
    return 1.0 - bvn_cdf(c1 - m1, c2 - m2, rho)


# ------------------------------------------------------------------------------------------------ the R0 cross-check
def r0_crosscheck(r0, per_symbol, dense):
    """X0 must reproduce the sealed re-test's R0 where both count the same thing: the 15m dense starts, and the
    W-C-long-15m placeable events by symbol in R1 (tradeable, before 2024-03-01), R2 (replication, before 2024-03-01) and
    R3 (tradeable, from 2024-03-01). Any difference is listed (an empty list = the detector and the data are R0's).
    [WY-X1 §4 "DET-PO, unmodified": docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    diff = []
    for key, ent in dense.items():
        old = (r0.get("dense") or {}).get(key)
        if old is not None and old.get("start") != ent.get("start"):
            diff.append(f"dense {key}: R0 {old.get('start')} != {ent.get('start')}")
    reads = r0.get("reads") or {}
    for read, syms, part in (("R1", EXPOSED, "pre"), ("R3", EXPOSED, "rt_post"),
                             ("R2", [s for c in EW.REPLICATION.values() for s in c], "pre")):
        want = ((reads.get(read) or {}).get(CELL) or {}).get("by_symbol") or {}
        for sym in syms:
            if sym not in per_symbol:
                continue
            got = per_symbol[sym].get(part, {}).get("placeable", 0)
            if got != want.get(sym, 0):
                diff.append(f"{read} {sym}: R0 {want.get(sym, 0)} != {got}")
    return diff


def r0_drift(r0, root=ROOT):
    """R0_PINNED files (EW CODE without tests) whose bytes differ from what R0 recorded (meta.code_sha256): non-empty = the
    measurement is no longer the re-test's.
    [WY-X1 §5 "RT §5, unchanged": docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    want = (r0.get("meta") or {}).get("code_sha256") or {}
    bad = []
    for p in R0_PINNED:
        full = os.path.join(root, p)
        got = _sha256(full) if os.path.exists(full) else None
        if got != want.get(p):
            bad.append(p)
    return bad


def cost_files(symbols):
    """The cost tables a read opens for `symbols` (repo-relative): the profile's symbol map and each symbolspec."""
    prof = RC.PROFILES[EW.COST_PROFILE]
    out = [_rel(prof["symbol_map"])] if prof.get("symbol_map") else []
    return out + [_rel(RC.spec_path(EW.COST_PROFILE, s)) for s in symbols]


def blob_drift(paths, r0, git=_git, root=ROOT):
    """Repo-relative `paths` whose bytes on disk differ from their blob at R0's commit (meta.git_head), or that git cannot
    show there: the files the re-test's measurement used without fingerprinting them.
    [WY-X1 §5 "Pins": docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    head = (r0.get("meta") or {}).get("git_head")
    bad = []
    for p in paths:
        rc, blob = git("show", f"{head}:{p}") if head else (None, b"")
        full = os.path.join(root, p)
        if not os.path.exists(full):
            bad.append(p)
            continue
        with open(full, "rb") as fh:
            cur = fh.read()
        if rc != 0 or hashlib.sha256(blob).digest() != hashlib.sha256(cur).digest():
            bad.append(p)
    return bad


def cost_drift(symbols, r0, git=_git, root=ROOT):
    """Cost tables that differ from their blob at R0's commit (meta.git_head): RT §5 priced with exactly these files.
    [WY-X1 §5: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return blob_drift(cost_files(symbols), r0, git, root)


# ------------------------------------------------------------------------------------------------ X0: counts (no outcome)
def alt_dense_entry(loader, sym, zone):
    """RT §4's dense START with the last complete calendar year (ALT_REF_YEAR) as the reference, without the month table.
    [WY-X1 §3, §13 item 4: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    candles, _prov = loader(sym, TF)
    dts = [_utc(c["time"]) for c in candles]
    ent = EW.dense_start([d.astimezone(zone).date() for d in dts], dts, ref_year=ALT_REF_YEAR) if dts else {}
    return {k: v for k, v in ent.items() if k != "months"}


def counts(out_path, loader=EW.load_ftmo, pool=None, optional=OPTIONAL, exposed=EXPOSED, r0=None, r1_rows=None,
           probe_n=PROBE_N, corr=True, dense=None, cost_r=RC.cost_r, alt_pool=None, price_ref=RC.price_ref_info):
    """X0 (WY-X1 §2, §3, §7): OUTCOME-BLIND. The 15m dense table (EW.dense_table, RT §4's rule; `dense` is for synthetic
    tests only, the CLI always computes it); per symbol the DET-PO W-C-long-15m events of the WY-X1 window (and of the
    re-test's windows, for the R0 cross-check), by period, type and year, the symbol-years and the rate; the overlap with
    exposed-symbol events; daily-return correlations with the exposed symbols; the point-in-time truncation probe; the
    power table; and each pool symbol's real_costs price reference (`price_ref`; None skips it, synthetic tests only), which
    the read pins. ALT_POOL symbols are counted with the ALT_REF_YEAR dense start. No walk, exit, exit-dependent cost or
    return is computed. Refuses before any data unless real_costs prices in RT §5's hour frame (EW.HOUR_FRAME).
    [WY-X1 §2, §3, §5, §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    if os.path.exists(out_path):
        raise SystemExit(f"{out_path} exists; refusing to overwrite a counts record")
    if RC.HOUR_FRAME != EW.HOUR_FRAME:
        raise SystemExit(f"refusing: real_costs.HOUR_FRAME is {RC.HOUR_FRAME!r}; the entry-hour spread proxy and RT §5 "
                         f"need {EW.HOUR_FRAME!r}")
    alt_pool = tuple(ALT_POOL if alt_pool is None else alt_pool)
    pool = pool_symbols() if pool is None else tuple(pool) + tuple(s for s in alt_pool if s not in pool)
    optional, exposed = tuple(s for s in optional if s not in pool), tuple(exposed)
    if set(alt_pool) & set(exposed):
        raise SystemExit("an EXPOSED symbol can never join the pool (WY-X1 §3)")
    syms = list(dict.fromkeys(pool + optional + exposed))
    dense = EW.dense_table([(s, TF) for s in syms], loader, "ftmo") if dense is None else dense
    zone = EW.series_zone("ftmo")
    dense_alt_pool = {f"{s}|{TF}": alt_dense_entry(loader, s, zone) for s in alt_pool}
    per, facts, events = {}, {}, {}
    for s in syms:
        d = dense_alt_pool if s in alt_pool else dense
        summ, f, evs = count_symbol(s, loader, d, exposed=s in exposed, cost_r=cost_r)
        summ["dense_rule"] = f"ref_year {ALT_REF_YEAR} (ALT_POOL)" if s in alt_pool else "RT §4 (ref_year 2023)"
        per[s], facts[s], events[s] = summ, f, evs
        print(f"X0 {s}: {summ['window']['placeable']} W-C-long-15m events in the window", flush=True)
    trad_post = [f for s in exposed for f in facts[s] if f["entry_time"] and f["entry_time"] >= DEV_CUTOFF]
    weeks, days = exposed_times(r1_rows or [], trad_post, zone)
    pool_f = [f for s in pool for f in facts[s] if f["prev_dense"] and f["placeable"]]
    opt_f = [f for s in optional for f in facts[s] if f["prev_dense"] and f["placeable"]]
    rec = {"meta": meta("counts"), "dense": dense, "dense_alt_pool": dense_alt_pool, "symbols": per,
           "events": {s: [f for f in facts[s] if f["prev_dense"] and f["placeable"]] for s in pool + optional},
           "overlap": {"pool": overlap(pool_f, weeks, days), "optional": overlap(opt_f, weeks, days),
                       "by_symbol": {s: overlap(facts[s], weeks, days) for s in list(pool) + list(optional)},
                       "exposed_weeks": sorted(weeks), "exposed_server_days": sorted(days),
                       "r1_events": len(r1_rows or []), "tradeable_post_events": len(trad_post)}}
    pool_n = len(pool_f)
    de = design_effect(pool_f)
    rec["pool"] = {"symbols": list(pool), "placeable": pool_n, "weeks": de["weeks"],
                   "n_eff_week_bound": de["n_eff_week_bound"],
                   "by_cluster": dict(collections.Counter(CLUSTER_OF.get(f["symbol"]) for f in pool_f)),
                   "by_type": dict(collections.Counter(f["type"] for f in pool_f)),
                   "pre": sum((per[s].get("pre") or {}).get("placeable", 0) for s in pool),
                   "post": sum((per[s].get("post") or {}).get("placeable", 0) for s in pool),
                   "symbol_years": sum(per[s].get("years", 0.0) for s in pool),
                   "planned_rr": EW._rr_quantiles([f["planned_rr"] for f in pool_f]),
                   "spread_r_entry_median": EW._rr_quantiles([f["spread_r_entry"]["median"] for f in pool_f
                                                              if f.get("spread_r_entry")])}
    rec["power"] = {"pool": power_table(pool_n, de["weeks"], de["n_eff_week_bound"]),
                    "pool_plus_optional": power_table(pool_n + len(opt_f),
                                                      design_effect(pool_f + opt_f)["weeks"],
                                                      design_effect(pool_f + opt_f)["n_eff_week_bound"])}
    nm = sum(1 for f in pool_f if GROUP_OF.get(f["symbol"]) == "metals")
    cost = {k: _mean_or_zero([f["spread_r_entry"]["median"] for f in pool_f
                              if GROUP_OF.get(f["symbol"]) == k and f.get("spread_r_entry")]) for k in ("metals", "indices")}
    rec["power"]["pass_with_breadth"] = {
        "n_metals": nm, "n_indices": pool_n - nm,
        "gross": {str(a): {str(sd): {f"{e:+.2f}": pass_power(nm, pool_n - nm, sd, e, a) for e in (0.0,) + EFFECTS}
                           for sd in SD_PLAN} for a in (0.05, 0.10)},
        "net_at_cost_proxy": {"mean_entry_hour_spread_R": cost, "note": "gross effect minus each group's mean entry-hour "
                              "spread proxy; swap and the p90 lines would lower it further",
                              **{str(a): {str(sd): {f"{e:+.2f}": pass_power(nm, pool_n - nm, sd, e - cost["metals"], a,
                                                                           effect_indices=e - cost["indices"])
                                                    for e in EFFECTS} for sd in SD_PLAN} for a in (0.05, 0.10)}}}
    alt = {}
    for s in [x for x in ALT_SYMBOLS if x in syms]:
        ent = alt_dense_entry(loader, s, zone)
        summ, f, _evs = count_symbol(s, loader, {f"{s}|{TF}": ent}, exposed=s in exposed, cost_r=cost_r)
        alt[s] = {"rule": f"RT §4 dense start with ref_year {ALT_REF_YEAR} ("
                          + ("in the pool: ALT_POOL" if s in alt_pool else "informational, not registered") + ")",
                  "dense": ent, "summary": summ,
                  "overlap": overlap(f, weeks, days) if s not in exposed else None}
    rec["alt_dense"] = alt
    if corr:
        rec["daily_corr"] = {s: {b: daily_corr(loader, s, b) for b in CORR_PAIRS.get(s, ())}
                             for s in list(pool) + list(optional)}
    # the truncation probe (RT §10 item 5 pattern): pool and optional events, re-detected on the series cut at the signal
    sample = [ev for s in list(pool) + list(optional) for ev in events[s]]
    rnd = random.Random(EW._seed("WY-X0", "probe"))
    sample = rnd.sample(sample, min(probe_n, len(sample))) if sample else []
    dense15 = dict({k: v for k, v in dense.items() if k.endswith(f"|{TF}")}, **dense_alt_pool)
    rec["probe"] = EW.probe(sample, loader, dense15, CFG, "W")
    if r0 is not None:
        rec["r0_crosscheck"] = r0_crosscheck(r0, {s: v for s, v in per.items() if s not in alt_pool}, dense)
        rec["r0_code_drift"] = r0_drift(r0)
    if price_ref is not None:                                # the cost model's other input, pinned by the read
        rec["price_ref"] = json.loads(json.dumps({s: price_ref(EW.COST_PROFILE, s) for s in pool}, default=str))
    rec["outcome_blind"] = ("no walk, exit, exit-dependent cost, placebo or return was computed; the entry OPEN is read for "
                            "RT §3.2's skip and the spread is priced at the entry hour")
    _dump(rec, out_path)
    print(f"X0: pool {pool_n} events ({rec['pool']['pre']} pre / {rec['pool']['post']} post 2024-03-01); probe "
          f"{rec['probe']['checked']} checked, {rec['probe']['violations']} violations; wrote {out_path}")
    return rec


def meta(kind):
    """Run provenance and the registered design (compared by the read against the counts record).
    [WY-X1 §11, §14: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    bt = EW.engine()
    return {"study": STUDY, "script": SCRIPT, "kind": kind, "git_head": G.git_head(ROOT),
            "preregistration": PREREG, "draft": PREREG_DRAFT,
            "draft_sha256": _sha256(os.path.join(ROOT, PREREG_DRAFT)) if os.path.exists(os.path.join(ROOT, PREREG_DRAFT))
            else None,
            "code_sha256": {p: (_sha256(os.path.join(ROOT, p)) if os.path.exists(os.path.join(ROOT, p)) else None)
                            for p in CODE},
            "design": {"cell": CELL, "tf": TF, "det_po": dict(CFG), "pool": list(pool_symbols()),
                       "alt_pool": list(ALT_POOL), "alt_ref_year": ALT_REF_YEAR, "optional": list(OPTIONAL),
                       "exposed": list(EXPOSED), "clusters": CLUSTER_OF, "groups": GROUP_OF,
                       "breadth_min": EW.BREADTH_MIN, "window": list(WINDOW),
                       "hypotheses": list(HYPOTHESES), "alpha": ALPHA, "against_p": AGAINST_P, "delta": DELTA,
                       "lines": list(LINES), "primary": PRIMARY, "cost_profile": EW.COST_PROFILE,
                       "hour_frame": EW.HOUR_FRAME, "H": bt.P[TF]["H"] * CFG["cap_mult"], "sob": bt.P[TF]["sob"],
                       "n_placebo": EW.N_PLACEBO, "breadth": {"cluster_min": EW.R2_CLUSTER_MIN,
                                                             "evaluable_min": EW.R2_EVALUABLE_MIN,
                                                             "agree": EW.R2_AGREE},
                       "sd_plan": list(SD_PLAN)}}


# ------------------------------------------------------------------------------------------------ X1: the read (sealed)
def holm(pvals, alpha):
    """Holm step-down at FWER alpha: the set of rejected indices (the k-th smallest p is rejected iff p_(k) <=
    alpha / (m - k + 1) and every smaller p was rejected). [WY-X1 §6]"""
    order = sorted(range(len(pvals)), key=lambda k: pvals[k])
    m, out = len(pvals), set()
    for rank, k in enumerate(order):
        if pvals[k] <= alpha / (m - rank):
            out.add(k)
        else:
            break
    return out


def breadth(rows, clusters=None, lines=LINES):
    """RT §4 R2's cluster rule over WY-X1's clusters, REPORTED (not a gate): of the clusters with >= R2_CLUSTER_MIN events
    (at least R2_EVALUABLE_MIN evaluable), at least min(R2_AGREE, evaluable) have net excess > 0 (EW.r2_pass, with the
    cluster map as an argument so the two optional European indices can sit in EU).
    [WY-X1 §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    clusters = clusters or CLUSTER_OF
    names = list(dict.fromkeys(clusters.values()))
    cl = {c: EW.summarise([r for r in rows if clusters.get(r["symbol"]) == c], lines) for c in names}
    ev = [c for c, s in cl.items() if s.get("n", 0) >= EW.R2_CLUSTER_MIN]
    agree = [c for c in ev if cl[c]["net_excess"] > 0]
    ok = len(ev) >= EW.R2_EVALUABLE_MIN and len(agree) >= min(EW.R2_AGREE, len(ev))
    return {"clusters": cl, "evaluable": ev, "agree": agree, "breadth": bool(ok)}


def decision_lines(decision=None):
    """The summary lines, the DECISION line first (EW.summarise's primary): the gross excess and RT's four net lines.
    [WY-X1 §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return ((GROSS,) + LINES) if (decision or DECISION) == "gross" else (LINES + (GROSS,))


def with_gross(rows):
    """Rows with a zero-cost GROSS line added to `cost`, so EW.summarise reports the placebo excess before cost."""
    return [dict(r, cost=dict(r["cost"], **{GROSS: 0.0})) for r in rows]


def breadth_groups(rows, groups=None, lines=None):
    """The WY-X1 breadth GATE = RT §6.2 item 3 (EW.r1_verdicts): metals and indices each hold >= EW.BREADTH_MIN events and
    each has a mean > 0 on the decision line (the first of `lines`); with fewer events in either group breadth cannot be
    met. [WY-X1 §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    lines = lines or LINES
    groups = groups or GROUP_OF
    g = {k: EW.summarise([r for r in rows if groups.get(r["symbol"]) == k], lines) for k in ("metals", "indices")}
    meetable = all(g[k].get("n", 0) >= EW.BREADTH_MIN for k in g)
    return {"groups": g, "meetable": meetable, "breadth": bool(meetable and all(g[k]["net_excess"] > 0 for k in g))}


def replicated_label(decision=None):
    """The positive label names its line and its data, so a before-cost PASS on history never reads as RT's net H-WC
    replicating: "REPLICATED (gross, history)" or "REPLICATED (net, history)".
    [WY-X1 §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    return f"REPLICATED ({decision or DECISION}, history)"


def verdict(summary, br, p_holm_ok, decision=None):
    """WY-X1 §6 label, on the decision line (`summary` from EW.summarise with that line first). REPLICATED (`replicated_label`)
    iff Holm rejects (one-sided, ALPHA) and the breadth gate (`breadth_groups`) holds, and, under the "net" decision only,
    the mean is > 0 on all four cost lines (RT §6.2 item 2). AGAINST THE BOOK iff two-sided p < AGAINST_P with a negative
    mean. NOT REPLICATED otherwise. [WY-X1 §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    decision = decision or DECISION
    n = summary.get("n", 0)
    lines_pos = bool(n) and all((summary["lines"][ln]["mean"] or 0) > 0 for ln in LINES if ln in summary["lines"])
    against = bool(n) and summary["net_excess"] < 0 and summary["p_two_sided"] < AGAINST_P
    gates = {"decision": decision, "holm_rejected": bool(p_holm_ok), "all_cost_lines_positive": lines_pos,
             "cost_lines_gate": decision == "net", "breadth": br["breadth"], "against_the_book": against,
             "upper_95": summary.get("upper_95"),
             "below_delta": bool(n) and summary.get("upper_95") is not None and summary["upper_95"] < DELTA}
    if p_holm_ok and br["breadth"] and (lines_pos or decision != "net"):
        return dict(gates, label=replicated_label(decision))
    if against:
        return dict(gates, label="AGAINST THE BOOK")
    return dict(gates, label="NOT REPLICATED")


def read_core(symbols, loader, dense, pricer, bt=None, window=WINDOW, exposed_weeks=frozenset(), clusters=None):
    """Score every W-C-long-15m event of `symbols` in `window` with RT §5 (EW.score: gross R from the engine walk, the
    ATR-multiple placebo, the four FTMO cost lines; trend-matched placebo carried, descriptive), each series cut at the
    window's end (as RT R1 / R2). Then: the pooled summary (EW.summarise: CR1 by ISO week, t with G - 1 df), Holm over
    HYPOTHESES, breadth, the label, and the descriptive splits (period, cluster, symbol, type, outcome mix, the
    exposed-week-free subset, and RT §3.7's flatten / ceiling variants).
    [WY-X1 §5, §6: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    bt = bt or EW.engine()
    lo, hi = window
    HZ = bt.P[TF]["H"] * CFG["cap_mult"]
    rows, desc, skipped, data = [], collections.defaultdict(list), collections.Counter(), {}
    with EW.walk_opts(bt):
        for sym in symbols:
            S = EW.make_series(sym, TF, loader, dense, CFG, "ftmo", until=hi)
            if S is None:
                data[sym] = {"bars": 0, "why": "no dense start or no bars"}
                continue
            evs = [ev for ev in detect(S)[LEG] if ev["side"] == SIDE and EW.kept(S, ev, lo, hi)]
            for ev in evs:
                r, why = EW.score(bt, S, ev, HZ, pricer, lo, hi, trend=True)
                if r is None:
                    skipped[why] += 1
                    continue
                rows.append(r)
                rc, why_c = EW.score(bt, S, ev, HZ, pricer, lo, hi, target=ev["ceiling"])
                if rc is not None:
                    desc["ceiling-target"].append(rc)
                with EW.walk_opts(bt, flatten=True):
                    rf, why_f = EW.score(bt, S, ev, HZ, pricer, lo, hi)
                if rf is not None:
                    desc["flatten"].append(rf)
            data[sym] = {"bars": len(S), "first": S.T[0], "last": S.T[-1], "dense_start": S.start.isoformat(),
                         "events": len(evs)}
    L, g = decision_lines(), with_gross(rows)
    summary = EW.summarise(g, L)
    ps = [summary.get("p_one_sided", 1.0) if summary.get("n") else 1.0]
    rej = holm(ps, ALPHA)
    br = breadth_groups(g, lines=L)
    tr = with_gross([dict(r, excess=r["excess_trend"]) for r in rows if r.get("excess_trend") is not None])
    out = {"summary": summary, "decision": DECISION, "lines": list(L),
           "holm": {"m": len(HYPOTHESES), "alpha": ALPHA, "rejected": sorted(rej)},
           "breadth": br, "clusters_r2_rule": breadth(g, clusters, lines=L), "verdict": verdict(summary, br, 0 in rej),
           "descriptive": {
               "by_period": {"pre_2024_03": EW.summarise([r for r in g if r["entry_time"] < DEV_CUTOFF], L),
                             "from_2024_03": EW.summarise([r for r in g if r["entry_time"] >= DEV_CUTOFF], L)},
               "by_symbol": EW.by(g, "symbol", L), "by_type": EW.by(g, "type", L),
               "exposed_week_free": EW.summarise([r for r in g if r["week"] not in exposed_weeks], L),
               "trend_placebo": EW.summarise(tr, L),
               "ceiling_target": EW.summarise(with_gross(desc["ceiling-target"]), L),
               "flatten": EW.summarise(with_gross(desc["flatten"]), L),
               "outcomes": dict(collections.Counter(r["outcome"] for r in rows)),
               "win_rate": (sum(1 for r in rows if r["R"] > 0) / len(rows)) if rows else None,
               "truncated": sum(1 for r in rows if r.get("truncated"))},
           "skipped": dict(skipped), "data": data, "rows": rows}
    return out


def x0_line(root=ROOT, rel=X0_OUT):
    """The line the sealed text carries for the counts record: "x0-sha256 <64 hex> <path>" (WY-X1 §11 step 5), or None
    when the record does not exist yet. [WY-X1 §11: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    full = os.path.join(root, rel)
    return f"x0-sha256 {_sha256(full)} {rel}" if os.path.exists(full) else None


def _require_x0(x0, text, x0_rel, man, design, x0_sha):
    """The counts record the read stands on: X0 of this script, pinned by the sealed text (exactly one `x0-sha256` line for
    its path, equal to `x0_sha`, the file's sha256: a counts run repeated after a data revision and recommitted at the same
    path is refused), made by the sealed code (its code_sha256 equals the manifest) under this design, with a passing
    probe, the registered pool, every pool symbol's price reference, and an EMPTY R0 cross-check and R0 code-drift list
    (both present). [WY-X1 §11: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    m = x0.get("meta") or {}
    if m.get("script") != SCRIPT or m.get("kind") != "counts":
        raise G.Refused(f"refused: {x0_rel} is not a counts record of {SCRIPT}")
    pins = [sha for sha, p in X0_LINE.findall(text) if p == x0_rel]
    if len(pins) != 1:
        raise G.Refused(f"refused: the sealed text must pin the counts record {x0_rel} by exactly one 'x0-sha256' line "
                        f"(found {len(pins)})")
    if pins[0] != x0_sha:
        raise G.Refused(f"refused: {x0_rel} is not the counts record the sealed text pins (sha256 {x0_sha[:12]} != "
                        f"sealed {pins[0][:12]})")
    code = m.get("code_sha256") or {}
    stale = [p for p in man if code.get(p) != man[p]]
    if stale:
        raise G.Refused("refused: the counts record was made by other code than the sealed manifest: " + ", ".join(stale))
    if m.get("design") != design:
        raise G.Refused("refused: the counts record was made under another registered design")
    pr = x0.get("probe") or {}
    if pr.get("ok") is not True or pr.get("violations") != 0 or not pr.get("checked"):
        raise G.Refused("refused: the X0 truncation probe did not pass; no outcome is read on a leaking detector")
    if (x0.get("pool") or {}).get("symbols") != list(pool_symbols()):
        raise G.Refused(f"refused: X0's pool {(x0.get('pool') or {}).get('symbols')} is not the registered "
                        f"{list(pool_symbols())}")
    if x0.get("r0_crosscheck") != [] or x0.get("r0_code_drift") != []:
        raise G.Refused("refused: X0 did not reproduce R0, ran on drifted code, or lacks the check (r0_crosscheck / "
                        "r0_code_drift must be present and empty)")
    missing = [s for s in pool_symbols() if not ((x0.get("price_ref") or {}).get(s) or {}).get("closes_sha256")]
    if missing:
        raise G.Refused("refused: X0 lacks the price reference of " + ", ".join(missing))


def _require_ledger(root=ROOT):
    """WY-X1 §10, §11 step 6: the ledger is committed and clean and holds LEDGER_KEY naming the sealed text (as EW
    `_require_ledger`). [WY-X1 §11: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    G.require_committed(root, [LEDGER])
    try:
        with open(os.path.join(root, LEDGER), encoding="utf-8") as fh:
            led = json.load(fh)
    except ValueError as e:
        raise G.Refused(f"refused: {LEDGER} is not valid JSON ({e})")
    ent = led.get(LEDGER_KEY) if isinstance(led, dict) else None
    if not isinstance(ent, dict) or ent.get("preregistration") != PREREG:
        raise G.Refused(f"refused: {LEDGER} has no {LEDGER_KEY!r} entry naming {PREREG}; register the study (WY-X1 §11 "
                        "step 6) before the read")


def _require_clean_trees(git=_git):
    """No edited, staged or untracked file under CLEAN_TREES (`git status --porcelain --untracked-files=all`), as EW
    `_require_clean_trees`: an edit outside CODE cannot reach the read either.
    [WY-X1 §5, §11: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    rc, out = git("status", "--porcelain", "--untracked-files=all", "--", *CLEAN_TREES)
    if rc != 0 or out.strip():
        lines = out.decode(errors="replace").strip().splitlines() if isinstance(out, bytes) else str(out).splitlines()
        raise G.Refused(f"refused: {', '.join(CLEAN_TREES)} must be committed and clean (untracked files included) "
                        "before the read: " + "; ".join(lines[:8]))


def cmd_read(counts_path, out_path, loader=EW.load_ftmo, cost_r=None, root=ROOT, git=_git):
    """The ONE read (WY-X1 §6). Every refusal below comes BEFORE any market data is loaded: the sealed text
    (prereg_guard), the canonical output with no git history, the committed code / counts / R0 / R1, the sealed code
    manifest, the ledger entry, the clean code and cost trees, the R0 code pin, the R0-commit blobs of the cost tables and
    of EXTRA_CODE, the hour frame, and the counts record's checks (its sha256 pinned by the sealed text). Then, on the
    data: the data pin (X0's window digests) and the price-reference pin (X0's `price_ref`), the traced computation, and
    the coverage check before writing.
    [WY-X1 §6, §11: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    text = G.require_sealed(root, PREREG, TAG)
    if os.path.abspath(out_path) != os.path.join(os.path.abspath(root), X1_OUT):
        raise G.Refused(f"refused: the read writes {X1_OUT} (got {out_path})")
    G.refuse_overwrite(out_path)
    rc, log = git("log", "--all", "--format=%H", "--", X1_OUT)
    if rc != 0 or log.strip():
        raise G.Refused(f"refused: {X1_OUT} has git history (the read runs once) or git cannot say")
    x0_rel = _rel(counts_path, root)
    G.require_committed(root, CODE + (x0_rel, R0_PATH, R1_PATH))
    man = G.require_fingerprint(root, text, CODE)
    _require_ledger(root)
    _require_clean_trees(git)
    with open(os.path.join(root, R0_PATH), encoding="utf-8") as fh:
        r0 = json.load(fh)
    drift = r0_drift(r0, root)
    if drift:
        raise G.Refused("refused: R0-pinned code (EW CODE without its tests) differs from what the re-test ran (R0 "
                        "meta.code_sha256): " + ", ".join(drift))
    pool = pool_symbols()
    cd = cost_drift(pool, r0, git, root)
    if cd:
        raise G.Refused("refused: cost tables differ from the R0 commit's: " + ", ".join(cd))
    xd = blob_drift(EXTRA_CODE, r0, git, root)
    if xd:
        raise G.Refused("refused: code the read executes outside R0's fingerprint differs from the R0 commit's blob: "
                        + ", ".join(xd))
    if RC.HOUR_FRAME != EW.HOUR_FRAME:
        raise G.Refused(f"refused: real_costs.HOUR_FRAME is {RC.HOUR_FRAME!r}, RT §5 needs {EW.HOUR_FRAME!r}")
    with open(os.path.join(root, x0_rel), encoding="utf-8") as fh:
        x0 = json.load(fh)
    _require_x0(x0, text, x0_rel, man, json.loads(json.dumps(meta("read")["design"], default=str)),
                _sha256(os.path.join(root, x0_rel)))
    G.trace_start(root)
    dense = {f"{s}|{TF}": (x0["dense_alt_pool"] if s in ALT_POOL else x0["dense"])[f"{s}|{TF}"] for s in pool}
    for s in pool:                                          # the data pin: the window's bars are X0's
        S = EW.make_series(s, TF, loader, dense, CFG, "ftmo", until=WINDOW_END)
        got = window_digest(S.src if S is not None else [])
        want = (x0["symbols"][s].get("data") or {}).get("sha256")
        if got["sha256"] != want:
            raise G.Refused(f"refused: {s} 15m bars inside the window differ from X0's (data revised since the counts)")
        del S
    for s in pool:                                          # the price-reference pin: the relspread scaling is X0's
        got = json.loads(json.dumps(RC.price_ref_info(EW.COST_PROFILE, s), default=str))
        if got != x0["price_ref"][s]:
            raise G.Refused(f"refused: {s} real_costs price reference differs from X0's (history revised in the spread "
                            "recording window since the counts)")
    pricer = EW.Pricer("ftmo", cost_r=cost_r)
    res = read_core(pool, loader, dense, pricer, window=WINDOW,
                    exposed_weeks=frozenset(x0["overlap"]["exposed_weeks"]))
    res["meta"] = dict(meta("read"), manifest=man, preregistration_sha256=_sha256(os.path.join(root, PREREG)),
                       counts={"path": x0_rel, "sha256": _sha256(os.path.join(root, x0_rel))},
                       price_ref={s: RC.price_ref_info(EW.COST_PROFILE, s) for s in pool},
                       cost_files={p: _sha256(os.path.join(root, p)) for p in cost_files(pool)})
    G.require_covered(man)
    loaded = sorted(EW._loaded_code() - set(CODE))
    if loaded:
        raise G.Refused("refused: the read loaded code the manifest does not list: " + ", ".join(loaded))
    res["meta"]["opened_files"] = G.opened_files(root, skip_prefixes=("data/history/ftmo/",))
    _dump(res, out_path)
    print(f"X1: n {res['summary'].get('n')}, label {res['verdict']['label']}; wrote {out_path}")
    return res


# ------------------------------------------------------------------------------------------------ report
def _f(x, nd=2, sign=True):
    if x is None:
        return "-"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def report(x0, x1=None):
    """Markdown summary of X0 (and of X1 when given). Counts, costs known at the entry, and power only unless X1 is passed.
    [WY-X1 §2, §7: docs/plans/2026-10-04-wyckoff-wcx-replication-preregistration-DRAFT.md]"""
    out = ["# WY-X1 counts (X0, outcome-blind)", "",
           "| symbol | role | dense start (15m) | symbol-years | events pre 2024-03 | events from 2024-03 | per year | "
           "Spring / Shakeout | entry-hour spread, R (median / mean) | same week as an exposed event |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    ov = x0["overlap"]["by_symbol"]
    exposed = set(((x0.get("meta") or {}).get("design") or {}).get("exposed") or EXPOSED)
    for s, v in x0["symbols"].items():
        role = "pool" if s in x0["pool"]["symbols"] else ("exposed" if s in exposed else "optional")
        w = v["window"]
        bt = w.get("by_type", {})
        o = ov.get(s) or {}
        sq = (v.get("spread_r_entry") or {}).get("median") or {}
        out.append(f"| {s} | {role} | {v.get('dense_start') or 'none'} | {_f(v.get('years'), 1, False)} | "
                   f"{(v.get('pre') or {}).get('placeable', 0)} | {(v.get('post') or {}).get('placeable', 0)} | "
                   f"{_f(v.get('rate_per_year'), 1, False)} | {bt.get('SPRING', 0)} / {bt.get('SHAKEOUT', 0)} | "
                   f"{_f(sq.get('median'), 2, False)} / {_f(sq.get('mean'), 2, False)} | {o.get('same_week', '-')} |")
    p = x0["pool"]
    out += ["", f"Pool: {p['placeable']} events ({p['pre']} before 2024-03-01, {p['post']} after) in "
                f"{p['weeks']} ISO weeks over {_f(p['symbol_years'], 1, False)} symbol-years; n_eff (week bound) "
                f"{_f(p['n_eff_week_bound'], 1, False)}. Probe: {x0['probe']['checked']} checked, "
                f"{x0['probe']['violations']} violations. R0 cross-check differences: "
                f"{len(x0.get('r0_crosscheck') or [])}; R0-pinned code drift: {len(x0.get('r0_code_drift') or [])}.", ""]
    pw = (x0.get("power") or {}).get("pool", {}).get("n")
    pp = (x0.get("power") or {}).get("pass_with_breadth") or {}
    if pw:
        out += ["| alpha (one-sided) | SD | MDE at 80 % | P(REPLICATED), gross +0.25 / +0.35 / +0.50R | false pass | "
                "P(REPLICATED) on the net line at the cost proxy, same effects |", "|---|---|---|---|---|---|"]
        for a in ("0.1", "0.05"):
            for sd in sorted(pw.get(a, {}), key=float):             # the record's own planning SDs (SD_PLAN)
                r = pw[a][sd]
                g = (pp.get("gross") or {}).get(a, {}).get(sd, {})
                n = (pp.get("net_at_cost_proxy") or {}).get(a, {}).get(sd, {})
                eff = ("+0.25", "+0.35", "+0.50")
                out.append(f"| {a} | {sd} | {_f(r['mde_80'], 2, False)} | "
                           + " / ".join(_f((g.get(e) or {}).get("replicated"), 2, False) for e in eff)
                           + f" | {_f((g.get('+0.00') or {}).get('replicated'), 2, False)} | "
                           + " / ".join(_f((n.get(e) or {}).get("replicated"), 3, False) for e in eff) + " |")
    if x1 is not None:
        s, v = x1["summary"], x1["verdict"]
        out += ["", "# WY-X1 read (X1)", "",
                f"Label: **{v['label']}** (decision line: {x1.get('decision')}). n {s.get('n')}, mean "
                f"{_f(s.get('net_excess'))} (one-sided p {_f(s.get('p_one_sided'), 3, False)}, 95 % upper bound "
                f"{_f(s.get('upper_95'))}); RT's net line (median spread, swap) "
                f"{_f(((s.get('lines') or {}).get(PRIMARY) or {}).get('mean'))}."]
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("manifest", help="print the code-sha256 lines the sealed text must carry")
    c = sub.add_parser("counts")
    c.add_argument("--out", required=True)
    r = sub.add_parser("read")
    r.add_argument("--counts", required=True)
    r.add_argument("--out", required=True)
    p = sub.add_parser("report")
    p.add_argument("--counts", required=True)
    p.add_argument("--read")
    p.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "manifest":
        with open(os.path.join(ROOT, R0_PATH), encoding="utf-8") as fh:
            r0 = json.load(fh)
        drift = r0_drift(r0) + blob_drift(EXTRA_CODE, r0)
        if drift:
            raise SystemExit("refusing: code differs from the re-test's (R0 meta.code_sha256, or the R0 commit's blob for "
                             "EXTRA_CODE): " + ", ".join(drift))
        lines = G.manifest_lines(ROOT, CODE)
        x0 = x0_line()
        print("\n".join(lines + ([x0] if x0 else [])))
        if not x0:
            print(f"(no {X0_OUT} yet: run counts and commit it, then re-run manifest for its x0-sha256 line)",
                  file=sys.stderr)
        return
    if a.cmd == "counts":
        with open(os.path.join(ROOT, R0_PATH), encoding="utf-8") as fh:
            r0 = json.load(fh)
        with open(os.path.join(ROOT, R1_PATH), encoding="utf-8") as fh:
            r1_rows = [{"signal_time": x["signal_time"]} for x in json.load(fh)["rows"][CELL]]
        counts(a.out, r0=r0, r1_rows=r1_rows)
        return
    if a.cmd == "read":
        cmd_read(a.counts, a.out)
        return
    with open(a.counts, encoding="utf-8") as fh:
        x0 = json.load(fh)
    x1 = None
    if a.read:
        with open(a.read, encoding="utf-8") as fh:
            x1 = json.load(fh)
    G.refuse_overwrite(a.out)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(report(x0, x1))
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
