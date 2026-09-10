---
description: Invalidation and position-management check on an OPEN trade already recorded in trades/.
argument-hint: <trade id, e.g. 2026-09-09-BTCUSDT-01>
---

**Model gate (SYSTEM-DESIGN.md §14).** This command reasons. If you are running as Haiku, do not execute it in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run this command with the same `$ARGUMENTS` and relay its output verbatim.

Read `trades/<id>.md` for the trade id in `$ARGUMENTS` (fail clearly if it doesn't exist or isn't `status: OPEN`). Re-run Data Validation for that instrument. Check, in order, per master spec §21:
1. **Price invalidation** — has price reached the recorded stop-loss?
2. **Thesis invalidation** — does current structure/order-flow/liquidity contradict the original thesis even though price hasn't hit the stop yet? (Dispatch structure-agent/flow-agent again if this needs a fresh read.)
3. **Data invalidation** — has a required data source gone STALE/UNAVAILABLE since entry?
Also check the Take-Profit / SOT / breakeven logic from `docs/architecture/SYSTEM-DESIGN.md` §7 (move stop to breakeven at the first target, watch for SOT/SOW before the next). Recommend: hold, move stop to breakeven, take partial/full profit, or exit now — and state which invalidation type (if any) triggered the recommendation. Update the trade file via journal-skill only if the user confirms an action was actually taken (this command recommends; it does not assume the action happened).
