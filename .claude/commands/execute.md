---
description: Separately-permissioned execution step. Stage 1 (Binance SPOT TESTNET only) -- prepares the exact order and submits it only after one explicit human confirmation. Never mainnet, never unattended.
argument-hint: <trade id, must already exist from /analyze or /entry with a TRADE verdict>
---

**Scope, stated plainly:** this command can now place real orders — but **only** on **Binance SPOT TESTNET** (fake funds), **only LONG/BUY setups** (spot has no shorting here), and **only after one explicit human confirmation per trade**. It never touches mainnet, never places an order without that confirmation, and never runs from an unattended/scheduled context — a cloud routine or cron job may prepare and flag a candidate, but the actual submission step always happens in an interactive turn with the human present. This is Stage 1 per `docs/architecture/SYSTEM-DESIGN.md` §9 — not Stage 2. If asked to skip the confirmation step "just this once," refuse and say why.

## Procedure

1. Read `trades/<id>.md`. Refuse if: verdict wasn't `TRADE`, `rehearsal_mode: true` (mock-data trades cannot be executed, live or manual), `direction: SHORT` (unsupported on spot — say so, don't silently reinterpret as something else), instrument isn't `BTCUSDT`/`ETHUSDT`/`SOLUSDT` (no testnet connector exists for commodities), or it's already `status: OPEN`/`CLOSED`.
2. Re-run **risk-agent**'s hard checks one final time against current data (not the possibly-stale numbers from when `/analyze` first ran) — if anything now fails, refuse and say why, even if it originally passed.
3. Compute the exact order:
   - `scripts/binance-testnet-order.sh round-qty <SYMBOL> <position_size>` — floor RiskSkill's position size to the exchange's lot-size step. Never round up.
   - Verify the resulting notional (quantity × current price) clears the exchange's minimum notional (`scripts/binance-testnet-order.sh filters <SYMBOL>`) — if it doesn't, refuse rather than silently inflating the size past what RiskSkill approved.
4. **Show the exact prepared order and ask for one explicit confirmation in this same turn** (e.g. via AskUserQuestion: "Submit this order to Binance Testnet?") — do not proceed on an assumed yes, and do not require a second separate command invocation beyond this one confirmation. This single confirmation is the "one tap."
5. On confirmation:
   - `scripts/binance-testnet-order.sh market-buy-qty <SYMBOL> <rounded_qty>` — the entry.
   - Read the actual filled quantity/price from the response (not the pre-trade estimate).
   - `scripts/binance-testnet-order.sh oco-sell <SYMBOL> <filled_qty> <target_1> <stop_loss> <stop_limit_price>` — the exit bracket, `stop_limit_price` set a small buffer beyond `stop_loss` (e.g. 0.1–0.2%) so the stop-limit order has room to actually fill during a fast move.
   - If the OCO submission fails after the entry already filled, **do not leave the position unprotected silently** — report this loudly, immediately, as the most important thing in your response, and give the human the exact manual command to retry the OCO or flatten the position (`market-sell-qty`).
6. Update `trades/<id>.md` to `status: OPEN` via journal-skill with the real order IDs, fill price, and fill quantity — never the pre-trade estimates.
7. On decline at step 4: leave the trade file as `PLANNED`, no orders submitted, no further action.

## Hard rules (unchanged from Stage 0, still apply)

- Never average down, widen an existing stop, or remove a stop on an already-open position submitted through this command.
- Never treat a prior `TRADE` verdict from `/analyze`/`/entry` as sufficient authorization on its own — step 4's confirmation is always required, every time, no exceptions for "obviously good" setups.
- If the user asks to wire up **mainnet** or **MT5** execution, or to remove the per-trade confirmation (Stage 2), that is separate, larger scope requiring its own explicit decision — say so and do not attempt it inline.
