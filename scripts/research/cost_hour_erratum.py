#!/usr/bin/env python3
"""Cost-hour erratum (2026-10-04): re-run every FTMO edge family and the book studies with the spread priced in the table's
own hour frame, next to the legacy frame, and report what changes. DESCRIPTIVE: every window here was already read; the
re-run reads nothing new (each family's own `run` over its own, already-read windows; F6 discovery only, its later reads
stay unread; the F2 forward stage is not run).

    python3 scripts/research/cost_hour_erratum.py all --workdir <scratch dir> --out docs/audits/2026-10-04-cost-hour-erratum.json

The defect: real_costs.spread_price was indexed with a leg's UTC hour, but the table (ExportSymbolSpec.mq5) buckets bars by
server hour minus the server-GMT offset at export (real_costs.HOUR_FRAME). In US standard time every leg read the
neighbouring hour's spread. Both frames run on the SAME code (real_costs.HOUR_FRAME switched per process), so a difference
is the frame and nothing else."""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = "scripts/research/cost_hour_erratum.py"
FRAMES = ("utc_legacy", "server_table")
#: family -> (module file, call). Each call writes one JSON to `out`.
FAMILIES = {
    "census": ("edge_census.py", lambda m, out: m.run(out)),
    "f2_exposed": ("edge_followup.py", lambda m, out: m.run("exposed", out)),
    "f2_history": ("edge_followup.py", lambda m, out: m.run("history", out)),
    "f3": ("edge_f3.py", lambda m, out: m.run(out)),
    "f4": ("edge_f4.py", lambda m, out: m.run(out)),
    "f5": ("edge_f5.py", lambda m, out: m.run(out)),
    "amd": ("edge_amd.py", lambda m, out: m.run(out)),
    "hold": ("edge_hold.py", lambda m, out: m.run(out)),
    "f6_discovery": ("edge_f6.py", lambda m, out: m.run("discovery", out)),
    "a1_vol_schedule": ("vol_schedule.py", lambda m, out: m.run(out)),
    "a3_silver": ("a3_silver.py", lambda m, out: m.run(out, require_clean=False)),
}
#: leaf keys whose change is a VERDICT change (reported in full), not a number moving
VERDICT_KEYS = ("verdict", "bh", "bh_rejected", "candidate", "confirmed", "survives", "pass", "passed", "PROPOSED",
                "variance_not_edge", "decision", "status")


def _module(fname):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    spec = importlib.util.spec_from_file_location(fname[:-3], os.path.join(ROOT, "scripts", "research", fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def one(family, frame, out):
    """Run one family in one frame (one process: the frame is a module global)."""
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import real_costs as RC
    if frame not in FRAMES:
        raise SystemExit(f"unknown frame {frame}")
    RC.HOUR_FRAME = frame
    fname, call = FAMILIES[family]
    if os.path.exists(out):
        os.remove(out)
    call(_module(fname), out)


def _walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out["structure"].append(f"{path}/{k}")
            else:
                _walk(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out["structure"].append(f"{path} len {len(a)} -> {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _walk(x, y, f"{path}[{i}]", out)
    elif isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str) or a is None or b is None:
        if a != b:
            leaf = path.rsplit("/", 1)[-1]
            kind = "verdict" if any(leaf.startswith(k) or leaf == k for k in VERDICT_KEYS) else "other"
            out[kind].append({"path": path, "legacy": a, "fixed": b})
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a != b:
            out["numbers_changed"] += 1
            leaf = path.rsplit("/", 1)[-1]
            if "net" in leaf and "bp" in leaf:
                d = b - a
                if abs(d) > abs(out["max_net_bp_change"]["delta"]):
                    out["max_net_bp_change"] = {"path": path, "legacy": a, "fixed": b, "delta": d}
    elif a != b:
        out["other"].append({"path": path, "legacy": a, "fixed": b})


def diff(legacy, fixed):
    out = {"numbers_changed": 0, "max_net_bp_change": {"path": None, "delta": 0.0}, "verdict": [], "other": [],
           "structure": []}
    _walk(legacy, fixed, "", out)
    out["other"] = out["other"][:40]
    return out


def run_all(workdir, out_path, jobs):
    os.makedirs(workdir, exist_ok=True)
    head = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", "scripts"], capture_output=True,
                           text=True).stdout.strip()
    tasks = [(f, fr, os.path.join(workdir, f"{f}.{fr}.json")) for f in FAMILIES for fr in FRAMES]

    def go(t):
        f, fr, out = t
        log = out + ".log"
        with open(log, "w") as fh:
            r = subprocess.run([sys.executable, "-W", "ignore", os.path.join(ROOT, SCRIPT), "one", "--family", f,
                                "--frame", fr, "--out", out], stdout=fh, stderr=subprocess.STDOUT, cwd=ROOT)
        return t, r.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as ex:
        codes = {t[:2]: rc for t, rc in ex.map(go, tasks)}
    res = {"meta": {"script": SCRIPT, "git_head": head, "scripts_dirty": bool(dirty), "status": "DESCRIPTIVE (re-run of read windows)",
                    "frames": FRAMES, "families": list(FAMILIES), "workdir": workdir}, "families": {}}
    for f in FAMILIES:
        paths = {fr: os.path.join(workdir, f"{f}.{fr}.json") for fr in FRAMES}
        if any(codes[(f, fr)] != 0 or not os.path.exists(p) for fr, p in paths.items()):
            res["families"][f] = {"error": {fr: codes[(f, fr)] for fr in FRAMES}, "logs": [p + ".log" for p in paths.values()]}
            continue
        a, b = (json.load(open(paths[fr])) for fr in FRAMES)
        res["families"][f] = diff(a, b)
    with open(out_path, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    for f, d in res["families"].items():
        if "error" in d:
            print(f, "ERROR", d["error"])
        else:
            print(f, "numbers", d["numbers_changed"], "max net bp", round(d["max_net_bp_change"]["delta"], 3),
                  "verdict flips", len(d["verdict"]))
    print(f"wrote {out_path}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("--family", choices=sorted(FAMILIES), required=True)
    o.add_argument("--frame", choices=FRAMES, required=True)
    o.add_argument("--out", required=True)
    a = sub.add_parser("all")
    a.add_argument("--workdir", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--jobs", type=int, default=8)
    x = ap.parse_args()
    if x.cmd == "one":
        one(x.family, x.frame, x.out)
    else:
        run_all(x.workdir, x.out, x.jobs)


if __name__ == "__main__":
    main()
