#!/usr/bin/env python3
"""Pick the N most CONSISTENT setups per market from stability-report JSON files and write the pilot's selection file.

Usage: rank-setups.py --crypto data/history/stability/crypto-*.json --cfd data/history/stability/cfd-*.json
                      [--n 5] [--min-trades-crypto 100] [--min-trades-cfd 40] [--out docs/backtests/<file>.md] [--select docs/architecture/pilot-top5.json]

A "setup" = (market, timeframe, method, ICT target model, configuration A/B/C). Rows are ranked by: not blown up → share of
positive quarters → share of positive years → worst quarter → stability ratio (quarter mean / σ × √n). One row per
(timeframe, method) survives (the best target model and configuration), so the top N are N different rules, not one rule at
several targets or fee assumptions. All four rule families are eligible: ICT and COMBINED enter with a LIMIT at the FVG edge; WYCKOFF (proxy) and WYCKOFF-BOOK enter at
MARKET on the close of the entry bar (Spring reclaim / Test / BU), exactly as the backtest.

The selection file (single writer: this script) is read by scripts/strategy-runner.py and shown by `/automation pilot profile top5`.
CFD setups get execution "mt5" (demo account through integrations/mt5/OrderBridge.mq5 + scripts/mt5-order-bridge.py) and only timeframes the MT5 EA
exports or the runner can aggregate (1H, 2H, 4H, 1D). Every number here is a code proxy over research history — for CFD that is
Yahoo Finance futures data (scripts/fetch-history-cfd.py), not the CFD quotes the pilot will trade on.
"""
import argparse, datetime, glob, json, os
FLAG_KEYS = ("ict_disp", "ict_pd", "std_origin", "flags_decided")   # per-setup ICT switches decided by scripts/ict-flags-1y.py; carried over on rewrite


def carry_flags(selection, path):
    """Keep the deck-faithful switches of setups whose id already exists in the selection file (they are decided separately)."""
    try:
        prev = {st["id"]: st for st in json.load(open(path, encoding="utf-8")).get("setups", [])}
    except Exception:
        return selection
    for st in selection["setups"]:
        for k in FLAG_KEYS:
            if k in prev.get(st["id"], {}):
                st[k] = prev[st["id"]][k]
    return selection

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNNABLE = {"ICT", "COMBINED", "WYCKOFF", "WYCKOFF-BOOK"}   # all four are executed by scripts/strategy-runner.py (Wyckoff = market entries at the bar close)
CFD_TFS = {"5m", "15m", "30m", "1H", "2H", "4H", "1D"}
# user decision 2026-09-11 (evening): one setup per HORIZON per market -- scalping / day / swing -- even where the backtest edge is weak.
HORIZONS = {"scalping": {"5m", "15m"}, "day": {"30m", "1H", "2H"}, "swing": {"4H", "1D"}}
HORIZON_MIN_TRADES = {"scalping": 60, "day": 60, "swing": 12}
CFG_DESC = {"A": dict(fee=0.0005, mgmt="none", htf=False), "B": dict(fee=0.0002, mgmt="be", htf=False), "C": dict(fee=0.0002, mgmt="be", htf=True)}


def load_rows(paths, market):
    rows = []
    for p in paths:
        d = json.load(open(p, encoding="utf-8"))
        target = os.path.basename(p).rsplit("-", 1)[1].rsplit(".", 1)[0]    # crypto-std25.json / crypto-scalp-std25.json -> std25
        for r in d["rows"]:
            rows.append(dict(r, market=market, target=(target if r["method"] == "ICT" else "border"), file=os.path.relpath(p, ROOT)))
    return rows


def rank(rows, min_trades, window=None):
    """window=None: whole history (consistency first). window='1y': the row's last-365-day metrics -- not blown up, then share of
    positive quarters in that year, then the year's return, then its worst quarter (user decision 2026-09-11: 'hiệu quả nhất trong 1 năm')."""
    if window == "1y":
        ok = [r for r in rows if r.get("w1y") and r["w1y"]["n"] >= min_trades]
        ok.sort(key=lambda r: (r["w1y"]["ruin"] is None, r["w1y"]["q_pos"], r["w1y"]["ann"], r["w1y"]["q_worst"]), reverse=True)
    else:
        ok = [r for r in rows if r["n"] >= min_trades]
        ok.sort(key=lambda r: (r["ruin"] is None, r["q_pos"], r["y_pos"] / max(1, r["y_n"]), r["q_worst"], r["stab"]), reverse=True)
    best = {}
    for r in ok:
        key = (r["tf"], r["method"])          # one rule family per (timeframe, method): the best target model and configuration survive
        if key not in best:
            best[key] = r
    return list(best.values())


def fmt(r, window=None):
    fin = f"CHÁY {r['ruin'][:10]}" if r["ruin"] else f"${r['final']:,.0f}"
    yrs = " / ".join(f"{v:+.0f}" for _, v in r["years"])
    if window == "1y":
        w = r["w1y"]; f1 = f"CHÁY {w['ruin'][:10]}" if w["ruin"] else f"${w['final']:,.0f}"
        return (f"| {r['tf']} | {r['method']} | {r['target']} | {r['cfg']} | {w['n']} | {f1} | {w['ann']:+.1f}% | −{w['dd']:.1f}% | {w['q_pos']:.0f}% | {w['q_worst']:+.1f}% | "
                f"{r['n']} · {r['ann']:+.1f}%/năm · {r['q_pos']:.0f}% quý dương · {r['y_pos']}/{r['y_n']} năm |")
    return (f"| {r['tf']} | {r['method']} | {r['target']} | {r['cfg']} | {r['n']} | {fin} | {r['ann']:+.1f}% | −{r['dd']:.1f}% | {r['q_pos']:.0f}% | "
            f"{r['q_worst']:+.1f}% | {r['stab']:+.2f} | {r['y_pos']}/{r['y_n']} ({yrs}) |")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--crypto", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/crypto-*.json"))
    ap.add_argument("--cfd", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/cfd-*.json"))
    ap.add_argument("--n", type=int, default=5); ap.add_argument("--min-trades-crypto", type=int, default=100); ap.add_argument("--min-trades-cfd", type=int, default=40)  # --window 1y lowers these: see main()
    ap.add_argument("--out"); ap.add_argument("--select")
    ap.add_argument("--crypto-symbols", default="BTCUSDT,ETHUSDT,SOLUSDT"); ap.add_argument("--cfd-symbols", default="XAUUSD,XAGUSD,USOIL,UKOIL")
    ap.add_argument("--horizons", action="store_true", help="select the best rule per horizon (scalping/day/swing) per market instead of the top N overall")
    ap.add_argument("--window", choices=["all", "1y"], default="all", help="1y = rank on the last 365 days of each row (`/automation on setup top N`)")
    a = ap.parse_args(); today = datetime.date.today().isoformat()
    if a.horizons:
        if a.window == "1y":
            if a.min_trades_crypto == 100: a.min_trades_crypto = 30
            if a.min_trades_cfd == 40: a.min_trades_cfd = 15
        return main_horizons(a, today)
    if a.window == "1y":
        if a.min_trades_crypto == 100: a.min_trades_crypto = 30
        if a.min_trades_cfd == 40: a.min_trades_cfd = 15
        return main_window_1y(a, today)
    L = [f"# Top {a.n} setup mỗi thị trường — xếp theo độ ổn định — {today}", "",
         "_`scripts/rank-setups.py` trên các file `stability-report.py --json`. Tiêu chí: không cháy → tỉ lệ quý dương → tỉ lệ năm dương → quý tệ nhất → tỉ số ổn định. Mỗi (khung, luật) giữ một target và cấu hình tốt nhất, nên 5 dòng là 5 luật khác nhau. Cấu hình A = phí taker 0,05 %, không quản lý; B = phí maker 0,02 % + hoà vốn +1R; C = B + lọc khung lớn. Cả long lẫn short. Mọi số là proxy code trên lịch sử nghiên cứu._", ""]
    selection = dict(generated=today, note="Written by scripts/rank-setups.py. Read by scripts/strategy-runner.py (pilot profile top5) and shown by /automation pilot profile. CFD execution = MT5 demo account via the file order bridge; crypto = Binance futures testnet.", setups=[])
    for market, paths, mn, syms in (("crypto", a.crypto, a.min_trades_crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.min_trades_cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market)
        if not rows:
            L += [f"## {market.upper()}: chưa có dữ liệu xếp hạng", ""]; continue
        ranked = rank(rows, mn)
        eligible = [r for r in ranked if r["method"] in RUNNABLE and (market == "crypto" or r["tf"] in CFD_TFS)]
        top = eligible[:a.n]
        L += [f"## {market.upper()} — top {a.n} (≥ {mn} lệnh; {len(rows)} dòng xét, {len(ranked)} luật khác nhau)", "",
              "| Khung | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in top:
            L.append(fmt(r))
        skipped = [r for r in ranked[:a.n + 3] if r not in eligible]
        if skipped:
            L += ["", "Xếp cao nhưng không chạy được trong pilot (luật chưa có trong runner hoặc khung MT5 không xuất): " + ", ".join(f"{r['tf']} {r['method']} {r['target']} {r['cfg']}" for r in skipped)]
        L.append("")
        for i, r in enumerate(top, 1):
            cfg = CFG_DESC[r["cfg"]]
            selection["setups"].append(dict(id=f"{market}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", rank=i, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                            ict_target=r["target"] if r["method"] == "ICT" else None, htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=cfg["fee"],
                                            execution="futures" if market == "crypto" else "mt5",
                                            backtest=dict(n=r["n"], ann_pct=round(r["ann"], 1), max_dd_pct=round(r["dd"], 1), q_pos_pct=round(r["q_pos"]), years_pos=f"{r['y_pos']}/{r['y_n']}", period=f"{r['first']}→{r['last']}", source=r["file"])))
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = carry_flags(selection, a.select)
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


def main_window_1y(a, today):
    L = [f"# Top {a.n} setup mỗi thị trường — hiệu quả 12 tháng gần nhất — {today}", "",
         "_`scripts/rank-setups.py --window 1y` (được `/automation on setup top N` gọi). Xếp theo cửa sổ 365 ngày cuối của mỗi dòng: không cháy → tỉ lệ quý dương trong năm → lợi nhuận năm → quý tệ nhất; mỗi (khung, luật) giữ một target và cấu hình. Cột cuối là toàn bộ lịch sử để đối chiếu. Cả long lẫn short; số là proxy code trên lịch sử nghiên cứu (CFD = futures Yahoo)._", ""]
    selection = dict(generated=today, mode=f"top{a.n}-1y", note=f"Written by scripts/rank-setups.py --window 1y --n {a.n} (from `/automation on setup top {a.n}`). Read by scripts/strategy-runner.py. Crypto = Binance futures testnet, CFD = MT5 demo via the file order bridge.", setups=[])
    for market, paths, mn, syms in (("crypto", a.crypto, a.min_trades_crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.min_trades_cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market)
        ranked = [r for r in rank(rows, mn, "1y") if r["method"] in RUNNABLE and (market == "crypto" or r["tf"] in CFD_TFS)]
        top = ranked[:a.n]
        L += [f"## {market.upper()} — top {a.n} (≥ {mn} lệnh trong 12 tháng; {len(rows)} dòng xét)", "",
              "| Khung | Luật | Target | Cấu hình | Lệnh 1 năm | Vốn cuối 1 năm ($10k) | % 1 năm | Sụt giảm 1 năm | Quý dương | Quý tệ nhất | Toàn lịch sử |", "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in top:
            L.append(fmt(r, "1y"))
        if not top:
            L.append("| — | không đủ lệnh trong 12 tháng | | | | | | | | | |")
        L.append("")
        for i, r in enumerate(top, 1):
            cfg = CFG_DESC[r["cfg"]]; w = r["w1y"]
            selection["setups"].append(dict(id=f"{market}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", rank=i, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                            ict_target=r["target"] if r["method"] == "ICT" else None, htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=cfg["fee"],
                                            execution="futures" if market == "crypto" else "mt5", negative_backtest=bool(w["ann"] < 0),
                                            backtest=dict(window="1y", n=w["n"], ann_pct=round(w["ann"], 1), max_dd_pct=round(w["dd"], 1), q_pos_pct=round(w["q_pos"]), since=w["since"],
                                                          full_n=r["n"], full_ann_pct=round(r["ann"], 1), full_q_pos_pct=round(r["q_pos"]), years_pos=f"{r['y_pos']}/{r['y_n']}", source=r["file"])))
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = carry_flags(selection, a.select)
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


def main_horizons(a, today):
    L = [f"# Setup theo khung — scalping / day / swing — mỗi thị trường — {today}", "",
         "_`scripts/rank-setups.py --horizons`. Quyết định người dùng 2026-09-11: mỗi thị trường chạy đủ 3 khung, kể cả khi lợi thế backtest yếu hoặc âm. Trong mỗi khung, luật tốt nhất theo cùng tiêu chí (không cháy → quý dương → năm dương → quý tệ nhất). Dòng âm được in nghiêng; scalping 5m/15m bị phí và trượt giá ăn nhiều nhất._", ""]
    selection = dict(generated=today, mode="horizons", note="Written by scripts/rank-setups.py --horizons. One setup per horizon per market (user decision 2026-09-11). Crypto = Binance futures testnet, CFD = MT5 demo via the file order bridge.", setups=[])
    for market, paths, syms in (("crypto", a.crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market)
        L += [f"## {market.upper()}", "", "| Khung | TF | Luật | Target | Cấu hình | Lệnh | Vốn cuối ($10k) | %/năm | Sụt giảm | Quý dương | Quý tệ nhất | Ổn định | Năm dương (từng năm %) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for hz, tfs in HORIZONS.items():
            mn = HORIZON_MIN_TRADES[hz] if a.window != "1y" else {"scalping": 20, "day": 15, "swing": 6}[hz]
            ranked = [r for r in rank([r for r in rows if r["tf"] in tfs], mn, a.window if a.window == "1y" else None) if r["method"] in RUNNABLE and (market == "crypto" or r["tf"] in CFD_TFS)]
            if not ranked:
                L.append(f"| {hz} | — | — | — | — | — | không đủ dữ liệu / lệnh | | | | | | |"); continue
            r = ranked[0]; w = r["w1y"] if a.window == "1y" else r; row = fmt(r, a.window if a.window == "1y" else None).replace("| ", "| " + hz + " | ", 1)
            L.append(row if w["ann"] >= 0 else row.replace(f"| {hz} |", f"| *{hz}* |", 1))
            cfg = CFG_DESC[r["cfg"]]
            selection["setups"].append(dict(id=f"{market}-{hz}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}", horizon=hz, rank=len(selection["setups"]) + 1, market=market, symbols=syms, tf=r["tf"], method=r["method"],
                                            ict_target=r["target"] if r["method"] == "ICT" else None, htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=cfg["fee"],
                                            execution="futures" if market == "crypto" else "mt5", negative_backtest=bool(w["ann"] < 0),
                                            backtest=dict(window=a.window, n=w["n"], ann_pct=round(w["ann"], 1), max_dd_pct=round(w["dd"], 1), q_pos_pct=round(w["q_pos"]), full_n=r["n"], full_ann_pct=round(r["ann"], 1), years_pos=f"{r['y_pos']}/{r['y_n']}", period=f"{r['first']}→{r['last']}", source=r["file"])))
        L.append("")
    if a.window == "1y":
        L[0] = L[0].replace("— mỗi thị trường —", "— mỗi thị trường — xếp trên 12 tháng gần nhất —"); selection["mode"] = "horizons-1y"
    md = "\n".join(L) + "\n"; print(md)
    if a.out:
        open(a.out, "w", encoding="utf-8").write(md)
    if a.select:
        selection = carry_flags(selection, a.select)
        json.dump(selection, open(a.select, "w", encoding="utf-8"), indent=1, ensure_ascii=False); print(f"-> {a.select} ({len(selection['setups'])} setups)")


if __name__ == "__main__":
    main()
