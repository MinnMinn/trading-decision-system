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
import argparse, bisect, collections, importlib.util, datetime, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import wyckoff_rules as W
import quality as _quality   # CLAUDE.md §20: the six data-quality states this loader flags its history against
import research_validity as _RV
import normalized as _N       # CLAUDE.md §8: available_time() is the one place "when a bar becomes knowable" is computed
import account_profile as _AP   # CLAUDE.md §33: a prop account and a personal account do not lose the same way  # CLAUDE.md §38: what those faults, and this engine's own gaps, do to a run
import event_risk as _ER        # CLAUDE.md §24-§32: the ±10' news window, read PIT off entry_time only
import sessions as _S            # CLAUDE.md §21: session labels, DST-aware
import performance as _perf      # CLAUDE.md §39: the ONE computer for the twenty-three metrics
import snapshot as _snapshot     # CLAUDE.md §10/§11: the run identifies its dataset and its configuration
import instruments as _I         # the ONE allowlist; also names the market a symbol belongs to (§35)
import methods as _M             # RUNNER_METHODS[method]["requires"]: which methodology dimension(s) a
                                  # method reads, so a --trader constraint applies to the RIGHT method only (§17)
import trader_constraints as _TC  # CLAUDE.md §0.9: per-trader, per-methodology constraints, tighten-only
P = {"5m": dict(R=60, K=18, T=20, H=120, sob=8), "15m": dict(R=48, K=16, T=16, H=96, sob=6), "30m": dict(R=48, K=14, T=14, H=84, sob=5), "1H": dict(R=48, K=12, T=12, H=72, sob=4),
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
OPTS = dict(min_rr=None,   # set to MIN_RR right after _ICT is read below -- see the note there
             types=(1, 2, 3), range_touches=0, htf=False, sides=("long", "short"), entry="book", mgmt="none", sloped_gate=False, st_min=None, phase_d=True, combined_entry="limit",
            st_gate=False, phase_b_gate=False, methods=None)
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


# CLAUDE.md §38: "A research run must be flagged or invalidated when there is evidence of ... corrupted
# provider data, incomplete required inputs." Every §20 fault the loaded history carries, so a result can be
# judged on the data that produced it. §38 owns what is finally done with these; §20's work was to make them
# detectable at all, and this is the point where a backtest meets its data.
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


def load(sym, tf):
    p = f"{ROOT}/data/history/ohlcv.{sym}.{tf}.json"
    if not os.path.exists(p):
        return None, None
    d = json.load(open(p))
    if _BARS_LIMIT and len(d.get("candles") or ()) > _BARS_LIMIT:
        d = dict(d, candles=d["candles"][-_BARS_LIMIT:])
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
                                  "source": os.path.relpath(p, ROOT)})
            print(f"DATA-QUALITY FLAG (CLAUDE.md §20/§38): {sym} {tf} history is {state}: {why}",
                  file=sys.stderr)
    return d["candles"], os.path.relpath(p, ROOT)


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


def walk(side, entry, stop, target, H_, L_, C_, start, horizon):
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
    j = min(len(C_) - 1, start + horizon - 1)
    return dict(outcome="timeout", R=((C_[j] - entry) if side == "long" else (entry - C_[j])) / r, exit=j,
                R_planned=rp, mfe=mfe, mae=mae, bars_held=j - start + 1)


def vtype(ratio, side="long"):
    """The book's volume TYPE for this bar. Spring and Upthrust use DIFFERENT tables and the difference is not
    a mirror -- it is the whole point of the 2026-09-19 knowledge audit.

    Spring (long) -- Bảng 2.1, WMT p049 (knowledge/wyckoff/modern-tools.md:55-61):
        type 1 = LOW ("no fresh selling pressure"), type 2 = MODERATE, type 3 = HIGH ("Shake Out", panic
        selling with market-maker absorption). Ascending in volume: 1 < 2 < 3.

    Upthrust (short) -- Bảng 2.2, WMT p064 (knowledge/wyckoff/modern-tools.md:66-72):
        type 1 = volume INCREASES at the touch, type 2 = UTAD, VERY HIGH at the extreme, type 3 = Minor UTAD,
        "strong but not as high as Type 2". Ordering is 2 > 3 >= 1 and **no Upthrust type is low-volume**.

    Until 2026-09-19 this function ignored `side` and ran the Spring ladder on shorts, so a below-average bar
    was called "type 1" and handed the most aggressive entry (`strategy-runner.setups_wyckoff`), while a
    genuine UTAD -- the highest-volume bar, the book's type 2 -- was labelled type 3. Both labels were wrong
    and the docstring cited p049 (the Spring page) as authority for them.

    What the proxy still CANNOT do: the book separates Upthrust type 1 from type 3 by PRICE reaction (type 1
    reverses sharply back inside the range; type 3 merely fails the prior structural high), not by volume. On
    volume alone they share one band, so this returns 1 for that band and never 3 for a short. That is a
    declared limit of the proxy, not a reading of the book -- `scripts/wyckoff_rules.py` is the engine that
    reads structure.
    """
    if ratio is None:
        return None
    if side == "long":
        return 1 if ratio < VOL["low_max_ratio"] else (3 if ratio > VOL["high_min_ratio"] else 2)
    # short: Upthrust. Very high -> UTAD (2); increased-at-the-touch -> (1); below that the book has no type.
    if ratio > VOL["high_min_ratio"]:
        return 2
    if ratio >= VOL["upthrust_min_ratio"]:
        return 1
    return None


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
    """First bar after the MSS whose range reaches the FVG near edge without first hitting the stop. Returns bar index or None."""
    for j in range(mss + 1, min(mss + 1 + K, n)):
        if side == "long":
            if L[j] <= stop:
                return None
            if L[j] <= edge:
                return j
        else:
            if H[j] >= stop:
                return None
            if H[j] >= edge:
                return j
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
_RUNGS = ["5m", "15m", "30m", "1H", "2H", "4H", "1D"]
import importlib.util as _iu
_as = _iu.spec_from_file_location("automation", os.path.join(ROOT, "scripts", "automation.py")); _auto = _iu.module_from_spec(_as); _as.loader.exec_module(_auto)
HTF_OF = {tf: _auto.next_rung(tf, _RUNGS) for tf in _RUNGS if _auto.next_rung(tf, _RUNGS)}
# The live rules seam (scripts/live_rules.py): the ICT branch calls the live scanner through this handle instead of
# re-deriving pivots/MSS/FVG itself (audit 2026-09-13 -- see docstring at the top of this file's ICT section).
_lspec = _iu.spec_from_file_location("live_rules", os.path.join(ROOT, "scripts", "live_rules.py"))
lr = _iu.module_from_spec(_lspec); _lspec.loader.exec_module(lr)


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
    out, seen = [], set()
    n = len(c)
    idx_of_time = {t: j for j, t in enumerate(Tm)}
    for i in range(n):
        a = lr.read_at(c, i, tf, methods)
        if a is None:            # window not yet the full live window -- live would not have scanned here at all
            continue
        su = lr.ict_scan.setup_candidate(a, lr.window(c, i, tf), lr.setup_lookback(tf))
        if not su or not su.get("complete") or not su.get("pd_ok"):
            continue
        bias, _ = lr.bias_at(c, i, tf, methods, facts=a)      # facts reused: no second analyze()
        if not bias_allows(bias, su["side"]):
            continue
        key = (su["side"], su["sweep"]["time"], su["mss"]["time"])
        if key in seen:          # the same setup stays visible for many bars; take it once, at its first bar
            continue
        seen.add(key)
        mss_i = idx_of_time.get(su["mss"]["time"])
        if mss_i is None:
            continue
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
        if fvg_fill(su["side"], mss_i, entry, far, stop, H, L, P[tf]["K"], i + 1) is not None:
            continue             # the runner would refuse this as already triggered -- so neither may this
        fill = fvg_fill(su["side"], i, entry, far, stop, H, L, P[tf]["K"], n)
        if fill is None:         # the limit never filled: live would hold an unfilled order, not a position
            continue
        w = walk(su["side"], entry, stop, target, H, L, C, fill + 1, HZ)
        if not w:
            continue
        out.append(dict(symbol=sym, tf=tf, side=su["side"], time=Tm[i], entry=entry, entry_time=Tm[fill],
                        stop=stop, target=target, exit_time=Tm[w["exit"]], vol_type=None, **w))
    return out


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
    return _fires_from(side, _wyckoff_candidates(side, O, H, L, C, V, tf, sym), C, Tm)


def _wyckoff_candidates(side, O, H, L, C, V, tf, sym):
    """The wyckoff_rules records of this window that COULD fire on its last bar (a reclaim, test or BU sitting on
    it) -- everything OPTS-independent, so scan() can cache it per window and re-run the gates cheaply for each
    config (stability-report's A/B/C, improve-loop's candidates) instead of re-detecting 100 000 windows apiece."""
    W.PARAMS["spring_max_bars_outside"] = P[tf]["sob"]
    last = len(C) - 1
    vkind = "tick" if (sym and _I.is_tick_volume(sym)) else "traded"   # wyckoff_rules R0 / WMT p131-133
    recs = W.detect_accumulations(O, H, L, C, V, volume_kind=vkind) if side == "long" else W.detect_distributions(O, H, L, C, V, volume_kind=vkind)
    return [r for r in recs if (r["bu"] and r["bu"]["bar"] == last) or r["reclaim"] == last or r["test"] == last]


def _fires_from(side, recs, C, Tm):
    """The OPTS-dependent half of the read: gates, leg choice, stop/target, placeability -- on the last bar."""
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
        tr = r["tr_hi"] - r["tr_lo"]; t0 = Tm[r["spring"] if r["spring"] is not None else r["sos"]]
        if r["path"] == "spring" and not r["shakeout"] and not r["abandon"] and not r["sot_too_strong"] and r["vol_type"] in OPTS["types"]:
            rec = r["reclaim"]; vt = r["vol_type"]; rr = r["rec_ratio"]
            w_bar = rec if (OPTS["entry"] == "book" and (vt == 1 or (vt == 3 and rr is not None and rr >= VOL["high_min_ratio"]))) else r["test"]
            # Only the last bar can be an entry -- earlier bars were earlier reads (the runner's rule, now the
            # backtest's too). An entry whose close already sits beyond its stop or target is not placeable.
            if w_bar == last:
                stop = r["spring_low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["spring_low"] * (1 + STOP_BUFFER_PCT)
                target = r["tr_hi"] if side == "long" else r["tr_lo"]
                if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                    out.append(dict(leg="spring", t0=t0, entry=C[last], stop=stop, target=target, rec=r))
        if OPTS["phase_d"] and r["bu"] and r["bu"]["bar"] == last:
            stop = r["bu"]["low"] * (1 - STOP_BUFFER_PCT) if side == "long" else r["bu"]["low"] * (1 + STOP_BUFFER_PCT)
            target = r["tr_hi"] + W.PARAMS["d_target_tr"] * tr if side == "long" else r["tr_lo"] - W.PARAMS["d_target_tr"] * tr
            if (side == "long" and target > C[last] > stop) or (side == "short" and target < C[last] < stop):
                out.append(dict(leg="phase_d", t0=t0, entry=C[last], stop=stop, target=target, rec=r))
    return out


def scan(sym, tf, only=None):
    """`only`: which of RUNNER_METHODS to compute; None (default) computes all three. A caller that needs exactly
    one method's trades should pass e.g. only=("ICT",) so scan() SKIPS the other methods' work rather than
    computing and discarding it -- in particular so it never calls the live ICT scanner (ict_setups_live, one
    ict-scan.analyze() per bar) when nobody asked for ICT trades. strategy-runner.replay() checks one method at
    a time across 9 symbols; before this, it paid the full live-scanner cost for ICT on every call regardless
    (code-quality review, 2026-09-13). NOT the same axis as OPTS["methods"] -- that key holds the wyckoff/ict BIAS
    DIMENSIONS the live rules read (resolve_methods/engaged_methods_for_market); `only` here names RUNNER methods
    (WYCKOFF-BOOK, ICT, COMBINED-BOOK). Deliberately a different name (`only`, not `methods`) so the two never collide."""
    want = set(RUNNER_METHODS) if only is None else set(only)
    c, src = load(sym, tf)
    if not c:
        return None
    p = P[tf]; R, K, T, HZ = p["R"], p["K"], p["T"], p["H"]
    H = [x["high"] for x in c]; L = [x["low"] for x in c]; C = [x["close"] for x in c]; V = [x.get("volume", 0) for x in c]; Tm = [x["time"] for x in c]; O = [x["open"] for x in c]
    n = len(c); trades = collections.defaultdict(list); PH = all_pivots(H, "high"); PL = all_pivots(L, "low")
    htf = htf_position(sym, tf) if OPTS["htf"] else None
    # ---------- WYCKOFF-BOOK / COMBINED-BOOK (scripts/wyckoff_rules.py: CHoCH gate, TR from SC/AR, Phase B, Spring vs Shakeout, VP veto, Test, Phase D) ----------
    if want & {"WYCKOFF-BOOK", "COMBINED-BOOK"}:
        # Window by window, exactly the live read -- wyckoff_fires() says why. A structure fires once per leg, at
        # the one bar the runner would have entered on; later windows re-find the same structure under the same
        # t0 and are dropped here, as replay() drops them.
        seen = set(); WIN = WYCKOFF_WINDOW
        # Detection is the cost (~0.5 ms/window) and does not depend on OPTS; the gates do. So the per-window
        # candidates are computed once per history in this process and every config re-runs only the gates.
        ck = (sym, tf, n, Tm[0], Tm[-1])
        if ck not in _WY_CANDIDATES:
            _WY_CANDIDATES[ck] = {(side, k): _wyckoff_candidates(side, O[k - WIN:k], H[k - WIN:k], L[k - WIN:k], C[k - WIN:k], V[k - WIN:k], tf, sym)
                                  for k in range(WIN, n + 1) for side in ("long", "short")}
        cands = _WY_CANDIDATES[ck]
        for k in range(WIN, n + 1):
            last = k - 1; a = k - WIN
            for side in OPTS["sides"]:
                cs = cands[(side, k)]
                if not cs:
                    continue
                for f in _fires_from(side, cs, C[a:k], Tm[a:k]):
                    key = (side, f["t0"], f["leg"])
                    if key in seen:
                        continue
                    seen.add(key)
                    r = f["rec"]; t0 = f["t0"]
                    if htf is not None and not htf_allows(htf, t0, side):
                        continue
                    base = dict(symbol=sym, tf=tf, side=side, time=t0, event=f"{sym}-{side}-book-{t0}", support=r["tr_lo"], resistance=r["tr_hi"], vol_type=r["vol_type"], vol_ratio=r["vol_ratio"],
                                volume_kind=r["volume_kind"], st_sign=r["st_sign"], phase_b_sign=r["phase_b_sign"],
                                st_pct=r["st_pct"], sot=r["sot"], path=r["path"])
                    if f["leg"] == "phase_d":
                        if "WYCKOFF-BOOK" in want:
                            w = walk(side, f["entry"], f["stop"], f["target"], H, L, C, last + 1, HZ)
                            if w:
                                trades["WYCKOFF-BOOK"].append(dict(base, event=base["event"] + "-D", entry=f["entry"], entry_time=Tm[last], stop=f["stop"], target=f["target"], exit_time=Tm[w["exit"]], leg="phase_d", **w))
                        continue
                    if "WYCKOFF-BOOK" in want:
                        w = walk(side, f["entry"], f["stop"], f["target"], H, L, C, last + 1, HZ)
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
                            e_bar, e_px = (fill, edge) if fill is not None else (mss, C[mss])
                            if e_bar < last:
                                continue
                            cw = walk(side, e_px, f["stop"], f["target"], H, L, C, e_bar + 1, HZ)
                            if cw:
                                trades["COMBINED-BOOK"].append(dict(base, entry=e_px, entry_time=Tm[e_bar], stop=f["stop"], target=f["target"], exit_time=Tm[cw["exit"]], via="fvg" if fill is not None else "mss", **cw))
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
        trades["ICT"] = ict_setups_live(sym, tf, c, Tm, HZ, H, L, C, resolve_methods(sym))
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
    tightening it PER METHOD means reassigning the module global around each method's own `scan(..., only=
    (method,))` call and restoring it in a `finally` -- there is no concurrency in this script, so the
    reassign/restore is safe and is the only way to give each of the three methods a different OPTS in one process
    without threading a parameter through every function scan() already has (`walk`, `find_ict`, `vtype`, ...
    all read the module global directly)."""
    global OPTS
    want = set(RUNNER_METHODS) if only is None else set(only)
    base = dict(OPTS)
    combined = None
    all_trades = {}
    for method in RUNNER_METHODS:
        if method not in want:
            continue
        tightened = base
        for dim in _dims_for(method):
            tightened = _TC.overlay(tightened, trader_id, dim)
        saved = OPTS
        OPTS = tightened
        try:
            r = scan(sym, tf, only=(method,))
        finally:
            OPTS = saved
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


def simulate(trades, fee_pct, account=None, calendar=None, sessions=None, trader=None):
    """Chronological RISK-per-trade compounding account (a trade's own `size` field scales its risk, default
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
    ts = sorted(trades, key=lambda t: t["entry_time"])
    equity = START; open_pos = {}; curve = []; taken = []; ruin = None
    peak = START; day_start = START; day = None; failed_by = None
    realised_today = 0.0; consec_losses = 0
    profit_by_day, profit_by_symbol = {}, {}
    for t in ts:
        # CLAUDE.md §37: "the backtest must execute the same logical Trading System and Decision Engine
        # semantics used by live decisions wherever practical." The R:R floor is one of those semantics, and
        # until 2026-09-18 the two paths applied it to DIFFERENT quantities: §34 moved the live gate to R
        # measured NET of fees (scripts/strategy-runner.py rr_reason), while this loop filtered on the GROSS
        # `R_planned` and only then charged the fee. The backtest was therefore taking trades the live runner
        # refuses -- measured at 8,071 admitted trades across BTC/ETH/SOL 15m, of which 392 (5 %) fall below
        # the floor once the venue's own fee is charged. A backtest that admits 5 % of trades its own live
        # system would decline is not measuring that system.
        #
        # RESEARCH-SEMANTICS CHANGE (§59): every stability report and every `pilot-top20.json` backtest block
        # produced before this date was computed under the gross convention and is NOT comparable to a run
        # after it. They are deliberately not regenerated here -- see SYSTEM-DESIGN.md §45.
        dist = abs(t["entry"] - t["stop"]) / t["entry"]
        fee_R = 2 * fee_pct / dist
        if t.get("R_planned", 99) - fee_R < OPTS["min_rr"]:
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
                break
        if equity <= RUIN_FRAC * START:
            ruin = ruin or (curve[-1][0] if curve else t["entry_time"])
            failed_by = failed_by or (f"equity <= {RUIN_FRAC:.0%} of the starting balance (no account "
                                      f"profile supplied, so the only loss condition is a blown account)")
            break
        until, ev = open_pos.get(t["symbol"], ("", None))
        if t["entry_time"] < until and t.get("event") != ev:
            continue
        open_pos[t["symbol"]] = (max(until, t["exit_time"]) if t.get("event") == ev else t["exit_time"], t.get("event"))
        net_R = t["R"] - fee_R
        size = t.get("size", 1.0)
        pnl = equity * RISK * size * net_R
        equity += pnl
        peak = max(peak, equity)
        realised_today += pnl
        consec_losses = consec_losses + 1 if net_R < 0 else 0
        profit_by_day[t["exit_time"][:10]] = profit_by_day.get(t["exit_time"][:10], 0.0) + pnl
        profit_by_symbol[t["symbol"]] = profit_by_symbol.get(t["symbol"], 0.0) + pnl
        taken.append(dict(t, net_R=round(net_R, 3), pnl=pnl))
        curve.append((t["exit_time"], equity))
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
    return equity, curve, taken


SIM_LAST = {"ruin": None, "failed_by": None, "account": None, "rules_not_applicable": [],
           "refused": {"news": 0, "session": 0}, "trader": None}   # how the last simulate() ended, under
           # whose account rules and whose §0.9 trader constraints


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
    ap.add_argument("--min-rr", type=float, default=MIN_RR, help="skip trades whose PLANNED R (target distance / stop distance) is below this")
    ap.add_argument("--types", default="1,2,3", help="Spring/Upthrust volume types allowed for WYCKOFF-BOOK/COMBINED-BOOK")
    ap.add_argument("--range-touches", type=int, default=0, help="require this many tests of EACH border before a Spring counts (0 = off)")
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
    limit_bars(a.bars)
    OPTS.update(min_rr=a.min_rr, types=tuple(int(x) for x in a.types.split(",")), range_touches=a.range_touches, htf=a.htf, sides=tuple(a.sides.split(",")), entry=a.entry, mgmt=a.mgmt, sloped_gate=a.sloped_gate, st_gate=a.st_gate, phase_b_gate=a.phase_b_gate, st_min=a.st_min, phase_d=not a.no_phase_d,
                methods=tuple(a.methods.split(",")) if a.methods else None)
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
         f"_Bộ lọc: R/R kế hoạch ≥ {a.min_rr} · loại KL {a.types} · biên TR chạm ≥ {a.range_touches} lần mỗi bên · lọc khung lớn {'bật' if a.htf else 'tắt'} · chiều {a.sides} · vào lệnh Wyckoff {a.entry} · cổng đối nhãn D1 {'bật' if a.st_gate else 'tắt'}/D2 {'bật' if a.phase_b_gate else 'tắt'} (dấu hiệu luôn được ghi) · cấu trúc xiên {'bỏ' if a.sloped_gate else 'nhận'} · quản lý {a.mgmt} · phí {a.fee_pct}%/chiều · displacement bắt buộc (R10/R11) · P/D gate bắt buộc (R13)_", "",
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
            eq, curve, taken = simulate(tr, fee, account=account, calendar=calendar, sessions=sessions, trader=a.trader)
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
            calendar=calendar, sessions=sessions, account=account)
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
