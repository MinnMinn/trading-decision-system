#!/usr/bin/env python3
"""Rank entry methods by CONSISTENCY over time, not by total return.

Runs scripts/backtest-methods.py's engine over several timeframes and configurations, books every closed trade on a
compounding account at bt.RISK per trade (= the live per-trade ceiling), and reports per method: trades, annualised %, max drawdown, share of positive quarters,
worst quarter, median quarter, quarter mean/σ (a t-like stability ratio), share of positive years, per-year returns.

Usage: stability-report.py [--tf 15m,30m,1H,2H,4H,1D] [--symbols ...] [--out docs/backtests/<file>.md] [--json PATH]
Configurations (all long AND short):
  A  taker fee 0.05 %, no management, no HTF filter               (the raw rule)
  B  maker fee 0.02 % (limit entries), breakeven at +1R (WMT p272)  (book-style management)
  C  as B + higher-timeframe boundary filter (htf_context rule)     (giảm khung)
"""
import argparse, datetime, importlib.util, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
METHODS = ("WYCKOFF", "WYCKOFF-BOOK", "ICT", "COMBINED", "COMBINED-BOOK")
CONFIGS = {"A": dict(fee=0.0005, mgmt="none", htf=False), "B": dict(fee=0.0002, mgmt="be", htf=False), "C": dict(fee=0.0002, mgmt="be", htf=True)}
MIN_TRADES = 30


def metrics(curve, first, last, taken, final, dd):
    q = [v for _, v in bt.period_returns(curve, first, last, bt.quarter_key)]
    y = bt.period_returns(curve, first, last, bt.year_key)
    days = (datetime.date.fromisoformat(last[:10]) - datetime.date.fromisoformat(first[:10])).days or 1
    sd = statistics.pstdev(q) if len(q) > 1 else 0.0
    return dict(n=len(taken), ann=((final / bt.START) ** (365 / days) - 1) * 100, dd=dd, final=final, ruin=bt.SIM_LAST["ruin"], q_pos=sum(1 for v in q if v > 0) / len(q) * 100 if q else 0, q_worst=min(q) if q else 0,
                q_med=statistics.median(q) if q else 0, q_mean=statistics.mean(q) if q else 0, q_sd=sd, stab=(statistics.mean(q) / sd * len(q) ** 0.5) if sd else 0,
                y_pos=sum(1 for _, v in y if v > 0), y_n=len(y), years=y, quarters=q)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,30m,1H,2H,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT"); ap.add_argument("--out"); ap.add_argument("--json"); ap.add_argument("--ict-target", default="range", choices=["range", "std2", "std25", "std4", "erl_next", "irl"])
    a = ap.parse_args(); today = datetime.date.today().isoformat(); rows = []
    for tf in a.tf.split(","):
        for cname, cfg in CONFIGS.items():
            bt.OPTS.update(mgmt=cfg["mgmt"], htf=cfg["htf"], sides=("long", "short"), types=(1, 2, 3), range_touches=0, entry="book", sloped_gate=False, st_min=None, phase_d=True, combined_entry="limit", ict_target=a.ict_target)
            scans = [s for s in (bt.scan(sym, tf) for sym in a.symbols.split(",")) if s]
            if not scans:
                continue
            first = min(s["first"] for s in scans); last = max(s["last"] for s in scans)
            since = (datetime.date.fromisoformat(last[:10]) - datetime.timedelta(days=365)).isoformat() + "T00:00:00Z"
            for m in METHODS:
                tr = [t for s in scans for t in s["trades"][m]]
                final, curve, taken = bt.simulate(tr, cfg["fee"])
                row = dict(tf=tf, cfg=cname, method=m, first=first[:10], last=last[:10], **metrics(curve, first, last, taken, final, bt.max_dd(curve)))
                # last-365-day window (user decision 2026-09-11: `/automation on setup top N` ranks on the most recent year)
                tr1 = [t for t in tr if t["entry_time"] >= since]
                f1, c1, tk1 = bt.simulate(tr1, cfg["fee"])
                w = metrics(c1, max(first, since), last, tk1, f1, bt.max_dd(c1)); w.pop("years", None); w.pop("quarters", None)
                row["w1y"] = dict(w, since=since[:10])
                rows.append(row)
            print(f"{tf} {cname} done", file=sys.stderr)
    ok = [r for r in rows if r["n"] >= MIN_TRADES]
    ok.sort(key=lambda r: (r["ruin"] is None, r["q_pos"], r["q_worst"], r["stab"]), reverse=True)
    L = [f"# Độ ổn định theo thời gian của các phương pháp — {today} — target ICT: {a.ict_target}", "",
         "_`scripts/stability-report.py`. Xếp hạng theo: tỉ lệ quý dương → quý tệ nhất → tỉ số ổn định (trung bình quý / σ quý × √số quý). Chỉ xếp hạng dòng có ≥ 30 lệnh; tài khoản $10.000, CHÁY khi vốn ≤ $1.000 (dừng, ghi ngày, xếp cuối). Cấu hình A = phí taker 0,05 %, không quản lý; B = phí maker 0,02 % + hoà vốn tại +1R (WMT p272); C = B + lọc khung lớn (luật biên). Cả long lẫn short. Mọi số là của proxy bằng code (xem docstring của `backtest-methods.py` và `wyckoff_rules.py`)._", "",
         "## Bảng xếp hạng (mọi khung, mọi cấu hình)", "",
         f"| # | Khung | Cấu hình | Phương pháp | Lệnh | Vốn cuối (từ ${bt.START:,.0f}) | %/năm | Sụt giảm tối đa | Quý dương | Quý tệ nhất | Quý trung vị | Ổn định | Năm dương | Giai đoạn |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(ok[:30], 1):
        fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
        L.append(f"| {i} | {r['tf']} | {r['cfg']} | {r['method']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | {r['q_worst']:+.1f}% | {r['q_med']:+.1f}% | {r['stab']:+.2f} | {r['y_pos']}/{r['y_n']} | {r['first']}→{r['last']} |")
    L += ["", "## Toàn bộ kết quả theo khung", ""]
    for tf in a.tf.split(","):
        sub = [r for r in rows if r["tf"] == tf]
        if not sub:
            continue
        yrs = sorted({y for r in sub for y, _ in r["years"]})
        L += [f"### {tf} ({sub[0]['first']} → {sub[0]['last']})", "", "| Cấu hình | Phương pháp | Lệnh | Vốn cuối | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | " + " | ".join(yrs) + " |", "|---|---|---|---|---|---|---|---|---|" + "---|" * len(yrs)]
        for r in sub:
            yv = dict(r["years"]); fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
            L.append(f"| {r['cfg']} | {r['method']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | {r['q_worst']:+.1f}% | {r['stab']:+.2f} | " + " | ".join(f"{yv.get(y, 0):+.1f}%" for y in yrs) + " |")
        L.append("")
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md); print(f"-> {a.out}", file=sys.stderr)
    if a.json:
        json.dump(dict(generated=today, rows=rows), open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
