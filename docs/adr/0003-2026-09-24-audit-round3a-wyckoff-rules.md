---
title: Round 3a of the 2026-09-24 system audit (mechanical Wyckoff rule fidelity) is Trading-System-version significant
date: 2026-09-25
status: ACCEPTED
context: docs/audits/2026-09-24-system-audit.md found 35 confirmed defects; round 1 (ADR 0001) fixed live-order safety, round 2 (ADR 0002) fixed ICT detection fidelity. Round 3a (this ADR) fixes the mechanical Wyckoff findings WY-1, WY-2, WY-3, WY-4 and WY-5, plus P7.4 from docs/audits/2026-09-24-wyckoff-label-review.md (wyckoff_bias must not keep pointing a direction through a structure whose Trading Range border has since been closed beyond). Round 3b (a parallel dispatch) covers chart labels and the narrative contract (scripts/build-artifact.py, scripts/check-narrative.py) and is not touched here. Round 4's backtest-integrity items (INT-*, PAR-3/4/8) and the stability-file regeneration remain out of scope.
problem: WY-1..WY-5 all live in scripts/wyckoff_rules.py, the single Wyckoff engine both the live runner (scripts/strategy-runner.py, via setups_wyckoff -> backtest-methods.wyckoff_fires) and the backtest (scripts/backtest-methods.py scan()) call through (CLAUDE.md §37). Each finding changes which structures are detected, which bar is read as the entry, or where the stop/target sit -- i.e. required-analysis outcomes and decision-relevant data interpretation, which CLAUDE.md §59 says "must be treated as potentially Trading System version significant". P7.4 changes the Wyckoff bias gate (scripts/htf_context.wyckoff_bias), used by check-narrative.py's verdict check and by any Trading System that engages Wyckoff bias (live_rules.bias_at, backtest-methods.py:494-498) -- also version-significant per the wyckoff-label-review's own summary table. As with rounds 1 and 2, no rebuilt/validated backtest exists yet (round 4's job), so there is no evidence to justify moving a live style's released version number today.
decision: Treat round 3a as version-significant NOW, by this ADR, WITHOUT moving any live style's "version" field in docs/architecture/trading-systems.json until round 4 (rebuild backtests, then measure) produces the evidence a version bump requires. This mirrors ADR 0001 and ADR 0002 exactly, for the same reasons.
alternatives:
  - Hand-edit trading-systems.json's affected styles' version field now, on the theory that a detection-fidelity fix obviously improves on the prior version and needs no separate validation step.
  - Register round 3a as a scripts/experiment.py Record using the improve-loop's Observation -> Hypothesis -> Candidate -> Backtest -> OOS -> Human Review pipeline (§42).
  - Do nothing beyond fixing the code: leave the version unchanged with no ADR, on the theory that a bugfix restores what the engine was always supposed to detect.
chosen_approach: This ADR (§53's record) plus leaving every live style's version field in trading-systems.json unchanged until round 4 supplies a validated, rebuilt backtest.
reason: Same reasoning as ADR 0001/0002. trading_system.py's version reader only accepts a RELEASED number; bumping it now would assert a validated improvement §46 forbids asserting without evidence. Filing an experiment Record would misuse the §42 research-candidate pipeline for a round that fixed shared detection-code defects directly rather than proposing and validating a strategy variant. Doing nothing is exactly what §59 forbids.
consequences: Every routable live style keeps its current version through round 3b/4; its configuration snapshot (trading_system.py snapshot(), §11) names that version for any decision made after this commit even though five mechanical Wyckoff defects plus one bias-integrity defect are now fixed, so a reader comparing pre- and post-round-3a decisions under the same version label must consult this ADR and the round 1-4 commit history, not the version field alone. WY-2 in particular changes which structures classify as Spring vs Shakeout (more Springs are now visible near a window's last bar), and WY-3 changes which closes count as SOS versus an inside-range UA read -- both change WYCKOFF-BOOK's traded population and any stability file or ranking built before this commit is stale for the same reason ADR 0002 flagged for ICT; round 3b/4 regenerate them. WY-1's short-side fix (Upthrust table) changes distribution-side trade counts and entry-bar choice; a below-upthrust_min_ratio break that used to fire as a "type 1" short no longer fires at all. P7.4 changes wyckoff_bias's return for a subset of Phase C/D/E reads (those whose TR border has been closed beyond since the read) from long/short to unknown; check-narrative.py's verdict check and any preset/backtest engaging Wyckoff bias (live_rules.bias_at, backtest-methods.py:494-498) is affected. No routable pilot preset engages Wyckoff bias today (per the wyckoff-label-review's own note), so this is latent in the live pilot but real for research/backtest paths that do.
rejected_alternatives:
  - Hand-editing trading-systems.json's version field without a validated backtest -- refused by the spirit of §46 and the letter of trading_system.py's version reader.
  - Filing a scripts/experiment.py Record for round 3a -- refused because the §42 pipeline is for research candidates with backtest/OOS evidence attached, none of which round 3a produced or was scoped to produce.
---

## What round 3a fixed

- **WY-1** — WYCKOFF-BOOK sorted Upthrusts/UTADs by the Spring volume table (Bảng 2.1, WMT p049) on the
  short/distribution side too, so a below-average-volume break above resistance (which the book does not call
  an Upthrust at all) was accepted as type 1 and could be shorted, and a genuine UTAD (very high volume, the
  book's type 2) was labelled type 3. `wyckoff_rules.vol_type(ratio, side)` is now the ONE owner of this logic
  (moved from `backtest-methods.vtype()`, which had no caller outside its own test module);
  `detect_accumulations`/`detect_distributions` pass `side` through, so a break below `upthrust_min_ratio` is
  refused (`vol_type=None`) rather than relabelled, per analysis-params.json's own
  `project_defined.volume._upthrust_basis` (Bảng 2.2, WMT p064, knowledge/wyckoff/modern-tools.md:66-72). The
  reclaim-vs-test leg choice at `backtest-methods._fires_from` is also now side-aware: a short's Upthrust type 2
  (UTAD) enters at the reclaim without waiting on the book's explicitly optional "UTAD Test" retest, instead of
  being forced through the Test branch that Spring type 2 requires.

- **WY-2** — the Phase-C break search's loop bound (`range(start, n - COMMIT)`) was meant only for the LPS[C]
  commitment look-ahead, but it also silently made every Spring within the last `COMMIT`(=2) bars of a window
  invisible — including a same-bar reclaim exactly on the window's last bar, the only bar a live read
  (`wyckoff_fires`) ever fires on. The book's type-1 "enter at the reclaim" leg (WA p80, Bảng 2.1) was
  therefore dead code in both live and backtest. The break search now runs to `n - 1`; the COMMIT look-ahead
  for the LPS[C] branch is guarded locally (`b + COMMIT - 1 < n`) instead of truncating the whole loop.

- **WY-3** — SOS and the TR top were measured against the AR high (`tr_hi`) only, never updated through Phase
  B, so a close above AR but still below a Phase-B UA high was accepted as SOS (WA p85: SOS = "vượt qua khỏi
  những điểm cao nhất trong Trading Range", not just the AR). `wyckoff_rules` now tracks `ceiling` — the
  highest CONFIRMED Phase-B swing high — and gates the LPS[C]/spring-path SOS test, the BU pullback zone and
  the Phase-D target base on it. `tr_hi` stays AR-only, used only for the đối nhãn thirds and `st_pct`, per the
  fix critique.

- **WY-4** — the Phase-D (BU/LPS) stop used `min(L[pull:entry+1])` where `pull` was overwritten by every
  qualifying pullback bar, so an earlier, deeper pullback bar was excluded and the stop sat above the real
  pullback low. Per the fix critique's timing-neutral formula, the stop is now `min(L[sos+1:entry+1])` — the
  whole pullback since the breakout — while the entry-timing logic (`pull = q` on each qualifying bar) is
  unchanged, so this is a stop-computation fix only, not an entry-semantics change.

- **WY-5** — the BU/LPS "lower volume than the SOS" pullback filter compared against the LAST
  confirmation/follow-through bar (`sos`/`lpsc_sos`, always `breakout_bar + COMMIT - 1`), not the breakout bar
  that actually passed the volume/spread effort test. `wyckoff_rules` now records the breakout bar separately
  (`sos_bar`/`lpsc_sos_bar`) and compares the pullback's volume against it, per WA p83-84's effort-vs-result
  reading ("SOS mở rộng chênh lệch giá và tăng khối lượng ... LPS khối lượng nguồn cung giảm dần").

- **P7.4** — `wyckoff_bias` returned a direction (long/short) from a Phase C/D/E structure without checking
  whether its Trading Range border had since been closed beyond — the exact scenario the wyckoff-label-review
  measured live (a 4H accumulation read with TR low 4,285.91 against a last close of 4,261.60, below that TR
  low, still returning "long"). `wyckoff_bias` now checks a completed close beyond the border (accumulation:
  `last < trading_range.low`; distribution: `last > trading_range.high`) and returns `"unknown"` with a new
  `bias.wy.invalidated` basis key when the structure is no longer intact. A missing `trading_range` (an older
  read with no border recorded) is unaffected — this only withholds bias when a border IS known and HAS been
  closed beyond, per the review's own scoping.

## Shared engine, no live/backtest divergence introduced

Every fix above lives in `scripts/wyckoff_rules.py` (detect_accumulations/detect_distributions) or in
`scripts/backtest-methods.py`'s `_fires_from`/`scan()`, both of which `scripts/strategy-runner.py`'s
`setups_wyckoff()` already delegates to unchanged (it calls `bt.wyckoff_fires()`, which calls the same
`_wyckoff_candidates`/`_fires_from` scan() uses). No separate live-side reimplementation existed for any of
WY-1..WY-5, so fixing the shared engine fixes both paths identically (CLAUDE.md §37) with no new mismatch for
round 4 to reconcile.

## Round 4 must handle

- Regenerate the stability files / ranking (`docs/architecture/*stability*`, pilot selection evidence) that were
  built under the pre-round-3a rules — WY-2 and WY-3 in particular change which structures fire and which bars
  are read as SOS, so any BTCUSDT/ETHUSDT/SOLUSDT WYCKOFF-BOOK trade counts measured before this commit are
  stale in the same way ADR 0002 flagged for ICT.
- Confirm whether any research/backtest path currently engaging Wyckoff bias (`live_rules.bias_at`,
  `backtest-methods.py:494-498`) has cached facts/narratives predating P7.4 — those should be re-evaluated, not
  trusted as still current, since P7.4 can turn a stored "long"/"short" into "unknown".
- INT-6 (HTF filter parity between ICT and WYCKOFF-BOOK) and the other round-4-scoped items (INT-*, PAR-3/4/8)
  are unaffected by this round and remain open.

See docs/audits/2026-09-24-system-audit.md and docs/audits/2026-09-24-wyckoff-label-review.md for the full
evidence, reviewer notes and fix critiques behind each finding, and
scripts/tests/test_audit_round3_wyckoff.py for the regression tests (each "old behaviour" assertion pinned
against the actual pre-round-3a commit `cd96591` via `load_git_revision`, not a restated claim).
