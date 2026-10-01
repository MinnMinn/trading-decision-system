#!/usr/bin/env python3
"""Hosted-runner speed benchmark for the fund-search shard layout (docs/audits/2026-10-01-shard-calibration.md section 6).

Runs a FIXED small set of scripts/research/shard_calibration.py jobs (one-year S3 slice, XAUUSD, baseline value sets; counts
and seconds only, no R) and prints seconds and the implied runner-speed factor against the reference-machine seconds the
shard model was calibrated on. Writes one JSON (`--out`, outside the checkout). The owner commits it as
docs/audits/2026-10-01-runner-benchmark.json and sets SHARD_MODEL["layout_factor"] to its `layout_factor`; `fund-search.py
declare` records its sha256 and notes when it is absent or differs.

    python3 scripts/research/runner_benchmark.py --out "$RUNNER_TEMP/runner-benchmark.json"
"""
import argparse
import json
import math
import os
import platform
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CAL = os.path.join(HERE, "shard_calibration.py")
S3 = "2023-03-01T00:00:00Z"
#: reference-machine seconds (Apple M3 Pro, docs/audits/2026-10-01-shard-calibration-data/res-A,C,F,D): the mean of the repeated runs
#: of the same job; (what, job spec, reference seconds, key of the seconds field in the job result)
JOBS = [
    ("ict_5m_1worker", {"kind": "scan", "method": "ict", "symbol": "XAUUSD", "tf": "5m", "slice": "S3", "sets": ["base"]}, 85.4, "seconds"),
    ("wyckoff_5m_1worker", {"kind": "scan", "method": "wyckoff", "symbol": "XAUUSD", "tf": "5m", "slice": "S3", "sets": ["base"]}, 21.9, "seconds"),
    ("ict_5m_4workers", {"kind": "scan_dev", "method": "ict", "symbol": "XAUUSD", "tf": "5m", "dev_start": S3, "workers": 4, "sets": ["base"]}, 28.1, "seconds"),
    ("wyckoff_5m_4groups_4workers", {"kind": "scan_dev", "method": "wyckoff", "symbol": "XAUUSD", "tf": "5m", "dev_start": S3, "workers": 4,
                                     "sets": ["w1:0", "w1:2", "w1:3", "w1:4"]}, 44.5, "seconds"),
    ("load_1m_series", {"kind": "load", "symbol": "XAUUSD", "tf": "1m"}, 9.3, "load_s"),
]
# the 1-worker and 4-worker ICT rows also give the parallel efficiency actually seen on the runner
REF_4W_SPEEDUP = 77.8 / 28.1


def run(spec):
    t0 = time.time()
    p = subprocess.run([sys.executable, CAL, "job", json.dumps(spec)], capture_output=True, text=True)
    line = [l for l in p.stdout.splitlines() if l.startswith("{")]
    if p.returncode != 0 or not line:
        return {"status": "ERROR", "wall_s": round(time.time() - t0, 1), "stderr": p.stderr[-400:]}
    return json.loads(line[-1])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    rows = []
    for name, spec, ref, key in JOBS:
        r = run(spec)
        ok = r.get("status") == "OK"
        sec = r.get(key) if ok else None
        rows.append({"job": name, "spec": spec, "reference_s": ref, "seconds": sec, "status": r.get("status"),
                     "factor": round(sec / ref, 3) if sec else None})
        print(f"{name:<30} runner {sec} s   reference {ref} s   factor {rows[-1]['factor']}", flush=True)
    fs = [r["factor"] for r in rows if r["factor"]]
    one = [r["factor"] for r in rows if r["job"].endswith("1worker") and r["factor"]]
    # the layout factor: the WORST single-process factor, rounded UP to the next 0.25 (a slower runner needs the smaller shards)
    lay = math.ceil(max(one) * 4) / 4 if one and len(one) == 2 else None
    out = {"layout_factor": lay, "factors": rows, "all_ok": len(fs) == len(JOBS),
           "python": platform.python_version(), "machine": platform.platform(), "cpu_count": os.cpu_count(),
           "note": "factor = runner seconds / reference-machine (Apple M3 Pro) seconds; layout_factor = worst single-process factor "
                   "rounded up to 0.25; the 4-worker rows show the parallel speed-up on this runner (reference "
                   f"{REF_4W_SPEEDUP:.2f}x for ICT)"}
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: out[k] for k in ("layout_factor", "all_ok")}))
    return 0 if out["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
