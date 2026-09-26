---
title: Pilot systems are enabled by absolute per-horizon criteria, not by a top-N ranking; the "top20" concept is removed
date: 2026-09-26
status: ACCEPTED
context: The pilot trades whatever docs/architecture/pilot-top20.json lists. That file is produced by scripts/rank-setups.py as a ranking cut-off -- top N overall, or the best setup per (horizon, method) -- and a negative-backtest pick was deliberately still included for coverage (2026-09-11). Audit INT-5 (docs/audits/2026-09-24-system-audit.md) added an out-of-sample holdout (round 4b, oos6m). The owner decided on 2026-09-26 to remove "top20" from the system and to enable only systems that meet explicit return and loss limits per horizon.
problem: A ranking always selects something, even when nothing is good, so the pilot could trade systems with no demonstrated edge, and a negative backtest could be enabled for coverage. "Top 20" also names a count, not a quality bar, and has spread into roughly 60 files (pilot state, logs, journal, schemas), which obscures what the pilot is actually running.
decision: |
  1. Selection is criteria-based. docs/architecture/selection-criteria.json is the single source of the thresholds. A system is enabled only if it passes every criterion of its horizon on its in-sample window AND on its untouched OOS window (oos6m). Every system that passes is eligible, and a horizon with no passing system trades nothing: there is no top-N cut-off, no coverage fallback and no runner-up substitution.
  2. Owner thresholds (2026-09-26), over a 6-month window, account-level, net of costs, live-parity 1% sizing:
     - scalping (minutes/seconds): mean monthly return >= +5% (10% is the target, reported, not a gate), at most 2 losing months, worst month >= -8%;
     - day (1H), capital-preservation profile: mean monthly >= +2%, at most 2 losing months, worst month >= -4%, max drawdown <= 10%;
     - swing (4H), capital-preservation profile: mean monthly >= +1.5%, worst quarter >= -3%, max drawdown <= 8%.
  3. "top20" is removed as a concept and a name. The pilot's selection file and its state/log files are renamed; historical records that carry the old name are left as written and read through a compatibility alias, never rewritten (§17, §42).
alternatives:
  - Keep ranking top N and add the thresholds only as a report column.
  - Keep one best setup per (horizon, method) slot and require it to also meet the thresholds.
  - Rename every historical record and log to the new name.
chosen_approach: Absolute per-horizon gates from selection-criteria.json, applied on in-sample and on OOS, with every passing system eligible; the top-N and per-slot modes and the coverage-over-evidence rule are removed; the rename leaves history immutable behind an alias.
reason: The owner's goal is capital preservation with a required edge, and a gate that can say "nothing qualifies" is the only selection consistent with it (CLAUDE.md §1 safety first, §45 attempt to disprove candidates). Applying the gate on OOS as well as in-sample keeps INT-5's protection. Rewriting history would break §17/§42 immutability and the traceability of past pilot decisions.
consequences: |
  The pilot may trade fewer systems, or none, for a horizon. That is the intended outcome, not a failure, and status output must say so plainly. With 1% risk per trade, a +5% mean month needs a strong, frequent edge, so few or no scalping systems may pass today.

  Several passing systems may run on the same account at once, so the existing account-level limits (max positions, daily loss, drawdown; account-profiles.json) remain the binding portfolio constraint. The criteria gate each system alone and do not replace them.

  Applying the gate to OOS makes the OOS window EXPOSED (§44). Round 4b already records this.

  The rename touches the pilot's live selection, state and log files, the trade-file schema and the journal. It is a shared-contract change (§59) and is implemented and reviewed as its own step, with the pilot layer off.
rejected_alternatives:
  - Keeping a top-N ranking with the thresholds as a report column only -- rejected; it still enables systems that fail the owner's limits.
  - One best setup per (horizon, method) slot that must also pass -- rejected; it caps eligible systems at one per slot for no stated reason and keeps the ranking concept the owner asked to remove.
  - Renaming historical records -- rejected by §17/§42 immutability; history is read through a compatibility alias instead.
---

## Owner's instruction (2026-09-26)

"Hãy loại bỏ 'top20' ra khỏi system. Với scalping hoặc trade tính bằng phút - giây, tao chỉ quan tâm những system
nào back test có lợi nhuận một tháng ít nhất 5-10%, và trong vòng 6 tháng có thể có 1-2 tháng thua lỗ tối đa -8%.
Còn day/swing thì số phần trăm có thể điều chỉnh lại để phù hợp với tiêu chí ưu tiên bảo toàn vốn, lợi nhuận bền
vững cho thời gian dài." Clarified by choice the same day: scalping = mean monthly >= 5%; day/swing = the
"capital preservation" profile.
