---
title: Pilot systems are enabled by absolute per-horizon criteria, not by a top-N ranking; the count-named selection concept is removed
date: 2026-09-26
status: ACCEPTED
context: The pilot trades whatever docs/architecture/pilot-selection.json lists. That file is produced by scripts/rank-setups.py as a ranking cut-off -- top N overall, or the best setup per (horizon, method) -- and a negative-backtest pick was deliberately still included for coverage (2026-09-11). Audit INT-5 (docs/audits/2026-09-24-system-audit.md) added an out-of-sample holdout (round 4b, oos6m). The owner decided on 2026-09-26 to remove the count-named selection (its name spelled a count of twenty) from the system and to enable only systems that meet explicit return and loss limits per horizon.
problem: A ranking always selects something, even when nothing is good, so the pilot could trade systems with no demonstrated edge, and a negative backtest could be enabled for coverage. The old name also named a count, not a quality bar, and had spread into roughly 60 files (pilot state, logs, journal, schemas), which obscured what the pilot was actually running.
decision: |
  1. Selection is criteria-based. docs/architecture/selection-criteria.json is the single source of the thresholds. A system is enabled only if it passes every criterion of its horizon on its in-sample window AND on its untouched OOS window (oos6m). Every system that passes is eligible, and a horizon with no passing system trades nothing: there is no top-N cut-off, no coverage fallback and no runner-up substitution.
  2. Owner thresholds (2026-09-26), over a 6-month window, account-level, net of costs, live-parity 1% sizing:
     - scalping (minutes/seconds): mean monthly return >= +5% (10% is the target, reported, not a gate), at most 2 losing months, worst month >= -8%;
     - day (1H), capital-preservation profile: mean monthly >= +2%, at most 2 losing months, worst month >= -4%, max drawdown <= 10%;
     - swing (4H), capital-preservation profile: mean monthly >= +1.5%, worst quarter >= -3%, max drawdown <= 8%.
  3. The count-named selection is removed as a concept and a name. The pilot's selection file and its state/log files are renamed ONCE with `git mv` (content unchanged): docs/architecture/pilot-selection.json and data/live/pilot-futures/pilot-selection-{state.json,log.jsonl,mt5-log.jsonl}. There is NO alias and no compatibility code: no code path knows the old names. Records whose contents are history are not rewritten (§17, §42); a record that carries an old value is read as opaque data and no code branches on it. Owner follow-up the same day: no tracked file may contain the old name at all, so documents and reports that used it were reworded to the new names, and reports whose whole subject was the removed top-N selection were deleted (git history keeps them).
alternatives:
  - Keep ranking top N and add the thresholds only as a report column.
  - Keep one best setup per (horizon, method) slot and require it to also meet the thresholds.
  - Rename every historical record and log to the new name.
chosen_approach: Absolute per-horizon gates from selection-criteria.json, applied on in-sample and on OOS, with every passing system eligible; the top-N and per-slot modes and the coverage-over-evidence rule are removed; the live files are renamed once, with no alias, and history is read as opaque data.
reason: The owner's goal is capital preservation with a required edge, and a gate that can say "nothing qualifies" is the only selection consistent with it (CLAUDE.md §1 safety first, §45 attempt to disprove candidates). Applying the gate on OOS as well as in-sample keeps INT-5's protection. Rewriting history would break §17/§42 immutability and the traceability of past pilot decisions.
consequences: |
  The pilot may trade fewer systems, or none, for a horizon. That is the intended outcome, not a failure, and status output must say so plainly. With 1% risk per trade, a +5% mean month needs a strong, frequent edge, so few or no scalping systems may pass today.

  Several passing systems may run on the same account at once, so the existing account-level limits (max positions, daily loss, drawdown; account-profiles.json) remain the binding portfolio constraint. The criteria gate each system alone and do not replace them.

  Applying the gate to OOS makes the OOS window EXPOSED (§44). Round 4b already records this.

  The rename touches the pilot's live selection, state and log files, the trade-file schema and the journal. It is a one-time `git mv` with no alias: a checkout or process still holding an old file name is not read by the new code, so the rename is done with the pilot layer off, and git history (not a compatibility path) is how an old name is traced. It is a shared-contract change (§59) and is implemented and reviewed as its own step.
rejected_alternatives:
  - Keeping a top-N ranking with the thresholds as a report column only -- rejected; it still enables systems that fail the owner's limits.
  - One best setup per (horizon, method) slot that must also pass -- rejected; it caps eligible systems at one per slot for no stated reason and keeps the ranking concept the owner asked to remove.
  - Rewriting the contents of historical records -- rejected by §17/§42 immutability; the live files are renamed once with their contents unchanged, and a historical value is read as opaque data.
  - A compatibility alias map for the old names -- rejected by the owner (2026-09-26) -- it keeps code that knows the removed name alive forever; the system stays lean and git history is the trace.
  - Judging a system on every account-conditioned stability file at once (addendum 2026-09-27) -- rejected by the owner; the same system measured under two accounts collided as a "conflicting duplicate" and was disabled for a reason outside selection-criteria.json. Also rejected: requiring a pass on every account's file, and judging on the account-free *-live file.
  - Shortening the in-sample window to 6 months to match the criteria's wording (addendum 2026-09-27) -- rejected by the owner; the 12-month in-sample window is the stricter reading and needs no regeneration.
---

## Owner's instruction (2026-09-26)

"Hãy loại bỏ '[the old count-named selection]' ra khỏi system. Với scalping hoặc trade tính bằng phút - giây, tao chỉ quan tâm những system
nào back test có lợi nhuận một tháng ít nhất 5-10%, và trong vòng 6 tháng có thể có 1-2 tháng thua lỗ tối đa -8%.
Còn day/swing thì số phần trăm có thể điều chỉnh lại để phù hợp với tiêu chí ưu tiên bảo toàn vốn, lợi nhuận bền
vững cho thời gian dài." Clarified by choice the same day: scalping = mean monthly >= 5%; day/swing = the
"capital preservation" profile. (The quoted name is elided in the square brackets because the same instruction
removes it from every tracked file.)

## Addendum (2026-09-27, owner decisions on the round 4c review)

1. **Which measurement is judged.** A system is judged only on the stability file measured under the account the
   pilot trades that market on -- `account_profile.for_venue(venue, "demo")`: crypto = `pilot-binance-futures-testnet`
   (`data/history/stability/crypto-pilot-binance-futures-testnet.json`), CFD = `pilot-mt5-demo`
   (`data/history/stability/cfd-pilot-mt5-demo.json`). Rows from every other account's file, and from runs with no
   account rules (`*-live.json`), are reported only (`reported_only_rows`) and never enable or disable anything.
   A market with no file for its pilot account trades nothing, and the selection file says why. Every stability
   row lands in exactly one experiment-budget bucket and the buckets must sum to `rows` (§43).
2. **In-sample window length.** The in-sample side stays the 365 days before the OOS cutoff (round 4b), judged
   against thresholds the owner stated for 6 months. That is the stricter reading (more months can only add losing
   months and drawdown), accepted as is.
