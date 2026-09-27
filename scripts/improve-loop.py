#!/usr/bin/env python3
"""CLAUDE.md §41 stages 1-4 + §42, orchestrated (docs/plans/2026-09-18-close-feature-gaps.md §0.10):

    baseline -> cluster LOSSES -> declared candidates (docs/architecture/improve-candidates.json) ->
    run each candidate -> one sealed experiment.Record per candidate (docs/experiments/) -> ranked report

Usage: improve-loop.py --market crypto --tf 15m --symbols BTCUSDT[,ETHUSDT,...] --method ICT
       [--min-size 3] [--objective expectancy] [--min-trades 20] [--fee-pct 0.05]
       [--account <id> | --account-file <path>] [--trader <id>] [--calendar <path>] [--sessions a,b]
       [--bars N] [--store PATH] [--out FILE.md] [--json FILE.json]

Audit finding this closes (docs/audits/2026-09-18-feature-audit.md row 8): "Không có orchestrator cluster ->
candidate -> backtest-methods -> so baseline -> report; ... docs/experiments/ chưa tồn tại." §41's own words
are the guardrail this script is built around, not a decoration on top of it:

    "AI may: discover patterns, identify repeated failure clusters, generate hypotheses, propose candidate
    changes, analyze experiment results. AI must NEVER silently rewrite the production Trading System."

So this script never writes `docs/architecture/pilot-selection.json`, `docs/architecture/methods.json`, or
`docs/architecture/trading-systems.json` -- adopting a candidate is §41 stage 11 (human decision), and it
happens outside this script entirely, by a human reading the report and, if they approve, making that
registry edit themselves. Every candidate this script runs is one DECLARED in
`docs/architecture/improve-candidates.json` (§41: "No candidate is invented at runtime"); a cluster whose key
fields match no declared candidate is reported as having none, not guessed at.
"""
import argparse
import datetime
import importlib.util
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel

# scripts/backtest-methods.py has a hyphen in its filename -- cannot be `import`ed directly. Same pattern
# scripts/stability-report.py already uses (module alias "bt").
_btspec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
bt = importlib.util.module_from_spec(_btspec)
_btspec.loader.exec_module(bt)

import sessions as S
import event_risk as ER
import outcomes as O
import experiment as X
import research_ledger as RL
import ranking as RK
import snapshot as SN
import trading_system as TS

CANDIDATES_PATH = os.path.join(ROOT, "docs", "architecture", "improve-candidates.json")

# Forbidden write targets (CLAUDE.md §41). This script's source is grepped for these three paths by
# scripts/tests/test_improve_loop.py -- they must appear only in comments/read paths, never on a write.
_PILOT_SELECTION = os.path.join(ROOT, "docs", "architecture", "pilot-selection.json")   # never written
_METHODS_JSON = os.path.join(ROOT, "docs", "architecture", "methods.json")   # never written
_TRADING_SYSTEMS = os.path.join(ROOT, "docs", "architecture", "trading-systems.json")   # never written

BY_FIELDS = ("method", "session", "vol_type", "via")

CLUSTER_HEAD_VI = "## Cụm lỗi lặp lại (loss clusters)"
NO_CANDIDATE_HEAD_VI = "### Không có ứng viên khai báo"


def _load_candidates(path=None):
    with open(path or CANDIDATES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    table = data.get("candidates") or {}
    for field, by_value in table.items():
        if field not in BY_FIELDS:
            raise ValueError(f"{CANDIDATES_PATH}: candidate field {field!r} is not one of the cluster keys "
                             f"improve-loop.py groups by ({list(BY_FIELDS)})")
        for value, spec in by_value.items():
            if "override" not in spec or not spec.get("override"):
                raise ValueError(f"{CANDIDATES_PATH}: {field}={value!r} has no `override`")
            if not str(spec.get("why") or "").strip():
                raise ValueError(f"{CANDIDATES_PATH}: {field}={value!r} has no `why`")
    return table


def _row_from_trade(t, method):
    """One §41 outcome row for `outcomes.cluster()`, built from a TAKEN trade (the population that was
    actually admitted and simulated -- `simulate()`'s own admission-time refusals, §24-§32/§21, are already
    excluded from `taken`, so a cluster here is a cluster of REALISED trade outcomes, not of refusals)."""
    outcome = t.get("outcome")
    return {
        "is_failure": outcome == "loss",
        "state": str(outcome or "?").upper(),
        "detail": f"{t.get('symbol')} {t.get('tf')} {t.get('side')} {t.get('entry_time')} "
                 f"R={t.get('net_R', t.get('R'))}",
        "method": method,
        "session": S.primary(t["entry_time"]) if t.get("entry_time") else None,
        "vol_type": t.get("vol_type"),
        "via": t.get("via"),
    }


def _apply_override(base_opts, base_sessions, override):
    """A NEW (opts, sessions) pair for one declared candidate. `sessions` REPLACES the baseline set (this is
    a candidate CONFIGURATION, not a §0.9 trader tighten); every other key must be a real OPTS key."""
    opts = dict(base_opts)
    sessions_ = base_sessions
    for k, v in override.items():
        if k == "sessions":
            sessions_ = tuple(v)
        elif k in bt.OPTS:
            opts[k] = tuple(v) if k == "types" and isinstance(v, list) else v
        else:
            raise ValueError(f"{CANDIDATES_PATH}: override key {k!r} is neither 'sessions' nor a "
                             f"scripts/backtest-methods.py OPTS key ({sorted(bt.OPTS)})")
    return opts, sessions_


def _account_config(account):
    if account is None:
        return X.unavailable("no --account was supplied for this run")
    return {"id": account.get("id"), "context_type": account.get("context_type"),
           "source": "docs/architecture/account-profiles.json"}


def _news_config(calendar):
    if calendar is None:
        return X.unavailable("no --calendar was supplied for this run")
    return {"policy": calendar.get("policy") or {}, "snapshot_id": (calendar.get("snapshot") or {}).get("id")}


def _session_config(sessions_):
    if not sessions_:
        return X.unavailable("no session gate was in force for this run")
    return {"allowed_sessions": list(sessions_)}


def _system_version(market, tf):
    try:
        style = TS.for_market_tf(market, tf)["id"]
    except KeyError:
        return X.unavailable(f"no Trading System covers {market!r} at {tf!r} "
                             f"(scripts/trading_system.py for_market_tf)"), None
    return TS.get(style)["version"], style


def _seal_candidate(*, run_id, candidate_id, override, why, cluster, baseline_stats, candidate_stats,
                    market, tf, method, symbols, account, calendar, sessions_, trader_id, dataset_snap,
                    cfg_snap, validation_method, store, at):
    parent_version, style = _system_version(market, tf)
    candidate_version = f"{parent_version if isinstance(parent_version, str) else 'unresolved'}" \
                        f"-candidate-{candidate_id}-{run_id}"
    rec = X.Record(
        hypothesis=f"Restricting/changing {candidate_id} away from the baseline loss cluster "
                  f"({cluster['n']} losses, {method}/{market}/{tf}) improves the objective without a "
                  f"material drop in sample size.",
        motivation=f"declared candidate override for cluster key {candidate_id}: {why}",
        parent_trading_system_version=parent_version,
        candidate_version=candidate_version,
        experiment_id=f"{run_id}-{candidate_id}".replace("=", "-"), at=at)
    rec.set("failure_pattern", {"cluster_key": cluster["key"], "n": cluster["n"], "states": cluster["states"],
                                "grouped_by": list(BY_FIELDS), "source": "scripts/outcomes.py cluster()"})
    rec.set("dataset_snapshot", dataset_snap)
    rec.set("configuration_snapshot", cfg_snap)
    rec.set("account_configuration", _account_config(account))
    rec.set("risk_configuration", {"risk_pct": bt.RISK, "min_rr_floor": bt.MIN_RR,
                                   "source": "docs/architecture/risk-config.json via trading_env"})
    rec.set("news_configuration", _news_config(calendar))
    rec.set("session_configuration", _session_config(sessions_))
    rec.set("parameters", {"override": override, "symbols": list(symbols), "trader": trader_id})
    rec.set("random_seed", bt._perf.BOOTSTRAP_SEED)
    rec.set("test_periods", {"first": cluster.get("first"), "last": cluster.get("last")})
    rec.set("validation_method", validation_method)
    rec.set("metrics", {"baseline": baseline_stats, "candidate": candidate_stats})
    rec.set("robustness_results", X.unavailable(
        "no walk-forward / perturbation run recorded (§45) -- improve-loop.py runs one in-sample comparison "
        "against the baseline only"))
    rec.set("system_version", parent_version)
    sealed = rec.seal()
    path = X.write(sealed, store=store)
    return sealed, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)
    ap.add_argument("--tf", required=True)
    ap.add_argument("--symbols", required=True)
    ap.add_argument("--method", required=True, choices=bt.RUNNER_METHODS)
    ap.add_argument("--min-size", type=int, default=3, help="outcomes.cluster() min_size (§41 stage 2-3)")
    ap.add_argument("--objective", default="expectancy", help="a docs/architecture/ranking.json objective id")
    ap.add_argument("--min-trades", type=int, default=20, help="an 'outperformer' must also have at least "
                                                                "this many taken trades")
    ap.add_argument("--fee-pct", type=float, default=0.05)
    ap.add_argument("--account")
    ap.add_argument("--account-file")
    ap.add_argument("--trader")
    ap.add_argument("--calendar")
    ap.add_argument("--sessions")
    ap.add_argument("--bars", type=int, default=None, help="cap each loaded series to its most recent N bars "
                                                            "(test/sandbox speed only -- see "
                                                            "scripts/backtest-methods.py limit_bars())")
    ap.add_argument("--store", default=None, help="experiment store dir (default: docs/experiments/)")
    ap.add_argument("--out")
    ap.add_argument("--json")
    a = ap.parse_args()

    bt.limit_bars(a.bars)
    symbols = tuple(a.symbols.split(","))
    method = a.method
    account = bt.load_account(a)
    calendar = ER.load(path=a.calendar) if a.calendar else None
    sessions_ = tuple(a.sessions.split(",")) if a.sessions else None
    if sessions_:
        unknown = [s for s in sessions_ if s not in S.LABELS]
        if unknown:
            raise SystemExit(f"--sessions names {unknown}, not in docs/architecture/sessions.json")
    if a.trader:
        bt._TC.for_trader(a.trader)
        t_sessions = bt.trader_sessions_for(a.trader)
        if t_sessions is not None:
            sessions_ = tuple(sorted(set(sessions_) & t_sessions)) if sessions_ else tuple(sorted(t_sessions))

    fee = a.fee_pct / 100
    today = datetime.date.today().isoformat()
    run_id = f"{today}-improve-{a.market}-{a.tf}-{method.lower()}"

    # ---- 1. baseline
    scanner = (lambda sym: bt.scan_for_trader(sym, a.tf, a.trader, only=(method,))) if a.trader else \
             (lambda sym: bt.scan(sym, a.tf, only=(method,)))
    scans = [s for s in (scanner(sym) for sym in symbols) if s]
    if not scans:
        raise SystemExit(f"no history for {symbols} at {a.tf} -- nothing to measure")
    first = min(s["first"] for s in scans)
    last = max(s["last"] for s in scans)
    base_trades = [dict(t, method=method) for s in scans for t in s["trades"].get(method, [])]
    # Round-4a fix round 1 (code review of a746ffc), should-fix #3: this run's own economics must match
    # stability-report.py's -- entry priced by THIS method's own declared entry (maker for a resting limit,
    # taker for a market order, docs/architecture/methods.json), exit always taker, and sizing that respects
    # the same notional-cap/loss-throttle/fee-in-budget formula strategy-runner.size() applies live
    # (INT-4/PAR-2, PAR-4/DEC-4). Before this, /improve measured a candidate's economics under the OLD flat
    # fee_pct/uncapped-sizing convention, which is not the system stability-report.py (and therefore
    # rank-setups.py) would actually rank it against.
    entry_order_type = "maker" if bt._M.RUNNER_METHODS[method]["entry"] == "limit" else "taker"
    base_eq, base_curve, base_taken = bt.simulate(base_trades, fee, account=account, calendar=calendar,
                                                   sessions=sessions_, trader=a.trader,
                                                   entry_order_type=entry_order_type, live_parity_sizing=True)
    base_stats = bt.summarize(base_taken, curve=base_curve, account=account)

    ledger = RL.periods()
    validation_method = (
        X.unavailable("in-sample only: no OOS period carved out (§44) -- "
                      "scripts/research_ledger.py periods() reports no untouched or holdout period")
        if not ledger["validation_available"] else
        {"method": "in-sample comparison against the same-data baseline",
        "oos_periods_available": [p["id"] for p in ledger["by_state"][RL.UNTOUCHED]] +
                                 [p["id"] for p in ledger["by_state"][RL.HOLDOUT]],
        "_note": "an OOS period exists in the ledger but this run did not carve the candidate search away "
                 "from it -- see docs/architecture/research-ledger.json before treating this as validated"})

    # ---- 2. cluster losses
    rows = [_row_from_trade(t, method) for t in base_taken]
    clusters = O.cluster(rows, by=BY_FIELDS, min_size=a.min_size)

    # ---- 3. declared candidates, deduplicated by (field, value)
    table = _load_candidates()
    triggered = {}          # (field, value) -> {"override":..., "why":..., "clusters":[cluster,...]}
    no_candidate = []
    for c in clusters["clusters"]:
        matched_any = False
        for field in BY_FIELDS:
            value = c["key"].get(field)
            spec = (table.get(field) or {}).get(value)
            if spec is None:
                continue
            matched_any = True
            key = (field, value)
            entry = triggered.setdefault(key, {"override": spec["override"], "why": spec["why"], "clusters": []})
            entry["clusters"].append(c)
        if not matched_any:
            no_candidate.append(c)

    # ---- 4. run each candidate once, seal one experiment record
    dataset_snap = SN.dataset_snapshot([(sym, a.tf) for sym in symbols])
    try:
        cfg_snap = SN.backtest_config_snapshot(bt, timeframes=[a.tf], methods=(method,), fee_pct=a.fee_pct,
                                               market=a.market, calendar=calendar, sessions=sessions_,
                                               account=account)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        cfg_snap = {"snapshot_error": f"{type(exc).__name__}: {exc}"}

    base_opts = dict(bt.OPTS)
    results = []
    for (field, value), entry in triggered.items():
        candidate_id = f"{field}={value}"
        try:
            cand_opts, cand_sessions = _apply_override(base_opts, sessions_, entry["override"])
        except ValueError as exc:
            results.append({"candidate_id": candidate_id, "error": str(exc)})
            continue
        # A `sessions`-only override changes nothing scan() reads (session gating is simulate()'s job, not
        # scan()'s) -- re-running the scanner for it would just be the same expensive ICT live-scanner pass
        # over every bar again for an identical answer. Reuse the already-scanned baseline trades.
        opts_only = {k: v for k, v in entry["override"].items() if k != "sessions"}
        if not opts_only:
            cand_trades_all = base_trades
        else:
            cand_trades_all = []
            for sym in symbols:
                saved = dict(bt.OPTS)
                bt.OPTS.clear(); bt.OPTS.update(cand_opts)
                try:
                    s = bt.scan(sym, a.tf, only=(method,))
                finally:
                    bt.OPTS.clear(); bt.OPTS.update(saved)
                if s:
                    cand_trades_all += [dict(t, method=method) for t in s["trades"].get(method, [])]
        c_eq, c_curve, c_taken = bt.simulate(cand_trades_all, fee, account=account, calendar=calendar,
                                             sessions=cand_sessions, trader=a.trader,
                                             entry_order_type=entry_order_type, live_parity_sizing=True)
        c_stats = bt.summarize(c_taken, curve=c_curve, account=account)
        cluster0 = dict(entry["clusters"][0], first=first, last=last)
        sealed, path = _seal_candidate(
            run_id=run_id, candidate_id=candidate_id, override=entry["override"], why=entry["why"],
            cluster=cluster0, baseline_stats=base_stats, candidate_stats=c_stats, market=a.market, tf=a.tf,
            method=method, symbols=symbols, account=account, calendar=calendar, sessions_=cand_sessions,
            trader_id=a.trader, dataset_snap=dataset_snap, cfg_snap=cfg_snap,
            validation_method=validation_method, store=a.store, at=None)
        results.append(dict(
            {"candidate_id": candidate_id, "clusters": entry["clusters"], "why": entry["why"],
             "override": entry["override"], "n": c_stats["n"],
             "expectancy": _num(c_stats), "pf": c_stats.get("pf"),
             "dd": bt.max_dd(c_curve), "failed_by": bt.SIM_LAST["failed_by"],
             "refused": dict(bt.SIM_LAST["refused"]), "experiment_id": sealed["experiment_id"],
             "record_path": repo_rel(path, ROOT)},
            **_ranking_keys(c_stats, bt.SIM_LAST)))

    # ---- 5. report
    md = _report(a, run_id, method, symbols, first, last, base_stats, base_curve, base_taken, clusters,
                results, no_candidate)
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        open(a.out, "w", encoding="utf-8").write(md)
        print(f"-> {a.out}")
    if a.json:
        json.dump({"run_id": run_id, "baseline": base_stats, "clusters": clusters, "candidates": results,
                  "no_candidate": [c["key"] for c in no_candidate]},
                 open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(f"-> {a.json}")


def _ranking_keys(stats, sim_last):
    """The §39 metrics `scripts/ranking.py` sorts on, copied UNCHANGED out of this candidate's perf block.

    Without these every objective except `expectancy` had nothing to read: ranking._num() returned None for
    every row, so `--objective prop_pass_rate` silently ranked by nothing. That matters here more than
    anywhere else -- "which candidate passes the challenge most often" is the question this loop exists to
    answer (user decision 2026-09-19). An `unavailable()` marker is carried through as-is: ranking._num()
    refuses to sort it as a number, which is the correct behaviour, and the report shows the reason.
    """
    perf = stats.get("perf") or {}
    out = {"ruin": sim_last.get("ruin")}
    for key in ("max_drawdown", "time_in_drawdown", "account_failure_probability", "prop_pass_probability",
                "sortino", "sharpe", "risk_of_ruin"):
        if key in perf:
            out[key] = perf[key]
    pp = perf.get("positive_period_share")
    if pp is not None:
        out["positive_period_share"] = pp
    wp = perf.get("worst_period")
    if wp is not None:
        out["worst_period"] = wp
    return out


def _num(stats):
    perf = stats.get("perf") or {}
    e = perf.get("expectancy")
    return e if isinstance(e, (int, float)) else None


def _report(a, run_id, method, symbols, first, last, base_stats, base_curve, base_taken, clusters, results,
           no_candidate):
    L = [f"# Vòng lặp cải tiến có kiểm soát — {method} {a.market} {a.tf} — {run_id}", "",
        f"_`scripts/improve-loop.py` -- CLAUDE.md §41 stages 1-4 (Trading Outcomes -> Failure Pattern -> "
        f"Hypothesis -> Candidate) + §42 (mỗi ứng viên là một experiment.Record niêm phong dưới "
        f"`docs/experiments/`). Không tự ý sửa pilot-selection.json / methods.json / trading-systems.json — "
        f"stage 11 (§41) là quyết định của con người, không phải của script này._", "",
        f"**Baseline** ({', '.join(symbols)}, {first[:10]} → {last[:10]}): n={base_stats['n']}, "
        f"expectancy={_num(base_stats)}, PF={base_stats.get('pf')}, "
        f"max DD={bt.max_dd(base_curve):.1f}%, failed_by={bt.SIM_LAST['failed_by'] or '—'}, "
        f"refused={bt.SIM_LAST['refused']}", "",
        CLUSTER_HEAD_VI,
        f"_min_size={clusters['min_size']} · nhóm theo {clusters['grouped_by']} · "
        f"{clusters['singletons']} nhóm dưới ngưỡng (không tính là cụm)._", ""]
    if not clusters["clusters"]:
        L.append("Không có cụm lỗi lặp lại nào đạt `min_size` trong baseline.")
    for c in clusters["clusters"]:
        L.append(f"- `{c['key']}` — n={c['n']}, states={c['states']}")
    L.append("")
    L.append("## Ứng viên đã chạy (xếp hạng theo `--objective`)")
    L.append("")
    ranked = RK.rank(results, objective_id=a.objective)["ranked"] if results else []
    if not ranked:
        L.append("Không có cụm nào khớp một ứng viên đã khai báo trong `docs/architecture/improve-candidates.json`.")
    for r in ranked:
        row = r["row"]
        if "error" in row:
            # A candidate whose override could not be applied (an OPTS key that no longer exists, say) is
            # recorded at line ~285 as {"candidate_id", "error"} and has none of the metric keys. Printing the
            # failure is the point -- the pre-2026-09-19 code indexed row["n"] straight away and the whole
            # report died with a KeyError, which hid WHICH candidate was broken behind a traceback.
            L.append(f"{r['rank']}. `{row['candidate_id']}` — KHÔNG CHẠY ĐƯỢC: {row['error']}")
            continue
        L.append(f"{r['rank']}. `{row['candidate_id']}` — n={row['n']}, expectancy={row['expectancy']}, "
                f"PF={row['pf']}, DD={row['dd']:.1f}%, failed_by={row['failed_by'] or '—'}, "
                f"refused={row['refused']} — record: `{row['record_path']}`")
        L.append(f"   - lý do: {row['why']}")
    L.append("")
    L.append("### Vượt trội hơn baseline (outperformers)")
    base_e = _num(base_stats)
    # `"error" not in row` first: a candidate that could not run has no metrics at all, and indexing its
    # row["n"] here is the same KeyError that used to kill the ranked list above (2026-09-19).
    outperf = [r for r in ranked if "error" not in r["row"] and r["row"]["n"] >= a.min_trades
              and base_e is not None
              and r["row"]["expectancy"] is not None and r["row"]["expectancy"] > base_e]
    if not outperf:
        L.append(f"Không có ứng viên nào vượt baseline trên `{a.objective}` với n ≥ {a.min_trades}.")
    for r in outperf:
        L.append(f"- `{r['row']['candidate_id']}` — record: `{r['row']['record_path']}`")
    L.append("")
    L.append(NO_CANDIDATE_HEAD_VI)
    if not no_candidate:
        L.append("Mọi cụm đều khớp ít nhất một ứng viên đã khai báo.")
    for c in no_candidate:
        L.append(f"- `{c['key']}` — n={c['n']}, states={c['states']} — không có ứng viên nào trong "
                f"`docs/architecture/improve-candidates.json` khớp bất kỳ trường nào của cụm này.")
    L.append("")
    L.append("---")
    L.append("**Con người quyết định (§41 stage 11).** Báo cáo này chỉ là bằng chứng: mọi bản ghi "
             "experiment ở trên đều `decision: PENDING`. Không ứng viên nào được tự động áp dụng; việc đưa "
             "một ứng viên vào `pilot-selection.json` / `methods.json` / `trading-systems.json` là một sửa đổi "
             "registry do một người thực hiện sau khi đọc báo cáo này, không phải hành động của "
             "`scripts/improve-loop.py`.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
