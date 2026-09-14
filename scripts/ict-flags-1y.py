#!/usr/bin/env python3
"""Decide the deck-faithful ICT switches (ict_disp / ict_pd / std_origin) per selected ICT setup on the LAST-365-DAY window.
Usage: ict-flags-1y.py [--select docs/architecture/pilot-top5.json] [--out docs/backtests/<file>.md] [--apply] [--criterion ret_dd|rank]
For every ICT setup in the selection file, runs scripts/backtest-methods.py's scan() for all 8 flag combinations with the
setup's own target / management / HTF / fee, keeps only trades entered in the last 365 days of the data, simulates a fresh
$10k account at 1 % risk, and ranks the combinations with one of two criteria:
  ret_dd (default) -- capital preservation first (the system's hard rule): not blown up -> return / max drawdown -> return.
  rank             -- rank-setups.py's 1y criterion: not blown up -> share of positive quarters -> return -> worst quarter.
Both verdicts are printed so the trade-off is visible. A combination is adopted only if it beats the all-off baseline on the
chosen criterion AND has at least MIN_TRADES trades in the window; otherwise the setup keeps all-off.
--apply writes the chosen keys into the selection file (strategy-runner.py reads them per tick). User decision 2026-09-12:
"choose the best from the 1-year backtest".
"""
import argparse, datetime, importlib.util, itertools, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
_s = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py")); bt = importlib.util.module_from_spec(_s); _s.loader.exec_module(bt)
MIN_TRADES = {"crypto": 60, "cfd": 30}
COMBOS = [dict(ict_disp=d, ict_pd=p, std_origin=o) for d in (False, True) for p in (False, True) for o in ("pivot", "highest")]


def window_metrics(trades, fee, start_iso):
    tr = [t for t in trades if t["entry_time"] >= start_iso]
    if not tr:
        return dict(n=0)
    eq, curve, taken = bt.simulate(tr, fee)
    first = min(t["entry_time"] for t in tr); last = max(t["exit_time"] for t in tr)
    q = bt.period_returns(curve, first, last, bt.quarter_key); m = bt.period_returns(curve, first, last, bt.month_key)
    dd = bt.max_dd(curve)
    ret = (eq / bt.START - 1) * 100
    return dict(n=len(taken), ret=ret, dd=dd, ruin=bt.SIM_LAST["ruin"], q_pos=sum(1 for _, v in q if v > 0) / max(1, len(q)), q_n=len(q), quarters=" ".join(f"{k[2:]}:{v:+.0f}" for k, v in q),
                q_worst=min((v for _, v in q), default=0.0), m_pos=sum(1 for _, v in m if v > 0) / max(1, len(m)), m_n=len(m),
                win=sum(1 for t in taken if t["net_R"] > 0) / len(taken) * 100, sumR=sum(t["net_R"] for t in taken), ret_dd=(ret / dd if dd > 0 else ret))


def key_rank(r):
    return (r["ruin"] is None, round(r["q_pos"], 3), round(r["ret"], 1), round(r["q_worst"], 1), round(r["ret_dd"], 2))


def key_ret_dd(r):
    return (r["ruin"] is None, round(r["ret_dd"], 2), round(r["ret"], 1))


CRIT = {"ret_dd": key_ret_dd, "rank": key_rank}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", default=f"{ROOT}/docs/architecture/pilot-top5.json"); ap.add_argument("--out", default=None); ap.add_argument("--apply", action="store_true")
    ap.add_argument("--criterion", default="ret_dd", choices=list(CRIT))
    a = ap.parse_args(); key = CRIT[a.criterion]
    sel = json.load(open(a.select, encoding="utf-8"))
    today = datetime.date.today().isoformat()
    L = [f"# Cờ ICT theo deck cho từng setup pilot — chọn trên cửa sổ 365 ngày cuối — {today}", "",
         "_`scripts/ict-flags-1y.py`. Mỗi setup ICT trong `docs/architecture/pilot-top5.json` chạy 8 tổ hợp (displacement × P/D gate × gốc STD) với đúng target / quản lý / lọc khung lớn / phí của setup, chỉ giữ lệnh vào trong 365 ngày cuối của dữ liệu, tài khoản $10k mới, 1%/lệnh. Tiêu chí chọn (`--criterion {a.criterion}`): `ret_dd` = bảo toàn vốn trước — không cháy → lợi nhuận/drawdown → lợi nhuận; `rank` = tiêu chí 1 năm của `rank-setups.py` — không cháy → tỉ lệ quý dương → lợi nhuận → quý tệ nhất. Cả hai phán quyết đều được in để thấy sự đánh đổi. Tổ hợp chỉ được bật khi thắng tổ hợp gốc theo tiêu chí đã chọn và có đủ lệnh (crypto ≥ 60, CFD ≥ 30)._", ""]
    decisions = {}
    for st in sel["setups"]:
        if st["method"] != "ICT":
            continue
        tf = st["tf"]; fee = st.get("fee_assumed", 0.0002)
        base_opts = dict(bt.OPTS)
        rows = []
        for combo in COMBOS:
            # min_rr is NOT pinned here (2026-09-13): it inherits bt.OPTS' default, which is bt.MIN_RR (3R). This
            # script's --apply writes ict_disp/ict_pd/std_origin straight into pilot-top5.json (line ~98) and
            # rank-setups.py carries those keys over on rewrite, so it is a decision path like any other. Choosing
            # a setup's ICT variant on a trade population the live rr_reason() gate would refuse picks the winner
            # of a race the pilot never runs.
            bt.OPTS.update(base_opts); bt.OPTS.update(sides=("long", "short"), htf=bool(st.get("htf")), mgmt=st.get("mgmt", "none"), **combo)
            trades = []; last = None
            for sym in st["symbols"]:
                r = bt.scan(sym, tf)
                if not r:
                    continue
                trades += r["trades"]["ICT"]; last = max(last or r["last"], r["last"])
            if last is None:
                continue
            start = (datetime.datetime.fromisoformat(last.replace("Z", "+00:00")) - datetime.timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
            m = window_metrics(trades, fee, start); m.update(combo, start=start[:10], last=last[:10]); rows.append(m)
        bt.OPTS.update(base_opts)
        rows = [r for r in rows if r["n"]]
        base = next((r for r in rows if not r["ict_disp"] and not r["ict_pd"] and r["std_origin"] == "pivot"), None)
        need = MIN_TRADES.get(st["market"], 60)
        eligible = [r for r in rows if r["n"] >= need]
        best = max(eligible, key=key) if eligible else None
        chosen = best if (best and base and key(best) > key(base)) else base
        alt = max(eligible, key=CRIT["rank" if a.criterion == "ret_dd" else "ret_dd"]) if eligible else None
        reason = ("dữ liệu quá ít, giữ gốc" if not eligible else ("tổ hợp gốc vẫn tốt nhất" if chosen is base else f"thắng tổ hợp gốc theo tiêu chí {a.criterion} (lợi nhuận/drawdown {chosen['ret_dd']:.2f} so với {base['ret_dd']:.2f})"))
        if alt is not None and alt is not chosen:
            reason += f"; theo tiêu chí còn lại thì chọn disp={'bật' if alt['ict_disp'] else 'tắt'}/P-D={'bật' if alt['ict_pd'] else 'tắt'}/{alt['std_origin']}"
        if chosen:
            decisions[st["id"]] = dict(ict_disp=chosen["ict_disp"], ict_pd=chosen["ict_pd"], std_origin=chosen["std_origin"], reason=reason, window=f"{chosen['start']}→{chosen['last']}", n=chosen["n"])
        L += [f"## {st['id']} — {st['market']} {tf} · {'lọc HTF' if st.get('htf') else 'không lọc HTF'} · {st.get('mgmt')} · phí {fee*100:.2f}%", "",
              f"Cửa sổ {rows[0]['start']} → {rows[0]['last']} (dữ liệu đến {rows[0]['last']}). Ngưỡng số lệnh: {need}.", "",
              "| disp | P/D | gốc STD | Lệnh | Thắng | ΣR | Lợi nhuận | Sụt giảm | LN/DD | Quý dương | Quý tệ nhất | Từng quý | Tháng dương | Chọn |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=key, reverse=True):
            L.append(f"| {'bật' if r['ict_disp'] else '–'} | {'bật' if r['ict_pd'] else '–'} | {r['std_origin']} | {r['n']} | {r['win']:.0f}% | {r['sumR']:+.1f} | {r['ret']:+.1f}% | −{r['dd']:.1f}% | {r['ret_dd']:.2f} | {r['q_pos']*100:.0f}% ({r['q_n']}) | {r['q_worst']:+.1f}% | {r['quarters']} | {r['m_pos']*100:.0f}% ({r['m_n']}) | {'**✓**' if r is chosen else ''} |")
        L += ["", f"**Quyết định:** disp={'bật' if chosen['ict_disp'] else 'tắt'}, P/D={'bật' if chosen['ict_pd'] else 'tắt'}, gốc STD={chosen['std_origin']} — {reason}." if chosen else "**Quyết định:** không có lệnh nào trong cửa sổ.", ""]
    if a.apply:
        for st in sel["setups"]:
            d = decisions.get(st["id"])
            if d:
                st.update(ict_disp=d["ict_disp"], ict_pd=d["ict_pd"], std_origin=d["std_origin"], flags_decided=f"{today} by scripts/ict-flags-1y.py on {d['window']} ({d['n']} trades): {d['reason']}")
        json.dump(sel, open(a.select, "w", encoding="utf-8"), ensure_ascii=False, indent=1); open(a.select, "a").write("\n")
        L += [f"Đã ghi vào `{os.path.relpath(a.select, ROOT)}` (khoá `ict_disp`, `ict_pd`, `std_origin`, `flags_decided`)."]
    out = a.out or f"{ROOT}/docs/backtests/{today}-ict-flags-1y.md"
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(json.dumps(decisions, ensure_ascii=False, indent=1)); print("->", os.path.relpath(out, ROOT))


if __name__ == "__main__":
    main()
