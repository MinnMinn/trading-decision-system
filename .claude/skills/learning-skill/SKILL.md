---
name: learning-skill
description: Use for post-trade review synthesis, cross-trade pattern detection, and drafting controlled system-improvement proposals under the institutional trading system. Invoked by LearningAgent as part of /review and /improve. Cannot modify safety-critical rules — see Governance below.
---

# LearningSkill

Implements the master spec's §26–31 self-learning loop: Observe → Measure → Identify Pattern → Propose Improvement → Validate → Approve → Deploy. Design note: `docs/architecture/SYSTEM-DESIGN.md` §11.

## Procedure

### `/review` (single closed trade)
Run the Post-Trade Review template (master spec §26) against the trade file JournalSkill already updated: Original Thesis vs. Outcome, was execution per plan, root-cause category (from the fixed list in `trade-file.schema.json`), MFE/MAE. Do not draw system-wide conclusions from one trade — that's `/improve`'s job, and only with sufficient sample size (§4 below).

### `/improve` (system-wide proposal)
1. **Observe**: scan `trades/index.jsonl` for a pattern — a repeated `root_cause`, a setup type with a poor realized R-distribution, a methodology mode that never seems to pass, etc.
2. **Measure**: report the actual sample size, win rate, expectancy, average R, and note explicitly whether that sample size is sufficient for the specific claim being made (master spec §30 — do not treat 30/50/100 as a universal threshold; state why the number you have is or isn't enough for *this* metric's variance).
3. **Propose**: use the exact template from master spec §31 — Current Rule / Observed Problem / Evidence / Proposed Change / Expected Benefit / Potential Risk / Validation Required / Recommendation (KEEP/TEST/ADOPT/REJECT).
4. **Never silently apply the change.** Output the proposal and stop. A human edits `docs/architecture/SYSTEM-DESIGN.md`, `docs/architecture/risk-config.json`, or the relevant Skill file directly if they accept it.

## Governance — hard boundary (master spec §29, §32)

LearningSkill/LearningAgent may propose changes to: scoring-rubric point allocations, methodology-mode thresholds (within the master spec's own stated defaults unless the human explicitly asks to change the defaults themselves), setup-detection heuristics, or Skill procedures.

It may **never** directly edit, and must always flag as requiring explicit human action even when proposing a change to: the per-trade risk ceiling (`risk-config.json` `max_risk_pct`), the instrument allowlist, the stop-loss/invalidation requirements, the Analysis≠Execution separation, or anything in `docs/architecture/SYSTEM-DESIGN.md` §1/§7/§9. These are safety-critical and structurally protected — a proposal touching them must say so explicitly and recommend the human edit the design doc directly rather than attempt to.
