#!/usr/bin/env python3
"""Deterministic Wyckoff/ICT event scanner + preliminary read + FACTS (no LLM).

Mirrors the artifacts' client-side ictAnalyze() so the preliminary read matches what the chart draws:
3-bar pivots, equal highs/lows (BSL/SSL) + external range liquidity (ERL), sweeps (wick through a
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
12. Fair_Value_Gaps, 18. Market_Structure_Shift, IRL-ERL), WMT/knowledge/08 (Effort-vs-Result, Spring, SOS/SOW);
thresholds (0.08% equal-level tolerance, 3-bar pivot, 1.5x volume) are this system's own parameters, and say so.
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
    "evr": "WMT p019–022, p149–154 · knowledge/08 §2.3, §4.1",
    "spring": "WMT p036–049 · knowledge/08 §2.6",
    "sos": "knowledge/08 §6",
    "sys": "[tính toán của hệ thống — không phải trích dẫn tài liệu]",
}

SHORT = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "SOLUSDT": "SOL", "XAUUSD": "XAU", "XAGUSD": "XAG", "USOIL": "OIL", "UKOIL": "BRENT"}


MT5_SYMBOLS = {"XAUUSD", "XAGUSD", "USOIL", "UKOIL"}


def load(sym, tf):
    """Crypto from the Binance connector (data/live/market-data); commodities from the MT5 file bridge
    (data/live/mt5-bridge, written by integrations/mt5/ExportOHLCV.mq5). Same candle shape either way."""
    base = "mt5-bridge" if sym in MT5_SYMBOLS else "market-data"
    with open(f"{ROOT}/data/live/{base}/ohlcv.{sym}.{tf}.json") as f:
        return json.load(f)["candles"]


def load_anchors(style):
    try:
        return json.load(open(f"{ROOT}/data/live/anchors.{style}.json", encoding="utf-8"))
    except Exception:
        return None


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
                mss.append({"type": "bull", "i": j, "level": H[lastH], "vol_mult": round(V[j] / avgv, 2) if avgv else None}); bias = 0; break
            if bias == 1 and lastL is not None and C[j] < L[lastL]:
                mss.append({"type": "bear", "i": j, "level": L[lastL], "vol_mult": round(V[j] / avgv, 2) if avgv else None}); bias = 0; break

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
        "last": last, "lo": lo, "hi": hi, "eq": eq, "pct": pct, "last_time": T[-1], "avgv": avgv,
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
        d = {"name": a["name"], "label": a.get("label", a["name"]), "role": role, "price": price, "time": t0,
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
    base = {"side": side, "sweep": {"pool": s["kind"], "level": s["level"], "time": T[s["swept"]]},
            "mss": {"level": m["level"], "time": T[m["i"]], "vol_mult": m.get("vol_mult")},
            "in_discount": a["pct"] < 0.5}
    fv = [f for f in a["fvgs_all"] if f["i"] > s["swept"] and f["type"] == ("bull" if side == "long" else "bear")]
    if not fv:
        base.update({"complete": False, "missing": "FVG cùng chiều sau cú quét"}); return base
    f = fv[-1]
    if side == "long":
        entry = f["hi"]; stop = min(L[s["swept"]:m["i"] + 1])
        tg = [p["level"] for p in a["unswept"] if p["kind"] == "BSL" and p["level"] > entry]
        target, tk = (min(tg), "BSL chưa quét") if tg else (a["hi"], "đỉnh cửa sổ (ERL)")
        risk, reward = entry - stop, target - entry
    else:
        entry = f["lo"]; stop = max(H[s["swept"]:m["i"] + 1])
        tg = [p["level"] for p in a["unswept"] if p["kind"] == "SSL" and p["level"] < entry]
        target, tk = (max(tg), "SSL chưa quét") if tg else (a["lo"], "đáy cửa sổ (ERL)")
        risk, reward = stop - entry, entry - target
    base.update({"complete": True, "fvg": {"lo": f["lo"], "hi": f["hi"], "time": T[f["i"]], "mitigated": f["mitigated"]},
                 "entry": entry, "stop": stop, "target": target, "target_kind": tk,
                 "R": round(reward / risk, 2) if risk > 0 else None})
    return base


def fmt(sym, v):
    return f"{v:,.0f}" if sym.startswith("BTC") else f"{v:,.2f}"


def sessions_note(sym):
    return " (killzone London/NY có ý nghĩa với vàng; phiên Á thường mỏng)" if sym in MT5_SYMBOLS else ""


def facts_table(sym, a, an, su):
    f = lambda v: fmt(sym, v)
    rows = [("Giá / vị trí", f"{f(a['last'])} · {a['pct']*100:.0f}% biên độ ({f(a['lo'])}–{f(a['hi'])}) · EQ {f(a['eq'])}")]
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
            rows.append(("Setup ứng viên", f"{su['side'].upper()} · quét {su['sweep']['pool']} {f(su['sweep']['level'])} ({su['sweep']['time'][11:16]}Z) → MSS {f(su['mss']['level'])} ({su['mss']['time'][11:16]}Z, vol {su['mss']['vol_mult']}×) → FVG {f(su['fvg']['lo'])}–{f(su['fvg']['hi'])}{' (đã lấp)' if su['fvg']['mitigated'] else ''}"))
            rows.append(("Entry / Stop / Target / R", f"{f(su['entry'])} / {f(su['stop'])} / {f(su['target'])} ({su['target_kind']}) / R = {su['R']}"))
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
        lines.append(f"MSS gần nhất: {'tăng' if m['type']=='bull' else 'giảm'} (đóng cửa vượt swing {f(m['level'])}, vol {m.get('vol_mult')}×). "
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
            stance = "SETUP TIỀM NĂNG"; why = "quét thanh khoản rồi MSS cùng chiều — mô hình sweep→MSS; cần nhận định cục bộ (Sonnet) và kiểm tra Wyckoff/volume trước khi vào lệnh"
    ts = a["last_time"][11:16]
    html = (f"<div class=\"prelim-head\">Nhận định sơ bộ tự động · {tf} · dữ liệu tới {ts} UTC · "
            f"<strong>{stance}</strong></div>"
            + facts_table(sym, a, an, su)
            + "<!--MODEL-->"
            + "<div class=\"prelim-scan\">"
            + "".join(f"<p>{l}</p>" for l in lines)
            + f"<p><em>Vì sao {stance.lower()}:</em> {why}. Đây là quét theo luật cố định (pivot 3 nến, dung sai đỉnh/đáy bằng nhau 0,08%, FVG ≥0,6× biên độ nến trung vị — {CITE['sys']}), "
              f"không phải nhận định của mô hình; bản đọc đầy đủ ở bảng bên dưới có thể cũ hơn dữ liệu này.</p>"
            + "</div>")
    return html, stance


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", required=True); ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--style", required=True); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--recent", type=int, default=4, help="bars counted as 'recent' for events")
    ap.add_argument("--state", default=None)
    ap.add_argument("--setup-lookback", type=int, default=None, help="bars in which the setup's sweep must sit (default max(12, 6*recent))")
    args = ap.parse_args()
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
        a = analyze(c, args.recent)
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
        facts[sym] = {"last": a["last"], "last_time": a["last_time"], "lo": a["lo"], "hi": a["hi"], "eq": a["eq"], "pct": round(a["pct"], 4),
                      "stance": stance, "anchors": an, "setup": su, "last_mss": a["last_mss"], "nearest_fvg": a["nearest_fvg"],
                      "unswept_pools": a["unswept"], "events_recent": a["events"]}
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
