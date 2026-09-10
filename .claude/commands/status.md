---
description: Data-source validation snapshot, open-position summary, and current rollup views.
---

**Model gate (SYSTEM-DESIGN.md §14).** Step 2 below contains a judgment (the quick invalidation pass on open positions). If you are running as Haiku, do not execute this command in this session: dispatch one `general-purpose` subagent with `model: sonnet` to run it and relay its output verbatim.

1. For crypto instruments, run `scripts/fetch-binance-klines.sh` (this connector is live and verified — see `docs/architecture/data-sources.md`) and report `crypto_market_data: AVAILABLE` on success. Check `data/live/mt5-bridge/` freshness for commodities per `docs/architecture/mt5-bridge.md` — `AVAILABLE` if a fresh bridge file exists, else `UNAVAILABLE`. Check for a configured CoinGlass key. Report the full `DataValidationStatus` for whatever instrument(s) the user cares about (or all mock-covered instruments if none specified).
2. Invoke journal-skill to regenerate `trades/index.jsonl` and the rollup views, then summarize: open positions (`status: OPEN`) with their current invalidation status (quick pass, not a full `/exit`), and headline stats from `docs/edge-log/EDGE-LOG.md` (trade count, win rate, expectancy — excluding rehearsal-mode trades) and `docs/mistakes/MISTAKE-DB.md` (top repeated `root_cause`, if any).
3. State plainly whether the system is currently in REHEARSAL MODE (any source MOCK) or live.
