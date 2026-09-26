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

# INT-5 (docs/audits/2026-09-24-system-audit.md): setups used to be SELECTED on the same last-365-day window
# they were then judged on, so the pilot's "evidence" was the window the choice was fitted to. Every row now
# also carries an in-sample / out-of-sample split around a cutoff DERIVED FROM THE DATA (never typed):
#   cutoff     = the dataset's last bar DATE minus OOS_MONTHS calendar months, at 00:00Z
#   in-sample  = trades whose ENTRY is in [cutoff - IS_LOOKBACK_DAYS, cutoff)  -- what selection may read
#   OOS        = trades whose ENTRY is on/after the cutoff                      -- what selection is judged on
# A trade opened before the cutoff belongs to in-sample even when it closes after it: membership is decided
# by the moment the decision was made (CLAUDE.md §8), never by an outcome. IS_LOOKBACK_DAYS keeps the
# in-sample basis the same length as the `--window 1y` ranking it replaces, shifted back to end at the cutoff.
# Each side is simulated as its OWN fresh START account (as `w1y` already was), so an OOS number never carries
# equity -- or a ruin -- earned in-sample. Consumer: scripts/rank-setups.py --window oos6m.
OOS_MONTHS = 6
IS_LOOKBACK_DAYS = 365


def months_before(d, months):
    """`d` minus `months` CALENDAR months, clamped to the target month's last day (Aug 31 - 6 -> Feb 28/29)."""
    y, m = d.year, d.month - months
    while m <= 0:
        m += 12; y -= 1
    import calendar as _cal
    return datetime.date(y, m, min(d.day, _cal.monthrange(y, m)[1]))


def oos_cutoff(last_bar_time, months=OOS_MONTHS):
    """The OOS cutoff for a dataset whose last bar is `last_bar_time` (ISO string): its DATE minus `months`
    calendar months, as the same 'YYYY-MM-DDT00:00:00Z' string form the engine's bar times compare against."""
    return months_before(datetime.date.fromisoformat(last_bar_time[:10]), months).isoformat() + "T00:00:00Z"


def is_since_for(cutoff, lookback_days=IS_LOOKBACK_DAYS):
    return (datetime.date.fromisoformat(cutoff[:10]) - datetime.timedelta(days=lookback_days)).isoformat() + "T00:00:00Z"


def split_in_out(trades, cutoff, is_since=None):
    """(in_sample, oos) by ENTRY time only: in-sample = is_since <= entry < cutoff; OOS = entry >= cutoff.
    A trade exactly AT the cutoff is OOS; one opened before and closed after is in-sample."""
    ins = [t for t in trades if t["entry_time"] < cutoff and (is_since is None or t["entry_time"] >= is_since)]
    oos = [t for t in trades if t["entry_time"] >= cutoff]
    return ins, oos


def dataset_last_bar(symbols, tfs):
    """(last bar time across every series this run reads, [(sym, tf) actually present]). The cutoff is derived
    from THIS, so it moves with the data and is never a typed date."""
    last, present = None, []
    for tf in tfs:
        for sym in symbols:
            c, _src = bt.load(sym, tf)
            if not c:
                continue
            present.append((sym, tf))
            if last is None or c[-1]["time"] > last:
                last = c[-1]["time"]
    return last, present


def _plain(v):
    """A §39 value as a plain float, or None when it is an unavailable() marker (never a fake 0)."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict) and "unavailable" not in v:
        for k in ("value", "fraction"):
            if isinstance(v.get(k), (int, float)):
                return float(v[k])
    return None


def window_block(trades, fee, account, entry_type, since, until):
    """One side of the IS/OOS split: simulated as a fresh START account, summarised with the same metrics()
    the `w1y` block uses, plus the four numbers the OOS gate reads, as plain values."""
    f, c, tk = bt.simulate(trades, fee, account=account, entry_order_type=entry_type, live_parity_sizing=True)
    w = metrics(c, since, until, tk, f, bt.max_dd(c)); w.pop("years", None); w.pop("quarters", None)
    w.update(since=since[:10], until=until[:10], net_pnl=f - bt.START,
             expectancy_R=_plain(w["perf"].get("expectancy")), profit_factor=_plain(w["perf"].get("profit_factor")))
    w.update(monthly_block(c, since, until, f))
    return w


def calendar_months(since, until):
    """Every calendar month 'YYYY-MM' touched by [since, until], in order -- including months with no trade."""
    y, m = int(since[:4]), int(since[5:7]); ey, em = int(until[:4]), int(until[5:7]); out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}"); m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def monthly_block(curve, since, until, final):
    """ADR 0008 / selection-criteria.json inputs for one window. Each CALENDAR month's return is the equity at
    that month's last booked point vs the previous month's, so a month with no trade is a 0% month, never a
    missing one (period_returns() skips such months). The first and last months are partial when the window does
    not start/end on a month boundary, and are flagged. `m_mean_geo` is the geometric mean monthly return over the
    window's exact length (30.4375-day months), so partial months cannot distort it."""
    eq_end = {}
    for t, e in curve:
        eq_end[t[:7]] = e
    months, prev = [], bt.START
    for k in calendar_months(since, until):
        e = eq_end.get(k, prev)
        months.append(dict(month=k, ret_pct=round((e / prev - 1) * 100, 4))); prev = e
    if months:
        months[0]["partial"] = since[8:10] != "01"
        months[-1]["partial"] = True  # a window ends at a cutoff or at the dataset's last bar, never on a month end we can assert
    days = max((datetime.date.fromisoformat(until[:10]) - datetime.date.fromisoformat(since[:10])).days, 1)
    rets = [x["ret_pct"] for x in months]
    return dict(months=months,
                m_mean_geo=((final / bt.START) ** (30.4375 / days) - 1) * 100,
                m_losing=sum(1 for v in rets if v < 0),
                m_worst=min(rets) if rets else 0.0)


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
    last_bar, present_series = dataset_last_bar(a.symbols.split(","), a.tf.split(","))
    if last_bar is None:
        raise SystemExit("no history for any requested (symbol, timeframe); nothing to measure")
    cutoff = oos_cutoff(last_bar); is_since = is_since_for(cutoff)
    print(f"OOS holdout (INT-5): dataset last bar {last_bar} -> cutoff {cutoff}; in-sample from {is_since}",
          file=sys.stderr)
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
                # INT-5: the in-sample / OOS split around the data-derived cutoff (see OOS_MONTHS above).
                t_in, t_out = split_in_out(tr, cutoff, is_since)
                row["oos6m"] = dict(cutoff=cutoff, dataset_last_bar=last_bar, split="entry_time",
                                    in_sample=window_block(t_in, fee, account, entry_type, max(first, is_since), cutoff),
                                    oos=window_block(t_out, fee, account, entry_type, max(first, cutoff), last))
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
            # Only the series that EXIST (and were therefore read): a requested (symbol, timeframe) with no
            # history file -- USOIL/UKOIL have no 15m -- used to make the whole snapshot fail with
            # FileNotFoundError, leaving the CFD runs with no dataset identity at all. The requested-but-absent
            # pairs are listed beside it, so the omission is recorded rather than silent.
            snap = snapshot.dataset_snapshot(present_series, base=os.path.join(ROOT, "data", "history"))
            absent = [f"{s}:{t}" for t in a.tf.split(",") for s in a.symbols.split(",") if (s, t) not in present_series]
            if absent:
                snap["requested_but_absent"] = absent
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
        run_params = dict(symbols=a.symbols, tf=a.tf, ict_target=a.ict_target, account=a.account,
                          account_file=a.account_file, live_parity_sizing=True, entry_pricing="per-method (INT-4/PAR-2)")
        oos_meta = dict(months=OOS_MONTHS, dataset_last_bar=last_bar, cutoff=cutoff, in_sample_since=is_since,
                        in_sample_lookback_days=IS_LOOKBACK_DAYS, split="entry_time: entry < cutoff -> in-sample, "
                        "entry >= cutoff -> OOS; each side a fresh account", source="scripts/stability-report.py (INT-5)")
        json.dump(dict(generated=today, run_params=run_params, oos_holdout=oos_meta, dataset_snapshot=snap,
                       config_snapshot=cfg_snap, research_validity=validity.stamp(), rows=rows),
                  open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
