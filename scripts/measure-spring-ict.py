#!/usr/bin/env python3
"""Measure, on stored candles, how often an ICT entry (MSS by body close + bullish FVG) follows a Spring candidate, and
what the "early" (Wyckoff, at the Spring) vs "late" (ICT, at the MSS) vs "partial early + add" entries would have done.

Usage: measure-spring-ict.py [--tf 15m,4H,1D] [--symbols BTCUSDT,ETHUSDT,SOLUSDT,XAUUSD] [--out docs/backtests/<file>.md] [--json PATH]
Data: data/history/ohlcv.<SYM>.<TF>.json (scripts/fetch-history.py) or, if absent, the live/bridge file.

Definitions — the book's where it has one, otherwise a PROJECT PARAMETER (named, so /improve can tune it):
  * Range support (proxy for SC/ST low)  = min low of the previous R bars, excluding the last 6 (support must have held a while)
      R: 15m 48 · 4H 30 · 1D 20 — PROJECT PARAMETER. The book draws the TR from AR high / SC-ST low (WA p71–72); without a
      full Wyckoff read per bar we use the rolling range low as the support line.
  * Spring candidate at bar i            = low pierces support and price closes back above it within 0–2 bars
      (Spring: same bar; Shakeout: close back inside within 2 bars — WA p80, p83, knowledge/wyckoff/advance.md §2.7.3). Cluster guard: 5 bars.
  * Spring volume type                   = ratio to the mean volume of the previous 20 bars: <0.7 type 1, 0.7–1.5 type 2, >1.5 type 3
      (thresholds: analysis-params.json project_defined.volume; typing: knowledge/wyckoff/modern-tools.md §2.6).
  * ICT confirmation within K bars       = first close above the last 3-bar pivot high before the Spring (MSS, knowledge/ict/core-a.md §2.17)
      AND a bullish FVG (candle1.high < candle3.low, knowledge/ict/core-a.md §2.21) in the leg from the Spring to the MSS+2.
      K: 15m 16 · 4H 8 · 1D 6 — PROJECT PARAMETER (≈ 4 h / 32 h / 6 days).
  * Stop                                 = Spring low − 0.05% of price (below the Spring low: knowledge/wyckoff/modern-tools.md §5 Step 4; buffer = pilot's).
  * Target                               = range high = max high of the previous R bars (Phase D "giá sẽ di chuyển ít nhất đến biên trên TR", WA p83–84).
  * Early entry (Wyckoff)                = close of the reclaim bar.   Late entry (ICT) = close of the MSS bar (only when confirmed).
  * Outcome                              = walk forward H bars (15m 96 · 4H 30 · 1D 20 — PROJECT PARAMETER): stop hit → −1R; target hit → +R_planned;
      both in one bar → loss (conservative); neither → mark-to-market R at bar H ("timeout").
  * Partial                              = 0.5 risk early; if confirmed, add 0.5 risk at the MSS close (same stop/target); else early half only.
Everything here is computed from the candle files; nothing is judged by a model.
"""
import argparse, datetime, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import instruments as I  # noqa: E402
# Feed directory comes from instruments.py (I.data_dir), keyed by market -- was a hard-coded symbol set.
P = {"15m": dict(R=48, K=16, H=96), "4H": dict(R=30, K=8, H=30), "1D": dict(R=20, K=6, H=20), "1H": dict(R=48, K=12, H=72), "5m": dict(R=60, K=18, H=120)}
VOL = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"]["volume"]
STOP_BUFFER_PCT = 0.0005


def load(sym, tf):
    for base in ("history", f"live/{I.data_dir(sym)}"):
        p = f"{ROOT}/data/{base}/ohlcv.{sym}.{tf}.json"
        if os.path.exists(p):
            return json.load(open(p))["candles"], os.path.relpath(p, ROOT)
    return None, None


def pivots_high(H, upto):
    return [i for i in range(3, upto - 3) if all(H[j] <= H[i] for j in range(i - 3, i + 4) if j != i)]


def walk(entry, stop, target, H_, L_, C_, start, horizon):
    """Outcome of one entry: ('win'|'loss'|'timeout', realized R)."""
    r = entry - stop
    if r <= 0:
        return None
    for j in range(start, min(len(C_), start + horizon)):
        hit_stop, hit_tgt = L_[j] <= stop, H_[j] >= target
        if hit_stop:
            return "loss", -1.0
        if hit_tgt:
            return "win", (target - entry) / r
    j = min(len(C_) - 1, start + horizon - 1)
    return "timeout", (C_[j] - entry) / r


def measure(sym, tf):
    c, src = load(sym, tf)
    if not c:
        return None
    p = P[tf]; R, K, HZ = p["R"], p["K"], p["H"]
    O = [x["open"] for x in c]; H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]; V = [x.get("volume", 0) for x in c]; T = [x["time"] for x in c]
    n = len(c); events = []; last_i = -99
    for i in range(R + 6, n - 3):
        support = min(L[i - R:i - 5]); resistance = max(H[i - R:i])
        if not (L[i] < support and i - last_i > 5):
            continue
        # reclaim within 0–2 bars
        rec = next((j for j in range(i, min(i + 3, n)) if C[j] > support), None)
        if rec is None:
            continue
        # the low of the excursion (Spring low)
        spring_low = min(L[i:rec + 1])
        if resistance <= support:
            continue
        avg20 = sum(V[i - 20:i]) / 20 if i >= 20 else 0
        ratio = V[i] / avg20 if avg20 else None
        vtype = None if ratio is None else (1 if ratio < VOL["low_max_ratio"] else (3 if ratio > VOL["high_min_ratio"] else 2))
        last_i = i
        # ICT confirmation: MSS = close above last pivot high before i; FVG bull in the leg
        ph = pivots_high(H, i)
        swing_hi = H[ph[-1]] if ph else None
        mss = fvg = None
        if swing_hi is not None:
            for j in range(rec + 1, min(rec + 1 + K, n)):
                if C[j] > swing_hi:
                    mss = j; break
            if mss is not None:
                for k in range(i + 1, min(mss + 2, n - 1)):
                    if H[k - 1] < L[k + 1]:
                        fvg = k; break
        confirmed = mss is not None and fvg is not None
        entry_e = C[rec]; stop = spring_low - STOP_BUFFER_PCT * entry_e; target = resistance
        early = walk(entry_e, stop, target, H, L, C, rec + 1, HZ)
        late = walk(C[mss], stop, target, H, L, C, mss + 1, HZ) if confirmed else None
        if early is None or (confirmed and late is None):
            continue
        ev = dict(time=T[i], reclaim_time=T[rec], support=support, resistance=resistance, spring_low=spring_low, vol_ratio=round(ratio, 2) if ratio else None, vol_type=vtype,
                  swing_high=swing_hi, mss_time=T[mss] if mss is not None else None, bars_to_mss=(mss - rec) if mss is not None else None, fvg=fvg is not None, confirmed=confirmed,
                  early=dict(entry=entry_e, stop=round(stop, 4), target=target, R_planned=round((target - entry_e) / (entry_e - stop), 2), outcome=early[0], R=round(early[1], 2)),
                  late=(dict(entry=C[mss], R_planned=round((target - C[mss]) / (C[mss] - stop), 2), outcome=late[0], R=round(late[1], 2)) if confirmed else None))
        ev["partial_R"] = round(0.5 * early[1] + (0.5 * late[1] if confirmed else 0.0), 2)
        events.append(ev)
    return dict(symbol=sym, tf=tf, source=src, bars=n, first=T[0], last=T[-1], params=p, events=events)


def stats(rs):
    if not rs:
        return dict(n=0)
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) < 0 else None
    return dict(n=len(rs), win_rate=round(len(wins) / len(rs), 2), avg_R=round(sum(rs) / len(rs), 2), sum_R=round(sum(rs), 1), profit_factor=(round(pf, 2) if pf else None))


def summarize(m):
    ev = m["events"]; conf = [e for e in ev if e["confirmed"]]; unconf = [e for e in ev if not e["confirmed"]]
    out = dict(symbol=m["symbol"], tf=m["tf"], bars=m["bars"], span=f"{m['first'][:10]}..{m['last'][:10]}", springs=len(ev), confirmed=len(conf),
               confirm_rate=(round(len(conf) / len(ev), 2) if ev else None), median_bars_to_mss=(statistics.median([e["bars_to_mss"] for e in conf]) if conf else None),
               early_all=stats([e["early"]["R"] for e in ev]), early_confirmed=stats([e["early"]["R"] for e in conf]), early_unconfirmed=stats([e["early"]["R"] for e in unconf]),
               late=stats([e["late"]["R"] for e in conf]), partial=stats([e["partial_R"] for e in ev]),
               by_vol_type={t: dict(n=len([e for e in ev if e["vol_type"] == t]), confirmed=len([e for e in ev if e["vol_type"] == t and e["confirmed"]]),
                                    early=stats([e["early"]["R"] for e in ev if e["vol_type"] == t])) for t in (1, 2, 3)})
    return out


def fmt_stats(s):
    return "—" if not s or not s.get("n") else f"n={s['n']} · thắng {s['win_rate'] * 100:.0f}% · R TB {s['avg_R']:+.2f} · ΣR {s['sum_R']:+.1f} · PF {s['profit_factor'] if s['profit_factor'] else '—'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,XAUUSD")
    ap.add_argument("--out"); ap.add_argument("--json")
    a = ap.parse_args()
    results, rows = [], []
    for tf in a.tf.split(","):
        for sym in a.symbols.split(","):
            m = measure(sym, tf)
            if not m:
                continue
            results.append(m); rows.append(summarize(m))
    today = datetime.date.today().isoformat()
    lines = [f"# Spring → ICT confirmation & early/late entry outcomes — measured {today}", "",
             "_Generated by `scripts/measure-spring-ict.py` from stored candles; every number is computed, none is judged. Definitions and the PROJECT PARAMETERS (R, K, H, thresholds) are in the script docstring. Read the caveats at the end before acting on this._", "",
             "| Mã | Khung | Nến | Khoảng | Spring ứng viên | ICT xác nhận (MSS+FVG) | Tỉ lệ | Trung vị nến tới MSS | Vào sớm (tất cả) | Vào sớm — có xác nhận | Vào sớm — không xác nhận | Vào sau (ICT) | Một phần (½ sớm + ½ sau) |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['symbol']} | {r['tf']} | {r['bars']} | {r['span']} | {r['springs']} | {r['confirmed']} | {(r['confirm_rate'] * 100 if r['confirm_rate'] is not None else 0):.0f}% | {r['median_bars_to_mss'] if r['median_bars_to_mss'] is not None else '—'} | {fmt_stats(r['early_all'])} | {fmt_stats(r['early_confirmed'])} | {fmt_stats(r['early_unconfirmed'])} | {fmt_stats(r['late'])} | {fmt_stats(r['partial'])} |")
    # totals per tf
    lines += ["", "## Gộp theo khung", "", "| Khung | Spring | Xác nhận | Tỉ lệ | Vào sớm (tất cả) | Vào sớm — có xác nhận | Vào sớm — không xác nhận | Vào sau (ICT) | Một phần |", "|---|---|---|---|---|---|---|---|---|"]
    for tf in a.tf.split(","):
        ev = [e for m in results if m["tf"] == tf for e in m["events"]]
        if not ev:
            continue
        conf = [e for e in ev if e["confirmed"]]; unconf = [e for e in ev if not e["confirmed"]]
        lines.append(f"| {tf} | {len(ev)} | {len(conf)} | {len(conf) / len(ev) * 100:.0f}% | {fmt_stats(stats([e['early']['R'] for e in ev]))} | {fmt_stats(stats([e['early']['R'] for e in conf]))} | {fmt_stats(stats([e['early']['R'] for e in unconf]))} | {fmt_stats(stats([e['late']['R'] for e in conf]))} | {fmt_stats(stats([e['partial_R'] for e in ev]))} |")
    lines += ["", "## Theo loại khối lượng của Spring (knowledge/wyckoff/modern-tools.md §2.6: loại 1 thấp < 0.7×, loại 2 trung bình, loại 3 cao > 1.5×)", "", "| Khung | Loại | Spring | Xác nhận | Vào sớm |", "|---|---|---|---|---|"]
    for tf in a.tf.split(","):
        for t in (1, 2, 3):
            ev = [e for m in results if m["tf"] == tf for e in m["events"] if e["vol_type"] == t]
            if ev:
                lines.append(f"| {tf} | {t} | {len(ev)} | {len([e for e in ev if e['confirmed']])} | {fmt_stats(stats([e['early']['R'] for e in ev]))} |")
    lines += ["", "## Caveats (đọc trước khi dùng)", "",
              "- Spring ứng viên ở đây là *proxy bằng code* (đáy xuyên hỗ trợ rolling rồi đóng lại), không phải Spring đã qua cổng CHoCH và đối nhãn của một phân tích đầy đủ. Số Spring thật sẽ ít hơn và tỉ lệ có thể khác.",
              "- Mục tiêu = biên trên vùng (WA p83–84) và stop dưới đáy Spring (knowledge/wyckoff/modern-tools.md §5 bước 4) là theo sách; R, K, H và ngưỡng khối lượng là tham số dự án.",
              "- Không tính phí/spread/trượt giá; nến có cả stop lẫn target tính là thua. XAUUSD chỉ có 300 nến từ MT5 và khối lượng là tick.",
              "- Mẫu nhỏ ở 4H/1D. Dùng để so sánh *tương đối* (sớm vs sau vs một phần, có xác nhận vs không), không phải kỳ vọng tuyệt đối.",
              "", f"_Nguồn: {', '.join(sorted(set(m['source'] for m in results)))}_"]
    md = "\n".join(lines) + "\n"
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True); open(a.out, "w", encoding="utf-8").write(md); print(f"-> {a.out}")
    if a.json:
        json.dump(dict(generated=today, results=results, summary=rows), open(a.json, "w"), ensure_ascii=False, indent=1); print(f"-> {a.json}")


if __name__ == "__main__":
    main()
