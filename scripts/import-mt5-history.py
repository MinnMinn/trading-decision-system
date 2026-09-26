#!/usr/bin/env python3
"""Turn a deep MT5 export into research history: server time -> UTC, with the zone as a read fact.

    python3 scripts/import-mt5-history.py                 # dry run: report what WOULD be written
    python3 scripts/import-mt5-history.py --write         # write data/history/ohlcv.<SYM>.<TF>.json
    python3 scripts/import-mt5-history.py --write XAUUSD  # one symbol

Reads `data/live/mt5-bridge/history.<SYM>.<TF>.json` (written by integrations/mt5/ExportHistory.mq5, raw
server time, no `Z`) and writes `data/history/ohlcv.<SYM>.<TF>.json` in the same shape every other history
file uses, so `backtest-methods.load()` reads it with no change.

WHY THIS IS A SEPARATE SCRIPT AND NOT PART OF THE EXPORT
--------------------------------------------------------
`ExportOHLCV.mq5` up to v1.02 converted bars with `TimeCurrent() - TimeGMT()` -- the offset *right now*. That
is wrong for any bar across a DST change (audit PAR-5 found it wrong even inside the 600-bar live window, so
v1.03 exports raw server time too and scripts/mt5_time.py converts both), and badly wrong for years of history: an EET broker runs UTC+2 in winter and UTC+3 in
summer, so September's offset applied to a bar from January shifts it by an hour. MQL5 cannot report the
offset that was in force for a historical bar. So the export writes the server's own numbers and the
conversion happens here, where real tzdata exists -- the same machinery `docs/architecture/sessions.json`
already uses for DST.

FOUR REFUSALS, ALL OF THEM DELIBERATE
-------------------------------------
1. **No declared zone, no import.** The zone comes from `providers.json mt5_bridge.server_timezone` and
   nowhere else. There is no default and no `--timezone` flag, because a flag default IS a guess and a wrong
   zone puts a silent one-hour error into every bar of every backtest -- worse than the futures proxy this
   replaces, because that one is labelled.
2. **A different server refuses.** The export records `_server`; if it is not the server the registry names,
   the declared zone is a claim about a different broker and does not apply.
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
"""
import argparse
import datetime
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I      # noqa: E402
import mt5_time as MT        # noqa: E402
import quality as Q          # noqa: E402

SRC_DIR = os.path.join(ROOT, "data", "live", "mt5-bridge")
OUT_DIR = os.path.join(ROOT, "data", "history")
RAW_MARKER = "mt5_bridge_history"
OUT_MARKER = "mt5_bridge_history_utc"


# The zone lookup, the server check and the server-time -> UTC conversion live in scripts/mt5_time.py, shared
# with the live converter (audit PAR-5, ADR 0006) so the same bar gets the same UTC stamp on both paths. This
# importer uses the STRICT conversion (`to_utc`): refusal 4 above is its documented choice.
Refused = MT.Refused
_zone = MT.server_zone
_to_utc = MT.to_utc


def read_export(path):
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    name = os.path.basename(path)
    if raw.get("_source") != RAW_MARKER:
        raise Refused(f"{name}: `_source` is {raw.get('_source')!r}, not {RAW_MARKER!r}. Only the one-shot "
                      f"ExportHistory script's output is convertible here.")
    MT.check_server(raw.get("_server"), name)
    sym, tf = raw.get("symbol"), raw.get("timeframe")
    if sym not in I.analysis(I.market_of(sym) or ""):
        raise Refused(f"{name}: {sym!r} is not on the instrument allowlist "
                      f"(docs/architecture/instruments.json).")
    return raw, sym, tf


def convert(raw, sym, tf, zone_name, zone):
    out = []
    prev = None
    for i, c in enumerate(raw.get("candles") or []):
        t = _to_utc(c["time"], zone, zone_name, f"{sym} {tf} bar {i}")
        if prev is not None and t <= prev:
            raise Refused(f"{sym} {tf}: bar {i} at {t.isoformat()} is not after the previous bar "
                          f"{prev.isoformat()}. Out-of-order bars mean the export is not what it claims.")
        prev = t
        for k in ("open", "high", "low", "close"):
            if c[k] is None:
                raise Refused(f"{sym} {tf}: bar {i} has a null {k}.")
        if not (c["low"] <= c["open"] <= c["high"] and c["low"] <= c["close"] <= c["high"]):
            raise Refused(f"{sym} {tf}: bar {i} is not a valid OHLC bar "
                          f"(o={c['open']} h={c['high']} l={c['low']} c={c['close']}).")
        out.append({"time": t.isoformat().replace("+00:00", "Z"), "open": float(c["open"]),
                    "high": float(c["high"]), "low": float(c["low"]), "close": float(c["close"]),
                    "volume": float(c.get("volume") or 0.0)})
    if not out:
        raise Refused(f"{sym} {tf}: the export contains no candles.")
    return out


def series(raw, sym, tf, candles, zone_name, now=None):
    """The file this writes. Provenance is not decoration: without it a snapshot of a research run reports
    `provider: None`, which is how the Yahoo futures history went unnoticed for as long as it did."""
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat().replace("+00:00", "Z")
    return {
        "symbol": sym,
        "timeframe": tf,
        "last_updated": stamp,
        "_source": OUT_MARKER,
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


def plan(symbols=None):
    rows = []
    for path in sorted(glob.glob(os.path.join(SRC_DIR, "history.*.json"))):
        try:
            raw, sym, tf = read_export(path)
        except Refused as exc:
            rows.append({"path": path, "error": str(exc)}); continue
        if symbols and sym not in symbols:
            continue
        rows.append({"path": path, "raw": raw, "symbol": sym, "timeframe": tf})
    return rows


def main():
    ap = argparse.ArgumentParser(description="Import deep MT5 history into data/history (CLAUDE.md §23.1).")
    ap.add_argument("symbols", nargs="*", help="limit to these symbols (default: every export found)")
    ap.add_argument("--write", action="store_true",
                    help="actually write data/history/ohlcv.<SYM>.<TF>.json (default: report only)")
    ap.add_argument("--allow-partial", action="store_true",
                    help="write even when the §20 check reports PARTIAL (a hole in the series)")
    a = ap.parse_args()

    try:
        zone_name, zone = _zone()
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr); return 2
    print(f"server timezone: {zone_name} (providers.json mt5_bridge.server_timezone)")

    rows = plan(set(a.symbols) or None)
    if not rows:
        print(f"no history.*.json in {os.path.relpath(SRC_DIR, ROOT)} -- run integrations/mt5/ExportHistory.mq5 "
              f"in MetaTrader first (docs/architecture/mt5-history-export.md)")
        return 1

    written, refused, flagged = 0, 0, 0
    replaced = []
    for row in rows:
        name = os.path.basename(row["path"])
        if row.get("error"):
            print(f"  REFUSED {name}: {row['error']}", file=sys.stderr); refused += 1; continue
        sym, tf = row["symbol"], row["timeframe"]
        try:
            candles = convert(row["raw"], sym, tf, zone_name, zone)
            doc = series(row["raw"], sym, tf, candles, zone_name)
            state, why = assess(sym, tf, doc)
        except Refused as exc:
            print(f"  REFUSED {name}: {exc}", file=sys.stderr); refused += 1; continue

        out = os.path.join(OUT_DIR, f"ohlcv.{sym}.{tf}.json")
        prior = None
        if os.path.exists(out):
            try:
                prior = json.load(open(out, encoding="utf-8")).get("_source")
            except (OSError, ValueError):
                prior = "unreadable"
        span = f"{candles[0]['time'][:10]} -> {candles[-1]['time'][:10]}"
        note = f"  {sym:7} {tf:4} {len(candles):>7} bars  {span}  §20 {state}"
        if prior and prior != OUT_MARKER:
            note += f"  [replaces {prior}]"
        print(note)
        if state not in ("FRESH", "STALE"):
            print(f"      §20 {state}: {why}", file=sys.stderr)
            flagged += 1
            if not (state == "PARTIAL" and a.allow_partial):
                print(f"      not written -- pass --allow-partial to accept a series with this state",
                      file=sys.stderr)
                continue
        if not a.write:
            continue
        os.makedirs(OUT_DIR, exist_ok=True)
        tmp = out + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
        os.replace(tmp, out)
        written += 1
        if prior and prior != OUT_MARKER:
            replaced.append(f"{sym} {tf} ({prior})")

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


if __name__ == "__main__":
    sys.exit(main())
