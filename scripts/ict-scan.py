#!/usr/bin/env python3
"""Deterministic Wyckoff/ICT event scanner + preliminary read (no LLM).

Mirrors the artifacts' client-side ictAnalyze() so the preliminary read matches what the chart draws:
3-bar pivots, equal highs/lows (BSL/SSL) + external range liquidity (ERL), sweeps (wick through a
level, close back), 3-candle FVGs until mitigation, MSS (close beyond last swing after a lower-low /
higher-high), premium/discount vs equilibrium, and volume outliers (Effort-vs-Result hint).

Usage: ict-scan.py --tf 1m --n 180 --style scalping [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--state FILE]
Prints JSON {symbol: {...}} to stdout; writes Vietnamese HTML snippets to data/live/prelim/<style>.<SYM>.html;
exit code 0 = no NEW events since the state file, 3 = new events (caller may trigger a full analysis + alert).
Sources cited in the snippets: docs/TTrades PDFs (3. Liquidity, 8. Discount__Premium, 11. MSS_vs_Liquidity_Grab,
12. Fair_Value_Gaps, 18. Market_Structure_Shift, IRL-ERL) and knowledge/07 (Effort-vs-Result); thresholds
(0.08% equal-level tolerance, 3-bar pivot, 1.5x volume) are this system's own parameters, and say so.
"""
import argparse, json, os, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CITE = {
    "liq": "docs/TTrades PDFs/3. Liquidity.pdf tr.1–5 · knowledge/04 §2.6–2.7",
    "grab": "docs/TTrades PDFs/11. MSS_vs_Liquidity_Grab.pdf tr.1–4 · knowledge/04 §2.14, §2.17",
    "pd": "docs/TTrades PDFs/8. Discount__Premium.pdf tr.1–5 · knowledge/04 §2.18–2.19",
    "fvg": "docs/TTrades PDFs/12. Fair_Value_Gaps.pdf tr.1–6 · knowledge/04 §2.21–2.24",
    "mss": "docs/TTrades PDFs/18. Market_Structure_Shift.pdf tr.1–3 · knowledge/05 §2.1–2.2",
    "erl": "docs/TTrades PDFs/IRL-ERL.pdf tr.1–8 · knowledge/05 §2.13",
    "evr": "WMT p019–022, p149–154 · knowledge/07 §2.3, §4.1",
    "sys": "[tính toán của hệ thống — không phải trích dẫn tài liệu]",
}


def load(sym, tf):
    with open(f"{ROOT}/data/live/market-data/ohlcv.{sym}.{tf}.json") as f:
        return json.load(f)["candles"]


def analyze(c, recent):
    n = len(c)
    O = [x["open"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
    V = [x.get("volume", 0) for x in c]; T = [x["time"] for x in c]
    lo, hi = min(L), max(H); eq = (lo + hi) / 2
    med = sorted(h - l for h, l in zip(H, L))[n // 2]
    avgv = sum(V) / n if n else 0

    sh, sl = [], []
    for i in range(3, n - 3):
        if all(H[j] <= H[i] for j in range(i - 3, i + 4) if j != i): sh.append(i)
        if all(L[j] >= L[i] for j in range(i - 3, i + 4) if j != i): sl.append(i)

    fvgs = []
    for i in range(1, n - 1):
        f = None
        if H[i - 1] < L[i + 1]: f = {"type": "bull", "i": i, "lo": H[i - 1], "hi": L[i + 1]}
        elif L[i - 1] > H[i + 1]: f = {"type": "bear", "i": i, "lo": H[i + 1], "hi": L[i - 1]}
        if not f: continue
        f["size"] = f["hi"] - f["lo"]; f["end"] = n - 1; f["mitigated"] = False
        for j in range(i + 2, n):
            if (f["type"] == "bull" and L[j] <= f["hi"]) or (f["type"] == "bear" and H[j] >= f["lo"]):
                f["end"] = j; f["mitigated"] = True; break
        if f["size"] >= 0.6 * med: fvgs.append(f)

    tol = eq * 0.0008
    pools = []
    def add(kind, idxs, level):
        first, last = min(idxs), max(idxs); swept = -1
        for j in range(last + 1, n):
            if kind == "BSL" and H[j] > level and C[j] < level: swept = j; break
            if kind == "SSL" and L[j] < level and C[j] > level: swept = j; break
        if not any(p["kind"] == kind and abs(p["level"] - level) <= tol for p in pools):
            pools.append({"kind": kind, "level": level, "from": first, "swept": swept})
    for a in range(len(sh)):
        for b in range(a + 1, len(sh)):
            if abs(H[sh[a]] - H[sh[b]]) <= tol and sh[b] - sh[a] >= 4: add("BSL", [sh[a], sh[b]], max(H[sh[a]], H[sh[b]])); break
    for a in range(len(sl)):
        for b in range(a + 1, len(sl)):
            if abs(L[sl[a]] - L[sl[b]]) <= tol and sl[b] - sl[a] >= 4: add("SSL", [sl[a], sl[b]], min(L[sl[a]], L[sl[b]])); break
    hi_i, lo_i = H.index(hi), L.index(lo)

    mss, obs = [], []
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
                mss.append({"type": "bull", "i": j, "level": H[lastH]}); bias = 0; break
            if bias == 1 and lastL is not None and C[j] < L[lastL]:
                mss.append({"type": "bear", "i": j, "level": L[lastL]}); bias = 0; break

    last = C[-1]; pct = (last - lo) / (hi - lo) if hi > lo else 0.5
    cut = n - recent
    events = []
    for p in pools:
        if p["swept"] >= cut:
            events.append({"kind": "sweep", "pool": p["kind"], "level": p["level"], "i": p["swept"], "time": T[p["swept"]]})
    if hi_i >= cut: events.append({"kind": "erl_high", "level": hi, "i": hi_i, "time": T[hi_i]})
    if lo_i >= cut: events.append({"kind": "erl_low", "level": lo, "i": lo_i, "time": T[lo_i]})
    for m in mss:
        if m["i"] >= cut: events.append({"kind": "mss_" + m["type"], "level": m["level"], "i": m["i"], "time": T[m["i"]]})
    for f in fvgs:
        if f["i"] >= cut: events.append({"kind": "fvg_" + f["type"], "lo": f["lo"], "hi": f["hi"], "i": f["i"], "time": T[f["i"]]})
    for i in range(cut, n):
        if avgv and V[i] >= 1.5 * avgv:
            events.append({"kind": "volume", "mult": round(V[i] / avgv, 2), "i": i, "time": T[i], "dir": "up" if C[i] >= O[i] else "down"})

    open_fvgs = [f for f in fvgs if not f["mitigated"]]
    nearest_fvg = min(open_fvgs, key=lambda f: min(abs(last - f["lo"]), abs(last - f["hi"])), default=None)
    unswept = [p for p in pools if p["swept"] < 0]
    return {
        "last": last, "lo": lo, "hi": hi, "eq": eq, "pct": pct, "last_time": T[-1],
        "pools": pools, "unswept": unswept, "mss": mss[-3:], "fvgs_open": open_fvgs[-4:], "nearest_fvg": nearest_fvg,
        "events": events, "last_mss": mss[-1] if mss else None,
    }


def fmt(sym, v):
    return f"{v:,.0f}" if sym.startswith("BTC") else f"{v:,.2f}"


def prelim_html(sym, a, tf, style):
    f = lambda v: fmt(sym, v)
    zone = "vùng giá thấp (discount)" if a["pct"] < 0.5 else "vùng giá cao (premium)"
    recent_sweeps = [e for e in a["events"] if e["kind"] == "sweep"]
    recent_mss = [e for e in a["events"] if e["kind"].startswith("mss_")]
    lines = []
    lines.append(f"Giá {f(a['last'])} = {a['pct']*100:.0f}% biên độ cửa sổ ({f(a['lo'])}–{f(a['hi'])}), {zone}, EQ {f(a['eq'])}. "
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
        lines.append(f"MSS gần nhất: {'tăng' if m['type']=='bull' else 'giảm'} (đóng cửa vượt swing {f(m['level'])}). "
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
            stance = "SETUP TIỀM NĂNG"; why = "quét thanh khoản rồi MSS cùng chiều — mô hình sweep→MSS; cần nhận định đầy đủ (Sonnet) và kiểm tra Wyckoff/volume trước khi vào lệnh"
    ts = a["last_time"][11:16]
    html = (f"<div class=\"prelim-head\">Nhận định sơ bộ tự động · {tf} · dữ liệu tới {ts} UTC · "
            f"<strong>{stance}</strong></div>"
            + "".join(f"<p>{l}</p>" for l in lines)
            + f"<p><em>Vì sao {stance.lower()}:</em> {why}. Đây là quét theo luật cố định (pivot 3 nến, dung sai đỉnh/đáy bằng nhau 0,08%, FVG ≥0,6× biên độ nến trung vị — {CITE['sys']}), "
              f"không phải nhận định của mô hình; bản đọc đầy đủ ở bảng bên dưới có thể cũ hơn dữ liệu này.</p>")
    return html, stance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True); ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--style", required=True); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--recent", type=int, default=4, help="bars counted as 'recent' for events")
    ap.add_argument("--state", default=None)
    args = ap.parse_args()
    state_path = args.state or f"{ROOT}/data/live/scan-state.{args.style}.json"
    try:
        state = json.load(open(state_path))
    except Exception:
        state = {}
    out_dir = f"{ROOT}/data/live/prelim"; os.makedirs(out_dir, exist_ok=True)
    result, new_events = {}, []
    for sym in args.symbols.split(","):
        c = load(sym, args.tf)[-args.n:]
        a = analyze(c, args.recent)
        html, stance = prelim_html(sym, a, args.tf, args.style)
        with open(f"{out_dir}/{args.style}.{sym}.html", "w") as f:
            f.write(html)
        seen = set(state.get(sym, []))
        # only structural events trigger a full re-analysis/alert; FVG formation and volume feed the prelim text only
        trigger_kinds = {"sweep", "erl_high", "erl_low", "mss_bull", "mss_bear"}
        fresh = [e for e in a["events"] if e["kind"] in trigger_kinds and f"{e['kind']}@{e['time']}" not in seen]
        for e in fresh: new_events.append({"symbol": sym, **e})
        state[sym] = sorted(set(list(seen) + [f"{e['kind']}@{e['time']}" for e in a["events"]]))[-200:]
        result[sym] = {"last": a["last"], "pct": round(a["pct"], 4), "eq": a["eq"], "stance": stance,
                       "events_recent": a["events"], "new_events": fresh, "prelim_file": f"data/live/prelim/{args.style}.{sym}.html"}
    json.dump(state, open(state_path, "w"))
    first_t = load(args.symbols.split(",")[0], args.tf)[-args.n:][0]["time"]
    meta = {"tf": args.tf, "n": args.n, "window_first": first_t,
            "window_last": max(load(sym, args.tf)[-1]["time"] for sym in args.symbols.split(",")),
            "symbols": {sym: {"last": result[sym]["last"], "pct": result[sym]["pct"], "stance": result[sym]["stance"]} for sym in args.symbols.split(",")}}
    json.dump(meta, open(f"{out_dir}/{args.style}.meta.json", "w"), ensure_ascii=False)
    result["_new_events"] = new_events
    result["_scanned_at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    sys.exit(3 if new_events else 0)


if __name__ == "__main__":
    main()
