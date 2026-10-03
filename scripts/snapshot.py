"""Dataset snapshots for research runs (CLAUDE.md §10): what data a result was computed from.

    import snapshot
    snap = snapshot.dataset_snapshot([("BTCUSDT", "15m"), ("ETHUSDT", "15m")], base="data/history")
    snap["code_version"]   -> {"git_sha": "b894e7e...", "dirty": True, "dirty_note": "..."}
    snap["series"][0]      -> provider, canonical_symbol, market_type, bars, first/last, sha256, ...

Why this exists: before it, a research run recorded a DATE and nothing else. `data/history/stability/
crypto-live.json` carried exactly one top-level key, `generated`, above sixty rows of metrics -- no provider,
no symbol list, no timeframe set, no input files, no code version. So "re-run this and see if it still holds"
had no defined meaning, and the 3%-vs-1% risk-ceiling drift (SYSTEM-DESIGN.md §9.y) was expensive to reason
about afterwards precisely because no result said which ceiling produced it.

**§10 is about the DATA. §11 is about the CONFIGURATION.** They are deliberately separate modules and
separate blocks in a run record: the same parameters over different candles, and the same candles under
different parameters, are both "a different experiment", and a single merged blob makes it impossible to say
which one changed. This module answers *what was read*; §11's will answer *how it was set up*.

**Content hashes, not just paths.** §10 asks for a "data version". A path is not a version -- the crypto
fetcher overwrites `ohlcv.<SYM>.<TF>.json` in place on every scanner run, so a result citing a path cites a
file that has since changed. The sha256 of the bytes actually read is the only version this repo can honestly
produce, because no feed here is immutable or versioned upstream.

**A dirty tree is recorded as dirty.** `git_sha` alone would claim reproducibility a modified working tree
cannot deliver. `dirty: true` plus the count of modified files is the honest answer, and
`scripts/tests/test_snapshot.py` asserts the flag is present rather than that it is false -- this repo's own
tree is usually dirty mid-change, and a test demanding cleanliness would just get disabled.
"""
import datetime
import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import account_profile as _AP
import instruments as I
import normalized as N
import providers as P
import trading_system as _TS   # CLAUDE.md §35: which dependencies the system declares REQUIRED_FOR_DECISION
import history_store as _HS    # shared reader/digest (single-file or split-gz), CLAUDE.md §58
import real_costs as _RC       # A0 (plan §2 2026-09-28): cost_profile name + its source files' sha256

SNAPSHOT_FORMAT = 1


def code_version():
    """Which code produced this, and whether that answer is trustworthy.

    Returns `git_sha: None` rather than guessing when git is unavailable -- an invented sha is worse than an
    absent one, because it reads as a resolvable commit (rules/reduce-hallucinations.md)."""
    def git(*args):
        try:
            out = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True, timeout=10)
            return out.stdout.strip() if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    sha = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    dirty_files = [l for l in (status or "").splitlines() if l.strip()]
    out = {"git_sha": sha, "dirty": bool(dirty_files), "modified_files": len(dirty_files)}
    if dirty_files:
        out["dirty_note"] = (f"{len(dirty_files)} uncommitted file(s) at snapshot time: this run is NOT "
                             f"reproducible from {sha or 'the recorded sha'} alone (CLAUDE.md §46).")
    return out


def file_digest(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def series_snapshot(symbol, timeframe, base=None):
    """One input series' identity: its provenance (§7) plus a content hash and its measured extent.

    Deliberately built on normalized.load() rather than re-reading the file: the provider, source venue,
    market type, canonical symbol and aggregation scope are exactly §7's provenance fields, and computing
    them a second way here would be a second answer to the same question.

    `sha256`/`split_parts` go through `history_store.digest()`/`history_store.part_digests()` rather than
    `file_digest(path)` directly (code review, 2026-09-29): `path` may now be a split-gz DIRECTORY, and
    `file_digest()` opening a directory in binary mode is an `IsADirectoryError`, not a wrong answer -- but a
    wrong answer would have been worse. For a plain-file series `history_store.digest()` is byte-identical to
    `file_digest(path)`, so no existing snapshot's recorded sha256 changes."""
    path, shape = N.resolve_path(symbol, timeframe, base)
    s = N.load(symbol, timeframe, base=base)
    prov, scope = s["provenance"], s["provenance"]["data_scope"]
    return {
        "symbol": symbol,
        "canonical_symbol": prov["canonical_symbol"],
        "market": prov["market"],
        "market_type": prov["market_type"],
        "timeframe": timeframe,
        "provider": prov["provider"],
        "source_venue": prov["source_venue"],
        "aggregation_scope": prov["aggregation_scope"],
        "underlying_venues": prov["underlying_venues"],
        "source_identifier": prov["source_identifier"],
        "retrieval_state": prov["quality"],          # §10 "retrieval state": AVAILABLE / STALE / MOCK / ...
        "received_time": prov["received_time"],
        "bars": scope["bars"],
        "first_open": scope["first_open"],
        "last_open": scope["last_open"],
        "sha256": _HS.digest(symbol, timeframe, root=base) if base else file_digest(path),
        # Per-part breakdown for a split-gz series (one gz-year part per entry), else None -- §10
        # reproducibility: `sha256` proves the WHOLE series is unchanged, but naming which YEAR a later
        # discrepancy would live in needs the parts. None (not omitted) for a plain-file series, so a reader
        # can tell "this series has one part, itself" from "this field was never computed".
        "split_parts": _HS.part_digests(symbol, timeframe, root=base) if base else None,
        # §10 "data version"/reproducibility: WHICH root these bytes were read from -- data/history vs a
        # second provider's data/history/ftmo are different datasets for the same (symbol, timeframe), and a
        # snapshot that does not name the root cannot be told apart from one that silently used the wrong one
        # (code review, 2026-09-29: this is exactly the bug that motivated this module's split-shape support).
        "history_root": repo_rel(base, ROOT) if base else None,
    }


def dataset_snapshot(series, base=None, now=None):
    """The snapshot for a research run reading `series` -- a list of (symbol, timeframe) pairs.

    `snapshot_id` is a digest of the inputs' own digests, so two runs over identical data share an id and a
    run over changed data cannot silently claim the earlier one's identity."""
    rows = [series_snapshot(sym, tf, base=base) for sym, tf in series]
    ident = hashlib.sha256("|".join(sorted(f"{r['symbol']}:{r['timeframe']}:{r['sha256']}" for r in rows))
                           .encode()).hexdigest()[:16]
    stamp = (now or datetime.datetime.now(datetime.timezone.utc)).isoformat().replace("+00:00", "Z")
    return {
        "snapshot_format": SNAPSHOT_FORMAT,
        "snapshot_id": ident,
        "created_at": stamp,
        "code_version": code_version(),
        "preprocessing_version": N.SNAPSHOT_INPUTS_VERSION,
        "history_root": repo_rel(base, ROOT) if base else None,
        "series": rows,
        "_note": ("CLAUDE.md §10. Identity of the DATA a result was computed from; the CONFIGURATION that "
                  "produced it is a separate block (§11). `sha256` is the version -- paths are overwritten "
                  "in place by the fetcher, so a path alone does not identify bytes."),
    }


# ------------------------------------------------------------------ configuration snapshot (CLAUDE.md §11)
#
# §11's own list, snake_cased. Every record carries an entry for EACH of these, because §11's "include where
# applicable" is an instruction about relevance, not a licence to omit silently: a field with no artifact must
# say so and name the section that owns it. A record that simply lacks `account_profile` is indistinguishable
# from one where the account profile was empty, and those are different facts.
CONFIG_FIELDS = (
    "trading_system_version",
    "methodology",
    "methodology_mode",
    "setup",
    "entry_rules",
    "exit_rules",
    "session",
    "required_evidence",
    "required_analytics",
    "risk_model",
    "account_profile",
    "news_rules",
    "custom_constraints",
    "provider_selection",
    "execution_assumptions",
    "parameters",
)


def unavailable(reason, owner):
    """A config field this system cannot yet capture, with the section that owns closing it.

    Distinct from `not_applicable()`: "we have no account-profile object" and "a mechanical-rule backtest has
    no methodology mode" are different statements, and flattening both to a missing key would lose which one
    is a gap and which is a category error."""
    return {"unavailable": reason, "owner": owner}


def not_applicable(reason):
    return {"not_applicable": reason}


def config_snapshot(*, fields, dataset_snapshot_id=None):
    """The configuration state behind a result (CLAUDE.md §11), as a complete record over CONFIG_FIELDS.

    Separate from the dataset snapshot on purpose (§10 vs §11): the same parameters over different candles,
    and the same candles under different parameters, are both "a different experiment", and one merged blob
    cannot say which changed. `dataset_snapshot_id` is the link between the two halves.

    Raises on an unknown or missing field rather than accepting a partial record -- the whole value of this
    block is that a reader can trust the absence of a value to mean something specific.
    """
    unknown = [k for k in fields if k not in CONFIG_FIELDS]
    if unknown:
        raise ValueError(f"unknown config field(s) {unknown}; CLAUDE.md §11 lists {list(CONFIG_FIELDS)}")
    missing = [k for k in CONFIG_FIELDS if k not in fields]
    if missing:
        raise ValueError(f"config snapshot is incomplete: {missing}. Every §11 field needs an entry -- a value, "
                         f"snapshot.unavailable(reason, owner), or snapshot.not_applicable(reason). An absent "
                         f"key cannot be told apart from an empty value.")
    return {"config_format": SNAPSHOT_FORMAT,
            "dataset_snapshot_id": dataset_snapshot_id,
            "fields": dict(fields),
            "_note": ("CLAUDE.md §11. The CONFIGURATION behind a result; the DATA is a separate block (§10), "
                      "linked by dataset_snapshot_id. Values read from mutable files are captured here BY "
                      "VALUE, so a later edit to risk-config.json or analysis-params.json cannot silently "
                      "change what a recorded result says it measured.")}


def _trading_systems(market, timeframes):
    """The §35 Trading Systems a backtest over these (market, timeframe) pairs is measuring.

    Returns (systems, error). `error` is a string when the pairs cannot be resolved -- an unknown market, or a
    timeframe no style covers. A backtest whose Trading System cannot be named is not a failure of the run, but
    it must not be reported as though the system were known, so the caller records the reason instead.
    """
    if not market:
        return {}, "no market supplied, so no Trading System can be named (§35)"
    out, unresolved = {}, []
    for tf in timeframes:
        try:
            out[tf] = _TS.for_market_tf(market, tf)["id"]
        except KeyError:
            unresolved.append(tf)
    if unresolved:
        return out, (f"no Trading System covers {market} at {', '.join(unresolved)} -- "
                     f"scripts/automation.py STYLE has no (market, timeframe) entry for it")
    return out, None


def backtest_config_snapshot(bt, *, timeframes, methods, configs=None, fee_pct=None,
                             ict_target=None, dataset_snapshot_id=None, market=None,
                             calendar=None, sessions=None, account=None, cost_profile=None):
    """A §11 record for a `scripts/backtest-methods.py`-driven run, built from its RESOLVED state.

    Captured by value, which is the point. `bt.RISK` and `bt.MIN_RR` are read at import from
    docs/architecture/risk-config.json and docs/architecture/analysis-params.json -- mutable files -- so a
    re-run after an edit measures a different system while the old report still claims the old numbers. That
    is not hypothetical: the risk ceiling moved 3 % -> 1 % on 2026-09-17 and every report produced before it
    was silently modelling a different account (`scripts/backtest-methods.py:59` (`RISK = _te.MAX_RISK_PCT`)).
    """
    opts = dict(bt.OPTS)
    # `bt.OPTS` is a MODULE-LEVEL dict that callers mutate per configuration -- stability-report.py does
    # `bt.OPTS.update(...)` once per (timeframe, config) inside its loop. So what is readable at the end of a
    # run is the RESIDUAL state of the last configuration, not "the run's settings". Reporting it as the
    # latter would be a snapshot that lies in the most plausible way possible, so every field built from
    # `opts` carries `varied_per_config` and points at the matrix that actually applied.
    varied = bool(configs) and len(configs) > 1
    residual = ("value is the RESIDUAL state after the last configuration in the run; the configurations "
                "actually evaluated are in setup.configs" if varied else None)
    systems, ts_error = _trading_systems(market, timeframes)
    # §35's classification, resolved for a MECHANICAL backtest: `engaged=()` because a rule-family backtest
    # engages no discretionary Confluence dimension (that is why `methodology_mode` below is not-applicable),
    # and `setup=None` because the run varies htf/method per configuration -- with no single setup row the
    # conditional dependencies resolve REQUIRED, which is the fail-closed direction.
    ts_required = {tf: list(_TS.required(sid, setup=None, engaged=())) for tf, sid in systems.items()}
    ts_kinds = {d: _TS.DEPENDENCIES[d]["kind"] for d in _TS.DEPENDENCIES}
    def _req(tf_map, kinds):
        return {tf: [d for d in req if ts_kinds[d] in kinds] for tf, req in tf_map.items()}
    # What the system declares required but this ENGINE never consults. Recorded rather than smoothed over:
    # §38 names "incomplete required inputs" as grounds to flag a research run, and it cannot flag what no
    # record mentions. The list is derived from the engine's own declared absences in this same snapshot
    # (news_rules / session below), not guessed.
    #   event_risk.calendar   -- `news_rules` below: the engine reads no news or calendar at all
    #   account.profile_rules -- `account_profile` below: only the risk fraction and ruin threshold apply,
    #                            not the account's entry gates
    #   venue.reconciliation  -- there is no venue in a backtest
    # `account.equity` is deliberately NOT in this list: the engine models it as bt.START, which is a modelled
    # value rather than an absent one.
    # A3/A4 (2026-09-18): a calendar/account is no longer NECESSARILY absent -- when `--calendar` is supplied
    # `event_risk.calendar` really is consulted (backtest-methods.simulate()'s admission-time refusal), so it
    # must not still be reported as unconsulted. `account.profile_rules` stays in the set regardless of
    # `account`: even WITH one, the engine applies only its survival rules and news/session restrictions, not
    # its full entry gates (position cap, per-symbol daily cap, overnight/weekend) -- see account_constraints
    # step 5 in decision-order.json.
    _maybe_applied = {"event_risk.calendar", "account.profile_rules", "venue.reconciliation"}
    if calendar is not None:
        _maybe_applied.discard("event_risk.calendar")
    not_applied = sorted({d for req in ts_required.values() for d in req} & _maybe_applied)
    return config_snapshot(dataset_snapshot_id=dataset_snapshot_id, fields={
        "trading_system_version": ({"systems": systems,
                                    "versions": {tf: _TS.get(sid)["version"] for tf, sid in systems.items()},
                                    "source": "docs/architecture/trading-systems.json"}
                                   if systems and not ts_error
                                   else unavailable(ts_error or "no Trading System resolved", "§35, §47")),
        "methodology": {"runner_methods": sorted(methods), "note":
                        "mechanical rule families (scripts/wyckoff_rules.py / the ICT scanner), NOT the "
                        "discretionary Confluence dimensions of the same name -- methods.json `_runner_note`"},
        "methodology_mode": not_applicable(
            "modes (NORMAL/ENHANCED/STRICT/SOLO) gate the /analyze Confluence path; a mechanical-rule "
            "backtest engages no dimensions and has no mode (§16)"),
        "setup": {"timeframes": list(timeframes), "configs": configs or {},
                  "ict_target": ict_target,
                  "ict_target_effective": (
                      "scripts/ict-scan.py setup_candidate() ignores this label entirely and always targets "
                      "the -2sigma projection first (models.md §2.1.5), falling back to the dealing-range edge "
                      "(core-a.md R13) only when no projection exists on the trade's side. `ict_target` is kept "
                      "here as a system-naming label ONLY (scripts/rank-setups.py reads it to name a system) "
                      "-- it does not, and never did, select among std2/std25/std4/erl_next/irl target models; "
                      "that switch was deleted from the engine 2026-09-13 (scripts/strategy-runner.py:22). "
                      "A0b erratum: docs/experiments/prop-search-2026-09-27/ERRATUM-2026-09-28.md "
                      "(docs/plans/2026-09-28-methodology-improvement-plan.md §A0b)."
                  ) if ict_target is not None else None},
        "entry_rules": {"entry": opts.get("entry"), "combined_entry": opts.get("combined_entry"),
                        "sides": list(opts.get("sides") or ()), "varied_per_config": residual},
        "exit_rules": {"mgmt": opts.get("mgmt"), "varied_per_config": residual,
                       "horizon_and_time_stop_bars": {tf: {"H": bt.P[tf]["H"], "T": bt.P[tf]["T"]}
                                                      for tf in timeframes if tf in bt.P}},
        "session": ({"allowed_sessions": sorted(sessions), "action": "admission-time refusal in simulate() "
                    "(--sessions, §0.3)"} if sessions else not_applicable(
            "the backtest applies no session/killzone filter: the ICT sources give no killzone rule for "
            "crypto or commodity CFDs (scripts/backtest-methods.py:27, knowledge/ict/core-a.md §6), and no "
            "--sessions flag was supplied for this run")),
        "required_evidence": ({"per_timeframe": _req(ts_required, {"data", "event_risk", "account", "risk",
                                                                   "execution", "methodology"}),
                               "declared_but_not_applied_by_this_engine": not_applied,
                               "source": "docs/architecture/trading-systems.json (§35)"}
                              if systems and not ts_error
                              else unavailable(ts_error or "no Trading System resolved", "§35")),
        "required_analytics": ({"per_timeframe": _req(ts_required, {"analytics"}),
                                "source": "docs/architecture/trading-systems.json (§35)"}
                               if systems and not ts_error
                               else unavailable(ts_error or "no Trading System resolved", "§35")),
        "risk_model": {"risk_pct_of_equity": bt.RISK,
                       "risk_source": "docs/architecture/risk-config.json max_risk_pct via trading_env",
                       "min_planned_rr": bt.MIN_RR,
                       "min_rr_source": "docs/architecture/analysis-params.json project_defined.ict.min_rr",
                       "account_start_usd": bt.START, "ruin_fraction": bt.RUIN_FRAC},
        # §33 + §11: WHICH account's rules were in force. A backtest run under a 15 % drawdown limit is not
        # comparable to one run under 5 %, so the rules are recorded rather than assumed. `account` is the
        # profile this specific run passed via --account/--account-file (A3); without one the backtest is not
        # tied to a venue, so it falls back to recording the profile the crypto pilot trades under.
        "account_profile": (
            # --account-file (§57) is deliberately NOT validated by account_profile._validate -- it is an ad
            # hoc "what would this look like" question, not configuration this repo ships -- so it is
            # reported by VALUE here rather than through _AP.snapshot(), which assumes the full registry shape
            # (derived max_positions etc.) a hand-written file is not obliged to declare.
            dict({"profile_id": account.get("id"), "context_type": account.get("context_type"),
                 "venue": account.get("venue"), "environment": account.get("environment"),
                 "rules": {k: v for k, v in (account.get("rules") or {}).items() if not str(k).startswith("_")},
                 "source": "docs/architecture/account-profiles.json" if account.get("id") in _AP.PROFILES
                           else "--account-file (ad hoc, not registry-validated, §57)"},
                note="the account THIS RUN measured against (--account/--account-file); the engine applies "
                     "its survival rules and news/session restrictions, not its full entry gates (see "
                     "required_evidence.declared_but_not_applied_by_this_engine)")
            if account else
            dict(_AP.snapshot(_AP.for_venue("futures")), note=(
            "no --account was supplied for this run; recorded for reference is the account the pilot trades "
            "this research under -- the backtest engine itself applies only the risk fraction and the ruin "
            "threshold (see risk_model), not any account's entry gates"))),
        "news_rules": ({"calendar_snapshot_id": (calendar.get("snapshot") or {}).get("id"),
                       "policy": calendar.get("policy") or {},
                       "tightened_by_account": bool(account and _AP.rule(account, "news_restrictions")),
                       "action": "admission-time refusal in simulate() (--calendar, §0.3)"}
                      if calendar else not_applicable(
            "the backtest reads no news or calendar at all, so no news rule was in force (§24-§32); note "
            "this means its results contain no event-risk filtering whatsoever")),
        # `range_touches` used to be captured here too (A0b, 2026-09-28): it was never a real scan()/simulate()
        # read at ANY value (docs/experiments/prop-search-2026-09-27/ERRATUM-2026-09-28.md), so recording it
        # was the same false-liveness defect as `ict_target` below -- except nothing names a system by it, so
        # it is dropped outright rather than kept-and-disclosed.
        # B1/Batch-1a (docs/plans/2026-09-29-execution-plan.md "Shared contract", rule 3: "every key is ...
        # recorded by the config snapshot"): the ICT fx_ keys (scripts/backtest-methods.py FX_ICT_KEYS) are
        # folded into custom_constraints, the existing bucket for every other OPTS overlay knob, rather than a
        # new CONFIG_FIELDS entry -- CONFIG_FIELDS is §11's closed, exact-match registry (config_snapshot()
        # raises on an unknown field), not an open extension point. Each key's own source is knowledge/ict/*.md
        # -- see docs/plans/2026-09-28-methodology-improvement-plan.md §3 for the item-by-item citation table.
        "custom_constraints": dict({k: opts.get(k, getattr(bt, "_OPTS_BASE", {}).get(k)
                                                if k in getattr(bt, "FX_ICT_V_KEYS", ()) else None) for k in
                                    ("types", "htf", "sloped_gate", "st_min", "phase_d",
                                     # Batch 1(b) F items (docs/plans/2026-09-28-methodology-improvement-plan.md
                                     # §3; shared fx_ contract, docs/plans/2026-09-29-execution-plan.md): read
                                     # on the scan/simulate path (backtest-methods._wyckoff_candidates callers /
                                     # _fires_from) and default to v1 (False) -- the live/pilot path never sets
                                     # them, so a residual snapshot never claims one was applied that was not.
                                     "fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring",
                                     "fx_w5_vp_abandon", "fx_w7_htf_target",
                                     # O1 (2026-09-30): simulate()'s min_rr admission cost basis; default v1.
                                     "fx_admission_entry_cost",
                                     # C3 (2026-10-02): walk()'s stop-fill rule on a gap; default v1.
                                     "fx_gap_fill",
                                     # D3 (2026-10-02): ICT fill-scan start after the FVG's third candle; default v1.
                                     "fx_fvg_formed_start",
                                     # Batch 2(a) Wyckoff V items (plan §3 V grid): read on the scan path
                                     # (backtest-methods._fires_from / _wy_params / scan); baseline = v1.
                                     "fx_w_stop", "fx_w4a_linger_closes", "fx_w6_window", "fx_w_spt",
                                     "fx_w_touch", "fx_w_tw")
                                    + ("fx_a2b_stale_htf_block",)
                                    + tuple(getattr(bt, "FX_ICT_KEYS", ()))
                                    # Batch 2(a) ICT V items (bt.FX_ICT_V_KEYS): recorded as their declared value; an opts dict that
                                    # lacks one records the BASELINE (what an absent key means), never None.
                                    + tuple(getattr(bt, "FX_ICT_V_KEYS", ()))},
                                   varied_per_config=residual),
        "provider_selection": {"see": "dataset_snapshot_id", "note":
                               "which providers supplied the bars is recorded in the §10 dataset snapshot, "
                               "by provider id per series; not duplicated here"},
        "execution_assumptions": {"fee_pct_per_side": fee_pct if fee_pct is not None else (
                                      "per configuration -- see setup.configs[*].fee" if configs else None),
                                  "stop_buffer_pct": bt.STOP_BUFFER_PCT,
                                  "slippage": "NOT MODELLED (scripts/backtest-methods.py:44)",
                                  "funding": "NOT MODELLED -- the traded crypto contract is a perpetual "
                                             "(SYSTEM-DESIGN.md §20.1)",
                                  "fill_model": "limit fills require the gap to be complete by the MSS close "
                                                "(causal cut, backtest-methods.py:180 fvg_fill)",
                                  # A0 (plan §2, §11): which real-cost profile (if any) priced this run, and
                                  # the sha256 of the exact export files it read -- so a report can be traced
                                  # to the broker export it was measured against, not merely a profile name
                                  # that might later be re-exported under the same name.
                                  "cost_profile": (_RC.profile_snapshot(cost_profile) if cost_profile else
                                                   not_applicable("--cost-profile not supplied; every trade "
                                                                  "priced by the flat fee_pct_per_side above "
                                                                  "(v1 unchanged, A0 plan §1.6)")),
                                  "flat_before_rollover": bool(opts.get("flat_before_rollover"))},
        "parameters": {"per_timeframe": {tf: dict(bt.P[tf]) for tf in timeframes if tf in bt.P},
                       "volume_thresholds": dict(bt.VOL), "displacement": dict(bt.DISP),
                       "preprocessing_version": N.SNAPSHOT_INPUTS_VERSION},
    })


def describe(snap):
    """One-line-per-series human summary, for a report header."""
    out = [f"snapshot {snap['snapshot_id']} · {snap['created_at']} · code "
           f"{(snap['code_version']['git_sha'] or 'unknown')[:8]}"
           f"{' (DIRTY)' if snap['code_version']['dirty'] else ''}"]
    for r in snap["series"]:
        out.append(f"  {r['canonical_symbol']:12} {r['timeframe']:4} {r['provider']:15} {r['market_type']:10} "
                   f"{r['bars']:>6} bars  {str(r['first_open'])[:10]}→{str(r['last_open'])[:10]}  "
                   f"{r['retrieval_state']:11} {r['sha256'][:12]}")
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Dataset snapshot for a research run (CLAUDE.md §10).")
    ap.add_argument("--symbols", default="BTCUSDT", help="comma-separated")
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--base", default=None, help="directory holding ohlcv.<SYM>.<TF>.json (default: live feed)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    pairs = [(s.strip(), a.tf) for s in a.symbols.split(",") if s.strip()]
    try:
        snap = dataset_snapshot(pairs, base=a.base)
    except FileNotFoundError as exc:
        print(f"missing input series: {exc}", file=sys.stderr)
        sys.exit(2)
    print(json.dumps(snap, indent=1) if a.json else describe(snap))
