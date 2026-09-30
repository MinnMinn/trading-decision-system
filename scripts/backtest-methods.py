#!/usr/bin/env python3
"""Backtest the ICT and WYCKOFF-BOOK entry methods (plus the non-runnable COMBINED-BOOK) on stored candles and report % returns per month / quarter / year at RISK per trade.

Usage: backtest-methods.py [--tf 15m,1H,4H,1D] [--symbols BTCUSDT,ETHUSDT,SOLUSDT] [--fee-pct 0.05] [--out docs/backtests/<file>.md] [--json PATH]
Data: data/history/ohlcv.<SYM>.<TF>.json (scripts/fetch-history.py). Everything is computed; nothing is judged by a model.

METHODS (long = accumulation side; short = the distribution mirror with the same rules):

  WYCKOFF-BOOK / COMBINED-BOOK — scripts/wyckoff_rules.py: downtrend → SC → 3×CHoBEV → CHoCH → AR → ST → ≥2 swing
    Phase B → Spring/Shakeout typed against WMT's own two tables → Test → (optionally) Phase D BU/LPS. This is
    the only Wyckoff engine in this file; the earlier "WYCKOFF" mechanical proxy (rolling min/max range, no
    Phase A/B, no CHoCH gate) was removed 2026-09-19 (docs/audits/2026-09-19-knowledge-fidelity.md finding 6:
    it could fire a "Spring" mid-trend with no accumulation structure behind it at all -- WA p68-80 requires the
    TR to be drawn from SC/AR only after three CHoBEV confirm a CHoCH). See the WYCKOFF-BOOK/COMBINED-BOOK
    block in scan() below for the ruleset.

  ICT      — knowledge/ict/core-a.md §2.17 (MSS by body close), §2.21 (FVG), knowledge/ict/core-b.md §2.2, §3.1; stop/target per .claude/skills/ict-skill "Invalidation"
    Liquidity      = the last 3-bar pivot low (SSL) / pivot high (BSL) before the bar. No volume, no trading range, no phase.
    Sweep          = low pierces the pivot low. MSS = within K bars a body close above the last 3-bar pivot high formed before the sweep.
    FVG            = bullish gap (candle1.high < candle3.low) in the leg from the sweep to MSS+1.
    Entry rule     = price returns into the FVG within K bars after the MSS: entry at the FVG's near edge (candle3.low). No return → no trade (limit not filled).
    Invalidation   = later body close below the swept low kills the read (knowledge/ict/core-a.md §3.6) — stop sits at the sweep low − buffer, so this is the stop.
    Target         = the next external liquidity = the highest high of the previous R bars (BSL). Same R as Wyckoff so the two are comparable.
    Timing         = none (crypto has no sourced killzone rule: knowledge/ict/core-a.md §6; docs/architecture/session-model.md).
    Displacement is MANDATORY, not a switch. The deck draws the line at the candle's body: R10 calls a
    full-bodied displacement close beyond structure an MSS, and R11 calls the same break WITHOUT displacement
    a liquidity grab -- "expect failure to continue", the opposite read (knowledge/ict/core-a.md §3.3 R10-R11,
    §2.16). So a non-displacement break is not a weaker MSS, it is a different event, and the pre-2026-09-19
    `--ict-disp` off-by-default switch measured a population in which the two were mixed.
    The other two switches of that 2026-09-12 trio are GONE rather than defaulted (knowledge audit finding 11):
      --ict-pd      R13 (longs in discount, shorts in premium) is not optional in the deck either, and it is
                    already enforced unconditionally on every ICT path -- scripts/ict-scan.py computes `pd_ok`
                    and ict_setups_live() below refuses any candidate without it. The flag read nothing.
      --std-origin  the deck fixes the anchor: fib 0 at "the previous high which made the highest high"
                    (Model11 p20, knowledge/ict/models.md §2.1.5), which is what ict-scan.py's `origin` already
                    computes. 'pivot' was a pre-2026-09-12 proxy kept as a choice; the deck offers no choice.

  COMBINED-BOOK (runnable=false, backtest-only) — SYSTEM-DESIGN §6 / knowledge/integrated/method.md §4: the book
    Wyckoff engine owns context + the excursion, ICT owns the entry structure left behind.
    Condition      = a book-engine Spring (WYCKOFF-BOOK's own gates, above) AND the ICT MSS + FVG confirmation within K bars.
    Entry rule     = ICT entry (return into the FVG) — else at the MSS close if price never returns (market order once the checklist is satisfied, WMT p269).
    Stop/target    = one invalidation owner (ict-skill "Invalidation"): the Spring low; target the TR opposite border.

OUTCOME — walk forward H bars: stop hit → −1R; target hit → +R_planned; both in one bar → loss; neither → mark-to-market R at bar H.
FEES    — taker fee per side (default 0.05%, Binance futures) charged on the notional; in R that is fee·2·entry/(entry−stop). Slippage not modelled.
ACCOUNT — RISK of current equity risked per trade, compounding, one open position per symbol, all symbols of a timeframe share one account.
          RISK is one number, set below and equal to strategy-runner.RISK_CEILING -- do NOT restate it as a literal in prose here or in the report title; it read "1%" for the whole day after the ceiling moved to 3%.
          Monthly / quarterly / yearly returns are equity-curve returns (closed trades booked at exit time).
"""
import argparse, bisect, collections, heapq, importlib.util, datetime, json, os, statistics, sys, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from repo_paths import repo_rel
import history_store as _HS      # CLAUDE.md §2/§58: THE shared history reader (single-file or split-gz) and
                                  # HISTORY_ROOT resolution -- also used by normalized.py/snapshot.py/
                                  # prop-search.py so a caller selecting an alternate root (a second
                                  # provider's dataset, e.g. data/history/ftmo) is honoured by every research
                                  # path that reads history, not just this engine (code review, 2026-09-29).
HISTORY_ROOT = _HS.history_root() # frozen into THIS module's own namespace at exec time (this module is
                                  # loaded fresh via importlib by every caller that wants a particular env
                                  # state -- history_store.history_root() itself is deliberately NOT cached,
                                  # see its own docstring for why). Re-exported as a plain attribute because
                                  # scan_cache.py reads `getattr(bt, "HISTORY_ROOT", None)`, and this name
                                  # predates the shared module. Unset BT_HISTORY_ROOT (the default, every
                                  # existing caller) reproduces `os.path.join(ROOT, "data", "history")`
                                  # exactly, unchanged.
import wyckoff_rules as W
import structures as _structures  # A1 (docs/plans/2026-09-28-methodology-improvement-plan.md §2, ADR 0009):
                                   # _wyckoff_candidates() below is routed through the one structure source.
import quality as _quality   # CLAUDE.md §20: the six data-quality states this loader flags its history against
import research_validity as _RV
import normalized as _N       # CLAUDE.md §8: available_time() is the one place "when a bar becomes knowable" is computed
import pit as _pit            # CLAUDE.md §8: series_as_of() is THE point-in-time load-time cutoff (see pit_cutoff() below)
import account_profile as _AP   # CLAUDE.md §33: a prop account and a personal account do not lose the same way  # CLAUDE.md §38: what those faults, and this engine's own gaps, do to a run
import event_risk as _ER        # CLAUDE.md §24-§32: the ±10' news window, read PIT off entry_time only
import sessions as _S            # CLAUDE.md §21: session labels, DST-aware
import performance as _perf      # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import snapshot as _snapshot     # CLAUDE.md §10/§11: the run identifies its dataset and its configuration
import instruments as _I         # the ONE allowlist; also names the market a symbol belongs to (§35)
import methods as _M             # RUNNER_METHODS[method]["requires"]: which methodology dimension(s) a
                                  # method reads, so a --trader constraint applies to the RIGHT method only (§17)
import trader_constraints as _TC  # CLAUDE.md §0.9: per-trader, per-methodology constraints, tighten-only
import providers as _P           # §4: which venue a market's orders go to (INT-4/PAR-2, PAR-4/DEC-4 fee/sizing)
import risk_model as _RM         # CLAUDE.md §34: THE fee/cost source (risk-config.json), shared with strategy-runner
import real_costs as _RC         # A0 (docs/plans/2026-09-28-methodology-improvement-plan.md §2): real, sourced
                                  # per-symbol/per-hour spread + per-night swap, selected by name via
                                  # `--cost-profile`/OPTS["cost_profile"] -- unset (default) leaves every
                                  # existing caller's fee/cost path exactly as it was (§1.6 live safety)
# "1m": owner decision 2026-09-29 (docs/plans/2026-09-28-methodology-improvement-plan.md §6 item 7) -- fund
# setups are now searched on 1m/5m/15m/30m, and this table had no 1m row at all (bt.scan(sym, "1m", ...) raised
# KeyError on `p = P[tf]` before this). PROJECT-DEFINED, not from the source books, same as every other row
# here: R/K/T/H scaled up from the 5m row (R=60, K=18, T=20, H=120) by roughly the same ratio the 5m->15m step
# uses. sob=10 is EXTRAPOLATED from the existing 5m=8/15m=6/30m=5 progression (not measured) -- see
# docs/architecture/analysis-params.json project_defined.fund_1m_timeframe_params for the recorded decision.
P = {"1m": dict(R=60, K=20, T=24, H=144, sob=10), "5m": dict(R=60, K=18, T=20, H=120, sob=8), "15m": dict(R=48, K=16, T=16, H=96, sob=6), "30m": dict(R=48, K=14, T=14, H=84, sob=5), "1H": dict(R=48, K=12, T=12, H=72, sob=4),
     "2H": dict(R=36, K=10, T=10, H=48, sob=3), "4H": dict(R=30, K=8, T=8, H=30, sob=3), "1D": dict(R=20, K=6, T=6, H=20, sob=2)}  # sob = bars a Spring may stay outside the TR (wyckoff_rules R6)
VOL = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"]["volume"]
STOP_BUFFER_PCT = 0.0005
import trading_env as _te
RISK = _te.MAX_RISK_PCT   # per-trade risk of equity. It MUST equal strategy-runner.RISK_CEILING or this report
                     # measures a different account than the one that trades -- so it is now READ from the same
                     # place the runner reads it (docs/architecture/risk-config.json via trading_env), not kept
                     # as a third copy of the number. It was the literal 0.03 until 2026-09-17; the ceiling moved
                     # to 1 % and a literal here would have left the report quietly modelling a 3 % account.
                     # Note for anyone re-reading docs/backtests/2026-09-13-rr-floor-and-risk.md: those figures
                     # were produced at 0.03. Under fixed-fractional sizing the R-multiples are unchanged, so the
                     # 3R floor conclusion carries over; the % return and % drawdown columns scale with RISK and
                     # must be re-run, not rescaled by eye.
START = 10000.0      # account size in $ (user decision 2026-09-11: $10,000 for readability)
RUIN_FRAC = 0.10     # the account is declared BLOWN (cháy) when equity <= 10 % of START; trading stops there and the report says so
# B1/Batch-1a (docs/plans/2026-09-29-execution-plan.md "Shared contract"): one OPTS key per ICT F item, bool,
# default = v1 behaviour (False). Threaded to scripts/ict-scan.py's analyze()/setup_candidate() via
# scripts/live_rules.py's read_at(opts=...) -- see ict_setups_live() below, the one call site that reads
# FX_ICT_KEYS out of OPTS. The live runner (scripts/strategy-runner.py) never sets any of these -- it calls
# lr.read_at()/lr.ict_scan.setup_candidate() with no opts= at all, so it always gets v1 (§1.6 live safety).
FX_ICT_KEYS = ("fx_b2a_fvg_in_leg", "fx_b2b_ce_fail", "fx_b1_pivot1", "fx_braid_optional")
# Batch 2(a): one key per ICT V item (docs/plans/2026-09-28-methodology-improvement-plan.md §3), each holding one
# value of the set DECLARED in scripts/ict-scan.py `V_ICT` (the single declaration; a check right after `lr` is
# loaded below asserts these defaults are that declaration's first = baseline = v1 values). Same rule as the F
# keys above: the live runner never sets any of them. B-MGMT is NOT a key here -- it is the existing `mgmt` knob.
FX_ICT_V_KEYS = ("fx_b_ex", "fx_b_pd", "fx_b_pool", "fx_b_buf", "fx_b_exit", "fx_b_lb", "fx_b6", "fx_b3", "fx_b7")
OPTS = dict(min_rr=None,   # set to MIN_RR right after _ICT is read below -- see the note there
             types=(1, 2, 3), htf=False, sides=("long", "short"), entry="book", mgmt="none", sloped_gate=False, st_min=None, phase_d=True, combined_entry="limit",
            st_gate=False, phase_b_gate=False, methods=None,
            # A0 (plan §2): both False/None by default -- v1 behaviour is byte-identical until a caller sets
            # these explicitly (main()'s --cost-profile/--flat-before-rollover, or a test's opts= override).
            flat_before_rollover=False, rollover_provider=None,
            # B1/Batch-1a: v1 default (False) for every fx_ ICT key -- see FX_ICT_KEYS just above.
            fx_b2a_fvg_in_leg=False, fx_b2b_ce_fail=False, fx_b1_pivot1=False, fx_braid_optional=False,
            # Batch 1(b) F items (docs/plans/2026-09-28-methodology-improvement-plan.md §3; the shared fx_ key
            # contract, docs/plans/2026-09-29-execution-plan.md): v1 default False for every key -- the live
            # runner never sets these. fx_w1/w2/w3/w5 change WYCKOFF-BOOK/COMBINED-BOOK detection itself (see
            # `_wyckoff_candidates`'s bridging into wyckoff_rules.PARAMS, and the `_WY_CANDIDATES` cache key in
            # scan()); fx_w7 changes only the Phase-D target/placeability in `_fires_from` (see
            # `_htf_wyckoff_target`). See scripts/wyckoff_rules.py's module docstring ("FIDELITY CORRECTIONS")
            # for each key's source and reading.
            fx_w1_tr_low_st=False, fx_w2_st_below_sc=False, fx_w3_mSOW_spring=False, fx_w5_vp_abandon=False,
            fx_w7_htf_target=False,
            # Batch 2(a) Wyckoff V items (plan §3 V grid; docs/architecture/v-grid-wyckoff.json). Each key holds ONE
            # value of its declared set, default = the baseline = v1 (WY_V_VALUES below is the declared sets); the
            # live runner never sets any of them. W-MGMT is the existing `mgmt` knob, not a new key; W4b is not
            # implemented (see the grid file), so it has no key here.
            fx_w_stop="current", fx_w4a_linger_closes=None, fx_w6_window=300, fx_w_spt="AR", fx_w_touch="off",
            fx_w_tw=(12, 2),
            # A2b decision side (plan §2, knowledge R20): default v1 = the HTF gate ignores staleness; the live
            # runner never sets it. See htf_bias_gate.
            fx_a2b_stale_htf_block=False,
            # Batch 2(a) ICT V items: the baseline (first declared) value of each = v1. See FX_ICT_V_KEYS above.
            fx_b_ex="iofed", fx_b_pd="r15", fx_b_pool="off", fx_b_buf="0", fx_b_exit="-2.0|H|floor",
            fx_b_lb="12|K", fx_b6="no", fx_b3="entry_tf", fx_b7="all_hours",
            # O1 (owner-approved 2026-09-30, docs/plans/2026-09-29-fund-search-preregistration-DRAFT.md): default v1
            # (False) = simulate()'s min_rr admission uses the real round-turn cost incl. the EXIT-hour spread and
            # swap. True = admission uses only what is knowable at the entry decision (see simulate()). The live
            # runner never sets it.
            fx_admission_entry_cost=False)
# The four fx_ keys that change WYCKOFF-BOOK/COMBINED-BOOK DETECTION (not just gating) -- read once per
# `_WY_CANDIDATES` cache build, bridged into the module-level wyckoff_rules.PARAMS the same way
# `spring_max_bars_outside` already is (see `_wyckoff_candidates`'s own docstring: it must stay OPTS-
# independent, so this bridging happens at its CALLERS, not inside it). fx_w7_htf_target is deliberately NOT
# here: it never touches detection, only `_fires_from`'s Phase-D target/placeability, so it needs no cache-key
# widening of `_WY_CANDIDATES`.
_FX_WYCKOFF_DETECTION_KEYS = ("fx_w1_tr_low_st", "fx_w2_st_below_sc", "fx_w3_mSOW_spring", "fx_w5_vp_abandon")


#: Batch 2(a) Wyckoff V items: the DECLARED value sets (plan §3, baseline first), the single in-code copy;
#: docs/architecture/v-grid-wyckoff.json restates them for fund-search.py and a test pins the two equal.
#: W4a's baseline "2" is the plan's grid accounting; the engine's v1 default is None (v1's own typing rule, which
#: is not a lingering-closes count) -- see `_check_wy_v_opts` and the grid file's note.
WY_V_VALUES = dict(
    fx_w_stop=("current", "spring_low"),
    fx_w4a_linger_closes=(None, 2, 3, 4),
    fx_w6_window=(300, 600),
    fx_w_spt=("AR", "ceiling", "VAH"),
    fx_w_touch=("off", "on"),
    fx_w_tw=((12, 2), (8, 2), (20, 2), (12, 3), (8, 3), (20, 3)),
)
W_TOUCH_MIN = 2   # "Two tests of each TR border before a Spring counts" (plan §3 W-TOUCH row; advance.md 2.11.2)
# The V keys that change DETECTION (per-call P= overrides + `_WY_CANDIDATES`/`_HTF_TR_CACHE` cache-key widening).
# Kept apart from `_FX_WYCKOFF_DETECTION_KEYS` (the four F keys, whose exact tuple is pinned by
# test_wyckoff_fidelity). fx_w_stop/fx_w_spt/fx_w_touch are pure gating (`_fires_from`); fx_w6_window changes
# the window scan() walks (a cache-key component of its own).
_FX_WYCKOFF_V_DETECTION_KEYS = ("fx_w4a_linger_closes", "fx_w_tw")


def _tw():
    """fx_w_tw as a tuple (a JSON round trip yields a list)."""
    v = OPTS.get("fx_w_tw", (12, 2))
    return tuple(v) if v is not None else (12, 2)


def _check_wy_v_opts():
    """Refuse a value outside the declared set instead of silently running the baseline (a typo in a grid
    cell must not become a mislabelled v1 run)."""
    for k, allowed in WY_V_VALUES.items():
        v = _tw() if k == "fx_w_tw" else OPTS.get(k, allowed[0])
        if v not in allowed:
            raise ValueError(f"OPTS[{k!r}] = {v!r} is not in the declared set {list(allowed)!r} "
                             f"(plan §3 V grid, docs/architecture/v-grid-wyckoff.json)")


def _fx_v_detection_opts():
    """The V detection keys as per-call P= overrides. Only NON-baseline values override, so at the baseline the
    PARAMS copy is exactly the v1 one."""
    out = {}
    n = OPTS.get("fx_w4a_linger_closes")
    if n is not None:
        out["fx_w4a_linger_closes"] = n
    tw = _tw()
    if tw != (12, 2):
        out["test_window"], out["min_phase_b_swings"] = tw
    return out


def _wy_params(sob):
    """The per-call copy of wyckoff_rules.PARAMS every detection call uses (never the global itself)."""
    return dict(W.PARAMS, spring_max_bars_outside=sob, **_fx_detection_opts(), **_fx_v_detection_opts())


def _wy_detection_ck():
    """Every OPTS value that changes Wyckoff DETECTION, for scan()'s `_WY_CANDIDATES` key and W7's
    `_HTF_TR_CACHE` key: the four F keys plus the V detection keys."""
    return (tuple(OPTS.get(_k, False) for _k in _FX_WYCKOFF_DETECTION_KEYS)
            + (OPTS.get("fx_w4a_linger_closes"), _tw()))


def _fx_detection_opts():
    """The four detection fx_ keys as the CURRENT OPTS states them, for a per-call `P=` copy of
    wyckoff_rules.PARAMS (see `_wyckoff_candidates`, `_htf_wyckoff_target`). Nothing in this file writes wyckoff_rules.PARAMS any more
    (code review round 1, item 3): a per-call copy cannot leak past its call, on a cache hit, or through an
    exception. The live runner never sets these keys, so this reads False (v1) there."""
    return {k: OPTS.get(k, False) for k in _FX_WYCKOFF_DETECTION_KEYS}
# `range_touches` (require N tests of EACH TR border before a Spring counts) lived here until A0b
# (docs/plans/2026-09-28-methodology-improvement-plan.md §A0b): it was set from --range-touches and echoed into
# every run's config snapshot as though it gated Springs, but no scan()/simulate() code path ever read
# OPTS["range_touches"] -- audited 2026-09-28 (docs/audits/2026-09-28-method-fidelity.md §2.3). Removed rather
# than left as a documented no-op so a future config snapshot cannot silently repeat the same false claim
# (CLAUDE.md §11: "do not rely on mutable external configuration" -- a key that looks live but is not is worse
# than one that is simply absent). `docs/architecture/improve-candidates.json` candidate `vol_type.1` declared
# an override on this key; with the key gone, scripts/improve-loop.py now REFUSES that candidate explicitly
# (`_apply_override` raises "not an OPTS key") instead of silently running a no-op -- see
# scripts/tests/test_improve_loop.py for the established pattern (the ict_disp removal did the same).
_ICT = json.load(open(f"{ROOT}/docs/architecture/analysis-params.json"))["project_defined"].get("ict", {})
DISP = _ICT.get("displacement", {"body_min_ratio": 0.6, "range_min_median_ratio": 1.2})
# The PLANNED-R:R floor. ONE reader for every path: trading_env.min_rr() validates and returns None rather than
# a fallback number. This used to be `_ICT.get("min_rr", {}).get("value", 2.0)`, and strategy-runner.py takes its
# floor from here (`MIN_RR = bt.MIN_RR`) -- so a dropped or renamed key would have silently put the LIVE runner
# back on the superseded 2R floor while it kept sizing at the 3 % ceiling (security review 2026-09-13, F1).
# Refuse loudly instead: this is an analysis script, and a measured population built on an unknown floor is not
# evidence. strategy-runner's own gate refuses per-signal when the floor is None.
_tespec = importlib.util.spec_from_file_location("trading_env", f"{ROOT}/scripts/trading_env.py")
trading_env = importlib.util.module_from_spec(_tespec); _tespec.loader.exec_module(trading_env)
MIN_RR = trading_env.min_rr()
if MIN_RR is None:
    raise SystemExit("analysis-params.json: project_defined.ict.min_rr.value is missing or not a positive number "
                     "-- the planned-R:R floor has one source and it must be readable")
OPTS["min_rr"] = MIN_RR
# The floor is ON by default (user decision 2026-09-13). It used to default to 0.0, which meant every caller that
# did not pass --min-rr measured a trade population the live gate would now refuse: 38 % of last year's setups
# planned under 2R. A caller that genuinely wants the unfiltered population (a flag sweep, say) must now say so.

# OPTS isolation (docs/audits/2026-09-24-system-audit.md, "OPTS isolation" round-4a finding): the canonical
# baseline, frozen the instant every module-level default (including MIN_RR) is in place. `scan(..., opts=...)`
# and `reset_opts()` build FROM this, never from whatever the mutable module global OPTS happens to hold at
# call time -- OPTS is a single module-level dict every scan-path function reads as a free variable
# (scan_for_trader's own docstring says so), and before this fix nothing stopped one caller's leftover mutation
# (a config sweep, a --trader overlay, a prior scan_for_trader() call that raised before its `finally` restored
# OPTS, or simply two callers in the same process using different keys) from silently becoming the NEXT
# caller's starting point. Measured in round 3: a stale OPTS["sides"] left over from an earlier tightened call
# produced a false "0 trades" result for an unrelated, later scan() call in the same process -- the two calls
# looked independent from their own call sites but were not, because both read the one global.
_OPTS_BASE = dict(OPTS)


# CLAUDE.md §38: "A research run must be flagged or invalidated when there is evidence of ... corrupted
# provider data, incomplete required inputs." Every §20 fault the loaded history carries, so a result can be
# judged on the data that produced it. §38 owns what is finally done with these; §20's work was to make them
# detectable at all, and this is the point where a backtest meets its data.
#
# CUTOFF-STABILITY ASSUMPTION (documented per fix-round-1 review item D, scripts/prop-search.py): `_ASSESSED`
# is keyed by (symbol, timeframe) ONLY, not by `_PIT_CUTOFF` -- so the quality state cached for (sym, tf) on
# the FIRST `load()` call in this process is served for every later call to the SAME (sym, tf), even if
# `pit_cutoff()` were changed in between. This is safe today because every caller that sets `_PIT_CUTOFF`
# (scripts/prop-search.py `_evaluate_candidate`) sets it to the SAME constant (VALIDATION_END) for the entire
# lifetime of one process -- it is never changed mid-run. A future caller that varies the cutoff within a
# single process (multiple validation boundaries in one run, say) would need to either clear `_ASSESSED`
# between cutoffs or fold the cutoff into this cache's key; neither is needed while every caller holds the
# cutoff fixed per process, so neither is done here speculatively (CLAUDE.md §57).
QUALITY_FLAGS = []
_ASSESSED = {}


#: (symbol -> {timeframe -> _source}) for every series this process has loaded. Read by `provider_mix()`.
PROVIDERS_SEEN = {}


def provider_mix():
    """Instruments whose loaded series did NOT all come from one provider.

    CLAUDE.md §6 forbids silent provider switching and §23 forbids presenting one venue's data as another's.
    Both were written about the live path; this is the same fault arriving in research, where it is quieter --
    every series is individually valid, correctly labelled, and produces a perfectly ordinary-looking row.
    Returns {symbol: {tf: source}} for the offenders, empty when every instrument has one source.
    """
    return {sym: dict(tfs) for sym, tfs in PROVIDERS_SEEN.items() if len(set(tfs.values())) > 1}


#: A caller-set cap on how many of the MOST RECENT bars `load()` returns, or None (the default: every bar in
#: the file). Exists for TEST / SANDBOX speed only (§0.10's `improve-loop.py` on a short real slice, per its
#: own docstring) -- it changes the SAMPLE a run measures, never PIT semantics (the last N bars are still read
#: in their own chronological order; nothing about availability, ordering or look-ahead changes). Set via
#: `limit_bars()`, never by assigning the module global directly, so every setter goes through the one place
#: this is documented.
_BARS_LIMIT = None


def limit_bars(n):
    """Cap every subsequent `load()` call to the most recent `n` bars (or lift the cap with `n=None`).

    Global and process-wide by design, matching how `OPTS` itself already works in this file -- a caller
    (`main()`'s `--bars`, `scripts/improve-loop.py`) sets it once before scanning, never per-symbol."""
    global _BARS_LIMIT
    _BARS_LIMIT = n


#: A caller-set point-in-time cutoff applied to every subsequent `load()` call, or None (the default: every
#: bar in the file, exactly as before this seam existed). Unlike `_BARS_LIMIT` (a SAMPLE-size convenience for
#: test speed), this is a research-integrity control (CLAUDE.md §8): it drops every candle whose AVAILABLE
#: time -- `normalized.available_time()`, open + one full period, the same rule `pit.series_as_of()` already
#: enforces everywhere else in this repo -- falls after the cutoff, so a bar that OPENS before the cutoff but
#: does not CLOSE until after it is excluded too (its high/low/close are not yet knowable at the cutoff). This
#: is what lets a caller (scripts/prop-search.py) feed the engine a history genuinely truncated at a validation
#: boundary, so nothing after that boundary can reach a decision, an indicator warm-up, or a data-quality
#: verdict -- the same invariant `htf_bias_gate()`/`ict_setups_live()` already hold bar-by-bar for the LIVE
#: read, now held at LOAD time for a whole archival run. Set via `pit_cutoff()`, never by assigning the module
#: global directly, matching `limit_bars()`'s own convention. Left at its default (None), `load()`'s behaviour
#: and output are BYTE-IDENTICAL to before this seam existed -- scripts/tests/test_prop_search.py proves this
#: with a small real scan compared with the cutoff left unset vs explicitly reset to None.
_PIT_CUTOFF = None


def pit_cutoff(cutoff):
    """Cap every subsequent `load()` call to candles whose AVAILABLE time (`normalized.available_time()`,
    reused via `pit.series_as_of()` -- see `_PIT_CUTOFF`'s own docstring) is <= `cutoff` (or lift the cap with
    `cutoff=None`). `cutoff` is an ISO-8601 `...Z` string or an aware `datetime` -- whatever `pit._aware()`
    already accepts; a naive datetime is refused rather than assumed to be UTC (CLAUDE.md §8).

    Global and process-wide, matching `limit_bars()`'s own convention -- a caller sets it once before
    scanning, never per-symbol."""
    global _PIT_CUTOFF
    _PIT_CUTOFF = cutoff


def load(sym, tf):
    # scripts/history_store.py: THE shared reader (single-file or split-gz) and its own load cache -- moved
    # out of this module (code review, 2026-09-29) so normalized.py/snapshot.py/prop-search.py read history
    # through the identical logic rather than a second copy that could drift (CLAUDE.md §58).
    d, p = _HS.read_doc(sym, tf, root=HISTORY_ROOT)
    if d is None:
        return None, None
    if _BARS_LIMIT and len(d.get("candles") or ()) > _BARS_LIMIT:
        d = dict(d, candles=d["candles"][-_BARS_LIMIT:])
    if _PIT_CUTOFF is not None:
        # CLAUDE.md §8: reuse pit.series_as_of() -- the ONE definition of "was this knowable yet?" -- rather
        # than re-deriving an availability rule here. `tf` is this call's own timeframe, matching every other
        # available_time() call in this file (htf_bias_gate, htf_position: always the SERIES' OWN tf, never
        # the caller's decision-bar tf).
        d = dict(d, candles=_pit.series_as_of(d["candles"], tf, _PIT_CUTOFF, symbol=sym))
    # CLAUDE.md §7: provenance travels with the series. Recorded per (symbol, timeframe) because ONE
    # instrument's series can come from two providers -- which is exactly what happened on 2026-09-18, when the
    # MT5 CFD import replaced XAUUSD 15m/1H/4H/1D and left 2H/30m/5m on the Yahoo futures proxy. A ranking
    # table built across those timeframes would compare a CFD against a futures contract and print one number.
    PROVIDERS_SEEN.setdefault(sym, {})[tf] = d.get("_source") or "UNDECLARED"
    if (sym, tf) not in _ASSESSED:
        # Freshness is meaningless for an archive -- nothing is late in 2023 -- so STALE and UNKNOWN are
        # expected here and are not faults. PARTIAL and INVALID are, and they are FLAGGED rather than raised:
        # refusing to run would delete the finding along with the result, and §38 offers "flagged OR
        # invalidated" precisely so a research defect can be reported instead of hidden in an exception.
        state, why = _quality.assess(d, tf, symbol=sym)
        _ASSESSED[(sym, tf)] = state
        if state not in ("FRESH", "STALE", "UNKNOWN"):
            QUALITY_FLAGS.append({"symbol": sym, "tf": tf, "state": state, "reason": why,
                                  "source": repo_rel(p, ROOT)})
            print(f"DATA-QUALITY FLAG (CLAUDE.md §20/§38): {sym} {tf} history is {state}: {why}",
                  file=sys.stderr)
    return list(d["candles"]), repo_rel(p, ROOT)  # a fresh list: the cached one is never handed out


# CLAUDE.md §38 "unrealistic execution assumptions", as DATA rather than as a paragraph of Vietnamese prose at
# the bottom of the report. True = modelled (the string says how), False = not modelled. Everything False is
# one §38 finding, because a run that omits a cost or a venue constraint is measuring a cheaper, more
# permissive venue than the one that trades -- a real measurement of a different system, which is why §38's
# first word (flag) applies rather than its second. The Caveats section of the report is now generated from
# this dict, so a newly modelled cost cannot be added to the engine and forgotten in the caveats, or vice versa.
EXECUTION_ASSUMPTIONS = {
    "taker_fee_both_sides": "charged on notional at --fee-pct per side",
    "position_sizing": f"fixed fractional at {RISK * 100:g}% of equity per trade (= the live ceiling)",
    "one_position_per_symbol": "overlapping signals on the same symbol are dropped",
    "same_bar_stop_and_target": "counted as the LOSS (pessimistic, not neutral)",
    "time_stop": "open positions closed at the close of bar entry+H (mark-to-market)",
    "slippage": False,
    "funding": False,
    "spread": False,
    "min_notional": False,          # so a booked trade may be a size no venue would accept
    "lot_step_rounding": False,
    "partial_fills": False,
}


_VERDICT_SLOT = "<!-- research-validity verdict: filled in after the run (CLAUDE.md §38) -->"

_VERDICT_HEAD = {
    _RV.VALID:      "**Kết luận §38: HỢP LỆ** — cả mười điều kiện của §38 đều đã được kiểm tra, không điều nào kích hoạt.",
    _RV.FLAGGED:    "**Kết luận §38: CÓ CỜ (FLAGGED)** — kết quả dưới đây đo một hệ thống KHÁC với hệ thống chạy thật; đọc các cờ trước khi dùng số.",
    _RV.INVALID:    "**Kết luận §38: KHÔNG HỢP LỆ (INVALID)** — các con số dưới đây KHÔNG phải là bằng chứng và không được dùng để chọn setup.",
    _RV.UNVERIFIED: "**Kết luận §38: CHƯA KIỂM CHỨNG (UNVERIFIED)** — không điều kiện nào kích hoạt, nhưng có điều kiện chưa hề được kiểm tra; đây không phải là 'sạch'.",
}


def _verdict_markdown(block):
    """§38's verdict as the first thing a reader of the report meets."""
    out = ["> " + _VERDICT_HEAD[block["verdict"]], ">"]
    for f in block["findings"]:
        word = "VÔ HIỆU" if f["disposition"] == _RV.INVALIDATES else "cờ"
        out.append(f"> - `{f['condition']}` ({word}{', nâng mức' if f['escalated'] else ''}): {f['detail']}")
    if block["unchecked"]:
        out.append("> - chưa kiểm tra: " + ", ".join(f"`{c}`" for c in block["unchecked"])
                   + " — xem `docs/architecture/research-validity.json` để biết vì sao chưa có detector.")
    out.append("> ")
    out.append("> _Nguồn: `docs/architecture/research-validity.json` qua `scripts/research_validity.py`._")
    return "\n".join(out)


def assess_run(cfg_snapshot=None, run=None, calendar=None):
    """This run's CLAUDE.md §38 verdict, built from the evidence the engine already has.

    Four feeds, all of which existed before §38 and none of which reached a verdict:
      * `QUALITY_FLAGS`      -- §20 faults in the loaded history (routed by fault kind: a timestamp fault
                                invalidates, another structural fault flags, a hole flags).
      * `EXECUTION_ASSUMPTIONS` -- what this engine does not model.
      * the §11 configuration snapshot -- dependencies the Trading System declares REQUIRED that this engine
                                never consults.
      * `OPTS["combined_entry"] == "hindsight"` -- LEGACY: before the COMBINED runner method was removed
                                (2026-09-19, docs/audits/2026-09-19-knowledge-fidelity.md finding 6) this was
                                the one switch in this file that was look-ahead BY CONSTRUCTION (it filled at
                                the FVG edge if the FUTURE showed a fill). No scan() code path reads it any
                                more -- setting it now changes no trade this engine produces -- but the OPTS
                                key and this check stay (so scripts/improve-loop.py's OPTS-key validation for
                                the unrelated `via.fvg` candidate in docs/architecture/improve-candidates.json
                                does not break, and so the check does not silently start reporting a false
                                "checked" the day someone else's edit reintroduces a hindsight fill path).

    Returns a `research_validity.Assessment`; callers stamp it into whatever they write.
    """
    a = _RV.Assessment(run)
    a.from_quality_flags(QUALITY_FLAGS)
    a.from_execution_assumptions(EXECUTION_ASSUMPTIONS, source="scripts/backtest-methods.py")
    if cfg_snapshot is not None:
        a.from_config_snapshot(cfg_snapshot)
    if OPTS.get("combined_entry") == "hindsight":
        a.finding("look_ahead",
                  "OPTS['combined_entry'] == 'hindsight': this switch no longer reaches any scan() code path "
                  "(the COMBINED runner method it controlled was removed 2026-09-19), so setting it changes no "
                  "trade -- but it is still refused as a research-validity finding rather than silently ignored, "
                  "in case a future entry rule reads it again without a matching update here",
                  source="scripts/backtest-methods.py")
    else:
        a.checked("look_ahead", f"OPTS['combined_entry']={OPTS.get('combined_entry')!r}; the non-causal "
                                f"'hindsight' rule was not used (and no longer affects any trade -- see OPTS "
                                f"default). Engine-wide look-ahead is proved separately "
                                f"by scripts/leakage.py (scripts/tests/test_backtesting.py)")
    # §6/§23 in the research path: one instrument, two providers, one table.
    for sym, tfs in sorted(provider_mix().items()):
        by_source = {}
        for tf, src in sorted(tfs.items()):
            by_source.setdefault(src, []).append(tf)
        detail = "; ".join(f"{src} on {'/'.join(tfs_)}" for src, tfs_ in sorted(by_source.items()))
        a.finding("unavailable_historical_data",
                  f"{sym} is measured across MORE THAN ONE provider in this run -- {detail}. The timeframes "
                  f"the traded instrument has no history for are standing in with a proxy from a different "
                  f"instrument, so a row spanning them compares two different markets and prints one number "
                  f"(CLAUDE.md §6, §23)",
                  source="scripts/backtest-methods.py provider_mix()")
    if calendar is not None:
        snap = (calendar.get("snapshot") or {})
        a.checked("future_calendar_state",
                 f"a calendar WAS supplied (--calendar, §0.3): snapshot id {snap.get('id')!r}, covers through "
                 f"{snap.get('covers_through')!r} -- admission-time refusal ran against this exact state "
                 f"(simulate()), so the run is not blind to it the way an unconditioned run is")
    else:
        a.not_applicable("future_calendar_state",
                         "this engine reads no economic calendar at all -- the omission is recorded under "
                         "incomplete_required_inputs, which is a different §38 condition")
    return a


def all_pivots(X, kind):
    """All 3-bar pivot indices (high or low) over the series, computed once."""
    out = []
    for i in range(3, len(X) - 3):
        w = [X[j] for j in range(i - 3, i + 4) if j != i]
        if (kind == "high" and all(v <= X[i] for v in w)) or (kind == "low" and all(v >= X[i] for v in w)):
            out.append(i)
    return out


def last_pivot(piv, upto):
    """Index of the last pivot confirmed before bar `upto` (a pivot at i needs bar i+3, so i <= upto-4)."""
    k = bisect.bisect_left(piv, upto - 3) - 1
    return piv[k] if k >= 0 else None


def walk(side, entry, stop, target, H_, L_, C_, start, horizon, Tm=None):
    """`Tm` (A0, plan §2): the series' own bar-close timestamps, parallel to `H_`/`L_`/`C_` -- only consulted
    when `OPTS["flat_before_rollover"]` is set (every existing caller passes nothing, or `Tm=None`, and gets
    byte-identical behaviour). When set, a position still open at the last bar that closes before the
    server's own daily rollover (`OPTS["rollover_provider"]`, via `real_costs.crosses_rollover`) is closed at
    THAT bar's close -- `outcome="rollover_flat"` -- rather than carried into the next bar. This is a clock
    decision only: it never looks at a later bar's price, matching CLAUDE.md §8."""
    r = (entry - stop) if side == "long" else (stop - entry)
    if r <= 0:
        return None
    rp = abs(target - entry) / r
    # Breakeven trigger. The BOOK (WMT p272) says to consider moving the stop to entry "once price has moved
    # favorably or consolidated into a new zone" and prints NO R figure -- "+1R" is this project's
    # operationalisation of "moved favorably", not the book's rule. Labelled 2026-09-19 after a knowledge
    # audit found the p272 cite making a project number look sourced.
    be_level = (entry + r) if side == "long" else (entry - r)   # +1R = PROJECT parameter (see above)
    cur_stop = stop; be = False
    # CLAUDE.md §39 asks for MFE and MAE and this loop is the only place that sees the bars BETWEEN entry and
    # exit, so it is the only place they can be measured. Both are in R and both are recorded on the bar that
    # ends the trade as well as the bars before it -- the extreme of the exit bar is part of the excursion.
    # §37 explicitly permits future bars to determine these: they are outcome fields, not decision fields, and
    # scripts/leakage.py already lists them in OUTCOME_FIELDS so the PIT prober does not read a change in them
    # as look-ahead.
    mfe = mae = 0.0

    def _excursion(j):
        nonlocal mfe, mae
        hi = (H_[j] - entry) / r if side == "long" else (entry - L_[j]) / r
        lo = (L_[j] - entry) / r if side == "long" else (entry - H_[j]) / r
        mfe = max(mfe, hi); mae = min(mae, lo)

    if OPTS.get("flat_before_rollover") and Tm is not None and 1 <= start < min(len(C_), start + horizon) \
            and _RC.crosses_rollover(Tm[start - 1], Tm[start], OPTS["rollover_provider"]):
        # The rule above only asks about the boundary AFTER each walked bar. The boundary between the ENTRY (fill)
        # bar and the first walked bar was never asked, so a position filled on the last bar before the server's
        # rollover (or before a data gap that spans it) was carried across it. Found on real FTMO history by the
        # fund-search rollover assertion once B-RAID/B1 raised the trade count. Same clock-only decision, no later
        # price is read: flat at the entry bar's own close, zero bars walked.
        j = start - 1
        return dict(outcome="rollover_flat", R=((C_[j] - entry) if side == "long" else (entry - C_[j])) / r, exit=j,
                    R_planned=rp, mfe=0.0, mae=0.0, bars_held=0)
    for j in range(start, min(len(C_), start + horizon)):
        _excursion(j)
        hit_stop = L_[j] <= cur_stop if side == "long" else H_[j] >= cur_stop
        hit_tgt = H_[j] >= target if side == "long" else L_[j] <= target
        if hit_stop:
            return dict(outcome="loss" if not be else "breakeven", R=-1.0 if not be else 0.0, exit=j,
                        R_planned=rp, mfe=mfe, mae=mae, bars_held=j - start + 1)
        if hit_tgt:
            return dict(outcome="win", R=rp, exit=j, R_planned=rp, mfe=mfe, mae=mae, bars_held=j - start + 1)
        if OPTS["mgmt"] == "be" and not be and ((H_[j] >= be_level) if side == "long" else (L_[j] <= be_level)):
            be = True; cur_stop = entry
        if OPTS.get("flat_before_rollover") and Tm is not None:
            # A0 fund-cell rule (plan §2, §6 items 3/5/7): bar j neither stopped nor targeted -- is it the
            # LAST bar closing before the server's own daily rollover? Only asks about bar j+1 if bar j+1 is
            # still inside this trade's own horizon/history window (mirroring the ordinary timeout bound
            # below); an end-of-window bar is left to the ordinary timeout path, not flattened early.
            nxt = j + 1
            if nxt < min(len(C_), start + horizon) and _RC.crosses_rollover(Tm[j], Tm[nxt], OPTS["rollover_provider"]):
                return dict(outcome="rollover_flat",
                            R=((C_[j] - entry) if side == "long" else (entry - C_[j])) / r, exit=j,
                            R_planned=rp, mfe=mfe, mae=mae, bars_held=j - start + 1)
    j = min(len(C_) - 1, start + horizon - 1)
    return dict(outcome="timeout", R=((C_[j] - entry) if side == "long" else (entry - C_[j])) / r, exit=j,
                R_planned=rp, mfe=mfe, mae=mae, bars_held=j - start + 1)


# WY-1 (docs/audits/2026-09-24-system-audit.md, 2026-09-25): this used to be its own side-aware
# implementation with no caller outside scripts/tests/test_bias_methods.py -- the engine
# (scripts/wyckoff_rules.py detect_accumulations/detect_distributions) kept typing every break with the
# Spring ladder regardless of side. `vol_type` in wyckoff_rules.py is now the ONE owner of this logic (both
# the live runner via wyckoff_fires and this backtest ask it the same question); this name stays as a thin
# alias so callers/tests that still spell it `vtype` (with a side argument) keep working.
vtype = W.vol_type


def is_displacement(j, O, H, L, C, R=48):
    """knowledge/ict/core-a.md §2.16 'aggressive move with full-bodied candles' read with the project ratios (analysis-params.json project_defined.ict)."""
    rg = H[j] - L[j]
    if rg <= 0:
        return False
    a = max(0, j - R); med = statistics.median(H[q] - L[q] for q in range(a, j)) if j - a >= 5 else rg
    return abs(C[j] - O[j]) >= DISP["body_min_ratio"] * rg and rg >= DISP["range_min_median_ratio"] * med


def find_ict(side, i, rec, H, L, C, K, n, PH, PL, O):
    """MSS (body close beyond the last pivot before the sweep) within K bars after rec, and an FVG in the leg.
    Returns (mss, fvg_edge, fvg_far) or None.

    The MSS candle MUST pass is_displacement (knowledge/ict/core-a.md §3.3 R10; a break without displacement is
    R11's liquidity grab, a different read). `O` is therefore required -- it used to default to None, which
    silently turned the gate off for every caller that omitted it (knowledge audit 2026-09-19, finding 11)."""
    disp_ok = lambda j: is_displacement(j, O, H, L, C)
    if side == "long":
        ph = last_pivot(PH, i)
        if ph is None:
            return None
        lvl = H[ph]
        mss = next((j for j in range(rec + 1, min(rec + 1 + K, n)) if C[j] > lvl and disp_ok(j)), None)
        if mss is None:
            return None
        # FVG must be COMPLETE by the MSS close (third candle <= mss): a gap whose third candle is mss+1 is only known
        # after that candle closed, and its low would already have "filled" the limit -- look-ahead (found 2026-09-11 parity test).
        for k in range(i + 1, min(mss, n - 1)):
            if H[k - 1] < L[k + 1]:
                return mss, L[k + 1], H[k - 1]
    else:
        pl = last_pivot(PL, i)
        if pl is None:
            return None
        lvl = L[pl]
        mss = next((j for j in range(rec + 1, min(rec + 1 + K, n)) if C[j] < lvl and disp_ok(j)), None)
        if mss is None:
            return None
        for k in range(i + 1, min(mss, n - 1)):
            if L[k - 1] > H[k + 1]:
                return mss, H[k + 1], L[k - 1]
    return None


def fvg_fill(side, mss, edge, far, stop, H, L, K, n):
    """First bar after the MSS (within the K-bar window anchored on `mss`) whose range reaches the FVG near
    edge -- the resting LIMIT. Returns None if the order never triggers in the window. Otherwise returns
    (bar_index, outcome):
      * "filled"             -- the limit filled and that same bar did not also reach the stop.
      * "filled_and_stopped" -- the SAME bar that reached the near edge also reached the stop.

    ICT-8 (docs/audits/2026-09-24-system-audit.md; project conservatism, CLAUDE.md §38 -- OHLC cannot order intra-bar events; no single book rule states this: a setup is
    invalid once its stop level is traded). For a long, stop < edge always (risk = entry-stop > 0), so ANY bar
    whose low reaches the stop has, in that same bar, already reached the edge -- there is no ordering of
    "filled" vs "invalidated" inside one OHLC bar. Checking the stop FIRST (as this function did before
    2026-09-24) returned None for that bar and every caller read None as "never triggered": the backtest
    silently dropped a real -1R loss, and the live runner (strategy-runner.ict_live_setups) could offer the
    setup as a brand-new order even though its own invalidation level had already traded. Checking the edge
    first and reporting BOTH conditions on the same bar fixes both paths from the one shared function (CLAUDE.md
    §37): the backtest now books the pessimistic/conservative -1R loss instead of dropping the trade (§38), and
    "fill is not None" already means "already triggered, including by invalidation" for the live caller, so no
    live-side special case is needed."""
    for j in range(mss + 1, min(mss + 1 + K, n)):
        if side == "long":
            hit_edge, hit_stop = L[j] <= edge, L[j] <= stop
        else:
            hit_edge, hit_stop = H[j] >= edge, H[j] >= stop
        if hit_edge:
            return j, ("filled_and_stopped" if hit_stop else "filled")
    return None


def range_established(H, L, a, b, support, resistance, touches, tol=0.15):
    """Trading range proxy (WA p71–72: the TR is drawn from AR and SC/ST — i.e. both borders have been tested):
    at least `touches` separate visits to within tol·TR of each border inside bars a..b (visits ≥ 3 bars apart)."""
    tr = resistance - support; lo_t = []; hi_t = []
    for j in range(a, b):
        if L[j] <= support + tol * tr and (not lo_t or j - lo_t[-1] > 3):
            lo_t.append(j)
        if H[j] >= resistance - tol * tr and (not hi_t or j - hi_t[-1] > 3):
            hi_t.append(j)
    return len(lo_t) >= touches and len(hi_t) >= touches


# Structure tier per timeframe: the next rung >= 4x (scripts/automation.py next_rung, docs/architecture/timeframe-mapping.md).
# "1m" added 2026-09-29 (plan §6 item 7, fund setups now searched on 1m too) -- next_rung("1m", _RUNGS) resolves
# to "5m" (5 >= 4x1), so a 1m setup gets an HTF_OF structure gate exactly like every other rung already does.
_RUNGS = ["1m", "5m", "15m", "30m", "1H", "2H", "4H", "1D"]
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
HTF_OF = {tf: _auto.next_rung(tf, _RUNGS) for tf in _RUNGS if _auto.next_rung(tf, _RUNGS)}
# The live rules seam (scripts/live_rules.py): the ICT branch calls the live scanner through this handle instead of
# re-deriving pivots/MSS/FVG itself (audit 2026-09-13 -- see docstring at the top of this file's ICT section).
_lspec = _iu.spec_from_file_location("live_rules", os.path.join(ROOT, "scripts", "live_rules.py"))
lr = _iu.module_from_spec(_lspec); _lspec.loader.exec_module(lr)
if {k: OPTS[k] for k in FX_ICT_V_KEYS} != lr.ict_scan.V_ICT_DEFAULTS:
    raise SystemExit("OPTS defaults for the ICT V keys differ from scripts/ict-scan.py V_ICT_DEFAULTS -- the "
                     "baseline (first declared value) of every V key must be v1 behaviour")


def htf_position(sym, tf):
    """Higher-timeframe context proxy for the giảm-khung rule (htf_context.py, WA p93–96, p201): where the HTF close sits
    inside its own rolling R-bar range (0 = at the low, 1 = at the high). Returns [(close_time, pct)] or None.

    Keyed on the HTF bar's CLOSE time (normalized.available_time: open + one full period), not its open time.
    Before 2026-09-18 this keyed on `c[i]["time"]` (the bar's OPEN), so `htf_allows`'s bisect on the LTF
    decision time `t` could select an HTF bar that had OPENED before `t` but not yet CLOSED -- its `close` (and
    the `pct` derived from it) was not actually knowable at `t`. A one-bar look-ahead leak, CLAUDE.md §8."""
    h = HTF_OF.get(tf)
    if not h:
        return None
    c, _ = load(sym, h)
    if not c:
        return None
    Rh = P[h]["R"]; out = []
    for i in range(Rh, len(c)):
        lo = min(x["low"] for x in c[i - Rh:i]); hi = max(x["high"] for x in c[i - Rh:i])
        close_time = _N.available_time(c[i], h).isoformat().replace("+00:00", "Z")
        out.append((close_time, (c[i]["close"] - lo) / (hi - lo) if hi > lo else 0.5))
    return out


def htf_allows(htf, t, side):
    """LEGACY: the pre-2026-09-13 rolling-percentile proxy. Still the higher-timeframe boundary filter for THIS
    scan()'s WYCKOFF-BOOK/COMBINED-BOOK block (unchanged, Task 8 dependency map -- those methods are not
    migrated by this task); strategy-runner.py's own htf_pass() no longer calls this (it
    was migrated onto bias_allows() below, Task 8, 2026-09-13). Boundary rule (htf_context.BOUNDARY_FRACTION):
    longs only when the HTF sits in the lower third of its range or has broken above it (markup); shorts the
    mirror. Uses the last HTF bar that CLOSED before t."""
    k = bisect.bisect_left(htf, (t,)) - 1
    if k < 0:
        return False
    pct = htf[k][1]
    return pct <= 1 / 3 or pct > 1.0 if side == "long" else pct >= 2 / 3 or pct < 0.0


def bias_allows(bias, side):
    """The giảm-khung gate read from the LIVE bias (htf_context.bias_of via live_rules.bias_at). `bias` is the
    first element of the (bias, basis) tuple that live_rules.bias_at(...) / htf_context.bias_of(...) return --
    i.e. call this as bias_allows(bias_at(...)[0], side), never with the (bias, basis) tuple itself. That first
    element is a string with exactly four possible values: "long", "short", "neutral", "unknown"
    (scripts/htf_context.py wyckoff_bias / ict_bias / bias_of).

    Only an explicit agreement opens the gate: `neutral` is a real reading that found no direction and `unknown`
    means no read was available, and neither is permission to take risk (capital preservation first). This is
    what strategy-runner.py's htf_pass() uses now (Task 8, 2026-09-13); htf_allows above is the rolling-
    percentile proxy it replaced there, kept because WYCKOFF-BOOK/COMBINED-BOOK in
    THIS file's scan() still use it (unchanged, Task 8 dependency map)."""
    return bias == side


#: (sym, htf) -> list of available_time strings, one per HTF bar, cached per history identity -- see
#: `htf_bias_gate` below. Recomputing normalized.available_time() for every HTF bar on every LTF decision
#: would be O(bars) per call in a loop that runs O(bars) times.
_HTF_TIMES = {}


# B3 (fx_b3="tfa_p5"): the higher-timeframe pairing of knowledge/ict/models.md §2.8 "Pairing table -- TFA p5 (3):
# Weekly->H4, Daily->H1, H4->M15, H1->M5, M30->M3, M15->M1", written as ENTRY timeframe -> BIAS timeframe in this
# engine's names. An entry timeframe the table does not pair (30m, 2H, 4H whose W1 has no live scan window, 1D)
# has NO bias tier under it: the gate is structurally unable to judge and refuses (never a silent fallback).
TFA_P5_BIAS_TF = {"1m": "15m", "5m": "1H", "15m": "4H", "1H": "1D"}


def htf_bias_gate(sym, tf, side, decision_time, methods, h=None):
    """INT-6/PAR-3 (docs/audits/2026-09-24-system-audit.md): THE htf gate, shared by every RUNNER_METHODS
    branch in `scan()` -- exactly the function strategy-runner.htf_pass() calls live
    (`bt.bias_allows(bt.lr.bias_at(candles_htf, len(candles_htf)-1, htf_tf, methods))`), except `candles_htf`
    there is already causal (fetch_candles/drop_forming), so its last element IS "the last HTF bar closed as
    of this tick" -- here, with the FULL stored history in hand, that same bar has to be found explicitly by
    `decision_time`.

    `decision_time` MUST be the LTF decision bar's own CLOSE -- `normalized.available_time(bar, tf)`, an
    ISO string with the same "+00:00"->"Z" normalisation `_HTF_TIMES` itself uses -- NEVER the bar's raw
    `"time"` field (its OPEN). `_HTF_TIMES` is built from `available_time()` too (line below), so comparing
    an LTF bar's OPEN against HTF CLOSE timestamps is an apples-to-oranges bisect: it silently selects an
    HTF bar one rung too early whenever the LTF bar's open falls inside the HTF bar that is STILL forming,
    which both scan() call sites did before round-4a fix round 1 (code review of a746ffc) -- measured at
    551/2000 boundary bars on BTCUSDT, diverging from what live's own htf_pass() (strategy-runner.py) reads
    at the same tick.

    Returns True (agrees), False (judged and refused), or None (structurally unable to judge -- htf_tf has no
    live scan window, or there is no HTF bar closed yet). Callers must refuse on anything other than an
    explicit True (`is not True`), matching strategy-runner.py's own fail-closed htf_pass() caller -- None is
    not permission.
    """
    # `h` (B3 only): an explicit bias tier overriding the next-rung default -- None (every existing caller) is
    # exactly the pre-B3 behaviour.
    h = h or HTF_OF.get(tf)
    if not h:
        return None
    c, _ = load(sym, h)
    if not c:
        return None
    key = (sym, h, len(c), c[0]["time"], c[-1]["time"])
    if key not in _HTF_TIMES:
        _HTF_TIMES[key] = [_N.available_time(x, h).isoformat().replace("+00:00", "Z") for x in c]
    times = _HTF_TIMES[key]
    i = bisect.bisect_right(times, decision_time) - 1
    if i < 0:
        return None
    if OPTS.get("fx_a2b_stale_htf_block"):
        # A2b (CLAUDE.md §20: never silently convert STALE to FRESH): a last-closed HTF bar older than
        # STALE_AFTER_BARS x the HTF timeframe -- quality.assess's own threshold -- is an unmet gate, never a pass.
        # Measured on bar-close time, so a market-closed gap (weekend) also counts as stale: stricter than v1 by
        # design, and stricter than the live feed's received-time check. Judge it with that in mind.
        age = (datetime.datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
               - datetime.datetime.fromisoformat(times[i].replace("Z", "+00:00"))).total_seconds()
        if age > _N.STALE_AFTER_BARS * _N.tf_seconds(h):
            return False
    try:
        bias, _ = lr.bias_at(c, i, h, methods)
    except (IndexError, KeyError):
        return None
    return bias_allows(bias, side)


#: (sym, htf, decision_time, side, history identity, sob, w1, w2, w3, w5) -> target price or None, memoized per
#: process -- W7 (below) re-detects the HTF series on every distinct decision it is asked about; this avoids
#: repeating that for the same question. The key is built the way `_WY_CANDIDATES`' is in scan(): the four
#: detection fx_ keys change DETECTION, so two configs differing in one of them must not share an entry, and the
#: HTF history identity keeps a reloaded/extended series from serving a stale one.
_HTF_TR_CACHE = {}


def _htf_wyckoff_target(sym, tf, side, decision_time):
    """W7 (WA2-19, WA p83-84; docs/plans/2026-09-28-methodology-improvement-plan.md §2 item A1b "higher-
    timeframe Wyckoff trading-range detection"): the target a Phase-D LTF entry projects when
    OPTS["fx_w7_htf_target"] is set, taken from the enclosing HIGHER-timeframe Wyckoff trading range --
    "move up a timeframe to see where the current TR sits inside the larger TR and use the larger TR's AR/SOS
    as the target" (WA2-19). Reads the HTF structure's own SOS breakout close if one has already occurred by
    `decision_time` (the more refined "already broke out to here" level), else its AR level (`tr_hi` for a
    long/accumulation read, `tr_lo` for a short/distribution read) -- the two literal alternatives WA2-19
    names. `decision_time` is the LTF Phase-D decision bar's own CLOSE -- `normalized.available_time(bar, tf)`
    as an ISO string with "+00:00"->"Z", exactly what htf_bias_gate's `decision_time` is -- NEVER the bar's raw
    `"time"` (its OPEN); see htf_bias_gate's docstring for why the OPEN would be wrong here. `_fires_from` builds
    it from `Tm[last]` + `tf` before calling this.

    Returns None -- "no HTF TR, no Phase-D trade" (plan §3 W7 row) -- when: `tf` has no higher rung (HTF_OF);
    `sym` is not given; the HTF series has no history; the PIT-truncated HTF prefix is too short to detect
    anything; or detection finds no HTF structure of the SAME side knowable as of `decision_time`.

    PIT (CLAUDE.md §8): the HTF series is truncated with pit.series_as_of() (the ONE `availableTime <=
    decisionTime` primitive, scripts/pit.py) BEFORE detection runs -- detection is RE-RUN on the truncated
    prefix, never sliced out of a full-history detection, because a later HTF bar can change which swing an
    earlier one paired with (wyckoff_fires()'s own docstring documents the general shape of this hazard for
    the LTF read; the same hazard applies one rung up).

    AWAITING OWNER SIGN-OFF (plan §3 W7 row, "it acts on ~80% of [Phase-D] trades, so owner sign-off is
    required in advance"): built behind OPTS["fx_w7_htf_target"] for its funnel/trade-count delta
    (docs/audits/2026-09-29-wyckoff-fidelity-funnel.md), NOT adopted -- the live/pilot path never sets this
    key."""
    h = HTF_OF.get(tf)
    if not h or not sym:
        return None
    c, _ = load(sym, h)
    key = ((sym, h, decision_time, side, (len(c), c[0]["time"], c[-1]["time"]) if c else None, P[h]["sob"])
           + _wy_detection_ck())
    if key in _HTF_TR_CACHE:
        return _HTF_TR_CACHE[key]
    target = None
    if c:
        trunc = _pit.series_as_of(c, h, decision_time, symbol=sym)
        if len(trunc) >= 2 * W.PARAMS["pivot"] + 5:
            O_ = [x["open"] for x in trunc]; H_ = [x["high"] for x in trunc]; L_ = [x["low"] for x in trunc]
            C_ = [x["close"] for x in trunc]; V_ = [x.get("volume", 0) for x in trunc]
            vkind = "tick" if _I.is_tick_volume(sym) else "traded"
            # spring_max_bars_outside is per-timeframe (P[h], not the LTF's P[tf]) -- the same convention
            # `_wyckoff_candidates` already uses for its own tf -- and the detection fx_ keys are read from
            # OPTS, both via a per-call copy of W.PARAMS: nothing global is written, so nothing needs restoring.
            wp = _wy_params(P[h]["sob"])
            recs = _structures.wyckoff_records(O_, H_, L_, C_, V_, P=wp, volume_kind=vkind, side=side)
            if recs:
                htf_r = recs[-1]   # the most recently formed HTF structure knowable as of decision_time
                target = C_[htf_r["sos"]] if htf_r["sos"] is not None else (
                    htf_r["tr_hi"] if side == "long" else htf_r["tr_lo"])
    _HTF_TR_CACHE[key] = target
    return target


def resolve_methods(sym):
    """The bias-reading methods engaged for `sym`, resolved from /automation the same way live does --
    htf_context.engaged_methods_for_market(automation.market_of(sym)). OPTS["methods"] holds an explicit
    --methods CLI override when one was given; None (its default) means "resolve it here", never a hardcoded
    tuple -- a backtest that guessed its own default methods would silently diverge from the run being
    reproduced (see live_rules.read_at's docstring for the same argument)."""
    if OPTS["methods"] is not None:
        return OPTS["methods"]
    return lr.htf.engaged_methods_for_market(_auto.market_of(sym))


def ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, methods):
    """ICT trades for one symbol/timeframe using the LIVE rules: at each bar, run the scanner over the window the
    live scanner would have read and ask IT for the setup. No pivot/MSS/FVG logic of our own -- that duplication is
    what made a backtest measure a system nobody trades (audit 2026-09-13).

    The entry is a LIMIT at the FVG near edge, exactly as live places it (strategy-runner.py: "LIMIT at the FVG
    near edge"). So a setup is NOT a trade: fvg_fill() decides whether price ever came back to that limit without
    first hitting the stop, and returns None when the order would simply never have filled. Skipping that check
    would enter every setup at a favourable price and make the whole backtest optimistic by construction."""
    x = _ict_ctx(sym, tf, c, Tm, HZ, H, L, C, methods)
    out, seen = [], set()
    for i in range(x.n):
        a = lr.read_at(c, i, tf, methods, opts=x.fx_opts)
        if a is None:            # window not yet the full live window -- live would not have scanned here at all
            continue
        su = _ict_candidate(x, i, a)
        if su is None:
            continue
        key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
        if key in seen:          # the same setup stays visible for many bars; take it once, at its first bar
            continue
        seen.add(key)
        t = _ict_trade(x, i, su)
        if t is not None:
            out.append(t)
    return out


def _ict_ctx(sym, tf, c, Tm, HZ, H, L, C, methods, idx_of_time=None):
    """Everything ict_setups_live() derives from OPTS once per scan -- moved verbatim out of its head so that
    scan_many() (scripts/scan_many.py) can build one per overlay and share the per-bar analysis between them.
    Reads the CURRENT module OPTS, exactly as ict_setups_live() always did. `x.fx_opts` is the overlay the
    per-bar analysis and setup_candidate() receive."""
    n = len(c)
    if idx_of_time is None:      # scan_many() passes one shared dict: it is a pure function of Tm, n entries big
        idx_of_time = {t: j for j, t in enumerate(Tm)}
    # B1/Batch-1a: the same fx_ overlay goes to BOTH read_at() (analyze()) and setup_candidate() -- B2b's
    # `inverted_at` field is only present on an fvg when analyze() itself was called with fx_b2b_ce_fail, so a
    # caller that set the key for one but not the other would silently get v1 setup_candidate() behaviour.
    fx_opts = {k: OPTS[k] for k in FX_ICT_KEYS}
    # A V key travels to analyze()/setup_candidate() only when it is NOT at its baseline: the baseline is what
    # they do when the key is absent, so an untouched run hands them the very same overlay it always did.
    fx_opts.update({k: OPTS[k] for k in FX_ICT_V_KEYS if OPTS[k] != lr.ict_scan.V_ICT_DEFAULTS[k]})
    # Batch 2(a) ICT V items (scripts/ict-scan.py V_ICT declares every value set; each key's baseline = v1, so
    # every branch below is a no-op unless a caller set a key). fx_b_ex / fx_b_pd / fx_b_pool / fx_b_buf and the
    # target part of fx_b_exit act inside analyze()/setup_candidate() through `fx_opts`; the rest act here.
    lr.ict_scan.check_v_opts({k: OPTS[k] for k in FX_ICT_V_KEYS})
    lb_tok, k_tok = lr.ict_scan.b_lb_parts(OPTS["fx_b_lb"])          # B-LB
    lb_base = lr.setup_lookback(tf)
    lookback = lb_base if lb_tok == "12" else int(round(lb_base * int(lb_tok) / 12))
    _, hold_tok, _floor = lr.ict_scan.b_exit_parts(OPTS["fx_b_exit"])   # B-EXIT time stop
    hz = {"H": HZ, "1.5H": int(round(1.5 * HZ)), "2H": 2 * HZ, "none": n}[hold_tok]
    b3_tfa = OPTS["fx_b3"] == "tfa_p5"                                # B3
    b7_kz = OPTS["fx_b7"] == "killzone" and (_I.display(sym).get("asset_class") == "indices")   # B7: indices only
    K = P[tf]["K"] * (2 if k_tok == "2K" else 1)      # B-LB: K-bar expiry K (v1) or 2K
    return types.SimpleNamespace(sym=sym, tf=tf, c=c, Tm=Tm, H=H, L=L, C=C, methods=methods, n=n,
                                 idx_of_time=idx_of_time, fx_opts=fx_opts, lookback=lookback, hz=hz,
                                 b3_tfa=b3_tfa, b7_kz=b7_kz, K=K)


def _ict_candidate(x, i, a):
    """The PRE-dedupe half of ict_setups_live()'s per-bar body: the setup at bar `i` given the bar's analysis `a`,
    after every gate that runs before the `seen` check -- or None. Reads OPTS (htf) exactly as the loop did."""
    sym, tf, c, Tm, H, L, C, methods = x.sym, x.tf, x.c, x.Tm, x.H, x.L, x.C, x.methods
    lookback, fx_opts, b3_tfa = x.lookback, x.fx_opts, x.b3_tfa
    su = lr.ict_scan.setup_candidate(a, lr.window(c, i, tf), lookback, opts=fx_opts)
    if not su or not su.get("complete") or not su.get("pd_ok"):
        return None
    if b3_tfa:
        # B3 (knowledge/ict/models.md §2.8, TFA p5): the bias is read on the PAIRED higher timeframe instead of
        # the entry timeframe -- same gate function the HTF filter uses, keyed on this bar's own close. No
        # pairing for this timeframe, or no readable/closed bias bar = cannot judge = refuse.
        pair = TFA_P5_BIAS_TF.get(tf)
        if pair is None or htf_bias_gate(sym, tf, su["side"],
                                         _N.available_time(c[i], tf).isoformat().replace("+00:00", "Z"),
                                         methods, h=pair) is not True:
            return None
    else:
        bias, _ = lr.bias_at(c, i, tf, methods, facts=a)      # facts reused: no second analyze()
        if not bias_allows(bias, su["side"]):
            return None
    # INT-6/PAR-3 (docs/audits/2026-09-24-system-audit.md): the SAME htf gate function live uses
    # (strategy-runner.htf_pass -> bt.bias_allows(bt.lr.bias_at(...))), keyed on the HTF bar closed at or
    # before THIS bar's own decision time -- not the Wyckoff engine's legacy percentile proxy, and not
    # "no gate at all", which is what the ICT path had before this fix. Only evaluated when a run asked
    # for the HTF filter at all (OPTS["htf"]) -- an untouched run (OPTS["htf"]=False, the default) is
    # unaffected, matching the live runner's own `st.get("htf")` per-setup opt-in.
    #
    # Round-4a fix round 1 (code review of a746ffc): `decision_time` must be bar i's own CLOSE
    # (normalized.available_time), not `Tm[i]` (its OPEN, per normalized.py:118) -- `_HTF_TIMES` is built
    # from `available_time` too, so comparing an LTF OPEN against HTF CLOSE timestamps silently misjudged
    # every LTF bar whose open time falls inside the HTF bar that is STILL forming (551/2000 measured
    # boundary bars on BTCUSDT), diverging from live htf_pass() (strategy-runner.py), which reads the last
    # HTF bar closed as of the tick, not one keyed on an open timestamp.
    if OPTS["htf"] and htf_bias_gate(sym, tf, su["side"],
                                     _N.available_time(c[i], tf).isoformat().replace("+00:00", "Z"),
                                     methods) is not True:
        return None
    return su


def _ict_trade(x, i, su):
    """The POST-dedupe half: the trade (or None) that setup `su`, first visible at bar `i`, becomes. A pure
    function of (i, su) and OPTS -- it does not depend on which other setups were seen, which is what lets
    scan_many() compute it per chunk and dedupe afterwards."""
    sym, tf, c, Tm, H, L, C, methods = x.sym, x.tf, x.c, x.Tm, x.H, x.L, x.C, x.methods
    Tm, H, L, C = x.Tm, x.H, x.L, x.C
    n, idx_of_time, hz, b7_kz, K = x.n, x.idx_of_time, x.hz, x.b7_kz, x.K
    mss_i = idx_of_time.get(su["mss"]["time"])
    if mss_i is None:
        return None
    entry = su["entry"]; stop = su["stop"]; target = su["target"]
    far = su["entry_models"]["fill"]   # ict-scan.py setup_candidate: the key is "entry_models", not "entries"
    # ---- the live runner's own two questions, in its own order (CLAUDE.md §37: the backtest runs the
    # live semantics). scripts/strategy-runner.py ict_live_setups asks them at the bar the setup first
    # becomes visible, which is THIS bar `i`:
    #
    #   1. "Has the limit already gone through?"  fvg_fill over mss_i+1 .. i. If price has already reached
    #      the FVG near edge by the time the setup is detectable, the runner refuses -- "already
    #      triggered on an earlier bar ... not a NEW order to place" -- and it is right to: it cannot
    #      place an order into a level price has left, and after a restart it cannot know whether an
    #      earlier process got it. A backtest that books that trade is booking one nobody can have.
    #   2. "Where does it fill?"  from i+1 onward, because the order does not exist until bar i closes.
    #
    # The old code asked only a version of (2), scanning from mss_i+1 -- i.e. it assumed the limit had
    # been resting since the MSS bar, which nobody could have done, since the setup is not detectable
    # until `i` and `i` is often mss_i + 1 or later.
    #
    # Measured, not reasoned about. BTCUSDT 15m 2026-09-09: MSS at 11:45, setup first complete and
    # bias-agreeing at 12:00, FVG near edge reached WITHIN 12:00. The old rule booked a 2.06R trade the
    # live runner refuses; that is §38's "unrealistic execution assumptions" and it is what made the
    # replay parity check fail once the check itself was repaired to use the live window.
    #
    # ICT-8/PAR-7 (docs/audits/2026-09-24-system-audit.md): both fvg_fill calls below are anchored on
    # `mss_i`, matching the live runner's own expiry (strategy-runner.ict_live_setups: bars_left = mss_i +
    # K - (n-1)). The old (2) scanned mss_i+1..i+K -- i.e. i-mss_i bars LONGER than live's own window -- so
    # the backtest could still book a fill live would already have expired. A setup detected after its own
    # window has already closed is refused outright, exactly as live refuses a `bars_left < 0` order.
    if i > mss_i + K:
        return None              # ICT-8/PAR-7: already expired by the time the setup is even detectable -- live would never place this order
    if fvg_fill(su["side"], mss_i, entry, far, stop, H, L, K, i + 1) is not None:
        return None             # the runner would refuse this as already triggered -- so neither may this
    fill = fvg_fill(su["side"], mss_i, entry, far, stop, H, L, K, n)
    if fill is None:         # the limit never filled within its K-bar window: live would hold/expire an unfilled order, not a position
        return None
    fill_bar, outcome = fill
    if OPTS["fx_b6"] == "yes" and any((H[j] >= target) if su["side"] == "long" else (L[j] <= target)
                                      for j in range(mss_i + 1, fill_bar)):
        return None             # B6: the target traded before the limit filled -- the pending order is cancelled
    if b7_kz and not _S.active(Tm[fill_bar]):
        return None             # B7: an index entry outside every session-registry window is not taken
    # INT-7 (docs/audits/2026-09-24-system-audit.md): every ICT trade record needs an `event` id, or
    # simulate()'s one-position-per-symbol rule (`t.get("event") != ev`, both None for two different ICT
    # trades) compares None != None -- False -- and never skips an overlapping ICT trade on the same
    # symbol, contradicting EXECUTION_ASSUMPTIONS["one_position_per_symbol"]. Built from the setup's own
    # sweep+MSS identity (the same tuple `key` above), so two DIFFERENT ICT setups never collide, and the
    # SAME setup detected again would (it cannot reach here twice -- `seen` dedupes it first).
    event = f"{sym}-{su['side']}-ict-{su['sweep']['time']}-{su['mss']['time']}"
    if outcome == "filled_and_stopped":
        # ICT-8: same-bar fill+stop is unknowable from OHLC. Book the pessimistic -1R loss instead of the
        # pre-2026-09-24 behaviour (fvg_fill returned None here and the trade silently vanished from the
        # backtest -- §38 "unrealistic execution assumptions").
        return dict(symbol=sym, tf=tf, side=su["side"], time=Tm[i], event=event, entry=entry, entry_time=Tm[fill_bar],
                    stop=stop, target=target, exit_time=Tm[fill_bar], vol_type=None,
                    outcome="loss", R=-1.0, R_planned=su.get("R"), exit=fill_bar, mfe=0.0, mae=-1.0, bars_held=1)
    w = walk(su["side"], entry, stop, target, H, L, C, fill_bar + 1, hz, Tm=Tm)
    if not w:
        return None
    return dict(symbol=sym, tf=tf, side=su["side"], time=Tm[i], event=event, entry=entry, entry_time=Tm[fill_bar],
                stop=stop, target=target, exit_time=Tm[w["exit"]], vol_type=None, **w)


RUNNER_METHODS = ("WYCKOFF-BOOK", "ICT", "COMBINED-BOOK")
# The proxy "WYCKOFF"/"COMBINED"/"PARTIAL" mechanical-range methods were removed 2026-09-19
# (docs/audits/2026-09-19-knowledge-fidelity.md finding 6: no CHoCH gate, no Phase A/B, TR = rolling
# min/max of the previous R bars -- a "Spring" could fire mid-trend with no accumulation behind it at all).
# WYCKOFF-BOOK (scripts/wyckoff_rules.py) is the only Wyckoff engine left in this file.


_WY_CANDIDATES = {}    # scan()'s per-process cache of _wyckoff_candidates, keyed by history identity (see scan)
WYCKOFF_WINDOW = 300   # bars one live WYCKOFF-BOOK read sees. ONE number for both engines: strategy-runner.WINDOW
                       # and replay() read it, and scan() walks the history in windows of exactly this size, so a
                       # structure the runner could not see (older than its window) is not a backtest trade either.


def wyckoff_fires(side, candles, tf, sym=None):
    """WYCKOFF-BOOK entries that fire on the LAST bar of `candles` -- THE live read. strategy-runner.setups_wyckoff()
    delegates here, and scan() calls it window by window, so the backtest and the runner ask wyckoff_rules the
    same question about the same bars (CLAUDE.md §37), the way ict_setups_live() already does for ICT.

    Why a per-window read and not one detection over the whole history (the shape scan()'s Wyckoff branch had
    until 2026-09-19): wyckoff_rules dates a swing at its pivot bar, but a k-bar pivot is only KNOWN k bars
    later, and the CHoCH stage consumes swing pairs up to one swing beyond the pair it is judging
    (`while j + 2 < len(sw)`). Run over the full series, the detector reported structures whose CHoCH was
    completed by a swing that formed AFTER the SOS and after the Phase D entry bar -- and scan() took the entry.
    XAGUSD 4H, entry 2026-07-20T05:00Z: the structure exists on no causal prefix until five bars after that
    entry. The parity harness (strategy-runner replay()) caught it because the runner never placed it -- it could
    not have. That is §8 look-ahead, and the fix is structural rather than a patch to that one stage: the
    backtest now sees exactly what the runner sees, and any later stage of the detector that leans on later bars
    is causal here by construction. Cost: ~0.5 ms per window, ~50 s over 105 000 15m bars (measured 2026-09-19).

    Returns one dict per firing: leg ("spring" | "phase_d"), t0 (the structure's Spring/SOS time -- the runner's
    signal key, "-D" appended by the caller for Phase D), entry (last close), stop, target, and `rec` (the
    wyckoff_rules record, indexes local to `candles`)."""
    O = [x["open"] for x in candles]; H = [x["high"] for x in candles]; L = [x["low"] for x in candles]
    C = [x["close"] for x in candles]; V = [x.get("volume", 0) for x in candles]; Tm = [x["time"] for x in candles]
    # Batch 1(b) F items: `_wyckoff_candidates` reads bt.OPTS's detection-relevant fx_ keys into a per-call copy
    # of wyckoff_rules.PARAMS (nothing global is written). The live runner (strategy-runner.setups_wyckoff ->
    # this function) never sets these keys, so bt.OPTS.get(k, False) reads v1 there unchanged.
    return _fires_from(side, _wyckoff_candidates(side, O, H, L, C, V, tf, sym), C, Tm, sym=sym, tf=tf)


def _wyckoff_candidates(side, O, H, L, C, V, tf, sym, pivots=None):
    """The wyckoff_rules records of this window that COULD fire on its last bar (a reclaim, test or BU sitting on
    it) -- everything OPTS-independent, so scan() can cache it per window and re-run the gates cheaply for each
    config (stability-report's A/B/C, improve-loop's candidates) instead of re-detecting 100 000 windows apiece.

    "OPTS-independent" has ONE sanctioned exception: the four detection fx_ keys, read here through
    `_fx_detection_opts()` and applied, with this tf's spring_max_bars_outside, to a PER-CALL COPY of
    wyckoff_rules.PARAMS -- the global dict is never written, so there is no state to restore on a cache hit or
    after an exception. Every caller that caches this function's output (scan()) keys the cache on those four
    keys (`ck`); the first eight parameters are unchanged so diagnose-methods.py's counting wrapper still fits it.

    `pivots` (scan_many only, byte-identical): this window's k-bar pivots, pre-computed once per series --
    `wyckoff_rules.window_pivots(pivot_index(H_full, L_full, k), a, len(window), k, swap=(side == "short"))`, k being
    `wp["pivot"]`. None (scan() and every other caller) = the detector finds them itself."""
    wp = _wy_params(P[tf]["sob"])
    last = len(C) - 1
    vkind = "tick" if (sym and _I.is_tick_volume(sym)) else "traded"   # wyckoff_rules R0 / WMT p131-133
    # A1: routed through scripts/structures.py, the one structure source (ADR 0009), via its raw hot-path
    # pass-through `wyckoff_records()` -- see structures.py's module docstring, "Hot-path / cold-path split"
    # (A1 code review round 1, item 4): this runs once per window of a backtest (scan()'s _WY_CANDIDATES cache
    # builder below calls it up to ~100 000 times), so it must not build the enriched trading_range envelope --
    # and must not allocate a per-window `candles` list just to timestamp it -- when nothing on this path reads
    # either. `wyckoff_records()` IS `W.detect_accumulations(...)`/`W.detect_distributions(...)` (P= the per-call
    # `wp` copy of W.PARAMS built above) -- byte-identical to the pre-A1 direct call when no fx_ key is set.
    recs = _structures.wyckoff_records(O, H, L, C, V, P=wp, volume_kind=vkind, side=side, pivots=pivots)
    return [r for r in recs if (r["bu"] and r["bu"]["bar"] == last) or r["reclaim"] == last or r["test"] == last]


def _fires_from(side, recs, C, Tm, sym=None, tf=None):
    """The OPTS-dependent half of the read: gates, leg choice, stop/target, placeability -- on the last bar.

    `sym`/`tf` are optional (default None, matching every existing caller/test that constructs `_fires_from`
    calls positionally with 4 args): they are read ONLY by the W7 fx_w7_htf_target branch below, to load the
    higher-timeframe companion series. Every other gate here is unaffected by their absence."""
    last = len(C) - 1; out = []
    for r in recs:
        # --- đối nhãn (WA p150-165), wyckoff_rules R3/R3b. BOTH signs are RECORDED on every structure and
        # NEITHER gates by default, and that symmetry is the point.
        # Dấu hiệu 1 defaulted ON for part of 2026-09-19 on the strength of WA p150 ("Nếu ST ở 1/3 phần dưới
        # Trading Range ... dấu hiệu để nhận dạng sớm tái phân phối hoặc phân phối") and was turned back off
        # the same day, for the same reason the sloped gate was: the book states a SIGN for early
        # identification, and "therefore refuse the trade" is an inference on top of it. The section these
        # come from is titled "những thử nghiệm trong các Phase" -- tests for judging a structure WHILE IT IS
        # FORMING -- and it closes by saying outright that "trong diễn biến thực tế của thị trường, chúng ta
        # không thể thực sự biết đó là tích lũy hay phân phối" (WA p167). A veto the source does not state is a
        # project rule, and a project rule wearing the book's authority is what the 2026-09-19 knowledge audit
        # exists to remove. What IS the book's: the thirds themselves (WA p150), which is why the signs use
        # 1/3 and 2/3 and not the half this code used before. Whether to gate on them is a §41 hypothesis with
        # a measurable answer -- run it with --st-gate and compare, rather than assuming.
        # Measured cost of defaulting Dấu hiệu 1 on, BTCUSDT: 4H WYCKOFF-BOOK 11 -> 9 structures and
        # COMBINED-BOOK 1 -> 0; 15m (20 000 bars) WYCKOFF-BOOK 6 -> 5.
        if OPTS["st_gate"] and r.get("st_sign") == "contradicts":
            continue
        if OPTS["phase_b_gate"] and r.get("phase_b_sign") == "contradicts":
            continue
        # sloped_gate stays OFF by default, and that is a reading of the book, not an omission. It was flipped
        # ON on 2026-09-19 on the strength of WA p170 ("Tôi không khuyến khích mọi người giao dịch với những
        # mẫu hình dốc như thế này") and flipped back the same day when the cost was measured. Three reasons,
        # in order of weight:
        #   1. The book TEACHES the four sloped variants over fifteen pages (WA p167-181) with their own
        #      entries (Spring[C], UTAD[C], LPSY[C]/[D]) and closes with "tất cả đều là biến thể của cấu trúc
        #      nằm ngang" (WA p180-181). A rule that discards them discards the book's own material.
        #   2. The discouragement is SCOPED. This repo's own extraction reads it as WA2-42: "IF you are a
        #      first-time Wyckoff operator, THEN use only horizontal schematics" (knowledge/wyckoff/advance.md:1113).
        #   3. The threshold is ours, not the book's. `slope_max_tr = 0.35` is a PROJECT parameter and the book
        #      says in the same breath that there is "không có một quy chuẩn nào về độ dốc" (WA p170). Gating
        #      by default on a number the source says does not exist is precisely the unlabelled-invention
        #      this week's audit exists to remove.
        # Measured cost of defaulting it on, BTCUSDT 15m, last 20 000 bars: WYCKOFF-BOOK 23 -> 5 structures
        # (-78 %) and COMBINED-BOOK 1 -> 0.
        if OPTS["sloped_gate"] and r["sloped"]:
            continue
        if OPTS["st_min"] is not None and r["st_pct"] < OPTS["st_min"]:
            continue
        if OPTS.get("fx_w_touch", "off") == "on" and r["path"] == "spring":
            # W-TOUCH (advance.md 2.11.2, WA p154): "two tests of each TR border before a Spring counts" -- the
            # RECORDED Phase-B test counts (R3b `phase_b_tests`), both thirds needing W_TOUCH_MIN. Symmetric, so
            # it reads the same on the inverted (short) frame.
            pbt = r["phase_b_tests"]
            if min(pbt["upper"], pbt["lower"]) < W_TOUCH_MIN:
                continue
        tr = r["tr_hi"] - r["tr_lo"]; t0 = Tm[r["spring"] if r["spring"] is not None else r["sos"]]
        if r["path"] == "spring" and not r["shakeout"] and not r["abandon"] and not r["sot_too_strong"] and r["vol_type"] in OPTS["types"]:
            rec = r["reclaim"]; vt = r["vol_type"]; rr = r["rec_ratio"]
            # WY-1 gap (docs/audits/2026-09-24-system-audit.md): the reclaim-vs-test leg choice is Spring
            # semantics (WA p80, Bang 2.1) and cannot be reused unchanged for a short. Upthrust type 1's
            # confirmation is "close below resistance" (the reclaim itself) and type 2 (UTAD)'s optional
            # "UTAD Test" retest is explicitly "not always present" (Bang 2.2, WMT p064,
            # knowledge/wyckoff/modern-tools.md §2.7) -- so a short enters at the reclaim for either volume
            # type instead of waiting on a test that the book itself does not require.
            w_bar = rec if (OPTS["entry"] == "book" and (
                (side == "long" and (vt == 1 or (vt == 3 and rr is not None and rr >= VOL["high_min_ratio"])))
                or (side == "short" and vt in (1, 2))
            )) else r["test"]
            # Only the last bar can be an entry -- earlier bars were earlier reads (the runner's rule, now the
            # backtest's too). An entry whose close already sits beyond its stop or target is not placeable.
            if w_bar == last:
                stop = r["spring_low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + STOP_BUFFER_PCT)
                target = r["tr_hi"] if side == "long" else r["tr_lo"]
                spt = OPTS.get("fx_w_spt", "AR")
                if spt == "ceiling":
                    # W-SPT (WA p85; WMT p273): the running Phase-B UA ceiling (the floor, for a short) instead of AR.
                    target = r["ceiling"]
                elif spt == "VAH":
                    # The TR's Value Area high (WA p259-265; the low, VAL, mirrors it for a short). detect_
                    # distributions has already swapped vah/val into REAL prices, so the short side reads `val`.
                    target = r["vah"] if side == "long" else r["val"]
                if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                    out.append(dict(leg="spring", t0=t0, entry=C[last], stop=stop, target=target, rec=r))
        if OPTS["phase_d"] and r["bu"] and r["bu"]["bar"] == last:
            stop = r["bu"]["low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["bu"]["low"] * (1 + STOP_BUFFER_PCT)
            if OPTS.get("fx_w_stop", "current") == "spring_low" and r["spring_low"] is not None:
                # W-STOP (WMT p271): the stop sits beyond the Spring low, not just the BU/LPS pullback low. A
                # structure with no Spring (the LPS[C] path) has no Spring low, so it keeps the BU stop.
                stop = r["spring_low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + STOP_BUFFER_PCT)
            if OPTS.get("fx_w7_htf_target"):
                # W7 (WA2-19, WA p83-84; plan §2 item A1b "higher-timeframe Wyckoff trading-range detection"):
                # Phase-D target = the HIGHER-timeframe TR's own AR/SOS, not ceiling + a PROJECT multiplier x TR
                # (WA1-06: the book defers P&F counting to a later book, so `d_target_tr` was never a sourced
                # number). "With no HTF TR there is no Phase-D trade" (plan §3 W7 row) -- AWAITING OWNER
                # SIGN-OFF (docs/audits/2026-09-29-wyckoff-fidelity-funnel.md), not adopted.
                # decision_time = the decision bar's CLOSE (normalized.available_time), never Tm[last] (its
                # OPEN) -- the same computation as scan()'s htf_bias_gate call; see _htf_wyckoff_target.
                htf_t = _htf_wyckoff_target(sym, tf, side,
                                            _N.available_time({"time": Tm[last]}, tf).isoformat().replace("+00:00", "Z") if tf else None)
                if htf_t is None:
                    continue
                target = htf_t
            else:
                # WY-3 (docs/audits/2026-09-24-system-audit.md; WA p85, p88-89): the Phase-D target projects from
                # the Phase-B ceiling (the running UA resistance), not the AR-only tr_hi -- a structure whose
                # Phase-B excursion ran past AR before the Spring/LPS[C] has a resistance level beyond AR.
                target = r["ceiling"] + W.PARAMS["d_target_tr"] * tr if side == "long" else r["ceiling"] - W.PARAMS["d_target_tr"] * tr
            if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                out.append(dict(leg="phase_d", t0=t0, entry=C[last], stop=stop, target=target, rec=r))
    return out


def reset_opts():
    """Restore module OPTS to the canonical baseline (`_OPTS_BASE`) -- for a caller (or a test) that mutated
    OPTS.update(...) directly and needs a known-clean starting point without going through `scan(..., opts=)`.
    OPTS isolation, docs/audits/2026-09-24-system-audit.md."""
    global OPTS
    OPTS = dict(_OPTS_BASE)


def _check_fx_registered(o):
    """A typo'd or unimplemented `fx_` key would run the baseline while looking like a variant (and still count toward
    N): refuse any `fx_` key not registered in _OPTS_BASE, and refuse B4 (`fx_b4*`) by name -- the grid declares it
    implemented=false, so no key exists for it."""
    for k in o:
        if k.startswith("fx_b4"):
            raise ValueError(f"{k!r}: B4 (HTF level engaged before the LTF MSS) is not implemented "
                             f"(docs/architecture/v-grid-ict.json, implemented=false); there is no such key")
        if k.startswith("fx_") and k not in _OPTS_BASE:
            raise ValueError(f"{k!r} is not a registered engine key (registered fx_ keys: "
                             f"{sorted(x for x in _OPTS_BASE if x.startswith('fx_'))})")


def _wy_window(sym, tf, n):
    """The window length one WYCKOFF-BOOK/COMBINED-BOOK scan walks (W6: OPTS["fx_w6_window"], 300 = the module's
    WYCKOFF_WINDOW), after refusing an out-of-set V value (`_check_wy_v_opts`) and a window longer than the history.
    Moved verbatim out of scan() so scan_many() validates an overlay exactly as scan() does."""
    _check_wy_v_opts()
    WIN = WYCKOFF_WINDOW if OPTS["fx_w6_window"] == 300 else OPTS["fx_w6_window"]
    if WIN != WYCKOFF_WINDOW and n < WIN:
        # Review round 1 (I3): a window longer than the history yields ZERO windows, which would read as a real
        # "no edge" cell. Refuse instead; the default window is untouched (v1 behaviour byte-identical).
        raise ValueError(f"fx_w6_window={WIN} needs at least {WIN} bars of history, {sym} {tf} has {n}; "
                         f"refusing to report an empty cell as a result")
    return WIN


def _wy_ctx(sym, tf, c, O, H, L, C, Tm, n, K, HZ, PH, PL, want, methods):
    """The per-scan arrays and constants scan()'s WYCKOFF-BOOK/COMBINED-BOOK per-fire body reads."""
    return types.SimpleNamespace(sym=sym, tf=tf, c=c, O=O, H=H, L=L, C=C, Tm=Tm, n=n, K=K, HZ=HZ, PH=PH, PL=PL,
                                 want=want, methods=methods)


def _wy_fire(x, side, f, a, last, trades):
    """The POST-dedupe half of scan()'s Wyckoff loop: everything that happens to one fire `f` (of `side`, found
    in the window starting at history bar `a` and ending at bar `last`) after its (side, t0, leg) key was first
    seen -- htf gate, the WYCKOFF-BOOK trade(s), the COMBINED-BOOK ICT leg -- appended to `trades[method]`. Moved
    verbatim out of scan() so scan_many() can run it per chunk; a pure function of its arguments and OPTS."""
    sym, tf, c, O, H, L, C, Tm, n = x.sym, x.tf, x.c, x.O, x.H, x.L, x.C, x.Tm, x.n
    K, HZ, PH, PL, want, methods = x.K, x.HZ, x.PH, x.PL, x.want, x.methods
    r = f["rec"]; t0 = f["t0"]
    # INT-6/PAR-3 (docs/audits/2026-09-24-system-audit.md): the SAME htf gate function live
    # uses for every method (bt.bias_allows(bt.lr.bias_at(...)), strategy-runner.htf_pass),
    # keyed on the LTF DECISION bar's own close time (the bar the structure fires on, matching
    # live's "at the entry tick"), not the legacy rolling-percentile proxy (`htf_allows`/
    # `htf_position`, kept below only for their own standalone regression tests --
    # scripts/tests/test_backtesting.py, scripts/tests/test_live_rules.py -- and no longer
    # wired into this gate) and not `t0` (the Spring/SOS time, which for a Phase-D leg can be
    # many bars before the actual BU/entry decision).
    #
    # Round-4a fix round 1 (code review of a746ffc): `decision_time` must be bar `last`'s own
    # CLOSE (normalized.available_time), not `Tm[last]` (its OPEN) -- see the matching fix in
    # ict_setups_live() above for the measured divergence from live htf_pass().
    if OPTS["htf"] and htf_bias_gate(sym, tf, side,
                                     _N.available_time(c[last], tf).isoformat().replace("+00:00", "Z"),
                                     methods) is not True:
        return
    base = dict(symbol=sym, tf=tf, side=side, time=t0, event=f"{sym}-{side}-book-{t0}", support=r["tr_lo"], resistance=r["tr_hi"], vol_type=r["vol_type"], vol_ratio=r["vol_ratio"],
                volume_kind=r["volume_kind"], st_sign=r["st_sign"], phase_b_sign=r["phase_b_sign"],
                st_pct=r["st_pct"], sot=r["sot"], path=r["path"])
    if f["leg"] == "phase_d":
        if "WYCKOFF-BOOK" in want:
            w = walk(side, f["entry"], f["stop"], f["target"], H, L, C, last + 1, HZ, Tm=Tm)
            if w:
                trades["WYCKOFF-BOOK"].append(dict(base, event=base["event"] + "-D", entry=f["entry"], entry_time=Tm[last], stop=f["stop"], target=f["target"], exit_time=Tm[w["exit"]], leg="phase_d", **w))
        return
    if "WYCKOFF-BOOK" in want:
        w = walk(side, f["entry"], f["stop"], f["target"], H, L, C, last + 1, HZ, Tm=Tm)
        if w:
            trades["WYCKOFF-BOOK"].append(dict(base, entry=f["entry"], entry_time=Tm[last], stop=f["stop"], target=f["target"], exit_time=Tm[w["exit"]], leg="spring", **w))
    if "COMBINED-BOOK" in want and r["reclaim"] is not None:
        # Window-local structure indexes -> history indexes for the ICT leg, which walks FORWARD
        # from the reclaim on the full arrays (an MSS/FVG that forms later is later information,
        # used later). The structure is only KNOWN at `last`, its fire bar: an ICT entry the leg
        # finds before that bar would be taken on a structure nobody had yet identified.
        ict = find_ict(side, a + r["spring"], a + r["reclaim"], H, L, C, K, n, PH, PL, O)
        if ict:
            mss, edge, far = ict
            fill = fvg_fill(side, mss, edge, far, f["stop"], H, L, K, n)
            # INT-3 (docs/audits/2026-09-24-system-audit.md): before this fix, a `fill is None`
            # (price never returned to the FVG edge within the K-bar window) fell back to a
            # MARKET entry at the MSS close (`mss, C[mss]`) -- a decision that could only be
            # made by looking K bars into the future to see whether the retrace happened, since
            # "fill is None" is itself only known after scanning mss+1..mss+K. Runaway moves got
            # the favourable MSS-close price and retracing ones got the FVG price: hindsight,
            # exactly what assess_run()'s own look_ahead check already assumed this path could
            # no longer produce. COMBINED-BOOK's entry model is the SAME return-to-FVG LIMIT ICT
            # uses (this leg IS the ICT confirmation, methods.json's COMBINED-BOOK.entry=
            # "market" describes the WYCKOFF leg, not this one) -- an order that never fills is
            # not a trade, exactly as ict_setups_live() already treats it. runnable=false, so
            # this cannot reach the pilot selection either way; fixed per CLAUDE.md §37 regardless.
            if fill is None:
                return
            e_bar, outcome = fill
            if e_bar < last:
                return          # already triggered on an earlier window -- not a NEW firing here
            if outcome == "filled_and_stopped":
                # ICT-8, applied to the same shared fvg_fill(): same-bar fill+stop is unknowable
                # from OHLC -- book the pessimistic -1R loss rather than silently dropping it.
                stop_dist = abs(edge - f["stop"])
                rp = abs(f["target"] - edge) / stop_dist if stop_dist else None
                trades["COMBINED-BOOK"].append(dict(base, entry=edge, entry_time=Tm[e_bar], stop=f["stop"], target=f["target"],
                                                    exit_time=Tm[e_bar], via="fvg", outcome="loss", R=-1.0, R_planned=rp,
                                                    exit=e_bar, mfe=0.0, mae=-1.0, bars_held=1))
                return
            cw = walk(side, edge, f["stop"], f["target"], H, L, C, e_bar + 1, HZ, Tm=Tm)
            if cw:
                trades["COMBINED-BOOK"].append(dict(base, entry=edge, entry_time=Tm[e_bar], stop=f["stop"], target=f["target"], exit_time=Tm[cw["exit"]], via="fvg", **cw))


def scan(sym, tf, only=None, opts=None):
    """`only`: which of RUNNER_METHODS to compute; None (default) computes all three. A caller that needs exactly
    one method's trades should pass e.g. only=("ICT",) so scan() SKIPS the other methods' work rather than
    computing and discarding it -- in particular so it never calls the live ICT scanner (ict_setups_live, one
    ict-scan.analyze() per bar) when nobody asked for ICT trades. strategy-runner.replay() checks one method at
    a time across 9 symbols; before this, it paid the full live-scanner cost for ICT on every call regardless
    (code-quality review, 2026-09-13). NOT the same axis as OPTS["methods"] -- that key holds the wyckoff/ict BIAS
    DIMENSIONS the live rules read (resolve_methods/engaged_methods_for_market); `only` here names RUNNER methods
    (WYCKOFF-BOOK, ICT, COMBINED-BOOK). Deliberately a different name (`only`, not `methods`) so the two never collide.

    `opts` (OPTS isolation, docs/audits/2026-09-24-system-audit.md): an explicit dict of OPTS overrides for THIS
    call only, applied on top of the frozen `_OPTS_BASE` -- never on top of whatever the mutable module-level
    OPTS happens to hold when this is called. `opts=None` (the default) leaves OPTS exactly as the caller left
    it, unchanged from before this parameter existed (main()'s own OPTS.update(...) CLI wiring keeps working).
    Passing `opts={}` still isolates: it runs the call against the clean baseline with no overrides at all,
    which is the fix for the "stale OPTS leaks into an unrelated call" defect this parameter exists to close."""
    if opts is not None:
        global OPTS
        saved = OPTS
        OPTS = dict(_OPTS_BASE, **opts)
        try:
            return scan(sym, tf, only=only, opts=None)
        finally:
            OPTS = saved
    _check_fx_registered(OPTS)
    want = set(RUNNER_METHODS) if only is None else set(only)
    c, src = load(sym, tf)
    if not c:
        return None
    p = P[tf]; R, K, T, HZ = p["R"], p["K"], p["T"], p["H"]
    H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]; V = [x.get("volume", 0) for x in c]; Tm = [x["time"] for x in c]; O = [x["open"] for x in c]
    n = len(c); trades = collections.defaultdict(list)
    # PH/PL feed only COMBINED-BOOK's ICT leg (find_ict): skipped when that method was not asked for (they are pure
    # functions of the series, so skipping them changes no output).
    PH = all_pivots(H, "high") if "COMBINED-BOOK" in want else None; PL = all_pivots(L, "low") if "COMBINED-BOOK" in want else None
    # INT-6/PAR-3 (docs/audits/2026-09-24-system-audit.md): `methods` resolved ONCE, reused by both the
    # WYCKOFF-BOOK/COMBINED-BOOK htf gate below and the ICT branch's own htf gate (ict_setups_live), so the two
    # methods can never be asked the giảm-khung question with different bias-reading dimensions in the same run.
    methods = resolve_methods(sym)
    # ---------- WYCKOFF-BOOK / COMBINED-BOOK (scripts/wyckoff_rules.py: CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D) ----------
    if want & {"WYCKOFF-BOOK", "COMBINED-BOOK"}:
        # Window by window, exactly the live read -- wyckoff_fires() says why. A structure fires once per leg, at
        # the one bar the runner would have entered on; later windows re-find the same structure under the same
        # t0 and are dropped here, as replay() drops them.
        # W6 (plan §3, fidelity §3.3 B1): OPTS["fx_w6_window"] 300 (the baseline) = the module's WYCKOFF_WINDOW, the
        # ONE number the live runner also reads; 600 is the V value. It is a component of the cache key below.
        seen = set(); WIN = _wy_window(sym, tf, n)
        # Detection is the cost (~0.5 ms/window) and does not depend on the GATING half of OPTS; the gates do.
        # So the per-window candidates are computed once per history in this process and every config re-runs
        # only the gates -- EXCEPT the four fx_w1/w2/w3/w5 keys (Batch 1(b) F items), which change DETECTION
        # itself, so they widen the cache key below the same way a different `sym`/`tf`/history does; two
        # configs differing only in one of those keys must never collide on this cache (they are NOT
        # OPTS-independent in the way this comment used to claim for every key).
        ck = (sym, tf, n, Tm[0], Tm[-1], WIN) + _wy_detection_ck()
        if ck not in _WY_CANDIDATES:
            _WY_CANDIDATES[ck] = {(side, k): _wyckoff_candidates(side, O[k - WIN:k], H[k - WIN:k], L[k - WIN:k], C[k - WIN:k], V[k - WIN:k], tf, sym)
                                  for k in range(WIN, n + 1) for side in ("long", "short")}
        cands = _WY_CANDIDATES[ck]
        x = _wy_ctx(sym, tf, c, O, H, L, C, Tm, n, K, HZ, PH, PL, want, methods)
        for k in range(WIN, n + 1):
            last = k - 1; a = k - WIN
            for side in OPTS["sides"]:
                cs = cands[(side, k)]
                if not cs:
                    continue
                for f in _fires_from(side, cs, C[a:k], Tm[a:k], sym=sym, tf=tf):
                    key = (side, f["t0"], f["leg"])
                    if key in seen:
                        continue
                    seen.add(key)
                    _wy_fire(x, side, f, a, last, trades)
    # ---------- ICT only ----------
    # The LIVE scanner (scripts/ict-scan.py + scripts/htf_context.py, via scripts/live_rules.py) decides every
    # structure -- pivot, sweep, MSS, FVG, dealing range, bias -- so the backtest measures the system actually
    # traded (audit 2026-09-13). The pre-2026-09-13 in-file proxy this branch used to fall back to under
    # `--rules legacy` is gone (Task 8, 2026-09-13): the evidence gate was met
    # (the legacy-vs-live comparison, deleted with the legacy engine on 2026-09-13 -- docs/plans/2026-09-13-collapse-to-one-system.md Task 4:
    # live's profit factor beat legacy on every timeframe
    # measured and legacy blew the account up twice where live never did), so the second implementation is dead
    # weight. Skipped entirely (never calls the live scanner) when "ICT" is not in `only` -- see scan()'s docstring.
    if "ICT" in want:
        trades["ICT"] = ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, methods)
    return dict(symbol=sym, tf=tf, source=src, bars=n, first=Tm[0], last=Tm[-1], trades=trades)


def _dims_for(method):
    """The methodology dimension(s) `method` (a RUNNER_METHODS name) requires, from
    docs/architecture/methods.json runner_methods[method]['requires'] -- e.g. WYCKOFF-BOOK -> ('wyckoff',),
    COMBINED-BOOK -> ('wyckoff', 'ict'). ONE reader (`scripts/methods.py`), not a second copy of the mapping."""
    return tuple(_M.RUNNER_METHODS[method]["requires"])


def scan_for_trader(sym, tf, trader_id, only=None):
    """`scan()`, with OPTS tightened per RUNNER METHOD by `trader_id`'s §0.9 constraints for that method's
    OWN methodology dimension(s) -- never a constraint from one methodology applied to a method that does not
    require it (CLAUDE.md §17: methodology-specific state is never merged). Returns the same shape as
    `scan()` (one dict of trades across every wanted RUNNER_METHODS name), so a caller with `trader_id=None`
    could call either function interchangeably.

    Implementation note: `OPTS` is a module-level dict every scan-path function reads as a free variable, so
    tightening it PER METHOD means giving each method's own `scan(..., only=(method,))` call its OWN isolated
    OPTS via `scan(..., opts=tightened)` -- OPTS isolation (docs/audits/2026-09-24-system-audit.md): before
    this, the per-method OPTS was assigned to the bare module global and restored by hand in a `finally`, which
    is exactly the "one caller's mutation becomes the next caller's silent starting point" shape the round-4a
    OPTS-isolation finding is about, just written out at this call site instead of inside scan() itself.
    scan()'s own `opts=` parameter now owns the save/restore, so this call site no longer needs to."""
    want = set(RUNNER_METHODS) if only is None else set(only)
    # `base` is deliberately the CURRENT module OPTS (main()'s CLI wiring runs OPTS.update(...) once before
    # scanning starts, and that IS this run's chosen configuration -- unlike scan(opts=...)'s isolation, which
    # exists for a caller that must NOT inherit an unrelated earlier call's leftover state). Per-method
    # tightening below still runs through scan(..., opts=tightened) so each method's own call is isolated from
    # the OTHER methods' tightened OPTS in this same loop (OPTS isolation, docs/audits/2026-09-24-system-audit.md).
    base = dict(OPTS)
    combined = None
    all_trades = {}
    for method in RUNNER_METHODS:
        if method not in want:
            continue
        tightened = base
        for dim in _dims_for(method):
            tightened = _TC.overlay(tightened, trader_id, dim)
        r = scan(sym, tf, only=(method,), opts=tightened)
        if r is None:
            return None
        if combined is None:
            combined = {k: v for k, v in r.items() if k != "trades"}
        all_trades[method] = r["trades"].get(method, [])
    if combined is None:
        return None
    combined["trades"] = all_trades
    return combined


def trader_sessions_for(trader_id):
    """The session set `trader_id`'s constraints narrow this run to (the union of every methodology dimension
    that declares a `sessions` item), or `None` when the trader declares no session constraint at all.

    Shared by `main()`'s `--trader` wiring and `scripts/improve-loop.py` so the two never compute this
    differently. Read at the CURRENT `OPTS` (any dict works -- `overlay()` only reads keys it knows about),
    which is why this can be called safely both before and after `scan_for_trader()` has run."""
    if not trader_id:
        return None
    allowed = None
    for dim in ("wyckoff", "ict"):
        s = _TC.overlay(OPTS, trader_id, dim).get("_sessions")
        if s is not None:
            allowed = s if allowed is None else (allowed & s)
    return allowed


#: §33 facts this engine cannot produce, declared rather than omitted. An omitted fact makes the rule that
#: needs it silently inapplicable, which is how an account limit disappears without anyone deciding to remove
#: it. `consec_errors` counts EXECUTION failures (a rejected order, a venue timeout) and a backtest has no
#: execution layer, so the rule that reads it can never fire here and the run says so.
UNAPPLICABLE_ACCOUNT_FACTS = {
    "consec_errors": "a backtest submits no orders, so it cannot observe an execution failure",
}


def load_account(args):
    """The account this run measures against, from `--account <profile-id>` / `--account-file <path>` --
    mutually exclusive, since both are answers to "whose rules?" and a run has exactly one account.

    THE one loader (A3, docs/plans/2026-09-18-close-feature-gaps.md §0.3): `stability-report.py` calls this
    too rather than keeping its own copy of the same five lines, which is how the two reports drifted on what
    `--account` even means before this fix (audit row 1: only stability-report.py had the flag at all).

    `--account` reads docs/architecture/account-profiles.json by id. `--account-file` evaluates a JSON profile
    ad hoc, without shipping it as configuration (§57) -- "what would this look like under my prop firm's
    rules?" when no such account is declared here; the file's basename becomes its `id` if it declares none.
    """
    account = getattr(args, "account", None)
    account_file = getattr(args, "account_file", None)
    if account and account_file:
        raise SystemExit("--account and --account-file are two different answers to 'whose rules?'; pass one")
    if account:
        return _AP.get(account)
    if account_file:
        acc = json.load(open(account_file, encoding="utf-8"))
        acc.setdefault("id", os.path.basename(account_file).rsplit(".", 1)[0])
        return acc
    return None


def _account_stop(profile, equity, peak, day_start, day, realised_today, consec_losses,
                  profit_by_day, profit_by_symbol):
    """Has this account FAILED, by its own declared rules? Returns the rule id that ended it, or None.

    CLAUDE.md §33's point, arriving in research: a personal account and a prop account do not lose in the same
    way. A personal account is only finished when the money is gone -- that is `RUIN_FRAC`, and it is what this
    engine assumed for every account until 2026-09-18. A prop account fails at a daily loss, at a drawdown
    measured from the peak or from the starting equity, long before the balance is anywhere near zero; a setup
    that survives the first and fails the second is the ordinary case, not an exotic one, and ranking both
    against "blown" alone cannot tell them apart.

    The rules are NOT reimplemented here -- `scripts/account_profile.py` is the one reader and already drives
    every limit. This walks the equity curve and asks it.

    ONE THING THIS CANNOT TELL APART, and it decides whether a result means anything
    --------------------------------------------------------------------------------
    §33's `action: HALT` covers two different facts and the profile does not separate them:

      * **terminal** -- a prop challenge breached its drawdown: the account is GONE, there is nothing to
        resume, and ending the run is exactly right;
      * **circuit-breaker** -- `pilot-mt5-demo`'s "five consecutive losses stops the account": the live runner
        stops and a HUMAN decides whether to resume. Over years of history, treating that as terminal kills
        every row in its first losing streak and measures "how long until five losses", not the setup.

    So a HALT ends the run HERE, which is right for the first kind and overstates the second. That is why no
    account is applied by default: passing one is a deliberate question ("what would this look like under these
    rules?"), not a silent change to what every number means. Until a profile can say which kind a rule is,
    reading a `--account` run means knowing which kind its rules are.

    SCALE, not just survival (found 2026-09-18 running the FTMO/The5ers profiles through this for the first
    time, A3 evidence run): this engine tracks equity at a fixed notional START ($10,000, a readability
    constant unrelated to any real account -- see START's own comment). A rule whose `basis` is
    "initial_balance" is read by `account_profile._basis_value` as the PROFILE's OWN declared dollar figure
    (e.g. $100,000), because on the LIVE path equity genuinely is in that account's real currency and the two
    already agree. Feeding this engine's $10,000-scaled equity into that same comparison unconditionally
    breaches a $90,000 floor on trade one, regardless of R. Fixed-fractional % returns are scale-invariant, so
    every equity-shaped fact below is rescaled onto the profile's own declared balance when it has one --
    changing the UNITS the comparison is made in, not the PERCENTAGE outcome a declared rule fires at.
    """
    if profile is None:
        return None
    ib = (profile.get("rules") or {}).get("initial_balance")
    scale = (ib["amount"] / START) if (isinstance(ib, dict) and isinstance(ib.get("amount"), (int, float))
                                       and not isinstance(ib.get("amount"), bool) and START) else 1.0
    facts = {"equity": equity * scale, "equity_start": START * scale, "day_start_equity": day_start * scale,
             "peak_equity": peak * scale, "initial_balance": START * scale, "trading_day": day,
             "realised_today": realised_today * scale, "consec_losses": consec_losses,
             "profit_by_day": {k: v * scale for k, v in profit_by_day.items()},
             "profit_by_symbol": {k: v * scale for k, v in profit_by_symbol.items()}}
    act, why = _AP.halt_check(profile, facts)
    return why if act in _AP.BLOCKING else None


def _venue_for_symbol(sym):
    """The unattended execution venue alias for `sym`'s market ("futures" | "mt5"), or None when the symbol's
    market has no declared unattended venue -- see scripts/providers.py unattended_venue_for. Wrapped so a
    symbol this engine has no venue model for degrades to "no venue-specific model" rather than raising out of
    a hot per-trade loop (INT-4/PAR-2, PAR-4/DEC-4 both key their fee/sizing model off this)."""
    market = _I.market_of(sym)
    if market is None:
        return None
    try:
        return _P.unattended_venue_for(market)
    except ValueError:
        return None


#: PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): which account-profiles.json profile this engine reads
#: leverage from, per market, so `_risk_scale` models the SAME notional cap strategy-runner.futures_leverage()
#: does (AP.max_leverage(profile("futures"))) without importing strategy-runner.py itself (strategy-runner.py
#: already imports this module as `bt`; the reverse import would be circular).
#:
#: Round-4a fix round 1 (code review of a746ffc), nit #5: these ids are a HAND-COPIED restatement of what
#: `account_profile.for_venue(venue, "demo")` resolves live (`for_venue("futures", "demo")["id"] ==
#: "pilot-binance-futures-testnet"`, `for_venue("mt5", "demo")["id"] == "pilot-mt5-demo"`, verified at the
#: time of writing) -- NOT a call to `for_venue` itself, because `for_venue` refuses outright the moment a
#: SECOND demo profile exists on a venue (docs/plans/2026-09-19-multi-account.md), and this backtest engine
#: has no `--account`-style venue selector to disambiguate with the way `strategy-runner.py --account <id>`
#: does. If the demo profile for either venue is ever renamed, or a second demo profile is added on either
#: venue, this dict silently stops matching what live actually sizes against and must be updated by hand --
#: scripts/tests/test_audit_round4_integrity.py::SizingProfileMatchesLiveForVenue pins the match so that
#: drift fails a test instead of silently mis-sizing a backtest.
_SIZING_PROFILE = {"crypto": "pilot-binance-futures-testnet", "cfd": "pilot-mt5-demo"}
NOTIONAL_CAP_PCT = 0.25   # == strategy-runner.NOTIONAL_CAP_PCT (a literal there too, not sourced from config)


def _risk_scale(sym, entry, stop, equity, risk_mult, entry_order_type, exit_order_type):
    """PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): the fraction of the intended risk
    (equity * RISK * risk_mult) this trade can ACTUALLY risk once the same constraints
    strategy-runner.size()/mt5_lots() apply are modelled here too:

      * DEC-4 -- the round-trip fee sits INSIDE the risk budget (risk_usd / (stop_distance + entry*entry_fee +
        stop*exit_fee)), not added on top of it, exactly like strategy-runner.size()'s `per_unit`.
      * PAR-4 -- the futures notional cap (NOTIONAL_CAP_PCT of equity x the account's own declared leverage)
        scales the position down on a tight stop, exactly as it does live; CFD/MT5 has no notional cap
        (mt5_lots only rounds to the broker's lot step), so only futures is capped here, matching live.

    `risk_mult` already carries the 2-consecutive-loss halving (the caller's own `consec_losses`, mirroring
    strategy-runner's `risk_mult = 0.5 if consec_losses >= 2 else 1.0`) -- this function only adds the
    fee-and-cap adjustment on TOP of that multiplier, it does not compute the loss throttle itself.

    Returns `risk_mult` unchanged (no fee/cap adjustment) for a market/venue this engine has no cost or
    leverage model for -- an unmodelled market is no WORSE off than before this fix, only the markets this DOES
    model change."""
    venue = _venue_for_symbol(sym)
    if venue is None:
        return risk_mult
    try:
        entry_fee = _RM.costs(venue, entry_order_type)["fee_pct_per_side"]
        exit_fee = _RM.costs(venue, exit_order_type)["fee_pct_per_side"]
    except _RM.RiskRefused:
        return risk_mult
    per_unit = abs(entry - stop) + entry * entry_fee + stop * exit_fee
    if per_unit <= 0:
        return risk_mult
    risk_usd = equity * RISK * risk_mult
    if risk_usd <= 0:
        return risk_mult
    qty = risk_usd / per_unit
    market = _I.market_of(sym)
    profile_id = _SIZING_PROFILE.get(market)
    leverage = _AP.max_leverage(_AP.get(profile_id)) if profile_id else None
    if leverage:
        cap = equity * NOTIONAL_CAP_PCT * float(leverage)
        if qty * entry > cap:
            qty = cap / entry
    effective_risk_usd = qty * per_unit
    return risk_mult * (effective_risk_usd / risk_usd)


def simulate(trades, fee_pct, account=None, calendar=None, sessions=None, trader=None, entry_order_type=None,
             live_parity_sizing=False, cost_profile=None, spread_stat="median"):
    """`cost_profile` (A0, plan §2): a `real_costs.PROFILES` name. `None` (the default, unchanged from before
    this parameter existed) prices every trade with the existing flat `fee_pct`/`risk_model.cost_r` path
    below -- v1 behaviour, byte-identical. When given, every trade's symbol/side/entry/stop/entry_time/
    exit_time is priced through `real_costs.cost_r` (real per-hour spread + per-night swap) INSTEAD of the
    flat fee for that trade; a symbol this profile has no export for RAISES `real_costs.CostRefused` rather
    than silently falling back to the flat fee, because a caller that asked for real costs and got a guessed
    one would not know it. `spread_stat` ("median" default, "p90" the disclosed stress option) passes through
    to `real_costs.cost_r`.

    `OPTS["fx_admission_entry_cost"]` (O1, default False = v1): with `cost_profile` set, the min_rr ADMISSION
    test normally subtracts the real round-turn cost including the exit-hour half-spread and swap nights, i.e. it
    depends on when the trade exits. When True the admission cost is `cost_r(entry_time, entry_time)`: entry-hour
    half-spread + an exit-leg half-spread ESTIMATED at the entry hour, swap 0 (unknowable), commission as
    recorded. Only the admission test changes; the reported net R keeps the real entry+exit cost.

    Chronological RISK-per-trade compounding account (a trade's own `size` field scales its risk, default
    1.0 -- no current runnable method sets it below 1.0; kept generic rather than hard-coded so a future
    multi-leg method is not a second copy of this loop); one open position per symbol (a trade whose entry
    falls inside an open trade of the same symbol is skipped, except a later trade sharing the SAME `event` id
    as the open one).

    `account` -- an §33 profile. Without one the only loss condition is RUIN_FRAC (the personal-account
    "blown" notion); with one, the profile's own failure rules end the run and SIM_LAST records WHICH.

    `calendar` / `sessions` -- CLAUDE.md §24-§32 / §21 admission-time refusal (§0.3). A candidate trade is
    refused -- never entered, never in `taken`, never on the equity curve -- when its OWN `entry_time` falls
    inside a restricted news window (`event_risk.blocked`) or outside an allowed session (`sessions.primary`).
    PIT: both checks use `entry_time` as BOTH the moment being judged and the decision time -- nothing later
    is consulted, matching CLAUDE.md §8. `account`'s own `news_restrictions` / `session_restrictions` apply ON
    TOP of these (tighten only, never loosen -- `account_profile.tighten_calendar` / the account's own allowed
    sessions intersected in): a profile whose rules are stricter than the CLI flags cannot be widened by them.
    `SIM_LAST["refused"]` records how many candidates each reason cost, so a report can show it was not silent.

    `trader` -- CLAUDE.md §0.9 (docs/plans/2026-09-18-close-feature-gaps.md): the trader id whose OPTS/session
    constraints already narrowed `trades` (via `scan_for_trader()` / `trader_sessions_for()`, applied by the
    CALLER before this function runs -- `simulate()` itself does not resolve trader constraints, only records
    which trader's run this was, exactly as `account` records which account's rules applied).

    `entry_order_type` (INT-4/PAR-2, docs/audits/2026-09-24-system-audit.md): "maker" | "taker" | None
    (default). When given, the round-trip cost is priced per side -- `entry_order_type` on the entry leg,
    ALWAYS "taker" on the exit leg (every exit on this venue is a STOP_MARKET/TAKE_PROFIT_MARKET or a market
    close for the time stop, never a resting maker order, regardless of how the entry was placed) -- via
    `risk_model.cost_r`, keyed on the trade's own symbol's venue. `None` (unchanged from before this
    parameter existed) keeps the single flat `fee_pct` charged on both sides, so every existing caller that
    does not pass it measures exactly what it measured before.

    `live_parity_sizing` (PAR-4/DEC-4): when True, `size` is scaled by `_risk_scale` (the fee-aware,
    notional-cap-aware, loss-throttled sizing strategy-runner.size()/mt5_lots() apply) instead of the bare
    `t.get("size", 1.0)`. False (the default, unchanged from before this parameter existed) keeps every
    existing caller's sizing exactly as it was.

    INT-2 (docs/audits/2026-09-24-system-audit.md): trades are still ADMITTED in entry_time order (the R:R
    floor, the news/session refusal, the account-survival check and the one-position-per-symbol rule are all
    genuinely causal decisions that may only see what already happened by `entry_time`) -- but a trade's P&L
    is no longer added to `equity` the instant it is admitted. Every admitted trade is queued and its P&L is
    booked at its own EXIT time, in EXIT order, so a later trade's sizing and the account-survival check see
    only equity that has actually been REALISED by that trade's own entry_time, never the outcome of a trade
    that is still open. Before this fix, `equity += pnl` ran in entry order, immediately, so a later trade
    (possibly on a different symbol -- the account is shared across symbols, see the module docstring) was
    sized from an EARLIER trade's already-known future outcome, and `max_dd`/the equity curve were built from
    entry-order cumulative values stamped at EXIT timestamps -- a path that never existed. Sizing on the
    equity a trade's own entry_time had ACTUALLY realised is what `equity * RISK * size * net_R` was always
    supposed to mean; this fix makes that true when positions overlap, not just when they happen not to.
    """
    eff_cal = calendar
    if account is not None and calendar is not None:
        eff_cal = _AP.tighten_calendar(account, calendar)   # refuses rather than loosening (§33)
    eff_sessions = set(sessions) if sessions else None
    if account is not None:
        sr = _AP.rule(account, "session_restrictions")
        if sr is not None:
            allowed = set(sr["allowed_sessions"])
            eff_sessions = allowed if eff_sessions is None else (eff_sessions & allowed)
    refused_news = refused_session = 0
    # B-EXIT's 2R component (fx_b_exit "...|no_floor", knowledge/ict/models.md §3.1 rule 23: 2R is "the minimum
    # requirement before taking profit on an open position", not an entry filter): the planned-R:R ENTRY floor
    # below is skipped for ICT trades. Baseline "floor" = v1. ICT trades only, identified by their `event` id form
    # "<sym>-<side>-ict-<sweep>-<mss>" (INT-7; Wyckoff ids are "<sym>-<side>-book-<t0>[-D]", test_v_items_ict pins
    # both forms) -- an explicit `method` field would change every v1 trade record, so the id form is kept.
    lr.ict_scan.check_v_opts({"fx_b_exit": OPTS["fx_b_exit"]})     # a typo'd floor token raises, never runs "floor"
    no_floor_ict = lr.ict_scan.b_exit_parts(OPTS["fx_b_exit"])[2] == "no_floor"
    ts = sorted(trades, key=lambda t: t["entry_time"])
    equity = START; open_pos = {}; curve = []; taken = []; ruin = None
    peak = START; day_start = START; day = None; failed_by = None
    realised_today = 0.0; consec_losses = 0
    profit_by_day, profit_by_symbol = {}, {}
    pending = []   # INT-2: admitted-but-not-yet-realised (trade_dict, pnl, net_R), a min-heap on exit_time
    heap_seq = 0

    def _realise(pnl_item):
        nonlocal equity, peak, realised_today, consec_losses
        t2, pnl, net_R = pnl_item
        equity += pnl
        peak = max(peak, equity)
        realised_today += pnl
        consec_losses = consec_losses + 1 if net_R < 0 else 0
        profit_by_day[t2["exit_time"][:10]] = profit_by_day.get(t2["exit_time"][:10], 0.0) + pnl
        profit_by_symbol[t2["symbol"]] = profit_by_symbol.get(t2["symbol"], 0.0) + pnl
        taken.append(dict(t2, net_R=round(net_R, 3), pnl=pnl))
        curve.append((t2["exit_time"], equity))

    def _flush_through(bound):
        # Round-4a fix round 1 (code review of a746ffc): STRICT `<`, not `<=`. An exit whose exit_time
        # EQUALS the new trade's own entry_time is a same-timestamp tie -- OHLC cannot order two events at
        # the same instant (the same reasoning ICT-8 already applies to a same-bar fill+stop). Treating the
        # tie as "already realised" let a same-timestamp exit's future outcome inflate the equity a new
        # trade is sized against -- reviewer repro: A exits +50R at 01:00, B enters at 01:00 -> B was sized
        # against the POST-A equity (-150.30) instead of the pre-A equity (-100.0), exactly the INT-2 leak
        # this fix closes for every OTHER ordering. Only exits STRICTLY BEFORE the new entry are realised.
        while pending and pending[0][0] < bound:
            _, _, item = heapq.heappop(pending)
            _realise(item)

    stopped = False
    for t in ts:
        # INT-2: realise every exit that had ALREADY happened by this trade's own entry_time BEFORE using
        # `equity`/`peak`/`consec_losses` to admit or size it -- so every downstream decision below sees only
        # outcomes that had actually occurred, never one still open.
        _flush_through(t["entry_time"])
        # CLAUDE.md §37: "the backtest must execute the same logical Trading System and Decision Engine
        # semantics used by live decisions wherever practical." The R:R floor is one of those semantics, and
        # until 2026-09-18 the two paths applied it to DIFFERENT quantities: §34 moved the live gate to R
        # measured NET of fees (scripts/strategy-runner.py rr_reason), while this loop filtered on the GROSS
        # `R_planned` and only then charged the fee. The backtest was therefore taking trades the live runner
        # refuses -- measured at 8,071 admitted trades across BTC/ETH/SOL 15m, of which 392 (5 %) fall below
        # the floor once the venue's own fee is charged. A backtest that admits 5 % of trades its own live
        # system would decline is not measuring that system.
        #
        # RESEARCH-SEMANTICS CHANGE (§59): every stability report and every `pilot-selection.json` backtest block
        # produced before this date was computed under the gross convention and is NOT comparable to a run
        # after it. They are deliberately not regenerated here -- see SYSTEM-DESIGN.md §45.
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        if cost_profile is not None:
            # A0 (plan §2): real per-hour spread + per-night swap REPLACES the flat fee for this trade --
            # refuses rather than falling back, see the parameter's own docstring.
            cr = _RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["exit_time"], t["symbol"], t["side"],
                            cost_profile, spread_stat=spread_stat)
            fee_R = cr["total_R"]
            adm_fee_R = fee_R
            if OPTS.get("fx_admission_entry_cost"):
                # O1: admission may use ONLY what is knowable at the entry decision (CLAUDE.md §8/§37). The exit
                # time/hour is not, so price both legs at the ENTRY hour (entry half-spread + the same half-spread
                # as the exit-leg estimate), no swap (nights held depend on the exit), commission as recorded.
                # `fee_R` (real entry+exit cost) still prices the REPORTED net R below.
                adm_fee_R = _RC.cost_r(t["entry"], t["stop"], t["entry_time"], t["entry_time"], t["symbol"],
                                       t["side"], cost_profile, spread_stat=spread_stat)["total_R"]
        elif entry_order_type is not None:
            # INT-4/PAR-2: entry and exit priced SEPARATELY -- the entry pays this run's own order type, the
            # exit ALWAYS pays taker (every exit on this venue is a market-on-trigger order).
            venue = _venue_for_symbol(t["symbol"])
            if venue is not None:
                try:
                    fee_R, _ = _RM.cost_r(t["entry"], t["stop"], venue, entry_order_type, exit_order_type="taker")
                except _RM.RiskRefused:
                    fee_R = 2 * fee_pct / dist
            else:
                fee_R = 2 * fee_pct / dist
        else:
            fee_R = 2 * fee_pct / dist
        if cost_profile is None:
            adm_fee_R = fee_R          # flat fee: does not depend on the exit, nothing to split
        if t.get("R_planned", 99) - adm_fee_R < OPTS["min_rr"] and not (
                no_floor_ict and "-ict-" in (t.get("event") or "")):
            continue
        # §24-§32 / §21 admission-time refusal, PIT on entry_time alone. Refused candidates never reach the
        # account-stop check below and never touch equity -- a refusal is not a loss, it is a trade that was
        # never taken (CLAUDE.md §36: only REQUIRED_FOR_DECISION inputs gate entry, and these are both).
        if eff_cal is not None:
            is_blocked, _why = _ER.blocked(t["symbol"], at=t["entry_time"], decision_time=t["entry_time"], cal=eff_cal)
            if is_blocked:
                refused_news += 1
                continue
        if eff_sessions is not None and _S.primary(t["entry_time"]) not in eff_sessions:
            refused_session += 1
            continue
        # The account's own rules first -- a prop account is finished long before the balance hits RUIN_FRAC.
        if account is not None:
            d = t["entry_time"][:10]
            if d != day:
                day, day_start, realised_today = d, equity, 0.0
            stop = _account_stop(account, equity, peak, day_start, day, realised_today, consec_losses,
                                 profit_by_day, profit_by_symbol)
            if stop:
                failed_by = failed_by or stop
                ruin = ruin or (curve[-1][0] if curve else t["entry_time"])
                stopped = True
                break
        if equity <= RUIN_FRAC * START:
            ruin = ruin or (curve[-1][0] if curve else t["entry_time"])
            failed_by = failed_by or (f"equity <= {RUIN_FRAC:.0%} of the starting balance (no account "
                                      f"profile supplied, so the only loss condition is a blown account)")
            stopped = True
            break
        until, ev = open_pos.get(t["symbol"], ("", None))
        if t["entry_time"] < until and t.get("event") != ev:
            continue
        open_pos[t["symbol"]] = (max(until, t["exit_time"]) if t.get("event") == ev else t["exit_time"], t.get("event"))
        net_R = t["R"] - fee_R
        if live_parity_sizing:
            # PAR-4/DEC-4: sized on equity as REALISED at this trade's own entry_time (INT-2), with the same
            # loss-throttled, fee-aware, notional-cap-aware formula strategy-runner.size()/mt5_lots() use. A
            # trade's own declared `size` field (a future multi-leg method) still scales on TOP of this, exactly
            # as it scaled on top of the flat 1.0 before this parameter existed.
            risk_mult = 0.5 if consec_losses >= 2 else 1.0
            scale = _risk_scale(t["symbol"], t["entry"], t["stop"], equity, risk_mult,
                                entry_order_type or "taker", "taker")
            size = t.get("size", 1.0) * scale
        else:
            # Unchanged from before this parameter existed: no loss throttle, no fee/cap adjustment.
            size = t.get("size", 1.0)
        pnl = equity * RISK * size * net_R
        heapq.heappush(pending, (t["exit_time"], heap_seq, (dict(t), pnl, net_R))); heap_seq += 1
    post_ruin = []
    if not stopped:
        # Every admitted-but-not-yet-realised trade still resolves: its ENTRY already happened (a causal
        # decision), and its EXIT is a future observation of price action, which CLAUDE.md §37 explicitly
        # allows ("future market movement may determine stop hit, target hit ... but may not influence
        # entry"). This is the ordinary end-of-history drain, not a post-ruin one.
        while pending:
            _, _, item = heapq.heappop(pending)
            _realise(item)
    else:
        # Round-4a fix round 1 (code review of a746ffc), should-fix #4: a failed/ruined account does not
        # keep trading. Before this, every still-open admitted trade's future P&L was ALSO drained into
        # `equity`/`curve`/`taken` after the `stopped` break above -- so the reported FINAL equity and
        # drawdown reflected price action that happened AFTER the account was already declared failed,
        # which could make a failed run look better (or worse) than the equity it actually failed at. The
        # reported `equity`/`curve`/`taken` are now PINNED at the failure point: nothing below advances
        # `equity` or appends to `curve`/`taken`. Already-admitted-but-not-yet-realised trades are recorded
        # separately, as a diagnostic only (SIM_LAST["post_ruin"]) -- what they WOULD have done, never
        # folded into the numbers a caller reads as "the result of this run".
        while pending:
            _, _, (t2, pnl, net_R) = heapq.heappop(pending)
            post_ruin.append(dict(t2, net_R=round(net_R, 3), pnl=pnl))
    curve.sort()
    if equity <= RUIN_FRAC * START and ruin is None:
        ruin = curve[-1][0]
        failed_by = failed_by or "equity <= 10% of the starting balance"
    SIM_LAST["ruin"] = ruin
    SIM_LAST["failed_by"] = failed_by
    SIM_LAST["account"] = (account or {}).get("id")
    SIM_LAST["rules_not_applicable"] = sorted(UNAPPLICABLE_ACCOUNT_FACTS) if account else []
    SIM_LAST["refused"] = {"news": refused_news, "session": refused_session}
    SIM_LAST["trader"] = trader
    SIM_LAST["post_ruin"] = post_ruin
    return equity, curve, taken


SIM_LAST = {"ruin": None, "failed_by": None, "account": None, "rules_not_applicable": [],
           "refused": {"news": 0, "session": 0}, "trader": None, "post_ruin": []}   # how the last simulate()
           # ended, under whose account rules and whose §0.9 trader constraints. `post_ruin` (round-4a fix
           # round 1, should-fix #4): trades that were admitted before the account failed but never got to
           # realise -- a diagnostic only, never folded into the returned equity/curve/taken.


def period_returns(curve, first, last, key):
    """Returns per period from the equity curve (equity at end of period vs end of previous period)."""
    eq_by = {}
    for t, e in curve:
        eq_by[key(t)] = e
    periods = sorted(set(key(t) for t, _ in curve) | {key(first), key(last)})
    out = []; prev = START
    for pkey in periods:
        e = eq_by.get(pkey, prev)
        out.append((pkey, (e / prev - 1) * 100)); prev = e
    return out


def month_key(t): return t[:7]
def quarter_key(t): return f"{t[:4]}-Q{(int(t[5:7]) - 1) // 3 + 1}"
def year_key(t): return t[:4]


def period_keys(res, key):
    """Row labels for the year/quarter/month tables: the UNION across every method, chronologically.

    Was `[k for k, _ in res["WYCKOFF"][key]]` (the "WYCKOFF" proxy method this once read, removed
    2026-09-19 -- docs/audits/2026-09-19-knowledge-fidelity.md finding 6). simulate() stops booking periods
    once a method ruins, and that method ruined in 2023 on this data -- so 2024 and 2025 disappeared from the
    table for EVERY method, including the only profitable one. One method's lifespan must not decide what the
    table shows about the others."""
    return sorted({k for m in res.values() for k, _ in m[key]})


def max_dd(curve):
    peak = START; dd = 0.0
    for _, e in curve:
        peak = max(peak, e); dd = max(dd, (peak - e) / peak)
    return dd * 100


def summarize(taken, *, curve=None, account=None):
    """The report's own five columns, PLUS the full CLAUDE.md §39 set under `perf`.

    The five legacy keys keep their exact names, types and units (win_rate in percent, pf None when there is
    no losing trade) because the markdown table and `stability-report.py` read them positionally; §39's
    twenty-three arrive additively through the one computer, so the two can no longer disagree about what
    'expectancy' means. The legacy `win_rate` also keeps its old denominator convention -- `perf.win_rate`
    is the §39 one, which counts a breakeven trade in the denominator and not in the numerator.
    """
    rs = [t["net_R"] * t.get("size", 1.0) for t in taken]
    if not rs:
        return dict(n=0, perf=_perf.metrics([], equity=curve, account=account))
    wins = [r for r in rs if r > 0]; losses = [r for r in rs if r <= 0]
    return dict(n=len(rs), win_rate=len(wins) / len(rs) * 100, avg_R=statistics.mean(rs), sum_R=sum(rs),
                pf=(sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else None),
                perf=_perf.metrics([dict(t, net_R=t["net_R"] * t.get("size", 1.0)) for t in taken],
                                   equity=curve, account=account))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", default="15m,1H,4H,1D"); ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--bars", type=int, default=None, help="cap every loaded series to its most recent N "
                                                            "bars (test/sandbox speed only, see load()/"
                                                            "limit_bars() -- changes the SAMPLE, not PIT)")
    ap.add_argument("--fee-pct", type=float, default=0.05, help="taker fee per side in percent"); ap.add_argument("--out"); ap.add_argument("--json")
    ap.add_argument("--cost-profile", default=os.environ.get("BT_COST_PROFILE") or None,
                    help="A0 (plan §2): a named real-cost profile (scripts/real_costs.py PROFILES, e.g. "
                         "ftmo_demo_2026_09) priced instead of --fee-pct/the flat mt5 assumption. Unset "
                         "(the default) leaves v1 behaviour byte-identical. Env var BT_COST_PROFILE is the "
                         "fallback default, matching BT_HISTORY_ROOT's own convention.")
    ap.add_argument("--spread-stat", default="median", choices=["median", "p90"],
                    help="which recorded_spread_m15 statistic --cost-profile prices spread from; p90 is the "
                         "disclosed stress option (default median)")
    ap.add_argument("--flat-before-rollover", action="store_true",
                    help="A0 fund-cell rule (plan §2, §6 items 3/5/7): close a position still open at the "
                         "last bar closing before --cost-profile's own server daily rollover, at that bar's "
                         "close (exit_reason=rollover_flat). Off by default (v1 unchanged). Requires "
                         "--cost-profile (the server clock is the profile's own provider).")
    ap.add_argument("--min-rr", type=float, default=MIN_RR, help="skip trades whose PLANNED R (target distance / stop distance) is below this")
    ap.add_argument("--types", default="1,2,3", help="Spring/Upthrust volume types allowed for WYCKOFF-BOOK/COMBINED-BOOK")
    ap.add_argument("--htf", action="store_true", help="higher-timeframe boundary filter (long only when the HTF is in the lower third of its range or above it)")
    ap.add_argument("--sides", default="long,short")
    ap.add_argument("--entry", default="book", choices=["book", "test"], help="Wyckoff entry: 'book' = type-1 at reclaim, others at retest; 'test' = always wait for the retest (WA p80: Test = confirmation)")
    ap.add_argument("--mgmt", default="none", choices=["none", "be"], help="'be' = move stop to entry once +1R is reached (WMT p272)")
    ap.add_argument("--sloped-gate", action="store_true", help="book engine: SKIP sloped structures. OFF by default, and that default is a deliberate reading -- see the note in scan(). The 0.35 slope threshold is a PROJECT parameter; the book states outright that slope has no standard (WA p170)")
    ap.add_argument("--st-gate", action="store_true", help="book engine: REFUSE a structure whose ST[A] sits in the contradicting third of the TR (đối nhãn Dấu hiệu 1, WA p150). Off by default: the book states a sign, not a veto -- see the note in scan(). The sign is recorded either way, as st_sign on every trade")
    ap.add_argument("--phase-b-gate", action="store_true", help="book engine: REFUSE a structure whose Phase-B tests cluster on the contradicting border (đối nhãn Dấu hiệu 2, WA p154). Same status as --st-gate; recorded as phase_b_sign either way")
    ap.add_argument("--st-min", type=float, default=None, help="book engine: require ST[A] at least this fraction of the TR above the SC (WA p75: 0.5 = supply thinned)")
    ap.add_argument("--no-phase-d", action="store_true", help="book engine: no BU/LPS Phase D entries")
    ap.add_argument("--methods", default=None,
                    help="comma-separated bias-reading methods (wyckoff,ict) for the live ICT rules; "
                         "default = resolved per symbol from /automation (htf_context.engaged_methods_for_market)")
    # CLAUDE.md §33: a personal account and a prop account do not lose the same way -- "did this setup
    # survive?" has no answer until you say WHOSE account. Without one the only loss condition is a blown
    # balance (RUIN_FRAC); §0.3's ONE loader (load_account) is shared with stability-report.py.
    ap.add_argument("--account", help="an §33 profile id from docs/architecture/account-profiles.json")
    ap.add_argument("--account-file", help="a JSON profile to EVALUATE against without shipping it as "
                                           "configuration -- 'what would this look like under my prop firm's "
                                           "rules?' when no such account exists here (§57)")
    ap.add_argument("--calendar", help="economic calendar JSON (event-calendar.json shape); admission-time "
                                       "news refusal in simulate() when supplied (§0.3)")
    ap.add_argument("--sessions", help="comma-separated allowed session labels (docs/architecture/"
                                       "sessions.json); entries outside are refused at admission time")
    ap.add_argument("--trader", help="a §0.9 trader id (docs/architecture/trader-constraints.json); tightens "
                                     "OPTS per RUNNER METHOD by that trader's own per-methodology constraints, "
                                     "and narrows --sessions by whatever `sessions` items the trader declares "
                                     "-- never loosens the CLI's own flags")
    a = ap.parse_args(); fee = a.fee_pct / 100
    if a.flat_before_rollover and not a.cost_profile:
        raise SystemExit("--flat-before-rollover requires --cost-profile: the server daily-rollover clock "
                         "comes from the profile's own provider (scripts/real_costs.py PROFILES).")
    limit_bars(a.bars)
    OPTS.update(min_rr=a.min_rr, types=tuple(int(x) for x in a.types.split(",")), htf=a.htf, sides=tuple(a.sides.split(",")), entry=a.entry, mgmt=a.mgmt, sloped_gate=a.sloped_gate, st_gate=a.st_gate, phase_b_gate=a.phase_b_gate, st_min=a.st_min, phase_d=not a.no_phase_d,
                methods=tuple(a.methods.split(",")) if a.methods else None,
                flat_before_rollover=a.flat_before_rollover,
                rollover_provider=(_RC.PROFILES[a.cost_profile]["provider"] if a.flat_before_rollover else None))
    account = load_account(a)
    calendar = _ER.load(path=a.calendar) if a.calendar else None
    sessions = tuple(a.sessions.split(",")) if a.sessions else None
    if sessions:
        unknown = [s for s in sessions if s not in _S.LABELS]
        if unknown:
            raise SystemExit(f"--sessions names {unknown}, not in docs/architecture/sessions.json "
                             f"({sorted(_S.LABELS)})")
    if a.trader:
        _TC.for_trader(a.trader)          # fail loudly on an unknown trader id rather than silently applying
                                          # nothing (no --trader typo should look like "no trader was given")
        t_sessions = trader_sessions_for(a.trader)
        if t_sessions is not None:
            sessions = tuple(sorted(set(sessions) & t_sessions)) if sessions else tuple(sorted(t_sessions))
    today = datetime.date.today().isoformat()
    account_line = (f"_Tài khoản: **{account['id']}** ({account.get('context_type', '?')}) -- chạy dừng khi "
                    f"TÀI KHOẢN NÀY thất bại theo luật của nó, không chỉ khi cháy vốn._" if account else
                    "_Không có tài khoản (`--account`): điều kiện dừng duy nhất là cháy vốn (RUIN_FRAC)._")
    news_line = (f"_Lịch tin: `{a.calendar}`; từ chối vào lệnh ±{(calendar.get('policy') or {}).get('pre_minutes', 10)}'"
                f"/±{(calendar.get('policy') or {}).get('post_minutes', 10)}' quanh tin theo mức impact bị hạn chế (§24-§32)._"
                if calendar else "_Không có lịch tin (`--calendar`): không lọc theo tin ở bước backtest._")
    sessions_line = (f"_Phiên cho phép: {', '.join(sessions)}; lệnh ngoài phiên này bị từ chối lúc vào lệnh._"
                     if sessions else "_Không giới hạn phiên (`--sessions`)._")
    trader_line = (f"_Trader: **{a.trader}** (`docs/architecture/trader-constraints.json`, §0.9) -- ràng buộc "
                   f"riêng theo phương pháp áp dụng PER RUNNER METHOD, chỉ SIẾT chặt (không bao giờ nới) so "
                   f"với cấu hình CLI ở trên._" if a.trader else
                   "_Không có trader (`--trader`): không áp ràng buộc riêng theo trader._")
    L = [f"# Wyckoff vs ICT vs kết hợp — lợi nhuận theo tháng/quý/năm, rủi ro {RISK * 100:g}%/lệnh — đo {today}", "",
         f"_Bộ lọc: R/R kế hoạch ≥ {a.min_rr} · loại KL {a.types} · lọc khung lớn {'bật' if a.htf else 'tắt'} · chiều {a.sides} · vào lệnh Wyckoff {a.entry} · cổng đối nhãn D1 {'bật' if a.st_gate else 'tắt'}/D2 {'bật' if a.phase_b_gate else 'tắt'} (dấu hiệu luôn được ghi) · cấu trúc xiên {'bỏ' if a.sloped_gate else 'nhận'} · quản lý {a.mgmt} · phí {a.fee_pct}%/chiều · displacement bắt buộc (R10/R11) · P/D gate bắt buộc (R13)_", "",
         f"_`scripts/backtest-methods.py` trên nến lưu tại `data/history/`; phí taker {a.fee_pct}%/chiều; mọi định nghĩa và THAM SỐ DỰ ÁN ở docstring của script. Số ở đây là của proxy bằng code, không phải của phân tích đầy đủ — đọc caveats cuối file._", "",
         account_line, "", news_line, "", sessions_line, "", trader_line, "",
         # CLAUDE.md §38: the verdict goes ABOVE the tables, not in a footnote. "Never silently produce a
         # trustworthy-looking performance result from invalid research" is a statement about what a reader
         # sees first. Filled in after the run, because the evidence (data-quality faults) only exists once
         # the history has been loaded.
         _VERDICT_SLOT, ""]
    allres = {}
    for tf in a.tf.split(","):
        scanner = (lambda sym: scan_for_trader(sym, tf, a.trader)) if a.trader else (lambda sym: scan(sym, tf))
        scans = [s for s in (scanner(sym) for sym in a.symbols.split(",")) if s]
        if not scans:
            continue
        first = min(s["first"] for s in scans); last = max(s["last"] for s in scans)
        L += [f"## Khung {tf} — {first[:10]} → {last[:10]} ({', '.join(f'{s['symbol']} {s['bars']} nến' for s in scans)})", ""]
        methods = RUNNER_METHODS
        res = {}
        for m in methods:
            tr = [t for s in scans for t in s["trades"][m]]
            # INT-4/PAR-2, PAR-4/DEC-4 (docs/audits/2026-09-24-system-audit.md): the entry order type comes from
            # THIS method's own declared entry (docs/architecture/methods.json runner_methods[m].entry), never
            # from a config letter -- "maker" for a resting limit (ICT), "taker" for a market order
            # (WYCKOFF-BOOK, COMBINED-BOOK). The exit is always taker inside simulate() itself.
            entry_order_type = "maker" if _M.RUNNER_METHODS[m]["entry"] == "limit" else "taker"
            eq, curve, taken = simulate(tr, fee, account=account, calendar=calendar, sessions=sessions, trader=a.trader,
                                        entry_order_type=entry_order_type, live_parity_sizing=True,
                                        cost_profile=a.cost_profile, spread_stat=a.spread_stat)
            res[m] = dict(final=eq, curve=curve, taken=taken, stats=summarize(taken, curve=curve), dd=max_dd(curve), ruin=SIM_LAST["ruin"], failed_by=SIM_LAST["failed_by"],
                          refused=dict(SIM_LAST["refused"]),
                          months=period_returns(curve, first, last, month_key), quarters=period_returns(curve, first, last, quarter_key), years=period_returns(curve, first, last, year_key))
        allres[tf] = res
        days = (datetime.date.fromisoformat(last[:10]) - datetime.date.fromisoformat(first[:10])).days or 1
        L += [f"| Phương pháp | Lệnh | Thắng | R ròng TB | ΣR | PF | Vốn cuối (từ ${START:,.0f}) | %/năm (quy đổi) | Sụt giảm tối đa | Cháy | Fail theo luật | Từ chối (tin/phiên) |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for m in methods:
            r = res[m]; s = r["stats"]
            failed_by = r["failed_by"] or "—"
            refused = f"{r['refused']['news']}/{r['refused']['session']}"
            if not s["n"]:
                L.append(f"| {m} | 0 | — | — | — | — | — | — | — | — | {failed_by} | {refused} |"); continue
            ann = ((r["final"] / START) ** (365 / days) - 1) * 100
            # A run that ENDED is not necessarily a BLOWN account: a prop rule halts at -10 % with 90 % of the
            # money still there (§33). Say which it was, so "CHÁY" keeps meaning "the money is gone".
            ruin = (f"DỪNG (luật) {r['ruin'][:10]}" if r.get("failed_by") else f"CHÁY {r['ruin'][:10]}") if r["ruin"] else "—"
            L.append(f"| {m} | {s['n']} | {s['win_rate']:.0f}% | {s['avg_R']:+.2f} | {s['sum_R']:+.1f} | {s['pf']:.2f} | ${r['final']:,.0f} ({(r['final'] / START - 1) * 100:+.1f}%) | {ann:+.1f}% | −{r['dd']:.1f}% | {ruin} | {failed_by} | {refused} |" if s["pf"] else
                     f"| {m} | {s['n']} | {s['win_rate']:.0f}% | {s['avg_R']:+.2f} | {s['sum_R']:+.1f} | — | ${r['final']:,.0f} ({(r['final'] / START - 1) * 100:+.1f}%) | {ann:+.1f}% | −{r['dd']:.1f}% | {ruin} | {failed_by} | {refused} |")
        for label, key in (("năm", "years"), ("quý", "quarters"), ("tháng", "months")):
            keys = period_keys(res, key)
            L += ["", f"**Theo {label} (% thay đổi vốn)**", "", "| Kỳ | " + " | ".join(methods) + " |", "|---|" + "---|" * len(methods)]
            for k in keys:
                L.append(f"| {k} | " + " | ".join(f"{dict(res[m][key]).get(k, 0):+.1f}%" for m in methods) + " |")
            if label == "tháng":
                L += ["", "| Tháng (thống kê) | " + " | ".join(methods) + " |", "|---|" + "---|" * len(methods)]
                L.append("| trung bình | " + " | ".join(f"{statistics.mean(v for _, v in res[m]['months']):+.1f}%" for m in methods) + " |")
                L.append("| trung vị | " + " | ".join(f"{statistics.median(v for _, v in res[m]['months']):+.1f}%" for m in methods) + " |")
                L.append("| tháng dương | " + " | ".join(f"{sum(1 for _, v in res[m]['months'] if v > 0)}/{len(res[m]['months'])}" for m in methods) + " |")
        # per symbol / side
        L += ["", "**Theo mã và chiều (R ròng)**", "", "| Mã | Chiều | " + " | ".join(methods) + " |", "|---|---|" + "---|" * len(methods)]
        for sym in a.symbols.split(","):
            for side in ("long", "short"):
                cells = []
                for m in methods:
                    s = summarize([t for t in res[m]["taken"] if t["symbol"] == sym and t["side"] == side])
                    cells.append(f"n={s['n']} · {s['win_rate']:.0f}% · {s['avg_R']:+.2f}R" if s["n"] else "—")
                L.append(f"| {sym} | {side} | " + " | ".join(cells) + " |")
        L.append("")
    L += ["## Caveats (đọc trước khi dùng)", "",
          "- Spring/Upthrust và MSS/FVG là *proxy bằng code*; không có cổng CHoCH, không đối nhãn, không Volume Profile, không footprint. Phân tích đầy đủ sẽ lọc bớt và kết quả thật khác.",
          "- Phí taker tính cả hai chiều trên giá trị lệnh; không tính trượt giá, funding. Với stop hẹp (scalping 15m) phí ăn một phần đáng kể của R.",
          "- Một vị thế mở/mã; lệnh trùng thời gian bị bỏ. Không lọc khung lớn (để so sánh công bằng giữa ba phương pháp).",
          "- Nến chạm cả stop và target trong cùng một nến tính là thua. Lệnh chưa đóng sau H nến được đóng theo giá đóng cửa (mark-to-market).",
          f"- Tài khoản bắt đầu ${START:,.0f}, rủi ro {RISK * 100:g} % mỗi lệnh; khi vốn ≤ 10 % vốn ban đầu thì coi là CHÁY: dừng giao dịch tại đó, ghi ngày cháy, các kỳ sau bằng 0. Kỳ chưa đủ dữ liệu chỉ tính phần có dữ liệu; %/năm quy đổi từ tổng % theo số ngày của mẫu.",
          "- R, K, T, H và ngưỡng khối lượng là THAM SỐ DỰ ÁN (không phải số trong sách); đổi chúng sẽ đổi kết quả. Không tối ưu hoá tham số ở đây.",
          # Generated from EXECUTION_ASSUMPTIONS rather than typed, so the caveat list cannot drift from what
          # the engine actually models -- the two used to be independent and the prose was already one item
          # short (it named slippage and funding, not MIN_NOTIONAL or lot step).
          "- Giả định khớp lệnh (CLAUDE.md §38): **có mô hình** — "
          + ", ".join(f"{k} ({v})" for k, v in EXECUTION_ASSUMPTIONS.items() if v is not False)
          + "; **KHÔNG mô hình** — " + ", ".join(k for k, v in EXECUTION_ASSUMPTIONS.items() if v is False)
          + ". Một lệnh trong báo cáo này có thể là cỡ mà sàn không nhận."]
    # §38's verdict, and the §10/§11 snapshots it is partly built from. Best-effort: a research run must not
    # FAIL because it could not identify itself, but a run that cannot must not look like one that did -- so a
    # snapshot error becomes an `incomplete_required_inputs` finding via from_config_snapshot(), not silence.
    try:
        cfg_snap = _snapshot.backtest_config_snapshot(
            sys.modules[__name__], timeframes=a.tf.split(","),
            methods=RUNNER_METHODS,
            fee_pct=a.fee_pct, market=_I.market_of(a.symbols.split(",")[0]),
            calendar=calendar, sessions=sessions, account=account, cost_profile=a.cost_profile)
    except (OSError, ValueError, KeyError, AttributeError) as exc:
        cfg_snap = {"snapshot_error": f"{type(exc).__name__}: {exc}"}
    validity = assess_run(cfg_snap, run=f"backtest-methods {a.symbols} {a.tf} ({today})", calendar=calendar)
    block = validity.stamp()
    L[L.index(_VERDICT_SLOT)] = _verdict_markdown(block)
    md = "\n".join(L) + "\n"
    print(md)
    if a.out:
        os.makedirs(os.path.dirname(a.out), exist_ok=True); open(a.out, "w", encoding="utf-8").write(md); print(f"-> {a.out}")
    if a.json:
        slim = {tf: {m: dict(final=r["final"], dd=r["dd"], ruin=r["ruin"], stats=r["stats"], months=r["months"], quarters=r["quarters"], years=r["years"],
                             trades=[{k: v for k, v in t.items() if k != "exit"} for t in r["taken"]]) for m, r in res.items()} for tf, res in allres.items()}
        json.dump(dict(generated=today, fee_pct=a.fee_pct, research_validity=block, config_snapshot=cfg_snap,
                       results=slim), open(a.json, "w"), ensure_ascii=False, indent=1); print(f"-> {a.json}")
    print(validity.describe(), file=sys.stderr)


if __name__ == "__main__":
    main()
