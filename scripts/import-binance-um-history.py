#!/usr/bin/env python3
"""Import Binance USDT-M perpetual history (klines + funding rates) from the PUBLIC archive https://data.binance.vision
into the repo's split-gz-year history layout (scripts/history_store.py), checksum-verified.

    python3 scripts/import-binance-um-history.py [--symbols <comma list>] --intervals 5m,1h --funding \
        --root data/history/binance_um [--end-month 2026-09]

--symbols defaults to the crypto market's BACKTESTED list in docs/architecture/instruments.json (scripts/instruments.py);
any symbol given must be on the crypto ANALYSIS allowlist.

Why (docs/plans/2026-10-03-candidates.md; owner 2026-10-03: crypto first): the repo held 4 years of BTC/ETH/SOL at 1H and
one year at 5m -- too short for three clean reads. The archive keeps every USDT-M perp since listing (BTCUSDT 2019-09).

Provenance (CLAUDE.md §7, §10): every monthly zip is verified against the archive's own `.CHECKSUM` (sha256) before it is
parsed; the index records each source file, its sha256, the fetch time and the column meaning. Prices are LAST-TRADE
klines (not bid, not ask): a long and a short both pay the taker fee and cross half the book; research must charge fees +
an explicit spread/slippage assumption. `taker_buy_volume` is real aggressor-side volume (signed flow), point-in-time at the
bar's close. Funding: one row per settlement, `calc_time` (ms) and `last_funding_rate`, known at that time.

Monthly files only (the current, incomplete month is not imported): every stored bar is final. Read-only on the network;
writes only under --root. Refuses (non-zero exit) on a checksum mismatch, an out-of-order bar or a duplicate time."""
import argparse
import csv
import datetime
import gzip
import hashlib
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import instruments as I  # noqa: E402 -- THE allowlist (CLAUDE.md: nothing else may hard-code a symbol list)

BASES = {"um": "https://data.binance.vision/data/futures/um/monthly",
         "spot": "https://data.binance.vision/data/spot/monthly"}
BASE = BASES["um"]
FIRST_MONTH = "2017-08"                         # the earliest spot month; missing months (404) are skipped
UA = {"User-Agent": "trading-decision-system research importer"}
KLINE_COLS = ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count",
              "taker_buy_volume", "taker_buy_quote_volume", "ignore")


class Refused(Exception):
    pass


def _get(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def months(first, last):
    y, m = map(int, first.split("-"))
    ly, lm = map(int, last.split("-"))
    while (y, m) <= (ly, lm):
        yield f"{y:04d}-{m:02d}"
        m += 1
        if m == 13:
            y, m = y + 1, 1


def fetch_verified(url):
    """(bytes, sha256) of a zip whose sha256 matches the archive's .CHECKSUM; None when the month does not exist (404)."""
    try:
        blob = _get(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    want = _get(url + ".CHECKSUM").decode().split()[0].lower()
    got = hashlib.sha256(blob).hexdigest()
    if got != want:
        raise Refused(f"checksum mismatch for {url}: archive says {want}, downloaded {got}")
    return blob, got


def _rows(blob):
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        name = z.namelist()[0]
        text = z.read(name).decode("utf-8")
    for row in csv.reader(io.StringIO(text)):
        if row and row[0] and not row[0][0].isdigit():
            continue                                    # header line (present in newer files)
        if row:
            yield row


def _iso(ts):
    """Archive timestamps are milliseconds, except SPOT files from 2025-01-01 on, which are MICROseconds
    (binance-public-data README). 1e14 separates them for any date after 1973 / before 5138."""
    t = int(ts)
    return datetime.datetime.fromtimestamp(t / (1e6 if t > 10 ** 14 else 1e3), tz=datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _ms(ts):
    t = int(ts)
    return t // 1000 if t > 10 ** 14 else t


def import_klines(sym, interval, root, last_month, market="um", first_month=FIRST_MONTH):
    out_dir = os.path.join(root, f"ohlcv.{sym}.{interval}")
    tmp = out_dir + f".tmp{os.getpid()}"
    os.makedirs(tmp, exist_ok=True)
    sources, years, by_year = [], [], {}
    prev, n = None, 0
    try:
        for mo in months(first_month, last_month):
            url = f"{BASES[market]}/klines/{sym}/{interval}/{sym}-{interval}-{mo}.zip"
            got = fetch_verified(url)
            if got is None:
                continue
            blob, sha = got
            sources.append({"url": url, "sha256": sha})
            for r in _rows(blob):
                t = _ms(r[0])
                if prev is not None and t <= prev:
                    raise Refused(f"{sym} {interval}: bar {_iso(t)} is not after {_iso(prev)} ({url})")
                prev = t
                y = int(_iso(t)[:4])
                by_year.setdefault(y, []).append({
                    "time": _iso(t), "open": float(r[1]), "high": float(r[2]), "low": float(r[3]), "close": float(r[4]),
                    "volume": float(r[5]), "quote_volume": float(r[7]), "trades": int(r[8]),
                    "taker_buy_volume": float(r[9]), "taker_buy_quote_volume": float(r[10])})
                n += 1
            print(f"{sym} {interval} {mo}: ok", flush=True)
        if not n:
            raise Refused(f"{sym} {interval}: nothing in the archive")
        for y, rows in sorted(by_year.items()):
            with gzip.open(os.path.join(tmp, f"{y}.json.gz"), "wt", encoding="utf-8") as fh:
                json.dump({"year": y, "candles": rows}, fh, separators=(",", ":"))
            years.append(y)
        first = by_year[years[0]][0]["time"]
        last = by_year[years[-1]][-1]["time"]
        index = {"symbol": sym, "timeframe": interval, "_format": "split-gz-year-v1", "years": years, "first": first,
                 "last": last, "_bars": n, "_source": f"binance_{market}_public_archive",
                 "_venue": "Binance USDT-M perpetual" if market == "um" else "Binance spot", "market_type": "PERPETUAL" if market == "um" else "SPOT",
                 "_price": "last-trade klines (not bid/ask); charge taker fee + an explicit spread/slippage assumption",
                 "_volume": "volume / taker_buy_volume in base asset: real traded and aggressor-buy volume",
                 "_fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "_months_complete_only": True, "_sources": sources,
                 "_importer": "scripts/import-binance-um-history.py"}
        with open(os.path.join(tmp, "index.json"), "w") as fh:
            json.dump(index, fh, indent=1)
        if os.path.exists(out_dir):
            shutil.rmtree(out_dir)
        os.replace(tmp, out_dir)
        print(f"wrote {out_dir}: {n} bars {first} -> {last}", flush=True)
    finally:
        if os.path.exists(tmp):
            shutil.rmtree(tmp)


def import_funding(sym, root, last_month):
    rows, sources = [], []
    for mo in months("2019-09", last_month):
        url = f"{BASE}/fundingRate/{sym}/{sym}-fundingRate-{mo}.zip"
        got = fetch_verified(url)
        if got is None:
            continue
        blob, sha = got
        sources.append({"url": url, "sha256": sha})
        for r in _rows(blob):
            rows.append({"time": _iso(r[0]), "interval_hours": int(r[1]) if r[1] else None, "rate": float(r[2])})
    rows.sort(key=lambda x: x["time"])
    if any(a["time"] == b["time"] for a, b in zip(rows, rows[1:])):
        raise Refused(f"{sym}: duplicate funding settlement times")
    doc = {"symbol": sym, "_source": "binance_um_public_archive fundingRate", "_sources": sources,
           "_meaning": "rate charged at `time` (settlement) on the position notional: longs pay a positive rate",
           "_fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "_importer": "scripts/import-binance-um-history.py", "rows": rows}
    os.makedirs(root, exist_ok=True)
    p = os.path.join(root, f"funding.{sym}.json.gz")
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print(f"wrote {p}: {len(rows)} settlements {rows[0]['time'] if rows else '-'} -> {rows[-1]['time'] if rows else '-'}")


def import_funding_rest(sym, root, before="2020-01-01T00:00:00Z"):
    """Realized funding BEFORE the archive's first month, from the public REST endpoint /fapi/v1/fundingRate (the archive's
    fundingRate files start 2020-01). Paged by startTime; stored separately (provenance: REST, not archive)."""
    end = int(datetime.datetime.fromisoformat(before.replace("Z", "+00:00")).timestamp() * 1000)
    start, rows = 1546300800000, []                    # 2019-01-01: before every USDT-M listing
    while start < end:
        url = (f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={start}&endTime={end - 1}"
               f"&limit=1000")
        page = json.loads(_get(url))
        if not page:
            break
        for r in page:
            rows.append({"time": _iso(r["fundingTime"]), "rate": float(r["fundingRate"])})
        start = int(page[-1]["fundingTime"]) + 1
        if len(page) < 1000:
            break
    rows.sort(key=lambda x: x["time"])
    doc = {"symbol": sym, "_source": "binance_um_rest /fapi/v1/fundingRate", "_before": before,
           "_meaning": "rate charged at `time` on the position notional: longs pay a positive rate",
           "_fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "_importer": "scripts/import-binance-um-history.py --rest-funding", "rows": rows}
    os.makedirs(root, exist_ok=True)
    p = os.path.join(root, f"funding_rest.{sym}.json.gz")
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    print(f"wrote {p}: {len(rows)} settlements {rows[0]['time'] if rows else '-'} -> {rows[-1]['time'] if rows else '-'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", help="comma list (default: instruments.backtested('crypto'))")
    ap.add_argument("--intervals", default="5m,1h")
    ap.add_argument("--funding", action="store_true")
    ap.add_argument("--root", default="data/history/binance_um")
    ap.add_argument("--market", choices=("um", "spot"), default="um", help="um = USDT-M perpetual (default), spot = spot")
    ap.add_argument("--first-month", default=FIRST_MONTH)
    ap.add_argument("--rest-funding", action="store_true", help="also fetch pre-2020 funding from the REST endpoint")
    ap.add_argument("--end-month", help="last COMPLETE month to import (default: the month before the current one)")
    a = ap.parse_args()
    today = datetime.date.today()
    last = a.end_month or (today.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    syms = a.symbols.split(",") if a.symbols else I.backtested("crypto")
    off = [x for x in syms if x not in I.analysis("crypto")]
    if off:
        print(f"REFUSED: {off} not on the crypto analysis allowlist (docs/architecture/instruments.json)", file=sys.stderr)
        sys.exit(2)
    try:
        for sym in syms:
            for iv in [x for x in a.intervals.split(",") if x]:
                import_klines(sym, iv, a.root, last, a.market, a.first_month)
            if a.funding and a.market == "um":
                import_funding(sym, a.root, last)
            if a.rest_funding:
                import_funding_rest(sym, a.root)
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
