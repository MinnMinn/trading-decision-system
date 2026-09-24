---
title: Round 1 of the 2026-09-24 system audit (live order safety and fees) is Trading-System-version significant
date: 2026-09-24
status: ACCEPTED
context: docs/audits/2026-09-24-system-audit.md found 35 confirmed defects; round 1 (this ADR) fixes the live-order-safety and fee findings DEC-1, DEC-2, DEC-3/PAR-2, DEC-4, DEC-5, DEC-6, DEC-7, DEC-8 and PAR-1 -- see the body below for what each one was.
problem: CLAUDE.md §59 says a change to risk, entry, exit or decision ordering "must be treated as potentially Trading System version significant", but scripts/trading_system.py's own _VERSION_RE only accepts a released form (v1, v2, ...) in trading-systems.json, and no rebuilt/validated backtest exists yet to justify moving that number.
decision: Treat round 1 as version-significant NOW, by this ADR, WITHOUT moving any live style's "version" field in docs/architecture/trading-systems.json until round 4 (rebuild backtests, then measure) produces the evidence a v2 requires.
alternatives:
  - Hand-edit trading-systems.json's affected styles' version field from v1 to v2 now, on the theory that a safety fix obviously improves on v1 and needs no separate validation step.
  - Register round 1 as an scripts/experiment.py Record with candidate_version v1.1, the store the improve-loop's Observation -> Hypothesis -> Candidate -> Backtest -> OOS -> Human Review pipeline (§42) uses for research candidates.
  - Do nothing beyond fixing the code: leave the version at v1 with no ADR, on the theory that a bugfix restores what v1 was always supposed to do rather than changing it.
chosen_approach: This ADR (§53's record) plus leaving every live style's version field in trading-systems.json at v1 until round 4 supplies a validated backtest.
reason: trading_system.py's _VERSION_RE = re.compile(r"^v[1-9][0-9]*$") rejects a candidate form outright, so trading-systems.json can only ever hold a RELEASED number; bumping it to v2 now would assert a validated improvement §46 explicitly forbids asserting without evidence ("a result without reproducibility metadata must not be treated as equivalent to a fully reproducible experiment"), the same reasoning applied to a system version standing in for a validation that has not run yet; filing an experiment Record would misuse the §42 research-candidate pipeline (dataset_snapshot, test_periods, validation_method, robustness_results) for a round that fixed live-path defects directly rather than proposing and validating a strategy variant; and doing nothing is exactly what §59 forbids ("must be treated as potentially version significant").
consequences: Every routable live style stays v1 in trading-systems.json through rounds 1-3; its configuration snapshot (trading_system.py snapshot(), §11) names v1 for any decision made after this commit even though nine live-path defects are now fixed, so a reader comparing pre- and post-round-1 decisions under the same v1 label must consult this ADR and the round 1-4 commit history, not the version field alone -- deliberately the same shape §46 already requires for a reproducibility grade. Round 4 is expected to produce the evidence for a next_candidate("v1") -> validated -> approved_successor() -> v2 transition, and this ADR is the record of what that transition, when it happens, is closing out.
rejected_alternatives:
  - Hand-editing trading-systems.json's version field to v2 without a validated backtest -- refused by the spirit of §46 (a claim must not exceed its evidence) and by the letter of trading_system.py's _VERSION_RE, which a candidate form does not even satisfy syntactically.
  - Filing an scripts/experiment.py Record for round 1 -- refused because the §42 pipeline is for research candidates with backtest/OOS evidence attached, none of which round 1 produced or was scoped to produce.
---

## What round 1 fixed

- **DEC-1** — a resting ICT LIMIT order could fill inside a HIGH-impact news blackout that opened after
  placement; `manage_pending()` now checks event risk every tick and cancels the order the way the STOP
  kill switch does.
- **DEC-2** — the MT5 position record's `risk_usd` was price-distance x lots with no contract multiplier, so
  every MT5 R-multiple was wrong by that factor; `open_position()` now scales by `tick_value/tick_size`.
- **DEC-3 / PAR-2** — the ICT net-R gate and R:R floor priced the exit at the ENTRY's order type (maker for a
  resting limit); every exit on this venue is a taker STOP_MARKET/TAKE_PROFIT_MARKET, so `risk_model.cost_r`/
  `net_r` now price the two legs separately and the runner always prices the exit taker.
- **DEC-4** — position size ignored fees, so the realised loss at the stop could exceed the 1% ceiling;
  `size()`/`mt5_lots()` now size on the all-in loss (price distance AND the round-trip fee). This is a
  LIVE-ONLY fix (`scripts/backtest-methods.py` is out of round-1 scope) and widens the sizing mismatch PAR-4
  already tracks for round 4.
- **DEC-5** — nothing re-validated risk/R:R after a MARKET fill; `revalidate_fill()` now disclose a
  `fill_risk_breach` log line when the actual fill diverges materially from the plan (the position is
  already open, so this is a disclosure, not a block).
- **DEC-6** — a declared account-survival rule whose basis fact the runner cannot supply reported UNKNOWN and
  `halt_check()` correctly never halts on UNKNOWN, but nothing blocked NEW ENTRIES on it either; `tick()` now
  also blocks entries via `_account_survival_block()` when such a rule is UNKNOWN, without ever halting on it.
- **DEC-7** — an UNKNOWN-impact event inside its own window was indistinguishable from "no news"; strict-mode
  gating (blocking) still requires an explicit STRICT mode this runner does not yet have a source for (the
  test suite pins that NORMAL must not gate on UNKNOWN), but `event_blackout()` now discloses a
  `unknown_event_disclosed` log line whenever the calendar's own `strict_no_trade` flag would have gated it.
- **DEC-8** — futures exits recorded P&L/R gross of fees against a backtest that books net; `close_record()`
  now subtracts the round-trip fee for a computed (non-venue) close and keeps the old figure as `pnl_gross`.
- **PAR-1** — live breakeven excluded the first bar after entry because it anchored on the wall-clock tick
  that noticed the fill rather than the entry bar itself; positions now carry `entry_bar_time` and
  `manage_position` arms breakeven from the bar strictly after it, matching the backtest's `entry_bar+1`.

See docs/audits/2026-09-24-system-audit.md for the full evidence, reviewer notes and fix critiques behind
each finding, and the round-1 commit for the code (`scripts/risk_model.py`, `scripts/strategy-runner.py`,
`scripts/tests/test_risk_model.py`, `scripts/tests/test_strategy_runner.py`). Rounds 2-4 of the plan cover
ICT/Wyckoff detection defects, backtest-side fixes, and the rebuilt-backtest validation this ADR's
`consequences` field anticipates.
