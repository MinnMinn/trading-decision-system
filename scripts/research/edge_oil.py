#!/usr/bin/env python3
"""Family OIL: the gold intraday-trend rules H7 / G9 on FTMO's crude-oil CFDs (UKOIL.cash, USOIL.cash).
Pre-registration (DRAFT until sealed): docs/plans/2026-10-04-oil-trend-transfer-preregistration-DRAFT.md [OIL-P1].
No FTMO oil bar exists in this repository when this is written; the owner exports them after the seal. (Yahoo CL=F / BZ=F
front-month futures files were in the repo from commit 3070e2e to 345e586, and the ICT / Wyckoff stability runs read their
1H / 4H bars 2024-04-19 -> 2026-09-11: the EXPOSED window is UNREAD-FOR-H, not fresh. OIL-P1 §3.)

    python3 scripts/research/edge_oil.py manifest                                 # the code-sha256 lines for the seal
    python3 scripts/research/edge_oil.py dry-run --symbol-list <symbollist.FTMO-Demo.json> --end YYYY-MM-DD --out <json>
    python3 scripts/research/edge_oil.py screen  --dry <dry json> --spec-dir <dir> --commission <json> --out <json>
    python3 scripts/research/edge_oil.py run --read discovery    --screen <json> --out docs/audits/<date>-edge-oil-discovery.json
    python3 scripts/research/edge_oil.py run --read confirmation --screen <json> --after <discovery json> --out ...
    python3 scripts/research/edge_oil.py run --read exposed      --screen <json> --after <confirmation json> --out ...

dry-run and screen are outcome-blind (bar / day / event COUNTS, event timing, volatility and spreads; no return after a
signal). A read computes outcome rows only for the days of its own window, runs once, from committed code whose sha256 the
SEALED pre-registration lists (scripts/research/prereg_guard.py: `manifest`, `require_fingerprint`, `require_covered`).

Rules: scripts/research/pit_trend.py ([CX-P1] §1 text), prev_rule "trading" (a 5-day market), min_bars = floor(0.8 x the
regular weekday session's 5m bars in the committed symbol-list export). Measurement, gates and screen: [CX-P1] §2, §4, §5
applied to one group (the oil members): T1 = H7 pooled, T2 = G9 pooled; placebo matched on entry slot, weekday and MOM20
sign within the symbol and read; CR1 by server date; cost per leg = half the recorded relative spread at the leg's table
bucket + c_sym; stress = p90 spread + c_sym; no swap (flat at the server day's last bar)."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


PT = _load("pit_trend", "scripts/research/pit_trend.py")
G = _load("prereg_guard", "scripts/research/prereg_guard.py")
_EC = None


def _ec():
    global _EC
    if _EC is None:
        _EC = _load("edge_census", "scripts/research/edge_census.py")
    return _EC


PREREG = "docs/plans/2026-10-04-oil-trend-transfer-preregistration.md"
TAG = "[OIL-P1]"
SCRIPT = "scripts/research/edge_oil.py"
TESTS_FILE = "scripts/tests/test_edge_oil.py"
#: Every file whose content can change an OIL read: this script, its tests, and every repository module a read executes
#: (traced: scripts/tests/test_edge_oil.py `test_code_lists_every_module_a_read_loads`).
CODE = (SCRIPT, TESTS_FILE, "scripts/tests/test_pit_trend.py", "scripts/tests/test_prereg_guard.py",
        "scripts/research/pit_trend.py", "scripts/research/prereg_guard.py", "scripts/research/edge_census.py",
        "scripts/real_costs.py", "scripts/history_store.py", "scripts/mt5_time.py", "scripts/providers.py",
        "scripts/instruments.py")
SYMBOLS = {"UKOIL": "UKOIL.cash", "USOIL": "USOIL.cash"}      # canonical -> FTMO raw name
HIST_ROOT = os.path.join(ROOT, "data", "history", "ftmo")
PROVIDER = "mt5_bridge_ftmo"
MIN_SHARE = 0.8
PREV_RULE = "trading"
DEV_END = datetime.date(2024, 3, 1)
SPLIT_SHARE = 0.60
MIN_MEMBER_DAYS = 250
FDR_Q, CONFIRM_P, EXPOSED_P = 0.10, 0.05, 0.10
SCREEN_Z, SCREEN_SHARE = 0.05, 0.5                             # cost may eat at most half of a z = 0.05 excess
READS = ("discovery", "confirmation", "exposed")
TESTS = (("T1", "H7"), ("T2", "G9"))
STOP_KS = (1.4, 2.0)                                           # report-only owner sizing (v4, v3)


# ------------------------------------------------------------------------------------------------ windows
def split_date(qual_by_sym, dev_end=DEV_END, share=SPLIT_SHARE):
    """D* = the smallest date d with #{pooled qualifying symbol-days < d, before dev_end} >= share x N."""
    days = sorted(d for v in qual_by_sym.values() for d in v if d < dev_end)
    if not days:
        return None
    need = share * len(days)
    counts = collections.Counter(days)
    seen = 0
    for d in sorted(counts):
        if seen >= need:
            return d
        seen += counts[d]
    return dev_end


def members(qual_by_sym, d_star, dev_end=DEV_END, min_days=MIN_MEMBER_DAYS):
    out = []
    for sym, v in sorted(qual_by_sym.items()):
        a = sum(1 for d in v if d < d_star)
        b = sum(1 for d in v if d_star <= d < dev_end)
        if a >= min_days and b >= min_days:
            out.append(sym)
    return out


def window(read, d_star, end_day):
    """[lo, hi) in server dates."""
    return {"discovery": (datetime.date.min, d_star), "confirmation": (d_star, DEV_END),
            "exposed": (DEV_END, end_day + datetime.timedelta(days=1))}[read]


def min_bars_for(entry):
    return math.floor(MIN_SHARE * PT.session_bars(entry["sessions_trade"]))


# ------------------------------------------------------------------------------------------------ dry run (counts only)
def dry_symbol(b, min_bars):
    """Outcome-blind counts for one symbol: qualifying / eligible days, events per rule per pre-DEV_END day, the hold length
    of those events (bars from entry to the day's last bar: timing, not return), the modal last-bar slot, sigma per eligible
    day before DEV_END."""
    qual = PT.qualifying(b, min_bars)
    ctx = PT.context(b, min_bars, PREV_RULE)
    evs = PT.events(b, ctx)
    holds = [PT.exit_index(b, e) - e["entry_i"] + 1 for r in PT.RULES for e in evs[r] if e["day"] < DEV_END]
    last_slots = collections.Counter(PT.slot(b, rows[-1]) for d, rows in b.day_rows.items() if d in qual)
    per_wd = collections.defaultdict(list)
    for d, rows in b.day_rows.items():
        per_wd[d.weekday()].append(len(rows))
    gaps = []                                  # data quality (futures-roll check): open(D) vs the previous day's last close
    for d, c in ctx.items():
        y = b.day_rows[c["prev_day"]][-1]
        g = b.O[b.day_rows[d][0]] / b.C[y] - 1.0
        sd_day = c["sigma"] * math.sqrt(max(1, min_bars))
        if sd_day > 0:
            gaps.append((d, g / sd_day))
    return {"bars": len(b.T), "first_bar": b.T[0] if b.T else None, "last_bar": b.T[-1] if b.T else None,
            "min_bars": min_bars, "qualifying_days": sorted(qual), "eligible_days": len(ctx),
            "events": {r: [e["day"] for e in evs[r]] for r in PT.RULES},
            "median_hold_bars": statistics.median(holds) if holds else None,
            "last_slot_mode": last_slots.most_common(1)[0][0] if last_slots else None,
            "sigma_pre_dev": [c["sigma"] for d, c in ctx.items() if d < DEV_END],
            "median_bars_per_weekday": {wd: statistics.median(v) for wd, v in sorted(per_wd.items())},
            "largest_overnight_gaps_daily_sd": [(str(d), round(z, 2)) for d, z in
                                                sorted(gaps, key=lambda x: -abs(x[1]))[:20]]}


def dry_summary(per_sym, end_day):
    qual = {s: v["qualifying_days"] for s, v in per_sym.items()}
    d_star = split_date(qual)
    mem = members(qual, d_star) if d_star else []
    out = {"d_star": str(d_star) if d_star else None, "members": mem, "end": str(end_day), "symbols": {}}
    for s, v in per_sym.items():
        w = {}
        for read in READS:
            lo, hi = window(read, d_star or DEV_END, end_day)
            w[read] = {"qualifying_days": sum(1 for d in v["qualifying_days"] if lo <= d < hi),
                       "events": {r: sum(1 for d in v["events"][r] if lo <= d < hi) for r in PT.RULES}}
        out["symbols"][s] = {k: v[k] for k in ("bars", "first_bar", "last_bar", "min_bars", "eligible_days",
                                               "median_hold_bars", "last_slot_mode", "median_bars_per_weekday",
                                               "largest_overnight_gaps_daily_sd")}
        out["symbols"][s]["windows"] = w
        sig = v["sigma_pre_dev"]
        out["symbols"][s]["S"] = (statistics.median(sig) * math.sqrt(v["median_hold_bars"])
                                  if sig and v["median_hold_bars"] else None)
    return out


# ------------------------------------------------------------------------------------------------ screen
def screen_symbol(sc, S, last_slot):
    """K = 0.5 x median over the 24 buckets of the relative spread + 0.5 x the relative spread at the bucket of the server
    day's last bar + 2 x c_sym; admitted iff K <= SCREEN_SHARE x SCREEN_Z x S ([CX-P1] §2)."""
    med = statistics.median(sc.spread_rel(h) for h in range(24))
    last_bucket = (last_slot // 60 - sc.offset_h) % 24
    K = 0.5 * med + 0.5 * sc.spread_rel(last_bucket) + 2 * sc.c_sym
    return {"K": K, "S": S, "limit": SCREEN_SHARE * SCREEN_Z * S if S else None,
            "admitted": bool(S) and K <= SCREEN_SHARE * SCREEN_Z * S, "spread_fallbacks": sc.fallbacks}


# ------------------------------------------------------------------------------------------------ a read
def read_rows(b, ctx, lo, hi, cost, rules=PT.RULES):
    """Outcome rows (with placebo excess) for the events of server days in [lo, hi), for the still-open `rules` only (a
    closed test's later windows are retired UNREAD: no row of it is computed)."""
    days = [d for d in ctx if lo <= d < hi]
    plc = PT.placebo_table(b, ctx, days)
    out, missing = {}, {}
    for rule, evs in PT.events(b, ctx).items():
        if rule not in rules:
            continue
        rows = [PT.outcome(b, e, ctx, cost) for e in evs if lo <= e["day"] < hi]
        out[rule], missing[rule] = PT.with_excess(rows, plc)
    return out, missing


def verdicts(read, tests, prior=None):
    """{test id: verdict} for this read. prior: the previous read's verdicts (a test that failed is closed)."""
    EC = _ec()
    out = {}
    if read == "discovery":
        ids = [t for t, _ in TESTS]
        p = [tests[t].get("p_one_sided", 1.0) if tests[t].get("n") else 1.0 for t in ids]
        rej = EC.bh(p, FDR_Q)
        for k, t in enumerate(ids):
            out[t] = {"advances": bool(k in rej and tests[t].get("n") and tests[t]["net_bp"] > 0), "bh_rejected": k in rej}
        return out
    for t, _ in TESTS:
        if not (prior or {}).get(t, {}).get("advances"):
            out[t] = {"advances": False, "closed_before_this_read": True}
            continue
        s = tests[t]
        if read == "confirmation":
            ok = s.get("n") and s["p_one_sided"] < CONFIRM_P and s["net_bp"] > 0 and s["net_bp_p90"] > 0
        else:
            ok = s.get("n") and s["p_one_sided"] < EXPOSED_P and s["net_bp"] > 0
        out[t] = {"advances": bool(ok)}
    return out


def owner_sizing(b, ctx, lo, hi, cost, n_members, rules=PT.RULES):
    """Report-only: the survivor's tradable form at 1 % / members at the stop, stop k in STOP_KS (open rules only)."""
    out = {}
    evs_all = PT.events(b, ctx)
    for k in STOP_KS:
        ts = [PT.stop_trade(b, e, ctx, k, cost) for r in rules for e in evs_all[r] if lo <= e["day"] < hi]
        if not ts:
            out[str(k)] = {"n": 0}
            continue
        out[str(k)] = {"n": len(ts), "mean_R_net": sum(t["R_net"] for t in ts) / len(ts),
                       "stop_share": sum(1 for t in ts if t["exit"] == "stop") / len(ts),
                       "gap_through": sum(1 for t in ts if t["R_net"] < -1.05),
                       "worst_R": min(t["R_net"] for t in ts), "risk_pct_each": 1.0 / max(1, n_members)}
    return out


def by_symbol_year(rows):
    """Report-only: summarise per rule x symbol x year, and per side."""
    EC = _ec()
    out = {}
    for rule, rs in rows.items():
        g = collections.defaultdict(list)
        for r in rs:
            g[f"{r['symbol']}|{r['year']}"].append(r)
            g[f"side={r['side']}"].append(r)
        out[rule] = {k: EC.summarise(v) for k, v in sorted(g.items())}
    return out


# ------------------------------------------------------------------------------------------------ CLI
def _zone():
    import real_costs as RC
    return RC.server_zone(PROVIDER)[1]


def _bars(sym, zone, end_iso=None):
    import history_store as HS
    doc, _ = HS.read_doc(sym, "5m", root=HIST_ROOT)
    if doc is None:
        raise G.Refused(f"refused: no FTMO 5m history for {sym} under {HIST_ROOT}")
    return PT.Bars(sym, doc["candles"], zone, end=end_iso)


def _end_iso(day, zone=None):
    """The instant server day `day` ends (00:00 server time on day + 1), as ISO "...Z": no bar after it is loaded."""
    zone = zone or _zone()
    n = day + datetime.timedelta(days=1)
    t = datetime.datetime(n.year, n.month, n.day, tzinfo=zone).astimezone(datetime.timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _rel(p):
    """A CLI path as a repository-relative path (what require_committed checks)."""
    return os.path.relpath(os.path.abspath(p), ROOT).replace(os.sep, "/")


def _dump(res, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dry-run")
    d.add_argument("--symbol-list", required=True)
    d.add_argument("--end", required=True, help="the fixed EXPOSED end date (recorded in the screening amendment)")
    d.add_argument("--out", required=True)
    s = sub.add_parser("screen")
    s.add_argument("--dry", required=True)
    s.add_argument("--spec-dir", required=True, help="dir with symbolspec.<raw>.json from ExportSymbolSpec")
    s.add_argument("--commission", required=True, help='{"UKOIL": c_sym, ...} commission per side, fraction of notional')
    s.add_argument("--out", required=True)
    sub.add_parser("manifest", help="print the code-sha256 lines the sealed text must carry")
    r = sub.add_parser("run")
    r.add_argument("--read", required=True, choices=READS)
    r.add_argument("--screen", required=True)
    r.add_argument("--after")
    r.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.cmd == "manifest":
        print("\n".join(G.manifest_lines(ROOT, CODE)))
        return
    G.refuse_overwrite(a.out)
    zone = _zone()
    if a.cmd == "dry-run":
        sl = {x["name"]: x for x in json.load(open(a.symbol_list))["symbols"]}
        end = datetime.date.fromisoformat(a.end)
        per = {}
        for canon, raw in SYMBOLS.items():
            per[canon] = dry_symbol(_bars(canon, zone, _end_iso(end, zone)), min_bars_for(sl[raw]))
        _dump({"meta": {"script": SCRIPT, "kind": "dry-run (counts only)", "git_head": G.git_head(ROOT),
                        "symbol_list": a.symbol_list,
                        "code_sha256": {p: G.file_sha256(os.path.join(ROOT, p)) for p in CODE}},
               "summary": dry_summary(per, end)}, a.out)
        return
    if a.cmd == "screen":
        dry = json.load(open(a.dry))["summary"]
        com = json.load(open(a.commission))
        out = {}
        for canon in dry["members"]:
            raw = SYMBOLS[canon]
            spec = json.load(open(os.path.join(a.spec_dir, f"symbolspec.{raw}.json")))
            import history_store as HS
            m15, _ = HS.read_doc(canon, "15m", root=HIST_ROOT)
            sc = PT.SpecCost(spec, PT.price_ref(m15["candles"], spec, zone), com.get(canon), zone)
            v = dry["symbols"][canon]
            out[canon] = dict(screen_symbol(sc, v["S"], v["last_slot_mode"]), c_sym=com.get(canon))
        _dump({"meta": {"script": SCRIPT, "kind": "screen (outcome-blind)", "dry": a.dry, "spec_dir": a.spec_dir,
                        "commission": a.commission}, "d_star": dry["d_star"], "end": dry["end"],
                "admitted": [c for c, v in out.items() if v["admitted"]], "symbols": out}, a.out)
        return
    text = G.require_sealed(ROOT, PREREG, TAG)
    scr = json.load(open(a.screen))
    G.require_committed(ROOT, CODE + tuple(_rel(x) for x in (a.screen, scr["meta"]["dry"]) + ((a.after,) if a.after else ())))
    man = G.require_fingerprint(ROOT, text, CODE)
    G.trace_start(ROOT)
    k = READS.index(a.read)
    prior = None
    if k > 0:
        if not a.after:
            raise G.Refused(f"refused: --after <{READS[k - 1]} json> is required")
        prev = json.load(open(a.after))
        if prev["meta"]["read"] != READS[k - 1]:
            raise G.Refused(f"refused: --after is the {prev['meta']['read']} read, not {READS[k - 1]}")
        prior = prev["verdicts"]
    d_star, end = datetime.date.fromisoformat(scr["d_star"]), datetime.date.fromisoformat(scr["end"])
    lo, hi = window(a.read, d_star, end)
    active = [rule for t, rule in TESTS if prior is None or prior.get(t, {}).get("advances")]
    EC = _ec()
    dry = json.load(open(scr["meta"]["dry"]))["summary"]["symbols"]
    rows = {rule: [] for rule in active}
    missing, sizing = {}, {}
    import history_store as HS
    for canon in scr["admitted"]:
        spec = json.load(open(os.path.join(scr["meta"]["spec_dir"], f"symbolspec.{SYMBOLS[canon]}.json")))
        m15, _ = HS.read_doc(canon, "15m", root=HIST_ROOT)
        sc = PT.SpecCost(spec, PT.price_ref(m15["candles"], spec, zone), scr["symbols"][canon]["c_sym"], zone)
        b = _bars(canon, zone, _end_iso(hi - datetime.timedelta(days=1), zone))
        ctx = PT.context(b, dry[canon]["min_bars"], PREV_RULE)
        got, miss = read_rows(b, ctx, lo, hi, sc, active)
        for rule in active:
            rows[rule] += got[rule]
        missing[canon] = miss
        sizing[canon] = owner_sizing(b, ctx, lo, hi, sc, len(scr["admitted"]), active)
    tests = {t: (EC.summarise(rows[rule]) if rule in active else {"n": 0, "retired_unread": True}) for t, rule in TESTS}
    res = {"meta": {"script": SCRIPT, "preregistration": PREREG, "tag": TAG, "read": a.read, "window": [str(lo), str(hi)],
                    "git_head": G.git_head(ROOT), "screen": a.screen, "after": a.after, "active_rules": active,
                    "dataset": G.dataset_snapshot(HIST_ROOT, [(c, tf) for c in scr["admitted"] for tf in ("5m", "15m")]),
                    "specs": {c: G.file_sha256(os.path.join(scr["meta"]["spec_dir"], f"symbolspec.{SYMBOLS[c]}.json"))
                              for c in scr["admitted"]}},
           "tests": tests, "verdicts": verdicts(a.read, tests, prior), "missing_placebo": missing,
           "owner_sizing_report_only": sizing, "by_symbol_year_report_only": by_symbol_year(rows), "rows": rows}
    G.require_covered(man)
    res["meta"].update(code_sha256=man, opened_files=G.opened_files(ROOT))
    _dump(res, a.out)


if __name__ == "__main__":
    main()
