#!/usr/bin/env python3
"""Import one FRED daily series (e.g. DGS10, the 10-year Treasury constant-maturity yield) as a dated JSON with provenance.

    python3 scripts/import-fred-series.py --series DGS10 --root data/history/fred

Point-in-time note (CLAUDE.md §8): FRED's DGS10 `date` is the OBSERVATION date. The Federal Reserve H.15 release ("posted
daily Monday through Friday at 4:15pm", federalreserve.gov/releases/h15) posts day d's value on the NEXT Board business day, so
a decision at time t may use d only when that posting day is on or before t. The reader enforces nothing; the research code
must apply the lag (scripts/research/edge_m1.py BoardCalendar; docs/plans/2026-10-03-edge-m1-month-end-preregistration.md
[M1-A1]). Missing days ('.') are
kept as null, never filled. Later revisions are not tracked (the vintage is the fetch time, recorded)."""
import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import urllib.request

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--series", required=True)
    ap.add_argument("--root", default="data/history/fred")
    a = ap.parse_args()
    url = URL.format(sid=a.series)
    blob = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research importer"}), timeout=60).read()
    rows = []
    for r in csv.DictReader(io.StringIO(blob.decode("utf-8"))):
        date = r.get("observation_date") or r.get("DATE")
        v = r.get(a.series)
        rows.append({"date": date, "value": None if v in (None, "", ".") else float(v)})
    rows.sort(key=lambda x: x["date"])
    if any(x["date"] == y["date"] for x, y in zip(rows, rows[1:])):
        raise SystemExit("duplicate dates in the FRED file")
    os.makedirs(a.root, exist_ok=True)
    doc = {"series": a.series, "_source": url, "_sha256_of_download": hashlib.sha256(blob).hexdigest(),
           "_fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "_pit": "`date` is the observation date; H.15 posts it at 16:15 ET on the NEXT Board business day",
           "_importer": "scripts/import-fred-series.py", "rows": rows}
    p = os.path.join(a.root, f"{a.series}.json")
    json.dump(doc, open(p, "w"), indent=0)
    print(f"wrote {p}: {len(rows)} rows {rows[0]['date']} -> {rows[-1]['date']}")


if __name__ == "__main__":
    main()
