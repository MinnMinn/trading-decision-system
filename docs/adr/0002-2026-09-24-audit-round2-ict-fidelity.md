---
title: Round 2 of the 2026-09-24 system audit (ICT detection fidelity) is Trading-System-version significant
date: 2026-09-24
status: ACCEPTED
context: docs/audits/2026-09-24-system-audit.md found 35 confirmed defects; round 1 (ADR 0001) fixed the live-order-safety and fee findings. Round 2 (this ADR) fixes the ICT detection-fidelity findings ICT-1, ICT-2, ICT-3, ICT-4, ICT-5, ICT-6 and ICT-8 -- see the body below for what each one was. ICT-7 was REFUTED by the audit's adversarial review and is not touched. Round 4's backtest-integrity items (INT-*, PAR-3/4/7/8) remain out of scope except where ICT-8 directly required touching shared code (PAR-7 is the same expiry-window defect as ICT-8's anchor half, so fixing ICT-8 correctly also resolves PAR-7).
problem: Every ICT-1..ICT-8 finding lives in code shared by both the live runner (scripts/strategy-runner.py) and the backtest (scripts/backtest-methods.py) through the single live-scanner seam (scripts/ict-scan.py via scripts/live_rules.py, CLAUDE.md §37). Fixing the detection logic changes which setups are complete, which MSS events are real, and which limit fills are booked -- i.e. it changes required-analysis outcomes and decision-relevant data interpretation, which CLAUDE.md §59 says "must be treated as potentially Trading System version significant". As with round 1, no rebuilt/validated backtest exists yet (that is round 4's job), so there is no evidence to justify moving a live style's released version number today.
decision: Treat round 2 as version-significant NOW, by this ADR, WITHOUT moving any live style's "version" field in docs/architecture/trading-systems.json until round 4 (rebuild backtests, then measure) produces the evidence a v2 requires. This mirrors ADR 0001's decision for round 1 exactly, for the same reasons.
alternatives:
  - Hand-edit trading-systems.json's affected styles' version field from v1 to v2 now, on the theory that a detection-fidelity fix obviously improves on v1 and needs no separate validation step.
  - Register round 2 as a scripts/experiment.py Record with candidate_version v1.1, using the improve-loop's Observation -> Hypothesis -> Candidate -> Backtest -> OOS -> Human Review pipeline (§42) built for research candidates.
  - Do nothing beyond fixing the code: leave the version at v1 with no ADR, on the theory that a bugfix restores what v1 was always supposed to detect rather than changing it.
chosen_approach: This ADR (§53's record) plus leaving every live style's version field in trading-systems.json at v1 until round 4 supplies a validated, rebuilt backtest.
reason: Same reasoning as ADR 0001. trading_system.py's _VERSION_RE rejects a candidate form outright, so trading-systems.json can only hold a RELEASED number; bumping it to v2 now would assert a validated improvement that §46 explicitly forbids asserting without evidence. Filing an experiment Record would misuse the §42 research-candidate pipeline for a round that fixed shared detection-code defects directly rather than proposing and validating a strategy variant. Doing nothing is exactly what §59 forbids.
consequences: Every routable live style stays v1 in trading-systems.json through round 3; its configuration snapshot (trading_system.py snapshot(), §11) names v1 for any decision made after this commit even though seven ICT detection defects are now fixed, so a reader comparing pre- and post-round-2 decisions under the same v1 label must consult this ADR and the round 1-4 commit history, not the version field alone. The pilot's currently-selected ICT setup (docs/architecture/pilot-top20.json, INT-1) was ranked from a stability file built under the PRE-round-2 rules, so its evidence is now further stale (on top of the personal-v1/crypto-live config-snapshot mismatch INT-1 already found); round 3/4's stability-file regeneration is expected to supersede it. Any existing data/live/prelim/*.facts.json and data/live/anchors.*.json written before this commit lack the `last_displaced_mss` and `closed_through_pools` fields introduced here -- htf_context.ict_bias and any renderer reading them degrades gracefully (treats a missing field as None/empty) until the next live scan regenerates them, rather than crashing.
rejected_alternatives:
  - Hand-editing trading-systems.json's version field to v2 without a validated backtest -- refused by the spirit of §46 and the letter of trading_system.py's _VERSION_RE.
  - Filing a scripts/experiment.py Record for round 2 -- refused because the §42 pipeline is for research candidates with backtest/OOS evidence attached, none of which round 2 produced or was scoped to produce.
---

## What round 2 fixed

- **ICT-1** — a level already body-closed-through was later mis-recorded as a liquidity sweep by an unrelated
  wick-and-close-back many bars afterward. `analyze()`'s `add()` now walks bar by bar and stops at the first
  body close beyond the level, tagging the pool `closed_through` (never `swept`) and excluding it from
  `unswept` and from the dealing-range edges, while keeping it visible in facts as `closed_through_pools`
  (knowledge/ict/core-a.md §4 pattern table, §3.2 R6/R25).

- **ICT-2** — the live scanner ran every ICT rule (sweep/MSS/FVG/prev-candle state) on the still-forming last
  candle. `ict-scan.py` now exposes `causal_window(c_full, tf, now)` (reusing `normalized.available_time`, the
  same rule `strategy-runner.drop_forming()` uses) and `main()` truncates the window before `analyze()`/
  `setup_candidate()`; `anchor_facts()` keeps reading the full window unchanged, since it already had its own
  `ref_i = n-2` mechanism.

- **ICT-3** — the premium/discount gate (`pd_ok`) compared the LAST CLOSE's position in the dealing range
  against 0.5, but the order is a LIMIT resting at the FVG near edge (`entry`), not at the close.
  `setup_candidate()` now computes `pd_ok` from the entry price's position in the same dealing range (clamped
  to [0,1] for display as `entry_pct`); the close-based reading survives only as the display-only
  `in_discount` field (knowledge/ict/core-a.md §3.4 R13, R14/§2.19).

- **ICT-4** — displacement was scored on the single breaking candle alone, so a multi-candle displacement whose
  smaller, final candle does the breaking was marked non-displaced; and a non-displaced close reset `bias` to
  0, so a LATER displaced close through the SAME swing was silently lost until an unrelated new pivot happened
  to form. `analyze()`'s MSS loop now scores displacement over the contiguous same-direction candle run ending
  at the breaking candle (or a same-direction FVG in that run), and a non-displaced close is recorded as a
  grab (`disp: false`) without resetting `bias`, so the hunt continues (knowledge/ict/core-a.md §2.16, R25).

- **ICT-5** — `htf_context.ict_bias` read `facts["last_mss"]` regardless of displacement, so a grab could set
  ICT's own directional bias as if it were a real MSS. `analyze()` now also exports `last_displaced_mss` (the
  newest MSS entry that actually has `disp: true`), and `ict_bias` reads only that field
  (knowledge/ict/core-a.md §2.17, core-b.md §2.2).

- **ICT-6** — an FVG was labelled "đã lấp" (filled) on the first touch of its near edge, which is the book's
  IOFED entry, not a failure. The label is now "đã chạm biên gần — IOFED" (touched); the underlying
  `mitigated`/exclusion-from-`open_fvgs` behaviour is unchanged, since core-b R3 already supports removing a
  touched gap from the IRL-objective list (knowledge/ict/core-a.md §2.23, §3.6 R23).

- **ICT-8 / PAR-7** — `fvg_fill` checked the stop before the edge, so a bar reaching both (which, for a long,
  is EVERY bar that reaches the stop, since stop < edge always) returned `None` and the backtest silently
  dropped a real -1R loss while the live runner read the same `None` as "not yet triggered" and could re-offer
  an already-invalidated setup as a new order. `fvg_fill` now checks the edge first and reports
  `(bar, "filled_and_stopped")` when the stop is also reached on that bar; the backtest books the pessimistic
  -1R loss instead of dropping the trade, and the live caller's existing `fill is not None` check already
  means "already triggered, including by invalidation" with no separate code path needed. Separately, the
  backtest's fill-search window was anchored on the bar the setup became DETECTABLE (`i`), not on the setup's
  own MSS bar, so it could stay open `i - mss_i` bars longer than the live runner's own `mss_i + K` expiry
  (`ict_live_setups`'s `bars_left`); `ict_setups_live` now anchors both the pre-check and the fill search on
  `mss_i` and refuses outright when `i > mss_i + K`, matching live exactly (knowledge/ict/core-a.md §3.6 R22,
  core-b R21).

## Refuted, not touched

- **ICT-7** — the audit's own adversarial review refuted this finding; the code's bias/MSS reading is correct
  as written.

See docs/audits/2026-09-24-system-audit.md for the full evidence, reviewer notes and fix critiques behind
each finding, and scripts/tests/test_audit_round2_ict.py for the regression tests (each pinned against the
actual pre-round-2 commit via `load_git_revision`, not a restated claim). Round 3 covers the Wyckoff label
review findings; round 4 covers backtest-integrity (INT-*, PAR-3/4/8) and the rebuilt-backtest validation this
ADR's `consequences` field anticipates.
