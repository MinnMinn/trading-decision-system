---
description: Post-trade review on a closed trade — dispatches learning-agent, then journal-skill persists the result.
argument-hint: <trade id> <result: WIN|LOSS|BREAKEVEN> <exit price> [root_cause] [notes]
---

1. Read `trades/<id>.md` (must exist; must be `status: OPEN` or `PLANNED`, moving to `CLOSED`).
2. Dispatch **learning-agent** for the single-trade Post-Trade Review (`.claude/skills/learning-skill/SKILL.md`'s `/review` procedure): Original Thesis vs. Outcome, Execution fidelity, root-cause category from the fixed list, MFE/MAE if known.
3. Invoke **journal-skill** to write the close-out fields (`date_closed`, `status: CLOSED`, `result`, `r_multiple`, `mfe`, `mae`, `exit_reason`, `root_cause`, `is_mistake`, `lessons`) into the trade file and append the Post-Trade Review section to its body, then regenerate `trades/index.jsonl` and both rollup views.
4. If this is the 2nd consecutive LOSS (non-rehearsal), state plainly that RiskSkill's consecutive-loss throttle is now active for the next trade.
