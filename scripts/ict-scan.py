#!/usr/bin/env python3
"""Deterministic Wyckoff/ICT event scanner + preliminary read + FACTS (no LLM).

Mirrors the artifacts' client-side ictAnalyze() so the preliminary read matches what the chart draws:
3-bar pivots, old + equal highs/lows (BSL/SSL, knowledge/ict/core-a.md §2.7) + external range liquidity (ERL), sweeps (wick through a
level, close back), 3-candle FVGs until mitigation, MSS (close beyond last swing after a lower-low /
higher-high), premium/discount vs equilibrium, and volume outliers (Effort-vs-Result hint).

FACTS (added 2026-09-10, rule "numbers from code, words from the model"):
  * anchors  -- data/live/anchors.<style>.json names the structural levels of the last full analysis
                (e.g. LPS_low / SOS_high, spring_low). For each level the scanner computes: last close
                above/below, distance %, the FIRST COMPLETED CLOSE beyond it after the anchor time
                (= invalidation candle), and the extreme since. The verdict rule (range / floor) is
                evaluated on the last COMPLETED candle, never on the forming one.
  * setup    -- if the classic chain sweep -> MSS (same direction) -> FVG exists, entry (FVG edge),
                stop (sweep extreme), target (nearest unswept pool, else window ERL) and R are computed.
  * facts    -- written to data/live/prelim/<style>.facts.json and rendered as a small table inside the
                prelim snippet. Models must quote these numbers, not recompute them.

Usage: ict-scan.py --tf 1m --n 180 --style scalping [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--state FILE]
Prints JSON {symbol: {...}} to stdout; writes Vietnamese HTML snippets to data/live/prelim/<style>.<SYM>.html;
exit code 0 = no NEW events since the state file, 3 = new events (caller may trigger a local/full read + alert).
Sources cited in the snippets: docs/TTrades PDFs (3. Liquidity, 8. Discount__Premium, 11. MSS_vs_Liquidity_Grab,
12. Fair_Value_Gaps, 18. Market_Structure_Shift, IRL-ERL), WA/knowledge/wyckoff/advance.md (Phase A-E, Spring/Shakeout, SOS/LPS, SOT),
                WMT/knowledge/wyckoff/modern-tools.md (Effort-vs-Result, Spring loai 1/2/3);
thresholds (equal-level tolerance, pivot width, FVG minimum size, displacement body/range ratios, 1.5x volume) are this
system's own parameters read from docs/architecture/analysis-params.json (project_defined.ict / .volume), and say so.
Dealing range = nearest unswept BSL above / SSL below the last close (knowledge/ict/core-a.md §2.18), window extremes as fallback.
MSS carries a displacement flag (knowledge/ict/core-a.md §2.16); a setup candidate requires it. 2026-09-12 (docs/audits/2026-09-12-ict-pdf-recheck.md).
"""
import argparse, json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I  # noqa: E402

CITE = {
    "liq": "docs/TTrades PDFs/3. Liquidity.pdf tr.1–5 · knowledge/ict/core-a.md §2.6–2.7",
    "grab": "docs/TTrades PDFs/11. MSS_vs_Liquidity_Grab.pdf tr.1–4 · knowledge/ict/core-a.md §2.14, §2.17",
    "pd": "docs/TTrades PDFs/8. Discount__Premium.pdf tr.1–5 · knowledge/ict/core-a.md §2.18–2.19",
    "fvg": "docs/TTrades PDFs/12. Fair_Value_Gaps.pdf tr.1–6 · knowledge/ict/core-a.md §2.21–2.24",
    "mss": "docs/TTrades PDFs/18. Market_Structure_Shift.pdf tr.1–3 · knowledge/ict/core-b.md §2.1–2.2",
    "erl": "docs/TTrades PDFs/IRL-ERL.pdf tr.1–8 · knowledge/ict/core-b.md §2.13",
    "evr": "WA p33–39 · knowledge/wyckoff/advance.md §2.2 · WMT p019–022, p149–154 · knowledge/wyckoff/modern-tools.md §2.3, §4.1",
    "spring": "WA p80 · knowledge/wyckoff/advance.md §2.7.3 (sự kiện) · WMT p036–049 · knowledge/wyckoff/modern-tools.md §2.6 (loại 1/2/3)",
    "sos": "WA p84–86 · knowledge/wyckoff/advance.md §2.7 (SOS/LPS/BU) · knowledge/wyckoff/modern-tools.md §6",
    "phase": "WA p71–123 · knowledge/wyckoff/advance.md §2.7–2.8 (Phase A–E) · đối nhãn: knowledge/wyckoff/advance.md §2.11",
    "sot": "WA p277–292 · knowledge/wyckoff/advance.md §4.6",
    "sys": "[tính toán của hệ thống — không phải trích dẫn tài liệu]",
}

# (A SHORT symbol->abbreviation dict lived here and was never read by anything -- deleted 2026-09-17. Short
#  labels belong in instruments.json display metadata if they are ever needed again.)


# Feed directory and tick-volume semantics come from instruments.py, keyed by market -- was a symbol set.


_PD = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"]
ICT = _PD.get("ict", {})
PIV = ICT.get("pivot_bars", {}).get("value", 3)
EQ_TOL = ICT.get("equal_level_tolerance_pct", {}).get("value", 0.08) / 100
FVG_MIN = ICT.get("fvg_min_size_median_ratio", {}).get("value", 0.6)
DISP = ICT.get("displacement", {"body_min_ratio": 0.6, "range_min_median_ratio": 1.2})
# Same one reader every other path uses (trading_env.min_rr): None rather than a fallback number when the value
# cannot be trusted. Here MIN_RR only drives the advisory `rr_ok` flag and the note printed at :359 -- but the
# `.get("value", 2.0)` shape is the bug the 2026-09-13 security review (F1) found on the live order paths, and a
# scanner that silently advises against the superseded 2R floor is the same defect with a quieter blast radius.
import importlib.util as _teu
_tespec = _teu.spec_from_file_location("trading_env", f"{ROOT}/scripts/trading_env.py")
trading_env = _teu.module_from_spec(_tespec); _tespec.loader.exec_module(trading_env)
MIN_RR = trading_env.min_rr()


def load(sym, tf):
    """Crypto from the Binance connector (data/live/market-data); commodities from the MT5 file bridge
    (data/live/mt5-bridge, written by integrations/mt5/ExportOHLCV.mq5). Same candle shape either way."""
    base = I.data_dir(sym)
    with open(f"{ROOT}/data/live/{base}/ohlcv.{sym}.{tf}.json") as f:
        return json.load(f)["candles"]


def load_anchors(style):
    try:
        return json.load(open(f"{ROOT}/data/live/anchors.{style}.json", encoding="utf-8"))
    except Exception:
        return None


def analyze(c, recent, tf=None, methods=("wyckoff", "ict")):
    """`methods` = the dimensions /automation has engaged. A disengaged one's work is SKIPPED, not merely hidden:
    the FVG-mitigation and pool-sweep scans are the quadratic part of this function and the volume-outlier scan is
    Wyckoff's alone, so paying for a read nothing will show slows down the methods that are on (2026-09-13).
    The shared window facts (last, window extremes, median range) are neither method's and are always computed."""
    ict, wyk = "ict" in methods, "wyckoff" in methods
    n = len(c)
    O = [x["open"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
    V = [x.get("volume", 0) for x in c]; T = [x["time"] for x in c]
    lo, hi = min(L), max(H); eq = (lo + hi) / 2
    med = sorted(h - l for h, l in zip(H, L))[n // 2]
    avgv = sum(V) / n if n else 0

    sh, sl = [], []
    for i in (range(PIV, n - PIV) if ict else ()):
        if all(H[j] <= H[i] for j in range(i - PIV, i + PIV + 1) if j != i): sh.append(i)
        if all(L[j] >= L[i] for j in range(i - PIV, i + PIV + 1) if j != i): sl.append(i)

    fvgs = []
    for i in (range(1, n - 1) if ict else ()):
        f = None
        if H[i - 1] < L[i + 1]: f = {"type": "bull", "i": i, "lo": H[i - 1], "hi": L[i + 1]}
        elif L[i - 1] > H[i + 1]: f = {"type": "bear", "i": i, "lo": H[i + 1], "hi": L[i - 1]}
        if not f: continue
        f["size"] = f["hi"] - f["lo"]; f["ce"] = (f["hi"] + f["lo"]) / 2; f["end"] = n - 1; f["mitigated"] = False
        for j in range(i + 2, n):
            if (f["type"] == "bull" and L[j] <= f["hi"]) or (f["type"] == "bear" and H[j] >= f["lo"]):
                f["end"] = j; f["mitigated"] = True; break
        if f["size"] >= FVG_MIN * med: fvgs.append(f)

    tol = eq * EQ_TOL
    pools = []
    def add(kind, idxs, level, ptype):
        # Dedupe BEFORE the sweep scan, not after. The scan is O(bars) and `analyze()` runs once per bar in a
        # backtest, so paying it for a pool that is about to be discarded is the whole cost of adding the
        # second liquidity type below. The order is safe: the dedupe compares kind and level only.
        if any(p["kind"] == kind and abs(p["level"] - level) <= tol for p in pools):
            return
        first, last = min(idxs), max(idxs); swept = -1
        for j in range(last + 1, n):
            if kind == "BSL" and H[j] > level and C[j] < level: swept = j; break
            if kind == "SSL" and L[j] < level and C[j] > level: swept = j; break
        pools.append({"kind": kind, "level": level, "from": first, "swept": swept, "type": ptype})
    # The deck enumerates TWO types of liquidity (knowledge/ict/core-a.md §2.7) and both rest on the same two
    # lines: "A Swing High at the top of the range will have stop losses from short positions (buy stops). This
    # is called buyside liquidity" (§2.6).
    #   type "equal" -- "Equal Highs & Lows are when price reaches the same price level multiple times."
    #   type "old"   -- "Old Highs & Lows are previous highs and lows." Old High -> BSL, Old Low -> SSL.
    # Equal pairs are added FIRST so that when a single swing sits on an already-recorded equal-highs line the
    # stronger, named reading keeps the row (the `tol` dedupe below drops the duplicate).
    #
    # Until 2026-09-19 only "equal" existed here, so a lone prior swing high/low could never be BSL/SSL: never a
    # sweep, never a target, never a dealing-range edge. That is the measured reason the dealing range kept
    # falling back to the scan-window edge (52 % of point-in-time samples read dr_source = mixed) --
    # docs/audits/2026-09-19-knowledge-fidelity.md finding 10.
    for a in range(len(sh)):
        for b in range(a + 1, len(sh)):
            if abs(H[sh[a]] - H[sh[b]]) <= tol and sh[b] - sh[a] >= 4: add("BSL", [sh[a], sh[b]], max(H[sh[a]], H[sh[b]]), "equal"); break
    for a in range(len(sl)):
        for b in range(a + 1, len(sl)):
            if abs(L[sl[a]] - L[sl[b]]) <= tol and sl[b] - sl[a] >= 4: add("SSL", [sl[a], sl[b]], min(L[sl[a]], L[sl[b]]), "equal"); break
    for i in sh: add("BSL", [i], H[i], "old")
    for i in sl: add("SSL", [i], L[i], "old")
    hi_i, lo_i = H.index(hi), L.index(lo)

    # MSS = body close beyond the swing preceding the raid (knowledge/ict/core-a.md §2.17, knowledge/ict/core-b.md §2.2). displacement = full-bodied
    # candle (knowledge/ict/core-a.md §2.16) read with the project ratios in analysis-params.json; ext/origin = the manipulation leg
    # (knowledge/ict/models.md §2.1.5); cisd = open of the first candle of the final opposing-colour run into the extreme (knowledge/ict/core-b.md §2.3)
    def is_disp(j):
        rg = H[j] - L[j]
        return rg > 0 and abs(C[j] - O[j]) >= DISP["body_min_ratio"] * rg and rg >= DISP["range_min_median_ratio"] * med
    def run_start(e, down):
        k = e
        if (C[k] >= O[k]) if down else (C[k] <= O[k]): k -= 1
        r = k
        while r >= 0 and ((C[r] < O[r]) if down else (C[r] > O[r])): r -= 1
        return r + 1 if r + 1 <= k else None
    mss = []
    piv = sorted([(i, "H") for i in sh] + [(i, "L") for i in sl])
    lastH = lastL = None; bias = 0
    for k, (pi, pt) in enumerate(piv):
        if pt == "H":
            if lastH is not None and H[pi] > H[lastH]: bias = 1
            lastH = pi
        else:
            if lastL is not None and L[pi] < L[lastL]: bias = -1
            lastL = pi
        nxt = piv[k + 1][0] if k + 1 < len(piv) else n
        for j in range(pi + 1, nxt):
            if bias == -1 and lastH is not None and C[j] > H[lastH]:
                frm = lastL or 0; e = min(range(frm, j), key=lambda q: L[q]); oi = max(range(lastH if lastH <= e else frm, e + 1), key=lambda q: H[q])
                r = run_start(e, True)
                cisd = {"level": O[r], "time": T[r], "confirmed": next((T[q] for q in range(r + 1, n) if C[q] > O[r]), None)} if r is not None else None
                mss.append({"type": "bull", "i": j, "level": H[lastH], "disp": is_disp(j), "ext": L[e], "ext_time": T[e], "origin": H[oi], "cisd": cisd,
                            "vol_mult": round(V[j] / avgv, 2) if avgv else None}); bias = 0; break
            if bias == 1 and lastL is not None and C[j] < L[lastL]:
                frm = lastH or 0; e = max(range(frm, j), key=lambda q: H[q]); oi = min(range(lastL if lastL <= e else frm, e + 1), key=lambda q: L[q])
                r = run_start(e, False)
                cisd = {"level": O[r], "time": T[r], "confirmed": next((T[q] for q in range(r + 1, n) if C[q] < O[r]), None)} if r is not None else None
                mss.append({"type": "bear", "i": j, "level": L[lastL], "disp": is_disp(j), "ext": H[e], "ext_time": T[e], "origin": L[oi], "cisd": cisd,
                            "vol_mult": round(V[j] / avgv, 2) if avgv else None}); bias = 0; break

    last = C[-1]
    # dealing range = nearest unswept BSL above / SSL below the last close (knowledge/ict/core-a.md §2.18); fallback = window extremes, reported as such
    wlo, whi = lo, hi
    above = [p["level"] for p in pools if p["swept"] < 0 and p["kind"] == "BSL" and p["level"] > last]
    below = [p["level"] for p in pools if p["swept"] < 0 and p["kind"] == "SSL" and p["level"] < last]
    hi = min(above) if above else whi; lo = max(below) if below else wlo; eq = (lo + hi) / 2
    dr_source = "pools" if (above and below) else ("mixed" if (above or below) else "window")
    pct = (last - lo) / (hi - lo) if hi > lo else 0.5
    # previous UTC-day high/low (knowledge/ict/core-a.md §2.12; day boundary 00Z is a project assumption) when the window spans more than one day
    days = {}
    for i in range(n):
        d = T[i][:10]; o = days.setdefault(d, {"h": H[i], "l": L[i], "i": i})
        o["h"] = max(o["h"], H[i]); o["l"] = min(o["l"], L[i])
    dkeys = sorted(days)
    prev_day = None
    if ict and len(dkeys) >= 2:
        pd_ = days[dkeys[-2]]; cur = days[dkeys[-1]]["i"]
        prev_day = {"date": dkeys[-2], "pdh": pd_["h"], "pdl": pd_["l"],
                    "pdh_state": "closed_through" if any(C[q] > pd_["h"] for q in range(cur, n)) else ("swept" if any(H[q] > pd_["h"] for q in range(cur, n)) else "intact"),
                    "pdl_state": "closed_through" if any(C[q] < pd_["l"] for q in range(cur, n)) else ("swept" if any(L[q] < pd_["l"] for q in range(cur, n)) else "intact")}
    # previous candle of THIS timeframe — ICT's own bias unit (knowledge/ict/core-a.md §2.11 PCH/PCL on H4/H1/M30/M15;
    # on a 1D/1W rung the previous candle IS the previous day/week, §2.12 PDH/PDL). Same three states as prev_day:
    # a body close beyond = that level was the draw; a wick beyond with the body closing back = failure to
    # displace (§2.14, §3.2 R5–R8). htf_context.ict_bias() reads this; it must reach facts.json to be usable.
    prev_candle = None
    if ict and n >= 2:
        prev_candle = {"tf": tf, "pch": H[n - 2], "pcl": L[n - 2],
                       "pch_state": "closed_through" if C[n - 1] > H[n - 2] else ("swept" if H[n - 1] > H[n - 2] else "intact"),
                       "pcl_state": "closed_through" if C[n - 1] < L[n - 2] else ("swept" if L[n - 1] < L[n - 2] else "intact")}
    cut = n - recent
    events = []
    for p in pools:
        if p["swept"] >= cut:
            events.append({"kind": "sweep", "pool": p["kind"], "level": p["level"], "i": p["swept"], "time": T[p["swept"]]})
    if ict and hi_i >= cut: events.append({"kind": "erl_high", "level": hi, "i": hi_i, "time": T[hi_i]})
    if ict and lo_i >= cut: events.append({"kind": "erl_low", "level": lo, "i": lo_i, "time": T[lo_i]})
    for m in mss:
        if m["i"] >= cut: events.append({"kind": "mss_" + m["type"], "level": m["level"], "i": m["i"], "time": T[m["i"]]})
    for f in fvgs:
        if f["i"] >= cut: events.append({"kind": "fvg_" + f["type"], "lo": f["lo"], "hi": f["hi"], "i": f["i"], "time": T[f["i"]]})
    for i in range(cut, n):
        if wyk and avgv and V[i] >= 1.5 * avgv:
            events.append({"kind": "volume", "mult": round(V[i] / avgv, 2), "i": i, "time": T[i], "dir": "up" if C[i] >= O[i] else "down"})

    open_fvgs = [f for f in fvgs if not f["mitigated"]]
    nearest_fvg = min(open_fvgs, key=lambda f: min(abs(last - f["lo"]), abs(last - f["hi"])), default=None)
    unswept = [p for p in pools if p["swept"] < 0]
    return {
        "last": last, "lo": lo, "hi": hi, "eq": eq, "pct": pct, "dr_source": dr_source, "window_lo": wlo, "window_hi": whi,
        "prev_day": prev_day, "prev_candle": prev_candle,
        "med_range": med, "last_time": T[-1], "avgv": avgv,
        "pools": pools, "unswept": unswept, "mss": mss[-3:], "fvgs_all": fvgs, "fvgs_open": open_fvgs[-4:], "nearest_fvg": nearest_fvg,
        "events": events, "last_mss": mss[-1] if mss else None,
    }


def anchor_facts(c, spec):
    """Compare the window to the named anchor levels of the last full analysis. Pure arithmetic.
    Verdicts use the last COMPLETED candle (c[-2]); the forming candle (c[-1]) is reported separately."""
    T = [x["time"] for x in c]; C = [x["close"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]
    n = len(c); ref_i = n - 2 if n > 1 else 0; ref = C[ref_i]
    lv, levels = {}, []
    for a in spec.get("levels", []):
        price, t0, role = a["price"], a.get("time", ""), a.get("role")
        after = [i for i, t in enumerate(T) if t > t0]
        first = None
        for i in after:
            if i > ref_i: break                      # never let the forming candle "confirm" a break
            if (role == "support" and C[i] < price) or (role == "resistance" and C[i] > price):
                first = i; break
        extreme = None
        if first is not None:
            seg = range(first, ref_i + 1)
            extreme = min(L[i] for i in seg) if role == "support" else max(H[i] for i in seg)
        # `method` and `short` come straight from anchors.<style>.json. They were dropped here, so every consumer
        # reading facts (htf_context.brief_lines, the ladder) lost the ability to tell a Wyckoff-named level from
        # an ICT one — and handed Wyckoff anchor NAMES to an ICT-only run (audit 2026-09-13).
        d = {"name": a["name"], "label": a.get("label", a["name"]), "method": a.get("method"), "short": a.get("short"),
             "role": role, "price": price, "time": t0,
             "ref_close": ref, "ref_vs": "above" if ref > price else "below",
             "dist_pct": round((ref - price) / price * 100, 3),
             "first_close_beyond": ({"time": T[first], "close": C[first]} if first is not None else None),
             "extreme_since": extreme,
             "forming_beyond": (C[-1] < price) if role == "support" else (C[-1] > price),
             "anchor_in_window": bool(t0) and t0 >= T[0]}
        lv[a["name"]] = d; levels.append(d)
    rule = spec.get("rule", {}); key = txt = short = None
    if rule.get("type") == "range" and rule.get("support") in lv and rule.get("resistance") in lv:
        s, r = lv[rule["support"]], lv[rule["resistance"]]
        if ref > r["price"]: key, txt, short = "above_res", f"PHÁ TRÊN {r['label']} — xác nhận tiếp diễn tăng", f"PHÁ TRÊN {r['label']}"
        elif ref < s["price"]: key, txt, short = "below_sup", f"PHÁ DƯỚI {s['label']} — cấu trúc mất hiệu lực, cần phân tích lại", f"PHÁ DƯỚI {s['label']}"
        else: key, txt, short = "inside", "CHỜ — vẫn giữa vùng", "CHỜ (giữa vùng)"
    elif rule.get("type") == "floor" and rule.get("support") in lv:
        s = lv[rule["support"]]
        if ref < s["price"]: key, txt, short = "below_sup", f"PHÁ CẤU TRÚC — đóng dưới {s['label']}", "PHÁ CẤU TRÚC"
        else: key, txt, short = "hold", rule.get("hold_text", f"vẫn giữ trên {s['label']}"), f"GIỮ TRÊN {s['label']}"
    return {"source": spec.get("source"), "updated": spec.get("updated"), "levels": levels,
            "ref_close": {"time": T[ref_i], "close": ref}, "verdict_key": key, "verdict": txt, "verdict_short": short}


def setup_candidate(a, c, lookback):
    """entry/stop/target/R for the classic chain sweep -> MSS (same direction) -> FVG, with the sweep inside the
    last `lookback` bars. None if no recent sweep+MSS."""
    H = [x["high"] for x in c]; L = [x["low"] for x in c]; T = [x["time"] for x in c]
    n = len(c)
    sweeps = [p for p in a["pools"] if p["swept"] >= max(0, n - lookback)]
    if not sweeps or not a["mss"]: return None
    s = max(sweeps, key=lambda p: p["swept"]); m = a["mss"][-1]
    if m["i"] <= s["swept"]: return None
    if s["kind"] == "SSL" and m["type"] == "bull": side = "long"
    elif s["kind"] == "BSL" and m["type"] == "bear": side = "short"
    else: return None
    O = [x["open"] for x in c]; Cc = [x["close"] for x in c]
    pd_ok = (a["pct"] < 0.5) if side == "long" else (a["pct"] > 0.5)   # longs in discount, shorts in premium (knowledge/ict/core-a.md §3.4 R13)
    base = {"side": side, "sweep": {"pool": s["kind"], "level": s["level"], "time": T[s["swept"]]},
            "mss": {"level": m["level"], "time": T[m["i"]], "vol_mult": m.get("vol_mult"), "displacement": m.get("disp"), "cisd": m.get("cisd")},
            "in_discount": a["pct"] < 0.5, "pd_ok": pd_ok, "dr_source": a["dr_source"]}
    if not m.get("disp"):
        base.update({"complete": False, "missing": "displacement trên nến phá swing (thân nến nhỏ / biên độ nhỏ — chưa phải MSS theo knowledge/ict/core-a.md §2.16)"}); return base
    fv = [f for f in a["fvgs_all"] if f["i"] > s["swept"] and f["type"] == ("bull" if side == "long" else "bear")]
    if not fv:
        base.update({"complete": False, "missing": "FVG cùng chiều sau cú quét"}); return base
    f = fv[-1]
    # OB = last opposing-close candle before the MSS candle (knowledge/ict/core-b.md §2.5): open line, 0.5 mean threshold, body low/high
    ob = None
    for q in range(m["i"] - 1, s["swept"] - 1, -1):
        if (Cc[q] < O[q]) if side == "long" else (Cc[q] > O[q]):
            ob = {"open": O[q], "mt": (O[q] + Cc[q]) / 2, "body_low": min(O[q], Cc[q]), "body_high": max(O[q], Cc[q]), "time": T[q]}; break
    leg = abs(m["origin"] - m["ext"])
    if side == "long":
        entry = f["hi"]; stop = min(L[s["swept"]:m["i"] + 1])
        entries = {"iofed": f["hi"], "ce": f["ce"], "fill": f["lo"]}
        stops = {"gap_far_edge": f["lo"], "ob_body_low": ob["body_low"] if ob else None, "sweep_extreme": stop}
        std = {"-2": m["origin"] + 2 * leg, "-2.5": m["origin"] + 2.5 * leg, "-4": m["origin"] + 4 * leg} if leg > 0 else None
        tg = [p["level"] for p in a["unswept"] if p["kind"] == "BSL" and p["level"] > entry]
        # TARGET ORDER, per the decks, and this time in the decks' own order. models.md §2.1.5 is explicit:
        # "the main focus for identifying targets is using standard deviation projections" -- the -2/-2.5
        # zone first, -4/-4.5 second. Liquidity levels are what the decks call a DRAW (core-a.md §2.8), a
        # place price is pulled toward and may react at; they are recorded below as `objective` for the
        # reader, not used as the target. The dealing range's far edge is the fallback only when no
        # manipulation leg exists to project from: it is the target the R13 diagram itself draws
        # (core-a.md §3.4, "target is the opposite range extreme").
        #
        # Until 2026-09-19 (second correction that day) the order was inverted -- nearest unswept pool first,
        # the projection only as a fallback. That was survivable while the only pools were equal highs/lows;
        # the same morning's addition of Old Highs & Lows (the deck's FIRST liquidity type, §2.7 -- correct
        # for sweeps and for the dealing range) made "nearest unswept pool" almost always the very next swing,
        # and planned R collapsed: median 0.55 across the reachable 15m population, ONE trade over the 3R
        # floor. On the SAME twenty entries, the deck's own target gave a median planned R of 2.91, +0.95R per
        # trade against +0.64R, and NINE trades over the floor. The scanner is the one seam both the backtest
        # (ict_setups_live) and the live runner (ict_live_setups) read, so this is the whole fix.
        objective = min(tg) if tg else None
        target, tk = ((std["-2"], "dự phóng −2σ (models.md §2.1.5)") if std and std["-2"] > entry
                      else (a["hi"], "biên trên dealing range (core-a.md R13)") if a["hi"] > entry
                      else (None, "không có mục tiêu: không dự phóng σ, biên range không ở trên entry"))
        if target is None:
            return None
        risk, reward = entry - stop, target - entry
    else:
        entry = f["lo"]; stop = max(H[s["swept"]:m["i"] + 1])
        entries = {"iofed": f["lo"], "ce": f["ce"], "fill": f["hi"]}
        stops = {"gap_far_edge": f["hi"], "ob_body_high": ob["body_high"] if ob else None, "sweep_extreme": stop}
        std = {"-2": m["origin"] - 2 * leg, "-2.5": m["origin"] - 2.5 * leg, "-4": m["origin"] - 4 * leg} if leg > 0 else None
        tg = [p["level"] for p in a["unswept"] if p["kind"] == "SSL" and p["level"] < entry]
        # Mirror of the long branch above -- see that comment for the order and for what changed.
        objective = max(tg) if tg else None
        target, tk = ((std["-2"], "dự phóng −2σ (models.md §2.1.5)") if std and std["-2"] < entry
                      else (a["lo"], "biên dưới dealing range (core-a.md R13)") if a["lo"] < entry
                      else (None, "không có mục tiêu: không dự phóng σ, biên range không ở dưới entry"))
        if target is None:
            return None
        risk, reward = stop - entry, entry - target
    R = round(reward / risk, 2) if risk > 0 else None
    base.update({"complete": True, "fvg": {"lo": f["lo"], "hi": f["hi"], "ce": f["ce"], "time": T[f["i"]], "mitigated": f["mitigated"]}, "ob": ob,
                 "entry": entry, "entry_models": entries, "stop": stop, "stop_owner": "sweep_extreme", "stop_options": stops,
                 "target": target, "target_kind": tk, "objective": objective, "std_targets": std, "R": R, "rr_ok": (R is not None and MIN_RR is not None and R >= MIN_RR), "min_rr": MIN_RR})
    return base


def facts_entry(a, stance, an, su, ctx):
    """The per-symbol payload written to prelim/<style>.facts.json — the ONLY channel by which a scan reaches
    htf_context, the checkers and the page builder. Extracted from main() so what it carries is testable: the draw
    levels (prev_day) were computed in analyze() and then dropped here, which is why ICT had no bias of its own."""
    return {"last": a["last"], "last_time": a["last_time"], "lo": a["lo"], "hi": a["hi"], "eq": a["eq"], "pct": round(a["pct"], 4),
            "stance": stance, "anchors": an, "setup": su, "last_mss": a["last_mss"], "nearest_fvg": a["nearest_fvg"],
            "prev_day": a["prev_day"], "prev_candle": a["prev_candle"],
            "unswept_pools": a["unswept"], "events_recent": a["events"],
            "context": ctx}   # HTF context: giảm khung (knowledge/wyckoff/advance.md §2.7, WA p93–96)


def fmt(sym, v):
    return f"{v:,.0f}" if sym.startswith("BTC") else f"{v:,.2f}"


def sessions_note(sym):
    return " (killzone London/NY có ý nghĩa với vàng; phiên Á thường mỏng)" if I.is_tick_volume(sym) else ""


def facts_table(sym, a, an, su):
    f = lambda v: fmt(sym, v)
    src = {"pools": "dealing range = BSL↔SSL chưa quét gần nhất", "mixed": "dealing range: một biên là BSL/SSL, biên kia là biên cửa sổ", "window": "dealing range = biên cửa sổ (không có cặp BSL/SSL chưa quét)"}[a.get("dr_source", "window")]
    rows = [("Giá / vị trí", f"{f(a['last'])} · {a['pct']*100:.0f}% của {f(a['lo'])}–{f(a['hi'])} · EQ {f(a['eq'])} · {src} · cửa sổ {f(a['window_lo'])}–{f(a['window_hi'])}")]
    if a.get("prev_day"):
        p_ = a["prev_day"]; st = {"intact": "chưa chạm", "swept": "râu xuyên, thân đóng lại (failure to displace)", "closed_through": "thân đã đóng qua"}
        rows.append(("PDH / PDL (ngày UTC trước)", f"PDH {f(p_['pdh'])} ({st[p_['pdh_state']]}) · PDL {f(p_['pdl'])} ({st[p_['pdl_state']]})"))
    if an:
        for L_ in an["levels"]:
            s = f"{L_['label']} {f(L_['price'])}: đóng {L_['ref_close']and ''}{'trên' if L_['ref_vs']=='above' else 'dưới'} ({L_['dist_pct']:+.2f}%)"
            if L_["first_close_beyond"]:
                b = L_["first_close_beyond"]; s += f" · nến đóng {'dưới' if L_['role']=='support' else 'trên'} đầu tiên {b['time'][5:16].replace('T',' ')}Z @ {f(b['close'])}"
                if L_["extreme_since"] is not None: s += f" · cực trị sau đó {f(L_['extreme_since'])}"
            rows.append(("Mốc neo", s))
        if an["verdict"]:
            rows.append(("Verdict theo luật", f"{an['verdict']} (nến đóng {an['ref_close']['time'][5:16].replace('T',' ')}Z = {f(an['ref_close']['close'])})"))
    if su:
        if su.get("complete"):
            ci = su["mss"].get("cisd"); ci_s = f" · CISD {f(ci['level'])} ({'đã đóng qua' if ci.get('confirmed') else 'chưa đóng qua'})" if ci else ""
            rows.append(("Setup ứng viên", f"{su['side'].upper()} · quét {su['sweep']['pool']} {f(su['sweep']['level'])} ({su['sweep']['time'][11:16]}Z) → MSS có displacement {f(su['mss']['level'])} ({su['mss']['time'][11:16]}Z, vol {su['mss']['vol_mult']}×){ci_s} → FVG {f(su['fvg']['lo'])}–{f(su['fvg']['hi'])} (CE {f(su['fvg']['ce'])}){' (đã lấp)' if su['fvg']['mitigated'] else ''}{'' if su['pd_ok'] else ' · SAI NỬA RANGE (long phải ở discount, short ở premium)'}"))
            em = su["entry_models"]; so = su["stop_options"]; ob = su.get("ob")
            rows.append(("Entry (3 mô hình FVG)", f"IOFED {f(em['iofed'])} · CE {f(em['ce'])} · lấp đầy {f(em['fill'])}" + (f" · OB open {f(ob['open'])} / 0.5 MT {f(ob['mt'])}" if ob else "")))
            rows.append(("Stop (chủ sở hữu = cực trị cú quét)", " · ".join(f"{k} {f(v)}" for k, v in so.items() if v is not None)))
            st_ = su.get("std_targets"); st_s = f" · STD −2 {f(st_['-2'])} / −2.5 {f(st_['-2.5'])} / −4 {f(st_['-4'])}" if st_ else ""
            rr_note = "" if su["rr_ok"] else (f" (< {su['min_rr']}R tối thiểu, knowledge/ict/models.md §3.1 luật 23)"
                                              if su["min_rr"] is not None else " (không đọc được sàn R/R)")
            rows.append(("Entry / Stop / Target / R", f"{f(su['entry'])} / {f(su['stop'])} / {f(su['target'])} ({su['target_kind']}) / R = {su['R']}{rr_note}{st_s}"))
        else:
            rows.append(("Setup ứng viên", f"{su['side'].upper()} chưa hoàn chỉnh: quét {su['sweep']['pool']} {f(su['sweep']['level'])} → MSS {f(su['mss']['level'])}, thiếu {su['missing']}"))
    body = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)
    return f"<table class=\"facts\"><tbody>{body}</tbody></table><p class=\"facts-note\">Số liệu trong bảng do scanner tính ({CITE['sys']}); mọi nhận định bên dưới phải dùng đúng các con số này.</p>"


def prelim_html(sym, a, tf, style, an=None, su=None):
    f = lambda v: fmt(sym, v)
    zone = "vùng giá thấp (discount)" if a["pct"] < 0.5 else "vùng giá cao (premium)"
    recent_sweeps = [e for e in a["events"] if e["kind"] == "sweep"]
    recent_mss = [e for e in a["events"] if e["kind"].startswith("mss_")]
    lines = []
    dr_note = {"pools": "dealing range = cặp BSL↔SSL chưa quét gần nhất", "mixed": "dealing range một biên là BSL/SSL, biên kia là biên cửa sổ", "window": "không có cặp BSL/SSL chưa quét nên dealing range = biên cửa sổ"}[a.get("dr_source", "window")]
    lines.append(f"Giá {f(a['last'])} = {a['pct']*100:.0f}% của dealing range {f(a['lo'])}–{f(a['hi'])} ({dr_note}), {zone}, EQ {f(a['eq'])}. "
                 f"<span class=\"cite\">{CITE['pd']}</span>")
    if recent_sweeps:
        s = recent_sweeps[-1]; t = s["time"][11:16]
        side = "SSL (đáy bằng nhau)" if s["pool"] == "SSL" else "BSL (đỉnh bằng nhau)"
        lines.append(f"Quét thanh khoản {side} tại {f(s['level'])} lúc {t} UTC, nến đóng ngược lại phía trong — "
                     f"đây là liquidity grab, chưa phải MSS cho tới khi có nến đóng phá swing ngược chiều. "
                     f"<span class=\"cite\">{CITE['grab']} · {CITE['liq']}</span>")
    erl = [e for e in a["events"] if e["kind"] in ("erl_high", "erl_low")]
    if erl:
        e = erl[-1]
        lines.append(f"Giá vừa chạm {'đỉnh' if e['kind']=='erl_high' else 'đáy'} ERL của cửa sổ ({f(e['level'])}, {e['time'][11:16]} UTC) — thanh khoản ngoài range, nơi thường có phản ứng. "
                     f"<span class=\"cite\">{CITE['erl']}</span>")
    if a["last_mss"]:
        m = a["last_mss"]
        lines.append(f"{'MSS' if m.get('disp') else 'Nến đóng qua swing nhưng thiếu displacement (chưa phải MSS)'} gần nhất: {'tăng' if m['type']=='bull' else 'giảm'} (đóng cửa vượt swing {f(m['level'])}, vol {m.get('vol_mult')}×"
                     + (f"; CISD {f(m['cisd']['level'])} {'đã' if m['cisd'].get('confirmed') else 'chưa'} được đóng qua" if m.get('cisd') else "") + "). "
                     f"<span class=\"cite\">{CITE['mss']}</span>")
    if a["nearest_fvg"]:
        g = a["nearest_fvg"]
        lines.append(f"FVG chưa lấp gần giá nhất: {'tăng' if g['type']=='bull' else 'giảm'} {f(g['lo'])}–{f(g['hi'])}. "
                     f"<span class=\"cite\">{CITE['fvg']}</span>")
    vol = [e for e in a["events"] if e["kind"] == "volume"]
    if vol:
        v = vol[-1]
        lines.append(f"Volume {v['mult']}x trung bình lúc {v['time'][11:16]} UTC trên nến {'tăng' if v['dir']=='up' else 'giảm'} — kiểm tra Effort-vs-Result trước khi tin vào hướng. "
                     f"<span class=\"cite\">{CITE['evr']} · bội số: {CITE['sys']}</span>")
    if an and an["verdict"]:
        cite = CITE["spring"] + " · " + CITE["sos"] if style == "swing" else CITE["sos"] + " · " + CITE["pd"]
        lines.append(f"So với mốc neo của phân tích đầy đủ gần nhất: <strong>{an['verdict']}</strong> (tính trên nến đã đóng {an['ref_close']['time'][11:16]} UTC). "
                     f"<span class=\"cite\">{cite} · phép so sánh: {CITE['sys']}</span>")
    # rule-based preliminary stance
    stance = "CHỜ"
    why = "chưa có quét thanh khoản + MSS xác nhận cùng chiều trong các nến gần đây"
    if recent_sweeps:
        s = recent_sweeps[-1]
        if s["pool"] == "SSL" and a["pct"] < 0.5:
            stance = "THEO DÕI LONG"; why = f"vừa quét SSL {f(s['level'])} trong vùng discount — chờ MSS tăng hoặc FVG tăng để xác nhận"
        elif s["pool"] == "BSL" and a["pct"] > 0.5:
            stance = "THEO DÕI SHORT"; why = f"vừa quét BSL {f(s['level'])} trong vùng premium — chờ MSS giảm hoặc FVG giảm để xác nhận"
    if recent_mss and recent_sweeps:
        m = recent_mss[-1]; s = recent_sweeps[-1]
        if (m["kind"] == "mss_bull" and s["pool"] == "SSL") or (m["kind"] == "mss_bear" and s["pool"] == "BSL"):
            if a["last_mss"] and a["last_mss"].get("disp"):
                stance = "SETUP TIỀM NĂNG"; why = "quét thanh khoản rồi MSS có displacement cùng chiều — mô hình sweep→MSS; cần nhận định cục bộ (Sonnet) và kiểm tra Wyckoff/volume trước khi vào lệnh"
            else:
                why = "quét thanh khoản rồi nến đóng qua swing cùng chiều nhưng thiếu displacement (thân/biên độ nhỏ) — chưa đủ là MSS theo knowledge/ict/core-a.md §2.16"
    ts = a["last_time"][11:16]
    html = (f"<div class=\"prelim-head\">Nhận định sơ bộ tự động · {tf} · dữ liệu tới {ts} UTC · "
            f"<strong>{stance}</strong></div>"
            + facts_table(sym, a, an, su)
            + "<!--MODEL-->"
            + "<div class=\"prelim-scan\">"
            + "".join(f"<p>{l}</p>" for l in lines)
            + f"<p><em>Vì sao {stance.lower()}:</em> {why}. Đây là quét theo luật cố định (pivot {PIV} nến, dung sai đỉnh/đáy bằng nhau {EQ_TOL*100:.2f}%, FVG ≥{FVG_MIN}× biên độ nến trung vị, displacement = thân ≥{DISP['body_min_ratio']} biên độ nến và biên độ ≥{DISP['range_min_median_ratio']}× trung vị — {CITE['sys']}), "
              f"không phải nhận định của mô hình; bản đọc đầy đủ ở bảng bên dưới có thể cũ hơn dữ liệu này.</p>"
            + "</div>")
    return html, stance


def main():
    import importlib.util as _iu
    _hs = _iu.spec_from_file_location("htf_context", f"{ROOT}/scripts/htf_context.py"); htf = _iu.module_from_spec(_hs); _hs.loader.exec_module(htf)
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True); ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--style", required=True); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--recent", type=int, default=4, help="bars counted as 'recent' for events")
    ap.add_argument("--state", default=None)
    ap.add_argument("--setup-lookback", type=int, default=None, help="bars in which the setup's sweep must sit (default max(12, 6*recent))")
    args = ap.parse_args()
    # This scanner feeds BOTH structural lanes (the ICT structures and, via anchors + volume outliers, Wyckoff's
    # Effort-vs-Result hint), so it stops entirely only when neither is engaged. With one of the two on, the
    # per-method work is skipped inside analyze() instead (user decision 2026-09-13).
    scan_methods = htf.engaged_methods(args.style)
    if not scan_methods:
        print(json.dumps({"skipped": f"no structural dimension engaged for style '{args.style}' "
                                     f"(/automation dimension wyckoff|ict on) — scanner did no work"}, ensure_ascii=False))
        sys.exit(0)   # 0 = "no NEW events", the same contract scan-loop.sh already handles
    syms = args.symbols.split(",")
    state_path = args.state or f"{ROOT}/data/live/scan-state.{args.style}.json"
    try:
        state = json.load(open(state_path))
    except Exception:
        state = {}
    out_dir = f"{ROOT}/data/live/prelim"; os.makedirs(out_dir, exist_ok=True)
    anchors = load_anchors(args.style) or {}
    result, new_events, facts = {}, [], {}
    for sym in syms:
        c = load(sym, args.tf)[-args.n:]
        a = analyze(c, args.recent, tf=args.tf, methods=scan_methods)
        spec = (anchors.get("symbols") or {}).get(sym)
        an = anchor_facts(c, {**spec, "source": anchors.get("source"), "updated": anchors.get("updated")}) if spec else None
        su = setup_candidate(a, c, args.setup_lookback or max(12, args.recent * 6))
        html, stance = prelim_html(sym, a, args.tf, args.style, an, su)
        tmp = f"{out_dir}/.{args.style}.{sym}.html.tmp"
        with open(tmp, "w") as f: f.write(html)
        os.replace(tmp, f"{out_dir}/{args.style}.{sym}.html")
        seen = set(state.get(sym, []))
        trigger_kinds = {"sweep", "erl_high", "erl_low", "mss_bull", "mss_bear"}
        fresh = [e for e in a["events"] if e["kind"] in trigger_kinds and f"{e['kind']}@{e['time']}" not in seen]
        for e in fresh: new_events.append({"symbol": sym, **e})
        state[sym] = sorted(set(list(seen) + [f"{e['kind']}@{e['time']}" for e in a["events"]]))[-200:]
        result[sym] = {"last": a["last"], "pct": round(a["pct"], 4), "eq": a["eq"], "stance": stance,
                       "verdict": an["verdict"] if an else None, "setup": su,
                       "events_recent": a["events"], "new_events": fresh, "prelim_file": f"data/live/prelim/{args.style}.{sym}.html"}
        facts[sym] = facts_entry(a, stance, an, su, htf.load_context(args.style, sym))
    json.dump(state, open(state_path, "w"))
    first_t = load(syms[0], args.tf)[-args.n:][0]["time"]
    meta = {"tf": args.tf, "n": args.n, "window_first": first_t,
            "window_last": max(load(sym, args.tf)[-1]["time"] for sym in syms),
            "symbols": {sym: {"last": result[sym]["last"], "pct": result[sym]["pct"], "stance": result[sym]["stance"],
                              "verdict": result[sym]["verdict"], "verdict_short": (facts[sym]["anchors"] or {}).get("verdict_short"),
                              "setup": (f"{result[sym]['setup']['side']} R={result[sym]['setup'].get('R')}" if result[sym]["setup"] and result[sym]["setup"].get("complete") else None)}
                        for sym in syms}}
    json.dump(meta, open(f"{out_dir}/{args.style}.meta.json", "w"), ensure_ascii=False)
    scanned = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump({"scanned_at": scanned, "tf": args.tf, "n": args.n, "window_first": first_t, "window_last": meta["window_last"],
               "anchors_source": anchors.get("source"), "symbols": facts},
              open(f"{out_dir}/{args.style}.facts.json", "w"), ensure_ascii=False, indent=1)
    result["_new_events"] = new_events
    result["_scanned_at"] = scanned
    print(json.dumps(result, ensure_ascii=False, indent=1))
    sys.exit(3 if new_events else 0)


if __name__ == "__main__":
    main()
