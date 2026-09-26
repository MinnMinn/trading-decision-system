---
title: Round 4a of the 2026-09-24 system audit (backtest integrity and backtest/live parity) is Trading-System-version significant
date: 2026-09-25
status: ACCEPTED
context: docs/audits/2026-09-24-system-audit.md found 35 confirmed defects; round 1 (ADR 0001) fixed live-order safety, round 2 (ADR 0002) fixed ICT detection fidelity, round 3a (ADR 0003) fixed mechanical Wyckoff rule fidelity, round 3b fixed chart labels/narrative. Round 4a (this ADR) is code-only backtest-integrity and backtest/live-parity fixes -- INT-2, INT-3, INT-4/PAR-2, INT-6/PAR-3, INT-7, PAR-4/DEC-4 (backtest side), plus a WY-3 follow-up and an OPTS-isolation fix found during this round. Round 4b (regenerating the stability files and re-selecting pilot setups from this fixed engine) and INT-1/INT-5 (stale stability files, multiple-testing/OOS accounting) remain out of scope.
problem: simulate() booked every trade's P&L at ENTRY in entry order rather than at EXIT in exit order, so a later trade's sizing and account-survival check could see an EARLIER trade's outcome before it had happened (INT-2) -- future information entering a risk decision, which CLAUDE.md §8/§37 forbid outright. COMBINED-BOOK entered at the MSS close whenever price never retraced to the FVG edge, a decision only knowable by having scanned the K bars after entry (INT-3). Configs B/C and the flat scalar `fee_pct` priced the entry and exit legs of every trade at the SAME rate, though every exit on this venue is a taker market order regardless of how the entry was placed (INT-4/PAR-2). The backtest's HTF gate differed completely from live -- ICT had none at all, WYCKOFF-BOOK/COMBINED-BOOK used a legacy percentile proxy keyed on the wrong bar (INT-6/PAR-3). ICT trades carried no `event` id, so the one-position-per-symbol rule could never block an overlapping ICT trade (INT-7). The backtest's own sizing had no notional cap, no 2-consecutive-loss throttle and did not price the round-trip fee into the risk budget, all three of which strategy-runner.size()/mt5_lots() already apply live (PAR-4/DEC-4). Each of these is either a look-ahead (§8/§37), a research-semantics divergence from what the live runner actually enforces (§37, §59), or a §38 "unrealistic execution assumption" -- exactly the CLAUDE.md §59 "required-analysis change, decision-semantics change" category that must be treated as potentially Trading-System-version significant.
decision: Treat round 4a as version-significant NOW, by this ADR, WITHOUT moving any live style's "version" field in docs/architecture/trading-systems.json until round 4b (regenerate stability files/rankings, then measure) produces the evidence a version bump requires. This mirrors ADR 0001/0002/0003 exactly, for the same reasons.
alternatives:
  - Hand-edit trading-systems.json's affected styles' version field now, on the theory that closing a look-ahead/parity defect obviously improves on the prior version and needs no separate validation step.
  - Register round 4a as a scripts/experiment.py Record using the improve-loop's Observation -> Hypothesis -> Candidate -> Backtest -> OOS -> Human Review pipeline (§42).
  - Do nothing beyond fixing the code: leave the version unchanged with no ADR, on the theory that a bugfix restores what the engine was always supposed to measure.
chosen_approach: This ADR (§53's record) plus leaving every live style's version field in trading-systems.json unchanged until round 4b supplies a validated, rebuilt stability report.
reason: Same reasoning as ADR 0001/0002/0003. trading_system.py's version reader only accepts a RELEASED number; bumping it now would assert a validated improvement §46 forbids asserting without evidence -- especially here, where INT-2/PAR-4/DEC-4 change every stability file's equity curve, drawdown and per-trade sizing simultaneously, and INT-4/PAR-2 change every config-B/C row's net R. Filing an experiment Record would misuse the §42 research-candidate pipeline for a round that fixed shared engine defects directly rather than proposing and validating a strategy variant. Doing nothing is exactly what §59 forbids.
consequences: |
  Every routable live style keeps its current version through round 4b; its configuration snapshot (trading_system.py snapshot(), §11) names that version for any decision made after this commit even though six backtest-integrity/parity defects are now fixed, so a reader comparing pre- and post-round-4a research results under the same version label must consult this ADR and the round 1-4 commit history, not the version field alone.

  INT-2 changes EVERY multi-symbol stability run: any run whose trades overlap across symbols (the account is shared across a timeframe's whole symbol set, per backtest-methods.py's own module docstring) had its equity curve, drawdown and account-survival trace computed from entry-order-cumulative values stamped at exit timestamps -- a path that never existed. Every existing `docs/architecture/*stability*` file and every `pilot-selection.json` backtest block is stale in this same sense ADR 0002/0003 already flagged for ICT/Wyckoff; round 4b regenerates them.

  INT-4/PAR-2 changes every config-B/C row's net R for WYCKOFF-BOOK (previously priced maker on both legs though its real entry is a market order) and understates cost for every ICT config-B/C row less severely than before (maker entry was already correct there; only the exit leg was wrong). PAR-4/DEC-4's `live_parity_sizing` is now available but is an OPT-IN parameter on `simulate()` -- `scripts/backtest-methods.py main()` and `scripts/stability-report.py` now pass it, but any other caller (`scripts/improve-loop.py`, ad hoc scripts) that calls `bt.simulate()` directly without it keeps the pre-round-4a sizing, and must adopt it before its own results are comparable to a run after this commit.

  INT-6/PAR-3 removes the "config C is identical to config B" defect for ICT (previously config C measured nothing config B did not) and moves WYCKOFF-BOOK/COMBINED-BOOK's HTF gate off the legacy percentile proxy onto the live bias read; any existing config-C row for either method is measuring a filter no live setup with `htf:true` was ever actually gated by, in ICT's case, or a different filter than the live one, in Wyckoff's case.

  INT-3's fix reduces (never increases) COMBINED-BOOK's already-near-zero trade count, since COMBINED-BOOK is `runnable=false` (docs/architecture/methods.json) and cannot reach `pilot-selection.json` either way -- no routable setup is affected, but any backtest-only research into COMBINED-BOOK predating this commit measured a partly-hindsight population.

  INT-7 can only ever REDUCE ICT's admitted trade count (a previously-admitted overlapping trade is now correctly skipped), so any prior ICT row's trade count is an upper bound on what a re-run now admits.
rejected_alternatives:
  - Hand-editing trading-systems.json's version field without a validated, regenerated stability report -- refused by the spirit of §46 and the letter of trading_system.py's version reader.
  - Filing a scripts/experiment.py Record for round 4a -- refused because the §42 pipeline is for research candidates with backtest/OOS evidence attached, none of which round 4a produced or was scoped to produce.
---

## What round 4a fixed

- **INT-2** — `simulate()` sorted trades by `entry_time` and added each one's FULL outcome to `equity`
  immediately upon processing, in entry order. A later trade (possibly on a different symbol -- the account is
  shared across a timeframe's whole symbol set) was therefore sized, and the account-survival check evaluated,
  against equity that already included an earlier trade's outcome even when that earlier trade had not yet
  exited as of the later trade's own `entry_time` — future information entering a risk decision (CLAUDE.md §8,
  §37). Fixed: trades are still ADMITTED in `entry_time` order (the R:R floor, news/session refusal, the
  account-survival check and the one-position-per-symbol rule are genuinely causal and may only see what
  already happened by `entry_time`), but an admitted trade's P&L is queued and booked at its own EXIT time, in
  EXIT order, via a small min-heap (`pending`) inside `simulate()`. Sizing/account checks now see only equity
  actually REALISED as of a trade's own entry_time.

- **INT-3** — COMBINED-BOOK's ICT leg entered at the MSS close whenever `fvg_fill(...)` returned `None` (price
  never retraced to the FVG edge within the K-bar window) — a decision knowable only by having scanned the
  entire window, i.e. the future. Fixed: an unfilled limit is not a trade, matching ICT's own live-limit
  semantics (`ict_setups_live` already treats a `None` fill this way). `runnable=false` so this cannot reach
  `pilot-selection.json` either way, but fixed per CLAUDE.md §37 regardless. The ICT-8 `fvg_fill` contract (a bar
  reaching both the edge and the stop returns `"filled_and_stopped"`, booked as a pessimistic -1R) is now also
  honoured on this leg, which previously read the outcome tag but never consulted it.

- **INT-4/PAR-2** — `stability-report.py`'s configs B/C priced EVERY method's entry leg as "maker" regardless
  of how that method actually enters (WYCKOFF-BOOK/COMBINED-BOOK enter at market, i.e. taker), and
  `backtest-methods.simulate()` itself took one flat `fee_pct` scalar charged on both legs at the SAME rate,
  though every exit on this venue is a taker STOP_MARKET/TAKE_PROFIT_MARKET regardless of the entry order type.
  Fixed: `simulate()` gained an `entry_order_type` parameter; when given, the entry leg is priced by
  `risk_model.cost_r` at that order type and the exit leg is ALWAYS priced taker.
  `stability-report.entry_order_type_for(cfg, method)` derives the entry side from the METHOD's own declared
  entry (`docs/architecture/methods.json runner_methods[method].entry`), never from the config letter; config A
  keeps pricing every method taker/taker on purpose (the unmanaged "raw rule" baseline).

- **INT-6/PAR-3** — the backtest's higher-timeframe gate did not match live for either method: the ICT branch
  never read `OPTS["htf"]` at all (so its config-B and config-C rows were byte-identical), and the
  WYCKOFF-BOOK/COMBINED-BOOK branch used the pre-2026-09-13 rolling-percentile proxy (`htf_allows`/
  `htf_position`), keyed on the structure's Spring/SOS time rather than the entry decision time. Fixed: a new
  `htf_bias_gate(sym, tf, side, decision_time, methods)` — the SAME `bias_allows(lr.bias_at(...))` function
  `strategy-runner.htf_pass()` calls live — is now shared by BOTH `scan()` branches, keyed on the LTF decision
  bar's own CLOSE time (`normalized.available_time(c[last], tf)` for Wyckoff, `available_time(c[i], tf)` for
  ICT — NOT `Tm[last]`/`Tm[i]`, which are the bar's OPEN time; code review of this commit found both call
  sites still passing the open time, silently misjudging the HTF bar for any LTF bar whose open falls inside
  an HTF bar that is still forming, fixed in a follow-up commit the same day). The legacy `htf_allows`/
  `htf_position` functions are kept, unused by this gate, only because scripts/tests/test_backtesting.py and
  scripts/tests/test_live_rules.py still exercise them directly as standalone regression tests.

- **INT-7** — ICT trade records carried no `event` id at all (`t.get("event")` was always `None`), so
  `simulate()`'s one-position-per-symbol rule (`t["entry_time"] < until and t.get("event") != ev`, `None !=
  None` → `False`) never blocked a second, overlapping ICT trade on the same symbol — contradicting
  `EXECUTION_ASSUMPTIONS["one_position_per_symbol"]`'s own stated claim. Fixed: `ict_setups_live()` now stamps
  every trade with `event=f"{sym}-{side}-ict-{sweep_time}-{mss_time}"`, built from the setup's own sweep+MSS
  identity, so two different setups can never collide onto the same id.

- **PAR-4/DEC-4 (backtest side)** — the backtest's own position sizing was a flat `equity * RISK * size *
  net_R` with no notional cap, no 2-consecutive-loss halving, and no round-trip fee inside the risk budget —
  all three of which `strategy-runner.size()`/`mt5_lots()` already apply live (DEC-4's live-side fix landed in
  round 1). Fixed: a new `_risk_scale(sym, entry, stop, equity, risk_mult, entry_order_type, exit_order_type)`
  reproduces the SAME formula (fee-aware `per_unit`, then the futures notional cap
  `NOTIONAL_CAP_PCT * leverage`, leverage read from the SAME account profile
  `strategy-runner.futures_leverage()` reads) and is applied via a new opt-in `simulate(..., live_parity_sizing=
  True)` parameter, combined with the SAME `risk_mult = 0.5 if consec_losses >= 2` loss throttle
  strategy-runner applies. CFD/MT5 (no notional cap in `mt5_lots`) is unaffected by the cap half of this fix.

- **WY-3 follow-up** — the Phase-B "ran away" guard in `wyckoff_rules.py` (`H[b] > tr_hi + tr`) still measured
  against the AR-only `tr_hi` even after round 3a's own WY-3 fix introduced `ceiling` (the running Phase-B UA
  high) for the SOS/BU/target tests right next to it. A Phase-B excursion that is itself a legitimate (if
  large) UA — WA p88-89's own worked examples run a UA well past the AR before the eventual SOS breaks the UA
  itself, not the AR — was discarded here even though the SOS test immediately above it would have judged the
  exact same excursion by the Phase-B ceiling. Fixed: gated on `ceiling + tr`, not `tr_hi + tr`.

- **OPTS isolation** — `backtest-methods.OPTS` is a mutable module-level dict every scan-path function reads as
  a free variable; a caller that mutated it (a config sweep, `scan_for_trader`'s own per-method tightening, or
  simply an earlier caller in the same process) left that mutation as the silent starting point for the next,
  otherwise-unrelated `scan()` call — round 3 measured this directly as a false "0 trades" result. Fixed:
  `scan(sym, tf, only=None, opts=None)` gained an `opts=` parameter that, when given, runs the call against a
  fresh copy of the canonical baseline (`_OPTS_BASE`, frozen at import time) rather than whatever OPTS happens
  to hold; `scan_for_trader()` now routes its own per-method tightening through this same parameter instead of
  hand-rolling its own save/restore of the bare module global; a new `reset_opts()` restores the baseline
  directly for callers/tests that need a known-clean starting point.

## Deferred to round 4b or explicitly out of scope

- **INT-1** (stale stability files stamped with the wrong rule_version) and **INT-5** (multiple-testing/OOS
  accounting) are unchanged by this round, as scoped.
- **PAR-5** (MT5 live export's DST-wrong bar stamping) was flagged NEEDS_CONTEXT during this round: fixing it
  correctly requires either changing what the Python bridge-file reader assumes about server time (converting
  with the IANA zone `docs/architecture/providers.json` already declares) or changing what
  `integrations/mt5/ExportOHLCV.mq5` writes, and choosing between those two is a design decision, not a
  mechanical fix, that this round did not make.
- **PAR-8** (CFD 30m/2H/5m backtests reading Yahoo futures) was found ALREADY FIXED before this round started
  — `rank-setups.py`'s `CFD_TFS = {"15m", "1H", "4H"}` (commit `8ab4e1d`, predating `cd78200`) already excludes
  every timeframe the live CFD system does not trade from ranking. No code change was needed; a regression test
  was added (`scripts/tests/test_audit_round4_integrity.py::PAR8CfdRankingExcludesUnexecutedTimeframes`) to
  lock it in.
- **ICT-8/PAR-7** (fvg_fill's same-bar fill+stop contract, and the ICT backtest fill window anchored on the
  setup's own MSS bar) were found ALREADY FIXED before this round started, both dated 2026-09-24/25 in the
  current code's own comments and already covered by `scripts/tests/test_audit_round2_ict.py`.
- Regenerating `docs/architecture/*stability*` and re-selecting `pilot-selection.json` from this fixed engine is
  round 4b's job, not this round's — this ADR's "consequences" section names exactly which prior research
  results are now stale for round 4b to regenerate.

See docs/audits/2026-09-24-system-audit.md for the full evidence, reviewer notes and fix critiques behind each
finding, and scripts/tests/test_audit_round4_integrity.py for the regression tests (each "old behaviour"
assertion pinned against the actual pre-round-4a commit `cd78200` via `load_git_revision`/direct git-show
comparison, not a restated claim).
