#!/usr/bin/env python3
"""Which definition of the "Asian session" makes its high/low behave most like liquidity? Measured, not argued.
Usage: asia-session-eval.py [--symbols BTCUSDT,ETHUSDT,SOLUSDT,XAUUSD] [--tf 15m] [--days 365] [--out docs/backtests/<file>.md]
The ICT decks draw "Asian Session High/Low" as levels the later sessions sweep or reverse from (knowledge/ict/core-a.md §2.9) but never
define the session's clock (knowledge/ict/core-a.md §6 item 9). Candidates (exchange-local clocks, converted per date, weekdays only):
  tokyo_00_06   00:00–06:00 Asia/Tokyo   (docs/architecture/session-model.md, current)
  ny_20_00      20:00–00:00 America/New_York (the decks' "Asia" killzone, 1. Killzones p3)
  utc_00_08     00:00–08:00 UTC           (exchange-day open to London pre-open)
  tokyo_09_15   09:00–15:00 Asia/Tokyo    (Tokyo cash equity hours)
  sg_08_16      08:00–16:00 Asia/Singapore
Per session instance: range = high/low of the bars inside the window; the "rest of day" = bars until the next instance starts.
Metrics: swept = at least one side taken by a wick; one_side = exactly one side taken (the deck's reversal frame);
reverse|swept = after the first side is taken, price closes back inside the range and later touches the opposite side
(liquidity behaviour) rather than continuing; range share = session range / whole-day range (a narrow, quiet range is what
the concept assumes). Score = mean(one_side, reverse|swept) − 0.5 × range share. Highest score wins; ties → the current setting.
"""
import argparse, datetime, json, os, statistics, zoneinfo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDS = {"tokyo_00_06": ("Asia/Tokyo", 0, 6), "ny_20_00": ("America/New_York", 20, 24), "utc_00_08": ("UTC", 0, 8), "tokyo_09_15": ("Asia/Tokyo", 9, 15), "sg_08_16": ("Asia/Singapore", 8, 16)}


def load(sym, tf):
    p = f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"
    return json.load(open(p))["candles"] if os.path.exists(p) else None


def spans(c, tz, a, b):
    z = zoneinfo.ZoneInfo(tz); out = []; start = None
    for i, x in enumerate(c):
        t = datetime.datetime.fromisoformat(x["time"].replace("Z", "+00:00"))
        if t.weekday() >= 5:
            inz = False
        else:
            lt = t.astimezone(z); h = lt.hour + lt.minute / 60; inz = a <= h < b
        if inz and start is None:
            start = i
        if not inz and start is not None:
            out.append((start, i - 1)); start = None
    return out


def evaluate(c, tz, a, b):
    sp = spans(c, tz, a, b); H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]
    res = dict(n=0, swept=0, one_side=0, both=0, rev=0, share=[])
    for k, (s0, s1) in enumerate(sp):
        e = sp[k + 1][0] if k + 1 < len(sp) else len(c)
        if e - s1 < 8:
            continue
        h = max(H[s0:s1 + 1]); l = min(L[s0:s1 + 1]); rng = h - l
        if rng <= 0:
            continue
        res["n"] += 1
        after = range(s1 + 1, e)
        fh = next((i for i in after if H[i] > h), None); fl = next((i for i in after if L[i] < l), None)
        dayH = max(H[s0:e]); dayL = min(L[s0:e]); res["share"].append(rng / (dayH - dayL) if dayH > dayL else 1.0)
        if fh is None and fl is None:
            continue
        res["swept"] += 1
        if (fh is None) != (fl is None):
            res["one_side"] += 1
        else:
            res["both"] += 1
        first, side = (fh, "H") if (fl is None or (fh is not None and fh <= fl)) else (fl, "L")
        back = next((i for i in range(first, e) if (l <= C[i] <= h)), None)
        if back is not None:
            opp = next((i for i in range(back, e) if (L[i] <= l if side == "H" else H[i] >= h)), None)
            if opp is not None:
                res["rev"] += 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,XAUUSD"); ap.add_argument("--tf", default="15m"); ap.add_argument("--days", type=int, default=365); ap.add_argument("--out", default=None)
    a = ap.parse_args(); today = datetime.date.today().isoformat()
    L = [f"# Ranh giới phiên Á — đo hành vi thanh khoản của đỉnh/đáy phiên — {today}", "",
         f"_`scripts/asia-session-eval.py` trên nến {a.tf} tại `data/history/`, {a.days} ngày cuối, chỉ ngày thường. Định nghĩa các chỉ số ở docstring của script. Điểm = trung bình(một phía, đảo chiều|quét) − 0.5 × tỉ lệ range phiên / range cả ngày._", ""]
    totals = {k: dict(n=0, swept=0, one_side=0, both=0, rev=0, share=[]) for k in CANDS}
    for sym in a.symbols.split(","):
        c = load(sym, a.tf)
        if not c:
            L.append(f"- {sym}: không có dữ liệu {a.tf}"); continue
        last = datetime.datetime.fromisoformat(c[-1]["time"].replace("Z", "+00:00")); start = (last - datetime.timedelta(days=a.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        c = [x for x in c if x["time"] >= start]
        L += [f"## {sym} — {c[0]['time'][:10]} → {c[-1]['time'][:10]} ({len(c)} nến)", "", "| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \\| quét | Range phiên / ngày (trung vị) | Điểm |", "|---|---|---|---|---|---|---|---|"]
        for k, (tz, x, y) in CANDS.items():
            r = evaluate(c, tz, x, y)
            for f in ("n", "swept", "one_side", "both", "rev"): totals[k][f] += r[f]
            totals[k]["share"] += r["share"]
            if not r["n"]:
                continue
            sw = r["swept"] / r["n"]; one = r["one_side"] / r["n"]; rv = r["rev"] / r["swept"] if r["swept"] else 0; sh = statistics.median(r["share"])
            L.append(f"| {k} ({tz} {x:02d}:00–{y%24:02d}:00) | {r['n']} | {sw*100:.0f}% | {one*100:.0f}% | {r['both']/r['n']*100:.0f}% | {rv*100:.0f}% | {sh*100:.0f}% | {(one+rv)/2 - 0.5*sh:.3f} |")
        L.append("")
    L += ["## Gộp mọi mã", "", "| Cửa sổ | Phiên | Bị quét | Một phía | Cả hai | Đảo chiều \\| quét | Range phiên / ngày | Điểm |", "|---|---|---|---|---|---|---|---|"]
    scored = []
    for k, r in totals.items():
        if not r["n"]:
            continue
        sw = r["swept"] / r["n"]; one = r["one_side"] / r["n"]; rv = r["rev"] / r["swept"] if r["swept"] else 0; sh = statistics.median(r["share"]); sc = (one + rv) / 2 - 0.5 * sh
        scored.append((sc, k)); L.append(f"| {k} | {r['n']} | {sw*100:.0f}% | {one*100:.0f}% | {r['both']/r['n']*100:.0f}% | {rv*100:.0f}% | {sh*100:.0f}% | {sc:.3f} |")
    scored.sort(reverse=True)
    L += ["", f"**Cửa sổ điểm cao nhất:** `{scored[0][1]}` ({scored[0][0]:.3f}); hiện tại `tokyo_00_06` = {dict((k, s) for s, k in scored).get('tokyo_00_06', 0):.3f}.", ""]
    out = a.out or f"{ROOT}/docs/backtests/{today}-asia-session.md"
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n"); print("\n".join(L[-12:])); print("->", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
