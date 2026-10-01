#!/usr/bin/env python3
"""Trade-COUNT measurement for the fund-search pre-registration (docs/audits/2026-10-01-trade-rates.md).

Counts ONLY: the number of ADMITTED trades (BtEngine.trades_for of scripts/fund-search.py: scan_many + simulate with
min_rr, real FTMO costs, flat-before-rollover, all adopted F keys) that the BASELINE value set produces per
(method, symbol, timeframe) in one-year slices of the development window. It never reads, prints or stores R,
any performance figure. Nothing here selects, evaluates or changes any engine/harness/grid/threshold.

Slice mechanics: the harness engine (BtEngine) is used unmodified on a PIT-truncated series that is cut to
[slice_start - WARMUP_DAYS - scan-spec bars, slice_end + FORWARD_DAYS]. Only trades whose ENTRY label lies in
[slice_start, slice_end) are counted. The cut is applied by wrapping `bt.load` for the ONE (symbol, timeframe) being
scanned (other timeframes, e.g. HTF reads, are untouched); the DEV_CUTOFF PIT cut of the harness still applies first.

    python3 scripts/research/trade_rates.py run   --out /tmp/b10-results.jsonl [--workers 4] [--timeout 3600]
    python3 scripts/research/trade_rates.py job   '{"method":"ict","symbol":"US500","tf":"30m","slice":"S1"}'
Needs BT_HISTORY_ROOT=data/history/ftmo.
"""
import argparse
import bisect
import concurrent.futures
import datetime
import importlib.util
import json
import math
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

SLICES = {"S1": ("2021-03-01T00:00:00Z", "2022-03-01T00:00:00Z"),
          "S2": ("2022-03-01T00:00:00Z", "2023-03-01T00:00:00Z"),
          "S3": ("2023-03-01T00:00:00Z", "2024-03-01T00:00:00Z")}   # S3 = the last dev year (final test fold)
WARMUP_DAYS = 14        # settles simulate()'s one-at-a-time state before the slice; on top of the method's scan window
FORWARD_DAYS = 5        # forward-walk bars after the slice end (flat-before-rollover closes every trade intraday)
SYMBOLS = {"metals": ("XAUUSD", "XAGUSD"), "indices": ("US500", "US30", "USTEC", "DE40", "FRA40")}
NEW_SYMBOLS = {"metals": ("XPTUSD", "XPDUSD"),
               "indices": ("UK100", "EU50", "JP225", "HK50", "AUS200", "US2000", "SPN35", "N25")}   # b16: enlarged cells
METALS_ALL = SYMBOLS["metals"] + NEW_SYMBOLS["metals"]
TFS = ("1m", "5m", "15m", "30m")
METHODS = ("ict", "wyckoff")


def _fs():
    spec = importlib.util.spec_from_file_location("fund_search", os.path.join(ROOT, "scripts", "fund-search.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fund_search"] = mod
    spec.loader.exec_module(mod)
    return mod


def _shift(iso, days):
    d = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    return (d + datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_job(job):
    fs = _fs()
    method, sym, tf, sl = job["method"], job["symbol"], job["tf"], job["slice"]
    start, end = SLICES[sl]
    grids, _ = fs.load_grids()
    grid = grids[method].runnable()
    bt = fs._load_bt()
    runner = fs.METHODS[method]
    real_load = bt.load
    info = {}

    def sliced(s, t):
        c, src = real_load(s, t)
        if (s, t) != (sym, tf) or not c:
            return c, src
        times = [x["time"] for x in c]
        spec_bars = bt.lr.scan_spec(tf)[0] if method == "ict" else bt._wy_window(sym, tf, len(c))
        i0 = bisect.bisect_left(times, _shift(start, -WARMUP_DAYS)) - spec_bars
        i1 = bisect.bisect_left(times, _shift(end, FORWARD_DAYS))
        info["first_bar"], info["last_bar"] = times[0], times[-1]
        if i0 < 0 or times[0] > start:
            info["no_data"] = True
            i0 = max(i0, 0)
        i1 = max(i1, i0 + 1)
        info["slice_bars"] = i1 - i0
        return c[i0:i1], src

    bt.load = sliced
    t0 = time.time()
    eng = fs.BtEngine(grid, runner, tf, [sym], bt=bt, workers=1)
    if info.get("no_data"):
        return dict(job, status="NO_DATA", reason=f"series starts {info.get('first_bar')}: not enough history for "
                    f"warm-up + slice", bars=info.get("slice_bars"), seconds=round(time.time() - t0, 1))
    taken = eng.trades_for(grid.baseline())
    n = sum(1 for t in taken if start <= t["entry_time"] < end)
    return dict(job, status="OK", trades=n, bars=info["slice_bars"], seconds=round(time.time() - t0, 1),
                workers=1, first_bar=info["first_bar"])


def all_jobs(symbols=None, tfs=None):
    """Default = the b10 set (7 symbols x 4 timeframes). `symbols` / `tfs` (b16) restrict or extend it to any list of
    symbols (asset class looked up in SYMBOLS / NEW_SYMBOLS) and timeframes."""
    jobs = []
    for tf in (tfs or TFS):
        for ac in ("metals", "indices"):
            for sym in (SYMBOLS[ac] + NEW_SYMBOLS[ac] if symbols else SYMBOLS[ac]):
                if symbols and sym not in symbols:
                    continue
                for m in METHODS:
                    for sl in SLICES:
                        jobs.append(dict(method=m, symbol=sym, tf=tf, slice=sl))
    return jobs


def _key(j):
    return (j["method"], j["symbol"], j["tf"], j["slice"])


def drive(out, workers, timeout, only_tf=None, symbols=None, tfs=None):
    done = set()
    if os.path.exists(out):
        with open(out) as fh:
            done = {_key(json.loads(l)) for l in fh if l.strip()}
    jobs = [j for j in all_jobs(symbols, tfs) if _key(j) not in done and (not only_tf or j["tf"] in only_tf)]
    order = {"1m": 0, "5m": 1, "15m": 2, "30m": 3}
    jobs.sort(key=lambda j: (order[j["tf"]], j["symbol"] not in METALS_ALL))   # heaviest first
    print(f"{len(jobs)} jobs, {workers} processes", flush=True)
    fh_out = open(out, "a")

    def one(j):
        t0 = time.time()
        try:
            p = subprocess.run([sys.executable, os.path.abspath(__file__), "job", json.dumps(j)],
                               capture_output=True, text=True, timeout=timeout)
            line = [l for l in p.stdout.splitlines() if l.startswith("{")]
            if p.returncode != 0 or not line:
                return dict(j, status="ERROR", seconds=round(time.time() - t0, 1), reason=p.stderr.strip()[-400:])
            return json.loads(line[-1])
        except subprocess.TimeoutExpired:
            return dict(j, status="NOT_MEASURED", seconds=round(time.time() - t0, 1),
                        reason=f"exceeded {timeout}s for one (method,symbol,slice)")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(one, jobs):
            fh_out.write(json.dumps(res) + "\n")
            fh_out.flush()
            print(json.dumps(res), flush=True)


N_REQ = {"ict": 760, "wyckoff": 690}     # coordinator's model (labelled assumption): pooled TEST trades for a 0.20R edge
FOLDS = {("1m", "metals"): 9, ("5m", "metals"): 17, ("15m", "metals"): 17, ("30m", "metals"): 17}   # plan --dry-run
STRUCTURAL_MIN_YEARS = 4                 # training >= 730 d + 2 test folds of 365 d
DESIGN_EFFECT = 2


def _folds(tf, ac):
    return FOLDS.get((tf, ac), 4)


def coverage(out, symbols=None, tfs=None):
    """In-slice bar counts per (symbol, timeframe, slice) from the PIT-truncated series (a data-availability fact: the
    early index history is sparse, so a slice can be only partly covered). Writes JSON {sym|tf|slice: bars}."""
    fs = _fs()
    bt = fs._load_bt()
    bt.pit_cutoff(fs.FS.DEV_CUTOFF)
    res = {}
    for tf in (tfs or TFS):
        for ac in SYMBOLS:
            for sym in (SYMBOLS[ac] + NEW_SYMBOLS[ac] if symbols else SYMBOLS[ac]):
                if symbols and sym not in symbols:
                    continue
                c, _ = bt.load(sym, tf)
                times = [x["time"] for x in c]
                for sl, (a, b) in SLICES.items():
                    res[f"{sym}|{tf}|{sl}"] = bisect.bisect_left(times, b) - bisect.bisect_left(times, a)
                print(sym, tf, flush=True)
    with open(out, "w") as fh:
        json.dump(res, fh, indent=1)


def report(path, cov_path=None):
    """Markdown tables from the results JSONL (+ coverage JSON): COUNTS, bars and seconds only."""
    rows = {}
    with open(path) as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows[(r["method"], r["symbol"], r["tf"], r["slice"])] = r
    cov = json.load(open(cov_path)) if cov_path else {}

    def cov_of(sym, tf, sl):
        return cov.get(f"{sym}|{tf}|{sl}")

    def complete(sym, tf, sl):
        """>= 90 % of the best-covered slice of this (symbol, timeframe)."""
        if not cov:
            return True
        best = max(cov_of(sym, tf, s) for s in SLICES)
        return cov_of(sym, tf, sl) >= 0.9 * best

    def cell_txt(r):
        if r is None:
            return "missing", ""
        if r["status"] != "OK":
            return r["status"], f"{r['status']}: {r.get('reason', '')}"
        return str(r["trades"]), f"{r['seconds']:.0f}"

    def span(y):
        return 2 + max(2, math.ceil(y - 1e-9))

    out = []
    for m in METHODS:
        out.append(f"\n#### {m.upper()}: admitted trades per one-year slice, bars scanned (incl. warm-up + forward), "
                   f"seconds per run\n")
        out.append("| cell | symbol | S1 trades | S2 trades | S3 trades | in-slice bars S1/S2/S3 | bars scanned S1 | S1 s | S2 s | S3 s |")
        out.append("|---|---|---|---|---|---|---|---|---|---|")
        for tf in TFS:
            for ac in ("metals", "indices"):
                pooled = {s: 0 for s in SLICES}
                for sym in SYMBOLS[ac]:
                    rs = {s: rows.get((m, sym, tf, s)) for s in SLICES}
                    t = {s: cell_txt(rs[s]) for s in SLICES}
                    for s in SLICES:
                        if rs[s] is not None and rs[s]["status"] == "OK":
                            pooled[s] += rs[s]["trades"]
                    cv = "/".join(str(cov_of(sym, tf, s)) for s in SLICES) if cov else ""
                    flag = "".join(f" {s}*" for s in SLICES if cov and not complete(sym, tf, s))
                    bars = rs["S1"]["bars"] if rs["S1"] and rs["S1"].get("bars") else ""
                    out.append(f"| {tf}-{ac} | {sym} | " + " | ".join(t[s][0] for s in SLICES) + f" | {cv}{flag} | {bars} | "
                               + " | ".join(t[s][1] for s in SLICES) + " |")
                out.append(f"| **{tf}-{ac}** | **pooled** | " + " | ".join(f"**{pooled[s]}**" for s in SLICES)
                           + " | | | | | |")
    out.append("\n`*` after a slice = that symbol's in-slice bars are < 90 % of its best-covered slice (partial data; "
               "its count is a lower bound).\n")
    out.append("#### Derived years of TEST history (MODEL)\n")
    out.append("rate = mean pooled trades/yr over the slices in which EVERY symbol of the cell is fully covered (all three "
               "for metals). years = n_req / rate; 2x = design effect 2. test folds needed = max(2, ceil(years)); min "
               "total span = 2 (training >= 730 d) + test folds needed.\n")
    out.append("| method | cell | slices used | pooled S1/S2/S3 | rate /yr | n_req | years (1x) | years (2x) | test folds now | "
               "expected TEST trades now | >= n_req? | >= 2x n_req? | min total span yrs (1x / 2x) |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m in METHODS:
        for tf in TFS:
            for ac in ("metals", "indices"):
                pool, used, names = [], [], []
                for s in SLICES:
                    v = 0
                    for sym in SYMBOLS[ac]:
                        r = rows.get((m, sym, tf, s))
                        v = None if (v is None or r is None or r["status"] != "OK") else v + r["trades"]
                    pool.append(v)
                    if v is not None and all(complete(sym, tf, s) for sym in SYMBOLS[ac]):
                        used.append(v)
                        names.append(s)
                if not used:
                    out.append(f"| {m} | {tf}-{ac} | none | {pool} | NOT MEASURED | | | | {_folds(tf, ac)} | | | | |")
                    continue
                rate = sum(used) / len(used)
                nreq = N_REQ[m]
                folds = _folds(tf, ac)
                exp = rate * folds
                y1, y2 = nreq / rate, DESIGN_EFFECT * nreq / rate
                out.append(f"| {m} | {tf}-{ac} | {','.join(names)} | {pool[0]}/{pool[1]}/{pool[2]} | {rate:.1f} | {nreq} | "
                           f"{y1:.1f} | {y2:.1f} | {folds} | {exp:.0f} | {'yes' if exp >= nreq else 'no'} | "
                           f"{'yes' if exp >= DESIGN_EFFECT * nreq else 'no'} | {span(y1)} / {span(y2)} |")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    rp = sub.add_parser("report")
    rp.add_argument("--in", dest="inp", required=True)
    rp.add_argument("--cov")
    cp = sub.add_parser("coverage")
    cp.add_argument("--out", required=True)
    cp.add_argument("--symbols", nargs="*")
    cp.add_argument("--tfs", nargs="*")
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--timeout", type=int, default=3600)
    r.add_argument("--tf", nargs="*")
    r.add_argument("--symbols", nargs="*", help="b16: restrict/extend the job set to these symbols (old or NEW_SYMBOLS)")
    r.add_argument("--tfs", nargs="*", help="b16: timeframes of the job set (default 1m 5m 15m 30m)")
    j = sub.add_parser("job")
    j.add_argument("spec")
    a = ap.parse_args(argv)
    if a.cmd == "report":
        print(report(a.inp, a.cov))
    elif a.cmd == "coverage":
        coverage(a.out, a.symbols, a.tfs)
    elif a.cmd == "job":
        print(json.dumps(run_job(json.loads(a.spec))))
    else:
        drive(a.out, a.workers, a.timeout, a.tf, a.symbols, a.tfs)


if __name__ == "__main__":
    main()
