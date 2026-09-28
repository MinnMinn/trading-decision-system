#!/usr/bin/env python3
"""Turn a deep MT5 export into research history: server time -> UTC, with the zone as a read fact.

    python3 scripts/import-mt5-history.py                 # dry run: report what WOULD be written
    python3 scripts/import-mt5-history.py --write         # write data/history/ohlcv.<SYM>.<TF>.json
    python3 scripts/import-mt5-history.py --write XAUUSD  # one symbol

    # a second MT5 server (owner decision 2026-09-28/29, docs/audits/2026-09-29-ftmo-server-timezone.md):
    python3 scripts/import-mt5-history.py --write --provider mt5_bridge_ftmo \\
        --symbol-map data/history/costs/ftmo/symbol-map.json --dest-root data/history/ftmo

Reads `data/live/mt5-bridge/history.<SYM>.<TF>.json` (written by integrations/mt5/ExportHistory.mq5, raw
server time, no `Z`) and writes `data/history/ohlcv.<SYM>.<TF>.json` in the same shape every other history
file uses, so `backtest-methods.load()` reads it with no change.

WHY THIS IS A SEPARATE SCRIPT AND NOT PART OF THE EXPORT
----------------------------------------------------------
`ExportOHLCV.mq5` up to v1.02 converted bars with `TimeCurrent() - TimeGMT()` -- the offset *right now*. That
is wrong for any bar across a DST change (audit PAR-5 found it wrong even inside the 600-bar live window, so
v1.03 exports raw server time too and scripts/mt5_time.py converts both), and badly wrong for years of history: an EET broker runs UTC+2 in winter and UTC+3 in
summer, so September's offset applied to a bar from January shifts it by an hour. MQL5 cannot report the
offset that was in force for a historical bar. So the export writes the server's own numbers and the
conversion happens here, where real tzdata exists -- the same machinery `docs/architecture/sessions.json`
already uses for DST.

FOUR REFUSALS, ALL OF THEM DELIBERATE
-------------------------------------
1. **No declared zone, no import.** The zone comes from `providers.json <provider>.server_timezone` (or a
   named `server_timezone_convention`, scripts/mt5_time.py) and nowhere else. There is no default and no
   `--timezone` flag, because a flag default IS a guess and a wrong zone puts a silent one-hour error into
   every bar of every backtest -- worse than the futures proxy this replaces, because that one is labelled.
2. **A different server refuses.** The export records `_server`; if it is not the server the registry names
   for `--provider`, the declared zone is a claim about a different broker and does not apply.
3. **A timestamp carrying `Z` refuses.** A `Z` is a claim about UTC, and this file's whole premise is that the
   export does not make that claim. A `Z` here means the file came from somewhere else.
4. **A nonexistent local time refuses; an ambiguous one is resolved by the clock and recorded.** At a spring
   transition 03:00-04:00 local does not exist, and at an autumn one a local hour happens twice. An EET
   broker's transition falls on a Sunday, when metals and FX are closed, so neither should appear -- if one
   does, the assumption behind that sentence is wrong and the import should stop rather than pick a branch.

WHAT THIS DOES NOT FIX
----------------------
Tick volume stays tick volume (the broker reports price-change counts, not traded size), and broker history
covers instruments that still exist -- the same survivorship gap crypto has. Both are declared on the
provider, not swept up here.

LARGE FILES (a second provider's M1/M5, ~40 MB to ~600 MB raw)
----------------------------------------------------------------
GitHub rejects a committed file over 100 MB, and a >50 MB single JSON is slow to `json.load()` on every
`backtest-methods.load()` call for a series a scan may touch once. Above `SPLIT_RAW_THRESHOLD_BYTES` (a
proxy on the RAW export's size -- close enough that a converted file's size is never far from it, and cheap
to check before reading anything) the import STREAMS the export line-by-line rather than `json.load()`-ing
the whole file, and writes `data/history/<root>/ohlcv.<SYM>.<TF>/` as an `index.json` plus one gzip part per
UTC calendar year (`stream_write_split()` below). Below the threshold, nothing changes: one `json.load()`,
one plain `ohlcv.<SYM>.<TF>.json`, byte-for-byte the same shape this script has always written.
"""
import argparse
import datetime
import glob
import gzip
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import instruments as I      # noqa: E402
import mt5_time as MT        # noqa: E402
import quality as Q          # noqa: E402

SRC_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
OUT_DIR = os.path.join(ROOT, "data", "history")
RAW_MARKER = "mt5_bridge_history"          # every ExportHistory.mq5 export, any server -- it does not know
                                            # which broker it ran on, so the marker is not server-specific.
OUT_MARKER = "mt5_bridge_history_utc"      # the DEFAULT provider's ("mt5_bridge") written-series marker,
                                            # unchanged from before this file supported a second provider.

# Above this RAW size, stream-convert and split into gz year parts instead of one json.load() + one file.
# A proxy on the SOURCE size rather than the converted size: measuring the converted size first would mean
# reading the whole file anyway, which is exactly the cost this exists to avoid. The converted shape (six
# short keys, no extra whitespace) is never larger than the raw one (six keys plus MQL5's own formatting), so
# a raw file just under this threshold cannot produce a converted file far over 50 MB.
SPLIT_RAW_THRESHOLD_BYTES = 45 * 1024 * 1024
SPLIT_FORMAT = "split-gz-year-v1"


# The zone lookup, the server check and the server-time -> UTC conversion live in scripts/mt5_time.py, shared
# with the live converter (audit PAR-5, ADR 0006) so the same bar gets the same UTC stamp on both paths. This
# importer uses the STRICT conversion (`to_utc`): refusal 4 above is its documented choice.
Refused = MT.Refused
_zone = MT.server_zone
_to_utc = MT.to_utc


def _out_marker(provider):
    """The written-series `_source` marker for `provider`. `f"{provider}_history_utc"` happens to equal the
    long-standing `OUT_MARKER` constant for the default provider ("mt5_bridge" -> "mt5_bridge_history_utc"),
    so this is a generalisation, not a behaviour change, for every existing call site."""
    return f"{provider}_history_utc"


def load_symbol_map(path):
    """`{raw export symbol: canonical instrument symbol}` from a file shaped like
    data/history/costs/ftmo/symbol-map.json (a `map` key). `None` (the default everywhere) means identity --
    the export's own symbol IS the canonical one, which is the only case that existed before a second
    provider needed a translation."""
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    m = doc.get("map")
    if not isinstance(m, dict):
        raise Refused(f"{path}: no `map` object -- expected the shape "
                      f"data/history/costs/ftmo/symbol-map.json uses.")
    return m


def _canonical(raw_sym, symbol_map):
    return (symbol_map or {}).get(raw_sym, raw_sym)


def read_export(path, provider="mt5_bridge", symbol_map=None):
    """Full read (small/test files, and every call site that existed before a second provider). Returns
    (raw, canonical_symbol, timeframe). `provider` and `symbol_map` are additive: neither call site that
    existed before this file supported a second provider passes them, so their defaults reproduce the exact
    behaviour those call sites already depend on."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    name = os.path.basename(path)
    if raw.get("_source") != RAW_MARKER:
        raise Refused(f"{name}: `_source` is {raw.get('_source')!r}, not {RAW_MARKER!r}. Only the one-shot "
                      f"ExportHistory script's output is convertible here.")
    MT.check_server(raw.get("_server"), name, provider=provider)
    raw_sym, tf = raw.get("symbol"), raw.get("timeframe")
    sym = _canonical(raw_sym, symbol_map)
    if sym not in I.analysis(I.market_of(sym) or ""):
        raise Refused(f"{name}: {sym!r} is not on the instrument allowlist "
                      f"(docs/architecture/instruments.json).")
    return raw, sym, tf


def _header_only(path):
    """(header_dict, raw_size_bytes) WITHOUT reading the candles -- for `plan()` deciding stream-vs-in-memory
    on a file that may be hundreds of MB. Trusts ExportHistory.mq5's exact, deterministic layout (every
    header field on its own `"key": value,` line, ending with the literal line `"candles": [`); refuses
    rather than guessing when a file does not match it, same as the rest of this module."""
    size = os.path.getsize(path)
    header_lines = []
    with open(path, encoding="utf-8") as fh:
        first = fh.readline()
        if first.strip() != "{":
            raise Refused(f"{os.path.basename(path)}: first line is {first.strip()[:40]!r}, not the opening "
                          f"`{{` ExportHistory.mq5 always writes -- not an export in the shape this reads.")
        for line in fh:
            if line.strip() == '"candles": [':
                break
            header_lines.append(line)
        else:
            raise Refused(f"{os.path.basename(path)}: no `\"candles\": [` line found before EOF -- not an "
                          f"ExportHistory.mq5 export in the shape this reads.")
    try:
        header = json.loads("{" + "".join(header_lines) + '"candles": []}')
    except ValueError as exc:
        raise Refused(f"{os.path.basename(path)}: header lines did not parse as JSON ({exc}).")
    return header, size


def _stream_candles(path):
    """Yield raw candle dicts from an ExportHistory.mq5 export, one line at a time, never holding the whole
    file in memory. Each candle line (`    {"time": ..., ...},`) is valid JSON on its own once a trailing
    comma is stripped; MQL5 writes exactly one candle per line (ExportHistory.mq5's own `FileWriteString`
    loop), which is what makes this safe rather than a general streaming-JSON parser."""
    with open(path, encoding="utf-8") as fh:
        past_header = False
        for line in fh:
            if not past_header:
                if line.strip() == '"candles": [':
                    past_header = True
                continue
            stripped = line.strip()
            if stripped.startswith("]"):
                return
            if not stripped:
                continue
            if stripped.endswith(","):
                stripped = stripped[:-1]
            try:
                yield json.loads(stripped)
            except ValueError as exc:
                raise Refused(f"{os.path.basename(path)}: a candle line did not parse ({exc}): "
                              f"{stripped[:160]!r}")


def _convert_bar(c, i, sym, tf, zone_name, zone):
    """One raw candle -> the six-key UTC candle dict this repo's history files all use, or Refused. The one
    place per-bar validation happens; `convert()` (in-memory) and the streaming writer both call this so the
    two paths can never drift into checking different things."""
    t = _to_utc(c["time"], zone, zone_name, f"{sym} {tf} bar {i}")
    for k in ("open", "high", "low", "close"):
        if c[k] is None:
            raise Refused(f"{sym} {tf}: bar {i} has a null {k}.")
    if not (c["low"] <= c["open"] <= c["high"] and c["low"] <= c["close"] <= c["high"]):
        raise Refused(f"{sym} {tf}: bar {i} is not a valid OHLC bar "
                      f"(o={c['open']} h={c['high']} l={c['low']} c={c['close']}).")
    return t, {"time": t.isoformat().replace("+00:00", "Z"), "open": float(c["open"]),
               "high": float(c["high"]), "low": float(c["low"]), "close": float(c["close"]),
               "volume": float(c.get("volume") or 0.0)}


def convert(raw, sym, tf, zone_name, zone):
    out = []
    prev = None
    for i, c in enumerate(raw.get("candles") or []):
        t, row = _convert_bar(c, i, sym, tf, zone_name, zone)
        if prev is not None and t <= prev:
            raise Refused(f"{sym} {tf}: bar {i} at {t.isoformat()} is not after the previous bar "
                          f"{prev.isoformat()}. Out-of-order bars mean the export is not what it claims.")
        prev = t
        out.append(row)
    if not out:
        raise Refused(f"{sym} {tf}: the export contains no candles.")
    return out


def series(raw, sym, tf, candles, zone_name, now=None, out_marker=None):
    """The file this writes. Provenance is not decoration: without it a snapshot of a research run reports
    `provider: None`, which is how the Yahoo futures history went unnoticed for as long as it did."""
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat().replace("+00:00", "Z")
    return {
        "symbol": sym,
        "timeframe": tf,
        "last_updated": stamp,
        "_source": out_marker or OUT_MARKER,
        "_server": raw.get("_server"),
        "_server_timezone": zone_name,
        "_server_timezone_source": MT.ZONE_SOURCE,
        "_exported_at_utc": raw.get("_exported_at_utc"),
        "_bars": len(candles),
        "_volume_caveat": "tick_volume, not real traded volume -- the broker counts price changes",
        "_note": ("Broker CFD history converted from raw server time to UTC by scripts/import-mt5-history.py. "
                  "This is the SAME instrument the pilot trades on this venue, which is what makes it a "
                  "better research base than the Yahoo front-month futures it replaces -- but it is this "
                  "account's history, so a move to another broker means re-exporting."),
        "candles": candles,
    }


def assess(sym, tf, doc):
    """§20 on the converted series, before anything is allowed to read it as history."""
    state, why = Q.assess(doc, tf, symbol=sym)
    return state, why


def plan(symbols=None, src_dir=None, provider="mt5_bridge", symbol_map=None, split_threshold=None):
    """Every `history.*.json` export in `src_dir` (default SRC_DIR, unchanged), refused or accepted. Rows for
    a file at or under `split_threshold` (default None -> module SPLIT_RAW_THRESHOLD_BYTES, unchanged) carry
    a full `raw` dict (`read_export()`, unchanged shape a caller can `convert()`/`series()` directly). Rows
    for a larger file carry `header` only (no `raw` key, so the candles are never fully materialised here) --
    `main()` is the only caller that knows what to do with those (`stream_write_split()`); every OTHER
    existing caller (the tests) only ever sees files small enough to stay on the `raw` path with the default
    threshold, so this addition changes nothing for them.

    `split_threshold=0` forces EVERY file onto the split-gz path regardless of size -- the FTMO-Demo dest
    root (`data/history/ftmo`) uses this (owner fix-round-1, 2026-09-29): a public repo must not carry a
    674 MB directory where most of it was plain, uncompressed JSON for series that individually stayed under
    the 45 MB single-file threshold but summed to hundreds of MB. Gzip-per-year for EVERY series, not just
    the biggest ones, is the fix; MetaQuotes-Demo's default run never passes this argument, so its behaviour
    (and every existing small-file test) is unaffected."""
    src_dir = src_dir or SRC_DIR
    threshold = SPLIT_RAW_THRESHOLD_BYTES if split_threshold is None else split_threshold
    rows = []
    for path in sorted(glob.glob(os.path.join(src_dir, "history.*.json"))):
        name = os.path.basename(path)
        size = os.path.getsize(path)
        try:
            if size > threshold:
                header, _ = _header_only(path)
                if header.get("_source") != RAW_MARKER:
                    raise Refused(f"{name}: `_source` is {header.get('_source')!r}, not {RAW_MARKER!r}.")
                MT.check_server(header.get("_server"), name, provider=provider)
                raw_sym, tf = header.get("symbol"), header.get("timeframe")
                sym = _canonical(raw_sym, symbol_map)
                if sym not in I.analysis(I.market_of(sym) or ""):
                    raise Refused(f"{name}: {sym!r} is not on the instrument allowlist "
                                  f"(docs/architecture/instruments.json).")
            else:
                _raw, sym, tf = read_export(path, provider=provider, symbol_map=symbol_map)
                header = _raw
        except Refused as exc:
            rows.append({"path": path, "error": str(exc)}); continue
        if symbols and sym not in symbols:
            continue
        row = {"path": path, "symbol": sym, "timeframe": tf, "size": size, "header": header}
        if size <= threshold:
            row["raw"] = header   # small file: header IS the full raw dict (read_export() read it whole)
        rows.append(row)
    return rows


def _year_part_name(year):
    return f"{year}.json.gz"


def stream_write_split(path, sym, tf, zone_name, zone, dest_root, provider, header):
    """Stream-convert one large export straight to `dest_root/ohlcv.<sym>.<tf>/` (an `index.json` plus one
    gzip part per UTC calendar year), never holding more than one year's candles in memory at once. Returns
    (first_iso, last_iso, total_bars, years, last_candle) or raises Refused (same per-bar checks as
    `convert()`, via `_convert_bar`, so a streamed file cannot pass a check the in-memory path would have
    failed). `last_candle` is what `main()` runs the §20 quality gate against post-write (CLAUDE.md §20/§59:
    a written series must clear the same gate the small-file path always has -- see the call site)."""
    out_dir = os.path.join(dest_root, f"ohlcv.{sym}.{tf}")
    os.makedirs(dest_root, exist_ok=True)
    tmp_dir = out_dir + f".tmp{os.getpid()}"
    os.makedirs(tmp_dir, exist_ok=True)

    year_fh = None
    year_open = None
    year_count = 0
    years = []
    total = 0
    prev_t = None
    first_iso = last_iso = None
    last_row = None
    try:
        for i, c in enumerate(_stream_candles(path)):
            t, row = _convert_bar(c, i, sym, tf, zone_name, zone)
            if prev_t is not None and t <= prev_t:
                raise Refused(f"{sym} {tf}: bar {i} at {t.isoformat()} is not after the previous bar "
                              f"{prev_t.isoformat()}. Out-of-order bars mean the export is not what it claims.")
            prev_t = t
            total += 1
            if first_iso is None:
                first_iso = row["time"]
            last_iso = row["time"]
            last_row = row

            year = t.year
            if year != year_open:
                if year_fh is not None:
                    year_fh.write(b"]}")
                    year_fh.close()
                year_open = year
                years.append(year)
                year_count = 0
                year_fh = gzip.open(os.path.join(tmp_dir, _year_part_name(year)), "wb")
                year_fh.write(f'{{"year": {year}, "candles": ['.encode("utf-8"))
            if year_count:
                year_fh.write(b",")
            year_fh.write(json.dumps(row).encode("utf-8"))
            year_count += 1
        if year_fh is not None:
            year_fh.write(b"]}")
            year_fh.close()
        if total == 0:
            raise Refused(f"{sym} {tf}: the export contains no candles.")

        index = {
            "symbol": sym, "timeframe": tf,
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
            "_source": _out_marker(provider),
            "_server": header.get("_server"),
            "_server_timezone": zone_name,
            "_server_timezone_source": MT.ZONE_SOURCE,
            "_exported_at_utc": header.get("_exported_at_utc"),
            "_bars": total,
            "_volume_caveat": "tick_volume, not real traded volume -- the broker counts price changes",
            "_note": ("Broker CFD history converted from raw server time to UTC by "
                      "scripts/import-mt5-history.py, split into per-UTC-year gzip parts because the "
                      "converted series is large (CLAUDE.md §23.1). See _format/_years."),
            "_format": SPLIT_FORMAT,
            "years": years,
            "first": first_iso,
            "last": last_iso,
        }
        with open(os.path.join(tmp_dir, "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh)
    except BaseException:
        if year_fh is not None:
            try:
                year_fh.close()
            except Exception:
                pass
        _rmtree(tmp_dir)
        raise

    if os.path.isdir(out_dir):
        _rmtree(out_dir)
    os.replace(tmp_dir, out_dir)
    # A prior run of THIS symbol/tf may have written the plain single-file shape (e.g. before a lower
    # split_threshold was chosen for this dest root). `backtest-methods.load()` checks the plain-file path
    # FIRST, so leaving a stale `ohlcv.<sym>.<tf>.json` next to the split dir this call just wrote would make
    # the reader silently serve the OLD, unsplit copy forever -- a duplicate that is not just wasted space
    # but wrong data once the two ever diverge. Removed only AFTER the split dir is safely in place.
    stale_single = out_dir + ".json"
    if os.path.exists(stale_single):
        os.remove(stale_single)
    return first_iso, last_iso, total, years, last_row


def _rmtree(d):
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(description="Import deep MT5 history into data/history (CLAUDE.md §23.1).")
    ap.add_argument("symbols", nargs="*", help="limit to these CANONICAL symbols (default: every export found)")
    ap.add_argument("--write", action="store_true",
                    help="actually write the output series (default: report only)")
    ap.add_argument("--allow-partial", action="store_true",
                    help="write even when the §20 check reports PARTIAL (a hole in the series)")
    ap.add_argument("--provider", default="mt5_bridge",
                    help="docs/architecture/providers.json provider id to read the server/zone from "
                         "(default: mt5_bridge, unchanged)")
    ap.add_argument("--symbol-map", default=None,
                    help="path to a {\"map\": {export_symbol: canonical_symbol}} JSON file "
                         "(default: none -- the export's own symbol is used as-is)")
    ap.add_argument("--src-dir", default=None, help="export folder (default: data/live/mt5-bridge)")
    ap.add_argument("--dest-root", default=None, help="output root (default: data/history)")
    ap.add_argument("--split-threshold-bytes", type=int, default=None,
                    help="raw-file size above which a series is written gz-per-UTC-year split instead of a "
                         "plain single JSON file (default: SPLIT_RAW_THRESHOLD_BYTES, 45 MB, unchanged). "
                         "Pass 0 to split EVERY series regardless of size -- a public-repo dest root where "
                         "no plain, uncompressed multi-MB JSON file should exist at all.")
    a = ap.parse_args()

    try:
        zone_name, zone = _zone(a.provider)
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr); return 2
    print(f"server timezone: {zone_name} (providers.json {a.provider})")

    symbol_map = load_symbol_map(a.symbol_map) if a.symbol_map else None
    src_dir = a.src_dir or SRC_DIR
    dest_root = a.dest_root or OUT_DIR
    out_marker = _out_marker(a.provider)

    rows = plan(set(a.symbols) or None, src_dir=src_dir, provider=a.provider, symbol_map=symbol_map,
                split_threshold=a.split_threshold_bytes)
    if not rows:
        print(f"no history.*.json in {repo_rel(src_dir, ROOT) if src_dir.startswith(ROOT) else src_dir} -- "
              f"run integrations/mt5/ExportHistory.mq5 in MetaTrader first "
              f"(docs/architecture/mt5-history-export.md)")
        return 1

    written, refused, flagged = 0, 0, 0
    replaced = []
    for row in rows:
        name = os.path.basename(row["path"])
        if row.get("error"):
            print(f"  REFUSED {name}: {row['error']}", file=sys.stderr); refused += 1; continue
        sym, tf = row["symbol"], row["timeframe"]

        if "raw" in row:   # small file: unchanged in-memory path
            try:
                candles = convert(row["raw"], sym, tf, zone_name, zone)
                doc = series(row["raw"], sym, tf, candles, zone_name, out_marker=out_marker)
                state, why = assess(sym, tf, doc)
            except Refused as exc:
                print(f"  REFUSED {name}: {exc}", file=sys.stderr); refused += 1; continue
            first, last, n = candles[0]["time"][:10], candles[-1]["time"][:10], len(candles)
            out_path = os.path.join(dest_root, f"ohlcv.{sym}.{tf}.json")
            prior_marker = _prior_marker(out_path)
            note = f"  {sym:7} {tf:4} {n:>9} bars  {first} -> {last}  §20 {state}"
            if prior_marker and prior_marker != out_marker:
                note += f"  [replaces {prior_marker}]"
            print(note)
            if state not in ("FRESH", "STALE"):
                print(f"      §20 {state}: {why}", file=sys.stderr)
                flagged += 1
                if not (state == "PARTIAL" and a.allow_partial):
                    print("      not written -- pass --allow-partial to accept a series with this state",
                          file=sys.stderr)
                    continue
            if not a.write:
                continue
            os.makedirs(dest_root, exist_ok=True)
            tmp = out_path + f".tmp{os.getpid()}"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            os.replace(tmp, out_path)
            written += 1
            if prior_marker and prior_marker != out_marker:
                replaced.append(f"{sym} {tf} ({prior_marker})")
            continue

        # large file: stream-convert + gz-year-split, dry-run still validates every bar (no candles written)
        if not a.write:
            try:
                # A dry run still proves the file converts (every bar checked) without writing anything.
                n = sum(1 for _ in _stream_and_validate(row["path"], sym, tf, zone_name, zone))
                print(f"  {sym:7} {tf:4} {n:>9} bars  (large -- would split into per-year gz parts)")
            except Refused as exc:
                print(f"  REFUSED {name}: {exc}", file=sys.stderr); refused += 1
            continue
        prior_marker = _prior_marker_any(dest_root, sym, tf)   # read BEFORE the write replaces it (below)
        try:
            first, last, n, years, last_row = stream_write_split(
                row["path"], sym, tf, zone_name, zone, dest_root, a.provider, row["header"])
        except Refused as exc:
            print(f"  REFUSED {name}: {exc}", file=sys.stderr); refused += 1; continue
        # §20 gate, post-write -- CLAUDE.md §59: a series this importer writes must clear the same gate the
        # small-file path always has. `_structural_fault`/continuity were already enforced bar-by-bar during
        # streaming (a violation would have raised Refused above, before any file existed), and this account's
        # CFD symbols are not `I.is_continuous()` so `assess()`'s only remaining question is freshness --
        # answered from `last_row` (the true last converted bar) rather than materialising the whole series
        # again just to hand it to assess().
        state, why = assess(sym, tf, {"candles": [last_row], "last_updated": last, "_bars": n})
        out_dir = os.path.join(dest_root, f"ohlcv.{sym}.{tf}")
        note = f"  {sym:7} {tf:4} {n:>9} bars  {first[:10]} -> {last[:10]}  §20 {state}  " \
               f"split into {len(years)} gz year part(s)"
        if prior_marker and prior_marker != out_marker:
            note += f"  [replaces {prior_marker}]"
        if state not in ("FRESH", "STALE"):
            print(note)
            print(f"      §20 {state}: {why}", file=sys.stderr)
            flagged += 1
            if not (state == "PARTIAL" and a.allow_partial):
                print("      not written -- pass --allow-partial to accept a series with this state",
                      file=sys.stderr)
                _rmtree(out_dir)
                continue
        print(note)
        written += 1
        if prior_marker and prior_marker != out_marker:
            replaced.append(f"{sym} {tf} ({prior_marker})")

    if not a.write:
        print("\ndry run -- nothing written. Re-run with --write to replace the research history.")
    else:
        print(f"\nwrote {written} series"
              + (f", {refused} refused" if refused else "")
              + (f", {flagged} flagged by §20" if flagged else ""))
        if replaced:
            print("REPLACED a different provider's series for: " + ", ".join(replaced))
            print("Every backtest and ranking built on those symbols is now STALE and must be re-run "
                  "(CLAUDE.md §59: this changes historical research semantics). instruments.json's "
                  "`_cfd_backtested_caveat` and the §23.1 notes describe the OLD source until that happens.")
    return 0 if refused == 0 else 2


def _stream_and_validate(path, sym, tf, zone_name, zone):
    """Like `_stream_candles()` but validated + converted, for a dry-run bar count with no disk writes."""
    prev = None
    for i, c in enumerate(_stream_candles(path)):
        t, row = _convert_bar(c, i, sym, tf, zone_name, zone)
        if prev is not None and t <= prev:
            raise Refused(f"{sym} {tf}: bar {i} at {t.isoformat()} is not after the previous bar "
                          f"{prev.isoformat()}. Out-of-order bars mean the export is not what it claims.")
        prev = t
        yield row


def _prior_marker(out_path):
    if not os.path.exists(out_path):
        return None
    try:
        return json.load(open(out_path, encoding="utf-8")).get("_source")
    except (OSError, ValueError):
        return "unreadable"


def _prior_marker_any(dest_root, sym, tf):
    """Like `_prior_marker()`, but shape-aware: a prior import over this (symbol, timeframe) may have written
    either the plain-file shape or a split-gz directory (e.g. a `--split-threshold-bytes` change between two
    runs, exactly what happened for the FTMO dest root, docs/audits/2026-09-29-ftmo-history-coverage.md
    'Fix round 1'). Checked BEFORE the write: `stream_write_split()` replaces/removes whichever shape was
    there, so the prior marker must be read first or there is nothing left to read it from."""
    plain = _prior_marker(os.path.join(dest_root, f"ohlcv.{sym}.{tf}.json"))
    if plain is not None:
        return plain
    split_index = os.path.join(dest_root, f"ohlcv.{sym}.{tf}", "index.json")
    if not os.path.exists(split_index):
        return None
    try:
        return json.load(open(split_index, encoding="utf-8")).get("_source")
    except (OSError, ValueError):
        return "unreadable"


if __name__ == "__main__":
    sys.exit(main())
