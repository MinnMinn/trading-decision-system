---
description: Separately-permissioned execution step. NO broker/exchange integration exists in v1 -- this produces a manual execution ticket only, it never places a real order.
argument-hint: <trade id, must already exist from /analyze or /entry with a TRADE verdict>
---

**This command cannot place a real trade.** No broker/exchange API is wired into this system (`docs/architecture/SYSTEM-DESIGN.md` §9, §12). Its entire job is:

1. Require an **explicit typed confirmation** distinct from having just run `/analyze` or `/entry` — the user must type something equivalent to "confirm execute `<trade id>`" in this same turn; a prior TRADE verdict alone is never sufficient (master spec §22, "Analysis ≠ Execution").
2. Read `trades/<id>.md`; refuse if its verdict wasn't `TRADE`, if it's a `rehearsal_mode: true` record (mock-data trades cannot be executed, live or manual), or if it's already `status: OPEN`/`CLOSED`.
3. Re-run **risk-agent**'s hard checks one final time against current data (not the possibly-stale numbers from when `/analyze` first ran) — if anything now fails, refuse and say why, even if it originally passed.
4. If all checks pass, print a **manual execution ticket**: exact instrument, direction, order type (per `docs/architecture/SYSTEM-DESIGN.md` §7's Market-order recommendation), size, stop-loss, and take-profit levels — formatted for the human to enter by hand into their own exchange/broker interface.
5. Update the trade file's `status` to `OPEN` via journal-skill **only after the user confirms they actually placed the order** — never assume execution happened just because the ticket was printed.
6. Never silently treat this command as "upgraded" to real execution. If the user asks to wire up real broker/exchange execution, that is a new, separate engineering task requiring Security review first (new external trust boundary + credential handling) — say so and do not attempt it inline.
