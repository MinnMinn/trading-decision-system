#!/usr/bin/env python3
"""Enable the pilot's systems by absolute per-horizon criteria and write the pilot's selection file (ADR 0008).

Usage: rank-setups.py [--crypto data/history/stability/crypto-*.json] [--cfd data/history/stability/cfd-*.json]
                      [--select docs/architecture/pilot-selection.json] [--out docs/backtests/<file>.md]
                      [--crypto-symbols ...] [--cfd-symbols ...] [--require-stamped]

There is ONE selection path (mode `criteria-oos6m`), decided by the owner on 2026-09-26
(docs/adr/0008-2026-09-26-criteria-based-selection-replaces-top-n.md):

  * a candidate is one stability row -- (market, timeframe, method, target/source file, configuration A/B/C) --
    whose timeframe is a pilot horizon (HORIZONS: scalping 15m, day 1H, swing 4H) and whose method is RUNNABLE;
  * it is ENABLED only if it passes EVERY criterion of its horizon in docs/architecture/selection-criteria.json
    (evaluated by scripts/selection_criteria.py, the file's one reader) on its IN-SAMPLE window AND on its
    held-out OOS window (stability-report.py's `oos6m` block, INT-5), and meets the data-sufficiency
    preconditions below;
  * every candidate that passes is enabled -- there is no ranking, no top-N cut-off, no one-per-slot winner, no
    coverage fallback and no runner-up substitution; a horizon with no passing candidate trades nothing, and the
    report and the selection file say so in words.

Data-sufficiency preconditions (kept from the decisions that preceded ADR 0008, which did not revoke them; both
can only DISABLE, never enable): each window must span at least MIN_WINDOW_DAYS (user decision 2026-09-13: a
result over less than three months is not evidence), and the in-sample window must hold at least
IS_MIN_TRADES[horizon] trades (the in-sample minimums round 4b used).

The selection file (single writer: this script) is read by scripts/strategy-runner.py every tick. CFD setups get
execution "mt5" (demo account through integrations/mt5/OrderBridge.mq5 + scripts/mt5-order-bridge.py), crypto
setups "futures" (Binance futures testnet). Every number here is a code proxy over research history.
"""
import argparse, datetime, glob, importlib.util, json, os
# Per-setup keys a rewrite must carry over. The ICT switch trio (ict_disp / ict_pd / std_origin) and the
# scripts/ict-flags-1y.py that tuned them were deleted 2026-09-19 (knowledge audit finding 11): none of the
# three could change an ICT setup, so a year of "decisions" about them measured noise. Nothing is carried now.
FLAG_KEYS = ()


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


def _global_rule_params(st):
    """The global detection parameters that apply to one setup (CLAUDE.md §14, scripts/setup_version.py).

    Resolved from backtest-methods' own state so the version tracks the numbers the rules actually ran with.
    RISK / START / RUIN_FRAC are deliberately absent: they size a position, they do not change which bars
    qualify, and folding them in would churn every version whenever the risk ceiling moved."""
    return {"min_rr": bt.MIN_RR, "stop_buffer_pct": bt.STOP_BUFFER_PCT,
            "displacement": dict(bt.DISP), "volume": dict(bt.VOL),
            "per_timeframe": dict(bt.P.get(st.get("tf"), {}))}


def finalize(selection, path):
    """Carry the deck-faithful switches, THEN stamp rule versions. One function so a write path cannot do the
    first half and forget the second -- which would ship setups a trade cannot be tied back to (§14)."""
    return SV.stamp(carry_flags(selection, path), _global_rule_params)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys as _sys; _sys.path.insert(0, os.path.join(ROOT, "scripts"))
import setup_version as SV      # CLAUDE.md §14: a setup carries the version of the rules it IS
import research_validity as RV  # CLAUDE.md §38: a selection may not be made from invalid research
import instruments as _I        # the ONE allowlist: a symbol set typed here would outlive the registry
import selection_criteria as SC  # ADR 0008: the ONE reader of docs/architecture/selection-criteria.json
_mspec = importlib.util.spec_from_file_location("methods", os.path.join(ROOT, "scripts", "methods.py"))
mreg = importlib.util.module_from_spec(_mspec); _mspec.loader.exec_module(mreg)
# backtest-methods holds the resolved detection parameters a setup's rule version is computed over
# (CLAUDE.md §14). Loaded the same way as `methods` above -- the filename has a dash, so it cannot be a
# plain import.
_btspec = importlib.util.spec_from_file_location("bt", os.path.join(ROOT, "scripts", "backtest-methods.py"))
bt = importlib.util.module_from_spec(_btspec); _btspec.loader.exec_module(bt)
RUNNABLE = mreg.runnable()   # executed by scripts/strategy-runner.py; source: docs/architecture/methods.json
# The three live rungs only (user decision 2026-09-13). Was a seven-rung superset that also named the retired
# five- and thirty-minute rungs, the two-hour rung and the daily -- harmless while it was a superset of the live
# set, which is exactly why it would have rotted unnoticed.
CFD_TFS = {"15m", "1H", "4H"}
# The horizon a timeframe belongs to (ADR 0008: scalping = 15m, day = 1H, swing = 4H). One timeframe per
# horizon (user decision 2026-09-13), matching automation.HORIZON_TF up to the 1h/1H spelling. The horizon
# names are the keys of selection-criteria.json `horizons`.
HORIZONS = {"scalping": "15m", "day": "1H", "swing": "4H"}
HORIZON_OF_TF = {tf: hz for hz, tf in HORIZONS.items()}
# The config table has ONE author: scripts/stability-report.py, which is what produced the rows being judged.
# This file used to keep its own copy with the fees written out -- 0.0005 / 0.0002 / 0.0002 -- and on
# 2026-09-18 that copy stamped `fee_assumed: 0.0002` onto two CFD setups whose MT5 account pays 0.0005 on both
# sides. A second copy of a domain rule is not a convenience, it is a second answer (CLAUDE.md §58); the fee
# now comes from the venue through `config_fee()`, the same call the rows were priced with.
_ss = importlib.util.spec_from_file_location("stability_report", f"{ROOT}/scripts/stability-report.py")
_SR = importlib.util.module_from_spec(_ss); _ss.loader.exec_module(_SR)
CFG_DESC = _SR.CONFIGS


def fee_assumed_for(cfg_name, market):
    """What the row was actually priced at, resolved through the venue -- never a literal here."""
    return _SR.config_fee(CFG_DESC[cfg_name], market)


UNSTAMPED = "UNSTAMPED"     # a stability file written before 2026-09-18, when §38 verdicts did not exist
SOURCE_VALIDITY = {}        # relpath -> the §38 block of each file this process read (for the written artifacts)
REFUSED = []                # (relpath, reason) for every file §38 would not let this selection use


def load_rows(paths, market, *, require_stamped=False):
    """Rows from stability-report JSON files, minus any file CLAUDE.md §38 says may not be selected from.

    This is the one place selection reads its input, so it is the one place the §38 gate belongs. "Never
    silently produce a trustworthy-looking performance result from invalid research" applies with particular
    force here: these rows do not end in a report, they end in the pilot's selection file, which is what the
    runner places orders from.

    Two verdicts are refused outright (`INVALID`, and anything not in the allow-list). `UNSTAMPED` -- a file
    written before the verdict existed -- is NOT silently trusted and NOT silently dropped: `research_validity.
    read()` raises, this call site catches, and the fact is carried onto every row, into the selection file and
    into the report. `--require-stamped` makes the strict behaviour available and should become the default
    once every stability file has been regenerated by a stamping `stability-report.py`.
    """
    rows = []
    for p in paths:
        d = json.load(open(p, encoding="utf-8"))
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")    # repo paths are POSIX in every written artifact
        try:
            block = RV.read(d, where=rel)
            # UNVERIFIED is allowed: it means nothing fired but some §38 conditions have no detector yet
            # (docs/architecture/research-validity.json says which and why). Every run today is in that state;
            # refusing it would refuse all research rather than the invalid kind.
            RV.require(block, where=rel, allow=(RV.VALID, RV.FLAGGED, RV.UNVERIFIED))
        except RV.Unstamped as exc:
            if require_stamped:
                REFUSED.append((rel, str(exc))); print(f"§38 REFUSED {rel}: unstamped", file=_sys.stderr); continue
            block = {"verdict": UNSTAMPED, "findings": [], "unchecked": list(RV.ORDER),
                     "_note": "written before scripts/research_validity.py existed; nothing was assessed"}
            print(f"§38 WARNING {rel}: no research-validity verdict (pre-2026-09-18 file). Rows from it are "
                  f"used but marked {UNSTAMPED}; re-run stability-report.py to assess it.", file=_sys.stderr)
        except RV.InvalidResearch as exc:
            REFUSED.append((rel, str(exc))); print(f"§38 REFUSED {exc}", file=_sys.stderr); continue
        SOURCE_VALIDITY[rel] = block
        target = os.path.basename(p).rsplit("-", 1)[1].rsplit(".", 1)[0]    # crypto-std25.json / crypto-scalp-std25.json -> std25
        for r in d["rows"]:
            rows.append(dict(r, market=market, target=(target if r["method"] == "ICT" else "border"),
                             file=rel, research_validity=block["verdict"]))
    return rows


def validity_note():
    """One line for the report, and the block the selection file carries. Never empty: a selection whose
    sources were all unassessed must say so as plainly as one whose sources were clean."""
    per = {rel: b["verdict"] for rel, b in SOURCE_VALIDITY.items()}
    # UNSTAMPED ranks ABOVE FLAGGED: a flagged run was assessed and its defects are named, while an unstamped
    # one is entirely unknown, and unknown is the worse thing to be selecting from.
    return {"per_source": per,
            "worst": RV.worst(per.values(), extra={UNSTAMPED: 3}) if per else UNSTAMPED,
            "refused": [{"source": s, "reason": w} for s, w in REFUSED],
            "source": "docs/architecture/research-validity.json (CLAUDE.md §38)"}


def validity_markdown():
    v = validity_note()
    bad = sorted({k for k, vv in v["per_source"].items() if vv not in (RV.VALID,)})
    line = f"_CLAUDE.md §38 — research validity of the sources: **{v['worst']}**._"
    if bad:
        line += " Sources not fully VALID: " + ", ".join(f"`{k}` ({v['per_source'][k]})" for k in bad) + "."
    if v["refused"]:
        line += " **Refused (not used for selection):** " + ", ".join(f"`{r['source']}`" for r in v["refused"]) + "."
    return line


# ---------------------------------------------------------------- data-sufficiency preconditions
MIN_WINDOW_DAYS = 90   # user decision 2026-09-13: under three months a window is no evidence either way
IS_MIN_TRADES = {"scalping": 20, "day": 15, "swing": 6}   # in-sample trade minimums (round 4b)
ENABLED, DISABLED = "ENABLED", "DISABLED"


def window_days(block):
    """Length of one IS/OOS window in days, or None when its dates are absent or unparseable."""
    try:
        return (datetime.date.fromisoformat(block["until"][:10]) - datetime.date.fromisoformat(block["since"][:10])).days
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def preconditions(r, horizon):
    """Reasons this row may not be enabled whatever its criteria say ([] = none). Fails closed: an absent block,
    unparseable dates or an absent trade count are reasons, never passes."""
    o = r.get("oos6m") or {}
    why = []
    for side, label in (("in_sample", "IS"), ("oos", "OOS")):
        b = o.get(side)
        if not isinstance(b, dict):
            why.append(f"precondition: no {label} window block (missing)"); continue
        d = window_days(b)
        if d is None:
            why.append(f"precondition: {label} window dates missing")
        elif d < MIN_WINDOW_DAYS:
            why.append(f"precondition: {label} window {d} days < {MIN_WINDOW_DAYS}")
    n = (o.get("in_sample") or {}).get("n") if isinstance(o.get("in_sample"), dict) else None
    mn = IS_MIN_TRADES[horizon]
    if not isinstance(n, int) or isinstance(n, bool):
        why.append("precondition: IS trade count missing")
    elif n < mn:
        why.append(f"precondition: IS n={n} < {mn} trades")
    return why


def require_oos_blocks(rows):
    """Every row must carry stability-report.py's `oos6m` block; a file written before INT-5 cannot be used."""
    missing = sorted({r["file"] for r in rows if not (r.get("oos6m") or {}).get("in_sample")})
    if missing:
        raise SystemExit("no in-sample/OOS split in " + ", ".join(missing) + " -- regenerate with the current "
                         "scripts/stability-report.py (it writes the `oos6m` block)")


def market_cutoff(rows, market):
    """The ONE cutoff every row of this market was split at. Candidates judged on different holdouts are not
    comparable, so a mixture is refused rather than resolved."""
    cuts = sorted({r["oos6m"]["cutoff"] for r in rows})
    if len(cuts) != 1:
        raise SystemExit(f"{market} rows were split at {len(cuts)} different cutoffs {cuts}; "
                         f"regenerate the {market} stability files from the same dataset")
    return cuts[0]


def _setup_id(market, hz, r):
    return f"{market}-{hz}-{r['method'].lower()}-{r['tf'].lower()}-{r['target']}-{r['cfg'].lower()}"


def candidacy(r, market):
    """(horizon, None) for a candidate, or (None, reason) for a row that is not one. Not a judgement of the row's
    numbers: only whether the pilot could run it at all."""
    if r.get("method") not in RUNNABLE:
        return None, f"method {r.get('method')} is not RUNNABLE (docs/architecture/methods.json)"
    hz = HORIZON_OF_TF.get(r.get("tf"))
    if hz is None:
        return None, f"timeframe {r.get('tf')} is not a pilot horizon ({', '.join(f'{h} {t}' for h, t in HORIZONS.items())})"
    if market == "cfd" and r["tf"] not in CFD_TFS:
        return None, f"timeframe {r['tf']} is not a live CFD rung"
    return hz, None


def judge(r, horizon, crit):
    """Pure. The decision for ONE candidate: every criterion on IS, every criterion on OOS, preconditions."""
    o = r.get("oos6m") or {}
    ev_is = SC.evaluate(o.get("in_sample"), horizon, crit)
    ev_oos = SC.evaluate(o.get("oos"), horizon, crit)
    reasons = preconditions(r, horizon)
    reasons += [f"IS {x}" for x in ev_is["failed"]] + [f"OOS {x}" for x in ev_oos["failed"]]
    passed = ev_is["passed"] and ev_oos["passed"] and not reasons
    return dict(decision=ENABLED if passed else DISABLED, reasons=reasons, in_sample=ev_is, oos=ev_oos)


def _same_numbers(a, b):
    return (a.get("oos6m") or {}).get("in_sample") == (b.get("oos6m") or {}).get("in_sample") and \
           (a.get("oos6m") or {}).get("oos") == (b.get("oos6m") or {}).get("oos")


def select_criteria(rows, market, crit):
    """Pure: the decision for every row of one market, and the experiment budget. Every candidate is judged on
    its own numbers only -- no row's decision depends on another row's (so no ranking, no substitution)."""
    hzs = list(HORIZONS)
    budget = dict(rows=len(rows), candidate_rows=0, not_candidates=0, duplicate_rows=0, passed_in_sample=0,
                  passed_oos=0, enabled=0, disabled=0,
                  by_horizon={hz: dict(candidates=0, enabled=0) for hz in hzs})
    judged, others, seen = [], [], {}
    for r in rows:
        hz, why_not = candidacy(r, market)
        if hz is None:
            budget["not_candidates"] += 1
            others.append(dict(row=r, reason=why_not)); continue
        sid = _setup_id(market, hz, r)
        if sid in seen:
            prev = seen[sid]
            if _same_numbers(prev["row"], r):
                budget["duplicate_rows"] += 1          # the same rule measured twice (e.g. a target-free method)
                continue
            # Same identity, different numbers: which one is the system? Unknown -- so neither is enabled.
            for j in (prev,):
                if j["decision"] == ENABLED:
                    j["decision"] = DISABLED; budget["enabled"] -= 1; budget["disabled"] += 1
                    budget["by_horizon"][hz]["enabled"] -= 1
                j["reasons"].append(f"conflicting duplicate rows for {sid} ({prev['row']['file']} vs {r['file']})")
            continue
        j = dict(judge(r, hz, crit), id=sid, horizon=hz, market=market, row=r)
        seen[sid] = j
        budget["candidate_rows"] += 1; budget["by_horizon"][hz]["candidates"] += 1
        budget["passed_in_sample"] += j["in_sample"]["passed"]
        budget["passed_oos"] += j["oos"]["passed"]
        if j["decision"] == ENABLED:
            budget["enabled"] += 1; budget["by_horizon"][hz]["enabled"] += 1
        else:
            budget["disabled"] += 1
        judged.append(j)
    return judged, others, budget


def _r(v, nd):
    return None if not isinstance(v, (int, float)) or isinstance(v, bool) else round(v, nd)


def _side(b):
    """The reported numbers of one IS/OOS block, rounded for the written artifacts (None where absent)."""
    b = b or {}
    months = b.get("months") if isinstance(b.get("months"), list) else []
    return dict(n=b.get("n"), expectancy_R=_r(b.get("expectancy_R"), 4), profit_factor=_r(b.get("profit_factor"), 3),
                net_pnl=_r(b.get("net_pnl"), 2), max_dd_pct=_r(b.get("dd"), 2), ann_pct=_r(b.get("ann"), 1),
                q_worst_pct=_r(b.get("q_worst"), 2), m_mean_geo_pct=_r(b.get("m_mean_geo"), 3),
                m_losing=b.get("m_losing"), m_worst_pct=_r(b.get("m_worst"), 3), months=len(months),
                partial_months=sum(1 for m in months if isinstance(m, dict) and m.get("partial")),
                ruin=b.get("ruin"), since=b.get("since"), until=b.get("until"))


def _checks(ev):
    return [dict(criterion=c["criterion"], value=_r(c["value"], 4), op=c["op"], threshold=c["threshold"],
                 passed=c["passed"], reason=c["reason"]) for c in ev["checks"]]


def _source_meta(paths):
    """Per stability file: when it was generated, from which data and code, and its split."""
    out = {}
    for p in sorted(paths):
        try:
            d = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ds = d.get("dataset_snapshot") or {}
        out[os.path.relpath(p, ROOT).replace(os.sep, "/")] = dict(
            generated=d.get("generated"), dataset_snapshot_id=ds.get("snapshot_id"),
            snapshot_error=ds.get("snapshot_error"), code_version=ds.get("code_version"),
            requested_but_absent=ds.get("requested_but_absent"), oos_holdout=d.get("oos_holdout"),
            run_params=d.get("run_params"), research_validity=(d.get("research_validity") or {}).get("verdict"))
    return out


def main():
    ap = argparse.ArgumentParser(description="ADR 0008 criteria-based selection of the pilot's systems")
    ap.add_argument("--crypto", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/crypto-*.json"))
    ap.add_argument("--cfd", nargs="*", default=glob.glob(f"{ROOT}/data/history/stability/cfd-*.json"))
    ap.add_argument("--out"); ap.add_argument("--select")
    ap.add_argument("--criteria", default=SC.PATH, help="selection-criteria.json (default: the one source)")
    # Defaults DERIVED, not typed. `--cfd-symbols` used to read "XAUUSD,XAGUSD,USOIL,UKOIL"; when USOIL/UKOIL
    # left the execution list on 2026-09-18 (no such symbol on the broker) that literal would have written them
    # straight back into the selection file on the next run, with nothing failing. The crypto default stays
    # the BACKTESTED subset rather than the execution list -- selection may only claim symbols that were
    # measured (instruments.json `backtested`), and that is a narrower set on purpose.
    ap.add_argument("--crypto-symbols", default=",".join(_I.backtested("crypto")))
    ap.add_argument("--cfd-symbols", default=",".join(_I.execution("cfd")))
    ap.add_argument("--require-stamped", action="store_true", help="CLAUDE.md §38: refuse stability files that carry no research-validity verdict (default: use them, marked UNSTAMPED)")
    a = ap.parse_args()
    return run(a, datetime.date.today().isoformat())


def run(a, today):
    try:
        crit = SC.load(a.criteria)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"selection criteria unusable, nothing selected: {exc}")
    import snapshot as _snap
    code = _snap.code_version()
    prev_exposure = {}
    if a.select and os.path.exists(a.select):
        try:
            with open(a.select, encoding="utf-8") as fh:
                prev_exposure = json.load(fh).get("oos_holdout") or {}
        except (OSError, ValueError):
            prev_exposure = {}
    crit_rel = os.path.relpath(os.path.abspath(a.criteria), ROOT).replace(os.sep, "/")
    selection = dict(generated=today, mode="criteria-oos6m",
                     note="Written by scripts/rank-setups.py (ADR 0008). A system is ENABLED only if it passes every "
                          "criterion of its horizon (selection-criteria.json) on its in-sample window AND its "
                          "held-out OOS window. Every passing system is enabled; there is no ranking, no top-N, no "
                          "per-slot winner and no fallback. A horizon listed in `horizons_without_system` trades "
                          "nothing. Crypto = Binance futures testnet, CFD = MT5 demo via the file order bridge.",
                     criteria=dict(source=crit_rel, version=crit.get("version"), decided=crit.get("decided"),
                                   window_months=crit.get("window_months"), horizons=crit["horizons"]),
                     preconditions=dict(min_window_days=MIN_WINDOW_DAYS, in_sample_min_trades=dict(IS_MIN_TRADES)),
                     setups=[], disabled=[], horizons_without_system=[], oos_holdout={}, experiment_budget={},
                     code_version=code)
    judged_all, others_all, totals, sources = [], [], {}, {}
    for market, paths, syms in (("crypto", a.crypto, a.crypto_symbols.split(",")), ("cfd", a.cfd, a.cfd_symbols.split(","))):
        rows = load_rows(sorted(paths), market, require_stamped=a.require_stamped)
        sources.update(_source_meta(paths))
        if not rows:
            selection["oos_holdout"][market] = dict(status="NO_DATA")
            selection["horizons_without_system"] += [dict(market=market, horizon=hz, reason="no stability rows")
                                                     for hz in HORIZONS]
            continue
        require_oos_blocks(rows)
        cutoff = market_cutoff(rows, market)
        last_bar = max(r["oos6m"]["dataset_last_bar"] for r in rows)
        judged, others, budget = select_criteria(rows, market, crit)
        for k, v in budget.items():
            if k != "by_horizon":
                totals[k] = totals.get(k, 0) + v
        selection["experiment_budget"][market] = budget
        uses = list(((prev_exposure.get(market) or {}).get("uses")) or [])
        prior_same = [u for u in uses if u.get("cutoff") == cutoff]
        uses.append(dict(date=today, cutoff=cutoff, by="rank-setups.py (criteria-oos6m)"))
        selection["oos_holdout"][market] = dict(
            cutoff=cutoff, dataset_last_bar=last_bar, oos_period=f"{cutoff[:10]} -> {last_bar[:10]}",
            in_sample_period=f"{rows[0]['oos6m']['in_sample'].get('since')} -> {cutoff[:10]}",
            status="EXPOSED",
            exposure=("this window has now decided which systems are enabled (CLAUDE.md §44): it is EXPOSED "
                      "and may not be called pristine/untouched validation data again"),
            times_used_for_selection=len(prior_same) + 1, uses=uses)
        for hz in HORIZONS:
            if not budget["by_horizon"][hz]["enabled"]:
                selection["horizons_without_system"].append(dict(
                    market=market, horizon=hz,
                    reason=f"0 of {budget['by_horizon'][hz]['candidates']} candidates met every criterion on "
                           f"in-sample and OOS -- this horizon trades nothing"))
        for j in judged:
            r = j["row"]
            cfg = CFG_DESC[r["cfg"]]
            ins, oos = _side(r["oos6m"].get("in_sample")), _side(r["oos6m"].get("oos"))
            entry = dict(id=j["id"], horizon=j["horizon"], market=market, symbols=syms, tf=r["tf"], method=r["method"],
                         htf=cfg["htf"], mgmt=cfg["mgmt"], fee_assumed=fee_assumed_for(r["cfg"], market),
                         execution="futures" if market == "crypto" else "mt5",
                         backtest=dict(window="oos6m", cutoff=cutoff, source=r["file"], in_sample=ins, oos=oos,
                                       full_n=r.get("n"), full_ann_pct=_r(r.get("ann"), 1),
                                       period=f"{r.get('first')}→{r.get('last')}"),
                         criteria_result=dict(in_sample=_checks(j["in_sample"]), oos=_checks(j["oos"]),
                                              reported_target=[dict(criterion=c["criterion"], value=_r(c["value"], 4),
                                                                    threshold=c["threshold"], met=c["passed"])
                                                               for c in j["in_sample"]["reported"] + j["oos"]["reported"]]),
                         decision=j["decision"], reasons=j["reasons"])
            (selection["setups"] if j["decision"] == ENABLED else selection["disabled"]).append(entry)
        judged_all += judged; others_all += [dict(o, market=market) for o in others]
    selection["experiment_budget"]["total"] = totals
    selection["experiment_budget"]["_note"] = (
        "CLAUDE.md §43. candidate_rows = every (timeframe, method, configuration, source file) row at a pilot "
        "horizon with a RUNNABLE method; each was judged on in-sample AND on OOS, so the OOS window adjudicated "
        "among all of them. passed_in_sample / passed_oos count each side independently; enabled needs both plus "
        "the preconditions. duplicate_rows = identical re-measurements of one system (counted once).")
    selection["sources"] = sources
    selection["research_validity"] = validity_note()
    md = criteria_markdown(selection, judged_all, others_all, today)
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(md)
    if a.select:
        selection = finalize(selection, a.select)
        # §47: disabled candidates stay traceable -- versioned exactly like the enabled ones.
        SV.stamp({"setups": selection["disabled"]}, _global_rule_params)
        with open(a.select, "w", encoding="utf-8") as fh:
            json.dump(selection, fh, indent=1, ensure_ascii=False)
        print(f"-> {a.select} ({len(selection['setups'])} enabled, {len(selection['disabled'])} disabled, "
              f"{len(selection['horizons_without_system'])} horizon(s) with no system)")
    return selection


def _fmt(v, f):
    return "n/a" if v is None else format(v, f)


def _cell(c):
    """One criterion cell: value, threshold and verdict -- the reader sees why, not just whether."""
    mark = "✓" if c["passed"] else "✗"
    val = "missing" if c["value"] is None else format(c["value"], ".2f")
    return f"{val} {c['op']} {c['threshold']:g} {mark}"


def criteria_markdown(selection, judged, others, today):
    code = selection.get("code_version") or {}
    crit = selection["criteria"]
    L = [f"# Pilot selection by criteria (ADR 0008) — {today}", "",
         "_`scripts/rank-setups.py` (mode `criteria-oos6m`). A system is **ENABLED only if it passes every criterion "
         "of its horizon on its in-sample window AND on its held-out OOS window** "
         f"(`{crit['source']}` v{crit.get('version')}, decided {crit.get('decided')}). Every system that passes is "
         "enabled; there is no ranking, no top-N, no per-slot winner, no coverage fallback and no runner-up "
         "substitution. A horizon with no passing system trades nothing. Returns are account-level, net of "
         "costs, live-parity 1 % sizing; each side of the split is its own fresh $10,000 account. Trades belong to "
         "a window by ENTRY time. Every number is a code proxy over research history._", "",
         "## Criteria", "", "| Horizon | Criterion | Threshold | Gates? |", "|---|---|---|---|"]
    for hz, spec in crit["horizons"].items():
        for k, v in spec.items():
            if k.startswith("_"):
                continue
            gates = "no — reported only" if k in SC.REPORTED_ONLY else "yes"
            L.append(f"| {hz} | {k} | {v:g} | {gates} |")
    pre = selection["preconditions"]
    L += ["", f"Data-sufficiency preconditions (can only disable): each window ≥ {pre['min_window_days']} days; "
          "in-sample trades ≥ " + ", ".join(f"{h} {n}" for h, n in pre["in_sample_min_trades"].items()) + ". "
          "A missing input fails its criterion (reason `missing`); it is never read as a pass.", "",
          "## Holdout", ""]
    for m, h in selection["oos_holdout"].items():
        if h.get("status") == "NO_DATA":
            L.append(f"- **{m}**: no stability rows"); continue
        L.append(f"- **{m}**: cutoff **{h['cutoff']}** (dataset last bar {h['dataset_last_bar']} − 6 calendar "
                 f"months, derived from the data); in-sample {h['in_sample_period']}; OOS {h['oos_period']}.")
    L += ["", "**The OOS period is now EXPOSED** (CLAUDE.md §44): it has decided which systems are enabled, so it "
          "may not later be described as pristine or untouched validation data. "
          + " ".join(f"{m}: used for selection {h.get('times_used_for_selection', '?')} time(s) at this cutoff."
                     for m, h in selection["oos_holdout"].items() if h.get("cutoff")), "",
          "## Provenance", "",
          f"- Code version (this run): `{code.get('git_sha')}`" + (f" — dirty: {code.get('dirty_note')}" if code.get("dirty") else ""),
          "- Stability sources (dataset snapshot id · generated · stability-report code SHA · §38 verdict):"]
    for rel, s in selection.get("sources", {}).items():
        cv = s.get("code_version") or {}
        L.append(f"  - `{rel}` · snapshot `{s.get('dataset_snapshot_id') or s.get('snapshot_error')}` · {s.get('generated')} · "
                 f"`{(cv.get('git_sha') or '?')[:12]}`{' (dirty)' if cv.get('dirty') else ''} · {s.get('research_validity')}"
                 + (f" · absent series: {', '.join(s['requested_but_absent'])}" if s.get("requested_but_absent") else ""))
    L += ["", "## Experiment budget (CLAUDE.md §43)", "",
          "| Market | Rows | Candidates | Not candidates | Duplicates | Passed IS | Passed OOS | Enabled | Disabled |",
          "|---|---|---|---|---|---|---|---|---|"]
    for m, b in selection["experiment_budget"].items():
        if m.startswith("_") or m == "total":
            continue
        L.append(f"| {m} | {b['rows']} | {b['candidate_rows']} | {b['not_candidates']} | {b['duplicate_rows']} | "
                 f"{b['passed_in_sample']} | {b['passed_oos']} | {b['enabled']} | {b['disabled']} |")
    L += ["", "_" + selection["experiment_budget"]["_note"] + "_"]
    for market in ("crypto", "cfd"):
        for hz, tf in HORIZONS.items():
            spec = crit["horizons"].get(hz, {})
            gates = [k for k in SC.GATES if k in spec]
            target = [k for k in SC.REPORTED_ONLY if k in spec]
            rows = [j for j in judged if j["market"] == market and j["horizon"] == hz]
            n_en = sum(1 for j in rows if j["decision"] == ENABLED)
            L += ["", f"## {market} · {hz} ({tf}) — {n_en} of {len(rows)} enabled", ""]
            if not n_en:
                L.append(f"**{market} {hz}: 0 systems enabled — this horizon trades nothing.**"); L.append("")
            if not rows:
                L.append("_No candidate rows at this horizon._"); continue
            head = ["System (method · target · cfg · file)", "IS n"] + [f"IS {k}" for k in gates] + \
                   ["OOS n"] + [f"OOS {k}" for k in gates] + \
                   [f"{k} (IS / OOS, not gating)" for k in target] + ["Decision", "Reasons"]
            L += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
            for j in rows:
                r = j["row"]; o = r.get("oos6m") or {}
                cells = [f"{r['method']} · {r['target']} · {r['cfg']} (`{r['file'].rsplit('/', 1)[-1]}`)",
                         str((o.get("in_sample") or {}).get("n", "missing"))]
                cells += [_cell(c) for c in j["in_sample"]["checks"]]
                cells += [str((o.get("oos") or {}).get("n", "missing"))]
                cells += [_cell(c) for c in j["oos"]["checks"]]
                for k in target:
                    ti = next((c for c in j["in_sample"]["reported"] if c["criterion"] == k), None)
                    to = next((c for c in j["oos"]["reported"] if c["criterion"] == k), None)
                    cells.append(f"{_fmt(ti and ti['value'], '.2f')} / {_fmt(to and to['value'], '.2f')} vs {spec[k]:g}")
                cells += ["**ENABLED**" if j["decision"] == ENABLED else "DISABLED",
                          "; ".join(j["reasons"]) or "every criterion met on IS and OOS"]
                L.append("| " + " | ".join(cells) + " |")
    L += ["", "## Summary", ""]
    en = [x["id"] for x in selection["setups"]]
    L.append(f"**Enabled ({len(en)}):** " + (", ".join(f"`{x}`" for x in en) if en else "none — the pilot trades nothing"))
    for h in selection["horizons_without_system"]:
        L.append(f"- **{h['market']} {h['horizon']}: no system enabled** — {h['reason']}")
    if others:
        L += ["", f"_Rows that are not candidates ({len(others)}), with why:_ "
              + "; ".join(f"{o['market']} {o['row'].get('tf')} {o['row'].get('method')} {o['row'].get('cfg')}: {o['reason']}"
                          for o in others)]
    L += ["", "_Limitations: each side is a fresh account, so a position opened in-sample does not block an OOS entry "
          "on the same symbol. The in-sample window is the 365 days before the cutoff, so its losing-month count and "
          "drawdown are measured over twelve months against thresholds the owner stated for six — the stricter "
          "reading. The first and last calendar months of a window are partial and still counted. Several enabled "
          "systems may trade the same account at once; the account-level limits (account-profiles.json) remain the "
          "binding portfolio constraint. The §38 flags of the source files apply to both sides._", "",
          validity_markdown()]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
