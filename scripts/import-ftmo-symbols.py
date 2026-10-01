#!/usr/bin/env python3
"""Validate an FTMO symbol-universe import and PROPOSE (never silently apply) the registry additions.

    # 1. after integrations/mt5/ExportSymbolList.mq5 (BEFORE any history is exported or imported):
    python3 scripts/import-ftmo-symbols.py --symbol-list /path/to/symbollist.<server>.json
    # 2. after ExportHistory + import-mt5-history.py + ExportSymbolSpec (verify what arrived):
    python3 scripts/import-ftmo-symbols.py --symbol-list ... --require-history
    # 3. apply the reviewed proposal (backup first; OFF unless asked):
    python3 scripts/import-ftmo-symbols.py --symbol-list ... --apply
    # no ExportSymbolList at hand (re-check what is already in the repo):
    python3 scripts/import-ftmo-symbols.py

Outputs (default `--out` = <system tmp>/import-ftmo-symbols, i.e. OUTSIDE the git tree):
    report.md / report.json        per-symbol validation
    registry.patch.json            RFC 6902 `add` ops for docs/architecture/instruments.json   (NOT applied)
    symbol-map.patch.json          RFC 6902 `add` ops for data/history/costs/ftmo/symbol-map.json (NOT applied)
    registry.diff / symbol-map.diff  unified diffs of exactly what --apply would write
Exit code: 0 = no ERROR among the selected symbols, 1 = at least one ERROR, 2 = bad usage / unreadable input.

WHAT IT CHECKS, PER SYMBOL
  * asset class from the symbol's MT5 path head (Forex->fx, Indices->indices, Metals->metals, Energies->energies,
    Crypto->crypto; everything else -> `other`, listed under "unmapped classes" and EXCLUDED from every proposal);
  * canonical name: `existing symbol-map.json entry` > `--override` > known alias (US100->USTEC, GER40->DE40: the two
    renames the repo's own map evidences) > strip `.cash` > identity. A canonical name that is not [A-Z0-9_]+ is
    REFUSED, not sanitised (the on-disk name is `ohlcv.<SYM>.<TF>`, a dot would be ambiguous). Two raw names that
    resolve to one canonical name, or one that lands on a Binance registry name, are ERRORs that block both;
  * which of the 8 timeframes (1m 5m 15m 30m 1H 4H 1D 1W) exist; 1m/5m/15m are the fund-search DECISION frames
    (missing -> ERROR), the other five are higher-timeframe context (missing -> WARN);
  * per series: bar count, first/last, duplicate or non-monotone timestamps and broken OHLC (INVALID -- the same
    definition as scripts/quality.py `_structural_fault`, reused), holes (a gap above 4 days intraday / 5 days 1D /
    15 days 1W is a `long_gap` WARN; weekends and the usual holidays are below it), split-index vs actual count;
  * the cost spec (symbolspec.<raw>.json): present, swap_mode == 1 (scripts/real_costs.py refuses any other),
    recorded M15 spread present, commission status (never guessed: `no_deals` is reported as unknown);
  * history depth vs the first-bar dates ExportSymbolList recorded BEFORE the export.

NOT EQUIVALENT (disclosed in every report): the Binance USDT history under data/history/ohlcv.*USDT.* is spot data
with different costs and hours; it is never read here and must never stand in for an FTMO crypto CFD.

--apply writes ONLY `add` ops for symbols with no ERROR, never touches `execution`, `backtested` or
`estate_capacity` (analysis != execution, instruments.json `_policy`), backs both files up into <out>/backup/, and
refuses outright while any ERROR exists. After it, run `python3 scripts/sync-instruments.py --write` (the derived
schema enums) and the registry tests.
"""
import argparse
import copy
import datetime
import difflib
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import history_store as HS   # noqa: E402 -- the one reader of the on-disk layout (resolve())
import quality as Q          # noqa: E402 -- _structural_fault: the repo's own INVALID definition

TOOL = "scripts/import-ftmo-symbols.py"
DECISION_TFS = ("1m", "5m", "15m")                       # owner 2026-09-28: the fund search's decision frames
CONTEXT_TFS = ("30m", "1H", "4H", "1D", "1W")            # higher-timeframe context, as the existing 7 symbols have
ALL_TFS = DECISION_TFS + CONTEXT_TFS

PATH_CLASS = {"forex": "fx", "indices": "indices", "metals": "metals", "energies": "energies", "crypto": "crypto"}
VALID_CLASSES = ("fx", "indices", "metals", "energies", "crypto")
OTHER = "other"
#: The only two renames the repo evidences (data/history/costs/ftmo/symbol-map.json). Anything else is `--override`.
KNOWN_ALIASES = {"US100": "USTEC", "GER40": "DE40"}
CANON_RE = re.compile(r"^[A-Z0-9_]{2,24}$")
#: A gap above this is a `long_gap` WARN (weekend ~2.2 d and ordinary holidays stay below it).
LONG_GAP_S = {"sub": 4 * 86400, "1D": 5 * 86400, "1W": 15 * 86400}
HISTORY_SHALLOWER_DAYS = 30
#: ExportHistory.mq5 `InpBars` default. A series with EXACTLY this many bars hit the cap: the OLDEST bars are the
#: ones missing (docs/audits/2026-09-29-ftmo-history-coverage.md "Data completeness caveats": XAUUSD/XAGUSD 1m).
EXPORT_BAR_CAP = 5000000
#: Issues that make a symbol unusable until the owner decides a name; such a symbol is never listed for export.
MAPPING_ERRORS = ("name_collision", "bad_canonical_name", "registry_other_market", "canonical_id_collision")
#: Measured 2026-10-01 by applying this tool's proposal for 6 symbols to a COPY of the repo and running the affected
#: tests / counting prop-search's candidate space (docs/plans/2026-10-01-symbol-universe-design.md section A.0).
SIDE_EFFECTS = (
    "analysis.cfd is the registry's ONLY symbol list that import-mt5-history.py and the engine accept, so it is the "
    "minimum a proposal can touch -- but it is also read by other code, which this addition changes:",
    "scripts/prop-search.py build_candidate_space() iterates analysis.cfd: its pre-registered candidate space grew "
    "from 180 to 342 with 6 added symbols (fund-search PRIOR_COUNTS prop_search_records is 180). No test failed.",
    "scripts/build-artifact.py draws every analysis symbol and NAMES the ones with no live feed: each added "
    "research-only symbol appears as 'no feed' (test_build_artifact "
    "NoSymbolIsDroppedSilently fails until it is updated).",
    "Re-adding forex majors trips the 2026-09-27 removal guards in test_instruments_sync "
    "(ForexWasRemovedCleanly); the derived schema enums need `python3 scripts/sync-instruments.py --write`.",
    "analysis != execution: nothing here is orderable. execution/backtested are never touched, and "
    "integrations/mt5/OrderBridge.mq5 InpAllowedSymbols stays as it is.",
)
NOT_EQUIVALENT = ("The local Binance USDT history (data/history/ohlcv.<SYM>USDT.*) is Binance SPOT data: different "
                  "costs, different hours, different instrument. It is NOT an FTMO crypto CFD and is never used "
                  "to validate, price or stand in for one.")


class Usage(Exception):
    pass


def default_out_dir():
    return os.path.join(tempfile.gettempdir(), "import-ftmo-symbols")


def _load_json(path, what):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise Usage(f"cannot read {what} {path}: {exc}")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _dumps(doc):
    """The exact serialisation of docs/architecture/instruments.json and symbol-map.json (byte round-trip verified)."""
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------------------------------------ mapping
def class_of(path, class_alias):
    """(asset_class, path_head). `path` is MT5's SYMBOL_PATH, e.g. 'Indices\\\\US500.cash'."""
    if not path:
        return OTHER, ""
    head = re.split(r"[\\/]", path.strip())[0].strip()
    key = head.lower()
    aliases = {k.lower(): v for k, v in (class_alias or {}).items()}
    return aliases.get(key) or PATH_CLASS.get(key) or OTHER, head


def derive_canonical(raw, existing_map, overrides):
    """(canonical, source). Precedence: existing map entry, --override, known alias, strip `.cash`, identity."""
    if raw in existing_map:
        return existing_map[raw], "existing_map"
    if raw in overrides:
        return overrides[raw], "override"
    stripped = raw[:-5] if raw.endswith(".cash") else raw
    if stripped in KNOWN_ALIASES:
        return KNOWN_ALIASES[stripped], "alias"
    return stripped, ("strip_cash" if stripped != raw else "identity")


def canonical_id(canon, base, profit):
    """The registry's provider-independent id: 'XAU/USD', 'EUR/USD' for a base+profit pair, else '<SYM>/<profit>'
    ('US500/USD', 'DE40/EUR') -- the convention of every existing instruments.json `canonical` value."""
    if not profit:
        return None
    if base and len(base) == 3 and canon == base + profit:
        return f"{base}/{profit}"
    return f"{canon}/{profit}"


# ------------------------------------------------------------------------------------------------ series scan
def _tf_step(tf):
    return Q.N.tf_seconds(tf)


def _long_gap_s(tf):
    return LONG_GAP_S.get(tf) or LONG_GAP_S["sub"]


def _iter_parts(path, shape):
    """Yield (year_or_None, candles) one part at a time -- never the whole 1.7M-bar series in memory."""
    if shape == "file":
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        yield None, doc.get("candles")
        return
    with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
        index = json.load(fh)
    for year in sorted(index.get("years") or ()):
        with gzip.open(os.path.join(path, f"{year}.json.gz"), "rt", encoding="utf-8") as fh:
            yield year, json.load(fh).get("candles")


def _read_index(path, shape):
    if shape != "split":
        return {}
    with open(os.path.join(path, "index.json"), encoding="utf-8") as fh:
        return json.load(fh)


def scan_series(path, shape, tf, fast=False):
    """One streaming pass. INVALID = quality._structural_fault on each part (the repo's own definition) or a
    repeated / backwards timestamp (also across part seams). Gaps are counted, never repaired."""
    index = _read_index(path, shape)
    res = {"present": True, "shape": shape, "bars": 0, "first": None, "last": None, "duplicates": 0,
           "non_monotone": 0, "fault": None, "gaps": {"total": 0, "long": 0, "max_seconds": 0, "max_at": None,
                                                      "examples": []},
           "scan": "full"}
    if fast and shape == "split":
        res.update(bars=int(index.get("_bars") or 0), first=index.get("first"), last=index.get("last"),
                   scan="index_only", integrity="UNVERIFIED")
        return res
    step, long_s = _tf_step(tf), _long_gap_s(tf)
    prev_dt = prev_s = None
    fromiso = datetime.datetime.fromisoformat
    for _, cs in _iter_parts(path, shape):
        if not isinstance(cs, list):
            res["fault"] = res["fault"] or "a part has no `candles` list"
            continue
        if cs and res["fault"] is None:
            res["fault"] = Q._structural_fault(cs)
        g = res["gaps"]
        for c in cs:
            ts = c["time"]
            try:
                dt = fromiso(ts.replace("Z", "+00:00"))
            except (ValueError, AttributeError, KeyError):
                res["fault"] = res["fault"] or f"unparseable time {ts!r}"
                continue
            if res["first"] is None:
                res["first"] = ts
            res["bars"] += 1
            if prev_dt is not None:
                delta = (dt - prev_dt).total_seconds()
                if delta == 0:
                    res["duplicates"] += 1
                    continue
                if delta < 0:
                    res["non_monotone"] += 1
                    continue
                if delta > step:
                    g["total"] += 1
                    if delta > g["max_seconds"]:
                        g["max_seconds"], g["max_at"] = int(delta), prev_s
                    if delta > long_s:
                        g["long"] += 1
                        if len(g["examples"]) < 5:
                            g["examples"].append({"after": prev_s, "before": ts, "hours": round(delta / 3600, 1)})
            prev_dt, prev_s = dt, ts
    res["last"] = prev_s
    if res["fault"] or res["duplicates"] or res["non_monotone"]:
        res["integrity"] = "INVALID"
    elif res["bars"] == 0:
        res["integrity"] = "MISSING"
    elif res["gaps"]["long"]:
        res["integrity"] = "VALID_WITH_GAPS"
    else:
        res["integrity"] = "VALID"
    if index.get("_bars") is not None and int(index["_bars"]) != res["bars"]:
        res["index_bars"] = int(index["_bars"])
    return res


# ------------------------------------------------------------------------------------------------ spec
def read_spec(costs_dir, raw):
    p = os.path.join(costs_dir, f"symbolspec.{raw}.json")
    if not os.path.exists(p):
        return {"present": False, "file": f"symbolspec.{raw}.json"}
    try:
        d = _load_json(p, "symbolspec")
    except Usage as exc:
        return {"present": True, "file": os.path.basename(p), "unreadable": str(exc)}
    rec = d.get("recorded_spread_m15") or {}
    return {"present": True, "file": os.path.basename(p), "swap_mode": d.get("swap_mode"), "point": d.get("point"),
            "digits": d.get("digits"), "currency_profit": d.get("currency_profit"),
            "commission_status": (d.get("commission") or {}).get("status"),
            "recorded_spread_bars": rec.get("bars"), "recorded_spread_median_points": rec.get("median_points")}


def _spec_issues(spec, listed):
    out = []
    if not spec["present"]:
        out.append(("ERROR", "spec_missing", f"{spec['file']} not found in the costs dir: scripts/real_costs.py "
                    f"refuses a symbol with no FTMO spec (no guessed or borrowed cost). Run ExportSymbolSpec.mq5."))
        return out
    if spec.get("unreadable"):
        return [("ERROR", "spec_unreadable", spec["unreadable"])]
    if spec.get("swap_mode") != 1:
        out.append(("ERROR", "spec_swap_mode_unsupported",
                    f"swap_mode {spec.get('swap_mode')!r}: scripts/real_costs.py swap_price implements "
                    f"SYMBOL_SWAP_MODE_POINTS (1) only and raises CostRefused otherwise; the model must be "
                    f"extended before this symbol can be priced."))
    if not spec.get("recorded_spread_bars"):
        out.append(("ERROR", "spec_no_recorded_spread", "recorded_spread_m15.bars is 0/missing: real_costs "
                    "spread_price has nothing measured to price this symbol with."))
    if spec.get("commission_status") != "from_deals":
        out.append(("INFO", "commission_unknown", f"commission status {spec.get('commission_status')!r}: the "
                    f"engine charges 0.0 (never guessed). Real per-lot commission, if any, must come from FTMO's "
                    f"contract page and needs a sized-cost path in real_costs before it counts."))
    if listed and spec.get("point") is not None and listed.get("point") not in (None, "") \
            and abs(float(listed["point"]) - float(spec["point"])) > 1e-12:
        out.append(("WARN", "spec_point_differs_from_list", f"spec point {spec['point']} != listed {listed['point']}"))
    return out


# ------------------------------------------------------------------------------------------------ report
def _synth_entries(existing_map, costs_dir):
    """Listless mode: the symbol set = symbol-map.json raw names + every symbolspec.<raw>.json."""
    raws = list(existing_map)
    if os.path.isdir(costs_dir):
        for n in sorted(os.listdir(costs_dir)):
            m = re.match(r"^symbolspec\.(.+)\.json$", n)
            if m and m.group(1) not in raws:
                raws.append(m.group(1))
    return [{"name": r, "path": None} for r in raws]


def build_report(list_doc, *, history_root, costs_dir, registry, symbol_map, overrides=None, class_alias=None,
                 only_symbols=None, only_classes=None, require_history=False, fast=False):
    overrides, class_alias = overrides or {}, class_alias or {}
    existing_map = dict(symbol_map.get("map") or {})
    reg_canon = {k: v for k, v in (registry.get("canonical") or {}).items() if not k.startswith("_")}
    reg_display = {k: v for k, v in (registry.get("display") or {}).items() if not k.startswith("_")}
    reg_cfd = list((registry.get("analysis") or {}).get("cfd") or [])
    reg_other_market = {s for m, lst in (registry.get("analysis") or {}).items() if m != "cfd" for s in lst}
    listless = list_doc is None
    entries = _synth_entries(existing_map, costs_dir) if listless else list(list_doc.get("symbols") or [])

    syms, unmapped = {}, {}
    for e in entries:
        raw = e.get("name")
        if not raw:
            continue
        canon, src = derive_canonical(raw, existing_map, overrides)
        if listless:
            cls = (reg_display.get(canon) or {}).get("asset_class") or OTHER
            cls = cls if cls in VALID_CLASSES else OTHER
            head = ""
        else:
            cls, head = class_of(e.get("path"), class_alias)
        s = {"raw": raw, "canonical": canon, "mapping_source": src, "asset_class": cls, "path": e.get("path"),
             "description": e.get("description"), "issues": [], "selected": False, "status": None,
             "timeframes": {}, "timeframes_present": [], "timeframes_missing": list(ALL_TFS),
             "decision_ready": False, "context_complete": False, "spec": None,
             "listed": {k: e.get(k) for k in ("first_bar_server", "server_first_date", "terminal_first_date",
                                              "trade_mode_name", "swap_mode", "spread_now_points", "digits",
                                              "contract_size", "currency_base", "currency_profit") if k in e},
             "in_registry": canon in reg_cfd, "in_map": raw in existing_map, "_entry": e}
        syms[raw] = s
        if cls == OTHER:
            u = unmapped.setdefault(head or "(no path)", [])
            u.append(raw)

    def issue(s, sev, code, msg):
        s["issues"].append({"severity": sev, "code": code, "message": msg})

    for s in syms.values():
        if s["asset_class"] == OTHER:
            s["status"] = "excluded_unmapped_class"
            issue(s, "INFO", "unmapped_class", f"path {s['path']!r} is not Forex/Indices/Metals/Energies/Crypto; "
                  f"excluded (use --class-alias '<path head>=<class>' to include a class deliberately).")
            continue
        sel = True
        if only_symbols is not None and s["raw"] not in only_symbols:
            sel = False
        if only_classes is not None and s["asset_class"] not in only_classes:
            sel = False
        s["selected"] = sel
        if not sel:
            s["status"] = "not_selected"

    # --- canonical-name validity and collisions (over every mapped-class symbol + the existing map's occupants)
    occupants = {}
    for raw, canon in existing_map.items():
        occupants.setdefault(canon, set()).add(raw)
    for s in syms.values():
        if s["asset_class"] != OTHER:
            occupants.setdefault(s["canonical"], set()).add(s["raw"])
    collisions = []
    for canon, raws in sorted(occupants.items()):
        if len(raws) > 1:
            collisions.append({"canonical": canon, "raw_names": sorted(raws)})
            for r in raws:
                s = syms.get(r)
                if s and s["selected"]:
                    others = sorted(raws - {r})
                    issue(s, "ERROR", "name_collision", f"canonical {canon!r} is also the target of {others}; two raw "
                          f"symbols would merge into one history directory. Resolve with --override RAW=CANON.")
    for s in syms.values():
        if not s["selected"]:
            continue
        if not CANON_RE.match(s["canonical"]):
            issue(s, "ERROR", "bad_canonical_name", f"canonical {s['canonical']!r} is not [A-Z0-9_]{{2,24}} "
                  f"(history is stored as ohlcv.<SYM>.<TF>; refused, not sanitised). Use --override.")
        if s["canonical"] in reg_other_market:
            issue(s, "ERROR", "registry_other_market", f"canonical {s['canonical']!r} is already a symbol of another "
                  f"market in the registry (the Binance crypto market); a CFD must never share its name.")

    # --- registry canonical-id uniqueness is checked while building proposals; now per-symbol data
    taken_ids = {v for v in reg_canon.values()}
    for s in syms.values():
        if not s["selected"]:
            continue
        blocking = any(i["severity"] == "ERROR" for i in s["issues"])
        spec = read_spec(costs_dir, s["raw"])
        s["spec"] = spec
        has_hist = False
        listed = s["_entry"]
        if not blocking:
            for tf in ALL_TFS:
                path, shape = HS.resolve(s["canonical"], tf, root=history_root)
                if shape is None:
                    continue
                try:
                    r = scan_series(path, shape, tf, fast=fast)
                except (OSError, ValueError, KeyError) as exc:
                    r = {"present": True, "shape": shape, "bars": 0, "integrity": "INVALID",
                         "fault": f"unreadable: {exc}", "duplicates": 0, "non_monotone": 0,
                         "gaps": {"total": 0, "long": 0, "max_seconds": 0, "examples": []}}
                s["timeframes"][tf] = r
                has_hist = True
        pres = [tf for tf in ALL_TFS if tf in s["timeframes"]]
        s["timeframes_present"] = pres
        s["timeframes_missing"] = [tf for tf in ALL_TFS if tf not in s["timeframes"]]
        s["decision_ready"] = all(tf in s["timeframes"] for tf in DECISION_TFS)
        s["context_complete"] = all(tf in s["timeframes"] for tf in ALL_TFS)
        if blocking:
            s["status"] = "error"
            continue

        if has_hist:
            for tf in DECISION_TFS:
                if tf not in s["timeframes"]:
                    issue(s, "ERROR", "decision_timeframe_missing", f"{tf} is a fund-search decision timeframe and "
                          f"has no series under {history_root}")
            for tf in CONTEXT_TFS:
                if tf not in s["timeframes"]:
                    issue(s, "WARN", "context_timeframe_missing", f"{tf} (higher-timeframe context) has no series")
            for tf, r in s["timeframes"].items():
                if r.get("integrity") == "INVALID":
                    why = r.get("fault") or (f"{r['duplicates']} duplicate / {r['non_monotone']} non-monotone "
                                              f"timestamp(s)")
                    issue(s, "ERROR", "series_invalid", f"{tf}: INVALID -- {why}")
                if r["gaps"]["long"]:
                    g = r["gaps"]
                    issue(s, "WARN", "long_gap", f"{tf}: {g['long']} gap(s) above "
                          f"{_long_gap_s(tf) // 86400} days (largest {round(g['max_seconds'] / 3600, 1)} h after "
                          f"{g['max_at']}); examples {g['examples'][:2]}")
                if r["bars"] == EXPORT_BAR_CAP:
                    issue(s, "WARN", "bars_hit_export_cap", f"{tf}: exactly {EXPORT_BAR_CAP} bars = ExportHistory "
                          f"InpBars cap; the oldest history is probably missing (series starts {r['first']}). "
                          f"Re-export with a larger InpBars if depth matters.")
                if r.get("index_bars") is not None:
                    issue(s, "WARN", "index_mismatch", f"{tf}: index.json says {r['index_bars']} bars, the parts "
                          f"hold {r['bars']}")
                if r.get("integrity") == "UNVERIFIED":
                    issue(s, "INFO", "index_only", f"{tf}: --fast read the index only; the series was not scanned")
            if s["asset_class"] == "crypto":
                gaps = sum(r["gaps"]["total"] for r in s["timeframes"].values())
                if gaps:
                    issue(s, "INFO", "crypto_cfd_hours", "FTMO crypto-CFD trading hours are not assumed 24/7: "
                          f"{gaps} gap(s) above one bar exist across the series; compare with the listed "
                          f"sessions_trade before treating the tape as continuous.")
            # depth vs what the terminal said was available
            lf = (listed.get("first_bar_server") or {}) if isinstance(listed, dict) else {}
            for tf in ("1m", "5m", "15m"):
                got, listed_first = (s["timeframes"].get(tf) or {}).get("first"), lf.get(tf)
                if got and listed_first:
                    try:
                        a = datetime.datetime.fromisoformat(got.replace("Z", "+00:00")).replace(tzinfo=None)
                        b = datetime.datetime.fromisoformat(listed_first.replace("Z", ""))
                    except ValueError:
                        continue
                    if (a - b).days > HISTORY_SHALLOWER_DAYS:
                        issue(s, "INFO", "history_shallower_than_available",
                              f"{tf}: exported series starts {got} but the terminal listed {listed_first} (server "
                              f"time) as available: {(a - b).days} days of depth were not exported/imported.")
                    elif (b - a).days > HISTORY_SHALLOWER_DAYS:
                        issue(s, "WARN", "listed_first_after_history", f"{tf}: series starts {got}, before the "
                              f"terminal's own first bar {listed_first}")
        if has_hist or spec["present"]:
            for sev, code, msg in _spec_issues(spec, listed if not listless else None):
                if has_hist or sev == "INFO":
                    issue(s, sev, code, msg)
        errs = [i for i in s["issues"] if i["severity"] == "ERROR"]
        warns = [i for i in s["issues"] if i["severity"] == "WARN"]
        if not has_hist:
            s["status"] = "spec_only" if spec["present"] else "listed_only"
            if require_history:
                issue(s, "ERROR", "history_missing", f"--require-history: no series under {history_root}")
                s["status"] = "error"
        elif errs:
            s["status"] = ("history_incomplete" if any(i["code"] == "decision_timeframe_missing" for i in errs)
                           and not any(i["code"] in ("series_invalid",) for i in errs) else "error")
            if any(i["code"] == "series_invalid" for i in errs):
                s["status"] = "invalid"
        else:
            s["status"] = "ready_with_warnings" if warns else "ready"

    # --- proposals (never gated on data, only on mapping/class/collision/ERROR-free)
    reg_ops, map_ops, new_ids = [], [], {}
    for s in sorted((x for x in syms.values() if x["selected"]), key=lambda x: x["raw"]):
        if any(i["severity"] == "ERROR" for i in s["issues"]):
            continue
        canon, e = s["canonical"], s["_entry"]
        if s["raw"] not in existing_map:
            map_ops.append({"op": "add", "path": "/map/" + _ptr(s["raw"]), "value": canon})
        if canon in reg_cfd and canon in reg_canon and canon in reg_display:
            continue
        profit = e.get("currency_profit") or (s["spec"] or {}).get("currency_profit")
        cid = canonical_id(canon, e.get("currency_base"), profit)
        if canon not in reg_canon:
            if not cid:
                issue(s, "WARN", "no_currency_profit", "no currency_profit in the symbol list or spec: cannot "
                      "propose the registry `canonical` id; add it by hand.")
                continue
            if cid in taken_ids or cid in new_ids:
                issue(s, "ERROR", "canonical_id_collision", f"registry canonical id {cid!r} is already taken by "
                      f"{new_ids.get(cid) or [k for k, v in reg_canon.items() if v == cid]}")
                continue
            new_ids[cid] = canon
            reg_ops.append({"op": "add", "path": "/canonical/" + _ptr(canon), "value": cid})
        if canon not in reg_display:
            digits = e.get("digits", (s["spec"] or {}).get("digits"))
            disp = {"id": canon.lower(), "label": (e.get("description") or canon)[:60],
                    "asset_class": s["asset_class"]}
            if digits is not None:
                disp["price_decimals"] = int(digits)
            reg_ops.append({"op": "add", "path": "/display/" + _ptr(canon), "value": disp})
        if canon not in reg_cfd:
            reg_ops.append({"op": "add", "path": "/analysis/cfd/-", "value": canon})
    # a canonical-id collision found while proposing is an ERROR that must show in the totals
    if reg_ops:
        names = [o["value"] for o in reg_ops if o["path"] == "/analysis/cfd/-"]
        reg_ops.insert(0, {"op": "add", "path": "/history/0", "value": {
            "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"),
            "change": f"FTMO symbol universe: {len(names)} CFD symbol(s) added to analysis.cfd ONLY "
                      f"(canonical + display entries); execution and backtested unchanged: {', '.join(names)}.",
            "reason": "Owner decision 2026-10-01: add the full FTMO CFD universe and FTMO crypto CFDs to raise the "
                      "fund search's statistical power (docs/plans/2026-10-01-symbol-universe-design.md). Generated "
                      f"by {TOOL} from an ExportSymbolList export; history/specs are validated separately.",
            "approved_by": "owner (decision 2026-10-01); registry edit applied by --apply after review"}})

    symbols_out = []
    for s in sorted(syms.values(), key=lambda x: x["raw"]):
        o = {k: v for k, v in s.items() if k != "_entry"}
        symbols_out.append(o)

    by_class = {}
    for s in symbols_out:
        c = by_class.setdefault(s["asset_class"], {"listed": 0, "selected": 0, "with_history": 0, "ready": 0,
                                                    "errors": 0})
        c["listed"] += 1
        c["selected"] += 1 if s["selected"] else 0
        c["with_history"] += 1 if s["timeframes_present"] else 0
        c["ready"] += 1 if s["status"] in ("ready", "ready_with_warnings") else 0
        c["errors"] += 1 if any(i["severity"] == "ERROR" for i in s["issues"]) else 0
    n_err = sum(1 for s in symbols_out if s["selected"] and any(i["severity"] == "ERROR" for i in s["issues"]))
    return {"tool": TOOL, "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
            "mode": "symbol_list" if not listless else "listless (symbol-map + spec files; class from registry)",
            "server": (list_doc or {}).get("_server"), "required_decision_timeframes": list(DECISION_TFS),
            "context_timeframes": list(CONTEXT_TFS), "not_equivalent": NOT_EQUIVALENT,
            "summary": {"symbols": len(symbols_out), "selected": sum(1 for s in symbols_out if s["selected"]),
                        "symbols_with_errors": n_err, "by_class": by_class,
                        "ready": sum(1 for s in symbols_out if s["status"] in ("ready", "ready_with_warnings"))},
            "unmapped_classes": [{"path_head": h, "count": len(v), "symbols": sorted(v)[:50]}
                                 for h, v in sorted(unmapped.items())],
            "collisions": collisions, "symbols": symbols_out,
            "proposals": {"registry_ops": reg_ops, "symbol_map_ops": map_ops,
                          "side_effects": list(SIDE_EFFECTS) if reg_ops else [],
                          "note": "NOT applied. Only `add` ops; execution/backtested/estate_capacity are never touched."}}


def _ptr(token):
    return token.replace("~", "~0").replace("/", "~1")


# ------------------------------------------------------------------------------------------------ patch application
def apply_ops(doc, ops):
    """Minimal RFC 6902 `add` for the shapes this tool emits: object member, array index, array append ('-')."""
    doc = copy.deepcopy(doc)
    for op in ops:
        if op["op"] != "add":
            raise ValueError(f"unsupported op {op['op']!r}")
        parts = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].lstrip("/").split("/")]
        cur = doc
        for p in parts[:-1]:
            cur = cur[int(p)] if isinstance(cur, list) else cur[p]
        last = parts[-1]
        if isinstance(cur, list):
            if last == "-":
                cur.append(op["value"])
            else:
                cur.insert(int(last), op["value"])
        else:
            if last in cur:
                raise ValueError(f"{op['path']} already exists; this tool never overwrites")
            cur[last] = op["value"]
    return doc


def _diff(path, before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=path + " (current)",
                                        tofile=path + " (proposed)"))


# ------------------------------------------------------------------------------------------------ rendering
def render_md(rep):
    s = rep["summary"]
    L = ["# FTMO symbol-universe validation", "",
         f"- generated {rep['generated_at_utc']} by `{rep['tool']}`; mode: {rep['mode']}; server: {rep['server']}",
         f"- symbols listed {s['symbols']}, selected {s['selected']}, ready {s['ready']}, "
         f"selected symbols with ERROR {s['symbols_with_errors']}",
         f"- decision timeframes (must exist): {', '.join(rep['required_decision_timeframes'])}; context: "
         f"{', '.join(rep['context_timeframes'])}",
         f"- **Not equivalent:** {rep['not_equivalent']}", "", "## By asset class", "",
         "| class | listed | selected | with history | ready | with errors |", "|---|---|---|---|---|---|"]
    for c, v in sorted(s["by_class"].items()):
        L.append(f"| {c} | {v['listed']} | {v['selected']} | {v['with_history']} | {v['ready']} | {v['errors']} |")
    L += ["", "## Unmapped classes (excluded from every proposal)", ""]
    if rep["unmapped_classes"]:
        for u in rep["unmapped_classes"]:
            L.append(f"- `{u['path_head']}`: {u['count']} symbol(s), e.g. {', '.join(u['symbols'][:8])}")
    else:
        L.append("- none")
    L += ["", "## Collisions", ""]
    if rep["collisions"]:
        for c in rep["collisions"]:
            L.append(f"- name_collision: canonical `{c['canonical']}` <- {', '.join(c['raw_names'])}")
    else:
        L.append("- none")
    L += ["", "## Listed depth BEFORE export (selected symbols; server time, from ExportSymbolList)", "",
          "| raw | class | canonical | server first date | first 1m | first 5m | first 15m | trade mode |",
          "|---|---|---|---|---|---|---|---|"]
    shown = 0
    for x in rep["symbols"]:
        if not x["selected"] or not x.get("listed"):
            continue
        li, fb = x["listed"], x["listed"].get("first_bar_server") or {}
        if shown >= 500:
            L.append("| ... | | | | | | | (first 500 only; report.json has all) |")
            break
        shown += 1
        L.append(f"| {x['raw']} | {x['asset_class']} | {x['canonical']} | {(li.get('server_first_date') or '-')[:10]} | "
                 f"{(fb.get('1m') or '-')[:10]} | {(fb.get('5m') or '-')[:10]} | {(fb.get('15m') or '-')[:10]} | "
                 f"{li.get('trade_mode_name') or '-'} |")
    if not shown:
        L.append("| (none: listless mode or no first-bar data in the list) | | | | | | | |")
    L += ["", "## Symbols with history, a spec, or an issue", "",
          "| raw | canonical (source) | class | status | timeframes present | missing | bars 1m / 5m / 15m | spec |",
          "|---|---|---|---|---|---|---|---|"]
    for x in rep["symbols"]:
        if not x["selected"] and x["status"] != "error":
            continue
        if x["status"] in ("listed_only",) and not x["issues"]:
            continue
        tf = x["timeframes"]
        bars = " / ".join(str((tf.get(t) or {}).get("bars", "-")) for t in DECISION_TFS)
        sp = x["spec"] or {}
        L.append(f"| {x['raw']} | {x['canonical']} ({x['mapping_source']}) | {x['asset_class']} | {x['status']} | "
                 f"{' '.join(x['timeframes_present']) or '-'} | {' '.join(x['timeframes_missing']) or '-'} | "
                 f"{bars} | {'yes' if sp.get('present') else 'MISSING'} |")
    L += ["", "## Issues", ""]
    any_issue = False
    for x in rep["symbols"]:
        for i in x["issues"]:
            if i["severity"] in ("ERROR", "WARN") or i["code"] in ("history_shallower_than_available",
                                                                    "crypto_cfd_hours", "commission_unknown"):
                any_issue = True
                L.append(f"- **{i['severity']}** `{x['raw']}` {i['code']}: {i['message']}")
    if not any_issue:
        L.append("- none")
    p = rep["proposals"]
    L += ["", "## Proposed additions (NOT applied)", "",
          f"- instruments.json: {len(p['registry_ops'])} op(s) -> `registry.patch.json`, diff `registry.diff`",
          f"- symbol-map.json: {len(p['symbol_map_ops'])} op(s) -> `symbol-map.patch.json`, diff `symbol-map.diff`",
          "- analysis list only: `execution` and `backtested` are never proposed (analysis != execution)",
          "- after `--apply`: run `python3 scripts/sync-instruments.py --write`, then the registry tests", ""]
    if p.get("side_effects"):
        L += ["### Side effects of adding to analysis.cfd (read before --apply)", ""] + [f"- {x}" for x in p["side_effects"]] + [""]
    return "\n".join(L)


def render_batches(rep, size):
    """RAW names (what MT5 knows) of every selected symbol whose MAPPING is valid (a symbol with a data ERROR still belongs in the next export -- that is how it gets fixed), in batches -- the InpSymbols values for
    ExportSymbolSpec.mq5 and ExportHistory.mq5. Sorted by class then name so a batch is one asset class."""
    ok = sorted((s for s in rep["symbols"] if s["selected"] and not any(i["code"] in MAPPING_ERRORS for i in s["issues"])),
                key=lambda s: (s["asset_class"], s["raw"]))
    lines = ["# InpSymbols batches (raw MT5 names; selected symbols with a valid mapping). One line = one script run.", ""]
    for i in range(0, len(ok), size):
        chunk = ok[i:i + size]
        lines.append(f"batch-{i // size + 1:02d} [{chunk[0]['asset_class']}..{chunk[-1]['asset_class']}]: "
                     + ",".join(s["raw"] for s in chunk))
    if not ok:
        lines.append("(no selected symbol with a valid mapping)")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------------------------------------ main
def _kv(items, what):
    out = {}
    for it in items or ():
        if "=" not in it:
            raise Usage(f"{what} expects KEY=VALUE, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate an FTMO symbol-universe import; propose registry additions.")
    ap.add_argument("--symbol-list", help="ExportSymbolList.mq5 JSON; omit for listless mode (symbol-map + specs)")
    ap.add_argument("--history-root", default=os.path.join(ROOT, "data", "history", "ftmo"))
    ap.add_argument("--costs-dir", default=os.path.join(ROOT, "data", "history", "costs", "ftmo"))
    ap.add_argument("--registry", default=os.path.join(ROOT, "docs", "architecture", "instruments.json"))
    ap.add_argument("--symbol-map", default=os.path.join(ROOT, "data", "history", "costs", "ftmo", "symbol-map.json"))
    ap.add_argument("--out", default=None, help="output dir (default: <system tmp>/import-ftmo-symbols)")
    ap.add_argument("--symbols", default=None, help="comma list of RAW names to select (default: all mapped classes)")
    ap.add_argument("--classes", default=None, help=f"comma list of classes to select, from {','.join(VALID_CLASSES)}")
    ap.add_argument("--override", action="append", metavar="RAW=CANON", help="force a canonical name (repeatable)")
    ap.add_argument("--class-alias", action="append", metavar="PATHHEAD=CLASS",
                    help="treat a path head (e.g. 'Forex Majors') as a class (repeatable)")
    ap.add_argument("--require-history", action="store_true",
                    help="a selected symbol with no series is an ERROR (use after the history import)")
    ap.add_argument("--batch-size", type=int, default=15,
                    help="symbols per line in export-batches.txt (paste one line into InpSymbols of ExportSymbolSpec / "
                         "ExportHistory; the terminal's input-string length limit is unverified, so keep batches small)")
    ap.add_argument("--fast", action="store_true", help="split series: read index.json only, skip the bar scan")
    ap.add_argument("--apply", action="store_true",
                    help="write the proposed additions into --registry and --symbol-map (backup first; off by default)")
    a = ap.parse_args(argv)

    try:
        list_doc = _load_json(a.symbol_list, "symbol list") if a.symbol_list else None
        if list_doc is not None and not isinstance(list_doc.get("symbols"), list):
            raise Usage(f"{a.symbol_list}: no `symbols` array -- not an ExportSymbolList.mq5 file")
        registry = _load_json(a.registry, "registry")
        smap = _load_json(a.symbol_map, "symbol map") if os.path.exists(a.symbol_map) else {"map": {}}
        overrides, class_alias = _kv(a.override, "--override"), _kv(a.class_alias, "--class-alias")
        for v in class_alias.values():
            if v not in VALID_CLASSES:
                raise Usage(f"--class-alias class {v!r} not in {VALID_CLASSES}")
        classes = set(x.strip() for x in a.classes.split(",")) if a.classes else None
        if classes and not classes <= set(VALID_CLASSES):
            raise Usage(f"--classes {sorted(classes - set(VALID_CLASSES))} not in {VALID_CLASSES}")
        only = set(x.strip() for x in a.symbols.split(",")) if a.symbols else None
    except Usage as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rep = build_report(list_doc, history_root=a.history_root, costs_dir=a.costs_dir, registry=registry,
                       symbol_map=smap, overrides=overrides, class_alias=class_alias, only_symbols=only,
                       only_classes=classes, require_history=a.require_history, fast=a.fast)
    rep["inputs"] = {"symbol_list": a.symbol_list, "symbol_list_sha256": _sha256(a.symbol_list) if a.symbol_list else None,
                     "registry": a.registry, "registry_sha256": _sha256(a.registry), "symbol_map": a.symbol_map,
                     "history_root": a.history_root, "costs_dir": a.costs_dir}

    reg_text, map_text = _dumps(registry), _dumps(smap)
    new_reg = apply_ops(registry, rep["proposals"]["registry_ops"])
    new_map = apply_ops(smap, rep["proposals"]["symbol_map_ops"])
    out = a.out or default_out_dir()
    os.makedirs(out, exist_ok=True)

    def w(name, text):
        with open(os.path.join(out, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    w("report.json", json.dumps(rep, indent=2, ensure_ascii=False) + "\n")
    w("report.md", render_md(rep))
    w("registry.patch.json", json.dumps(rep["proposals"]["registry_ops"], indent=2, ensure_ascii=False) + "\n")
    w("symbol-map.patch.json", json.dumps(rep["proposals"]["symbol_map_ops"], indent=2, ensure_ascii=False) + "\n")
    w("export-batches.txt", render_batches(rep, max(1, a.batch_size)))
    w("registry.diff", _diff(os.path.relpath(a.registry, ROOT) if a.registry.startswith(ROOT) else a.registry,
                              reg_text, _dumps(new_reg)))
    w("symbol-map.diff", _diff(os.path.relpath(a.symbol_map, ROOT) if a.symbol_map.startswith(ROOT) else a.symbol_map,
                                map_text, _dumps(new_map)))

    s = rep["summary"]
    print(f"{TOOL}: {s['symbols']} symbol(s), {s['selected']} selected, {s['ready']} ready, "
          f"{s['symbols_with_errors']} with ERROR; {len(rep['unmapped_classes'])} unmapped class(es); "
          f"{len(rep['collisions'])} collision(s)")
    print(f"  proposals (NOT applied unless --apply): {len(rep['proposals']['registry_ops'])} registry op(s), "
          f"{len(rep['proposals']['symbol_map_ops'])} symbol-map op(s)")
    print(f"  report: {os.path.join(out, 'report.md')}")
    rc = 1 if s["symbols_with_errors"] else 0

    if a.apply:
        if rc:
            print("REFUSED --apply: ERROR(s) exist among the selected symbols; fix them or narrow with "
                  "--symbols/--classes (nothing was written).", file=sys.stderr)
            return 1
        if not (rep["proposals"]["registry_ops"] or rep["proposals"]["symbol_map_ops"]):
            print("--apply: nothing to add.")
            return 0
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bdir = os.path.join(out, "backup")
        os.makedirs(bdir, exist_ok=True)
        for p in (a.registry, a.symbol_map):
            if os.path.exists(p):
                shutil.copy2(p, os.path.join(bdir, f"{os.path.basename(p)}.{stamp}"))
        with open(a.registry, "w", encoding="utf-8") as fh:
            fh.write(_dumps(new_reg))
        with open(a.symbol_map, "w", encoding="utf-8") as fh:
            fh.write(_dumps(new_map))
        for p, want in ((a.registry, new_reg), (a.symbol_map, new_map)):
            with open(p, encoding="utf-8") as fh:
                if json.load(fh) != want:
                    print(f"error: {p} did not round-trip after writing; restore from {bdir}", file=sys.stderr)
                    return 1
        print(f"--apply: wrote {a.registry} and {a.symbol_map}; backups in {bdir}")
        for x in rep["proposals"].get("side_effects") or ():
            print(f"  side effect: {x}")
        print("  next: python3 scripts/sync-instruments.py --write ; run test_instruments_sync, "
              "test_canonical_market_model, test_fx_registry_complete")
    return rc


if __name__ == "__main__":
    sys.exit(main())
