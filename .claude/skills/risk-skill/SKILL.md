---
name: risk-skill
description: Use whenever a trade plan needs position sizing, R:R calculation, or a hard-safety-rule check under the institutional trading system. Invoked by RiskAgent as part of /analyze, /entry, /risk, and /execute — this is the ONLY skill authorized to approve a position size.
---

# RiskSkill

Owns capital preservation — the master spec's top priority. Full design: `docs/architecture/SYSTEM-DESIGN.md` §7. Config: `docs/architecture/risk-config.json`. Output schema: `docs/architecture/schemas/risk-calculation.schema.json`.

## Procedure

1. **Read config** (`docs/architecture/risk-config.json`) for `account_equity` and `default_risk_pct`, unless the caller supplied explicit overrides. If `account_equity` is 0 or missing, refuse to size a position and ask the user for it — never assume a number.
2. **Check the consecutive-loss throttle**: scan `trades/index.jsonl` (or regenerate it via JournalSkill first) for the most recent closed, non-rehearsal trades. If the last 2+ are `LOSS`, apply `throttled_risk_pct` from the config instead of `default_risk_pct`, and state that the throttle is active and why. Throttle resets only per the config's `reset_condition` (one subsequent WIN, or an explicit logged override) — never silently after a time window.
3. **Compute position size**: `position_size = (account_equity × risk_pct) / |entry − stop_loss|` (in the instrument's native units). Show the arithmetic, not just the result.
4. **Compute R:R at each target**: `(target − entry) / (entry − stop_loss)` (sign-adjusted for direction).
5. **Run the hard checks** (all must be true to output anything but a FAIL):
   - `risk_pct ≤ max_risk_pct` from `docs/architecture/risk-config.json` — THE per-trade ceiling for every order path, manual and automated, read through `scripts/trading_env.py` `MAX_RISK_PCT`. Never overridable without an explicit typed exception that gets logged in the resulting trade file. Read the value; do not restate it here — until 2026-09-17 this line's own copy (1%) disagreed with `trading_env.py` (3%), so the pilot sized at three times what this skill enforced.
   - A stop-loss price exists and sits beyond the pattern's invalidation point (below the Spring's low / above the Upthrust's high, per WyckoffSkill's read) — not an arbitrary distance.
   - Price invalidation, thesis invalidation, and data invalidation (master spec §21) are each stated, not just the stop price.
   - If the request is to average down, widen an existing stop, or remove a stop on an open position — **refuse outright**, do not merely warn. State why (master spec §25, rules 3–5).
6. **Emit the `RiskCalculation` object** per the schema, including `hard_checks` and `consecutive_losses`/`throttle_active`.

## What this skill never does

- Never sizes a position without a real, config-sourced or explicitly-supplied account equity.
- Never approves risk above `risk-config.json` `max_risk_pct` silently — and refuses outright if that value is unreadable, rather than assuming one.
- Never treats "the setup looks certain" as a reason to increase size (master spec §20).
