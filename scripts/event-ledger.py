#!/usr/bin/env python3
"""Forward measurement of the Wyckoff events called by the FULL analysis (the model's read, not a code proxy).

The daily full analysis writes data/live/narrative/<style>.json with, per symbol, wyckoff.events (time, label) and the trading
range it drew. There is no history of those reads, so they cannot be backtested; this ledger records every event the first time it
appears and measures the outcome afterwards from stored candles. That is the only honest way to answer "how do the Springs of
a full Wyckoff read perform" (user decision 2026-09-11, option 3).

  event-ledger.py append [--style S ...]     read data/live/narrative/*.json, append unseen events to data/live/events/wyckoff-events.jsonl
                                             (key: style, symbol, event time, event token). Single writer of that file.
  event-ledger.py measure [--out FILE.md]    for Spring/Shakeout (long) and UT/UTAD (short) events: entry = first close back inside the
                                             TR within 3 bars after the event bar, stop = event-bar extreme -/+ 0.05 %, target = the
                                             opposite TR border the analysis drew (WMT p273, WA p83–84), breakeven at +1R, horizon H bars
                                             (backtest-methods P[tf]); ICT confirmation = MSS + FVG within K bars (backtest-methods.find_ict).
                                             Outcomes: win / loss / breakeven / timeout / pending (not enough bars yet) / no_entry.
Labels are parsed, never interpreted: the token is the first word of the label (WA vocabulary), the price the first number in it
(VN or EN number format).
"""
import argparse, datetime, glob, importlib.util, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I  # noqa: E402
import htf_context as htf
_spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(bt)
LEDGER = os.path.join(ROOT, "data", "live", "events", "wyckoff-events.jsonl")
LONG_TOKENS = ("SPRING", "SHAKEOUT"); SHORT_TOKENS = ("UT", "UTAD")
# Feed directory comes from instruments.py (I.data_dir), keyed by market -- was a hard-coded symbol set.
TF_SEC = {"5m": 300, "15m": 900, "30m": 1800, "1H": 3600, "2H": 7200, "4H": 14400, "1D": 86400}


def parse_price(label):
    m = re.search(r"\d[\d.,]*\d|\d", label)
    if not m:
        return None
    s = m.group(0)
    if "." in s and "," in s:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        s = s.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", "") if all(len(p) == 3 for p in parts[1:]) else s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        s = s.replace(".", "") if len(parts) > 2 or (len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3) else s
    try:
        return float(s)
    except ValueError:
        return None


def token_of(label):
    m = re.match(r"\s*([A-Za-z]+)", label)
    return m.group(1).upper() if m else None


def load_ledger():
    if not os.path.exists(LEDGER):
        return []
    return [json.loads(l) for l in open(LEDGER, encoding="utf-8") if l.strip()]


def cmd_append(styles):
    seen = {(r["style"], r["symbol"], r["time"], r["token"]) for r in load_ledger()}
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True); added = 0
    for p in sorted(glob.glob(os.path.join(ROOT, "data", "live", "narrative", "*.json"))):
        style = os.path.basename(p)[:-5]
        if styles and style not in styles:
            continue
        try:
            n = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        tf = {"1h": "1H", "4h": "4H"}.get(htf.STYLE_TF.get(style), htf.STYLE_TF.get(style))
        for sym, v in (n.get("symbols") or {}).items():
            w = v.get("wyckoff") or {}
            for e in w.get("events") or []:
                tok = token_of(e.get("label", ""))
                if not tok or (style, sym, e["time"], tok) in seen:
                    continue
                rec = dict(style=style, symbol=sym, tf=tf, time=e["time"], token=tok, label=e["label"], price=parse_price(e["label"]),
                           structure=w.get("structure"), phase=w.get("phase"), trading_range=w.get("trading_range"), verdict=v.get("verdict"),
                           narrative_updated=n.get("updated"), recorded=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
                with open(LEDGER, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                seen.add((style, sym, e["time"], tok)); added += 1
    print(f"event ledger: +{added} events -> {os.path.relpath(LEDGER, ROOT)} ({len(seen)} total)")


def candles_for(sym, tf):
    for base in ("history", f"live/{I.data_dir(sym)}"):
        p = f"{ROOT}/data/{base}/ohlcv.{sym}.{tf}.json"
        if os.path.exists(p):
            c = json.load(open(p))["candles"]
            if c and c[0]["time"] <= "2026-09-01":
                return c, base
    return None, None


def measure_one(r):
    tf = r.get("tf"); tr = r.get("trading_range") or {}
    if not tf or tf not in bt.P or r["token"] not in LONG_TOKENS + SHORT_TOKENS or not tr.get("high") or not tr.get("low"):
        return dict(r, outcome="no_entry", why="no timeframe / not a reversal event / no trading range")
    c, src = candles_for(r["symbol"], tf)
    if not c:
        return dict(r, outcome="pending", why="no candles on disk")
    T = [x["time"] for x in c]
    if r["time"] not in T:
        return dict(r, outcome="pending", why="event bar not in the candle file")
    i = T.index(r["time"]); H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
    side = "long" if r["token"] in LONG_TOKENS else "short"; lo, hi = float(tr["low"]), float(tr["high"])
    rec = next((j for j in range(i, min(i + 3, len(c))) if (C[j] > lo if side == "long" else C[j] < hi)), None)
    if rec is None:
        return dict(r, outcome="no_entry" if len(c) > i + 3 else "pending", why="no close back inside the TR within 3 bars")
    ext = min(L[i:rec + 1]) if side == "long" else max(H[i:rec + 1])
    stop = ext * (1 - bt.STOP_BUFFER_PCT) if side == "long" else ext * (1 + bt.STOP_BUFFER_PCT)
    target = hi if side == "long" else lo
    if (side == "long" and target <= C[rec]) or (side == "short" and target >= C[rec]):
        return dict(r, outcome="no_entry", why="target not beyond the entry")
    bt.OPTS["mgmt"] = "be"
    w = bt.walk(side, C[rec], stop, target, H, L, C, rec + 1, bt.P[tf]["H"])
    bars_avail = len(c) - 1 - rec
    if w and w["outcome"] == "timeout" and bars_avail < bt.P[tf]["H"]:
        w["outcome"] = "pending"
    PH = bt.all_pivots(H, "high"); PL = bt.all_pivots(L, "low")
    ict = bt.find_ict(side, i, rec, H, L, C, bt.P[tf]["K"], len(c), PH, PL)
    return dict(r, side=side, entry=C[rec], stop=round(stop, 4), target=target, outcome=w["outcome"] if w else "no_entry",
                R=round(w["R"], 2) if w else None, R_planned=round(w["R_planned"], 2) if w else None, bars_available=bars_avail,
                ict_confirmed=bool(ict), ict_mss_time=(T[ict[0]] if ict else None), source=src)


def cmd_measure(out):
    rows = [measure_one(r) for r in load_ledger()]
    rev = [r for r in rows if r["token"] in LONG_TOKENS + SHORT_TOKENS]
    done = [r for r in rev if r["outcome"] in ("win", "loss", "breakeven", "timeout")]
    L = [f"# Sổ sự kiện Wyckoff của phân tích đầy đủ — đo {datetime.date.today().isoformat()}", "",
         f"_`scripts/event-ledger.py measure`. Sự kiện được ghi lần đầu khi xuất hiện trong `data/live/narrative/*.json` (không nhìn trước), kết quả đo từ nến lưu. Entry = nến đóng lại trong TR sau sự kiện, stop dưới/trên cực trị sự kiện, target = biên đối diện TR mà phân tích vẽ, hoà vốn +1R, hạn H nến._", "",
         f"Tổng sự kiện ghi: {len(rows)} · sự kiện đảo chiều (Spring/Shakeout/UT/UTAD): {len(rev)} · đã có kết quả: {len(done)} · đang chờ: {len([r for r in rev if r['outcome'] == 'pending'])}", ""]
    if done:
        rs = [r["R"] for r in done]; wins = [r for r in rs if r > 0]
        L.append(f"**Kết quả**: thắng {len(wins)}/{len(done)} · R trung bình {sum(rs) / len(rs):+.2f} · ΣR {sum(rs):+.1f} · có xác nhận ICT: {sum(1 for r in done if r['ict_confirmed'])}/{len(done)}")
        conf = [r["R"] for r in done if r["ict_confirmed"]]; unc = [r["R"] for r in done if not r["ict_confirmed"]]
        if conf:
            L.append(f"- Có xác nhận ICT: n={len(conf)} · R TB {sum(conf) / len(conf):+.2f}")
        if unc:
            L.append(f"- Không xác nhận ICT: n={len(unc)} · R TB {sum(unc) / len(unc):+.2f}")
    L += ["", "| Style | Mã | Khung | Thời điểm | Sự kiện | Pha | Cấu trúc | Chiều | Entry | Stop | Target | R kế hoạch | ICT xác nhận | Kết quả | R |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rev:
        L.append(f"| {r['style']} | {r['symbol']} | {r.get('tf')} | {r['time']} | {r['label']} | {r.get('phase')} | {r.get('structure')} | {r.get('side', '—')} | {r.get('entry', '—')} | {r.get('stop', '—')} | {r.get('target', '—')} | {r.get('R_planned', '—')} | {'có' if r.get('ict_confirmed') else ('không' if r.get('side') else '—')} | {r['outcome']}{(' (' + r['why'] + ')') if r.get('why') else ''} | {r.get('R', '—')} |")
    md = "\n".join(L) + "\n"; print(md)
    if out:
        open(out, "w", encoding="utf-8").write(md); print(f"-> {out}")


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("append"); a1.add_argument("--style", action="append", default=[])
    a2 = sub.add_parser("measure"); a2.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "append":
        cmd_append(a.style)
    else:
        cmd_measure(a.out)


if __name__ == "__main__":
    main()
