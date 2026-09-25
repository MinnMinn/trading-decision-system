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
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import snapshot          # CLAUDE.md §10: every research run identifies the dataset it read
import instruments as _I  # §35: the run's own symbols name the market, and (market, tf) names the system
import performance as _perf  # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import providers as _P       # §4: which venue this market's orders go to -- and therefore what a fill costs
import importlib.util as _iu
_rs = _iu.spec_from_file_location("risk_model", os.path.join(ROOT, "scripts", "risk_model.py"))
_RM = _iu.module_from_spec(_rs); _rs.loader.exec_module(_RM)   # THE fee source (risk-config.json `costs`)
METHODS = bt.RUNNER_METHODS   # ONE source (scripts/backtest-methods.py); WYCKOFF, COMBINED and PARTIAL were
                              # removed 2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md finding 6) --
                              # this used to be a second, hand-kept copy of the same tuple, which is exactly
                              # how it stayed stale.
# A config's fee is a SIDE of the venue's declared cost, never a literal. Until 2026-09-18 these carried
# 0.0005 / 0.0002 / 0.0002 outright -- the Binance taker/maker schedule -- and every market got them, so a CFD
# row in config B or C was priced at 0.02 %/side when the MT5 account pays 0.05 %. The ranking then SELECTED
# two of those rows (cfd-day-combined-1h-border-b, cfd-swing-wyckoff-4h-border-b), i.e. the pilot was about to
# be handed setups whose edge was measured 2.5x cheaper than the venue charges.
#
# `taker` vs `maker` is the config's real claim -- "this rule enters at market" vs "this rule enters on a
# limit" -- and what THAT costs is the venue's business. On MT5 the broker prices CFDs in the spread and both
# sides are equal, so B and C correctly stop claiming a rebate that does not exist there and differ from A only
# by the management rule and the HTF filter, which is what they actually are.
CONFIGS = {"A": dict(side="taker", mgmt="none", htf=False),
           "B": dict(side="maker", mgmt="be", htf=False),
           "C": dict(side="maker", mgmt="be", htf=True)}


def config_fee(cfg, market):
    """The per-side fee this config implies ON THIS MARKET, from risk-config.json's `costs` -- THE one source.

    Raises rather than defaulting: a market whose venue declares no cost cannot be priced, and guessing a fee
    is how a backtest comes to describe an account nobody has (CLAUDE.md §34, §38).
    """
    venue = _P.unattended_venue_for(market)
    costs = _RM._config()["costs"]
    if venue not in costs or not isinstance(costs[venue], dict):
        raise SystemExit(f"risk-config.json declares no costs for venue {venue!r} ({market}); refusing to "
                         f"price a backtest at a guessed fee")
    return costs[venue][f"{cfg['side']}_pct_per_side"]


def entry_order_type_for(cfg, method):
    """INT-4/PAR-2 (docs/audits/2026-09-24-system-audit.md): the ENTRY order type `simulate()` should price
    for this (config, method) pair -- and it is no longer simply `cfg["side"]`.

    Config A prices every method taker/taker on purpose (the "raw rule" baseline, unaffected by how any method
    actually enters). Configs B/C used to price EVERY method "maker" on both sides, which is right for ICT (a
    resting limit) but wrong for WYCKOFF-BOOK/COMBINED-BOOK (methods.json runner_methods[method].entry ==
    "market", i.e. taker) -- a CFD/crypto WYCKOFF-BOOK row in B/C was priced at the maker rate on both legs
    though its real entry is a market order and its exit (this file's own `simulate()` call) is ALWAYS taker.
    So for B/C the entry side comes from the METHOD's own declared entry, never from the config letter; only
    the EXIT side (always "taker", applied inside `simulate()` itself) is unconditional.
    """
    if cfg["side"] == "taker":
        return "taker"
    return "maker" if bt._M.RUNNER_METHODS[method]["entry"] == "limit" else "taker"
MIN_TRADES = 30


def metrics(curve, first, last, taken, final, dd, account=None, full_taken=None, full_curve=None):
    q = [v for _, v in bt.period_returns(curve, first, last, bt.quarter_key)]
    y = bt.period_returns(curve, first, last, bt.year_key)
    days = (datetime.date.fromisoformat(last[:10]) - datetime.date.fromisoformat(first[:10])).days or 1
    sd = statistics.pstdev(q) if len(q) > 1 else 0.0
    # CLAUDE.md §39's twenty-three, additively, from the ONE computer. The row's own keys are unchanged --
    # rank-setups.py reads `ann`, `q_pos`, `y_pos`, `ruin`, `stab` positionally -- but `stab` is no longer the
    # only risk-adjusted number available: it is a quarterly Sharpe-family quantity under a different name,
    # and `perf.sharpe` / `perf.sortino` are now beside it, per trade and labelled as such.
    # §39's probability metrics (risk_of_ruin, account_failure_probability, prop_pass_probability) must be
    # estimated over the FULL trade population, not over the account run's truncated one. `simulate(account=)`
    # STOPS at the first breach, so `taken` under an account is "the trades before it broke" -- on the crypto
    # demo profile that is 5-16 trades, and bootstrapping them resamples a sequence already conditioned on
    # ending in failure. The account's RULES still apply (they are what the bootstrap tests each resampled path
    # against); only the sample they are tested on is the untruncated one. `failed_by` on the row stays what it
    # was: a fact about the one real path. Fixed 2026-09-19 when ranking by prop-pass returned nothing for
    # crypto because every row's n had collapsed to the length of its own failure.
    pop, pop_curve = (full_taken, full_curve) if full_taken is not None else (taken, curve)
    pop_days = days or 1
    perf = _perf.metrics(pop, equity=pop_curve, account=account,
                         trades_per_year=(len(pop) * 365 / pop_days) if pop else None)
    return dict(n=len(pop), n_until_account_failure=len(taken), ann=((final / bt.START) ** (365 / days) - 1) * 100, dd=dd, final=final, ruin=bt.SIM_LAST["ruin"], q_pos=sum(1 for v in q if v > 0) / len(q) * 100 if q else 0, q_worst=min(q) if q else 0,
                q_med=statistics.median(q) if q else 0, q_mean=statistics.mean(q) if q else 0, q_sd=sd, stab=(statistics.mean(q) / sd * len(q) ** 0.5) if sd else 0,
                y_pos=sum(1 for _, v in y if v > 0), y_n=len(y), years=y, quarters=q, perf=perf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,30m,1H,2H,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT"); ap.add_argument("--out"); ap.add_argument("--json"); ap.add_argument("--ict-target", default="range", choices=["range", "std2", "std25", "std4", "erl_next", "irl"])
    # CLAUDE.md §33: a personal account and a prop account do not lose the same way, so "did this setup
    # survive?" has no answer until you say WHOSE account. Without one the only loss condition is a blown
    # balance (the personal notion) and §39's money/ruin/failure/pass metrics stay UNAVAILABLE BY NAME.
    ap.add_argument("--account", help="an §33 profile id from docs/architecture/account-profiles.json")
    ap.add_argument("--account-file", help="a JSON profile to EVALUATE against without shipping it as "
                                           "configuration -- for asking 'what would this look like under my "
                                           "prop firm's rules?' when no such account exists here (§57)")
    a = ap.parse_args(); today = datetime.date.today().isoformat(); rows = []
    # THE one loader (A3, docs/plans/2026-09-18-close-feature-gaps.md §0.3): this used to be five lines
    # duplicated inline here and again in backtest-methods.py main(); `bt.load_account` is now the only place
    # "--account and --account-file are two different answers" is enforced, so the two reports cannot drift
    # on what the flag means.
    account = bt.load_account(a)
    if account:
        print(f"account rules in force: {account['id']} ({account.get('context_type')}) -- a run ends when THIS "
              f"account would have failed, not only when the balance is gone", file=sys.stderr)
    # The market names the venue, and the venue names the fee. Derived from the run's own symbols so a CFD run
    # cannot be priced on a crypto schedule (the defect this replaced).
    market = _I.market_of(a.symbols.split(",")[0])
    if market is None:
        raise SystemExit(f"{a.symbols.split(',')[0]} is not on the instrument allowlist; refusing to guess a "
                         f"market, a venue, or a fee")
    for tf in a.tf.split(","):
        for cname, cfg in CONFIGS.items():
            fee = config_fee(cfg, market)
            bt.OPTS.update(mgmt=cfg["mgmt"], htf=cfg["htf"], sides=("long", "short"), types=(1, 2, 3), range_touches=0, entry="book", sloped_gate=False, st_gate=False, phase_b_gate=False, st_min=None, phase_d=True, combined_entry="limit", ict_target=a.ict_target)
            scans = [s for s in (bt.scan(sym, tf) for sym in a.symbols.split(",")) if s]
            if not scans:
                continue
            first = min(s["first"] for s in scans); last = max(s["last"] for s in scans)
            since = (datetime.date.fromisoformat(last[:10]) - datetime.timedelta(days=365)).isoformat() + "T00:00:00Z"
            for m in METHODS:
                tr = [t for s in scans for t in s["trades"][m]]
                # INT-4/PAR-2, PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): entry priced by THIS
                # method's own declared entry (never blindly "maker" for every method in configs B/C), exit
                # always taker (inside simulate() itself); sizing matches strategy-runner's own fee-aware,
                # notional-cap-aware, loss-throttled formula.
                entry_type = entry_order_type_for(cfg, m)
                final, curve, taken = bt.simulate(tr, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
                failed_by, acct_id = bt.SIM_LAST["failed_by"], bt.SIM_LAST["account"]
                # The same trades WITHOUT the account's stop, so the §39 probabilities have the whole
                # population to resample (see metrics() -- the account's rules still gate every path).
                f_full, c_full, t_full = (bt.simulate(tr, fee, entry_order_type=entry_type, live_parity_sizing=True) if account else (final, curve, taken))
                row = dict(tf=tf, cfg=cname, method=m, first=first[:10], last=last[:10],
                           failed_by=failed_by, account=acct_id,
                           **metrics(curve, first, last, taken, final, bt.max_dd(curve), account=account,
                                     full_taken=t_full, full_curve=c_full))
                # last-365-day window (user decision 2026-09-11: `/automation on setup top N` ranks on the most recent year)
                tr1 = [t for t in tr if t["entry_time"] >= since]
                f1, c1, tk1 = bt.simulate(tr1, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
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
        # CLAUDE.md §10: a result must identify the data it was computed from. Before this, the only
        # top-level key above sixty rows of metrics was `generated` -- a DATE -- so "re-run this and see if
        # it still holds" had no defined meaning. The snapshot is additive (rank-setups.py reads `rows` and
        # is unaffected) and best-effort: a research run must not FAIL because a snapshot could not be taken,
        # but it must never silently claim one, so the failure is recorded in place of the snapshot.
        try:
            snap = snapshot.dataset_snapshot([(sym, tf) for tf in a.tf.split(",")
                                              for sym in a.symbols.split(",")],
                                             base=os.path.join(ROOT, "data", "history"))
        except (OSError, ValueError, KeyError) as exc:
            snap = {"snapshot_error": f"{type(exc).__name__}: {exc}",
                    "_note": "CLAUDE.md §10: this run's dataset could not be identified; treat the result as "
                             "not reproducible."}
        # CLAUDE.md §11, the sibling block: the CONFIGURATION behind the numbers, captured BY VALUE. `RISK`
        # and `MIN_RR` are read at import from mutable config files, so without this a re-run after an edit
        # measures a different system while the old report still claims the old figures -- which is exactly
        # what happened when the risk ceiling moved 3% -> 1% on 2026-09-17.
        try:
            cfg_snap = snapshot.backtest_config_snapshot(
                bt, timeframes=a.tf.split(","), methods=METHODS, configs=CONFIGS,
                fee_pct=getattr(a, "fee_pct", None), ict_target=a.ict_target,
                dataset_snapshot_id=snap.get("snapshot_id"),
                # §35: the (market, timeframe) pair IS the Trading System, so the market is what lets the
                # snapshot name which system's declared dependencies this run was measuring. Derived from the
                # run's own symbols rather than passed in, so it cannot disagree with them.
                market=_I.market_of(a.symbols.split(",")[0]))
        except (OSError, ValueError, KeyError, AttributeError) as exc:
            cfg_snap = {"snapshot_error": f"{type(exc).__name__}: {exc}",
                        "_note": "CLAUDE.md §11: this run's configuration could not be captured; treat the "
                                 "result as not reproducible."}
        # CLAUDE.md §38, the third block: what this run's own evidence makes the rows above worth. It is
        # written HERE and not left to the consumer because rank-setups.py reads these files to choose what
        # the pilot trades, and a selection made from an unassessed research result is exactly the outcome
        # §38's last sentence forbids. `bt.assess_run` reads the engine's data-quality flags, its declared
        # execution assumptions and the configuration snapshot above; it is not a second opinion about them.
        validity = bt.assess_run(cfg_snap, run=f"stability-report {a.symbols} {a.tf} target={a.ict_target}")
        print(validity.describe(), file=sys.stderr)
        json.dump(dict(generated=today, dataset_snapshot=snap, config_snapshot=cfg_snap,
                       research_validity=validity.stamp(), rows=rows),
                  open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
